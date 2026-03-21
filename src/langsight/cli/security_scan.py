from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.table import Table

from langsight.cli._storage import try_open_storage
from langsight.config import load_config
from langsight.security.models import ScanResult, Severity
from langsight.security.scanner import SecurityScanner

console = Console()
err_console = Console(stderr=True)

_SEVERITY_STYLE = {
    Severity.CRITICAL: "[bold red]CRITICAL[/bold red]",
    Severity.HIGH: "[red]HIGH[/red]",
    Severity.MEDIUM: "[yellow]MEDIUM[/yellow]",
    Severity.LOW: "[dim]LOW[/dim]",
    Severity.INFO: "[dim]INFO[/dim]",
}


@click.command("security-scan")
@click.option(
    "--config",
    "config_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Path to .langsight.yaml (auto-discovered if not set).",
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
    help="CI mode — exit 1 if any CRITICAL or HIGH findings.",
)
def security_scan(config_path: Path | None, output_json: bool, ci: bool) -> None:
    """Scan MCP servers for security vulnerabilities.

    Checks: OWASP MCP Top 10, tool poisoning / prompt injection, CVEs.
    """
    config = load_config(config_path)

    if not config.servers:
        err_console.print("[yellow]No MCP servers configured.[/yellow]")
        err_console.print("Run [bold]langsight init[/bold] to get started.")
        sys.exit(1)

    async def _run() -> list[ScanResult]:
        storage = await try_open_storage(config)
        try:
            scanner = SecurityScanner(storage=storage)
            return await scanner.scan_many(config.servers)
        finally:
            if storage:
                await storage.close()

    results = asyncio.run(_run())

    if output_json:
        click.echo(json.dumps(_results_to_json(results), indent=2))
    else:
        _display_results(results)

    # CI mode: exit 1 on CRITICAL or HIGH findings
    if ci:
        has_critical_or_high = any(
            f.severity in (Severity.CRITICAL, Severity.HIGH) for r in results for f in r.findings
        )
        if has_critical_or_high:
            sys.exit(1)


def _display_results(results: list[ScanResult]) -> None:
    total_findings = sum(len(r.findings) for r in results)
    clean = sum(1 for r in results if r.is_clean)

    table = Table(
        title=(
            f"Security Scan Results  "
            f"[dim]({len(results)} server{'s' if len(results) != 1 else ''}, "
            f"{total_findings} finding{'s' if total_findings != 1 else ''})[/dim]"
        ),
        show_header=True,
        header_style="bold",
        border_style="dim",
    )
    table.add_column("Severity", min_width=10)
    table.add_column("Server", style="bold", min_width=18)
    table.add_column("Category", min_width=14)
    table.add_column("Finding")
    table.add_column("Tool", style="dim", min_width=10)

    for result in results:
        if result.error:
            table.add_row(
                "[dim]ERROR[/dim]",
                result.server_name,
                "—",
                f"[red]{result.error}[/red]",
                "—",
            )
            continue

        if result.is_clean:
            table.add_row(
                "[green]CLEAN[/green]",
                result.server_name,
                "—",
                "[dim]No findings[/dim]",
                "—",
            )
            continue

        for finding in result.findings_by_severity():
            table.add_row(
                _SEVERITY_STYLE.get(finding.severity, finding.severity.value),
                finding.server_name,
                finding.category,
                finding.title,
                finding.tool_name or "—",
            )

    console.print(table)

    if clean == len(results):
        console.print(f"\n[green]✓ All {len(results)} servers are clean[/green]\n")
    else:
        critical = sum(r.critical_count for r in results)
        high = sum(r.high_count for r in results)
        console.print(
            f"\n[dim]{clean}/{len(results)} servers clean — "
            f"{critical} critical, {high} high[/dim]\n"
        )


def _results_to_json(results: list[ScanResult]) -> list[dict[str, Any]]:
    output = []
    for r in results:
        output.append(
            {
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
        )
    return output
