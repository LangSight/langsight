"""
LangSight SDK — 2-line MCP observability integration.

Usage:
    from langsight.sdk import LangSightClient

    client = LangSightClient(url="http://localhost:8000")
    traced_mcp = client.wrap(mcp_session, server_name="postgres-mcp")

    # All call_tool() calls are now traced
    result = await traced_mcp.call_tool("query", {"sql": "SELECT 1"})
"""

from __future__ import annotations

from langsight.sdk.client import LangSightClient, MCPClientProxy
from langsight.sdk.models import PreventionEvent, ToolCallSpan, ToolCallStatus

__all__ = [
    "LangSightClient",
    "MCPClientProxy",
    "PreventionEvent",
    "ToolCallSpan",
    "ToolCallStatus",
]
