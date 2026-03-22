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


@pytest.fixture
def config() -> CircuitBreakerConfig:
    return CircuitBreakerConfig(
        failure_threshold=3,
        cooldown_seconds=10.0,
        half_open_max_calls=2,
    )


@pytest.fixture
def cb(config: CircuitBreakerConfig, clock: _FakeClock) -> CircuitBreaker:
    return CircuitBreaker("test-server", config, _clock=clock)


class TestInitialState:
    def test_starts_closed(self, cb: CircuitBreaker) -> None:
        assert cb.state == CircuitBreakerState.CLOSED

    def test_allows_calls_when_closed(self, cb: CircuitBreaker) -> None:
        assert cb.should_allow() is True

    def test_zero_cooldown_when_closed(self, cb: CircuitBreaker) -> None:
        assert cb.cooldown_remaining_s == 0.0

    def test_server_name(self, cb: CircuitBreaker) -> None:
        assert cb.server_name == "test-server"

    def test_zero_consecutive_failures(self, cb: CircuitBreaker) -> None:
        assert cb.consecutive_failures == 0


class TestClosedToOpen:
    def test_below_threshold_stays_closed(self, cb: CircuitBreaker) -> None:
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.should_allow() is True

    def test_threshold_reached_opens_circuit(self, cb: CircuitBreaker) -> None:
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN

    def test_open_rejects_calls(self, cb: CircuitBreaker) -> None:
        for _ in range(3):
            cb.record_failure()
        assert cb.should_allow() is False

    def test_cooldown_remaining(
        self, cb: CircuitBreaker, clock: _FakeClock
    ) -> None:
        for _ in range(3):
            cb.record_failure()
        assert cb.cooldown_remaining_s == pytest.approx(10.0, abs=0.1)
        clock.advance(4.0)
        assert cb.cooldown_remaining_s == pytest.approx(6.0, abs=0.1)

    def test_success_resets_failure_count(self, cb: CircuitBreaker) -> None:
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.consecutive_failures == 0
        assert cb.state == CircuitBreakerState.CLOSED


class TestOpenToHalfOpen:
    def test_stays_open_before_cooldown(
        self, cb: CircuitBreaker, clock: _FakeClock
    ) -> None:
        for _ in range(3):
            cb.record_failure()
        clock.advance(5.0)
        assert cb.should_allow() is False

    def test_transitions_to_half_open_after_cooldown(
        self, cb: CircuitBreaker, clock: _FakeClock
    ) -> None:
        for _ in range(3):
            cb.record_failure()
        clock.advance(10.0)
        assert cb.should_allow() is True
        assert cb.state == CircuitBreakerState.HALF_OPEN


class TestHalfOpenToClosed:
    def _open_then_half_open(
        self, cb: CircuitBreaker, clock: _FakeClock
    ) -> None:
        for _ in range(3):
            cb.record_failure()
        clock.advance(10.0)
        cb.should_allow()  # triggers HALF_OPEN

    def test_all_successes_close_circuit(
        self, cb: CircuitBreaker, clock: _FakeClock
    ) -> None:
        self._open_then_half_open(cb, clock)
        cb.record_success()
        assert cb.state == CircuitBreakerState.HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitBreakerState.CLOSED

    def test_closed_allows_calls(
        self, cb: CircuitBreaker, clock: _FakeClock
    ) -> None:
        self._open_then_half_open(cb, clock)
        cb.record_success()
        cb.record_success()
        assert cb.should_allow() is True


class TestHalfOpenToOpen:
    def _open_then_half_open(
        self, cb: CircuitBreaker, clock: _FakeClock
    ) -> None:
        for _ in range(3):
            cb.record_failure()
        clock.advance(10.0)
        cb.should_allow()

    def test_failure_reopens_circuit(
        self, cb: CircuitBreaker, clock: _FakeClock
    ) -> None:
        self._open_then_half_open(cb, clock)
        cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN

    def test_reopened_has_fresh_cooldown(
        self, cb: CircuitBreaker, clock: _FakeClock
    ) -> None:
        self._open_then_half_open(cb, clock)
        cb.record_failure()
        assert cb.cooldown_remaining_s == pytest.approx(10.0, abs=0.1)

    def test_half_open_limits_calls(
        self, cb: CircuitBreaker, clock: _FakeClock
    ) -> None:
        self._open_then_half_open(cb, clock)
        assert cb.should_allow() is True
        cb.record_success()
        assert cb.should_allow() is True
        # After 2 calls (half_open_max_calls=2), and only 1 success recorded,
        # the 2nd call is still allowed since we track calls separately


class TestRecordReturnValues:
    def test_record_success_returns_state(self, cb: CircuitBreaker) -> None:
        state = cb.record_success()
        assert state == CircuitBreakerState.CLOSED

    def test_record_failure_returns_state(self, cb: CircuitBreaker) -> None:
        state = cb.record_failure()
        assert state == CircuitBreakerState.CLOSED
        state = cb.record_failure()
        assert state == CircuitBreakerState.CLOSED
        state = cb.record_failure()
        assert state == CircuitBreakerState.OPEN
