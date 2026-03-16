from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from langsight.config import load_config
from langsight.health.checker import HealthChecker
from langsight.models import HealthCheckResult, ServerStatus

console = Console()
err_console = Console(stderr=True)

_STATUS_DISPLAY = {
    ServerStatus.UP:       "[green]✓ up[/green]",
    ServerStatus.DEGRADED: "[yellow]⚠ degraded[/yellow]",
    ServerStatus.DOWN:     "[red]✗ down[/red]",
    ServerStatus.STALE:    "[dim]~ stale[/dim]",
    ServerStatus.UNKNOWN:  "[dim]? unknown[/dim]",
}


@click.command("mcp-health")
@click.option(
    "--config", "config_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Path to .langsight.yaml (auto-discovered if not set).",
)
@click.option(
    "--json", "output_json",
    is_flag=True,
    help="Output results as JSON (stdout).",
)
def mcp_health(config_path: Path | None, output_json: bool) -> None:
    """Check the health of all configured MCP servers."""
    config = load_config(config_path)

    if not config.servers:
        err_console.print("[yellow]No MCP servers configured.[/yellow]")
        err_console.print("Run [bold]langsight init[/bold] to get started.")
        sys.exit(1)

    checker = HealthChecker()
    results = asyncio.run(checker.check_many(config.servers))

    if output_json:
        click.echo(json.dumps([r.model_dump(mode="json") for r in results], indent=2))
    else:
        _display_table(results)

    if any(r.status == ServerStatus.DOWN for r in results):
        sys.exit(1)


def _display_table(results: list[HealthCheckResult]) -> None:
    table = Table(
        title=f"MCP Server Health  [dim]({len(results)} server{'s' if len(results) != 1 else ''})[/dim]",
        show_header=True,
        header_style="bold",
        border_style="dim",
    )
    table.add_column("Server", style="bold", min_width=18)
    table.add_column("Status", min_width=14)
    table.add_column("Latency", justify="right", min_width=9)
    table.add_column("Tools", justify="right", min_width=6)
    table.add_column("Schema", min_width=10)
    table.add_column("Error", style="red dim", no_wrap=False)

    for r in results:
        table.add_row(
            r.server_name,
            _STATUS_DISPLAY.get(r.status, r.status.value),
            f"{r.latency_ms:.0f}ms" if r.latency_ms is not None else "—",
            str(r.tools_count) if r.tools_count else "—",
            r.schema_hash or "—",
            r.error or "",
        )

    console.print(table)

    up = sum(1 for r in results if r.status == ServerStatus.UP)
    console.print(f"\n[dim]{up}/{len(results)} servers healthy[/dim]\n")
