from __future__ import annotations

import asyncio
import hashlib
import inspect

import structlog
from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader

from langsight.config import LangSightConfig
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
        logger.warning("api.auth.missing_key", path=str(request.url.path))
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

    logger.warning("api.auth.invalid_key", path=str(request.url.path))
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Invalid API key",
    )


# Convenience alias — use as `dependencies=[Depends(require_auth)]` on routers
require_auth = Depends(verify_api_key)
