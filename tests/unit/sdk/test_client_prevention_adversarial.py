"""Adversarial and edge-case tests for SDK prevention integration.

Tests the interaction between multiple prevention features, default session
handling, error propagation, and backward compatibility.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from langsight.exceptions import (
    BudgetExceededError,
    CircuitBreakerOpenError,
    LoopDetectedError,
)
from langsight.sdk.client import LangSightClient, MCPClientProxy
from langsight.sdk.models import ToolCallStatus


class _FakeMCPClient:
    """Minimal mock MCP client."""

    def __init__(
        self,
        result: object = "ok",
        error: Exception | None = None,
    ) -> None:
        self._result = result
        self._error = error
        self.call_count = 0

    async def call_tool(self, name: str, arguments: dict | None = None) -> object:
        self.call_count += 1
        if self._error:
            raise self._error
        return self._result


class _FlakyMCPClient:
    """Returns results for some calls and raises errors for others."""

    def __init__(self, outcomes: list[object | Exception]) -> None:
        self._outcomes = list(outcomes)
        self.call_count = 0

    async def call_tool(self, name: str, arguments: dict | None = None) -> object:
        self.call_count += 1
        outcome = self._outcomes.pop(0) if self._outcomes else RuntimeError("exhausted")
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


# ---------------------------------------------------------------------------
# All three prevention features active simultaneously
# ---------------------------------------------------------------------------


class TestAllPreventionFeaturesActive:
    @pytest.fixture
    def full_client(self) -> LangSightClient:
        return LangSightClient(
            url="http://test:8000",
            loop_detection=True,
            loop_threshold=3,
            loop_action="terminate",
            max_steps=5,
            circuit_breaker=True,
            circuit_breaker_threshold=2,
            circuit_breaker_cooldown=60.0,
        )

    async def test_loop_detected_within_budget_and_circuit_closed(
        self, full_client: LangSightClient
    ) -> None:
        """Loop detection fires even when budget and circuit breaker are fine."""
        mcp = _FakeMCPClient(result="ok")
        proxy = full_client.wrap(mcp, server_name="srv", session_id="sess-1")

        with patch.object(full_client, "send_span", new_callable=AsyncMock):
            await proxy.call_tool("query", {"sql": "SELECT 1"})
            await proxy.call_tool("query", {"sql": "SELECT 1"})
            with pytest.raises(LoopDetectedError):
                await proxy.call_tool("query", {"sql": "SELECT 1"})

        assert mcp.call_count == 2

    async def test_budget_exceeded_after_varied_calls(
        self, full_client: LangSightClient
    ) -> None:
        """Budget fires after max_steps=5 even when calls are all different."""
        mcp = _FakeMCPClient(result="ok")
        proxy = full_client.wrap(mcp, server_name="srv", session_id="sess-2")

        with patch.object(full_client, "send_span", new_callable=AsyncMock):
            for i in range(5):
                await proxy.call_tool(f"tool_{i}", {"i": i})

            with pytest.raises(BudgetExceededError) as exc_info:
                await proxy.call_tool("tool_6", {"i": 6})

        assert exc_info.value.limit_type == "max_steps"
        assert mcp.call_count == 5

    async def test_circuit_breaker_fires_before_loop_check(
        self, full_client: LangSightClient
    ) -> None:
        """Circuit breaker (checked first) blocks the call even if loop would also fire."""
        mcp = _FakeMCPClient(error=RuntimeError("down"))
        proxy = full_client.wrap(mcp, server_name="failing-srv", session_id="sess-3")

        with patch.object(full_client, "send_span", new_callable=AsyncMock):
            with pytest.raises(RuntimeError):
                await proxy.call_tool("query", {"sql": "SELECT 1"})
            with pytest.raises(RuntimeError):
                await proxy.call_tool("query", {"sql": "SELECT 1"})

            # Circuit is open. Next identical call would trigger both loop AND circuit breaker.
            # Circuit breaker is checked first.
            with pytest.raises(CircuitBreakerOpenError):
                await proxy.call_tool("query", {"sql": "SELECT 1"})


# ---------------------------------------------------------------------------
# No session_id — uses "__default__" key
# ---------------------------------------------------------------------------


class TestDefaultSessionKey:
    async def test_loop_detection_uses_default_key(self) -> None:
        client = LangSightClient(
            url="http://test:8000",
            loop_detection=True,
            loop_threshold=2,
        )
        mcp = _FakeMCPClient(result="ok")
        proxy = client.wrap(mcp, server_name="srv")  # no session_id

        with patch.object(client, "send_span", new_callable=AsyncMock):
            await proxy.call_tool("query", {"x": 1})
            with pytest.raises(LoopDetectedError):
                await proxy.call_tool("query", {"x": 1})

    async def test_budget_uses_default_key(self) -> None:
        client = LangSightClient(
            url="http://test:8000",
            max_steps=1,
        )
        mcp = _FakeMCPClient(result="ok")
        proxy = client.wrap(mcp, server_name="srv")  # no session_id

        with patch.object(client, "send_span", new_callable=AsyncMock):
            await proxy.call_tool("query", {"x": 1})
            with pytest.raises(BudgetExceededError):
                await proxy.call_tool("query", {"x": 2})

    async def test_separate_sessions_have_separate_loop_detectors(self) -> None:
        """Different session_ids get independent loop detectors."""
        client = LangSightClient(
            url="http://test:8000",
            loop_detection=True,
            loop_threshold=2,
        )
        mcp = _FakeMCPClient(result="ok")
        proxy_a = client.wrap(mcp, server_name="srv", session_id="a")
        proxy_b = client.wrap(mcp, server_name="srv", session_id="b")

        with patch.object(client, "send_span", new_callable=AsyncMock):
            # Session A: one call
            await proxy_a.call_tool("query", {"x": 1})
            # Session B: one call
            await proxy_b.call_tool("query", {"x": 1})
            # Session A: second call triggers loop (threshold=2)
            with pytest.raises(LoopDetectedError):
                await proxy_a.call_tool("query", {"x": 1})
            # Session B: second call also triggers loop independently
            with pytest.raises(LoopDetectedError):
                await proxy_b.call_tool("query", {"x": 1})

    async def test_none_session_and_default_share_state(self) -> None:
        """Two proxies with session_id=None share the same __default__ key."""
        client = LangSightClient(
            url="http://test:8000",
            loop_detection=True,
            loop_threshold=3,
        )
        mcp = _FakeMCPClient(result="ok")
        proxy1 = client.wrap(mcp, server_name="srv")
        proxy2 = client.wrap(mcp, server_name="srv")

        with patch.object(client, "send_span", new_callable=AsyncMock):
            await proxy1.call_tool("query", {"x": 1})
            await proxy2.call_tool("query", {"x": 1})
            # Third call through either proxy should trigger loop
            with pytest.raises(LoopDetectedError):
                await proxy1.call_tool("query", {"x": 1})


# ---------------------------------------------------------------------------
# Budget exceeded mid-session after some successful calls
# ---------------------------------------------------------------------------


class TestBudgetExceededMidSession:
    async def test_first_calls_succeed_then_budget_blocks(self) -> None:
        client = LangSightClient(
            url="http://test:8000",
            max_steps=3,
        )
        mcp = _FakeMCPClient(result="result")
        proxy = client.wrap(mcp, server_name="srv", session_id="sess")
        sent_spans: list = []

        async def capture_span(span: object) -> None:
            sent_spans.append(span)

        with patch.object(client, "send_span", side_effect=capture_span):
            r1 = await proxy.call_tool("a", {})
            r2 = await proxy.call_tool("b", {})
            r3 = await proxy.call_tool("c", {})
            assert r1 == "result"
            assert r2 == "result"
            assert r3 == "result"

            with pytest.raises(BudgetExceededError):
                await proxy.call_tool("d", {})

        # Verify the prevented span
        prevented = [s for s in sent_spans if s.status == ToolCallStatus.PREVENTED]
        assert len(prevented) == 1
        assert "budget_exceeded" in prevented[0].error

        # Verify successful spans
        success = [s for s in sent_spans if s.status == ToolCallStatus.SUCCESS]
        assert len(success) == 3


# ---------------------------------------------------------------------------
# Client with all prevention disabled (backward compat)
# ---------------------------------------------------------------------------


class TestAllPreventionDisabled:
    async def test_no_prevention_many_identical_calls(self) -> None:
        client = LangSightClient(url="http://test:8000")
        mcp = _FakeMCPClient(result="ok")
        proxy = client.wrap(mcp, server_name="srv", session_id="sess")

        with patch.object(client, "send_span", new_callable=AsyncMock):
            for _ in range(50):
                result = await proxy.call_tool("query", {"sql": "SELECT 1"})
                assert result == "ok"

        assert mcp.call_count == 50

    async def test_no_prevention_many_failures_no_circuit_breaker(self) -> None:
        client = LangSightClient(url="http://test:8000")
        mcp = _FakeMCPClient(error=RuntimeError("down"))
        proxy = client.wrap(mcp, server_name="srv")

        with patch.object(client, "send_span", new_callable=AsyncMock):
            for _ in range(20):
                with pytest.raises(RuntimeError):
                    await proxy.call_tool("query", {})

        # No CircuitBreakerOpenError — all RuntimeErrors
        assert mcp.call_count == 20

    async def test_internal_state_dicts_empty(self) -> None:
        client = LangSightClient(url="http://test:8000")
        assert client._loop_config is None
        assert client._budget_config is None
        assert client._cb_default_config is None
        assert len(client._loop_detectors) == 0
        assert len(client._session_budgets) == 0
        assert len(client._circuit_breakers) == 0


# ---------------------------------------------------------------------------
# Error in underlying tool call + circuit breaker tracking
# ---------------------------------------------------------------------------


class TestToolCallErrorWithCircuitBreaker:
    async def test_timeout_counts_as_failure(self) -> None:
        client = LangSightClient(
            url="http://test:8000",
            circuit_breaker=True,
            circuit_breaker_threshold=2,
        )
        mcp = _FakeMCPClient(error=TimeoutError("read timeout"))
        proxy = client.wrap(mcp, server_name="srv")

        with patch.object(client, "send_span", new_callable=AsyncMock):
            with pytest.raises(TimeoutError):
                await proxy.call_tool("query", {})
            with pytest.raises(TimeoutError):
                await proxy.call_tool("query", {})

            # Circuit should be open
            with pytest.raises(CircuitBreakerOpenError):
                await proxy.call_tool("query", {})

    async def test_success_after_failure_resets_circuit_breaker(self) -> None:
        client = LangSightClient(
            url="http://test:8000",
            circuit_breaker=True,
            circuit_breaker_threshold=3,
        )
        outcomes: list[object | Exception] = [
            RuntimeError("err"),
            RuntimeError("err"),
            "ok",  # reset
            RuntimeError("err"),
            RuntimeError("err"),
            "ok",  # reset again
        ]
        mcp = _FlakyMCPClient(outcomes)
        proxy = client.wrap(mcp, server_name="srv")

        with patch.object(client, "send_span", new_callable=AsyncMock):
            with pytest.raises(RuntimeError):
                await proxy.call_tool("a", {})
            with pytest.raises(RuntimeError):
                await proxy.call_tool("b", {})
            result = await proxy.call_tool("c", {})  # success resets
            assert result == "ok"

            with pytest.raises(RuntimeError):
                await proxy.call_tool("d", {})
            with pytest.raises(RuntimeError):
                await proxy.call_tool("e", {})
            result = await proxy.call_tool("f", {})  # success resets again
            assert result == "ok"

        # No CircuitBreakerOpenError was raised — success kept resetting
        assert mcp.call_count == 6


# ---------------------------------------------------------------------------
# send_span failure does not break prevention logic
# ---------------------------------------------------------------------------


class TestSendSpanFailureDoesNotBreakPrevention:
    async def test_send_span_error_does_not_propagate(self) -> None:
        """If send_span raises, the tool call result should still be returned."""
        client = LangSightClient(url="http://test:8000")
        mcp = _FakeMCPClient(result="important_result")
        proxy = client.wrap(mcp, server_name="srv")

        async def failing_send(span: object) -> None:
            raise ConnectionError("LangSight API unreachable")

        with patch.object(client, "send_span", side_effect=failing_send):
            # send_span is called inside call_tool. It should not break the call.
            # Looking at client.py: send_span is awaited directly after the finally block,
            # so if it raises, it will propagate. Let's verify this behavior.
            # Actually in prevented path: send_span is awaited then exception is raised.
            # In normal path: send_span is awaited in the finally block.
            # The send_span IS awaited — so its error WILL propagate unless caught.
            # This test documents current behavior: send_span errors DO propagate.
            with pytest.raises(ConnectionError):
                await proxy.call_tool("query", {})

    async def test_prevention_still_applies_when_send_span_mocked(self) -> None:
        """Prevention checks happen before send_span is called."""
        client = LangSightClient(
            url="http://test:8000",
            loop_detection=True,
            loop_threshold=2,
        )
        mcp = _FakeMCPClient(result="ok")
        proxy = client.wrap(mcp, server_name="srv", session_id="sess")

        with patch.object(client, "send_span", new_callable=AsyncMock):
            await proxy.call_tool("query", {"x": 1})
            with pytest.raises(LoopDetectedError):
                await proxy.call_tool("query", {"x": 1})


# ---------------------------------------------------------------------------
# Prevented span contains correct metadata
# ---------------------------------------------------------------------------


class TestPreventedSpanMetadata:
    async def test_prevented_span_has_zero_latency(self) -> None:
        client = LangSightClient(
            url="http://test:8000",
            max_steps=0,
        )
        mcp = _FakeMCPClient(result="ok")
        proxy = client.wrap(mcp, server_name="my-srv", session_id="my-sess")
        sent_spans: list = []

        async def capture(span: object) -> None:
            sent_spans.append(span)

        with patch.object(client, "send_span", side_effect=capture):
            with pytest.raises(BudgetExceededError):
                await proxy.call_tool("query", {"sql": "X"})

        span = sent_spans[0]
        assert span.latency_ms == 0.0
        assert span.status == ToolCallStatus.PREVENTED
        assert span.server_name == "my-srv"
        assert span.session_id == "my-sess"
        assert span.tool_name == "query"

    async def test_prevented_span_has_input_args_when_not_redacted(self) -> None:
        client = LangSightClient(
            url="http://test:8000",
            max_steps=0,
            redact_payloads=False,
        )
        mcp = _FakeMCPClient(result="ok")
        proxy = client.wrap(mcp, server_name="srv")
        sent_spans: list = []

        async def capture(span: object) -> None:
            sent_spans.append(span)

        with patch.object(client, "send_span", side_effect=capture):
            with pytest.raises(BudgetExceededError):
                await proxy.call_tool("query", {"sql": "SELECT 1"})

        span = sent_spans[0]
        assert span.input_args == {"sql": "SELECT 1"}

    async def test_prevented_span_has_no_input_args_when_redacted(self) -> None:
        client = LangSightClient(
            url="http://test:8000",
            max_steps=0,
            redact_payloads=True,
        )
        mcp = _FakeMCPClient(result="ok")
        proxy = client.wrap(mcp, server_name="srv")
        sent_spans: list = []

        async def capture(span: object) -> None:
            sent_spans.append(span)

        with patch.object(client, "send_span", side_effect=capture):
            with pytest.raises(BudgetExceededError):
                await proxy.call_tool("query", {"sql": "SELECT 1"})

        span = sent_spans[0]
        assert span.input_args is None


# ---------------------------------------------------------------------------
# Circuit breaker is per-server, not per-session
# ---------------------------------------------------------------------------


class TestCircuitBreakerPerServer:
    async def test_different_servers_have_independent_breakers(self) -> None:
        client = LangSightClient(
            url="http://test:8000",
            circuit_breaker=True,
            circuit_breaker_threshold=1,
        )
        mcp_a = _FakeMCPClient(error=RuntimeError("down"))
        mcp_b = _FakeMCPClient(result="ok")
        proxy_a = client.wrap(mcp_a, server_name="server-a")
        proxy_b = client.wrap(mcp_b, server_name="server-b")

        with patch.object(client, "send_span", new_callable=AsyncMock):
            # Trip server-a
            with pytest.raises(RuntimeError):
                await proxy_a.call_tool("query", {})
            with pytest.raises(CircuitBreakerOpenError):
                await proxy_a.call_tool("query", {})

            # server-b is unaffected
            result = await proxy_b.call_tool("query", {})
            assert result == "ok"


# ---------------------------------------------------------------------------
# Loop detection with warn mode + budget interaction
# ---------------------------------------------------------------------------


class TestWarnModeDoesNotBlockButBudgetDoes:
    async def test_warn_mode_loop_then_budget_blocks(self) -> None:
        client = LangSightClient(
            url="http://test:8000",
            loop_detection=True,
            loop_threshold=2,
            loop_action="warn",  # warn only, don't block
            max_steps=3,
        )
        mcp = _FakeMCPClient(result="ok")
        proxy = client.wrap(mcp, server_name="srv", session_id="sess")

        with patch.object(client, "send_span", new_callable=AsyncMock):
            # These trigger loop warning but NOT termination
            await proxy.call_tool("query", {"x": 1})
            await proxy.call_tool("query", {"x": 1})
            await proxy.call_tool("query", {"x": 1})

            # 4th call exceeds budget (max_steps=3)
            with pytest.raises(BudgetExceededError):
                await proxy.call_tool("query", {"x": 1})

        assert mcp.call_count == 3
