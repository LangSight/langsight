"""
Shared span-recording logic for all framework integrations.

Each framework integration (CrewAI, Pydantic AI, OpenAI Agents SDK) calls
record_tool_call() before and after a tool execution. This module handles
building the span and sending it to LangSight — the frameworks don't need
to know about ToolCallSpan or the SDK client directly.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import structlog

from langsight.sdk.client import LangSightClient
from langsight.sdk.models import SpanType, ToolCallSpan, ToolCallStatus

logger = structlog.get_logger()


class BaseIntegration:
    """Base class for all framework integrations.

    Subclasses call _record() inside their framework-specific hooks.
    """

    def __init__(
        self,
        client: LangSightClient | None,
        server_name: str = "unknown",
        agent_name: str | None = None,
        session_id: str | None = None,
    ) -> None:
        self._client: LangSightClient | None = (
            client  # may be None if auto_patch() called before .env loaded
        )
        self._server_name = server_name
        self._agent_name = agent_name
        self._session_id = session_id
        self._redact = getattr(client, "_redact_payloads", False) if client else False

    @staticmethod
    def _parse_input(input_str: str) -> dict[str, Any] | None:
        """Try to parse a LangChain input string into a dict."""
        try:
            parsed = json.loads(input_str)
            if isinstance(parsed, dict):
                return parsed
            return {"input": parsed}
        except (json.JSONDecodeError, TypeError):
            return {"input": input_str} if input_str else None

    def _record(
        self,
        tool_name: str,
        started_at: datetime,
        status: ToolCallStatus,
        error: str | None = None,
        trace_id: str | None = None,
        input_str: str | None = None,
        output: Any | None = None,
        # v0.4 — optional overrides for auto-detect mode
        parent_span_id: str | None = None,
        span_type: SpanType = "tool_call",
        server_name: str | None = None,
        agent_name: str | None = None,
        span_id: str | None = None,
    ) -> None:
        """Build a ToolCallSpan and synchronously buffer it for delivery.

        This method is fully synchronous — no event loop required. Spans are
        buffered via ``client.buffer_span()`` and delivered by the async flush
        loop or the atexit handler.  This guarantees spans are never lost due
        to event-loop state transitions between sub-agent ``ainvoke()`` calls.
        """
        redact = self._redact
        effective_server = server_name or self._server_name
        effective_agent = agent_name or self._agent_name
        common = dict(
            server_name=effective_server,
            tool_name=tool_name,
            started_at=started_at,
            status=status,
            error=error,
            agent_name=effective_agent,
            session_id=self._session_id,
            trace_id=trace_id,
            project_id=getattr(self._client or {}, "_project_id", None) or "",
            input_args=None if redact else self._parse_input(input_str or ""),
            output_result=None if redact else (str(output) if output is not None else None),
            parent_span_id=parent_span_id,
            span_type=span_type,
        )
        if span_id is not None:
            from datetime import UTC
            from datetime import datetime as _dt

            ended_at = _dt.now(UTC)
            span = ToolCallSpan(
                span_id=span_id,
                ended_at=ended_at,
                **common,  # type: ignore[arg-type]
            )
        else:
            span = ToolCallSpan.record(**common)  # type: ignore[arg-type]
        # Lazy client resolution — handles case where auto_patch() was called
        # before .env was loaded and _client was None at construction time.
        client = self._client
        if client is None:
            try:
                from langsight.sdk.auto_patch import _resolve_client

                client = _resolve_client()
                if client is not None:
                    self._client = client  # cache for subsequent calls
            except ImportError:
                pass
        if client is None:
            return  # still no client — drop span silently
        client.buffer_span(span)
        logger.debug(
            "integration.span_recorded",
            tool=tool_name,
            status=status,
            latency_ms=span.latency_ms,
        )
