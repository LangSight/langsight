"""langsight scan — zero-Docker MCP health + security scan.

Discovers MCP servers from Claude Desktop, Cursor, VS Code, and other
IDE configs, then runs health checks and security scans in parallel.

No Docker, Postgres, or ClickHouse required. Results are stored locally
in ~/.langsight/scan.db (SQLite) for history and drift tracking.

Usage examples:
    langsight scan                  # scan all auto-discovered servers
    langsight scan --fix            # show remediation steps per finding
    langsight scan --json           # machine-readable JSON output
    langsight scan --ci             # exit 1 on CRITICAL/HIGH (CI/CD gate)
    langsight scan --db ./my.db     # custom SQLite path
    langsight scan --config .langsight.yaml   # use existing config file
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
from rich import box

from langsight.health.checker import HealthChecker
from langsight.models import HealthCheckResult, MCPServer, ServerStatus
from langsight.security.models import ScanResult, Severity
from langsight.security.scanner import SecurityScanner
from langsight.storage.sqlite import DEFAULT_DB_PATH, SQLiteBackend

console = Console()
err_console = Console(stderr=True)

_STATUS_ICON: dict[ServerStatus, str] = {
    ServerStatus.UP:       "[green]✓ up[/green]",
    ServerStatus.DEGRADED: "[yellow]⚠ degraded[/yellow]",
    ServerStatus.DOWN:     "[red]✗ down[/red]",
    ServerStatus.STALE:    "[dim]~ stale[/dim]",
    ServerStatus.UNKNOWN:  "[dim]? unknown[/dim]",
}

_SEV_ICON: dict[Severity, str] = {
    Severity.CRITICAL: "[bold red]● CRITICAL[/bold red]",
    Severity.HIGH:     "[red]● HIGH[/red]",
    Severity.MEDIUM:   "[yellow]● MEDIUM[/yellow]",
    Severity.LOW:      "[dim]● LOW[/dim]",
    Severity.INFO:     "[dim]  INFO[/dim]",
}


def _dict_to_server(d: dict[str, Any]) -> MCPServer:
    """Convert a discovered-server dict to an MCPServer model."""
    return MCPServer(
        name=d["name"],
        transport=d.get("transport", "stdio"),
        url=d.get("url"),
        command=d.get("command"),
        args=d.get("args", []),
        env=d.get("env", {}),
        tags=d.get("tags", []),
    )


def _issue_cell(scan: ScanResult) -> str:
    if scan.error:
        return "[dim]scan error[/dim]"
    if scan.critical_count:
        return f"[bold red]{scan.critical_count} critical[/bold red]"
    if scan.high_count:
        return f"[red]{scan.high_count} high[/red]"
    medium = sum(1 for f in scan.findings if f.severity == Severity.MEDIUM)
    if medium:
        return f"[yellow]{medium} medium[/yellow]"
    low = sum(1 for f in scan.findings if f.severity == Severity.LOW)
    if low:
        return f"[dim]{low} low[/dim]"
    return "[green]✓ clean[/green]"


@click.command("scan")
@click.option(
    "--config",
    "config_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Path to .langsight.yaml. If omitted, servers are auto-discovered from IDE configs.",
)
@click.option(
    "--db",
    "db_path",
    type=click.Path(path_type=Path),
    default=None,
    help=f"SQLite database path for scan history (default: {DEFAULT_DB_PATH}).",
)
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    help="Output results as JSON (stdout).",
)
@click.option(
    "--ci",
    is_flag=True,
    help="CI mode — exit 1 if any CRITICAL or HIGH findings are found.",
)
@click.option(
    "--fix",
    is_flag=True,
    help="Show detailed remediation steps for each finding.",
)
def scan(
    config_path: Path | None,
    db_path: Path | None,
    output_json: bool,
    ci: bool,
    fix: bool,
) -> None:
    """Zero-Docker MCP health + security scan.

    Auto-discovers MCP servers from Claude Desktop, Cursor, VS Code,
    Windsurf, and other IDE configs, then runs health checks and
    security scans in parallel. No Docker or database required.

    Results are stored locally in ~/.langsight/scan.db for history
    and schema drift tracking across scans.
    """
    asyncio.run(_run_scan(config_path, db_path, output_json, ci, fix))


async def _run_scan(
    config_path: Path | None,
    db_path: Path | None,
    output_json: bool,
    ci: bool,
    fix: bool,
) -> None:
    # ── Resolve servers ───────────────────────────────────────────────────────
    servers: list[MCPServer]
    sources: list[tuple[str, int]] = []  # (source_name, count)

    if config_path or _langsight_yaml_exists():
        # Use existing .langsight.yaml
        from langsight.config import load_config
        try:
            cfg = load_config(config_path)
            servers = cfg.servers
            sources = [("config file", len(servers))]
        except Exception as exc:  # noqa: BLE001
            err_console.print(f"[red]Error loading config: {exc}[/red]")
            sys.exit(1)
    else:
        # Auto-discover from IDE configs
        from langsight.cli.init import _discover_servers  # internal reuse
        discovered = _discover_servers()
        if not discovered:
            console.print(
                "\n[yellow]No MCP servers found.[/yellow]\n"
                "LangSight looks for MCP servers in Claude Desktop, Cursor,\n"
                "VS Code, Windsurf, and other IDE configs.\n\n"
                "If you have a config file, run:\n"
                "  [bold]langsight init[/bold]       — interactive setup\n"
                "  [bold]langsight add <name>[/bold]  — add a server manually\n"
            )
            sys.exit(0)

        # Count by source, deduplicate servers
        source_counts: dict[str, int] = {}
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for d in discovered:
            src = d.get("_source", "unknown")
            source_counts[src] = source_counts.get(src, 0) + 1
            if d["name"] not in seen:
                seen.add(d["name"])
                unique.append(d)
        sources = sorted(source_counts.items(), key=lambda x: -x[1])
        servers = [_dict_to_server(d) for d in unique]

    if not servers:
        console.print("[yellow]No servers to scan.[/yellow]")
        sys.exit(0)

    # ── Open SQLite storage ───────────────────────────────────────────────────
    resolved_db = db_path or DEFAULT_DB_PATH
    storage = await SQLiteBackend.open(resolved_db)

    # ── Run health checks + security scan in parallel ─────────────────────────
    if not output_json:
        source_str = "  ·  ".join(f"{s} ({n})" for s, n in sources)
        console.print(
            f"\n[bold]LangSight Scan[/bold]  "
            f"[dim]{len(servers)} server{'s' if len(servers) != 1 else ''}"
            f"{f'  ·  {source_str}' if source_str else ''}[/dim]\n"
        )

    checker = HealthChecker(storage=storage)
    scanner = SecurityScanner(storage=storage)

    health_results, scan_results = await asyncio.gather(
        checker.check_many(servers),
        scanner.scan_many(servers),
    )

    await storage.close()

    # ── Build combined lookup ─────────────────────────────────────────────────
    health_by_name: dict[str, HealthCheckResult] = {r.server_name: r for r in health_results}
    scan_by_name: dict[str, ScanResult] = {r.server_name: r for r in scan_results}

    # ── JSON output ───────────────────────────────────────────────────────────
    if output_json:
        output = [
            {
                "server": s.name,
                "health": health_by_name[s.name].model_dump(mode="json") if s.name in health_by_name else None,
                "security": _scan_to_dict(scan_by_name[s.name]) if s.name in scan_by_name else None,
            }
            for s in servers
        ]
        click.echo(json.dumps(output, indent=2))
        _maybe_exit_ci(ci, scan_results)
        return

    # ── Rich table ────────────────────────────────────────────────────────────
    table = Table(box=box.SIMPLE_HEAD, show_edge=False, pad_edge=False)
    table.add_column("Server", style="bold", min_width=20)
    table.add_column("Status", min_width=14)
    table.add_column("Latency", justify="right", min_width=9)
    table.add_column("Tools", justify="right", min_width=6)
    table.add_column("Security")

    for server in servers:
        h = health_by_name.get(server.name)
        s = scan_by_name.get(server.name)
        status_str = _STATUS_ICON.get(h.status, h.status.value) if h else "[dim]—[/dim]"
        latency_str = f"{h.latency_ms:.0f}ms" if h and h.latency_ms is not None else "—"
        tools_str = str(h.tools_count) if h and h.tools_count else "—"
        issue_str = _issue_cell(s) if s else "—"
        table.add_row(server.name, status_str, latency_str, tools_str, issue_str)

    console.print(table)

    # ── Findings detail ───────────────────────────────────────────────────────
    all_findings = [
        (r.server_name, f)
        for r in scan_results
        for f in r.findings_by_severity()
    ]

    if all_findings:
        console.print()
        findings_table = Table(box=box.SIMPLE_HEAD, show_edge=False, pad_edge=False)
        findings_table.add_column("Severity", min_width=14)
        findings_table.add_column("Server", style="bold", min_width=20)
        findings_table.add_column("Category", min_width=14)
        findings_table.add_column("Finding")
        if fix:
            findings_table.add_column("Fix")

        for server_name, finding in all_findings:
            row = [
                _SEV_ICON.get(finding.severity, finding.severity.value),
                server_name,
                finding.category,
                finding.title,
            ]
            if fix:
                row.append(f"[dim]{finding.remediation}[/dim]")
            findings_table.add_row(*row)

        console.print(findings_table)
    else:
        console.print("[green]  ✓ No security findings[/green]\n")

    # ── Summary line ──────────────────────────────────────────────────────────
    n_up = sum(1 for r in health_results if r.status == ServerStatus.UP)
    n_down = sum(1 for r in health_results if r.status == ServerStatus.DOWN)
    n_crit = sum(r.critical_count for r in scan_results)
    n_high = sum(r.high_count for r in scan_results)
    n_medium = sum(
        sum(1 for f in r.findings if f.severity == Severity.MEDIUM) for r in scan_results
    )

    parts: list[str] = [f"[dim]{n_up}/{len(servers)} servers up[/dim]"]
    if n_crit:
        parts.append(f"[bold red]{n_crit} critical[/bold red]")
    if n_high:
        parts.append(f"[red]{n_high} high[/red]")
    if n_medium:
        parts.append(f"[yellow]{n_medium} medium[/yellow]")
    if not (n_crit or n_high or n_medium):
        parts.append("[green]all clean[/green]")

    console.print("  " + "  ·  ".join(parts))
    console.print(f"  [dim]Results saved to {resolved_db}[/dim]")

    if all_findings and not fix:
        console.print("  [dim]Run [bold]langsight scan --fix[/bold] for remediation steps[/dim]\n")
    else:
        console.print()

    _maybe_exit_ci(ci, scan_results)


def _maybe_exit_ci(ci: bool, scan_results: list[ScanResult]) -> None:
    if not ci:
        return
    has_high = any(
        f.severity in (Severity.CRITICAL, Severity.HIGH)
        for r in scan_results
        for f in r.findings
    )
    if has_high:
        sys.exit(1)


def _langsight_yaml_exists() -> bool:
    for candidate in [Path(".langsight.yaml"), Path(".langsight.yml")]:
        if candidate.exists():
            return True
    return False


def _scan_to_dict(r: ScanResult) -> dict[str, Any]:
    return {
        "server_name": r.server_name,
        "scanned_at": r.scanned_at.isoformat(),
        "error": r.error,
        "findings_count": len(r.findings),
        "critical_count": r.critical_count,
        "high_count": r.high_count,
        "findings": [
            {
                "severity": f.severity.value,
                "category": f.category,
                "title": f.title,
                "description": f.description,
                "remediation": f.remediation,
                "tool_name": f.tool_name,
                "cve_id": f.cve_id,
            }
            for f in r.findings_by_severity()
        ],
    }
