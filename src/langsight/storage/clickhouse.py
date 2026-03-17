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

from langsight.models import HealthCheckResult, ServerStatus
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
        checked_at   DateTime64(3, 'UTC')
    )
    ENGINE = MergeTree()
    PARTITION BY toYYYYMM(checked_at)
    ORDER BY (server_name, checked_at)
    TTL toDateTime(checked_at) + INTERVAL 90 DAY
    SETTINGS index_granularity = 8192
    """,
    # Tool call spans from the SDK / OTLP — 90-day TTL
    # parent_span_id enables multi-agent tree reconstruction
    # span_type: tool_call | agent | handoff
    # Note: session_id / parent_span_id / agent_name use String DEFAULT ''
    # (empty string = absent) because ClickHouse ORDER BY cannot contain Nullable columns.
    # Query pattern: WHERE session_id != '' to filter sessions.
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
        agent_name     String DEFAULT ''
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
    # Materialized view: pre-aggregated tool reliability per hour
    # Drives the Tool Reliability page in the dashboard without real-time fan-out
    """
    CREATE MATERIALIZED VIEW IF NOT EXISTS mv_tool_reliability
    ENGINE = SummingMergeTree()
    ORDER BY (server_name, tool_name, hour)
    POPULATE
    AS SELECT
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
    GROUP BY server_name, tool_name, hour
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
    ) -> list[HealthCheckResult]:
        """Return the N most recent health results, newest first."""
        result = await self._client.query(
            """
            SELECT server_name, status, latency_ms, tools_count,
                   schema_hash, error, checked_at
            FROM mcp_health_results
            WHERE server_name = {server_name:String}
            ORDER BY checked_at DESC
            LIMIT {limit:UInt32}
            """,
            parameters={"server_name": server_name, "limit": limit},
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
    ]

    def _span_row(self, s: ToolCallSpan) -> list[Any]:
        # None → '' for String DEFAULT '' columns (no Nullable in ORDER BY)
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

    async def get_tool_reliability(
        self,
        server_name: str | None = None,
        hours: int = 24,
    ) -> list[dict[str, Any]]:
        """Return tool reliability metrics for the given time window.

        Uses the mv_tool_reliability materialized view for fast aggregation.
        Returns rows sorted by total_calls descending.
        """
        where = "WHERE hour >= now() - INTERVAL {hours:UInt32} HOUR"
        params: dict[str, Any] = {"hours": hours}

        if server_name:
            where += " AND server_name = {server_name:String}"
            params["server_name"] = server_name

        # Compute ratios in Python to avoid nested aggregation errors in ClickHouse
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
    ) -> list[dict[str, Any]]:
        """Return recent agent sessions with call counts, failures, and cost estimate.

        Uses mv_agent_sessions materialized view for fast aggregation.
        """
        where = "WHERE first_call_at >= now() - INTERVAL {hours:UInt32} HOUR"
        params: dict[str, Any] = {"hours": hours, "limit": limit}

        if agent_name:
            where += " AND agent_name = {agent_name:String}"
            params["agent_name"] = agent_name

        result = await self._client.query(
            f"""
            SELECT
                session_id,
                agent_name,
                first_call_at,
                last_call_at,
                tool_calls,
                failed_calls,
                total_latency_ms,
                servers_used,
                dateDiff('millisecond', first_call_at, last_call_at) AS duration_ms
            FROM mv_agent_sessions
            {where}
            ORDER BY first_call_at DESC
            LIMIT {{limit:UInt32}}
            """,
            parameters=params,
        )

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
        ]
        return [dict(zip(cols, row, strict=False)) for row in result.result_rows]

    async def get_session_trace(self, session_id: str) -> list[dict[str, Any]]:
        """Return all spans for a session, ordered by start time.

        Returns the full flat list — callers reconstruct the tree
        using parent_span_id.
        """
        result = await self._client.query(
            """
            SELECT
                span_id, parent_span_id, span_type,
                server_name, tool_name, agent_name,
                started_at, ended_at, latency_ms,
                status, error, trace_id
            FROM mcp_tool_calls
            WHERE session_id = {session_id:String}
            ORDER BY started_at ASC
            """,
            parameters={"session_id": session_id},
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
    server_name, status, latency_ms, tools_count, schema_hash, error, checked_at = row
    return HealthCheckResult(
        server_name=server_name,
        status=ServerStatus(status),
        latency_ms=float(latency_ms) if latency_ms is not None else None,
        tools_count=int(tools_count or 0),
        schema_hash=schema_hash,
        error=error,
        checked_at=checked_at if checked_at.tzinfo else checked_at.replace(tzinfo=UTC),
    )
