"""
langsight init — interactive setup wizard.

Auto-discovers MCP servers from all major IDE and AI clients:
  - Claude Desktop, Cursor, VS Code, Windsurf
  - Claude Code, Gemini CLI, Kiro, Zed, Cline
  - Project-local configs (.cursor/mcp.json, .mcp.json, .vscode/mcp.json)

Then generates a .langsight.yaml and runs a first health check.
"""

from __future__ import annotations

import asyncio
import json
import os
import platform
import sys
import urllib.parse
from pathlib import Path
from typing import Any

import click
import yaml
from rich.console import Console
from rich.table import Table

console = Console()

_OUTPUT_PATH = Path(".langsight.yaml")


# ---------------------------------------------------------------------------
# Platform-aware config source registry
# ---------------------------------------------------------------------------


def _get_config_sources() -> list[tuple[str, Path, str]]:
    """Return (display_name, path, servers_key) for the current platform.

    servers_key is the top-level JSON key that holds the servers dict:
      "mcpServers"      — Claude Desktop, Cursor, Windsurf, Claude Code,
                          Gemini CLI, Kiro, Cline
      "servers"         — VS Code
      "context_servers" — Zed
    """
    is_mac = platform.system() == "Darwin"
    is_win = platform.system() == "Windows"
    appdata = Path(os.environ.get("APPDATA", "~"))
    userprofile = Path(os.environ.get("USERPROFILE", "~"))

    sources: list[tuple[str, Path, str]] = []

    # ── Claude Desktop ───────────────────────────────────────────────────────
    if is_mac:
        claude = Path("~/Library/Application Support/Claude/claude_desktop_config.json")
    elif is_win:
        claude = appdata / "Claude/claude_desktop_config.json"
    else:
        claude = Path("~/.config/Claude/claude_desktop_config.json")
    sources.append(("Claude Desktop", claude, "mcpServers"))

    # ── Cursor (global) ──────────────────────────────────────────────────────
    sources.append(("Cursor", Path("~/.cursor/mcp.json"), "mcpServers"))

    # ── VS Code (global) — uses "servers" key ────────────────────────────────
    if is_mac:
        vscode = Path("~/Library/Application Support/Code/User/mcp.json")
    elif is_win:
        vscode = appdata / "Code/User/mcp.json"
    else:
        vscode = Path("~/.config/Code/User/mcp.json")
    sources.append(("VS Code", vscode, "servers"))

    # ── Windsurf ─────────────────────────────────────────────────────────────
    if is_win:
        windsurf = userprofile / ".codeium/windsurf/mcp_config.json"
    else:
        windsurf = Path("~/.codeium/windsurf/mcp_config.json")
    sources.append(("Windsurf", windsurf, "mcpServers"))

    # ── Claude Code (global) ─────────────────────────────────────────────────
    sources.append(("Claude Code", Path("~/.claude.json"), "mcpServers"))

    # ── Gemini CLI ───────────────────────────────────────────────────────────
    sources.append(("Gemini CLI", Path("~/.gemini/settings.json"), "mcpServers"))

    # ── Kiro ─────────────────────────────────────────────────────────────────
    sources.append(("Kiro", Path("~/.kiro/settings/mcp.json"), "mcpServers"))

    # ── Zed — uses "context_servers" key ─────────────────────────────────────
    sources.append(("Zed", Path("~/.config/zed/settings.json"), "context_servers"))

    # ── Cline (VS Code extension globalStorage) ───────────────────────────────
    cline_rel = "Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json"
    if is_mac:
        cline = Path(f"~/Library/Application Support/{cline_rel}")
    elif is_win:
        cline = appdata / cline_rel
    else:
        cline = Path(f"~/.config/{cline_rel}")
    sources.append(("Cline", cline, "mcpServers"))

    # ── Project-local configs (relative to CWD) ───────────────────────────────
    sources.append(("Cursor (project)", Path(".cursor/mcp.json"), "mcpServers"))
    sources.append(("Claude Code (project)", Path(".mcp.json"), "mcpServers"))
    sources.append(("VS Code (project)", Path(".vscode/mcp.json"), "servers"))

    return sources


# ---------------------------------------------------------------------------
# Transport detection
# ---------------------------------------------------------------------------


def _detect_transport(cfg: dict[str, Any]) -> str:
    """Detect transport from a server config entry.

    stdio          — has a "command" key
    sse            — URL whose last path segment is exactly "sse"
    streamable_http — any other HTTP URL
    """
    if "command" in cfg:
        return "stdio"
    url = cfg.get("url", "")
    if not url:
        return "stdio"
    last = urllib.parse.urlparse(url).path.rstrip("/").split("/")[-1].lower()
    return "sse" if last == "sse" else "streamable_http"


# ---------------------------------------------------------------------------
# Config file parsing
# ---------------------------------------------------------------------------


def _parse_mcp_config(
    path: Path,
    source: str,
    key_name: str,
) -> list[dict[str, Any]]:
    """Parse one MCP config file and return normalised server dicts."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    servers_raw = raw.get(key_name, {})

    # Continue.dev stores servers as an array — normalise to dict
    if isinstance(servers_raw, list):
        servers_raw = {s["name"]: s for s in servers_raw if isinstance(s, dict) and "name" in s}

    if not isinstance(servers_raw, dict):
        return []

    servers: list[dict[str, Any]] = []
    for name, cfg in servers_raw.items():
        if not isinstance(cfg, dict):
            continue

        transport = _detect_transport(cfg)
        server: dict[str, Any] = {"name": name, "source": source, "transport": transport}

        if transport == "stdio":
            server["command"] = cfg.get("command", "")
            if cfg.get("args"):
                server["args"] = cfg["args"]
            if cfg.get("env"):
                server["env"] = cfg["env"]
        else:
            server["url"] = cfg.get("url", "")
            if cfg.get("headers"):
                server["headers"] = cfg["headers"]

        servers.append(server)

    return servers


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def _fingerprint(server: dict[str, Any]) -> str:
    """Stable dedup key — prevents the same server appearing from multiple clients."""
    if server.get("transport") == "stdio":
        cmd = server.get("command", "")
        args = "|".join(server.get("args", []))
        return f"stdio:{cmd}:{args}"
    return f"http:{server.get('url', '')}"


def _discover_servers() -> list[dict[str, Any]]:
    """Scan all known MCP config locations and return a deduplicated server list."""
    servers: list[dict[str, Any]] = []
    seen: set[str] = set()

    for source_name, raw_path, key_name in _get_config_sources():
        path = raw_path.expanduser() if str(raw_path).startswith("~") else raw_path.resolve()
        if not path.exists():
            continue

        try:
            found = _parse_mcp_config(path, source_name, key_name)
        except Exception as exc:  # noqa: BLE001
            console.print(f"  [yellow]⚠[/yellow]  {source_name} — parse error: {exc}")
            continue

        new_count = 0
        for s in found:
            fp = _fingerprint(s)
            if fp in seen:
                continue
            seen.add(fp)
            servers.append(s)
            new_count += 1

        if new_count:
            console.print(
                f"  [green]✓[/green]  {source_name} ([dim]{path}[/dim]) — {new_count} server(s)"
            )

    return servers


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------


def _display_discovered(servers: list[dict[str, Any]]) -> None:
    table = Table(
        title=f"Discovered {len(servers)} MCP server(s)",
        show_header=True,
        header_style="bold",
        border_style="dim",
    )
    table.add_column("#", justify="right", style="dim", width=3)
    table.add_column("Name", style="bold")
    table.add_column("Transport")
    table.add_column("Command / URL", style="dim", no_wrap=True, max_width=52)
    table.add_column("Source", style="dim")

    for i, srv in enumerate(servers, 1):
        detail = srv.get("command") or srv.get("url") or "—"
        if srv.get("args"):
            detail += " " + " ".join(str(a) for a in srv["args"])
        table.add_row(
            str(i),
            srv["name"],
            srv.get("transport", "stdio"),
            detail,
            srv.get("source", "—"),
        )
    console.print(table)


# ---------------------------------------------------------------------------
# First health check (stateless — no storage needed)
# ---------------------------------------------------------------------------


async def _run_health_check(servers: list[dict[str, Any]]) -> None:
    """Quick stateless health check against discovered servers."""
    from langsight.health.checker import HealthChecker
    from langsight.models import MCPServer, TransportType

    mcp_servers: list[MCPServer] = []
    for s in servers:
        try:
            mcp_servers.append(
                MCPServer(
                    name=s["name"],
                    transport=TransportType(s.get("transport", "stdio")),
                    command=s.get("command") or None,
                    args=s.get("args", []),
                    env=s.get("env", {}),
                    url=s.get("url") or None,
                    timeout_seconds=5,
                )
            )
        except Exception:  # noqa: BLE001
            pass

    if not mcp_servers:
        return

    console.print("\n[dim]Running first health check...[/dim]\n")
    checker = HealthChecker(storage=None)
    results = await checker.check_many(mcp_servers, global_timeout=30.0)

    for result in results:
        if result.status.value == "up":
            badge = "[green]UP[/green]"
        elif result.status.value == "degraded":
            badge = "[yellow]DEGRADED[/yellow]"
        else:
            badge = "[red]DOWN[/red]"

        latency = f"{result.latency_ms:.0f}ms" if result.latency_ms else "—"
        tools = f"{result.tools_count} tools" if result.tools_count else ""
        error = f"  [dim]{result.error}[/dim]" if result.error else ""
        console.print(f"  {badge:<22} {result.server_name:<28} {latency:<10} {tools}{error}")

    down = sum(1 for r in results if r.status.value == "down")
    degraded = sum(1 for r in results if r.status.value == "degraded")

    if down:
        console.print(
            f"\n  [red]{down} server(s) DOWN.[/red] "
            "Run [bold]langsight mcp-health[/bold] for details."
        )
    elif degraded:
        console.print(
            f"\n  [yellow]{degraded} server(s) DEGRADED.[/yellow] "
            "Run [bold]langsight mcp-health[/bold] for details."
        )
    else:
        console.print("\n  [green]All servers healthy.[/green]")


# ---------------------------------------------------------------------------
# Config generation
# ---------------------------------------------------------------------------


def _build_config(
    servers: list[dict[str, Any]],
    slack_webhook: str | None,
) -> dict[str, Any]:
    config: dict[str, Any] = {
        "servers": [
            {k: v for k, v in srv.items() if k != "source" and v is not None} for srv in servers
        ]
    }
    if slack_webhook:
        config["alerts"] = {"slack_webhook": slack_webhook}
    return config


def _write_config(config: dict[str, Any], path: Path) -> None:
    path.write_text(yaml.dump(config, default_flow_style=False, sort_keys=False))


# ---------------------------------------------------------------------------
# CLI command
# ---------------------------------------------------------------------------


@click.command("init")
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    default=None,
    help=f"Output path for config file (default: {_OUTPUT_PATH}).",
)
@click.option(
    "--slack-webhook",
    default=None,
    help="Slack webhook URL for alerts.",
)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    help="Skip confirmation prompts.",
)
@click.option(
    "--skip-check",
    is_flag=True,
    help="Skip the first health check after writing config.",
)
def init(
    output: Path | None,
    slack_webhook: str | None,
    yes: bool,
    skip_check: bool,
) -> None:
    """Auto-discover MCP servers and generate .langsight.yaml."""
    output_path = output or _OUTPUT_PATH

    console.print("\n[bold]LangSight Init[/bold] — scanning for MCP servers...\n")

    discovered = _discover_servers()

    if not discovered:
        console.print("[yellow]No MCP servers found in known config locations.[/yellow]")
        console.print(
            "\nAdd a server manually:\n"
            "  langsight add <name> --url https://my-mcp.example.com/mcp\n"
            "  langsight add <name> --command 'uv run server.py'\n"
        )
        sys.exit(1)

    console.print()
    _display_discovered(discovered)

    if not yes:
        include_all = click.confirm(f"\nInclude all {len(discovered)} server(s)?", default=True)
        if not include_all:
            console.print("[dim]Aborted.[/dim]")
            sys.exit(0)

    if not slack_webhook and not yes:
        slack_webhook = (
            click.prompt(
                "Slack webhook URL for alerts (leave blank to skip)",
                default="",
                show_default=False,
            )
            or None
        )

    config = _build_config(discovered, slack_webhook)
    _write_config(config, output_path)

    console.print(f"\n[green]✓[/green] Config written to [bold]{output_path}[/bold]")
    console.print(f"  {len(discovered)} MCP server(s) configured")
    if slack_webhook:
        console.print("  Slack alerts enabled")

    if not skip_check:
        asyncio.run(_run_health_check(discovered))

    console.print(
        "\n[dim]Next steps:[/dim]\n"
        "  langsight mcp-health      # Full health status + scorecard\n"
        "  langsight security-scan   # Security audit\n"
        "  langsight monitor         # Start continuous monitoring\n"
    )
