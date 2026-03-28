"""Blast radius computation for downed MCP servers.

When a server goes DOWN or DEGRADED, this module answers:
  - Which agents depend on this server?
  - How many sessions are at risk?
  - What is the estimated severity of the outage?

Data source: ClickHouse mcp_tool_calls (last N hours of real traffic).
"""

from __future__ import annotations

from enum import Enum

import structlog
from pydantic import BaseModel

from langsight.storage.base import StorageBackend

logger = structlog.get_logger()


class BlastRadiusSeverity(str, Enum):
    CRITICAL = "critical"   # > 5 agents or > 100 sessions at risk
    HIGH = "high"           # > 2 agents or > 20 sessions
    MEDIUM = "medium"       # any recent traffic
    LOW = "low"             # no recent traffic


class AffectedAgent(BaseModel):
    agent_name: str
    call_count: int
    session_count: int
    error_count: int
    error_rate_pct: float
    avg_latency_ms: float | None
    last_called_at: str | None


class BlastRadiusResult(BaseModel):
    server_name: str
    server_status: str
    hours: int
    severity: BlastRadiusSeverity
    total_sessions_at_risk: int
    total_agents_affected: int
    total_calls: int
    affected_agents: list[AffectedAgent]


async def compute_blast_radius(
    server_name: str,
    storage: StorageBackend,
    hours: int = 24,
    project_id: str | None = None,
    server_status: str = "unknown",
) -> BlastRadiusResult:
    """Compute blast radius for a server outage.

    Queries real tool-call traffic to determine which agents
    and sessions are affected if this server is unavailable.
    """
    fn = getattr(storage, "get_blast_radius_data", None)
    if fn is None:
        logger.warning("blast_radius.storage_not_supported", server=server_name)
        return BlastRadiusResult(
            server_name=server_name,
            server_status=server_status,
            hours=hours,
            severity=BlastRadiusSeverity.LOW,
            total_sessions_at_risk=0,
            total_agents_affected=0,
            total_calls=0,
            affected_agents=[],
        )

    data: dict = await fn(
        server_name=server_name,
        hours=hours,
        project_id=project_id,
    )

    agents: list[AffectedAgent] = []
    total_calls = 0

    for row in data.get("agents", []):
        call_count = int(row.get("call_count", 0))
        session_count = int(row.get("session_count", 0))
        error_count = int(row.get("error_count", 0))
        total_calls += call_count

        agents.append(
            AffectedAgent(
                agent_name=str(row["agent_name"]),
                call_count=call_count,
                session_count=session_count,
                error_count=error_count,
                error_rate_pct=round(error_count / call_count * 100, 1) if call_count else 0.0,
                avg_latency_ms=float(row["avg_latency_ms"]) if row.get("avg_latency_ms") is not None else None,
                last_called_at=str(row["last_called_at"]) if row.get("last_called_at") else None,
            )
        )

    n_agents = len(agents)
    n_sessions = int(data.get("total_sessions", 0))

    if n_agents > 5 or n_sessions > 100:
        severity = BlastRadiusSeverity.CRITICAL
    elif n_agents > 2 or n_sessions > 20:
        severity = BlastRadiusSeverity.HIGH
    elif n_agents > 0:
        severity = BlastRadiusSeverity.MEDIUM
    else:
        severity = BlastRadiusSeverity.LOW

    logger.info(
        "blast_radius.computed",
        server=server_name,
        status=server_status,
        severity=severity,
        agents=n_agents,
        sessions=n_sessions,
    )

    return BlastRadiusResult(
        server_name=server_name,
        server_status=server_status,
        hours=hours,
        severity=severity,
        total_sessions_at_risk=n_sessions,
        total_agents_affected=n_agents,
        total_calls=total_calls,
        affected_agents=agents,
    )
