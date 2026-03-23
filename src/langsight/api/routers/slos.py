"""
Agent SLO management and evaluation endpoints (P5.5).

GET    /api/slos           — list all SLO definitions
POST   /api/slos           — create a new SLO
DELETE /api/slos/{slo_id}  — delete an SLO
GET    /api/slos/status    — evaluate all SLOs against current data
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from pydantic import BaseModel, Field

from langsight.api.dependencies import get_active_project_id, get_storage, require_admin
from langsight.models import AgentSLO, SLOMetric
from langsight.reliability.engine import SLOEvaluator
from langsight.storage.base import StorageBackend

router = APIRouter(prefix="/slos", tags=["slos"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class CreateSLORequest(BaseModel):
    agent_name: str = Field(..., description="Agent name to track")
    metric: SLOMetric = Field(..., description="'success_rate' or 'latency_p99'")
    target: float = Field(
        ...,
        description="Target value: success_rate = % (0-100), latency_p99 = ms",
        gt=0,
    )
    window_hours: int = Field(default=24, ge=1, le=720, description="Evaluation window in hours")


class SLOResponse(BaseModel):
    id: str
    agent_name: str
    metric: str
    target: float
    window_hours: int
    created_at: str


class SLOStatusResponse(BaseModel):
    slo_id: str
    agent_name: str
    metric: str
    target: float
    current_value: float | None
    window_hours: int
    status: str  # "ok" | "breached" | "no_data"
    evaluated_at: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/status", response_model=list[SLOStatusResponse], summary="Evaluate all SLOs")
async def get_slo_status(
    project_id: str | None = Depends(get_active_project_id),
    storage: StorageBackend = Depends(get_storage),
) -> list[SLOStatusResponse]:
    """Evaluate every defined SLO against current session data.

    Returns status "ok", "breached", or "no_data" for each SLO.
    Requires ClickHouse for latency_p99 and success_rate metrics.
    """
    if not hasattr(storage, "list_slos"):
        return []

    slos = await storage.list_slos(project_id=project_id)
    evaluator = SLOEvaluator(storage)
    evaluations = await evaluator.evaluate_all(slos, project_id=project_id)

    return [
        SLOStatusResponse(
            slo_id=e.slo_id,
            agent_name=e.agent_name,
            metric=e.metric.value,
            target=e.target,
            current_value=e.current_value,
            window_hours=e.window_hours,
            status=e.status,
            evaluated_at=e.evaluated_at.isoformat(),
        )
        for e in evaluations
    ]


@router.get("", response_model=list[SLOResponse], summary="List all SLO definitions")
async def list_slos(
    project_id: str | None = Depends(get_active_project_id),
    storage: StorageBackend = Depends(get_storage),
) -> list[SLOResponse]:
    """Return SLO definitions scoped to the active project."""
    if not hasattr(storage, "list_slos"):
        return []
    slos = await storage.list_slos(project_id=project_id)
    return [_slo_to_response(s) for s in slos]


@router.post(
    "",
    response_model=SLOResponse,
    status_code=http_status.HTTP_201_CREATED,
    summary="Create a new SLO",
)
async def create_slo(
    body: CreateSLORequest,
    project_id: str | None = Depends(get_active_project_id),
    storage: StorageBackend = Depends(get_storage),
    _: None = Depends(require_admin),
) -> SLOResponse:
    """Define a new Agent SLO scoped to the active project.

    Example — 95% success rate for customer-support-bot over 24h:
        { "agent_name": "customer-support-bot", "metric": "success_rate",
          "target": 95.0, "window_hours": 24 }
    """
    if not hasattr(storage, "create_slo"):
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SLO management requires PostgreSQL backend.",
        )
    slo = AgentSLO(
        id=uuid.uuid4().hex,
        project_id=project_id or "",
        agent_name=body.agent_name,
        metric=body.metric,
        target=body.target,
        window_hours=body.window_hours,
        created_at=datetime.now(UTC),
    )
    await storage.create_slo(slo)
    return _slo_to_response(slo)


@router.delete(
    "/{slo_id}",
    status_code=http_status.HTTP_204_NO_CONTENT,
    summary="Delete an SLO",
)
async def delete_slo(
    slo_id: str,
    project_id: str | None = Depends(get_active_project_id),
    storage: StorageBackend = Depends(get_storage),
    _: None = Depends(require_admin),
) -> None:
    """Delete an SLO definition. Only deletes within the active project."""
    if not hasattr(storage, "delete_slo"):
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SLO management requires PostgreSQL backend.",
        )
    found = await storage.delete_slo(slo_id, project_id=project_id)
    if not found:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"SLO '{slo_id}' not found.",
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _slo_to_response(slo: AgentSLO) -> SLOResponse:
    return SLOResponse(
        id=slo.id,
        agent_name=slo.agent_name,
        metric=slo.metric.value,
        target=slo.target,
        window_hours=slo.window_hours,
        created_at=slo.created_at.isoformat(),
    )
