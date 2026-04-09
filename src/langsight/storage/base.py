from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from langsight.models import (
    AgentSLO,
    ApiKeyRecord,
    HealthCheckResult,
    InviteToken,
    ModelPricing,
    PreventionConfig,
    Project,
    ProjectMember,
    SchemaDriftEvent,
    User,
)


@runtime_checkable
class StorageBackend(Protocol):
    """Protocol that all storage backends must implement.

    Implementations: PostgresBackend (metadata), ClickHouseBackend (traces).
    The rest of the codebase talks only to this interface — never to a
    concrete backend directly. Switching backends is a config change.
    """

    async def save_health_result(self, result: HealthCheckResult) -> None:
        """Persist a health check result."""
        ...

    async def get_latest_schema_hash(self, server_name: str, project_id: str = "") -> str | None:
        """Return the most recently stored schema hash for a server, or None."""
        ...

    async def save_schema_snapshot(
        self,
        server_name: str,
        schema_hash: str,
        tools_count: int,
        project_id: str = "",
    ) -> None:
        """Persist a schema snapshot for drift comparison on the next run."""
        ...

    async def get_health_history(
        self,
        server_name: str,
        limit: int = 10,
        project_id: str | None = None,
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

    # ── Model pricing ────────────────────────────────────────────────────────

    async def list_model_pricing(self) -> list[ModelPricing]:
        """Return all model pricing entries (active and historical)."""
        ...

    async def get_active_model_pricing(self, model_id: str) -> ModelPricing | None:
        """Return the currently active pricing for a model_id, or None."""
        ...

    async def create_model_pricing(self, entry: ModelPricing) -> None:
        """Persist a new model pricing entry."""
        ...

    async def deactivate_model_pricing(self, entry_id: str) -> bool:
        """Set effective_to=now on a pricing entry. Returns True if found."""
        ...

    # ── Project management ───────────────────────────────────────────────────

    async def create_project(self, project: Project) -> None:
        """Persist a new project."""
        ...

    async def get_project(self, project_id: str) -> Project | None:
        """Return a project by ID, or None."""
        ...

    async def get_project_by_slug(self, slug: str) -> Project | None:
        """Return a project by slug, or None."""
        ...

    async def list_projects(self) -> list[Project]:
        """Return all projects (global admin view)."""
        ...

    async def list_projects_for_user(self, user_id: str) -> list[Project]:
        """Return projects where user has explicit membership."""
        ...

    async def update_project(self, project_id: str, name: str, slug: str) -> bool:
        """Rename a project. Returns True if found."""
        ...

    async def delete_project(self, project_id: str) -> bool:
        """Delete a project and all its memberships. Returns True if found."""
        ...

    # ── Project membership ────────────────────────────────────────────────────

    async def add_member(self, member: ProjectMember) -> None:
        """Add a user to a project."""
        ...

    async def get_member(self, project_id: str, user_id: str) -> ProjectMember | None:
        """Return a user's membership in a project, or None."""
        ...

    async def list_members(self, project_id: str) -> list[ProjectMember]:
        """Return all members of a project."""
        ...

    async def update_member_role(self, project_id: str, user_id: str, role: str) -> bool:
        """Change a member's project role. Returns True if found."""
        ...

    async def remove_member(self, project_id: str, user_id: str) -> bool:
        """Remove a user from a project. Returns True if found."""
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

    async def accept_invite(self, token: str, user: User) -> bool:
        """Atomically mark invite used + create user. Returns False on race."""
        ...

    # ── SLO management ───────────────────────────────────────────────────────

    async def create_slo(self, slo: AgentSLO) -> None:
        """Persist a new SLO definition."""
        ...

    async def list_slos(self, project_id: str | None = None) -> list[AgentSLO]:
        """Return SLO definitions. When project_id is set, returns only that project's SLOs."""
        ...

    async def get_slo(self, slo_id: str) -> AgentSLO | None:
        """Return a single SLO by ID, or None if not found."""
        ...

    async def delete_slo(self, slo_id: str, project_id: str | None = None) -> bool:
        """Delete an SLO. When project_id is set, only deletes within that project."""
        ...

    # ── Alert config ─────────────────────────────────────────────────────────

    async def get_alert_config(self, project_id: str = "") -> dict[str, Any] | None:
        """Return the persisted alert config for a project, or None if never saved."""
        ...

    async def save_alert_config(
        self,
        slack_webhook: str | None,
        alert_types: dict[str, bool],
        project_id: str = "",
    ) -> None:
        """Upsert the alert config row for a project."""
        ...

    # ── Fired alerts (persisted history + lifecycle) ─────────────────────────

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
        ...

    async def get_fired_alerts(
        self,
        project_id: str = "",
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Return fired alerts, most-recent-first."""
        ...

    async def count_fired_alerts(self, project_id: str = "", status: str | None = None) -> int:
        """Count fired alerts matching the given filters."""
        ...

    async def ack_alert(self, alert_id: str, acked_by: str = "user", project_id: str = "") -> bool:
        """Mark an alert as acknowledged. Returns True if updated."""
        ...

    async def resolve_alert(self, alert_id: str, project_id: str = "") -> bool:
        """Mark an alert as resolved. Returns True if updated."""
        ...

    async def snooze_alert(self, alert_id: str, snooze_minutes: int, project_id: str = "") -> bool:
        """Snooze an alert for N minutes. Returns True if updated."""
        ...

    async def get_alert_counts(self, project_id: str = "") -> dict[str, int]:
        """Return count of active alerts per severity."""
        ...

    # ── Audit logs ────────────────────────────────────────────────────────────

    async def append_audit_log(
        self,
        event: str,
        user_id: str,
        ip: str,
        details: dict[str, Any],
    ) -> None:
        """Append a new audit log entry."""
        ...

    async def list_audit_logs(self, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        """Return audit log entries most-recent-first."""
        ...

    async def count_audit_logs(self) -> int:
        """Return total number of audit log entries."""
        ...

    # -- Agent metadata (catalog) --

    async def get_all_agent_metadata(self, project_id: str | None = None) -> list[dict[str, Any]]:
        """List all agent metadata records."""
        ...

    async def get_agent_metadata(
        self, agent_name: str, project_id: str | None = None
    ) -> dict[str, Any] | None:
        """Get metadata for one agent by name."""
        ...

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
        """Create or update agent metadata."""
        ...

    async def delete_agent_metadata(self, agent_name: str, project_id: str | None = None) -> bool:
        """Delete agent metadata scoped to project."""
        ...

    async def get_all_server_metadata(self, project_id: str | None = None) -> list[dict[str, Any]]:
        """List all server metadata records."""
        ...

    async def get_server_metadata(
        self, server_name: str, project_id: str | None = None
    ) -> dict[str, Any] | None:
        """Get metadata for one server by name."""
        ...

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
        """Create or update server metadata."""
        ...

    async def delete_server_metadata(self, server_name: str, project_id: str | None = None) -> bool:
        """Delete server metadata scoped to project."""
        ...

    async def upsert_server_tools(
        self, server_name: str, tools: list[dict[str, object]], project_id: str | None = None
    ) -> None:
        """Upsert declared tools for a server (from SDK list_tools() interception)."""
        ...

    async def get_server_tools(
        self, server_name: str, project_id: str | None = None
    ) -> list[dict[str, object]]:
        """Get all declared tools for a server, scoped to project."""
        ...

    # ── v0.3 Prevention Config ───────────────────────────────────────────────

    async def list_prevention_configs(self, project_id: str) -> list[PreventionConfig]:
        """Return all prevention configs for a project, ordered by agent_name."""
        ...

    async def get_prevention_config(
        self, agent_name: str, project_id: str
    ) -> PreventionConfig | None:
        """Return config for this specific agent, or None if not configured."""
        ...

    async def get_effective_prevention_config(
        self, agent_name: str, project_id: str
    ) -> PreventionConfig | None:
        """Return agent-specific config, falling back to project default ('*')."""
        ...

    async def upsert_prevention_config(self, config: PreventionConfig) -> PreventionConfig:
        """Create or update prevention config for an agent."""
        ...

    async def delete_prevention_config(self, agent_name: str, project_id: str) -> bool:
        """Delete config for this agent. Returns True if found and deleted."""
        ...

    # ── v0.3 Session health tags ─────────────────────────────────────────────

    async def save_session_health_tag(
        self,
        session_id: str,
        health_tag: str,
        details: str | None = None,
        project_id: str | None = None,
    ) -> None:
        """Persist (or replace) a health tag for a session."""
        ...

    async def get_session_health_tag(
        self, session_id: str, project_id: str | None = None
    ) -> str | None:
        """Return the health tag for a session, or None."""
        ...

    async def get_untagged_sessions(
        self,
        inactive_seconds: int = 30,
        limit: int = 100,
        project_id: str | None = None,
    ) -> list[str]:
        """Return session_ids with no health tag that have been inactive for N seconds."""
        ...

    async def save_schema_drift_event(self, event: SchemaDriftEvent) -> None:
        """Persist a schema drift event (one row per SchemaChange)."""
        ...

    async def get_schema_drift_history(
        self,
        server_name: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Return recent drift events for a server, newest first."""
        ...

    async def get_drift_impact(
        self,
        server_name: str,
        tool_name: str,
        hours: int = 24,
        project_id: str = "",
    ) -> list[dict[str, Any]]:
        """Return agents/sessions that called a tool recently (consumer impact)."""
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
