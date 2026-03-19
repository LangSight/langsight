from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from langsight.api.audit import append_audit
from langsight.api.dependencies import get_session_user, get_storage, require_admin
from langsight.models import ApiKeyRecord, ApiKeyRole
from langsight.storage.base import StorageBackend

logger = structlog.get_logger()
router = APIRouter(prefix="/auth", tags=["auth"])

_KEY_BYTES = 32  # 256-bit key → 64 hex chars


# ── Request / response models ─────────────────────────────────────────────────


class CreateApiKeyRequest(BaseModel):
    name: str  # user-given label, e.g. "LibreChat production"
    role: ApiKeyRole = ApiKeyRole.ADMIN  # "admin" or "viewer"


class ApiKeyCreatedResponse(BaseModel):
    """Returned once on creation. The raw key is never stored — save it now."""

    id: str
    name: str
    key: str  # full raw key — shown ONCE
    key_prefix: str
    created_at: datetime


class ApiKeyResponse(BaseModel):
    """Safe representation — no raw key, no hash."""

    id: str
    name: str
    key_prefix: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None

    @classmethod
    def from_record(cls, r: ApiKeyRecord) -> ApiKeyResponse:
        return cls(
            id=r.id,
            name=r.name,
            key_prefix=r.key_prefix,
            created_at=r.created_at,
            last_used_at=r.last_used_at,
            revoked_at=r.revoked_at,
        )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post(
    "/api-keys",
    response_model=ApiKeyCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new API key",
)
async def create_api_key(
    body: CreateApiKeyRequest,
    request: Request,
    storage: StorageBackend = Depends(get_storage),
    _: None = Depends(require_admin),
) -> ApiKeyCreatedResponse:
    """Generate a new API key.  The raw key is returned **once** — store it safely."""
    if not body.name.strip():
        raise HTTPException(status_code=422, detail="Key name cannot be empty")

    raw_key = secrets.token_hex(_KEY_BYTES)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    key_prefix = raw_key[:8]
    key_id = uuid.uuid4().hex
    now = datetime.now(UTC)

    # Capture the owning user from the session (dashboard proxy) or API key caller.
    # This links the key to its creator for project membership checks.
    creator_user_id, _creator_role = get_session_user(request)

    record = ApiKeyRecord(
        id=key_id,
        name=body.name.strip(),
        key_prefix=key_prefix,
        key_hash=key_hash,
        role=body.role,
        user_id=creator_user_id,
        created_at=now,
    )

    if hasattr(storage, "create_api_key"):
        await storage.create_api_key(record)
    else:
        # Storage backend doesn't support API keys (e.g. ClickHouse read-only mode)
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Current storage backend does not support API key management",
        )

    client_ip = request.client.host if request.client else "unknown"
    logger.info("audit.api_key.created", id=key_id, name=record.name, client_ip=client_ip)
    append_audit(
        "api_key.created",
        creator_user_id,
        client_ip,
        {"key_id": key_id, "name": record.name, "role": body.role.value},
        storage=storage,
    )
    return ApiKeyCreatedResponse(
        id=key_id,
        name=record.name,
        key=raw_key,
        key_prefix=key_prefix,
        created_at=now,
    )


@router.get(
    "/api-keys",
    response_model=list[ApiKeyResponse],
    summary="List all API keys",
)
async def list_api_keys(
    storage: StorageBackend = Depends(get_storage),
    _: None = Depends(require_admin),
) -> list[ApiKeyResponse]:
    """Return all API keys (active and revoked)."""
    if not hasattr(storage, "list_api_keys"):
        return []
    records = await storage.list_api_keys()
    return [ApiKeyResponse.from_record(r) for r in records]


@router.delete(
    "/api-keys/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke an API key",
)
async def revoke_api_key(
    key_id: str,
    request: Request,
    storage: StorageBackend = Depends(get_storage),
    _: None = Depends(require_admin),
) -> None:
    """Revoke an API key immediately. Revoked keys cannot be un-revoked."""
    if not hasattr(storage, "revoke_api_key"):
        raise HTTPException(
            status_code=501, detail="Storage backend does not support key revocation"
        )

    found = await storage.revoke_api_key(key_id)
    if not found:
        raise HTTPException(status_code=404, detail="API key not found or already revoked")
    client_ip = request.client.host if request.client else "unknown"
    logger.info("audit.api_key.revoked", id=key_id, client_ip=client_ip)
    append_audit("api_key.revoked", None, client_ip, {"key_id": key_id}, storage=storage)
