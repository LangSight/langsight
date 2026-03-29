from __future__ import annotations

import sys

import click
import structlog

from langsight.cli.add import add
from langsight.cli.api_key import api_key
from langsight.cli.costs import costs
from langsight.cli.init import init
from langsight.cli.investigate import investigate
from langsight.cli.mcp_health import mcp_health
from langsight.cli.monitor import monitor
from langsight.cli.scan import scan
from langsight.cli.scorecard import scorecard
from langsight.cli.security_scan import security_scan
from langsight.cli.serve import serve
from langsight.cli.sessions import sessions

# Route all structlog output to stderr so --json flags produce clean stdout.
structlog.configure(logger_factory=structlog.PrintLoggerFactory(sys.stderr))


@click.group()
@click.version_option(version="0.10.0", prog_name="langsight")
def cli() -> None:
    """LangSight — agent runtime reliability platform.

    Trace every tool call your agents make, monitor MCP server health,
    detect security vulnerabilities, and attribute agent failures to
    their root cause.
    """


cli.add_command(scan)  # zero-Docker: auto-discover + health + security
cli.add_command(add)
cli.add_command(api_key)
cli.add_command(costs)
cli.add_command(init)
cli.add_command(sessions)
cli.add_command(investigate)
cli.add_command(mcp_health)
cli.add_command(monitor)
cli.add_command(scorecard)
cli.add_command(security_scan)
cli.add_command(serve)
