from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from langsight.api.routers import health, security
from langsight.config import load_config
from langsight.storage.factory import open_storage

logger = structlog.get_logger()


def create_app(config_path: Path | None = None) -> FastAPI:
    """Application factory.

    Args:
        config_path: Optional path to .langsight.yaml. Auto-discovered when None.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        app.state.config = load_config(config_path)
        app.state.storage = await open_storage(app.state.config.storage)
        logger.info(
            "api.startup",
            servers=len(app.state.config.servers),
        )
        try:
            yield
        finally:
            await app.state.storage.close()
            logger.info("api.shutdown")

    app = FastAPI(
        title="LangSight API",
        description=(
            "Open-source MCP observability and security platform. "
            "Monitor server health, detect vulnerabilities, attribute agent failures."
        ),
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    app.include_router(health.router, prefix="/api")
    app.include_router(security.router, prefix="/api")

    @app.get("/api/status", tags=["meta"])
    async def status() -> dict:
        """API and storage health check."""
        return {
            "status": "ok",
            "version": "0.1.0",
            "servers_configured": len(app.state.config.servers),
        }

    return app
