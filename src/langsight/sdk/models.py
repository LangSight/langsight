from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

# UUID4 patterns: used by the API ingest endpoint (traces.py) to validate
# client-supplied session_id values.  The model itself is permissive so
# unit tests can use short IDs without boilerplate.
#   hex-only (uuid4().hex): 32 lowercase hex chars, no dashes
#   standard form:          8-4-4-4-12 hex with dashes
SESSION_ID_RE = re.compile(
    r"^[0-9a-f]{32}$"
    r"|^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


class ToolCallStatus(StrEnum):
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    PREVENTED = "prevented"  # v0.3 — call blocked by loop/budget/circuit breaker


# Span types for multi-agent tracing
#   tool_call:  actual MCP tool execution, HTTP API call, or function call
#   agent:      agent lifecycle span (LLM generation, task started/finished)
#   handoff:    explicit delegation from one agent to another
#   llm_intent: LLM decided to call a tool — NOT actual execution.
#               Never counted in agent→server metrics.  Still registered in
#               the pending-tool queue so the real tool_call can claim it.
SpanType = Literal[
    "tool_call",      # MCP/tool execution
    "agent",          # LLM generation or agent lifecycle
    "handoff",        # agent-to-agent delegation
    "llm_intent",     # LLM decided to call a tool (not actual execution)
    "user_message",   # human input mid-session (HITL, clarification, approval)
]

# Lineage provenance — how parent/child was determined
LineageProvenance = Literal[
    "explicit",  # from explicit handoff_span() or manual parent_span_id
    "derived_parent",  # inferred from parent_span_id where agent_name differs
    "derived_timing",  # inferred from timestamp proximity (weakest fallback)
    "derived_legacy",  # pre-protocol historical data
    "inferred_otel",  # auto-instrumented via OpenTelemetry
]

# Lineage quality status
LineageStatus = Literal[
    "complete",  # all parent/child links valid
    "incomplete",  # some links missing but recoverable
    "orphaned",  # parent span not found in session
    "invalid_parent",  # parent exists but violates invariants
    "session_mismatch",  # parent in different session_id
    "trace_mismatch",  # parent in different trace_id
]


class ToolCallSpan(BaseModel):
    """A single span in an agent trace.

    Four span types:
    - tool_call:  an MCP tool call, HTTP API call, or function call by an agent
    - agent:      an agent lifecycle span (agent started/finished a task)
    - handoff:    one agent delegating work to another agent
    - llm_intent: LLM decided to call a tool (not actual execution)

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
    latency_ms: float | None = None  # auto-computed from started_at/ended_at if omitted
    status: ToolCallStatus
    error: str | None = None
    agent_name: str | None = None  # which agent emitted this span
    input_args: dict[str, Any] | None = None  # tool call arguments (omitted when redacted)
    output_result: str | None = None  # tool return value as string (omitted when redacted)
    llm_input: str | None = None  # P5.3 — LLM prompt/messages (agent spans only)
    llm_output: str | None = None  # P5.3 — LLM completion text (agent spans only)
    replay_of: str | None = None  # P5.7 — original span_id this is a replay of
    project_id: str | None = None  # P6 — project this span belongs to
    input_tokens: int | None = None  # P7 — LLM input token count
    output_tokens: int | None = None  # P7 — LLM output token count
    model_id: str | None = None  # P7 — model used (gen_ai.request.model)

    # --- Lineage protocol v1.0 fields ---
    target_agent_name: str | None = None  # explicit handoff destination (handoff spans only)
    lineage_provenance: LineageProvenance = "explicit"  # how parent/child was determined
    lineage_status: LineageStatus = "complete"  # quality flag for this span's lineage
    schema_version: str = "1.0"  # protocol version for backward/forward compat

    @model_validator(mode="after")
    def _compute_latency(self) -> ToolCallSpan:
        """Auto-compute latency_ms from started_at/ended_at if not provided."""
        if self.latency_ms is None:
            self.latency_ms = round((self.ended_at - self.started_at).total_seconds() * 1000, 2)
        return self

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
        project_id: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        model_id: str | None = None,
        target_agent_name: str | None = None,
        lineage_provenance: LineageProvenance = "explicit",
        lineage_status: LineageStatus = "complete",
        schema_version: str = "1.0",
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
            project_id=project_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model_id=model_id,
            target_agent_name=target_agent_name,
            lineage_provenance=lineage_provenance,
            lineage_status=lineage_status,
            schema_version=schema_version,
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
        """Create a handoff span when one agent delegates to another.

        Sets target_agent_name explicitly (not embedded in tool_name).
        tool_name still contains "→ {to_agent}" for backward compat display.
        """
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
            target_agent_name=to_agent,
            lineage_provenance="explicit",
            schema_version="1.0",
        )


# ---------------------------------------------------------------------------
# v0.3 Prevention events
# ---------------------------------------------------------------------------


class PreventionEvent(BaseModel):
    """SDK-originated prevention event sent to the API for alerting.

    Emitted when the SDK blocks a tool call (loop, budget, circuit breaker)
    or when a soft budget threshold is crossed.
    """

    event_type: Literal[
        "loop_detected",
        "budget_warning",
        "budget_exceeded",
        "circuit_breaker_open",
        "circuit_breaker_recovered",
    ]
    session_id: str | None = None
    server_name: str | None = None
    tool_name: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
