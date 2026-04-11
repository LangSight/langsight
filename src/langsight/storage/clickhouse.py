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

import re
from datetime import UTC, datetime
from typing import Any

import clickhouse_connect
import structlog

from langsight.models import HealthCheckResult, PreventionConfig, SchemaDriftEvent, ServerStatus
from langsight.sdk.models import ToolCallSpan

logger = structlog.get_logger()

_SAFE_DB_NAME = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

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
        recorded_at  DateTime64(3, 'UTC'),
        project_id   String DEFAULT ''
    )
    ENGINE = MergeTree()
    ORDER BY (project_id, server_name, recorded_at)
    SETTINGS index_granularity = 8192
    """,
    "ALTER TABLE mcp_schema_snapshots ADD COLUMN IF NOT EXISTS project_id String DEFAULT ''",
    # Schema drift events — one row per atomic change, append-only
    """
    CREATE TABLE IF NOT EXISTS schema_drift_events (
        server_name    String,
        tool_name      String,
        drift_type     LowCardinality(String),
        change_kind    LowCardinality(String),
        param_name     Nullable(String),
        old_value      Nullable(String),
        new_value      Nullable(String),
        previous_hash  Nullable(String),
        current_hash   String,
        has_breaking   UInt8 DEFAULT 0,
        detected_at    DateTime64(3, 'UTC'),
        project_id     String DEFAULT ''
    )
    ENGINE = MergeTree()
    PARTITION BY toYYYYMM(detected_at)
    ORDER BY (project_id, server_name, detected_at)
    TTL toDateTime(detected_at) + INTERVAL 90 DAY
    SETTINGS index_granularity = 8192
    """,
    "ALTER TABLE schema_drift_events ADD COLUMN IF NOT EXISTS project_id String DEFAULT ''",
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
    # Drop mv_agent_sessions from any existing install — the view consumed CPU on
    # every insert but was never queryable correctly (AggregatingMergeTree columns
    # cannot be used in WHERE clauses, and *Merge combinators in SELECT produce
    # incorrect results against unmerged parts).  get_agent_sessions() now queries
    # mcp_tool_calls directly for both the project-scoped and admin paths.
    "DROP TABLE IF EXISTS mv_agent_sessions",
    # v0.3 Session health tags — one row per (project, session), auto-classified
    # Uses ReplacingMergeTree so re-tagging a session replaces the old row.
    # ORDER BY includes project_id to prevent cross-project tag collisions.
    """
    CREATE TABLE IF NOT EXISTS session_health_tags (
        session_id   String,
        health_tag   LowCardinality(String),
        details      Nullable(String),
        project_id   String DEFAULT '',
        tagged_at    DateTime64(3, 'UTC')
    )
    ENGINE = ReplacingMergeTree(tagged_at)
    ORDER BY (project_id, session_id)
    SETTINGS index_granularity = 8192
    """,
    # Migrate existing installs: add project_id to ORDER BY.
    # No-op if already correct; safe to run on every startup.
    "ALTER TABLE session_health_tags MODIFY ORDER BY (project_id, session_id)",
    # ---------------------------------------------------------------------------
    # Data skipping indexes (bloom filters) on mcp_tool_calls.
    #
    # The sort key (server_name, tool_name, started_at, span_id) is efficient
    # for tool-level queries but leaves project_id, session_id, and agent_name
    # unsorted — every equality filter on these columns scans all granules in
    # the matching month partition (~8 192 rows each).
    #
    # Bloom filter indexes let ClickHouse skip granules where the column value
    # is definitely absent, reducing I/O by ~90 % for selective predicates.
    # GRANULARITY 1 = one bloom filter entry per index granule (8 192 rows).
    # IF NOT EXISTS makes these idempotent on every startup.
    # MATERIALIZE runs as a background mutation — does not block startup.
    # ---------------------------------------------------------------------------
    "ALTER TABLE mcp_tool_calls ADD INDEX IF NOT EXISTS idx_bf_project_id  project_id  TYPE bloom_filter GRANULARITY 1",
    "ALTER TABLE mcp_tool_calls ADD INDEX IF NOT EXISTS idx_bf_session_id  session_id  TYPE bloom_filter GRANULARITY 1",
    "ALTER TABLE mcp_tool_calls ADD INDEX IF NOT EXISTS idx_bf_agent_name  agent_name  TYPE bloom_filter GRANULARITY 1",
    "ALTER TABLE mcp_tool_calls MATERIALIZE INDEX idx_bf_project_id",
    "ALTER TABLE mcp_tool_calls MATERIALIZE INDEX idx_bf_session_id",
    "ALTER TABLE mcp_tool_calls MATERIALIZE INDEX idx_bf_agent_name",
    "ALTER TABLE session_health_tags ADD INDEX IF NOT EXISTS idx_bf_project_id project_id TYPE bloom_filter GRANULARITY 1",
    "ALTER TABLE session_health_tags MATERIALIZE INDEX idx_bf_project_id",
    # --- Lineage protocol v1.0 columns ---
    "ALTER TABLE mcp_tool_calls ADD COLUMN IF NOT EXISTS target_agent_name String DEFAULT ''",
    "ALTER TABLE mcp_tool_calls ADD COLUMN IF NOT EXISTS lineage_provenance LowCardinality(String) DEFAULT 'explicit'",
    "ALTER TABLE mcp_tool_calls ADD COLUMN IF NOT EXISTS lineage_status LowCardinality(String) DEFAULT 'complete'",
    "ALTER TABLE mcp_tool_calls ADD COLUMN IF NOT EXISTS schema_version String DEFAULT '1.0'",
    # gen_ai.response.finish_reasons — why LLM stopped (stop, tool_calls, max_tokens, content_filter, etc.)
    "ALTER TABLE mcp_tool_calls ADD COLUMN IF NOT EXISTS finish_reason String DEFAULT ''",
    # Anthropic prompt caching token counts (gen_ai.usage.cache_read_input_tokens etc.)
    "ALTER TABLE mcp_tool_calls ADD COLUMN IF NOT EXISTS cache_read_tokens Nullable(UInt32)",
    "ALTER TABLE mcp_tool_calls ADD COLUMN IF NOT EXISTS cache_creation_tokens Nullable(UInt32)",
    # Thinking tokens (Gemini 2.5, o1, etc.) — derived from total_tokens - input_tokens - output_tokens
    "ALTER TABLE mcp_tool_calls ADD COLUMN IF NOT EXISTS thinking_tokens Nullable(UInt32)",
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
        if not _SAFE_DB_NAME.match(database):
            raise ValueError(
                f"Invalid ClickHouse database name {database!r}. "
                "Must match ^[a-zA-Z_][a-zA-Z0-9_]*$"
            )

        # Timeout constants — keep low so a runaway aggregation never blocks
        # the API indefinitely. 5 s connect, 30 s per query.
        _CONNECT_TIMEOUT = 5
        _QUERY_TIMEOUT = 30

        # Connect without database first to create it if missing
        admin = await clickhouse_connect.get_async_client(
            host=host,
            port=port,
            username=username,
            password=password,
            connect_timeout=_CONNECT_TIMEOUT,
            send_receive_timeout=_QUERY_TIMEOUT,
        )
        await admin.command(f"CREATE DATABASE IF NOT EXISTS `{database}`")
        await admin.close()

        client = await clickhouse_connect.get_async_client(
            host=host,
            port=port,
            database=database,
            username=username,
            password=password,
            connect_timeout=_CONNECT_TIMEOUT,
            send_receive_timeout=_QUERY_TIMEOUT,
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

    async def get_latest_schema_hash(self, server_name: str, project_id: str = "") -> str | None:
        """Return the most recent schema hash for a server."""
        result = await self._client.query(
            """
            SELECT schema_hash
            FROM mcp_schema_snapshots
            WHERE server_name = {server_name:String}
              AND project_id = {project_id:String}
            ORDER BY recorded_at DESC
            LIMIT 1
            """,
            parameters={"server_name": server_name, "project_id": project_id},
        )
        rows = result.result_rows
        return rows[0][0] if rows else None

    async def save_schema_snapshot(
        self,
        server_name: str,
        schema_hash: str,
        tools_count: int,
        project_id: str = "",
    ) -> None:
        """Persist a schema snapshot."""
        await self._client.insert(
            "mcp_schema_snapshots",
            [[server_name, schema_hash, tools_count, datetime.now(UTC), project_id]],
            column_names=["server_name", "schema_hash", "tools_count", "recorded_at", "project_id"],
        )

    async def get_health_history(
        self,
        server_name: str,
        limit: int = 10,
        project_id: str | None = None,
    ) -> list[HealthCheckResult]:
        """Return the N most recent health results, newest first.

        When project_id is set, returns only results strictly for that project.
        Global/unscoped results (project_id='') are excluded to prevent
        cross-tenant data leakage in multi-tenant deployments.
        """
        params: dict[str, Any] = {"server_name": server_name, "limit": limit}
        project_filter = ""
        if project_id:
            project_filter = "AND project_id = {project_id:String}"
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

    async def get_distinct_health_server_names(
        self,
        project_id: str | None = None,
    ) -> set[str]:
        """Return all distinct server names that have health check data.

        Used by list_servers_health to discover CLI-monitored servers that
        are not in the API container's config.servers.
        """
        if project_id:
            result = await self._client.query(
                """
                SELECT DISTINCT server_name
                FROM mcp_health_results
                WHERE project_id = {project_id:String}
                  AND server_name != ''
                """,
                parameters={"project_id": project_id},
            )
        else:
            result = await self._client.query(
                """
                SELECT DISTINCT server_name
                FROM mcp_health_results
                WHERE server_name != ''
                """
            )
        return {row[0] for row in result.result_rows if row[0]}

    # ---------------------------------------------------------------------------
    # Schema drift events
    # ---------------------------------------------------------------------------

    async def save_schema_drift_event(self, event: SchemaDriftEvent) -> None:
        """Persist one row per SchemaChange in the schema_drift_events table."""
        project_id = getattr(event, "project_id", "")
        cols = [
            "server_name",
            "tool_name",
            "drift_type",
            "change_kind",
            "param_name",
            "old_value",
            "new_value",
            "previous_hash",
            "current_hash",
            "has_breaking",
            "detected_at",
            "project_id",
        ]
        if not event.changes:
            await self._client.insert(
                "schema_drift_events",
                [
                    [
                        event.server_name,
                        "",
                        "unknown",
                        "hash_changed",
                        None,
                        None,
                        None,
                        event.previous_hash,
                        event.current_hash,
                        int(event.has_breaking),
                        event.detected_at,
                        project_id,
                    ]
                ],
                column_names=cols,
            )
            return

        rows = [
            [
                event.server_name,
                change.tool_name,
                change.drift_type.value,
                change.kind,
                change.param_name,
                change.old_value,
                change.new_value,
                event.previous_hash,
                event.current_hash,
                int(event.has_breaking),
                event.detected_at,
                project_id,
            ]
            for change in event.changes
        ]
        await self._client.insert("schema_drift_events", rows, column_names=cols)
        logger.info(
            "storage.schema_drift.saved",
            server=event.server_name,
            changes=len(event.changes),
            has_breaking=event.has_breaking,
        )

    async def get_schema_drift_history(
        self,
        server_name: str,
        limit: int = 20,
        project_id: str = "",
    ) -> list[dict[str, Any]]:
        """Return recent drift events for a server, grouped by detected_at."""
        result = await self._client.query(
            """
            SELECT
                server_name,
                tool_name,
                drift_type,
                change_kind,
                param_name,
                old_value,
                new_value,
                previous_hash,
                current_hash,
                has_breaking,
                detected_at
            FROM schema_drift_events
            WHERE server_name = {server_name:String}
              AND project_id = {project_id:String}
            ORDER BY detected_at DESC
            LIMIT {limit:UInt32}
            """,
            parameters={"server_name": server_name, "limit": limit, "project_id": project_id},
        )
        cols = [
            "server_name",
            "tool_name",
            "drift_type",
            "change_kind",
            "param_name",
            "old_value",
            "new_value",
            "previous_hash",
            "current_hash",
            "has_breaking",
            "detected_at",
        ]
        return [dict(zip(cols, row, strict=False)) for row in result.result_rows]

    async def get_drift_impact(
        self,
        server_name: str,
        tool_name: str,
        hours: int = 24,
        project_id: str = "",
    ) -> list[dict[str, Any]]:
        """Return agents/sessions that called a tool recently.

        Used for consumer impact analysis: "tool X changed — who uses it?"
        """
        result = await self._client.query(
            """
            SELECT
                agent_name,
                session_id,
                count()                   AS call_count,
                countIf(status = 'error') AS error_count,
                avg(latency_ms)           AS avg_latency_ms,
                max(started_at)           AS last_called_at
            FROM mcp_tool_calls
            WHERE
                server_name = {server_name:String}
                AND tool_name  = {tool_name:String}
                AND started_at >= now() - INTERVAL {hours:UInt32} HOUR
                AND project_id = {project_id:String}
            GROUP BY agent_name, session_id
            ORDER BY call_count DESC
            LIMIT 100
            """,
            parameters={
                "server_name": server_name,
                "tool_name": tool_name,
                "hours": hours,
                "project_id": project_id,
            },
        )
        return [
            {
                "agent_name": row[0],
                "session_id": row[1],
                "call_count": row[2],
                "error_count": row[3],
                "avg_latency_ms": float(row[4]) if row[4] is not None else None,
                "last_called_at": row[5],
            }
            for row in result.result_rows
        ]

    async def get_blast_radius_data(
        self,
        server_name: str,
        hours: int = 24,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        """Return per-agent call stats and total distinct sessions for blast radius.

        Two queries run concurrently:
          1. Per-agent breakdown: call_count, session_count, error_count, avg_latency.
          2. Total distinct sessions across all agents (avoids double-counting).
        """
        project_filter = ""
        params: dict[str, Any] = {"server_name": server_name, "hours": hours}
        if project_id:
            project_filter = "AND (project_id = {project_id:String} OR project_id = '')"
            params["project_id"] = project_id

        agent_query = f"""
            SELECT
                agent_name,
                COUNT(DISTINCT session_id) AS session_count,
                COUNT(*)                   AS call_count,
                countIf(status = 'error')  AS error_count,
                avg(latency_ms)            AS avg_latency_ms,
                max(started_at)            AS last_called_at
            FROM mcp_tool_calls
            WHERE
                server_name = {{server_name:String}}
                AND started_at >= now() - INTERVAL {{hours:UInt32}} HOUR
                {project_filter}
            GROUP BY agent_name
            ORDER BY call_count DESC
            LIMIT 50
        """

        sessions_query = f"""
            SELECT COUNT(DISTINCT session_id) AS total_sessions
            FROM mcp_tool_calls
            WHERE
                server_name = {{server_name:String}}
                AND started_at >= now() - INTERVAL {{hours:UInt32}} HOUR
                {project_filter}
        """

        import asyncio

        agent_res, session_res = await asyncio.gather(
            self._client.query(agent_query, parameters=params),
            self._client.query(sessions_query, parameters=params),
        )

        agents = [
            {
                "agent_name": row[0],
                "session_count": int(row[1]),
                "call_count": int(row[2]),
                "error_count": int(row[3]),
                "avg_latency_ms": float(row[4]) if row[4] is not None else None,
                "last_called_at": row[5],
            }
            for row in agent_res.result_rows
        ]

        total_sessions = int(session_res.result_rows[0][0]) if session_res.result_rows else 0

        return {"agents": agents, "total_sessions": total_sessions}

    async def get_server_logs(
        self,
        server_name: str,
        hours: int = 24,
        limit: int = 200,
        project_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return recent tool call log entries for a server, newest first."""
        project_filter = ""
        params: dict[str, Any] = {"server_name": server_name, "hours": hours, "limit": limit}
        if project_id:
            project_filter = "AND (project_id = {project_id:String} OR project_id = '')"
            params["project_id"] = project_id

        result = await self._client.query(
            f"""
            SELECT
                started_at,
                agent_name,
                tool_name,
                status,
                latency_ms,
                error,
                session_id,
                span_id
            FROM mcp_tool_calls
            WHERE
                server_name = {{server_name:String}}
                AND started_at >= now() - INTERVAL {{hours:UInt32}} HOUR
                {project_filter}
            ORDER BY started_at DESC
            LIMIT {{limit:UInt32}}
            """,
            parameters=params,
        )
        return [
            {
                "started_at": row[0],
                "agent_name": row[1],
                "tool_name": row[2],
                "status": row[3],
                "latency_ms": float(row[4]) if row[4] is not None else None,
                "error": row[5],
                "session_id": row[6],
                "span_id": row[7],
            }
            for row in result.result_rows
        ]

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
        "target_agent_name",
        "lineage_provenance",
        "lineage_status",
        "schema_version",
        "finish_reason",
        "cache_read_tokens",
        "cache_creation_tokens",
        "thinking_tokens",
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
            s.target_agent_name or "",
            s.lineage_provenance,
            s.lineage_status,
            s.schema_version,
            s.finish_reason or "",
            s.cache_read_tokens,
            s.cache_creation_tokens,
            s.thinking_tokens,
        ]

    # async_insert=1: ClickHouse buffers concurrent writes internally and flushes
    # as a single batch, avoiding per-request memory allocation spikes that cause
    # Code 241 (MEMORY_LIMIT_EXCEEDED) under high concurrent insert load.
    # wait_for_async_insert=0: fire-and-forget — the HTTP response returns as soon
    # as the write is queued, not after flush. Acceptable for telemetry data.
    _INSERT_SETTINGS = {"async_insert": 1, "wait_for_async_insert": 0}

    async def save_tool_call_span(self, span: ToolCallSpan) -> None:
        """Persist a single span (tool_call, agent, or handoff)."""
        await self._client.insert(
            "mcp_tool_calls",
            [self._span_row(span)],
            column_names=self._SPAN_COLUMNS,
            settings=self._INSERT_SETTINGS,
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
            settings=self._INSERT_SETTINGS,
        )
        logger.debug("storage.clickhouse.spans_saved", count=len(spans))

    async def get_distinct_span_server_names(self, project_id: str | None = None) -> set[str]:
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
              AND server_name NOT IN ('claude-sdk', 'coordinator')
              {project_filter}
            ORDER BY server_name
            LIMIT 100
            """,
            parameters=params,
        )
        return {row[0] for row in result.result_rows}

    async def get_distinct_span_agent_names(self, project_id: str | None = None) -> set[str]:
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
        """Return tool reliability metrics including latency percentiles.

        Queries mcp_tool_calls directly (not the MV) so that ClickHouse
        quantile() functions can operate on raw latency values.
        The MV only stores sums and cannot produce accurate percentiles.
        """
        params: dict[str, Any] = {"hours": hours}
        where = "WHERE started_at >= now() - INTERVAL {hours:UInt32} HOUR"
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
                count()                                         AS total_calls,
                countIf(status = 'success')                    AS success_calls,
                countIf(status = 'error')                      AS error_calls,
                countIf(status = 'timeout')                    AS timeout_calls,
                round(avg(latency_ms), 2)                      AS avg_latency_ms,
                round(max(latency_ms), 2)                      AS max_latency_ms,
                round(quantile(0.50)(latency_ms), 2)           AS p50_latency_ms,
                round(quantile(0.95)(latency_ms), 2)           AS p95_latency_ms,
                round(quantile(0.99)(latency_ms), 2)           AS p99_latency_ms,
                -- Error categorisation: bucket by error message content
                countIf(status = 'error'
                    AND (lower(error) LIKE '%timeout%'
                         OR lower(error) LIKE '%timed out%'))  AS err_timeout,
                countIf(status = 'error'
                    AND (lower(error) LIKE '%connection%'
                         OR lower(error) LIKE '%unreachable%'
                         OR lower(error) LIKE '%refused%'))     AS err_connection,
                countIf(status = 'error'
                    AND (lower(error) LIKE '%validation%'
                         OR lower(error) LIKE '%required%'
                         OR lower(error) LIKE '%invalid%'
                         OR lower(error) LIKE '%parameter%'))  AS err_params,
                countIf(status = 'error'
                    AND lower(error) NOT LIKE '%timeout%'
                    AND lower(error) NOT LIKE '%timed out%'
                    AND lower(error) NOT LIKE '%connection%'
                    AND lower(error) NOT LIKE '%unreachable%'
                    AND lower(error) NOT LIKE '%refused%'
                    AND lower(error) NOT LIKE '%validation%'
                    AND lower(error) NOT LIKE '%required%'
                    AND lower(error) NOT LIKE '%invalid%'
                    AND lower(error) NOT LIKE '%parameter%')   AS err_server
            FROM mcp_tool_calls
            {where}
            GROUP BY server_name, tool_name
            ORDER BY total_calls DESC
            """,
            parameters=params,
        )

        rows = []
        for row in result.result_rows:
            total = int(row[2]) or 1
            success = int(row[3])
            rows.append(
                {
                    "server_name": row[0],
                    "tool_name": row[1],
                    "total_calls": int(row[2]),
                    "success_calls": success,
                    "error_calls": int(row[4]),
                    "timeout_calls": int(row[5]),
                    "success_rate_pct": round(success / total * 100, 2),
                    "avg_latency_ms": float(row[6]),
                    "max_latency_ms": float(row[7]),
                    "p50_latency_ms": float(row[8]),
                    "p95_latency_ms": float(row[9]),
                    "p99_latency_ms": float(row[10]),
                    "error_breakdown": {
                        "timeout": int(row[11]),
                        "connection": int(row[12]),
                        "params": int(row[13]),
                        "server": int(row[14]),
                    },
                }
            )
        return rows

    async def get_server_invocation_stats(
        self,
        project_id: str | None = None,
        hours: int = 168,  # 7 days
    ) -> list[dict[str, Any]]:
        """Return last-invocation time and success status per server.

        Queries mcp_tool_calls directly (not the MV) to get the most-recent
        call timestamp and whether it succeeded. Used for "Last Used" and
        "Last OK?" columns in the MCP Servers dashboard table.
        """
        params: dict[str, Any] = {"hours": hours}
        project_filter = ""
        if project_id:
            project_filter = "AND project_id = {project_id:String}"
            params["project_id"] = project_id

        result = await self._client.query(
            f"""
            SELECT
                server_name,
                max(started_at)                    AS last_called_at,
                argMax(status, started_at)         AS last_call_status,
                count()                            AS total_calls,
                countIf(status = 'success')        AS success_calls
            FROM mcp_tool_calls
            WHERE started_at >= now() - INTERVAL {{hours:UInt32}} HOUR
              AND server_name != ''
              {project_filter}
            GROUP BY server_name
            ORDER BY last_called_at DESC
            """,
            parameters=params,
        )
        rows = []
        for row in result.result_rows:
            total = int(row[3]) or 1
            rows.append(
                {
                    "server_name": row[0],
                    "last_called_at": row[1].isoformat() if row[1] else None,
                    "last_call_status": row[2],
                    "last_call_ok": row[2] == "success",
                    "total_calls": int(row[3]),
                    "success_rate_pct": round(int(row[4]) / total * 100, 1),
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
            "total_thinking_tokens",
            "model_id",
            "agents_used",
            "has_prompt",  # True when a session span with llm_input was captured
        ]

        # Both the project-scoped and admin (all-projects) paths use the same query
        # against mcp_tool_calls.  project_id filter is applied when supplied.
        # ClickHouse bloom filter indexes on project_id and session_id make this
        # efficient even on large datasets.
        where = "WHERE t.started_at >= now() - INTERVAL {hours:UInt32} HOUR AND t.session_id != ''"
        params: dict[str, Any] = {"hours": hours, "limit": limit}
        having = ""

        if project_id:
            where += " AND t.project_id = {project_id:String}"
            params["project_id"] = project_id
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
                countIf(t.span_type IN ('tool_call', 'node'))                   AS tool_calls,
                countIf(t.status != 'success' AND t.span_type IN ('tool_call', 'node')) AS failed_calls,
                sum(t.latency_ms)                                    AS total_latency_ms,
                groupUniqArrayIf(t.server_name, t.span_type = 'tool_call') AS servers_used,
                dateDiff('millisecond', min(t.started_at), max(t.ended_at)) AS duration_ms,
                any(sht.health_tag)                                  AS health_tag,
                sum(t.input_tokens)                                  AS total_input_tokens,
                sum(t.output_tokens)                                 AS total_output_tokens,
                sum(t.thinking_tokens)                               AS total_thinking_tokens,
                anyIf(t.model_id, t.model_id != '')                  AS model_id,
                groupUniqArrayIf(t.agent_name, t.agent_name != '')   AS agents_used,
                countIf(t.span_type = 'agent' AND t.tool_name = 'session' AND t.llm_input != '') > 0 AS has_prompt
            FROM mcp_tool_calls t
            LEFT JOIN (
                -- argMax avoids FINAL deduplication scan on ReplacingMergeTree —
                -- picks the health_tag from the row with the latest tagged_at,
                -- which is correct and ~10x faster than FINAL on large tables.
                -- project_id is included in GROUP BY to prevent cross-tenant
                -- health tag bleed when different projects share session IDs.
                SELECT session_id, project_id, argMax(health_tag, tagged_at) AS health_tag
                FROM session_health_tags
                GROUP BY session_id, project_id
            ) sht ON t.session_id = sht.session_id AND t.project_id = sht.project_id
            {where}
            GROUP BY t.session_id
            {having}
            ORDER BY first_call_at DESC
            LIMIT {{limit:UInt32}}
            SETTINGS max_threads = 4
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
                input_tokens, output_tokens, model_id,
                target_agent_name, lineage_provenance,
                lineage_status, schema_version, finish_reason,
                cache_read_tokens, cache_creation_tokens, thinking_tokens
            FROM mcp_tool_calls
            WHERE {where}
            ORDER BY started_at ASC
            LIMIT 10000
            SETTINGS max_memory_usage = 200000000
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
            "target_agent_name",
            "lineage_provenance",
            "lineage_status",
            "schema_version",
            "finish_reason",
            "cache_read_tokens",
            "cache_creation_tokens",
            "thinking_tokens",
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
                sum(output_tokens)     AS output_tokens,
                sum(thinking_tokens)   AS thinking_tokens
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
            "thinking_tokens",
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
                if(target_agent_name != '', target_agent_name,
                   replaceOne(tool_name, '\u2192 ', '')) AS to_agent,
                count()                          AS handoff_count,
                uniq(session_id)                 AS session_count,
                countIf(lineage_provenance = 'explicit') AS explicit_count,
                countIf(lineage_provenance != 'explicit') AS inferred_count
            FROM mcp_tool_calls
            {where}
            GROUP BY from_agent, to_agent
            ORDER BY handoff_count DESC
            """,
            parameters=params,
        )

        cols = [
            "from_agent",
            "to_agent",
            "handoff_count",
            "session_count",
            "explicit_count",
            "inferred_count",
        ]
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
        params: dict[str, Any] = {"hours": hours}
        # Build per-alias predicates to avoid ambiguous column references in self-join
        project_filter = ""
        if project_id:
            project_filter = (
                " AND child.project_id = {project_id:String}"
                " AND parent.project_id = {project_id:String}"
            )
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
            WHERE child.started_at  >= now() - INTERVAL {{hours:UInt32}} HOUR
              AND parent.started_at >= now() - INTERVAL {{hours:UInt32}} HOUR
              {project_filter}
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

    async def get_session_health_tag(
        self, session_id: str, project_id: str | None = None
    ) -> str | None:
        """Return the health tag for a session, scoped to project when provided."""
        if project_id:
            result = await self._client.query(
                "SELECT health_tag FROM session_health_tags FINAL"
                " WHERE session_id = {sid:String} AND project_id = {pid:String} LIMIT 1",
                parameters={"sid": session_id, "pid": project_id},
            )
        else:
            result = await self._client.query(
                "SELECT health_tag FROM session_health_tags FINAL"
                " WHERE session_id = {sid:String} LIMIT 1",
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
        """Time-bucketed metrics for the monitoring dashboard.

        Bucket granularity adapts to the requested window so charts always
        have enough data points for a meaningful trend line:
          <=1h  → 5-minute buckets  (up to 12 points)
          <=6h  → 15-minute buckets (up to 24 points)
          <=24h → 1-hour buckets    (up to 24 points)
          >24h  → 6-hour buckets    (up to 28 points for 7d)
        """
        # Choose bucket function and format based on window size
        if hours <= 1:
            bucket_fn = "toStartOfFiveMinutes(started_at)"
            bucket_fmt = "%Y-%m-%dT%H:%i:00Z"
        elif hours <= 6:
            bucket_fn = "toStartOfFifteenMinutes(started_at)"
            bucket_fmt = "%Y-%m-%dT%H:%i:00Z"
        elif hours <= 24:
            bucket_fn = "toStartOfHour(started_at)"
            bucket_fmt = "%Y-%m-%dT%H:00:00Z"
        else:
            bucket_fn = "toStartOfInterval(started_at, INTERVAL 6 HOUR)"
            bucket_fmt = "%Y-%m-%dT%H:00:00Z"

        where = "WHERE started_at >= now() - INTERVAL {hours:UInt32} HOUR AND session_id != ''"
        params: dict[str, Any] = {"hours": hours}
        if project_id:
            where += " AND project_id = {project_id:String}"
            params["project_id"] = project_id

        result = await self._client.query(
            f"""
            SELECT
                formatDateTime({bucket_fn}, '{bucket_fmt}') AS bucket,
                uniqExact(session_id)                                            AS sessions,
                countIf(span_type IN ('tool_call', 'node'))                                AS tool_calls,
                countIf(status != 'success' AND span_type IN ('tool_call', 'node'))        AS errors,
                if(countIf(span_type IN ('tool_call', 'node')) > 0,
                   countIf(status != 'success' AND span_type IN ('tool_call', 'node')) /
                   countIf(span_type IN ('tool_call', 'node')), 0)                         AS error_rate,
                avg(latency_ms)                                                  AS avg_latency_ms,
                quantile(0.99)(latency_ms)                                       AS p99_latency_ms,
                sum(input_tokens)                                                AS input_tokens,
                sum(output_tokens)                                               AS output_tokens,
                uniqExactIf(agent_name, agent_name != '')                        AS agents,
                uniqExactIf(session_id,
                    status != 'success' AND span_type IN ('tool_call', 'node'))             AS failed_sessions,
                if(uniqExact(session_id) > 0,
                   uniqExactIf(session_id,
                       status != 'success' AND span_type IN ('tool_call', 'node')) /
                   uniqExact(session_id), 0)                                     AS session_error_rate,
                quantileIf(0.99)(latency_ms, span_type = 'agent')               AS session_p99_ms
            FROM mcp_tool_calls
            {where}
            GROUP BY bucket
            ORDER BY bucket
            """,
            parameters=params,
        )
        cols = [
            "bucket",
            "sessions",
            "tool_calls",
            "errors",
            "error_rate",
            "avg_latency_ms",
            "p99_latency_ms",
            "input_tokens",
            "output_tokens",
            "agents",
            "failed_sessions",
            "session_error_rate",
            "session_p99_ms",
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
        cols = [
            "model_id",
            "calls",
            "input_tokens",
            "output_tokens",
            "avg_latency_ms",
            "error_count",
        ]
        return [dict(zip(cols, row, strict=False)) for row in result.result_rows]

    async def get_monitoring_tools(
        self,
        hours: int = 24,
        project_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Per-tool aggregated metrics for the Tools tab."""
        where = (
            "WHERE started_at >= now() - INTERVAL {hours:UInt32} HOUR AND span_type = 'tool_call'"
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
                   0)                                                 AS calls_per_session,
                countIf(error LIKE 'ContentError:%')                  AS content_errors
            FROM mcp_tool_calls
            {where}
            GROUP BY server_name, tool_name
            ORDER BY calls DESC
            """,
            parameters=params,
        )
        cols = [
            "server_name",
            "tool_name",
            "calls",
            "errors",
            "avg_latency_ms",
            "p99_latency_ms",
            "success_rate",
            "calls_per_session",
            "content_errors",
        ]
        return [dict(zip(cols, row, strict=False)) for row in result.result_rows]

    async def get_monitoring_trends(
        self,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        """Compare last 7 days vs previous 7 days for key metrics.

        Returns current and previous period values for sessions, errors,
        avg latency, and p99 latency so the dashboard can show WoW deltas.
        """
        where_base = "started_at >= now() - INTERVAL 14 DAY"
        params: dict[str, Any] = {}
        if project_id:
            where_base += " AND project_id = {project_id:String}"
            params["project_id"] = project_id

        result = await self._client.query(
            f"""
            SELECT
                round(avgIf(latency_ms,
                    started_at >= now() - INTERVAL 7 DAY
                    AND span_type = 'tool_call'), 2)                                AS cur_avg_lat,
                round(avgIf(latency_ms,
                    started_at < now() - INTERVAL 7 DAY
                    AND span_type = 'tool_call'), 2)                                AS prev_avg_lat,
                round(quantileIf(0.99)(latency_ms,
                    started_at >= now() - INTERVAL 7 DAY
                    AND span_type = 'tool_call'), 2)                                AS cur_p99,
                round(quantileIf(0.99)(latency_ms,
                    started_at < now() - INTERVAL 7 DAY
                    AND span_type = 'tool_call'), 2)                                AS prev_p99,
                countIf(started_at >= now() - INTERVAL 7 DAY
                    AND status != 'success' AND span_type = 'tool_call')            AS cur_errors,
                countIf(started_at < now() - INTERVAL 7 DAY
                    AND status != 'success' AND span_type = 'tool_call')            AS prev_errors,
                countIf(started_at >= now() - INTERVAL 7 DAY
                    AND span_type = 'tool_call')                                    AS cur_calls,
                countIf(started_at < now() - INTERVAL 7 DAY
                    AND span_type = 'tool_call')                                    AS prev_calls,
                uniqExactIf(session_id,
                    started_at >= now() - INTERVAL 7 DAY AND session_id != '')      AS cur_sessions,
                uniqExactIf(session_id,
                    started_at < now() - INTERVAL 7 DAY AND session_id != '')       AS prev_sessions
            FROM mcp_tool_calls
            WHERE {where_base}
            """,
            parameters=params,
        )

        if not result.result_rows:
            return {}

        r = result.result_rows[0]

        def safe_float(v: Any) -> float | None:
            try:
                f = float(v)
                return None if (f != f) else f  # nan check
            except (TypeError, ValueError):
                return None

        def delta_pct(cur: float | None, prev: float | None) -> float | None:
            if cur is None or prev is None or prev == 0:
                return None
            return round((cur - prev) / prev * 100, 1)

        cur_avg = safe_float(r[0])
        prev_avg = safe_float(r[1])
        cur_p99 = safe_float(r[2])
        prev_p99 = safe_float(r[3])
        cur_err = int(r[4])
        prev_err = int(r[5])
        cur_calls = int(r[6])
        prev_calls = int(r[7])
        cur_sess = int(r[8])
        prev_sess = int(r[9])

        cur_err_rate = cur_err / cur_calls if cur_calls else None
        prev_err_rate = prev_err / prev_calls if prev_calls else None

        return {
            "cur_avg_latency_ms": cur_avg,
            "prev_avg_latency_ms": prev_avg,
            "avg_latency_delta_pct": delta_pct(cur_avg, prev_avg),
            "cur_p99_latency_ms": cur_p99,
            "prev_p99_latency_ms": prev_p99,
            "p99_latency_delta_pct": delta_pct(cur_p99, prev_p99),
            "cur_error_rate": cur_err_rate,
            "prev_error_rate": prev_err_rate,
            "error_rate_delta_pct": delta_pct(cur_err_rate, prev_err_rate),
            "cur_sessions": cur_sess,
            "prev_sessions": prev_sess,
            "sessions_delta_pct": delta_pct(float(cur_sess), float(prev_sess)),
        }

    async def get_agent_loop_counts(
        self,
        hours: int = 24,
        project_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return per-agent loop detection counts from prevented spans."""
        where = "WHERE started_at >= now() - INTERVAL {hours:UInt32} HOUR AND status = 'prevented' AND error LIKE '%loop%'"
        params: dict[str, Any] = {"hours": hours}
        if project_id:
            where += " AND project_id = {project_id:String}"
            params["project_id"] = project_id
        result = await self._client.query(
            f"""
            SELECT agent_name, count() AS loop_count
            FROM mcp_tool_calls
            {where}
            GROUP BY agent_name
            ORDER BY loop_count DESC
            """,
            parameters=params,
        )
        return [{"agent_name": r[0], "loop_count": int(r[1])} for r in result.result_rows]

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
        where = "WHERE started_at >= now() - INTERVAL 24 HOUR AND session_id != ''"
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
                countIf(span_type = 'agent')                    AS llm_calls,
                countIf(span_type IN ('tool_call', 'node'))    AS tool_calls
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
        cols = [
            "session_id",
            "agent_name",
            "last_activity",
            "span_count",
            "llm_calls",
            "tool_calls",
        ]
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
