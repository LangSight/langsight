"""Tests for v0.3 prevention features wired into LangSightClient + MCPClientProxy."""

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

    def __init__(self, result: object = "ok", error: Exception | None = None) -> None:
        self._result = result
        self._error = error
        self.call_count = 0

    async def call_tool(self, name: str, arguments: dict | None = None) -> object:
        self.call_count += 1
        if self._error:
            raise self._error
        return self._result


@pytest.fixture
def client_no_prevention() -> LangSightClient:
    return LangSightClient(url="http://test:8000")


@pytest.fixture
def client_with_loop() -> LangSightClient:
    return LangSightClient(
        url="http://test:8000",
        loop_detection=True,
        loop_threshold=3,
        loop_action="terminate",
    )


@pytest.fixture
def client_with_budget() -> LangSightClient:
    return LangSightClient(
        url="http://test:8000",
        max_steps=3,
    )


@pytest.fixture
def client_with_circuit_breaker() -> LangSightClient:
    return LangSightClient(
        url="http://test:8000",
        circuit_breaker=True,
        circuit_breaker_threshold=2,
        circuit_breaker_cooldown=60.0,
    )


class TestNoPrevention:
    @pytest.mark.asyncio
    async def test_call_passes_through(self, client_no_prevention: LangSightClient) -> None:
        mcp = _FakeMCPClient(result="hello")
        with patch.object(client_no_prevention, "send_span", new_callable=AsyncMock):
            proxy = client_no_prevention.wrap(mcp, server_name="test")
            result = await proxy.call_tool("echo", {"msg": "hi"})
        assert result == "hello"
        assert mcp.call_count == 1


class TestLoopDetection:
    @pytest.mark.asyncio
    async def test_blocks_after_threshold(self, client_with_loop: LangSightClient) -> None:
        mcp = _FakeMCPClient(result="ok")
        proxy = client_with_loop.wrap(mcp, server_name="test", session_id="sess-1")

        with patch.object(client_with_loop, "send_span", new_callable=AsyncMock):
            # First two calls succeed
            await proxy.call_tool("query", {"sql": "SELECT 1"})
            await proxy.call_tool("query", {"sql": "SELECT 1"})

            # Third identical call should be blocked
            with pytest.raises(LoopDetectedError) as exc_info:
                await proxy.call_tool("query", {"sql": "SELECT 1"})

        assert exc_info.value.tool_name == "query"
        assert exc_info.value.pattern == "repetition"
        assert mcp.call_count == 2  # only 2 real calls made

    @pytest.mark.asyncio
    async def test_different_args_not_blocked(self, client_with_loop: LangSightClient) -> None:
        mcp = _FakeMCPClient(result="ok")
        proxy = client_with_loop.wrap(mcp, server_name="test", session_id="sess-1")

        with patch.object(client_with_loop, "send_span", new_callable=AsyncMock):
            await proxy.call_tool("query", {"sql": "SELECT 1"})
            await proxy.call_tool("query", {"sql": "SELECT 2"})
            await proxy.call_tool("query", {"sql": "SELECT 3"})

        assert mcp.call_count == 3

    @pytest.mark.asyncio
    async def test_warn_mode_allows_call(self) -> None:
        client = LangSightClient(
            url="http://test:8000",
            loop_detection=True,
            loop_threshold=3,
            loop_action="warn",
        )
        mcp = _FakeMCPClient(result="ok")
        proxy = client.wrap(mcp, server_name="test", session_id="sess-1")

        with patch.object(client, "send_span", new_callable=AsyncMock):
            # All 3 calls should succeed (warn, don't terminate)
            await proxy.call_tool("query", {"sql": "SELECT 1"})
            await proxy.call_tool("query", {"sql": "SELECT 1"})
            await proxy.call_tool("query", {"sql": "SELECT 1"})

        assert mcp.call_count == 3

    @pytest.mark.asyncio
    async def test_prevented_span_recorded(self, client_with_loop: LangSightClient) -> None:
        mcp = _FakeMCPClient(result="ok")
        proxy = client_with_loop.wrap(mcp, server_name="test", session_id="sess-1")
        sent_spans: list = []

        async def capture_span(span: object) -> None:
            sent_spans.append(span)

        with patch.object(client_with_loop, "send_span", side_effect=capture_span):
            await proxy.call_tool("query", {"sql": "SELECT 1"})
            await proxy.call_tool("query", {"sql": "SELECT 1"})
            with pytest.raises(LoopDetectedError):
                await proxy.call_tool("query", {"sql": "SELECT 1"})

        # Last span should be PREVENTED
        prevented = sent_spans[-1]
        assert prevented.status == ToolCallStatus.PREVENTED
        assert prevented.latency_ms == 0.0
        assert "loop_detected" in prevented.error


class TestBudgetGuardrails:
    @pytest.mark.asyncio
    async def test_blocks_after_step_limit(self, client_with_budget: LangSightClient) -> None:
        mcp = _FakeMCPClient(result="ok")
        proxy = client_with_budget.wrap(mcp, server_name="test", session_id="sess-1")

        with patch.object(client_with_budget, "send_span", new_callable=AsyncMock):
            await proxy.call_tool("a", {})
            await proxy.call_tool("b", {})
            await proxy.call_tool("c", {})

            # 4th call exceeds max_steps=3
            with pytest.raises(BudgetExceededError) as exc_info:
                await proxy.call_tool("d", {})

        assert exc_info.value.limit_type == "max_steps"
        assert mcp.call_count == 3

    @pytest.mark.asyncio
    async def test_prevented_span_recorded(self, client_with_budget: LangSightClient) -> None:
        mcp = _FakeMCPClient(result="ok")
        proxy = client_with_budget.wrap(mcp, server_name="test", session_id="sess-1")
        sent_spans: list = []

        async def capture_span(span: object) -> None:
            sent_spans.append(span)

        with patch.object(client_with_budget, "send_span", side_effect=capture_span):
            await proxy.call_tool("a", {})
            await proxy.call_tool("b", {})
            await proxy.call_tool("c", {})
            with pytest.raises(BudgetExceededError):
                await proxy.call_tool("d", {})

        prevented = sent_spans[-1]
        assert prevented.status == ToolCallStatus.PREVENTED
        assert "budget_exceeded" in prevented.error


class TestCircuitBreaker:
    @pytest.mark.asyncio
    async def test_opens_after_failures(
        self, client_with_circuit_breaker: LangSightClient
    ) -> None:
        mcp = _FakeMCPClient(error=RuntimeError("connection refused"))
        proxy = client_with_circuit_breaker.wrap(
            mcp, server_name="failing-server", session_id="sess-1"
        )

        with patch.object(client_with_circuit_breaker, "send_span", new_callable=AsyncMock):
            # 2 failures = threshold reached
            with pytest.raises(RuntimeError):
                await proxy.call_tool("query", {})
            with pytest.raises(RuntimeError):
                await proxy.call_tool("query", {})

            # Circuit is now open — 3rd call should be prevented
            with pytest.raises(CircuitBreakerOpenError) as exc_info:
                await proxy.call_tool("query", {})

        assert exc_info.value.server_name == "failing-server"
        assert mcp.call_count == 2  # only 2 real calls

    @pytest.mark.asyncio
    async def test_success_resets_failures(
        self, client_with_circuit_breaker: LangSightClient
    ) -> None:
        mcp = _FakeMCPClient(result="ok")
        proxy = client_with_circuit_breaker.wrap(
            mcp, server_name="good-server", session_id="sess-1"
        )

        with patch.object(client_with_circuit_breaker, "send_span", new_callable=AsyncMock):
            # Successful calls should work fine
            for _ in range(10):
                await proxy.call_tool("query", {})

        assert mcp.call_count == 10

    @pytest.mark.asyncio
    async def test_shared_across_proxies(
        self, client_with_circuit_breaker: LangSightClient
    ) -> None:
        """Circuit breaker state is shared for the same server_name."""
        mcp1 = _FakeMCPClient(error=RuntimeError("down"))
        mcp2 = _FakeMCPClient(result="ok")
        proxy1 = client_with_circuit_breaker.wrap(
            mcp1, server_name="shared-server", session_id="sess-1"
        )
        proxy2 = client_with_circuit_breaker.wrap(
            mcp2, server_name="shared-server", session_id="sess-2"
        )

        with patch.object(client_with_circuit_breaker, "send_span", new_callable=AsyncMock):
            # proxy1 triggers 2 failures
            with pytest.raises(RuntimeError):
                await proxy1.call_tool("query", {})
            with pytest.raises(RuntimeError):
                await proxy1.call_tool("query", {})

            # proxy2 (same server) should be blocked by circuit breaker
            with pytest.raises(CircuitBreakerOpenError):
                await proxy2.call_tool("query", {})


class TestPreventionOrder:
    @pytest.mark.asyncio
    async def test_circuit_breaker_checked_before_loop(self) -> None:
        """If circuit breaker is open AND loop detected, circuit breaker wins."""
        client = LangSightClient(
            url="http://test:8000",
            loop_detection=True,
            loop_threshold=3,
            circuit_breaker=True,
            circuit_breaker_threshold=1,  # opens after 1 failure
        )
        mcp = _FakeMCPClient(error=RuntimeError("down"))
        proxy = client.wrap(mcp, server_name="srv", session_id="sess-1")

        with patch.object(client, "send_span", new_callable=AsyncMock):
            # 1 failure opens circuit
            with pytest.raises(RuntimeError):
                await proxy.call_tool("query", {"sql": "SELECT 1"})

            # Next call blocked by circuit breaker (not loop)
            with pytest.raises(CircuitBreakerOpenError):
                await proxy.call_tool("query", {"sql": "SELECT 1"})
