"""
Anthropic SDK integration — traces tool_use calls via LangSight.

The Anthropic SDK (``anthropic`` package) returns tool_use content blocks
in message responses. This integration provides two patterns:

1. **Decorator** — wrap individual tool handler functions::

       @langsight_anthropic_tool(client=client, server_name="my-tools")
       async def get_weather(location: str) -> str:
           ...

2. **Message processor** — extract and trace all tool_use blocks from a
   message response after the fact::

       processor = AnthropicToolTracer(client=client, agent_name="my-agent")
       response = await anthropic_client.messages.create(...)
       await processor.trace_response(response)

Both patterns are fire-and-forget and fail-open.

Claude Agent SDK (``claude_agent_sdk``) compatibility:
    The Claude Agent SDK builds on the Anthropic SDK and uses the same
    tool_use content blocks. The ``AnthropicToolTracer`` works with both.
    For Claude Agent SDK's higher-level agent loop, use the hooks pattern::

        tracer = LangSightClaudeAgentHooks(client=client)
        # Pass as lifecycle hooks to the agent runner
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


class AnthropicToolTracer(BaseIntegration):
    """Traces tool_use blocks from Anthropic SDK message responses.

    Call ``trace_response()`` after each ``messages.create()`` to record
    all tool calls the model requested. Pairs with your tool execution
    to capture timing.

    Usage::

        tracer = AnthropicToolTracer(client=ls_client, agent_name="assistant")
        response = await client.messages.create(model="claude-sonnet-4-6", ...)

        # Record the model's tool requests
        await tracer.trace_response(response)

        # Execute tools and record results
        for block in response.content:
            if block.type == "tool_use":
                result = await tracer.execute_and_trace(
                    block.name, block.input, my_tool_handler
                )
    """

    def __init__(
        self,
        client: LangSightClient,
        server_name: str = "anthropic-tools",
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

    async def trace_response(self, response: Any) -> None:
        """Extract tool_use blocks from a message response and record spans.

        This records the *model's decision* to use tools — call it right after
        ``messages.create()``. For execution tracing, use ``execute_and_trace()``.
        """
        try:
            content = getattr(response, "content", None) or []
            usage = getattr(response, "usage", None)
            model = getattr(response, "model", None)

            input_tokens = getattr(usage, "input_tokens", None) if usage else None
            output_tokens = getattr(usage, "output_tokens", None) if usage else None

            for block in content:
                if getattr(block, "type", None) != "tool_use":
                    continue
                tool_name = getattr(block, "name", "unknown")
                tool_input = getattr(block, "input", None)

                span = ToolCallSpan.record(
                    server_name=self._server_name,
                    tool_name=tool_name,
                    started_at=datetime.now(UTC),
                    status=ToolCallStatus.SUCCESS,
                    agent_name=self._agent_name,
                    session_id=self._session_id,
                    trace_id=self._trace_id,
                    input_args=tool_input if isinstance(tool_input, dict) else None,
                    model_id=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )
                await self._client.send_span(span)
                logger.debug("anthropic.tool_use_traced", tool=tool_name)
        except Exception:  # noqa: BLE001
            logger.debug("anthropic.trace_response_failed")

    async def execute_and_trace(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        handler: Callable[..., Coroutine[Any, Any, Any]],
    ) -> Any:
        """Execute a tool handler and record the execution span.

        Usage::

            for block in response.content:
                if block.type == "tool_use":
                    result = await tracer.execute_and_trace(
                        block.name, block.input, my_handlers[block.name]
                    )
        """
        started_at = datetime.now(UTC)
        status = ToolCallStatus.SUCCESS
        error: str | None = None
        output: str | None = None
        try:
            result = await handler(**tool_input)
            try:
                import json
                output = json.dumps(result, default=str)
            except Exception:  # noqa: BLE001
                output = str(result)
            return result
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
                    server_name=self._server_name,
                    tool_name=tool_name,
                    started_at=started_at,
                    status=status,
                    error=error,
                    agent_name=self._agent_name,
                    session_id=self._session_id,
                    trace_id=self._trace_id,
                    input_args=tool_input,
                    output_result=output,
                )
                await self._client.send_span(span)
            except Exception:  # noqa: BLE001
                pass  # fail-open: tracing must never break tool calls


class LangSightClaudeAgentHooks(BaseIntegration):
    """Claude Agent SDK lifecycle hooks that trace tool calls via LangSight.

    Implements the hooks protocol for the Claude Agent SDK's agent runner.
    Each tool execution is traced as a span with timing, status, and payloads.

    Usage::

        from langsight.integrations.anthropic_sdk import LangSightClaudeAgentHooks

        hooks = LangSightClaudeAgentHooks(client=ls_client, agent_name="my-agent")

        # Pass to the Claude Agent SDK runner
        result = await runner.run(agent, hooks=hooks)
    """

    def __init__(
        self,
        client: LangSightClient,
        server_name: str = "claude-agent",
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
        self._pending: dict[str, datetime] = {}

    async def on_tool_start(
        self, tool_name: str, tool_input: dict[str, Any] | None = None, **kwargs: Any
    ) -> None:
        """Called when the agent begins executing a tool."""
        try:
            self._pending[tool_name] = datetime.now(UTC)
        except Exception:  # noqa: BLE001
            pass

    async def on_tool_end(
        self, tool_name: str, tool_output: Any = None, **kwargs: Any
    ) -> None:
        """Called when a tool execution completes."""
        try:
            started_at = self._pending.pop(tool_name, datetime.now(UTC))
            await self._record(
                tool_name=tool_name,
                started_at=started_at,
                status=ToolCallStatus.SUCCESS,
                trace_id=self._trace_id,
            )
        except Exception:  # noqa: BLE001
            logger.debug("claude_agent.on_tool_end_failed", tool=tool_name)

    async def on_tool_error(
        self, tool_name: str, error: Any = None, **kwargs: Any
    ) -> None:
        """Called when a tool execution fails."""
        try:
            started_at = self._pending.pop(tool_name, datetime.now(UTC))
            await self._record(
                tool_name=tool_name,
                started_at=started_at,
                status=ToolCallStatus.ERROR,
                error=str(error) if error else None,
                trace_id=self._trace_id,
            )
        except Exception:  # noqa: BLE001
            logger.debug("claude_agent.on_tool_error_failed", tool=tool_name)

    async def on_handoff(
        self, from_agent: str, to_agent: str, **kwargs: Any
    ) -> None:
        """Called when one agent delegates to another."""
        try:
            handoff = ToolCallSpan.handoff_span(
                from_agent=from_agent,
                to_agent=to_agent,
                started_at=datetime.now(UTC),
                trace_id=self._trace_id,
                session_id=self._session_id,
            )
            await self._client.send_span(handoff)
        except Exception:  # noqa: BLE001
            logger.debug("claude_agent.on_handoff_failed")


def langsight_anthropic_tool(
    client: LangSightClient,
    server_name: str = "anthropic-tools",
    agent_name: str | None = None,
    session_id: str | None = None,
) -> Callable[[F], F]:
    """Decorator that traces an Anthropic SDK tool handler via LangSight.

    Usage::

        @langsight_anthropic_tool(client=client)
        async def get_weather(location: str) -> str:
            return f"72°F in {location}"

        # When Anthropic SDK calls this tool, the execution is traced
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
