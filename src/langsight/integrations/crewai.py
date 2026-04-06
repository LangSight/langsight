"""
CrewAI integration for LangSight.

Traces every tool call made by a CrewAI agent and sends ToolCallSpans
to the LangSight API.

Usage (zero-code, recommended):
    import langsight
    langsight.auto_patch()  # patches CrewAI automatically

    # Your existing CrewAI code unchanged:
    crew = Crew(agents=[...], tasks=[...])
    result = crew.kickoff()

Usage (manual / legacy):
    from langsight.sdk import LangSightClient
    from langsight.integrations.crewai import LangSightCrewAICallback

    client = LangSightClient(url="http://localhost:8000")
    callback = LangSightCrewAICallback(
        client=client,
        server_name="my-mcp-server",
        agent_name="customer-support-agent",
    )

    agent = Agent(
        role="Support Agent",
        tools=[my_mcp_tool],
        callbacks=[callback],       # ← one line added
    )

CrewAI ships with crewai>=0.1.0. This integration does NOT import crewai
at module level — it only imports when the callback methods are called,
so LangSight can be installed without crewai.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from langsight.integrations.base import BaseIntegration
from langsight.sdk.client import LangSightClient
from langsight.sdk.models import ToolCallStatus

# MCP tool name pattern: mcp__<server>__<tool>
_MCP_PREFIX = "mcp__"


def _parse_mcp_tool_name(raw_tool_name: str) -> tuple[str | None, str]:
    """Parse a CrewAI tool name into (server_name, tool_name).

    CrewAI MCP tools follow the ``mcp__<server>__<tool>`` convention used
    across the LangSight SDK.  Returns ``(None, raw_tool_name)`` for
    non-MCP tools.
    """
    if raw_tool_name.startswith(_MCP_PREFIX):
        parts = raw_tool_name.split("__", 2)
        server = parts[1] if len(parts) >= 2 else None
        tool = parts[2] if len(parts) == 3 else raw_tool_name
        return server, tool
    return None, raw_tool_name


class LangSightCrewAICallback(BaseIntegration):
    """CrewAI callback that traces MCP tool calls via LangSight.

    Drop-in addition to any CrewAI Agent or Crew — add to the
    `callbacks` list and every tool call is automatically traced.

    The auto-patcher (``langsight.auto_patch()``) injects this callback
    automatically into every ``crewai.Crew`` and ``crewai.Agent`` — no
    manual registration required.
    """

    def __init__(
        self,
        client: LangSightClient,
        server_name: str = "crewai-mcp",
        agent_name: str | None = None,
        session_id: str | None = None,
    ) -> None:
        super().__init__(
            client=client,
            server_name=server_name,
            agent_name=agent_name,
            session_id=session_id,
        )
        # Track in-flight tool calls: tool_name → started_at
        self._pending: dict[str, datetime] = {}

    def set_agent_name(self, name: str) -> None:
        """Override the agent name — called by the auto-patcher with the
        CrewAI agent ``role`` field (e.g. "SQL Analyst").
        """
        self._agent_name = name

    # ---------------------------------------------------------------------------
    # CrewAI callback interface
    # Compatible with crewai.callbacks.BaseCallbackHandler
    # ---------------------------------------------------------------------------

    def on_tool_start(
        self,
        tool_name: str,
        tool_input: str | dict[str, Any],
        **kwargs: Any,
    ) -> None:
        """Called by CrewAI when a tool call begins."""
        # Resolve session from active context if not set at construction time
        if self._session_id is None:
            try:
                from langsight.sdk.auto_patch import _session_ctx

                self._session_id = _session_ctx.get()
            except ImportError:
                pass

        # Attempt to extract agent_name from the tool's agent attribute
        # (available in some CrewAI versions via kwargs["agent"])
        if self._agent_name is None:
            agent_obj = kwargs.get("agent")
            if agent_obj is not None:
                role = getattr(agent_obj, "role", None)
                if role:
                    self._agent_name = str(role)

        self._pending[tool_name] = datetime.now(UTC)

    async def on_tool_end(
        self,
        tool_name: str,
        tool_output: Any,
        **kwargs: Any,
    ) -> None:
        """Called by CrewAI when a tool call completes successfully."""
        started_at = self._pending.pop(tool_name, datetime.now(UTC))

        # Resolve server_name from MCP tool name pattern
        mcp_server, resolved_tool = _parse_mcp_tool_name(tool_name)
        effective_server = mcp_server or self._server_name

        self._record(
            tool_name=resolved_tool,
            started_at=started_at,
            status=ToolCallStatus.SUCCESS,
            server_name=effective_server,
        )

    async def on_tool_error(
        self,
        tool_name: str,
        error: Exception | str,
        **kwargs: Any,
    ) -> None:
        """Called by CrewAI when a tool call fails."""
        started_at = self._pending.pop(tool_name, datetime.now(UTC))

        # Resolve server_name from MCP tool name pattern
        mcp_server, resolved_tool = _parse_mcp_tool_name(tool_name)
        effective_server = mcp_server or self._server_name

        self._record(
            tool_name=resolved_tool,
            started_at=started_at,
            status=ToolCallStatus.ERROR,
            error=str(error),
            server_name=effective_server,
        )
