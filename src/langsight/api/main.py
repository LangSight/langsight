from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from fastapi import Depends

from langsight.api.dependencies import verify_api_key
from langsight.api.routers import agents, auth, costs, health, reliability, security, slos, traces
from langsight.config import Settings, load_config
from langsight.storage.factory import open_storage

logger = structlog.get_logger()


def create_app(config_path: Path | None = None) -> FastAPI:
    """Application factory.

    Args:
        config_path: Optional path to .langsight.yaml. Auto-discovered when None.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        config = load_config(config_path)
        # Apply env var overrides (LANGSIGHT_STORAGE_MODE etc.) — used in Docker
        settings = Settings()
        config = config.model_copy(update={"storage": settings.apply_to_storage(config.storage)})
        app.state.config = config
        app.state.storage = await open_storage(app.state.config.storage)

        # Auth setup — store parsed keys on app state so the dep can read them
        api_keys = settings.parsed_api_keys()
        app.state.api_keys = api_keys
        if api_keys:
            logger.info("api.startup.auth_enabled", key_count=len(api_keys))
        else:
            logger.warning(
                "api.startup.auth_disabled",
                hint="Set LANGSIGHT_API_KEYS=<key1,key2> to enable authentication",
            )

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
            "Open-source agent observability platform. "
            "Trace every tool call, monitor MCP health, detect security vulnerabilities."
        ),
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS — configurable via LANGSIGHT_CORS_ORIGINS env var
    _settings = Settings()
    cors_origins = _settings.parsed_cors_origins()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["*"],
        allow_credentials=True,
    )

    # All data routers require authentication (dependency applied at router level)
    _auth_dep = [Depends(verify_api_key)]

    app.state.config_path = config_path
    # Auth router — key management endpoints, also require auth (except first-run bootstrap)
    app.include_router(auth.router, prefix="/api", dependencies=_auth_dep)
    app.include_router(agents.router, prefix="/api", dependencies=_auth_dep)
    app.include_router(costs.router, prefix="/api", dependencies=_auth_dep)
    app.include_router(health.router, prefix="/api", dependencies=_auth_dep)
    app.include_router(reliability.router, prefix="/api", dependencies=_auth_dep)
    app.include_router(security.router, prefix="/api", dependencies=_auth_dep)
    app.include_router(slos.router, prefix="/api", dependencies=_auth_dep)
    app.include_router(traces.router, prefix="/api", dependencies=_auth_dep)

    @app.get("/api/status", tags=["meta"])
    async def status() -> dict[str, Any]:
        """API and storage health check — unauthenticated, safe to expose."""
        return {
            "status": "ok",
            "version": "0.1.0",
            "servers_configured": len(app.state.config.servers),
            "auth_enabled": bool(getattr(app.state, "api_keys", [])),
        }

    return app
