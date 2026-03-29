from __future__ import annotations

import asyncio
import inspect
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status

from langsight.api.dependencies import get_active_project_id, get_config, get_storage, require_admin
from langsight.config import LangSightConfig
from langsight.health.checker import HealthChecker
from langsight.models import HealthCheckResult
from langsight.storage.base import StorageBackend

router = APIRouter(prefix="/health", tags=["health"])


async def _project_server_names(storage: StorageBackend, project_id: str) -> set[str]:
    """Return server names visible to a project (from server_metadata + spans)."""
    names: set[str] = set()
    get_meta = getattr(storage, "get_all_server_metadata", None)
    if get_meta and asyncio.iscoroutinefunction(get_meta):
        meta = await get_meta(project_id=project_id)
        names.update(m["server_name"] for m in meta)
    return names


async def _health_server_names(
    storage: StorageBackend,
    project_id: str | None,
) -> set[str]:
    """Return all server names that have health check data in ClickHouse.

    This is the source of truth for the health page — any server the CLI has
    ever checked will appear here, even if it's not in the API's config.servers.
    """
    fn = getattr(storage, "get_distinct_health_server_names", None)
    if fn and asyncio.iscoroutinefunction(fn):
        return set(await fn(project_id=project_id))
    return set()


@router.get(
    "/servers",
    response_model=list[HealthCheckResult],
    summary="List latest health status for all configured servers",
)
async def list_servers_health(
    storage: StorageBackend = Depends(get_storage),
    config: LangSightConfig = Depends(get_config),
    project_id: str | None = Depends(get_active_project_id),
) -> list[HealthCheckResult]:
    """Return the most recent health check result for each configured server.

    When a project is active, only returns health for servers visible to
    that project (based on server_metadata). Admins see all servers.
    """
    # Collect server names from three sources (union):
    #   1. ClickHouse health data  — servers the CLI has ever checked
    #   2. config.servers          — servers in this container's config
    #   3. server_metadata         — servers explicitly registered via API
    # This ensures CLI-monitored servers always appear in the dashboard,
    # even when the API container has a different (or empty) config.
    ch_names = await _health_server_names(storage, project_id)
    config_names = {s.name for s in config.servers}
    meta_names = await _project_server_names(storage, project_id) if project_id else set()

    all_names = ch_names | config_names | meta_names

    # When project scoping is active, only show servers that have health data
    # scoped to this project (already filtered by ClickHouse project_id above).
    # Servers from config/metadata without any health data in this project are
    # excluded to avoid ghost entries.
    if project_id and ch_names:
        all_names = ch_names | (config_names & meta_names)

    if not all_names:
        return []

    histories = await asyncio.gather(
        *(
            storage.get_health_history(name, limit=1, project_id=project_id)
            for name in sorted(all_names)
        )
    )
    return [h[0] for h in histories if h]


@router.get("/servers/invocations")
async def get_server_invocations(
    hours: int = Query(default=168, ge=1, le=720, description="Look-back window in hours"),
    storage: StorageBackend = Depends(get_storage),
    project_id: str | None = Depends(get_active_project_id),
) -> list[dict[str, Any]]:
    """Per-server last-invocation stats: last_called_at, last_call_ok, total_calls.

    Must be declared BEFORE /servers/{server_name} to avoid route shadowing.
    Used by the MCP Servers dashboard 'Last Used' and 'Last OK?' columns.
    """
    fn = getattr(storage, "get_server_invocation_stats", None)
    if fn is None or not inspect.iscoroutinefunction(fn):
        return []
    return list(await fn(project_id=project_id, hours=hours))


@router.get(
    "/servers/{server_name}",
    response_model=HealthCheckResult,
    summary="Get latest health status for one server",
    responses={404: {"description": "No health data found for this server"}},
)
async def get_server_health(
    server_name: str,
    storage: StorageBackend = Depends(get_storage),
    project_id: str | None = Depends(get_active_project_id),
) -> HealthCheckResult:
    """Return the most recent health check result for a specific server."""
    if project_id:
        allowed = await _project_server_names(storage, project_id)
        if server_name not in allowed:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND, detail="Server not found."
            )
    history = await storage.get_health_history(server_name, limit=1, project_id=project_id)
    if not history:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"No health data found for server '{server_name}'. Run a check first.",
        )
    return history[0]


@router.get(
    "/servers/{server_name}/history",
    response_model=list[HealthCheckResult],
    summary="Get health check history for one server",
)
async def get_server_history(
    server_name: str,
    limit: int = Query(default=10, ge=1, le=100, description="Number of results to return"),
    storage: StorageBackend = Depends(get_storage),
    project_id: str | None = Depends(get_active_project_id),
) -> list[HealthCheckResult]:
    """Return historical health check results for a server, newest first."""
    if project_id:
        allowed = await _project_server_names(storage, project_id)
        if server_name not in allowed:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND, detail="Server not found."
            )
    return await storage.get_health_history(server_name, limit=limit, project_id=project_id)


@router.post(
    "/check",
    response_model=list[HealthCheckResult],
    status_code=http_status.HTTP_200_OK,
    summary="Trigger on-demand health check for all servers",
)
async def trigger_health_check(
    storage: StorageBackend = Depends(get_storage),
    config: LangSightConfig = Depends(get_config),
    _: None = Depends(require_admin),
) -> list[HealthCheckResult]:
    """Run a health check against all configured servers immediately.

    Results are persisted and returned. Schema drift detection is active.
    """
    if not config.servers:
        return []
    checker = HealthChecker(storage=storage)
    return await checker.check_many(config.servers)


@router.get(
    "/servers/{server_name}/scorecard",
    summary="A-F composite health scorecard for a server",
)
async def get_server_scorecard(
    server_name: str,
    storage: StorageBackend = Depends(get_storage),
    project_id: str | None = Depends(get_active_project_id),
) -> dict[str, Any]:
    """Compute and return a composite A-F health grade for an MCP server.

    Combines availability (30%), security (25%), reliability (20%),
    schema stability (15%), and performance (10%) into a single grade.
    Hard veto caps can force the grade down for fatal flaws regardless
    of the numeric score (e.g. server DOWN 10x → automatic F).
    """
    from langsight.health.scorecard import ScorecardEngine, ServerHealthState

    # ── Availability: 7-day health history ───────────────────────────────
    history = await storage.get_health_history(server_name, limit=336, project_id=project_id)
    total = len(history)
    successful = sum(1 for h in history if h.status.value == "up")
    consecutive_failures = 0
    for h in history:  # newest first
        if h.status.value == "down":
            consecutive_failures += 1
        else:
            break

    # ── Schema drift: last 7 days ─────────────────────────────────────────
    breaking_drifts = 0
    compatible_drifts = 0
    drift_fn = getattr(storage, "get_schema_drift_history", None)
    if drift_fn:
        drift_rows = await drift_fn(server_name=server_name, limit=200)
        for row in drift_rows:
            if row.get("drift_type") == "breaking":
                breaking_drifts += 1
            elif row.get("drift_type") == "compatible":
                compatible_drifts += 1

    # ── Reliability: last 24 h from tool reliability ──────────────────────
    error_rate_pct = 0.0
    latency_cv = 0.0
    tool_rel_fn = getattr(storage, "get_tool_reliability", None)
    if tool_rel_fn:
        rel_rows = await tool_rel_fn(server_name=server_name, hours=24, project_id=project_id)
        if rel_rows:
            total_calls = sum(r.get("total_calls", 0) for r in rel_rows)
            total_errors = sum(r.get("error_calls", 0) for r in rel_rows)
            if total_calls > 0:
                error_rate_pct = (total_errors / total_calls) * 100

    # ── Performance: p99 latency from recent history ──────────────────────
    latencies = [h.latency_ms for h in history if h.latency_ms is not None]
    current_p99: float | None = None
    if latencies:
        sorted_lat = sorted(latencies)
        p99_idx = max(0, int(len(sorted_lat) * 0.99) - 1)
        current_p99 = sorted_lat[p99_idx]

    state = ServerHealthState(
        server_name=server_name,
        total_checks_7d=total,
        successful_checks_7d=successful,
        consecutive_failures=consecutive_failures,
        breaking_drifts_7d=breaking_drifts,
        compatible_drifts_7d=compatible_drifts,
        error_rate_pct=error_rate_pct,
        latency_cv=latency_cv,
        current_p99_ms=current_p99,
    )

    result = ScorecardEngine.compute(state)
    return result.to_dict()


@router.get(
    "/servers/{server_name}/drift-history",
    summary="Schema drift history for a server",
)
async def get_drift_history(
    server_name: str,
    limit: int = Query(default=20, ge=1, le=100),
    storage: StorageBackend = Depends(get_storage),
    project_id: str | None = Depends(get_active_project_id),
) -> list[dict[str, Any]]:
    """Return recent schema drift events for a server, newest first.

    Each entry represents one atomic tool schema change (tool removed,
    parameter added, description changed, etc.) with its drift_type
    classification (breaking / compatible / warning).
    """
    fn = getattr(storage, "get_schema_drift_history", None)
    if fn is None:
        return []
    return list(await fn(server_name=server_name, limit=limit))


@router.get(
    "/servers/{server_name}/drift-impact",
    summary="Consumer impact for a changed tool",
)
async def get_drift_impact(
    server_name: str,
    tool_name: str = Query(..., description="Tool name to analyse"),
    hours: int = Query(default=24, ge=1, le=168),
    storage: StorageBackend = Depends(get_storage),
    project_id: str | None = Depends(get_active_project_id),
) -> list[dict[str, Any]]:
    """Return agents and sessions that called a tool recently.

    Use this to answer: 'Tool X changed — which agents will break?'
    Results are ordered by call_count descending.
    """
    fn = getattr(storage, "get_drift_impact", None)
    if fn is None:
        return []
    return list(await fn(server_name=server_name, tool_name=tool_name, hours=hours))


@router.get(
    "/servers/{server_name}/blast-radius",
    summary="Blast radius — which agents and sessions are affected when this server is down",
)
async def get_blast_radius(
    server_name: str,
    hours: int = Query(default=24, ge=1, le=168),
    storage: StorageBackend = Depends(get_storage),
    project_id: str | None = Depends(get_active_project_id),
) -> dict[str, Any]:
    """Compute blast radius for a server outage.

    Returns which agents depend on this server and how many sessions
    are at risk, based on real tool-call traffic from the last N hours.
    Severity is classified as: critical / high / medium / low.
    """
    from langsight.rca.blast_radius import compute_blast_radius

    # Resolve current server status from latest health result
    server_status: str = "unknown"
    history_fn = getattr(storage, "get_health_history", None)
    if history_fn is not None:
        history = await history_fn(server_name=server_name, limit=1, project_id=project_id)
        if history:
            server_status = history[0].status

    result = await compute_blast_radius(
        server_name=server_name,
        storage=storage,
        hours=hours,
        project_id=project_id,
        server_status=server_status,
    )
    return result.model_dump()


@router.get(
    "/servers/{server_name}/logs",
    summary="Recent tool call log entries for a server",
)
async def get_server_logs(
    server_name: str,
    hours: int = Query(default=24, ge=1, le=168),
    limit: int = Query(default=200, ge=1, le=1000),
    storage: StorageBackend = Depends(get_storage),
    project_id: str | None = Depends(get_active_project_id),
) -> list[dict[str, Any]]:
    """Return recent tool call activity for a server as a chronological log.

    Entries are ordered newest-first. Each entry includes the agent that made
    the call, tool name, status, latency, error message, and session ID.
    """
    fn = getattr(storage, "get_server_logs", None)
    if fn is None:
        return []
    return list(
        await fn(
            server_name=server_name,
            hours=hours,
            limit=limit,
            project_id=project_id,
        )
    )
