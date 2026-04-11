from __future__ import annotations

import threading
from unittest.mock import patch
from uuid import uuid4

import pytest

from langsight.integrations.langchain import (
    LangSightLangChainCallback,
    _detect_agent_name,
    _get_global_tool_stack,
)
from langsight.sdk.client import LangSightClient


@pytest.fixture
def client() -> LangSightClient:
    return LangSightClient(url="http://localhost:8000")


def _make_callback(
    client: LangSightClient,
    server_name: str | None = "langchain-tools",
    agent_name: str | None = "test-agent",
    auto_detect: bool = False,
) -> LangSightLangChainCallback:
    """Build a callback while suppressing the langchain import."""
    with patch(
        "langsight.integrations.langchain.LangSightLangChainCallback.__init__"
    ) as mock_init:
        mock_init.return_value = None
        cb = LangSightLangChainCallback.__new__(LangSightLangChainCallback)
        cb._client = client
        cb._server_name = server_name or "langchain"
        cb._agent_name = agent_name
        cb._session_id = "sess-001"
        cb._trace_id = "trace-001"
        cb._redact = False
        cb._auto_detect = auto_detect
        cb._pending = {}
        cb._active_chains = {}
        cb._pending_llm = {}
        cb._active_lg_nodes = set()
        cb._local = threading.local()
        cb._session_input = None
        cb._session_output = None
        cb._session_input_captured = False
        cb._node_counter = {}
        cb._max_node_iterations = 10
        cb._budget = None
        cb._pricing_table = {}
        cb._budget_violated = False
        cb._budget_violation = None
    return cb


@pytest.fixture
def callback(client: LangSightClient) -> LangSightLangChainCallback:
    """Fixed-mode callback (backward compatible)."""
    return _make_callback(client, auto_detect=False)


@pytest.fixture
def auto_callback(client: LangSightClient) -> LangSightLangChainCallback:
    """Auto-detect mode callback."""
    # Clear global tool stack between tests
    _get_global_tool_stack().clear()
    return _make_callback(client, server_name=None, agent_name=None, auto_detect=True)


# =============================================================================
# Agent detection heuristic
# =============================================================================


class TestDetectAgentName:
    def test_returns_name_for_user_agent(self) -> None:
        assert _detect_agent_name({"name": "supervisor"}) == "supervisor"

    def test_returns_none_for_runnable_sequence(self) -> None:
        assert _detect_agent_name({"name": "RunnableSequence"}) is None

    def test_returns_none_for_empty_name(self) -> None:
        assert _detect_agent_name({"name": ""}) is None
        assert _detect_agent_name({}) is None

    def test_returns_none_for_internal_langgraph_node(self) -> None:
        assert (
            _detect_agent_name(
                {"name": "agent"}, metadata={"langgraph_node": "tools"}
            )
            is None
        )
        assert (
            _detect_agent_name(
                {"name": "start"}, metadata={"langgraph_node": "__start__"}
            )
            is None
        )

    def test_returns_name_when_metadata_has_non_internal_node(self) -> None:
        result = _detect_agent_name(
            {"name": "analyst"}, metadata={"langgraph_node": "analyst"}
        )
        assert result == "analyst"

    def test_skips_llm_wrapper_names(self) -> None:
        assert _detect_agent_name({"name": "ChatOpenAI"}) is None
        assert _detect_agent_name({"name": "ChatGoogleGenerativeAI"}) is None

    def test_skips_prompt_template(self) -> None:
        assert _detect_agent_name({"name": "ChatPromptTemplate"}) is None


# =============================================================================
# Fixed mode (backward compatible) — tool calls
# =============================================================================


class TestFixedModeToolCalls:
    def test_on_tool_start_records_pending(
        self, callback: LangSightLangChainCallback
    ) -> None:
        run_id = uuid4()
        callback.on_tool_start(
            {"name": "search_tool"}, "query string", run_id=run_id
        )
        assert str(run_id) in callback._pending
        pending = callback._pending[str(run_id)]
        assert pending.tool_name == "search_tool"

    def test_on_tool_start_extracts_name_from_id(
        self, callback: LangSightLangChainCallback
    ) -> None:
        run_id = uuid4()
        callback.on_tool_start(
            {"id": ["langchain", "tools", "MyCustomTool"]},
            "input",
            run_id=run_id,
        )
        assert callback._pending[str(run_id)].tool_name == "MyCustomTool"

    def test_on_tool_end_clears_pending(
        self, callback: LangSightLangChainCallback
    ) -> None:
        run_id = uuid4()
        callback.on_tool_start({"name": "my_tool"}, "input", run_id=run_id)

        callback.on_tool_end("result", run_id=run_id)

        assert str(run_id) not in callback._pending

    def test_on_tool_error_clears_pending(
        self, callback: LangSightLangChainCallback
    ) -> None:
        run_id = uuid4()
        callback.on_tool_start({"name": "my_tool"}, "input", run_id=run_id)

        callback.on_tool_error(ValueError("failed"), run_id=run_id)

        assert str(run_id) not in callback._pending

    def test_on_tool_end_unknown_run_id_no_crash(
        self, callback: LangSightLangChainCallback
    ) -> None:
        callback.on_tool_end("result", run_id=uuid4())

    def test_on_tool_error_unknown_run_id_no_crash(
        self, callback: LangSightLangChainCallback
    ) -> None:
        callback.on_tool_error("error", run_id=uuid4())

    def test_fixed_mode_skips_chain_tracking(
        self, callback: LangSightLangChainCallback
    ) -> None:
        """In fixed mode, on_chain_start is a no-op."""
        run_id = uuid4()
        callback.on_chain_start(
            {"name": "supervisor"}, {}, run_id=run_id
        )
        assert len(callback._active_chains) == 0


# =============================================================================
# Auto-detect mode — agent detection + parent linking
# =============================================================================


class TestAutoDetectAgentSpans:
    def test_on_chain_start_detects_agent(
        self, auto_callback: LangSightLangChainCallback
    ) -> None:
        run_id = uuid4()
        auto_callback.on_chain_start(
            {"name": "supervisor"}, {}, run_id=run_id
        )
        chain = auto_callback._active_chains[str(run_id)]
        assert chain.is_agent is True
        assert chain.name == "supervisor"
        assert chain.agent_span_id is not None

    def test_on_chain_start_skips_internals(
        self, auto_callback: LangSightLangChainCallback
    ) -> None:
        run_id = uuid4()
        auto_callback.on_chain_start(
            {"name": "RunnableSequence"}, {}, run_id=run_id
        )
        chain = auto_callback._active_chains.get(str(run_id))
        assert chain is not None
        assert chain.is_agent is False

    def test_on_chain_end_emits_agent_span(
        self, auto_callback: LangSightLangChainCallback
    ) -> None:
        run_id = uuid4()
        auto_callback.on_chain_start(
            {"name": "supervisor"}, {}, run_id=run_id
        )
        auto_callback._client.buffer_span = lambda span: None

        auto_callback.on_chain_end({}, run_id=run_id)

        # Agent span should have been buffered and chain cleaned up
        assert str(run_id) not in auto_callback._active_chains

    def test_on_chain_error_emits_error_agent_span(
        self, auto_callback: LangSightLangChainCallback
    ) -> None:
        run_id = uuid4()
        auto_callback.on_chain_start(
            {"name": "analyst"}, {}, run_id=run_id
        )
        auto_callback._client.buffer_span = lambda span: None

        auto_callback.on_chain_error(
            RuntimeError("LLM failed"), run_id=run_id
        )

        assert str(run_id) not in auto_callback._active_chains


# =============================================================================
# Cross-ainvoke parent linking
# =============================================================================


class TestCrossAinvokeLinking:
    def test_tool_start_pushes_to_stack(
        self, auto_callback: LangSightLangChainCallback
    ) -> None:
        run_id = uuid4()
        auto_callback.on_tool_start(
            {"name": "call_analyst"}, "task", run_id=run_id
        )
        assert len(auto_callback._tool_stack) == 1
        assert auto_callback._tool_stack[0].tool_name == "call_analyst"

    def test_tool_end_pops_from_stack(
        self, auto_callback: LangSightLangChainCallback
    ) -> None:
        run_id = uuid4()
        auto_callback.on_tool_start(
            {"name": "call_analyst"}, "task", run_id=run_id
        )
        auto_callback.on_tool_end("result", run_id=run_id)
        assert len(auto_callback._tool_stack) == 0

    def test_new_agent_chain_links_to_executing_tool(
        self, auto_callback: LangSightLangChainCallback
    ) -> None:
        """When a tool is executing and a new agent starts, link to the tool."""
        tool_run = uuid4()
        auto_callback.on_tool_start(
            {"name": "call_analyst"}, "task", run_id=tool_run
        )
        tool_span_id = auto_callback._pending[str(tool_run)].span_id

        # Now a new agent starts INSIDE the tool (cross-ainvoke)
        agent_run = uuid4()
        auto_callback.on_chain_start(
            {"name": "analyst"}, {}, run_id=agent_run, parent_run_id=None
        )
        chain = auto_callback._active_chains[str(agent_run)]
        assert chain.parent_span_id == tool_span_id

    def test_nested_tools_maintain_stack_order(
        self, auto_callback: LangSightLangChainCallback
    ) -> None:
        run1 = uuid4()
        run2 = uuid4()
        auto_callback.on_tool_start({"name": "tool_a"}, "", run_id=run1)
        auto_callback.on_tool_start({"name": "tool_b"}, "", run_id=run2)
        assert len(auto_callback._tool_stack) == 2
        assert auto_callback._tool_stack[-1].tool_name == "tool_b"


# =============================================================================
# Prompt capture
# =============================================================================


class TestPromptCapture:
    def test_set_input_stores_prompt(
        self, auto_callback: LangSightLangChainCallback
    ) -> None:
        auto_callback.set_input("who are the top 5 customers?")
        assert auto_callback._session_input == "who are the top 5 customers?"
        assert auto_callback._session_input_captured is True

    def test_set_output_stores_answer(
        self, auto_callback: LangSightLangChainCallback
    ) -> None:
        auto_callback.set_output("The top 5 are...")
        assert auto_callback._session_output == "The top 5 are..."

    def test_on_chat_model_start_captures_first_human_message(
        self, auto_callback: LangSightLangChainCallback
    ) -> None:
        from types import SimpleNamespace

        human_msg = SimpleNamespace(type="human", content="Hello, world!")
        auto_callback.on_chat_model_start(
            {}, [[human_msg]], run_id=uuid4()
        )
        assert auto_callback._session_input == "Hello, world!"
        assert auto_callback._session_input_captured is True

    def test_on_chat_model_start_only_captures_first(
        self, auto_callback: LangSightLangChainCallback
    ) -> None:
        from types import SimpleNamespace

        msg1 = SimpleNamespace(type="human", content="First")
        auto_callback.on_chat_model_start({}, [[msg1]], run_id=uuid4())

        msg2 = SimpleNamespace(type="human", content="Second")
        auto_callback.on_chat_model_start({}, [[msg2]], run_id=uuid4())

        assert auto_callback._session_input == "First"

    def test_set_input_overrides_auto_capture(
        self, auto_callback: LangSightLangChainCallback
    ) -> None:
        auto_callback.set_input("Explicit prompt")

        from types import SimpleNamespace

        msg = SimpleNamespace(type="human", content="Auto-captured")
        auto_callback.on_chat_model_start({}, [[msg]], run_id=uuid4())

        assert auto_callback._session_input == "Explicit prompt"


# =============================================================================
# Backward compatibility
# =============================================================================


class TestBackwardCompatibility:
    def test_fixed_mode_with_explicit_server_name(
        self, client: LangSightClient
    ) -> None:
        cb = _make_callback(
            client, server_name="my-server", agent_name="my-agent", auto_detect=False
        )
        assert cb._auto_detect is False
        assert cb._server_name == "my-server"
        assert cb._agent_name == "my-agent"

    def test_auto_detect_mode_when_no_server_name(
        self, client: LangSightClient
    ) -> None:
        cb = _make_callback(
            client, server_name=None, agent_name=None, auto_detect=True
        )
        assert cb._auto_detect is True
        assert cb._server_name == "langchain"


# =============================================================================
# LangGraph alias
# =============================================================================


class TestLangGraphAlias:
    def test_langgraph_callback_is_same_class(self) -> None:
        from langsight.integrations.langgraph import LangSightLangGraphCallback

        assert LangSightLangGraphCallback is LangSightLangChainCallback
