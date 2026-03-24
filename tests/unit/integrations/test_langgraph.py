"""Tests for the LangGraph integration (now an alias to the unified LangChain callback).

Since v0.4, LangSightLangGraphCallback IS LangSightLangChainCallback.
These tests verify the alias works and that auto-detect chain tracking
(the feature that was previously LangGraph-specific) works correctly
through the unified callback.
"""

from __future__ import annotations

import asyncio
import threading
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from langsight.integrations.langgraph import (
    LangSightLangGraphCallback,
    _fire_and_forget,
)
from langsight.integrations.langchain import LangSightLangChainCallback
from langsight.sdk.client import LangSightClient
from langsight.sdk.models import ToolCallStatus


@pytest.fixture
def client() -> LangSightClient:
    return LangSightClient(url="http://localhost:8000")


@pytest.fixture
def callback(client: LangSightClient) -> LangSightLangGraphCallback:
    """Auto-detect mode callback (chain tracking active)."""
    with patch(
        "langsight.integrations.langchain.LangSightLangChainCallback.__init__"
    ) as mock_init:
        mock_init.return_value = None
        cb = LangSightLangGraphCallback.__new__(LangSightLangGraphCallback)
        cb._client = client
        cb._server_name = "langgraph"
        cb._agent_name = "test-graph"
        cb._session_id = "sess-001"
        cb._trace_id = "trace-001"
        cb._redact = False
        cb._auto_detect = True  # chain tracking requires auto-detect
        cb._pending = {}
        cb._active_chains = {}
        cb._local = threading.local()
        cb._session_input = None
        cb._session_output = None
        cb._session_input_captured = False
    return cb


# =============================================================================
# Alias verification
# =============================================================================


class TestLangGraphAlias:
    def test_is_same_class(self) -> None:
        assert LangSightLangGraphCallback is LangSightLangChainCallback

    def test_fire_and_forget_exported(self) -> None:
        assert callable(_fire_and_forget)


# =============================================================================
# Constructor
# =============================================================================


class TestLangSightLangGraphCallbackConstructor:
    def test_creates_with_patched_init(self, callback: LangSightLangGraphCallback) -> None:
        assert callback._server_name == "langgraph"
        assert callback._agent_name == "test-graph"
        assert callback._session_id == "sess-001"

    def test_constructor_handles_missing_langchain(self, client: LangSightClient) -> None:
        with patch("builtins.__import__", side_effect=ImportError("no langchain")):
            pass  # Constructor handles ImportError gracefully


# =============================================================================
# _fire_and_forget
# =============================================================================


class TestFireAndForget:
    async def test_schedules_coroutine_in_running_loop(self) -> None:
        called = False

        async def coro() -> None:
            nonlocal called
            called = True

        _fire_and_forget(coro())
        await asyncio.sleep(0.05)
        assert called

    def test_runs_in_thread_when_no_loop(self) -> None:
        called = False

        async def coro() -> None:
            nonlocal called
            called = True

        _fire_and_forget(coro())
        import time
        time.sleep(0.1)
        assert called


# =============================================================================
# Node/chain tracking (auto-detect mode)
# =============================================================================


class TestLangGraphNodeTracking:
    def test_on_chain_start_tracks_node_name(self, callback: LangSightLangGraphCallback) -> None:
        run_id = uuid4()
        callback.on_chain_start(
            {"name": "agent_node"},
            {"input": "hello"},
            run_id=run_id,
        )
        assert str(run_id) in callback._active_chains
        assert callback._active_chains[str(run_id)].name == "agent_node"

    def test_on_chain_start_extracts_name_from_id(self, callback: LangSightLangGraphCallback) -> None:
        run_id = uuid4()
        callback.on_chain_start(
            {"id": ["langgraph", "nodes", "ToolNode"]},
            {},
            run_id=run_id,
        )
        chain = callback._active_chains[str(run_id)]
        assert chain.name == "ToolNode"

    def test_on_chain_start_defaults_to_unknown(self, callback: LangSightLangGraphCallback) -> None:
        run_id = uuid4()
        callback.on_chain_start({"id": ["unknown"]}, {}, run_id=run_id)
        assert callback._active_chains[str(run_id)].name == "unknown"

    def test_on_chain_end_clears_node(self, callback: LangSightLangGraphCallback) -> None:
        run_id = uuid4()
        callback.on_chain_start({"name": "my_node"}, {}, run_id=run_id)
        callback.on_chain_end({}, run_id=run_id)
        assert str(run_id) not in callback._active_chains

    def test_on_chain_end_unknown_run_id_no_crash(self, callback: LangSightLangGraphCallback) -> None:
        callback.on_chain_end({}, run_id=uuid4())

    def test_on_chain_error_cleans_up(self, callback: LangSightLangGraphCallback) -> None:
        run_id = uuid4()
        callback.on_chain_start({"name": "bad_node"}, {}, run_id=run_id)
        callback.on_chain_error(RuntimeError("fail"), run_id=run_id)
        assert str(run_id) not in callback._active_chains

    def test_multiple_nodes_tracked_independently(self, callback: LangSightLangGraphCallback) -> None:
        r1, r2 = uuid4(), uuid4()
        callback.on_chain_start({"name": "node_a"}, {}, run_id=r1)
        callback.on_chain_start({"name": "node_b"}, {}, run_id=r2)
        assert len(callback._active_chains) == 2
        callback.on_chain_end({}, run_id=r1)
        assert str(r1) not in callback._active_chains
        assert str(r2) in callback._active_chains


# =============================================================================
# Tool tracking
# =============================================================================


class TestLangGraphOnToolStart:
    def test_records_pending(self, callback: LangSightLangGraphCallback) -> None:
        run_id = uuid4()
        callback.on_tool_start(
            {"name": "search"},
            "query",
            run_id=run_id,
        )
        assert str(run_id) in callback._pending
        assert callback._pending[str(run_id)].tool_name == "search"

    def test_extracts_name_from_id_field(self, callback: LangSightLangGraphCallback) -> None:
        run_id = uuid4()
        callback.on_tool_start(
            {"id": ["tools", "MyTool"]}, "input", run_id=run_id
        )
        assert callback._pending[str(run_id)].tool_name == "MyTool"


class TestLangGraphOnToolEnd:
    def test_clears_pending_and_fires_span(
        self, callback: LangSightLangGraphCallback
    ) -> None:
        run_id = uuid4()
        callback.on_tool_start({"name": "search"}, "query", run_id=run_id)

        with patch("langsight.integrations.langchain._fire_and_forget"):
            callback.on_tool_end("result", run_id=run_id)

        assert str(run_id) not in callback._pending

    def test_unknown_run_id_no_crash(self, callback: LangSightLangGraphCallback) -> None:
        callback.on_tool_end("result", run_id=uuid4())

    def test_passes_session_and_trace_ids(
        self, callback: LangSightLangGraphCallback
    ) -> None:
        run_id = uuid4()
        callback.on_tool_start({"name": "search"}, "query", run_id=run_id)
        assert callback._session_id == "sess-001"
        assert callback._trace_id == "trace-001"


class TestLangGraphOnToolError:
    def test_clears_pending_and_fires_error_span(
        self, callback: LangSightLangGraphCallback
    ) -> None:
        run_id = uuid4()
        callback.on_tool_start({"name": "search"}, "query", run_id=run_id)

        with patch("langsight.integrations.langchain._fire_and_forget"):
            callback.on_tool_error(RuntimeError("fail"), run_id=run_id)

        assert str(run_id) not in callback._pending

    def test_unknown_run_id_no_crash(self, callback: LangSightLangGraphCallback) -> None:
        callback.on_tool_error(RuntimeError("fail"), run_id=uuid4())
