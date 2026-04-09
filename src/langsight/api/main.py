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
    investigate,
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


class AIProviderConfig(BaseModel):
    api_key: str = ""  # empty = keep existing; "*masked*" = no-op; otherwise update
    model: str = ""  # preferred model for RCA investigation
    base_url: str = ""  # for ollama / custom OpenAI-compat endpoints


class InstanceSettings(BaseModel):
    """Typed request body for PUT /api/settings."""

    redact_payloads: bool
    ai_providers: dict[str, AIProviderConfig] = {}


# Env-var names for each provider
_PROVIDER_ENV: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "ollama": "OLLAMA_BASE_URL",  # ollama uses base_url not api_key
}

_MASK = "*masked*"


def _mask_key(key: str) -> str:
    """Return a masked version of an API key for display."""
    if not key:
        return ""
    if len(key) <= 8:
        return _MASK
    return key[:4] + "..." + key[-4:]


def _apply_provider_envs(providers: dict[str, Any]) -> None:
    """Write saved provider config into os.environ so providers.py picks it up."""
    import os as _os

    for provider, cfg in providers.items():
        api_key = cfg.get("api_key", "") if isinstance(cfg, dict) else getattr(cfg, "api_key", "")
        base_url = (
            cfg.get("base_url", "") if isinstance(cfg, dict) else getattr(cfg, "base_url", "")
        )
        env_key = _PROVIDER_ENV.get(provider)
        if env_key and api_key and api_key != _MASK:
            _os.environ[env_key] = api_key
        if provider == "ollama" and base_url:
            _os.environ["OLLAMA_BASE_URL"] = base_url


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

    except ValueError:
        # Weak/invalid password — re-raise so startup fails loudly.
        # Swallowing this would let the server start without any admin user,
        # making the weak-password check a no-op.
        raise
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
        # ── Settings — resolved early so Redis check can use redis_url ─────────
        config = load_config(config_path)
        # Apply env var overrides (LANGSIGHT_STORAGE_MODE etc.) — used in Docker
        settings = Settings()
        config = config.model_copy(update={"storage": settings.apply_to_storage(config.storage)})

        # ── Multi-worker safety check ─────────────────────────────────────────
        # Without Redis, the rate limiter (slowapi) is in-memory. Running N
        # workers means each worker has an independent counter — effective
        # limit becomes limit×N, breaking brute-force and DoS protection.
        # With LANGSIGHT_REDIS_URL set, slowapi uses Redis storage so all
        # workers share a single counter. Hard-fail when Redis is absent and
        # workers > 1 so operators don't accidentally deploy a broken stack.
        _workers = int(os.environ.get("LANGSIGHT_WORKERS", "1"))
        if _workers > 1 and not settings.redis_url:
            raise RuntimeError(
                f"LANGSIGHT_WORKERS={_workers} requires LANGSIGHT_REDIS_URL to be set. "
                "Without Redis, each worker has an independent rate-limit counter and "
                "SSE events are not shared across workers. "
                "Set LANGSIGHT_REDIS_URL=redis://redis:6379 (see docker-compose --profile redis), "
                "or keep LANGSIGHT_WORKERS=1 for single-instance deployments."
            )

        app.state.config = config
        app.state.storage = await open_storage(app.state.config.storage)

        # ── Login-failures table — ensure it exists (idempotent) ─────────────
        from langsight.api.routers.users import _CREATE_LOGIN_FAILURES_TABLE, _get_raw_conn

        _lf_pool = _get_raw_conn(app.state.storage)
        if _lf_pool is not None:
            try:
                async with _lf_pool.acquire() as _conn:
                    await _conn.execute(_CREATE_LOGIN_FAILURES_TABLE)
                logger.info("api.startup.login_failures_table_ready")
            except Exception as _exc:  # noqa: BLE001
                logger.warning("api.startup.login_failures_table_error", error=str(_exc))

        # ── Load saved AI provider keys into os.environ ───────────────────────
        # Keys saved via PUT /api/settings are persisted in Postgres settings_json.
        # On startup, load them into os.environ so providers.py picks them up.
        try:
            if app.state.storage and hasattr(app.state.storage, "get_instance_settings"):
                _saved = await app.state.storage.get_instance_settings()
                _saved_providers = _saved.get("ai_providers") or {}
                if _saved_providers:
                    _apply_provider_envs(_saved_providers)
                    logger.info(
                        "api.startup.ai_providers_loaded",
                        providers=[
                            p
                            for p, c in _saved_providers.items()
                            if isinstance(c, dict) and c.get("api_key")
                        ],
                    )
        except Exception:  # noqa: BLE001
            pass  # non-fatal — env vars still work as fallback

        # ── Redis — optional, required for multi-worker mode ─────────────────
        from langsight.api.rate_limit import limiter as _rate_limiter
        from langsight.api.redis_client import close_redis_client, get_redis_client

        if settings.redis_url:
            try:
                app.state.redis = await get_redis_client(settings.redis_url)
                # Reconfigure rate limiter to use Redis storage
                _rate_limiter.reconfigure(settings.redis_url)
                logger.info("redis.rate_limiter_configured")
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(
                    f"LANGSIGHT_REDIS_URL is set but Redis is unreachable: {exc}. "
                    "Check that Redis is running and the URL is correct."
                ) from exc
        else:
            app.state.redis = None

        # ── SSE broadcaster — Redis-backed when available, in-memory otherwise
        from langsight.api.broadcast import RedisBroadcaster

        if settings.redis_url and app.state.redis is not None:
            app.state.broadcaster = RedisBroadcaster(app.state.redis)
            logger.info("sse.redis_broadcaster_active")
        else:
            app.state.broadcaster = SSEBroadcaster()

        # Auth setup — store parsed keys on app state so the dep can read them
        api_keys = settings.parsed_api_keys()
        app.state.api_keys = api_keys
        # auth_disabled: True = explicitly allow unauthenticated access.
        # Sourced from LangSightConfig (yaml) OR Settings (env var) — either is valid.
        app.state.auth_disabled = config.auth_disabled or settings.auth_disabled
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

        # Seed a "Sample Project" with demo agent sessions on first run.
        # Only attempt when admin_id is known — passing "system" would violate
        # the FK constraint project_members.user_id → users.id and silently
        # fail the entire bootstrap step.
        if admin_id:
            await _bootstrap_sample_project(app.state.storage, admin_id)

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
        monitor_task: asyncio.Task[Any] | None = None
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
            await close_redis_client()
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

    # Body size limit — reject requests larger than 10 MB to prevent OOM via
    # the trace ingestion endpoint. Single span batches should never approach
    # this limit; legitimate large payloads are handled by the field constraints
    # on ToolCallSpan (output_result, llm_input, llm_output capped at 128 KB).
    _MAX_BODY_SIZE = 10 * 1024 * 1024  # 10 MB

    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse as StarletteJSONResponse
    from starlette.responses import Response as StarletteResponse

    class BodySizeLimitMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next: Any) -> StarletteResponse:
            content_length = request.headers.get("content-length")
            if content_length and int(content_length) > _MAX_BODY_SIZE:
                return StarletteJSONResponse(
                    status_code=413,
                    content={
                        "detail": f"Payload too large (max {_MAX_BODY_SIZE // 1024 // 1024} MB)"
                    },
                )
            return await call_next(request)

    app.add_middleware(BodySizeLimitMiddleware)

    # Security headers — applied to every response
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
    app.include_router(investigate.router, prefix="/api", dependencies=_auth_dep)
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
                except Exception:  # noqa: BLE001
                    # Do not expose error details — connection strings, hostnames,
                    # and credentials may appear in exception messages.
                    storage_detail = {"storage": "error"}
        else:
            storage_detail = {"storage": "error"}

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
        import os as _os

        storage = getattr(app.state, "storage", None)
        base: dict[str, Any] = {"redact_payloads": False}
        if storage and hasattr(storage, "get_instance_settings"):
            base = cast(dict[str, Any], await storage.get_instance_settings())

        # Build ai_providers status — merge DB-saved config + live env vars
        # Keys from DB take precedence; env vars fill in gaps (e.g. set in .env)
        saved_providers: dict[str, Any] = base.pop("ai_providers", {}) or {}
        providers_out: dict[str, Any] = {}
        for provider, env_key in _PROVIDER_ENV.items():
            saved = saved_providers.get(provider, {})
            if isinstance(saved, dict):
                saved_key = saved.get("api_key", "")
                saved_model = saved.get("model", "")
                saved_url = saved.get("base_url", "")
            else:
                saved_key = saved_model = saved_url = ""
            # Prefer DB-saved key; fall back to env var
            live_key = saved_key or _os.environ.get(env_key, "")
            live_url = saved_url or (
                _os.environ.get("OLLAMA_BASE_URL", "") if provider == "ollama" else ""
            )
            providers_out[provider] = {
                "api_key": _mask_key(live_key),  # never return raw key
                "configured": bool(live_key or (provider == "ollama" and live_url)),
                "model": saved_model,
                "base_url": live_url if provider == "ollama" else "",
            }
        base["ai_providers"] = providers_out
        return base

    @app.put(
        "/api/settings",
        tags=["settings"],
        dependencies=[Depends(verify_api_key), Depends(require_admin)],
    )
    async def save_settings(body: InstanceSettings) -> dict[str, Any]:
        """Update global instance settings. Admin only."""
        storage = getattr(app.state, "storage", None)

        # Merge new provider config with existing saved config
        # (preserves keys for providers not included in the PUT body)
        existing: dict[str, Any] = {}
        if storage and hasattr(storage, "get_instance_settings"):
            existing = cast(dict[str, Any], await storage.get_instance_settings())
        saved_providers: dict[str, Any] = existing.get("ai_providers", {}) or {}

        merged_providers: dict[str, Any] = dict(saved_providers)
        for provider, cfg in body.ai_providers.items():
            prev = saved_providers.get(provider, {})
            prev_key = prev.get("api_key", "") if isinstance(prev, dict) else ""
            # If client sends "*masked*" or empty, keep existing key
            new_key = cfg.api_key if (cfg.api_key and cfg.api_key != _MASK) else prev_key
            merged_providers[provider] = {
                "api_key": new_key,
                "model": cfg.model or (prev.get("model", "") if isinstance(prev, dict) else ""),
                "base_url": cfg.base_url
                or (prev.get("base_url", "") if isinstance(prev, dict) else ""),
            }

        # Apply to os.environ immediately so current process uses them
        _apply_provider_envs(merged_providers)

        payload = body.model_dump()
        payload["ai_providers"] = merged_providers
        if storage and hasattr(storage, "save_instance_settings"):
            await storage.save_instance_settings(payload)
            result = cast(dict[str, Any], await storage.get_instance_settings())
            # Mask keys in response
            if "ai_providers" in result:
                for _p, cfg in result["ai_providers"].items():
                    if isinstance(cfg, dict) and cfg.get("api_key"):
                        cfg["api_key"] = _mask_key(cfg["api_key"])
            return result
        return {"redact_payloads": False, "ai_providers": {}}

    return app
