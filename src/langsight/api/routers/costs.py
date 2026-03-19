from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from langsight.api.dependencies import get_active_project_id, get_config, get_storage, require_admin
from langsight.config import LangSightConfig
from langsight.costs.engine import (
    AgentCostEntry,
    CostEntry,
    ModelPricingLookup,
    SessionCostEntry,
    aggregate_cost_rows,
    load_cost_rules,
)
from langsight.models import ModelPricing
from langsight.storage.base import StorageBackend

router = APIRouter(prefix="/costs", tags=["costs"])


# ---------------------------------------------------------------------------
# Model pricing request/response models
# ---------------------------------------------------------------------------


class ModelPricingResponse(BaseModel):
    id: str
    provider: str
    model_id: str
    display_name: str
    input_per_1m_usd: float
    output_per_1m_usd: float
    cache_read_per_1m_usd: float
    effective_from: str
    effective_to: str | None
    notes: str | None
    is_custom: bool
    is_active: bool


class CreateModelPricingRequest(BaseModel):
    provider: str
    model_id: str
    display_name: str
    input_per_1m_usd: float = 0.0
    output_per_1m_usd: float = 0.0
    cache_read_per_1m_usd: float = 0.0
    notes: str | None = None


def _pricing_to_response(p: ModelPricing) -> ModelPricingResponse:
    return ModelPricingResponse(
        id=p.id,
        provider=p.provider,
        model_id=p.model_id,
        display_name=p.display_name,
        input_per_1m_usd=p.input_per_1m_usd,
        output_per_1m_usd=p.output_per_1m_usd,
        cache_read_per_1m_usd=p.cache_read_per_1m_usd,
        effective_from=p.effective_from.isoformat(),
        effective_to=p.effective_to.isoformat() if p.effective_to else None,
        notes=p.notes,
        is_custom=p.is_custom,
        is_active=p.is_active,
    )


class CostBreakdownEntry(BaseModel):
    server_name: str
    tool_name: str
    total_calls: int
    cost_per_call_usd: float
    total_cost_usd: float
    cost_type: str = "call_based"
    model_id: str | None = None
    total_input_tokens: int = 0
    total_output_tokens: int = 0


class AgentCostBreakdownEntry(BaseModel):
    agent_name: str
    total_calls: int
    total_cost_usd: float


class SessionCostBreakdownEntry(BaseModel):
    session_id: str
    agent_name: str | None
    total_calls: int
    total_cost_usd: float


class CostsBreakdownResponse(BaseModel):
    storage_mode: str
    supports_costs: bool
    hours: int
    total_calls: int
    total_cost_usd: float
    llm_cost_usd: float = 0.0  # token-based LLM spend
    tool_cost_usd: float = 0.0  # call-based tool spend
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    by_tool: list[CostBreakdownEntry]
    by_agent: list[AgentCostBreakdownEntry]
    by_session: list[SessionCostBreakdownEntry]


def _to_tool_entry(entry: CostEntry) -> CostBreakdownEntry:
    data = entry.to_dict()
    return CostBreakdownEntry(
        server_name=data["server_name"],
        tool_name=data["tool_name"],
        total_calls=data["total_calls"],
        cost_per_call_usd=data["cost_per_call_usd"],
        total_cost_usd=data["total_cost_usd"],
        cost_type=data.get("cost_type", "call_based"),
        model_id=data.get("model_id"),
        total_input_tokens=data.get("total_input_tokens", 0),
        total_output_tokens=data.get("total_output_tokens", 0),
    )


def _to_agent_entry(entry: AgentCostEntry) -> AgentCostBreakdownEntry:
    data = entry.to_dict()
    return AgentCostBreakdownEntry(
        agent_name=data["agent_name"],
        total_calls=data["total_calls"],
        total_cost_usd=data["total_cost_usd"],
    )


def _to_session_entry(entry: SessionCostEntry) -> SessionCostBreakdownEntry:
    data = entry.to_dict()
    return SessionCostBreakdownEntry(
        session_id=data["session_id"],
        agent_name=data["agent_name"],
        total_calls=data["total_calls"],
        total_cost_usd=data["total_cost_usd"],
    )


@router.get(
    "/models",
    response_model=list[ModelPricingResponse],
    summary="List all model pricing entries",
)
async def list_model_pricing(
    storage: StorageBackend = Depends(get_storage),
) -> list[ModelPricingResponse]:
    """Return all model pricing entries (active and historical)."""
    if not hasattr(storage, "list_model_pricing"):
        return []
    entries = await storage.list_model_pricing()
    return [_pricing_to_response(e) for e in entries]


@router.post(
    "/models",
    response_model=ModelPricingResponse,
    status_code=201,
    summary="Add a custom model pricing entry (admin only)",
    dependencies=[Depends(require_admin)],
)
async def create_model_pricing(
    body: CreateModelPricingRequest,
    storage: StorageBackend = Depends(get_storage),
) -> ModelPricingResponse:
    """Add a custom model to the pricing table.

    Use this for:
    - Models not in the built-in seed list
    - Custom/fine-tuned models
    - Self-hosted models with a cost (e.g. GPU cloud inference)
    """
    if not hasattr(storage, "create_model_pricing"):
        from fastapi import HTTPException

        raise HTTPException(
            status_code=503, detail="Model pricing requires SQLite or PostgreSQL backend."
        )

    entry = ModelPricing(
        id=uuid.uuid4().hex,
        provider=body.provider,
        model_id=body.model_id,
        display_name=body.display_name,
        input_per_1m_usd=body.input_per_1m_usd,
        output_per_1m_usd=body.output_per_1m_usd,
        cache_read_per_1m_usd=body.cache_read_per_1m_usd,
        effective_from=datetime.now(UTC),
        notes=body.notes,
        is_custom=True,
    )
    await storage.create_model_pricing(entry)
    return _pricing_to_response(entry)


@router.patch(
    "/models/{entry_id}",
    response_model=ModelPricingResponse,
    summary="Update model pricing (admin only) — deactivates old, inserts new",
    dependencies=[Depends(require_admin)],
)
async def update_model_pricing(
    entry_id: str,
    body: CreateModelPricingRequest,
    storage: StorageBackend = Depends(get_storage),
) -> ModelPricingResponse:
    """Update pricing for a model.

    Deactivates the existing entry (sets effective_to=now) and creates
    a new active entry. This preserves full price history so historical
    cost calculations remain accurate.
    """
    if not hasattr(storage, "deactivate_model_pricing"):
        from fastapi import HTTPException

        raise HTTPException(
            status_code=503, detail="Model pricing requires SQLite or PostgreSQL backend."
        )

    await storage.deactivate_model_pricing(entry_id)

    new_entry = ModelPricing(
        id=uuid.uuid4().hex,
        provider=body.provider,
        model_id=body.model_id,
        display_name=body.display_name,
        input_per_1m_usd=body.input_per_1m_usd,
        output_per_1m_usd=body.output_per_1m_usd,
        cache_read_per_1m_usd=body.cache_read_per_1m_usd,
        effective_from=datetime.now(UTC),
        notes=body.notes,
        is_custom=True,
    )
    await storage.create_model_pricing(new_entry)
    return _pricing_to_response(new_entry)


@router.delete(
    "/models/{entry_id}",
    status_code=204,
    summary="Deactivate a model pricing entry (admin only)",
    dependencies=[Depends(require_admin)],
)
async def deactivate_model_pricing(
    entry_id: str,
    storage: StorageBackend = Depends(get_storage),
) -> None:
    """Deactivate a model pricing entry (sets effective_to=now)."""
    if not hasattr(storage, "deactivate_model_pricing"):
        from fastapi import HTTPException

        raise HTTPException(
            status_code=503, detail="Model pricing requires SQLite or PostgreSQL backend."
        )
    await storage.deactivate_model_pricing(entry_id)


@router.get(
    "/breakdown",
    response_model=CostsBreakdownResponse,
    summary="Get cost attribution breakdown",
)
async def get_costs_breakdown(
    request: Request,
    hours: int = Query(default=24, ge=1, le=720, description="Look-back window in hours"),
    project_id: str | None = Depends(get_active_project_id),
    storage: StorageBackend = Depends(get_storage),
    config: LangSightConfig = Depends(get_config),
) -> CostsBreakdownResponse:
    """Return cost attribution totals grouped by tool, agent, and session.

    Uses token-based pricing for LLM spans (when model_id + token counts available)
    and call-based pricing for MCP tool spans. Model pricing loaded from DB.
    """
    storage_mode = config.storage.mode
    if not hasattr(storage, "get_cost_call_counts"):
        return CostsBreakdownResponse(
            storage_mode=storage_mode,
            supports_costs=False,
            hours=hours,
            total_calls=0,
            total_cost_usd=0.0,
            by_tool=[],
            by_agent=[],
            by_session=[],
        )

    rows = await storage.get_cost_call_counts(hours=hours, project_id=project_id)

    config_path = getattr(request.app.state, "config_path", None)
    rules = load_cost_rules(config_path if isinstance(config_path, Path) else None)

    # Load model pricing from DB for token-based costing
    model_lookup: ModelPricingLookup | None = None
    if hasattr(storage, "list_model_pricing"):
        try:
            pricing_rows = await storage.list_model_pricing()
            # Only use active (effective_to is None) pricing
            active = [p for p in pricing_rows if p.effective_to is None]
            model_lookup = ModelPricingLookup(active)
        except Exception:  # noqa: BLE001
            pass

    by_tool, by_agent, by_session = aggregate_cost_rows(rows, rules, model_lookup)
    total_calls = sum(entry.total_calls for entry in by_tool)
    total_cost_usd = round(sum(entry.total_cost_usd for entry in by_tool), 6)
    llm_cost = round(sum(e.total_cost_usd for e in by_tool if e.cost_type == "token_based"), 6)
    tool_cost = round(sum(e.total_cost_usd for e in by_tool if e.cost_type == "call_based"), 6)
    total_input_tokens = sum(e.total_input_tokens for e in by_tool)
    total_output_tokens = sum(e.total_output_tokens for e in by_tool)

    return CostsBreakdownResponse(
        storage_mode=storage_mode,
        supports_costs=True,
        hours=hours,
        total_calls=total_calls,
        total_cost_usd=total_cost_usd,
        llm_cost_usd=llm_cost,
        tool_cost_usd=tool_cost,
        total_input_tokens=total_input_tokens,
        total_output_tokens=total_output_tokens,
        by_tool=[_to_tool_entry(entry) for entry in by_tool],
        by_agent=[_to_agent_entry(entry) for entry in by_agent],
        by_session=[_to_session_entry(entry) for entry in by_session[:10]],
    )
