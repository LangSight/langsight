from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite
import structlog

from langsight.models import HealthCheckResult, ServerStatus, ToolInfo

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# DDL — schema created on first open, idempotent
# ---------------------------------------------------------------------------
_DDL = """
CREATE TABLE IF NOT EXISTS health_results (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    server_name  TEXT    NOT NULL,
    status       TEXT    NOT NULL,
    latency_ms   REAL,
    tools_count  INTEGER NOT NULL DEFAULT 0,
    schema_hash  TEXT,
    error        TEXT,
    checked_at   TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS schema_snapshots (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    server_name  TEXT    NOT NULL,
    schema_hash  TEXT    NOT NULL,
    tools_count  INTEGER NOT NULL DEFAULT 0,
    recorded_at  TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_health_server_time
    ON health_results (server_name, checked_at DESC);

CREATE INDEX IF NOT EXISTS idx_schema_server_time
    ON schema_snapshots (server_name, recorded_at DESC);
"""


class SQLiteBackend:
    """SQLite storage backend — local file, zero infrastructure required.

    Usage:
        async with SQLiteBackend.open() as db:
            await db.save_health_result(result)

    The database file is created at `~/.langsight/data.db` by default.
    """

    _DEFAULT_PATH = Path("~/.langsight/data.db")

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    # ---------------------------------------------------------------------------
    # Factory
    # ---------------------------------------------------------------------------

    @classmethod
    async def open(cls, path: Path | None = None) -> SQLiteBackend:
        """Open (or create) the SQLite database and return a ready backend."""
        db_path = (path or cls._DEFAULT_PATH).expanduser()
        db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = await aiosqlite.connect(db_path)
        conn.row_factory = aiosqlite.Row
        await conn.executescript(_DDL)
        await conn.commit()

        logger.debug("storage.sqlite.opened", path=str(db_path))
        return cls(conn)

    # ---------------------------------------------------------------------------
    # StorageBackend implementation
    # ---------------------------------------------------------------------------

    async def save_health_result(self, result: HealthCheckResult) -> None:
        """Persist a health check result."""
        await self._conn.execute(
            """
            INSERT INTO health_results
                (server_name, status, latency_ms, tools_count, schema_hash, error, checked_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.server_name,
                result.status.value,
                result.latency_ms,
                result.tools_count,
                result.schema_hash,
                result.error,
                result.checked_at.isoformat(),
            ),
        )
        await self._conn.commit()
        logger.debug("storage.sqlite.health_saved", server=result.server_name)

    async def get_latest_schema_hash(self, server_name: str) -> str | None:
        """Return the most recently stored schema hash for a server, or None."""
        async with self._conn.execute(
            """
            SELECT schema_hash FROM schema_snapshots
            WHERE server_name = ?
            ORDER BY recorded_at DESC
            LIMIT 1
            """,
            (server_name,),
        ) as cursor:
            row = await cursor.fetchone()
        return row["schema_hash"] if row else None

    async def save_schema_snapshot(
        self,
        server_name: str,
        schema_hash: str,
        tools_count: int,
    ) -> None:
        """Persist a schema snapshot."""
        await self._conn.execute(
            """
            INSERT INTO schema_snapshots (server_name, schema_hash, tools_count, recorded_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                server_name,
                schema_hash,
                tools_count,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        await self._conn.commit()
        logger.debug("storage.sqlite.schema_saved", server=server_name, hash=schema_hash)

    async def get_health_history(
        self,
        server_name: str,
        limit: int = 10,
    ) -> list[HealthCheckResult]:
        """Return the N most recent health results for a server, newest first."""
        async with self._conn.execute(
            """
            SELECT * FROM health_results
            WHERE server_name = ?
            ORDER BY checked_at DESC
            LIMIT ?
            """,
            (server_name, limit),
        ) as cursor:
            rows = await cursor.fetchall()

        return [_row_to_result(row) for row in rows]

    async def close(self) -> None:
        """Close the database connection."""
        await self._conn.close()
        logger.debug("storage.sqlite.closed")

    # ---------------------------------------------------------------------------
    # Async context manager support
    # ---------------------------------------------------------------------------

    async def __aenter__(self) -> SQLiteBackend:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _row_to_result(row: aiosqlite.Row) -> HealthCheckResult:
    return HealthCheckResult(
        server_name=row["server_name"],
        status=ServerStatus(row["status"]),
        latency_ms=row["latency_ms"],
        tools_count=row["tools_count"] or 0,
        schema_hash=row["schema_hash"],
        error=row["error"],
        checked_at=datetime.fromisoformat(row["checked_at"]),
    )
