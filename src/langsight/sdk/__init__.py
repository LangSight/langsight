"""
LangSight SDK — agent runtime reliability.

Zero-code auto-instrumentation::

    import langsight
    langsight.auto_patch()   # patches OpenAI, Anthropic, Google SDKs

    from openai import OpenAI
    client = OpenAI()        # automatically traced — no wrap_llm() needed

    async with langsight.session(agent_name="orchestrator") as session_id:
        response = await client.chat.completions.create(model="gpt-4o", ...)

Explicit wrapping (original approach)::

    import langsight

    ls = langsight.init()  # reads LANGSIGHT_URL / API_KEY / PROJECT_ID from env
    traced_mcp = ls.wrap(mcp_session, server_name="postgres-mcp")
    result = await traced_mcp.call_tool("query", {"sql": "SELECT 1"})
"""

from __future__ import annotations

import os
from typing import Any

import structlog

from langsight.sdk.auto_patch import (
    SessionContext,
    auto_patch,
    clear_context,
    session,
    set_context,
    unpatch,
)
from langsight.sdk.client import LangSightClient, MCPClientProxy
from langsight.sdk.models import PreventionEvent, ToolCallSpan, ToolCallStatus
from langsight.sdk.trace import trace

_logger = structlog.get_logger()


def init(
    url: str | None = None,
    api_key: str | None = None,
    project_id: str | None = None,
    **kwargs: Any,
) -> LangSightClient | None:
    """Initialize LangSight from environment variables.

    Reads ``LANGSIGHT_URL``, ``LANGSIGHT_API_KEY``, and ``LANGSIGHT_PROJECT_ID``
    from the environment.  Explicit keyword arguments override env vars.

    Returns ``None`` if ``LANGSIGHT_URL`` is not set — safe for unconditional use::

        ls = langsight.init()
        if ls:
            traced = ls.wrap(session, server_name="my-server")

    All extra ``**kwargs`` are forwarded to :class:`LangSightClient` (e.g.
    ``loop_detection=True``, ``max_steps=25``).
    """
    resolved_url = url or os.environ.get("LANGSIGHT_URL")
    if not resolved_url:
        _logger.debug("langsight.init.skipped", reason="LANGSIGHT_URL not set")
        return None

    return LangSightClient(
        url=resolved_url,
        api_key=api_key or os.environ.get("LANGSIGHT_API_KEY"),
        project_id=project_id or os.environ.get("LANGSIGHT_PROJECT_ID"),
        **kwargs,
    )


__all__ = [
    "LangSightClient",
    "MCPClientProxy",
    "PreventionEvent",
    "ToolCallSpan",
    "ToolCallStatus",
    "auto_patch",
    "clear_context",
    "init",
    "session",
    "set_context",
    "trace",
    "unpatch",
]
