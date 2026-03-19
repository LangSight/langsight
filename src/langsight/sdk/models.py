from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class ToolCallStatus(StrEnum):
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"


# Span types for multi-agent tracing
SpanType = Literal["tool_call", "agent", "handoff"]


class ToolCallSpan(BaseModel):
    """A single span in an agent trace.

    Three span types:
    - tool_call: an MCP tool call, HTTP API call, or function call by an agent
    - agent:     an agent lifecycle span (agent started/finished a task)
    - handoff:   one agent delegating work to another agent

    Multi-agent tracing:
        parent_span_id links child spans to their parent, forming a tree.
        Agent A emits a handoff span when delegating to Agent B.
        Agent B's tool_call spans set parent_span_id to the handoff span's span_id.
        trace_id groups the entire task (all agents, all tools) under one root.

    Example tree:
        trace_id: "trace-123"
        ├── span: agent      / support-agent         / no parent
        │   ├── span: tool_call / jira-mcp/get_issue   / parent=above
        │   ├── span: handoff   / → billing-agent      / parent=above
        │   │   ├── span: tool_call / crm-mcp/update   / parent=handoff
        │   │   └── span: tool_call / slack-mcp/notify  / parent=handoff

    Payload fields (P5.1):
        input_args:    the arguments passed to the tool (None if redact_payloads=True)
        output_result: the tool's return value serialised to string (None if redacted or on error)
    """

    span_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    parent_span_id: str | None = None  # enables multi-agent tree reconstruction
    span_type: SpanType = "tool_call"  # tool_call | agent | handoff
    trace_id: str | None = None  # groups all spans in one task/conversation
    session_id: str | None = None  # application-level session identifier
    server_name: str  # tool server / agent name / "handoff"
    tool_name: str  # tool called / agent task / target agent name
    started_at: datetime
    ended_at: datetime
    latency_ms: float
    status: ToolCallStatus
    error: str | None = None
    agent_name: str | None = None  # which agent emitted this span
    input_args: dict[str, Any] | None = None   # tool call arguments (omitted when redacted)
    output_result: str | None = None            # tool return value as string (omitted when redacted)
    llm_input: str | None = None               # P5.3 — LLM prompt/messages (agent spans only)
    llm_output: str | None = None              # P5.3 — LLM completion text (agent spans only)
    replay_of: str | None = None               # P5.7 — original span_id this is a replay of

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
        parent_span_id: str | None = None,
        span_type: SpanType = "tool_call",
        input_args: dict[str, Any] | None = None,
        output_result: str | None = None,
        llm_input: str | None = None,
        llm_output: str | None = None,
        replay_of: str | None = None,
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
            parent_span_id=parent_span_id,
            span_type=span_type,
            input_args=input_args,
            output_result=output_result,
            llm_input=llm_input,
            llm_output=llm_output,
            replay_of=replay_of,
        )

    @classmethod
    def agent_span(
        cls,
        agent_name: str,
        task: str,
        started_at: datetime,
        status: ToolCallStatus = ToolCallStatus.SUCCESS,
        trace_id: str | None = None,
        session_id: str | None = None,
        parent_span_id: str | None = None,
        error: str | None = None,
    ) -> ToolCallSpan:
        """Create an agent lifecycle span (agent started/finished a task)."""
        return cls.record(
            server_name=agent_name,
            tool_name=task,
            started_at=started_at,
            status=status,
            error=error,
            trace_id=trace_id,
            agent_name=agent_name,
            session_id=session_id,
            parent_span_id=parent_span_id,
            span_type="agent",
        )

    @classmethod
    def handoff_span(
        cls,
        from_agent: str,
        to_agent: str,
        started_at: datetime,
        trace_id: str | None = None,
        session_id: str | None = None,
        parent_span_id: str | None = None,
    ) -> ToolCallSpan:
        """Create a handoff span when one agent delegates to another."""
        return cls.record(
            server_name=from_agent,
            tool_name=f"→ {to_agent}",
            started_at=started_at,
            status=ToolCallStatus.SUCCESS,
            trace_id=trace_id,
            agent_name=from_agent,
            session_id=session_id,
            parent_span_id=parent_span_id,
            span_type="handoff",
        )
