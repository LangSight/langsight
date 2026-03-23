"""
Circuit breaker — per-server protection against cascading failures.

States:
  CLOSED    → normal, calls pass through
  OPEN      → disabled, calls rejected immediately
  HALF_OPEN → testing recovery, limited calls allowed

Transitions:
  CLOSED  + N consecutive failures       → OPEN
  OPEN    + cooldown elapsed             → HALF_OPEN
  HALF_OPEN + all test calls succeed     → CLOSED
  HALF_OPEN + any test call fails        → OPEN (reset cooldown)
"""

from __future__ import annotations

import time
from enum import StrEnum
from typing import Protocol

import structlog
from pydantic import BaseModel

logger = structlog.get_logger()


class _MonotonicClock(Protocol):
    def monotonic(self) -> float: ...


class CircuitBreakerState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerConfig(BaseModel, frozen=True):
    """Immutable circuit breaker configuration."""

    failure_threshold: int = 5
    cooldown_seconds: float = 60.0
    half_open_max_calls: int = 2


class CircuitBreaker:
    """Per-server circuit breaker state machine.

    Thread-safe for single-threaded asyncio (no locks needed — Python GIL +
    cooperative scheduling means no preemption within a sync method).
    """

    def __init__(
        self,
        server_name: str,
        config: CircuitBreakerConfig,
        *,
        _clock: _MonotonicClock | None = None,
    ) -> None:
        self._server_name = server_name
        self._config = config
        self._state = CircuitBreakerState.CLOSED
        self._consecutive_failures: int = 0
        self._opened_at: float | None = None
        self._half_open_successes: int = 0
        self._half_open_calls: int = 0
        # Allow injecting a clock for testing (must have .monotonic() method)
        self._clock = _clock

    def _now(self) -> float:
        if self._clock is not None:
            return self._clock.monotonic()
        return time.monotonic()

    @property
    def state(self) -> CircuitBreakerState:
        return self._state

    @property
    def server_name(self) -> str:
        return self._server_name

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    @property
    def cooldown_remaining_s(self) -> float:
        """Seconds remaining in cooldown. 0.0 if not in OPEN state."""
        if self._state != CircuitBreakerState.OPEN or self._opened_at is None:
            return 0.0
        elapsed = self._now() - self._opened_at
        remaining = self._config.cooldown_seconds - elapsed
        return max(0.0, remaining)

    def should_allow(self) -> bool:
        """Pre-call check. Returns True if the call should proceed."""
        if self._state == CircuitBreakerState.CLOSED:
            return True

        if self._state == CircuitBreakerState.OPEN:
            if self._opened_at is None:
                return False
            elapsed = self._now() - self._opened_at
            if elapsed >= self._config.cooldown_seconds:
                # Cooldown elapsed → transition to HALF_OPEN
                self._state = CircuitBreakerState.HALF_OPEN
                self._half_open_successes = 0
                self._half_open_calls = 0
                logger.info(
                    "circuit_breaker.half_open",
                    server=self._server_name,
                    cooldown_s=self._config.cooldown_seconds,
                )
                return True
            return False

        # HALF_OPEN — allow limited calls
        return self._half_open_calls < self._config.half_open_max_calls

    def record_success(self) -> CircuitBreakerState:
        """Post-call: record a successful call. Returns the new state."""
        if self._state == CircuitBreakerState.CLOSED:
            self._consecutive_failures = 0
            return self._state

        if self._state == CircuitBreakerState.HALF_OPEN:
            self._half_open_successes += 1
            self._half_open_calls += 1
            if self._half_open_successes >= self._config.half_open_max_calls:
                # All test calls succeeded → close circuit
                self._state = CircuitBreakerState.CLOSED
                self._consecutive_failures = 0
                self._opened_at = None
                logger.info(
                    "circuit_breaker.closed",
                    server=self._server_name,
                    message="recovered after successful test calls",
                )
            return self._state

        return self._state

    def record_failure(self) -> CircuitBreakerState:
        """Post-call: record a failed call. Returns the new state."""
        if self._state == CircuitBreakerState.CLOSED:
            self._consecutive_failures += 1
            if self._consecutive_failures >= self._config.failure_threshold:
                self._state = CircuitBreakerState.OPEN
                self._opened_at = self._now()
                logger.warning(
                    "circuit_breaker.open",
                    server=self._server_name,
                    failures=self._consecutive_failures,
                    cooldown_s=self._config.cooldown_seconds,
                )
            return self._state

        if self._state == CircuitBreakerState.HALF_OPEN:
            # Test call failed → reopen with fresh cooldown
            self._half_open_calls += 1
            self._state = CircuitBreakerState.OPEN
            self._opened_at = self._now()
            logger.warning(
                "circuit_breaker.reopened",
                server=self._server_name,
                message="test call failed during half-open",
                cooldown_s=self._config.cooldown_seconds,
            )
            return self._state

        return self._state
