"""
Agent action lineage API — DAG of agents, MCP servers, and their relationships.

GET /api/agents/lineage — returns the full lineage graph for a time window
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from langsight.api.dependencies import get_active_project_id, get_storage
from langsight.storage.base import StorageBackend

router = APIRouter(prefix="/agents", tags=["agents"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class LineageNodeMetrics(BaseModel):
    """Flexible metrics dict — contents vary by node type."""

    model_config = {"extra": "allow"}


class LineageNode(BaseModel):
    """A node in the lineage DAG (agent or server)."""

    id: str
    type: str  # "agent" | "server"
    label: str
    metrics: dict[str, Any]


class LineageEdge(BaseModel):
    """An edge in the lineage DAG (calls or handoff)."""

    source: str
    target: str
    type: str  # "calls" | "handoff"
    metrics: dict[str, Any]


class LineageGraph(BaseModel):
    """Full lineage graph response."""

    window_hours: int
    nodes: list[LineageNode]
    edges: list[LineageEdge]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get(
    "/lineage",
    response_model=LineageGraph,
    summary="Get agent action lineage graph",
)
async def get_lineage(
    hours: int = Query(default=168, ge=1, le=720, description="Look-back window in hours"),
    project_id: str | None = Depends(get_active_project_id),
    storage: StorageBackend = Depends(get_storage),
) -> LineageGraph:
    """Return the agent action lineage DAG for the requested time window.

    Nodes represent agents and MCP servers. Edges represent observed
    tool calls (agent -> server) and handoffs (agent -> agent).

    The graph is built from actual span data — edges are observed, not
    configured. New tools and agents appear automatically. Dead edges
    age out via the time window.

    Requires ClickHouse backend. Returns empty graph on SQLite.
    """
    if not hasattr(storage, "get_lineage_graph"):
        return LineageGraph(window_hours=hours, nodes=[], edges=[])

    result = await storage.get_lineage_graph(hours=hours, project_id=project_id)

    return LineageGraph(
        window_hours=result["window_hours"],
        nodes=[LineageNode(**n) for n in result["nodes"]],
        edges=[LineageEdge(**e) for e in result["edges"]],
    )
