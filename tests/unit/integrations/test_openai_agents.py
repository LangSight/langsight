from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from langsight.integrations.openai_agents import (
    LangSightOpenAIHooks,
    langsight_openai_tool,
)
from langsight.sdk.client import LangSightClient
from langsight.sdk.models import ToolCallStatus


@pytest.fixture
def client() -> LangSightClient:
    return LangSightClient(url="http://localhost:8000")


@pytest.fixture
def hooks(client: LangSightClient) -> LangSightOpenAIHooks:
    return LangSightOpenAIHooks(
        client=client,
        server_name="test-openai",
        agent_name="test-agent",
        session_id="sess-001",
        trace_id="trace-001",
    )


def _make_agent(name: str = "my-agent") -> SimpleNamespace:
    return SimpleNamespace(name=name)


def _make_tool(name: str = "search_tool") -> SimpleNamespace:
    return SimpleNamespace(name=name)


class TestLangSightOpenAIHooksConstructor:
    def test_creates_with_all_params(self, client: LangSightClient) -> None:
        hooks = LangSightOpenAIHooks(
            client=client,
            server_name="custom-server",
            agent_name="my-agent",
            session_id="sess-123",
            trace_id="trace-456",
        )
        assert hooks._server_name == "custom-server"
        assert hooks._agent_name == "my-agent"
        assert hooks._session_id == "sess-123"
        assert hooks._trace_id == "trace-456"
        assert hooks._pending == {}

    def test_creates_with_defaults(self, client: LangSightClient) -> None:
        hooks = LangSightOpenAIHooks(client=client)
        assert hooks._server_name == "openai-agents"
        assert hooks._agent_name is None
        assert hooks._session_id is None
        assert hooks._trace_id is None


class TestLangSightOpenAIHooksToolKey:
    def test_tool_key_uses_agent_and_tool_name(self, hooks: LangSightOpenAIHooks) -> None:
        agent = _make_agent("agent-a")
        tool = _make_tool("search")
        key = hooks._tool_key(agent, tool)
        assert key.startswith("agent-a:search:")

    def test_tool_key_falls_back_to_id_when_no_name(self, hooks: LangSightOpenAIHooks) -> None:
        agent = SimpleNamespace()  # no name attribute
        tool = SimpleNamespace()  # no name attribute
        key = hooks._tool_key(agent, tool)
        # Should use str(id(...)) fallback — just verify it doesn't crash
        assert ":" in key

    def test_tool_name_extracts_name_attr(self, hooks: LangSightOpenAIHooks) -> None:
        tool = _make_tool("get_weather")
        assert hooks._tool_name(tool) == "get_weather"

    def test_tool_name_falls_back_to_dunder_name(self, hooks: LangSightOpenAIHooks) -> None:
        async def my_function() -> None:
            pass

        assert hooks._tool_name(my_function) == "my_function"

    def test_tool_name_falls_back_to_str(self, hooks: LangSightOpenAIHooks) -> None:
        tool = 42  # no name attribute, no __name__
        result = hooks._tool_name(tool)
        assert result == "42"


class TestLangSightOpenAIHooksAgentLabel:
    def test_agent_label_uses_agent_name_attr(self, hooks: LangSightOpenAIHooks) -> None:
        agent = _make_agent("labeled-agent")
        assert hooks._agent_label(agent) == "labeled-agent"

    def test_agent_label_falls_back_to_configured_name(self, hooks: LangSightOpenAIHooks) -> None:
        agent = SimpleNamespace()  # no name
        assert hooks._agent_label(agent) == "test-agent"

    def test_agent_label_falls_back_to_unknown(self, client: LangSightClient) -> None:
        hooks = LangSightOpenAIHooks(client=client, agent_name=None)
        agent = SimpleNamespace()
        assert hooks._agent_label(agent) == "unknown"


class TestLangSightOpenAIHooksOnToolStart:
    async def test_on_tool_start_records_pending(self, hooks: LangSightOpenAIHooks) -> None:
        agent = _make_agent()
        tool = _make_tool("search")
        await hooks.on_tool_start(context=None, agent=agent, tool=tool)

        key = hooks._tool_key(agent, tool)
        assert key in hooks._pending
        assert isinstance(hooks._pending[key], datetime)

    async def test_on_tool_start_multiple_tools(self, hooks: LangSightOpenAIHooks) -> None:
        agent = _make_agent()
        tool1 = _make_tool("search")
        tool2 = _make_tool("fetch")

        await hooks.on_tool_start(context=None, agent=agent, tool=tool1)
        await hooks.on_tool_start(context=None, agent=agent, tool=tool2)

        assert len(hooks._pending) == 2

    async def test_on_tool_start_fail_open(self, hooks: LangSightOpenAIHooks) -> None:
        """Exception in _tool_key should not propagate."""
        with patch.object(hooks, "_tool_key", side_effect=RuntimeError("boom")):
            await hooks.on_tool_start(context=None, agent=None, tool=None)
        # No exception raised — fail-open


class TestLangSightOpenAIHooksOnToolEnd:
    async def test_on_tool_end_clears_pending_and_sends_span(
        self, hooks: LangSightOpenAIHooks, client: LangSightClient
    ) -> None:
        agent = _make_agent()
        tool = _make_tool("search")
        await hooks.on_tool_start(context=None, agent=agent, tool=tool)
        key = hooks._tool_key(agent, tool)
        assert key in hooks._pending

        with patch.object(client, "buffer_span") as mock_send:
            await hooks.on_tool_end(context=None, agent=agent, tool=tool, result="ok")

        assert key not in hooks._pending
        mock_send.assert_called_once()
        span = mock_send.call_args[0][0]
        assert span.tool_name == "search"
        assert span.status == ToolCallStatus.SUCCESS
        assert span.server_name == "test-openai"
        assert span.agent_name == "my-agent"  # from runtime agent object, not constructor

    async def test_on_tool_end_without_start_still_sends(
        self, hooks: LangSightOpenAIHooks, client: LangSightClient
    ) -> None:
        """If on_tool_start was missed, on_tool_end should still create a span."""
        agent = _make_agent()
        tool = _make_tool("orphan_tool")

        with patch.object(client, "buffer_span") as mock_send:
            await hooks.on_tool_end(context=None, agent=agent, tool=tool)

        mock_send.assert_called_once()
        span = mock_send.call_args[0][0]
        assert span.tool_name == "orphan_tool"
        assert span.status == ToolCallStatus.SUCCESS

    async def test_on_tool_end_fail_open(
        self, hooks: LangSightOpenAIHooks, client: LangSightClient
    ) -> None:
        """Exception in send_span should not propagate."""
        agent = _make_agent()
        tool = _make_tool("fail_tool")
        await hooks.on_tool_start(context=None, agent=agent, tool=tool)

        with patch.object(client, "buffer_span", side_effect=RuntimeError("network")):
            await hooks.on_tool_end(context=None, agent=agent, tool=tool)
        # No exception raised

    async def test_on_tool_end_passes_trace_id(
        self, hooks: LangSightOpenAIHooks, client: LangSightClient
    ) -> None:
        agent = _make_agent()
        tool = _make_tool("search")
        await hooks.on_tool_start(context=None, agent=agent, tool=tool)

        with patch.object(hooks, "_record", new_callable=AsyncMock) as mock_record:
            await hooks.on_tool_end(context=None, agent=agent, tool=tool, result="ok")

        mock_record.assert_called_once()
        assert mock_record.call_args[1]["trace_id"] == "trace-001"


class TestLangSightOpenAIHooksOnToolError:
    async def test_on_tool_error_clears_pending_and_sends_error_span(
        self, hooks: LangSightOpenAIHooks, client: LangSightClient
    ) -> None:
        agent = _make_agent()
        tool = _make_tool("bad_tool")
        await hooks.on_tool_start(context=None, agent=agent, tool=tool)
        key = hooks._tool_key(agent, tool)

        with patch.object(client, "buffer_span") as mock_send:
            await hooks.on_tool_error(
                context=None, agent=agent, tool=tool, error=ValueError("bad input")
            )

        assert key not in hooks._pending
        span = mock_send.call_args[0][0]
        assert span.status == ToolCallStatus.ERROR
        assert "bad input" in span.error

    async def test_on_tool_error_without_start_still_sends(
        self, hooks: LangSightOpenAIHooks, client: LangSightClient
    ) -> None:
        agent = _make_agent()
        tool = _make_tool("orphan_error")

        with patch.object(client, "buffer_span") as mock_send:
            await hooks.on_tool_error(
                context=None, agent=agent, tool=tool, error="timeout"
            )

        mock_send.assert_called_once()

    async def test_on_tool_error_with_none_error(
        self, hooks: LangSightOpenAIHooks, client: LangSightClient
    ) -> None:
        agent = _make_agent()
        tool = _make_tool("mystery_fail")
        await hooks.on_tool_start(context=None, agent=agent, tool=tool)

        with patch.object(hooks, "_record", new_callable=AsyncMock) as mock_record:
            await hooks.on_tool_error(
                context=None, agent=agent, tool=tool, error=None
            )

        assert mock_record.call_args[1]["error"] is None

    async def test_on_tool_error_fail_open(
        self, hooks: LangSightOpenAIHooks, client: LangSightClient
    ) -> None:
        agent = _make_agent()
        tool = _make_tool("err_tool")
        await hooks.on_tool_start(context=None, agent=agent, tool=tool)

        with patch.object(client, "buffer_span", side_effect=RuntimeError("network")):
            await hooks.on_tool_error(
                context=None, agent=agent, tool=tool, error="boom"
            )
        # No exception raised


class TestLangSightOpenAIHooksOnHandoff:
    async def test_on_handoff_creates_handoff_span(
        self, hooks: LangSightOpenAIHooks, client: LangSightClient
    ) -> None:
        from_agent = _make_agent("orchestrator")
        to_agent = _make_agent("billing-agent")

        with patch.object(client, "buffer_span") as mock_send:
            await hooks.on_handoff(
                context=None, from_agent=from_agent, to_agent=to_agent
            )

        mock_send.assert_called_once()
        span = mock_send.call_args[0][0]
        assert span.span_type == "handoff"
        assert span.server_name == "orchestrator"
        assert span.tool_name == "\u2192 billing-agent"
        assert span.trace_id == "trace-001"
        assert span.session_id == "sess-001"

    async def test_on_handoff_fail_open(
        self, hooks: LangSightOpenAIHooks, client: LangSightClient
    ) -> None:
        with patch.object(client, "buffer_span", side_effect=RuntimeError("network")):
            await hooks.on_handoff(
                context=None,
                from_agent=_make_agent("a"),
                to_agent=_make_agent("b"),
            )
        # No exception raised

    async def test_on_handoff_uses_agent_name_fallback(
        self, hooks: LangSightOpenAIHooks, client: LangSightClient
    ) -> None:
        """Agents without a name attribute fall back to configured agent_name."""
        from_agent = SimpleNamespace()  # no name
        to_agent = SimpleNamespace()  # no name

        with patch.object(client, "buffer_span") as mock_send:
            await hooks.on_handoff(context=None, from_agent=from_agent, to_agent=to_agent)

        span = mock_send.call_args[0][0]
        assert span.server_name == "test-agent"
        assert span.tool_name == "\u2192 test-agent"


class TestLangSightOpenAIHooksLifecycleNoOps:
    async def test_on_agent_start_is_noop(self, hooks: LangSightOpenAIHooks) -> None:
        await hooks.on_agent_start(context=None, agent=_make_agent())

    async def test_on_agent_end_is_noop(self, hooks: LangSightOpenAIHooks) -> None:
        await hooks.on_agent_end(context=None, agent=_make_agent(), output="done")


class TestLangsightOpenAIToolDecorator:
    async def test_decorator_traces_success(self, client: LangSightClient) -> None:
        @langsight_openai_tool(client=client, server_name="my-tools", agent_name="deco-agent")
        async def search(query: str) -> str:
            return f"results for {query}"

        with patch.object(client, "buffer_span") as mock_send:
            result = await search("hello")

        assert result == "results for hello"
        mock_send.assert_called_once()
        span = mock_send.call_args[0][0]
        assert span.tool_name == "search"
        assert span.status == ToolCallStatus.SUCCESS
        assert span.server_name == "my-tools"
        assert span.agent_name == "deco-agent"

    async def test_decorator_traces_error(self, client: LangSightClient) -> None:
        @langsight_openai_tool(client=client, server_name="my-tools")
        async def failing_tool() -> str:
            raise ValueError("bad input")

        with patch.object(client, "buffer_span") as mock_send:
            with pytest.raises(ValueError, match="bad input"):
                await failing_tool()

        span = mock_send.call_args[0][0]
        assert span.status == ToolCallStatus.ERROR
        assert "bad input" in span.error

    async def test_decorator_traces_timeout(self, client: LangSightClient) -> None:
        @langsight_openai_tool(client=client, server_name="my-tools")
        async def slow_tool() -> str:
            raise TimeoutError("took too long")

        with patch.object(client, "buffer_span") as mock_send:
            with pytest.raises(TimeoutError):
                await slow_tool()

        span = mock_send.call_args[0][0]
        assert span.status == ToolCallStatus.TIMEOUT
        assert "took too long" in span.error

    async def test_decorator_preserves_function_name(self, client: LangSightClient) -> None:
        @langsight_openai_tool(client=client, server_name="my-tools")
        async def my_named_tool() -> None:
            pass

        assert my_named_tool.__name__ == "my_named_tool"

    async def test_decorator_with_default_params(self, client: LangSightClient) -> None:
        @langsight_openai_tool(client=client)
        async def default_tool() -> str:
            return "ok"

        with patch.object(client, "buffer_span") as mock_send:
            await default_tool()

        span = mock_send.call_args[0][0]
        assert span.server_name == "openai-agents"
        assert span.agent_name is None

    async def test_decorator_sends_span_even_on_error(self, client: LangSightClient) -> None:
        """The span should be sent in the finally block even when the tool raises."""
        @langsight_openai_tool(client=client, server_name="pg")
        async def exploding_tool() -> str:
            raise RuntimeError("boom")

        with patch.object(client, "buffer_span") as mock_send:
            with pytest.raises(RuntimeError):
                await exploding_tool()

        # Span was still sent despite the error
        mock_send.assert_called_once()

    async def test_decorator_passes_session_id(self, client: LangSightClient) -> None:
        @langsight_openai_tool(client=client, server_name="tools", session_id="sess-x")
        async def traced_tool() -> str:
            return "ok"

        with patch.object(client, "buffer_span") as mock_send:
            await traced_tool()

        span = mock_send.call_args[0][0]
        assert span.session_id == "sess-x"
