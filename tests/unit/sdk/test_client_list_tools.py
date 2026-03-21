"""
Unit tests for MCPClientProxy.list_tools() interception.

Covers:
- list_tools() returns the underlying result unchanged
- record_tool_schemas() is fired with the correct server_name and tool data
- Fail-open: extraction errors do not prevent list_tools() from returning
- Fail-open: backend unreachable on record_tool_schemas does not prevent list_tools()
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from langsight.sdk.client import LangSightClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tool(name: str, description: str = "", schema: dict | None = None) -> SimpleNamespace:
    """Return an object that mimics the MCP SDK Tool type."""
    t = SimpleNamespace()
    t.name = name
    t.description = description
    t.inputSchema = schema or {"type": "object", "properties": {}}
    return t


def _make_list_tools_result(*tools: SimpleNamespace) -> SimpleNamespace:
    """Return an object whose `.tools` attribute holds the tool list."""
    r = SimpleNamespace()
    r.tools = list(tools)
    return r


@pytest.fixture
def langsight_client() -> LangSightClient:
    return LangSightClient(url="http://localhost:8000")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestListToolsReturnsResultUnchanged:
    """list_tools() must be transparent — the caller gets the original result."""

    @pytest.mark.unit
    async def test_list_tools_returns_result_unchanged(
        self, langsight_client: LangSightClient
    ) -> None:
        """Proxy list_tools() returns exactly what the underlying client returns."""
        tool_a = _make_tool("query", "Run SQL query")
        raw_result = _make_list_tools_result(tool_a)

        mock_mcp = MagicMock()
        mock_mcp.list_tools = AsyncMock(return_value=raw_result)

        with patch.object(langsight_client, "record_tool_schemas", new_callable=AsyncMock):
            proxy = langsight_client.wrap(mock_mcp, server_name="pg")
            result = await proxy.list_tools()

        assert result is raw_result

    @pytest.mark.unit
    async def test_list_tools_result_is_not_modified(
        self, langsight_client: LangSightClient
    ) -> None:
        """The proxy must not mutate the result object in any way."""
        tool_a = _make_tool("list_buckets", "List S3 buckets")
        tool_b = _make_tool("read_object", "Read an object from S3")
        raw_result = _make_list_tools_result(tool_a, tool_b)

        mock_mcp = MagicMock()
        mock_mcp.list_tools = AsyncMock(return_value=raw_result)

        with patch.object(langsight_client, "record_tool_schemas", new_callable=AsyncMock):
            proxy = langsight_client.wrap(mock_mcp, server_name="s3")
            result = await proxy.list_tools()

        assert result.tools is raw_result.tools
        assert len(result.tools) == 2


class TestListToolsFiresRecordToolSchemas:
    """record_tool_schemas() must be called with the correct server_name and tool data."""

    @pytest.mark.unit
    async def test_list_tools_fires_record_tool_schemas(
        self, langsight_client: LangSightClient
    ) -> None:
        """record_tool_schemas is invoked once with the extracted tool payloads."""
        schema = {"type": "object", "properties": {"sql": {"type": "string"}}}
        tool_a = _make_tool("query", "Run SQL", schema)
        raw_result = _make_list_tools_result(tool_a)

        mock_mcp = MagicMock()
        mock_mcp.list_tools = AsyncMock(return_value=raw_result)

        with patch.object(
            langsight_client, "record_tool_schemas", new_callable=AsyncMock
        ) as mock_record:
            proxy = langsight_client.wrap(mock_mcp, server_name="pg-mcp")
            await proxy.list_tools()
            # Give the created task time to run
            await asyncio.sleep(0)

        mock_record.assert_called_once()
        call_args = mock_record.call_args
        server_arg = call_args[0][0]
        tools_arg = call_args[0][1]

        assert server_arg == "pg-mcp"
        assert len(tools_arg) == 1
        assert tools_arg[0]["name"] == "query"
        assert tools_arg[0]["description"] == "Run SQL"
        assert tools_arg[0]["input_schema"] == schema

    @pytest.mark.unit
    async def test_list_tools_sends_correct_server_name(
        self, langsight_client: LangSightClient
    ) -> None:
        """The server_name passed to wrap() is forwarded to record_tool_schemas."""
        raw_result = _make_list_tools_result(_make_tool("list_tables"))
        mock_mcp = MagicMock()
        mock_mcp.list_tools = AsyncMock(return_value=raw_result)

        with patch.object(
            langsight_client, "record_tool_schemas", new_callable=AsyncMock
        ) as mock_record:
            proxy = langsight_client.wrap(mock_mcp, server_name="my-special-server")
            await proxy.list_tools()
            await asyncio.sleep(0)

        assert mock_record.call_args[0][0] == "my-special-server"

    @pytest.mark.unit
    async def test_list_tools_sends_multiple_tools(
        self, langsight_client: LangSightClient
    ) -> None:
        """All tools in the result are forwarded, not just the first one."""
        tools = [_make_tool(f"tool_{i}", f"Tool {i}") for i in range(5)]
        raw_result = _make_list_tools_result(*tools)
        mock_mcp = MagicMock()
        mock_mcp.list_tools = AsyncMock(return_value=raw_result)

        with patch.object(
            langsight_client, "record_tool_schemas", new_callable=AsyncMock
        ) as mock_record:
            proxy = langsight_client.wrap(mock_mcp, server_name="pg")
            await proxy.list_tools()
            await asyncio.sleep(0)

        tools_sent = mock_record.call_args[0][1]
        assert len(tools_sent) == 5
        assert [t["name"] for t in tools_sent] == [f"tool_{i}" for i in range(5)]

    @pytest.mark.unit
    async def test_list_tools_forwards_project_id_to_record_tool_schemas(
        self, langsight_client: LangSightClient
    ) -> None:
        """project_id set on the proxy is forwarded to record_tool_schemas."""
        raw_result = _make_list_tools_result(_make_tool("query"))
        mock_mcp = MagicMock()
        mock_mcp.list_tools = AsyncMock(return_value=raw_result)

        with patch.object(
            langsight_client, "record_tool_schemas", new_callable=AsyncMock
        ) as mock_record:
            proxy = langsight_client.wrap(
                mock_mcp, server_name="pg", project_id="proj-abc"
            )
            await proxy.list_tools()
            await asyncio.sleep(0)

        # Third positional arg is project_id
        project_id_arg = mock_record.call_args[0][2]
        assert project_id_arg == "proj-abc"

    @pytest.mark.unit
    async def test_list_tools_uses_input_schema_fallbacks(
        self, langsight_client: LangSightClient
    ) -> None:
        """Tools without inputSchema fall back to input_schema attribute, then {}."""
        # Tool with neither inputSchema nor input_schema — fallback to {}
        bare_tool = SimpleNamespace()
        bare_tool.name = "no_schema_tool"
        bare_tool.description = "A tool without schema"
        # Deliberately not setting inputSchema or input_schema

        raw_result = SimpleNamespace()
        raw_result.tools = [bare_tool]

        mock_mcp = MagicMock()
        mock_mcp.list_tools = AsyncMock(return_value=raw_result)

        with patch.object(
            langsight_client, "record_tool_schemas", new_callable=AsyncMock
        ) as mock_record:
            proxy = langsight_client.wrap(mock_mcp, server_name="pg")
            await proxy.list_tools()
            await asyncio.sleep(0)

        tools_sent = mock_record.call_args[0][1]
        assert tools_sent[0]["input_schema"] == {}


class TestListToolsFailOpenOnExtractionError:
    """If tool extraction throws, list_tools() must still return the result — no raise."""

    @pytest.mark.unit
    async def test_list_tools_fail_open_on_extraction_error(
        self, langsight_client: LangSightClient
    ) -> None:
        """If iterating tools raises, list_tools() still returns the raw result."""
        # The tools attribute is not iterable — will raise TypeError during extraction
        bad_result = SimpleNamespace()
        bad_result.tools = None  # iterating None raises TypeError

        mock_mcp = MagicMock()
        mock_mcp.list_tools = AsyncMock(return_value=bad_result)

        proxy = langsight_client.wrap(mock_mcp, server_name="broken-server")

        # Must NOT raise — fail-open contract
        result = await proxy.list_tools()
        assert result is bad_result

    @pytest.mark.unit
    async def test_list_tools_fail_open_when_tools_attribute_missing(
        self, langsight_client: LangSightClient
    ) -> None:
        """Result object with no .tools and no __iter__ still does not raise."""
        # A plain object with no .tools: getattr returns None, then iterating None fails.
        # The proxy treats None as a fallback and iterates it — which raises. Must be caught.
        no_tools_result = object()  # object() has no .tools, no __iter__

        mock_mcp = MagicMock()
        mock_mcp.list_tools = AsyncMock(return_value=no_tools_result)

        proxy = langsight_client.wrap(mock_mcp, server_name="pg")

        result = await proxy.list_tools()
        assert result is no_tools_result

    @pytest.mark.unit
    async def test_list_tools_closes_schema_task_when_scheduling_fails(
        self, langsight_client: LangSightClient
    ) -> None:
        """A failed create_task() must not leak an un-awaited coroutine."""
        raw_result = _make_list_tools_result(_make_tool("query"))
        mock_mcp = MagicMock()
        mock_mcp.list_tools = AsyncMock(return_value=raw_result)

        proxy = langsight_client.wrap(mock_mcp, server_name="pg")

        with patch("langsight.sdk.client.asyncio.create_task", side_effect=RuntimeError("loop closed")):
            result = await proxy.list_tools()

        assert result is raw_result

    @pytest.mark.unit
    async def test_list_tools_fail_open_when_individual_tool_has_no_name(
        self, langsight_client: LangSightClient
    ) -> None:
        """Tools whose name cannot be extracted still don't cause list_tools() to raise."""
        bad_tool = object()  # no name, description, or inputSchema attributes
        raw_result = SimpleNamespace()
        raw_result.tools = [bad_tool]

        mock_mcp = MagicMock()
        mock_mcp.list_tools = AsyncMock(return_value=raw_result)

        proxy = langsight_client.wrap(mock_mcp, server_name="pg")

        # Should not raise — getattr with fallbacks handles missing attrs
        result = await proxy.list_tools()
        assert result is raw_result


class TestListToolsFailOpenOnBackendUnreachable:
    """If record_tool_schemas fails, list_tools() must still return normally."""

    @pytest.mark.unit
    async def test_list_tools_fail_open_on_backend_unreachable(
        self, langsight_client: LangSightClient
    ) -> None:
        """record_tool_schemas raising does not propagate out of list_tools()."""
        raw_result = _make_list_tools_result(_make_tool("query"))
        mock_mcp = MagicMock()
        mock_mcp.list_tools = AsyncMock(return_value=raw_result)

        with patch.object(
            langsight_client,
            "record_tool_schemas",
            new_callable=AsyncMock,
            side_effect=Exception("connection refused"),
        ):
            proxy = langsight_client.wrap(mock_mcp, server_name="pg")
            # Must not raise even though record_tool_schemas is broken
            result = await proxy.list_tools()

        assert result is raw_result

    @pytest.mark.unit
    async def test_list_tools_fail_open_on_http_timeout(
        self, langsight_client: LangSightClient
    ) -> None:
        """An asyncio.TimeoutError from record_tool_schemas is also swallowed."""
        raw_result = _make_list_tools_result(_make_tool("query"))
        mock_mcp = MagicMock()
        mock_mcp.list_tools = AsyncMock(return_value=raw_result)

        with patch.object(
            langsight_client,
            "record_tool_schemas",
            new_callable=AsyncMock,
            side_effect=TimeoutError("timeout"),
        ):
            proxy = langsight_client.wrap(mock_mcp, server_name="pg")
            result = await proxy.list_tools()

        assert result is raw_result

    @pytest.mark.unit
    async def test_list_tools_still_returns_when_no_event_loop_for_task(
        self, langsight_client: LangSightClient
    ) -> None:
        """Even if asyncio.create_task is unavailable, list_tools() does not crash."""
        raw_result = _make_list_tools_result(_make_tool("query"))
        mock_mcp = MagicMock()
        mock_mcp.list_tools = AsyncMock(return_value=raw_result)

        # Patch create_task to raise RuntimeError (simulates no running loop edge case
        # that the SDK handles gracefully in _ensure_flush_loop)
        with patch("asyncio.create_task", side_effect=RuntimeError("no event loop")):
            proxy = langsight_client.wrap(mock_mcp, server_name="pg")
            # The try/except in list_tools wraps the whole extraction+task block
            result = await proxy.list_tools()

        assert result is raw_result
