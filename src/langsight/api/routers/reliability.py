"""
Tool reliability, anomaly detection, and incomplete session endpoints.

GET /api/reliability/anomalies           — statistically unusual tool behaviour
GET /api/reliability/tools               — per-tool reliability metrics
GET /api/reliability/incomplete-sessions — detect crashed/stale agent sessions
POST /api/reliability/tag-incomplete     — tag stale sessions as 'incomplete'
"""

from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, Depends, Query

from langsight.api.dependencies import get_active_project_id, get_storage
from langsight.reliability.engine import AnomalyDetector, ReliabilityEngine
from langsight.storage.base import StorageBackend

router = APIRouter(prefix="/reliability", tags=["reliability"])


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------


def _anomaly_to_dict(a: Any) -> dict[str, Any]:
    return cast(dict[str, Any], a.to_dict())


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get(
    "/anomalies",
    summary="Detect statistically anomalous tool behaviour",
    response_model=list[dict[str, Any]],
)
async def get_anomalies(
    current_hours: int = Query(
        default=1,
        ge=1,
        le=24,
        description="Time window for current metrics (hours)",
    ),
    baseline_hours: int = Query(
        default=168,
        ge=24,
        le=720,
        description="Baseline window for statistics (hours, default 7 days)",
    ),
    z_threshold: float = Query(
        default=2.0,
        ge=1.0,
        le=5.0,
        description="Z-score threshold to fire an anomaly (default 2.0 = 2 standard deviations)",
    ),
    project_id: str | None = Depends(get_active_project_id),
    storage: StorageBackend = Depends(get_storage),
) -> list[dict[str, Any]]:
    """Return tools whose current metrics deviate significantly from their baseline.

    Uses z-score comparison:
      z = (current_value - baseline_mean) / baseline_stddev

    An anomaly is fired when |z| >= z_threshold (default 2.0).
    Severity is "critical" when |z| >= 3.0, "warning" otherwise.

    Metrics checked per tool:
      - error_rate: fraction of failed calls
      - avg_latency_ms: mean call latency

    Requires ClickHouse backend.
    """
    detector = AnomalyDetector(storage, z_threshold=z_threshold)
    anomalies = await detector.detect(
        current_hours=current_hours,
        baseline_hours=baseline_hours,
        project_id=project_id,
    )
    return [_anomaly_to_dict(a) for a in anomalies]


@router.get(
    "/tools",
    summary="Per-tool reliability metrics",
    response_model=list[dict[str, Any]],
)
async def get_tool_metrics(
    hours: int = Query(default=24, ge=1, le=720),
    server_name: str | None = Query(default=None),
    project_id: str | None = Depends(get_active_project_id),
    storage: StorageBackend = Depends(get_storage),
) -> list[dict[str, Any]]:
    """Return reliability metrics for all tools over the given time window.

    Requires ClickHouse backend.
    """
    engine = ReliabilityEngine(storage)
    metrics = await engine.get_metrics(server_name=server_name, hours=hours, project_id=project_id)
    return [m.to_dict() for m in metrics]


@router.get(
    "/incomplete-sessions",
    summary="Detect stale/crashed agent sessions",
    response_model=list[dict[str, Any]],
)
async def get_incomplete_sessions(
    stale_minutes: int = Query(
        default=5,
        ge=1,
        le=60,
        description="Minutes since last span to consider a session stale",
    ),
    project_id: str | None = Depends(get_active_project_id),
    storage: StorageBackend = Depends(get_storage),
) -> list[dict[str, Any]]:
    """Find sessions that stopped receiving spans — likely crashed agents.

    A session is considered incomplete when:
    - Its last span was more than ``stale_minutes`` ago
    - It has fewer than 5 total spans
    - It has no existing health tag (not yet classified)
    """
    if not hasattr(storage, "get_incomplete_sessions"):
        return []
    return await storage.get_incomplete_sessions(
        stale_minutes=stale_minutes,
        project_id=project_id,
    )


@router.post(
    "/tag-incomplete",
    summary="Tag stale sessions as 'incomplete'",
)
async def tag_incomplete_sessions(
    stale_minutes: int = Query(default=5, ge=1, le=60),
    project_id: str | None = Depends(get_active_project_id),
    storage: StorageBackend = Depends(get_storage),
) -> dict[str, int]:
    """Scan for stale sessions and tag them as 'incomplete'.

    Returns the count of newly tagged sessions.
    """
    if not hasattr(storage, "get_incomplete_sessions") or not hasattr(storage, "save_session_health_tag"):
        return {"tagged": 0}

    incomplete = await storage.get_incomplete_sessions(
        stale_minutes=stale_minutes,
        project_id=project_id,
    )
    tagged = 0
    for session in incomplete:
        sid = session.get("session_id")
        if sid:
            await storage.save_session_health_tag(sid, "incomplete")
            tagged += 1
    return {"tagged": tagged}
