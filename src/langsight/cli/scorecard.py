"""langsight scorecard — A-F composite health grades for MCP servers."""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from langsight.cli._storage import try_open_storage
from langsight.config import load_config
from langsight.health.checker import HealthChecker
from langsight.health.scorecard import ScorecardEngine, ScorecardResult, ServerHealthState
from langsight.models import HealthCheckResult, ServerStatus
from langsight.storage.base import StorageBackend

console = Console()
err_console = Console(stderr=True)

_GRADE_STYLE = {
    "A+": "bold bright_green",
    "A":  "bold green",
    "B":  "bold cyan",
    "C":  "bold yellow",
    "D":  "bold red",
    "F":  "bold bright_red",
}

_LOOKBACK_DAYS = 7


async def _build_state(
    server_name: str,
    result: HealthCheckResult,
    storage: StorageBackend | None,
) -> ServerHealthState:
    """Build a ServerHealthState from a live health check + optional stored history."""
    state = ServerHealthState(
        server_name=server_name,
        current_p99_ms=result.latency_ms,
    )

    # Seed from current check
    if result.status == ServerStatus.UP:
        state.total_checks_7d = 1
        state.successful_checks_7d = 1
    elif result.status in (ServerStatus.DOWN, ServerStatus.DEGRADED):
        state.total_checks_7d = 1
        state.successful_checks_7d = 0
        state.consecutive_failures = 1

    if not storage:
        return state

    try:
        cutoff = datetime.now(UTC) - timedelta(days=_LOOKBACK_DAYS)
        history = await storage.get_health_history(server_name, limit=500)
        recent = [r for r in history if r.checked_at >= cutoff]

        if recent:
            state.total_checks_7d = len(recent)
            state.successful_checks_7d = sum(1 for r in recent if r.status == ServerStatus.UP)

            # Consecutive failures from the front of the list (most-recent first)
            consec = 0
            for r in recent:
                if r.status != ServerStatus.UP:
                    consec += 1
                else:
                    break
            state.consecutive_failures = consec

            # Schema drift signals
            for r in recent:
                if r.status == ServerStatus.DEGRADED and r.error and "schema drift" in r.error:
                    if "breaking" in r.error:
                        state.breaking_drifts_7d += 1
                    else:
                        state.compatible_drifts_7d += 1

            # p99 baseline from stored latencies
            latencies = sorted(r.latency_ms for r in recent if r.latency_ms is not None)
            if latencies:
                p99_idx = max(0, int(len(latencies) * 0.99) - 1)
                state.baseline_p99_ms = latencies[p99_idx]

    except Exception:  # noqa: BLE001
        pass  # storage unavailable — fall back to single-check defaults

    return state


def _dimension_pts(result: ScorecardResult, name: str) -> str:
    """Format dimension as 'earned/max' pts (e.g. 28/30)."""
    for d in result.dimensions:
        if d.name == name:
            earned = round(d.score * d.weight)
            max_pts = round(d.weight * 100)
            return f"{earned}/{max_pts}"
    return "—"


def _display_table(results: list[ScorecardResult]) -> None:
    table = Table(
        title="MCP Server Scorecards",
        show_header=True,
        header_style="bold",
        border_style="dim",
    )
    table.add_column("Server", style="bold", min_width=18)
    table.add_column("Grade", justify="center", min_width=6)
    table.add_column("Score", justify="right", min_width=7)
    table.add_column("Avail", justify="right", min_width=7)
    table.add_column("Security", justify="right", min_width=10)
    table.add_column("Reliability", justify="right", min_width=11)
    table.add_column("Schema", justify="right", min_width=8)
    table.add_column("Perf", justify="right", min_width=6)
    table.add_column("Cap / Notes", style="dim", no_wrap=False)

    for r in results:
        grade_style = _GRADE_STYLE.get(r.grade, "bold")
        table.add_row(
            r.server_name,
            f"[{grade_style}]{r.grade}[/{grade_style}]",
            f"{r.score:.1f}",
            _dimension_pts(r, "availability"),
            _dimension_pts(r, "security"),
            _dimension_pts(r, "reliability"),
            _dimension_pts(r, "schema_stability"),
            _dimension_pts(r, "performance"),
            r.cap_applied or "",
        )

    console.print(table)


@click.command("scorecard")
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
    help="Grade a single server by name.",
)
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    help="Output results as JSON (stdout).",
)
@click.option(
    "--fail-below",
    "fail_below",
    type=click.Choice(["A", "B", "C", "D"]),
    default=None,
    help="Exit code 1 if any server grades below this threshold.",
)
def scorecard(
    config_path: Path | None,
    server_name: str | None,
    output_json: bool,
    fail_below: str | None,
) -> None:
    """Grade MCP servers A-F across availability, security, reliability, schema stability, and performance."""
    config = load_config(config_path)

    if not config.servers:
        err_console.print("[yellow]No MCP servers configured.[/yellow]")
        err_console.print("Run [bold]langsight init[/bold] to get started.")
        sys.exit(1)

    servers = config.servers
    if server_name:
        servers = [s for s in config.servers if s.name == server_name]
        if not servers:
            err_console.print(f"[red]Server '{server_name}' not found.[/red]")
            err_console.print(f"Available: {', '.join(s.name for s in config.servers)}")
            sys.exit(1)

    async def _run() -> list[ScorecardResult]:
        storage = await try_open_storage(config)
        try:
            checker = HealthChecker(storage=storage, project_id=config.project_id)
            health_results = await checker.check_many(servers)

            states = await asyncio.gather(*[
                _build_state(r.server_name, r, storage)
                for r in health_results
            ])
            return [ScorecardEngine.compute(s) for s in states]
        finally:
            if storage:
                await storage.close()

    scorecards = asyncio.run(_run())

    if output_json:
        click.echo(json.dumps([r.to_dict() for r in scorecards], indent=2))
        return

    _display_table(scorecards)

    _order = ["A+", "A", "B", "C", "D", "F"]
    if fail_below:
        threshold_idx = _order.index(fail_below)
        if any(_order.index(r.grade) > threshold_idx for r in scorecards):
            sys.exit(1)
