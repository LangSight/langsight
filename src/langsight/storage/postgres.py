from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import asyncpg
import structlog

from langsight.models import (
    AgentSLO,
    ApiKeyRecord,
    ApiKeyRole,
    HealthCheckResult,
    InviteToken,
    ModelPricing,
    Project,
    ProjectMember,
    ProjectRole,
    ServerStatus,
    SLOMetric,
    User,
    UserRole,
)

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# DDL — idempotent, runs on first open
# ---------------------------------------------------------------------------
_DDL_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS api_keys (
        id           TEXT        PRIMARY KEY,
        name         TEXT        NOT NULL,
        key_prefix   TEXT        NOT NULL,
        key_hash     TEXT        UNIQUE NOT NULL,
        role         TEXT        NOT NULL DEFAULT 'admin',
        created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        last_used_at TIMESTAMPTZ,
        revoked_at   TIMESTAMPTZ
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys (key_hash)
    """,
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
    """
    CREATE TABLE IF NOT EXISTS model_pricing (
        id                    TEXT        PRIMARY KEY,
        provider              TEXT        NOT NULL,
        model_id              TEXT        NOT NULL,
        display_name          TEXT        NOT NULL,
        input_per_1m_usd      DOUBLE PRECISION NOT NULL DEFAULT 0,
        output_per_1m_usd     DOUBLE PRECISION NOT NULL DEFAULT 0,
        cache_read_per_1m_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
        effective_from        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        effective_to          TIMESTAMPTZ,
        notes                 TEXT,
        is_custom             BOOLEAN     NOT NULL DEFAULT FALSE
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_model_pricing_model_id ON model_pricing (model_id, effective_from DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS projects (
        id          TEXT        PRIMARY KEY,
        name        TEXT        NOT NULL,
        slug        TEXT        UNIQUE NOT NULL,
        created_by  TEXT        NOT NULL,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_projects_slug ON projects (slug)
    """,
    """
    CREATE TABLE IF NOT EXISTS project_members (
        project_id  TEXT        NOT NULL,
        user_id     TEXT        NOT NULL,
        role        TEXT        NOT NULL DEFAULT 'viewer',
        added_by    TEXT        NOT NULL,
        added_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (project_id, user_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_project_members_user ON project_members (user_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS users (
        id            TEXT        PRIMARY KEY,
        email         TEXT        UNIQUE NOT NULL,
        password_hash TEXT        NOT NULL,
        role          TEXT        NOT NULL DEFAULT 'viewer',
        active        BOOLEAN     NOT NULL DEFAULT TRUE,
        invited_by    TEXT,
        created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        last_login_at TIMESTAMPTZ
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_users_email ON users (email)
    """,
    """
    CREATE TABLE IF NOT EXISTS invite_tokens (
        token       TEXT        PRIMARY KEY,
        email       TEXT        NOT NULL,
        role        TEXT        NOT NULL DEFAULT 'viewer',
        invited_by  TEXT        NOT NULL,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        expires_at  TIMESTAMPTZ NOT NULL,
        used_at     TIMESTAMPTZ
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS agent_slos (
        id           TEXT        PRIMARY KEY,
        agent_name   TEXT        NOT NULL,
        metric       TEXT        NOT NULL,
        target       DOUBLE PRECISION NOT NULL,
        window_hours INTEGER     NOT NULL DEFAULT 24,
        created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS alert_config (
        id            TEXT        PRIMARY KEY DEFAULT 'singleton',
        slack_webhook TEXT,
        alert_types   JSONB       NOT NULL DEFAULT '{}'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS audit_logs (
        id        BIGSERIAL   PRIMARY KEY,
        timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        event     TEXT        NOT NULL,
        user_id   TEXT        NOT NULL DEFAULT 'system',
        ip        TEXT        NOT NULL DEFAULT 'unknown',
        details   JSONB       NOT NULL DEFAULT '{}'
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_audit_logs_time ON audit_logs (timestamp DESC)
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

    # ── API key management ────────────────────────────────────────────────────
    # Full Postgres implementation — uses a dedicated api_keys table.

    async def create_api_key(self, record: ApiKeyRecord) -> None:
        await self._pool.execute(
            """
            INSERT INTO api_keys (id, name, key_prefix, key_hash, role, created_at)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            record.id,
            record.name,
            record.key_prefix,
            record.key_hash,
            record.role.value,
            record.created_at,
        )
        logger.info("storage.postgres.api_key_created", id=record.id, name=record.name)

    async def list_api_keys(self) -> list[ApiKeyRecord]:
        rows = await self._pool.fetch("SELECT * FROM api_keys ORDER BY created_at DESC")
        return [_row_to_api_key(r) for r in rows]

    async def get_api_key_by_hash(self, key_hash: str) -> ApiKeyRecord | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM api_keys WHERE key_hash = $1 AND revoked_at IS NULL",
            key_hash,
        )
        return _row_to_api_key(row) if row else None

    async def revoke_api_key(self, key_id: str) -> bool:
        result: str = await self._pool.execute(
            "UPDATE api_keys SET revoked_at = NOW() WHERE id = $1 AND revoked_at IS NULL",
            key_id,
        )
        found = result != "UPDATE 0"
        if found:
            logger.info("storage.postgres.api_key_revoked", id=key_id)
        return found

    async def touch_api_key(self, key_id: str) -> None:
        await self._pool.execute(
            "UPDATE api_keys SET last_used_at = NOW() WHERE id = $1",
            key_id,
        )

    # ── Model pricing ─────────────────────────────────────────────────────────

    async def list_model_pricing(self) -> list[ModelPricing]:
        rows = await self._pool.fetch(
            "SELECT * FROM model_pricing ORDER BY provider, model_id, effective_from DESC"
        )
        return [_row_to_model_pricing(r) for r in rows]

    async def get_active_model_pricing(self, model_id: str) -> ModelPricing | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM model_pricing WHERE model_id = $1 AND effective_to IS NULL ORDER BY effective_from DESC LIMIT 1",
            model_id,
        )
        return _row_to_model_pricing(row) if row else None

    async def create_model_pricing(self, entry: ModelPricing) -> None:
        await self._pool.execute(
            """
            INSERT INTO model_pricing
                (id, provider, model_id, display_name, input_per_1m_usd, output_per_1m_usd,
                 cache_read_per_1m_usd, effective_from, effective_to, notes, is_custom)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
            """,
            entry.id,
            entry.provider,
            entry.model_id,
            entry.display_name,
            entry.input_per_1m_usd,
            entry.output_per_1m_usd,
            entry.cache_read_per_1m_usd,
            entry.effective_from,
            entry.effective_to,
            entry.notes,
            entry.is_custom,
        )

    async def deactivate_model_pricing(self, entry_id: str) -> bool:
        from datetime import UTC, datetime

        result: str = await self._pool.execute(
            "UPDATE model_pricing SET effective_to = $1 WHERE id = $2 AND effective_to IS NULL",
            datetime.now(UTC),
            entry_id,
        )
        return result != "UPDATE 0"

    # ── Project management ────────────────────────────────────────────────────

    async def create_project(self, project: Project) -> None:
        await self._pool.execute(
            "INSERT INTO projects (id, name, slug, created_by, created_at) VALUES ($1,$2,$3,$4,$5)",
            project.id,
            project.name,
            project.slug,
            project.created_by,
            project.created_at,
        )

    async def get_project(self, project_id: str) -> Project | None:
        row = await self._pool.fetchrow("SELECT * FROM projects WHERE id = $1", project_id)
        return _row_to_project(row) if row else None

    async def get_project_by_slug(self, slug: str) -> Project | None:
        row = await self._pool.fetchrow("SELECT * FROM projects WHERE slug = $1", slug)
        return _row_to_project(row) if row else None

    async def list_projects(self) -> list[Project]:
        rows = await self._pool.fetch("SELECT * FROM projects ORDER BY created_at DESC")
        return [_row_to_project(r) for r in rows]

    async def list_projects_for_user(self, user_id: str) -> list[Project]:
        rows = await self._pool.fetch(
            """
            SELECT p.* FROM projects p
            JOIN project_members m ON p.id = m.project_id
            WHERE m.user_id = $1
            ORDER BY p.created_at DESC
            """,
            user_id,
        )
        return [_row_to_project(r) for r in rows]

    async def update_project(self, project_id: str, name: str, slug: str) -> bool:
        result: str = await self._pool.execute(
            "UPDATE projects SET name = $1, slug = $2 WHERE id = $3", name, slug, project_id
        )
        return result != "UPDATE 0"

    async def delete_project(self, project_id: str) -> bool:
        await self._pool.execute("DELETE FROM project_members WHERE project_id = $1", project_id)
        result: str = await self._pool.execute("DELETE FROM projects WHERE id = $1", project_id)
        return result != "DELETE 0"

    # ── Project membership ────────────────────────────────────────────────────

    async def add_member(self, member: ProjectMember) -> None:
        await self._pool.execute(
            """
            INSERT INTO project_members (project_id, user_id, role, added_by, added_at)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (project_id, user_id) DO UPDATE SET role = EXCLUDED.role
            """,
            member.project_id,
            member.user_id,
            member.role.value,
            member.added_by,
            member.added_at,
        )

    async def get_member(self, project_id: str, user_id: str) -> ProjectMember | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM project_members WHERE project_id = $1 AND user_id = $2",
            project_id,
            user_id,
        )
        return _row_to_member(row) if row else None

    async def list_members(self, project_id: str) -> list[ProjectMember]:
        rows = await self._pool.fetch(
            "SELECT * FROM project_members WHERE project_id = $1 ORDER BY added_at DESC", project_id
        )
        return [_row_to_member(r) for r in rows]

    async def update_member_role(self, project_id: str, user_id: str, role: str) -> bool:
        result: str = await self._pool.execute(
            "UPDATE project_members SET role = $1 WHERE project_id = $2 AND user_id = $3",
            role,
            project_id,
            user_id,
        )
        return result != "UPDATE 0"

    async def remove_member(self, project_id: str, user_id: str) -> bool:
        result: str = await self._pool.execute(
            "DELETE FROM project_members WHERE project_id = $1 AND user_id = $2",
            project_id,
            user_id,
        )
        return result != "DELETE 0"

    # ── User management ───────────────────────────────────────────────────────

    async def create_user(self, user: User) -> None:
        await self._pool.execute(
            """
            INSERT INTO users (id, email, password_hash, role, active, invited_by, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            user.id,
            user.email,
            user.password_hash,
            user.role.value,
            user.active,
            user.invited_by,
            user.created_at,
        )

    async def get_user_by_email(self, email: str) -> User | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM users WHERE email = $1 AND active = TRUE", email
        )
        return _row_to_user(row) if row else None

    async def get_user_by_id(self, user_id: str) -> User | None:
        row = await self._pool.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
        return _row_to_user(row) if row else None

    async def list_users(self) -> list[User]:
        rows = await self._pool.fetch("SELECT * FROM users ORDER BY created_at DESC")
        return [_row_to_user(r) for r in rows]

    async def update_user_role(self, user_id: str, role: str) -> bool:
        result: str = await self._pool.execute(
            "UPDATE users SET role = $1 WHERE id = $2", role, user_id
        )
        return result != "UPDATE 0"

    async def deactivate_user(self, user_id: str) -> bool:
        result: str = await self._pool.execute(
            "UPDATE users SET active = FALSE WHERE id = $1", user_id
        )
        return result != "UPDATE 0"

    async def touch_user_login(self, user_id: str) -> None:
        await self._pool.execute("UPDATE users SET last_login_at = NOW() WHERE id = $1", user_id)

    async def count_users(self) -> int:
        row = await self._pool.fetchrow("SELECT COUNT(*) AS n FROM users WHERE active = TRUE")
        return int(row["n"]) if row else 0

    # ── Invite management ─────────────────────────────────────────────────────

    async def create_invite(self, invite: InviteToken) -> None:
        await self._pool.execute(
            """
            INSERT INTO invite_tokens (token, email, role, invited_by, created_at, expires_at)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            invite.token,
            invite.email,
            invite.role.value,
            invite.invited_by,
            invite.created_at,
            invite.expires_at,
        )

    async def get_invite(self, token: str) -> InviteToken | None:
        row = await self._pool.fetchrow("SELECT * FROM invite_tokens WHERE token = $1", token)
        return _row_to_invite(row) if row else None

    async def mark_invite_used(self, token: str) -> None:
        await self._pool.execute("UPDATE invite_tokens SET used_at = NOW() WHERE token = $1", token)

    # ── SLO management ────────────────────────────────────────────────────────

    async def create_slo(self, slo: AgentSLO) -> None:
        await self._pool.execute(
            """
            INSERT INTO agent_slos (id, agent_name, metric, target, window_hours, created_at)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            slo.id,
            slo.agent_name,
            slo.metric.value,
            slo.target,
            slo.window_hours,
            slo.created_at,
        )
        logger.info("storage.postgres.slo_created", id=slo.id, agent=slo.agent_name)

    async def list_slos(self) -> list[AgentSLO]:
        rows = await self._pool.fetch("SELECT * FROM agent_slos ORDER BY created_at DESC")
        return [_row_to_slo(r) for r in rows]

    async def get_slo(self, slo_id: str) -> AgentSLO | None:
        row = await self._pool.fetchrow("SELECT * FROM agent_slos WHERE id = $1", slo_id)
        return _row_to_slo(row) if row else None

    async def delete_slo(self, slo_id: str) -> bool:
        result: str = await self._pool.execute("DELETE FROM agent_slos WHERE id = $1", slo_id)
        return result != "DELETE 0"

    # ── Alert config ──────────────────────────────────────────────────────────

    async def get_alert_config(self) -> dict[str, Any] | None:
        """Return the persisted alert config, or None if never saved."""
        row = await self._pool.fetchrow(
            "SELECT slack_webhook, alert_types FROM alert_config WHERE id = 'singleton'"
        )
        if row is None:
            return None
        alert_types = row["alert_types"] or {}
        if isinstance(alert_types, str):
            import json

            alert_types = json.loads(alert_types)
        return {"slack_webhook": row["slack_webhook"], "alert_types": alert_types}

    async def save_alert_config(
        self, slack_webhook: str | None, alert_types: dict[str, bool]
    ) -> None:
        """Upsert the singleton alert config row."""
        import json

        await self._pool.execute(
            """
            INSERT INTO alert_config (id, slack_webhook, alert_types)
            VALUES ('singleton', $1, $2::jsonb)
            ON CONFLICT (id) DO UPDATE SET
                slack_webhook = EXCLUDED.slack_webhook,
                alert_types   = EXCLUDED.alert_types
            """,
            slack_webhook,
            json.dumps(alert_types),
        )

    # ── Audit logs ────────────────────────────────────────────────────────────

    async def append_audit_log(
        self,
        event: str,
        user_id: str,
        ip: str,
        details: dict[str, Any],
    ) -> None:
        """Append a new audit log entry."""
        import json

        await self._pool.execute(
            "INSERT INTO audit_logs (event, user_id, ip, details) VALUES ($1, $2, $3, $4::jsonb)",
            event,
            user_id,
            ip,
            json.dumps(details),
        )

    async def list_audit_logs(self, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        """Return audit log entries most-recent-first."""
        rows = await self._pool.fetch(
            "SELECT id, timestamp, event, user_id, ip, details FROM audit_logs ORDER BY id DESC LIMIT $1 OFFSET $2",
            limit,
            offset,
        )
        return [
            {
                "id": r["id"],
                "timestamp": r["timestamp"].isoformat()
                if hasattr(r["timestamp"], "isoformat")
                else str(r["timestamp"]),
                "event": r["event"],
                "user_id": r["user_id"],
                "ip": r["ip"],
                "details": r["details"] if isinstance(r["details"], dict) else {},
            }
            for r in rows
        ]

    async def count_audit_logs(self) -> int:
        """Return total number of audit log entries."""
        row = await self._pool.fetchrow("SELECT COUNT(*) AS n FROM audit_logs")
        return int(row["n"]) if row else 0

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


def _row_to_model_pricing(row: asyncpg.Record) -> ModelPricing:
    return ModelPricing(
        id=row["id"],
        provider=row["provider"],
        model_id=row["model_id"],
        display_name=row["display_name"],
        input_per_1m_usd=float(row["input_per_1m_usd"]),
        output_per_1m_usd=float(row["output_per_1m_usd"]),
        cache_read_per_1m_usd=float(row["cache_read_per_1m_usd"]),
        effective_from=row["effective_from"],
        effective_to=row["effective_to"],
        notes=row["notes"],
        is_custom=bool(row["is_custom"]),
    )


def _row_to_project(row: asyncpg.Record) -> Project:
    return Project(
        id=row["id"],
        name=row["name"],
        slug=row["slug"],
        created_by=row["created_by"],
        created_at=row["created_at"],
    )


def _row_to_member(row: asyncpg.Record) -> ProjectMember:
    return ProjectMember(
        project_id=row["project_id"],
        user_id=row["user_id"],
        role=ProjectRole(row["role"]),
        added_by=row["added_by"],
        added_at=row["added_at"],
    )


def _row_to_user(row: asyncpg.Record) -> User:
    return User(
        id=row["id"],
        email=row["email"],
        password_hash=row["password_hash"],
        role=UserRole(row["role"]),
        active=bool(row["active"]),
        invited_by=row["invited_by"],
        created_at=row["created_at"],
        last_login_at=row["last_login_at"],
    )


def _row_to_invite(row: asyncpg.Record) -> InviteToken:
    return InviteToken(
        token=row["token"],
        email=row["email"],
        role=UserRole(row["role"]),
        invited_by=row["invited_by"],
        created_at=row["created_at"],
        expires_at=row["expires_at"],
        used_at=row["used_at"],
    )


def _row_to_slo(row: asyncpg.Record) -> AgentSLO:
    return AgentSLO(
        id=row["id"],
        agent_name=row["agent_name"],
        metric=SLOMetric(row["metric"]),
        target=float(row["target"]),
        window_hours=int(row["window_hours"]),
        created_at=row["created_at"],
    )


def _row_to_api_key(row: asyncpg.Record) -> ApiKeyRecord:
    return ApiKeyRecord(
        id=row["id"],
        name=row["name"],
        key_prefix=row["key_prefix"],
        key_hash=row["key_hash"],
        role=ApiKeyRole(row["role"]) if row["role"] else ApiKeyRole.ADMIN,
        created_at=row["created_at"],
        last_used_at=row["last_used_at"],
        revoked_at=row["revoked_at"],
    )


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
