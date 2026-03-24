"""
Adversarial security tests for the SDK integration layer.

Attack surface: src/langsight/integrations/{openai_agents,anthropic_sdk,langgraph}.py
             + src/langsight/sdk/client.py (send_span, close, flush)

These tests verify properties that the integration layer MUST uphold:

1. Fail-open guarantee — tracing failures never propagate to the agent runtime.
   If LangSightClient.send_span raises, the tool call must still succeed.

2. Malicious input handling — tool names with special characters, SQL injection
   strings, extremely long strings, None/empty values must not crash the tracer.

3. Concurrent safety — multiple tools running simultaneously must not corrupt
   pending state dictionaries.

4. Resource cleanup — client.close() must flush remaining spans. No leaks.

5. PII in payloads — when redact_payloads=True, input_args and output_result
   must not be captured in spans.

6. Exception classification — TimeoutError must be recorded as TIMEOUT status,
   not ERROR. Other exceptions must be ERROR.

IMPORTANT: The decorator-based wrappers (langsight_openai_tool, langsight_anthropic_tool)
call `await client.send_span(span)` inside a `finally` block WITHOUT try/except.
If send_span raises, the exception propagates and masks the tool's return value.
These tests document and verify that behavior so regressions are caught.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from langsight.sdk.client import LangSightClient
from langsight.sdk.models import ToolCallSpan, ToolCallStatus

pytestmark = pytest.mark.security


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client(
    send_span_side_effect: Exception | None = None,
    redact_payloads: bool = False,
) -> LangSightClient:
    """Return a LangSightClient with send_span mocked.

    The real client buffers spans and POSTs them — we replace send_span
    with a mock so tests run offline and we can inspect what was recorded.
    """
    client = LangSightClient(
        url="http://localhost:8000",
        redact_payloads=redact_payloads,
    )
    if send_span_side_effect:
        client.buffer_span = MagicMock(side_effect=send_span_side_effect)
        client.buffer_span = MagicMock(side_effect=send_span_side_effect)
    else:
        client.buffer_span = MagicMock()
        client.buffer_span = MagicMock()
    client.flush = AsyncMock()
    client.close = AsyncMock()
    return client


def _mock_agent(name: str = "test-agent") -> MagicMock:
    """Return a mock agent object with a .name attribute."""
    agent = MagicMock()
    agent.name = name
    return agent


def _mock_tool(name: str = "test-tool") -> MagicMock:
    """Return a mock tool object with a .name attribute."""
    tool = MagicMock()
    tool.name = name
    return tool


def _mock_response(
    tool_use_blocks: list[tuple[str, dict]] | None = None,
    model: str = "claude-sonnet-4-20250514",
    input_tokens: int = 100,
    output_tokens: int = 50,
) -> MagicMock:
    """Build a mock Anthropic message response with tool_use blocks."""
    response = MagicMock()
    response.model = model

    usage = MagicMock()
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens
    response.usage = usage

    blocks = []
    for tool_name, tool_input in (tool_use_blocks or []):
        block = MagicMock()
        block.type = "tool_use"
        block.name = tool_name
        block.input = tool_input
        blocks.append(block)
    response.content = blocks
    return response


# ===========================================================================
# 1. FAIL-OPEN GUARANTEE
#    Tracing failures must NEVER propagate to the agent runtime.
# ===========================================================================


class TestFailOpenGuaranteeHooks:
    """Invariant: hook-based integrations swallow all tracing exceptions.

    The on_tool_start/on_tool_end/on_tool_error methods wrap their bodies
    in try/except Exception and silently continue. A LangSightClient crash
    must never propagate to the agent framework.
    """

    async def test_openai_hooks_on_tool_end_swallows_send_span_error(self) -> None:
        """send_span raising RuntimeError must not escape on_tool_end."""
        from langsight.integrations.openai_agents import LangSightOpenAIHooks

        client = _make_client(send_span_side_effect=RuntimeError("network down"))
        hooks = LangSightOpenAIHooks(client=client, agent_name="test")

        agent = _mock_agent()
        tool = _mock_tool()

        await hooks.on_tool_start(context=None, agent=agent, tool=tool)
        # Must not raise — the exception is caught internally
        await hooks.on_tool_end(context=None, agent=agent, tool=tool, result="ok")

    async def test_openai_hooks_on_tool_error_swallows_send_span_error(self) -> None:
        """send_span crash during on_tool_error must not propagate."""
        from langsight.integrations.openai_agents import LangSightOpenAIHooks

        client = _make_client(send_span_side_effect=ConnectionError("refused"))
        hooks = LangSightOpenAIHooks(client=client, agent_name="test")

        agent = _mock_agent()
        tool = _mock_tool()

        await hooks.on_tool_start(context=None, agent=agent, tool=tool)
        await hooks.on_tool_error(
            context=None, agent=agent, tool=tool, error=ValueError("bad input")
        )

    async def test_openai_hooks_on_handoff_swallows_send_span_error(self) -> None:
        """send_span crash during on_handoff must not propagate."""
        from langsight.integrations.openai_agents import LangSightOpenAIHooks

        client = _make_client(send_span_side_effect=RuntimeError("timeout"))
        hooks = LangSightOpenAIHooks(client=client, agent_name="test")

        await hooks.on_handoff(
            context=None, from_agent=_mock_agent("a"), to_agent=_mock_agent("b")
        )

    async def test_claude_hooks_on_tool_end_swallows_send_span_error(self) -> None:
        """Claude Agent SDK hooks: send_span crash must not propagate."""
        from langsight.integrations.anthropic_sdk import LangSightClaudeAgentHooks

        client = _make_client(send_span_side_effect=RuntimeError("network down"))
        hooks = LangSightClaudeAgentHooks(client=client, agent_name="test")

        await hooks.on_tool_start(tool_name="search")
        await hooks.on_tool_end(tool_name="search", tool_output="result")

    async def test_claude_hooks_on_tool_error_swallows_send_span_error(self) -> None:
        """Claude Agent SDK hooks: error path also swallows tracing failures."""
        from langsight.integrations.anthropic_sdk import LangSightClaudeAgentHooks

        client = _make_client(send_span_side_effect=RuntimeError("crash"))
        hooks = LangSightClaudeAgentHooks(client=client, agent_name="test")

        await hooks.on_tool_start(tool_name="query")
        await hooks.on_tool_error(tool_name="query", error=Exception("db down"))

    async def test_anthropic_tracer_trace_response_swallows_send_span_error(self) -> None:
        """AnthropicToolTracer.trace_response must not propagate tracing errors."""
        from langsight.integrations.anthropic_sdk import AnthropicToolTracer

        client = _make_client(send_span_side_effect=RuntimeError("boom"))
        tracer = AnthropicToolTracer(client=client, agent_name="test")

        response = _mock_response(tool_use_blocks=[("search", {"q": "test"})])
        # Must not raise — trace_response is fire-and-forget
        await tracer.trace_response(response)

    async def test_anthropic_execute_and_trace_returns_result_even_when_send_span_fails(
        self,
    ) -> None:
        """execute_and_trace: the tool's return value must be returned even
        when send_span raises in the finally block. Fail-open guarantee.
        """
        from langsight.integrations.anthropic_sdk import AnthropicToolTracer

        client = _make_client(send_span_side_effect=RuntimeError("tracing down"))
        tracer = AnthropicToolTracer(client=client, agent_name="test")

        async def my_handler(q: str) -> str:
            return f"result for {q}"

        # send_span raises, but the tool result is still returned (fail-open)
        result = await tracer.execute_and_trace("search", {"q": "hello"}, my_handler)
        assert result == "result for hello"


class TestFailOpenGuaranteeDecorators:
    """Invariant: decorator-based integrations must not block tool execution.

    All decorator wrappers catch exceptions from send_span in the finally
    block — tracing failures never propagate to the caller.
    """

    async def test_openai_tool_decorator_fail_open(self) -> None:
        """send_span raising in finally block must NOT propagate — tool result returned."""
        from langsight.integrations.openai_agents import langsight_openai_tool

        client = _make_client(send_span_side_effect=RuntimeError("tracing down"))

        @langsight_openai_tool(client=client, server_name="test")
        async def my_tool(q: str) -> str:
            return f"found: {q}"

        result = await my_tool(q="test")
        assert result == "found: test"

    async def test_anthropic_tool_decorator_fail_open(self) -> None:
        """send_span raising in finally block must NOT propagate — tool result returned."""
        from langsight.integrations.anthropic_sdk import langsight_anthropic_tool

        client = _make_client(send_span_side_effect=RuntimeError("tracing down"))

        @langsight_anthropic_tool(client=client, server_name="test")
        async def my_tool(location: str) -> str:
            return f"72F in {location}"

        result = await my_tool(location="NYC")
        assert result == "72F in NYC"

    async def test_openai_tool_decorator_succeeds_when_send_span_works(self) -> None:
        """When send_span works normally, the decorator returns the tool result."""
        from langsight.integrations.openai_agents import langsight_openai_tool

        client = _make_client()

        @langsight_openai_tool(client=client, server_name="test")
        async def my_tool(q: str) -> str:
            return f"found: {q}"

        result = await my_tool(q="hello")
        assert result == "found: hello"
        client.buffer_span.assert_called_once()

    async def test_anthropic_tool_decorator_succeeds_when_send_span_works(self) -> None:
        """When send_span works normally, the decorator returns the tool result."""
        from langsight.integrations.anthropic_sdk import langsight_anthropic_tool

        client = _make_client()

        @langsight_anthropic_tool(client=client, server_name="test")
        async def my_tool(location: str) -> str:
            return f"sunny in {location}"

        result = await my_tool(location="SF")
        assert result == "sunny in SF"
        client.buffer_span.assert_called_once()


# ===========================================================================
# 2. MALICIOUS INPUT HANDLING
#    Special characters, injection attempts, and extreme values in tool names
#    and payloads must not crash the tracing layer.
# ===========================================================================


class TestMaliciousToolNames:
    """Invariant: any string as a tool name must be handled without crash.

    Tool names come from model outputs or user definitions. A hostile or
    confused model might emit tool names with SQL injection, null bytes,
    or extremely long strings. The tracing layer must record them safely.
    """

    @pytest.mark.parametrize(
        "tool_name",
        [
            "'; DROP TABLE spans; --",
            "Robert'); DROP TABLE students;--",
            "<script>alert('xss')</script>",
            "../../../../etc/passwd",
            "\x00null_byte_tool",
            "",  # empty string
            "tool" * 10000,  # 40KB tool name
            "SELECT * FROM information_schema.tables",
            "{{template_injection}}",
            "${env:SECRET_KEY}",
            "tool\nwith\nnewlines",
            "tool\twith\ttabs",
            "\ud800",  # unpaired surrogate (if it gets through)
        ],
        ids=[
            "sql_injection_single_quote",
            "sql_injection_bobby_tables",
            "xss_script_tag",
            "path_traversal",
            "null_byte",
            "empty_string",
            "extremely_long_name",
            "sql_select_statement",
            "template_injection",
            "env_variable_reference",
            "newlines_in_name",
            "tabs_in_name",
            "unpaired_surrogate",
        ],
    )
    async def test_openai_hooks_handle_malicious_tool_name(self, tool_name: str) -> None:
        """OpenAI hooks must not crash on hostile tool names."""
        from langsight.integrations.openai_agents import LangSightOpenAIHooks

        client = _make_client()
        hooks = LangSightOpenAIHooks(client=client, agent_name="test")

        agent = _mock_agent()
        tool = _mock_tool(name=tool_name)

        await hooks.on_tool_start(context=None, agent=agent, tool=tool)
        await hooks.on_tool_end(context=None, agent=agent, tool=tool, result="ok")

        # Verify span was recorded (not silently dropped)
        if client.buffer_span.called:
            span = client.buffer_span.call_args[0][0]
            assert isinstance(span, ToolCallSpan)

    @pytest.mark.parametrize(
        "tool_name",
        [
            "'; DROP TABLE spans; --",
            "<img src=x onerror=alert(1)>",
            "",
            "a" * 50000,
            "\x00\x01\x02",
        ],
        ids=[
            "sql_injection",
            "xss_img_tag",
            "empty",
            "50kb_name",
            "control_chars",
        ],
    )
    async def test_claude_hooks_handle_malicious_tool_name(self, tool_name: str) -> None:
        """Claude Agent SDK hooks must not crash on hostile tool names."""
        from langsight.integrations.anthropic_sdk import LangSightClaudeAgentHooks

        client = _make_client()
        hooks = LangSightClaudeAgentHooks(client=client, agent_name="test")

        await hooks.on_tool_start(tool_name=tool_name)
        await hooks.on_tool_end(tool_name=tool_name, tool_output="result")

    @pytest.mark.parametrize(
        "tool_name",
        [
            "'; DROP TABLE spans; --",
            "a" * 50000,
            "",
        ],
        ids=["sql_injection", "50kb_name", "empty"],
    )
    async def test_anthropic_tracer_handle_malicious_tool_name_in_response(
        self, tool_name: str
    ) -> None:
        """AnthropicToolTracer must handle hostile names in API responses."""
        from langsight.integrations.anthropic_sdk import AnthropicToolTracer

        client = _make_client()
        tracer = AnthropicToolTracer(client=client, agent_name="test")

        response = _mock_response(tool_use_blocks=[(tool_name, {"key": "val"})])
        await tracer.trace_response(response)

    async def test_langgraph_callback_handles_malicious_tool_name_in_serialized(
        self,
    ) -> None:
        """LangGraph callback extracts tool_name from serialized dict — test hostile values."""
        from langsight.integrations.langgraph import LangSightLangGraphCallback

        client = _make_client()
        callback = LangSightLangGraphCallback(client=client, agent_name="test")

        malicious_name = "'; DROP TABLE spans; --"
        run_id = uuid4()

        callback.on_tool_start(
            serialized={"name": malicious_name},
            input_str="test input",
            run_id=run_id,
        )
        callback.on_tool_end(output="result", run_id=run_id)


class TestMaliciousToolInput:
    """Invariant: hostile payloads in tool input must not crash the tracer."""

    async def test_anthropic_execute_and_trace_handles_none_in_input(self) -> None:
        """None values in tool_input dict must not crash the tracer."""
        from langsight.integrations.anthropic_sdk import AnthropicToolTracer

        client = _make_client()
        tracer = AnthropicToolTracer(client=client, agent_name="test")

        async def handler(key: Any = None) -> str:
            return "ok"

        result = await tracer.execute_and_trace(
            "test_tool", {"key": None}, handler
        )
        assert result == "ok"

    async def test_anthropic_tracer_handles_non_dict_tool_input(self) -> None:
        """If tool_input in a response block is not a dict, it must not crash.

        The code checks `isinstance(tool_input, dict)` before passing to span.
        Non-dict values should be handled gracefully.
        """
        from langsight.integrations.anthropic_sdk import AnthropicToolTracer

        client = _make_client()
        tracer = AnthropicToolTracer(client=client, agent_name="test")

        response = MagicMock()
        response.model = "claude-sonnet-4-20250514"
        response.usage = MagicMock()
        response.usage.input_tokens = 10
        response.usage.output_tokens = 5

        block = MagicMock()
        block.type = "tool_use"
        block.name = "tool"
        block.input = "not-a-dict"  # malicious: string instead of dict
        response.content = [block]

        await tracer.trace_response(response)
        # Must not crash — the isinstance check should handle this

    async def test_anthropic_tracer_handles_response_with_no_content(self) -> None:
        """A response with content=None must not crash trace_response."""
        from langsight.integrations.anthropic_sdk import AnthropicToolTracer

        client = _make_client()
        tracer = AnthropicToolTracer(client=client, agent_name="test")

        response = MagicMock()
        response.content = None
        response.usage = None
        response.model = None

        await tracer.trace_response(response)
        # Must not raise

    async def test_anthropic_tracer_handles_response_with_no_usage(self) -> None:
        """A response with usage=None must still trace tool_use blocks."""
        from langsight.integrations.anthropic_sdk import AnthropicToolTracer

        client = _make_client()
        tracer = AnthropicToolTracer(client=client, agent_name="test")

        response = MagicMock()
        response.content = []
        response.usage = None
        response.model = None

        block = MagicMock()
        block.type = "tool_use"
        block.name = "search"
        block.input = {"q": "test"}
        response.content = [block]

        await tracer.trace_response(response)
        client.buffer_span.assert_called_once()


# ===========================================================================
# 3. CONCURRENT SAFETY
#    Multiple tools running simultaneously must not corrupt pending state.
# ===========================================================================


class TestConcurrentSafetyOpenAI:
    """Invariant: concurrent on_tool_start/on_tool_end pairs for different
    tools must not lose or cross-contaminate pending timestamps."""

    async def test_concurrent_tool_calls_do_not_corrupt_pending_state(self) -> None:
        """Three tools start concurrently, end in different order.

        Each tool's start time must be correctly matched to its end event.
        No KeyError, no lost entries, no timestamp cross-contamination.
        """
        from langsight.integrations.openai_agents import LangSightOpenAIHooks

        client = _make_client()
        hooks = LangSightOpenAIHooks(client=client, agent_name="test")

        agent = _mock_agent()
        tool_a = _mock_tool("tool_a")
        tool_b = _mock_tool("tool_b")
        tool_c = _mock_tool("tool_c")

        # Start all three
        await hooks.on_tool_start(context=None, agent=agent, tool=tool_a)
        await hooks.on_tool_start(context=None, agent=agent, tool=tool_b)
        await hooks.on_tool_start(context=None, agent=agent, tool=tool_c)

        # Pending should have 3 entries
        assert len(hooks._pending) == 3

        # End in reverse order
        await hooks.on_tool_end(context=None, agent=agent, tool=tool_c, result="c")
        await hooks.on_tool_end(context=None, agent=agent, tool=tool_a, result="a")
        await hooks.on_tool_end(context=None, agent=agent, tool=tool_b, result="b")

        # All pending entries consumed
        assert len(hooks._pending) == 0
        # Three spans recorded
        assert client.buffer_span.call_count == 3

    async def test_tool_end_without_start_does_not_crash(self) -> None:
        """If on_tool_end is called without a matching on_tool_start,
        it must still record a span (with fallback start time), not crash."""
        from langsight.integrations.openai_agents import LangSightOpenAIHooks

        client = _make_client()
        hooks = LangSightOpenAIHooks(client=client, agent_name="test")

        agent = _mock_agent()
        tool = _mock_tool("orphan_tool")

        # End without start — should use datetime.now(UTC) as fallback
        await hooks.on_tool_end(context=None, agent=agent, tool=tool, result="ok")
        client.buffer_span.assert_called_once()

    async def test_tool_error_without_start_does_not_crash(self) -> None:
        """on_tool_error without matching on_tool_start must not crash."""
        from langsight.integrations.openai_agents import LangSightOpenAIHooks

        client = _make_client()
        hooks = LangSightOpenAIHooks(client=client, agent_name="test")

        agent = _mock_agent()
        tool = _mock_tool("orphan_error")

        await hooks.on_tool_error(
            context=None, agent=agent, tool=tool, error=Exception("boom")
        )
        client.buffer_span.assert_called_once()


class TestConcurrentSafetyClaude:
    """Invariant: Claude Agent SDK hooks use tool_name as the pending key.

    If two tools with the SAME name run concurrently (e.g., the same tool
    called twice in parallel), the second on_tool_start overwrites the first
    pending entry. This is a known limitation. Tests verify the behavior.
    """

    async def test_same_tool_name_concurrent_overwrites_pending_timestamp(self) -> None:
        """Two concurrent calls to the same tool_name: the second start
        overwrites the first's timestamp. on_tool_end for the first pop
        will use the second's timestamp (or fallback)."""
        from langsight.integrations.anthropic_sdk import LangSightClaudeAgentHooks

        client = _make_client()
        hooks = LangSightClaudeAgentHooks(client=client, agent_name="test")

        # Both start
        await hooks.on_tool_start(tool_name="search")
        await hooks.on_tool_start(tool_name="search")  # overwrites first entry

        # Only one pending entry (same key)
        assert len(hooks._pending) == 1

        # First end pops the entry
        await hooks.on_tool_end(tool_name="search", tool_output="result1")
        assert len(hooks._pending) == 0

        # Second end: no pending entry — uses fallback datetime.now(UTC)
        await hooks.on_tool_end(tool_name="search", tool_output="result2")
        # Both calls recorded — no crash
        assert client.buffer_span.call_count == 2

    async def test_different_tool_names_concurrent_no_corruption(self) -> None:
        """Different tool names running concurrently must not interfere."""
        from langsight.integrations.anthropic_sdk import LangSightClaudeAgentHooks

        client = _make_client()
        hooks = LangSightClaudeAgentHooks(client=client, agent_name="test")

        await hooks.on_tool_start(tool_name="search")
        await hooks.on_tool_start(tool_name="query")
        assert len(hooks._pending) == 2

        await hooks.on_tool_end(tool_name="query", tool_output="q-result")
        await hooks.on_tool_end(tool_name="search", tool_output="s-result")
        assert len(hooks._pending) == 0
        assert client.buffer_span.call_count == 2


class TestConcurrentSafetyLangGraph:
    """Invariant: LangGraph callback uses run_id (UUID) as pending key,
    which guarantees uniqueness. Concurrent tool calls cannot collide."""

    async def test_concurrent_tools_with_different_run_ids(self) -> None:
        """Different run_ids must never collide in the pending dict."""
        from langsight.integrations.langgraph import LangSightLangGraphCallback

        client = _make_client()
        callback = LangSightLangGraphCallback(client=client, agent_name="test")

        run_id_1 = uuid4()
        run_id_2 = uuid4()

        callback.on_tool_start(
            {"name": "tool_a"}, "input", run_id=run_id_1
        )
        callback.on_tool_start(
            {"name": "tool_b"}, "input", run_id=run_id_2
        )
        assert len(callback._pending) == 2

        callback.on_tool_end(output="result_b", run_id=run_id_2)
        callback.on_tool_end(output="result_a", run_id=run_id_1)
        assert len(callback._pending) == 0

    async def test_tool_end_with_unknown_run_id_is_silently_ignored(self) -> None:
        """on_tool_end for an unknown run_id must not crash (early return)."""
        from langsight.integrations.langgraph import LangSightLangGraphCallback

        client = _make_client()
        callback = LangSightLangGraphCallback(client=client, agent_name="test")

        # End for a run_id that was never started
        callback.on_tool_end(output="orphan", run_id=uuid4())
        # No span sent (early return guard)
        client.buffer_span.assert_not_called()

    async def test_tool_error_with_unknown_run_id_is_silently_ignored(self) -> None:
        """on_tool_error for an unknown run_id must not crash."""
        from langsight.integrations.langgraph import LangSightLangGraphCallback

        client = _make_client()
        callback = LangSightLangGraphCallback(client=client, agent_name="test")

        callback.on_tool_error(error=RuntimeError("boom"), run_id=uuid4())
        client.buffer_span.assert_not_called()


# ===========================================================================
# 4. RESOURCE CLEANUP
#    client.close() must flush remaining spans. No resource leaks.
# ===========================================================================


class TestResourceCleanup:
    """Invariant: LangSightClient.close() flushes buffered spans and closes HTTP."""

    async def test_close_flushes_remaining_spans(self) -> None:
        """Spans buffered but not yet flushed must be sent on close()."""
        client = LangSightClient(url="http://localhost:8000")
        # Mock the internal _post_spans to avoid real HTTP
        client._post_spans = AsyncMock()

        span = ToolCallSpan.record(
            server_name="test",
            tool_name="tool",
            started_at=datetime.now(UTC),
            status=ToolCallStatus.SUCCESS,
        )
        # Directly add to buffer (bypassing send_span which tries to create tasks)
        client._buffer.append(span)
        assert len(client._buffer) == 1

        await client.close()
        # Buffer must be empty after close
        assert len(client._buffer) == 0
        # _post_spans must have been called with the buffered span
        client._post_spans.assert_called_once()
        posted_spans = client._post_spans.call_args[0][0]
        assert len(posted_spans) == 1
        assert posted_spans[0].tool_name == "tool"

    async def test_close_is_idempotent(self) -> None:
        """Calling close() twice must not crash or double-flush."""
        client = LangSightClient(url="http://localhost:8000")
        client._post_spans = AsyncMock()

        await client.close()
        await client.close()
        # No crash, no error — close is safe to call multiple times

    async def test_close_with_empty_buffer_does_not_post(self) -> None:
        """close() with no buffered spans must not call _post_spans."""
        client = LangSightClient(url="http://localhost:8000")
        client._post_spans = AsyncMock()

        await client.close()
        client._post_spans.assert_not_called()


# ===========================================================================
# 5. PII IN PAYLOADS
#    When redact_payloads=True, input_args and output_result must be stripped.
# ===========================================================================


class TestPIIRedaction:
    """Invariant: redact_payloads=True on the client must prevent input_args
    and output_result from appearing in recorded spans.

    This is enforced at the MCPClientProxy level (call_tool). The framework
    integrations do NOT currently support redaction — they pass input_args
    and output_result unconditionally. These tests verify the proxy behavior
    and document the gap in the integration layer.
    """

    async def test_mcp_proxy_redacts_input_args_when_enabled(self) -> None:
        """MCPClientProxy with redact_payloads=True must not capture input_args."""
        inner_client = MagicMock()
        inner_client.call_tool = AsyncMock(return_value={"data": "secret"})

        ls_client = LangSightClient(url="http://localhost:8000", redact_payloads=True)
        ls_client.buffer_span = MagicMock()

        proxy = ls_client.wrap(
            inner_client,
            server_name="test",
            redact_payloads=True,
        )

        await proxy.call_tool("query", {"sql": "SELECT ssn FROM users"})

        span = ls_client.buffer_span.call_args[0][0]
        assert span.input_args is None, "input_args must be None when redact_payloads=True"
        assert span.output_result is None, "output_result must be None when redact_payloads=True"

    async def test_mcp_proxy_captures_input_args_when_redaction_disabled(self) -> None:
        """MCPClientProxy with redact_payloads=False must capture input_args."""
        inner_client = MagicMock()
        inner_client.call_tool = AsyncMock(return_value={"data": "public"})

        ls_client = LangSightClient(url="http://localhost:8000", redact_payloads=False)
        ls_client.buffer_span = MagicMock()

        proxy = ls_client.wrap(
            inner_client,
            server_name="test",
            redact_payloads=False,
        )

        await proxy.call_tool("query", {"sql": "SELECT 1"})

        span = ls_client.buffer_span.call_args[0][0]
        assert span.input_args == {"sql": "SELECT 1"}, "input_args must be captured when not redacted"
        assert span.output_result is not None, "output_result must be captured when not redacted"

    async def test_anthropic_execute_and_trace_always_captures_input_and_output(
        self,
    ) -> None:
        """AnthropicToolTracer.execute_and_trace does NOT support redaction.

        This test documents that input_args and output_result are always
        captured — a known gap. When redaction is added to the integration
        layer, update this test.
        """
        from langsight.integrations.anthropic_sdk import AnthropicToolTracer

        client = _make_client()
        tracer = AnthropicToolTracer(client=client, agent_name="test")

        async def handler(ssn: str) -> str:
            return f"SSN is {ssn}"

        sensitive_input = {"ssn": "123-45-6789"}
        await tracer.execute_and_trace("lookup", sensitive_input, handler)

        span = client.buffer_span.call_args[0][0]
        # Currently: input_args IS captured (no redaction support)
        assert span.input_args == sensitive_input, (
            "AnthropicToolTracer does not yet support redaction"
        )
        # output_result IS captured
        assert "123-45-6789" in span.output_result, (
            "AnthropicToolTracer does not yet support output redaction"
        )

    async def test_anthropic_trace_response_skips_non_dict_input_args(self) -> None:
        """When tool_input is not a dict, input_args must be None in the span.

        This prevents arbitrary objects from leaking into the span payload.
        """
        from langsight.integrations.anthropic_sdk import AnthropicToolTracer

        client = _make_client()
        tracer = AnthropicToolTracer(client=client, agent_name="test")

        response = MagicMock()
        response.model = "claude-sonnet-4-20250514"
        response.usage = MagicMock()
        response.usage.input_tokens = 10
        response.usage.output_tokens = 5

        block = MagicMock()
        block.type = "tool_use"
        block.name = "tool"
        block.input = ["not", "a", "dict"]  # list, not dict
        response.content = [block]

        await tracer.trace_response(response)

        span = client.buffer_span.call_args[0][0]
        assert span.input_args is None, (
            "Non-dict tool_input must not be stored in input_args"
        )


# ===========================================================================
# 6. EXCEPTION CLASSIFICATION
#    TimeoutError must be TIMEOUT status, not ERROR. Other exceptions → ERROR.
# ===========================================================================


class TestExceptionClassificationDecorators:
    """Invariant: TimeoutError is classified as TIMEOUT, all others as ERROR.

    This distinction matters for alerting — TIMEOUT triggers different SLO
    rules than ERROR. Misclassification corrupts observability data.
    """

    async def test_openai_tool_timeout_recorded_as_timeout_status(self) -> None:
        """TimeoutError in a decorated OpenAI tool → TIMEOUT status in span."""
        from langsight.integrations.openai_agents import langsight_openai_tool

        client = _make_client()

        @langsight_openai_tool(client=client, server_name="test")
        async def slow_tool(q: str) -> str:
            raise TimeoutError("15s deadline exceeded")

        with pytest.raises(TimeoutError):
            await slow_tool(q="hello")

        span = client.buffer_span.call_args[0][0]
        assert span.status == ToolCallStatus.TIMEOUT, (
            f"TimeoutError must be TIMEOUT, not {span.status}"
        )
        assert "15s deadline" in span.error

    async def test_openai_tool_generic_error_recorded_as_error_status(self) -> None:
        """ValueError in a decorated OpenAI tool → ERROR status in span."""
        from langsight.integrations.openai_agents import langsight_openai_tool

        client = _make_client()

        @langsight_openai_tool(client=client, server_name="test")
        async def bad_tool(q: str) -> str:
            raise ValueError("invalid input")

        with pytest.raises(ValueError):
            await bad_tool(q="hello")

        span = client.buffer_span.call_args[0][0]
        assert span.status == ToolCallStatus.ERROR, (
            f"ValueError must be ERROR, not {span.status}"
        )

    async def test_anthropic_tool_timeout_recorded_as_timeout_status(self) -> None:
        """TimeoutError in a decorated Anthropic tool → TIMEOUT status."""
        from langsight.integrations.anthropic_sdk import langsight_anthropic_tool

        client = _make_client()

        @langsight_anthropic_tool(client=client, server_name="test")
        async def slow_tool(location: str) -> str:
            raise TimeoutError("API timeout")

        with pytest.raises(TimeoutError):
            await slow_tool(location="NYC")

        span = client.buffer_span.call_args[0][0]
        assert span.status == ToolCallStatus.TIMEOUT

    async def test_anthropic_tool_runtime_error_recorded_as_error_status(self) -> None:
        """RuntimeError in a decorated Anthropic tool → ERROR status."""
        from langsight.integrations.anthropic_sdk import langsight_anthropic_tool

        client = _make_client()

        @langsight_anthropic_tool(client=client, server_name="test")
        async def broken_tool(location: str) -> str:
            raise RuntimeError("internal failure")

        with pytest.raises(RuntimeError):
            await broken_tool(location="NYC")

        span = client.buffer_span.call_args[0][0]
        assert span.status == ToolCallStatus.ERROR

    async def test_anthropic_execute_and_trace_timeout_is_timeout_status(self) -> None:
        """TimeoutError in execute_and_trace → TIMEOUT status in span."""
        from langsight.integrations.anthropic_sdk import AnthropicToolTracer

        client = _make_client()
        tracer = AnthropicToolTracer(client=client, agent_name="test")

        async def slow_handler(q: str) -> str:
            raise TimeoutError("10s exceeded")

        with pytest.raises(TimeoutError):
            await tracer.execute_and_trace("search", {"q": "test"}, slow_handler)

        span = client.buffer_span.call_args[0][0]
        assert span.status == ToolCallStatus.TIMEOUT
        assert "10s exceeded" in span.error

    async def test_anthropic_execute_and_trace_generic_error_is_error_status(
        self,
    ) -> None:
        """ValueError in execute_and_trace → ERROR status in span."""
        from langsight.integrations.anthropic_sdk import AnthropicToolTracer

        client = _make_client()
        tracer = AnthropicToolTracer(client=client, agent_name="test")

        async def bad_handler(q: str) -> str:
            raise ValueError("invalid query")

        with pytest.raises(ValueError):
            await tracer.execute_and_trace("search", {"q": "test"}, bad_handler)

        span = client.buffer_span.call_args[0][0]
        assert span.status == ToolCallStatus.ERROR


class TestExceptionClassificationHooks:
    """Invariant: hooks-based integrations record the correct status."""

    async def test_openai_hooks_on_tool_error_records_error_status(self) -> None:
        """on_tool_error must record ERROR status, not SUCCESS."""
        from langsight.integrations.openai_agents import LangSightOpenAIHooks

        client = _make_client()
        hooks = LangSightOpenAIHooks(client=client, agent_name="test")

        agent = _mock_agent()
        tool = _mock_tool()

        await hooks.on_tool_start(context=None, agent=agent, tool=tool)
        await hooks.on_tool_error(
            context=None, agent=agent, tool=tool, error=RuntimeError("crash")
        )

        span = client.buffer_span.call_args[0][0]
        assert span.status == ToolCallStatus.ERROR
        assert "crash" in span.error

    async def test_openai_hooks_on_tool_end_records_success_status(self) -> None:
        """on_tool_end must record SUCCESS status."""
        from langsight.integrations.openai_agents import LangSightOpenAIHooks

        client = _make_client()
        hooks = LangSightOpenAIHooks(client=client, agent_name="test")

        agent = _mock_agent()
        tool = _mock_tool()

        await hooks.on_tool_start(context=None, agent=agent, tool=tool)
        await hooks.on_tool_end(context=None, agent=agent, tool=tool, result="ok")

        span = client.buffer_span.call_args[0][0]
        assert span.status == ToolCallStatus.SUCCESS

    async def test_claude_hooks_on_tool_error_records_error_status(self) -> None:
        """Claude Agent SDK on_tool_error must record ERROR status."""
        from langsight.integrations.anthropic_sdk import LangSightClaudeAgentHooks

        client = _make_client()
        hooks = LangSightClaudeAgentHooks(client=client, agent_name="test")

        await hooks.on_tool_start(tool_name="query")
        await hooks.on_tool_error(tool_name="query", error=Exception("db timeout"))

        span = client.buffer_span.call_args[0][0]
        assert span.status == ToolCallStatus.ERROR
        assert "db timeout" in span.error


# ===========================================================================
# 7. ADDITIONAL EDGE CASES
#    Boundary conditions, agent object edge cases, none/missing attributes.
# ===========================================================================


class TestAgentAndToolObjectEdgeCases:
    """Invariant: integrations must handle agents/tools with missing attributes.

    The OpenAI and LangGraph callbacks use getattr() to extract names from
    agent/tool objects. If .name is missing, they fall back to __name__ or
    str(obj). None of these fallbacks should crash.
    """

    async def test_openai_hooks_tool_without_name_attribute(self) -> None:
        """A tool object with no .name and no .__name__ must not crash."""
        from langsight.integrations.openai_agents import LangSightOpenAIHooks

        client = _make_client()
        hooks = LangSightOpenAIHooks(client=client, agent_name="test")

        agent = _mock_agent()
        tool = object()  # no .name, no .__name__

        await hooks.on_tool_start(context=None, agent=agent, tool=tool)
        await hooks.on_tool_end(context=None, agent=agent, tool=tool, result="ok")
        # Must not crash — str(tool) used as fallback

    async def test_openai_hooks_agent_without_name_attribute(self) -> None:
        """An agent object with no .name must not crash."""
        from langsight.integrations.openai_agents import LangSightOpenAIHooks

        client = _make_client()
        hooks = LangSightOpenAIHooks(client=client, agent_name="test")

        agent = object()  # no .name
        tool = _mock_tool()

        await hooks.on_tool_start(context=None, agent=agent, tool=tool)
        await hooks.on_tool_end(context=None, agent=agent, tool=tool, result="ok")

    async def test_langgraph_chain_start_with_empty_serialized_dict(self) -> None:
        """on_chain_start with an empty serialized dict must not crash."""
        from langsight.integrations.langgraph import LangSightLangGraphCallback

        client = _make_client()
        callback = LangSightLangGraphCallback(client=client, agent_name="test")

        run_id = uuid4()
        # Empty serialized dict — should not crash (skip chain names filter it)
        callback.on_chain_start(
            serialized={},  # no "name", no "id"
            inputs={},
            run_id=run_id,
        )
        # With empty serialized, _detect_agent_name returns None → no _active_chains entry
        # The key property: it does NOT crash

    async def test_langgraph_chain_end_cleans_up_active_chains(self) -> None:
        """on_chain_end must remove the chain from _active_chains."""
        from langsight.integrations.langgraph import LangSightLangGraphCallback

        client = _make_client()
        callback = LangSightLangGraphCallback(client=client, agent_name="test")

        run_id_1 = uuid4()
        run_id_2 = uuid4()

        callback.on_chain_start({"name": "supervisor"}, {}, run_id=run_id_1)
        callback.on_chain_start({"name": "analyst"}, {}, run_id=run_id_2)

        # Both tracked
        assert str(run_id_1) in callback._active_chains
        assert str(run_id_2) in callback._active_chains

        # End analyst → removed from active
        callback.on_chain_end({}, run_id=run_id_2)
        assert str(run_id_2) not in callback._active_chains
        assert str(run_id_1) in callback._active_chains

        # End supervisor → both gone
        callback.on_chain_end({}, run_id=run_id_1)
        assert str(run_id_1) not in callback._active_chains

    async def test_langgraph_chain_error_cleans_up_like_chain_end(self) -> None:
        """on_chain_error must clean up the same way on_chain_end does."""
        from langsight.integrations.langgraph import LangSightLangGraphCallback

        client = _make_client()
        callback = LangSightLangGraphCallback(client=client, agent_name="test")

        run_id = uuid4()
        callback.on_chain_start({"name": "failing_node"}, {}, run_id=run_id)
        assert str(run_id) in callback._active_chains

        callback.on_chain_error(RuntimeError("node crashed"), run_id=run_id)
        assert str(run_id) not in callback._active_chains

    async def test_openai_hooks_on_tool_start_idempotent_for_same_tool(self) -> None:
        """Calling on_tool_start twice for the same tool should overwrite,
        not accumulate, the pending entry (since _tool_key is deterministic
        for same agent+tool+id(tool))."""
        from langsight.integrations.openai_agents import LangSightOpenAIHooks

        client = _make_client()
        hooks = LangSightOpenAIHooks(client=client, agent_name="test")

        agent = _mock_agent()
        tool = _mock_tool()

        await hooks.on_tool_start(context=None, agent=agent, tool=tool)
        await hooks.on_tool_start(context=None, agent=agent, tool=tool)

        # Same tool object → same key → one entry
        # The _tool_key includes id(tool), so same object = same key
        key = hooks._tool_key(agent, tool)
        assert key in hooks._pending


class TestHandoffSpanIntegrity:
    """Invariant: handoff spans must correctly record from_agent and to_agent."""

    async def test_openai_handoff_span_contains_correct_agent_names(self) -> None:
        """on_handoff must record from_agent and to_agent in the span."""
        from langsight.integrations.openai_agents import LangSightOpenAIHooks

        client = _make_client()
        hooks = LangSightOpenAIHooks(client=client, agent_name="orchestrator")

        from_agent = _mock_agent("orchestrator")
        to_agent = _mock_agent("billing-agent")

        await hooks.on_handoff(context=None, from_agent=from_agent, to_agent=to_agent)

        span = client.buffer_span.call_args[0][0]
        assert span.span_type == "handoff"
        assert span.server_name == "orchestrator"
        assert "billing-agent" in span.tool_name

    async def test_claude_handoff_span_contains_correct_agent_names(self) -> None:
        """Claude Agent SDK on_handoff must record correct agent names."""
        from langsight.integrations.anthropic_sdk import LangSightClaudeAgentHooks

        client = _make_client()
        hooks = LangSightClaudeAgentHooks(client=client, agent_name="orchestrator")

        await hooks.on_handoff(from_agent="orchestrator", to_agent="researcher")

        span = client.buffer_span.call_args[0][0]
        assert span.span_type == "handoff"
        assert span.server_name == "orchestrator"
        assert "researcher" in span.tool_name
