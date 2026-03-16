from __future__ import annotations

from pathlib import Path

import click

from langsight.api.main import create_app


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
    """
    import uvicorn

    app = create_app(config_path=config_path)
    click.echo(f"Starting LangSight API on http://{host}:{port}")
    click.echo(f"Docs: http://{'localhost' if host == '0.0.0.0' else host}:{port}/docs")
    uvicorn.run(app, host=host, port=port, reload=reload)
