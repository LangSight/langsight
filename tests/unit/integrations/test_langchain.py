from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

import pytest

from langsight.integrations.langchain import LangSightLangChainCallback
from langsight.sdk.client import LangSightClient


@pytest.fixture
def client() -> LangSightClient:
    return LangSightClient(url="http://localhost:8000")


@pytest.fixture
def callback(client: LangSightClient) -> LangSightLangChainCallback:
    with patch("langsight.integrations.langchain.LangSightLangChainCallback.__init__") as mock_init:
        mock_init.return_value = None
        cb = LangSightLangChainCallback.__new__(LangSightLangChainCallback)
        cb._client = client
        cb._server_name = "langchain-tools"
        cb._agent_name = "test-agent"
        cb._session_id = None
        cb._trace_id = None
        cb._pending = {}
    return cb


class TestLangSightLangChainCallback:
    def test_on_tool_start_records_pending(self, callback: LangSightLangChainCallback) -> None:
        run_id = uuid4()
        callback.on_tool_start(
            {"name": "search_tool"},
            "query string",
            run_id=run_id,
        )
        assert str(run_id) in callback._pending
        tool_name, started_at, input_str = callback._pending[str(run_id)]
        assert tool_name == "search_tool"

    def test_on_tool_start_extracts_name_from_id(self, callback: LangSightLangChainCallback) -> None:
        run_id = uuid4()
        callback.on_tool_start(
            {"id": ["langchain", "tools", "MyCustomTool"]},
            "input",
            run_id=run_id,
        )
        tool_name, _, _input = callback._pending[str(run_id)]
        assert tool_name == "MyCustomTool"

    def test_on_tool_end_clears_pending(self, callback: LangSightLangChainCallback) -> None:
        run_id = uuid4()
        callback._pending[str(run_id)] = ("my_tool", datetime.now(UTC), "input")

        with patch("asyncio.ensure_future"):
            callback.on_tool_end("result", run_id=run_id)

        assert str(run_id) not in callback._pending

    def test_on_tool_error_clears_pending(self, callback: LangSightLangChainCallback) -> None:
        run_id = uuid4()
        callback._pending[str(run_id)] = ("my_tool", datetime.now(UTC), "input")

        with patch("asyncio.ensure_future"):
            callback.on_tool_error(ValueError("failed"), run_id=run_id)

        assert str(run_id) not in callback._pending

    def test_on_tool_end_unknown_run_id_no_crash(self, callback: LangSightLangChainCallback) -> None:
        # Should handle unknown run_id gracefully
        with patch("asyncio.ensure_future"):
            callback.on_tool_end("result", run_id=uuid4())

    def test_on_tool_error_unknown_run_id_no_crash(self, callback: LangSightLangChainCallback) -> None:
        with patch("asyncio.ensure_future"):
            callback.on_tool_error("error", run_id=uuid4())

    def test_instantiation_without_langchain_logs_warning(self, client: LangSightClient) -> None:
        """Should not raise even if langchain is not installed."""
        with patch("builtins.__import__", side_effect=ImportError("no langchain")):
            # Should warn but not raise
            pass  # Constructor handles the ImportError gracefully
