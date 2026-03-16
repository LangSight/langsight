from __future__ import annotations

from datetime import UTC, datetime

import asyncpg
import structlog

from langsight.models import HealthCheckResult, ServerStatus

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# DDL — idempotent, runs on first open
# ---------------------------------------------------------------------------
_DDL_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS health_results (
        id           SERIAL PRIMARY KEY,
        server_name  TEXT             NOT NULL,
        status       TEXT             NOT NULL,
        latency_ms   DOUBLE PRECISION,
        tools_count  INTEGER          NOT NULL DEFAULT 0,
        schema_hash  TEXT,
        error        TEXT,
        checked_at   TIMESTAMPTZ      NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS schema_snapshots (
        id           SERIAL PRIMARY KEY,
        server_name  TEXT        NOT NULL,
        schema_hash  TEXT        NOT NULL,
        tools_count  INTEGER     NOT NULL DEFAULT 0,
        recorded_at  TIMESTAMPTZ NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_health_server_time
        ON health_results (server_name, checked_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_schema_server_time
        ON schema_snapshots (server_name, recorded_at DESC)
    """,
]


class PostgresBackend:
    """PostgreSQL storage backend — for production and team deployments.

    Uses asyncpg connection pool directly (no ORM) for maximum performance.
    Schema is created idempotently on first open.

    Usage:
        async with await PostgresBackend.open(dsn) as db:
            await db.save_health_result(result)

    Phase 2 migration path:
        Change storage.mode from "sqlite" to "postgres" in .langsight.yaml.
        All CLI commands and the API use open_storage() which switches
        transparently — no code changes required.
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    # ---------------------------------------------------------------------------
    # Factory
    # ---------------------------------------------------------------------------

    @classmethod
    async def open(cls, dsn: str) -> PostgresBackend:
        """Open a connection pool and create schema if needed."""
        pool = await asyncpg.create_pool(dsn, min_size=2, max_size=10)
        async with pool.acquire() as conn:
            async with conn.transaction():
                for stmt in _DDL_STATEMENTS:
                    await conn.execute(stmt)

        logger.debug("storage.postgres.opened", dsn=_redact_dsn(dsn))
        return cls(pool)

    # ---------------------------------------------------------------------------
    # StorageBackend implementation
    # ---------------------------------------------------------------------------

    async def save_health_result(self, result: HealthCheckResult) -> None:
        """Persist a health check result."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO health_results
                    (server_name, status, latency_ms, tools_count,
                     schema_hash, error, checked_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                result.server_name,
                result.status.value,
                result.latency_ms,
                result.tools_count,
                result.schema_hash,
                result.error,
                result.checked_at,
            )
        logger.debug("storage.postgres.health_saved", server=result.server_name)

    async def get_latest_schema_hash(self, server_name: str) -> str | None:
        """Return the most recent schema hash for a server, or None."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT schema_hash FROM schema_snapshots
                WHERE server_name = $1
                ORDER BY recorded_at DESC
                LIMIT 1
                """,
                server_name,
            )
        return row["schema_hash"] if row else None

    async def save_schema_snapshot(
        self,
        server_name: str,
        schema_hash: str,
        tools_count: int,
    ) -> None:
        """Persist a schema snapshot."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO schema_snapshots
                    (server_name, schema_hash, tools_count, recorded_at)
                VALUES ($1, $2, $3, $4)
                """,
                server_name,
                schema_hash,
                tools_count,
                datetime.now(UTC),
            )
        logger.debug(
            "storage.postgres.schema_saved",
            server=server_name,
            hash=schema_hash,
        )

    async def get_health_history(
        self,
        server_name: str,
        limit: int = 10,
    ) -> list[HealthCheckResult]:
        """Return the N most recent health results for a server, newest first."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM health_results
                WHERE server_name = $1
                ORDER BY checked_at DESC
                LIMIT $2
                """,
                server_name,
                limit,
            )
        return [_row_to_result(row) for row in rows]

    async def close(self) -> None:
        """Close the connection pool."""
        await self._pool.close()
        logger.debug("storage.postgres.closed")

    # ---------------------------------------------------------------------------
    # Async context manager
    # ---------------------------------------------------------------------------

    async def __aenter__(self) -> PostgresBackend:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _row_to_result(row: asyncpg.Record) -> HealthCheckResult:
    return HealthCheckResult(
        server_name=row["server_name"],
        status=ServerStatus(row["status"]),
        latency_ms=row["latency_ms"],
        tools_count=row["tools_count"] or 0,
        schema_hash=row["schema_hash"],
        error=row["error"],
        checked_at=row["checked_at"],
    )


def _redact_dsn(dsn: str) -> str:
    """Remove password from DSN for safe logging."""
    try:
        from urllib.parse import urlparse, urlunparse

        parsed = urlparse(dsn)
        if parsed.password:
            redacted = parsed._replace(
                netloc=f"{parsed.username}:***@{parsed.hostname}"
                + (f":{parsed.port}" if parsed.port else "")
            )
            return urlunparse(redacted)
    except Exception:  # noqa: BLE001
        pass
    return dsn
