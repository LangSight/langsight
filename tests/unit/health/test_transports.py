"""Unit tests for langsight.health.transports.

Covers:
  - _parse_tools() with all inputSchema variants (string, dict, Pydantic, invalid)
  - ping() health_tool probe logic (tool missing, isError=True, no health_tool)
  - ping() TimeoutError → MCPTimeoutError conversion
  - _open_session() validation: missing command / missing url
"""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.types import Tool

from langsight.exceptions import MCPConnectionError, MCPHealthToolError, MCPTimeoutError
from langsight.health.transports import _open_session, _parse_tools, ping
from langsight.models import MCPServer, ToolInfo, TransportType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tool(name: str, description: str = "desc", input_schema: Any = None) -> Tool:
    """Build a minimal mcp.types.Tool with the given inputSchema value."""
    t = MagicMock(spec=Tool)
    t.name = name
    t.description = description
    t.inputSchema = input_schema
    return t


# ---------------------------------------------------------------------------
# _parse_tools — inputSchema type variants
# ---------------------------------------------------------------------------


class TestParseToolsInputSchema:
    """_parse_tools() must normalise every inputSchema shape to a plain dict."""

    def test_input_schema_as_dict_passes_through(self) -> None:
        """When inputSchema is already a dict, it must be preserved unchanged."""
        schema = {"type": "object", "properties": {"q": {"type": "string"}}}
        raw = _make_tool("search", input_schema=schema)
        tools = _parse_tools([raw])
        assert tools[0].input_schema == schema

    def test_input_schema_as_json_string_is_parsed(self) -> None:
        """Some servers (e.g. atlassian-mcp) serialise inputSchema as a JSON
        string.  _parse_tools must decode it to a dict.
        """
        schema = {"type": "object", "required": ["limit"]}
        raw = _make_tool("list", input_schema=json.dumps(schema))
        tools = _parse_tools([raw])
        assert tools[0].input_schema == schema

    def test_input_schema_json_string_nested_object(self) -> None:
        """Nested JSON string must be fully deserialised, not partially parsed."""
        schema = {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer"},
            },
        }
        raw = _make_tool("search", input_schema=json.dumps(schema))
        tools = _parse_tools([raw])
        assert tools[0].input_schema["properties"]["limit"]["type"] == "integer"

    def test_invalid_json_string_returns_empty_dict(self) -> None:
        """An invalid JSON string must be silently dropped — not raise an exception.

        Regression guard: before the fix, a ValueError from json.loads would
        propagate up and crash the health check entirely.
        """
        raw = _make_tool("broken", input_schema="{not valid json")
        tools = _parse_tools([raw])
        assert tools[0].input_schema == {}

    def test_non_json_string_returns_empty_dict(self) -> None:
        """Arbitrary non-JSON strings (e.g. 'any') must also produce {} silently."""
        raw = _make_tool("ambiguous", input_schema="any")
        tools = _parse_tools([raw])
        assert tools[0].input_schema == {}

    def test_input_schema_pydantic_model_uses_model_dump(self) -> None:
        """If inputSchema has a model_dump() method (Pydantic v2), it must be called."""
        expected = {"type": "object", "properties": {}}
        pydantic_like = MagicMock()
        pydantic_like.model_dump.return_value = expected
        # Must have model_dump but NOT be a plain string
        raw = _make_tool("tool", input_schema=pydantic_like)
        tools = _parse_tools([raw])
        assert tools[0].input_schema == expected
        pydantic_like.model_dump.assert_called_once()

    def test_input_schema_none_yields_empty_dict(self) -> None:
        """None inputSchema must produce an empty dict, not None."""
        raw = _make_tool("no_schema", input_schema=None)
        tools = _parse_tools([raw])
        assert tools[0].input_schema == {}

    def test_input_schema_empty_string_yields_empty_dict(self) -> None:
        """An empty string is not valid JSON — must produce {} without raising."""
        raw = _make_tool("empty", input_schema="")
        tools = _parse_tools([raw])
        assert tools[0].input_schema == {}

    def test_multiple_tools_all_parsed(self) -> None:
        """When multiple tools are passed, every one is parsed independently."""
        raw_tools = [
            _make_tool("a", input_schema={"type": "object"}),
            _make_tool("b", input_schema=json.dumps({"type": "array"})),
            _make_tool("c", input_schema="{bad json"),
        ]
        tools = _parse_tools(raw_tools)
        assert len(tools) == 3
        assert tools[0].input_schema == {"type": "object"}
        assert tools[1].input_schema == {"type": "array"}
        assert tools[2].input_schema == {}

    def test_returns_tool_info_instances(self) -> None:
        raw = _make_tool("t", input_schema={"type": "object"})
        tools = _parse_tools([raw])
        assert all(isinstance(t, ToolInfo) for t in tools)

    def test_tool_name_and_description_preserved(self) -> None:
        raw = _make_tool("my_tool", description="Does something useful")
        tools = _parse_tools([raw])
        assert tools[0].name == "my_tool"
        assert tools[0].description == "Does something useful"


# ---------------------------------------------------------------------------
# ping() — health_tool probe integration
# ---------------------------------------------------------------------------


def _stdio_server(
    health_tool: str | None = None,
    health_tool_args: dict | None = None,
) -> MCPServer:
    kwargs: dict[str, Any] = {
        "name": "test-mcp",
        "transport": TransportType.STDIO,
        "command": "python server.py",
        "timeout_seconds": 5,
    }
    if health_tool is not None:
        kwargs["health_tool"] = health_tool
    if health_tool_args is not None:
        kwargs["health_tool_args"] = health_tool_args
    return MCPServer(**kwargs)


def _mock_session(tool_names: list[str], probe_is_error: bool = False) -> MagicMock:
    """Return a mock ClientSession with the given tools and configurable probe result."""
    session = MagicMock()
    session.initialize = AsyncMock()

    # tools/list result
    tools_result = MagicMock()
    tools_result.tools = [_make_tool(n, input_schema={"type": "object"}) for n in tool_names]
    session.list_tools = AsyncMock(return_value=tools_result)

    # call_tool result
    probe_result = MagicMock()
    probe_result.isError = probe_is_error
    probe_result.content = [MagicMock(text="backend error: connection refused")]
    session.call_tool = AsyncMock(return_value=probe_result)

    return session


class TestPingHealthToolProbe:
    """ping() must correctly handle the health_tool deep-probe logic."""

    async def test_no_health_tool_returns_normally(self) -> None:
        """When health_tool is not configured, ping behaves as before the feature."""
        server = _stdio_server()  # no health_tool
        session = _mock_session(["list_tables", "query"])

        with patch("langsight.health.transports._open_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            latency, tools = await ping(server)

        assert latency > 0
        assert len(tools) == 2
        session.call_tool.assert_not_called()

    async def test_health_tool_found_and_succeeds_returns_normally(self) -> None:
        """When health_tool is present in tools/list and succeeds, ping returns UP."""
        server = _stdio_server(health_tool="search", health_tool_args={"q": "test"})
        session = _mock_session(["search", "list_tables"], probe_is_error=False)

        with patch("langsight.health.transports._open_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            latency, tools = await ping(server)

        assert latency > 0
        assert any(t.name == "search" for t in tools)
        session.call_tool.assert_called_once_with("search", {"q": "test"})

    async def test_health_tool_missing_from_tools_list_raises_mcp_health_tool_error(
        self,
    ) -> None:
        """If the configured health_tool is NOT in tools/list, MCPHealthToolError
        must be raised.  The checker will convert this to DEGRADED.
        """
        server = _stdio_server(health_tool="missing_probe")
        # session has no "missing_probe" tool
        session = _mock_session(["list_tables", "query"])

        with patch("langsight.health.transports._open_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            with pytest.raises(MCPHealthToolError) as exc_info:
                await ping(server)

        assert "missing_probe" in str(exc_info.value)
        # Must not proceed to call_tool when the tool isn't registered
        session.call_tool.assert_not_called()

    async def test_health_tool_missing_error_lists_available_tools(self) -> None:
        """The MCPHealthToolError message must include the available tool names
        so the user knows what tools are actually exposed.
        """
        server = _stdio_server(health_tool="health_check")
        session = _mock_session(["list_tables", "query"])

        with patch("langsight.health.transports._open_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            with pytest.raises(MCPHealthToolError) as exc_info:
                await ping(server)

        msg = str(exc_info.value)
        assert "list_tables" in msg or "query" in msg

    async def test_health_tool_is_error_true_raises_mcp_health_tool_error(self) -> None:
        """When the probe call returns isError=True, MCPHealthToolError is raised.
        This covers the case where the MCP server is alive but the backend
        (e.g. DataHub search endpoint) is down.
        """
        server = _stdio_server(health_tool="search_entities")
        session = _mock_session(["search_entities"], probe_is_error=True)

        with patch("langsight.health.transports._open_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            with pytest.raises(MCPHealthToolError) as exc_info:
                await ping(server)

        assert "search_entities" in str(exc_info.value)

    async def test_health_tool_call_exception_wrapped_as_mcp_health_tool_error(
        self,
    ) -> None:
        """Any exception from call_tool (not MCPHealthToolError) must be caught
        and re-raised as MCPHealthToolError, preserving the original as __cause__.
        """
        server = _stdio_server(health_tool="search_entities")
        session = _mock_session(["search_entities"])
        session.call_tool.side_effect = RuntimeError("unexpected RPC failure")

        with patch("langsight.health.transports._open_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            with pytest.raises(MCPHealthToolError) as exc_info:
                await ping(server)

        # Original exception preserved as cause for debugging
        assert isinstance(exc_info.value.__cause__, RuntimeError)

    async def test_health_tool_is_error_false_does_not_raise(self) -> None:
        """isError=False (the default success case) must NOT raise any exception."""
        server = _stdio_server(health_tool="search_entities")
        session = _mock_session(["search_entities"], probe_is_error=False)

        with patch("langsight.health.transports._open_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            # Should complete without raising
            latency, tools = await ping(server)

        assert latency > 0

    async def test_health_tool_uses_health_tool_args(self) -> None:
        """health_tool_args must be forwarded as-is to session.call_tool."""
        args = {"query": "canary", "limit": 1, "type": "DATASET"}
        server = _stdio_server(health_tool="search_entities", health_tool_args=args)
        session = _mock_session(["search_entities"], probe_is_error=False)

        with patch("langsight.health.transports._open_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            await ping(server)

        session.call_tool.assert_called_once_with("search_entities", args)

    async def test_health_tool_empty_args_uses_empty_dict(self) -> None:
        """When health_tool_args is empty (default), call_tool receives {}."""
        server = _stdio_server(health_tool="ping_backend")
        session = _mock_session(["ping_backend"], probe_is_error=False)

        with patch("langsight.health.transports._open_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            await ping(server)

        _, call_args_positional = session.call_tool.call_args
        # call_tool("ping_backend", {}) — second arg is the args dict
        assert session.call_tool.call_args[0][1] == {}


# ---------------------------------------------------------------------------
# ping() — timeout and error propagation
# ---------------------------------------------------------------------------


class TestPingTimeoutAndErrors:
    """ping() must correctly convert TimeoutError into MCPTimeoutError."""

    async def test_timeout_raises_mcp_timeout_error(self) -> None:
        """anyio.fail_after raises TimeoutError on timeout; ping must wrap it
        as MCPTimeoutError for the checker to display the right status.
        """
        server = _stdio_server()

        with patch("langsight.health.transports._open_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(side_effect=TimeoutError("timeout"))
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            with pytest.raises(MCPTimeoutError) as exc_info:
                await ping(server)

        assert "timed out" in str(exc_info.value).lower()
        assert "test-mcp" in str(exc_info.value)

    async def test_timeout_error_message_includes_timeout_seconds(self) -> None:
        """MCPTimeoutError message must include the server's timeout_seconds value."""
        server = MCPServer(
            name="slow-mcp",
            transport=TransportType.STDIO,
            command="python server.py",
            timeout_seconds=10,
        )
        with patch("langsight.health.transports._open_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(side_effect=TimeoutError())
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            with pytest.raises(MCPTimeoutError) as exc_info:
                await ping(server)

        assert "10" in str(exc_info.value)

    async def test_mcp_health_tool_error_propagates_from_ping(self) -> None:
        """MCPHealthToolError raised inside ping must propagate — not be caught
        as MCPTimeoutError. The checker needs to distinguish DEGRADED from DOWN.
        """
        server = _stdio_server(health_tool="probe")
        session = _mock_session(["probe"])
        # probe succeeds on tools/list but the session.call_tool raises directly
        session.call_tool.side_effect = MCPHealthToolError("tool returned error")

        with patch("langsight.health.transports._open_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            with pytest.raises(MCPHealthToolError):
                await ping(server)


# ---------------------------------------------------------------------------
# _open_session() — configuration validation (no real transport needed)
# ---------------------------------------------------------------------------


class TestOpenSessionValidation:
    """_open_session raises MCPConnectionError for misconfigured servers."""

    async def test_stdio_without_command_raises(self) -> None:
        """stdio transport without command= must raise MCPConnectionError immediately."""
        server = MCPServer(
            name="no-cmd",
            transport=TransportType.STDIO,
            # no command
        )
        with pytest.raises(MCPConnectionError) as exc_info:
            async with _open_session(server):
                pass  # pragma: no cover

        assert "command" in str(exc_info.value).lower()
        assert "no-cmd" in str(exc_info.value)

    async def test_sse_without_url_raises(self) -> None:
        """sse transport without url= must raise MCPConnectionError immediately."""
        server = MCPServer(
            name="no-url-sse",
            transport=TransportType.SSE,
            # no url
        )
        with pytest.raises(MCPConnectionError) as exc_info:
            async with _open_session(server):
                pass  # pragma: no cover

        assert "url" in str(exc_info.value).lower()
        assert "no-url-sse" in str(exc_info.value)

    async def test_streamable_http_without_url_raises(self) -> None:
        """streamable_http transport without url= must raise MCPConnectionError."""
        server = MCPServer(
            name="no-url-http",
            transport=TransportType.STREAMABLE_HTTP,
            # no url
        )
        with pytest.raises(MCPConnectionError) as exc_info:
            async with _open_session(server):
                pass  # pragma: no cover

        assert "url" in str(exc_info.value).lower()
        assert "no-url-http" in str(exc_info.value)
