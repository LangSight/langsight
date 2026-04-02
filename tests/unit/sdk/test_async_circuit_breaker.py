"""Unit tests for AsyncCircuitBreaker — Redis-backed cross-replica circuit breaker."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from langsight.sdk.circuit_breaker import (
    AsyncCircuitBreaker,
    CircuitBreakerConfig,
)


def _make_redis(hgetall_return: dict | None = None) -> MagicMock:
    """Return a mock redis.asyncio.Redis client."""
    redis = MagicMock()
    redis.hgetall = AsyncMock(return_value=hgetall_return or {})
    redis.hset = AsyncMock(return_value=1)
    redis.expire = AsyncMock(return_value=1)
    redis.eval = AsyncMock(return_value=1)
    return redis


def _make_config(threshold: int = 3, cooldown: float = 60.0) -> CircuitBreakerConfig:
    return CircuitBreakerConfig(
        failure_threshold=threshold,
        cooldown_seconds=cooldown,
        half_open_max_calls=1,
    )


# ---------------------------------------------------------------------------
# Cold-start behaviour
# ---------------------------------------------------------------------------


class TestAsyncCircuitBreakerColdStart:
    @pytest.mark.asyncio
    async def test_should_allow_true_when_redis_empty(self) -> None:
        """No Redis key → CLOSED default → calls are allowed."""
        cb = AsyncCircuitBreaker("srv", _make_config(), _make_redis())
        assert await cb.should_allow() is True

    @pytest.mark.asyncio
    async def test_loads_open_state_from_redis(self) -> None:
        """If Redis says OPEN, should_allow returns False."""
        import time

        redis = _make_redis(
            hgetall_return={
                "state": "open",
                "consecutive_failures": "3",
                "opened_at": str(time.monotonic()),  # just opened — still in cooldown
            }
        )
        cb = AsyncCircuitBreaker("srv", _make_config(cooldown=999.0), redis)
        assert await cb.should_allow() is False

    @pytest.mark.asyncio
    async def test_loads_closed_state_from_redis(self) -> None:
        """Redis CLOSED state → should_allow True."""
        redis = _make_redis(
            hgetall_return={"state": "closed", "consecutive_failures": "0", "opened_at": ""}
        )
        cb = AsyncCircuitBreaker("srv", _make_config(), redis)
        assert await cb.should_allow() is True

    @pytest.mark.asyncio
    async def test_initialized_flag_prevents_double_load(self) -> None:
        """Redis is only queried once even with multiple should_allow() calls."""
        redis = _make_redis()
        cb = AsyncCircuitBreaker("srv", _make_config(), redis)
        await cb.should_allow()
        await cb.should_allow()
        await cb.should_allow()
        assert redis.hgetall.call_count == 1


# ---------------------------------------------------------------------------
# State transitions + persistence
# ---------------------------------------------------------------------------


class TestAsyncCircuitBreakerTransitions:
    @pytest.mark.asyncio
    async def test_record_failure_opens_circuit_at_threshold(self) -> None:
        """N consecutive failures → OPEN, state persisted to Redis."""
        import asyncio

        redis = _make_redis()
        cb = AsyncCircuitBreaker("srv", _make_config(threshold=2), redis)
        await cb.should_allow()  # prime _initialized

        await cb.record_failure()
        assert await cb.should_allow() is True  # 1 failure < threshold

        await cb.record_failure()
        # Now OPEN
        assert await cb.should_allow() is False

        # Drain ensure_future tasks so Redis save coroutines actually run
        await asyncio.sleep(0)
        assert redis.hset.call_count >= 1

    @pytest.mark.asyncio
    async def test_record_success_resets_failures(self) -> None:
        """A successful call on CLOSED circuit resets failure count."""
        redis = _make_redis()
        cb = AsyncCircuitBreaker("srv", _make_config(threshold=3), redis)
        await cb.should_allow()

        await cb.record_failure()
        await cb.record_failure()
        await cb.record_success()  # reset

        # Failure count reset — two more failures should not open
        await cb.record_failure()
        await cb.record_failure()
        assert await cb.should_allow() is True

    @pytest.mark.asyncio
    async def test_persist_called_after_state_change(self) -> None:
        """Every record_failure / record_success fires an async save to Redis."""
        redis = _make_redis()
        cb = AsyncCircuitBreaker("srv", _make_config(threshold=5), redis)
        await cb.should_allow()

        redis.hset.reset_mock()
        await cb.record_failure()
        # ensure_future schedules the coroutine; drive it by awaiting a sleep
        import asyncio

        await asyncio.sleep(0)  # allow scheduled tasks to run
        assert redis.hset.call_count >= 1

    @pytest.mark.asyncio
    async def test_redis_unavailable_falls_back_to_closed(self) -> None:
        """If Redis raises on load, the breaker falls back to CLOSED (fail-open)."""
        redis = MagicMock()
        redis.hgetall = AsyncMock(side_effect=ConnectionError("redis down"))
        redis.hset = AsyncMock(return_value=1)
        redis.expire = AsyncMock(return_value=1)

        cb = AsyncCircuitBreaker("srv", _make_config(), redis)
        # Should not raise — fail-open
        assert await cb.should_allow() is True


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


class TestAsyncCircuitBreakerProperties:
    @pytest.mark.asyncio
    async def test_server_name_property(self) -> None:
        cb = AsyncCircuitBreaker("my-server", _make_config(), _make_redis())
        assert cb.server_name == "my-server"

    @pytest.mark.asyncio
    async def test_consecutive_failures_delegates(self) -> None:
        redis = _make_redis()
        cb = AsyncCircuitBreaker("srv", _make_config(threshold=5), redis)
        await cb.should_allow()
        await cb.record_failure()
        await cb.record_failure()
        assert cb.consecutive_failures == 2

    @pytest.mark.asyncio
    async def test_cooldown_remaining_zero_when_closed(self) -> None:
        cb = AsyncCircuitBreaker("srv", _make_config(), _make_redis())
        assert cb.cooldown_remaining_s == 0.0


# ---------------------------------------------------------------------------
# LangSightClient integration — redis_url wires AsyncCircuitBreaker
# ---------------------------------------------------------------------------


class TestLangSightClientRedisCircuitBreaker:
    def test_no_redis_url_returns_sync_circuit_breaker(self) -> None:
        from langsight.sdk.circuit_breaker import CircuitBreaker
        from langsight.sdk.client import LangSightClient

        client = LangSightClient(
            url="http://test:8000",
            circuit_breaker=True,
        )
        cb = client._get_circuit_breaker("srv")
        assert isinstance(cb, CircuitBreaker)
        assert not isinstance(cb, AsyncCircuitBreaker)

    def test_with_redis_url_and_available_redis_returns_async_circuit_breaker(self) -> None:
        from langsight.sdk.client import LangSightClient

        with patch("redis.asyncio.from_url", return_value=MagicMock()):
            client = LangSightClient(
                url="http://test:8000",
                circuit_breaker=True,
                redis_url="redis://localhost:6379",
            )
            cb = client._get_circuit_breaker("srv")
            assert isinstance(cb, AsyncCircuitBreaker)

    def test_with_redis_url_but_import_fails_falls_back_to_sync(self) -> None:
        """If redis package not installed, fall back silently to in-process CB."""
        from langsight.sdk.circuit_breaker import CircuitBreaker
        from langsight.sdk.client import LangSightClient

        with patch.dict("sys.modules", {"redis": None, "redis.asyncio": None}):
            client = LangSightClient(
                url="http://test:8000",
                circuit_breaker=True,
                redis_url="redis://localhost:6379",
            )
            # Force re-creation — clear cached client
            client._redis_client = None
            cb = client._get_circuit_breaker("srv")
            # Falls back to sync CircuitBreaker
            assert isinstance(cb, CircuitBreaker)
