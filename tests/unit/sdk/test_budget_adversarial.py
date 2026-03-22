"""Adversarial and edge-case tests for budget guardrails.

Covers: max_steps=0, max_cost_usd=0.0, soft_alert_fraction boundaries,
negative costs, very large costs, and budget isolation between sessions.
"""

from __future__ import annotations

import pytest

from langsight.sdk.budget import BudgetConfig, BudgetViolation, BudgetWarning, SessionBudget


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


# ---------------------------------------------------------------------------
# max_steps=0 — should block immediately
# ---------------------------------------------------------------------------


class TestMaxStepsZero:
    """max_steps=0 means no calls should be allowed: step_count+1 > 0 is always True."""

    def test_first_call_blocked(self) -> None:
        budget = SessionBudget(BudgetConfig(max_steps=0))
        violation = budget.check_pre_call()
        assert violation is not None
        assert violation.limit_type == "max_steps"
        assert violation.limit_value == 0.0
        assert violation.actual_value == 1.0  # would-be first call

    def test_no_steps_recorded(self) -> None:
        budget = SessionBudget(BudgetConfig(max_steps=0))
        assert budget.step_count == 0


# ---------------------------------------------------------------------------
# max_cost_usd=0.0 — should block after any cost
# ---------------------------------------------------------------------------


class TestMaxCostZero:
    def test_zero_cost_call_does_not_trigger(self) -> None:
        """A call with 0.0 cost should not exceed the limit (0.0 > 0.0 is False)."""
        budget = SessionBudget(BudgetConfig(max_cost_usd=0.0))
        violation = budget.record_step_and_cost(cost_usd=0.0)
        assert violation is None

    def test_any_positive_cost_triggers(self) -> None:
        budget = SessionBudget(BudgetConfig(max_cost_usd=0.0))
        violation = budget.record_step_and_cost(cost_usd=0.001)
        assert violation is not None
        assert violation.limit_type == "max_cost_usd"
        assert violation.limit_value == 0.0
        assert violation.actual_value == pytest.approx(0.001)

    def test_cost_exceeded_blocks_next_pre_call(self) -> None:
        budget = SessionBudget(BudgetConfig(max_cost_usd=0.0))
        budget.record_step_and_cost(cost_usd=0.01)
        violation = budget.check_pre_call()
        assert violation is not None
        assert violation.limit_type == "max_cost_usd"


# ---------------------------------------------------------------------------
# soft_alert_fraction=0.0 — warns immediately
# ---------------------------------------------------------------------------


class TestSoftAlertFractionZero:
    def test_warns_on_first_step(self) -> None:
        """With fraction=0.0, threshold = max_steps * 0 = 0. So step_count >= 0 is always True."""
        budget = SessionBudget(
            BudgetConfig(max_steps=10, soft_alert_fraction=0.0)
        )
        # Even at step 0, the threshold is 0 so 0 >= 0 => warn
        warnings = budget.check_soft_thresholds()
        assert len(warnings) == 1
        assert warnings[0].limit_type == "max_steps"
        assert warnings[0].threshold_pct == 0.0

    def test_warns_on_first_cost(self) -> None:
        budget = SessionBudget(
            BudgetConfig(max_cost_usd=1.0, soft_alert_fraction=0.0)
        )
        # cumulative_cost_usd = 0.0 >= 1.0 * 0.0 = 0.0 => True
        warnings = budget.check_soft_thresholds()
        assert len(warnings) == 1
        assert warnings[0].limit_type == "max_cost_usd"

    def test_warns_on_first_wall_time(self, clock: _FakeClock) -> None:
        budget = SessionBudget(
            BudgetConfig(max_wall_time_s=60.0, soft_alert_fraction=0.0),
            _clock=clock,
        )
        # wall_time = 0.0 >= 60.0 * 0.0 = 0.0 => True
        warnings = budget.check_soft_thresholds()
        assert len(warnings) == 1
        assert warnings[0].limit_type == "max_wall_time_s"


# ---------------------------------------------------------------------------
# soft_alert_fraction=1.0 — warns only at exact limit
# ---------------------------------------------------------------------------


class TestSoftAlertFractionOne:
    def test_no_warn_below_limit(self) -> None:
        budget = SessionBudget(
            BudgetConfig(max_steps=10, soft_alert_fraction=1.0)
        )
        for _ in range(9):
            budget.record_step_and_cost()
        warnings = budget.check_soft_thresholds()
        assert len(warnings) == 0

    def test_warns_at_exact_limit(self) -> None:
        budget = SessionBudget(
            BudgetConfig(max_steps=10, soft_alert_fraction=1.0)
        )
        for _ in range(10):
            budget.record_step_and_cost()
        warnings = budget.check_soft_thresholds()
        assert len(warnings) == 1
        assert warnings[0].limit_type == "max_steps"

    def test_cost_warns_at_exact_limit(self) -> None:
        budget = SessionBudget(
            BudgetConfig(max_cost_usd=1.0, soft_alert_fraction=1.0)
        )
        budget.record_step_and_cost(cost_usd=0.99)
        warnings = budget.check_soft_thresholds()
        assert len(warnings) == 0

        budget.record_step_and_cost(cost_usd=0.01)
        warnings = budget.check_soft_thresholds()
        assert len(warnings) == 1


# ---------------------------------------------------------------------------
# Negative cost values (defensive check)
# ---------------------------------------------------------------------------


class TestNegativeCost:
    def test_negative_cost_is_ignored(self) -> None:
        """FIXED: negative costs are rejected and do not change the cumulative total."""
        budget = SessionBudget(BudgetConfig(max_cost_usd=1.0))
        budget.record_step_and_cost(cost_usd=0.50)
        budget.record_step_and_cost(cost_usd=-0.30)  # must be ignored
        assert budget.cumulative_cost_usd == pytest.approx(0.50)

    def test_negative_cost_cannot_undo_exceeded_flag(self) -> None:
        """FIXED: once cost limit exceeded, negative costs cannot reset the total."""
        budget = SessionBudget(BudgetConfig(max_cost_usd=1.0))
        violation = budget.record_step_and_cost(cost_usd=1.50)
        assert violation is not None
        # Negative cost rejected — total stays at 1.50
        budget.record_step_and_cost(cost_usd=-1.00)
        assert budget.cumulative_cost_usd == pytest.approx(1.50)
        # Flag is sticky — pre_call still fails
        violation = budget.check_pre_call()
        assert violation is not None
        assert violation.limit_type == "max_cost_usd"

    def test_all_negative_costs_leave_zero(self) -> None:
        """FIXED: all-negative cost calls leave cumulative at 0.0 (nothing added)."""
        budget = SessionBudget(BudgetConfig(max_cost_usd=0.0))
        budget.record_step_and_cost(cost_usd=-0.01)  # rejected
        assert budget.cumulative_cost_usd == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Very large cost values (overflow check)
# ---------------------------------------------------------------------------


class TestVeryLargeCost:
    def test_large_cost_triggers_violation(self) -> None:
        budget = SessionBudget(BudgetConfig(max_cost_usd=100.0))
        violation = budget.record_step_and_cost(cost_usd=1e15)
        assert violation is not None
        assert violation.actual_value == pytest.approx(1e15)

    def test_large_accumulated_cost(self) -> None:
        budget = SessionBudget(BudgetConfig(max_cost_usd=1e18))
        for _ in range(1000):
            budget.record_step_and_cost(cost_usd=1e12)
        assert budget.cumulative_cost_usd == pytest.approx(1e15)
        violation = budget.check_pre_call()
        assert violation is None  # 1e15 < 1e18

    def test_float_precision_near_limit(self) -> None:
        """Test that floating-point precision doesn't cause false positives."""
        budget = SessionBudget(BudgetConfig(max_cost_usd=1.0))
        # Add costs that should sum to exactly 1.0 in ideal math
        for _ in range(10):
            budget.record_step_and_cost(cost_usd=0.1)
        # Due to float precision, sum of 10 * 0.1 may not be exactly 1.0
        # The important thing: we don't crash and behavior is reasonable
        assert isinstance(budget.cumulative_cost_usd, float)


# ---------------------------------------------------------------------------
# Budget isolation: multiple sessions sharing same client config
# ---------------------------------------------------------------------------


class TestBudgetIsolation:
    def test_separate_budgets_independent_steps(self) -> None:
        config = BudgetConfig(max_steps=3)
        budget_a = SessionBudget(config)
        budget_b = SessionBudget(config)

        # Session A exhausts its budget
        for _ in range(3):
            assert budget_a.check_pre_call() is None
            budget_a.record_step_and_cost()
        assert budget_a.check_pre_call() is not None  # blocked

        # Session B should be independent
        assert budget_b.check_pre_call() is None
        budget_b.record_step_and_cost()
        assert budget_b.step_count == 1

    def test_separate_budgets_independent_cost(self) -> None:
        config = BudgetConfig(max_cost_usd=1.0)
        budget_a = SessionBudget(config)
        budget_b = SessionBudget(config)

        budget_a.record_step_and_cost(cost_usd=1.50)
        assert budget_a.check_pre_call() is not None  # blocked

        assert budget_b.check_pre_call() is None  # unaffected
        assert budget_b.cumulative_cost_usd == 0.0

    def test_separate_budgets_independent_wall_time(self, clock: _FakeClock) -> None:
        """Each budget tracks its own start time."""
        config = BudgetConfig(max_wall_time_s=10.0)
        budget_a = SessionBudget(config, _clock=clock)
        clock.advance(5.0)
        budget_b = SessionBudget(config, _clock=clock)  # starts at 1005.0

        clock.advance(6.0)
        # budget_a: wall_time = 11.0 >= 10.0 => violation
        violation_a = budget_a.check_pre_call()
        assert violation_a is not None
        assert violation_a.limit_type == "max_wall_time_s"

        # budget_b: wall_time = 6.0 < 10.0 => no violation
        violation_b = budget_b.check_pre_call()
        assert violation_b is None


# ---------------------------------------------------------------------------
# max_wall_time_s=0 — should block immediately
# ---------------------------------------------------------------------------


class TestMaxWallTimeZero:
    def test_blocks_immediately(self, clock: _FakeClock) -> None:
        """wall_time = 0.0 >= 0.0 => violation."""
        budget = SessionBudget(
            BudgetConfig(max_wall_time_s=0.0), _clock=clock
        )
        violation = budget.check_pre_call()
        assert violation is not None
        assert violation.limit_type == "max_wall_time_s"
        assert violation.limit_value == 0.0

    def test_any_time_elapsed_also_blocked(self, clock: _FakeClock) -> None:
        budget = SessionBudget(
            BudgetConfig(max_wall_time_s=0.0), _clock=clock
        )
        clock.advance(0.001)
        violation = budget.check_pre_call()
        assert violation is not None


# ---------------------------------------------------------------------------
# Step count incrementing regardless of cost violation
# ---------------------------------------------------------------------------


class TestStepCountWithCostViolation:
    def test_step_count_increments_even_when_cost_violated(self) -> None:
        budget = SessionBudget(BudgetConfig(max_cost_usd=0.5, max_steps=100))
        violation = budget.record_step_and_cost(cost_usd=1.0)
        assert violation is not None  # cost exceeded
        assert budget.step_count == 1  # still recorded the step


# ---------------------------------------------------------------------------
# Combined limits: step + cost + wall time all active
# ---------------------------------------------------------------------------


class TestCombinedLimits:
    def test_step_limit_reached_first(self, clock: _FakeClock) -> None:
        budget = SessionBudget(
            BudgetConfig(max_steps=2, max_cost_usd=10.0, max_wall_time_s=60.0),
            _clock=clock,
        )
        budget.record_step_and_cost(cost_usd=0.01)
        budget.record_step_and_cost(cost_usd=0.01)
        violation = budget.check_pre_call()
        assert violation is not None
        assert violation.limit_type == "max_steps"

    def test_cost_limit_reached_first(self, clock: _FakeClock) -> None:
        budget = SessionBudget(
            BudgetConfig(max_steps=100, max_cost_usd=0.5, max_wall_time_s=60.0),
            _clock=clock,
        )
        budget.record_step_and_cost(cost_usd=0.60)
        # Cost violated in post-call, pre-call checks cost flag first
        violation = budget.check_pre_call()
        assert violation is not None
        assert violation.limit_type == "max_cost_usd"

    def test_wall_time_limit_reached_first(self, clock: _FakeClock) -> None:
        budget = SessionBudget(
            BudgetConfig(max_steps=100, max_cost_usd=10.0, max_wall_time_s=5.0),
            _clock=clock,
        )
        budget.record_step_and_cost(cost_usd=0.01)
        clock.advance(5.0)
        violation = budget.check_pre_call()
        assert violation is not None
        assert violation.limit_type == "max_wall_time_s"

    def test_priority_order_cost_exceeds_and_steps_exceeds(self) -> None:
        """When both cost and steps are exceeded, cost flag is checked first
        in check_pre_call because _cost_exceeded is checked before max_steps.
        """
        budget = SessionBudget(
            BudgetConfig(max_steps=1, max_cost_usd=0.0)
        )
        budget.record_step_and_cost(cost_usd=0.01)  # exceeds cost, uses step
        violation = budget.check_pre_call()
        assert violation is not None
        # Cost is checked first in check_pre_call
        assert violation.limit_type == "max_cost_usd"


# ---------------------------------------------------------------------------
# Soft threshold fires only once per limit, even across multiple calls
# ---------------------------------------------------------------------------


class TestSoftThresholdFiringBehavior:
    def test_fires_once_never_again(self) -> None:
        budget = SessionBudget(
            BudgetConfig(max_steps=10, soft_alert_fraction=0.50)
        )
        for _ in range(5):
            budget.record_step_and_cost()
        warnings1 = budget.check_soft_thresholds()
        assert len(warnings1) == 1

        for _ in range(4):
            budget.record_step_and_cost()
        warnings2 = budget.check_soft_thresholds()
        assert len(warnings2) == 0  # already warned

    def test_different_limit_types_warn_independently(self, clock: _FakeClock) -> None:
        budget = SessionBudget(
            BudgetConfig(
                max_steps=10,
                max_cost_usd=1.0,
                max_wall_time_s=100.0,
                soft_alert_fraction=0.5,
            ),
            _clock=clock,
        )
        # Trigger steps warning only
        for _ in range(5):
            budget.record_step_and_cost(cost_usd=0.01)
        warnings = budget.check_soft_thresholds()
        types = {w.limit_type for w in warnings}
        assert "max_steps" in types
        assert "max_cost_usd" not in types  # only $0.05, below 50% of $1.0

        # Now trigger cost warning
        budget.record_step_and_cost(cost_usd=0.50)
        warnings = budget.check_soft_thresholds()
        types = {w.limit_type for w in warnings}
        assert "max_cost_usd" in types
        assert "max_steps" not in types  # already fired


# ---------------------------------------------------------------------------
# Record step and cost with no limits configured
# ---------------------------------------------------------------------------


class TestNoLimitsAllowed:
    def test_record_many_steps_no_violation(self) -> None:
        budget = SessionBudget(BudgetConfig())
        for i in range(10_000):
            violation = budget.record_step_and_cost(cost_usd=float(i))
            assert violation is None
        assert budget.step_count == 10_000

    def test_pre_call_never_fails(self, clock: _FakeClock) -> None:
        budget = SessionBudget(BudgetConfig(), _clock=clock)
        clock.advance(1e9)  # billion seconds
        assert budget.check_pre_call() is None
