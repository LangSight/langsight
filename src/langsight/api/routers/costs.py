from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from langsight.api.dependencies import get_config, get_storage
from langsight.config import LangSightConfig
from langsight.costs.engine import (
    AgentCostEntry,
    CostEntry,
    SessionCostEntry,
    aggregate_cost_rows,
    load_cost_rules,
)
from langsight.storage.base import StorageBackend

router = APIRouter(prefix="/costs", tags=["costs"])


class CostBreakdownEntry(BaseModel):
    server_name: str
    tool_name: str
    total_calls: int
    cost_per_call_usd: float
    total_cost_usd: float


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
    "/breakdown",
    response_model=CostsBreakdownResponse,
    summary="Get cost attribution breakdown",
)
async def get_costs_breakdown(
    request: Request,
    hours: int = Query(default=24, ge=1, le=720, description="Look-back window in hours"),
    storage: StorageBackend = Depends(get_storage),
    config: LangSightConfig = Depends(get_config),
) -> CostsBreakdownResponse:
    """Return cost attribution totals grouped by tool, agent, and session.

    Cost attribution requires a backend that exposes traced tool-call counts.
    ClickHouse provides this today.
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

    rows = await storage.get_cost_call_counts(hours=hours)
    config_path = getattr(request.app.state, "config_path", None)
    rules = load_cost_rules(config_path if isinstance(config_path, Path) else None)
    by_tool, by_agent, by_session = aggregate_cost_rows(rows, rules)
    total_calls = sum(entry.total_calls for entry in by_tool)
    total_cost_usd = round(sum(entry.total_cost_usd for entry in by_tool), 6)

    return CostsBreakdownResponse(
        storage_mode=storage_mode,
        supports_costs=True,
        hours=hours,
        total_calls=total_calls,
        total_cost_usd=total_cost_usd,
        by_tool=[_to_tool_entry(entry) for entry in by_tool],
        by_agent=[_to_agent_entry(entry) for entry in by_agent],
        by_session=[_to_session_entry(entry) for entry in by_session[:10]],
    )
