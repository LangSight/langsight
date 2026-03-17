from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ToolCallStatus(StrEnum):
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"


class ToolCallSpan(BaseModel):
    """A single recorded MCP tool call — the unit of observability in the SDK.

    Sent to POST /api/traces/spans and stored for reliability analysis.
    """

    span_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    trace_id: str | None = None  # session / conversation ID — groups spans into a trace
    server_name: str  # MCP server name (matches MCPServer.name)
    tool_name: str  # Tool that was called
    started_at: datetime  # When the call was initiated
    ended_at: datetime  # When the call completed (or failed)
    latency_ms: float  # ended_at - started_at in milliseconds
    status: ToolCallStatus  # success / error / timeout
    error: str | None = None  # Error message if status != success
    agent_name: str | None = None  # Name of the agent that made the call
    session_id: str | None = None  # Application-level session identifier

    @classmethod
    def record(
        cls,
        server_name: str,
        tool_name: str,
        started_at: datetime,
        status: ToolCallStatus,
        error: str | None = None,
        trace_id: str | None = None,
        agent_name: str | None = None,
        session_id: str | None = None,
    ) -> ToolCallSpan:
        """Convenience constructor — computes ended_at and latency_ms automatically."""
        ended_at = datetime.now(UTC)
        latency_ms = (ended_at - started_at).total_seconds() * 1000
        return cls(
            server_name=server_name,
            tool_name=tool_name,
            started_at=started_at,
            ended_at=ended_at,
            latency_ms=round(latency_ms, 2),
            status=status,
            error=error,
            trace_id=trace_id,
            agent_name=agent_name,
            session_id=session_id,
        )
