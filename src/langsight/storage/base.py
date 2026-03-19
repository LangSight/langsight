from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from langsight.models import AgentSLO, ApiKeyRecord, HealthCheckResult, InviteToken, User


@runtime_checkable
class StorageBackend(Protocol):
    """Protocol that all storage backends must implement.

    Implementations: SQLiteBackend (Phase 1), PostgresBackend (Phase 2),
    ClickHouseBackend (Phase 3).
    The rest of the codebase talks only to this interface — never to a
    concrete backend directly. Switching backends is a config change.
    """

    async def save_health_result(self, result: HealthCheckResult) -> None:
        """Persist a health check result."""
        ...

    async def get_latest_schema_hash(self, server_name: str) -> str | None:
        """Return the most recently stored schema hash for a server, or None."""
        ...

    async def save_schema_snapshot(
        self,
        server_name: str,
        schema_hash: str,
        tools_count: int,
    ) -> None:
        """Persist a schema snapshot for drift comparison on the next run."""
        ...

    async def get_health_history(
        self,
        server_name: str,
        limit: int = 10,
    ) -> list[HealthCheckResult]:
        """Return the N most recent health results for a server, newest first."""
        ...

    # ── API key management ────────────────────────────────────────────────────

    async def create_api_key(self, record: ApiKeyRecord) -> None:
        """Persist a new API key record (key_hash already hashed by caller)."""
        ...

    async def list_api_keys(self) -> list[ApiKeyRecord]:
        """Return all non-revoked API key records, newest first."""
        ...

    async def get_api_key_by_hash(self, key_hash: str) -> ApiKeyRecord | None:
        """Look up a key by its hash. Returns None if not found or revoked."""
        ...

    async def revoke_api_key(self, key_id: str) -> bool:
        """Mark a key as revoked. Returns True if found, False if not."""
        ...

    async def touch_api_key(self, key_id: str) -> None:
        """Update last_used_at to now (called on each authenticated request)."""
        ...

    # ── User management ──────────────────────────────────────────────────────

    async def create_user(self, user: User) -> None:
        """Persist a new user account."""
        ...

    async def get_user_by_email(self, email: str) -> User | None:
        """Look up a user by email. Returns None if not found or inactive."""
        ...

    async def get_user_by_id(self, user_id: str) -> User | None:
        """Look up a user by ID."""
        ...

    async def list_users(self) -> list[User]:
        """Return all users (active and inactive), newest first."""
        ...

    async def update_user_role(self, user_id: str, role: str) -> bool:
        """Change a user's role. Returns True if found."""
        ...

    async def deactivate_user(self, user_id: str) -> bool:
        """Deactivate a user account. Returns True if found."""
        ...

    async def touch_user_login(self, user_id: str) -> None:
        """Update last_login_at to now."""
        ...

    async def count_users(self) -> int:
        """Return total number of users (used for first-run bootstrap detection)."""
        ...

    # ── Invite management ────────────────────────────────────────────────────

    async def create_invite(self, invite: InviteToken) -> None:
        """Persist an invite token."""
        ...

    async def get_invite(self, token: str) -> InviteToken | None:
        """Look up an invite by token. Returns None if not found."""
        ...

    async def mark_invite_used(self, token: str) -> None:
        """Mark an invite as used."""
        ...

    # ── SLO management ───────────────────────────────────────────────────────

    async def create_slo(self, slo: AgentSLO) -> None:
        """Persist a new SLO definition."""
        ...

    async def list_slos(self) -> list[AgentSLO]:
        """Return all SLO definitions."""
        ...

    async def get_slo(self, slo_id: str) -> AgentSLO | None:
        """Return a single SLO by ID, or None if not found."""
        ...

    async def delete_slo(self, slo_id: str) -> bool:
        """Delete an SLO. Returns True if found and deleted."""
        ...

    async def close(self) -> None:
        """Release any resources held by the backend (connections, file handles)."""
        ...

    async def __aenter__(self) -> StorageBackend:
        """Enter async context manager."""
        ...

    async def __aexit__(self, *args: Any) -> None:
        """Exit async context manager — calls close()."""
        ...
