"""
langsight sessions — agent session traces and multi-agent call trees.

Usage:
    langsight sessions                       # list recent sessions (last 24h)
    langsight sessions --window 7d           # last 7 days
    langsight sessions --agent support-agent # filter by agent name
    langsight sessions --id sess-abc123      # full trace for one session
    langsight sessions --json                # JSON output
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
from rich.tree import Tree

from langsight.config import LangSightConfig, load_config
from langsight.exceptions import ConfigError
from langsight.storage.factory import open_storage

console = Console()
err_console = Console(stderr=True)

_STATUS_STYLE = {
    "success": "[green]✓[/green]",
    "error": "[red]✗[/red]",
    "timeout": "[yellow]⏱[/yellow]",
}
_SPAN_TYPE_ICON = {
    "tool_call": "🔧",
    "agent": "🤖",
    "handoff": "→ ",
}


@click.command("sessions")
@click.option("--config", "config_path", type=click.Path(path_type=Path), default=None)
@click.option(
    "--window", "-w", default="24h", show_default=True, help="Look-back window: 30m, 2h, 7d."
)
@click.option("--agent", "agent_name", default=None, help="Filter by agent name.")
@click.option("--id", "session_id", default=None, help="Show full trace for a specific session ID.")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON.")
def sessions(
    config_path: Path | None,
    window: str,
    agent_name: str | None,
    session_id: str | None,
    output_json: bool,
) -> None:
    """List agent sessions or show a full multi-agent trace.

    Requires ClickHouse backend (storage.mode: clickhouse).
    """
    config = load_config(config_path)
    hours = _parse_hours(window)
    try:
        asyncio.run(_run(config, hours, agent_name, session_id, output_json))
    except ConfigError as exc:
        err_console.print(f"[red]Storage not configured:[/red] {exc}")
        err_console.print(
            "[dim]sessions requires ClickHouse + Postgres. "
            "Run [bold]docker compose up[/bold] to start the full stack.[/dim]"
        )
        sys.exit(1)


async def _run(
    config: LangSightConfig,
    hours: int,
    agent_name: str | None,
    session_id: str | None,
    output_json: bool,
) -> None:
    async with await open_storage(config.storage) as storage:
        if session_id:
            await _show_trace(storage, session_id, output_json)
        else:
            await _list_sessions(storage, hours, agent_name, output_json)


# ---------------------------------------------------------------------------
# Session list
# ---------------------------------------------------------------------------


async def _list_sessions(
    storage: object,
    hours: int,
    agent_name: str | None,
    output_json: bool,
) -> None:
    if not hasattr(storage, "get_agent_sessions"):
        err_console.print(
            "[yellow]No session data available.[/yellow]\n"
            "Switch to ClickHouse (storage.mode: clickhouse) and instrument\n"
            "your agents with the LangSight SDK to see sessions here."
        )
        sys.exit(0)

    rows = await storage.get_agent_sessions(hours=hours, agent_name=agent_name)

    if output_json:
        click.echo(json.dumps(rows, default=str, indent=2))
        return

    if not rows:
        console.print(f"[dim]No sessions in the last {hours}h.[/dim]")
        return

    table = Table(
        title=f"Agent Sessions  [dim](last {hours}h — {len(rows)} sessions)[/dim]",
        show_header=True,
        header_style="bold",
        border_style="dim",
    )
    table.add_column("Session", style="bold dim", min_width=14)
    table.add_column("Agent", style="bold", min_width=16)
    table.add_column("Calls", justify="right", min_width=6)
    table.add_column("Failed", justify="right", min_width=7)
    table.add_column("Duration", justify="right", min_width=9)
    table.add_column("Servers", style="dim")

    for r in rows:
        failed = int(r.get("failed_calls") or 0)
        calls = int(r.get("tool_calls") or 0)
        failed_str = f"[red]{failed}[/red]" if failed else "[dim]0[/dim]"
        dur = r.get("duration_ms") or 0
        dur_str = f"{dur:.0f}ms" if dur < 2000 else f"{dur / 1000:.1f}s"

        servers = r.get("servers_used") or []
        servers_str = ", ".join(servers[:3])
        if len(servers) > 3:
            servers_str += f" +{len(servers) - 3}"

        short_id = str(r.get("session_id") or "")[:12]
        table.add_row(
            short_id,
            str(r.get("agent_name") or "—"),
            str(calls),
            failed_str,
            dur_str,
            servers_str,
        )

    console.print(table)
    console.print(
        "\n[dim]Use [bold]langsight sessions --id <session_id>[/bold] "
        "to see the full trace.[/dim]\n"
    )


# ---------------------------------------------------------------------------
# Trace view
# ---------------------------------------------------------------------------


async def _show_trace(
    storage: object,
    session_id: str,
    output_json: bool,
) -> None:
    if not hasattr(storage, "get_session_trace"):
        err_console.print("[yellow]Session traces require ClickHouse backend.[/yellow]")
        sys.exit(1)

    spans = await storage.get_session_trace(session_id)

    if not spans:
        err_console.print(f"[red]Session '{session_id}' not found.[/red]")
        sys.exit(1)

    if output_json:
        click.echo(json.dumps(spans, default=str, indent=2))
        return

    _render_trace(session_id, spans)


def _render_trace(session_id: str, spans: list[dict[str, Any]]) -> None:
    """Render spans as an indented tree in the terminal."""
    tool_spans = [s for s in spans if s.get("span_type") in ("tool_call", "node")]
    failed = sum(1 for s in tool_spans if s.get("status") != "success")
    total_ms = sum(float(s.get("latency_ms") or 0) for s in tool_spans)

    # Find root agent/session name
    agent_names = [s.get("agent_name") for s in spans if s.get("agent_name")]
    session_label = agent_names[0] if agent_names else "agent"

    console.print(
        f"\n[bold]Trace: {session_id[:16]}  ({session_label})[/bold]\n"
        f"[dim]{len(tool_spans)} tool calls · "
        f"{failed} failed · "
        f"{total_ms:.0f}ms total[/dim]\n"
    )

    # Build tree structure
    by_id = {s["span_id"]: dict(s) for s in spans}
    roots = [
        s for s in spans if not s.get("parent_span_id") or s.get("parent_span_id") not in by_id
    ]

    tree = Tree(f"[bold]{session_id[:16]}[/bold]")
    for root in roots:
        _add_tree_node(tree, root, by_id, spans)

    console.print(tree)
    console.print()


def _add_tree_node(
    parent: Tree,
    span: dict[str, Any],
    by_id: dict[str, Any],
    all_spans: list[dict[str, Any]],
) -> None:
    span_type = span.get("span_type", "tool_call")
    status = span.get("status", "success")
    icon = _SPAN_TYPE_ICON.get(span_type, "  ")
    status_icon = _STATUS_STYLE.get(status, "?")
    latency = span.get("latency_ms")
    lat_str = f"  [dim]{latency:.0f}ms[/dim]" if latency else ""
    error = span.get("error") or ""
    error_str = f"  [red dim]{error[:40]}[/red dim]" if error else ""

    if span_type == "handoff":
        label = f"{icon}[bold yellow]{span.get('tool_name', '')}[/bold yellow]  [dim]handoff[/dim]"
    elif span_type == "agent":
        label = (
            f"{icon}[bold cyan]{span.get('agent_name', span.get('server_name', ''))}[/bold cyan]"
            f"  [dim]{span.get('tool_name', '')}[/dim]"
        )
    else:
        label = (
            f"{icon}[dim]{span.get('server_name', '')}[/dim]"
            f"/[bold]{span.get('tool_name', '')}[/bold]"
            f"  {status_icon}{lat_str}{error_str}"
        )

    node = parent.add(label)

    # Add children
    children = [s for s in all_spans if s.get("parent_span_id") == span["span_id"]]
    for child in sorted(children, key=lambda s: s.get("started_at", "")):
        _add_tree_node(node, child, by_id, all_spans)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_hours(window: str) -> int:
    w = window.strip().lower()
    if w.endswith("d"):
        return int(w[:-1]) * 24
    if w.endswith("h"):
        return int(w[:-1])
    if w.endswith("m"):
        return max(1, int(w[:-1]) // 60)
    return int(w)
