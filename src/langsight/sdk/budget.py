"""
Budget guardrails — prevent runaway agent sessions.

Tracks three limits per session:
  1. max_steps:       hard stop on number of tool calls
  2. max_wall_time_s: hard stop on wall-clock time
  3. max_cost_usd:    hard stop on cumulative LLM + tool cost

Cost tracking is post-call (we can't predict the next call's cost),
so the cost limit fires on the first call that pushes over the threshold.
Step count and wall time are checked pre-call.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Literal

import structlog
from pydantic import BaseModel

logger = structlog.get_logger()


class BudgetConfig(BaseModel, frozen=True):
    """Immutable budget configuration."""

    max_cost_usd: float | None = None
    max_steps: int | None = None
    max_wall_time_s: float | None = None
    soft_alert_fraction: float = 0.80


@dataclass(frozen=True)
class BudgetViolation:
    """A hard budget limit has been exceeded."""

    limit_type: Literal["max_cost_usd", "max_steps", "max_wall_time_s"]
    limit_value: float
    actual_value: float


@dataclass(frozen=True)
class BudgetWarning:
    """A soft budget threshold has been crossed (fires once per limit)."""

    limit_type: str
    threshold_pct: float
    current_value: float
    limit_value: float


class SessionBudget:
    """Per-session budget tracker.

    Pre-call:  check step count and wall time (knowable before the call).
    Post-call: update step count, add cost, check cost limit.
    """

    def __init__(
        self,
        config: BudgetConfig,
        *,
        _clock: object | None = None,
    ) -> None:
        self._config = config
        self._step_count: int = 0
        self._cumulative_cost_usd: float = 0.0
        self._started_at: float = (
            _clock.monotonic() if _clock is not None else time.monotonic()  # type: ignore[union-attr]
        )
        self._soft_warned: set[str] = set()
        self._clock = _clock
        self._cost_exceeded: bool = False

    def _now(self) -> float:
        if self._clock is not None:
            return self._clock.monotonic()  # type: ignore[union-attr]
        return time.monotonic()

    @property
    def step_count(self) -> int:
        return self._step_count

    @property
    def cumulative_cost_usd(self) -> float:
        return self._cumulative_cost_usd

    @property
    def wall_time_s(self) -> float:
        return self._now() - self._started_at

    def check_pre_call(self) -> BudgetViolation | None:
        """Pre-call: check step count, wall time, and post-call cost flag.

        Returns a BudgetViolation if any hard limit is exceeded, None otherwise.
        """
        # Check if a previous post-call cost check flagged overage
        if self._cost_exceeded and self._config.max_cost_usd is not None:
            return BudgetViolation(
                limit_type="max_cost_usd",
                limit_value=self._config.max_cost_usd,
                actual_value=self._cumulative_cost_usd,
            )

        # Check step count (the NEXT call would be step_count + 1)
        if self._config.max_steps is not None:
            if self._step_count + 1 > self._config.max_steps:
                return BudgetViolation(
                    limit_type="max_steps",
                    limit_value=float(self._config.max_steps),
                    actual_value=float(self._step_count + 1),
                )

        # Check wall time
        if self._config.max_wall_time_s is not None:
            wall = self.wall_time_s
            if wall >= self._config.max_wall_time_s:
                return BudgetViolation(
                    limit_type="max_wall_time_s",
                    limit_value=self._config.max_wall_time_s,
                    actual_value=wall,
                )

        return None

    def record_step_and_cost(self, cost_usd: float = 0.0) -> BudgetViolation | None:
        """Post-call: increment step count, add cost, check cost limit.

        Returns a BudgetViolation if the cost limit is now exceeded.
        The violation is stored so the next pre-call check catches it.
        """
        import math

        self._step_count += 1
        # Guard: reject non-finite or negative costs to prevent state corruption.
        # Negative costs would reduce the cumulative total (budget bypass).
        # NaN/inf would poison all future comparisons.
        if math.isfinite(cost_usd) and cost_usd >= 0.0:
            self._cumulative_cost_usd += cost_usd

        if (
            self._config.max_cost_usd is not None
            and self._cumulative_cost_usd > self._config.max_cost_usd
        ):
            self._cost_exceeded = True
            return BudgetViolation(
                limit_type="max_cost_usd",
                limit_value=self._config.max_cost_usd,
                actual_value=self._cumulative_cost_usd,
            )

        return None

    def check_soft_thresholds(self) -> list[BudgetWarning]:
        """Check all limits against the soft threshold. Returns warnings not yet fired.

        Each warning fires at most once per session per limit type.
        """
        warnings: list[BudgetWarning] = []
        fraction = self._config.soft_alert_fraction

        if self._config.max_steps is not None and "max_steps" not in self._soft_warned:
            threshold = self._config.max_steps * fraction
            if self._step_count >= threshold:
                self._soft_warned.add("max_steps")
                warnings.append(
                    BudgetWarning(
                        limit_type="max_steps",
                        threshold_pct=fraction,
                        current_value=float(self._step_count),
                        limit_value=float(self._config.max_steps),
                    )
                )

        if (
            self._config.max_cost_usd is not None
            and "max_cost_usd" not in self._soft_warned
        ):
            threshold = self._config.max_cost_usd * fraction
            if self._cumulative_cost_usd >= threshold:
                self._soft_warned.add("max_cost_usd")
                warnings.append(
                    BudgetWarning(
                        limit_type="max_cost_usd",
                        threshold_pct=fraction,
                        current_value=self._cumulative_cost_usd,
                        limit_value=self._config.max_cost_usd,
                    )
                )

        if (
            self._config.max_wall_time_s is not None
            and "max_wall_time_s" not in self._soft_warned
        ):
            threshold = self._config.max_wall_time_s * fraction
            wall = self.wall_time_s
            if wall >= threshold:
                self._soft_warned.add("max_wall_time_s")
                warnings.append(
                    BudgetWarning(
                        limit_type="max_wall_time_s",
                        threshold_pct=fraction,
                        current_value=wall,
                        limit_value=self._config.max_wall_time_s,
                    )
                )

        return warnings
