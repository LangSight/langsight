"""
CrewAI integration for LangSight.

Traces every tool call made by a CrewAI agent and sends ToolCallSpans
to the LangSight API.

Usage:
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


class LangSightCrewAICallback(BaseIntegration):
    """CrewAI callback that traces MCP tool calls via LangSight.

    Drop-in addition to any CrewAI Agent or Crew — add to the
    `callbacks` list and every tool call is automatically traced.
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

    # ---------------------------------------------------------------------------
    # CrewAI callback interface
    # Compatible with crewai.callbacks.BaseCallbackHandler
    # ---------------------------------------------------------------------------

    def on_tool_start(
        self,
        tool_name: str,
        tool_input: str | dict,
        **kwargs: Any,
    ) -> None:
        """Called by CrewAI when a tool call begins."""
        self._pending[tool_name] = datetime.now(UTC)

    async def on_tool_end(
        self,
        tool_name: str,
        tool_output: Any,
        **kwargs: Any,
    ) -> None:
        """Called by CrewAI when a tool call completes successfully."""
        started_at = self._pending.pop(tool_name, datetime.now(UTC))
        await self._record(
            tool_name=tool_name,
            started_at=started_at,
            status=ToolCallStatus.SUCCESS,
        )

    async def on_tool_error(
        self,
        tool_name: str,
        error: Exception | str,
        **kwargs: Any,
    ) -> None:
        """Called by CrewAI when a tool call fails."""
        started_at = self._pending.pop(tool_name, datetime.now(UTC))
        await self._record(
            tool_name=tool_name,
            started_at=started_at,
            status=ToolCallStatus.ERROR,
            error=str(error),
        )
