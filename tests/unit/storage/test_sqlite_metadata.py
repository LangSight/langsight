"""
Unit tests for SQLiteBackend metadata methods.

Covers: API keys, model pricing, projects, members, users,
        invite tokens, SLOs, alert config, and audit logs.
These tests use a real in-memory-ish SQLite file via tmp_path —
no mocking, no external services.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from langsight.models import (
    AgentSLO,
    ApiKeyRecord,
    ApiKeyRole,
    InviteToken,
    ModelPricing,
    Project,
    ProjectMember,
    ProjectRole,
    SLOMetric,
    User,
    UserRole,
)
from langsight.storage.sqlite import SQLiteBackend


@pytest.fixture
async def db(tmp_path: Path) -> SQLiteBackend:
    backend = await SQLiteBackend.open(tmp_path / "test.db")
    yield backend
    await backend.close()


def _now() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# API Keys
# ---------------------------------------------------------------------------

class TestApiKeys:
    async def test_create_and_list(self, db: SQLiteBackend) -> None:
        record = ApiKeyRecord(
            id="key-1", name="test-key", key_prefix="abcd1234",
            key_hash="sha256hash", role=ApiKeyRole.ADMIN, created_at=_now(),
        )
        await db.create_api_key(record)
        keys = await db.list_api_keys()
        assert len(keys) == 1
        assert keys[0].id == "key-1"
        assert keys[0].name == "test-key"

    async def test_get_by_hash_returns_record(self, db: SQLiteBackend) -> None:
        record = ApiKeyRecord(
            id="key-2", name="k2", key_prefix="prefix12",
            key_hash="uniquehash", role=ApiKeyRole.VIEWER, created_at=_now(),
        )
        await db.create_api_key(record)
        found = await db.get_api_key_by_hash("uniquehash")
        assert found is not None
        assert found.id == "key-2"

    async def test_get_by_hash_returns_none_for_missing(self, db: SQLiteBackend) -> None:
        result = await db.get_api_key_by_hash("nonexistent")
        assert result is None

    async def test_revoke_sets_revoked_at(self, db: SQLiteBackend) -> None:
        record = ApiKeyRecord(
            id="key-3", name="k3", key_prefix="pre3xxxx",
            key_hash="hash3", role=ApiKeyRole.ADMIN, created_at=_now(),
        )
        await db.create_api_key(record)
        found = await db.revoke_api_key("key-3")
        assert found is True
        # Revoked keys should not be returned by get_api_key_by_hash
        result = await db.get_api_key_by_hash("hash3")
        assert result is None

    async def test_revoke_returns_false_for_nonexistent(self, db: SQLiteBackend) -> None:
        found = await db.revoke_api_key("no-such-key")
        assert found is False

    async def test_touch_api_key(self, db: SQLiteBackend) -> None:
        record = ApiKeyRecord(
            id="key-4", name="k4", key_prefix="pre4xxxx",
            key_hash="hash4", role=ApiKeyRole.ADMIN, created_at=_now(),
        )
        await db.create_api_key(record)
        # Should not raise
        await db.touch_api_key("key-4")


# ---------------------------------------------------------------------------
# Model Pricing
# ---------------------------------------------------------------------------

class TestModelPricing:
    async def test_list_empty(self, db: SQLiteBackend) -> None:
        entries = await db.list_model_pricing()
        assert entries == []

    async def test_create_and_list(self, db: SQLiteBackend) -> None:
        entry = ModelPricing(
            id="mp-1", provider="anthropic", model_id="claude-3",
            display_name="Claude 3", input_per_1m_usd=3.0, output_per_1m_usd=15.0,
            cache_read_per_1m_usd=0.3, effective_from=_now(),
        )
        await db.create_model_pricing(entry)
        entries = await db.list_model_pricing()
        assert len(entries) == 1
        assert entries[0].model_id == "claude-3"

    async def test_get_active_returns_latest(self, db: SQLiteBackend) -> None:
        entry = ModelPricing(
            id="mp-2", provider="openai", model_id="gpt-4",
            display_name="GPT-4", input_per_1m_usd=5.0, output_per_1m_usd=15.0,
            cache_read_per_1m_usd=0.0, effective_from=_now(),
        )
        await db.create_model_pricing(entry)
        found = await db.get_active_model_pricing("gpt-4")
        assert found is not None
        assert found.model_id == "gpt-4"

    async def test_get_active_returns_none_for_unknown_model(self, db: SQLiteBackend) -> None:
        result = await db.get_active_model_pricing("unknown-model")
        assert result is None

    async def test_deactivate_sets_effective_to(self, db: SQLiteBackend) -> None:
        entry = ModelPricing(
            id="mp-3", provider="google", model_id="gemini",
            display_name="Gemini", input_per_1m_usd=1.0, output_per_1m_usd=2.0,
            cache_read_per_1m_usd=0.0, effective_from=_now(),
        )
        await db.create_model_pricing(entry)
        found = await db.deactivate_model_pricing("mp-3")
        assert found is True
        # Deactivated entry should no longer be returned as active
        active = await db.get_active_model_pricing("gemini")
        assert active is None


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

class TestProjects:
    async def test_create_and_get(self, db: SQLiteBackend) -> None:
        p = Project(id="proj-1", name="Alpha", slug="alpha",
                    created_by="user-1", created_at=_now())
        await db.create_project(p)
        found = await db.get_project("proj-1")
        assert found is not None
        assert found.name == "Alpha"

    async def test_get_returns_none_for_missing(self, db: SQLiteBackend) -> None:
        assert await db.get_project("missing") is None

    async def test_get_by_slug(self, db: SQLiteBackend) -> None:
        p = Project(id="proj-2", name="Beta", slug="beta",
                    created_by="user-1", created_at=_now())
        await db.create_project(p)
        found = await db.get_project_by_slug("beta")
        assert found is not None
        assert found.id == "proj-2"

    async def test_list_projects(self, db: SQLiteBackend) -> None:
        p1 = Project(id="p1", name="P1", slug="p1", created_by="u", created_at=_now())
        p2 = Project(id="p2", name="P2", slug="p2", created_by="u", created_at=_now())
        await db.create_project(p1)
        await db.create_project(p2)
        projects = await db.list_projects()
        assert len(projects) == 2

    async def test_update_project(self, db: SQLiteBackend) -> None:
        p = Project(id="proj-upd", name="Old", slug="old",
                    created_by="u", created_at=_now())
        await db.create_project(p)
        found = await db.update_project("proj-upd", "New Name", "new-slug")
        assert found is True
        updated = await db.get_project("proj-upd")
        assert updated is not None
        assert updated.name == "New Name"

    async def test_delete_project(self, db: SQLiteBackend) -> None:
        p = Project(id="proj-del", name="Del", slug="del",
                    created_by="u", created_at=_now())
        await db.create_project(p)
        found = await db.delete_project("proj-del")
        assert found is True
        assert await db.get_project("proj-del") is None

    async def test_delete_returns_false_for_missing(self, db: SQLiteBackend) -> None:
        assert await db.delete_project("no-such") is False


# ---------------------------------------------------------------------------
# Project Members
# ---------------------------------------------------------------------------

class TestProjectMembers:
    @pytest.fixture
    async def project(self, db: SQLiteBackend) -> Project:
        p = Project(id="pm-proj", name="Proj", slug="pm-proj",
                    created_by="owner", created_at=_now())
        await db.create_project(p)
        return p

    async def test_add_and_get_member(self, db: SQLiteBackend, project: Project) -> None:
        m = ProjectMember(project_id="pm-proj", user_id="user-a",
                          role=ProjectRole.MEMBER, added_by="owner", added_at=_now())
        await db.add_member(m)
        found = await db.get_member("pm-proj", "user-a")
        assert found is not None
        assert found.role == ProjectRole.MEMBER

    async def test_get_member_returns_none_for_missing(self, db: SQLiteBackend, project: Project) -> None:
        assert await db.get_member("pm-proj", "ghost") is None

    async def test_list_members(self, db: SQLiteBackend, project: Project) -> None:
        for uid in ["u1", "u2", "u3"]:
            await db.add_member(ProjectMember(
                project_id="pm-proj", user_id=uid,
                role=ProjectRole.VIEWER, added_by="owner", added_at=_now(),
            ))
        members = await db.list_members("pm-proj")
        assert len(members) == 3

    async def test_update_member_role(self, db: SQLiteBackend, project: Project) -> None:
        m = ProjectMember(project_id="pm-proj", user_id="user-b",
                          role=ProjectRole.VIEWER, added_by="owner", added_at=_now())
        await db.add_member(m)
        found = await db.update_member_role("pm-proj", "user-b", "owner")
        assert found is True
        updated = await db.get_member("pm-proj", "user-b")
        assert updated is not None
        assert updated.role == ProjectRole.OWNER

    async def test_remove_member(self, db: SQLiteBackend, project: Project) -> None:
        m = ProjectMember(project_id="pm-proj", user_id="user-c",
                          role=ProjectRole.MEMBER, added_by="owner", added_at=_now())
        await db.add_member(m)
        found = await db.remove_member("pm-proj", "user-c")
        assert found is True
        assert await db.get_member("pm-proj", "user-c") is None


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

class TestUsers:
    def _user(self, uid: str = "user-1", email: str = "test@example.com") -> User:
        return User(
            id=uid, email=email, password_hash="hashed",
            role=UserRole.VIEWER, active=True, invited_by=None, created_at=_now(),
        )

    async def test_create_and_get_by_email(self, db: SQLiteBackend) -> None:
        await db.create_user(self._user())
        found = await db.get_user_by_email("test@example.com")
        assert found is not None
        assert found.id == "user-1"

    async def test_get_by_email_returns_none_for_missing(self, db: SQLiteBackend) -> None:
        assert await db.get_user_by_email("nobody@example.com") is None

    async def test_get_by_id(self, db: SQLiteBackend) -> None:
        await db.create_user(self._user())
        found = await db.get_user_by_id("user-1")
        assert found is not None
        assert found.email == "test@example.com"

    async def test_list_users(self, db: SQLiteBackend) -> None:
        await db.create_user(self._user("u1", "a@a.com"))
        await db.create_user(self._user("u2", "b@b.com"))
        users = await db.list_users()
        assert len(users) == 2

    async def test_update_user_role(self, db: SQLiteBackend) -> None:
        await db.create_user(self._user())
        found = await db.update_user_role("user-1", "admin")
        assert found is True
        updated = await db.get_user_by_id("user-1")
        assert updated is not None
        assert updated.role == UserRole.ADMIN

    async def test_deactivate_user(self, db: SQLiteBackend) -> None:
        await db.create_user(self._user())
        found = await db.deactivate_user("user-1")
        assert found is True
        # Deactivated users should not appear in get_user_by_email
        assert await db.get_user_by_email("test@example.com") is None

    async def test_count_users(self, db: SQLiteBackend) -> None:
        assert await db.count_users() == 0
        await db.create_user(self._user())
        assert await db.count_users() == 1

    async def test_touch_user_login(self, db: SQLiteBackend) -> None:
        await db.create_user(self._user())
        # Should not raise
        await db.touch_user_login("user-1")


# ---------------------------------------------------------------------------
# Invite Tokens
# ---------------------------------------------------------------------------

class TestInviteTokens:
    def _invite(self, token: str = "tok123") -> InviteToken:
        return InviteToken(
            token=token, email="invite@example.com", role=UserRole.VIEWER,
            invited_by="admin-1", created_at=_now(),
            expires_at=_now() + timedelta(hours=72),
        )

    async def test_create_and_get(self, db: SQLiteBackend) -> None:
        await db.create_invite(self._invite())
        found = await db.get_invite("tok123")
        assert found is not None
        assert found.email == "invite@example.com"

    async def test_get_returns_none_for_missing(self, db: SQLiteBackend) -> None:
        assert await db.get_invite("no-such-token") is None

    async def test_mark_invite_used(self, db: SQLiteBackend) -> None:
        await db.create_invite(self._invite())
        await db.mark_invite_used("tok123")
        found = await db.get_invite("tok123")
        assert found is not None
        assert found.is_used is True

    async def test_unused_invite_not_used(self, db: SQLiteBackend) -> None:
        await db.create_invite(self._invite("fresh-tok"))
        found = await db.get_invite("fresh-tok")
        assert found is not None
        assert found.is_used is False

    async def test_expired_invite_detected(self, db: SQLiteBackend) -> None:
        expired = InviteToken(
            token="exp-tok", email="e@e.com", role=UserRole.VIEWER,
            invited_by="admin", created_at=_now() - timedelta(hours=100),
            expires_at=_now() - timedelta(hours=1),  # in the past
        )
        await db.create_invite(expired)
        found = await db.get_invite("exp-tok")
        assert found is not None
        assert found.is_expired is True


# ---------------------------------------------------------------------------
# SLOs
# ---------------------------------------------------------------------------

class TestSLOs:
    def _slo(self, slo_id: str = "slo-1", agent: str = "my-agent") -> AgentSLO:
        return AgentSLO(
            id=slo_id, agent_name=agent, metric=SLOMetric.SUCCESS_RATE,
            target=95.0, window_hours=24, created_at=_now(),
        )

    async def test_create_and_list(self, db: SQLiteBackend) -> None:
        await db.create_slo(self._slo())
        slos = await db.list_slos()
        assert len(slos) == 1
        assert slos[0].agent_name == "my-agent"

    async def test_get_slo(self, db: SQLiteBackend) -> None:
        await db.create_slo(self._slo())
        found = await db.get_slo("slo-1")
        assert found is not None
        assert found.target == 95.0

    async def test_get_slo_returns_none_for_missing(self, db: SQLiteBackend) -> None:
        assert await db.get_slo("no-such-slo") is None

    async def test_delete_slo(self, db: SQLiteBackend) -> None:
        await db.create_slo(self._slo())
        found = await db.delete_slo("slo-1")
        assert found is True
        assert await db.get_slo("slo-1") is None

    async def test_delete_returns_false_for_missing(self, db: SQLiteBackend) -> None:
        assert await db.delete_slo("not-there") is False


# ---------------------------------------------------------------------------
# Alert Config
# ---------------------------------------------------------------------------

class TestAlertConfig:
    async def test_get_returns_none_when_never_saved(self, db: SQLiteBackend) -> None:
        result = await db.get_alert_config()
        assert result is None

    async def test_save_and_get(self, db: SQLiteBackend) -> None:
        await db.save_alert_config(
            slack_webhook="https://hooks.slack.com/test",
            alert_types={"mcp_down": True, "agent_failure": False},
        )
        cfg = await db.get_alert_config()
        assert cfg is not None
        assert cfg["slack_webhook"] == "https://hooks.slack.com/test"
        assert cfg["alert_types"]["mcp_down"] is True
        assert cfg["alert_types"]["agent_failure"] is False

    async def test_upsert_replaces_existing(self, db: SQLiteBackend) -> None:
        await db.save_alert_config("https://old.com", {"mcp_down": True})
        await db.save_alert_config("https://new.com", {"mcp_down": False})
        cfg = await db.get_alert_config()
        assert cfg is not None
        assert cfg["slack_webhook"] == "https://new.com"
        assert cfg["alert_types"]["mcp_down"] is False

    async def test_save_with_null_webhook(self, db: SQLiteBackend) -> None:
        await db.save_alert_config(None, {"mcp_down": True})
        cfg = await db.get_alert_config()
        assert cfg is not None
        assert cfg["slack_webhook"] is None


# ---------------------------------------------------------------------------
# Audit Logs
# ---------------------------------------------------------------------------

class TestAuditLogs:
    async def test_count_zero_when_empty(self, db: SQLiteBackend) -> None:
        assert await db.count_audit_logs() == 0

    async def test_append_and_list(self, db: SQLiteBackend) -> None:
        await db.append_audit_log("user.login", "user-1", "127.0.0.1", {"role": "admin"})
        logs = await db.list_audit_logs()
        assert len(logs) == 1
        assert logs[0]["event"] == "user.login"
        assert logs[0]["user_id"] == "user-1"

    async def test_list_most_recent_first(self, db: SQLiteBackend) -> None:
        for ev in ["first", "second", "third"]:
            await db.append_audit_log(ev, "u", "127.0.0.1", {})
        logs = await db.list_audit_logs()
        assert logs[0]["event"] == "third"
        assert logs[-1]["event"] == "first"

    async def test_count_reflects_entries(self, db: SQLiteBackend) -> None:
        for i in range(5):
            await db.append_audit_log(f"evt_{i}", "u", "127.0.0.1", {})
        assert await db.count_audit_logs() == 5

    async def test_limit_respected(self, db: SQLiteBackend) -> None:
        for i in range(10):
            await db.append_audit_log(f"evt_{i}", "u", "127.0.0.1", {})
        logs = await db.list_audit_logs(limit=3)
        assert len(logs) == 3

    async def test_offset_respected(self, db: SQLiteBackend) -> None:
        for i in range(5):
            await db.append_audit_log(f"evt_{i}", "u", "127.0.0.1", {})
        logs = await db.list_audit_logs(limit=10, offset=3)
        assert len(logs) == 2  # 5 total - 3 offset = 2 remaining

    async def test_details_stored_and_retrieved(self, db: SQLiteBackend) -> None:
        await db.append_audit_log("config.changed", "u", "1.2.3.4", {"key": "val", "n": 42})
        logs = await db.list_audit_logs()
        assert logs[0]["details"] == {"key": "val", "n": 42}

    async def test_list_projects_for_user(self, db: SQLiteBackend) -> None:
        """list_projects_for_user returns only projects where user is a member."""
        p1 = Project(id="lpu-p1", name="P1", slug="lpu-p1", created_by="u", created_at=_now())
        p2 = Project(id="lpu-p2", name="P2", slug="lpu-p2", created_by="u", created_at=_now())
        await db.create_project(p1)
        await db.create_project(p2)
        await db.add_member(ProjectMember(
            project_id="lpu-p1", user_id="specific-user",
            role=ProjectRole.MEMBER, added_by="u", added_at=_now(),
        ))
        user_projects = await db.list_projects_for_user("specific-user")
        assert len(user_projects) == 1
        assert user_projects[0].id == "lpu-p1"
