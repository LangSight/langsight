"""
langsight add — register an MCP server manually.

Supports both production HTTP servers and local stdio servers:

  # HTTP/remote (production)
  langsight add postgres-mcp --url https://postgres-mcp.internal.company.com/mcp
  langsight add github-mcp   --url https://github-mcp.prod.com/mcp \\
                             --header "Authorization=Bearer $TOKEN"

  # stdio (local / dev)
  langsight add local-db --command "uv run python server.py" \\
                         --args "--db-url postgresql://localhost/mydb"

Runs a connection test immediately. Appends to .langsight.yaml on success.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import click
import yaml
from rich.console import Console

console = Console()

_OUTPUT_PATH = Path(".langsight.yaml")


# ---------------------------------------------------------------------------
# Connection test
# ---------------------------------------------------------------------------


async def _test_connection(server_dict: dict[str, Any]) -> tuple[bool, str, int, list[str]]:
    """Try to connect and run initialize + tools/list.

    Returns (ok, error_msg, latency_ms, tool_names).
    """
    from langsight.health.checker import HealthChecker
    from langsight.models import MCPServer, TransportType

    try:
        mcp_server = MCPServer(
            name=server_dict["name"],
            transport=TransportType(server_dict.get("transport", "stdio")),
            command=server_dict.get("command") or None,
            args=server_dict.get("args", []),
            env=server_dict.get("env", {}),
            url=server_dict.get("url") or None,
            timeout_seconds=10,
        )
    except Exception as exc:
        return False, str(exc), 0, []

    checker = HealthChecker(storage=None)
    result = await checker.check(mcp_server)

    if result.status.value == "down":
        return False, result.error or "connection failed", 0, []

    tool_names = [t.name for t in result.tools] if result.tools else []
    latency = int(result.latency_ms or 0)
    return True, "", latency, tool_names


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------


def _load_config(path: Path) -> dict[str, Any]:
    if path.exists():
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {}


def _save_config(config: dict[str, Any], path: Path) -> None:
    path.write_text(yaml.dump(config, default_flow_style=False, sort_keys=False))


def _server_exists(config: dict[str, Any], name: str) -> bool:
    return any(s.get("name") == name for s in config.get("servers", []))


def _append_server(config: dict[str, Any], server: dict[str, Any]) -> None:
    config.setdefault("servers", []).append(server)


# ---------------------------------------------------------------------------
# CLI command
# ---------------------------------------------------------------------------


@click.command("add")
@click.argument("name")
@click.option(
    "--url",
    default=None,
    help="HTTP/SSE/StreamableHTTP URL (for remote servers).",
)
@click.option(
    "--command",
    default=None,
    help="Shell command to launch a stdio MCP server.",
)
@click.option(
    "--args",
    "extra_args",
    multiple=True,
    help="Arguments for the stdio command (repeatable).",
)
@click.option(
    "--env",
    "env_pairs",
    multiple=True,
    metavar="KEY=VALUE",
    help="Environment variables for stdio server (repeatable).",
)
@click.option(
    "--header",
    "headers",
    multiple=True,
    metavar="KEY=VALUE",
    help="HTTP headers for remote server auth (repeatable).",
)
@click.option(
    "--config",
    "-c",
    "config_path",
    type=click.Path(path_type=Path),
    default=None,
    help=f"Config file to update (default: {_OUTPUT_PATH}).",
)
@click.option(
    "--skip-check",
    is_flag=True,
    help="Skip the connection test.",
)
def add(
    name: str,
    url: str | None,
    command: str | None,
    extra_args: tuple[str, ...],
    env_pairs: tuple[str, ...],
    headers: tuple[str, ...],
    config_path: Path | None,
    skip_check: bool,
) -> None:
    """Register an MCP server and append it to .langsight.yaml.

    NAME is the server identifier used in health checks and dashboards.
    """
    if not url and not command:
        console.print("[red]Error:[/red] provide --url (HTTP server) or --command (stdio server).")
        sys.exit(1)

    output_path = config_path or _OUTPUT_PATH

    # ── Detect transport ──────────────────────────────────────────────────
    if url:
        import urllib.parse

        last = urllib.parse.urlparse(url).path.rstrip("/").split("/")[-1].lower()
        transport = "sse" if last == "sse" else "streamable_http"
    else:
        transport = "stdio"

    # ── Parse env / header pairs ──────────────────────────────────────────
    env: dict[str, str] = {}
    for pair in env_pairs:
        if "=" not in pair:
            console.print(f"[yellow]Warning:[/yellow] ignoring malformed env pair: {pair!r}")
            continue
        k, v = pair.split("=", 1)
        env[k.strip()] = v.strip()

    parsed_headers: dict[str, str] = {}
    for pair in headers:
        if "=" not in pair:
            console.print(f"[yellow]Warning:[/yellow] ignoring malformed header pair: {pair!r}")
            continue
        k, v = pair.split("=", 1)
        parsed_headers[k.strip()] = v.strip()

    # ── Build server dict ─────────────────────────────────────────────────
    server: dict[str, Any] = {"name": name, "transport": transport}
    if transport == "stdio":
        server["command"] = command
        if extra_args:
            server["args"] = list(extra_args)
        if env:
            server["env"] = env
    else:
        server["url"] = url
        if parsed_headers:
            server["headers"] = parsed_headers

    # ── Check for duplicate ───────────────────────────────────────────────
    config = _load_config(output_path)
    if _server_exists(config, name):
        console.print(f"[yellow]Warning:[/yellow] server '{name}' already exists in {output_path}.")
        if not click.confirm("Overwrite?", default=False):
            sys.exit(0)
        config["servers"] = [s for s in config.get("servers", []) if s.get("name") != name]

    # ── Connection test ───────────────────────────────────────────────────
    console.print(f"\nAdding [bold]{name}[/bold] ({transport})...")

    if not skip_check:
        console.print("  Testing connection...", end="")
        ok, error, latency_ms, tool_names = asyncio.run(_test_connection(server))

        if ok:
            console.print(f"  [green]✓[/green] Connected in {latency_ms}ms")
            if tool_names:
                console.print(
                    f"  [green]✓[/green] {len(tool_names)} tool(s): {', '.join(tool_names[:8])}"
                )
                if len(tool_names) > 8:
                    console.print(f"    … and {len(tool_names) - 8} more")
        else:
            console.print(f"  [red]✗[/red] Connection failed: {error}")
            if not click.confirm("\nAdd anyway?", default=False):
                sys.exit(1)
    else:
        console.print("  [dim]Skipping connection test.[/dim]")

    # ── Append and save ───────────────────────────────────────────────────
    _append_server(config, server)
    _save_config(config, output_path)

    console.print(f"\n[green]✓[/green] '{name}' added to [bold]{output_path}[/bold]")
    console.print(
        "\n[dim]Next steps:[/dim]\n"
        f"  langsight mcp-health {name}   # Check health\n"
        f"  langsight security-scan       # Security audit\n"
        f"  langsight monitor             # Start continuous monitoring\n"
    )
