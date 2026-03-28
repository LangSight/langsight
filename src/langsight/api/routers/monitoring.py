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
    error_rate: float = 0.0       # MCP: errors / tool_calls
    avg_latency_ms: float = 0.0   # MCP: avg tool call latency
    p99_latency_ms: float = 0.0   # MCP: p99 tool call latency
    input_tokens: int = 0
    output_tokens: int = 0
    agents: int = 0
    failed_sessions: int = 0              # Agent: sessions with ≥1 failed tool call
    session_error_rate: float = 0.0       # Agent: failed_sessions / sessions
    session_p99_ms: float = 0.0           # Agent: p99 of agent span duration


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
    calls_per_session: float = 0.0
    content_errors: int = 0


class ErrorCategory(BaseModel):
    category: str
    count: int = 0
    llm_errors: int = 0
    tool_errors: int = 0
    pct: float = 0.0


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
            m.est_cost_usd = round(
                m.input_tokens / 1_000_000 * inp + m.output_tokens / 1_000_000 * out, 6
            )
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


class MonitoringTrends(BaseModel):
    cur_avg_latency_ms: float | None = None
    prev_avg_latency_ms: float | None = None
    avg_latency_delta_pct: float | None = None
    cur_p99_latency_ms: float | None = None
    prev_p99_latency_ms: float | None = None
    p99_latency_delta_pct: float | None = None
    cur_error_rate: float | None = None
    prev_error_rate: float | None = None
    error_rate_delta_pct: float | None = None
    cur_sessions: int | None = None
    prev_sessions: int | None = None
    sessions_delta_pct: float | None = None


@router.get("/trends", response_model=MonitoringTrends)
async def get_trends(
    project_id: str | None = Depends(get_active_project_id),
    storage: StorageBackend = Depends(get_storage),
) -> MonitoringTrends:
    """Compare last 7 days vs previous 7 days — sessions, error rate, latency."""
    if not hasattr(storage, "get_monitoring_trends"):
        return MonitoringTrends()
    data = await storage.get_monitoring_trends(project_id=project_id)
    return MonitoringTrends(**data) if data else MonitoringTrends()


@router.get("/errors", response_model=list[ErrorCategory])
async def get_error_breakdown(
    hours: int = Query(default=24, ge=1, le=720),
    project_id: str | None = Depends(get_active_project_id),
    storage: StorageBackend = Depends(get_storage),
) -> list[ErrorCategory]:
    """Return error taxonomy breakdown — what types of errors are failing."""
    if not hasattr(storage, "get_error_breakdown"):
        return []
    rows = await storage.get_error_breakdown(hours=hours, project_id=project_id)
    return [ErrorCategory(**r) for r in rows]
