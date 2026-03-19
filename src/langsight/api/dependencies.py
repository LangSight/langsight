from __future__ import annotations

import asyncio
import hashlib
import inspect

import structlog
from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader

from langsight.config import LangSightConfig
from langsight.models import ApiKeyRole, Project, ProjectRole
from langsight.storage.base import StorageBackend

logger = structlog.get_logger()

# Header scheme — clients send:  X-API-Key: <key>
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


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
    """Validate the X-API-Key header.

    Lookup order:
    1. DB-stored keys (hashed, managed via UI) — preferred
    2. Env var keys LANGSIGHT_API_KEYS — fallback / bootstrap

    Auth is disabled entirely when no keys exist in either source.

    Raises HTTP 401 on missing key, HTTP 403 on invalid key.
    """
    env_keys: list[str] = getattr(request.app.state, "api_keys", [])
    storage: StorageBackend = request.app.state.storage

    # Check if any keys are configured at all
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
        # Auth fully disabled — local dev mode
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

    # 2. Check env var keys (plain comparison — env keys are trusted bootstrap keys)
    if api_key in env_keys:
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
    """Return the user_id associated with the current request's API key.

    Returns None when:
    - Auth is disabled (local dev)
    - The key is an env-var bootstrap key (no user association)
    - The key is not found

    Used to check project membership — env-var keys get global admin access.
    """
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

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
        )

    # Env-var bootstrap keys are always global admin
    if api_key in env_keys:
        return ProjectAccess(project, ProjectRole.OWNER, is_global_admin=True)

    # DB key — check global role first
    get_fn = getattr(storage, "get_api_key_by_hash", None)
    if get_fn and inspect.iscoroutinefunction(get_fn):
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        record = await get_fn(key_hash)
        if record and record.role == ApiKeyRole.ADMIN:
            return ProjectAccess(project, ProjectRole.OWNER, is_global_admin=True)

    # Check project membership
    # We use key_prefix as a proxy for user lookup until api_keys.user_id is added
    # For now: any authenticated non-admin user gets member access if they have a DB key
    # TODO: proper user_id linkage
    if get_fn and inspect.iscoroutinefunction(get_fn):
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        record = await get_fn(key_hash)
        if record:
            # Check explicit membership via user_id (when linked)
            member = await storage.get_member(project_id, record.id)
            if member:
                return ProjectAccess(project, member.role)

    # No access — 404 to prevent enumeration
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")


async def require_admin(
    request: Request,
    api_key: str | None = Security(_api_key_header),
) -> None:
    """Dependency that enforces admin role.

    Allows access when:
    - Auth is disabled (no keys configured) — local dev mode
    - Key is an env var key (bootstrap keys are always admin)
    - Key is a DB key with role="admin"

    Raises HTTP 403 when a viewer key attempts a write operation.
    """
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

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # Env var keys are always admin (bootstrap)
    if api_key in env_keys:
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
