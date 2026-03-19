from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from fastapi import Depends

# Rate limiter — keyed by client IP
limiter = Limiter(key_func=get_remote_address)

from langsight.api.dependencies import verify_api_key
from langsight.api.routers import agents, auth, costs, health, reliability, security, slos, traces, users
from langsight.config import Settings, load_config
from langsight.storage.factory import open_storage

logger = structlog.get_logger()


async def _bootstrap_admin(storage: object) -> None:
    """Create the first admin user from env vars if no users exist.

    Only runs when LANGSIGHT_ADMIN_EMAIL and LANGSIGHT_ADMIN_PASSWORD are set
    AND no users exist in the database. After the first user is created,
    this function is a no-op — all user management goes through the UI/API.
    """
    import os
    import uuid
    from datetime import UTC, datetime

    import bcrypt

    from langsight.models import User, UserRole

    if not hasattr(storage, "count_users"):
        return  # SQLite/ClickHouse without user support

    try:
        count = await storage.count_users()
        if count > 0:
            return  # users already exist — skip bootstrap

        admin_email    = os.environ.get("LANGSIGHT_ADMIN_EMAIL", "").strip()
        admin_password = os.environ.get("LANGSIGHT_ADMIN_PASSWORD", "").strip()

        if not admin_email or not admin_password:
            logger.warning(
                "api.startup.no_admin",
                hint="Set LANGSIGHT_ADMIN_EMAIL and LANGSIGHT_ADMIN_PASSWORD to create the first admin",
            )
            return

        password_hash = bcrypt.hashpw(
            admin_password.encode(), bcrypt.gensalt(12)
        ).decode()

        admin = User(
            id=uuid.uuid4().hex,
            email=admin_email,
            password_hash=password_hash,
            role=UserRole.ADMIN,
            active=True,
            invited_by=None,
            created_at=datetime.now(UTC),
        )
        await storage.create_user(admin)
        logger.info("api.startup.admin_bootstrapped", email=admin_email)

    except Exception as exc:  # noqa: BLE001
        logger.warning("api.startup.bootstrap_error", error=str(exc))


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

        # First-run bootstrap — create initial admin user from env vars if no users exist
        await _bootstrap_admin(app.state.storage)

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

    # Rate limiting state — required by slowapi
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

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
    # User management — admin-gated routes (list/invite/role/deactivate)
    app.include_router(users.router, prefix="/api", dependencies=_auth_dep)
    # Public user routes — no auth needed (login verify + accept-invite)
    app.include_router(users.public_router, prefix="/api")

    @app.get("/api/status", tags=["meta"])
    async def status() -> dict[str, Any]:
        """Combined status — kept for backwards compatibility. Prefer /readiness."""
        return {
            "status": "ok",
            "version": "0.1.0",
            "servers_configured": len(app.state.config.servers),
            "auth_enabled": bool(getattr(app.state, "api_keys", [])),
        }

    @app.get("/api/liveness", tags=["meta"])
    async def liveness() -> dict[str, str]:
        """Liveness probe — is the process alive?

        Returns 200 immediately. Used by Docker/K8s to decide whether to
        restart the container. Does NOT check storage or dependencies.
        """
        return {"status": "alive"}

    @app.get("/api/readiness", tags=["meta"])
    async def readiness() -> dict[str, Any]:
        """Readiness probe — can the process serve traffic?

        Checks that storage is reachable. Returns 200 when ready,
        503 when storage is unavailable. Used by load balancers and K8s
        to decide whether to send traffic to this instance.
        """
        from fastapi import Response
        from fastapi.responses import JSONResponse

        storage = getattr(app.state, "storage", None)
        storage_ok = False
        storage_error: str | None = None

        if storage is not None:
            try:
                # Cheap check — just test the connection is alive
                if hasattr(storage, "get_health_history"):
                    await storage.get_health_history("__probe__", limit=1)
                storage_ok = True
            except Exception as exc:  # noqa: BLE001
                storage_error = str(exc)
        else:
            storage_error = "storage not initialised"

        body: dict[str, Any] = {
            "status": "ready" if storage_ok else "not_ready",
            "version": "0.1.0",
            "storage": "ok" if storage_ok else f"error: {storage_error}",
            "auth_enabled": bool(getattr(app.state, "api_keys", [])),
        }
        if storage_ok:
            return JSONResponse(content=body, status_code=200)
        return JSONResponse(content=body, status_code=503)

    return app
