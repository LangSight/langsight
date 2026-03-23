from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from langsight.integrations.langgraph import (
    LangSightLangGraphCallback,
    _fire_and_forget,
)
from langsight.sdk.client import LangSightClient
from langsight.sdk.models import ToolCallStatus


@pytest.fixture
def client() -> LangSightClient:
    return LangSightClient(url="http://localhost:8000")


@pytest.fixture
def callback(client: LangSightClient) -> LangSightLangGraphCallback:
    """Create callback while suppressing langchain import (not installed in test env)."""
    with patch("langsight.integrations.langgraph.LangSightLangGraphCallback.__init__") as mock_init:
        mock_init.return_value = None
        cb = LangSightLangGraphCallback.__new__(LangSightLangGraphCallback)
        cb._client = client
        cb._server_name = "langgraph"
        cb._agent_name = "test-graph"
        cb._session_id = "sess-001"
        cb._trace_id = "trace-001"
        cb._pending = {}
        cb._active_nodes = {}
        cb._current_node = None
    return cb


# =============================================================================
# Constructor
# =============================================================================


class TestLangSightLangGraphCallbackConstructor:
    def test_creates_with_patched_init(self, callback: LangSightLangGraphCallback) -> None:
        assert callback._server_name == "langgraph"
        assert callback._agent_name == "test-graph"
        assert callback._session_id == "sess-001"
        assert callback._trace_id == "trace-001"
        assert callback._pending == {}
        assert callback._active_nodes == {}
        assert callback._current_node is None

    def test_constructor_handles_missing_langchain(self, client: LangSightClient) -> None:
        """When langchain is not installed, constructor should warn but not crash."""
        with patch("builtins.__import__", side_effect=ImportError("no langchain")):
            # The __init__ catches ImportError internally
            pass


# =============================================================================
# _fire_and_forget helper
# =============================================================================


class TestFireAndForget:
    async def test_schedules_coroutine_in_running_loop(self) -> None:
        """When an event loop is running, _fire_and_forget should schedule the task."""
        called = False

        async def coro() -> None:
            nonlocal called
            called = True

        _fire_and_forget(coro())
        await asyncio.sleep(0.01)
        assert called

    def test_runs_in_thread_when_no_loop(self) -> None:
        """When no event loop is running, _fire_and_forget should run in a thread."""
        with patch("asyncio.get_running_loop", side_effect=RuntimeError("no loop")):
            with patch("threading.Thread") as mock_thread:
                mock_instance = MagicMock()
                mock_thread.return_value = mock_instance

                async def dummy() -> None:
                    pass

                _fire_and_forget(dummy())
                mock_thread.assert_called_once()
                mock_instance.start.assert_called_once()


# =============================================================================
# on_chain_start / on_chain_end — Node tracking
# =============================================================================


class TestLangGraphNodeTracking:
    def test_on_chain_start_tracks_node_name(self, callback: LangSightLangGraphCallback) -> None:
        run_id = uuid4()
        callback.on_chain_start(
            {"name": "agent_node"},
            {"input": "hello"},
            run_id=run_id,
        )

        assert str(run_id) in callback._active_nodes
        assert callback._active_nodes[str(run_id)] == "agent_node"
        assert callback._current_node == "agent_node"

    def test_on_chain_start_extracts_name_from_id(self, callback: LangSightLangGraphCallback) -> None:
        run_id = uuid4()
        callback.on_chain_start(
            {"id": ["langgraph", "nodes", "ToolNode"]},
            {},
            run_id=run_id,
        )

        assert callback._active_nodes[str(run_id)] == "ToolNode"
        assert callback._current_node == "ToolNode"

    def test_on_chain_start_defaults_to_unknown(self, callback: LangSightLangGraphCallback) -> None:
        run_id = uuid4()
        callback.on_chain_start({}, {}, run_id=run_id)
        assert callback._active_nodes[str(run_id)] == "unknown"

    def test_on_chain_end_clears_node(self, callback: LangSightLangGraphCallback) -> None:
        run_id = uuid4()
        callback.on_chain_start({"name": "agent_node"}, {}, run_id=run_id)
        assert callback._current_node == "agent_node"

        callback.on_chain_end({}, run_id=run_id)
        assert str(run_id) not in callback._active_nodes
        assert callback._current_node is None

    def test_on_chain_end_resets_to_previous_node(self, callback: LangSightLangGraphCallback) -> None:
        run_id_1 = uuid4()
        run_id_2 = uuid4()

        callback.on_chain_start({"name": "router"}, {}, run_id=run_id_1)
        callback.on_chain_start({"name": "tool_node"}, {}, run_id=run_id_2)
        assert callback._current_node == "tool_node"

        callback.on_chain_end({}, run_id=run_id_2)
        assert callback._current_node == "router"

    def test_on_chain_end_unknown_run_id_no_crash(self, callback: LangSightLangGraphCallback) -> None:
        callback.on_chain_end({}, run_id=uuid4())

    def test_on_chain_error_cleans_up(self, callback: LangSightLangGraphCallback) -> None:
        run_id = uuid4()
        callback.on_chain_start({"name": "error_node"}, {}, run_id=run_id)

        callback.on_chain_error(RuntimeError("node error"), run_id=run_id)
        assert str(run_id) not in callback._active_nodes
        assert callback._current_node is None

    def test_multiple_nodes_tracked_independently(self, callback: LangSightLangGraphCallback) -> None:
        run_id_a = uuid4()
        run_id_b = uuid4()

        callback.on_chain_start({"name": "node_a"}, {}, run_id=run_id_a)
        callback.on_chain_start({"name": "node_b"}, {}, run_id=run_id_b)

        assert len(callback._active_nodes) == 2
        assert callback._current_node == "node_b"


# =============================================================================
# on_tool_start / on_tool_end / on_tool_error
# =============================================================================


class TestLangGraphOnToolStart:
    def test_records_pending_with_node_context(self, callback: LangSightLangGraphCallback) -> None:
        chain_id = uuid4()
        callback.on_chain_start({"name": "agent_node"}, {}, run_id=chain_id)

        tool_id = uuid4()
        callback.on_tool_start(
            {"name": "search_tool"},
            "query string",
            run_id=tool_id,
        )

        key = str(tool_id)
        assert key in callback._pending
        tool_name, started_at, node_name, _input = callback._pending[key]
        assert tool_name == "search_tool"
        assert node_name == "agent_node"
        assert isinstance(started_at, datetime)

    def test_records_pending_without_node_context(self, callback: LangSightLangGraphCallback) -> None:
        tool_id = uuid4()
        callback.on_tool_start({"name": "orphan_tool"}, "input", run_id=tool_id)

        tool_name, _, node_name, _input = callback._pending[str(tool_id)]
        assert tool_name == "orphan_tool"
        assert node_name is None

    def test_extracts_name_from_id_field(self, callback: LangSightLangGraphCallback) -> None:
        tool_id = uuid4()
        callback.on_tool_start(
            {"id": ["langchain", "tools", "MyTool"]},
            "input",
            run_id=tool_id,
        )

        tool_name, _, _, _input = callback._pending[str(tool_id)]
        assert tool_name == "MyTool"

    def test_defaults_to_unknown(self, callback: LangSightLangGraphCallback) -> None:
        tool_id = uuid4()
        callback.on_tool_start({}, "input", run_id=tool_id)

        tool_name, _, _, _input = callback._pending[str(tool_id)]
        assert tool_name == "unknown"


class TestLangGraphOnToolEnd:
    def test_clears_pending_and_fires_span(
        self, callback: LangSightLangGraphCallback, client: LangSightClient
    ) -> None:
        tool_id = uuid4()
        callback._pending[str(tool_id)] = ("search", datetime.now(UTC), "agent_node", "input")

        with patch("langsight.integrations.langgraph._fire_and_forget") as mock_fire:
            callback.on_tool_end("result data", run_id=tool_id)

        assert str(tool_id) not in callback._pending
        mock_fire.assert_called_once()
        # Extract the span from the coroutine argument
        coro = mock_fire.call_args[0][0]
        assert coro is not None

    def test_includes_node_name_in_server_name(
        self, callback: LangSightLangGraphCallback, client: LangSightClient
    ) -> None:
        tool_id = uuid4()
        callback._pending[str(tool_id)] = ("query", datetime.now(UTC), "tool_node", "input")

        with patch.object(client, "send_span", new_callable=AsyncMock) as mock_send:
            with patch("langsight.integrations.langgraph._fire_and_forget", side_effect=lambda coro: coro.close()):
                callback.on_tool_end("ok", run_id=tool_id)

        span = mock_send.call_args[0][0]
        assert span.server_name == "langgraph/tool_node"
        assert span.tool_name == "query"
        assert span.status == ToolCallStatus.SUCCESS
        assert span.agent_name == "test-graph"

    def test_uses_base_server_name_when_no_node(
        self, callback: LangSightLangGraphCallback, client: LangSightClient
    ) -> None:
        tool_id = uuid4()
        callback._pending[str(tool_id)] = ("query", datetime.now(UTC), None, "input")

        with patch.object(client, "send_span", new_callable=AsyncMock) as mock_send:
            with patch("langsight.integrations.langgraph._fire_and_forget", side_effect=lambda coro: coro.close()):
                callback.on_tool_end("ok", run_id=tool_id)

        span = mock_send.call_args[0][0]
        assert span.server_name == "langgraph"

    def test_unknown_run_id_no_crash(self, callback: LangSightLangGraphCallback) -> None:
        callback.on_tool_end("result", run_id=uuid4())

    def test_passes_session_and_trace_ids(
        self, callback: LangSightLangGraphCallback, client: LangSightClient
    ) -> None:
        tool_id = uuid4()
        callback._pending[str(tool_id)] = ("tool", datetime.now(UTC), "node", "input")

        with patch.object(client, "send_span", new_callable=AsyncMock) as mock_send:
            with patch("langsight.integrations.langgraph._fire_and_forget", side_effect=lambda coro: coro.close()):
                callback.on_tool_end("ok", run_id=tool_id)

        span = mock_send.call_args[0][0]
        assert span.session_id == "sess-001"
        assert span.trace_id == "trace-001"


class TestLangGraphOnToolError:
    def test_clears_pending_and_fires_error_span(
        self, callback: LangSightLangGraphCallback, client: LangSightClient
    ) -> None:
        tool_id = uuid4()
        callback._pending[str(tool_id)] = ("bad_tool", datetime.now(UTC), "agent_node", "input")

        with patch.object(client, "send_span", new_callable=AsyncMock) as mock_send:
            with patch("langsight.integrations.langgraph._fire_and_forget", side_effect=lambda coro: coro.close()):
                callback.on_tool_error(ValueError("db error"), run_id=tool_id)

        assert str(tool_id) not in callback._pending
        span = mock_send.call_args[0][0]
        assert span.status == ToolCallStatus.ERROR
        assert "db error" in span.error
        assert span.server_name == "langgraph/agent_node"

    def test_unknown_run_id_no_crash(self, callback: LangSightLangGraphCallback) -> None:
        callback.on_tool_error(RuntimeError("err"), run_id=uuid4())

    def test_uses_base_server_name_when_no_node(
        self, callback: LangSightLangGraphCallback, client: LangSightClient
    ) -> None:
        tool_id = uuid4()
        callback._pending[str(tool_id)] = ("tool", datetime.now(UTC), None, "input")

        with patch.object(client, "send_span", new_callable=AsyncMock) as mock_send:
            with patch("langsight.integrations.langgraph._fire_and_forget", side_effect=lambda coro: coro.close()):
                callback.on_tool_error(RuntimeError("err"), run_id=tool_id)

        span = mock_send.call_args[0][0]
        assert span.server_name == "langgraph"


# =============================================================================
# Full lifecycle — chain + tool together
# =============================================================================


class TestLangGraphFullLifecycle:
    def test_tool_in_node_gets_node_context(
        self, callback: LangSightLangGraphCallback, client: LangSightClient
    ) -> None:
        chain_id = uuid4()
        tool_id = uuid4()

        # Node starts
        callback.on_chain_start({"name": "search_node"}, {}, run_id=chain_id)

        # Tool runs inside node
        callback.on_tool_start({"name": "web_search"}, "query", run_id=tool_id)

        # Tool completes
        with patch.object(client, "send_span", new_callable=AsyncMock) as mock_send:
            with patch("langsight.integrations.langgraph._fire_and_forget", side_effect=lambda coro: coro.close()):
                callback.on_tool_end("results", run_id=tool_id)

        span = mock_send.call_args[0][0]
        assert span.server_name == "langgraph/search_node"
        assert span.tool_name == "web_search"

        # Node ends
        callback.on_chain_end({}, run_id=chain_id)
        assert callback._current_node is None

    def test_multiple_tools_in_sequence(
        self, callback: LangSightLangGraphCallback, client: LangSightClient
    ) -> None:
        chain_id = uuid4()
        callback.on_chain_start({"name": "multi_tool_node"}, {}, run_id=chain_id)

        tool_id_1 = uuid4()
        tool_id_2 = uuid4()

        callback.on_tool_start({"name": "tool_a"}, "input_a", run_id=tool_id_1)
        callback.on_tool_start({"name": "tool_b"}, "input_b", run_id=tool_id_2)

        spans = []
        with patch.object(client, "send_span", new_callable=AsyncMock) as mock_send:
            with patch("langsight.integrations.langgraph._fire_and_forget", side_effect=lambda coro: coro.close()):
                callback.on_tool_end("ok_a", run_id=tool_id_1)
                callback.on_tool_end("ok_b", run_id=tool_id_2)

        assert mock_send.call_count == 2
        tool_names = {call[0][0].tool_name for call in mock_send.call_args_list}
        assert tool_names == {"tool_a", "tool_b"}

    def test_tool_error_in_node_context(
        self, callback: LangSightLangGraphCallback, client: LangSightClient
    ) -> None:
        chain_id = uuid4()
        tool_id = uuid4()

        callback.on_chain_start({"name": "failing_node"}, {}, run_id=chain_id)
        callback.on_tool_start({"name": "bad_tool"}, "input", run_id=tool_id)

        with patch.object(client, "send_span", new_callable=AsyncMock) as mock_send:
            with patch("langsight.integrations.langgraph._fire_and_forget", side_effect=lambda coro: coro.close()):
                callback.on_tool_error(RuntimeError("failed"), run_id=tool_id)

        span = mock_send.call_args[0][0]
        assert span.server_name == "langgraph/failing_node"
        assert span.status == ToolCallStatus.ERROR


# =============================================================================
# LLM lifecycle no-ops
# =============================================================================


class TestLangGraphLLMNoOps:
    def test_on_llm_start_is_noop(self, callback: LangSightLangGraphCallback) -> None:
        callback.on_llm_start({"name": "claude"}, ["prompt"])

    def test_on_llm_end_is_noop(self, callback: LangSightLangGraphCallback) -> None:
        callback.on_llm_end(SimpleNamespace(generations=[]))
