"""
langsight investigate — AI-assisted root cause attribution for MCP failures.

Gathers evidence from storage (health history, schema drift, alerts) and
sends it to Claude for root cause analysis. Falls back to rule-based
heuristics when ANTHROPIC_API_KEY is not set.

Usage:
    langsight investigate                          # analyse all servers
    langsight investigate --server postgres-mcp    # focus on one server
    langsight investigate --window 2h              # look back 2 hours
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from langsight.config import LangSightConfig, load_config
from langsight.exceptions import ConfigError
from langsight.investigate.providers import LLMProvider, create_provider
from langsight.models import ServerStatus
from langsight.storage.factory import open_storage

console = Console()
err_console = Console(stderr=True)

_DEFAULT_WINDOW_HOURS = 1
_MAX_HISTORY_RESULTS = 20


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


@click.command("investigate")
@click.option(
    "--config",
    "config_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Path to .langsight.yaml (auto-discovered if not set).",
)
@click.option(
    "--server",
    "server_name",
    default=None,
    help="Focus investigation on a specific server (default: all servers).",
)
@click.option(
    "--window",
    "-w",
    default=f"{_DEFAULT_WINDOW_HOURS}h",
    show_default=True,
    help="Look-back window, e.g. 30m, 2h, 1d.",
)
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    help="Output raw evidence JSON instead of the RCA report.",
)
def investigate(
    config_path: Path | None,
    server_name: str | None,
    window: str,
    output_json: bool,
) -> None:
    """Investigate MCP failures and attribute root causes.

    Queries health history and schema drift data, then uses Claude to
    produce a root cause analysis report. Falls back to rule-based
    analysis when ANTHROPIC_API_KEY is not configured.
    """
    config = load_config(config_path)

    if not config.servers:
        err_console.print("[yellow]No MCP servers configured.[/yellow]")
        err_console.print("Run [bold]langsight init[/bold] to get started.")
        sys.exit(1)

    servers = (
        [s for s in config.servers if s.name == server_name] if server_name else config.servers
    )
    if not servers:
        err_console.print(f"[red]Server '{server_name}' not found in config.[/red]")
        sys.exit(1)

    window_hours = _parse_window(window)
    try:
        asyncio.run(_run(servers, config, window_hours, output_json))
    except ConfigError as exc:
        err_console.print(f"[red]Storage not configured:[/red] {exc}")
        err_console.print(
            "[dim]investigate requires ClickHouse + Postgres. "
            "Run [bold]docker compose up[/bold] to start the full stack.[/dim]"
        )
        sys.exit(1)


# ---------------------------------------------------------------------------
# Evidence gathering
# ---------------------------------------------------------------------------


async def _run(
    servers: list[Any], config: LangSightConfig, window_hours: float, output_json: bool
) -> None:
    async with await open_storage(config.storage) as storage:
        evidence_by_server: dict[str, dict[str, Any]] = {}

        for server in servers:
            history = await storage.get_health_history(server.name, limit=_MAX_HISTORY_RESULTS)

            # Filter to the look-back window
            cutoff = datetime.now(UTC) - timedelta(hours=window_hours)
            recent = [r for r in history if r.checked_at >= cutoff]

            evidence_by_server[server.name] = {
                "server_name": server.name,
                "transport": server.transport.value,
                "window_hours": window_hours,
                "total_checks": len(recent),
                "down_count": sum(1 for r in recent if r.status == ServerStatus.DOWN),
                "degraded_count": sum(1 for r in recent if r.status == ServerStatus.DEGRADED),
                "up_count": sum(1 for r in recent if r.status == ServerStatus.UP),
                "latest_status": recent[0].status.value if recent else "no_data",
                "latest_error": recent[0].error if recent else None,
                "schema_drift_events": [
                    {
                        "checked_at": r.checked_at.isoformat(),
                        "error": r.error,
                        "schema_hash": r.schema_hash,
                    }
                    for r in recent
                    if r.status == ServerStatus.DEGRADED and r.error and "schema drift" in r.error
                ],
                "latency_ms_samples": [r.latency_ms for r in recent if r.latency_ms is not None],
                "recent_errors": [
                    {"checked_at": r.checked_at.isoformat(), "error": r.error}
                    for r in recent
                    if r.error and r.status != ServerStatus.DEGRADED
                ][:5],
            }

    if output_json:
        import json

        click.echo(json.dumps(evidence_by_server, indent=2))
        return

    inv_cfg = config.investigate
    try:
        provider = create_provider(
            provider=inv_cfg.provider,
            model=inv_cfg.model,
            api_key=None,  # resolved from env vars (ANTHROPIC_API_KEY etc.)
            base_url=inv_cfg.base_url,
        )
        await _analyse_with_llm(evidence_by_server, provider)
    except ConfigError as exc:
        err_console.print(f"[yellow]{exc}[/yellow]")
        err_console.print("[dim]Falling back to rule-based analysis.[/dim]")
        _analyse_with_rules(evidence_by_server)


# ---------------------------------------------------------------------------
# LLM analysis
# ---------------------------------------------------------------------------

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


async def _analyse_with_llm(evidence: dict[str, dict[str, Any]], provider: LLMProvider) -> None:
    """Send evidence to the configured LLM provider and display the RCA report."""
    evidence_text = _format_evidence_for_prompt(evidence)
    prompt = _USER_PROMPT_TEMPLATE.format(evidence=evidence_text)

    console.print(f"\n[dim]Analysing with {provider.display_name}...[/dim]")

    try:
        report = await provider.analyse(prompt, _SYSTEM_PROMPT)
        console.print(
            Panel(
                Markdown(report),
                title=f"[bold]Root Cause Analysis[/bold]  [dim]({provider.display_name})[/dim]",
                border_style="blue",
            )
        )
    except Exception as exc:  # noqa: BLE001
        err_console.print(
            f"[yellow]LLM error ({exc}) — falling back to rule-based analysis.[/yellow]"
        )
        _analyse_with_rules(evidence)


# ---------------------------------------------------------------------------
# Rule-based fallback
# ---------------------------------------------------------------------------


def _analyse_with_rules(evidence: dict[str, dict[str, Any]]) -> None:
    """Deterministic RCA heuristics — no API key required."""
    lines: list[str] = [
        "# Root Cause Analysis  *(rule-based — configure a provider in .langsight.yaml for AI analysis)*\n"
    ]

    all_healthy = True
    for server_name, ev in evidence.items():
        status = ev["latest_status"]
        total = ev["total_checks"]

        if total == 0:
            lines.append(f"## {server_name}\n\n**No data** in the look-back window.\n")
            continue

        down_pct = ev["down_count"] / total * 100 if total else 0
        has_drift = bool(ev["schema_drift_events"])
        avg_latency = (
            sum(ev["latency_ms_samples"]) / len(ev["latency_ms_samples"])
            if ev["latency_ms_samples"]
            else None
        )

        if status == "up" and down_pct == 0 and not has_drift:
            lines.append(
                f"## {server_name}\n\n✅ **Healthy** — {total} checks passed, no issues detected.\n"
            )
            continue

        all_healthy = False
        lines.append(f"## {server_name}\n")

        # Root cause
        if status == "down" or down_pct > 50:
            lines.append(
                "**Root Cause**: Server is unreachable — connection failure or process crash.\n\n"
                f"**Evidence**: {ev['down_count']}/{total} checks failed "
                f"({down_pct:.0f}%). Latest error: `{ev['latest_error'] or 'unknown'}`\n\n"
                "**Recommended Actions**:\n"
                "1. Check if the MCP server process is running\n"
                "2. Verify the `command` path in `.langsight.yaml` is correct\n"
                "3. Run `langsight mcp-health` to get current status\n"
            )
        elif has_drift:
            drift = ev["schema_drift_events"][0]
            lines.append(
                "**Root Cause**: Tool schema changed unexpectedly — possible unplanned deployment or supply chain issue.\n\n"
                f"**Evidence**: Schema drift detected at {drift['checked_at']}: `{drift['error']}`\n\n"
                "**Recommended Actions**:\n"
                "1. Verify if a deployment occurred at the time of the drift\n"
                "2. Run `langsight security-scan` to check for tool poisoning\n"
                "3. Review the MCP server's changelog or recent commits\n"
            )
        elif avg_latency and avg_latency > 1000:
            lines.append(
                f"**Root Cause**: High latency — server is responding but slowly (avg {avg_latency:.0f}ms).\n\n"
                "**Evidence**: Latency above 1000ms threshold, which degrades agent response times.\n\n"
                "**Recommended Actions**:\n"
                "1. Check database or upstream service performance\n"
                "2. Review server logs for slow queries or connection pool exhaustion\n"
                "3. Consider increasing `timeout_seconds` in `.langsight.yaml` as a short-term fix\n"
            )
        elif ev["degraded_count"] > 0:
            lines.append(
                "**Root Cause**: Intermittent degradation.\n\n"
                f"**Evidence**: {ev['degraded_count']}/{total} checks returned DEGRADED status.\n\n"
                "**Recommended Actions**:\n"
                "1. Run `langsight mcp-health` to check current state\n"
                "2. Review recent errors: "
                + ", ".join(f"`{e['error']}`" for e in ev["recent_errors"][:3])
                + "\n"
            )

    if all_healthy:
        lines.append("\n✅ **All servers are healthy.** No issues found in the look-back window.\n")

    lines.append("\n---\n*Set `ANTHROPIC_API_KEY` for AI-powered root cause analysis with Claude.*")

    console.print(
        Panel(
            Markdown("\n".join(lines)),
            title="[bold]Root Cause Analysis[/bold]  [dim](rule-based)[/dim]",
            border_style="yellow",
        )
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_window(window: str) -> float:
    """Parse a window string like '30m', '2h', '1d' into hours."""
    window = window.strip().lower()
    if window.endswith("m"):
        return float(window[:-1]) / 60
    if window.endswith("h"):
        return float(window[:-1])
    if window.endswith("d"):
        return float(window[:-1]) * 24
    return float(window)  # assume hours


def _format_evidence_for_prompt(evidence: dict[str, dict[str, Any]]) -> str:
    """Format evidence as a readable text block for the Claude prompt."""
    parts: list[str] = []
    for server_name, ev in evidence.items():
        total = ev["total_checks"]
        if total == 0:
            parts.append(f"### {server_name}\nNo data in the look-back window.\n")
            continue

        latencies = ev["latency_ms_samples"]
        avg_lat = f"{sum(latencies) / len(latencies):.0f}ms" if latencies else "n/a"

        parts.append(
            f"### {server_name} (transport: {ev['transport']})\n"
            f"- Look-back window: {ev['window_hours']}h\n"
            f"- Total checks: {total}\n"
            f"- UP: {ev['up_count']}  DEGRADED: {ev['degraded_count']}  DOWN: {ev['down_count']}\n"
            f"- Latest status: {ev['latest_status']}\n"
            f"- Latest error: {ev['latest_error'] or 'none'}\n"
            f"- Average latency: {avg_lat}\n"
            f"- Schema drift events: {len(ev['schema_drift_events'])}\n"
        )
        if ev["schema_drift_events"]:
            for d in ev["schema_drift_events"][:3]:
                parts.append(f"  - {d['checked_at']}: {d['error']}\n")
        if ev["recent_errors"]:
            parts.append("- Recent errors:\n")
            for e in ev["recent_errors"]:
                parts.append(f"  - {e['checked_at']}: {e['error']}\n")

    return "\n".join(parts)
