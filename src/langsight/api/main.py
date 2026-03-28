from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path
from typing import Any, cast

import structlog
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from langsight.api.broadcast import SSEBroadcaster
from langsight.api.dependencies import require_admin, verify_api_key
from langsight.api.metrics import PrometheusMiddleware, metrics_router
from langsight.api.rate_limit import limiter  # single global instance
from langsight.api.routers import (
    agents,
    alerts_config,
    alerts_feed,
    auth,
    costs,
    health,
    lineage,
    live,
    monitoring,
    prevention_config,
    projects,
    reliability,
    security,
    servers,
    slos,
    traces,
    users,
)
from langsight.config import Settings, load_config
from langsight.storage.factory import open_storage

logger = structlog.get_logger()


class InstanceSettings(BaseModel):
    """Typed request body for PUT /api/settings."""

    redact_payloads: bool


try:
    _VERSION = _pkg_version("langsight")
except PackageNotFoundError:
    import tomllib

    _toml = tomllib.loads((Path(__file__).parents[3] / "pyproject.toml").read_text())
    _VERSION = _toml["project"]["version"]


_MODEL_PRICING_SEED: list[tuple[str, str, str, float, float, float, str]] = [
    (
        "anthropic",
        "claude-opus-4-6",
        "Claude Opus 4.6",
        15.00,
        75.00,
        1.50,
        "Public pricing 2026-03",
    ),
    (
        "anthropic",
        "claude-sonnet-4-6",
        "Claude Sonnet 4.6",
        3.00,
        15.00,
        0.30,
        "Public pricing 2026-03",
    ),
    (
        "anthropic",
        "claude-haiku-4-5-20251001",
        "Claude Haiku 4.5",
        0.80,
        4.00,
        0.08,
        "Public pricing 2026-03",
    ),
    ("openai", "gpt-4o", "GPT-4o", 2.50, 10.00, 0.00, "Public pricing 2026-03"),
    ("openai", "gpt-4o-mini", "GPT-4o Mini", 0.15, 0.60, 0.00, "Public pricing 2026-03"),
    ("openai", "o3", "o3", 10.00, 40.00, 0.00, "Public pricing 2026-03"),
    ("openai", "o3-mini", "o3-mini", 1.10, 4.40, 0.00, "Public pricing 2026-03"),
    ("google", "gemini-1.5-pro", "Gemini 1.5 Pro", 1.25, 5.00, 0.00, "Public pricing 2026-03"),
    ("google", "gemini-1.5-flash", "Gemini 1.5 Flash", 0.075, 0.30, 0.00, "Public pricing 2026-03"),
    ("google", "gemini-2.0-flash", "Gemini 2.0 Flash", 0.10, 0.40, 0.00, "Public pricing 2026-03"),
    (
        "google",
        "gemini-2.5-flash",
        "Gemini 2.5 Flash",
        0.15,
        0.60,
        0.0375,
        "Public pricing 2026-03",
    ),
    ("google", "gemini-2.5-pro", "Gemini 2.5 Pro", 1.25, 10.00, 0.31, "Public pricing 2026-03"),
    ("meta", "llama-3.1-70b", "Llama 3.1 70B", 0.00, 0.00, 0.00, "Self-hosted — no API cost"),
    ("meta", "llama-3.3-70b", "Llama 3.3 70B", 0.00, 0.00, 0.00, "Self-hosted — no API cost"),
    ("aws", "amazon.nova-pro-v1", "Amazon Nova Pro", 0.80, 3.20, 0.00, "Public pricing 2026-03"),
    ("aws", "amazon.nova-lite-v1", "Amazon Nova Lite", 0.06, 0.24, 0.00, "Public pricing 2026-03"),
]


async def _seed_model_pricing(storage: Any) -> None:
    """Seed model_pricing table with builtin models if empty."""
    import uuid
    from datetime import UTC, datetime

    from langsight.models import ModelPricing

    if not hasattr(storage, "list_model_pricing"):
        return
    try:
        existing = await storage.list_model_pricing()
        existing_ids = {e.model_id for e in existing}
        now = datetime.now(UTC)
        added = 0
        for provider, model_id, display_name, inp, out, cache, notes in _MODEL_PRICING_SEED:
            if model_id in existing_ids:
                continue  # already present — skip
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
            added += 1
        if added:
            logger.info("api.startup.model_pricing_seeded", count=added)
    except Exception as exc:  # noqa: BLE001
        logger.warning("api.startup.model_pricing_seed_error", error=str(exc))


async def _bootstrap_admin(storage: Any) -> str | None:
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

        admin_email = os.environ.get("LANGSIGHT_ADMIN_EMAIL", "").strip()
        admin_password = os.environ.get("LANGSIGHT_ADMIN_PASSWORD", "").strip()

        if not admin_email or not admin_password:
            logger.warning(
                "api.startup.no_admin",
                hint="Set LANGSIGHT_ADMIN_EMAIL and LANGSIGHT_ADMIN_PASSWORD to create the first admin",
            )
            return None

        _WEAK_PASSWORDS = {"admin", "password", "langsight", "changeme", "secret", "123456"}
        if len(admin_password) < 12 or admin_password.lower() in _WEAK_PASSWORDS:
            logger.error(
                "api.startup.weak_admin_password",
                hint="LANGSIGHT_ADMIN_PASSWORD must be at least 12 characters and not a common password",
            )
            raise ValueError(
                "LANGSIGHT_ADMIN_PASSWORD is too weak. "
                "Use at least 12 characters and avoid common passwords."
            )

        password_hash = bcrypt.hashpw(admin_password.encode(), bcrypt.gensalt(12)).decode()

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


async def _bootstrap_default_project(storage: Any, admin_user_id: str) -> None:
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


_SAMPLE_PROJECT_SLUG = "sample-project"


async def _bootstrap_sample_project(storage: Any, admin_user_id: str) -> None:
    """Create a 'Sample Project' with demo agent sessions on first run.

    The sample project is isolated from user-created projects — users can
    explore the demo data without mixing it with their own traces.
    Skipped if the sample project already exists or LANGSIGHT_SKIP_DEMO_SEED=1.
    """
    if not hasattr(storage, "get_project_by_slug") or not hasattr(storage, "create_project"):
        return

    try:
        existing = await storage.get_project_by_slug(_SAMPLE_PROJECT_SLUG)
        if existing:
            return  # already created on a previous startup

        import uuid
        from datetime import UTC, datetime

        from langsight.demo_seed import seed_demo_data
        from langsight.models import Project, ProjectMember, ProjectRole

        now = datetime.now(UTC)
        project = Project(
            id=uuid.uuid4().hex,
            name="Sample Project",
            slug=_SAMPLE_PROJECT_SLUG,
            created_by=admin_user_id,
            created_at=now,
        )
        await storage.create_project(project)
        await storage.add_member(
            ProjectMember(
                project_id=project.id,
                user_id=admin_user_id,
                role=ProjectRole.OWNER,
                added_by=admin_user_id,
                added_at=now,
            )
        )
        logger.info("api.startup.sample_project_created", project_id=project.id)

        await seed_demo_data(storage, project.id)

    except Exception as exc:  # noqa: BLE001
        logger.warning("api.startup.sample_project_error", error=str(exc))


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
        app.state.broadcaster = SSEBroadcaster()

        # Auth setup — store parsed keys on app state so the dep can read them
        api_keys = settings.parsed_api_keys()
        app.state.api_keys = api_keys
        # Dashboard URL — used to construct invite links that point to the UI, not the API
        app.state.dashboard_url = settings.dashboard_url
        # Trusted proxy networks — CIDRs whose X-User-* headers are trusted for session auth
        from langsight.api.dependencies import parse_trusted_proxy_networks

        app.state.trusted_proxy_networks = parse_trusted_proxy_networks(
            settings.trusted_proxy_cidrs
        )
        if api_keys:
            logger.info("api.startup.auth_enabled", key_count=len(api_keys))
        else:
            logger.warning("=" * 72)
            logger.warning("SECURITY WARNING: LangSight API is running WITHOUT authentication.")
            logger.warning("Any client that can reach this API has full read/write access.")
            logger.warning(
                "Set LANGSIGHT_API_KEYS=<key> or create API keys in the dashboard"
                " before exposing this service to a network."
            )
            logger.warning("=" * 72)

        # First-run bootstrap — create initial admin user and sample project
        await _seed_model_pricing(app.state.storage)
        admin_id = await _bootstrap_admin(app.state.storage)

        # Seed a "Sample Project" with demo agent sessions on first run
        await _bootstrap_sample_project(app.state.storage, admin_id or "system")

        logger.info(
            "api.startup",
            servers=len(app.state.config.servers),
        )

        # ── Embedded monitor loop ──────────────────────────────────────────
        # Start continuous health checks as a background task so users only
        # need ONE command: `langsight serve`.  The loop respects the same
        # config file and credentials as the CLI `langsight monitor`.
        # Disable by setting LANGSIGHT_MONITOR_ENABLED=false (e.g. if you
        # are running a separate `langsight monitor` daemon instead).
        monitor_task: asyncio.Task | None = None
        if settings.monitor_enabled and app.state.config.servers:
            from langsight.health.checker import HealthChecker

            _interval = settings.monitor_interval_seconds
            _checker = HealthChecker(
                storage=app.state.storage,
                project_id="",  # global — visible to all projects
            )
            _servers = app.state.config.servers

            async def _monitor_loop() -> None:
                logger.info(
                    "monitor.started",
                    servers=len(_servers),
                    interval_seconds=_interval,
                )
                while True:
                    try:
                        await _checker.check_many(_servers)
                    except Exception as exc:  # noqa: BLE001
                        logger.error("monitor.cycle_error", error=str(exc))
                    await asyncio.sleep(_interval)

            monitor_task = asyncio.create_task(_monitor_loop())
            logger.info(
                "monitor.embedded",
                servers=len(_servers),
                interval_seconds=_interval,
                note="disable with LANGSIGHT_MONITOR_ENABLED=false",
            )
        elif not app.state.config.servers:
            logger.info(
                "monitor.skipped",
                reason="no servers in config — run `langsight monitor` separately",
            )

        try:
            yield
        finally:
            if monitor_task:
                monitor_task.cancel()
                try:
                    await monitor_task
                except asyncio.CancelledError:
                    pass
            await app.state.storage.close()
            logger.info("api.shutdown")

    app = FastAPI(
        title="LangSight API",
        description=(
            "Open-source agent runtime reliability platform. "
            "Prevent loops, enforce budgets, monitor MCP health, detect security vulnerabilities."
        ),
        version=_VERSION,
        lifespan=lifespan,
        # Disable Swagger/ReDoc in production — set LANGSIGHT_ENV=development to enable.
        # Exposing API schema unauthenticated leaks endpoint names and parameter shapes.
        docs_url="/docs" if os.environ.get("LANGSIGHT_ENV") == "development" else None,
        redoc_url="/redoc" if os.environ.get("LANGSIGHT_ENV") == "development" else None,
    )

    # Prometheus metrics — request count + duration histograms
    app.add_middleware(PrometheusMiddleware)

    # Rate limiting — global 200/min default, per-route overrides where needed
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

    # Security headers — applied to every response
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import Response as StarletteResponse

    class SecurityHeadersMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next: Any) -> StarletteResponse:
            response: StarletteResponse = await call_next(request)
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["X-XSS-Protection"] = "1; mode=block"
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
            # Only add HSTS in production (behind HTTPS)
            if request.headers.get("X-Forwarded-Proto") == "https":
                response.headers["Strict-Transport-Security"] = (
                    "max-age=31536000; includeSubDomains"
                )
            return response

    app.add_middleware(SecurityHeadersMiddleware)

    # CORS — configurable via LANGSIGHT_CORS_ORIGINS env var
    _settings = Settings()
    cors_origins = _settings.parsed_cors_origins()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["GET", "POST", "DELETE", "PATCH", "PUT"],
        allow_headers=["Content-Type", "X-API-Key", "Authorization"],
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
    app.include_router(alerts_feed.router, prefix="/api", dependencies=_auth_dep)
    app.include_router(agents.router, prefix="/api", dependencies=_auth_dep)
    app.include_router(servers.router, prefix="/api", dependencies=_auth_dep)
    app.include_router(lineage.router, prefix="/api", dependencies=_auth_dep)
    app.include_router(costs.router, prefix="/api", dependencies=_auth_dep)
    app.include_router(health.router, prefix="/api", dependencies=_auth_dep)
    app.include_router(monitoring.router, prefix="/api", dependencies=_auth_dep)
    app.include_router(reliability.router, prefix="/api", dependencies=_auth_dep)
    app.include_router(security.router, prefix="/api", dependencies=_auth_dep)
    # prevention_config MUST be registered before projects — its /api/projects/prevention-config
    # route would otherwise be swallowed by /api/projects/{project_id} from the projects router.
    app.include_router(prevention_config.router, prefix="/api", dependencies=_auth_dep)
    app.include_router(projects.router, prefix="/api", dependencies=_auth_dep)
    app.include_router(slos.router, prefix="/api", dependencies=_auth_dep)
    app.include_router(traces.router, prefix="/api", dependencies=_auth_dep)
    # User management — admin-gated routes (list/invite/role/deactivate)
    app.include_router(users.router, prefix="/api", dependencies=_auth_dep)
    # Public user routes — no auth needed (login verify + accept-invite)
    app.include_router(users.public_router, prefix="/api")
    # Live SSE event stream — requires auth
    app.include_router(live.router, prefix="/api", dependencies=_auth_dep)
    # Prometheus metrics — no auth (scrapers need direct access)
    app.include_router(metrics_router)

    @app.get("/api/status", tags=["meta"])
    async def status() -> dict[str, Any]:
        """Public status probe — returns minimal info to avoid fingerprinting.

        Kept for backwards compatibility. Prefer /readiness for health checks.
        Sensitive fields (servers_configured, auth_enabled, storage_mode) were
        removed from the public response — they are only available via /readiness
        to authenticated callers.
        """
        return {"status": "ok", "version": _VERSION}

    @app.get("/api/liveness", tags=["meta"])
    async def liveness() -> dict[str, str]:
        """Liveness probe — is the process alive?

        Returns 200 immediately. Used by Docker/K8s to decide whether to
        restart the container. Does NOT check storage or dependencies.
        """
        return {"status": "alive"}

    @app.get("/api/readiness", tags=["meta"])
    async def readiness() -> JSONResponse:
        """Readiness probe — can the process serve traffic?

        Checks that storage is reachable. Returns 200 when ready,
        503 when storage is unavailable. Used by load balancers and K8s
        to decide whether to send traffic to this instance.
        """

        storage = getattr(app.state, "storage", None)
        storage_ok = False
        storage_detail: dict[str, str] = {}

        if storage is not None:
            if hasattr(storage, "ping"):
                # DualStorage: ping both Postgres and ClickHouse independently
                storage_detail = await storage.ping()
                storage_ok = all(v == "ok" for v in storage_detail.values())
            else:
                # Single-backend fallback
                try:
                    if hasattr(storage, "get_health_history"):
                        await storage.get_health_history("__probe__", limit=1)
                    storage_ok = True
                    storage_detail = {"storage": "ok"}
                except Exception as exc:  # noqa: BLE001
                    storage_detail = {"storage": f"error: {exc}"}
        else:
            storage_detail = {"storage": "error: storage not initialised"}

        body: dict[str, Any] = {
            "status": "ready" if storage_ok else "not_ready",
            "version": _VERSION,
            "storage": storage_detail,
            # auth_enabled and storage_mode intentionally omitted — they leak
            # deployment internals to unauthenticated callers.
        }
        if storage_ok:
            return JSONResponse(content=body, status_code=200)
        return JSONResponse(content=body, status_code=503)

    # ── Instance settings (global admin toggle for redact_payloads etc.) ──────

    @app.get(
        "/api/settings",
        tags=["settings"],
        dependencies=[Depends(verify_api_key)],
    )
    async def get_settings() -> dict[str, Any]:
        """Return global instance settings. Requires authentication."""
        storage = getattr(app.state, "storage", None)
        if storage and hasattr(storage, "get_instance_settings"):
            return cast(dict[str, Any], await storage.get_instance_settings())
        return {"redact_payloads": False}

    @app.put(
        "/api/settings",
        tags=["settings"],
        dependencies=[Depends(verify_api_key), Depends(require_admin)],
    )
    async def save_settings(body: InstanceSettings) -> dict[str, Any]:
        """Update global instance settings. Admin only."""
        storage = getattr(app.state, "storage", None)
        if storage and hasattr(storage, "save_instance_settings"):
            await storage.save_instance_settings(body.model_dump())
            return cast(dict[str, Any], await storage.get_instance_settings())
        return {"redact_payloads": False}

    return app
