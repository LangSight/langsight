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
    """
    CREATE TABLE IF NOT EXISTS mcp_tool_calls (
        span_id      String,
        trace_id     Nullable(String),
        server_name  String,
        tool_name    String,
        started_at   DateTime64(3, 'UTC'),
        ended_at     DateTime64(3, 'UTC'),
        latency_ms   Float64,
        status       LowCardinality(String),
        error        Nullable(String),
        agent_name   Nullable(String),
        session_id   Nullable(String)
    )
    ENGINE = MergeTree()
    PARTITION BY toYYYYMM(started_at)
    ORDER BY (server_name, tool_name, started_at)
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
        """Open a ClickHouse connection and create schema if needed."""
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

    async def save_tool_call_span(self, span: ToolCallSpan) -> None:
        """Persist a tool call span from the SDK or OTLP ingestion."""
        await self._client.insert(
            "mcp_tool_calls",
            [
                [
                    span.span_id,
                    span.trace_id,
                    span.server_name,
                    span.tool_name,
                    span.started_at,
                    span.ended_at,
                    span.latency_ms,
                    span.status.value,
                    span.error,
                    span.agent_name,
                    span.session_id,
                ]
            ],
            column_names=[
                "span_id",
                "trace_id",
                "server_name",
                "tool_name",
                "started_at",
                "ended_at",
                "latency_ms",
                "status",
                "error",
                "agent_name",
                "session_id",
            ],
        )

    async def save_tool_call_spans(self, spans: list[ToolCallSpan]) -> None:
        """Batch insert multiple tool call spans (more efficient than one-by-one)."""
        if not spans:
            return
        rows = [
            [
                s.span_id,
                s.trace_id,
                s.server_name,
                s.tool_name,
                s.started_at,
                s.ended_at,
                s.latency_ms,
                s.status.value,
                s.error,
                s.agent_name,
                s.session_id,
            ]
            for s in spans
        ]
        await self._client.insert(
            "mcp_tool_calls",
            rows,
            column_names=[
                "span_id",
                "trace_id",
                "server_name",
                "tool_name",
                "started_at",
                "ended_at",
                "latency_ms",
                "status",
                "error",
                "agent_name",
                "session_id",
            ],
        )
        logger.debug("storage.clickhouse.spans_saved", count=len(spans))

    async def get_tool_reliability(
        self,
        server_name: str | None = None,
        hours: int = 24,
    ) -> list[dict]:
        """Return tool reliability metrics for the given time window.

        Uses the mv_tool_reliability materialized view for fast aggregation.
        Returns rows sorted by total_calls descending.
        """
        where = "WHERE hour >= now() - INTERVAL {hours:UInt32} HOUR"
        params: dict = {"hours": hours}

        if server_name:
            where += " AND server_name = {server_name:String}"
            params["server_name"] = server_name

        result = await self._client.query(
            f"""
            SELECT
                server_name,
                tool_name,
                sum(total_calls)    AS total_calls,
                sum(success_calls)  AS success_calls,
                sum(error_calls)    AS error_calls,
                sum(timeout_calls)  AS timeout_calls,
                round(sum(success_calls) / sum(total_calls) * 100, 2) AS success_rate_pct,
                round(sum(total_latency_ms) / sum(total_calls), 2)    AS avg_latency_ms,
                max(max_latency_ms) AS max_latency_ms
            FROM mv_tool_reliability
            {where}
            GROUP BY server_name, tool_name
            ORDER BY total_calls DESC
            """,
            parameters=params,
        )

        cols = [
            "server_name",
            "tool_name",
            "total_calls",
            "success_calls",
            "error_calls",
            "timeout_calls",
            "success_rate_pct",
            "avg_latency_ms",
            "max_latency_ms",
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


def _row_to_result(row: tuple) -> HealthCheckResult:
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
