"""
OpenAI Agents SDK integration — traces tool calls via LangSight.

The OpenAI Agents SDK uses a tracing system where you can provide custom
trace processors. This integration hooks into the tool execution lifecycle
via the ``on_tool_start`` / ``on_tool_end`` callbacks in the ``RunHooks``
protocol.

Usage::

    from langsight.sdk import LangSightClient
    from langsight.integrations.openai_agents import LangSightOpenAIHooks

    client = LangSightClient(url="http://localhost:8000")
    hooks = LangSightOpenAIHooks(client=client, agent_name="my-agent")

    # Pass as run hooks — all tool calls traced automatically
    from agents import Runner
    result = await Runner.run(agent, input="...", hooks=hooks)

Also works as a context-based decorator for individual tool functions::

    from langsight.integrations.openai_agents import langsight_openai_tool

    @langsight_openai_tool(client=client, server_name="my-tools")
    async def search(query: str) -> str:
        ...
"""

from __future__ import annotations

import functools
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import Any, TypeVar

import structlog

from langsight.integrations.base import BaseIntegration
from langsight.sdk.client import LangSightClient
from langsight.sdk.models import ToolCallSpan, ToolCallStatus

logger = structlog.get_logger()

F = TypeVar("F", bound=Callable[..., Coroutine[Any, Any, Any]])


class LangSightOpenAIHooks(BaseIntegration):
    """OpenAI Agents SDK RunHooks that traces tool calls via LangSight.

    Implements the ``RunHooks`` protocol from ``agents``:
    - ``on_agent_start(context, agent)`` — tracks active agent span
    - ``on_tool_start(context, agent, tool)`` — records start time
    - ``on_tool_end(context, agent, tool, result)`` — emits success span
    - ``on_tool_error(context, agent, tool, error)`` — emits error span
    - ``on_handoff(context, from_agent, to_agent)`` — emits handoff span

    Lineage hardening (v1.0 protocol):
    - Tracks active agent spans so handoffs can set parent_span_id
    - Stores handoff span_id so child agent tool calls link to the handoff
    - Propagates agent_name from the runtime agent object, not just constructor

    All methods are async and fail-open: exceptions in tracing never
    propagate to the agent runtime.
    """

    def __init__(
        self,
        client: LangSightClient,
        server_name: str = "openai-agents",
        agent_name: str | None = None,
        session_id: str | None = None,
        trace_id: str | None = None,
    ) -> None:
        super().__init__(
            client=client,
            server_name=server_name,
            agent_name=agent_name,
            session_id=session_id,
        )
        self._trace_id = trace_id
        self._pending: dict[str, datetime] = {}  # tool_key → started_at

        # --- Lineage tracking ---
        # agent object id → span_id of its active agent lifecycle span
        self._active_agent_spans: dict[int, str] = {}
        # agent object id → span_id of the handoff that created this agent
        self._active_handoffs: dict[int, str] = {}

    def _tool_key(self, agent: Any, tool: Any) -> str:
        """Build a unique key for a tool invocation."""
        agent_name = getattr(agent, "name", None) or str(id(agent))
        tool_name = getattr(tool, "name", None) or getattr(tool, "__name__", None) or str(tool)
        return f"{agent_name}:{tool_name}:{id(tool)}"

    def _tool_name(self, tool: Any) -> str:
        return getattr(tool, "name", None) or getattr(tool, "__name__", None) or str(tool)

    def _agent_label(self, agent: Any) -> str:
        return getattr(agent, "name", None) or self._agent_name or "unknown"

    # -- RunHooks protocol methods --

    async def on_agent_start(self, context: Any, agent: Any, **kwargs: Any) -> None:
        """Called when an agent begins a run. Tracks the agent's lifecycle span."""
        try:
            agent_name = self._agent_label(agent)
            # Determine parent: if this agent was handed-off to, link to handoff span
            parent_span_id = self._active_handoffs.get(id(agent))

            span = ToolCallSpan.agent_span(
                agent_name=agent_name,
                task="agent_run",
                started_at=datetime.now(UTC),
                trace_id=self._trace_id,
                session_id=self._session_id,
                parent_span_id=parent_span_id,
            )
            self._client.buffer_span(span)  # type: ignore[union-attr]  # type: ignore[union-attr]
            # Track so on_handoff can link to this span
            self._active_agent_spans[id(agent)] = span.span_id
        except Exception:  # noqa: BLE001
            pass  # fail-open

    async def on_agent_end(
        self, context: Any, agent: Any, output: Any = None, **kwargs: Any
    ) -> None:
        """Called when an agent completes a run."""
        try:
            self._active_agent_spans.pop(id(agent), None)
            self._active_handoffs.pop(id(agent), None)
        except Exception:  # noqa: BLE001
            pass

    async def on_tool_start(self, context: Any, agent: Any, tool: Any, **kwargs: Any) -> None:
        """Called when the agent begins executing a tool."""
        try:
            self._pending[self._tool_key(agent, tool)] = datetime.now(UTC)
        except Exception:  # noqa: BLE001
            pass  # fail-open

    async def on_tool_end(
        self, context: Any, agent: Any, tool: Any, result: Any = None, **kwargs: Any
    ) -> None:
        """Called when a tool execution completes successfully."""
        try:
            key = self._tool_key(agent, tool)
            started_at = self._pending.pop(key, datetime.now(UTC))
            # Use runtime agent name, not just constructor default
            agent_name = self._agent_label(agent)
            # Link to handoff span if this agent was delegated to
            parent_span_id = self._active_handoffs.get(id(agent))
            self._record(
                tool_name=self._tool_name(tool),
                started_at=started_at,
                status=ToolCallStatus.SUCCESS,
                trace_id=self._trace_id,
                agent_name=agent_name,
                parent_span_id=parent_span_id,
            )
        except Exception:  # noqa: BLE001
            logger.debug("openai_agents.on_tool_end_failed", tool=str(tool))

    async def on_tool_error(
        self, context: Any, agent: Any, tool: Any, error: Any = None, **kwargs: Any
    ) -> None:
        """Called when a tool execution raises an error."""
        try:
            key = self._tool_key(agent, tool)
            started_at = self._pending.pop(key, datetime.now(UTC))
            agent_name = self._agent_label(agent)
            parent_span_id = self._active_handoffs.get(id(agent))
            self._record(
                tool_name=self._tool_name(tool),
                started_at=started_at,
                status=ToolCallStatus.ERROR,
                error=str(error) if error else None,
                trace_id=self._trace_id,
                agent_name=agent_name,
                parent_span_id=parent_span_id,
            )
        except Exception:  # noqa: BLE001
            logger.debug("openai_agents.on_tool_error_failed", tool=str(tool))

    async def on_handoff(self, context: Any, from_agent: Any, to_agent: Any, **kwargs: Any) -> None:
        """Called when one agent hands off to another.

        Creates a handoff span linked to the source agent's active task span.
        Stores the handoff span_id so the child agent's tool calls
        (and agent span) link back to it via parent_span_id.
        """
        try:
            # Link handoff to parent agent's active task
            parent_span_id = self._active_agent_spans.get(id(from_agent))

            handoff = ToolCallSpan.handoff_span(
                from_agent=self._agent_label(from_agent),
                to_agent=self._agent_label(to_agent),
                started_at=datetime.now(UTC),
                trace_id=self._trace_id,
                session_id=self._session_id,
                parent_span_id=parent_span_id,
            )
            self._client.buffer_span(handoff)  # type: ignore[union-attr]

            # Store so child agent's on_agent_start + on_tool_* link to handoff
            self._active_handoffs[id(to_agent)] = handoff.span_id
        except Exception:  # noqa: BLE001
            logger.debug("openai_agents.on_handoff_failed")


def langsight_openai_tool(
    client: LangSightClient,
    server_name: str = "openai-agents",
    agent_name: str | None = None,
    session_id: str | None = None,
) -> Callable[[F], F]:
    """Decorator that traces an OpenAI Agents SDK tool function via LangSight.

    Usage::

        @langsight_openai_tool(client=client, server_name="my-tools")
        async def search(query: str) -> str:
            return await do_search(query)
    """

    def decorator(fn: F) -> F:
        tool_name = fn.__name__

        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            started_at = datetime.now(UTC)
            status = ToolCallStatus.SUCCESS
            error: str | None = None
            try:
                return await fn(*args, **kwargs)
            except TimeoutError as exc:
                status = ToolCallStatus.TIMEOUT
                error = str(exc)
                raise
            except Exception as exc:  # noqa: BLE001
                status = ToolCallStatus.ERROR
                error = str(exc)
                raise
            finally:
                try:
                    span = ToolCallSpan.record(
                        server_name=server_name,
                        tool_name=tool_name,
                        started_at=started_at,
                        status=status,
                        error=error,
                        agent_name=agent_name,
                        session_id=session_id,
                    )
                    client.buffer_span(span)
                except Exception:  # noqa: BLE001
                    pass  # fail-open: tracing must never break tool calls

        return wrapper  # type: ignore[return-value]

    return decorator
