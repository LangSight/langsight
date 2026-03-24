"""Adversarial and edge-case tests for the circuit breaker state machine.

Focuses on degenerate configurations, rapid state cycling, and boundary
conditions that the happy-path tests do not cover.
"""

from __future__ import annotations

import pytest

from langsight.sdk.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerState,
)


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
# failure_threshold=0  (degenerate: should it trip immediately?)
# ---------------------------------------------------------------------------


class TestFailureThresholdZero:
    """When failure_threshold=0, the breaker should never open because
    the condition is `consecutive_failures >= threshold` and 0 >= 0 is True
    on the first failure, but with 0 failures recorded before the check,
    the initial call should still be allowed.

    This validates how the code handles a nonsensical configuration.
    """

    def test_starts_closed(self, clock: _FakeClock) -> None:
        config = CircuitBreakerConfig(failure_threshold=0, cooldown_seconds=5.0)
        cb = CircuitBreaker("edge-srv", config, _clock=clock)
        assert cb.state == CircuitBreakerState.CLOSED

    def test_should_allow_initially(self, clock: _FakeClock) -> None:
        config = CircuitBreakerConfig(failure_threshold=0, cooldown_seconds=5.0)
        cb = CircuitBreaker("edge-srv", config, _clock=clock)
        # CLOSED state always allows calls regardless of threshold
        assert cb.should_allow() is True

    def test_single_failure_opens_circuit(self, clock: _FakeClock) -> None:
        """With threshold=0, any failure >= 0 consecutive failures should trigger OPEN."""
        config = CircuitBreakerConfig(failure_threshold=0, cooldown_seconds=5.0)
        cb = CircuitBreaker("edge-srv", config, _clock=clock)
        # The very first failure: consecutive_failures goes to 1, 1 >= 0 => OPEN
        state = cb.record_failure()
        assert state == CircuitBreakerState.OPEN

    def test_rejects_after_single_failure(self, clock: _FakeClock) -> None:
        config = CircuitBreakerConfig(failure_threshold=0, cooldown_seconds=5.0)
        cb = CircuitBreaker("edge-srv", config, _clock=clock)
        cb.record_failure()
        assert cb.should_allow() is False


# ---------------------------------------------------------------------------
# failure_threshold=1  (opens on very first failure)
# ---------------------------------------------------------------------------


class TestFailureThresholdOne:
    """threshold=1 means the breaker trips on the first recorded failure."""

    def test_first_failure_opens(self, clock: _FakeClock) -> None:
        config = CircuitBreakerConfig(
            failure_threshold=1, cooldown_seconds=10.0, half_open_max_calls=1
        )
        cb = CircuitBreaker("strict-srv", config, _clock=clock)
        assert cb.state == CircuitBreakerState.CLOSED
        state = cb.record_failure()
        assert state == CircuitBreakerState.OPEN
        assert cb.should_allow() is False

    def test_recovery_with_single_half_open_call(self, clock: _FakeClock) -> None:
        config = CircuitBreakerConfig(
            failure_threshold=1, cooldown_seconds=5.0, half_open_max_calls=1
        )
        cb = CircuitBreaker("strict-srv", config, _clock=clock)
        cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN

        clock.advance(5.0)
        assert cb.should_allow() is True
        assert cb.state == CircuitBreakerState.HALF_OPEN

        cb.record_success()
        assert cb.state == CircuitBreakerState.CLOSED

    def test_half_open_failure_reopens_immediately(self, clock: _FakeClock) -> None:
        config = CircuitBreakerConfig(
            failure_threshold=1, cooldown_seconds=5.0, half_open_max_calls=1
        )
        cb = CircuitBreaker("strict-srv", config, _clock=clock)
        cb.record_failure()
        clock.advance(5.0)
        cb.should_allow()  # -> HALF_OPEN
        cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN


# ---------------------------------------------------------------------------
# cooldown_seconds=0  (immediate recovery attempt)
# ---------------------------------------------------------------------------


class TestZeroCooldown:
    """With cooldown_seconds=0 the circuit should transition from OPEN to
    HALF_OPEN on the very next should_allow() call.
    """

    def test_immediate_transition_to_half_open(self, clock: _FakeClock) -> None:
        config = CircuitBreakerConfig(
            failure_threshold=2, cooldown_seconds=0.0, half_open_max_calls=1
        )
        cb = CircuitBreaker("fast-recover", config, _clock=clock)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN
        # cooldown=0 means elapsed >= 0 is always true
        assert cb.should_allow() is True
        assert cb.state == CircuitBreakerState.HALF_OPEN

    def test_cooldown_remaining_is_zero_when_open(self, clock: _FakeClock) -> None:
        config = CircuitBreakerConfig(
            failure_threshold=2, cooldown_seconds=0.0, half_open_max_calls=1
        )
        cb = CircuitBreaker("fast-recover", config, _clock=clock)
        cb.record_failure()
        cb.record_failure()
        # Even immediately after opening, cooldown remaining should be 0
        assert cb.cooldown_remaining_s == 0.0

    def test_rapid_close_after_open(self, clock: _FakeClock) -> None:
        config = CircuitBreakerConfig(
            failure_threshold=2, cooldown_seconds=0.0, half_open_max_calls=1
        )
        cb = CircuitBreaker("fast-recover", config, _clock=clock)
        cb.record_failure()
        cb.record_failure()
        cb.should_allow()  # -> HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitBreakerState.CLOSED


# ---------------------------------------------------------------------------
# Rapid cycling: OPEN -> HALF_OPEN -> OPEN -> HALF_OPEN -> ...
# ---------------------------------------------------------------------------


class TestRapidCycling:
    """Test rapid cycling between OPEN and HALF_OPEN without the clock
    advancing (using cooldown_seconds=0).
    """

    def test_five_rapid_cycles(self, clock: _FakeClock) -> None:
        config = CircuitBreakerConfig(
            failure_threshold=1, cooldown_seconds=0.0, half_open_max_calls=1
        )
        cb = CircuitBreaker("flaky-srv", config, _clock=clock)

        for _cycle in range(5):
            # Trip open
            if cb.state == CircuitBreakerState.CLOSED:
                cb.record_failure()
            assert cb.state == CircuitBreakerState.OPEN

            # Immediately go to half-open (cooldown=0)
            assert cb.should_allow() is True
            assert cb.state == CircuitBreakerState.HALF_OPEN

            # Fail again -> back to open
            cb.record_failure()
            assert cb.state == CircuitBreakerState.OPEN

    def test_cycle_then_recover(self, clock: _FakeClock) -> None:
        """After several failed recovery attempts, a success closes the circuit."""
        config = CircuitBreakerConfig(
            failure_threshold=1, cooldown_seconds=0.0, half_open_max_calls=1
        )
        cb = CircuitBreaker("eventually-ok", config, _clock=clock)
        cb.record_failure()

        # 3 failed recovery attempts
        for _ in range(3):
            cb.should_allow()
            cb.record_failure()
            assert cb.state == CircuitBreakerState.OPEN

        # Finally recover
        cb.should_allow()
        cb.record_success()
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.should_allow() is True

    def test_cycling_with_real_cooldown(self, clock: _FakeClock) -> None:
        """Cycle with non-zero cooldown — each reopen resets the cooldown timer."""
        config = CircuitBreakerConfig(
            failure_threshold=2, cooldown_seconds=10.0, half_open_max_calls=1
        )
        cb = CircuitBreaker("cycling-srv", config, _clock=clock)

        # Trip open
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN

        # Wait for cooldown, enter half-open, fail again
        clock.advance(10.0)
        cb.should_allow()  # -> HALF_OPEN
        cb.record_failure()  # -> OPEN (fresh cooldown)
        assert cb.state == CircuitBreakerState.OPEN

        # Not enough time for second cooldown
        clock.advance(5.0)
        assert cb.should_allow() is False

        # Full second cooldown
        clock.advance(5.0)
        assert cb.should_allow() is True
        assert cb.state == CircuitBreakerState.HALF_OPEN


# ---------------------------------------------------------------------------
# Half-open call limiting
# ---------------------------------------------------------------------------


class TestHalfOpenCallLimiting:
    """Verify that HALF_OPEN only allows half_open_max_calls before rejecting."""

    def test_exceeding_max_calls_in_half_open(self, clock: _FakeClock) -> None:
        config = CircuitBreakerConfig(
            failure_threshold=2, cooldown_seconds=5.0, half_open_max_calls=2
        )
        cb = CircuitBreaker("srv", config, _clock=clock)
        cb.record_failure()
        cb.record_failure()
        clock.advance(5.0)

        # First call transitions to HALF_OPEN and is allowed
        assert cb.should_allow() is True
        cb.record_success()
        # Second call still allowed (half_open_calls=1, max=2)
        assert cb.should_allow() is True
        # But record the second before checking the third
        cb.record_success()  # closes circuit
        assert cb.state == CircuitBreakerState.CLOSED

    def test_half_open_rejects_when_at_max_without_completing(
        self, clock: _FakeClock
    ) -> None:
        """If we have made max calls without recording them, additional should be rejected."""
        config = CircuitBreakerConfig(
            failure_threshold=2, cooldown_seconds=5.0, half_open_max_calls=1
        )
        cb = CircuitBreaker("srv", config, _clock=clock)
        cb.record_failure()
        cb.record_failure()
        clock.advance(5.0)

        # First check transitions to HALF_OPEN (calls=0, max=1)
        assert cb.should_allow() is True
        # Before recording result, should_allow checks calls < max
        # half_open_calls is still 0 (only updated on record_success/record_failure)
        # So should_allow will return True again since _half_open_calls hasn't been bumped
        assert cb.should_allow() is True

        # But recording success or failure bumps the call count
        cb.record_success()
        # Now half_open_calls=1 = max, and successes=1 = max -> CLOSED
        assert cb.state == CircuitBreakerState.CLOSED


# ---------------------------------------------------------------------------
# Concurrent failures and success interleaving
# ---------------------------------------------------------------------------


class TestInterleavedFailuresAndSuccesses:
    """Test that successes in CLOSED state reset the failure counter."""

    def test_interleaved_below_threshold(self, clock: _FakeClock) -> None:
        config = CircuitBreakerConfig(failure_threshold=3, cooldown_seconds=10.0)
        cb = CircuitBreaker("srv", config, _clock=clock)
        cb.record_failure()
        cb.record_failure()
        assert cb.consecutive_failures == 2
        cb.record_success()  # reset
        assert cb.consecutive_failures == 0
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreakerState.CLOSED  # only 2 consecutive
        cb.record_success()
        assert cb.consecutive_failures == 0

    def test_exactly_at_threshold_with_interleaved_success(
        self, clock: _FakeClock
    ) -> None:
        config = CircuitBreakerConfig(failure_threshold=3, cooldown_seconds=10.0)
        cb = CircuitBreaker("srv", config, _clock=clock)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()  # resets to 0
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()  # 3 consecutive -> OPEN
        assert cb.state == CircuitBreakerState.OPEN


# ---------------------------------------------------------------------------
# Record while OPEN (no-op behavior)
# ---------------------------------------------------------------------------


class TestRecordInOpenState:
    """Calling record_success/record_failure while OPEN should be a no-op
    since no calls should be going through.
    """

    def test_record_success_in_open_state_is_noop(self, clock: _FakeClock) -> None:
        config = CircuitBreakerConfig(failure_threshold=1, cooldown_seconds=10.0)
        cb = CircuitBreaker("srv", config, _clock=clock)
        cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN

        state = cb.record_success()
        assert state == CircuitBreakerState.OPEN  # no transition

    def test_record_failure_in_open_state_is_noop(self, clock: _FakeClock) -> None:
        config = CircuitBreakerConfig(failure_threshold=1, cooldown_seconds=10.0)
        cb = CircuitBreaker("srv", config, _clock=clock)
        cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN

        state = cb.record_failure()
        assert state == CircuitBreakerState.OPEN  # no transition


# ---------------------------------------------------------------------------
# Cooldown remaining edge cases
# ---------------------------------------------------------------------------


class TestCooldownRemainingEdgeCases:
    def test_cooldown_remaining_never_negative(self, clock: _FakeClock) -> None:
        config = CircuitBreakerConfig(failure_threshold=1, cooldown_seconds=10.0)
        cb = CircuitBreaker("srv", config, _clock=clock)
        cb.record_failure()
        clock.advance(100.0)  # way past cooldown
        remaining = cb.cooldown_remaining_s
        assert remaining == 0.0

    def test_cooldown_remaining_zero_when_half_open(self, clock: _FakeClock) -> None:
        config = CircuitBreakerConfig(failure_threshold=1, cooldown_seconds=5.0)
        cb = CircuitBreaker("srv", config, _clock=clock)
        cb.record_failure()
        clock.advance(5.0)
        cb.should_allow()  # -> HALF_OPEN
        assert cb.cooldown_remaining_s == 0.0

    def test_cooldown_remaining_zero_when_closed(self, clock: _FakeClock) -> None:
        config = CircuitBreakerConfig(failure_threshold=2, cooldown_seconds=5.0)
        cb = CircuitBreaker("srv", config, _clock=clock)
        # Never opened
        assert cb.cooldown_remaining_s == 0.0


# ---------------------------------------------------------------------------
# Large half_open_max_calls
# ---------------------------------------------------------------------------


class TestLargeHalfOpenMaxCalls:
    def test_requires_many_successes_to_close(self, clock: _FakeClock) -> None:
        config = CircuitBreakerConfig(
            failure_threshold=1, cooldown_seconds=0.0, half_open_max_calls=10
        )
        cb = CircuitBreaker("srv", config, _clock=clock)
        cb.record_failure()  # -> OPEN
        cb.should_allow()  # -> HALF_OPEN

        for _i in range(9):
            cb.record_success()
            assert cb.state == CircuitBreakerState.HALF_OPEN

        cb.record_success()  # 10th
        assert cb.state == CircuitBreakerState.CLOSED

    def test_failure_during_long_half_open_test_reopens(
        self, clock: _FakeClock
    ) -> None:
        config = CircuitBreakerConfig(
            failure_threshold=1, cooldown_seconds=0.0, half_open_max_calls=10
        )
        cb = CircuitBreaker("srv", config, _clock=clock)
        cb.record_failure()  # -> OPEN
        cb.should_allow()  # -> HALF_OPEN

        for _ in range(5):
            cb.record_success()
        assert cb.state == CircuitBreakerState.HALF_OPEN

        cb.record_failure()  # mid-test failure -> OPEN
        assert cb.state == CircuitBreakerState.OPEN
