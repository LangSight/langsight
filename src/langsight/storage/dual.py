"""Dual-storage backend — production LangSight deployment topology.

Routes every storage operation to the appropriate backend:

  metadata_store (PostgresBackend)
      users, projects, API keys, model pricing, SLOs, invite tokens
      — relational, low-volume, strong consistency required

  analytics_store (ClickHouseBackend)
      spans, traces, health results, reliability stats, costs
      — time-series, high-volume, append-only

This class is transparent to all callers: it satisfies the StorageBackend
protocol and forwards each method to the right backend. No router, dependency,
or model code needs to know about the split.

Usage (configured automatically by factory.py when mode = "dual"):

    storage = await open_storage(config)   # returns DualStorage
    await storage.save_health_result(...)  # → ClickHouse
    await storage.list_users()             # → Postgres
"""

from __future__ import annotations

import asyncio
from typing import Any

from langsight.models import (
    AgentSLO,
    ApiKeyRecord,
    HealthCheckResult,
    InviteToken,
    ModelPricing,
    Project,
    ProjectMember,
    User,
)
from langsight.sdk.models import ToolCallSpan
from langsight.storage.clickhouse import ClickHouseBackend
from langsight.storage.postgres import PostgresBackend


class DualStorage:
    """Routes metadata ops to Postgres and analytics ops to ClickHouse.

    All StorageBackend protocol methods are explicitly implemented here so that
    type checkers and IDE tooling see a complete surface. ClickHouse-specific
    extension methods (get_session_trace, compare_sessions, get_cost_call_counts,
    get_tool_reliability, get_baseline_stats) are forwarded via __getattr__.
    """

    def __init__(self, metadata: PostgresBackend, analytics: ClickHouseBackend) -> None:
        self._meta = metadata
        self._analytics = analytics

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def close(self) -> None:
        """Close both backends concurrently; surface any exceptions."""
        results = await asyncio.gather(
            self._meta.close(),
            self._analytics.close(),
            return_exceptions=True,
        )
        # Re-raise first exception (if any) so callers know teardown failed
        for r in results:
            if isinstance(r, BaseException):
                raise r

    async def ping(self) -> dict[str, str]:
        """Probe both backends and return per-backend status.

        Used by the /api/readiness endpoint to verify both Postgres and
        ClickHouse are reachable before declaring the instance ready.

        Returns a dict like::

            {"postgres": "ok", "clickhouse": "ok"}

        Any unreachable backend has its value set to "error: <reason>".
        """

        async def _ping_meta() -> str:
            try:
                await self._meta.count_users()
                return "ok"
            except Exception as exc:  # noqa: BLE001
                return f"error: {exc}"

        async def _ping_analytics() -> str:
            try:
                await self._analytics.get_health_history("__probe__", limit=1)
                return "ok"
            except Exception as exc:  # noqa: BLE001
                return f"error: {exc}"

        postgres_status, clickhouse_status = await asyncio.gather(_ping_meta(), _ping_analytics())
        return {"postgres": postgres_status, "clickhouse": clickhouse_status}

    async def __aenter__(self) -> DualStorage:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    # ── Analytics → ClickHouse ────────────────────────────────────────────────
    # Health monitoring

    async def save_health_result(self, result: HealthCheckResult) -> None:
        return await self._analytics.save_health_result(result)

    async def get_latest_schema_hash(self, server_name: str) -> str | None:
        return await self._analytics.get_latest_schema_hash(server_name)

    async def save_schema_snapshot(
        self,
        server_name: str,
        schema_hash: str,
        tools_count: int,
    ) -> None:
        return await self._analytics.save_schema_snapshot(server_name, schema_hash, tools_count)

    async def get_health_history(
        self,
        server_name: str,
        limit: int = 10,
    ) -> list[HealthCheckResult]:
        return await self._analytics.get_health_history(server_name, limit)

    # Span ingestion

    async def save_tool_call_span(self, span: ToolCallSpan) -> None:
        return await self._analytics.save_tool_call_span(span)

    async def save_tool_call_spans(self, spans: list[ToolCallSpan]) -> None:
        return await self._analytics.save_tool_call_spans(spans)

    # ── Metadata → Postgres ───────────────────────────────────────────────────
    # API keys

    async def create_api_key(self, record: ApiKeyRecord) -> None:
        return await self._meta.create_api_key(record)

    async def list_api_keys(self) -> list[ApiKeyRecord]:
        return await self._meta.list_api_keys()

    async def get_api_key_by_hash(self, key_hash: str) -> ApiKeyRecord | None:
        return await self._meta.get_api_key_by_hash(key_hash)

    async def revoke_api_key(self, key_id: str) -> bool:
        return await self._meta.revoke_api_key(key_id)

    async def touch_api_key(self, key_id: str) -> None:
        return await self._meta.touch_api_key(key_id)

    # Model pricing

    async def list_model_pricing(self) -> list[ModelPricing]:
        return await self._meta.list_model_pricing()

    async def get_active_model_pricing(self, model_id: str) -> ModelPricing | None:
        return await self._meta.get_active_model_pricing(model_id)

    async def create_model_pricing(self, entry: ModelPricing) -> None:
        return await self._meta.create_model_pricing(entry)

    async def deactivate_model_pricing(self, entry_id: str) -> bool:
        return await self._meta.deactivate_model_pricing(entry_id)

    # Projects

    async def create_project(self, project: Project) -> None:
        return await self._meta.create_project(project)

    async def get_project(self, project_id: str) -> Project | None:
        return await self._meta.get_project(project_id)

    async def get_project_by_slug(self, slug: str) -> Project | None:
        return await self._meta.get_project_by_slug(slug)

    async def list_projects(self) -> list[Project]:
        return await self._meta.list_projects()

    async def list_projects_for_user(self, user_id: str) -> list[Project]:
        return await self._meta.list_projects_for_user(user_id)

    async def update_project(self, project_id: str, name: str, slug: str) -> bool:
        return await self._meta.update_project(project_id, name, slug)

    async def delete_project(self, project_id: str) -> bool:
        return await self._meta.delete_project(project_id)

    # Project membership

    async def add_member(self, member: ProjectMember) -> None:
        return await self._meta.add_member(member)

    async def get_member(self, project_id: str, user_id: str) -> ProjectMember | None:
        return await self._meta.get_member(project_id, user_id)

    async def list_members(self, project_id: str) -> list[ProjectMember]:
        return await self._meta.list_members(project_id)

    async def update_member_role(self, project_id: str, user_id: str, role: str) -> bool:
        return await self._meta.update_member_role(project_id, user_id, role)

    async def remove_member(self, project_id: str, user_id: str) -> bool:
        return await self._meta.remove_member(project_id, user_id)

    # Users

    async def create_user(self, user: User) -> None:
        return await self._meta.create_user(user)

    async def get_user_by_email(self, email: str) -> User | None:
        return await self._meta.get_user_by_email(email)

    async def get_user_by_id(self, user_id: str) -> User | None:
        return await self._meta.get_user_by_id(user_id)

    async def list_users(self) -> list[User]:
        return await self._meta.list_users()

    async def update_user_role(self, user_id: str, role: str) -> bool:
        return await self._meta.update_user_role(user_id, role)

    async def deactivate_user(self, user_id: str) -> bool:
        return await self._meta.deactivate_user(user_id)

    async def touch_user_login(self, user_id: str) -> None:
        return await self._meta.touch_user_login(user_id)

    async def count_users(self) -> int:
        return await self._meta.count_users()

    # Invite tokens

    async def create_invite(self, invite: InviteToken) -> None:
        return await self._meta.create_invite(invite)

    async def get_invite(self, token: str) -> InviteToken | None:
        return await self._meta.get_invite(token)

    async def mark_invite_used(self, token: str) -> None:
        return await self._meta.mark_invite_used(token)

    # SLOs

    async def create_slo(self, slo: AgentSLO) -> None:
        return await self._meta.create_slo(slo)

    async def list_slos(self) -> list[AgentSLO]:
        return await self._meta.list_slos()

    async def get_slo(self, slo_id: str) -> AgentSLO | None:
        return await self._meta.get_slo(slo_id)

    async def delete_slo(self, slo_id: str) -> bool:
        return await self._meta.delete_slo(slo_id)

    # Alert config → Postgres

    async def get_alert_config(self) -> dict[str, Any] | None:
        return await self._meta.get_alert_config()

    async def save_alert_config(
        self, slack_webhook: str | None, alert_types: dict[str, bool]
    ) -> None:
        return await self._meta.save_alert_config(slack_webhook, alert_types)

    # Audit logs → Postgres

    async def append_audit_log(
        self,
        event: str,
        user_id: str,
        ip: str,
        details: dict[str, Any],
    ) -> None:
        return await self._meta.append_audit_log(event, user_id, ip, details)

    async def list_audit_logs(self, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        return await self._meta.list_audit_logs(limit, offset)

    async def count_audit_logs(self) -> int:
        return await self._meta.count_audit_logs()

    # Lineage graph → ClickHouse

    async def get_lineage_graph(
        self,
        hours: int = 168,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        return await self._analytics.get_lineage_graph(hours=hours, project_id=project_id)

    # Agent metadata → Postgres

    async def get_all_agent_metadata(self, project_id: str | None = None) -> list[dict[str, Any]]:
        return await self._meta.get_all_agent_metadata(project_id=project_id)

    async def get_agent_metadata(self, agent_name: str, project_id: str | None = None) -> dict[str, Any] | None:
        return await self._meta.get_agent_metadata(agent_name, project_id=project_id)

    async def upsert_agent_metadata(self, agent_name: str, description: str, owner: str, tags: list[str], status: str, runbook_url: str, project_id: str | None = None) -> dict[str, Any]:
        return await self._meta.upsert_agent_metadata(agent_name, description, owner, tags, status, runbook_url, project_id)

    async def delete_agent_metadata(self, agent_name: str, project_id: str | None = None) -> bool:
        return await self._meta.delete_agent_metadata(agent_name, project_id=project_id)

    # Server metadata → Postgres

    async def get_all_server_metadata(self, project_id: str | None = None) -> list[dict[str, Any]]:
        return await self._meta.get_all_server_metadata(project_id=project_id)

    async def get_server_metadata(self, server_name: str, project_id: str | None = None) -> dict[str, Any] | None:
        return await self._meta.get_server_metadata(server_name, project_id=project_id)

    async def upsert_server_metadata(self, *, server_name: str, description: str = "", owner: str = "", tags: list[str] | None = None, transport: str = "", runbook_url: str = "", project_id: str | None = None) -> dict[str, Any]:
        return await self._meta.upsert_server_metadata(server_name=server_name, description=description, owner=owner, tags=tags, transport=transport, runbook_url=runbook_url, project_id=project_id)

    async def delete_server_metadata(self, server_name: str, project_id: str | None = None) -> bool:
        return await self._meta.delete_server_metadata(server_name, project_id=project_id)

    async def upsert_server_tools(self, server_name: str, tools: list[dict[str, object]], project_id: str | None = None) -> None:
        return await self._meta.upsert_server_tools(server_name, tools, project_id=project_id)

    async def get_server_tools(self, server_name: str, project_id: str | None = None) -> list[dict[str, object]]:
        return await self._meta.get_server_tools(server_name, project_id=project_id)

    # ── ClickHouse extension methods ──────────────────────────────────────────
    # Methods not in the base StorageBackend protocol but used by API routers
    # via hasattr/getattr (e.g. get_session_trace, compare_sessions,
    # get_cost_call_counts, get_tool_reliability, get_baseline_stats,
    # get_agent_sessions, get_lineage_graph). Delegated transparently to the
    # analytics backend.

    def __getattr__(self, name: str) -> Any:
        """Forward any unresolved attribute to the analytics (ClickHouse) backend."""
        return getattr(self._analytics, name)
