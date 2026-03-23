"""
LangGraph integration — graph-aware tracing via LangSight.

Extends the LangChain callback with LangGraph-specific context:
- Node name tracking (which graph node is executing)
- Graph-level span grouping
- Conditional routing visibility

Usage::

    from langsight.sdk import LangSightClient
    from langsight.integrations.langgraph import LangSightLangGraphCallback

    client = LangSightClient(url="http://localhost:8000")
    callback = LangSightLangGraphCallback(
        client=client,
        agent_name="my-graph",
        session_id="sess-001",
    )

    # Pass to LangGraph — all tool calls + node transitions traced
    result = await graph.ainvoke(
        {"input": "..."},
        config={"callbacks": [callback]},
    )

Also works with synchronous ``graph.invoke()``.

Note: The basic LangChain callback (``LangSightLangChainCallback``) also
works with LangGraph since LangGraph accepts LangChain callbacks. This
integration adds node-level context that the basic callback doesn't capture.
"""

from __future__ import annotations

import asyncio
import threading
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog

from langsight.integrations.base import BaseIntegration
from langsight.sdk.client import LangSightClient
from langsight.sdk.models import ToolCallSpan, ToolCallStatus

logger = structlog.get_logger()


def _fire_and_forget(coro: Any) -> None:
    """Schedule a coroutine from a synchronous LangChain/LangGraph callback."""
    try:
        loop = asyncio.get_running_loop()
        if loop.is_running() and not loop.is_closed():
            loop.create_task(coro)
            return
    except RuntimeError:
        pass
    thread = threading.Thread(target=asyncio.run, args=(coro,), daemon=True)
    thread.start()


class LangSightLangGraphCallback(BaseIntegration):
    """LangGraph callback that traces tool calls with graph node context.

    Implements LangChain's BaseCallbackHandler protocol (which LangGraph
    accepts) and adds node-level tracking:

    - ``on_chain_start`` / ``on_chain_end`` — tracks which graph node is active
    - ``on_tool_start`` / ``on_tool_end`` — traces tool calls with node context
    - Captures node name in the span's ``server_name`` field

    The span tree shows:  graph_name → node_name → tool_name
    """

    def __init__(
        self,
        client: LangSightClient,
        server_name: str = "langgraph",
        agent_name: str | None = None,
        session_id: str | None = None,
        trace_id: str | None = None,
    ) -> None:
        # Lazy import — try langchain-core first (available without full langchain),
        # fall back to langchain for older installations.
        try:
            try:
                from langchain_core.callbacks.base import BaseCallbackHandler
            except ImportError:
                from langchain.callbacks.base import BaseCallbackHandler  # type: ignore[no-redef]

            self.__class__.__bases__ = (BaseIntegration, BaseCallbackHandler)
            BaseCallbackHandler.__init__(self)
        except ImportError:
            logger.warning(
                "langchain-core not installed. Install with: pip install langchain-core langgraph"
            )

        super().__init__(
            client=client,
            server_name=server_name,
            agent_name=agent_name,
            session_id=session_id,
        )
        self._trace_id = trace_id
        # Tool call tracking: run_id → (tool_name, started_at, node_name)
        self._pending: dict[str, tuple[str, datetime, str | None]] = {}
        # Node tracking: chain_run_id → node_name
        self._active_nodes: dict[str, str] = {}
        # Current node name (most recently started)
        self._current_node: str | None = None

    # -- Chain (node) lifecycle --

    def on_chain_start(
        self,
        serialized: dict[str, Any],
        inputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Track which LangGraph node is currently executing."""
        node_name = serialized.get("name") or serialized.get("id", ["unknown"])[-1] or "unknown"
        key = str(run_id)
        self._active_nodes[key] = node_name
        self._current_node = node_name

    def on_chain_end(
        self,
        outputs: dict[str, Any],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """Clean up node tracking when a chain/node completes."""
        key = str(run_id)
        self._active_nodes.pop(key, None)
        # Reset current node to the most recent remaining active node
        if self._active_nodes:
            self._current_node = list(self._active_nodes.values())[-1]
        else:
            self._current_node = None

    def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """Clean up on chain error."""
        self.on_chain_end({}, run_id=run_id)

    # -- Tool lifecycle --

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """Called when a tool call begins within a graph node."""
        tool_name = serialized.get("name") or serialized.get("id", ["unknown"])[-1] or "unknown"
        self._pending[str(run_id)] = (tool_name, datetime.now(UTC), self._current_node)

    def on_tool_end(
        self,
        output: Any,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """Called when a tool call completes successfully."""
        key = str(run_id)
        if key not in self._pending:
            return
        tool_name, started_at, node_name = self._pending.pop(key)
        # Use node_name as server_name if available — shows graph context
        effective_server = f"{self._server_name}/{node_name}" if node_name else self._server_name
        span = ToolCallSpan.record(
            server_name=effective_server,
            tool_name=tool_name,
            started_at=started_at,
            status=ToolCallStatus.SUCCESS,
            agent_name=self._agent_name,
            session_id=self._session_id,
            trace_id=self._trace_id,
            project_id=getattr(self._client, "_project_id", None) or "",
        )
        _fire_and_forget(self._client.send_span(span))

    def on_tool_error(
        self,
        error: BaseException | Any,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """Called when a tool call raises an error."""
        key = str(run_id)
        if key not in self._pending:
            return
        tool_name, started_at, node_name = self._pending.pop(key)
        effective_server = f"{self._server_name}/{node_name}" if node_name else self._server_name
        span = ToolCallSpan.record(
            server_name=effective_server,
            tool_name=tool_name,
            started_at=started_at,
            status=ToolCallStatus.ERROR,
            error=str(error),
            agent_name=self._agent_name,
            session_id=self._session_id,
            trace_id=self._trace_id,
            project_id=getattr(self._client, "_project_id", None) or "",
        )
        _fire_and_forget(self._client.send_span(span))

    # -- LLM lifecycle (optional — captures model usage) --

    def on_llm_start(self, serialized: dict[str, Any], prompts: list[str], **kwargs: Any) -> None:
        """No-op — can be extended to capture LLM spans."""

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        """No-op — can be extended to capture LLM spans."""
