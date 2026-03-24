"""
Monitoring time-series endpoints — Overview, Models, Tools.

Provides hourly-bucketed metrics for the dashboard monitoring page:
  GET /api/monitoring/timeseries  — traffic, errors, latency, tokens over time
  GET /api/monitoring/models      — per-model cost, tokens, latency
  GET /api/monitoring/tools       — per-tool call volume, errors, latency
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from langsight.api.dependencies import get_active_project_id, get_storage
from langsight.storage.base import StorageBackend

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class TimeseriesBucket(BaseModel):
    bucket: str  # ISO timestamp for the start of the bucket
    sessions: int = 0
    tool_calls: int = 0
    errors: int = 0
    error_rate: float = 0.0
    avg_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    agents: int = 0


class ModelMetrics(BaseModel):
    model_id: str
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    avg_latency_ms: float = 0.0
    error_count: int = 0
    est_cost_usd: float | None = None


class ToolMetrics(BaseModel):
    server_name: str
    tool_name: str
    calls: int = 0
    errors: int = 0
    avg_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    success_rate: float = 100.0


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/timeseries", response_model=list[TimeseriesBucket])
async def get_timeseries(
    hours: int = Query(default=24, ge=1, le=720),
    project_id: str | None = Depends(get_active_project_id),
    storage: StorageBackend = Depends(get_storage),
) -> list[TimeseriesBucket]:
    """Return hourly-bucketed metrics for the monitoring dashboard."""
    if not hasattr(storage, "get_monitoring_timeseries"):
        return []
    rows = await storage.get_monitoring_timeseries(hours=hours, project_id=project_id)
    return [TimeseriesBucket(**r) for r in rows]


@router.get("/models", response_model=list[ModelMetrics])
async def get_models(
    hours: int = Query(default=24, ge=1, le=720),
    project_id: str | None = Depends(get_active_project_id),
    storage: StorageBackend = Depends(get_storage),
) -> list[ModelMetrics]:
    """Return per-model token usage, latency, and cost."""
    if not hasattr(storage, "get_monitoring_models"):
        return []
    rows = await storage.get_monitoring_models(hours=hours, project_id=project_id)

    # Estimate cost from model pricing if available
    pricing: dict[str, tuple[float, float]] = {}
    if hasattr(storage, "list_model_pricing"):
        for mp in await storage.list_model_pricing():
            pricing[mp.model_id] = (mp.input_per_1m_usd, mp.output_per_1m_usd)

    result = []
    for r in rows:
        m = ModelMetrics(**r)
        if m.model_id in pricing:
            inp, out = pricing[m.model_id]
            m.est_cost_usd = round(m.input_tokens / 1_000_000 * inp + m.output_tokens / 1_000_000 * out, 6)
        result.append(m)
    return result


@router.get("/tools", response_model=list[ToolMetrics])
async def get_tools(
    hours: int = Query(default=24, ge=1, le=720),
    project_id: str | None = Depends(get_active_project_id),
    storage: StorageBackend = Depends(get_storage),
) -> list[ToolMetrics]:
    """Return per-tool call volume, errors, and latency."""
    if not hasattr(storage, "get_monitoring_tools"):
        return []
    rows = await storage.get_monitoring_tools(hours=hours, project_id=project_id)
    return [ToolMetrics(**r) for r in rows]
