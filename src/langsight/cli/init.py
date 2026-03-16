"""
langsight init — interactive setup wizard.

Auto-discovers MCP servers from:
  - Claude Desktop: ~/.config/claude/claude_desktop_config.json
  - Cursor:         ~/.cursor/mcp.json
  - VS Code:        ~/.vscode/mcp.json

Then generates a .langsight.yaml in the current directory.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
import yaml
from rich.console import Console
from rich.table import Table

console = Console()

# Known MCP config file locations and their display names
_MCP_CONFIG_SOURCES: list[tuple[str, Path]] = [
    ("Claude Desktop", Path("~/.config/claude/claude_desktop_config.json")),
    ("Cursor", Path("~/.cursor/mcp.json")),
    ("VS Code", Path("~/.vscode/mcp.json")),
]

_OUTPUT_PATH = Path(".langsight.yaml")


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
def init(
    output: Path | None,
    slack_webhook: str | None,
    yes: bool,
) -> None:
    """Auto-discover MCP servers and generate .langsight.yaml."""
    output_path = output or _OUTPUT_PATH

    console.print("\n[bold]LangSight Init[/bold] — scanning for MCP servers...\n")

    discovered = _discover_servers()

    if not discovered:
        console.print("[yellow]No MCP servers found in known config locations.[/yellow]")
        console.print(
            "Add servers manually to .langsight.yaml or specify config paths:\n"
            "  - ~/.config/claude/claude_desktop_config.json (Claude Desktop)\n"
            "  - ~/.cursor/mcp.json (Cursor)\n"
            "  - ~/.vscode/mcp.json (VS Code)\n"
        )
        sys.exit(1)

    _display_discovered(discovered)

    if not yes:
        include_all = click.confirm(f"\nInclude all {len(discovered)} server(s)?", default=True)
        if not include_all:
            console.print("[dim]Aborted.[/dim]")
            sys.exit(0)

    # Prompt for Slack webhook if not provided
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
    console.print(
        "\n[dim]Next steps:[/dim]\n"
        "  langsight mcp-health      # Check server health\n"
        "  langsight security-scan   # Run security audit\n"
        "  langsight monitor         # Start continuous monitoring\n"
    )


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def _discover_servers() -> list[dict]:
    """Scan known MCP config locations and return server dicts."""
    servers: list[dict] = []
    for source_name, raw_path in _MCP_CONFIG_SOURCES:
        path = raw_path.expanduser()
        if not path.exists():
            continue
        try:
            found = _parse_mcp_config(path, source_name)
            servers.extend(found)
            console.print(
                f"  [green]✓[/green] {source_name} ([dim]{path}[/dim]) — {len(found)} server(s)"
            )
        except Exception as exc:  # noqa: BLE001
            console.print(f"  [yellow]⚠[/yellow] {source_name} — parse error: {exc}")
    return servers


def _parse_mcp_config(path: Path, source: str) -> list[dict]:
    """Parse an MCP config JSON file and return server dicts."""
    raw = json.loads(path.read_text())
    mcp_servers = raw.get("mcpServers", {})
    servers: list[dict] = []
    for name, cfg in mcp_servers.items():
        server: dict = {"name": name, "source": source}
        if "command" in cfg:
            server["transport"] = "stdio"
            server["command"] = cfg["command"]
            if "args" in cfg:
                server["args"] = cfg["args"]
            if "env" in cfg:
                server["env"] = cfg["env"]
        elif "url" in cfg:
            url: str = cfg["url"]
            server["transport"] = "sse" if "sse" in url.lower() else "streamable_http"
            server["url"] = url
        else:
            server["transport"] = "stdio"
        servers.append(server)
    return servers


# ---------------------------------------------------------------------------
# Display + config generation
# ---------------------------------------------------------------------------


def _display_discovered(servers: list[dict]) -> None:
    table = Table(
        title=f"\nDiscovered {len(servers)} MCP server(s)",
        show_header=True,
        header_style="bold",
        border_style="dim",
    )
    table.add_column("#", justify="right", style="dim")
    table.add_column("Name", style="bold")
    table.add_column("Transport")
    table.add_column("Source", style="dim")

    for i, srv in enumerate(servers, 1):
        table.add_row(
            str(i),
            srv["name"],
            srv.get("transport", "stdio"),
            srv.get("source", "—"),
        )
    console.print(table)


def _build_config(servers: list[dict], slack_webhook: str | None) -> dict:
    """Build the .langsight.yaml config dict."""
    config: dict = {
        "servers": [
            {k: v for k, v in srv.items() if k not in ("source",) and v is not None}
            for srv in servers
        ]
    }
    if slack_webhook:
        config["alerts"] = {"slack_webhook": slack_webhook}
    return config


def _write_config(config: dict, path: Path) -> None:
    path.write_text(yaml.dump(config, default_flow_style=False, sort_keys=False))
