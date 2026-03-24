"""
LangSight SDK — agent runtime reliability.

Usage (MCP):
    from langsight.sdk import LangSightClient

    client = LangSightClient(url="http://localhost:8000")
    traced_mcp = client.wrap(mcp_session, server_name="postgres-mcp")
    result = await traced_mcp.call_tool("query", {"sql": "SELECT 1"})

Usage (LLM SDK — OpenAI, Anthropic, Gemini):
    from langsight.sdk import LangSightClient

    client = LangSightClient(url="http://localhost:8000")
    traced_llm = client.wrap_llm(OpenAI(), agent_name="my-agent")
    response = traced_llm.chat.completions.create(model="gpt-4o", tools=[...])
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
