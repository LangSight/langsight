from __future__ import annotations

import secrets

import click
from rich.console import Console
from rich.panel import Panel

console = Console()

_KEY_BYTES = 32  # 256 bits → 64-char hex string


@click.group(name="api-key")
def api_key() -> None:
    """Manage LangSight API keys."""


@api_key.command(name="generate")
@click.option(
    "--count",
    default=1,
    show_default=True,
    help="Number of API keys to generate.",
)
def generate(count: int) -> None:
    """Generate one or more random API keys.

    Add the keys to LANGSIGHT_API_KEYS (comma-separated) to enable
    authentication on the LangSight API.

    Example:

        export LANGSIGHT_API_KEYS=$(langsight api-key generate)

    Or for multiple keys:

        langsight api-key generate --count 3
    """
    keys = [secrets.token_hex(_KEY_BYTES) for _ in range(count)]

    if count == 1:
        # Single key — plain output so it's easy to pipe / export
        console.print(keys[0])
    else:
        console.print(
            Panel(
                "\n".join(keys),
                title=f"[bold]{count} Generated API Keys[/bold]",
                subtitle="Add to LANGSIGHT_API_KEYS (comma-separated)",
            )
        )
        console.print(
            f"\n[dim]LANGSIGHT_API_KEYS={','.join(keys)}[/dim]",
        )
