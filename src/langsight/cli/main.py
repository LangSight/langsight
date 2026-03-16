from __future__ import annotations

import click

from langsight.cli.mcp_health import mcp_health


@click.group()
@click.version_option(version="0.1.0", prog_name="langsight")
def cli() -> None:
    """LangSight — MCP observability and security platform.

    Monitor MCP server health, detect security vulnerabilities,
    and attribute AI agent failures to their root cause.
    """


cli.add_command(mcp_health)
