from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import aiosqlite
import structlog

from langsight.models import AgentSLO, ApiKeyRecord, HealthCheckResult, ServerStatus, SLOMetric

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# DDL — schema created on first open, idempotent
# ---------------------------------------------------------------------------
_DDL = """
CREATE TABLE IF NOT EXISTS api_keys (
    id           TEXT    PRIMARY KEY,
    name         TEXT    NOT NULL,
    key_prefix   TEXT    NOT NULL,
    key_hash     TEXT    UNIQUE NOT NULL,
    created_at   TEXT    NOT NULL,
    last_used_at TEXT,
    revoked_at   TEXT
);

CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys (key_hash);

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

CREATE TABLE IF NOT EXISTS agent_slos (
    id           TEXT    PRIMARY KEY,
    agent_name   TEXT    NOT NULL,
    metric       TEXT    NOT NULL,
    target       REAL    NOT NULL,
    window_hours INTEGER NOT NULL DEFAULT 24,
    created_at   TEXT    NOT NULL
);
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
                datetime.now(UTC).isoformat(),
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

    # ── API key management ────────────────────────────────────────────────────

    async def create_api_key(self, record: ApiKeyRecord) -> None:
        """Persist a new API key record."""
        await self._conn.execute(
            """
            INSERT INTO api_keys (id, name, key_prefix, key_hash, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                record.id,
                record.name,
                record.key_prefix,
                record.key_hash,
                record.created_at.isoformat(),
            ),
        )
        await self._conn.commit()
        logger.info("storage.sqlite.api_key_created", id=record.id, name=record.name)

    async def list_api_keys(self) -> list[ApiKeyRecord]:
        """Return all API key records (including revoked), newest first."""
        async with self._conn.execute(
            "SELECT * FROM api_keys ORDER BY created_at DESC"
        ) as cursor:
            rows = await cursor.fetchall()
        return [_row_to_api_key(row) for row in rows]

    async def get_api_key_by_hash(self, key_hash: str) -> ApiKeyRecord | None:
        """Look up a key by its SHA-256 hash. Returns None if not found or revoked."""
        async with self._conn.execute(
            "SELECT * FROM api_keys WHERE key_hash = ? AND revoked_at IS NULL",
            (key_hash,),
        ) as cursor:
            row = await cursor.fetchone()
        return _row_to_api_key(row) if row else None

    async def revoke_api_key(self, key_id: str) -> bool:
        """Mark a key as revoked. Returns True if found."""
        cursor = await self._conn.execute(
            "UPDATE api_keys SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
            (datetime.now(UTC).isoformat(), key_id),
        )
        await self._conn.commit()
        found = cursor.rowcount > 0
        if found:
            logger.info("storage.sqlite.api_key_revoked", id=key_id)
        return found

    async def touch_api_key(self, key_id: str) -> None:
        """Update last_used_at to now."""
        await self._conn.execute(
            "UPDATE api_keys SET last_used_at = ? WHERE id = ?",
            (datetime.now(UTC).isoformat(), key_id),
        )
        await self._conn.commit()

    # ── SLO management ────────────────────────────────────────────────────────

    async def create_slo(self, slo: AgentSLO) -> None:
        """Persist a new SLO definition."""
        await self._conn.execute(
            """
            INSERT INTO agent_slos (id, agent_name, metric, target, window_hours, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (slo.id, slo.agent_name, slo.metric.value, slo.target, slo.window_hours, slo.created_at.isoformat()),
        )
        await self._conn.commit()
        logger.info("storage.sqlite.slo_created", id=slo.id, agent=slo.agent_name)

    async def list_slos(self) -> list[AgentSLO]:
        """Return all SLO definitions, newest first."""
        async with self._conn.execute(
            "SELECT * FROM agent_slos ORDER BY created_at DESC"
        ) as cursor:
            rows = await cursor.fetchall()
        return [_row_to_slo(row) for row in rows]

    async def get_slo(self, slo_id: str) -> AgentSLO | None:
        """Return a single SLO by ID, or None."""
        async with self._conn.execute(
            "SELECT * FROM agent_slos WHERE id = ?", (slo_id,)
        ) as cursor:
            row = await cursor.fetchone()
        return _row_to_slo(row) if row else None

    async def delete_slo(self, slo_id: str) -> bool:
        """Delete an SLO. Returns True if found."""
        cursor = await self._conn.execute(
            "DELETE FROM agent_slos WHERE id = ?", (slo_id,)
        )
        await self._conn.commit()
        return cursor.rowcount > 0

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


def _row_to_api_key(row: aiosqlite.Row) -> ApiKeyRecord:
    return ApiKeyRecord(
        id=row["id"],
        name=row["name"],
        key_prefix=row["key_prefix"],
        key_hash=row["key_hash"],
        created_at=datetime.fromisoformat(row["created_at"]),
        last_used_at=datetime.fromisoformat(row["last_used_at"]) if row["last_used_at"] else None,
        revoked_at=datetime.fromisoformat(row["revoked_at"]) if row["revoked_at"] else None,
    )


def _row_to_slo(row: aiosqlite.Row) -> AgentSLO:
    return AgentSLO(
        id=row["id"],
        agent_name=row["agent_name"],
        metric=SLOMetric(row["metric"]),
        target=float(row["target"]),
        window_hours=int(row["window_hours"]),
        created_at=datetime.fromisoformat(row["created_at"]),
    )


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
