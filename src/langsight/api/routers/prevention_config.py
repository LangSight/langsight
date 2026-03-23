"""
Prevention Config API — dashboard-managed thresholds for agent loop/budget/circuit breaker.

GET  /api/agents/prevention-configs              — list all configs for the active project
GET  /api/agents/{agent_name}/prevention-config  — effective config for one agent
PUT  /api/agents/{agent_name}/prevention-config  — upsert config for one agent
DELETE /api/agents/{agent_name}/prevention-config — remove agent-specific config
GET  /api/projects/prevention-config             — project-level default config ("*")
PUT  /api/projects/prevention-config             — upsert project-level defaults
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from pydantic import BaseModel, Field

from langsight.api.dependencies import get_active_project_id, get_storage, require_admin
from langsight.models import PreventionConfig
from langsight.storage.base import StorageBackend

router = APIRouter(tags=["prevention-config"])

_DEFAULT_AGENT = "*"


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class PreventionConfigRequest(BaseModel):
    """Body for PUT /api/agents/{agent_name}/prevention-config."""

    loop_enabled: bool = True
    loop_threshold: int = Field(default=3, ge=1, le=50)
    loop_action: str = Field(default="terminate", pattern="^(terminate|warn)$")
    max_steps: int | None = Field(default=None, ge=1)
    max_cost_usd: float | None = Field(default=None, gt=0)
    max_wall_time_s: float | None = Field(default=None, gt=0)
    budget_soft_alert: float = Field(default=0.80, ge=0.1, le=1.0)
    cb_enabled: bool = True
    cb_failure_threshold: int = Field(default=5, ge=1)
    cb_cooldown_seconds: float = Field(default=60.0, ge=1.0)
    cb_half_open_max_calls: int = Field(default=2, ge=1)


class PreventionConfigResponse(BaseModel):
    """Returned by all prevention config endpoints."""

    agent_name: str
    loop_enabled: bool
    loop_threshold: int
    loop_action: str
    max_steps: int | None
    max_cost_usd: float | None
    max_wall_time_s: float | None
    budget_soft_alert: float
    cb_enabled: bool
    cb_failure_threshold: int
    cb_cooldown_seconds: float
    cb_half_open_max_calls: int
    is_default: bool  # True when this came from the "*" project default
    updated_at: str  # ISO 8601


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get(
    "/agents/prevention-configs",
    response_model=list[PreventionConfigResponse],
    summary="List all prevention configs for the active project",
)
async def list_prevention_configs(
    project_id: str | None = Depends(get_active_project_id),
    storage: StorageBackend = Depends(get_storage),
) -> list[PreventionConfigResponse]:
    """Return all per-agent and project-default prevention configs."""
    if not project_id or not hasattr(storage, "list_prevention_configs"):
        return []
    configs = await storage.list_prevention_configs(project_id)
    return [_to_response(c) for c in configs]


@router.get(
    "/agents/{agent_name}/prevention-config",
    response_model=PreventionConfigResponse,
    summary="Get effective prevention config for an agent",
    responses={404: {"description": "No config found — use SDK constructor defaults"}},
)
async def get_prevention_config(
    agent_name: str,
    project_id: str | None = Depends(get_active_project_id),
    storage: StorageBackend = Depends(get_storage),
) -> PreventionConfigResponse:
    """Return the effective config for an agent (agent-specific or project default).

    Used by the SDK on `client.wrap()` to fetch server-managed thresholds.
    Returns 404 when no config is set — SDK falls back to constructor defaults.
    """
    if not project_id or not hasattr(storage, "get_effective_prevention_config"):
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail="No prevention config found."
        )
    config = await storage.get_effective_prevention_config(agent_name, project_id)
    if not config:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail="No prevention config found."
        )
    return _to_response(config)


@router.put(
    "/agents/{agent_name}/prevention-config",
    response_model=PreventionConfigResponse,
    summary="Create or update prevention config for an agent",
)
async def upsert_prevention_config(
    agent_name: str,
    body: PreventionConfigRequest,
    project_id: str | None = Depends(get_active_project_id),
    storage: StorageBackend = Depends(get_storage),
    _: None = Depends(require_admin),
) -> PreventionConfigResponse:
    """Upsert prevention thresholds for an agent. SDK will pick these up on next wrap()."""
    if not project_id:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST, detail="Project required."
        )
    if not hasattr(storage, "upsert_prevention_config"):
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Prevention config requires PostgreSQL backend.",
        )
    now = datetime.now(UTC)
    existing = await storage.get_prevention_config(agent_name, project_id)
    config = PreventionConfig(
        id=existing.id if existing else uuid.uuid4().hex,
        project_id=project_id,
        agent_name=agent_name,
        loop_enabled=body.loop_enabled,
        loop_threshold=body.loop_threshold,
        loop_action=body.loop_action,
        max_steps=body.max_steps,
        max_cost_usd=body.max_cost_usd,
        max_wall_time_s=body.max_wall_time_s,
        budget_soft_alert=body.budget_soft_alert,
        cb_enabled=body.cb_enabled,
        cb_failure_threshold=body.cb_failure_threshold,
        cb_cooldown_seconds=body.cb_cooldown_seconds,
        cb_half_open_max_calls=body.cb_half_open_max_calls,
        created_at=existing.created_at if existing else now,
        updated_at=now,
    )
    saved = await storage.upsert_prevention_config(config)
    return _to_response(saved)


@router.delete(
    "/agents/{agent_name}/prevention-config",
    status_code=http_status.HTTP_204_NO_CONTENT,
    summary="Remove agent-specific prevention config (falls back to project default)",
)
async def delete_prevention_config(
    agent_name: str,
    project_id: str | None = Depends(get_active_project_id),
    storage: StorageBackend = Depends(get_storage),
    _: None = Depends(require_admin),
) -> None:
    """Delete the agent-specific config. Agent will use project default or SDK defaults."""
    if not project_id or not hasattr(storage, "delete_prevention_config"):
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Not found.")
    found = await storage.delete_prevention_config(agent_name, project_id)
    if not found:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail="No config found for this agent."
        )


@router.get(
    "/projects/prevention-config",
    response_model=PreventionConfigResponse,
    summary="Get project-level default prevention config",
    responses={404: {"description": "No project default set"}},
)
async def get_project_prevention_config(
    project_id: str | None = Depends(get_active_project_id),
    storage: StorageBackend = Depends(get_storage),
) -> PreventionConfigResponse:
    """Return the project-level default ('*') prevention config."""
    if not project_id or not hasattr(storage, "get_prevention_config"):
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Not found.")
    config = await storage.get_prevention_config(_DEFAULT_AGENT, project_id)
    if not config:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail="No project default set."
        )
    return _to_response(config)


@router.put(
    "/projects/prevention-config",
    response_model=PreventionConfigResponse,
    summary="Create or update project-level default prevention config",
)
async def upsert_project_prevention_config(
    body: PreventionConfigRequest,
    project_id: str | None = Depends(get_active_project_id),
    storage: StorageBackend = Depends(get_storage),
    _: None = Depends(require_admin),
) -> PreventionConfigResponse:
    """Upsert project-level defaults applied to all agents without a specific config."""
    if not project_id:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST, detail="Project required."
        )
    if not hasattr(storage, "upsert_prevention_config"):
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Prevention config requires PostgreSQL backend.",
        )
    now = datetime.now(UTC)
    existing = await storage.get_prevention_config(_DEFAULT_AGENT, project_id)
    config = PreventionConfig(
        id=existing.id if existing else uuid.uuid4().hex,
        project_id=project_id,
        agent_name=_DEFAULT_AGENT,
        loop_enabled=body.loop_enabled,
        loop_threshold=body.loop_threshold,
        loop_action=body.loop_action,
        max_steps=body.max_steps,
        max_cost_usd=body.max_cost_usd,
        max_wall_time_s=body.max_wall_time_s,
        budget_soft_alert=body.budget_soft_alert,
        cb_enabled=body.cb_enabled,
        cb_failure_threshold=body.cb_failure_threshold,
        cb_cooldown_seconds=body.cb_cooldown_seconds,
        cb_half_open_max_calls=body.cb_half_open_max_calls,
        created_at=existing.created_at if existing else now,
        updated_at=now,
    )
    saved = await storage.upsert_prevention_config(config)
    return _to_response(saved)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_response(config: PreventionConfig) -> PreventionConfigResponse:
    return PreventionConfigResponse(
        agent_name=config.agent_name,
        loop_enabled=config.loop_enabled,
        loop_threshold=config.loop_threshold,
        loop_action=config.loop_action,
        max_steps=config.max_steps,
        max_cost_usd=config.max_cost_usd,
        max_wall_time_s=config.max_wall_time_s,
        budget_soft_alert=config.budget_soft_alert,
        cb_enabled=config.cb_enabled,
        cb_failure_threshold=config.cb_failure_threshold,
        cb_cooldown_seconds=config.cb_cooldown_seconds,
        cb_half_open_max_calls=config.cb_half_open_max_calls,
        is_default=config.agent_name == _DEFAULT_AGENT,
        updated_at=config.updated_at.isoformat(),
    )
