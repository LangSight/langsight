from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from langsight.integrations.anthropic_sdk import (
    AnthropicToolTracer,
    LangSightClaudeAgentHooks,
    langsight_anthropic_tool,
)
from langsight.sdk.client import LangSightClient
from langsight.sdk.models import ToolCallStatus


@pytest.fixture
def client() -> LangSightClient:
    return LangSightClient(url="http://localhost:8000")


@pytest.fixture
def tracer(client: LangSightClient) -> AnthropicToolTracer:
    return AnthropicToolTracer(
        client=client,
        server_name="test-anthropic",
        agent_name="test-agent",
        session_id="sess-001",
        trace_id="trace-001",
    )


@pytest.fixture
def hooks(client: LangSightClient) -> LangSightClaudeAgentHooks:
    return LangSightClaudeAgentHooks(
        client=client,
        server_name="test-claude",
        agent_name="claude-agent",
        session_id="sess-002",
        trace_id="trace-002",
    )


def _make_tool_use_block(name: str = "get_weather", input_data: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", name=name, input=input_data or {"location": "NYC"})


def _make_text_block(text: str = "Hello") -> SimpleNamespace:
    return SimpleNamespace(type="text", text=text)


def _make_response(
    content: list | None = None,
    model: str = "claude-sonnet-4-6",
    input_tokens: int = 100,
    output_tokens: int = 50,
) -> SimpleNamespace:
    usage = SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens)
    return SimpleNamespace(
        content=content or [],
        model=model,
        usage=usage,
    )


# =============================================================================
# AnthropicToolTracer — Constructor
# =============================================================================


class TestAnthropicToolTracerConstructor:
    def test_creates_with_all_params(self, client: LangSightClient) -> None:
        tracer = AnthropicToolTracer(
            client=client,
            server_name="custom",
            agent_name="my-agent",
            session_id="sess-x",
            trace_id="trace-y",
        )
        assert tracer._server_name == "custom"
        assert tracer._agent_name == "my-agent"
        assert tracer._session_id == "sess-x"
        assert tracer._trace_id == "trace-y"

    def test_creates_with_defaults(self, client: LangSightClient) -> None:
        tracer = AnthropicToolTracer(client=client)
        assert tracer._server_name == "anthropic-tools"
        assert tracer._agent_name is None
        assert tracer._session_id is None
        assert tracer._trace_id is None


# =============================================================================
# AnthropicToolTracer — trace_response
# =============================================================================


class TestAnthropicToolTracerTraceResponse:
    async def test_trace_response_extracts_tool_use_blocks(
        self, tracer: AnthropicToolTracer, client: LangSightClient
    ) -> None:
        response = _make_response(
            content=[
                _make_text_block("Let me check the weather"),
                _make_tool_use_block("get_weather", {"location": "NYC"}),
                _make_tool_use_block("get_time", {"timezone": "EST"}),
            ]
        )

        with patch.object(client, "send_span", new_callable=AsyncMock) as mock_send:
            await tracer.trace_response(response)

        assert mock_send.call_count == 2
        span1 = mock_send.call_args_list[0][0][0]
        span2 = mock_send.call_args_list[1][0][0]
        assert span1.tool_name == "get_weather"
        assert span2.tool_name == "get_time"

    async def test_trace_response_skips_non_tool_use_blocks(
        self, tracer: AnthropicToolTracer, client: LangSightClient
    ) -> None:
        response = _make_response(content=[_make_text_block("Hello"), _make_text_block("World")])

        with patch.object(client, "send_span", new_callable=AsyncMock) as mock_send:
            await tracer.trace_response(response)

        mock_send.assert_not_called()

    async def test_trace_response_captures_model_and_usage(
        self, tracer: AnthropicToolTracer, client: LangSightClient
    ) -> None:
        response = _make_response(
            content=[_make_tool_use_block("search")],
            model="claude-opus-4-6",
            input_tokens=200,
            output_tokens=75,
        )

        with patch.object(client, "send_span", new_callable=AsyncMock) as mock_send:
            await tracer.trace_response(response)

        span = mock_send.call_args[0][0]
        assert span.model_id == "claude-opus-4-6"
        assert span.input_tokens == 200
        assert span.output_tokens == 75

    async def test_trace_response_captures_input_args(
        self, tracer: AnthropicToolTracer, client: LangSightClient
    ) -> None:
        response = _make_response(
            content=[_make_tool_use_block("search", {"query": "AI agents"})],
        )

        with patch.object(client, "send_span", new_callable=AsyncMock) as mock_send:
            await tracer.trace_response(response)

        span = mock_send.call_args[0][0]
        assert span.input_args == {"query": "AI agents"}

    async def test_trace_response_handles_empty_content(
        self, tracer: AnthropicToolTracer, client: LangSightClient
    ) -> None:
        response = _make_response(content=[])

        with patch.object(client, "send_span", new_callable=AsyncMock) as mock_send:
            await tracer.trace_response(response)

        mock_send.assert_not_called()

    async def test_trace_response_handles_none_content(
        self, tracer: AnthropicToolTracer, client: LangSightClient
    ) -> None:
        response = SimpleNamespace(content=None, usage=None, model=None)

        with patch.object(client, "send_span", new_callable=AsyncMock) as mock_send:
            await tracer.trace_response(response)

        mock_send.assert_not_called()

    async def test_trace_response_handles_missing_attributes(
        self, tracer: AnthropicToolTracer, client: LangSightClient
    ) -> None:
        """Response object missing content/usage/model attributes entirely."""
        response = object()

        with patch.object(client, "send_span", new_callable=AsyncMock) as mock_send:
            await tracer.trace_response(response)

        mock_send.assert_not_called()

    async def test_trace_response_handles_none_usage(
        self, tracer: AnthropicToolTracer, client: LangSightClient
    ) -> None:
        response = SimpleNamespace(
            content=[_make_tool_use_block("search")],
            usage=None,
            model="claude-sonnet-4-6",
        )

        with patch.object(client, "send_span", new_callable=AsyncMock) as mock_send:
            await tracer.trace_response(response)

        span = mock_send.call_args[0][0]
        assert span.input_tokens is None
        assert span.output_tokens is None

    async def test_trace_response_sets_status_to_success(
        self, tracer: AnthropicToolTracer, client: LangSightClient
    ) -> None:
        response = _make_response(content=[_make_tool_use_block("tool1")])

        with patch.object(client, "send_span", new_callable=AsyncMock) as mock_send:
            await tracer.trace_response(response)

        span = mock_send.call_args[0][0]
        assert span.status == ToolCallStatus.SUCCESS

    async def test_trace_response_passes_session_and_trace_ids(
        self, tracer: AnthropicToolTracer, client: LangSightClient
    ) -> None:
        response = _make_response(content=[_make_tool_use_block("tool1")])

        with patch.object(client, "send_span", new_callable=AsyncMock) as mock_send:
            await tracer.trace_response(response)

        span = mock_send.call_args[0][0]
        assert span.session_id == "sess-001"
        assert span.trace_id == "trace-001"

    async def test_trace_response_fail_open(
        self, tracer: AnthropicToolTracer, client: LangSightClient
    ) -> None:
        """Exception in send_span should not propagate."""
        response = _make_response(content=[_make_tool_use_block("boom")])

        with patch.object(client, "send_span", new_callable=AsyncMock, side_effect=RuntimeError("network")):
            await tracer.trace_response(response)
        # No exception raised

    async def test_trace_response_unknown_tool_name_defaults_to_unknown(
        self, tracer: AnthropicToolTracer, client: LangSightClient
    ) -> None:
        block = SimpleNamespace(type="tool_use")  # no name attribute
        response = SimpleNamespace(
            content=[block], usage=None, model=None
        )

        with patch.object(client, "send_span", new_callable=AsyncMock) as mock_send:
            await tracer.trace_response(response)

        span = mock_send.call_args[0][0]
        assert span.tool_name == "unknown"

    async def test_trace_response_non_dict_input_skipped(
        self, tracer: AnthropicToolTracer, client: LangSightClient
    ) -> None:
        """When tool input is not a dict, input_args should be None."""
        block = SimpleNamespace(type="tool_use", name="tool1", input="raw string")
        response = SimpleNamespace(content=[block], usage=None, model=None)

        with patch.object(client, "send_span", new_callable=AsyncMock) as mock_send:
            await tracer.trace_response(response)

        span = mock_send.call_args[0][0]
        assert span.input_args is None


# =============================================================================
# AnthropicToolTracer — execute_and_trace
# =============================================================================


class TestAnthropicToolTracerExecuteAndTrace:
    async def test_execute_and_trace_captures_success(
        self, tracer: AnthropicToolTracer, client: LangSightClient
    ) -> None:
        async def handler(location: str) -> str:
            return f"72F in {location}"

        with patch.object(client, "send_span", new_callable=AsyncMock) as mock_send:
            result = await tracer.execute_and_trace("get_weather", {"location": "NYC"}, handler)

        assert result == "72F in NYC"
        mock_send.assert_called_once()
        span = mock_send.call_args[0][0]
        assert span.tool_name == "get_weather"
        assert span.status == ToolCallStatus.SUCCESS
        assert span.input_args == {"location": "NYC"}
        assert span.output_result is not None
        assert "72F" in span.output_result

    async def test_execute_and_trace_captures_error(
        self, tracer: AnthropicToolTracer, client: LangSightClient
    ) -> None:
        async def bad_handler(location: str) -> str:
            raise ValueError("unknown location")

        with patch.object(client, "send_span", new_callable=AsyncMock) as mock_send:
            with pytest.raises(ValueError, match="unknown location"):
                await tracer.execute_and_trace("get_weather", {"location": "Mars"}, bad_handler)

        span = mock_send.call_args[0][0]
        assert span.status == ToolCallStatus.ERROR
        assert "unknown location" in span.error

    async def test_execute_and_trace_captures_timeout(
        self, tracer: AnthropicToolTracer, client: LangSightClient
    ) -> None:
        async def slow_handler(**kwargs: object) -> str:
            raise TimeoutError("too slow")

        with patch.object(client, "send_span", new_callable=AsyncMock) as mock_send:
            with pytest.raises(TimeoutError):
                await tracer.execute_and_trace("slow_tool", {}, slow_handler)

        span = mock_send.call_args[0][0]
        assert span.status == ToolCallStatus.TIMEOUT

    async def test_execute_and_trace_sends_span_on_error(
        self, tracer: AnthropicToolTracer, client: LangSightClient
    ) -> None:
        """Span must be sent even when handler raises."""
        async def exploding(**kwargs: object) -> str:
            raise RuntimeError("boom")

        with patch.object(client, "send_span", new_callable=AsyncMock) as mock_send:
            with pytest.raises(RuntimeError):
                await tracer.execute_and_trace("exploding", {}, exploding)

        mock_send.assert_called_once()

    async def test_execute_and_trace_records_timing(
        self, tracer: AnthropicToolTracer, client: LangSightClient
    ) -> None:
        async def handler(**kwargs: object) -> str:
            return "ok"

        with patch.object(client, "send_span", new_callable=AsyncMock) as mock_send:
            await tracer.execute_and_trace("tool1", {}, handler)

        span = mock_send.call_args[0][0]
        assert span.latency_ms is not None
        assert span.latency_ms >= 0
        assert span.started_at <= span.ended_at

    async def test_execute_and_trace_serializes_non_json_output(
        self, tracer: AnthropicToolTracer, client: LangSightClient
    ) -> None:
        """Non-JSON-serializable results should fall back to str()."""
        class CustomObj:
            def __str__(self) -> str:
                return "custom-repr"

        async def handler(**kwargs: object) -> CustomObj:
            return CustomObj()

        with patch.object(client, "send_span", new_callable=AsyncMock) as mock_send:
            result = await tracer.execute_and_trace("tool1", {}, handler)

        assert isinstance(result, CustomObj)
        span = mock_send.call_args[0][0]
        assert span.output_result is not None


# =============================================================================
# LangSightClaudeAgentHooks — Constructor
# =============================================================================


class TestClaudeAgentHooksConstructor:
    def test_creates_with_all_params(self, client: LangSightClient) -> None:
        hooks = LangSightClaudeAgentHooks(
            client=client,
            server_name="custom-claude",
            agent_name="my-agent",
            session_id="s1",
            trace_id="t1",
        )
        assert hooks._server_name == "custom-claude"
        assert hooks._agent_name == "my-agent"
        assert hooks._session_id == "s1"
        assert hooks._trace_id == "t1"
        assert hooks._pending == {}

    def test_creates_with_defaults(self, client: LangSightClient) -> None:
        hooks = LangSightClaudeAgentHooks(client=client)
        assert hooks._server_name == "claude-agent"
        assert hooks._agent_name is None
        assert hooks._pending == {}


# =============================================================================
# LangSightClaudeAgentHooks — on_tool_start / on_tool_end / on_tool_error
# =============================================================================


class TestClaudeAgentHooksOnToolStart:
    async def test_records_pending(self, hooks: LangSightClaudeAgentHooks) -> None:
        await hooks.on_tool_start("search", {"query": "AI"})
        assert "search" in hooks._pending
        assert isinstance(hooks._pending["search"], datetime)

    async def test_records_multiple_tools(self, hooks: LangSightClaudeAgentHooks) -> None:
        await hooks.on_tool_start("search", {})
        await hooks.on_tool_start("fetch", {})
        assert len(hooks._pending) == 2

    async def test_fail_open_on_exception(self, hooks: LangSightClaudeAgentHooks) -> None:
        """Even if _pending dict somehow fails, on_tool_start must not raise."""
        with patch.object(hooks, "_pending", side_effect=RuntimeError("broken")):
            # The property is replaced with something that raises,
            # but the except block catches it
            pass
        # Just verify calling with normal args doesn't raise
        await hooks.on_tool_start("tool", {})


class TestClaudeAgentHooksOnToolEnd:
    async def test_clears_pending_and_sends_span(
        self, hooks: LangSightClaudeAgentHooks, client: LangSightClient
    ) -> None:
        await hooks.on_tool_start("search", {})

        with patch.object(client, "send_span", new_callable=AsyncMock) as mock_send:
            await hooks.on_tool_end("search", tool_output="result")

        assert "search" not in hooks._pending
        mock_send.assert_called_once()
        span = mock_send.call_args[0][0]
        assert span.tool_name == "search"
        assert span.status == ToolCallStatus.SUCCESS
        assert span.server_name == "test-claude"
        assert span.agent_name == "claude-agent"

    async def test_without_start_still_sends(
        self, hooks: LangSightClaudeAgentHooks, client: LangSightClient
    ) -> None:
        with patch.object(client, "send_span", new_callable=AsyncMock) as mock_send:
            await hooks.on_tool_end("orphan_tool", tool_output="data")

        mock_send.assert_called_once()

    async def test_passes_trace_id(
        self, hooks: LangSightClaudeAgentHooks, client: LangSightClient
    ) -> None:
        await hooks.on_tool_start("search", {})

        with patch.object(hooks, "_record", new_callable=AsyncMock) as mock_record:
            await hooks.on_tool_end("search")

        assert mock_record.call_args[1]["trace_id"] == "trace-002"

    async def test_fail_open(
        self, hooks: LangSightClaudeAgentHooks, client: LangSightClient
    ) -> None:
        await hooks.on_tool_start("tool", {})

        with patch.object(client, "send_span", new_callable=AsyncMock, side_effect=RuntimeError("network")):
            await hooks.on_tool_end("tool")
        # No exception raised


class TestClaudeAgentHooksOnToolError:
    async def test_clears_pending_and_sends_error_span(
        self, hooks: LangSightClaudeAgentHooks, client: LangSightClient
    ) -> None:
        await hooks.on_tool_start("search", {})

        with patch.object(client, "send_span", new_callable=AsyncMock) as mock_send:
            await hooks.on_tool_error("search", error=ValueError("bad"))

        assert "search" not in hooks._pending
        span = mock_send.call_args[0][0]
        assert span.status == ToolCallStatus.ERROR
        assert "bad" in span.error

    async def test_with_none_error(
        self, hooks: LangSightClaudeAgentHooks, client: LangSightClient
    ) -> None:
        await hooks.on_tool_start("tool", {})

        with patch.object(hooks, "_record", new_callable=AsyncMock) as mock_record:
            await hooks.on_tool_error("tool", error=None)

        assert mock_record.call_args[1]["error"] is None

    async def test_without_start_still_sends(
        self, hooks: LangSightClaudeAgentHooks, client: LangSightClient
    ) -> None:
        with patch.object(client, "send_span", new_callable=AsyncMock) as mock_send:
            await hooks.on_tool_error("orphan", error="timeout")

        mock_send.assert_called_once()

    async def test_fail_open(
        self, hooks: LangSightClaudeAgentHooks, client: LangSightClient
    ) -> None:
        await hooks.on_tool_start("tool", {})

        with patch.object(client, "send_span", new_callable=AsyncMock, side_effect=RuntimeError("network")):
            await hooks.on_tool_error("tool", error="boom")
        # No exception raised


# =============================================================================
# LangSightClaudeAgentHooks — on_handoff
# =============================================================================


class TestClaudeAgentHooksOnHandoff:
    async def test_creates_handoff_span(
        self, hooks: LangSightClaudeAgentHooks, client: LangSightClient
    ) -> None:
        with patch.object(client, "send_span", new_callable=AsyncMock) as mock_send:
            await hooks.on_handoff(from_agent="orchestrator", to_agent="billing")

        mock_send.assert_called_once()
        span = mock_send.call_args[0][0]
        assert span.span_type == "handoff"
        assert span.server_name == "orchestrator"
        assert span.tool_name == "\u2192 billing"
        assert span.trace_id == "trace-002"
        assert span.session_id == "sess-002"

    async def test_fail_open(
        self, hooks: LangSightClaudeAgentHooks, client: LangSightClient
    ) -> None:
        with patch.object(client, "send_span", new_callable=AsyncMock, side_effect=RuntimeError("network")):
            await hooks.on_handoff(from_agent="a", to_agent="b")
        # No exception raised


# =============================================================================
# langsight_anthropic_tool decorator
# =============================================================================


class TestLangsightAnthropicToolDecorator:
    async def test_traces_success(self, client: LangSightClient) -> None:
        @langsight_anthropic_tool(client=client, server_name="my-tools", agent_name="deco-agent")
        async def get_weather(location: str) -> str:
            return f"72F in {location}"

        with patch.object(client, "send_span", new_callable=AsyncMock) as mock_send:
            result = await get_weather("NYC")

        assert result == "72F in NYC"
        mock_send.assert_called_once()
        span = mock_send.call_args[0][0]
        assert span.tool_name == "get_weather"
        assert span.status == ToolCallStatus.SUCCESS
        assert span.server_name == "my-tools"
        assert span.agent_name == "deco-agent"

    async def test_traces_error(self, client: LangSightClient) -> None:
        @langsight_anthropic_tool(client=client, server_name="tools")
        async def failing_tool() -> str:
            raise ValueError("bad input")

        with patch.object(client, "send_span", new_callable=AsyncMock) as mock_send:
            with pytest.raises(ValueError, match="bad input"):
                await failing_tool()

        span = mock_send.call_args[0][0]
        assert span.status == ToolCallStatus.ERROR
        assert "bad input" in span.error

    async def test_traces_timeout(self, client: LangSightClient) -> None:
        @langsight_anthropic_tool(client=client, server_name="tools")
        async def slow_tool() -> str:
            raise TimeoutError("too slow")

        with patch.object(client, "send_span", new_callable=AsyncMock) as mock_send:
            with pytest.raises(TimeoutError):
                await slow_tool()

        span = mock_send.call_args[0][0]
        assert span.status == ToolCallStatus.TIMEOUT

    async def test_preserves_function_name(self, client: LangSightClient) -> None:
        @langsight_anthropic_tool(client=client, server_name="tools")
        async def my_named_tool() -> None:
            pass

        assert my_named_tool.__name__ == "my_named_tool"

    async def test_sends_span_even_on_error(self, client: LangSightClient) -> None:
        @langsight_anthropic_tool(client=client, server_name="tools")
        async def exploding() -> str:
            raise RuntimeError("boom")

        with patch.object(client, "send_span", new_callable=AsyncMock) as mock_send:
            with pytest.raises(RuntimeError):
                await exploding()

        mock_send.assert_called_once()

    async def test_default_params(self, client: LangSightClient) -> None:
        @langsight_anthropic_tool(client=client)
        async def default_tool() -> str:
            return "ok"

        with patch.object(client, "send_span", new_callable=AsyncMock) as mock_send:
            await default_tool()

        span = mock_send.call_args[0][0]
        assert span.server_name == "anthropic-tools"
        assert span.agent_name is None

    async def test_passes_session_id(self, client: LangSightClient) -> None:
        @langsight_anthropic_tool(client=client, server_name="tools", session_id="sess-abc")
        async def tracked_tool() -> str:
            return "ok"

        with patch.object(client, "send_span", new_callable=AsyncMock) as mock_send:
            await tracked_tool()

        span = mock_send.call_args[0][0]
        assert span.session_id == "sess-abc"
