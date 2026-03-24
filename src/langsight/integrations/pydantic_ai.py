"""
Pydantic AI integration for LangSight.

Wraps a Pydantic AI tool function to automatically record ToolCallSpans.

Usage:
    from langsight.sdk import LangSightClient
    from langsight.integrations.pydantic_ai import langsight_tool

    client = LangSightClient(url="http://localhost:8000")

    @langsight_tool(client=client, server_name="postgres-mcp")
    async def query_database(sql: str) -> list[dict]:
        return await mcp_session.call_tool("query", {"sql": sql})

    # Use query_database as a Pydantic AI tool — all calls traced
"""

from __future__ import annotations

import functools
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import Any, TypeVar

from langsight.sdk.client import LangSightClient
from langsight.sdk.models import ToolCallSpan, ToolCallStatus

F = TypeVar("F", bound=Callable[..., Coroutine[Any, Any, Any]])


def langsight_tool(
    client: LangSightClient,
    server_name: str = "pydantic-ai-mcp",
    agent_name: str | None = None,
    session_id: str | None = None,
) -> Callable[[F], F]:
    """Decorator that traces a Pydantic AI tool function via LangSight.

    Wrap any async function that calls an MCP tool. The decorator records
    a ToolCallSpan for every invocation, success or failure.

    Args:
        client: LangSightClient instance.
        server_name: MCP server name to attach to spans.
        agent_name: Optional agent identifier for spans.
        session_id: Optional session identifier for spans.
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
