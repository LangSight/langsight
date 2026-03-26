"""
User management and invite endpoints.

POST   /api/users/invite              — admin: generate invite link for a new user
POST   /api/users/accept-invite       — public: accept invite, set password, create account
GET    /api/users                     — admin: list all users
PATCH  /api/users/{user_id}/role      — admin: change user role
DELETE /api/users/{user_id}           — admin: deactivate user

POST   /api/users/verify              — dashboard auth: verify email+password, return user info
"""

from __future__ import annotations

import asyncio
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi import status as http_status
from pydantic import BaseModel, EmailStr, Field

from langsight.api.audit import append_audit
from langsight.api.dependencies import (
    _is_proxy_request,
    get_current_user_id,
    get_storage,
    require_admin,
)
from langsight.api.rate_limit import limiter
from langsight.models import InviteToken, User, UserRole
from langsight.storage.base import StorageBackend

logger = structlog.get_logger()


def _mask_email(email: str) -> str:
    """Mask an email for audit logs: 'alice@example.com' → 'a***@example.com'."""
    local, _, domain = email.partition("@")
    if not domain:
        return "***"
    return f"{local[0]}***@{domain}" if local else f"***@{domain}"


def _login_rate_key(request: Request) -> str:
    """Rate-limit key for /verify that respects X-Forwarded-For from trusted proxies.

    In production the dashboard container calls /verify on behalf of users.
    Without this, all users share one rate-limit bucket (the container IP).
    When the request comes from a trusted proxy, we use the first IP in
    X-Forwarded-For (the real client). Otherwise, fall back to client.host.
    """
    if _is_proxy_request(request):
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            # X-Forwarded-For: client, proxy1, proxy2 — first entry is the real client
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


router = APIRouter(prefix="/users", tags=["users"])
# Public endpoints — no API key required (used during login and invite acceptance)
public_router = APIRouter(prefix="/users", tags=["users"])

_INVITE_TTL_HOURS = 72
_BCRYPT_ROUNDS = 12


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class InviteRequest(BaseModel):
    email: EmailStr
    role: UserRole = UserRole.VIEWER


class InviteResponse(BaseModel):
    token: str
    email: str
    role: str
    expires_at: str
    invite_url: str  # full URL with token — admin shares this


class AcceptInviteRequest(BaseModel):
    # token_hex(32) always produces exactly 64 hex characters
    token: str = Field(..., min_length=64, max_length=64)
    password: str = Field(..., min_length=8, max_length=128, description="8–128 characters")


class UserResponse(BaseModel):
    id: str
    email: str
    role: str
    active: bool
    created_at: str
    last_login_at: str | None


class UpdateRoleRequest(BaseModel):
    role: UserRole


class VerifyRequest(BaseModel):
    email: EmailStr
    password: str


class VerifyResponse(BaseModel):
    id: str
    email: str
    role: str
    name: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _hash_password(password: str) -> str:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: bcrypt.hashpw(password.encode(), bcrypt.gensalt(_BCRYPT_ROUNDS)).decode(),
    )


async def _verify_password(password: str, hashed: str) -> bool:
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(None, bcrypt.checkpw, password.encode(), hashed.encode())
    except Exception:  # noqa: BLE001
        return False


def _user_to_response(u: User) -> UserResponse:
    return UserResponse(
        id=u.id,
        email=u.email,
        role=u.role.value,
        active=u.active,
        created_at=u.created_at.isoformat(),
        last_login_at=u.last_login_at.isoformat() if u.last_login_at else None,
    )


def _require_user_storage(storage: StorageBackend) -> None:
    if not hasattr(storage, "create_user"):
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User management requires SQLite or PostgreSQL backend.",
        )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post(
    "/invite",
    response_model=InviteResponse,
    status_code=http_status.HTTP_201_CREATED,
    summary="Generate an invite link for a new user (admin only)",
    dependencies=[Depends(require_admin)],
)
async def invite_user(
    body: InviteRequest,
    request: Request,
    storage: StorageBackend = Depends(get_storage),
    caller_user_id: str | None = Depends(get_current_user_id),
) -> InviteResponse:
    """Generate a one-time invite link. Send the invite_url to the new user.

    The link expires after 72 hours. The invited user sets their own password
    when accepting the invite.
    """
    _require_user_storage(storage)

    # Check if a user with this email already exists
    existing = await storage.get_user_by_email(body.email)
    if existing:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail=f"A user with email '{body.email}' already exists.",
        )

    inviter_id = caller_user_id or "system"
    token = secrets.token_hex(32)
    now = datetime.now(UTC)
    expires_at = now + timedelta(hours=_INVITE_TTL_HOURS)

    invite = InviteToken(
        token=token,
        email=body.email,
        role=body.role,
        invited_by=inviter_id,
        created_at=now,
        expires_at=expires_at,
    )
    await storage.create_invite(invite)

    # Use LANGSIGHT_DASHBOARD_URL when set — the invite link must point to the
    # Next.js dashboard, not the FastAPI backend. Falls back to request.base_url
    # for local dev where both run behind the same proxy.
    dashboard_url = getattr(request.app.state, "dashboard_url", None)
    base_url = dashboard_url.rstrip("/") if dashboard_url else str(request.base_url).rstrip("/")
    invite_url = f"{base_url}/accept-invite?token={token}"

    client_ip = request.client.host if request.client else "unknown"
    masked_email = _mask_email(body.email)
    logger.info(
        "audit.user.invite_created", email=masked_email, role=body.role.value, client_ip=client_ip
    )
    append_audit(
        "user.invite_created",
        inviter_id,
        client_ip,
        {"email": masked_email, "role": body.role.value},
        storage=storage,
    )

    return InviteResponse(
        token=token,
        email=body.email,
        role=body.role.value,
        expires_at=expires_at.isoformat(),
        invite_url=invite_url,
    )


@public_router.post(
    "/accept-invite",
    response_model=UserResponse,
    status_code=http_status.HTTP_201_CREATED,
    summary="Accept an invite and create your account",
)
@limiter.limit("5/minute")
async def accept_invite(
    body: AcceptInviteRequest,
    request: Request,
    storage: StorageBackend = Depends(get_storage),
) -> UserResponse:
    """Accept an invite link and set your password.

    The invite token is consumed on use. Expired or already-used tokens
    are rejected. The created account is immediately active.
    """
    _require_user_storage(storage)

    invite = await storage.get_invite(body.token)
    if not invite:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Invalid or expired invite token.",
        )
    if invite.is_used:
        raise HTTPException(
            status_code=http_status.HTTP_410_GONE,
            detail="This invite has already been used.",
        )
    if invite.is_expired:
        raise HTTPException(
            status_code=http_status.HTTP_410_GONE,
            detail="This invite has expired. Ask an admin to send a new one.",
        )

    # Check email not already taken (race condition guard)
    existing = await storage.get_user_by_email(invite.email)
    if existing:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    user = User(
        id=uuid.uuid4().hex,
        email=invite.email,
        password_hash=await _hash_password(body.password),
        role=invite.role,
        active=True,
        invited_by=invite.invited_by,
        created_at=datetime.now(UTC),
    )

    # Prefer atomic accept_invite (single transaction) when available.
    # Falls back to two-step for backends without transaction support.
    if hasattr(storage, "accept_invite"):
        ok = await storage.accept_invite(body.token, user)
        if not ok:
            raise HTTPException(
                status_code=http_status.HTTP_409_CONFLICT,
                detail="This invite has already been used.",
            )
    else:
        await storage.mark_invite_used(body.token)
        await storage.create_user(user)

    client_ip = request.client.host if request.client else "unknown"
    masked_email = _mask_email(user.email)
    logger.info(
        "audit.user.account_created", email=masked_email, role=user.role.value, client_ip=client_ip
    )
    append_audit(
        "user.account_created",
        user.id,
        client_ip,
        {"email": masked_email, "role": user.role.value},
        storage=storage,
    )

    return _user_to_response(user)


@router.get(
    "",
    response_model=list[UserResponse],
    summary="List all users (admin only)",
    dependencies=[Depends(require_admin)],
)
async def list_users(
    storage: StorageBackend = Depends(get_storage),
) -> list[UserResponse]:
    """Return all user accounts (active and inactive)."""
    _require_user_storage(storage)
    users = await storage.list_users()
    return [_user_to_response(u) for u in users]


@router.patch(
    "/{user_id}/role",
    response_model=UserResponse,
    summary="Change a user's role (admin only)",
    dependencies=[Depends(require_admin)],
)
async def update_role(
    user_id: str,
    body: UpdateRoleRequest,
    request: Request,
    storage: StorageBackend = Depends(get_storage),
) -> UserResponse:
    """Change a user's role to admin or viewer."""
    _require_user_storage(storage)

    found = await storage.update_user_role(user_id, body.role.value)
    if not found:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    user = await storage.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    client_ip = request.client.host if request.client else "unknown"
    logger.info(
        "audit.user.role_changed", user_id=user_id, new_role=body.role.value, client_ip=client_ip
    )
    append_audit(
        "user.role_changed",
        user_id,
        client_ip,
        {"new_role": body.role.value},
        storage=storage,
    )
    return _user_to_response(user)


@router.delete(
    "/{user_id}",
    status_code=http_status.HTTP_204_NO_CONTENT,
    summary="Deactivate a user account (admin only)",
    dependencies=[Depends(require_admin)],
)
async def deactivate_user(
    user_id: str,
    request: Request,
    storage: StorageBackend = Depends(get_storage),
) -> None:
    """Deactivate a user. They will no longer be able to log in."""
    _require_user_storage(storage)

    found = await storage.deactivate_user(user_id)
    if not found:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    client_ip = request.client.host if request.client else "unknown"
    logger.info("audit.user.deactivated", user_id=user_id, client_ip=client_ip)
    append_audit("user.deactivated", user_id, client_ip, storage=storage)


@public_router.post(
    "/verify",
    response_model=VerifyResponse,
    summary="Verify dashboard login credentials",
)
@limiter.limit("10/minute", key_func=_login_rate_key)
async def verify_credentials(
    body: VerifyRequest,
    request: Request,
    storage: StorageBackend = Depends(get_storage),
) -> VerifyResponse:
    """Verify email + password and return user info.

    Called by the NextAuth credentials provider during dashboard login.
    Returns 401 on invalid credentials — do not distinguish between
    'user not found' and 'wrong password' to prevent user enumeration.
    """
    _require_user_storage(storage)

    user = await storage.get_user_by_email(body.email)
    if not user or not await _verify_password(body.password, user.password_hash):
        # Mask email — log domain only to avoid PII in log aggregators
        _domain = body.email.split("@")[-1] if "@" in body.email else "?"
        logger.warning(
            "audit.auth.dashboard_login_failed",
            email_domain=_domain,
            client_ip=request.client.host if request.client else "unknown",
        )
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    await storage.touch_user_login(user.id)

    logger.info(
        "audit.auth.dashboard_login_success",
        user_id=user.id,
        role=user.role.value,
    )

    return VerifyResponse(
        id=user.id,
        email=user.email,
        role=user.role.value,
        name=user.email.split("@")[0],
    )
