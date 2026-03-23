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
    - ``on_tool_start(context, agent, tool)`` — records start time
    - ``on_tool_end(context, agent, tool, result)`` — emits success span
    - ``on_tool_error(context, agent, tool, error)`` — emits error span
    - ``on_handoff(context, from_agent, to_agent)`` — emits handoff span

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
            await self._record(
                tool_name=self._tool_name(tool),
                started_at=started_at,
                status=ToolCallStatus.SUCCESS,
                trace_id=self._trace_id,
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
            await self._record(
                tool_name=self._tool_name(tool),
                started_at=started_at,
                status=ToolCallStatus.ERROR,
                error=str(error) if error else None,
                trace_id=self._trace_id,
            )
        except Exception:  # noqa: BLE001
            logger.debug("openai_agents.on_tool_error_failed", tool=str(tool))

    async def on_handoff(self, context: Any, from_agent: Any, to_agent: Any, **kwargs: Any) -> None:
        """Called when one agent hands off to another."""
        try:
            handoff = ToolCallSpan.handoff_span(
                from_agent=self._agent_label(from_agent),
                to_agent=self._agent_label(to_agent),
                started_at=datetime.now(UTC),
                trace_id=self._trace_id,
                session_id=self._session_id,
            )
            await self._client.send_span(handoff)
        except Exception:  # noqa: BLE001
            logger.debug("openai_agents.on_handoff_failed")

    # -- Optional lifecycle hooks (no-ops unless needed) --

    async def on_agent_start(self, context: Any, agent: Any, **kwargs: Any) -> None:
        """Called when an agent begins a run."""

    async def on_agent_end(
        self, context: Any, agent: Any, output: Any = None, **kwargs: Any
    ) -> None:
        """Called when an agent completes a run."""


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
                    await client.send_span(span)
                except Exception:  # noqa: BLE001
                    pass  # fail-open: tracing must never break tool calls

        return wrapper  # type: ignore[return-value]

    return decorator
