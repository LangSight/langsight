"""
Unit tests for RedisCircuitBreakerStore in langsight.sdk.circuit_breaker.

Covers:
  - Key format: langsight:cb:{server_name}
  - TTL calculation: 2× cooldown_seconds
  - load(): returns dict from hgetall, empty dict when key missing
  - save(): calls hset + expire, refreshes TTL on each call
  - cas_transition(): returns True on success (eval→1), False on conflict (eval→0)
  - cas_transition(): passes extra_fields as ARGV pairs to the Lua script
  - cas_transition(): ARGV ordering matches the _LUA_CAS script expectations

All tests use AsyncMock — no real Redis required.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from langsight.sdk.circuit_breaker import RedisCircuitBreakerStore

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_redis() -> AsyncMock:
    """Return a mock Redis client with all methods needed by RedisCircuitBreakerStore."""
    redis = AsyncMock()
    redis.hgetall = AsyncMock(return_value={})
    redis.hset = AsyncMock(return_value=1)
    redis.expire = AsyncMock(return_value=1)
    redis.eval = AsyncMock(return_value=1)
    return redis


@pytest.fixture
def store(mock_redis: AsyncMock) -> RedisCircuitBreakerStore:
    return RedisCircuitBreakerStore(mock_redis, "test-server", cooldown_seconds=60.0)


# ===========================================================================
# Key format and TTL
# ===========================================================================


class TestRedisCircuitBreakerStoreInit:
    def test_key_format(self, store: RedisCircuitBreakerStore) -> None:
        """Redis key must follow the pattern langsight:cb:{server_name}."""
        assert store._key == "langsight:cb:test-server"

    def test_key_uses_provided_server_name(self) -> None:
        """Different server names produce different keys."""
        redis = AsyncMock()
        store_a = RedisCircuitBreakerStore(redis, "server-alpha", cooldown_seconds=30.0)
        store_b = RedisCircuitBreakerStore(redis, "server-beta", cooldown_seconds=30.0)
        assert store_a._key == "langsight:cb:server-alpha"
        assert store_b._key == "langsight:cb:server-beta"

    def test_ttl_is_2x_cooldown(self, store: RedisCircuitBreakerStore) -> None:
        """TTL must be exactly 2 × cooldown_seconds."""
        assert store._ttl == 120  # 60.0 * 2 = 120

    def test_ttl_rounds_down_to_int(self) -> None:
        """TTL is stored as int (truncated, not rounded)."""
        redis = AsyncMock()
        store = RedisCircuitBreakerStore(redis, "srv", cooldown_seconds=45.9)
        # int(45.9 * 2) = int(91.8) = 91
        assert store._ttl == 91

    def test_ttl_minimum_is_1(self) -> None:
        """Very short cooldowns must not produce a zero or negative TTL."""
        redis = AsyncMock()
        store = RedisCircuitBreakerStore(redis, "srv", cooldown_seconds=0.1)
        assert store._ttl >= 1


# ===========================================================================
# load()
# ===========================================================================


class TestRedisCircuitBreakerStoreLoad:
    @pytest.mark.asyncio
    async def test_load_returns_dict_from_hgetall(
        self, store: RedisCircuitBreakerStore, mock_redis: AsyncMock
    ) -> None:
        """load() must return whatever hgetall returns."""
        mock_redis.hgetall.return_value = {"state": "open", "consecutive_failures": "5"}

        result = await store.load()

        assert result == {"state": "open", "consecutive_failures": "5"}

    @pytest.mark.asyncio
    async def test_load_calls_hgetall_with_correct_key(
        self, store: RedisCircuitBreakerStore, mock_redis: AsyncMock
    ) -> None:
        """hgetall must be called with the store's key."""
        await store.load()

        mock_redis.hgetall.assert_awaited_once_with("langsight:cb:test-server")

    @pytest.mark.asyncio
    async def test_load_returns_empty_dict_when_key_missing(
        self, store: RedisCircuitBreakerStore, mock_redis: AsyncMock
    ) -> None:
        """When the Redis key does not exist, hgetall returns {} — load() must propagate it."""
        mock_redis.hgetall.return_value = {}

        result = await store.load()

        assert result == {}

    @pytest.mark.asyncio
    async def test_load_preserves_all_fields(
        self, store: RedisCircuitBreakerStore, mock_redis: AsyncMock
    ) -> None:
        """All hash fields returned by hgetall are included in the result."""
        fields = {
            "state": "half_open",
            "consecutive_failures": "3",
            "opened_at": "1234567.89",
        }
        mock_redis.hgetall.return_value = fields

        result = await store.load()

        assert result == fields


# ===========================================================================
# save()
# ===========================================================================


class TestRedisCircuitBreakerStoreSave:
    @pytest.mark.asyncio
    async def test_save_calls_hset_with_correct_key_and_mapping(
        self, store: RedisCircuitBreakerStore, mock_redis: AsyncMock
    ) -> None:
        """save() must call hset with mapping=fields."""
        fields = {"state": "closed", "consecutive_failures": "0"}

        await store.save(fields)

        mock_redis.hset.assert_awaited_once_with(
            "langsight:cb:test-server", mapping=fields
        )

    @pytest.mark.asyncio
    async def test_save_calls_expire_with_correct_ttl(
        self, store: RedisCircuitBreakerStore, mock_redis: AsyncMock
    ) -> None:
        """save() must refresh the TTL by calling expire with _ttl."""
        await store.save({"state": "closed"})

        mock_redis.expire.assert_awaited_once_with("langsight:cb:test-server", 120)

    @pytest.mark.asyncio
    async def test_save_calls_hset_before_expire(
        self, store: RedisCircuitBreakerStore, mock_redis: AsyncMock
    ) -> None:
        """hset must be called before expire (write data first, then set TTL)."""
        call_order: list[str] = []
        mock_redis.hset.side_effect = lambda *a, **kw: call_order.append("hset")
        mock_redis.expire.side_effect = lambda *a, **kw: call_order.append("expire")

        await store.save({"state": "open"})

        assert call_order == ["hset", "expire"]

    @pytest.mark.asyncio
    async def test_save_refreshes_ttl_each_call(
        self, store: RedisCircuitBreakerStore, mock_redis: AsyncMock
    ) -> None:
        """Calling save() twice must call expire twice (TTL refreshed each time)."""
        await store.save({"state": "open"})
        await store.save({"state": "closed"})

        assert mock_redis.expire.await_count == 2


# ===========================================================================
# cas_transition()
# ===========================================================================


class TestRedisCircuitBreakerStoreCasTransition:
    @pytest.mark.asyncio
    async def test_cas_transition_returns_true_on_success(
        self, store: RedisCircuitBreakerStore, mock_redis: AsyncMock
    ) -> None:
        """When eval returns 1, the transition succeeded — return True."""
        mock_redis.eval.return_value = 1

        result = await store.cas_transition("open", "half_open")

        assert result is True

    @pytest.mark.asyncio
    async def test_cas_transition_returns_false_on_conflict(
        self, store: RedisCircuitBreakerStore, mock_redis: AsyncMock
    ) -> None:
        """When eval returns 0, another replica already changed the state — return False."""
        mock_redis.eval.return_value = 0

        result = await store.cas_transition("open", "half_open")

        assert result is False

    @pytest.mark.asyncio
    async def test_cas_transition_calls_eval_with_correct_key(
        self, store: RedisCircuitBreakerStore, mock_redis: AsyncMock
    ) -> None:
        """eval must be called with numkeys=1 and KEYS[1] = store._key."""
        await store.cas_transition("closed", "open")

        call_args = mock_redis.eval.await_args
        # Positional: (script, numkeys, key, *argv)
        assert call_args.args[1] == 1  # numkeys
        assert call_args.args[2] == "langsight:cb:test-server"  # KEYS[1]

    @pytest.mark.asyncio
    async def test_cas_transition_argv_contains_expected_state_new_state_ttl(
        self, store: RedisCircuitBreakerStore, mock_redis: AsyncMock
    ) -> None:
        """ARGV must start with [expected_state, new_state, str(ttl)]."""
        await store.cas_transition("open", "half_open")

        call_args = mock_redis.eval.await_args
        # args: (script, numkeys, key, argv[0], argv[1], argv[2], ...)
        argv = list(call_args.args[3:])

        assert argv[0] == "open"          # ARGV[1] in Lua
        assert argv[1] == "half_open"     # ARGV[2] in Lua
        assert argv[2] == str(store._ttl)  # ARGV[3] in Lua

    @pytest.mark.asyncio
    async def test_cas_transition_passes_extra_fields_as_argv_pairs(
        self, store: RedisCircuitBreakerStore, mock_redis: AsyncMock
    ) -> None:
        """extra_fields are appended to ARGV as key-value pairs after the base args."""
        extra = {"consecutive_failures": "3", "opened_at": "1234567.0"}

        await store.cas_transition("closed", "open", extra_fields=extra)

        call_args = mock_redis.eval.await_args
        argv = list(call_args.args[3:])

        # Base: [expected, new, ttl] = argv[0:3]
        # Extra pairs start at argv[3]
        extra_argv = argv[3:]
        # Should be pairs of (key, value)
        assert len(extra_argv) == len(extra) * 2
        for key in extra:
            assert key in extra_argv
            idx = extra_argv.index(key)
            assert extra_argv[idx + 1] == extra[key]

    @pytest.mark.asyncio
    async def test_cas_transition_no_extra_fields_argv_has_exactly_3_elements(
        self, store: RedisCircuitBreakerStore, mock_redis: AsyncMock
    ) -> None:
        """Without extra_fields, ARGV must have exactly 3 elements."""
        await store.cas_transition("closed", "open")

        call_args = mock_redis.eval.await_args
        argv = list(call_args.args[3:])
        assert len(argv) == 3

    @pytest.mark.asyncio
    async def test_cas_transition_with_none_extra_fields_behaves_same_as_empty(
        self, store: RedisCircuitBreakerStore, mock_redis: AsyncMock
    ) -> None:
        """cas_transition(extra_fields=None) must produce the same ARGV as extra_fields={}."""
        await store.cas_transition("open", "closed", extra_fields=None)

        call_args = mock_redis.eval.await_args
        argv = list(call_args.args[3:])
        assert len(argv) == 3

    @pytest.mark.asyncio
    async def test_cas_transition_uses_lua_script_containing_hget(
        self, store: RedisCircuitBreakerStore, mock_redis: AsyncMock
    ) -> None:
        """The Lua script passed to eval must contain the CAS logic (HGET + HSET)."""
        await store.cas_transition("open", "half_open")

        call_args = mock_redis.eval.await_args
        script: str = call_args.args[0]
        assert "HGET" in script
        assert "HSET" in script
        assert "EXPIRE" in script
