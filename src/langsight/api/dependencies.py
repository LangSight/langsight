from __future__ import annotations

import asyncio
import hashlib
import hmac
import inspect
import ipaddress
import time

import structlog
from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader

from langsight.config import LangSightConfig
from langsight.models import ApiKeyRole, Project, ProjectRole
from langsight.storage.base import StorageBackend

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Cached auth-enabled check — avoids querying list_api_keys() on every request
# ---------------------------------------------------------------------------
_HAS_DB_KEYS_CACHE: tuple[bool, float] = (False, 0.0)  # (value, expires_at)
_HAS_DB_KEYS_TTL = 30.0  # seconds
_HAS_DB_KEYS_LOCK = asyncio.Lock()


async def _has_db_keys(storage: StorageBackend) -> bool:
    """Check if any active API keys exist in the DB. Cached for 30 seconds.

    Thread-safe via asyncio.Lock — concurrent requests share one DB query
    instead of racing.
    """
    global _HAS_DB_KEYS_CACHE  # noqa: PLW0603
    # Fast path: check cache without lock (monotonic reads are safe)
    value, expires_at = _HAS_DB_KEYS_CACHE
    if time.monotonic() < expires_at:
        return value

    async with _HAS_DB_KEYS_LOCK:
        # Double-check after acquiring lock (another coroutine may have refreshed)
        value, expires_at = _HAS_DB_KEYS_CACHE
        if time.monotonic() < expires_at:
            return value

        list_fn = getattr(storage, "list_api_keys", None)
        if list_fn is None or not inspect.iscoroutinefunction(list_fn):
            return False
        try:
            db_keys = await list_fn()
            result = any(not k.is_revoked for k in db_keys)
        except Exception:  # noqa: BLE001
            # DB error: conservatively treat as auth-enabled (fail-closed)
            result = True
        _HAS_DB_KEYS_CACHE = (result, time.monotonic() + _HAS_DB_KEYS_TTL)
        return result


def invalidate_api_key_cache() -> None:
    """Call after creating/revoking an API key to bust the cache immediately."""
    global _HAS_DB_KEYS_CACHE  # noqa: PLW0603
    _HAS_DB_KEYS_CACHE = (False, 0.0)


# Header scheme — clients send:  X-API-Key: <key>
# SDK clients may send:          Authorization: Bearer <key>
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _read_api_key(request: Request, declared: str | None = None) -> str | None:
    """Resolve the API key for this request.

    Priority:
    1. `declared` — value already extracted by FastAPI from the X-API-Key header
    2. X-API-Key header (direct read, for code paths not using Security())
    3. Authorization: Bearer <key>  — SDK clients use this standard form

    Returns None when no key is present in any supported location.
    """
    if declared:
        return declared
    key = request.headers.get("X-API-Key")
    if key:
        return key
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:].strip()
        return token or None
    return None


# Default trusted proxy addresses — loopback only.
# Overridden at startup via LANGSIGHT_TRUSTED_PROXY_CIDRS env var to support
# Docker/K8s deployments where the dashboard runs in a separate container.
_DEFAULT_TRUSTED_PROXY_CIDRS = "127.0.0.1/32,::1/128"

_IPv4Network = ipaddress.IPv4Network
_IPv6Network = ipaddress.IPv6Network
_IPNetwork = _IPv4Network | _IPv6Network


def parse_trusted_proxy_networks(cidrs_str: str) -> list[_IPNetwork]:
    """Parse a comma-separated string of CIDRs/IPs into network objects.

    Invalid entries are logged and skipped rather than raising — a misconfigured
    CIDR should not prevent the API from starting.
    """
    # Only 0.0.0.0/0 (all IPv4) and ::/0 (all IPv6) trust the entire public
    # internet as a proxy — that enables session header spoofing from anywhere.
    # Reject those; warn (but allow) private ranges broader than /16 since
    # Docker (172.16.0.0/12) and K8s (10.0.0.0/8) use broad private CIDRs.
    networks: list[_IPNetwork] = []
    for raw in cidrs_str.split(","):
        cidr = raw.strip()
        if not cidr:
            continue
        try:
            net = ipaddress.ip_network(cidr, strict=False)
        except ValueError:
            logger.warning("config.invalid_trusted_proxy_cidr", cidr=cidr)
            continue
        if net.prefixlen == 0:
            logger.error(
                "config.trusted_proxy_cidr_internet_wide",
                cidr=cidr,
                hint="0.0.0.0/0 trusts the entire internet as a proxy — anyone can spoof X-User-Id headers. Use a specific CIDR.",
            )
            raise ValueError(
                f"LANGSIGHT_TRUSTED_PROXY_CIDRS: {cidr} trusts the entire internet. "
                "Specify the actual proxy IP or subnet (e.g. 172.16.0.0/12 for Docker)."
            )
        if net.prefixlen < 8:
            logger.warning(
                "config.trusted_proxy_cidr_very_broad",
                cidr=cidr,
                prefixlen=net.prefixlen,
                hint="This CIDR is very broad. Ensure it covers only your proxy infrastructure.",
            )
        networks.append(net)
    return networks


def _is_proxy_request(request: Request) -> bool:
    """Return True if the request originated from a trusted Next.js proxy.

    Trusted networks are loaded from app.state.trusted_proxy_networks (set at
    startup from LANGSIGHT_TRUSTED_PROXY_CIDRS). Falls back to loopback-only
    when app.state is not available (e.g. in unit tests).
    """
    client_host = request.client.host if request.client else ""
    if not client_host:
        return False

    # Resolve trusted networks from app state (configured at startup)
    trusted: list[_IPNetwork] | None = getattr(
        getattr(request, "app", None),
        "state",
        None,
    )
    trusted_nets: list[_IPNetwork] = getattr(
        trusted, "trusted_proxy_networks", None
    ) or parse_trusted_proxy_networks(_DEFAULT_TRUSTED_PROXY_CIDRS)

    try:
        addr = ipaddress.ip_address(client_host)
        return any(addr in net for net in trusted_nets)
    except ValueError:
        # client_host is a hostname (e.g. "localhost" in some test environments)
        return client_host == "localhost"


def _verify_proxy_hmac(request: Request, user_id: str, user_role: str) -> bool:
    """Verify the HMAC signature on proxy headers.

    When LANGSIGHT_PROXY_SECRET is set, the proxy signs X-User-Id and
    X-User-Role with a timestamp. This prevents header forgery even from
    within the trusted CIDR.

    SECURITY: Fails closed — returns False when LANGSIGHT_PROXY_SECRET is
    not configured. CIDR-only trust is no longer sufficient because any
    compromised container on the trusted subnet could forge X-User-* headers.
    Set LANGSIGHT_PROXY_SECRET on both the API and dashboard containers.

    Returns True only when:
    - The signature is valid and the timestamp is within 60 seconds.
    """
    import os

    secret = os.environ.get("LANGSIGHT_PROXY_SECRET", "")
    if not secret:
        logger.warning(
            "audit.proxy.hmac_not_configured",
            hint="LANGSIGHT_PROXY_SECRET is not set — session auth via proxy headers is disabled. "
            "Set the same secret on both API and dashboard containers.",
            client_ip=request.client.host if request.client else "unknown",
        )
        return False  # Fail closed — CIDR-only trust is not sufficient

    sig = request.headers.get("X-Proxy-Signature", "")
    ts = request.headers.get("X-Proxy-Timestamp", "")
    if not sig or not ts:
        logger.warning(
            "audit.proxy.missing_hmac",
            client_ip=request.client.host if request.client else "unknown",
        )
        return False

    # Check timestamp freshness (60-second window)
    try:
        ts_int = int(ts)
    except ValueError:
        return False
    now = int(time.time())
    if abs(now - ts_int) > 60:
        logger.warning("audit.proxy.stale_timestamp", delta=abs(now - ts_int))
        return False

    # Verify HMAC
    expected_payload = f"{user_id}:{user_role}:{ts}"
    expected_sig = hmac.new(secret.encode(), expected_payload.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected_sig)


def _get_session_user(request: Request) -> tuple[str | None, str | None]:
    """Extract (user_id, user_role) from X-User-* headers (proxy-only).

    SECURITY: Headers are ONLY trusted when:
    1. The request originates from a trusted proxy IP (CIDR check), AND
    2. The HMAC signature is valid (when LANGSIGHT_PROXY_SECRET is set).

    This is the single canonical implementation of the proxy-trust boundary —
    do not replicate this logic elsewhere; import get_session_user instead.

    These headers are injected by the Next.js proxy route after verifying
    the user's NextAuth session.
    """
    if not _is_proxy_request(request):
        return None, None
    user_id = request.headers.get("X-User-Id")
    user_role = request.headers.get("X-User-Role")
    if not user_id:
        return None, None

    # Verify HMAC signature when LANGSIGHT_PROXY_SECRET is configured
    if not _verify_proxy_hmac(request, user_id, user_role or ""):
        logger.warning(
            "audit.proxy.hmac_verification_failed",
            client_ip=request.client.host if request.client else "unknown",
        )
        return None, None

    return user_id or None, user_role or None


# Public alias — routers should import this name, not the private _get_session_user
get_session_user = _get_session_user


def get_storage(request: Request) -> StorageBackend:
    """Inject the storage backend from app state."""
    return request.app.state.storage  # type: ignore[no-any-return]


def get_config(request: Request) -> LangSightConfig:
    """Inject the loaded LangSight config from app state."""
    return request.app.state.config  # type: ignore[no-any-return]


async def verify_api_key(
    request: Request,
    api_key: str | None = Security(_api_key_header),
) -> None:
    """Validate the request is authenticated.

    Accepts (in priority order):
    1. X-User-Id + X-User-Role headers from the Next.js proxy (session auth)
    2. X-API-Key header — DB-stored hashed key or env-var bootstrap key
    3. Authorization: Bearer <key> — SDK / standard HTTP clients

    Auth is disabled entirely when no keys exist in DB or env vars.

    Raises HTTP 401 on missing key, HTTP 403 on invalid key.
    """
    # 1. Next.js proxy session headers (dashboard users)
    user_id, user_role = _get_session_user(request)
    # Resolve API key from X-API-Key or Authorization: Bearer (SDK compat)
    api_key = _read_api_key(request, api_key)
    if user_id and user_role:
        logger.debug(
            "audit.auth.session", user_id=user_id, role=user_role, path=str(request.url.path)
        )
        return

    env_keys: list[str] = getattr(request.app.state, "api_keys", [])
    storage: StorageBackend = request.app.state.storage

    # Check if any API keys are configured at all (cached — avoids DB query per request)
    has_env_keys = bool(env_keys)
    has_db_keys = await _has_db_keys(storage)

    if not has_env_keys and not has_db_keys:
        # Fail-closed: no keys configured anywhere.
        # auth_disabled can be set in two places:
        #   1. app.state.auth_disabled — set by create_app() lifespan from
        #      Settings (env var) or LangSightConfig (yaml).
        #   2. app.state.config.auth_disabled — fallback for test clients that
        #      bypass the lifespan but set app.state.config = load_config(...).
        # Both paths must check False before raising 401.
        state = getattr(getattr(request, "app", None), "state", None)
        auth_disabled = getattr(state, "auth_disabled", False)
        if not auth_disabled:
            cfg = getattr(state, "config", None)
            auth_disabled = bool(getattr(cfg, "auth_disabled", False))
        if not auth_disabled:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=(
                    "Authentication is required. Configure LANGSIGHT_API_KEYS "
                    "or create API keys via the dashboard. "
                    "To explicitly disable auth (local dev only): "
                    "set LANGSIGHT_AUTH_DISABLED=true."
                ),
                headers={"WWW-Authenticate": "ApiKey"},
            )
        return  # auth explicitly disabled

    if not api_key:
        logger.warning(
            "audit.auth.missing_key",
            path=str(request.url.path),
            client_ip=request.client.host if request.client else "unknown",
            method=request.method,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # 1. Check DB-stored keys (sha256 hash comparison — constant time via == on fixed-length hex)
    get_fn = getattr(storage, "get_api_key_by_hash", None)
    if get_fn is not None and inspect.iscoroutinefunction(get_fn):
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        record = await get_fn(key_hash)
        if record:
            if getattr(record, "is_expired", False):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="API key has expired",
                )
            # Update last_used_at in background (non-blocking)
            touch_fn = getattr(storage, "touch_api_key", None)
            if touch_fn is not None and inspect.iscoroutinefunction(touch_fn):
                asyncio.create_task(touch_fn(record.id))
            return

    # 2. Check env var keys — timing-safe comparison to prevent oracle attacks
    if any(hmac.compare_digest(api_key, k) for k in env_keys):
        return

    logger.warning(
        "audit.auth.invalid_key",
        path=str(request.url.path),
        client_ip=request.client.host if request.client else "unknown",
        method=request.method,
        key_prefix=api_key[:8] if api_key else None,
    )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Invalid API key",
    )


# Convenience alias — use as `dependencies=[Depends(require_auth)]` on routers
require_auth = Depends(verify_api_key)


async def get_current_user_id(
    request: Request,
    api_key: str | None = Security(_api_key_header),
) -> str | None:
    """Return the user_id for the current request.

    Sources (in priority order):
    1. X-User-Id header from Next.js proxy (dashboard session)
    2. API key lookup from DB

    Returns None when auth is disabled or the key has no user association.
    """
    # Session header from proxy (most reliable — user verified by NextAuth)
    user_id, _ = _get_session_user(request)
    if user_id:
        return user_id

    api_key = _read_api_key(request, api_key)
    if not api_key:
        return None

    storage: StorageBackend = request.app.state.storage
    get_fn = getattr(storage, "get_api_key_by_hash", None)
    if get_fn is None or not inspect.iscoroutinefunction(get_fn):
        return None

    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    try:
        record = await get_fn(key_hash)
        if record is None:
            return None
        # Prefer user_id (set since migration b3c9e1f2a047); fall back to key
        # record id for keys created before the migration.
        return str(record.user_id) if record.user_id else str(record.id)
    except Exception:  # noqa: BLE001
        return None


class ProjectAccess:
    """Result of project access check — project + caller's effective role."""

    def __init__(self, project: Project, role: ProjectRole, is_global_admin: bool = False) -> None:
        self.project = project
        self.role = role
        self.is_global_admin = is_global_admin

    @property
    def can_write(self) -> bool:
        return self.role in (ProjectRole.OWNER, ProjectRole.MEMBER) or self.is_global_admin

    @property
    def is_owner(self) -> bool:
        return self.role == ProjectRole.OWNER or self.is_global_admin


async def get_project_access(
    project_id: str,
    request: Request,
    api_key: str | None = Security(_api_key_header),
) -> ProjectAccess:
    """Dependency that returns ProjectAccess if the caller can see the project.

    Access rules:
    1. Global admin (env-var key OR db key with role=admin) → always allowed
    2. Project member → allowed with their membership role
    3. No membership → HTTP 404 (prevents project enumeration)

    Usage:
        @router.get("/{project_id}/sessions")
        async def list_sessions(access: ProjectAccess = Depends(get_project_access)):
            ...
    """
    storage: StorageBackend = request.app.state.storage
    env_keys: list[str] = getattr(request.app.state, "api_keys", [])

    if not hasattr(storage, "get_project"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Project management requires SQLite or PostgreSQL backend.",
        )

    project = await storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")

    # Auth disabled — treat as global admin.
    # Use the cached _has_db_keys() instead of calling list_api_keys() directly
    # so this per-request check is not a DB round-trip on every API call.
    has_any_keys = bool(env_keys) or await _has_db_keys(storage)
    if not has_any_keys:
        return ProjectAccess(project, ProjectRole.OWNER, is_global_admin=True)

    # Session headers from Next.js proxy
    user_id, user_role = _get_session_user(request)
    if user_id:
        if user_role == "admin":
            # Verify the user is still active + admin in the DB before
            # granting global admin access. Prevents stale JWTs from
            # retaining privileges after role change or deactivation.
            get_user_fn = getattr(storage, "get_user_by_id", None)
            if get_user_fn is not None and inspect.iscoroutinefunction(get_user_fn):
                try:
                    db_user = await get_user_fn(user_id)
                    if db_user is None or not db_user.active or db_user.role.value != "admin":
                        # Fall through to member check instead of granting admin
                        user_role = "viewer"
                    else:
                        return ProjectAccess(project, ProjectRole.OWNER, is_global_admin=True)
                except Exception:  # noqa: BLE001
                    pass  # fail-open for reads — fall through to member check
            else:
                return ProjectAccess(project, ProjectRole.OWNER, is_global_admin=True)
        # Check project membership by user_id
        member = await storage.get_member(project_id, user_id)
        if member:
            return ProjectAccess(project, member.role)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")

    api_key = _read_api_key(request, api_key)
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
        )

    # Env-var bootstrap keys are always global admin — timing-safe comparison
    if any(hmac.compare_digest(api_key, k) for k in env_keys):
        return ProjectAccess(project, ProjectRole.OWNER, is_global_admin=True)

    # DB key — single lookup: check admin role then project membership
    get_fn = getattr(storage, "get_api_key_by_hash", None)
    if get_fn and inspect.iscoroutinefunction(get_fn):
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        record = await get_fn(key_hash)
        if record:
            if record.role == ApiKeyRole.ADMIN:
                return ProjectAccess(project, ProjectRole.OWNER, is_global_admin=True)
            # Use user_id if populated (migration b3c9e1f2a047+); fall back to
            # key record id for keys created before the migration.
            principal_id = record.user_id or record.id
            member = await storage.get_member(project_id, principal_id)
            if member:
                return ProjectAccess(project, member.role)

    # No access — 404 to prevent enumeration
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")


async def get_active_project_id(
    request: Request,
    project_id: str | None = None,
) -> str | None:
    """Resolve the project_id to filter by for this request.

    Priority order (highest wins):
    1. API key's project_id — when a project-scoped key is used, always use
       its bound project. This is the "API key = project" pattern: set
       LANGSIGHT_API_KEY to a project-scoped key and all CLI health checks,
       monitor runs, and API calls are automatically scoped to that project.
    2. .langsight.yaml project_id field — explicit config-file override.
    3. project_id query parameter — for dashboard and direct API calls.
    4. Global admin with no project_id → None (sees all data).
    5. Non-admin without project_id → HTTP 400.
    """
    storage: StorageBackend = request.app.state.storage
    if not hasattr(storage, "list_members"):
        return project_id  # storage doesn't support projects — allow through

    env_keys: list[str] = getattr(request.app.state, "api_keys", [])

    # ── Resolve caller identity ───────────────────────────────────────────────
    user_id, user_role = _get_session_user(request)
    is_session_admin = bool(user_id and user_role == "admin")

    api_key = _read_api_key(request) or ""
    is_env_key_admin = any(hmac.compare_digest(api_key, k) for k in env_keys)

    is_admin = is_session_admin or is_env_key_admin

    # ── Determine whether auth is enabled (cached) ──────────────────────────
    has_env_keys = bool(env_keys)
    has_db_keys = await _has_db_keys(storage)
    auth_enabled = has_env_keys or has_db_keys

    # ── Priority 1: project-scoped API key ───────────────────────────────────
    # When the caller presents a DB key that has project_id set, use it
    # unconditionally. This implements "API key = project" — changing your
    # LANGSIGHT_API_KEY changes which project you write to, with no flags.
    if api_key and not is_env_key_admin:
        get_fn = getattr(storage, "get_api_key_by_hash", None)
        if get_fn and inspect.iscoroutinefunction(get_fn):
            key_hash = hashlib.sha256(api_key.encode()).hexdigest()
            record = await get_fn(key_hash)
            if record and record.project_id:
                return str(record.project_id)

    # ── Priority 2: .langsight.yaml project_id field ─────────────────────────
    config = getattr(getattr(request, "app", None), "state", None)
    config_obj = getattr(config, "config", None) if config else None
    cfg_project_id = getattr(config_obj, "project_id", None) if config_obj else None
    if isinstance(cfg_project_id, str) and cfg_project_id:
        return cfg_project_id

    # ── Handle missing project_id ─────────────────────────────────────────────
    if not project_id:
        if is_admin or not auth_enabled:
            return None
        # Authenticated non-admin must specify which project to query
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "project_id query parameter is required. "
                "Select a project or contact an admin to gain project access."
            ),
        )

    # ── project_id provided — validate membership ─────────────────────────────
    if is_admin or not auth_enabled:
        return project_id

    if user_id:
        # Non-admin session user — verify project membership
        member = await storage.get_member(project_id, user_id)
        if member:
            return project_id
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")

    # DB API key — check admin role or project membership
    get_fn = getattr(storage, "get_api_key_by_hash", None)
    if get_fn and inspect.iscoroutinefunction(get_fn) and api_key:
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        record = await get_fn(key_hash)
        if record:
            if record.role == ApiKeyRole.ADMIN:
                return project_id
            principal_id = record.user_id or record.id
            member = await storage.get_member(project_id, principal_id)
            if member:
                return project_id

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")


async def require_admin(
    request: Request,
    api_key: str | None = Security(_api_key_header),
) -> None:
    """Dependency that enforces admin role.

    Allows access when:
    - Auth is disabled (no keys configured) — local dev mode
    - Session header from proxy shows role=admin
    - Key is an env var key (bootstrap keys are always admin)
    - Key is a DB key with role="admin"

    Raises HTTP 403 when a viewer/member attempts a write operation.
    """
    # Check session header from proxy first
    user_id, user_role = _get_session_user(request)
    if user_id:
        if user_role != "admin":
            logger.warning(
                "audit.rbac.session_write_blocked",
                user_id=user_id,
                role=user_role,
                path=str(request.url.path),
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Write operations require admin role",
            )
        # SECURITY: Verify the session user is still active and still admin
        # in the DB. JWTs bake the role at login time — a demoted or deactivated
        # user keeps their old JWT until expiry. This DB check on admin-gated
        # routes closes that window.
        storage: StorageBackend = request.app.state.storage
        get_user_fn = getattr(storage, "get_user_by_id", None)
        if get_user_fn is not None and inspect.iscoroutinefunction(get_user_fn):
            try:
                db_user = await get_user_fn(user_id)
                if db_user is None or not db_user.active:
                    logger.warning(
                        "audit.rbac.deactivated_session",
                        user_id=user_id,
                        path=str(request.url.path),
                    )
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Account has been deactivated",
                    )
                if db_user.role.value != "admin":
                    logger.warning(
                        "audit.rbac.stale_admin_session",
                        user_id=user_id,
                        jwt_role="admin",
                        db_role=db_user.role.value,
                        path=str(request.url.path),
                    )
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Your role has been changed. Please log in again.",
                    )
            except HTTPException:
                raise
            except Exception:  # noqa: BLE001
                # DB error: fail-closed — deny rather than trust stale JWT
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Unable to verify session — try again",
                ) from None
        return

    env_keys: list[str] = getattr(request.app.state, "api_keys", [])
    storage: StorageBackend = request.app.state.storage

    has_env_keys = bool(env_keys)
    has_db_keys = await _has_db_keys(storage)

    if not has_env_keys and not has_db_keys:
        config_obj = getattr(getattr(request, "app", None), "state", None)
        cfg = getattr(config_obj, "config", None) if config_obj else None
        if cfg is not None and not getattr(cfg, "auth_disabled", False):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=(
                    "Authentication is required. Configure LANGSIGHT_API_KEYS "
                    "or create API keys via the dashboard."
                ),
                headers={"WWW-Authenticate": "ApiKey"},
            )
        return  # auth explicitly disabled or no config

    api_key = _read_api_key(request, api_key)
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # Env var keys are always admin (bootstrap) — timing-safe comparison
    if any(hmac.compare_digest(api_key, k) for k in env_keys):
        return

    # DB key — check role
    get_fn = getattr(storage, "get_api_key_by_hash", None)
    if get_fn is not None and inspect.iscoroutinefunction(get_fn):
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        record = await get_fn(key_hash)
        if record:
            if record.role == ApiKeyRole.VIEWER:
                logger.warning(
                    "audit.rbac.viewer_write_blocked",
                    path=str(request.url.path),
                    key_prefix=api_key[:8],
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Write operations require an admin API key",
                )
            return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Invalid API key",
    )
