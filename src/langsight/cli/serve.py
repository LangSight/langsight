from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console

from langsight.api.main import create_app
from langsight.config import load_config
from langsight.exceptions import ConfigError

err_console = Console(stderr=True)


@click.command("serve")
@click.option(
    "--host",
    default="0.0.0.0",
    show_default=True,
    help="Host to bind to.",
)
@click.option(
    "--port",
    "-p",
    default=8000,
    show_default=True,
    help="Port to listen on.",
)
@click.option(
    "--config",
    "config_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Path to .langsight.yaml (auto-discovered if not set).",
)
@click.option(
    "--reload",
    is_flag=True,
    help="Enable auto-reload (development only).",
)
def serve(
    host: str,
    port: int,
    config_path: Path | None,
    reload: bool,
) -> None:
    """Start the LangSight REST API server.

    Serves the FastAPI application with full documentation at /docs.
    Requires ClickHouse + Postgres — run docker compose up first.
    """
    import asyncio

    import uvicorn

    # Validate storage config before starting uvicorn to give a clear error
    # instead of a deep stack trace from inside the FastAPI lifespan.
    config = load_config(config_path)
    from langsight.storage.factory import open_storage

    async def _check_storage() -> None:
        async with await open_storage(config.storage):
            pass

    try:
        asyncio.run(_check_storage())
    except ConfigError as exc:
        err_console.print(f"[red]Storage not configured:[/red] {exc}")
        err_console.print(
            "[dim]serve requires ClickHouse + Postgres. "
            "Run [bold]docker compose up[/bold] to start the full stack.[/dim]"
        )
        sys.exit(1)

    app = create_app(config_path=config_path)
    click.echo(f"Starting LangSight API on http://{host}:{port}")
    click.echo(f"Docs: http://{'localhost' if host == '0.0.0.0' else host}:{port}/docs")
    uvicorn.run(app, host=host, port=port, reload=reload)
