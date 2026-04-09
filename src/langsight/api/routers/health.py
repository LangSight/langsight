from __future__ import annotations

import asyncio
import inspect
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status

from langsight.api.dependencies import get_active_project_id, get_config, get_storage, require_admin
from langsight.config import LangSightConfig
from langsight.health.checker import HealthChecker
from langsight.models import HealthCheckResult, ServerStatus
from langsight.storage.base import StorageBackend

router = APIRouter(prefix="/health", tags=["health"])


async def _project_server_names(storage: StorageBackend, project_id: str) -> set[str]:
    """Return server names visible to a project.

    Unions server_metadata (Postgres) with ClickHouse health data so that
    the detail/history endpoints authorise exactly the same set that
    list_servers_health() shows.  Without the ClickHouse source, servers that
    appear in the list because they have health data would 404 on drill-down.
    """
    names: set[str] = set()
    get_meta = getattr(storage, "get_all_server_metadata", None)
    if get_meta and asyncio.iscoroutinefunction(get_meta):
        meta = await get_meta(project_id=project_id)
        names.update(m["server_name"] for m in meta)
    # Also authorise servers that have health-check data in ClickHouse for
    # this project — matches the list endpoint's inclusion logic exactly.
    ch_names = await _health_server_names(storage, project_id)
    names.update(ch_names)
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


async def _auto_discover_servers(
    storage: StorageBackend,
    project_id: str,
) -> list[dict[str, Any]]:
    """Auto-register MCP servers seen in traces into server_metadata.

    Fetches servers from ClickHouse tool call spans and upserts any that are
    not yet registered in Postgres server_metadata for this project.
    Returns the up-to-date server_metadata list (avoids a second round-trip).
    """
    span_fn = getattr(storage, "get_distinct_span_server_names", None)
    upsert_fn = getattr(storage, "upsert_server_metadata", None)
    get_meta_fn = getattr(storage, "get_all_server_metadata", None)

    if not (
        span_fn
        and asyncio.iscoroutinefunction(span_fn)
        and upsert_fn
        and asyncio.iscoroutinefunction(upsert_fn)
        and get_meta_fn
        and asyncio.iscoroutinefunction(get_meta_fn)
    ):
        return []

    span_names, existing_meta = await asyncio.gather(
        span_fn(project_id=project_id),
        get_meta_fn(project_id=project_id),
    )
    existing_names = {m["server_name"] for m in existing_meta}
    new_names = set(span_names) - existing_names
    if new_names:
        await asyncio.gather(
            *(
                upsert_fn(
                    server_name=name,
                    description="",
                    project_id=project_id,
                )
                for name in new_names
            )
        )
        return list(await get_meta_fn(project_id=project_id))
    return list(existing_meta)


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

    When a project is active:
      - Auto-discovers servers from traces and registers them in server_metadata
      - Only shows servers registered to this project (no global config bleed)
    When no project is active (admin/global view):
      - Shows servers from config.servers + any with health data in ClickHouse
    """
    ch_names = await _health_server_names(storage, project_id)

    if project_id:
        # Auto-discover from traces → upsert into server_metadata → get full list
        meta = await _auto_discover_servers(storage, project_id)
        meta_names = {m["server_name"] for m in meta}
        all_names = ch_names | meta_names
    else:
        # Global/admin view: include config.servers (no project filter)
        config_names = {s.name for s in config.servers}
        all_names = ch_names | config_names

    if not all_names:
        return []

    histories = await asyncio.gather(
        *(
            storage.get_health_history(name, limit=1, project_id=project_id)
            for name in sorted(all_names)
        )
    )
    results = [h[0] for h in histories if h]

    # Servers registered in metadata but never health-checked → synthetic UNKNOWN
    from datetime import UTC, datetime

    checked_names = {r.server_name for r in results}
    for name in sorted(all_names - checked_names):
        results.append(
            HealthCheckResult(
                server_name=name,
                status=ServerStatus.UNKNOWN,
                checked_at=datetime.now(UTC),
                project_id=project_id or "",
            )
        )
    return results


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
    project_id: str | None = Depends(get_active_project_id),
    _: None = Depends(require_admin),
) -> list[HealthCheckResult]:
    """Run a health check against all configured servers immediately.

    When project is active: checks SSE/HTTP servers registered to that project.
    stdio servers cannot be pinged from the API container (subprocess env missing).
    When no project: checks global config.servers (admin/CLI-managed servers).
    """
    if project_id:
        from langsight.models import MCPServer as MCPServerModel
        from langsight.models import TransportType

        meta_fn = getattr(storage, "get_all_server_metadata", None)
        if not meta_fn or not asyncio.iscoroutinefunction(meta_fn):
            return []
        meta_rows = await meta_fn(project_id=project_id)
        checkable: list[MCPServerModel] = []
        not_configured: list[HealthCheckResult] = []
        for row in meta_rows:
            transport_str = row.get("transport", "")
            url = row.get("url", "")
            if transport_str in ("sse", "streamable_http") and url:
                try:
                    checkable.append(
                        MCPServerModel(
                            name=row["server_name"],
                            transport=TransportType(transport_str),
                            url=url,
                        )
                    )
                except (ValueError, KeyError):
                    not_configured.append(
                        HealthCheckResult(
                            server_name=row.get("server_name", "unknown"),
                            status=ServerStatus.UNKNOWN,
                            error=(
                                "Server discovered but transport/url not configured"
                                " — edit server settings to enable health checks"
                            ),
                            project_id=project_id,
                        )
                    )
            else:
                not_configured.append(
                    HealthCheckResult(
                        server_name=row.get("server_name", "unknown"),
                        status=ServerStatus.UNKNOWN,
                        error=(
                            "Server discovered but transport/url not configured"
                            " — edit server settings to enable health checks"
                        ),
                        project_id=project_id,
                    )
                )
        if not checkable:
            return not_configured
        checker = HealthChecker(storage=storage, project_id=project_id)
        checked = await checker.check_many(checkable)
        return checked + not_configured

    # Global/admin view — use config.servers
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
    return list(await fn(server_name=server_name, limit=limit, project_id=project_id or ""))


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
    return list(
        await fn(server_name=server_name, tool_name=tool_name, hours=hours, project_id=project_id or "")
    )


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
