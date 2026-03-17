from __future__ import annotations

import hashlib
import json
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import anyio
from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import Tool

from langsight.exceptions import MCPConnectionError, MCPTimeoutError
from langsight.models import MCPServer, ToolInfo, TransportType

# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _open_session(server: MCPServer) -> AsyncGenerator[ClientSession, None]:
    """Open an authenticated MCP ClientSession for the given server."""
    if server.transport == TransportType.STDIO:
        if not server.command:
            raise MCPConnectionError(
                f"Server '{server.name}': stdio transport requires 'command' to be set."
            )
        params = StdioServerParameters(
            command=server.command,
            args=server.args or [],
            env=server.env or None,
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                yield session

    elif server.transport == TransportType.SSE:
        if not server.url:
            raise MCPConnectionError(
                f"Server '{server.name}': sse transport requires 'url' to be set."
            )
        async with sse_client(server.url) as (read, write):
            async with ClientSession(read, write) as session:
                yield session

    else:
        raise MCPConnectionError(
            f"Server '{server.name}': transport '{server.transport}' is not yet supported. "
            "Supported: stdio, sse."
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def ping(server: MCPServer) -> tuple[float, list[ToolInfo]]:
    """Connect to an MCP server, initialise the session, and fetch the tools list.

    Returns:
        Tuple of (latency_ms, list[ToolInfo]) measured from connection start
        to initialize() completion.

    Raises:
        MCPTimeoutError: connection or initialisation timed out.
        MCPConnectionError: transport misconfiguration or connection refused.
    """
    try:
        with anyio.fail_after(server.timeout_seconds):
            start = time.perf_counter()
            async with _open_session(server) as session:
                await session.initialize()
                latency_ms = (time.perf_counter() - start) * 1000

                tools_result = await session.list_tools()
                tools = _parse_tools(tools_result.tools)

            return latency_ms, tools

    except TimeoutError as exc:
        raise MCPTimeoutError(
            f"Server '{server.name}' timed out after {server.timeout_seconds}s."
        ) from exc


def hash_tools(tools: list[ToolInfo]) -> str:
    """Compute a stable 16-char hash of a tool list for schema drift detection.

    The hash is computed over tool names, descriptions, and input schemas,
    sorted by name to ensure stability regardless of server-side ordering.
    """
    schema = [
        {
            "name": t.name,
            "description": t.description,
            "input_schema": t.input_schema,
        }
        for t in sorted(tools, key=lambda t: t.name)
    ]
    return hashlib.sha256(json.dumps(schema, sort_keys=True).encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_tools(raw_tools: list[Tool]) -> list[ToolInfo]:
    """Convert MCP SDK Tool objects to LangSight ToolInfo models."""
    tools: list[ToolInfo] = []
    for t in raw_tools:
        input_schema: dict[str, Any] = {}
        if t.inputSchema:
            raw_schema = t.inputSchema
            input_schema = (
                raw_schema.model_dump() if hasattr(raw_schema, "model_dump") else dict(raw_schema)
            )
        tools.append(
            ToolInfo(
                name=t.name,
                description=getattr(t, "description", None),
                input_schema=input_schema,
            )
        )
    return tools
