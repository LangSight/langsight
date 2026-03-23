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
from langsight.sdk.models import ToolCallSpan, ToolCallStatus

logger = structlog.get_logger()


class BaseIntegration:
    """Base class for all framework integrations.

    Subclasses call _record() inside their framework-specific hooks.
    """

    def __init__(
        self,
        client: LangSightClient,
        server_name: str = "unknown",
        agent_name: str | None = None,
        session_id: str | None = None,
    ) -> None:
        self._client = client
        self._server_name = server_name
        self._agent_name = agent_name
        self._session_id = session_id
        self._redact = getattr(client, "_redact_payloads", False)

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

    async def _record(
        self,
        tool_name: str,
        started_at: datetime,
        status: ToolCallStatus,
        error: str | None = None,
        trace_id: str | None = None,
        input_str: str | None = None,
        output: Any | None = None,
    ) -> None:
        """Build and fire-and-forget a ToolCallSpan."""
        redact = self._redact
        span = ToolCallSpan.record(
            server_name=self._server_name,
            tool_name=tool_name,
            started_at=started_at,
            status=status,
            error=error,
            agent_name=self._agent_name,
            session_id=self._session_id,
            trace_id=trace_id,
            project_id=getattr(self._client, "_project_id", None) or "",
            input_args=None if redact else self._parse_input(input_str or ""),
            output_result=None if redact else (str(output) if output is not None else None),
        )
        await self._client.send_span(span)
        logger.debug(
            "integration.span_recorded",
            tool=tool_name,
            status=status,
            latency_ms=span.latency_ms,
        )
