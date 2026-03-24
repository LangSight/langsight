"""Tests for cross-layer span linking (wrap_llm → wrap context propagation)."""

from __future__ import annotations

import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from langsight.sdk.client import LangSightClient
from langsight.sdk.context import (
    _get_pending,
    claim_pending_tool,
    register_pending_tool,
)
from langsight.sdk.llm_wrapper import GenaiClientProxy, OpenAIProxy


@pytest.fixture(autouse=True)
def _clear_pending() -> None:
    """Clear thread-local pending state before each test."""
    _get_pending().clear()


@pytest.fixture
def client() -> LangSightClient:
    return LangSightClient(url="http://localhost:8000")


# =============================================================================
# Low-level: register / claim
# =============================================================================


class TestPendingToolCalls:
    def test_register_and_claim(self) -> None:
        register_pending_tool("search", "span-1")
        ctx = claim_pending_tool("search")
        assert ctx is not None
        assert ctx.span_id == "span-1"

    def test_claim_returns_none_when_empty(self) -> None:
        assert claim_pending_tool("unknown") is None

    def test_fifo_order(self) -> None:
        register_pending_tool("get_product", "span-a")
        register_pending_tool("get_product", "span-b")
        assert claim_pending_tool("get_product").span_id == "span-a"  # type: ignore[union-attr]
        assert claim_pending_tool("get_product").span_id == "span-b"  # type: ignore[union-attr]
        assert claim_pending_tool("get_product") is None

    def test_different_tools_independent(self) -> None:
        register_pending_tool("tool_a", "span-1")
        register_pending_tool("tool_b", "span-2")
        assert claim_pending_tool("tool_b").span_id == "span-2"  # type: ignore[union-attr]
        assert claim_pending_tool("tool_a").span_id == "span-1"  # type: ignore[union-attr]

    def test_agent_name_propagated(self) -> None:
        register_pending_tool("search", "span-1", agent_name="orchestrator")
        ctx = claim_pending_tool("search")
        assert ctx is not None
        assert ctx.agent_name == "orchestrator"

    def test_thread_isolation(self) -> None:
        """Pending calls in one thread must not leak to another."""
        register_pending_tool("search", "span-main")
        result_from_thread: list[object] = []

        def worker() -> None:
            result_from_thread.append(claim_pending_tool("search"))

        t = threading.Thread(target=worker)
        t.start()
        t.join()

        # Other thread sees nothing
        assert result_from_thread[0] is None
        # Original thread still has it
        ctx = claim_pending_tool("search")
        assert ctx is not None
        assert ctx.span_id == "span-main"


# =============================================================================
# wrap_llm registers pending
# =============================================================================


class TestWrapLlmRegistersPending:
    def test_openai_registers_function_calls(self, client: LangSightClient) -> None:
        """OpenAI proxy should register tool_call spans as pending."""
        tool_call = SimpleNamespace(
            function=SimpleNamespace(name="get_weather", arguments='{"city": "NYC"}'),
        )
        message = SimpleNamespace(tool_calls=[tool_call], content=None)
        choice = SimpleNamespace(message=message)
        usage = SimpleNamespace(prompt_tokens=100, completion_tokens=50)
        response = SimpleNamespace(choices=[choice], model="gpt-4o", usage=usage)

        fake_client = SimpleNamespace()
        fake_client.chat = SimpleNamespace()
        fake_client.chat.completions = SimpleNamespace()
        fake_client.chat.completions.create = lambda **kw: response

        proxy = OpenAIProxy(fake_client, client, agent_name="agent")
        proxy.chat.completions.create(model="gpt-4o", messages=[])

        # The function_call span should now be pending
        claimed = claim_pending_tool("get_weather")
        assert claimed is not None

    def test_genai_registers_function_calls(self, client: LangSightClient) -> None:
        """GenAI proxy should register tool_call spans as pending."""
        fn_call = SimpleNamespace(name="list_products", args={"category": "Electronics"})
        part = SimpleNamespace(function_call=fn_call)
        content = SimpleNamespace(parts=[part])
        candidate = SimpleNamespace(content=content)
        usage = SimpleNamespace(prompt_token_count=100, candidates_token_count=50)
        response = SimpleNamespace(candidates=[candidate], usage_metadata=usage)

        fake_genai = SimpleNamespace()
        fake_genai.models = SimpleNamespace()
        fake_genai.models.generate_content = lambda **kw: response

        proxy = GenaiClientProxy(fake_genai, client, agent_name="orchestrator")
        proxy.models.generate_content(model="gemini-2.5-flash", contents=[])

        claimed = claim_pending_tool("list_products")
        assert claimed is not None

    def test_no_function_calls_no_pending(self, client: LangSightClient) -> None:
        """No function calls in response → nothing registered."""
        message = SimpleNamespace(tool_calls=None, content="Hello!")
        choice = SimpleNamespace(message=message)
        usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5)
        response = SimpleNamespace(choices=[choice], model="gpt-4o", usage=usage)

        fake_client = SimpleNamespace()
        fake_client.chat = SimpleNamespace()
        fake_client.chat.completions = SimpleNamespace()
        fake_client.chat.completions.create = lambda **kw: response

        proxy = OpenAIProxy(fake_client, client, agent_name="agent")
        proxy.chat.completions.create(model="gpt-4o", messages=[])

        assert claim_pending_tool("anything") is None


# =============================================================================
# call_tool claims pending as parent
# =============================================================================


class TestCallToolClaimsPending:
    @pytest.mark.asyncio
    async def test_claims_pending_as_parent(self, client: LangSightClient) -> None:
        """MCPClientProxy.call_tool() should use pending span as parent."""
        register_pending_tool("list_low_stock", "llm-intent-span-id")

        # Build a minimal mock MCP client
        mock_mcp = MagicMock()
        mock_result = MagicMock()
        mock_result.isError = False
        mock_result.content = []
        mock_mcp.call_tool = AsyncMock(return_value=mock_result)

        proxy = client.wrap(mock_mcp, server_name="inventory", session_id="sess-1")

        # Capture the span that gets buffered
        captured: list = []
        original_buffer = client.buffer_span

        def capture(span: object) -> None:
            captured.append(span)

        client.buffer_span = capture  # type: ignore[assignment]

        await proxy.call_tool("list_low_stock", {})

        client.buffer_span = original_buffer  # type: ignore[assignment]

        assert len(captured) == 1
        assert captured[0].parent_span_id == "llm-intent-span-id"

    @pytest.mark.asyncio
    async def test_no_pending_leaves_parent_empty(self, client: LangSightClient) -> None:
        """Without prior wrap_llm, parent_span_id stays as constructor value."""
        mock_mcp = MagicMock()
        mock_result = MagicMock()
        mock_result.isError = False
        mock_result.content = []
        mock_mcp.call_tool = AsyncMock(return_value=mock_result)

        proxy = client.wrap(mock_mcp, server_name="inventory", session_id="sess-1")

        captured: list = []

        def capture(span: object) -> None:
            captured.append(span)

        client.buffer_span = capture  # type: ignore[assignment]

        await proxy.call_tool("some_tool", {})

        assert len(captured) == 1
        assert captured[0].parent_span_id is None
