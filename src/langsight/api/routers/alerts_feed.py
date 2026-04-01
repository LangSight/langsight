"""
Alerts feed API — fired alert history with ack/resolve/snooze lifecycle.

GET  /api/alerts/feed           — list fired alerts (filterable by status)
GET  /api/alerts/counts         — active alert counts per severity
POST /api/alerts/{id}/ack       — acknowledge an alert
POST /api/alerts/{id}/resolve   — resolve an alert
POST /api/alerts/{id}/snooze    — snooze an alert for N minutes
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi import status as http_status
from pydantic import BaseModel

from langsight.api.dependencies import get_active_project_id
from langsight.storage.base import StorageBackend

logger = structlog.get_logger()
router = APIRouter(tags=["alerts"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class FiredAlertResponse(BaseModel):
    id: str
    alert_type: str
    severity: str
    server_name: str
    session_id: str | None
    title: str
    message: str
    fired_at: str
    status: str
    acked_at: str | None
    acked_by: str | None
    snoozed_until: str | None
    resolved_at: str | None
    project_id: str


class AlertFeedResponse(BaseModel):
    total: int
    limit: int
    offset: int
    alerts: list[FiredAlertResponse]


class AlertCountsResponse(BaseModel):
    critical: int
    warning: int
    info: int
    total: int


class SnoozeRequest(BaseModel):
    minutes: int = 60


class AckRequest(BaseModel):
    acked_by: str = "user"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row_to_response(row: dict[str, Any]) -> FiredAlertResponse:
    def _iso(v: Any) -> str | None:
        if v is None:
            return None
        return v.isoformat() if hasattr(v, "isoformat") else str(v)

    return FiredAlertResponse(
        id=row["id"],
        alert_type=row["alert_type"],
        severity=row["severity"],
        server_name=row["server_name"] or "",
        session_id=row.get("session_id"),
        title=row["title"],
        message=row["message"],
        fired_at=_iso(row["fired_at"]) or "",
        status=row["status"],
        acked_at=_iso(row.get("acked_at")),
        acked_by=row.get("acked_by"),
        snoozed_until=_iso(row.get("snoozed_until")),
        resolved_at=_iso(row.get("resolved_at")),
        project_id=row.get("project_id") or "",
    )


def _storage(request: Request) -> StorageBackend:
    from typing import cast

    return cast(StorageBackend, request.app.state.storage)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/alerts/feed", response_model=AlertFeedResponse)
async def get_alert_feed(
    request: Request,
    status: str | None = Query(
        default=None, description="active | acked | snoozed | resolved | all"
    ),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    project_id: str | None = Depends(get_active_project_id),
) -> AlertFeedResponse:
    """Return the fired alert feed for this project."""
    storage = _storage(request)
    pid = project_id or ""

    if not hasattr(storage, "get_fired_alerts"):
        return AlertFeedResponse(total=0, limit=limit, offset=offset, alerts=[])

    rows = await storage.get_fired_alerts(project_id=pid, status=status, limit=limit, offset=offset)
    total = await storage.count_fired_alerts(project_id=pid, status=status)
    return AlertFeedResponse(
        total=total,
        limit=limit,
        offset=offset,
        alerts=[_row_to_response(r) for r in rows],
    )


@router.get("/alerts/counts", response_model=AlertCountsResponse)
async def get_alert_counts(
    request: Request,
    project_id: str | None = Depends(get_active_project_id),
) -> AlertCountsResponse:
    """Return active alert counts per severity."""
    storage = _storage(request)
    pid = project_id or ""

    if not hasattr(storage, "get_alert_counts"):
        return AlertCountsResponse(critical=0, warning=0, info=0, total=0)

    counts = await storage.get_alert_counts(project_id=pid)
    return AlertCountsResponse(
        critical=counts.get("critical", 0),
        warning=counts.get("warning", 0),
        info=counts.get("info", 0),
        total=counts.get("total", 0),
    )


@router.post("/alerts/{alert_id}/ack", status_code=http_status.HTTP_200_OK)
async def ack_alert(
    alert_id: str,
    body: AckRequest,
    request: Request,
    project_id: str | None = Depends(get_active_project_id),
) -> dict[str, Any]:
    """Acknowledge a fired alert."""
    storage = _storage(request)
    if not hasattr(storage, "ack_alert"):
        raise HTTPException(status_code=501, detail="Alert persistence not supported")
    updated = await storage.ack_alert(alert_id=alert_id, acked_by=body.acked_by, project_id=project_id or "")
    if not updated:
        raise HTTPException(status_code=404, detail="Alert not found or already in final state")
    logger.info("alerts.acked", alert_id=alert_id, acked_by=body.acked_by)
    return {"ok": True, "alert_id": alert_id, "status": "acked"}


@router.post("/alerts/{alert_id}/resolve", status_code=http_status.HTTP_200_OK)
async def resolve_alert(
    alert_id: str,
    request: Request,
    project_id: str | None = Depends(get_active_project_id),
) -> dict[str, Any]:
    """Resolve a fired alert."""
    storage = _storage(request)
    if not hasattr(storage, "resolve_alert"):
        raise HTTPException(status_code=501, detail="Alert persistence not supported")
    updated = await storage.resolve_alert(alert_id=alert_id, project_id=project_id or "")
    if not updated:
        raise HTTPException(status_code=404, detail="Alert not found or already resolved")
    logger.info("alerts.resolved", alert_id=alert_id)
    return {"ok": True, "alert_id": alert_id, "status": "resolved"}


@router.post("/alerts/{alert_id}/snooze", status_code=http_status.HTTP_200_OK)
async def snooze_alert(
    alert_id: str,
    body: SnoozeRequest,
    request: Request,
    project_id: str | None = Depends(get_active_project_id),
) -> dict[str, Any]:
    """Snooze a fired alert for N minutes (15, 60, 240, or 1440)."""
    if body.minutes not in (15, 60, 240, 1440):
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="minutes must be one of: 15, 60, 240, 1440",
        )
    storage = _storage(request)
    if not hasattr(storage, "snooze_alert"):
        raise HTTPException(status_code=501, detail="Alert persistence not supported")
    updated = await storage.snooze_alert(alert_id=alert_id, snooze_minutes=body.minutes, project_id=project_id or "")
    if not updated:
        raise HTTPException(status_code=404, detail="Alert not found or already resolved")
    logger.info("alerts.snoozed", alert_id=alert_id, minutes=body.minutes)
    return {"ok": True, "alert_id": alert_id, "status": "snoozed", "minutes": body.minutes}
