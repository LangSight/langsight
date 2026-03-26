"""
langsight costs — tool call cost attribution report.

Shows how much each MCP tool costs per server, sorted by total cost.
Requires ClickHouse backend (storage.mode: clickhouse) for live data.

Usage:
    langsight costs                    # last 24h
    langsight costs --window 7d        # last 7 days
    langsight costs --json             # JSON output for scripting
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.table import Table

from langsight.config import LangSightConfig, load_config
from langsight.costs.engine import CostEngine, load_cost_rules
from langsight.exceptions import ConfigError
from langsight.reliability.engine import ReliabilityEngine
from langsight.storage.factory import open_storage

console = Console()
err_console = Console(stderr=True)


@click.command("costs")
@click.option(
    "--config",
    "config_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Path to .langsight.yaml (auto-discovered if not set).",
)
@click.option(
    "--window",
    "-w",
    default="24h",
    show_default=True,
    help="Look-back window: 24h, 7d, 30d.",
)
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    help="Output as JSON.",
)
def costs(config_path: Path | None, window: str, output_json: bool) -> None:
    """Show MCP tool call cost attribution.

    Requires ClickHouse backend (storage.mode: clickhouse).
    Configure pricing rules in .langsight.yaml under costs.rules.
    """
    config = load_config(config_path)
    hours = _parse_window_hours(window)
    try:
        asyncio.run(_run(config, config_path, hours, output_json))
    except ConfigError as exc:
        err_console.print(f"[red]Storage not configured:[/red] {exc}")
        err_console.print(
            "[dim]costs requires ClickHouse + Postgres. "
            "Run [bold]docker compose up[/bold] to start the full stack.[/dim]"
        )
        sys.exit(1)


async def _run(
    config: LangSightConfig, config_path: Path | None, hours: int, output_json: bool
) -> None:
    async with await open_storage(config.storage) as storage:
        rules = load_cost_rules(config_path)
        reliability = ReliabilityEngine(storage)
        engine = CostEngine(reliability, rules=rules)
        entries = await engine.calculate(hours=hours)

    if not entries:
        if not output_json:
            err_console.print(
                "[yellow]No tool call data found.[/yellow]\n"
                "Switch to ClickHouse (storage.mode: clickhouse) and make sure\n"
                "the LangSight SDK or OTLP endpoint is sending spans."
            )
        else:
            click.echo(json.dumps([], indent=2))
        sys.exit(0)

    if output_json:
        click.echo(json.dumps([e.to_dict() for e in entries], indent=2))
        return

    _display_table(entries, hours)


def _display_table(entries: list[Any], hours: int) -> None:
    total = sum(e.total_cost_usd for e in entries)
    total_calls = sum(e.total_calls for e in entries)

    table = Table(
        title=f"MCP Tool Costs  [dim](last {hours}h — {total_calls:,} total calls)[/dim]",
        show_header=True,
        header_style="bold",
        border_style="dim",
    )
    table.add_column("Server", style="bold", min_width=18)
    table.add_column("Tool", min_width=16)
    table.add_column("Calls", justify="right", min_width=8)
    table.add_column("$/call", justify="right", min_width=8)
    table.add_column("Total cost", justify="right", min_width=12)

    for e in entries:
        table.add_row(
            e.server_name,
            e.tool_name,
            f"{e.total_calls:,}",
            f"${e.cost_per_call:.4f}",
            f"${e.total_cost_usd:.4f}",
        )

    console.print(table)
    console.print(f"\n[bold]Total: ${total:.4f}[/bold]  over {hours}h\n")


def _parse_window_hours(window: str) -> int:
    w = window.strip().lower()
    if w.endswith("d"):
        return int(w[:-1]) * 24
    if w.endswith("h"):
        return int(w[:-1])
    return int(w)
