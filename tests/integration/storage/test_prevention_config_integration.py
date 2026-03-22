"""
Integration tests for prevention_config storage — PostgresBackend.

Requires a running Postgres instance (docker compose up -d).
All tests use a real DB connection and clean up after themselves.

Run:
    docker compose up -d
    uv run pytest tests/integration/storage/test_prevention_config_integration.py -v
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from langsight.models import PreventionConfig, Project, ProjectMember, ProjectRole, User, UserRole

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def pg(postgres_dsn: str, require_postgres: None):
    """Real PostgresBackend against the test Postgres instance."""
    from langsight.storage.postgres import PostgresBackend
    backend = await PostgresBackend.open(postgres_dsn)
    yield backend
    await backend.close()


@pytest.fixture
async def project_id(pg) -> str:
    """Create a throwaway project and return its ID. Deleted on teardown."""
    pid = uuid.uuid4().hex
    now = datetime.now(UTC)
    proj = Project(id=pid, name=f"test-{pid[:8]}", slug=f"test-{pid[:8]}", created_by="test", created_at=now)
    await pg.create_project(proj)
    yield pid
    # Teardown: delete all prevention configs + project
    try:
        configs = await pg.list_prevention_configs(pid)
        for c in configs:
            await pg.delete_prevention_config(c.agent_name, pid)
        await pg.delete_project(pid)
    except Exception:  # noqa: BLE001
        pass


def _config(project_id: str, agent_name: str = "test-agent", **kwargs) -> PreventionConfig:
    """Build a PreventionConfig with sane defaults."""
    defaults = dict(
        loop_enabled=True, loop_threshold=3, loop_action="terminate",
        max_steps=None, max_cost_usd=None, max_wall_time_s=None,
        budget_soft_alert=0.80, cb_enabled=True, cb_failure_threshold=5,
        cb_cooldown_seconds=60.0, cb_half_open_max_calls=2,
    )
    defaults.update(kwargs)
    return PreventionConfig(
        id=uuid.uuid4().hex,
        project_id=project_id,
        agent_name=agent_name,
        **defaults,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# CRUD round-trips
# ---------------------------------------------------------------------------


class TestUpsertAndGet:
    async def test_upsert_creates_new_config(self, pg, project_id: str) -> None:
        config = _config(project_id, "orchestrator", max_steps=25, max_cost_usd=1.00)
        saved = await pg.upsert_prevention_config(config)
        assert saved.agent_name == "orchestrator"
        assert saved.max_steps == 25
        assert saved.max_cost_usd == pytest.approx(1.00)
        assert saved.project_id == project_id

    async def test_upsert_updates_existing_config(self, pg, project_id: str) -> None:
        config = _config(project_id, "orchestrator", max_steps=25)
        await pg.upsert_prevention_config(config)

        # Update with same agent_name — should overwrite
        updated = _config(project_id, "orchestrator", max_steps=50, loop_threshold=5)
        saved = await pg.upsert_prevention_config(updated)
        assert saved.max_steps == 50
        assert saved.loop_threshold == 5

    async def test_upsert_preserves_project_id(self, pg, project_id: str) -> None:
        config = _config(project_id, "billing-agent")
        saved = await pg.upsert_prevention_config(config)
        assert saved.project_id == project_id

    async def test_get_returns_none_when_not_set(self, pg, project_id: str) -> None:
        result = await pg.get_prevention_config("no-such-agent", project_id)
        assert result is None

    async def test_get_returns_config_when_set(self, pg, project_id: str) -> None:
        config = _config(project_id, "support-agent", max_steps=15)
        await pg.upsert_prevention_config(config)
        fetched = await pg.get_prevention_config("support-agent", project_id)
        assert fetched is not None
        assert fetched.max_steps == 15
        assert fetched.agent_name == "support-agent"

    async def test_all_nullable_fields_round_trip(self, pg, project_id: str) -> None:
        """None values for max_steps, max_cost_usd, max_wall_time_s survive the DB round-trip."""
        config = _config(project_id, "data-analyst",
                         max_steps=None, max_cost_usd=None, max_wall_time_s=None)
        saved = await pg.upsert_prevention_config(config)
        assert saved.max_steps is None
        assert saved.max_cost_usd is None
        assert saved.max_wall_time_s is None

    async def test_populated_fields_round_trip(self, pg, project_id: str) -> None:
        config = _config(project_id, "full-agent",
                         max_steps=10, max_cost_usd=0.50, max_wall_time_s=120.0,
                         loop_threshold=5, loop_action="warn", cb_failure_threshold=3,
                         cb_cooldown_seconds=30.0, cb_half_open_max_calls=1)
        saved = await pg.upsert_prevention_config(config)
        assert saved.max_steps == 10
        assert saved.max_cost_usd == pytest.approx(0.50)
        assert saved.max_wall_time_s == pytest.approx(120.0)
        assert saved.loop_threshold == 5
        assert saved.loop_action == "warn"
        assert saved.cb_failure_threshold == 3
        assert saved.cb_cooldown_seconds == pytest.approx(30.0)
        assert saved.cb_half_open_max_calls == 1

    async def test_boolean_fields_round_trip(self, pg, project_id: str) -> None:
        config = _config(project_id, "disabled-agent", loop_enabled=False, cb_enabled=False)
        saved = await pg.upsert_prevention_config(config)
        assert saved.loop_enabled is False
        assert saved.cb_enabled is False


class TestDelete:
    async def test_delete_returns_true_when_found(self, pg, project_id: str) -> None:
        config = _config(project_id, "to-delete")
        await pg.upsert_prevention_config(config)
        result = await pg.delete_prevention_config("to-delete", project_id)
        assert result is True

    async def test_delete_removes_config(self, pg, project_id: str) -> None:
        config = _config(project_id, "to-delete-2")
        await pg.upsert_prevention_config(config)
        await pg.delete_prevention_config("to-delete-2", project_id)
        fetched = await pg.get_prevention_config("to-delete-2", project_id)
        assert fetched is None

    async def test_delete_returns_false_when_not_found(self, pg, project_id: str) -> None:
        result = await pg.delete_prevention_config("ghost-agent", project_id)
        assert result is False

    async def test_delete_is_project_scoped(self, pg, project_id: str) -> None:
        """Deleting from project A does not affect project B."""
        pid2 = uuid.uuid4().hex
        now = datetime.now(UTC)
        await pg.create_project(Project(
            id=pid2, name=f"proj-{pid2[:6]}", slug=f"proj-{pid2[:6]}",
            created_by="test", created_at=now,
        ))
        try:
            config_b = _config(pid2, "shared-agent")
            await pg.upsert_prevention_config(config_b)

            # Delete from project A (where the agent doesn't exist)
            result = await pg.delete_prevention_config("shared-agent", project_id)
            assert result is False  # not found in project A

            # Config in project B is untouched
            fetched = await pg.get_prevention_config("shared-agent", pid2)
            assert fetched is not None
        finally:
            await pg.delete_prevention_config("shared-agent", pid2)
            await pg.delete_project(pid2)


class TestList:
    async def test_list_returns_empty_for_new_project(self, pg, project_id: str) -> None:
        configs = await pg.list_prevention_configs(project_id)
        assert configs == []

    async def test_list_returns_all_configs(self, pg, project_id: str) -> None:
        for name in ["agent-a", "agent-b", "*"]:
            await pg.upsert_prevention_config(_config(project_id, name))
        configs = await pg.list_prevention_configs(project_id)
        names = {c.agent_name for c in configs}
        assert names == {"agent-a", "agent-b", "*"}

    async def test_list_is_project_scoped(self, pg, project_id: str) -> None:
        """Configs from other projects are not returned."""
        pid2 = uuid.uuid4().hex
        now = datetime.now(UTC)
        await pg.create_project(Project(
            id=pid2, name=f"other-{pid2[:6]}", slug=f"other-{pid2[:6]}",
            created_by="test", created_at=now,
        ))
        try:
            await pg.upsert_prevention_config(_config(project_id, "mine"))
            await pg.upsert_prevention_config(_config(pid2, "theirs"))
            configs = await pg.list_prevention_configs(project_id)
            names = {c.agent_name for c in configs}
            assert "mine" in names
            assert "theirs" not in names
        finally:
            await pg.delete_prevention_config("theirs", pid2)
            await pg.delete_project(pid2)

    async def test_list_ordered_by_agent_name(self, pg, project_id: str) -> None:
        for name in ["zzz", "aaa", "mmm"]:
            await pg.upsert_prevention_config(_config(project_id, name))
        configs = await pg.list_prevention_configs(project_id)
        names = [c.agent_name for c in configs]
        assert names == sorted(names)


# ---------------------------------------------------------------------------
# Effective config fallback
# ---------------------------------------------------------------------------


class TestEffectiveConfig:
    async def test_returns_agent_specific_when_set(self, pg, project_id: str) -> None:
        """Agent-specific config takes priority over project default."""
        await pg.upsert_prevention_config(_config(project_id, "*", max_steps=100))
        await pg.upsert_prevention_config(_config(project_id, "my-agent", max_steps=10))
        eff = await pg.get_effective_prevention_config("my-agent", project_id)
        assert eff is not None
        assert eff.max_steps == 10   # agent-specific, not 100

    async def test_falls_back_to_project_default(self, pg, project_id: str) -> None:
        """When no agent-specific config, returns the '*' project default."""
        await pg.upsert_prevention_config(_config(project_id, "*", max_steps=50))
        eff = await pg.get_effective_prevention_config("unset-agent", project_id)
        assert eff is not None
        assert eff.max_steps == 50
        assert eff.agent_name == "*"

    async def test_returns_none_when_neither_set(self, pg, project_id: str) -> None:
        """No agent config and no project default → None (SDK uses constructor defaults)."""
        eff = await pg.get_effective_prevention_config("nobody", project_id)
        assert eff is None

    async def test_after_delete_falls_back_to_default(self, pg, project_id: str) -> None:
        """Deleting agent-specific config reveals the project default."""
        await pg.upsert_prevention_config(_config(project_id, "*", max_steps=99))
        await pg.upsert_prevention_config(_config(project_id, "my-agent", max_steps=5))

        # Before delete: agent-specific wins
        eff = await pg.get_effective_prevention_config("my-agent", project_id)
        assert eff.max_steps == 5

        await pg.delete_prevention_config("my-agent", project_id)

        # After delete: falls back to project default
        eff = await pg.get_effective_prevention_config("my-agent", project_id)
        assert eff is not None
        assert eff.max_steps == 99

    async def test_effective_config_is_project_scoped(self, pg, project_id: str) -> None:
        """Project default from project B does not bleed into project A."""
        pid2 = uuid.uuid4().hex
        now = datetime.now(UTC)
        await pg.create_project(Project(
            id=pid2, name=f"scope-{pid2[:6]}", slug=f"scope-{pid2[:6]}",
            created_by="test", created_at=now,
        ))
        try:
            # Only project B has a default
            await pg.upsert_prevention_config(_config(pid2, "*", max_steps=77))
            eff = await pg.get_effective_prevention_config("any-agent", project_id)
            assert eff is None  # project A has nothing
        finally:
            await pg.delete_prevention_config("*", pid2)
            await pg.delete_project(pid2)


# ---------------------------------------------------------------------------
# Demo seed idempotency
# ---------------------------------------------------------------------------


class TestDemoSeedIdempotency:
    async def test_upsert_twice_does_not_duplicate(self, pg, project_id: str) -> None:
        """Running the seed twice doesn't create duplicate rows."""
        config = _config(project_id, "orchestrator", max_steps=25)
        await pg.upsert_prevention_config(config)
        await pg.upsert_prevention_config(config)  # second run
        configs = await pg.list_prevention_configs(project_id)
        orchestrator_rows = [c for c in configs if c.agent_name == "orchestrator"]
        assert len(orchestrator_rows) == 1

    async def test_second_upsert_updates_values(self, pg, project_id: str) -> None:
        """Second upsert with different values updates, doesn't duplicate."""
        config_v1 = _config(project_id, "support-agent", max_steps=15)
        config_v2 = _config(project_id, "support-agent", max_steps=20)
        await pg.upsert_prevention_config(config_v1)
        await pg.upsert_prevention_config(config_v2)
        configs = await pg.list_prevention_configs(project_id)
        rows = [c for c in configs if c.agent_name == "support-agent"]
        assert len(rows) == 1
        assert rows[0].max_steps == 20  # updated value
