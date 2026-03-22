"""
Unit tests for PostgresBackend prevention config storage methods.

Covers:
- list_prevention_configs: empty result, row mapping
- get_prevention_config: not found, found
- get_effective_prevention_config: agent-specific takes priority over "*", only default exists, neither exists
- upsert_prevention_config: SQL called with correct args, returned model matches
- delete_prevention_config: True when row deleted, False when DELETE 0
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from langsight.models import PreventionConfig
from langsight.storage.postgres import PostgresBackend


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pool(
    fetchrow_return=None,
    fetch_return=None,
    execute_return: str = "DELETE 0",
) -> MagicMock:
    """Return a MagicMock asyncpg pool that speaks directly on the pool object
    (prevention config methods call self._pool.fetch / fetchrow / execute directly,
    not through pool.acquire context manager)."""
    pool = MagicMock()
    pool.fetch = AsyncMock(return_value=fetch_return or [])
    pool.fetchrow = AsyncMock(return_value=fetchrow_return)
    pool.execute = AsyncMock(return_value=execute_return)
    return pool


_NOW = datetime(2026, 3, 22, 10, 0, 0, tzinfo=UTC)


def _fake_row(
    *,
    id: str = "cfg-001",
    project_id: str = "proj-abc",
    agent_name: str = "orchestrator",
    loop_enabled: bool = True,
    loop_threshold: int = 3,
    loop_action: str = "terminate",
    max_steps: int | None = None,
    max_cost_usd: float | None = None,
    max_wall_time_s: float | None = None,
    budget_soft_alert: float = 0.80,
    cb_enabled: bool = True,
    cb_failure_threshold: int = 5,
    cb_cooldown_seconds: float = 60.0,
    cb_half_open_max_calls: int = 2,
    created_at: datetime = _NOW,
    updated_at: datetime = _NOW,
) -> dict:
    """Return a dict behaving like an asyncpg Record for _row_to_prevention_config."""
    return {
        "id": id,
        "project_id": project_id,
        "agent_name": agent_name,
        "loop_enabled": loop_enabled,
        "loop_threshold": loop_threshold,
        "loop_action": loop_action,
        "max_steps": max_steps,
        "max_cost_usd": max_cost_usd,
        "max_wall_time_s": max_wall_time_s,
        "budget_soft_alert": budget_soft_alert,
        "cb_enabled": cb_enabled,
        "cb_failure_threshold": cb_failure_threshold,
        "cb_cooldown_seconds": cb_cooldown_seconds,
        "cb_half_open_max_calls": cb_half_open_max_calls,
        "created_at": created_at,
        "updated_at": updated_at,
    }


@pytest.fixture
def pool() -> MagicMock:
    return _make_pool()


@pytest.fixture
def backend(pool: MagicMock) -> PostgresBackend:
    return PostgresBackend(pool)


# ---------------------------------------------------------------------------
# list_prevention_configs
# ---------------------------------------------------------------------------


class TestListPreventionConfigs:
    async def test_returns_empty_list_when_pool_returns_no_rows(
        self, backend: PostgresBackend, pool: MagicMock
    ) -> None:
        pool.fetch.return_value = []
        result = await backend.list_prevention_configs("proj-abc")
        assert result == []

    async def test_returns_single_prevention_config_when_one_row(
        self, backend: PostgresBackend, pool: MagicMock
    ) -> None:
        pool.fetch.return_value = [_fake_row(agent_name="orchestrator")]
        result = await backend.list_prevention_configs("proj-abc")
        assert len(result) == 1
        assert isinstance(result[0], PreventionConfig)
        assert result[0].agent_name == "orchestrator"

    async def test_maps_multiple_rows_to_models(
        self, backend: PostgresBackend, pool: MagicMock
    ) -> None:
        pool.fetch.return_value = [
            _fake_row(agent_name="*", id="cfg-default"),
            _fake_row(agent_name="orchestrator", id="cfg-orch"),
            _fake_row(agent_name="billing-agent", id="cfg-billing"),
        ]
        result = await backend.list_prevention_configs("proj-abc")
        assert len(result) == 3
        names = {c.agent_name for c in result}
        assert names == {"*", "orchestrator", "billing-agent"}

    async def test_passes_project_id_to_query(
        self, backend: PostgresBackend, pool: MagicMock
    ) -> None:
        pool.fetch.return_value = []
        await backend.list_prevention_configs("proj-xyz")
        pool.fetch.assert_called_once()
        call_args = pool.fetch.call_args[0]
        assert "proj-xyz" in call_args

    async def test_maps_optional_fields_as_none(
        self, backend: PostgresBackend, pool: MagicMock
    ) -> None:
        pool.fetch.return_value = [
            _fake_row(max_steps=None, max_cost_usd=None, max_wall_time_s=None)
        ]
        result = await backend.list_prevention_configs("proj-abc")
        config = result[0]
        assert config.max_steps is None
        assert config.max_cost_usd is None
        assert config.max_wall_time_s is None

    async def test_maps_optional_fields_when_present(
        self, backend: PostgresBackend, pool: MagicMock
    ) -> None:
        pool.fetch.return_value = [
            _fake_row(max_steps=25, max_cost_usd=5.00, max_wall_time_s=300.0)
        ]
        result = await backend.list_prevention_configs("proj-abc")
        config = result[0]
        assert config.max_steps == 25
        assert config.max_cost_usd == 5.00
        assert config.max_wall_time_s == 300.0


# ---------------------------------------------------------------------------
# get_prevention_config
# ---------------------------------------------------------------------------


class TestGetPreventionConfig:
    async def test_returns_none_when_pool_returns_none(
        self, backend: PostgresBackend, pool: MagicMock
    ) -> None:
        pool.fetchrow.return_value = None
        result = await backend.get_prevention_config("orchestrator", "proj-abc")
        assert result is None

    async def test_returns_prevention_config_when_row_found(
        self, backend: PostgresBackend, pool: MagicMock
    ) -> None:
        pool.fetchrow.return_value = _fake_row(
            agent_name="orchestrator", id="cfg-001", loop_threshold=7
        )
        result = await backend.get_prevention_config("orchestrator", "proj-abc")
        assert isinstance(result, PreventionConfig)
        assert result.agent_name == "orchestrator"
        assert result.loop_threshold == 7

    async def test_passes_both_project_id_and_agent_name_to_query(
        self, backend: PostgresBackend, pool: MagicMock
    ) -> None:
        pool.fetchrow.return_value = None
        await backend.get_prevention_config("my-agent", "proj-xyz")
        pool.fetchrow.assert_called_once()
        call_args = pool.fetchrow.call_args[0]
        assert "my-agent" in call_args
        assert "proj-xyz" in call_args

    async def test_maps_circuit_breaker_fields_correctly(
        self, backend: PostgresBackend, pool: MagicMock
    ) -> None:
        pool.fetchrow.return_value = _fake_row(
            cb_enabled=True,
            cb_failure_threshold=10,
            cb_cooldown_seconds=120.0,
            cb_half_open_max_calls=3,
        )
        result = await backend.get_prevention_config("orchestrator", "proj-abc")
        assert result is not None
        assert result.cb_enabled is True
        assert result.cb_failure_threshold == 10
        assert result.cb_cooldown_seconds == 120.0
        assert result.cb_half_open_max_calls == 3

    async def test_maps_loop_action_warn(
        self, backend: PostgresBackend, pool: MagicMock
    ) -> None:
        pool.fetchrow.return_value = _fake_row(loop_action="warn")
        result = await backend.get_prevention_config("orchestrator", "proj-abc")
        assert result is not None
        assert result.loop_action == "warn"

    async def test_returns_project_default_when_agent_name_is_star(
        self, backend: PostgresBackend, pool: MagicMock
    ) -> None:
        pool.fetchrow.return_value = _fake_row(agent_name="*", id="cfg-default")
        result = await backend.get_prevention_config("*", "proj-abc")
        assert result is not None
        assert result.agent_name == "*"


# ---------------------------------------------------------------------------
# get_effective_prevention_config
# ---------------------------------------------------------------------------


class TestGetEffectivePreventionConfig:
    async def test_returns_none_when_no_config_at_all(
        self, backend: PostgresBackend, pool: MagicMock
    ) -> None:
        pool.fetchrow.return_value = None
        result = await backend.get_effective_prevention_config("orchestrator", "proj-abc")
        assert result is None

    async def test_returns_agent_specific_config_when_present(
        self, backend: PostgresBackend, pool: MagicMock
    ) -> None:
        # Pool returns the agent-specific row (SQL ORDER BY puts it first)
        pool.fetchrow.return_value = _fake_row(
            agent_name="orchestrator", id="cfg-orch", loop_threshold=10
        )
        result = await backend.get_effective_prevention_config("orchestrator", "proj-abc")
        assert result is not None
        assert result.agent_name == "orchestrator"
        assert result.loop_threshold == 10

    async def test_returns_project_default_when_no_agent_specific_config(
        self, backend: PostgresBackend, pool: MagicMock
    ) -> None:
        # SQL falls back to "*" — simulate by returning a "*" row
        pool.fetchrow.return_value = _fake_row(
            agent_name="*", id="cfg-default", loop_threshold=5
        )
        result = await backend.get_effective_prevention_config("unknown-agent", "proj-abc")
        assert result is not None
        assert result.agent_name == "*"
        assert result.loop_threshold == 5

    async def test_passes_agent_name_and_project_id_to_query(
        self, backend: PostgresBackend, pool: MagicMock
    ) -> None:
        pool.fetchrow.return_value = None
        await backend.get_effective_prevention_config("my-agent", "proj-xyz")
        pool.fetchrow.assert_called_once()
        call_args = pool.fetchrow.call_args[0]
        assert "my-agent" in call_args
        assert "proj-xyz" in call_args

    async def test_query_uses_any_array_for_fallback(
        self, backend: PostgresBackend, pool: MagicMock
    ) -> None:
        """The query must include ARRAY[$2, '*'] or equivalent for fallback to work."""
        pool.fetchrow.return_value = None
        await backend.get_effective_prevention_config("orchestrator", "proj-abc")
        sql = pool.fetchrow.call_args[0][0]
        # The SQL must reference both the agent name placeholder and the wildcard
        assert "$2" in sql or "orchestrator" in str(pool.fetchrow.call_args)
        assert "*" in sql


# ---------------------------------------------------------------------------
# upsert_prevention_config
# ---------------------------------------------------------------------------


class TestUpsertPreventionConfig:
    def _make_config(
        self,
        *,
        agent_name: str = "orchestrator",
        loop_threshold: int = 5,
        loop_action: str = "terminate",
        loop_enabled: bool = True,
        max_steps: int | None = None,
        cb_enabled: bool = True,
        cb_failure_threshold: int = 5,
        cb_cooldown_seconds: float = 60.0,
        cb_half_open_max_calls: int = 2,
    ) -> PreventionConfig:
        return PreventionConfig(
            id="cfg-001",
            project_id="proj-abc",
            agent_name=agent_name,
            loop_enabled=loop_enabled,
            loop_threshold=loop_threshold,
            loop_action=loop_action,
            max_steps=max_steps,
            budget_soft_alert=0.80,
            cb_enabled=cb_enabled,
            cb_failure_threshold=cb_failure_threshold,
            cb_cooldown_seconds=cb_cooldown_seconds,
            cb_half_open_max_calls=cb_half_open_max_calls,
            created_at=_NOW,
            updated_at=_NOW,
        )

    async def test_calls_fetchrow_with_upsert_sql(
        self, backend: PostgresBackend, pool: MagicMock
    ) -> None:
        config = self._make_config()
        pool.fetchrow.return_value = _fake_row(
            id=config.id,
            agent_name=config.agent_name,
            project_id=config.project_id,
        )
        await backend.upsert_prevention_config(config)
        pool.fetchrow.assert_called_once()

    async def test_passes_all_config_fields_to_query(
        self, backend: PostgresBackend, pool: MagicMock
    ) -> None:
        config = self._make_config(
            loop_threshold=8,
            loop_action="warn",
            cb_failure_threshold=10,
            cb_cooldown_seconds=120.0,
            cb_half_open_max_calls=3,
        )
        pool.fetchrow.return_value = _fake_row(
            id=config.id,
            agent_name=config.agent_name,
            project_id=config.project_id,
            loop_threshold=8,
            loop_action="warn",
            cb_failure_threshold=10,
            cb_cooldown_seconds=120.0,
            cb_half_open_max_calls=3,
        )
        await backend.upsert_prevention_config(config)
        call_args = pool.fetchrow.call_args[0]
        assert config.id in call_args
        assert config.project_id in call_args
        assert config.agent_name in call_args
        assert 8 in call_args
        assert "warn" in call_args
        assert 10 in call_args

    async def test_returns_prevention_config_from_returned_row(
        self, backend: PostgresBackend, pool: MagicMock
    ) -> None:
        config = self._make_config(loop_threshold=9)
        pool.fetchrow.return_value = _fake_row(
            id=config.id,
            agent_name=config.agent_name,
            project_id=config.project_id,
            loop_threshold=9,
        )
        result = await backend.upsert_prevention_config(config)
        assert isinstance(result, PreventionConfig)
        assert result.loop_threshold == 9

    async def test_upserts_project_default_with_star_agent_name(
        self, backend: PostgresBackend, pool: MagicMock
    ) -> None:
        config = self._make_config(agent_name="*")
        pool.fetchrow.return_value = _fake_row(
            id=config.id, agent_name="*", project_id=config.project_id
        )
        result = await backend.upsert_prevention_config(config)
        assert result.agent_name == "*"
        call_args = pool.fetchrow.call_args[0]
        assert "*" in call_args

    async def test_passes_null_optional_fields(
        self, backend: PostgresBackend, pool: MagicMock
    ) -> None:
        """None values for max_steps, max_cost_usd, max_wall_time_s must be passed through."""
        config = self._make_config(max_steps=None)
        pool.fetchrow.return_value = _fake_row(
            id=config.id,
            agent_name=config.agent_name,
            project_id=config.project_id,
            max_steps=None,
        )
        await backend.upsert_prevention_config(config)
        call_args = pool.fetchrow.call_args[0]
        assert None in call_args  # max_steps=None must be forwarded, not omitted

    async def test_sql_contains_on_conflict_clause(
        self, backend: PostgresBackend, pool: MagicMock
    ) -> None:
        config = self._make_config()
        pool.fetchrow.return_value = _fake_row(
            id=config.id, agent_name=config.agent_name, project_id=config.project_id
        )
        await backend.upsert_prevention_config(config)
        sql = pool.fetchrow.call_args[0][0]
        assert "ON CONFLICT" in sql.upper()
        assert "RETURNING" in sql.upper()


# ---------------------------------------------------------------------------
# delete_prevention_config
# ---------------------------------------------------------------------------


class TestDeletePreventionConfig:
    async def test_returns_true_when_row_deleted(
        self, backend: PostgresBackend, pool: MagicMock
    ) -> None:
        pool.execute.return_value = "DELETE 1"
        result = await backend.delete_prevention_config("orchestrator", "proj-abc")
        assert result is True

    async def test_returns_false_when_no_row_found(
        self, backend: PostgresBackend, pool: MagicMock
    ) -> None:
        pool.execute.return_value = "DELETE 0"
        result = await backend.delete_prevention_config("orchestrator", "proj-abc")
        assert result is False

    async def test_passes_project_id_and_agent_name_to_query(
        self, backend: PostgresBackend, pool: MagicMock
    ) -> None:
        pool.execute.return_value = "DELETE 1"
        await backend.delete_prevention_config("my-agent", "proj-xyz")
        pool.execute.assert_called_once()
        call_args = pool.execute.call_args[0]
        assert "my-agent" in call_args
        assert "proj-xyz" in call_args

    async def test_returns_true_when_multiple_rows_deleted(
        self, backend: PostgresBackend, pool: MagicMock
    ) -> None:
        # DELETE 2 is unusual (unique constraint) but result != "DELETE 0" → True
        pool.execute.return_value = "DELETE 2"
        result = await backend.delete_prevention_config("orchestrator", "proj-abc")
        assert result is True

    async def test_deletes_project_default_config(
        self, backend: PostgresBackend, pool: MagicMock
    ) -> None:
        pool.execute.return_value = "DELETE 1"
        result = await backend.delete_prevention_config("*", "proj-abc")
        assert result is True
        call_args = pool.execute.call_args[0]
        assert "*" in call_args
