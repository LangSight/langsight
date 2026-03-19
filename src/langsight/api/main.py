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
from langsight.api.routers import agents, alerts_config, auth, costs, health, projects, reliability, security, slos, traces, users
from langsight.config import Settings, load_config
from langsight.storage.factory import open_storage

logger = structlog.get_logger()


_MODEL_PRICING_SEED: list[tuple[str, str, str, float, float, float, str]] = [
    ("anthropic", "claude-opus-4-6",           "Claude Opus 4.6",       15.00, 75.00, 1.50,  "Public pricing 2026-03"),
    ("anthropic", "claude-sonnet-4-6",         "Claude Sonnet 4.6",      3.00, 15.00, 0.30,  "Public pricing 2026-03"),
    ("anthropic", "claude-haiku-4-5-20251001", "Claude Haiku 4.5",       0.80,  4.00, 0.08,  "Public pricing 2026-03"),
    ("openai",    "gpt-4o",                    "GPT-4o",                  2.50, 10.00, 0.00,  "Public pricing 2026-03"),
    ("openai",    "gpt-4o-mini",               "GPT-4o Mini",             0.15,  0.60, 0.00,  "Public pricing 2026-03"),
    ("openai",    "o3",                        "o3",                     10.00, 40.00, 0.00,  "Public pricing 2026-03"),
    ("openai",    "o3-mini",                   "o3-mini",                 1.10,  4.40, 0.00,  "Public pricing 2026-03"),
    ("google",    "gemini-1.5-pro",            "Gemini 1.5 Pro",          1.25,  5.00, 0.00,  "Public pricing 2026-03"),
    ("google",    "gemini-1.5-flash",          "Gemini 1.5 Flash",        0.075, 0.30, 0.00,  "Public pricing 2026-03"),
    ("google",    "gemini-2.0-flash",          "Gemini 2.0 Flash",        0.10,  0.40, 0.00,  "Public pricing 2026-03"),
    ("meta",      "llama-3.1-70b",             "Llama 3.1 70B",           0.00,  0.00, 0.00,  "Self-hosted — no API cost"),
    ("meta",      "llama-3.3-70b",             "Llama 3.3 70B",           0.00,  0.00, 0.00,  "Self-hosted — no API cost"),
    ("aws",       "amazon.nova-pro-v1",        "Amazon Nova Pro",         0.80,  3.20, 0.00,  "Public pricing 2026-03"),
    ("aws",       "amazon.nova-lite-v1",       "Amazon Nova Lite",        0.06,  0.24, 0.00,  "Public pricing 2026-03"),
]


async def _seed_model_pricing(storage: object) -> None:
    """Seed model_pricing table with builtin models if empty."""
    import uuid
    from datetime import UTC, datetime

    from langsight.models import ModelPricing

    if not hasattr(storage, "list_model_pricing"):
        return
    try:
        existing = await storage.list_model_pricing()
        if existing:
            return  # already seeded
        now = datetime.now(UTC)
        for provider, model_id, display_name, inp, out, cache, notes in _MODEL_PRICING_SEED:
            entry = ModelPricing(
                id=uuid.uuid4().hex,
                provider=provider,
                model_id=model_id,
                display_name=display_name,
                input_per_1m_usd=inp,
                output_per_1m_usd=out,
                cache_read_per_1m_usd=cache,
                effective_from=now,
                notes=notes,
                is_custom=False,
            )
            await storage.create_model_pricing(entry)
        logger.info("api.startup.model_pricing_seeded", count=len(_MODEL_PRICING_SEED))
    except Exception as exc:  # noqa: BLE001
        logger.warning("api.startup.model_pricing_seed_error", error=str(exc))


async def _bootstrap_admin(storage: object) -> str | None:
    """Create the first admin user from env vars if no users exist.

    Returns the new admin's user id, or None if no bootstrap occurred.
    Only runs when LANGSIGHT_ADMIN_EMAIL and LANGSIGHT_ADMIN_PASSWORD are set
    AND no users exist in the database.
    """
    import os
    import uuid
    from datetime import UTC, datetime

    import bcrypt

    from langsight.models import User, UserRole

    if not hasattr(storage, "count_users"):
        return None

    try:
        count = await storage.count_users()
        if count > 0:
            return None  # users already exist — skip bootstrap

        admin_email    = os.environ.get("LANGSIGHT_ADMIN_EMAIL", "").strip()
        admin_password = os.environ.get("LANGSIGHT_ADMIN_PASSWORD", "").strip()

        if not admin_email or not admin_password:
            logger.warning(
                "api.startup.no_admin",
                hint="Set LANGSIGHT_ADMIN_EMAIL and LANGSIGHT_ADMIN_PASSWORD to create the first admin",
            )
            return None

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
        return admin.id

    except Exception as exc:  # noqa: BLE001
        logger.warning("api.startup.bootstrap_error", error=str(exc))
        return None


async def _bootstrap_default_project(storage: object, admin_user_id: str) -> None:
    """Create a default project and make the bootstrap admin its owner.

    Only runs when no projects exist. After the first project is created,
    this function is a no-op — all project management goes through the UI/API.
    """
    import uuid
    from datetime import UTC, datetime

    from langsight.models import Project, ProjectMember, ProjectRole

    if not hasattr(storage, "list_projects"):
        return

    try:
        projects = await storage.list_projects()
        if projects:
            return  # projects already exist — skip bootstrap

        now = datetime.now(UTC)
        project = Project(
            id=uuid.uuid4().hex,
            name="Default",
            slug="default",
            created_by=admin_user_id,
            created_at=now,
        )
        await storage.create_project(project)

        member = ProjectMember(
            project_id=project.id,
            user_id=admin_user_id,
            role=ProjectRole.OWNER,
            added_by=admin_user_id,
            added_at=now,
        )
        await storage.add_member(member)
        logger.info("api.startup.default_project_created", project_id=project.id)

    except Exception as exc:  # noqa: BLE001
        logger.warning("api.startup.project_bootstrap_error", error=str(exc))


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
        # Dashboard URL — used to construct invite links that point to the UI, not the API
        app.state.dashboard_url = settings.dashboard_url
        if api_keys:
            logger.info("api.startup.auth_enabled", key_count=len(api_keys))
        else:
            logger.warning(
                "api.startup.auth_disabled",
                hint="Set LANGSIGHT_API_KEYS=<key1,key2> to enable authentication",
            )

        # First-run bootstrap — create initial admin user and default project
        await _seed_model_pricing(app.state.storage)
        admin_id = await _bootstrap_admin(app.state.storage)
        if admin_id:
            await _bootstrap_default_project(app.state.storage, admin_id)

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

    # Security headers — applied to every response
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import Response as StarletteResponse

    class SecurityHeadersMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next: Any) -> StarletteResponse:
            response = await call_next(request)
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["X-XSS-Protection"] = "1; mode=block"
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
            # Only add HSTS in production (behind HTTPS)
            if request.headers.get("X-Forwarded-Proto") == "https":
                response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
            return response

    app.add_middleware(SecurityHeadersMiddleware)

    # CORS — configurable via LANGSIGHT_CORS_ORIGINS env var
    _settings = Settings()
    cors_origins = _settings.parsed_cors_origins()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["GET", "POST", "DELETE", "PATCH", "PUT"],
        allow_headers=["*"],
        allow_credentials=True,
    )

    # All data routers require authentication (dependency applied at router level)
    _auth_dep = [Depends(verify_api_key)]

    app.state.config_path = config_path
    # Seed alert_types with defaults so GET /api/alerts/config returns them immediately
    from langsight.api.routers.alerts_config import _DEFAULT_ALERT_TYPES
    app.state.alert_types = dict(_DEFAULT_ALERT_TYPES)

    # Auth router — key management endpoints, also require auth (except first-run bootstrap)
    app.include_router(auth.router, prefix="/api", dependencies=_auth_dep)
    app.include_router(alerts_config.router, prefix="/api", dependencies=_auth_dep)
    app.include_router(agents.router, prefix="/api", dependencies=_auth_dep)
    app.include_router(costs.router, prefix="/api", dependencies=_auth_dep)
    app.include_router(health.router, prefix="/api", dependencies=_auth_dep)
    app.include_router(reliability.router, prefix="/api", dependencies=_auth_dep)
    app.include_router(security.router, prefix="/api", dependencies=_auth_dep)
    app.include_router(projects.router, prefix="/api", dependencies=_auth_dep)
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
