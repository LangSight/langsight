from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import aiosqlite
import structlog

from langsight.models import AgentSLO, ApiKeyRecord, ApiKeyRole, HealthCheckResult, InviteToken, ModelPricing, Project, ProjectMember, ProjectRole, ServerStatus, SLOMetric, User, UserRole

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
    role         TEXT    NOT NULL DEFAULT 'admin',
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

CREATE TABLE IF NOT EXISTS model_pricing (
    id                    TEXT    PRIMARY KEY,
    provider              TEXT    NOT NULL,
    model_id              TEXT    NOT NULL,
    display_name          TEXT    NOT NULL,
    input_per_1m_usd      REAL    NOT NULL DEFAULT 0,
    output_per_1m_usd     REAL    NOT NULL DEFAULT 0,
    cache_read_per_1m_usd REAL    NOT NULL DEFAULT 0,
    effective_from        TEXT    NOT NULL,
    effective_to          TEXT,
    notes                 TEXT,
    is_custom             INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_model_pricing_model_id ON model_pricing (model_id, effective_from DESC);

CREATE TABLE IF NOT EXISTS projects (
    id          TEXT    PRIMARY KEY,
    name        TEXT    NOT NULL,
    slug        TEXT    UNIQUE NOT NULL,
    created_by  TEXT    NOT NULL,
    created_at  TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_projects_slug ON projects (slug);

CREATE TABLE IF NOT EXISTS project_members (
    project_id  TEXT    NOT NULL,
    user_id     TEXT    NOT NULL,
    role        TEXT    NOT NULL DEFAULT 'viewer',
    added_by    TEXT    NOT NULL,
    added_at    TEXT    NOT NULL,
    PRIMARY KEY (project_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_project_members_user ON project_members (user_id);

CREATE TABLE IF NOT EXISTS users (
    id            TEXT    PRIMARY KEY,
    email         TEXT    UNIQUE NOT NULL,
    password_hash TEXT    NOT NULL,
    role          TEXT    NOT NULL DEFAULT 'viewer',
    active        INTEGER NOT NULL DEFAULT 1,
    invited_by    TEXT,
    created_at    TEXT    NOT NULL,
    last_login_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);

CREATE TABLE IF NOT EXISTS invite_tokens (
    token       TEXT    PRIMARY KEY,
    email       TEXT    NOT NULL,
    role        TEXT    NOT NULL DEFAULT 'viewer',
    invited_by  TEXT    NOT NULL,
    created_at  TEXT    NOT NULL,
    expires_at  TEXT    NOT NULL,
    used_at     TEXT
);

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
            INSERT INTO api_keys (id, name, key_prefix, key_hash, role, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                record.id,
                record.name,
                record.key_prefix,
                record.key_hash,
                record.role.value,
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

    # ── Model pricing ─────────────────────────────────────────────────────────

    async def list_model_pricing(self) -> list[ModelPricing]:
        async with self._conn.execute(
            "SELECT * FROM model_pricing ORDER BY provider, model_id, effective_from DESC"
        ) as cur:
            rows = await cur.fetchall()
        return [_row_to_model_pricing(r) for r in rows]

    async def get_active_model_pricing(self, model_id: str) -> ModelPricing | None:
        async with self._conn.execute(
            "SELECT * FROM model_pricing WHERE model_id = ? AND effective_to IS NULL ORDER BY effective_from DESC LIMIT 1",
            (model_id,),
        ) as cur:
            row = await cur.fetchone()
        return _row_to_model_pricing(row) if row else None

    async def create_model_pricing(self, entry: ModelPricing) -> None:
        await self._conn.execute(
            """
            INSERT INTO model_pricing
                (id, provider, model_id, display_name, input_per_1m_usd, output_per_1m_usd,
                 cache_read_per_1m_usd, effective_from, effective_to, notes, is_custom)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.id, entry.provider, entry.model_id, entry.display_name,
                entry.input_per_1m_usd, entry.output_per_1m_usd, entry.cache_read_per_1m_usd,
                entry.effective_from.isoformat(),
                entry.effective_to.isoformat() if entry.effective_to else None,
                entry.notes, 1 if entry.is_custom else 0,
            ),
        )
        await self._conn.commit()

    async def deactivate_model_pricing(self, entry_id: str) -> bool:
        cursor = await self._conn.execute(
            "UPDATE model_pricing SET effective_to = ? WHERE id = ? AND effective_to IS NULL",
            (datetime.now(UTC).isoformat(), entry_id),
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    # ── Project management ────────────────────────────────────────────────────

    async def create_project(self, project: Project) -> None:
        await self._conn.execute(
            "INSERT INTO projects (id, name, slug, created_by, created_at) VALUES (?, ?, ?, ?, ?)",
            (project.id, project.name, project.slug, project.created_by, project.created_at.isoformat()),
        )
        await self._conn.commit()

    async def get_project(self, project_id: str) -> Project | None:
        async with self._conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)) as cur:
            row = await cur.fetchone()
        return _row_to_project(row) if row else None

    async def get_project_by_slug(self, slug: str) -> Project | None:
        async with self._conn.execute("SELECT * FROM projects WHERE slug = ?", (slug,)) as cur:
            row = await cur.fetchone()
        return _row_to_project(row) if row else None

    async def list_projects(self) -> list[Project]:
        async with self._conn.execute("SELECT * FROM projects ORDER BY created_at DESC") as cur:
            rows = await cur.fetchall()
        return [_row_to_project(r) for r in rows]

    async def list_projects_for_user(self, user_id: str) -> list[Project]:
        async with self._conn.execute(
            """
            SELECT p.* FROM projects p
            JOIN project_members m ON p.id = m.project_id
            WHERE m.user_id = ?
            ORDER BY p.created_at DESC
            """,
            (user_id,),
        ) as cur:
            rows = await cur.fetchall()
        return [_row_to_project(r) for r in rows]

    async def update_project(self, project_id: str, name: str, slug: str) -> bool:
        cursor = await self._conn.execute(
            "UPDATE projects SET name = ?, slug = ? WHERE id = ?", (name, slug, project_id)
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    async def delete_project(self, project_id: str) -> bool:
        await self._conn.execute("DELETE FROM project_members WHERE project_id = ?", (project_id,))
        cursor = await self._conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        await self._conn.commit()
        return cursor.rowcount > 0

    # ── Project membership ────────────────────────────────────────────────────

    async def add_member(self, member: ProjectMember) -> None:
        await self._conn.execute(
            "INSERT OR REPLACE INTO project_members (project_id, user_id, role, added_by, added_at) VALUES (?, ?, ?, ?, ?)",
            (member.project_id, member.user_id, member.role.value, member.added_by, member.added_at.isoformat()),
        )
        await self._conn.commit()

    async def get_member(self, project_id: str, user_id: str) -> ProjectMember | None:
        async with self._conn.execute(
            "SELECT * FROM project_members WHERE project_id = ? AND user_id = ?", (project_id, user_id)
        ) as cur:
            row = await cur.fetchone()
        return _row_to_member(row) if row else None

    async def list_members(self, project_id: str) -> list[ProjectMember]:
        async with self._conn.execute(
            "SELECT * FROM project_members WHERE project_id = ? ORDER BY added_at DESC", (project_id,)
        ) as cur:
            rows = await cur.fetchall()
        return [_row_to_member(r) for r in rows]

    async def update_member_role(self, project_id: str, user_id: str, role: str) -> bool:
        cursor = await self._conn.execute(
            "UPDATE project_members SET role = ? WHERE project_id = ? AND user_id = ?",
            (role, project_id, user_id),
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    async def remove_member(self, project_id: str, user_id: str) -> bool:
        cursor = await self._conn.execute(
            "DELETE FROM project_members WHERE project_id = ? AND user_id = ?", (project_id, user_id)
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    # ── User management ───────────────────────────────────────────────────────

    async def create_user(self, user: User) -> None:
        await self._conn.execute(
            """
            INSERT INTO users (id, email, password_hash, role, active, invited_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user.id, user.email, user.password_hash, user.role.value,
             1 if user.active else 0, user.invited_by, user.created_at.isoformat()),
        )
        await self._conn.commit()

    async def get_user_by_email(self, email: str) -> User | None:
        async with self._conn.execute(
            "SELECT * FROM users WHERE email = ? AND active = 1", (email,)
        ) as cursor:
            row = await cursor.fetchone()
        return _row_to_user(row) if row else None

    async def get_user_by_id(self, user_id: str) -> User | None:
        async with self._conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
        return _row_to_user(row) if row else None

    async def list_users(self) -> list[User]:
        async with self._conn.execute(
            "SELECT * FROM users ORDER BY created_at DESC"
        ) as cursor:
            rows = await cursor.fetchall()
        return [_row_to_user(r) for r in rows]

    async def update_user_role(self, user_id: str, role: str) -> bool:
        cursor = await self._conn.execute(
            "UPDATE users SET role = ? WHERE id = ?", (role, user_id)
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    async def deactivate_user(self, user_id: str) -> bool:
        cursor = await self._conn.execute(
            "UPDATE users SET active = 0 WHERE id = ?", (user_id,)
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    async def touch_user_login(self, user_id: str) -> None:
        await self._conn.execute(
            "UPDATE users SET last_login_at = ? WHERE id = ?",
            (datetime.now(UTC).isoformat(), user_id),
        )
        await self._conn.commit()

    async def count_users(self) -> int:
        async with self._conn.execute("SELECT COUNT(*) FROM users WHERE active = 1") as cursor:
            row = await cursor.fetchone()
        return row[0] if row else 0

    # ── Invite management ─────────────────────────────────────────────────────

    async def create_invite(self, invite: InviteToken) -> None:
        await self._conn.execute(
            """
            INSERT INTO invite_tokens (token, email, role, invited_by, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (invite.token, invite.email, invite.role.value, invite.invited_by,
             invite.created_at.isoformat(), invite.expires_at.isoformat()),
        )
        await self._conn.commit()

    async def get_invite(self, token: str) -> InviteToken | None:
        async with self._conn.execute(
            "SELECT * FROM invite_tokens WHERE token = ?", (token,)
        ) as cursor:
            row = await cursor.fetchone()
        return _row_to_invite(row) if row else None

    async def mark_invite_used(self, token: str) -> None:
        await self._conn.execute(
            "UPDATE invite_tokens SET used_at = ? WHERE token = ?",
            (datetime.now(UTC).isoformat(), token),
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
        role=ApiKeyRole(row["role"]) if row["role"] else ApiKeyRole.ADMIN,
        created_at=datetime.fromisoformat(row["created_at"]),
        last_used_at=datetime.fromisoformat(row["last_used_at"]) if row["last_used_at"] else None,
        revoked_at=datetime.fromisoformat(row["revoked_at"]) if row["revoked_at"] else None,
    )


def _row_to_model_pricing(row: aiosqlite.Row) -> ModelPricing:
    return ModelPricing(
        id=row["id"],
        provider=row["provider"],
        model_id=row["model_id"],
        display_name=row["display_name"],
        input_per_1m_usd=float(row["input_per_1m_usd"]),
        output_per_1m_usd=float(row["output_per_1m_usd"]),
        cache_read_per_1m_usd=float(row["cache_read_per_1m_usd"]),
        effective_from=datetime.fromisoformat(row["effective_from"]),
        effective_to=datetime.fromisoformat(row["effective_to"]) if row["effective_to"] else None,
        notes=row["notes"],
        is_custom=bool(row["is_custom"]),
    )


def _row_to_project(row: aiosqlite.Row) -> Project:
    return Project(
        id=row["id"],
        name=row["name"],
        slug=row["slug"],
        created_by=row["created_by"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _row_to_member(row: aiosqlite.Row) -> ProjectMember:
    return ProjectMember(
        project_id=row["project_id"],
        user_id=row["user_id"],
        role=ProjectRole(row["role"]),
        added_by=row["added_by"],
        added_at=datetime.fromisoformat(row["added_at"]),
    )


def _row_to_user(row: aiosqlite.Row) -> User:
    return User(
        id=row["id"],
        email=row["email"],
        password_hash=row["password_hash"],
        role=UserRole(row["role"]),
        active=bool(row["active"]),
        invited_by=row["invited_by"],
        created_at=datetime.fromisoformat(row["created_at"]),
        last_login_at=datetime.fromisoformat(row["last_login_at"]) if row["last_login_at"] else None,
    )


def _row_to_invite(row: aiosqlite.Row) -> InviteToken:
    return InviteToken(
        token=row["token"],
        email=row["email"],
        role=UserRole(row["role"]),
        invited_by=row["invited_by"],
        created_at=datetime.fromisoformat(row["created_at"]),
        expires_at=datetime.fromisoformat(row["expires_at"]),
        used_at=datetime.fromisoformat(row["used_at"]) if row["used_at"] else None,
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
