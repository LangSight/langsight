"""
Agent sessions API — the primary observability surface for multi-agent workflows.

GET /api/agents/sessions              — list sessions with call counts and costs
GET /api/agents/sessions/{session_id} — full span tree for one session
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from pydantic import BaseModel

from langsight.api.dependencies import get_active_project_id, get_config, get_storage, require_admin
from langsight.config import LangSightConfig
from langsight.storage.base import StorageBackend

router = APIRouter(prefix="/agents", tags=["agents"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class AgentSession(BaseModel):
    """Summary of one agent session.

    Fields:
        session_id: Unique session identifier.
        agent_name: Name of the top-level agent that started the session.
        first_call_at: ISO 8601 timestamp of the first span in the session.
        last_call_at: ISO 8601 timestamp of the last span in the session.
        tool_calls: Total number of tool call spans (excludes agent lifecycle spans).
        failed_calls: Number of tool call spans whose status is not "success".
        duration_ms: Wall-clock duration from first_call_at to last_call_at.
        servers_used: Deduplicated list of MCP server names called in the session.
        health_tag: Auto-classified session outcome assigned by the v0.3 prevention
            layer when the session ends. Possible values:

            - ``success``               All tool calls completed without issue.
            - ``success_with_fallback`` Completed, but a circuit-breaker fallback was used.
            - ``loop_detected``         Session terminated due to a detected loop pattern.
            - ``budget_exceeded``       Stopped because a cost, step, or time limit was hit.
            - ``tool_failure``          One or more tool calls failed (no loop/budget event).
            - ``circuit_breaker_open``  A tool call was blocked by an open circuit breaker.
            - ``timeout``               Session exceeded the configured max_wall_time_s limit.
            - ``schema_drift``          A tool schema changed mid-session, triggering drift alert.

            ``None`` when the session was recorded before v0.3 or when the prevention
            layer is not enabled.
    """

    session_id: str
    agent_name: str | None
    first_call_at: str
    last_call_at: str
    tool_calls: int
    failed_calls: int
    duration_ms: float
    servers_used: list[str]
    health_tag: str | None = None  # v0.3 — auto-classified session health tag


class SpanNode(BaseModel):
    """A single span in a session trace (tool_call, agent, or handoff)."""

    span_id: str
    parent_span_id: str | None
    span_type: str
    server_name: str
    tool_name: str
    agent_name: str | None
    started_at: str
    ended_at: str
    latency_ms: float
    status: str
    error: str | None
    trace_id: str | None
    input_json: str | None = None  # P5.1 payload — None when redacted or not captured
    output_json: str | None = None  # P5.1 payload — None when redacted or on error
    llm_input: str | None = None  # P5.3 — LLM prompt (agent spans only)
    llm_output: str | None = None  # P5.3 — LLM completion (agent spans only)
    children: list[SpanNode] = []


class SessionTrace(BaseModel):
    """Full trace for one agent session — spans as a tree."""

    session_id: str
    spans_flat: list[dict[str, Any]]
    root_spans: list[dict[str, Any]]  # top-level spans (no parent)
    total_spans: int
    tool_calls: int
    failed_calls: int
    duration_ms: float | None


class SessionComparison(BaseModel):
    """Side-by-side comparison of two session traces."""

    session_a: str
    session_b: str
    spans_a: list[dict[str, Any]]
    spans_b: list[dict[str, Any]]
    diff: list[dict[str, Any]]  # per-tool diff entries
    summary: dict[str, int]  # matched / diverged / only_a / only_b


class ReplayResponse(BaseModel):
    """Result of a session replay execution."""

    original_session_id: str
    replay_session_id: str
    total_spans: int
    replayed: int
    skipped: int
    failed: int
    duration_ms: float


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get(
    "/sessions",
    response_model=list[AgentSession],
    summary="List recent agent sessions",
)
async def list_sessions(
    hours: int = Query(default=24, ge=1, le=720, description="Look-back window in hours"),
    agent_name: str | None = Query(default=None, description="Filter by agent name"),
    health_tag: str | None = Query(default=None, description="Filter by health tag (v0.3)"),
    limit: int = Query(default=50, ge=1, le=1000),
    project_id: str | None = Depends(get_active_project_id),
    storage: StorageBackend = Depends(get_storage),
) -> list[AgentSession]:
    """Return recent agent sessions with call counts, failure rates, and duration.

    Query parameters:
        hours: Look-back window in hours (1–720, default 24).
        agent_name: Optional filter — return only sessions for this agent.
        health_tag: Optional filter — return only sessions with this health tag (v0.3).
            Accepted values: ``success``, ``success_with_fallback``, ``loop_detected``,
            ``budget_exceeded``, ``tool_failure``, ``circuit_breaker_open``,
            ``timeout``, ``schema_drift``.
        limit: Maximum sessions to return (1–1000, default 50).

    Requires ClickHouse backend. Returns empty list on PostgreSQL-only deployments.
    """
    if not hasattr(storage, "get_agent_sessions"):
        return []

    rows = await storage.get_agent_sessions(
        hours=hours,
        agent_name=agent_name,
        limit=limit,
        project_id=project_id,
        health_tag=health_tag,
    )
    return [
        AgentSession(
            session_id=r["session_id"] or "unknown",
            agent_name=r["agent_name"],
            first_call_at=str(r["first_call_at"]),
            last_call_at=str(r["last_call_at"]),
            tool_calls=int(r.get("tool_calls") or 0),
            failed_calls=int(r.get("failed_calls") or 0),
            duration_ms=float(r.get("duration_ms") or 0),
            servers_used=list(r.get("servers_used") or []),
            health_tag=r.get("health_tag") or None,
        )
        for r in rows
    ]


# NOTE: /sessions/compare MUST be registered before /sessions/{session_id}
# or FastAPI will match "compare" as a session_id value.
@router.get(
    "/sessions/compare",
    response_model=SessionComparison,
    summary="Compare two session traces side-by-side",
    responses={
        404: {"description": "One or both sessions not found"},
        503: {"description": "Requires ClickHouse backend"},
    },
)
async def compare_sessions(
    a: str = Query(..., description="First session ID"),
    b: str = Query(..., description="Second session ID"),
    project_id: str | None = Depends(get_active_project_id),
    storage: StorageBackend = Depends(get_storage),
) -> SessionComparison:
    """Return a side-by-side diff of two sessions.

    Aligns spans by (server_name, tool_name) call order. Each diff entry
    has status: 'matched' | 'diverged' | 'only_a' | 'only_b'.

    Diverged = status changed OR latency difference >= 20%.
    """
    if not hasattr(storage, "compare_sessions"):
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Session comparison requires ClickHouse backend.",
        )
    if a == b:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Session IDs must be different.",
        )

    result = await storage.compare_sessions(a, b, project_id=project_id)

    # Project isolation: if a project filter is active, both sessions must belong to it.
    # Spans with no project_id (ingested before project tagging was introduced) are
    # treated as belonging to any project — they are not rejected.
    if project_id:
        spans_a_in_project = [
            s
            for s in result["spans_a"]
            if s.get("project_id") is None or s.get("project_id") == project_id
        ]
        spans_b_in_project = [
            s
            for s in result["spans_b"]
            if s.get("project_id") is None or s.get("project_id") == project_id
        ]
        if result["spans_a"] and not spans_a_in_project:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND, detail="Session not found."
            )
        if result["spans_b"] and not spans_b_in_project:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND, detail="Session not found."
            )
        # Replace with filtered spans — prevents returning foreign-project span data
        # even when the session IDs matched (ownership check passed above).
        result = {**result, "spans_a": spans_a_in_project, "spans_b": spans_b_in_project}

    if not result["spans_a"] and not result["spans_b"]:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Neither session was found.",
        )

    return SessionComparison(**result)


@router.get(
    "/sessions/{session_id}",
    response_model=SessionTrace,
    summary="Get full span tree for one agent session",
    responses={404: {"description": "Session not found"}},
)
async def get_session(
    session_id: str,
    project_id: str | None = Depends(get_active_project_id),
    storage: StorageBackend = Depends(get_storage),
) -> SessionTrace:
    """Return all spans for a session as a flat list and reconstructed tree.

    The `root_spans` field contains top-level spans with nested `children`.
    Use this to render a multi-agent call tree in a UI.
    """
    if not hasattr(storage, "get_session_trace"):
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Session traces require ClickHouse backend (storage.mode: clickhouse).",
        )

    spans = await storage.get_session_trace(session_id, project_id=project_id)
    if not spans:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found.",
        )

    tree = _build_tree(spans)
    tool_spans = [s for s in spans if s.get("span_type") == "tool_call"]
    failed = [s for s in tool_spans if s.get("status") != "success"]

    # Duration = max(ended_at) - min(started_at)
    started = [s["started_at"] for s in spans if s.get("started_at")]
    ended = [s["ended_at"] for s in spans if s.get("ended_at")]
    duration_ms: float | None = None
    if started and ended:
        from datetime import UTC, datetime

        def _to_dt(v: object) -> datetime:
            if isinstance(v, datetime):
                return v if v.tzinfo else v.replace(tzinfo=UTC)
            return datetime.fromisoformat(str(v))

        duration_ms = (_to_dt(max(ended)) - _to_dt(min(started))).total_seconds() * 1000

    return SessionTrace(
        session_id=session_id,
        spans_flat=spans,
        root_spans=tree,
        total_spans=len(spans),
        tool_calls=len(tool_spans),
        failed_calls=len(failed),
        duration_ms=duration_ms,
    )


@router.post(
    "/sessions/{session_id}/replay",
    response_model=ReplayResponse,
    status_code=202,
    summary="Replay a session's tool calls against live MCP servers",
    responses={
        404: {"description": "Session not found"},
        503: {"description": "Requires ClickHouse backend"},
    },
)
async def replay_session(
    session_id: str,
    timeout_per_call: float = Query(default=10.0, ge=1.0, le=60.0),
    total_timeout: float = Query(default=60.0, ge=5.0, le=300.0),
    project_id: str | None = Depends(get_active_project_id),
    storage: StorageBackend = Depends(get_storage),
    config: LangSightConfig = Depends(get_config),
) -> ReplayResponse:
    """Re-execute all tool calls from a session against live MCP servers.

    Callers must be a member of the project that owns the session (or a global
    admin). Non-admin authenticated users must supply ?project_id= — the same
    project scoping enforced on all other analytics endpoints.

    Each tool call is replayed with the exact input_args stored from the original
    run (requires P5.1 payload capture to be enabled — redact_payloads must be false).

    The replay is stored as a new session. Use the returned replay_session_id
    with GET /api/agents/sessions/compare to diff original vs replay.

    Requires ClickHouse backend and reachable MCP servers.
    """
    from langsight.replay.engine import ReplayEngine

    if not hasattr(storage, "get_session_trace"):
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Session replay requires ClickHouse backend.",
        )

    engine = ReplayEngine(
        storage=storage,
        config=config,
        timeout_per_call=timeout_per_call,
        total_timeout=total_timeout,
    )

    try:
        result = await engine.replay(session_id, project_id=project_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    return ReplayResponse(**result.to_dict())


# ---------------------------------------------------------------------------
# Tree reconstruction
# ---------------------------------------------------------------------------


def _build_tree(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reconstruct a parent-child tree from a flat list of spans.

    Returns the root spans (those with no parent_span_id) with
    their children nested recursively.
    """
    by_id: dict[str, dict[str, Any]] = {s["span_id"]: dict(s, children=[]) for s in spans}

    roots: list[dict[str, Any]] = []
    for span in by_id.values():
        parent_id = span.get("parent_span_id")
        if parent_id and parent_id in by_id:
            by_id[parent_id]["children"].append(span)
        else:
            roots.append(span)

    return roots


# ---------------------------------------------------------------------------
# Agent metadata (catalog)
# ---------------------------------------------------------------------------


class AgentMetadataUpdate(BaseModel):
    description: str = ""
    owner: str = ""
    tags: list[str] = []
    status: Literal["active", "deprecated", "experimental"] = "active"
    runbook_url: str = ""


class AgentMetadataResponse(BaseModel):
    id: str
    agent_name: str
    description: str
    owner: str
    tags: list[str]
    status: str
    runbook_url: str
    project_id: str | None
    created_at: str
    updated_at: str


@router.get("/metadata", response_model=list[AgentMetadataResponse])
async def list_agent_metadata(
    storage: StorageBackend = Depends(get_storage),
    project_id: str | None = Depends(get_active_project_id),
) -> list[dict[str, Any]]:
    """List all agent metadata for the project."""
    rows = await storage.get_all_agent_metadata(project_id=project_id)
    for r in rows:
        r["created_at"] = str(r["created_at"])
        r["updated_at"] = str(r["updated_at"])
        if isinstance(r.get("tags"), str):
            import json

            r["tags"] = json.loads(r["tags"])
    return rows


@router.get("/metadata/{agent_name}", response_model=AgentMetadataResponse)
async def get_agent_metadata(
    agent_name: str,
    storage: StorageBackend = Depends(get_storage),
    project_id: str | None = Depends(get_active_project_id),
) -> dict[str, Any]:
    """Get metadata for one agent."""
    row = await storage.get_agent_metadata(agent_name, project_id=project_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"No metadata for agent '{agent_name}'")
    row["created_at"] = str(row["created_at"])
    row["updated_at"] = str(row["updated_at"])
    if isinstance(row.get("tags"), str):
        import json

        row["tags"] = json.loads(row["tags"])
    return row


@router.put(
    "/metadata/{agent_name}",
    response_model=AgentMetadataResponse,
    status_code=http_status.HTTP_200_OK,
)
async def upsert_agent_metadata(
    agent_name: str,
    body: AgentMetadataUpdate,
    storage: StorageBackend = Depends(get_storage),
    project_id: str | None = Depends(get_active_project_id),
    _admin: None = Depends(require_admin),
) -> dict[str, Any]:
    """Create or update agent metadata."""
    row = await storage.upsert_agent_metadata(
        agent_name=agent_name,
        description=body.description,
        owner=body.owner,
        tags=body.tags,
        status=body.status,
        runbook_url=body.runbook_url,
        project_id=project_id,
    )
    row["created_at"] = str(row["created_at"])
    row["updated_at"] = str(row["updated_at"])
    if isinstance(row.get("tags"), str):
        import json

        row["tags"] = json.loads(row["tags"])
    return row


@router.delete("/metadata/{agent_name}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_agent_metadata(
    agent_name: str,
    storage: StorageBackend = Depends(get_storage),
    project_id: str | None = Depends(get_active_project_id),
    _admin: None = Depends(require_admin),
) -> None:
    """Delete agent metadata scoped to the active project."""
    deleted = await storage.delete_agent_metadata(agent_name, project_id=project_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"No metadata for agent '{agent_name}'")
