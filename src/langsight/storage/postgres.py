from __future__ import annotations

import json
import uuid
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
    PreventionConfig,
    Project,
    ProjectMember,
    ProjectRole,
    SchemaDriftEvent,
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
        user_id      TEXT,
        project_id   TEXT,
        created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        last_used_at TIMESTAMPTZ,
        revoked_at   TIMESTAMPTZ
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys (key_hash)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_api_keys_user_id ON api_keys (user_id)
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
        project_id   TEXT        NOT NULL DEFAULT '',
        agent_name   TEXT        NOT NULL,
        metric       TEXT        NOT NULL,
        target       DOUBLE PRECISION NOT NULL,
        window_hours INTEGER     NOT NULL DEFAULT 24,
        created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS project_id TEXT NULL",
    "ALTER TABLE health_results ADD COLUMN IF NOT EXISTS project_id TEXT NOT NULL DEFAULT ''",
    "CREATE INDEX IF NOT EXISTS idx_health_results_project ON health_results(project_id, server_name)",
    "ALTER TABLE agent_slos ADD COLUMN IF NOT EXISTS project_id TEXT NOT NULL DEFAULT ''",
    "CREATE INDEX IF NOT EXISTS idx_agent_slos_project ON agent_slos(project_id)",
    # Composite index for SLO evaluator — queries per-agent per-project
    "CREATE INDEX IF NOT EXISTS idx_agent_slos_project_agent ON agent_slos(project_id, agent_name)",
    """
    CREATE TABLE IF NOT EXISTS alert_config (
        id            TEXT        PRIMARY KEY DEFAULT 'singleton',
        slack_webhook TEXT,
        alert_types   JSONB       NOT NULL DEFAULT '{}'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS audit_logs (
        id         BIGSERIAL   PRIMARY KEY,
        timestamp  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        event      TEXT        NOT NULL,
        user_id    TEXT        NOT NULL DEFAULT 'system',
        ip         TEXT        NOT NULL DEFAULT 'unknown',
        details    JSONB       NOT NULL DEFAULT '{}',
        project_id TEXT        NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_audit_logs_time ON audit_logs (timestamp DESC)
    """,
    "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS project_id TEXT NOT NULL DEFAULT ''",
    "CREATE INDEX IF NOT EXISTS idx_audit_logs_project ON audit_logs (project_id, timestamp DESC)",
    """
    CREATE TABLE IF NOT EXISTS agent_metadata (
        id          TEXT        PRIMARY KEY,
        agent_name  TEXT        NOT NULL,
        description TEXT        NOT NULL DEFAULT '',
        owner       TEXT        NOT NULL DEFAULT '',
        tags        JSONB       NOT NULL DEFAULT '[]',
        status      TEXT        NOT NULL DEFAULT 'active',
        runbook_url TEXT        NOT NULL DEFAULT '',
        project_id  TEXT        REFERENCES projects(id),
        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(agent_name, project_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_agent_metadata_name ON agent_metadata(agent_name)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_agent_metadata_project ON agent_metadata(project_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS server_metadata (
        id          TEXT        PRIMARY KEY,
        server_name TEXT        NOT NULL,
        description TEXT        NOT NULL DEFAULT '',
        owner       TEXT        NOT NULL DEFAULT '',
        tags        JSONB       NOT NULL DEFAULT '[]',
        transport   TEXT        NOT NULL DEFAULT '',
        runbook_url TEXT        NOT NULL DEFAULT '',
        project_id  TEXT        REFERENCES projects(id),
        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(server_name, project_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_server_metadata_name ON server_metadata(server_name)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_server_metadata_project ON server_metadata(project_id)
    """,
    # Migration: drop old single-column unique constraints and replace with
    # compound (name, project_id) constraints for proper project isolation.
    # These are no-ops if the columns were never UNIQUE or already migrated.
    """
    DO $$ BEGIN
        ALTER TABLE agent_metadata DROP CONSTRAINT IF EXISTS agent_metadata_agent_name_key;
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'agent_metadata_agent_name_project_id_key'
        ) THEN
            ALTER TABLE agent_metadata ADD CONSTRAINT agent_metadata_agent_name_project_id_key
                UNIQUE (agent_name, project_id);
        END IF;
    END $$
    """,
    """
    DO $$ BEGIN
        ALTER TABLE server_metadata DROP CONSTRAINT IF EXISTS server_metadata_server_name_key;
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'server_metadata_server_name_project_id_key'
        ) THEN
            ALTER TABLE server_metadata ADD CONSTRAINT server_metadata_server_name_project_id_key
                UNIQUE (server_name, project_id);
        END IF;
    END $$
    """,
    """
    CREATE TABLE IF NOT EXISTS server_tools (
        id           TEXT        PRIMARY KEY,
        server_name  TEXT        NOT NULL,
        tool_name    TEXT        NOT NULL,
        description  TEXT        NOT NULL DEFAULT '',
        input_schema JSONB       NOT NULL DEFAULT '{}',
        project_id   TEXT        REFERENCES projects(id),
        first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        last_seen_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(server_name, tool_name, project_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_server_tools_server ON server_tools(server_name)
    """,
    # v0.3 Prevention Config — dashboard-managed thresholds per agent
    """
    CREATE TABLE IF NOT EXISTS prevention_config (
        id                     TEXT             PRIMARY KEY,
        project_id             TEXT             NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        agent_name             TEXT             NOT NULL,
        loop_enabled           BOOLEAN          NOT NULL DEFAULT TRUE,
        loop_threshold         INTEGER          NOT NULL DEFAULT 3,
        loop_action            TEXT             NOT NULL DEFAULT 'terminate',
        max_steps              INTEGER,
        max_cost_usd           DOUBLE PRECISION,
        max_wall_time_s        DOUBLE PRECISION,
        budget_soft_alert      DOUBLE PRECISION NOT NULL DEFAULT 0.80,
        cb_enabled             BOOLEAN          NOT NULL DEFAULT TRUE,
        cb_failure_threshold   INTEGER          NOT NULL DEFAULT 5,
        cb_cooldown_seconds    DOUBLE PRECISION NOT NULL DEFAULT 60.0,
        cb_half_open_max_calls INTEGER          NOT NULL DEFAULT 2,
        created_at             TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
        updated_at             TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
        UNIQUE (project_id, agent_name)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_prevention_config_project
        ON prevention_config (project_id, agent_name)
    """,
    """
    CREATE TABLE IF NOT EXISTS instance_settings (
        id              TEXT    PRIMARY KEY DEFAULT 'singleton',
        redact_payloads BOOLEAN NOT NULL DEFAULT FALSE,
        settings_json   JSONB   NOT NULL DEFAULT '{}'
    )
    """,
    # Fired alerts — persisted alert history with ack/resolve/snooze lifecycle
    """
    CREATE TABLE IF NOT EXISTS fired_alerts (
        id            TEXT        PRIMARY KEY,
        alert_type    TEXT        NOT NULL,
        severity      TEXT        NOT NULL,
        server_name   TEXT        NOT NULL DEFAULT '',
        session_id    TEXT,
        title         TEXT        NOT NULL,
        message       TEXT        NOT NULL,
        fired_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        status        TEXT        NOT NULL DEFAULT 'active',
        acked_at      TIMESTAMPTZ,
        acked_by      TEXT,
        snoozed_until TIMESTAMPTZ,
        resolved_at   TIMESTAMPTZ,
        project_id    TEXT        NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_fired_alerts_project_status ON fired_alerts (project_id, status, fired_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_fired_alerts_fired_at ON fired_alerts (fired_at DESC)",
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
    async def open(cls, dsn: str, min_size: int = 2, max_size: int = 20) -> PostgresBackend:
        """Open a connection pool and create schema if needed.

        command_timeout=30 prevents any single query from blocking the pool
        indefinitely. If DDL fails, the pool is closed to prevent leaks.
        """
        pool = await asyncpg.create_pool(
            dsn,
            min_size=min_size,
            max_size=max_size,
            command_timeout=30,
        )
        try:
            async with pool.acquire() as conn:
                async with conn.transaction():
                    for stmt in _DDL_STATEMENTS:
                        await conn.execute(stmt)
        except Exception:
            await pool.close()
            raise

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
                     schema_hash, error, checked_at, project_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                result.server_name,
                result.status.value,
                result.latency_ms,
                result.tools_count,
                result.schema_hash,
                result.error,
                result.checked_at,
                result.project_id,
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
        project_id: str | None = None,
    ) -> list[HealthCheckResult]:
        """Return the N most recent health results for a server, newest first."""
        async with self._pool.acquire() as conn:
            if project_id:
                rows = await conn.fetch(
                    """
                    SELECT * FROM health_results
                    WHERE server_name = $1 AND (project_id = $3 OR project_id = '')
                    ORDER BY checked_at DESC
                    LIMIT $2
                    """,
                    server_name,
                    limit,
                    project_id,
                )
            else:
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
            INSERT INTO api_keys (id, name, key_prefix, key_hash, role, user_id, project_id, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            record.id,
            record.name,
            record.key_prefix,
            record.key_hash,
            record.role.value,
            record.user_id,
            record.project_id,
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
        """Delete a project and all its scoped data atomically.

        All 5 DELETEs run in a single transaction — a crash mid-way will
        roll back automatically rather than leaving orphaned rows.
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("DELETE FROM agent_metadata WHERE project_id = $1", project_id)
                await conn.execute("DELETE FROM server_metadata WHERE project_id = $1", project_id)
                await conn.execute("DELETE FROM server_tools WHERE project_id = $1", project_id)
                await conn.execute("DELETE FROM project_members WHERE project_id = $1", project_id)
                result: str = await conn.execute("DELETE FROM projects WHERE id = $1", project_id)
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

    async def get_member_counts(self, project_ids: list[str]) -> dict[str, int]:
        """Return {project_id: member_count} in a single query (avoids N+1)."""
        if not project_ids:
            return {}
        rows = await self._pool.fetch(
            "SELECT project_id, COUNT(*) AS cnt FROM project_members WHERE project_id = ANY($1) GROUP BY project_id",
            project_ids,
        )
        return {r["project_id"]: int(r["cnt"]) for r in rows}

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
        row = await self._pool.fetchrow(
            f"SELECT {_USER_SAFE_COLS} FROM users WHERE id = $1", user_id
        )
        return _row_to_user_safe(row) if row else None

    async def list_users(self) -> list[User]:
        rows = await self._pool.fetch(
            f"SELECT {_USER_SAFE_COLS} FROM users ORDER BY created_at DESC"
        )
        return [_row_to_user_safe(r) for r in rows]

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
        await self._pool.execute(
            "UPDATE invite_tokens SET used_at = NOW() WHERE token = $1 AND used_at IS NULL",
            token,
        )

    async def accept_invite(self, token: str, user: User) -> bool:
        """Atomically mark an invite as used and create the user account.

        Returns True on success. Returns False if the invite was already
        consumed (concurrent accept race). The caller should treat False
        as a 409 Conflict.
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                result: str = await conn.execute(
                    "UPDATE invite_tokens SET used_at = NOW() WHERE token = $1 AND used_at IS NULL",
                    token,
                )
                if result == "UPDATE 0":
                    return False  # already consumed — no user created
                await conn.execute(
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
                return True

    # ── SLO management ────────────────────────────────────────────────────────

    async def create_slo(self, slo: AgentSLO) -> None:
        await self._pool.execute(
            """
            INSERT INTO agent_slos (id, project_id, agent_name, metric, target, window_hours, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            slo.id,
            slo.project_id,
            slo.agent_name,
            slo.metric.value,
            slo.target,
            slo.window_hours,
            slo.created_at,
        )
        logger.info("storage.postgres.slo_created", id=slo.id, agent=slo.agent_name)

    async def list_slos(self, project_id: str | None = None) -> list[AgentSLO]:
        if project_id:
            rows = await self._pool.fetch(
                "SELECT * FROM agent_slos WHERE project_id = $1 ORDER BY created_at DESC",
                project_id,
            )
        else:
            rows = await self._pool.fetch("SELECT * FROM agent_slos ORDER BY created_at DESC")
        return [_row_to_slo(r) for r in rows]

    async def get_slo(self, slo_id: str) -> AgentSLO | None:
        row = await self._pool.fetchrow("SELECT * FROM agent_slos WHERE id = $1", slo_id)
        return _row_to_slo(row) if row else None

    async def delete_slo(self, slo_id: str, project_id: str | None = None) -> bool:
        if project_id:
            result: str = await self._pool.execute(
                "DELETE FROM agent_slos WHERE id = $1 AND project_id = $2",
                slo_id,
                project_id,
            )
        else:
            result = await self._pool.execute("DELETE FROM agent_slos WHERE id = $1", slo_id)
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
            alert_types = json.loads(alert_types)
        return {"slack_webhook": row["slack_webhook"], "alert_types": alert_types}

    async def save_alert_config(
        self, slack_webhook: str | None, alert_types: dict[str, bool]
    ) -> None:
        """Upsert the singleton alert config row."""
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

    # ── Fired alerts (persisted alert history) ───────────────────────────────

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
        """Persist a fired alert for history and lifecycle management."""
        from datetime import UTC, datetime

        await self._pool.execute(
            """
            INSERT INTO fired_alerts
                (id, alert_type, severity, server_name, session_id, title, message, fired_at, status, project_id)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'active', $9)
            ON CONFLICT (id) DO NOTHING
            """,
            alert_id,
            alert_type,
            severity,
            server_name,
            session_id,
            title,
            message,
            datetime.now(UTC),
            project_id,
        )

    async def get_fired_alerts(
        self,
        project_id: str = "",
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Return fired alerts, most-recent-first."""
        from datetime import UTC, datetime

        where_clauses = ["(project_id = $1 OR project_id = '')"]
        params: list[Any] = [project_id]
        idx = 2

        if status and status != "all":
            if status == "snoozed":
                where_clauses.append(f"(status = 'snoozed' AND snoozed_until > ${idx})")
                params.append(datetime.now(UTC))
            else:
                where_clauses.append(f"status = ${idx}")
                params.append(status)
            idx += 1

        where = " AND ".join(where_clauses)
        rows = await self._pool.fetch(
            f"""
            SELECT id, alert_type, severity, server_name, session_id,
                   title, message, fired_at, status,
                   acked_at, acked_by, snoozed_until, resolved_at, project_id
            FROM fired_alerts
            WHERE {where}
            ORDER BY fired_at DESC
            LIMIT ${idx} OFFSET ${idx + 1}
            """,
            *params,
            limit,
            offset,
        )
        return [dict(r) for r in rows]

    async def count_fired_alerts(self, project_id: str = "", status: str | None = None) -> int:
        """Count fired alerts matching the given filters."""
        from datetime import UTC, datetime

        where_clauses = ["(project_id = $1 OR project_id = '')"]
        params: list[Any] = [project_id]
        idx = 2

        if status and status != "all":
            if status == "snoozed":
                where_clauses.append(f"(status = 'snoozed' AND snoozed_until > ${idx})")
                params.append(datetime.now(UTC))
            else:
                where_clauses.append(f"status = ${idx}")
                params.append(status)

        where = " AND ".join(where_clauses)
        row = await self._pool.fetchrow(
            f"SELECT COUNT(*) AS n FROM fired_alerts WHERE {where}", *params
        )
        return int(row["n"]) if row else 0

    async def ack_alert(self, alert_id: str, acked_by: str = "user") -> bool:
        """Mark an alert as acknowledged. Returns True if updated."""
        from datetime import UTC, datetime

        result = await self._pool.execute(
            """
            UPDATE fired_alerts
            SET status = 'acked', acked_at = $1, acked_by = $2
            WHERE id = $3 AND status = 'active'
            """,
            datetime.now(UTC),
            acked_by,
            alert_id,
        )
        return result.endswith("1")

    async def resolve_alert(self, alert_id: str) -> bool:
        """Mark an alert as resolved. Returns True if updated."""
        from datetime import UTC, datetime

        result = await self._pool.execute(
            """
            UPDATE fired_alerts
            SET status = 'resolved', resolved_at = $1
            WHERE id = $2 AND status NOT IN ('resolved')
            """,
            datetime.now(UTC),
            alert_id,
        )
        return result.endswith("1")

    async def snooze_alert(self, alert_id: str, snooze_minutes: int) -> bool:
        """Snooze an alert for N minutes. Returns True if updated."""
        from datetime import UTC, datetime, timedelta

        until = datetime.now(UTC) + timedelta(minutes=snooze_minutes)
        result = await self._pool.execute(
            """
            UPDATE fired_alerts
            SET status = 'snoozed', snoozed_until = $1
            WHERE id = $2 AND status NOT IN ('resolved')
            """,
            until,
            alert_id,
        )
        return result.endswith("1")

    async def get_alert_counts(self, project_id: str = "") -> dict[str, int]:
        """Return count of active alerts per severity."""
        rows = await self._pool.fetch(
            """
            SELECT severity, COUNT(*) AS n
            FROM fired_alerts
            WHERE (project_id = $1 OR project_id = '')
              AND status = 'active'
            GROUP BY severity
            """,
            project_id,
        )
        counts: dict[str, int] = {"critical": 0, "warning": 0, "info": 0, "total": 0}
        for row in rows:
            sev = row["severity"]
            n = int(row["n"])
            counts[sev] = n
            counts["total"] += n
        return counts

    # ── Instance settings (global, singleton) ────────────────────────────────

    async def get_instance_settings(self) -> dict[str, Any]:
        """Return global instance settings, with defaults if never saved."""
        row = await self._pool.fetchrow(
            "SELECT redact_payloads, settings_json FROM instance_settings WHERE id = 'singleton'"
        )
        if row is None:
            return {"redact_payloads": False}
        extra = row["settings_json"] or {}
        if isinstance(extra, str):
            extra = json.loads(extra)
        return {"redact_payloads": row["redact_payloads"], **extra}

    async def save_instance_settings(self, settings: dict[str, Any]) -> None:
        """Upsert the singleton instance settings row."""
        redact = settings.get("redact_payloads", False)
        extra = {k: v for k, v in settings.items() if k != "redact_payloads"}
        await self._pool.execute(
            """
            INSERT INTO instance_settings (id, redact_payloads, settings_json)
            VALUES ('singleton', $1, $2::jsonb)
            ON CONFLICT (id) DO UPDATE SET
                redact_payloads = EXCLUDED.redact_payloads,
                settings_json   = EXCLUDED.settings_json
            """,
            redact,
            json.dumps(extra),
        )

    # ── Audit logs ────────────────────────────────────────────────────────────

    async def append_audit_log(
        self,
        event: str,
        user_id: str,
        ip: str,
        details: dict[str, Any],
        project_id: str = "",
    ) -> None:
        """Append a new audit log entry."""
        await self._pool.execute(
            "INSERT INTO audit_logs (event, user_id, ip, details, project_id)"
            " VALUES ($1, $2, $3, $4::jsonb, $5)",
            event,
            user_id,
            ip,
            json.dumps(details),
            project_id,
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
                "details": (
                    json.loads(r["details"])
                    if isinstance(r["details"], str)
                    else r["details"] or {}
                ),
            }
            for r in rows
        ]

    async def count_audit_logs(self) -> int:
        """Return total number of audit log entries."""
        row = await self._pool.fetchrow("SELECT COUNT(*) AS n FROM audit_logs")
        return int(row["n"]) if row else 0

    # ---------------------------------------------------------------------------
    # Agent metadata (catalog)
    # ---------------------------------------------------------------------------

    async def get_all_agent_metadata(self, project_id: str | None = None) -> list[dict[str, Any]]:
        if project_id:
            rows = await self._pool.fetch(
                "SELECT * FROM agent_metadata WHERE project_id = $1 ORDER BY agent_name",
                project_id,
            )
        else:
            rows = await self._pool.fetch("SELECT * FROM agent_metadata ORDER BY agent_name")
        return [dict(r) for r in rows]

    async def get_agent_metadata(
        self, agent_name: str, project_id: str | None = None
    ) -> dict[str, Any] | None:
        if project_id:
            row = await self._pool.fetchrow(
                "SELECT * FROM agent_metadata WHERE agent_name = $1 AND project_id = $2",
                agent_name,
                project_id,
            )
        else:
            row = await self._pool.fetchrow(
                "SELECT * FROM agent_metadata WHERE agent_name = $1",
                agent_name,
            )
        return dict(row) if row else None

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
        now = datetime.now(UTC)
        if project_id is None:
            row = await self._pool.fetchrow(
                """
                UPDATE agent_metadata
                SET description = $2,
                    owner = $3,
                    tags = $4::jsonb,
                    status = $5,
                    runbook_url = $6,
                    updated_at = $7
                WHERE agent_name = $1 AND project_id IS NULL
                RETURNING *
                """,
                agent_name,
                description,
                owner,
                json.dumps(tags),
                status,
                runbook_url,
                now,
            )
            if row:
                return dict(row)

            row = await self._pool.fetchrow(
                """
                INSERT INTO agent_metadata (id, agent_name, description, owner, tags, status, runbook_url, project_id, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, NULL, $8, $8)
                RETURNING *
                """,
                uuid.uuid4().hex,
                agent_name,
                description,
                owner,
                json.dumps(tags),
                status,
                runbook_url,
                now,
            )
            return dict(row) if row else {}

        row = await self._pool.fetchrow(
            """
            INSERT INTO agent_metadata (id, agent_name, description, owner, tags, status, runbook_url, project_id, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8, $9, $9)
            ON CONFLICT (agent_name, project_id) DO UPDATE SET
                description = EXCLUDED.description,
                owner = EXCLUDED.owner,
                tags = EXCLUDED.tags,
                status = EXCLUDED.status,
                runbook_url = EXCLUDED.runbook_url,
                updated_at = EXCLUDED.updated_at
            RETURNING *
            """,
            uuid.uuid4().hex,
            agent_name,
            description,
            owner,
            json.dumps(tags),
            status,
            runbook_url,
            project_id,
            now,
        )
        return dict(row) if row else {}

    async def delete_agent_metadata(self, agent_name: str, project_id: str | None = None) -> bool:
        if project_id:
            result: str = await self._pool.execute(
                "DELETE FROM agent_metadata WHERE agent_name = $1 AND project_id = $2",
                agent_name,
                project_id,
            )
        else:
            result = await self._pool.execute(
                "DELETE FROM agent_metadata WHERE agent_name = $1 AND project_id IS NULL",
                agent_name,
            )
        return result != "DELETE 0"

    # Server metadata (catalog)
    async def get_all_server_metadata(self, project_id: str | None = None) -> list[dict[str, Any]]:
        if project_id:
            rows = await self._pool.fetch(
                "SELECT * FROM server_metadata WHERE project_id = $1 ORDER BY server_name",
                project_id,
            )
        else:
            rows = await self._pool.fetch("SELECT * FROM server_metadata ORDER BY server_name")
        return [dict(r) for r in rows]

    async def get_server_metadata(
        self, server_name: str, project_id: str | None = None
    ) -> dict[str, Any] | None:
        if project_id:
            row = await self._pool.fetchrow(
                "SELECT * FROM server_metadata WHERE server_name = $1 AND project_id = $2",
                server_name,
                project_id,
            )
        else:
            row = await self._pool.fetchrow(
                "SELECT * FROM server_metadata WHERE server_name = $1", server_name
            )
        return dict(row) if row else None

    async def upsert_server_metadata(
        self,
        *,
        server_name: str,
        description: str = "",
        owner: str = "",
        tags: list[str] | None = None,
        transport: str = "",
        runbook_url: str = "",
        project_id: str | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        if project_id is None:
            row = await self._pool.fetchrow(
                """
                UPDATE server_metadata
                SET description = $2,
                    owner = $3,
                    tags = $4::jsonb,
                    transport = $5,
                    runbook_url = $6,
                    updated_at = $7
                WHERE server_name = $1 AND project_id IS NULL
                RETURNING *
                """,
                server_name,
                description,
                owner,
                json.dumps(tags or []),
                transport,
                runbook_url,
                now,
            )
            if row:
                return dict(row)

            row = await self._pool.fetchrow(
                """
                INSERT INTO server_metadata (id, server_name, description, owner, tags, transport, runbook_url, project_id, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, NULL, $8, $8)
                RETURNING *
                """,
                uuid.uuid4().hex,
                server_name,
                description,
                owner,
                json.dumps(tags or []),
                transport,
                runbook_url,
                now,
            )
            return dict(row) if row else {}

        row = await self._pool.fetchrow(
            """
            INSERT INTO server_metadata (id, server_name, description, owner, tags, transport, runbook_url, project_id, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8, $9, $9)
            ON CONFLICT (server_name, project_id) DO UPDATE SET
                description = EXCLUDED.description,
                owner = EXCLUDED.owner,
                tags = EXCLUDED.tags,
                transport = EXCLUDED.transport,
                runbook_url = EXCLUDED.runbook_url,
                updated_at = EXCLUDED.updated_at
            RETURNING *
            """,
            uuid.uuid4().hex,
            server_name,
            description,
            owner,
            json.dumps(tags or []),
            transport,
            runbook_url,
            project_id,
            now,
        )
        return dict(row) if row else {}

    async def delete_server_metadata(self, server_name: str, project_id: str | None = None) -> bool:
        if project_id:
            result: str = await self._pool.execute(
                "DELETE FROM server_metadata WHERE server_name = $1 AND project_id = $2",
                server_name,
                project_id,
            )
        else:
            result = await self._pool.execute(
                "DELETE FROM server_metadata WHERE server_name = $1 AND project_id IS NULL",
                server_name,
            )
        return result != "DELETE 0"

    # Server tools (captured from list_tools() SDK interception)
    async def upsert_server_tools(
        self, server_name: str, tools: list[dict[str, object]], project_id: str | None = None
    ) -> None:
        """Upsert a batch of tools for a server in a single pipelined call."""
        if not tools:
            return
        now = datetime.now(UTC)
        args = [
            (
                uuid.uuid4().hex,
                server_name,
                str(tool.get("name", "")),
                str(tool.get("description", "")),
                json.dumps(tool.get("input_schema") or {}),
                project_id,
                now,
            )
            for tool in tools
        ]
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                if project_id is None:
                    for tool in tools:
                        row = await conn.fetchrow(
                            """
                            UPDATE server_tools
                            SET description = $3,
                                input_schema = $4::jsonb,
                                last_seen_at = $5
                            WHERE server_name = $1 AND tool_name = $2 AND project_id IS NULL
                            RETURNING id
                            """,
                            server_name,
                            str(tool.get("name", "")),
                            str(tool.get("description", "")),
                            json.dumps(tool.get("input_schema") or {}),
                            now,
                        )
                        if row is not None:
                            continue

                        await conn.execute(
                            """
                            INSERT INTO server_tools (id, server_name, tool_name, description, input_schema, project_id, first_seen_at, last_seen_at)
                            VALUES ($1, $2, $3, $4, $5::jsonb, NULL, $6, $6)
                            """,
                            uuid.uuid4().hex,
                            server_name,
                            str(tool.get("name", "")),
                            str(tool.get("description", "")),
                            json.dumps(tool.get("input_schema") or {}),
                            now,
                        )
                    return

                await conn.executemany(
                    """
                    INSERT INTO server_tools (id, server_name, tool_name, description, input_schema, project_id, first_seen_at, last_seen_at)
                    VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $7)
                    ON CONFLICT (server_name, tool_name, project_id) DO UPDATE SET
                        description = EXCLUDED.description,
                        input_schema = EXCLUDED.input_schema,
                        last_seen_at = EXCLUDED.last_seen_at
                    """,
                    args,
                )

    async def get_server_tools(
        self, server_name: str, project_id: str | None = None
    ) -> list[dict[str, object]]:
        """Get all declared tools for a server, scoped to project."""
        if project_id:
            rows = await self._pool.fetch(
                "SELECT * FROM server_tools WHERE server_name = $1 AND project_id = $2 ORDER BY tool_name",
                server_name,
                project_id,
            )
        else:
            rows = await self._pool.fetch(
                "SELECT * FROM server_tools WHERE server_name = $1 AND project_id IS NULL ORDER BY tool_name",
                server_name,
            )
        return [dict(r) for r in rows]

    # ---------------------------------------------------------------------------
    # v0.3 Prevention Config — dashboard-managed prevention thresholds per agent
    # ---------------------------------------------------------------------------

    async def list_prevention_configs(self, project_id: str) -> list[PreventionConfig]:
        """Return all prevention configs for a project, ordered by agent_name."""
        rows = await self._pool.fetch(
            "SELECT * FROM prevention_config WHERE project_id = $1 ORDER BY agent_name",
            project_id,
        )
        return [_row_to_prevention_config(r) for r in rows]

    async def get_prevention_config(
        self, agent_name: str, project_id: str
    ) -> PreventionConfig | None:
        """Return config for this specific agent, or None if not configured."""
        row = await self._pool.fetchrow(
            "SELECT * FROM prevention_config WHERE project_id = $1 AND agent_name = $2",
            project_id,
            agent_name,
        )
        return _row_to_prevention_config(row) if row else None

    async def get_effective_prevention_config(
        self, agent_name: str, project_id: str
    ) -> PreventionConfig | None:
        """Return agent-specific config, falling back to project default ('*')."""
        row = await self._pool.fetchrow(
            """
            SELECT * FROM prevention_config
            WHERE project_id = $1 AND agent_name = ANY(ARRAY[$2, '*'])
            ORDER BY CASE WHEN agent_name = $2 THEN 0 ELSE 1 END
            LIMIT 1
            """,
            project_id,
            agent_name,
        )
        return _row_to_prevention_config(row) if row else None

    async def upsert_prevention_config(self, config: PreventionConfig) -> PreventionConfig:
        """Create or update prevention config for an agent."""
        now = datetime.now(UTC)
        row = await self._pool.fetchrow(
            """
            INSERT INTO prevention_config (
                id, project_id, agent_name,
                loop_enabled, loop_threshold, loop_action,
                max_steps, max_cost_usd, max_wall_time_s, budget_soft_alert,
                cb_enabled, cb_failure_threshold, cb_cooldown_seconds, cb_half_open_max_calls,
                created_at, updated_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $15)
            ON CONFLICT (project_id, agent_name) DO UPDATE SET
                loop_enabled           = EXCLUDED.loop_enabled,
                loop_threshold         = EXCLUDED.loop_threshold,
                loop_action            = EXCLUDED.loop_action,
                max_steps              = EXCLUDED.max_steps,
                max_cost_usd           = EXCLUDED.max_cost_usd,
                max_wall_time_s        = EXCLUDED.max_wall_time_s,
                budget_soft_alert      = EXCLUDED.budget_soft_alert,
                cb_enabled             = EXCLUDED.cb_enabled,
                cb_failure_threshold   = EXCLUDED.cb_failure_threshold,
                cb_cooldown_seconds    = EXCLUDED.cb_cooldown_seconds,
                cb_half_open_max_calls = EXCLUDED.cb_half_open_max_calls,
                updated_at             = EXCLUDED.updated_at
            RETURNING *
            """,
            config.id,
            config.project_id,
            config.agent_name,
            config.loop_enabled,
            config.loop_threshold,
            config.loop_action,
            config.max_steps,
            config.max_cost_usd,
            config.max_wall_time_s,
            config.budget_soft_alert,
            config.cb_enabled,
            config.cb_failure_threshold,
            config.cb_cooldown_seconds,
            config.cb_half_open_max_calls,
            now,
        )
        return _row_to_prevention_config(row)

    async def delete_prevention_config(self, agent_name: str, project_id: str) -> bool:
        """Delete config for this agent. Returns True if found and deleted."""
        result: str = await self._pool.execute(
            "DELETE FROM prevention_config WHERE project_id = $1 AND agent_name = $2",
            project_id,
            agent_name,
        )
        return result != "DELETE 0"

    # ---------------------------------------------------------------------------
    # v0.3 Session health tags — not stored in Postgres (ClickHouse handles these)
    # Stubs satisfy the StorageBackend protocol when Postgres is used standalone.
    # ---------------------------------------------------------------------------

    async def save_session_health_tag(
        self,
        session_id: str,
        health_tag: str,
        details: str | None = None,
        project_id: str | None = None,
    ) -> None:
        """No-op: health tags live in ClickHouse, not Postgres."""

    async def get_session_health_tag(
        self, session_id: str, project_id: str | None = None
    ) -> str | None:
        """No-op: health tags live in ClickHouse, not Postgres."""
        return None

    async def get_untagged_sessions(
        self,
        inactive_seconds: int = 30,
        limit: int = 100,
        project_id: str | None = None,
    ) -> list[str]:
        """No-op: health tags live in ClickHouse, not Postgres."""
        return []

    async def save_schema_drift_event(self, event: SchemaDriftEvent) -> None:
        """No-op: schema drift events live in ClickHouse, not Postgres."""

    async def get_schema_drift_history(
        self,
        server_name: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """No-op: schema drift history lives in ClickHouse, not Postgres."""
        return []

    async def get_drift_impact(
        self,
        server_name: str,
        tool_name: str,
        hours: int = 24,
    ) -> list[dict[str, Any]]:
        """No-op: drift impact data lives in ClickHouse, not Postgres."""
        return []

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


# Columns for non-authentication queries — excludes password_hash so the
# bcrypt hash never travels into layers that don't need it.
_USER_SAFE_COLS = "id, email, role, active, invited_by, created_at, last_login_at"


def _row_to_user(row: asyncpg.Record) -> User:
    """Map a full DB row (with password_hash) to a User — for auth only."""
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


def _row_to_user_safe(row: asyncpg.Record) -> User:
    """Map a safe DB row (without password_hash) to a User — for non-auth reads."""
    return User(
        id=row["id"],
        email=row["email"],
        password_hash="",  # not fetched — never needed outside auth
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
        project_id=row.get("project_id", "") or "",
        agent_name=row["agent_name"],
        metric=SLOMetric(row["metric"]),
        target=float(row["target"]),
        window_hours=int(row["window_hours"]),
        created_at=row["created_at"],
    )


def _row_to_api_key(row: asyncpg.Record) -> ApiKeyRecord:
    row_dict = dict(row)
    return ApiKeyRecord(
        id=row_dict["id"],
        name=row_dict["name"],
        key_prefix=row_dict["key_prefix"],
        key_hash=row_dict["key_hash"],
        role=ApiKeyRole(row_dict["role"]) if row_dict["role"] else ApiKeyRole.ADMIN,
        user_id=row_dict.get("user_id"),
        project_id=row_dict.get("project_id"),
        created_at=row_dict["created_at"],
        last_used_at=row_dict["last_used_at"],
        revoked_at=row_dict["revoked_at"],
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


def _row_to_prevention_config(row: asyncpg.Record) -> PreventionConfig:
    return PreventionConfig(
        id=row["id"],
        project_id=row["project_id"],
        agent_name=row["agent_name"],
        loop_enabled=bool(row["loop_enabled"]),
        loop_threshold=int(row["loop_threshold"]),
        loop_action=str(row["loop_action"]),
        max_steps=int(row["max_steps"]) if row["max_steps"] is not None else None,
        max_cost_usd=float(row["max_cost_usd"]) if row["max_cost_usd"] is not None else None,
        max_wall_time_s=float(row["max_wall_time_s"])
        if row["max_wall_time_s"] is not None
        else None,
        budget_soft_alert=float(row["budget_soft_alert"]),
        cb_enabled=bool(row["cb_enabled"]),
        cb_failure_threshold=int(row["cb_failure_threshold"]),
        cb_cooldown_seconds=float(row["cb_cooldown_seconds"]),
        cb_half_open_max_calls=int(row["cb_half_open_max_calls"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
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
