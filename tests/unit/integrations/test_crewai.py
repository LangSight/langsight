from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from langsight.integrations.crewai import (
    LangSightCrewAICallback,
    _parse_mcp_tool_name,
)
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


class TestParseMcpToolName:
    def test_mcp_pattern_returns_server_and_tool(self) -> None:
        server, tool = _parse_mcp_tool_name("mcp__postgres__query")
        assert server == "postgres"
        assert tool == "query"

    def test_mcp_pattern_two_parts_only(self) -> None:
        server, tool = _parse_mcp_tool_name("mcp__postgres")
        assert server == "postgres"
        assert tool == "mcp__postgres"

    def test_non_mcp_name_returns_none_server(self) -> None:
        server, tool = _parse_mcp_tool_name("run_sql")
        assert server is None
        assert tool == "run_sql"

    def test_mcp_tool_with_underscores_in_tool_name(self) -> None:
        server, tool = _parse_mcp_tool_name("mcp__s3__list_buckets")
        assert server == "s3"
        assert tool == "list_buckets"


class TestSetAgentName:
    def test_set_agent_name_updates_internal_name(
        self, callback: LangSightCrewAICallback
    ) -> None:
        callback.set_agent_name("SQL Analyst")
        assert callback._agent_name == "SQL Analyst"

    async def test_set_agent_name_reflected_in_span(
        self, client: LangSightClient
    ) -> None:
        cb = LangSightCrewAICallback(client=client, server_name="pg")
        cb.set_agent_name("Data Engineer")
        cb.on_tool_start("query", "SELECT 1")
        with patch.object(client, "buffer_span") as mock_send:
            await cb.on_tool_end("query", [{"id": 1}])
        span = mock_send.call_args[0][0]
        assert span.agent_name == "Data Engineer"


class TestMcpToolNameParsing:
    async def test_mcp_tool_name_extracts_server_on_end(
        self, client: LangSightClient
    ) -> None:
        cb = LangSightCrewAICallback(client=client, server_name="fallback")
        cb.on_tool_start("mcp__postgres__query", "SELECT 1")
        with patch.object(client, "buffer_span") as mock_send:
            await cb.on_tool_end("mcp__postgres__query", [{"id": 1}])
        span = mock_send.call_args[0][0]
        assert span.server_name == "postgres"
        assert span.tool_name == "query"

    async def test_mcp_tool_name_extracts_server_on_error(
        self, client: LangSightClient
    ) -> None:
        cb = LangSightCrewAICallback(client=client, server_name="fallback")
        cb.on_tool_start("mcp__s3__list_buckets", {})
        with patch.object(client, "buffer_span") as mock_send:
            await cb.on_tool_error("mcp__s3__list_buckets", RuntimeError("denied"))
        span = mock_send.call_args[0][0]
        assert span.server_name == "s3"
        assert span.tool_name == "list_buckets"

    async def test_non_mcp_tool_uses_configured_server(
        self, callback: LangSightCrewAICallback, client: LangSightClient
    ) -> None:
        callback.on_tool_start("run_sql", "SELECT 1")
        with patch.object(client, "buffer_span") as mock_send:
            await callback.on_tool_end("run_sql", [])
        span = mock_send.call_args[0][0]
        assert span.server_name == "test-server"


class TestAgentKwargsExtraction:
    def test_on_tool_start_extracts_agent_role_from_kwargs(
        self, callback: LangSightCrewAICallback
    ) -> None:
        """When CrewAI passes agent= kwarg, its role becomes agent_name."""
        # Reset agent_name so extraction can fire
        callback._agent_name = None
        mock_agent = MagicMock()
        mock_agent.role = "Research Analyst"
        callback.on_tool_start("search", "climate change", agent=mock_agent)
        assert callback._agent_name == "Research Analyst"

    def test_on_tool_start_skips_agent_extraction_when_name_set(
        self, callback: LangSightCrewAICallback
    ) -> None:
        """Existing agent_name is not overwritten by kwargs."""
        mock_agent = MagicMock()
        mock_agent.role = "Different Role"
        callback.on_tool_start("search", "query", agent=mock_agent)
        # Original name from fixture should be preserved
        assert callback._agent_name == "test-agent"


class TestSessionContextInjection:
    def test_on_tool_start_picks_up_session_from_context(
        self, client: LangSightClient
    ) -> None:
        """session_id is lazily resolved from _session_ctx on first tool start."""
        from langsight.sdk.auto_patch import _session_ctx

        cb = LangSightCrewAICallback(client=client)
        assert cb._session_id is None

        token = _session_ctx.set("ctx-session-42")
        try:
            cb.on_tool_start("ping", {})
            assert cb._session_id == "ctx-session-42"
        finally:
            _session_ctx.reset(token)
