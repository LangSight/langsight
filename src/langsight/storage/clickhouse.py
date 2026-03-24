"""
ClickHouse storage backend — for production deployments at scale.

Stores time-series health check results and tool call spans in ClickHouse,
optimised for the queries LangSight runs:
  - "What is the success rate of postgres-mcp/query over the last 24h?"
  - "What is the p95 latency per tool over the last 7 days?"
  - "Which tools are degrading vs. the 7-day baseline?"
  - "What did this MCP server cost us this week?"

Uses clickhouse-connect (async HTTP) — no native driver needed.

Schema design:
  mcp_health_results   — MergeTree, partitioned by month, TTL 90 days
  mcp_tool_calls       — MergeTree, partitioned by month, TTL 90 days
  mv_tool_reliability  — Materialized view: hourly aggregations per tool

Switch from SQLite → ClickHouse in .langsight.yaml:
  storage:
    mode: clickhouse
    clickhouse_url: http://localhost:8123
    clickhouse_database: langsight
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import clickhouse_connect
import structlog

from langsight.models import HealthCheckResult, PreventionConfig, ServerStatus
from langsight.sdk.models import ToolCallSpan

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------

_DDL = [
    # Health check results — full fidelity, 90-day TTL
    """
    CREATE TABLE IF NOT EXISTS mcp_health_results (
        server_name  String,
        status       LowCardinality(String),
        latency_ms   Nullable(Float64),
        tools_count  UInt16 DEFAULT 0,
        schema_hash  Nullable(String),
        error        Nullable(String),
        checked_at   DateTime64(3, 'UTC'),
        project_id   String DEFAULT ''
    )
    ENGINE = MergeTree()
    PARTITION BY toYYYYMM(checked_at)
    ORDER BY (server_name, checked_at)
    TTL toDateTime(checked_at) + INTERVAL 90 DAY
    SETTINGS index_granularity = 8192
    """,
    # Migration: backfill project_id on existing mcp_health_results rows.
    # Runs after CREATE so the table always exists. IF NOT EXISTS is idempotent.
    "ALTER TABLE mcp_health_results ADD COLUMN IF NOT EXISTS project_id String DEFAULT ''",
    # Tool call spans from the SDK / OTLP — 90-day TTL
    # parent_span_id enables multi-agent tree reconstruction
    # span_type: tool_call | agent | handoff
    # Note: session_id / parent_span_id / agent_name use String DEFAULT ''
    # (empty string = absent) because ClickHouse ORDER BY cannot contain Nullable columns.
    # Query pattern: WHERE session_id != '' to filter sessions.
    # input_json / output_json: P5.1 payload capture — Nullable, omitted when redact_payloads=True
    """
    CREATE TABLE IF NOT EXISTS mcp_tool_calls (
        span_id        String,
        parent_span_id String DEFAULT '',
        span_type      LowCardinality(String) DEFAULT 'tool_call',
        trace_id       String DEFAULT '',
        session_id     String DEFAULT '',
        server_name    String,
        tool_name      String,
        started_at     DateTime64(3, 'UTC'),
        ended_at       DateTime64(3, 'UTC'),
        latency_ms     Float64,
        status         LowCardinality(String),
        error          Nullable(String),
        agent_name     String DEFAULT '',
        input_json     Nullable(String),
        output_json    Nullable(String),
        llm_input      Nullable(String),
        llm_output     Nullable(String),
        replay_of      String DEFAULT '',
        project_id     String DEFAULT '',
        input_tokens   Nullable(UInt32),
        output_tokens  Nullable(UInt32),
        model_id       String DEFAULT ''
    )
    ENGINE = MergeTree()
    PARTITION BY toYYYYMM(started_at)
    ORDER BY (server_name, tool_name, started_at, span_id)
    TTL toDateTime(started_at) + INTERVAL 90 DAY
    SETTINGS index_granularity = 8192
    """,
    # Schema snapshots — lightweight, no TTL
    """
    CREATE TABLE IF NOT EXISTS mcp_schema_snapshots (
        server_name  String,
        schema_hash  String,
        tools_count  UInt16 DEFAULT 0,
        recorded_at  DateTime64(3, 'UTC')
    )
    ENGINE = MergeTree()
    ORDER BY (server_name, recorded_at)
    SETTINGS index_granularity = 8192
    """,
    # Migration: drop old mv_tool_reliability if it lacks project_id so the
    # CREATE below recreates it with multi-tenant support. Safe: POPULATE
    # rebuilds from the raw mcp_tool_calls table on first startup.
    "DROP VIEW IF EXISTS mv_tool_reliability",
    # Materialized view: pre-aggregated tool reliability per (project, tool, hour)
    # Drives the Tool Reliability page in the dashboard without real-time fan-out
    """
    CREATE MATERIALIZED VIEW IF NOT EXISTS mv_tool_reliability
    ENGINE = SummingMergeTree()
    ORDER BY (project_id, server_name, tool_name, hour)
    POPULATE
    AS SELECT
        project_id,
        server_name,
        tool_name,
        toStartOfHour(started_at)           AS hour,
        count()                              AS total_calls,
        countIf(status = 'success')          AS success_calls,
        countIf(status = 'error')            AS error_calls,
        countIf(status = 'timeout')          AS timeout_calls,
        sum(latency_ms)                      AS total_latency_ms,
        max(latency_ms)                      AS max_latency_ms
    FROM mcp_tool_calls
    GROUP BY project_id, server_name, tool_name, hour
    """,
    # Materialized view: agent sessions — one row per session
    # Drives langsight sessions + GET /api/agents/sessions
    """
    CREATE MATERIALIZED VIEW IF NOT EXISTS mv_agent_sessions
    ENGINE = AggregatingMergeTree()
    ORDER BY (session_id, agent_name)
    POPULATE
    AS SELECT
        session_id,
        agent_name,
        min(started_at)                                      AS first_call_at,
        max(ended_at)                                        AS last_call_at,
        count()                                              AS total_spans,
        countIf(span_type = 'tool_call')                     AS tool_calls,
        countIf(status != 'success' AND span_type='tool_call') AS failed_calls,
        sum(latency_ms)                                      AS total_latency_ms,
        groupUniqArray(server_name)                          AS servers_used
    FROM mcp_tool_calls
    WHERE session_id != ''
    GROUP BY session_id, agent_name
    """,
    # v0.3 Session health tags — one row per session, auto-classified
    # Uses ReplacingMergeTree so re-tagging a session replaces the old row
    """
    CREATE TABLE IF NOT EXISTS session_health_tags (
        session_id   String,
        health_tag   LowCardinality(String),
        details      Nullable(String),
        project_id   String DEFAULT '',
        tagged_at    DateTime64(3, 'UTC')
    )
    ENGINE = ReplacingMergeTree(tagged_at)
    ORDER BY (session_id)
    SETTINGS index_granularity = 8192
    """,
]


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class ClickHouseBackend:
    """ClickHouse storage backend for production LangSight deployments.

    Usage:
        async with await ClickHouseBackend.open(
            host="localhost", port=8123, database="langsight"
        ) as db:
            await db.save_health_result(result)
            await db.save_tool_call_span(span)

    Switch from SQLite via .langsight.yaml:
        storage:
          mode: clickhouse
          clickhouse_url: http://localhost:8123
          clickhouse_database: langsight
    """

    def __init__(self, client: clickhouse_connect.driver.AsyncClient) -> None:
        self._client = client

    @classmethod
    async def open(
        cls,
        host: str = "localhost",
        port: int = 8123,
        database: str = "langsight",
        username: str = "default",
        password: str = "",
    ) -> ClickHouseBackend:
        """Open a ClickHouse connection and create schema if needed.

        Creates the database automatically if it doesn't exist.
        """
        # Connect without database first to create it if missing
        admin = await clickhouse_connect.get_async_client(
            host=host,
            port=port,
            username=username,
            password=password,
        )
        await admin.command(f"CREATE DATABASE IF NOT EXISTS `{database}`")
        await admin.close()

        client = await clickhouse_connect.get_async_client(
            host=host,
            port=port,
            database=database,
            username=username,
            password=password,
        )

        # Create schema (idempotent)
        for ddl in _DDL:
            await client.command(ddl)

        logger.info(
            "storage.clickhouse.opened",
            host=host,
            port=port,
            database=database,
        )
        return cls(client)

    # ---------------------------------------------------------------------------
    # StorageBackend interface
    # ---------------------------------------------------------------------------

    async def save_health_result(self, result: HealthCheckResult) -> None:
        """Persist a health check result."""
        await self._client.insert(
            "mcp_health_results",
            [
                [
                    result.server_name,
                    result.status.value,
                    result.latency_ms,
                    result.tools_count,
                    result.schema_hash,
                    result.error,
                    result.checked_at,
                    result.project_id,
                ]
            ],
            column_names=[
                "server_name",
                "status",
                "latency_ms",
                "tools_count",
                "schema_hash",
                "error",
                "checked_at",
                "project_id",
            ],
        )
        logger.debug("storage.clickhouse.health_saved", server=result.server_name)

    async def get_latest_schema_hash(self, server_name: str) -> str | None:
        """Return the most recent schema hash for a server."""
        result = await self._client.query(
            """
            SELECT schema_hash
            FROM mcp_schema_snapshots
            WHERE server_name = {server_name:String}
            ORDER BY recorded_at DESC
            LIMIT 1
            """,
            parameters={"server_name": server_name},
        )
        rows = result.result_rows
        return rows[0][0] if rows else None

    async def save_schema_snapshot(
        self,
        server_name: str,
        schema_hash: str,
        tools_count: int,
    ) -> None:
        """Persist a schema snapshot."""
        await self._client.insert(
            "mcp_schema_snapshots",
            [[server_name, schema_hash, tools_count, datetime.now(UTC)]],
            column_names=["server_name", "schema_hash", "tools_count", "recorded_at"],
        )

    async def get_health_history(
        self,
        server_name: str,
        limit: int = 10,
        project_id: str | None = None,
    ) -> list[HealthCheckResult]:
        """Return the N most recent health results, newest first.

        When project_id is set, returns only results for that project OR
        global results (project_id='') so CLI-triggered checks are always visible.
        """
        params: dict[str, Any] = {"server_name": server_name, "limit": limit}
        project_filter = ""
        if project_id:
            project_filter = "AND (project_id = {project_id:String} OR project_id = '')"
            params["project_id"] = project_id
        result = await self._client.query(
            f"""
            SELECT server_name, status, latency_ms, tools_count,
                   schema_hash, error, checked_at, project_id
            FROM mcp_health_results
            WHERE server_name = {{server_name:String}}
            {project_filter}
            ORDER BY checked_at DESC
            LIMIT {{limit:UInt32}}
            """,
            parameters=params,
        )
        return [_row_to_result(row) for row in result.result_rows]

    async def close(self) -> None:
        """Close the ClickHouse connection."""
        await self._client.close()
        logger.debug("storage.clickhouse.closed")

    # ---------------------------------------------------------------------------
    # ClickHouse-specific: tool call spans
    # ---------------------------------------------------------------------------

    _SPAN_COLUMNS = [
        "span_id",
        "parent_span_id",
        "span_type",
        "trace_id",
        "session_id",
        "server_name",
        "tool_name",
        "started_at",
        "ended_at",
        "latency_ms",
        "status",
        "error",
        "agent_name",
        "input_json",
        "output_json",
        "llm_input",
        "llm_output",
        "replay_of",
        "project_id",
        "input_tokens",
        "output_tokens",
        "model_id",
    ]

    def _span_row(self, s: ToolCallSpan) -> list[Any]:
        import json

        # None → '' for String DEFAULT '' columns (no Nullable in ORDER BY)
        input_json: str | None = None
        if s.input_args is not None:
            try:
                input_json = json.dumps(s.input_args, default=str)
            except Exception:  # noqa: BLE001
                input_json = str(s.input_args)

        return [
            s.span_id,
            s.parent_span_id or "",
            s.span_type,
            s.trace_id or "",
            s.session_id or "",
            s.server_name,
            s.tool_name,
            s.started_at,
            s.ended_at,
            s.latency_ms,
            s.status.value,
            s.error,  # Nullable(String) — kept for error messages
            s.agent_name or "",
            input_json,  # Nullable(String) — None when redacted
            s.output_result,  # Nullable(String) — None when redacted
            s.llm_input,  # Nullable(String) — LLM prompt (agent spans only)
            s.llm_output,  # Nullable(String) — LLM completion (agent spans only)
            s.replay_of or "",
            s.project_id or "",
            s.input_tokens,  # Nullable(UInt32)
            s.output_tokens,  # Nullable(UInt32)
            s.model_id or "",
        ]

    async def save_tool_call_span(self, span: ToolCallSpan) -> None:
        """Persist a single span (tool_call, agent, or handoff)."""
        await self._client.insert(
            "mcp_tool_calls",
            [self._span_row(span)],
            column_names=self._SPAN_COLUMNS,
        )

    async def save_tool_call_spans(self, spans: list[ToolCallSpan]) -> None:
        """Batch insert multiple spans."""
        if not spans:
            return
        rows = [self._span_row(s) for s in spans]
        await self._client.insert(
            "mcp_tool_calls",
            rows,
            column_names=self._SPAN_COLUMNS,
        )
        logger.debug("storage.clickhouse.spans_saved", count=len(spans))

    async def get_distinct_span_server_names(
        self, project_id: str | None = None
    ) -> set[str]:
        """Return distinct server_name values from tool call spans.

        Used by the Discover endpoint to find MCP servers that have sent
        traces but are not yet registered in the server catalog.
        """
        params: dict[str, Any] = {}
        project_filter = ""
        if project_id:
            project_filter = "AND project_id = {project_id:String}"
            params["project_id"] = project_id

        result = await self._client.query(
            f"""
            SELECT DISTINCT server_name
            FROM mcp_tool_calls
            WHERE server_name != ''
              AND span_type = 'tool_call'
              {project_filter}
            ORDER BY server_name
            LIMIT 100
            """,
            parameters=params,
        )
        return {row[0] for row in result.result_rows}

    async def get_distinct_span_agent_names(
        self, project_id: str | None = None
    ) -> set[str]:
        """Return distinct agent_name values from spans.

        Used by the Discover endpoint to find agents that have sent
        traces but are not yet registered in the agent catalog.
        """
        params: dict[str, Any] = {}
        project_filter = ""
        if project_id:
            project_filter = "AND project_id = {project_id:String}"
            params["project_id"] = project_id

        result = await self._client.query(
            f"""
            SELECT DISTINCT agent_name
            FROM mcp_tool_calls
            WHERE agent_name != ''
              {project_filter}
            ORDER BY agent_name
            LIMIT 100
            """,
            parameters=params,
        )
        return {row[0] for row in result.result_rows}

    async def get_tool_reliability(
        self,
        server_name: str | None = None,
        hours: int = 24,
        project_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return tool reliability metrics for the given time window.

        Uses the mv_tool_reliability materialized view for fast aggregation.
        project_id is now a first-class column in the MV — no base-table fallback needed.
        """
        params: dict[str, Any] = {"hours": hours}
        where = "WHERE hour >= now() - INTERVAL {hours:UInt32} HOUR"
        if project_id:
            where += " AND project_id = {project_id:String}"
            params["project_id"] = project_id
        if server_name:
            where += " AND server_name = {server_name:String}"
            params["server_name"] = server_name
        result = await self._client.query(
            f"""
            SELECT
                server_name,
                tool_name,
                sum(total_calls)       AS total_calls,
                sum(success_calls)     AS success_calls,
                sum(error_calls)       AS error_calls,
                sum(timeout_calls)     AS timeout_calls,
                sum(total_latency_ms)  AS total_latency_ms,
                max(max_latency_ms)    AS max_latency_ms
            FROM mv_tool_reliability
            {where}
            GROUP BY server_name, tool_name
            ORDER BY total_calls DESC
            """,
            parameters=params,
        )

        rows = []
        for row in result.result_rows:
            total = int(row[2]) or 1  # avoid div-by-zero
            success = int(row[3])
            total_lat = float(row[6])
            rows.append(
                {
                    "server_name": row[0],
                    "tool_name": row[1],
                    "total_calls": int(row[2]),
                    "success_calls": success,
                    "error_calls": int(row[4]),
                    "timeout_calls": int(row[5]),
                    "success_rate_pct": round(success / total * 100, 2),
                    "avg_latency_ms": round(total_lat / total, 2),
                    "max_latency_ms": float(row[7]),
                }
            )
        return rows

    # ---------------------------------------------------------------------------
    # Agent sessions — multi-agent tracing queries
    # ---------------------------------------------------------------------------

    async def get_agent_sessions(
        self,
        hours: int = 24,
        agent_name: str | None = None,
        limit: int = 50,
        project_id: str | None = None,
        health_tag: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return recent agent sessions with call counts, failures, and health tags.

        Uses mv_agent_sessions materialized view for fast aggregation.
        JOINs with session_health_tags to include v0.3 health tag per session.
        """
        cols = [
            "session_id",
            "agent_name",
            "first_call_at",
            "last_call_at",
            "tool_calls",
            "failed_calls",
            "total_latency_ms",
            "servers_used",
            "duration_ms",
            "health_tag",  # v0.3
            "total_input_tokens",
            "total_output_tokens",
            "model_id",
            "agents_used",
        ]

        # mv_agent_sessions does not include project_id — query base table when filtering by project
        if project_id:
            where = (
                "WHERE t.started_at >= now() - INTERVAL {hours:UInt32} HOUR"
                " AND t.session_id != ''"
                " AND t.project_id = {project_id:String}"
            )
            params: dict[str, Any] = {"hours": hours, "limit": limit, "project_id": project_id}
            having = ""
            if agent_name:
                having = "HAVING has(groupUniqArray(t.agent_name), {agent_name:String})"
                params["agent_name"] = agent_name
            if health_tag:
                where += " AND sht.health_tag = {health_tag:String}"
                params["health_tag"] = health_tag
            result = await self._client.query(
                f"""
                SELECT
                    t.session_id,
                    anyIf(t.agent_name, t.agent_name != '')              AS agent_name,
                    min(t.started_at)                                    AS first_call_at,
                    max(t.ended_at)                                      AS last_call_at,
                    countIf(t.span_type = 'tool_call')                  AS tool_calls,
                    countIf(t.status != 'success' AND t.span_type = 'tool_call') AS failed_calls,
                    sum(t.latency_ms)                                    AS total_latency_ms,
                    groupUniqArray(t.server_name)                       AS servers_used,
                    dateDiff('millisecond', min(t.started_at), max(t.ended_at)) AS duration_ms,
                    any(sht.health_tag)                                  AS health_tag,
                    sum(t.input_tokens)                                  AS total_input_tokens,
                    sum(t.output_tokens)                                 AS total_output_tokens,
                    anyIf(t.model_id, t.model_id != '')                  AS model_id,
                    arrayFilter(x -> x != '', groupUniqArray(t.agent_name)) AS agents_used
                FROM mcp_tool_calls t
                LEFT JOIN (SELECT session_id, health_tag FROM session_health_tags FINAL) sht
                    ON t.session_id = sht.session_id
                {where}
                GROUP BY t.session_id
                {having}
                ORDER BY first_call_at DESC
                LIMIT {{limit:UInt32}}
                """,
                parameters=params,
            )
            return [dict(zip(cols, row, strict=False)) for row in result.result_rows]

        # No project_id filter — use the fast MV, join health tags separately
        where = "WHERE mv.first_call_at >= now() - INTERVAL {hours:UInt32} HOUR"
        params = {"hours": hours, "limit": limit}

        if agent_name:
            where += " AND mv.agent_name = {agent_name:String}"
            params["agent_name"] = agent_name
        if health_tag:
            where += " AND sht.health_tag = {health_tag:String}"
            params["health_tag"] = health_tag

        result = await self._client.query(
            f"""
            SELECT
                mv.session_id,
                any(mv.agent_name)                                          AS agent_name,
                min(mv.first_call_at)                                       AS first_call_at,
                max(mv.last_call_at)                                        AS last_call_at,
                sum(mv.tool_calls)                                          AS tool_calls,
                sum(mv.failed_calls)                                        AS failed_calls,
                sum(mv.total_latency_ms)                                    AS total_latency_ms,
                groupUniqArrayArray(mv.servers_used)                        AS servers_used,
                dateDiff('millisecond', min(mv.first_call_at), max(mv.last_call_at)) AS duration_ms,
                any(sht.health_tag)                                         AS health_tag,
                sum(tok.total_input_tokens)                                 AS total_input_tokens,
                sum(tok.total_output_tokens)                                AS total_output_tokens,
                anyIf(tok.model_id, tok.model_id != '')                     AS model_id,
                arrayFilter(x -> x != '', groupUniqArray(mv.agent_name))    AS agents_used
            FROM mv_agent_sessions mv
            LEFT JOIN (
                SELECT session_id, agent_name,
                       sum(input_tokens) AS total_input_tokens,
                       sum(output_tokens) AS total_output_tokens,
                       anyIf(model_id, model_id != '') AS model_id
                FROM mcp_tool_calls
                WHERE session_id != '' AND agent_name != ''
                GROUP BY session_id, agent_name
            ) tok ON mv.session_id = tok.session_id AND mv.agent_name = tok.agent_name
            LEFT JOIN (SELECT session_id, health_tag FROM session_health_tags FINAL) sht
                ON mv.session_id = sht.session_id
            {where}
            GROUP BY mv.session_id
            ORDER BY first_call_at DESC
            LIMIT {{limit:UInt32}}
            """,
            parameters=params,
        )

        return [dict(zip(cols, row, strict=False)) for row in result.result_rows]

    async def get_session_trace(
        self,
        session_id: str,
        project_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return all spans for a session, ordered by start time.

        Returns the full flat list — callers reconstruct the tree
        using parent_span_id.
        """
        where = "session_id = {session_id:String}"
        params: dict[str, Any] = {"session_id": session_id}
        if project_id:
            where += " AND project_id = {project_id:String}"
            params["project_id"] = project_id

        result = await self._client.query(
            f"""
            SELECT
                span_id, parent_span_id, span_type,
                server_name, tool_name, agent_name,
                started_at, ended_at, latency_ms,
                status, error, trace_id,
                input_json, output_json,
                llm_input, llm_output,
                replay_of, project_id,
                input_tokens, output_tokens, model_id
            FROM mcp_tool_calls
            WHERE {where}
            ORDER BY started_at ASC
            """,
            parameters=params,
        )

        cols = [
            "span_id",
            "parent_span_id",
            "span_type",
            "server_name",
            "tool_name",
            "agent_name",
            "started_at",
            "ended_at",
            "latency_ms",
            "status",
            "error",
            "trace_id",
            "input_json",
            "output_json",
            "llm_input",
            "llm_output",
            "replay_of",
            "project_id",
            "input_tokens",
            "output_tokens",
            "model_id",
        ]
        rows = [dict(zip(cols, row, strict=False)) for row in result.result_rows]
        # Ensure timestamps carry UTC timezone — ClickHouse DateTime64('UTC')
        # returns naive datetimes via clickhouse-connect, causing JS to
        # interpret them as local time instead of UTC.
        for row in rows:
            for key in ("started_at", "ended_at"):
                dt = row.get(key)
                if dt is not None and hasattr(dt, "tzinfo") and dt.tzinfo is None:
                    from datetime import UTC

                    row[key] = dt.replace(tzinfo=UTC)
        return rows

    async def compare_sessions(
        self,
        session_a: str,
        session_b: str,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        """Fetch both session traces and compute a diff.

        project_id is enforced at the storage level — each session is fetched
        with the project filter so cross-project comparisons return empty spans.

        Returns:
          session_a: flat span list for session A
          session_b: flat span list for session B
          diff: list of DiffEntry dicts describing per-position comparison
          summary: high-level counts (only_in_a, only_in_b, matched, diverged)
        """
        import asyncio

        spans_a, spans_b = await asyncio.gather(
            self.get_session_trace(session_a, project_id=project_id),
            self.get_session_trace(session_b, project_id=project_id),
        )

        diff, summary = _diff_spans(spans_a, spans_b)

        return {
            "session_a": session_a,
            "session_b": session_b,
            "spans_a": spans_a,
            "spans_b": spans_b,
            "diff": diff,
            "summary": summary,
        }

    async def get_baseline_stats(
        self,
        baseline_hours: int = 168,  # 7 days
        project_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return per-tool baseline statistics (mean + stddev) for anomaly detection.

        Computes statistics from hourly aggregated data in mv_tool_reliability.
        project_id is now a first-class column in the MV — no base-table fallback needed.
        """
        params: dict[str, Any] = {"baseline_hours": baseline_hours}
        project_filter = ""
        if project_id:
            project_filter = "AND project_id = {project_id:String}"
            params["project_id"] = project_id
        inner_query = f"""
            SELECT
                server_name,
                tool_name,
                hour,
                error_calls / greatest(total_calls, 1)       AS error_rate,
                total_latency_ms / greatest(total_calls, 1)  AS avg_latency
            FROM mv_tool_reliability
            WHERE hour >= now() - INTERVAL {{baseline_hours:UInt32}} HOUR
              AND total_calls > 0
              {project_filter}
            GROUP BY server_name, tool_name, hour, error_calls, total_calls, total_latency_ms
        """

        result = await self._client.query(
            f"""
            SELECT
                server_name,
                tool_name,
                avg(error_rate)          AS baseline_error_mean,
                stddevPop(error_rate)    AS baseline_error_stddev,
                avg(avg_latency)         AS baseline_latency_mean,
                stddevPop(avg_latency)   AS baseline_latency_stddev,
                count()                  AS sample_hours
            FROM ({inner_query})
            GROUP BY server_name, tool_name
            HAVING sample_hours >= 3
            ORDER BY server_name, tool_name
            """,
            parameters=params,
        )
        cols = [
            "server_name",
            "tool_name",
            "baseline_error_mean",
            "baseline_error_stddev",
            "baseline_latency_mean",
            "baseline_latency_stddev",
            "sample_hours",
        ]
        return [dict(zip(cols, row, strict=False)) for row in result.result_rows]

    async def get_cost_call_counts(
        self,
        hours: int = 24,
        project_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return aggregated tool-call counts for cost attribution.

        Groups by server, tool, agent, and session so higher-level cost reports
        can derive per-tool, per-agent, and per-session totals in Python while
        applying pricing rules consistently in one place.
        """
        where = "started_at >= now() - INTERVAL {hours:UInt32} HOUR"
        params: dict[str, Any] = {"hours": hours}
        if project_id:
            where += " AND project_id = {project_id:String}"
            params["project_id"] = project_id

        result = await self._client.query(
            f"""
            SELECT
                server_name,
                tool_name,
                nullIf(agent_name, '') AS agent_name,
                nullIf(session_id, '') AS session_id,
                nullIf(model_id, '')   AS model_id,
                count()                AS total_calls,
                sum(input_tokens)      AS input_tokens,
                sum(output_tokens)     AS output_tokens
            FROM mcp_tool_calls
            WHERE {where}
            GROUP BY server_name, tool_name, agent_name, session_id, model_id
            ORDER BY total_calls DESC, server_name, tool_name
            """,
            parameters=params,
        )

        cols = [
            "server_name",
            "tool_name",
            "agent_name",
            "session_id",
            "model_id",
            "total_calls",
            "input_tokens",
            "output_tokens",
        ]
        return [dict(zip(cols, row, strict=False)) for row in result.result_rows]

    # ---------------------------------------------------------------------------
    # Agent action lineage — DAG of agents, servers, and their relationships
    # ---------------------------------------------------------------------------

    async def get_lineage_graph(
        self,
        hours: int = 168,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        """Return nodes and edges for the agent action lineage DAG.

        Builds the graph from actual span data in mcp_tool_calls:
          - Agent-to-server edges from tool_call spans
          - Agent-to-agent edges from handoff spans
          - Node metrics derived from edge aggregations

        Args:
            hours: Look-back window (default 168 = 7 days).
            project_id: Optional project scope filter.

        Returns a dict with keys: window_hours, nodes, edges.
        """
        import asyncio

        agent_server_edges, handoff_edges, delegation_edges = await asyncio.gather(
            self._lineage_agent_server_edges(hours, project_id),
            self._lineage_handoff_edges(hours, project_id),
            self._lineage_delegation_edges(hours, project_id),
        )

        # ── Assemble unique nodes from edges ──────────────────────────────────
        agent_metrics: dict[str, dict[str, Any]] = {}
        server_metrics: dict[str, dict[str, Any]] = {}

        for edge in agent_server_edges:
            agent = edge["agent_name"]
            server = edge["server_name"]

            # Accumulate agent metrics
            if agent not in agent_metrics:
                agent_metrics[agent] = {
                    "total_calls": 0,
                    "error_count": 0,
                    "avg_latency_ms": 0.0,
                    "sessions": 0,
                    "_latency_sum": 0.0,
                    "_call_count_for_avg": 0,
                }
            am = agent_metrics[agent]
            am["total_calls"] += edge["call_count"]
            am["error_count"] += edge["error_count"]
            am["_latency_sum"] += edge["avg_latency_ms"] * edge["call_count"]
            am["_call_count_for_avg"] += edge["call_count"]
            am["sessions"] = max(am["sessions"], edge["session_count"])

            # Accumulate server metrics
            if server not in server_metrics:
                server_metrics[server] = {
                    "total_calls": 0,
                    "error_count": 0,
                    "avg_latency_ms": 0.0,
                    "_latency_sum": 0.0,
                    "_call_count_for_avg": 0,
                }
            sm = server_metrics[server]
            sm["total_calls"] += edge["call_count"]
            sm["error_count"] += edge["error_count"]
            sm["_latency_sum"] += edge["avg_latency_ms"] * edge["call_count"]
            sm["_call_count_for_avg"] += edge["call_count"]

        # Agents that only appear as handoff/delegation targets
        for edge in [*handoff_edges, *delegation_edges]:
            for agent in (edge["from_agent"], edge["to_agent"]):
                if agent and agent not in agent_metrics:
                    agent_metrics[agent] = {
                        "total_calls": 0,
                        "error_count": 0,
                        "avg_latency_ms": 0.0,
                        "sessions": 0,
                        "_latency_sum": 0.0,
                        "_call_count_for_avg": 0,
                    }

        # Finalize weighted-average latency
        for am in agent_metrics.values():
            if am["_call_count_for_avg"] > 0:
                am["avg_latency_ms"] = round(am["_latency_sum"] / am["_call_count_for_avg"], 2)
            del am["_latency_sum"]
            del am["_call_count_for_avg"]

        for sm in server_metrics.values():
            if sm["_call_count_for_avg"] > 0:
                sm["avg_latency_ms"] = round(sm["_latency_sum"] / sm["_call_count_for_avg"], 2)
            del sm["_latency_sum"]
            del sm["_call_count_for_avg"]

        # ── Build node list ───────────────────────────────────────────────────
        nodes: list[dict[str, Any]] = []
        for name, metrics in agent_metrics.items():
            nodes.append(
                {
                    "id": f"agent:{name}",
                    "type": "agent",
                    "label": name,
                    "metrics": metrics,
                }
            )
        for name, metrics in server_metrics.items():
            nodes.append(
                {
                    "id": f"server:{name}",
                    "type": "server",
                    "label": name,
                    "metrics": metrics,
                }
            )

        # ── Build edge list ───────────────────────────────────────────────────
        edges: list[dict[str, Any]] = []
        for edge in agent_server_edges:
            edges.append(
                {
                    "source": f"agent:{edge['agent_name']}",
                    "target": f"server:{edge['server_name']}",
                    "type": "calls",
                    "metrics": {
                        "call_count": edge["call_count"],
                        "error_count": edge["error_count"],
                        "avg_latency_ms": round(edge["avg_latency_ms"], 2),
                        "session_count": edge["session_count"],
                    },
                }
            )
        for edge in handoff_edges:
            edges.append(
                {
                    "source": f"agent:{edge['from_agent']}",
                    "target": f"agent:{edge['to_agent']}",
                    "type": "handoff",
                    "metrics": {
                        "handoff_count": edge["handoff_count"],
                        "session_count": edge["session_count"],
                    },
                }
            )
        # Delegation edges inferred from parent_span_id
        # (agent A's tool call is the parent of agent B's tool calls)
        # Emitted as "handoff" type so the dashboard renders them identically.
        for edge in delegation_edges:
            source = f"agent:{edge['from_agent']}"
            target = f"agent:{edge['to_agent']}"
            # Don't duplicate if already covered by an explicit handoff edge
            if not any(e["source"] == source and e["target"] == target for e in edges):
                edges.append(
                    {
                        "source": source,
                        "target": target,
                        "type": "handoff",
                        "metrics": {
                            "handoff_count": edge["delegation_count"],
                            "session_count": edge["session_count"],
                        },
                    }
                )

        return {
            "window_hours": hours,
            "nodes": nodes,
            "edges": edges,
        }

    async def _lineage_agent_server_edges(
        self,
        hours: int,
        project_id: str | None,
    ) -> list[dict[str, Any]]:
        """Query agent-to-server edges from tool_call spans."""
        where = (
            "WHERE started_at >= now() - INTERVAL {hours:UInt32} HOUR"
            " AND agent_name != ''"
            " AND span_type = 'tool_call'"
        )
        params: dict[str, Any] = {"hours": hours}
        if project_id:
            where += " AND project_id = {project_id:String}"
            params["project_id"] = project_id

        result = await self._client.query(
            f"""
            SELECT
                agent_name,
                server_name,
                count()                      AS call_count,
                countIf(status != 'success') AS error_count,
                avg(latency_ms)              AS avg_latency_ms,
                uniq(session_id)             AS session_count
            FROM mcp_tool_calls
            {where}
            GROUP BY agent_name, server_name
            ORDER BY call_count DESC
            """,
            parameters=params,
        )

        cols = [
            "agent_name",
            "server_name",
            "call_count",
            "error_count",
            "avg_latency_ms",
            "session_count",
        ]
        return [dict(zip(cols, row, strict=False)) for row in result.result_rows]

    async def _lineage_handoff_edges(
        self,
        hours: int,
        project_id: str | None,
    ) -> list[dict[str, Any]]:
        """Query agent-to-agent handoff edges."""
        where = (
            "WHERE started_at >= now() - INTERVAL {hours:UInt32} HOUR"
            " AND span_type = 'handoff'"
            " AND agent_name != ''"
        )
        params: dict[str, Any] = {"hours": hours}
        if project_id:
            where += " AND project_id = {project_id:String}"
            params["project_id"] = project_id

        result = await self._client.query(
            f"""
            SELECT
                agent_name                       AS from_agent,
                replaceOne(tool_name, '\u2192 ', '') AS to_agent,
                count()                          AS handoff_count,
                uniq(session_id)                 AS session_count
            FROM mcp_tool_calls
            {where}
            GROUP BY agent_name, tool_name
            ORDER BY handoff_count DESC
            """,
            parameters=params,
        )

        cols = ["from_agent", "to_agent", "handoff_count", "session_count"]
        return [dict(zip(cols, row, strict=False)) for row in result.result_rows]

    async def _lineage_delegation_edges(
        self,
        hours: int,
        project_id: str | None,
    ) -> list[dict[str, Any]]:
        """Infer agent-to-agent delegation from parent_span_id relationships.

        When agent A's tool call is the parent of agent B's tool calls,
        that means A delegated work to B. This captures the supervisor → analyst
        pattern that the unified callback records via cross-ainvoke parent linking.
        """
        where = "started_at >= now() - INTERVAL {hours:UInt32} HOUR"
        params: dict[str, Any] = {"hours": hours}
        if project_id:
            where += " AND project_id = {project_id:String}"
            params["project_id"] = project_id

        result = await self._client.query(
            f"""
            SELECT
                parent.agent_name  AS from_agent,
                child.agent_name   AS to_agent,
                count()            AS delegation_count,
                uniq(child.session_id) AS session_count
            FROM mcp_tool_calls AS child
            INNER JOIN mcp_tool_calls AS parent
                ON child.parent_span_id = parent.span_id
            WHERE child.{where}
              AND parent.{where}
              AND child.agent_name != ''
              AND parent.agent_name != ''
              AND child.agent_name != parent.agent_name
            GROUP BY parent.agent_name, child.agent_name
            ORDER BY delegation_count DESC
            """,
            parameters=params,
        )

        cols = ["from_agent", "to_agent", "delegation_count", "session_count"]
        return [dict(zip(cols, row, strict=False)) for row in result.result_rows]

    # ---------------------------------------------------------------------------
    # v0.3 Prevention Config — no-ops (lives in Postgres, not ClickHouse)
    # ---------------------------------------------------------------------------

    async def list_prevention_configs(self, project_id: str) -> list[PreventionConfig]:
        """No-op: prevention config lives in Postgres."""
        return []

    async def get_prevention_config(
        self, agent_name: str, project_id: str
    ) -> PreventionConfig | None:
        """No-op: prevention config lives in Postgres."""
        return None

    async def get_effective_prevention_config(
        self, agent_name: str, project_id: str
    ) -> PreventionConfig | None:
        """No-op: prevention config lives in Postgres."""
        return None

    async def upsert_prevention_config(self, config: PreventionConfig) -> PreventionConfig:
        """No-op: prevention config lives in Postgres."""
        return config

    async def delete_prevention_config(self, agent_name: str, project_id: str) -> bool:
        """No-op: prevention config lives in Postgres."""
        return False

    # ---------------------------------------------------------------------------
    # v0.3 Session health tags
    # ---------------------------------------------------------------------------

    async def save_session_health_tag(
        self,
        session_id: str,
        health_tag: str,
        details: str | None = None,
        project_id: str | None = None,
    ) -> None:
        """Persist (or replace) a health tag for a session."""
        now = datetime.now(UTC)
        await self._client.insert(
            "session_health_tags",
            [[session_id, health_tag, details, project_id or "", now]],
            column_names=["session_id", "health_tag", "details", "project_id", "tagged_at"],
        )

    async def get_session_health_tag(self, session_id: str) -> str | None:
        """Return the health tag for a session, or None if not tagged."""
        result = await self._client.query(
            "SELECT health_tag FROM session_health_tags FINAL WHERE session_id = {sid:String} LIMIT 1",
            parameters={"sid": session_id},
        )
        rows = result.result_rows
        if rows:
            return str(rows[0][0])
        return None

    async def get_untagged_sessions(
        self,
        inactive_seconds: int = 30,
        limit: int = 100,
        project_id: str | None = None,
    ) -> list[str]:
        """Return session_ids that have no health tag and have been inactive for N seconds."""
        project_filter = "AND project_id = {pid:String}" if project_id else ""
        params: dict[str, Any] = {"inactive_s": inactive_seconds, "lim": limit}
        if project_id:
            params["pid"] = project_id
        result = await self._client.query(
            f"""
            SELECT DISTINCT session_id
            FROM mcp_tool_calls
            WHERE session_id != ''
              {project_filter}
              AND session_id NOT IN (SELECT DISTINCT session_id FROM session_health_tags FINAL)
            GROUP BY session_id
            HAVING max(ended_at) < now() - INTERVAL {{inactive_s:UInt32}} SECOND
            LIMIT {{lim:UInt32}}
            """,
            parameters=params,
        )
        return [str(row[0]) for row in result.result_rows]

    # ---------------------------------------------------------------------------
    # Monitoring time-series
    # ---------------------------------------------------------------------------

    async def get_monitoring_timeseries(
        self,
        hours: int = 24,
        project_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Hourly-bucketed metrics for the monitoring dashboard."""
        where = "WHERE started_at >= now() - INTERVAL {hours:UInt32} HOUR AND session_id != ''"
        params: dict[str, Any] = {"hours": hours}
        if project_id:
            where += " AND project_id = {project_id:String}"
            params["project_id"] = project_id

        result = await self._client.query(
            f"""
            SELECT
                formatDateTime(toStartOfHour(started_at), '%Y-%m-%dT%H:00:00Z') AS bucket,
                uniqExact(session_id)                                            AS sessions,
                countIf(span_type = 'tool_call')                                AS tool_calls,
                countIf(status != 'success' AND span_type = 'tool_call')        AS errors,
                if(countIf(span_type = 'tool_call') > 0,
                   countIf(status != 'success' AND span_type = 'tool_call') /
                   countIf(span_type = 'tool_call'), 0)                         AS error_rate,
                avg(latency_ms)                                                  AS avg_latency_ms,
                quantile(0.99)(latency_ms)                                       AS p99_latency_ms,
                sum(input_tokens)                                                AS input_tokens,
                sum(output_tokens)                                               AS output_tokens,
                uniqExactIf(agent_name, agent_name != '')                        AS agents
            FROM mcp_tool_calls
            {where}
            GROUP BY bucket
            ORDER BY bucket
            """,
            parameters=params,
        )
        cols = [
            "bucket", "sessions", "tool_calls", "errors", "error_rate",
            "avg_latency_ms", "p99_latency_ms", "input_tokens", "output_tokens", "agents",
        ]
        return [dict(zip(cols, row, strict=False)) for row in result.result_rows]

    async def get_monitoring_models(
        self,
        hours: int = 24,
        project_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Per-model aggregated metrics for the Models tab."""
        where = "WHERE started_at >= now() - INTERVAL {hours:UInt32} HOUR AND model_id != ''"
        params: dict[str, Any] = {"hours": hours}
        if project_id:
            where += " AND project_id = {project_id:String}"
            params["project_id"] = project_id

        result = await self._client.query(
            f"""
            SELECT
                model_id,
                count()                                          AS calls,
                sum(input_tokens)                                AS input_tokens,
                sum(output_tokens)                               AS output_tokens,
                avg(latency_ms)                                  AS avg_latency_ms,
                countIf(status != 'success')                    AS error_count
            FROM mcp_tool_calls
            {where}
            GROUP BY model_id
            ORDER BY calls DESC
            """,
            parameters=params,
        )
        cols = ["model_id", "calls", "input_tokens", "output_tokens", "avg_latency_ms", "error_count"]
        return [dict(zip(cols, row, strict=False)) for row in result.result_rows]

    async def get_monitoring_tools(
        self,
        hours: int = 24,
        project_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Per-tool aggregated metrics for the Tools tab."""
        where = (
            "WHERE started_at >= now() - INTERVAL {hours:UInt32} HOUR"
            " AND span_type = 'tool_call'"
        )
        params: dict[str, Any] = {"hours": hours}
        if project_id:
            where += " AND project_id = {project_id:String}"
            params["project_id"] = project_id

        result = await self._client.query(
            f"""
            SELECT
                server_name,
                tool_name,
                count()                                               AS calls,
                countIf(status != 'success')                         AS errors,
                avg(latency_ms)                                       AS avg_latency_ms,
                quantile(0.99)(latency_ms)                            AS p99_latency_ms,
                if(count() > 0,
                   countIf(status = 'success') / count() * 100,
                   100)                                               AS success_rate,
                if(countDistinct(session_id) > 0,
                   round(count() / countDistinct(session_id), 2),
                   0)                                                 AS calls_per_session
            FROM mcp_tool_calls
            {where}
            GROUP BY server_name, tool_name
            ORDER BY calls DESC
            """,
            parameters=params,
        )
        cols = ["server_name", "tool_name", "calls", "errors", "avg_latency_ms", "p99_latency_ms", "success_rate", "calls_per_session"]
        return [dict(zip(cols, row, strict=False)) for row in result.result_rows]

    async def get_error_breakdown(
        self,
        hours: int = 24,
        project_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Error taxonomy breakdown — categorises all failed spans by error type.

        Categories: safety_filter, max_tokens, api_unavailable, timeout,
                    rate_limit, auth_error, agent_crash, other_error.
        """
        where = "WHERE started_at >= now() - INTERVAL {hours:UInt32} HOUR AND status != 'success'"
        params: dict[str, Any] = {"hours": hours}
        if project_id:
            where += " AND project_id = {project_id:String}"
            params["project_id"] = project_id

        result = await self._client.query(
            f"""
            SELECT
                multiIf(
                    error LIKE 'FinishReason:SAFETY%'       OR error LIKE 'FinishReason:PROHIBITED%',
                        'safety_filter',
                    error LIKE 'FinishReason:MAX_TOKENS%'   OR error LIKE 'FinishReason:length%',
                        'max_tokens',
                    error LIKE 'FinishReason:RECITATION%',
                        'recitation',
                    error LIKE '%503%'                      OR error LIKE '%UNAVAILABLE%',
                        'api_unavailable',
                    status = 'timeout'                      OR error LIKE '%timeout%' OR error LIKE '%timed out%',
                        'timeout',
                    error LIKE '%rate limit%'               OR error LIKE '%429%' OR error LIKE '%too many%',
                        'rate_limit',
                    error LIKE '%auth%'                     OR error LIKE '%401%' OR error LIKE '%403%' OR error LIKE '%forbidden%',
                        'auth_error',
                    error LIKE '%AgentCrash%'               OR error LIKE '%TaskGroup%',
                        'agent_crash',
                    'other_error'
                ) AS category,
                count()                                     AS count,
                countIf(span_type = 'agent')                AS llm_errors,
                countIf(span_type = 'tool_call')            AS tool_errors
            FROM mcp_tool_calls
            {where}
            GROUP BY category
            ORDER BY count DESC
            """,
            parameters=params,
        )
        total = sum(int(r[1]) for r in result.result_rows) or 1
        cols = ["category", "count", "llm_errors", "tool_errors"]
        rows = [dict(zip(cols, r, strict=False)) for r in result.result_rows]
        for r in rows:
            r["pct"] = round(int(r["count"]) / total * 100, 1)
        return rows

    async def get_incomplete_sessions(
        self,
        stale_minutes: int = 5,
        project_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Find sessions that stopped receiving spans — likely crashed agents."""
        where = (
            "WHERE started_at >= now() - INTERVAL 24 HOUR"
            " AND session_id != ''"
        )
        params: dict[str, Any] = {"stale_minutes": stale_minutes}
        if project_id:
            where += " AND project_id = {project_id:String}"
            params["project_id"] = project_id

        result = await self._client.query(
            f"""
            SELECT
                session_id,
                anyIf(agent_name, agent_name != '') AS agent_name,
                max(ended_at)                        AS last_activity,
                count()                              AS span_count,
                countIf(span_type = 'agent')        AS llm_calls,
                countIf(span_type = 'tool_call')    AS tool_calls
            FROM mcp_tool_calls
            {where}
            GROUP BY session_id
            HAVING last_activity < now() - INTERVAL {{stale_minutes:UInt32}} MINUTE
               AND span_count < 5
               AND session_id NOT IN (
                   SELECT session_id FROM session_health_tags
                   WHERE health_tag IN ('success', 'tool_failure', 'loop_detected',
                                        'budget_exceeded', 'incomplete')
               )
            ORDER BY last_activity DESC
            """,
            parameters=params,
        )
        cols = ["session_id", "agent_name", "last_activity", "span_count", "llm_calls", "tool_calls"]
        return [dict(zip(cols, row, strict=False)) for row in result.result_rows]

    # ---------------------------------------------------------------------------
    # Context manager
    # ---------------------------------------------------------------------------

    async def __aenter__(self) -> ClickHouseBackend:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _diff_spans(
    spans_a: list[dict[str, Any]],
    spans_b: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Align two span sequences by tool identity and produce a diff.

    Alignment strategy: match spans by (server_name, tool_name) in call order.
    This handles agents that call the same tool multiple times by matching
    the Nth call in A to the Nth call in B.

    Returns (diff_entries, summary).
    Each diff_entry has:
      tool_key:      "server/tool"
      status:        "matched" | "diverged" | "only_a" | "only_b"
      span_a:        span dict or None
      span_b:        span dict or None
      latency_delta_pct: float | None (positive = B is slower)
      status_changed: bool
    """
    from collections import defaultdict

    # Group spans by tool_key preserving order
    def _index(spans: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        idx: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for s in spans:
            key = f"{s.get('server_name', '')}/{s.get('tool_name', '')}"
            idx[key].append(s)
        return idx

    idx_a = _index(spans_a)
    idx_b = _index(spans_b)

    all_keys: list[str] = []
    seen: set[str] = set()
    for s in spans_a + spans_b:
        k = f"{s.get('server_name', '')}/{s.get('tool_name', '')}"
        if k not in seen:
            all_keys.append(k)
            seen.add(k)

    diff: list[dict[str, Any]] = []
    summary = {"matched": 0, "diverged": 0, "only_a": 0, "only_b": 0}

    for key in all_keys:
        calls_a = idx_a.get(key, [])
        calls_b = idx_b.get(key, [])
        max_len = max(len(calls_a), len(calls_b))

        for i in range(max_len):
            sa = calls_a[i] if i < len(calls_a) else None
            sb = calls_b[i] if i < len(calls_b) else None

            if sa is None:
                diff.append(
                    {
                        "tool_key": key,
                        "status": "only_b",
                        "span_a": None,
                        "span_b": sb,
                        "latency_delta_pct": None,
                        "status_changed": False,
                    }
                )
                summary["only_b"] += 1
            elif sb is None:
                diff.append(
                    {
                        "tool_key": key,
                        "status": "only_a",
                        "span_a": sa,
                        "span_b": None,
                        "latency_delta_pct": None,
                        "status_changed": False,
                    }
                )
                summary["only_a"] += 1
            else:
                lat_a = float(sa.get("latency_ms") or 0)
                lat_b = float(sb.get("latency_ms") or 0)
                lat_delta = round((lat_b - lat_a) / max(lat_a, 1) * 100, 1)
                status_changed = sa.get("status") != sb.get("status")
                diverged = status_changed or abs(lat_delta) >= 20
                entry_status = "diverged" if diverged else "matched"
                diff.append(
                    {
                        "tool_key": key,
                        "status": entry_status,
                        "span_a": sa,
                        "span_b": sb,
                        "latency_delta_pct": lat_delta,
                        "status_changed": status_changed,
                    }
                )
                summary["diverged" if diverged else "matched"] += 1

    return diff, summary


def _row_to_result(row: Any) -> HealthCheckResult:
    server_name, status, latency_ms, tools_count, schema_hash, error, checked_at, *rest = row
    project_id = rest[0] if rest else ""
    return HealthCheckResult(
        server_name=server_name,
        status=ServerStatus(status),
        latency_ms=float(latency_ms) if latency_ms is not None else None,
        tools_count=int(tools_count or 0),
        schema_hash=schema_hash,
        error=error,
        checked_at=checked_at if checked_at.tzinfo else checked_at.replace(tzinfo=UTC),
        project_id=project_id or "",
    )
