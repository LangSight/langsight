"""
Agent sessions API — the primary observability surface for multi-agent workflows.

GET /api/agents/sessions              — list sessions with call counts and costs
GET /api/agents/sessions/{session_id} — full span tree for one session
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from pydantic import BaseModel

from langsight.api.dependencies import get_storage
from langsight.storage.base import StorageBackend

router = APIRouter(prefix="/agents", tags=["agents"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class AgentSession(BaseModel):
    """Summary of one agent session."""

    session_id: str
    agent_name: str | None
    first_call_at: str
    last_call_at: str
    tool_calls: int
    failed_calls: int
    duration_ms: float
    servers_used: list[str]


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
    children: list[SpanNode] = []


class SessionTrace(BaseModel):
    """Full trace for one agent session — spans as a tree."""

    session_id: str
    spans_flat: list[dict]
    root_spans: list[dict]  # top-level spans (no parent)
    total_spans: int
    tool_calls: int
    failed_calls: int
    duration_ms: float | None


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
    limit: int = Query(default=50, ge=1, le=200),
    storage: StorageBackend = Depends(get_storage),
) -> list[AgentSession]:
    """Return recent agent sessions with call counts, failure rates, and duration.

    Requires ClickHouse backend. Returns empty list on SQLite.
    """
    if not hasattr(storage, "get_agent_sessions"):
        return []

    rows = await storage.get_agent_sessions(hours=hours, agent_name=agent_name, limit=limit)
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
        )
        for r in rows
    ]


@router.get(
    "/sessions/{session_id}",
    response_model=SessionTrace,
    summary="Get full span tree for one agent session",
    responses={404: {"description": "Session not found"}},
)
async def get_session(
    session_id: str,
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

    spans = await storage.get_session_trace(session_id)
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


# ---------------------------------------------------------------------------
# Tree reconstruction
# ---------------------------------------------------------------------------


def _build_tree(spans: list[dict]) -> list[dict]:
    """Reconstruct a parent-child tree from a flat list of spans.

    Returns the root spans (those with no parent_span_id) with
    their children nested recursively.
    """
    by_id = {s["span_id"]: dict(s, children=[]) for s in spans}

    roots: list[dict] = []
    for span in by_id.values():
        parent_id = span.get("parent_span_id")
        if parent_id and parent_id in by_id:
            by_id[parent_id]["children"].append(span)
        else:
            roots.append(span)

    return roots
