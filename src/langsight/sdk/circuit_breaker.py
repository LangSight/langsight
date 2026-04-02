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

import asyncio
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


# ---------------------------------------------------------------------------
# Optional Redis-backed state store
# ---------------------------------------------------------------------------


class RedisCircuitBreakerStore:
    """Optional Redis-backed state store for CircuitBreaker.

    Stores per-server state in a Redis HASH so that multiple SDK replicas
    monitoring the same server converge on a shared OPEN/CLOSED/HALF_OPEN
    state, preventing one replica from hammering a broken server while
    another has already opened the breaker.

    Key:  ``langsight:cb:{server_name}`` (HASH)
    TTL:  2× cooldown_seconds — auto-expires if the breaker is never
          triggered again, falling back to the CLOSED default.

    Atomic state transitions use a Lua CAS (compare-and-swap) script to
    prevent race conditions when two replicas call ``record_failure()``
    simultaneously.

    Usage (opt-in — not wired into CircuitBreaker automatically)::

        store = RedisCircuitBreakerStore(redis_client, "my-server", cooldown_seconds=60.0)
        raw = await store.load()         # {'state': 'open', ...} or {}
        await store.save({'state': 'closed', 'consecutive_failures': '0'})
        ok = await store.cas_transition('open', 'half_open')
    """

    # Lua CAS: transition state only if it equals the expected value.
    # Returns 1 on success, 0 if the state didn't match (another replica won).
    _LUA_CAS = """
local current = redis.call('HGET', KEYS[1], 'state')
if current ~= ARGV[1] and current ~= false then
    return 0
end
redis.call('HSET', KEYS[1], 'state', ARGV[2])
for i = 4, #ARGV, 2 do
    redis.call('HSET', KEYS[1], ARGV[i], ARGV[i+1])
end
redis.call('EXPIRE', KEYS[1], ARGV[3])
return 1
"""

    def __init__(
        self,
        redis_client: object,  # redis.asyncio.Redis — typed loosely to avoid import
        server_name: str,
        cooldown_seconds: float,
    ) -> None:
        self._redis = redis_client
        self._key = f"langsight:cb:{server_name}"
        self._ttl = max(int(cooldown_seconds * 2), 1)

    async def load(self) -> dict[str, str]:
        """Load state from Redis. Returns {} if the key does not exist."""
        data: dict[str, str] = await self._redis.hgetall(self._key)  # type: ignore[attr-defined]
        return data

    async def save(self, fields: dict[str, str]) -> None:
        """Write multiple fields atomically and refresh the TTL."""
        await self._redis.hset(self._key, mapping=fields)  # type: ignore[attr-defined]
        await self._redis.expire(self._key, self._ttl)  # type: ignore[attr-defined]

    async def cas_transition(
        self,
        expected_state: str,
        new_state: str,
        extra_fields: dict[str, str] | None = None,
    ) -> bool:
        """Atomically transition state only if it currently equals expected_state.

        Returns True if the transition succeeded, False if another replica
        already changed the state (safe to retry or ignore).
        """
        extra = extra_fields or {}
        argv: list[str] = [expected_state, new_state, str(self._ttl)]
        for k, v in extra.items():
            argv.extend([k, v])
        result: int = await self._redis.eval(  # type: ignore[attr-defined]
            self._LUA_CAS, 1, self._key, *argv
        )
        return bool(result)


# ---------------------------------------------------------------------------
# Async circuit breaker — wraps CircuitBreaker with Redis persistence
# ---------------------------------------------------------------------------


class AsyncCircuitBreaker:
    """CircuitBreaker with Redis-backed state for cross-replica convergence.

    Multiple SDK replicas monitoring the same MCP server share one circuit
    breaker state in Redis.  Worker A opening the breaker for ``postgres-mcp``
    prevents Workers B and C from continuing to hammer it.

    Read path stays in-process (zero Redis round-trip per call).  State is
    loaded from Redis once on first access, then kept in sync via
    fire-and-forget saves after every state change.

    Usage::

        async_cb = AsyncCircuitBreaker("postgres-mcp", config, redis_client)
        if not await async_cb.should_allow():
            raise CircuitBreakerOpenError(...)
        try:
            result = await mcp.call_tool(...)
            await async_cb.record_success()
        except Exception:
            await async_cb.record_failure()
            raise
    """

    def __init__(
        self,
        server_name: str,
        config: CircuitBreakerConfig,
        redis_client: object,
    ) -> None:
        self._cb = CircuitBreaker(server_name, config)
        self._store = RedisCircuitBreakerStore(redis_client, server_name, config.cooldown_seconds)
        self._initialized = False

    async def _ensure_loaded(self) -> None:
        """Load Redis state once on first access — no-op on subsequent calls."""
        if self._initialized:
            return
        self._initialized = True  # set before await so concurrent calls don't double-load
        try:
            data = await self._store.load()
            if not data:
                return  # key absent → CLOSED default is correct
            state_str = data.get("state", CircuitBreakerState.CLOSED.value)
            try:
                self._cb._state = CircuitBreakerState(state_str)
            except ValueError:
                pass  # unknown state value — keep CLOSED
            self._cb._consecutive_failures = int(data.get("consecutive_failures", 0))
            opened_at_str = data.get("opened_at", "")
            if opened_at_str:
                try:
                    self._cb._opened_at = float(opened_at_str)
                except ValueError:
                    pass
        except Exception:  # noqa: BLE001
            pass  # Redis unavailable — in-process CLOSED default is safe

    def _persist(self) -> None:
        """Fire-and-forget: persist current state to Redis after a state change."""
        opened_at = self._cb._opened_at
        fields = {
            "state": self._cb.state.value,
            "consecutive_failures": str(self._cb._consecutive_failures),
            "opened_at": str(opened_at) if opened_at is not None else "",
        }
        try:
            asyncio.ensure_future(self._store.save(fields))
        except RuntimeError:
            pass  # no event loop — state change won't be persisted (acceptable)

    async def should_allow(self) -> bool:
        """Check if a call should proceed. Loads Redis state on first call."""
        await self._ensure_loaded()
        return self._cb.should_allow()

    async def record_success(self) -> None:
        """Record a successful call and persist state change to Redis."""
        await self._ensure_loaded()
        self._cb.record_success()
        self._persist()

    async def record_failure(self) -> None:
        """Record a failed call and persist state change to Redis."""
        await self._ensure_loaded()
        self._cb.record_failure()
        self._persist()

    @property
    def consecutive_failures(self) -> int:
        return self._cb._consecutive_failures

    @property
    def cooldown_remaining_s(self) -> float:
        return self._cb.cooldown_remaining_s

    @property
    def server_name(self) -> str:
        return self._cb.server_name
