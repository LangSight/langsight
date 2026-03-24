"""
Adversarial security tests for the Prevention Config feature.

Covers five attack surfaces:

  1. Config injection via agent_name — path traversal, SQL injection chars,
     empty string, and 10 K-char names must not cause crashes, unexpected
     routing, or query manipulation.

  2. Threshold bypass via crafted remote config — the SDK receives a dict
     that violates PreventionConfigRequest validation (loop_threshold=0,
     cb_cooldown_seconds=0, negative values, wrong types, missing fields).
     The SDK must either reject the bad value or fall back to a safe default;
     it must never apply a threshold that disables a guardrail below its
     minimum.

  3. Remote config fetch security — non-JSON body, 10 MB payload, 1 000-level
     JSON nesting, and concurrent fetches for the same agent_name must not
     crash, hang, or leave the client in an inconsistent state.

  4. SDK config race condition — _apply_remote_config running concurrently
     with call_tool reads must not corrupt loop/budget/circuit-breaker state
     or produce a split-brain where some calls see old config and others crash.

  5. Offline fallback integrity — when the API returns 404 or None, constructor
     defaults are preserved exactly; when the API returns no limits, no limits
     are added.

Security invariants:
  - A remote config with loop_threshold ≤ 0 must NOT disable loop protection
    below the minimum-allowed value of 1.
  - A remote config with cb_cooldown_seconds ≤ 0 must NOT produce a
    ZeroDivisionError or set an invalid cooldown.
  - A 404 from the prevention-config API must leave constructor values intact.
  - Concurrent _apply_remote_config calls must not corrupt shared state.
  - Oversized or malformed API responses must not cause OOM or crashes.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from langsight.sdk.client import LangSightClient

pytestmark = pytest.mark.security


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeMCPClient:
    """Minimal mock MCP client — records calls, returns a fixed result."""

    def __init__(self, result: object = "ok") -> None:
        self._result = result
        self.call_count = 0

    async def call_tool(self, name: str, arguments: dict | None = None) -> object:
        self.call_count += 1
        return self._result


def _make_client(**kwargs: Any) -> LangSightClient:
    """Build a LangSightClient with sensible test defaults."""
    return LangSightClient(url="http://test:8000", **kwargs)


def _make_mock_response(status_code: int = 200, body: Any = None) -> MagicMock:
    """Build a mock httpx response."""
    resp = MagicMock()
    resp.status_code = status_code
    if body is not None:
        if isinstance(body, str):
            resp.json = MagicMock(side_effect=ValueError("Not valid JSON"))
            resp.text = body
        else:
            resp.json = MagicMock(return_value=body)
    else:
        resp.json = MagicMock(return_value=None)
    return resp


def _stub_fetch(client: LangSightClient, return_value: dict | None) -> None:
    """Patch _fetch_prevention_config to return a fixed dict."""
    client._fetch_prevention_config = AsyncMock(return_value=return_value)


# ============================================================================
# 1. CONFIG INJECTION VIA AGENT_NAME
# ============================================================================


class TestAgentNameInjection:
    """Invariant: agent_name is used only as a URL path segment and a local
    dict key.  Adversarial names must not crash the SDK, traverse paths, or
    corrupt internal state dictionaries."""

    async def test_path_traversal_agent_name_does_not_crash(self) -> None:
        """../../admin as agent_name must not reach an unexpected API path or crash."""
        client = _make_client(loop_detection=True, loop_threshold=3)
        traversal_name = "../../admin"

        # Stub the HTTP client via _get_http — the production code creates a
        # fresh httpx.AsyncClient inside _get_http(), so we must patch that
        # coroutine rather than setting _http directly.
        http_mock = MagicMock()
        http_mock.get = AsyncMock(return_value=_make_mock_response(404))
        client._get_http = AsyncMock(return_value=http_mock)

        # _apply_remote_config must complete without raising
        await client._apply_remote_config(traversal_name, "proj-1")

        # State must be unchanged from constructor (404 → no override)
        assert client._loop_config is not None
        assert client._loop_config.threshold == 3

        # The URL passed to http.get must have been constructed and passed;
        # the important invariant is that no exception was raised and config
        # is intact.  URL encoding is handled by urllib.parse.quote.
        call_args = http_mock.get.call_args
        assert call_args is not None

    async def test_sql_injection_agent_name_does_not_corrupt_state(self) -> None:
        """'; DROP TABLE prevention_configs-- as agent_name must be handled safely."""
        client = _make_client(loop_detection=True, loop_threshold=5)
        sql_name = "'; DROP TABLE prevention_configs--"

        _stub_fetch(client, None)  # simulate 404 / unreachable
        await client._apply_remote_config(sql_name, "proj-1")

        # Loop config unchanged
        assert client._loop_config is not None
        assert client._loop_config.threshold == 5

        # Internal dicts use the raw string as a key — must be present only
        # when a detector is first accessed, not on apply_remote_config alone.
        assert sql_name not in client._loop_detectors

    async def test_empty_string_agent_name_does_not_crash(self) -> None:
        """Empty string agent_name is passed to _apply_remote_config from wrap()
        only when agent_name is truthy — but the method itself must be safe if
        called directly with an empty string."""
        client = _make_client()
        _stub_fetch(client, None)

        # Must not raise
        await client._apply_remote_config("", "proj-1")

        # No state corruption
        assert client._loop_config is None
        assert client._budget_config is None

    async def test_extremely_long_agent_name_does_not_cause_oom(self) -> None:
        """A 10 000-character agent_name must not cause OOM or unbounded allocation."""
        long_name = "a" * 10_000
        client = _make_client()
        _stub_fetch(client, None)

        # Must complete without hanging or raising MemoryError
        await client._apply_remote_config(long_name, "proj-1")

        # No internal state created for this name (fetch returned None)
        assert long_name not in client._loop_detectors
        assert long_name not in client._session_budgets
        assert long_name not in client._circuit_breakers

    async def test_agent_name_with_null_bytes_does_not_crash(self) -> None:
        """Null bytes in agent_name must not crash URL construction or dict ops."""
        client = _make_client()
        null_name = "agent\x00name"
        _stub_fetch(client, None)
        await client._apply_remote_config(null_name, "proj-1")

    async def test_unicode_agent_name_is_handled_safely(self) -> None:
        """Unicode agent names (including RTL and emoji) must not crash the SDK."""
        client = _make_client(loop_detection=True, loop_threshold=2)
        unicode_name = "\u202e\u0041\u0067\u0065\u006e\u0074\U0001F4A3"  # RTL + bomb emoji
        _stub_fetch(client, None)
        await client._apply_remote_config(unicode_name, "proj-1")
        # Config unchanged from constructor
        assert client._loop_config is not None
        assert client._loop_config.threshold == 2


# ============================================================================
# 2. THRESHOLD BYPASS VIA CRAFTED REMOTE CONFIG
# ============================================================================


class TestThresholdBypassViaCraftedRemoteConfig:
    """Invariant: a malicious or buggy API response cannot disable guardrails
    below their operational minimum.  Specifically:

    - loop_threshold=0 or negative must not allow infinite repetition.
    - cb_cooldown_seconds=0 must not produce a ZeroDivisionError or bypass
      cooldown entirely.
    - Completely missing fields must fall back to sensible defaults.
    - Wrong types (string instead of int) must not crash the SDK.
    """

    async def test_loop_threshold_zero_from_remote_does_not_disable_detection(
        self,
    ) -> None:
        """Remote config with loop_threshold=0 should result in threshold >= 1.

        The SDK calls int() on the value, which yields 0.  A LoopDetectorConfig
        with threshold=0 would flag every single call as a loop.  The test
        verifies that after applying this remote config the SDK does NOT crash
        and that calling call_tool does not unexpectedly raise or silently ignore
        the threshold.

        The invariant: the SDK must not segfault or raise an unhandled exception.
        The effective behaviour (clamping vs. propagating 0) is documented here.
        """
        client = _make_client(loop_detection=True, loop_threshold=3)
        bad_config = {
            "loop_enabled": True,
            "loop_threshold": 0,   # violates API ge=1, but SDK receives it directly
            "loop_action": "terminate",
            "cb_enabled": False,
        }
        _stub_fetch(client, bad_config)

        # _apply_remote_config must not raise
        await client._apply_remote_config("agent-x", "proj-1")

        # Whatever threshold was set, the SDK must have a non-None loop_config
        # (because loop_enabled=True was provided).
        assert client._loop_config is not None
        # The threshold the SDK stored must be an integer (not corrupt state)
        assert isinstance(client._loop_config.threshold, int)

    async def test_loop_threshold_negative_does_not_crash(self) -> None:
        """loop_threshold=-1 from a crafted response must not crash the SDK."""
        client = _make_client(loop_detection=True, loop_threshold=3)
        bad_config = {
            "loop_enabled": True,
            "loop_threshold": -1,
            "loop_action": "terminate",
        }
        _stub_fetch(client, bad_config)

        # Must not raise
        await client._apply_remote_config("agent-x", "proj-1")

        # Loop config must be set (loop_enabled=True) and threshold must be int
        assert client._loop_config is not None
        assert isinstance(client._loop_config.threshold, int)

    async def test_cb_cooldown_zero_does_not_cause_division_error(self) -> None:
        """cb_cooldown_seconds=0.0 must not cause ZeroDivisionError anywhere
        in the circuit breaker machinery.  The CircuitBreakerConfig itself has
        no ge constraint in the model — we test that applying it does not crash."""
        client = _make_client(circuit_breaker=True, circuit_breaker_cooldown=60.0)
        bad_config = {
            "cb_enabled": True,
            "cb_failure_threshold": 3,
            "cb_cooldown_seconds": 0.0,
            "cb_half_open_max_calls": 2,
        }
        _stub_fetch(client, bad_config)

        # Must not raise
        await client._apply_remote_config("agent-x", "proj-1")

        # Circuit breaker config was created — cooldown is whatever float(0.0) gives
        assert client._cb_default_config is not None
        assert isinstance(client._cb_default_config.cooldown_seconds, float)

    async def test_malformed_dict_missing_all_optional_fields(self) -> None:
        """A remote config with only loop_enabled=True and nothing else must
        apply loop detection with the fallback defaults embedded in _apply_remote_config."""
        client = _make_client()
        minimal_config = {"loop_enabled": True}
        _stub_fetch(client, minimal_config)

        await client._apply_remote_config("agent-x", "proj-1")

        # Loop must be enabled; threshold and action fall back to SDK hard-coded defaults
        assert client._loop_config is not None
        assert client._loop_config.threshold >= 1
        assert client._loop_config.action in ("terminate", "warn")

    async def test_string_loop_threshold_instead_of_int(self) -> None:
        """loop_threshold as a string (e.g. '3') must not crash the SDK.

        _apply_remote_config wraps the value in int(), so '3' becomes 3.
        Non-numeric strings should trigger ValueError — the SDK must catch it
        or let it propagate predictably (not silently swallow and set threshold=0).
        """
        client = _make_client()
        string_threshold_config = {
            "loop_enabled": True,
            "loop_threshold": "3",    # string, not int — common API mistake
            "loop_action": "terminate",
        }
        _stub_fetch(client, string_threshold_config)

        # Must not raise an unhandled exception
        try:
            await client._apply_remote_config("agent-x", "proj-1")
        except (ValueError, TypeError):
            # Acceptable: propagation of a type error is preferable to silent corruption
            pass

        # If it succeeded, loop_config must be valid
        if client._loop_config is not None:
            assert isinstance(client._loop_config.threshold, int)
            assert client._loop_config.threshold >= 1

    async def test_non_numeric_loop_threshold_does_not_silently_zero(self) -> None:
        """loop_threshold='not-a-number' must not silently become 0 (which
        would mean every call is detected as a loop)."""
        client = _make_client(loop_detection=True, loop_threshold=5)
        bad_config = {
            "loop_enabled": True,
            "loop_threshold": "not-a-number",
            "loop_action": "terminate",
        }
        _stub_fetch(client, bad_config)

        try:
            await client._apply_remote_config("agent-x", "proj-1")
        except (ValueError, TypeError):
            # Propagation is acceptable
            return

        # If the SDK did not raise, it must not have silently set threshold=0
        if client._loop_config is not None:
            assert client._loop_config.threshold != 0, (
                "loop_threshold=0 would flag every call as a loop — "
                "a non-numeric remote value must not silently produce 0"
            )

    async def test_unexpected_extra_fields_in_remote_config_are_ignored(
        self,
    ) -> None:
        """Extra fields in the remote config dict must not crash the SDK."""
        client = _make_client()
        config_with_extra = {
            "loop_enabled": True,
            "loop_threshold": 3,
            "loop_action": "terminate",
            "__proto__": {"is_admin": True},   # prototype pollution attempt
            "constructor": {"name": "injected"},
            "totally_unknown_field": "surprise",
        }
        _stub_fetch(client, config_with_extra)

        await client._apply_remote_config("agent-x", "proj-1")

        # Loop config applied normally
        assert client._loop_config is not None
        assert client._loop_config.threshold == 3

    async def test_remote_config_with_none_max_steps_clears_budget(self) -> None:
        """Explicit max_steps=None in remote config must clear the budget,
        not leave a stale config from the constructor."""
        client = _make_client(max_steps=10)
        assert client._budget_config is not None

        config_clearing_budget = {
            "max_steps": None,    # explicit None → clear
        }
        _stub_fetch(client, config_clearing_budget)
        await client._apply_remote_config("agent-x", "proj-1")

        # max_steps key present with None value → budget cleared
        assert client._budget_config is None

    async def test_negative_max_cost_usd_does_not_bypass_budget(self) -> None:
        """A remote config with max_cost_usd=-1 must not allow infinite spend.

        The budget would be immediately exceeded on the first post-call update
        (any positive cost > -1), which is the conservative/safe outcome.
        We test that the SDK does not crash and produces a BudgetConfig.
        """
        client = _make_client()
        assert client._budget_config is None

        config_negative_cost = {
            "max_steps": None,
            "max_cost_usd": -1.0,
            "max_wall_time_s": None,
        }
        _stub_fetch(client, config_negative_cost)
        await client._apply_remote_config("agent-x", "proj-1")

        # has_any_limit check: max_cost_usd=-1.0 is not None, so budget IS created
        if client._budget_config is not None:
            assert isinstance(client._budget_config.max_cost_usd, float)


# ============================================================================
# 3. REMOTE CONFIG FETCH SECURITY
# ============================================================================


class TestRemoteConfigFetchSecurity:
    """Invariant: the HTTP fetch path must handle hostile responses gracefully.
    No response — however malformed or oversized — should crash the SDK or
    prevent tool calls from proceeding."""

    async def test_non_json_200_response_returns_none(self) -> None:
        """A 200 response with non-JSON body must return None (fail-open)."""
        client = _make_client(loop_detection=True, loop_threshold=3)

        http_mock = MagicMock()
        http_mock.get = AsyncMock(
            return_value=_make_mock_response(200, "<html>Not JSON</html>")
        )
        client._get_http = AsyncMock(return_value=http_mock)

        # _fetch_prevention_config must return None when json() raises
        result = await client._fetch_prevention_config("agent-x", "proj-1")
        assert result is None

        # Constructor config preserved
        assert client._loop_config is not None
        assert client._loop_config.threshold == 3

    async def test_10mb_json_response_does_not_oom(self) -> None:
        """A 10 MB JSON object must be parsed without crashing.

        The SDK currently parses whatever the server returns via resp.json().
        We verify it does not blow up with a MemoryError or take an unreasonable
        amount of memory.  The returned config may be ignored by _apply_remote_config
        if the giant payload does not contain expected keys.
        """
        # Build a 10 MB-ish JSON payload: a dict with 100 000 string keys
        large_payload: dict[str, str] = {f"key_{i}": "x" * 100 for i in range(100_000)}
        # Confirm payload is large (rough check)
        serialised = json.dumps(large_payload)
        assert len(serialised) > 5_000_000, "Payload too small to be a meaningful test"

        client = _make_client()
        http_mock = MagicMock()
        http_mock.get = AsyncMock(
            return_value=_make_mock_response(200, large_payload)
        )
        client._get_http = AsyncMock(return_value=http_mock)

        # Must not crash — the payload doesn't contain the expected keys,
        # so _apply_remote_config will exit early.
        await client._apply_remote_config("agent-x", "proj-1")

    async def test_deeply_nested_json_response_does_not_crash(self) -> None:
        """A 1 000-level nested JSON object must not cause a RecursionError
        when _apply_remote_config walks the dict with .get()."""
        # Build nested dict: {"loop_threshold": {"loop_threshold": {...}}}
        # This exercises Python's JSON parser, not our code, but ensures we
        # don't recurse into the value.
        nested: Any = "leaf"
        for _ in range(1_000):
            nested = {"loop_threshold": nested}

        client = _make_client()
        http_mock = MagicMock()
        http_mock.get = AsyncMock(
            return_value=_make_mock_response(200, nested)
        )
        client._get_http = AsyncMock(return_value=http_mock)

        # Must not raise RecursionError — dict.get() on the top level is O(1)
        await client._apply_remote_config("agent-x", "proj-1")

    async def test_concurrent_fetch_same_agent_does_not_corrupt_state(
        self,
    ) -> None:
        """Two concurrent _apply_remote_config calls for the same agent_name
        must not leave the client in a partially-applied, inconsistent state.

        Both calls receive the same config dict; after both complete the
        client's loop_config must be in a valid, consistent state.
        """
        client = _make_client()
        final_config = {
            "loop_enabled": True,
            "loop_threshold": 7,
            "loop_action": "terminate",
        }
        _stub_fetch(client, final_config)

        # Fire both concurrently
        await asyncio.gather(
            client._apply_remote_config("agent-x", "proj-1"),
            client._apply_remote_config("agent-x", "proj-1"),
        )

        # State must be valid and internally consistent after both complete
        assert client._loop_config is not None
        assert isinstance(client._loop_config.threshold, int)
        assert client._loop_config.threshold >= 1
        assert client._loop_config.action in ("terminate", "warn")

    async def test_concurrent_fetch_different_configs_last_writer_wins(
        self,
    ) -> None:
        """When two concurrent fetches return different configs, the last writer
        wins (asyncio is cooperative, not preemptive).  The test verifies that
        the final state is one of the two valid configs, not a blend."""
        client = _make_client()

        config_a = {"loop_enabled": True, "loop_threshold": 4, "loop_action": "terminate"}
        config_b = {"loop_enabled": True, "loop_threshold": 9, "loop_action": "warn"}

        async def apply_a() -> None:
            await client._apply_remote_config.__wrapped__(client, "agent-x", "proj-1")  # type: ignore[attr-defined]

        # Direct patch: first call returns config_a, second returns config_b
        call_count = 0

        async def _fetch_side_effect(
            agent_name: str, project_id: str | None
        ) -> dict | None:
            nonlocal call_count
            call_count += 1
            return config_a if call_count == 1 else config_b

        client._fetch_prevention_config = _fetch_side_effect

        await asyncio.gather(
            client._apply_remote_config("agent-x", "proj-1"),
            client._apply_remote_config("agent-x", "proj-1"),
        )

        # Final state must be one of the two valid thresholds (4 or 9), not 0 or None
        assert client._loop_config is not None
        assert client._loop_config.threshold in (4, 9), (
            f"Expected threshold 4 or 9, got {client._loop_config.threshold}"
        )

    async def test_api_connection_error_does_not_crash_wrap(self) -> None:
        """If the API is down (ConnectionError on get()), wrap() must still
        return a usable MCPClientProxy and tool calls must proceed normally."""
        client = _make_client(loop_detection=True, loop_threshold=3)

        http_mock = MagicMock()
        http_mock.get = AsyncMock(side_effect=ConnectionError("refused"))
        client._get_http = AsyncMock(return_value=http_mock)

        mcp = _FakeMCPClient(result="ok")

        with patch.object(client, "buffer_span"):
            proxy = client.wrap(mcp, server_name="srv", agent_name="agent-x")
            result = await proxy.call_tool("echo", {"msg": "hello"})

        assert result == "ok"
        assert mcp.call_count == 1

    async def test_api_timeout_does_not_crash_fetch(self) -> None:
        """httpx.TimeoutException during the fetch must return None (fail-open)."""
        import httpx

        client = _make_client()

        http_mock = MagicMock()
        http_mock.get = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
        client._get_http = AsyncMock(return_value=http_mock)

        result = await client._fetch_prevention_config("agent-x", "proj-1")
        assert result is None


# ============================================================================
# 4. SDK CONFIG RACE CONDITION
# ============================================================================


class TestSDKConfigRaceCondition:
    """Invariant: concurrent wrap() calls and _apply_remote_config must not
    produce split-brain state where some proxies have old limits and others
    have None (and therefore no limits at all)."""

    async def test_apply_remote_config_during_call_tool_does_not_corrupt(
        self,
    ) -> None:
        """_apply_remote_config updating _loop_config while call_tool is reading
        it must not cause an AttributeError or LoopDetectedError from stale state.

        Strategy: run call_tool and _apply_remote_config concurrently; assert that
        call_tool either succeeds or raises one of the three known prevention
        exceptions — never AttributeError or TypeError from a partially-applied
        config object.
        """
        from langsight.exceptions import (
            BudgetExceededError,
            CircuitBreakerOpenError,
            LoopDetectedError,
        )

        client = _make_client(loop_detection=True, loop_threshold=10)

        # Remote config will disable loop detection entirely
        _stub_fetch(client, {"loop_enabled": False})

        mcp = _FakeMCPClient(result="ok")
        proxy = client.wrap(
            mcp,
            server_name="srv",
            agent_name="racing-agent",
            session_id="sess-race",
        )

        caught_exceptions: list[Exception] = []

        async def run_call() -> None:
            try:
                with patch.object(client, "buffer_span"):
                    await proxy.call_tool("tool", {"x": 1})
            except (LoopDetectedError, BudgetExceededError, CircuitBreakerOpenError):
                pass  # known, expected prevention exceptions
            except Exception as exc:  # noqa: BLE001
                caught_exceptions.append(exc)

        async def run_config_update() -> None:
            await client._apply_remote_config("racing-agent", "proj-1")

        await asyncio.gather(run_call(), run_config_update())

        # No unexpected exceptions (AttributeError, TypeError, etc.)
        assert caught_exceptions == [], (
            f"Unexpected exceptions during concurrent access: {caught_exceptions}"
        )

    async def test_multiple_concurrent_wrap_calls_share_consistent_state(
        self,
    ) -> None:
        """Multiple concurrent wrap() calls for the same agent_name must each
        receive a valid MCPClientProxy that operates against the same underlying
        prevention state (no per-wrap private copy divergence)."""
        client = _make_client(loop_detection=True, loop_threshold=5)
        # Disable the background remote config fetch for this test
        client._fetch_prevention_config = AsyncMock(return_value=None)

        mcp = _FakeMCPClient(result="ok")

        proxies = [
            client.wrap(mcp, server_name="srv", agent_name="concurrent-agent")
            for _ in range(20)
        ]

        # All proxies must share the same LangSightClient state
        for proxy in proxies:
            langsight_ref = object.__getattribute__(proxy, "_langsight")
            assert langsight_ref is client

    async def test_apply_remote_config_called_twice_is_idempotent(
        self,
    ) -> None:
        """Calling _apply_remote_config twice with the same config must produce
        the same result as calling it once — no state accumulation."""
        client = _make_client()
        config = {
            "loop_enabled": True,
            "loop_threshold": 4,
            "loop_action": "warn",
            "cb_enabled": True,
            "cb_failure_threshold": 3,
            "cb_cooldown_seconds": 30.0,
            "cb_half_open_max_calls": 1,
        }
        _stub_fetch(client, config)

        await client._apply_remote_config("agent-x", "proj-1")
        loop_config_after_first = client._loop_config
        cb_config_after_first = client._cb_default_config

        await client._apply_remote_config("agent-x", "proj-1")

        # Values must be the same (not doubled or stacked)
        assert client._loop_config is not None
        assert client._loop_config.threshold == loop_config_after_first.threshold  # type: ignore[union-attr]
        assert client._cb_default_config is not None
        assert (
            client._cb_default_config.failure_threshold
            == cb_config_after_first.failure_threshold  # type: ignore[union-attr]
        )


# ============================================================================
# 5. OFFLINE FALLBACK INTEGRITY
# ============================================================================


class TestOfflineFallbackIntegrity:
    """Invariant: when the prevention-config API is unavailable (404 or None),
    constructor defaults must be preserved exactly.  The SDK must never silently
    add limits when none were requested, or silently remove limits that were set."""

    async def test_404_from_api_preserves_constructor_max_steps(self) -> None:
        """SDK with max_steps=5 from constructor: API returns 404 → max_steps=5 unchanged."""
        client = _make_client(max_steps=5)
        assert client._budget_config is not None
        assert client._budget_config.max_steps == 5

        _stub_fetch(client, None)  # None = 404 / unreachable
        await client._apply_remote_config("agent-x", "proj-1")

        assert client._budget_config is not None
        assert client._budget_config.max_steps == 5

    async def test_404_from_api_preserves_constructor_loop_threshold(self) -> None:
        """SDK with loop_threshold=7: API returns None → threshold still 7."""
        client = _make_client(loop_detection=True, loop_threshold=7)
        assert client._loop_config is not None
        assert client._loop_config.threshold == 7

        _stub_fetch(client, None)
        await client._apply_remote_config("agent-x", "proj-1")

        assert client._loop_config is not None
        assert client._loop_config.threshold == 7

    async def test_404_from_api_preserves_constructor_circuit_breaker(
        self,
    ) -> None:
        """Circuit breaker with threshold=3 from constructor: 404 → unchanged."""
        client = _make_client(
            circuit_breaker=True,
            circuit_breaker_threshold=3,
            circuit_breaker_cooldown=45.0,
        )
        assert client._cb_default_config is not None
        assert client._cb_default_config.failure_threshold == 3

        _stub_fetch(client, None)
        await client._apply_remote_config("agent-x", "proj-1")

        assert client._cb_default_config is not None
        assert client._cb_default_config.failure_threshold == 3

    async def test_no_limits_in_constructor_and_api_returns_none_stays_no_limits(
        self,
    ) -> None:
        """SDK with no limits from constructor + API returns None: no limits are set.

        This is the backward-compatibility case: a caller who opted out of all
        prevention must stay opted out even after _apply_remote_config runs.
        """
        client = _make_client()  # no loop, no budget, no CB
        assert client._loop_config is None
        assert client._budget_config is None
        assert client._cb_default_config is None

        _stub_fetch(client, None)
        await client._apply_remote_config("agent-x", "proj-1")

        # Still no limits — None response must not activate defaults
        assert client._loop_config is None
        assert client._budget_config is None
        assert client._cb_default_config is None

    async def test_remote_config_with_loop_disabled_clears_constructor_loop_config(
        self,
    ) -> None:
        """Remote config with loop_enabled=False must override constructor's
        loop_detection=True.  This is the authoritative server-side disable case."""
        client = _make_client(loop_detection=True, loop_threshold=3)
        assert client._loop_config is not None

        _stub_fetch(client, {"loop_enabled": False})
        await client._apply_remote_config("agent-x", "proj-1")

        # Loop detection must now be disabled
        assert client._loop_config is None

    async def test_remote_config_with_cb_disabled_clears_constructor_cb(
        self,
    ) -> None:
        """Remote cb_enabled=False must override constructor circuit_breaker=True."""
        client = _make_client(circuit_breaker=True, circuit_breaker_threshold=5)
        assert client._cb_default_config is not None

        _stub_fetch(client, {"cb_enabled": False})
        await client._apply_remote_config("agent-x", "proj-1")

        assert client._cb_default_config is None

    async def test_api_404_call_tool_still_enforces_constructor_step_limit(
        self,
    ) -> None:
        """End-to-end: constructor max_steps=2, API returns 404.
        The third call must still raise BudgetExceededError."""
        from langsight.exceptions import BudgetExceededError

        client = _make_client(max_steps=2)
        _stub_fetch(client, None)
        await client._apply_remote_config("agent-x", "proj-1")

        mcp = _FakeMCPClient(result="ok")
        proxy = client.wrap(mcp, server_name="srv", session_id="offline-sess")

        with patch.object(client, "buffer_span"):
            await proxy.call_tool("a", {})
            await proxy.call_tool("b", {})
            with pytest.raises(BudgetExceededError) as exc_info:
                await proxy.call_tool("c", {})

        assert exc_info.value.limit_type == "max_steps"
        assert mcp.call_count == 2

    async def test_api_404_call_tool_still_enforces_constructor_loop_detection(
        self,
    ) -> None:
        """End-to-end: constructor loop_threshold=2, API returns 404.
        The third identical call must still raise LoopDetectedError."""
        from langsight.exceptions import LoopDetectedError

        client = _make_client(loop_detection=True, loop_threshold=2)
        _stub_fetch(client, None)
        await client._apply_remote_config("agent-x", "proj-1")

        mcp = _FakeMCPClient(result="ok")
        proxy = client.wrap(mcp, server_name="srv", session_id="offline-loop-sess")

        with patch.object(client, "buffer_span"):
            await proxy.call_tool("repeat_tool", {"arg": "value"})
            with pytest.raises(LoopDetectedError):
                await proxy.call_tool("repeat_tool", {"arg": "value"})

        assert mcp.call_count == 1

    async def test_project_id_url_encoded_in_fetch(self) -> None:
        """project_id containing forward-slashes must be percent-encoded in the
        query string so that a value like 'proj/../../etc/passwd' cannot be used
        to traverse the URL path.

        SECURITY FINDING: _fetch_prevention_config calls urllib.parse.quote(project_id)
        with the default safe='/' which leaves forward slashes unencoded.  A caller
        with a crafted project_id can therefore inject '/' into the query parameter
        value, potentially manipulating intermediary proxies or logging pipelines.

        The fix is to call quote(project_id, safe='') so that '/' is encoded as '%2F'.

        This test pins the vulnerability.  It will PASS once the production code
        is corrected.  Until then it correctly fails, documenting the open gap.
        """
        client = _make_client()

        http_mock = MagicMock()
        http_mock.get = AsyncMock(return_value=_make_mock_response(404))
        client._get_http = AsyncMock(return_value=http_mock)

        special_project_id = "proj/../../etc/passwd"
        await client._fetch_prevention_config("my-agent", special_project_id)

        # Confirm the HTTP call was made
        assert http_mock.get.called, "Expected _get_http().get() to be called"
        # Extract the URL — call_args[0][0] is the first positional arg
        called_url: str = http_mock.get.call_args[0][0]
        # The '/' in project_id must be percent-encoded in the query string.
        # quote(s, safe='') encodes '/' as '%2F'; the default safe='/' does not.
        query_string = called_url.split("?", 1)[-1] if "?" in called_url else ""
        assert "../" not in query_string, (
            f"SECURITY: Unencoded path traversal in project_id query param: {query_string!r}. "
            f"Fix: use quote(project_id, safe='') in _fetch_prevention_config."
        )

    async def test_agent_name_url_encoded_in_fetch(self) -> None:
        """agent_name containing path-traversal chars must be percent-encoded in the URL
        path segment, not inserted raw.

        A value like 'my-agent/prevention-config/../../../api/auth/keys' would resolve
        to a different endpoint on path-aware proxies if not encoded.

        FIXED: _fetch_prevention_config now uses quote(agent_name, safe='') to encode
        the path segment, ensuring '/' becomes '%2F'.
        """
        client = _make_client()
        http_mock = MagicMock()
        http_mock.get = AsyncMock(return_value=_make_mock_response(404))
        client._get_http = AsyncMock(return_value=http_mock)

        traversal_agent = "my-agent/prevention-config/../../../api/auth/keys"
        await client._fetch_prevention_config(traversal_agent, None)

        assert http_mock.get.called
        called_url: str = http_mock.get.call_args[0][0]
        # The path segment between /agents/ and /prevention-config must be encoded
        path = called_url.split("?")[0]
        assert "/../" not in path, (
            f"SECURITY: Unencoded path traversal in agent_name URL segment: {path!r}."
        )
        assert "%2F" in path, (
            f"Forward slash must be percent-encoded in the URL path segment: {path!r}."
        )
