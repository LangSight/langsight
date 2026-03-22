"""
Unit tests for the PreventionConfig Pydantic model.

Covers:
- Default field values
- agent_name="*" as valid project-level default
- frozen=True — mutation raises ValidationError
- Optional budget fields default to None (disabled)
- Field type coercion (int/float/bool)
- created_at / updated_at auto-populated via Field(default_factory)
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from langsight.models import PreventionConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _minimal_config(**overrides) -> PreventionConfig:
    """Return the smallest valid PreventionConfig, with field overrides."""
    base = {
        "id": "cfg-test-001",
        "project_id": "proj-abc",
        "agent_name": "orchestrator",
    }
    base.update(overrides)
    return PreventionConfig(**base)


# ---------------------------------------------------------------------------
# Default values
# ---------------------------------------------------------------------------


class TestPreventionConfigDefaults:
    def test_loop_enabled_defaults_to_true(self) -> None:
        config = _minimal_config()
        assert config.loop_enabled is True

    def test_loop_threshold_defaults_to_three(self) -> None:
        config = _minimal_config()
        assert config.loop_threshold == 3

    def test_loop_action_defaults_to_terminate(self) -> None:
        config = _minimal_config()
        assert config.loop_action == "terminate"

    def test_max_steps_defaults_to_none(self) -> None:
        config = _minimal_config()
        assert config.max_steps is None

    def test_max_cost_usd_defaults_to_none(self) -> None:
        config = _minimal_config()
        assert config.max_cost_usd is None

    def test_max_wall_time_s_defaults_to_none(self) -> None:
        config = _minimal_config()
        assert config.max_wall_time_s is None

    def test_budget_soft_alert_defaults_to_080(self) -> None:
        config = _minimal_config()
        assert config.budget_soft_alert == 0.80

    def test_cb_enabled_defaults_to_true(self) -> None:
        config = _minimal_config()
        assert config.cb_enabled is True

    def test_cb_failure_threshold_defaults_to_five(self) -> None:
        config = _minimal_config()
        assert config.cb_failure_threshold == 5

    def test_cb_cooldown_seconds_defaults_to_60(self) -> None:
        config = _minimal_config()
        assert config.cb_cooldown_seconds == 60.0

    def test_cb_half_open_max_calls_defaults_to_two(self) -> None:
        config = _minimal_config()
        assert config.cb_half_open_max_calls == 2

    def test_created_at_auto_populated_with_utc_datetime(self) -> None:
        config = _minimal_config()
        assert isinstance(config.created_at, datetime)
        assert config.created_at.tzinfo is not None

    def test_updated_at_auto_populated_with_utc_datetime(self) -> None:
        config = _minimal_config()
        assert isinstance(config.updated_at, datetime)
        assert config.updated_at.tzinfo is not None


# ---------------------------------------------------------------------------
# agent_name="*" as project-level default
# ---------------------------------------------------------------------------


class TestProjectDefaultAgentName:
    def test_star_agent_name_is_accepted(self) -> None:
        config = _minimal_config(agent_name="*")
        assert config.agent_name == "*"

    def test_star_agent_name_preserved_exactly(self) -> None:
        config = _minimal_config(agent_name="*")
        assert config.agent_name == "*"
        assert len(config.agent_name) == 1

    def test_named_agent_is_accepted(self) -> None:
        config = _minimal_config(agent_name="billing-agent")
        assert config.agent_name == "billing-agent"

    def test_empty_string_agent_name_is_accepted(self) -> None:
        """Pydantic does not restrict the string value — empty string is technically valid."""
        config = _minimal_config(agent_name="")
        assert config.agent_name == ""


# ---------------------------------------------------------------------------
# Immutability (frozen=True)
# ---------------------------------------------------------------------------


class TestPreventionConfigImmutability:
    def test_modifying_loop_threshold_raises(self) -> None:
        config = _minimal_config()
        with pytest.raises((ValidationError, TypeError)):
            config.loop_threshold = 10  # type: ignore[misc]

    def test_modifying_agent_name_raises(self) -> None:
        config = _minimal_config()
        with pytest.raises((ValidationError, TypeError)):
            config.agent_name = "other-agent"  # type: ignore[misc]

    def test_modifying_cb_enabled_raises(self) -> None:
        config = _minimal_config()
        with pytest.raises((ValidationError, TypeError)):
            config.cb_enabled = False  # type: ignore[misc]

    def test_modifying_loop_enabled_raises(self) -> None:
        config = _minimal_config()
        with pytest.raises((ValidationError, TypeError)):
            config.loop_enabled = False  # type: ignore[misc]

    def test_modifying_project_id_raises(self) -> None:
        config = _minimal_config()
        with pytest.raises((ValidationError, TypeError)):
            config.project_id = "proj-other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Optional threshold fields — None means disabled
# ---------------------------------------------------------------------------


class TestOptionalThresholdFields:
    def test_max_steps_none_means_no_step_limit(self) -> None:
        config = _minimal_config(max_steps=None)
        assert config.max_steps is None

    def test_max_cost_usd_none_means_no_cost_limit(self) -> None:
        config = _minimal_config(max_cost_usd=None)
        assert config.max_cost_usd is None

    def test_max_wall_time_s_none_means_no_time_limit(self) -> None:
        config = _minimal_config(max_wall_time_s=None)
        assert config.max_wall_time_s is None

    def test_max_steps_with_positive_int(self) -> None:
        config = _minimal_config(max_steps=25)
        assert config.max_steps == 25

    def test_max_cost_usd_with_positive_float(self) -> None:
        config = _minimal_config(max_cost_usd=10.50)
        assert config.max_cost_usd == 10.50

    def test_max_wall_time_s_with_positive_float(self) -> None:
        config = _minimal_config(max_wall_time_s=300.0)
        assert config.max_wall_time_s == 300.0


# ---------------------------------------------------------------------------
# Full field construction
# ---------------------------------------------------------------------------


class TestPreventionConfigFullConstruction:
    def test_full_construction_with_all_fields(self) -> None:
        now = datetime.now(UTC)
        config = PreventionConfig(
            id="cfg-full",
            project_id="proj-xyz",
            agent_name="orchestrator",
            loop_enabled=True,
            loop_threshold=5,
            loop_action="warn",
            max_steps=50,
            max_cost_usd=2.00,
            max_wall_time_s=600.0,
            budget_soft_alert=0.75,
            cb_enabled=True,
            cb_failure_threshold=10,
            cb_cooldown_seconds=120.0,
            cb_half_open_max_calls=3,
            created_at=now,
            updated_at=now,
        )
        assert config.id == "cfg-full"
        assert config.project_id == "proj-xyz"
        assert config.agent_name == "orchestrator"
        assert config.loop_enabled is True
        assert config.loop_threshold == 5
        assert config.loop_action == "warn"
        assert config.max_steps == 50
        assert config.max_cost_usd == 2.00
        assert config.max_wall_time_s == 600.0
        assert config.budget_soft_alert == 0.75
        assert config.cb_enabled is True
        assert config.cb_failure_threshold == 10
        assert config.cb_cooldown_seconds == 120.0
        assert config.cb_half_open_max_calls == 3
        assert config.created_at == now
        assert config.updated_at == now

    def test_loop_disabled_configuration(self) -> None:
        """loop_enabled=False with loop_threshold present — both are stored."""
        config = _minimal_config(loop_enabled=False, loop_threshold=5)
        assert config.loop_enabled is False
        assert config.loop_threshold == 5

    def test_circuit_breaker_disabled_configuration(self) -> None:
        config = _minimal_config(cb_enabled=False)
        assert config.cb_enabled is False
        # Other CB fields are still stored even when disabled
        assert config.cb_failure_threshold == 5
        assert config.cb_cooldown_seconds == 60.0

    def test_two_configs_with_different_agent_names_are_independent(self) -> None:
        cfg_default = _minimal_config(agent_name="*", id="d1")
        cfg_agent = _minimal_config(agent_name="orchestrator", id="a1")
        assert cfg_default.agent_name != cfg_agent.agent_name
        assert cfg_default.id != cfg_agent.id

    def test_model_serialises_to_dict_without_error(self) -> None:
        config = _minimal_config()
        d = config.model_dump()
        assert d["id"] == "cfg-test-001"
        assert d["agent_name"] == "orchestrator"
        assert d["max_steps"] is None
