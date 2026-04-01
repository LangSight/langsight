"""
Investigate API — AI-powered root cause analysis for MCP failures.

POST /api/investigate   — run an investigation on one or more servers

The endpoint gathers health history + schema drift evidence from storage,
sends it to the configured LLM provider (Claude, GPT-4o, Gemini, or Ollama),
and returns the RCA report as Markdown plus the raw evidence JSON.

Falls back to rule-based heuristics when no LLM API key is configured.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from langsight.api.dependencies import get_active_project_id
from langsight.exceptions import ConfigError
from langsight.models import ServerStatus
from langsight.storage.base import StorageBackend

logger = structlog.get_logger()
router = APIRouter(tags=["investigate"])

_MAX_HISTORY = 20

_SYSTEM_PROMPT = (
    "You are an expert SRE specialising in MCP (Model Context Protocol) server reliability. "
    "You analyse health check data and schema drift events to identify root causes of failures. "
    "Be concise, specific, and actionable. Format your response as Markdown."
)

_USER_PROMPT_TEMPLATE = """Analyse the following MCP server health evidence and produce a root cause analysis report.

## Evidence

{evidence}

## Required output format

For each server with issues, provide:

1. **Root Cause** — The most likely cause of the failure or degradation
2. **Evidence** — Specific data points that support your conclusion
3. **Impact** — What this means for agents using this server
4. **Recommended Actions** — Prioritised list of remediation steps

If all servers are healthy, confirm this with a brief summary.
Keep the report concise — use bullet points where possible."""


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class InvestigateRequest(BaseModel):
    server_names: list[str]
    window_hours: float = 1.0
    provider: str = "anthropic"
    model: str | None = None
    project_id: str | None = None


class ServerEvidence(BaseModel):
    server_name: str
    window_hours: float
    total_checks: int
    up_count: int
    down_count: int
    degraded_count: int
    latest_status: str
    latest_error: str | None
    avg_latency_ms: float | None
    schema_drift_events: int
    recent_errors: list[dict[str, str]]


class InvestigateResponse(BaseModel):
    report: str
    provider_used: str
    evidence: list[ServerEvidence]
    generated_at: str


# ---------------------------------------------------------------------------
# Evidence gathering
# ---------------------------------------------------------------------------


async def _gather_evidence(
    server_name: str,
    storage: StorageBackend,
    window_hours: float,
    project_id: str | None = None,
) -> dict[str, Any]:
    history = await storage.get_health_history(
        server_name, limit=_MAX_HISTORY, project_id=project_id
    )
    cutoff = datetime.now(UTC) - timedelta(hours=window_hours)
    recent = [r for r in history if r.checked_at >= cutoff]

    latencies = [r.latency_ms for r in recent if r.latency_ms is not None]
    avg_latency = sum(latencies) / len(latencies) if latencies else None

    return {
        "server_name": server_name,
        "window_hours": window_hours,
        "total_checks": len(recent),
        "down_count": sum(1 for r in recent if r.status == ServerStatus.DOWN),
        "degraded_count": sum(1 for r in recent if r.status == ServerStatus.DEGRADED),
        "up_count": sum(1 for r in recent if r.status == ServerStatus.UP),
        "latest_status": recent[0].status.value if recent else "no_data",
        "latest_error": recent[0].error if recent else None,
        "avg_latency_ms": avg_latency,
        "schema_drift_events": [
            {"checked_at": r.checked_at.isoformat(), "error": r.error}
            for r in recent
            if r.status == ServerStatus.DEGRADED and r.error and "schema drift" in r.error
        ],
        "recent_errors": [
            {"checked_at": r.checked_at.isoformat(), "error": r.error}
            for r in recent
            if r.error and r.status != ServerStatus.DEGRADED
        ][:5],
    }


def _format_evidence(evidence_map: dict[str, dict[str, Any]]) -> str:
    parts: list[str] = []
    for server_name, ev in evidence_map.items():
        total = ev["total_checks"]
        if total == 0:
            parts.append(f"### {server_name}\nNo data in the look-back window.\n")
            continue
        avg = f"{ev['avg_latency_ms']:.0f}ms" if ev["avg_latency_ms"] else "n/a"
        parts.append(
            f"### {server_name}\n"
            f"- Look-back window: {ev['window_hours']}h\n"
            f"- Total checks: {total}\n"
            f"- UP: {ev['up_count']}  DEGRADED: {ev['degraded_count']}  DOWN: {ev['down_count']}\n"
            f"- Latest status: {ev['latest_status']}\n"
            f"- Latest error: {ev['latest_error'] or 'none'}\n"
            f"- Average latency: {avg}\n"
            f"- Schema drift events: {len(ev['schema_drift_events'])}\n"
        )
        for d in ev["schema_drift_events"][:3]:
            parts.append(f"  - {d['checked_at']}: {d['error']}\n")
        if ev["recent_errors"]:
            parts.append("- Recent errors:\n")
            for e in ev["recent_errors"]:
                parts.append(f"  - {e['checked_at']}: {e['error']}\n")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Rule-based fallback
# ---------------------------------------------------------------------------


def _rule_based_report(evidence_map: dict[str, dict[str, Any]]) -> str:
    lines: list[str] = [
        "# Root Cause Analysis\n*(rule-based — configure ANTHROPIC_API_KEY for AI analysis)*\n"
    ]
    all_healthy = True

    for server_name, ev in evidence_map.items():
        total = ev["total_checks"]
        if total == 0:
            lines.append(f"## {server_name}\n\n**No data** in the look-back window.\n")
            continue

        status = ev["latest_status"]
        down_pct = ev["down_count"] / total * 100
        has_drift = bool(ev["schema_drift_events"])
        avg_lat = ev["avg_latency_ms"]

        if status == "up" and down_pct == 0 and not has_drift:
            lines.append(f"## {server_name}\n\n✅ **Healthy** — {total} checks passed.\n")
            continue

        all_healthy = False
        lines.append(f"## {server_name}\n")

        if status == "down" or down_pct > 50:
            lines.append(
                "**Root Cause**: Server is unreachable.\n\n"
                f"**Evidence**: {ev['down_count']}/{total} checks failed ({down_pct:.0f}%). "
                f"Error: `{ev['latest_error'] or 'unknown'}`\n\n"
                "**Actions**: Check if the MCP server process is running. Verify the command path.\n"
            )
        elif has_drift:
            d = ev["schema_drift_events"][0]
            lines.append(
                "**Root Cause**: Unexpected tool schema change.\n\n"
                f"**Evidence**: Drift at {d['checked_at']}: `{d['error']}`\n\n"
                "**Actions**: Verify recent deployments. Run `langsight scan` to check for poisoning.\n"
            )
        elif avg_lat and avg_lat > 1000:
            lines.append(
                f"**Root Cause**: High latency (avg {avg_lat:.0f}ms).\n\n"
                "**Actions**: Check DB or upstream service performance.\n"
            )
        elif ev["degraded_count"] > 0:
            lines.append(
                f"**Root Cause**: Intermittent degradation ({ev['degraded_count']}/{total} checks).\n\n"
                "**Actions**: Review recent errors in the health timeline.\n"
            )

    if all_healthy:
        lines.append("\n✅ **All servers are healthy.** No issues found in the look-back window.\n")

    lines.append("\n---\n*Set `ANTHROPIC_API_KEY` for AI-powered analysis with Claude.*")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.post("/investigate", response_model=InvestigateResponse)
async def run_investigation(
    body: InvestigateRequest,
    request: Request,
    project_id: str | None = Depends(get_active_project_id),
) -> InvestigateResponse:
    """Run an AI-powered root cause investigation on MCP servers.

    Gathers health history and schema drift evidence from storage, then
    uses the configured LLM provider to produce a root cause analysis
    report. Falls back to rule-based heuristics if no API key is set.
    """
    storage: StorageBackend = request.app.state.storage

    # Use the dependency-resolved project_id (enforced by auth), not the
    # user-supplied body.project_id, to prevent cross-project evidence reads.
    scoped_project_id = project_id  # from get_active_project_id dependency

    # Gather evidence in parallel
    tasks = [
        _gather_evidence(name, storage, body.window_hours, scoped_project_id)
        for name in body.server_names
    ]
    evidence_list = await asyncio.gather(*tasks)
    evidence_map: dict[str, dict[str, Any]] = {ev["server_name"]: ev for ev in evidence_list}

    # Try LLM provider
    report = ""
    provider_used = "rule-based"

    try:
        from langsight.investigate.providers import create_provider

        provider = create_provider(
            provider=body.provider,
            model=body.model,
            api_key=None,
            base_url=None,
        )
        evidence_text = _format_evidence(evidence_map)
        prompt = _USER_PROMPT_TEMPLATE.format(evidence=evidence_text)
        report = await provider.analyse(prompt, _SYSTEM_PROMPT)
        provider_used = provider.display_name
    except ConfigError:
        report = _rule_based_report(evidence_map)
    except Exception as exc:  # noqa: BLE001
        logger.warning("investigate.llm_error", error=str(exc))
        report = _rule_based_report(evidence_map)

    # Build evidence response objects
    evidence_out = [
        ServerEvidence(
            server_name=ev["server_name"],
            window_hours=ev["window_hours"],
            total_checks=ev["total_checks"],
            up_count=ev["up_count"],
            down_count=ev["down_count"],
            degraded_count=ev["degraded_count"],
            latest_status=ev["latest_status"],
            latest_error=ev["latest_error"],
            avg_latency_ms=ev["avg_latency_ms"],
            schema_drift_events=len(ev["schema_drift_events"]),
            recent_errors=ev["recent_errors"],
        )
        for ev in evidence_map.values()
    ]

    logger.info(
        "investigate.completed",
        servers=body.server_names,
        provider=provider_used,
        window_hours=body.window_hours,
    )

    return InvestigateResponse(
        report=report,
        provider_used=provider_used,
        evidence=evidence_out,
        generated_at=datetime.now(UTC).isoformat(),
    )
