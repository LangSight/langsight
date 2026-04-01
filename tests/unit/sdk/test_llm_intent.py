"""Tests for llm_intent span emission from LLM wrappers.

All 3 LLM response processors (OpenAI, Anthropic, Gemini) now emit
span_type="llm_intent" for tool decisions (not "tool_call"), and
register those spans in the pending-tool queue.

Covers:
- OpenAI processor emits llm_intent for tool_calls
- Anthropic processor emits llm_intent for tool_use blocks
- Gemini processor emits llm_intent for function_call parts
- llm_intent spans are registered in pending queue
- Text-only LLM response does NOT emit llm_intent span
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from langsight.sdk.auto_patch import (
    _agent_ctx,
    _session_ctx,
    _trace_ctx,
    clear_context,
    set_context,
)
from langsight.sdk.client import LangSightClient
from langsight.sdk.context import (
    _pending_tools_ctx,
    claim_pending_tool,
)
from langsight.sdk.llm_wrapper import (
    AnthropicProxy,
    GeminiProxy,
    GenaiClientProxy,
    OpenAIProxy,
    _maybe_emit_handoffs,
)
from langsight.sdk.models import ToolCallSpan


@pytest.fixture
def client() -> LangSightClient:
    return LangSightClient(url="http://localhost:8000")


@pytest.fixture(autouse=True)
def _clear_pending() -> None:
    """Reset pending tools context before each test."""
    _pending_tools_ctx.set(None)


def _capture_spans(client: LangSightClient) -> list[ToolCallSpan]:
    """Replace buffer_span with a list collector, return the list."""
    captured: list[ToolCallSpan] = []
    client.buffer_span = lambda span: captured.append(span)  # type: ignore[assignment]
    return captured


# =============================================================================
# OpenAI — llm_intent for tool_calls
# =============================================================================


class TestOpenAILlmIntent:
    def _make_openai_response_with_tools(
        self, tool_names: list[str]
    ) -> tuple[SimpleNamespace, SimpleNamespace]:
        """Build a mock OpenAI response with tool_calls and a fake client."""
        tool_calls = [
            SimpleNamespace(
                function=SimpleNamespace(name=name, arguments='{"key": "val"}')
            )
            for name in tool_names
        ]
        message = SimpleNamespace(tool_calls=tool_calls, content=None)
        choice = SimpleNamespace(message=message, finish_reason="tool_calls")
        usage = SimpleNamespace(prompt_tokens=100, completion_tokens=50)
        response = SimpleNamespace(choices=[choice], model="gpt-4o", usage=usage)

        fake_client = SimpleNamespace()
        fake_client.chat = SimpleNamespace()
        fake_client.chat.completions = SimpleNamespace()
        fake_client.chat.completions.create = lambda **kw: response

        return fake_client, response

    def test_openai_emits_llm_intent_for_tool_calls(self, client: LangSightClient) -> None:
        fake_client, _ = self._make_openai_response_with_tools(["get_weather"])
        captured = _capture_spans(client)

        proxy = OpenAIProxy(fake_client, client, agent_name="test-agent")
        proxy.chat.completions.create(model="gpt-4o", messages=[])

        # Should have: 1 agent span + 1 llm_intent span
        assert len(captured) == 2
        agent_span = captured[0]
        intent_span = captured[1]
        assert agent_span.span_type == "agent"
        assert intent_span.span_type == "llm_intent"
        assert intent_span.tool_name == "get_weather"

    def test_openai_multiple_tool_calls_emit_multiple_intents(
        self, client: LangSightClient
    ) -> None:
        fake_client, _ = self._make_openai_response_with_tools(
            ["search", "fetch_data", "summarize"]
        )
        captured = _capture_spans(client)

        proxy = OpenAIProxy(fake_client, client, agent_name="agent")
        proxy.chat.completions.create(model="gpt-4o", messages=[])

        intent_spans = [s for s in captured if s.span_type == "llm_intent"]
        assert len(intent_spans) == 3
        assert {s.tool_name for s in intent_spans} == {"search", "fetch_data", "summarize"}

    def test_openai_llm_intent_has_parent_set_to_llm_span(
        self, client: LangSightClient
    ) -> None:
        fake_client, _ = self._make_openai_response_with_tools(["search"])
        captured = _capture_spans(client)

        proxy = OpenAIProxy(fake_client, client, agent_name="agent")
        proxy.chat.completions.create(model="gpt-4o", messages=[])

        agent_span = captured[0]
        intent_span = captured[1]
        assert intent_span.parent_span_id == agent_span.span_id

    def test_openai_llm_intent_registered_in_pending_queue(
        self, client: LangSightClient
    ) -> None:
        fake_client, _ = self._make_openai_response_with_tools(["get_weather"])
        captured = _capture_spans(client)  # noqa: F841

        proxy = OpenAIProxy(fake_client, client, agent_name="agent-x")
        proxy.chat.completions.create(model="gpt-4o", messages=[])

        # The llm_intent span should be in the pending queue
        ctx = claim_pending_tool("get_weather")
        assert ctx is not None
        assert ctx.agent_name == "agent-x"

    def test_openai_text_only_response_no_intent_span(
        self, client: LangSightClient
    ) -> None:
        """Text-only response should NOT produce any llm_intent span."""
        message = SimpleNamespace(tool_calls=None, content="Hello!")
        choice = SimpleNamespace(message=message, finish_reason="stop")
        usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5)
        response = SimpleNamespace(choices=[choice], model="gpt-4o", usage=usage)

        fake_client = SimpleNamespace()
        fake_client.chat = SimpleNamespace()
        fake_client.chat.completions = SimpleNamespace()
        fake_client.chat.completions.create = lambda **kw: response

        captured = _capture_spans(client)
        proxy = OpenAIProxy(fake_client, client, agent_name="agent")
        proxy.chat.completions.create(model="gpt-4o", messages=[])

        intent_spans = [s for s in captured if s.span_type == "llm_intent"]
        assert len(intent_spans) == 0


# =============================================================================
# Anthropic — llm_intent for tool_use blocks
# =============================================================================


class TestAnthropicLlmIntent:
    def _make_anthropic_response_with_tools(
        self, tool_names: list[str]
    ) -> tuple[SimpleNamespace, SimpleNamespace]:
        blocks = [
            SimpleNamespace(type="tool_use", name=name, input={"key": "val"})
            for name in tool_names
        ]
        usage = SimpleNamespace(input_tokens=100, output_tokens=50)
        response = SimpleNamespace(
            content=blocks,
            model="claude-sonnet-4-6",
            usage=usage,
            stop_reason="tool_use",
        )

        fake_client = SimpleNamespace()
        fake_client.messages = SimpleNamespace()
        fake_client.messages.create = lambda **kw: response

        return fake_client, response

    def test_anthropic_emits_llm_intent_for_tool_use(
        self, client: LangSightClient
    ) -> None:
        fake_client, _ = self._make_anthropic_response_with_tools(["get_weather"])
        captured = _capture_spans(client)

        proxy = AnthropicProxy(fake_client, client, agent_name="claude-agent")
        proxy.messages.create(model="claude-sonnet-4-6", messages=[])

        intent_spans = [s for s in captured if s.span_type == "llm_intent"]
        assert len(intent_spans) == 1
        assert intent_spans[0].tool_name == "get_weather"

    def test_anthropic_multiple_tool_use_blocks(
        self, client: LangSightClient
    ) -> None:
        fake_client, _ = self._make_anthropic_response_with_tools(
            ["search", "get_time"]
        )
        captured = _capture_spans(client)

        proxy = AnthropicProxy(fake_client, client, agent_name="agent")
        proxy.messages.create(model="claude-sonnet-4-6", messages=[])

        intent_spans = [s for s in captured if s.span_type == "llm_intent"]
        assert len(intent_spans) == 2

    def test_anthropic_llm_intent_registered_in_pending_queue(
        self, client: LangSightClient
    ) -> None:
        fake_client, _ = self._make_anthropic_response_with_tools(["search_db"])
        _capture_spans(client)

        proxy = AnthropicProxy(fake_client, client, agent_name="my-agent")
        proxy.messages.create(model="claude-sonnet-4-6", messages=[])

        ctx = claim_pending_tool("search_db")
        assert ctx is not None
        assert ctx.agent_name == "my-agent"

    def test_anthropic_text_only_response_no_intent(
        self, client: LangSightClient
    ) -> None:
        text_block = SimpleNamespace(type="text", text="Hello there!")
        usage = SimpleNamespace(input_tokens=10, output_tokens=5)
        response = SimpleNamespace(
            content=[text_block],
            model="claude-sonnet-4-6",
            usage=usage,
            stop_reason="end_turn",
        )

        fake_client = SimpleNamespace()
        fake_client.messages = SimpleNamespace()
        fake_client.messages.create = lambda **kw: response

        captured = _capture_spans(client)
        proxy = AnthropicProxy(fake_client, client, agent_name="agent")
        proxy.messages.create(model="claude-sonnet-4-6", messages=[])

        intent_spans = [s for s in captured if s.span_type == "llm_intent"]
        assert len(intent_spans) == 0

    def test_anthropic_llm_intent_parent_is_agent_span(
        self, client: LangSightClient
    ) -> None:
        fake_client, _ = self._make_anthropic_response_with_tools(["search"])
        captured = _capture_spans(client)

        proxy = AnthropicProxy(fake_client, client, agent_name="agent")
        proxy.messages.create(model="claude-sonnet-4-6", messages=[])

        agent_span = [s for s in captured if s.span_type == "agent"][0]
        intent_span = [s for s in captured if s.span_type == "llm_intent"][0]
        assert intent_span.parent_span_id == agent_span.span_id


# =============================================================================
# Gemini (legacy SDK) — llm_intent for function_call
# =============================================================================


class TestGeminiLlmIntent:
    def _make_gemini_response_with_functions(
        self, function_names: list[str]
    ) -> tuple[SimpleNamespace, SimpleNamespace]:
        parts = [
            SimpleNamespace(
                function_call=SimpleNamespace(name=name, args={"key": "val"})
            )
            for name in function_names
        ]
        content = SimpleNamespace(parts=parts)
        candidate = SimpleNamespace(content=content, finish_reason="STOP")
        usage = SimpleNamespace(prompt_token_count=100, candidates_token_count=50)
        response = SimpleNamespace(candidates=[candidate], usage_metadata=usage)

        fake_model = SimpleNamespace(model_name="gemini-2.5-flash")
        return fake_model, response

    def test_gemini_emits_llm_intent_for_function_call(
        self, client: LangSightClient
    ) -> None:
        fake_model, response = self._make_gemini_response_with_functions(
            ["list_products"]
        )
        fake_model.generate_content = lambda *a, **kw: response
        captured = _capture_spans(client)

        proxy = GeminiProxy(fake_model, client, agent_name="gemini-agent")
        proxy.generate_content(contents=[])

        intent_spans = [s for s in captured if s.span_type == "llm_intent"]
        assert len(intent_spans) == 1
        assert intent_spans[0].tool_name == "list_products"

    def test_gemini_llm_intent_registered_in_pending_queue(
        self, client: LangSightClient
    ) -> None:
        fake_model, response = self._make_gemini_response_with_functions(
            ["get_stock"]
        )
        fake_model.generate_content = lambda *a, **kw: response
        _capture_spans(client)

        proxy = GeminiProxy(fake_model, client, agent_name="stock-agent")
        proxy.generate_content(contents=[])

        ctx = claim_pending_tool("get_stock")
        assert ctx is not None
        assert ctx.agent_name == "stock-agent"

    def test_gemini_text_only_no_intent(self, client: LangSightClient) -> None:
        """Response without function_call should not emit llm_intent."""
        text_part = SimpleNamespace(function_call=None)
        content = SimpleNamespace(parts=[text_part])
        candidate = SimpleNamespace(content=content, finish_reason="STOP")
        usage = SimpleNamespace(prompt_token_count=10, candidates_token_count=5)
        response = SimpleNamespace(candidates=[candidate], usage_metadata=usage)

        fake_model = SimpleNamespace(model_name="gemini-2.5-flash")
        fake_model.generate_content = lambda *a, **kw: response

        captured = _capture_spans(client)
        proxy = GeminiProxy(fake_model, client, agent_name="agent")
        proxy.generate_content(contents=[])

        intent_spans = [s for s in captured if s.span_type == "llm_intent"]
        assert len(intent_spans) == 0


# =============================================================================
# Google GenAI new SDK — llm_intent for function_call
# =============================================================================


class TestGenaiClientLlmIntent:
    def _make_genai_response_with_functions(
        self, function_names: list[str]
    ) -> tuple[SimpleNamespace, SimpleNamespace]:
        parts = [
            SimpleNamespace(
                function_call=SimpleNamespace(name=name, args={"key": "val"})
            )
            for name in function_names
        ]
        content = SimpleNamespace(parts=parts)
        candidate = SimpleNamespace(content=content, finish_reason="STOP")
        usage = SimpleNamespace(prompt_token_count=100, candidates_token_count=50)
        response = SimpleNamespace(candidates=[candidate], usage_metadata=usage)

        # Build fake google.genai.Client structure
        fake_client = SimpleNamespace()
        fake_client.models = SimpleNamespace()
        fake_client.models.generate_content = lambda **kw: response

        return fake_client, response

    def test_genai_emits_llm_intent_for_function_call(
        self, client: LangSightClient
    ) -> None:
        fake_genai, _ = self._make_genai_response_with_functions(["search"])
        captured = _capture_spans(client)

        proxy = GenaiClientProxy(fake_genai, client, agent_name="analyst")
        proxy.models.generate_content(model="gemini-2.5-flash", contents=[])

        intent_spans = [s for s in captured if s.span_type == "llm_intent"]
        assert len(intent_spans) == 1
        assert intent_spans[0].tool_name == "search"

    def test_genai_llm_intent_registered_in_pending_queue(
        self, client: LangSightClient
    ) -> None:
        fake_genai, _ = self._make_genai_response_with_functions(["get_orders"])
        _capture_spans(client)

        proxy = GenaiClientProxy(fake_genai, client, agent_name="order-agent")
        proxy.models.generate_content(model="gemini-2.5-flash", contents=[])

        ctx = claim_pending_tool("get_orders")
        assert ctx is not None
        assert ctx.agent_name == "order-agent"


# =============================================================================
# _maybe_emit_handoffs — called from all three processors
# =============================================================================


@pytest.fixture(autouse=True)
def _clean_ctx():
    """Reset contextvars around every test in this module."""
    _session_ctx.set(None)
    _agent_ctx.set(None)
    _trace_ctx.set(None)
    yield
    _session_ctx.set(None)
    _agent_ctx.set(None)
    _trace_ctx.set(None)


class TestOpenAIHandoffViaProcessor:
    """OpenAI _process_openai_response() calls _maybe_emit_handoffs() after
    registering llm_intent spans.  Verify the handoff span appears when the
    tool name matches a delegation pattern."""

    def _make_openai_response(self, tool_name: str) -> tuple[SimpleNamespace, SimpleNamespace]:
        tool_call = SimpleNamespace(
            function=SimpleNamespace(name=tool_name, arguments='{"task": "go"}')
        )
        message = SimpleNamespace(tool_calls=[tool_call], content=None)
        choice = SimpleNamespace(message=message, finish_reason="tool_calls")
        usage = SimpleNamespace(prompt_tokens=100, completion_tokens=40)
        response = SimpleNamespace(choices=[choice], model="gpt-4o", usage=usage)

        fake_client = SimpleNamespace()
        fake_client.chat = SimpleNamespace()
        fake_client.chat.completions = SimpleNamespace()
        fake_client.chat.completions.create = lambda **kw: response
        return fake_client, response

    def test_openai_call_analyst_emits_handoff_alongside_llm_intent(
        self, client: LangSightClient
    ) -> None:
        """OpenAI: call_analyst tool → both llm_intent and handoff spans emitted."""
        fake_client, _ = self._make_openai_response("call_analyst")
        tokens = set_context(agent_name="orchestrator")
        try:
            captured: list[ToolCallSpan] = []
            client.buffer_span = lambda s: captured.append(s)  # type: ignore[assignment]

            proxy = OpenAIProxy(fake_client, client, agent_name="orchestrator", session_id="s1")
            proxy.chat.completions.create(model="gpt-4o", messages=[])

            intent_spans = [s for s in captured if s.span_type == "llm_intent"]
            handoff_spans = [s for s in captured if s.span_type == "handoff"]

            assert len(intent_spans) == 1, "llm_intent span must still be emitted"
            assert intent_spans[0].tool_name == "call_analyst"

            assert len(handoff_spans) == 1, "handoff span must be auto-emitted"
            assert handoff_spans[0].target_agent_name == "analyst"
            assert handoff_spans[0].agent_name == "orchestrator"
        finally:
            clear_context(tokens)

    def test_openai_regular_tool_no_handoff_but_intent_present(
        self, client: LangSightClient
    ) -> None:
        """OpenAI: get_weather → llm_intent emitted, but no handoff span."""
        fake_client, _ = self._make_openai_response("get_weather")
        tokens = set_context(agent_name="orchestrator")
        try:
            captured: list[ToolCallSpan] = []
            client.buffer_span = lambda s: captured.append(s)  # type: ignore[assignment]

            proxy = OpenAIProxy(fake_client, client, agent_name="orchestrator", session_id="s1")
            proxy.chat.completions.create(model="gpt-4o", messages=[])

            handoff_spans = [s for s in captured if s.span_type == "handoff"]
            intent_spans = [s for s in captured if s.span_type == "llm_intent"]

            assert len(intent_spans) == 1
            assert len(handoff_spans) == 0
        finally:
            clear_context(tokens)


class TestAnthropicHandoffViaProcessor:
    """Anthropic _process_anthropic_response() calls _maybe_emit_handoffs()."""

    def _make_anthropic_response(self, tool_name: str) -> tuple[SimpleNamespace, SimpleNamespace]:
        block = SimpleNamespace(type="tool_use", name=tool_name, input={"task": "go"})
        usage = SimpleNamespace(input_tokens=100, output_tokens=40)
        response = SimpleNamespace(
            content=[block],
            model="claude-sonnet-4-6",
            usage=usage,
            stop_reason="tool_use",
        )
        fake_client = SimpleNamespace()
        fake_client.messages = SimpleNamespace()
        fake_client.messages.create = lambda **kw: response
        return fake_client, response

    def test_anthropic_delegate_worker_emits_handoff_alongside_llm_intent(
        self, client: LangSightClient
    ) -> None:
        """Anthropic: delegate_worker tool → both llm_intent and handoff spans emitted."""
        fake_client, _ = self._make_anthropic_response("delegate_worker")
        tokens = set_context(agent_name="supervisor")
        try:
            captured: list[ToolCallSpan] = []
            client.buffer_span = lambda s: captured.append(s)  # type: ignore[assignment]

            proxy = AnthropicProxy(fake_client, client, agent_name="supervisor", session_id="s2")
            proxy.messages.create(model="claude-sonnet-4-6", messages=[])

            intent_spans = [s for s in captured if s.span_type == "llm_intent"]
            handoff_spans = [s for s in captured if s.span_type == "handoff"]

            assert len(intent_spans) == 1
            assert intent_spans[0].tool_name == "delegate_worker"

            assert len(handoff_spans) == 1
            assert handoff_spans[0].target_agent_name == "worker"
            assert handoff_spans[0].agent_name == "supervisor"
        finally:
            clear_context(tokens)

    def test_anthropic_regular_tool_no_handoff(self, client: LangSightClient) -> None:
        """Anthropic: search_db → llm_intent but no handoff."""
        fake_client, _ = self._make_anthropic_response("search_db")
        tokens = set_context(agent_name="supervisor")
        try:
            captured: list[ToolCallSpan] = []
            client.buffer_span = lambda s: captured.append(s)  # type: ignore[assignment]

            proxy = AnthropicProxy(fake_client, client, agent_name="supervisor", session_id="s2")
            proxy.messages.create(model="claude-sonnet-4-6", messages=[])

            handoff_spans = [s for s in captured if s.span_type == "handoff"]
            assert len(handoff_spans) == 0
        finally:
            clear_context(tokens)


class TestGeminiHandoffViaProcessor:
    """Gemini _process_gemini_response() calls _maybe_emit_handoffs()."""

    def _make_gemini_response(self, tool_name: str) -> tuple[SimpleNamespace, SimpleNamespace]:
        fn_call = SimpleNamespace(name=tool_name, args={"task": "go"})
        part = SimpleNamespace(function_call=fn_call)
        content = SimpleNamespace(parts=[part])
        candidate = SimpleNamespace(content=content, finish_reason="STOP")
        usage = SimpleNamespace(prompt_token_count=100, candidates_token_count=40)
        response = SimpleNamespace(candidates=[candidate], usage_metadata=usage)
        fake_model = SimpleNamespace(model_name="gemini-2.5-flash")
        fake_model.generate_content = lambda *a, **kw: response
        return fake_model, response

    def test_gemini_invoke_billing_emits_handoff_alongside_llm_intent(
        self, client: LangSightClient
    ) -> None:
        """Gemini: invoke_billing tool → both llm_intent and handoff spans emitted."""
        fake_model, _ = self._make_gemini_response("invoke_billing")
        tokens = set_context(agent_name="planner")
        try:
            captured: list[ToolCallSpan] = []
            client.buffer_span = lambda s: captured.append(s)  # type: ignore[assignment]

            proxy = GeminiProxy(fake_model, client, agent_name="planner", session_id="s3")
            proxy.generate_content(contents=[])

            intent_spans = [s for s in captured if s.span_type == "llm_intent"]
            handoff_spans = [s for s in captured if s.span_type == "handoff"]

            assert len(intent_spans) == 1
            assert intent_spans[0].tool_name == "invoke_billing"

            assert len(handoff_spans) == 1
            assert handoff_spans[0].target_agent_name == "billing"
            assert handoff_spans[0].agent_name == "planner"
        finally:
            clear_context(tokens)

    def test_gemini_regular_tool_no_handoff(self, client: LangSightClient) -> None:
        """Gemini: list_products → llm_intent but no handoff."""
        fake_model, _ = self._make_gemini_response("list_products")
        tokens = set_context(agent_name="planner")
        try:
            captured: list[ToolCallSpan] = []
            client.buffer_span = lambda s: captured.append(s)  # type: ignore[assignment]

            proxy = GeminiProxy(fake_model, client, agent_name="planner", session_id="s3")
            proxy.generate_content(contents=[])

            handoff_spans = [s for s in captured if s.span_type == "handoff"]
            assert len(handoff_spans) == 0
        finally:
            clear_context(tokens)
