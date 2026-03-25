from __future__ import annotations

import asyncio

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
    if get_meta:
        meta = await get_meta(project_id=project_id)
        names.update(m["server_name"] for m in meta)
    return names


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
    # Determine which servers to show
    allowed: set[str] | None = None
    if project_id:
        allowed = await _project_server_names(storage, project_id)

    visible = [s for s in config.servers if allowed is None or s.name in allowed]
    histories = await asyncio.gather(
        *(storage.get_health_history(s.name, limit=1, project_id=project_id) for s in visible)
    )
    return [h[0] for h in histories if h]


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
