from __future__ import annotations

import asyncio
import hashlib
import hmac
import inspect
import ipaddress

import structlog
from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader

from langsight.config import LangSightConfig
from langsight.models import ApiKeyRole, Project, ProjectRole
from langsight.storage.base import StorageBackend

logger = structlog.get_logger()

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
    networks: list[_IPNetwork] = []
    for raw in cidrs_str.split(","):
        cidr = raw.strip()
        if not cidr:
            continue
        try:
            networks.append(ipaddress.ip_network(cidr, strict=False))
        except ValueError:
            logger.warning("config.invalid_trusted_proxy_cidr", cidr=cidr)
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


def _get_session_user(request: Request) -> tuple[str | None, str | None]:
    """Extract (user_id, user_role) from X-User-* headers (proxy-only).

    SECURITY: Headers are ONLY trusted when the request originates from
    _TRUSTED_PROXY_IPS. Any other caller receives (None, None). This is
    the single canonical implementation of the proxy-trust boundary —
    do not replicate this logic elsewhere; import get_session_user instead.

    These headers are injected by the Next.js proxy route after verifying
    the user's NextAuth session.
    """
    if not _is_proxy_request(request):
        return None, None
    user_id = request.headers.get("X-User-Id")
    user_role = request.headers.get("X-User-Role")
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

    # Check if any API keys are configured at all
    has_env_keys = bool(env_keys)
    has_db_keys = False
    list_fn = getattr(storage, "list_api_keys", None)
    if list_fn is not None and inspect.iscoroutinefunction(list_fn):
        try:
            db_keys = await list_fn()
            has_db_keys = any(not k.is_revoked for k in db_keys)
        except Exception:  # noqa: BLE001 — storage errors must not block auth
            pass

    if not has_env_keys and not has_db_keys:
        # Auth fully disabled — local dev mode (no keys configured at all)
        return

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
        # API keys don't have user_id yet — return key id as proxy
        # TODO: link api_keys.user_id in a future migration
        return record.id if record else None
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

    # Auth disabled — treat as global admin
    has_any_keys = bool(env_keys) or (
        hasattr(storage, "list_api_keys") and bool(await storage.list_api_keys())
    )
    if not has_any_keys:
        return ProjectAccess(project, ProjectRole.OWNER, is_global_admin=True)

    # Session headers from Next.js proxy
    user_id, user_role = _get_session_user(request)
    if user_id:
        if user_role == "admin":
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
            # Check project membership via key record id (until api_keys.user_id is linked)
            member = await storage.get_member(project_id, record.id)
            if member:
                return ProjectAccess(project, member.role)

    # No access — 404 to prevent enumeration
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")


async def get_active_project_id(
    request: Request,
    project_id: str | None = None,
) -> str | None:
    """Resolve the project_id to filter by for this request.

    - If project_id query param is provided, verify the caller is a member
      (or a global admin) and return it.
    - If not provided, return None → caller sees all data they have access to.
    - Global admins (session role=admin or env-var key) always pass through.
    """
    if not project_id:
        return None

    storage: StorageBackend = request.app.state.storage
    if not hasattr(storage, "list_members"):
        return project_id  # storage doesn't support projects — allow through

    env_keys: list[str] = getattr(request.app.state, "api_keys", [])

    # Session user from proxy
    user_id, user_role = _get_session_user(request)
    if user_id:
        if user_role == "admin":
            return project_id
        member = await storage.get_member(project_id, user_id)
        if member:
            return project_id
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")

    # Auth disabled — allow through only when NO keys exist anywhere (env or DB)
    has_env_keys = bool(env_keys)
    has_db_keys = False
    list_fn = getattr(storage, "list_api_keys", None)
    if list_fn is not None and inspect.iscoroutinefunction(list_fn):
        try:
            db_keys = await list_fn()
            has_db_keys = any(not k.is_revoked for k in db_keys)
        except Exception:  # noqa: BLE001
            pass
    if not has_env_keys and not has_db_keys:
        return project_id

    # Env-var key = global admin — timing-safe comparison (also accepts Bearer token)
    api_key = _read_api_key(request) or ""
    if any(hmac.compare_digest(api_key, k) for k in env_keys):
        return project_id

    # DB key — check admin role or project membership
    get_fn = getattr(storage, "get_api_key_by_hash", None)
    if get_fn and inspect.iscoroutinefunction(get_fn):
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        record = await get_fn(key_hash)
        if record:
            if record.role == ApiKeyRole.ADMIN:
                return project_id
            member = await storage.get_member(project_id, record.id)
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
        return

    env_keys: list[str] = getattr(request.app.state, "api_keys", [])
    storage: StorageBackend = request.app.state.storage

    # Auth disabled — allow everything
    has_env_keys = bool(env_keys)
    has_db_keys = False
    list_fn = getattr(storage, "list_api_keys", None)
    if list_fn is not None and inspect.iscoroutinefunction(list_fn):
        try:
            db_keys = await list_fn()
            has_db_keys = any(not k.is_revoked for k in db_keys)
        except Exception:  # noqa: BLE001
            pass

    if not has_env_keys and not has_db_keys:
        return  # auth disabled

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
