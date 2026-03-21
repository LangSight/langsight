"""
Unit tests for storage/dual.py — DualStorage routing class.

Verifies that every method in the StorageBackend protocol routes to
the correct backend:
  - analytics (health, spans, schema)  → ClickHouseBackend (_analytics)
  - metadata  (users, projects, etc.)  → PostgresBackend   (_meta)
  - lifecycle (close, context manager)
  - __getattr__ extension method fallback → _analytics
"""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

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
from langsight.storage.dual import DualStorage

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def meta() -> MagicMock:
    """Mock PostgresBackend (metadata store)."""
    m = MagicMock()
    m.close = AsyncMock()
    return m


@pytest.fixture
def analytics() -> MagicMock:
    """Mock ClickHouseBackend (analytics store)."""
    a = MagicMock()
    a.close = AsyncMock()
    return a


@pytest.fixture
def storage(meta: MagicMock, analytics: MagicMock) -> DualStorage:
    return DualStorage(meta, analytics)


def _health() -> HealthCheckResult:
    return HealthCheckResult(
        server_name="test-server",
        status="up",
        latency_ms=42.0,
        tools_count=3,
        schema_hash="abc",
        error=None,
        checked_at=datetime.now(UTC),
    )


def _span() -> ToolCallSpan:
    return MagicMock(spec=ToolCallSpan)


def _user() -> User:
    return MagicMock(spec=User)


def _project() -> Project:
    return MagicMock(spec=Project)


def _api_key() -> ApiKeyRecord:
    return MagicMock(spec=ApiKeyRecord)


# ---------------------------------------------------------------------------
# Analytics → ClickHouse
# ---------------------------------------------------------------------------

class TestAnalyticsRouting:
    async def test_save_health_result_goes_to_analytics(
        self, storage: DualStorage, meta: MagicMock, analytics: MagicMock
    ) -> None:
        analytics.save_health_result = AsyncMock()
        result = _health()
        await storage.save_health_result(result)
        analytics.save_health_result.assert_called_once_with(result)
        meta.save_health_result.assert_not_called()

    async def test_get_latest_schema_hash_goes_to_analytics(
        self, storage: DualStorage, meta: MagicMock, analytics: MagicMock
    ) -> None:
        analytics.get_latest_schema_hash = AsyncMock(return_value="hashval")
        result = await storage.get_latest_schema_hash("my-server")
        assert result == "hashval"
        analytics.get_latest_schema_hash.assert_called_once_with("my-server")
        meta.get_latest_schema_hash.assert_not_called()

    async def test_save_schema_snapshot_goes_to_analytics(
        self, storage: DualStorage, meta: MagicMock, analytics: MagicMock
    ) -> None:
        analytics.save_schema_snapshot = AsyncMock()
        await storage.save_schema_snapshot("srv", "h123", 5)
        analytics.save_schema_snapshot.assert_called_once_with("srv", "h123", 5)
        meta.save_schema_snapshot.assert_not_called()

    async def test_get_health_history_goes_to_analytics(
        self, storage: DualStorage, meta: MagicMock, analytics: MagicMock
    ) -> None:
        expected = [_health()]
        analytics.get_health_history = AsyncMock(return_value=expected)
        result = await storage.get_health_history("srv", limit=5)
        assert result is expected
        analytics.get_health_history.assert_called_once_with("srv", 5)

    async def test_save_tool_call_span_goes_to_analytics(
        self, storage: DualStorage, meta: MagicMock, analytics: MagicMock
    ) -> None:
        analytics.save_tool_call_span = AsyncMock()
        span = _span()
        await storage.save_tool_call_span(span)
        analytics.save_tool_call_span.assert_called_once_with(span)

    async def test_save_tool_call_spans_goes_to_analytics(
        self, storage: DualStorage, meta: MagicMock, analytics: MagicMock
    ) -> None:
        analytics.save_tool_call_spans = AsyncMock()
        spans = [_span(), _span()]
        await storage.save_tool_call_spans(spans)
        analytics.save_tool_call_spans.assert_called_once_with(spans)


# ---------------------------------------------------------------------------
# Metadata → Postgres
# ---------------------------------------------------------------------------

class TestApiKeyRouting:
    async def test_create_api_key_goes_to_meta(
        self, storage: DualStorage, meta: MagicMock, analytics: MagicMock
    ) -> None:
        meta.create_api_key = AsyncMock()
        record = _api_key()
        await storage.create_api_key(record)
        meta.create_api_key.assert_called_once_with(record)
        analytics.create_api_key.assert_not_called()

    async def test_list_api_keys_goes_to_meta(
        self, storage: DualStorage, meta: MagicMock, analytics: MagicMock
    ) -> None:
        expected = [_api_key()]
        meta.list_api_keys = AsyncMock(return_value=expected)
        result = await storage.list_api_keys()
        assert result is expected
        analytics.list_api_keys.assert_not_called()

    async def test_get_api_key_by_hash_goes_to_meta(
        self, storage: DualStorage, meta: MagicMock, analytics: MagicMock
    ) -> None:
        record = _api_key()
        meta.get_api_key_by_hash = AsyncMock(return_value=record)
        result = await storage.get_api_key_by_hash("sha256hex")
        assert result is record
        analytics.get_api_key_by_hash.assert_not_called()

    async def test_revoke_api_key_goes_to_meta(
        self, storage: DualStorage, meta: MagicMock
    ) -> None:
        meta.revoke_api_key = AsyncMock(return_value=True)
        assert await storage.revoke_api_key("key-id") is True

    async def test_touch_api_key_goes_to_meta(
        self, storage: DualStorage, meta: MagicMock
    ) -> None:
        meta.touch_api_key = AsyncMock()
        await storage.touch_api_key("key-id")
        meta.touch_api_key.assert_called_once_with("key-id")


class TestModelPricingRouting:
    async def test_list_model_pricing_goes_to_meta(
        self, storage: DualStorage, meta: MagicMock, analytics: MagicMock
    ) -> None:
        meta.list_model_pricing = AsyncMock(return_value=[])
        result = await storage.list_model_pricing()
        assert result == []
        analytics.list_model_pricing.assert_not_called()

    async def test_create_model_pricing_goes_to_meta(
        self, storage: DualStorage, meta: MagicMock
    ) -> None:
        meta.create_model_pricing = AsyncMock()
        entry = MagicMock(spec=ModelPricing)
        await storage.create_model_pricing(entry)
        meta.create_model_pricing.assert_called_once_with(entry)

    async def test_deactivate_model_pricing_goes_to_meta(
        self, storage: DualStorage, meta: MagicMock
    ) -> None:
        meta.deactivate_model_pricing = AsyncMock(return_value=True)
        assert await storage.deactivate_model_pricing("entry-id") is True


class TestProjectRouting:
    async def test_create_project_goes_to_meta(
        self, storage: DualStorage, meta: MagicMock, analytics: MagicMock
    ) -> None:
        meta.create_project = AsyncMock()
        project = _project()
        await storage.create_project(project)
        meta.create_project.assert_called_once_with(project)
        analytics.create_project.assert_not_called()

    async def test_get_project_goes_to_meta(
        self, storage: DualStorage, meta: MagicMock
    ) -> None:
        project = _project()
        meta.get_project = AsyncMock(return_value=project)
        result = await storage.get_project("proj-1")
        assert result is project

    async def test_list_projects_goes_to_meta(
        self, storage: DualStorage, meta: MagicMock, analytics: MagicMock
    ) -> None:
        meta.list_projects = AsyncMock(return_value=[_project()])
        result = await storage.list_projects()
        assert len(result) == 1
        analytics.list_projects.assert_not_called()

    async def test_list_projects_for_user_goes_to_meta(
        self, storage: DualStorage, meta: MagicMock
    ) -> None:
        meta.list_projects_for_user = AsyncMock(return_value=[])
        await storage.list_projects_for_user("user-1")
        meta.list_projects_for_user.assert_called_once_with("user-1")

    async def test_update_project_goes_to_meta(
        self, storage: DualStorage, meta: MagicMock
    ) -> None:
        meta.update_project = AsyncMock(return_value=True)
        result = await storage.update_project("p1", "New Name", "new-slug")
        assert result is True

    async def test_delete_project_goes_to_meta(
        self, storage: DualStorage, meta: MagicMock
    ) -> None:
        meta.delete_project = AsyncMock(return_value=True)
        assert await storage.delete_project("proj-1") is True


class TestMemberRouting:
    async def test_add_member_goes_to_meta(
        self, storage: DualStorage, meta: MagicMock
    ) -> None:
        meta.add_member = AsyncMock()
        member = MagicMock(spec=ProjectMember)
        await storage.add_member(member)
        meta.add_member.assert_called_once_with(member)

    async def test_get_member_goes_to_meta(
        self, storage: DualStorage, meta: MagicMock, analytics: MagicMock
    ) -> None:
        member = MagicMock(spec=ProjectMember)
        meta.get_member = AsyncMock(return_value=member)
        result = await storage.get_member("p1", "u1")
        assert result is member
        analytics.get_member.assert_not_called()

    async def test_list_members_goes_to_meta(
        self, storage: DualStorage, meta: MagicMock
    ) -> None:
        meta.list_members = AsyncMock(return_value=[])
        await storage.list_members("p1")
        meta.list_members.assert_called_once_with("p1")

    async def test_remove_member_goes_to_meta(
        self, storage: DualStorage, meta: MagicMock
    ) -> None:
        meta.remove_member = AsyncMock(return_value=True)
        assert await storage.remove_member("p1", "u1") is True


class TestUserRouting:
    async def test_create_user_goes_to_meta(
        self, storage: DualStorage, meta: MagicMock, analytics: MagicMock
    ) -> None:
        meta.create_user = AsyncMock()
        user = _user()
        await storage.create_user(user)
        meta.create_user.assert_called_once_with(user)
        analytics.create_user.assert_not_called()

    async def test_get_user_by_email_goes_to_meta(
        self, storage: DualStorage, meta: MagicMock
    ) -> None:
        user = _user()
        meta.get_user_by_email = AsyncMock(return_value=user)
        result = await storage.get_user_by_email("a@b.com")
        assert result is user

    async def test_list_users_goes_to_meta(
        self, storage: DualStorage, meta: MagicMock, analytics: MagicMock
    ) -> None:
        meta.list_users = AsyncMock(return_value=[])
        await storage.list_users()
        analytics.list_users.assert_not_called()

    async def test_count_users_goes_to_meta(
        self, storage: DualStorage, meta: MagicMock
    ) -> None:
        meta.count_users = AsyncMock(return_value=5)
        assert await storage.count_users() == 5

    async def test_touch_user_login_goes_to_meta(
        self, storage: DualStorage, meta: MagicMock
    ) -> None:
        meta.touch_user_login = AsyncMock()
        await storage.touch_user_login("u1")
        meta.touch_user_login.assert_called_once_with("u1")


class TestInviteRouting:
    async def test_create_invite_goes_to_meta(
        self, storage: DualStorage, meta: MagicMock, analytics: MagicMock
    ) -> None:
        meta.create_invite = AsyncMock()
        invite = MagicMock(spec=InviteToken)
        await storage.create_invite(invite)
        meta.create_invite.assert_called_once_with(invite)
        analytics.create_invite.assert_not_called()

    async def test_get_invite_goes_to_meta(
        self, storage: DualStorage, meta: MagicMock
    ) -> None:
        invite = MagicMock(spec=InviteToken)
        meta.get_invite = AsyncMock(return_value=invite)
        result = await storage.get_invite("token-abc")
        assert result is invite

    async def test_mark_invite_used_goes_to_meta(
        self, storage: DualStorage, meta: MagicMock
    ) -> None:
        meta.mark_invite_used = AsyncMock()
        await storage.mark_invite_used("token-abc")
        meta.mark_invite_used.assert_called_once_with("token-abc")

    async def test_accept_invite_goes_to_meta(
        self, storage: DualStorage, meta: MagicMock, analytics: MagicMock
    ) -> None:
        meta.accept_invite = AsyncMock(return_value=True)
        user = _user()
        result = await storage.accept_invite("token-xyz", user)
        assert result is True
        meta.accept_invite.assert_called_once_with("token-xyz", user)
        analytics.accept_invite.assert_not_called()


class TestSLORouting:
    async def test_create_slo_goes_to_meta(
        self, storage: DualStorage, meta: MagicMock, analytics: MagicMock
    ) -> None:
        meta.create_slo = AsyncMock()
        slo = MagicMock(spec=AgentSLO)
        await storage.create_slo(slo)
        meta.create_slo.assert_called_once_with(slo)
        analytics.create_slo.assert_not_called()

    async def test_list_slos_goes_to_meta(
        self, storage: DualStorage, meta: MagicMock
    ) -> None:
        meta.list_slos = AsyncMock(return_value=[])
        result = await storage.list_slos()
        assert result == []

    async def test_delete_slo_goes_to_meta(
        self, storage: DualStorage, meta: MagicMock
    ) -> None:
        meta.delete_slo = AsyncMock(return_value=True)
        assert await storage.delete_slo("slo-id") is True


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

class TestLifecycle:
    async def test_close_closes_both_backends(
        self, storage: DualStorage, meta: MagicMock, analytics: MagicMock
    ) -> None:
        await storage.close()
        meta.close.assert_called_once()
        analytics.close.assert_called_once()

    async def test_close_re_raises_meta_exception(
        self, storage: DualStorage, meta: MagicMock, analytics: MagicMock
    ) -> None:
        meta.close = AsyncMock(side_effect=RuntimeError("meta close failed"))
        with pytest.raises(RuntimeError, match="meta close failed"):
            await storage.close()

    async def test_context_manager_calls_close(
        self, meta: MagicMock, analytics: MagicMock
    ) -> None:
        async with DualStorage(meta, analytics) as s:
            assert s is not None
        meta.close.assert_called_once()
        analytics.close.assert_called_once()

    async def test_aenter_returns_self(
        self, storage: DualStorage
    ) -> None:
        result = await storage.__aenter__()
        assert result is storage


# ---------------------------------------------------------------------------
# Extension method fallback (__getattr__)
# ---------------------------------------------------------------------------

class TestExtensionFallback:
    async def test_get_session_trace_forwards_to_analytics(
        self, storage: DualStorage, analytics: MagicMock
    ) -> None:
        """ClickHouse-specific get_session_trace falls through to analytics."""
        analytics.get_session_trace = AsyncMock(return_value={"spans": []})
        result = await storage.get_session_trace("sess-1")
        analytics.get_session_trace.assert_called_once_with("sess-1")
        assert result == {"spans": []}

    async def test_get_agent_sessions_forwards_to_analytics(
        self, storage: DualStorage, analytics: MagicMock
    ) -> None:
        analytics.get_agent_sessions = AsyncMock(return_value=[])
        result = await storage.get_agent_sessions(hours=1)
        analytics.get_agent_sessions.assert_called_once_with(hours=1)
        assert result == []

    def test_unknown_attr_resolves_to_analytics_attribute(
        self, storage: DualStorage, analytics: MagicMock
    ) -> None:
        analytics.some_custom_method = "custom_value"
        assert storage.some_custom_method == "custom_value"


class TestAlertConfigRouting:
    async def test_get_alert_config_goes_to_meta(
        self, storage: DualStorage, meta: MagicMock, analytics: MagicMock
    ) -> None:
        meta.get_alert_config = AsyncMock(return_value=None)
        result = await storage.get_alert_config()
        assert result is None
        meta.get_alert_config.assert_called_once()
        analytics.get_alert_config.assert_not_called()

    async def test_save_alert_config_goes_to_meta(
        self, storage: DualStorage, meta: MagicMock, analytics: MagicMock
    ) -> None:
        meta.save_alert_config = AsyncMock()
        await storage.save_alert_config("https://hooks.slack.com/x", {"mcp_down": True})
        meta.save_alert_config.assert_called_once_with(
            "https://hooks.slack.com/x", {"mcp_down": True}
        )
        analytics.save_alert_config.assert_not_called()


class TestAuditLogRouting:
    async def test_append_audit_log_goes_to_meta(
        self, storage: DualStorage, meta: MagicMock, analytics: MagicMock
    ) -> None:
        meta.append_audit_log = AsyncMock()
        await storage.append_audit_log("evt", "u1", "1.2.3.4", {"k": "v"})
        meta.append_audit_log.assert_called_once_with("evt", "u1", "1.2.3.4", {"k": "v"})
        analytics.append_audit_log.assert_not_called()

    async def test_list_audit_logs_goes_to_meta(
        self, storage: DualStorage, meta: MagicMock, analytics: MagicMock
    ) -> None:
        meta.list_audit_logs = AsyncMock(return_value=[])
        result = await storage.list_audit_logs(limit=10, offset=0)
        assert result == []
        meta.list_audit_logs.assert_called_once_with(10, 0)

    async def test_count_audit_logs_goes_to_meta(
        self, storage: DualStorage, meta: MagicMock, analytics: MagicMock
    ) -> None:
        meta.count_audit_logs = AsyncMock(return_value=42)
        result = await storage.count_audit_logs()
        assert result == 42
        analytics.count_audit_logs.assert_not_called()


# ---------------------------------------------------------------------------
# Protocol conformance — auto-detect missing delegations
# ---------------------------------------------------------------------------

class TestProtocolConformance:
    """Verify DualStorage explicitly implements every method in StorageBackend.

    This catches bugs like the missing accept_invite delegation: if someone adds
    a method to the StorageBackend protocol but forgets to add it to DualStorage,
    this test will fail immediately.

    Methods handled by __getattr__ (forwarded to analytics) are NOT considered
    explicit implementations — only methods defined directly on DualStorage count.
    """

    def test_all_protocol_methods_are_explicitly_implemented(self) -> None:
        import inspect

        from langsight.storage.base import StorageBackend

        # Get all public async methods from the protocol (excluding dunder)
        protocol_methods = {
            name
            for name, _ in inspect.getmembers(StorageBackend, predicate=inspect.isfunction)
            if not name.startswith("_")
        }

        # Get methods explicitly defined on DualStorage class (not inherited, not __getattr__)
        dual_methods = {
            name
            for name in dir(DualStorage)
            if not name.startswith("_") and name in protocol_methods
            and name in DualStorage.__dict__  # must be defined on DualStorage itself
        }

        # __getattr__ catches anything not explicitly defined and routes to _analytics.
        # That's fine for ClickHouse extension methods, but protocol methods MUST be
        # explicitly delegated so the routing target (meta vs analytics) is intentional.
        missing = protocol_methods - dual_methods - {"close", "__aenter__", "__aexit__"}
        # close/__aenter__/__aexit__ are lifecycle methods that may delegate differently

        # Check lifecycle methods exist too (they're special-cased above for clarity)
        for lifecycle in ("close",):
            assert lifecycle in DualStorage.__dict__, (
                f"DualStorage is missing explicit implementation of lifecycle method: {lifecycle}"
            )

        assert not missing, (
            f"DualStorage is missing explicit implementations for these StorageBackend methods "
            f"(they would fall through to __getattr__ → analytics, which may be wrong):\n"
            f"  {sorted(missing)}\n"
            f"Add explicit delegation in dual.py for each."
        )
