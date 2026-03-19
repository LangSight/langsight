"""
Tool reliability and anomaly detection endpoints.

GET /api/reliability/anomalies  — statistically unusual tool behaviour (P5.4)
GET /api/reliability/tools      — per-tool reliability metrics
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
