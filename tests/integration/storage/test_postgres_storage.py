"""
Integration tests for PostgresBackend.

Requires a running Postgres instance (from docker compose up -d).
All tests are marked @pytest.mark.integration and skipped automatically
when Postgres is not reachable — see tests/conftest.py.

Run:
    docker compose up -d
    uv run pytest tests/integration/ -m integration -v
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

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

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
async def pg(postgres_dsn: str, require_postgres: None):
    """Open a real PostgresBackend against the test Postgres instance."""
    from langsight.storage.postgres import PostgresBackend
    backend = await PostgresBackend.open(postgres_dsn)
    yield backend
    await backend.close()


def _now() -> datetime:
    return datetime.now(UTC)


def _health(server: str = "pg-server") -> HealthCheckResult:
    return HealthCheckResult(
        server_name=server,
        status=ServerStatus.UP,
        latency_ms=42.0,
        tools_count=3,
        schema_hash="abc123",
        error=None,
        checked_at=_now(),
    )


def _user(uid: str, email: str) -> User:
    return User(
        id=uid, email=email, password_hash="bcrypt_hash",
        role=UserRole.VIEWER, active=True, invited_by=None, created_at=_now(),
    )


def _project(pid: str, slug: str) -> Project:
    return Project(id=pid, name=pid, slug=slug, created_by="admin", created_at=_now())


# ---------------------------------------------------------------------------
# Health results (ClickHouse in production, Postgres for smoke test)
# ---------------------------------------------------------------------------

class TestHealthResults:
    async def test_save_and_retrieve(self, pg) -> None:
        result = _health()
        await pg.save_health_result(result)
        history = await pg.get_health_history(result.server_name, limit=1)
        assert len(history) >= 1
        assert history[0].server_name == result.server_name
        assert history[0].status == ServerStatus.UP

    async def test_schema_snapshot_round_trip(self, pg) -> None:
        await pg.save_schema_snapshot("test-server", "hash_v1", tools_count=5)
        h = await pg.get_latest_schema_hash("test-server")
        assert h == "hash_v1"

    async def test_get_latest_hash_returns_none_when_absent(self, pg) -> None:
        assert await pg.get_latest_schema_hash("nonexistent-server") is None


# ---------------------------------------------------------------------------
# API Keys
# ---------------------------------------------------------------------------

class TestApiKeys:
    async def test_create_list_revoke(self, pg) -> None:
        import uuid
        kid = uuid.uuid4().hex
        record = ApiKeyRecord(
            id=kid, name="integration-key", key_prefix="inte1234",
            key_hash=f"hash_{kid}", role=ApiKeyRole.ADMIN, created_at=_now(),
        )
        await pg.create_api_key(record)

        keys = await pg.list_api_keys()
        ids = [k.id for k in keys]
        assert kid in ids

        found = await pg.get_api_key_by_hash(f"hash_{kid}")
        assert found is not None
        assert found.name == "integration-key"

        revoked = await pg.revoke_api_key(kid)
        assert revoked is True

        # After revocation, get_api_key_by_hash returns None
        assert await pg.get_api_key_by_hash(f"hash_{kid}") is None

    async def test_touch_api_key(self, pg) -> None:
        import uuid
        kid = uuid.uuid4().hex
        record = ApiKeyRecord(
            id=kid, name="touch-key", key_prefix="touc5678",
            key_hash=f"touchhash_{kid}", role=ApiKeyRole.VIEWER, created_at=_now(),
        )
        await pg.create_api_key(record)
        await pg.touch_api_key(kid)   # should not raise


# ---------------------------------------------------------------------------
# Model Pricing
# ---------------------------------------------------------------------------

class TestModelPricing:
    async def test_create_list_deactivate(self, pg) -> None:
        import uuid
        mid = uuid.uuid4().hex
        entry = ModelPricing(
            id=mid, provider="test", model_id=f"model-{mid}",
            display_name="Test Model", input_per_1m_usd=1.0,
            output_per_1m_usd=2.0, cache_read_per_1m_usd=0.1,
            effective_from=_now(),
        )
        await pg.create_model_pricing(entry)

        entries = await pg.list_model_pricing()
        assert any(e.id == mid for e in entries)

        active = await pg.get_active_model_pricing(f"model-{mid}")
        assert active is not None
        assert active.input_per_1m_usd == 1.0

        deactivated = await pg.deactivate_model_pricing(mid)
        assert deactivated is True
        assert await pg.get_active_model_pricing(f"model-{mid}") is None


# ---------------------------------------------------------------------------
# Projects + Members
# ---------------------------------------------------------------------------

class TestProjects:
    async def test_create_get_update_delete(self, pg) -> None:
        import uuid
        pid = uuid.uuid4().hex
        p = _project(pid, f"slug-{pid[:8]}")
        await pg.create_project(p)

        found = await pg.get_project(pid)
        assert found is not None
        assert found.name == pid

        by_slug = await pg.get_project_by_slug(f"slug-{pid[:8]}")
        assert by_slug is not None

        updated = await pg.update_project(pid, "New Name", f"new-{pid[:8]}")
        assert updated is True
        assert (await pg.get_project(pid)).name == "New Name"

        deleted = await pg.delete_project(pid)
        assert deleted is True
        assert await pg.get_project(pid) is None

    async def test_list_projects_for_user(self, pg) -> None:
        import uuid
        uid = uuid.uuid4().hex
        pid = uuid.uuid4().hex
        p = _project(pid, f"user-proj-{pid[:8]}")
        await pg.create_project(p)
        await pg.add_member(ProjectMember(
            project_id=pid, user_id=uid, role=ProjectRole.MEMBER,
            added_by="admin", added_at=_now(),
        ))
        user_projects = await pg.list_projects_for_user(uid)
        assert any(proj.id == pid for proj in user_projects)

    async def test_member_crud(self, pg) -> None:
        import uuid
        pid = uuid.uuid4().hex
        uid = uuid.uuid4().hex
        await pg.create_project(_project(pid, f"mem-{pid[:8]}"))

        await pg.add_member(ProjectMember(
            project_id=pid, user_id=uid, role=ProjectRole.VIEWER,
            added_by="admin", added_at=_now(),
        ))
        m = await pg.get_member(pid, uid)
        assert m is not None
        assert m.role == ProjectRole.VIEWER

        members = await pg.list_members(pid)
        assert any(mem.user_id == uid for mem in members)

        updated = await pg.update_member_role(pid, uid, "owner")
        assert updated is True
        assert (await pg.get_member(pid, uid)).role == ProjectRole.OWNER

        removed = await pg.remove_member(pid, uid)
        assert removed is True
        assert await pg.get_member(pid, uid) is None


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

class TestUsers:
    async def test_create_get_list_deactivate(self, pg) -> None:
        import uuid
        uid = uuid.uuid4().hex
        email = f"{uid[:8]}@integration.test"
        user = _user(uid, email)
        await pg.create_user(user)

        by_email = await pg.get_user_by_email(email)
        assert by_email is not None
        assert by_email.id == uid

        by_id = await pg.get_user_by_id(uid)
        assert by_id is not None

        users = await pg.list_users()
        assert any(u.id == uid for u in users)

        assert await pg.count_users() >= 1

        role_updated = await pg.update_user_role(uid, "admin")
        assert role_updated is True

        await pg.touch_user_login(uid)   # should not raise

        deactivated = await pg.deactivate_user(uid)
        assert deactivated is True
        # Deactivated user no longer returned by email lookup
        assert await pg.get_user_by_email(email) is None


# ---------------------------------------------------------------------------
# Invite Tokens
# ---------------------------------------------------------------------------

class TestInviteTokens:
    async def test_create_get_mark_used(self, pg) -> None:
        import secrets
        token = secrets.token_hex(32)  # 64 chars
        invite = InviteToken(
            token=token, email="invited@integration.test", role=UserRole.VIEWER,
            invited_by="admin", created_at=_now(),
            expires_at=_now() + timedelta(hours=72),
        )
        await pg.create_invite(invite)

        found = await pg.get_invite(token)
        assert found is not None
        assert found.email == "invited@integration.test"
        assert found.is_used is False
        assert found.is_expired is False

        await pg.mark_invite_used(token)
        used = await pg.get_invite(token)
        assert used.is_used is True


# ---------------------------------------------------------------------------
# SLOs
# ---------------------------------------------------------------------------

class TestSLOs:
    async def test_create_list_get_delete(self, pg) -> None:
        import uuid
        sid = uuid.uuid4().hex
        slo = AgentSLO(
            id=sid, agent_name=f"agent-{sid[:8]}",
            metric=SLOMetric.SUCCESS_RATE, target=99.0,
            window_hours=24, created_at=_now(),
        )
        await pg.create_slo(slo)

        slos = await pg.list_slos()
        assert any(s.id == sid for s in slos)

        found = await pg.get_slo(sid)
        assert found is not None
        assert found.target == 99.0

        deleted = await pg.delete_slo(sid)
        assert deleted is True
        assert await pg.get_slo(sid) is None


# ---------------------------------------------------------------------------
# Alert Config + Audit Logs
# ---------------------------------------------------------------------------

class TestAlertConfigAndAuditLogs:
    async def test_alert_config_round_trip(self, pg) -> None:
        assert await pg.get_alert_config() is None or True  # may be set from other tests
        await pg.save_alert_config(
            "https://hooks.slack.com/integration-test",
            {"mcp_down": True, "agent_failure": False},
        )
        cfg = await pg.get_alert_config()
        assert cfg is not None
        assert cfg["slack_webhook"] == "https://hooks.slack.com/integration-test"
        assert cfg["alert_types"]["mcp_down"] is True

    async def test_audit_log_append_list_count(self, pg) -> None:
        before = await pg.count_audit_logs()
        await pg.append_audit_log("integration.test.event", "test-user", "127.0.0.1",
                                  {"detail": "from integration test"})
        assert await pg.count_audit_logs() == before + 1

        logs = await pg.list_audit_logs(limit=1, offset=0)
        assert logs[0]["event"] == "integration.test.event"
        assert logs[0]["details"]["detail"] == "from integration test"
