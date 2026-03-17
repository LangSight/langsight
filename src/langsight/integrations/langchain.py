"""
LangChain integration for LangSight.

Traces every tool call made by LangChain agents, LangGraph workflows,
and any LangChain-based framework (Langflow, LangGraph, etc.)

Usage:
    from langsight.sdk import LangSightClient
    from langsight.integrations.langchain import LangSightLangChainCallback

    client = LangSightClient(url="http://localhost:8000")
    callback = LangSightLangChainCallback(
        client=client,
        server_name="my-tools",
        agent_name="my-agent",
    )

    # LangChain agent
    agent = initialize_agent(tools, llm, callbacks=[callback])

    # LangGraph
    graph.invoke(input, config={"callbacks": [callback]})

    # Langflow — add to any component's callbacks list
    # Same pattern works for any LangChain-based framework

This integration does NOT import langchain at module level — LangSight can
be installed without langchain.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog

from langsight.integrations.base import BaseIntegration
from langsight.sdk.client import LangSightClient
from langsight.sdk.models import ToolCallStatus

logger = structlog.get_logger()


class LangSightLangChainCallback(BaseIntegration):
    """LangChain BaseCallbackHandler that traces tool calls via LangSight.

    Works with:
    - LangChain agents (initialize_agent, AgentExecutor)
    - LangGraph workflows
    - Langflow (add to component callbacks)
    - Any LangChain-based framework

    Inherits from BaseIntegration for shared span recording logic.
    Inherits from LangChain's BaseCallbackHandler via lazy import.
    """

    def __init__(
        self,
        client: LangSightClient,
        server_name: str = "langchain-tools",
        agent_name: str | None = None,
        session_id: str | None = None,
        trace_id: str | None = None,
    ) -> None:
        # Lazy import — don't require langchain at module level
        try:
            from langchain.callbacks.base import (  # type: ignore[import-not-found]
                BaseCallbackHandler,
            )

            # Dynamically inherit from BaseCallbackHandler
            self.__class__.__bases__ = (BaseIntegration, BaseCallbackHandler)
            BaseCallbackHandler.__init__(self)
        except ImportError:
            logger.warning("langchain not installed. Install with: pip install langchain")

        super().__init__(
            client=client,
            server_name=server_name,
            agent_name=agent_name,
            session_id=session_id,
        )
        self._trace_id = trace_id
        # run_id (UUID) → (tool_name, started_at)
        self._pending: dict[str, tuple[str, datetime]] = {}

    # ---------------------------------------------------------------------------
    # LangChain callback interface
    # ---------------------------------------------------------------------------

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """Called when a LangChain tool call begins."""
        tool_name = serialized.get("name") or serialized.get("id", ["unknown"])[-1] or "unknown"
        self._pending[str(run_id)] = (tool_name, datetime.now(UTC))

    def on_tool_end(
        self,
        output: Any,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """Called when a LangChain tool call completes successfully."""
        key = str(run_id)
        if key not in self._pending:
            return
        tool_name, started_at = self._pending.pop(key)
        asyncio.ensure_future(
            self._record(
                tool_name=tool_name,
                started_at=started_at,
                status=ToolCallStatus.SUCCESS,
                trace_id=self._trace_id,
            )
        )

    def on_tool_error(
        self,
        error: BaseException | Any,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """Called when a LangChain tool call raises an error."""
        key = str(run_id)
        if key not in self._pending:
            return
        tool_name, started_at = self._pending.pop(key)
        asyncio.ensure_future(
            self._record(
                tool_name=tool_name,
                started_at=started_at,
                status=ToolCallStatus.ERROR,
                error=str(error),
                trace_id=self._trace_id,
            )
        )
