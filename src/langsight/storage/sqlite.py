"""SQLite storage backend — zero-Docker local scan mode.

Implements the minimal StorageBackend subset required for
``langsight scan`` (health checks + schema tracking + drift events).

All other StorageBackend methods are no-op stubs that return empty
values — this backend is intentionally lightweight. For production
deployments use the ``dual`` backend (Postgres + ClickHouse).

The default database lives at ``~/.langsight/scan.db``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiosqlite
import structlog

from langsight.models import (
    HealthCheckResult,
    SchemaDriftEvent,
    ServerStatus,
)
from langsight.storage.base import StorageBackend

logger = structlog.get_logger()

DEFAULT_DB_PATH = Path.home() / ".langsight" / "scan.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS health_results (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    server_name  TEXT    NOT NULL,
    status       TEXT    NOT NULL,
    latency_ms   REAL,
    tools_count  INTEGER DEFAULT 0,
    schema_hash  TEXT,
    error        TEXT,
    checked_at   TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS schema_snapshots (
    server_name  TEXT PRIMARY KEY,
    schema_hash  TEXT NOT NULL,
    tools_count  INTEGER DEFAULT 0,
    recorded_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS schema_drift_events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    server_name   TEXT NOT NULL,
    tool_name     TEXT NOT NULL,
    drift_type    TEXT NOT NULL,
    change_kind   TEXT NOT NULL,
    param_name    TEXT,
    old_value     TEXT,
    new_value     TEXT,
    previous_hash TEXT,
    current_hash  TEXT NOT NULL,
    has_breaking  INTEGER DEFAULT 0,
    detected_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_health_server ON health_results(server_name);
CREATE INDEX IF NOT EXISTS idx_drift_server  ON schema_drift_events(server_name);
"""


class SQLiteBackend(StorageBackend):
    """Local SQLite backend — health checks and schema tracking only."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    @classmethod
    async def open(cls, path: Path = DEFAULT_DB_PATH) -> SQLiteBackend:
        """Open (or create) the SQLite database at *path*."""
        path.parent.mkdir(parents=True, exist_ok=True)
        db = await aiosqlite.connect(str(path))
        # WAL mode allows concurrent reads + a single writer without blocking.
        # busy_timeout gives retrying writers up to 5 s before raising "locked".
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA busy_timeout=5000")
        await db.executescript(_SCHEMA)
        await db.commit()
        logger.debug("storage.sqlite.opened", path=str(path))
        backend = cls(db)
        return backend

    # ── Health results ────────────────────────────────────────────────────────

    async def save_health_result(self, result: HealthCheckResult) -> None:
        await self._db.execute(
            """
            INSERT INTO health_results
                (server_name, status, latency_ms, tools_count, schema_hash, error, checked_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.server_name,
                result.status.value,
                result.latency_ms,
                result.tools_count or 0,
                result.schema_hash,
                result.error,
                result.checked_at.isoformat(),
            ),
        )
        await self._db.commit()

    async def get_health_history(
        self,
        server_name: str,
        limit: int = 10,
        project_id: str | None = None,
    ) -> list[HealthCheckResult]:
        async with self._db.execute(
            """
            SELECT server_name, status, latency_ms, tools_count, schema_hash, error, checked_at
            FROM health_results
            WHERE server_name = ?
            ORDER BY checked_at DESC
            LIMIT ?
            """,
            (server_name, limit),
        ) as cursor:
            rows = await cursor.fetchall()

        return [
            HealthCheckResult(
                server_name=row[0],
                status=ServerStatus(row[1]),
                latency_ms=row[2],
                tools_count=row[3],
                schema_hash=row[4],
                error=row[5],
                checked_at=datetime.fromisoformat(row[6]),
            )
            for row in rows
        ]

    # ── Schema snapshots ──────────────────────────────────────────────────────

    async def get_latest_schema_hash(self, server_name: str, project_id: str = "") -> str | None:
        async with self._db.execute(
            "SELECT schema_hash FROM schema_snapshots WHERE server_name = ?",
            (server_name,),
        ) as cursor:
            row = await cursor.fetchone()
        return row[0] if row else None

    async def save_schema_snapshot(
        self,
        server_name: str,
        schema_hash: str,
        tools_count: int,
        project_id: str = "",
    ) -> None:
        await self._db.execute(
            """
            INSERT INTO schema_snapshots (server_name, schema_hash, tools_count, recorded_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(server_name) DO UPDATE SET
                schema_hash  = excluded.schema_hash,
                tools_count  = excluded.tools_count,
                recorded_at  = excluded.recorded_at
            """,
            (server_name, schema_hash, tools_count, datetime.now(UTC).isoformat()),
        )
        await self._db.commit()

    # ── Schema drift ──────────────────────────────────────────────────────────

    async def save_schema_drift_event(self, event: SchemaDriftEvent) -> None:
        for change in event.changes:
            await self._db.execute(
                """
                INSERT INTO schema_drift_events
                    (server_name, tool_name, drift_type, change_kind, param_name,
                     old_value, new_value, previous_hash, current_hash, has_breaking, detected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
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
                    event.detected_at.isoformat(),
                ),
            )
        await self._db.commit()

    async def get_schema_drift_history(
        self,
        server_name: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        async with self._db.execute(
            """
            SELECT server_name, tool_name, drift_type, change_kind, param_name,
                   old_value, new_value, previous_hash, current_hash, has_breaking, detected_at
            FROM schema_drift_events
            WHERE server_name = ?
            ORDER BY detected_at DESC
            LIMIT ?
            """,
            (server_name, limit),
        ) as cursor:
            rows = await cursor.fetchall()

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
        return [dict(zip(cols, row, strict=False)) for row in rows]

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def close(self) -> None:
        await self._db.close()
        logger.debug("storage.sqlite.closed")

    async def __aenter__(self) -> SQLiteBackend:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    # ── Stubs — not used in scan mode ─────────────────────────────────────────
    # All remaining StorageBackend methods return safe empty defaults.

    async def get_distinct_health_server_names(self, project_id: str | None = None) -> set[str]:
        async with self._db.execute("SELECT DISTINCT server_name FROM health_results") as c:
            rows = await c.fetchall()
        return {row[0] for row in rows}

    async def upsert_server_tools(
        self, server_name: str, tools: list[dict[str, object]], project_id: str | None = None
    ) -> None:
        pass

    async def get_server_tools(
        self, server_name: str, project_id: str | None = None
    ) -> list[dict[str, object]]:
        return []

    async def get_drift_impact(
        self, server_name: str, tool_name: str, hours: int = 24
    ) -> list[dict[str, Any]]:
        return []

    async def create_api_key(self, record: Any) -> None:
        pass

    async def list_api_keys(self) -> list[Any]:
        return []

    async def get_api_key_by_hash(self, key_hash: str) -> None:
        return None

    async def revoke_api_key(self, key_id: str) -> bool:
        return False

    async def touch_api_key(self, key_id: str) -> None:
        pass

    async def list_model_pricing(self) -> list[Any]:
        return []

    async def get_active_model_pricing(self, model_id: str) -> None:
        return None

    async def create_model_pricing(self, entry: Any) -> None:
        pass

    async def deactivate_model_pricing(self, entry_id: str) -> bool:
        return False

    async def create_project(self, project: Any) -> None:
        pass

    async def get_project(self, project_id: str) -> None:
        return None

    async def get_project_by_slug(self, slug: str) -> None:
        return None

    async def list_projects(self) -> list[Any]:
        return []

    async def list_projects_for_user(self, user_id: str) -> list[Any]:
        return []

    async def update_project(self, project_id: str, name: str, slug: str) -> bool:
        return False

    async def delete_project(self, project_id: str) -> bool:
        return False

    async def add_member(self, member: Any) -> None:
        pass

    async def get_member(self, project_id: str, user_id: str) -> None:
        return None

    async def list_members(self, project_id: str) -> list[Any]:
        return []

    async def update_member_role(self, project_id: str, user_id: str, role: str) -> bool:
        return False

    async def remove_member(self, project_id: str, user_id: str) -> bool:
        return False

    async def create_user(self, user: Any) -> None:
        pass

    async def get_user_by_email(self, email: str) -> None:
        return None

    async def get_user_by_id(self, user_id: str) -> None:
        return None

    async def list_users(self) -> list[Any]:
        return []

    async def update_user_role(self, user_id: str, role: str) -> bool:
        return False

    async def deactivate_user(self, user_id: str) -> bool:
        return False

    async def touch_user_login(self, user_id: str) -> None:
        pass

    async def count_users(self) -> int:
        return 0

    async def create_invite(self, invite: Any) -> None:
        pass

    async def get_invite(self, token: str) -> None:
        return None

    async def mark_invite_used(self, token: str) -> None:
        pass

    async def accept_invite(self, token: str, user: Any) -> bool:
        return False

    async def create_slo(self, slo: Any) -> None:
        pass

    async def list_slos(self, project_id: str | None = None) -> list[Any]:
        return []

    async def get_slo(self, slo_id: str) -> None:
        return None

    async def delete_slo(self, slo_id: str, project_id: str | None = None) -> bool:
        return False

    async def get_alert_config(self, project_id: str = "") -> dict[str, Any] | None:
        return None

    async def save_alert_config(
        self,
        slack_webhook: str | None,
        alert_types: dict[str, bool],
        project_id: str = "",
    ) -> None:
        pass

    async def append_audit_log(
        self, event: str, user_id: str, ip: str, details: dict[str, Any]
    ) -> None:
        pass

    async def list_audit_logs(self, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        return []

    async def count_audit_logs(self) -> int:
        return 0

    async def get_all_agent_metadata(self, project_id: str | None = None) -> list[dict[str, Any]]:
        return []

    async def get_agent_metadata(
        self, agent_name: str, project_id: str | None = None
    ) -> dict[str, Any] | None:
        return None

    async def upsert_agent_metadata(
        self,
        agent_name: str,
        description: str,
        owner: str,
        tags: list[str],
        status: str,
        runbook_url: str,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        return {}

    async def delete_agent_metadata(self, agent_name: str, project_id: str | None = None) -> bool:
        return False

    async def get_all_server_metadata(self, project_id: str | None = None) -> list[dict[str, Any]]:
        return []

    async def get_server_metadata(
        self, server_name: str, project_id: str | None = None
    ) -> dict[str, Any] | None:
        return None

    async def upsert_server_metadata(
        self,
        *,
        server_name: str,
        description: str = "",
        owner: str = "",
        tags: list[str] | None = None,
        transport: str = "",
        url: str = "",
        runbook_url: str = "",
        project_id: str | None = None,
    ) -> dict[str, Any]:
        return {}

    async def delete_server_metadata(self, server_name: str, project_id: str | None = None) -> bool:
        return False

    async def list_prevention_configs(self, project_id: str) -> list[Any]:
        return []

    async def get_prevention_config(self, agent_name: str, project_id: str) -> None:
        return None

    async def get_effective_prevention_config(self, agent_name: str, project_id: str) -> None:
        return None

    async def upsert_prevention_config(self, config: Any) -> Any:
        return config

    async def delete_prevention_config(self, agent_name: str, project_id: str) -> bool:
        return False

    async def save_session_health_tag(
        self,
        session_id: str,
        health_tag: str,
        details: str | None = None,
        project_id: str | None = None,
    ) -> None:
        pass

    async def get_session_health_tag(
        self, session_id: str, project_id: str | None = None
    ) -> str | None:
        return None

    async def get_untagged_sessions(
        self, inactive_seconds: int = 30, limit: int = 100, project_id: str | None = None
    ) -> list[str]:
        return []

    # Fired alerts — no-ops for local scan-only mode
    async def save_fired_alert(
        self,
        alert_id: str,
        alert_type: str,
        severity: str,
        server_name: str,
        title: str,
        message: str,
        session_id: str | None = None,
        project_id: str = "",
    ) -> None:
        pass

    async def get_fired_alerts(
        self, project_id: str = "", status: str | None = None, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        return []

    async def count_fired_alerts(self, project_id: str = "", status: str | None = None) -> int:
        return 0

    async def ack_alert(self, alert_id: str, acked_by: str = "user", project_id: str = "") -> bool:
        return False

    async def resolve_alert(self, alert_id: str, project_id: str = "") -> bool:
        return False

    async def snooze_alert(self, alert_id: str, snooze_minutes: int, project_id: str = "") -> bool:
        return False

    async def get_alert_counts(self, project_id: str = "") -> dict[str, int]:
        return {"critical": 0, "warning": 0, "info": 0, "total": 0}
