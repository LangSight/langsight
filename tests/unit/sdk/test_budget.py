from __future__ import annotations

import pytest

from langsight.sdk.budget import BudgetConfig, SessionBudget


class _FakeClock:
    """Deterministic clock for testing."""

    def __init__(self, start: float = 0.0) -> None:
        self._time = start

    def monotonic(self) -> float:
        return self._time

    def advance(self, seconds: float) -> None:
        self._time += seconds


@pytest.fixture
def clock() -> _FakeClock:
    return _FakeClock(start=1000.0)


class TestStepLimit:
    def test_no_limit_allows_unlimited_steps(self) -> None:
        budget = SessionBudget(BudgetConfig())
        for _ in range(100):
            assert budget.check_pre_call() is None
            budget.record_step_and_cost()

    def test_within_limit_allows_call(self) -> None:
        budget = SessionBudget(BudgetConfig(max_steps=5))
        for _ in range(5):
            assert budget.check_pre_call() is None
            budget.record_step_and_cost()

    def test_exceeding_limit_returns_violation(self) -> None:
        budget = SessionBudget(BudgetConfig(max_steps=3))
        for _ in range(3):
            assert budget.check_pre_call() is None
            budget.record_step_and_cost()
        violation = budget.check_pre_call()
        assert violation is not None
        assert violation.limit_type == "max_steps"
        assert violation.limit_value == 3.0
        assert violation.actual_value == 4.0  # would-be 4th call

    def test_step_count_property(self) -> None:
        budget = SessionBudget(BudgetConfig(max_steps=10))
        assert budget.step_count == 0
        budget.record_step_and_cost()
        assert budget.step_count == 1
        budget.record_step_and_cost()
        assert budget.step_count == 2


class TestWallTimeLimit:
    def test_within_limit_allows_call(self, clock: _FakeClock) -> None:
        budget = SessionBudget(BudgetConfig(max_wall_time_s=60.0), _clock=clock)
        clock.advance(30.0)
        assert budget.check_pre_call() is None

    def test_exceeding_limit_returns_violation(self, clock: _FakeClock) -> None:
        budget = SessionBudget(BudgetConfig(max_wall_time_s=60.0), _clock=clock)
        clock.advance(60.0)
        violation = budget.check_pre_call()
        assert violation is not None
        assert violation.limit_type == "max_wall_time_s"
        assert violation.limit_value == 60.0
        assert violation.actual_value >= 60.0

    def test_wall_time_property(self, clock: _FakeClock) -> None:
        budget = SessionBudget(BudgetConfig(), _clock=clock)
        assert budget.wall_time_s == pytest.approx(0.0)
        clock.advance(5.0)
        assert budget.wall_time_s == pytest.approx(5.0)


class TestCostLimit:
    def test_no_limit_allows_unlimited_cost(self) -> None:
        budget = SessionBudget(BudgetConfig())
        for _ in range(10):
            result = budget.record_step_and_cost(cost_usd=1.0)
            assert result is None

    def test_within_limit_no_violation(self) -> None:
        budget = SessionBudget(BudgetConfig(max_cost_usd=1.00))
        result = budget.record_step_and_cost(cost_usd=0.50)
        assert result is None

    def test_exceeding_limit_returns_violation(self) -> None:
        budget = SessionBudget(BudgetConfig(max_cost_usd=1.00))
        budget.record_step_and_cost(cost_usd=0.60)
        violation = budget.record_step_and_cost(cost_usd=0.50)
        assert violation is not None
        assert violation.limit_type == "max_cost_usd"
        assert violation.limit_value == 1.00
        assert violation.actual_value == pytest.approx(1.10)

    def test_cost_violation_blocks_next_pre_call(self) -> None:
        budget = SessionBudget(BudgetConfig(max_cost_usd=1.00))
        budget.record_step_and_cost(cost_usd=1.10)
        violation = budget.check_pre_call()
        assert violation is not None
        assert violation.limit_type == "max_cost_usd"

    def test_cumulative_cost_property(self) -> None:
        budget = SessionBudget(BudgetConfig())
        assert budget.cumulative_cost_usd == 0.0
        budget.record_step_and_cost(cost_usd=0.25)
        assert budget.cumulative_cost_usd == pytest.approx(0.25)
        budget.record_step_and_cost(cost_usd=0.30)
        assert budget.cumulative_cost_usd == pytest.approx(0.55)


class TestSoftThresholds:
    def test_warns_at_threshold(self) -> None:
        budget = SessionBudget(
            BudgetConfig(max_steps=10, soft_alert_fraction=0.80)
        )
        for _ in range(7):
            budget.record_step_and_cost()
        warnings = budget.check_soft_thresholds()
        assert len(warnings) == 0

        budget.record_step_and_cost()  # step 8 = 80%
        warnings = budget.check_soft_thresholds()
        assert len(warnings) == 1
        assert warnings[0].limit_type == "max_steps"
        assert warnings[0].threshold_pct == 0.80

    def test_warns_once_only(self) -> None:
        budget = SessionBudget(
            BudgetConfig(max_steps=10, soft_alert_fraction=0.80)
        )
        for _ in range(8):
            budget.record_step_and_cost()
        warnings1 = budget.check_soft_thresholds()
        assert len(warnings1) == 1
        # Second check should not re-warn
        budget.record_step_and_cost()
        warnings2 = budget.check_soft_thresholds()
        assert len(warnings2) == 0

    def test_cost_soft_threshold(self) -> None:
        budget = SessionBudget(
            BudgetConfig(max_cost_usd=1.00, soft_alert_fraction=0.80)
        )
        budget.record_step_and_cost(cost_usd=0.85)
        warnings = budget.check_soft_thresholds()
        assert len(warnings) == 1
        assert warnings[0].limit_type == "max_cost_usd"

    def test_wall_time_soft_threshold(self, clock: _FakeClock) -> None:
        budget = SessionBudget(
            BudgetConfig(max_wall_time_s=100.0, soft_alert_fraction=0.80),
            _clock=clock,
        )
        clock.advance(85.0)
        warnings = budget.check_soft_thresholds()
        assert len(warnings) == 1
        assert warnings[0].limit_type == "max_wall_time_s"

    def test_multiple_soft_thresholds(self, clock: _FakeClock) -> None:
        budget = SessionBudget(
            BudgetConfig(
                max_steps=10,
                max_cost_usd=1.00,
                max_wall_time_s=100.0,
                soft_alert_fraction=0.80,
            ),
            _clock=clock,
        )
        # Trigger all three
        for _ in range(8):
            budget.record_step_and_cost(cost_usd=0.11)
        clock.advance(85.0)
        warnings = budget.check_soft_thresholds()
        types = {w.limit_type for w in warnings}
        assert types == {"max_steps", "max_cost_usd", "max_wall_time_s"}


class TestNoLimitsConfigured:
    def test_no_violation_ever(self, clock: _FakeClock) -> None:
        budget = SessionBudget(BudgetConfig(), _clock=clock)
        for _ in range(100):
            assert budget.check_pre_call() is None
            budget.record_step_and_cost(cost_usd=10.0)
        clock.advance(99999.0)
        assert budget.check_pre_call() is None
        assert budget.check_soft_thresholds() == []
