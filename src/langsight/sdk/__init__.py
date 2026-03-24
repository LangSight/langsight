"""
LangSight SDK — agent runtime reliability.

Quick start::

    import langsight

    ls = langsight.init()  # reads LANGSIGHT_URL / API_KEY / PROJECT_ID from env
    traced_mcp = ls.wrap(mcp_session, server_name="postgres-mcp")
    result = await traced_mcp.call_tool("query", {"sql": "SELECT 1"})

Explicit init::

    from langsight.sdk import LangSightClient

    client = LangSightClient(url="http://localhost:8000", project_id="my-project")
    traced_llm = client.wrap_llm(OpenAI(), agent_name="my-agent")
    response = traced_llm.chat.completions.create(model="gpt-4o", tools=[...])
"""

from __future__ import annotations

import os
from typing import Any

import structlog

from langsight.sdk.client import LangSightClient, MCPClientProxy
from langsight.sdk.models import PreventionEvent, ToolCallSpan, ToolCallStatus

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
    "init",
]
