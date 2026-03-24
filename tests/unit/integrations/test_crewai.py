from __future__ import annotations

from unittest.mock import patch

import pytest

from langsight.integrations.crewai import LangSightCrewAICallback
from langsight.sdk.client import LangSightClient
from langsight.sdk.models import ToolCallStatus


@pytest.fixture
def client() -> LangSightClient:
    return LangSightClient(url="http://localhost:8000")


@pytest.fixture
def callback(client: LangSightClient) -> LangSightCrewAICallback:
    return LangSightCrewAICallback(
        client=client,
        server_name="test-server",
        agent_name="test-agent",
    )


class TestLangSightCrewAICallback:
    def test_on_tool_start_records_pending(self, callback: LangSightCrewAICallback) -> None:
        callback.on_tool_start("query", {"sql": "SELECT 1"})
        assert "query" in callback._pending

    async def test_on_tool_end_sends_success_span(
        self, callback: LangSightCrewAICallback, client: LangSightClient
    ) -> None:
        callback.on_tool_start("query", "SELECT 1")
        with patch.object(client, "buffer_span") as mock_send:
            await callback.on_tool_end("query", [{"id": 1}])

        mock_send.assert_called_once()
        span = mock_send.call_args[0][0]
        assert span.tool_name == "query"
        assert span.status == ToolCallStatus.SUCCESS
        assert span.server_name == "test-server"
        assert span.agent_name == "test-agent"

    async def test_on_tool_error_sends_error_span(
        self, callback: LangSightCrewAICallback, client: LangSightClient
    ) -> None:
        callback.on_tool_start("query", "SELECT 1")
        with patch.object(client, "buffer_span") as mock_send:
            await callback.on_tool_error("query", RuntimeError("db error"))

        span = mock_send.call_args[0][0]
        assert span.status == ToolCallStatus.ERROR
        assert "db error" in span.error  # type: ignore[operator]

    async def test_pending_cleared_after_tool_end(
        self, callback: LangSightCrewAICallback, client: LangSightClient
    ) -> None:
        callback.on_tool_start("query", "SELECT 1")
        with patch.object(client, "buffer_span"):
            await callback.on_tool_end("query", [])
        assert "query" not in callback._pending

    async def test_pending_cleared_after_tool_error(
        self, callback: LangSightCrewAICallback, client: LangSightClient
    ) -> None:
        callback.on_tool_start("query", "SELECT 1")
        with patch.object(client, "buffer_span"):
            await callback.on_tool_error("query", "error")
        assert "query" not in callback._pending

    async def test_tool_end_without_start_doesnt_crash(
        self, callback: LangSightCrewAICallback, client: LangSightClient
    ) -> None:
        # Should handle missing start gracefully
        with patch.object(client, "buffer_span"):
            await callback.on_tool_end("unknown_tool", [])


class TestLangSightPydanticAIDecorator:
    async def test_decorator_traces_success(self) -> None:
        from langsight.integrations.pydantic_ai import langsight_tool

        client = LangSightClient(url="http://localhost:8000")

        @langsight_tool(client=client, server_name="pg")
        async def my_tool(sql: str) -> list:
            return [{"id": 1}]

        with patch.object(client, "buffer_span") as mock_send:
            result = await my_tool("SELECT 1")

        assert result == [{"id": 1}]
        mock_send.assert_called_once()
        span = mock_send.call_args[0][0]
        assert span.tool_name == "my_tool"
        assert span.status == ToolCallStatus.SUCCESS

    async def test_decorator_traces_error(self) -> None:
        from langsight.integrations.pydantic_ai import langsight_tool

        client = LangSightClient(url="http://localhost:8000")

        @langsight_tool(client=client, server_name="pg")
        async def failing_tool() -> list:
            raise ValueError("bad input")

        with patch.object(client, "buffer_span") as mock_send:
            with pytest.raises(ValueError):
                await failing_tool()

        span = mock_send.call_args[0][0]
        assert span.status == ToolCallStatus.ERROR

    async def test_decorator_preserves_function_name(self) -> None:
        from langsight.integrations.pydantic_ai import langsight_tool

        client = LangSightClient(url="http://localhost:8000")

        @langsight_tool(client=client, server_name="pg")
        async def my_named_tool() -> None:
            pass

        assert my_named_tool.__name__ == "my_named_tool"
