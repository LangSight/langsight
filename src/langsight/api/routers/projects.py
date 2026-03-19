"""
Project management API.

GET    /api/projects                              — list projects visible to caller
POST   /api/projects                              — create a new project
GET    /api/projects/{project_id}                 — get project detail + caller's role
PATCH  /api/projects/{project_id}                 — rename project (owner only)
DELETE /api/projects/{project_id}                 — delete project (owner or global admin)
GET    /api/projects/{project_id}/members         — list members
POST   /api/projects/{project_id}/members         — add member (owner only)
PATCH  /api/projects/{project_id}/members/{uid}   — change member role (owner only)
DELETE /api/projects/{project_id}/members/{uid}   — remove member (owner only)
"""

from __future__ import annotations

import inspect
import re
import uuid
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi import status as http_status
from pydantic import BaseModel, Field

from langsight.api.audit import append_audit
from langsight.api.dependencies import (
    ProjectAccess,
    _read_api_key,
    get_project_access,
    get_session_user,
    get_storage,
)
from langsight.models import Project, ProjectMember, ProjectRole
from langsight.storage.base import StorageBackend

logger = structlog.get_logger()
router = APIRouter(prefix="/projects", tags=["projects"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class CreateProjectRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    slug: str | None = Field(
        default=None, description="URL-safe slug. Auto-generated from name if omitted."
    )


class UpdateProjectRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    slug: str | None = None


class AddMemberRequest(BaseModel):
    user_id: str
    role: ProjectRole = ProjectRole.MEMBER


class UpdateMemberRoleRequest(BaseModel):
    role: ProjectRole


class ProjectResponse(BaseModel):
    id: str
    name: str
    slug: str
    created_by: str
    created_at: str
    member_count: int = 0
    your_role: str | None = None  # caller's role in this project


class MemberResponse(BaseModel):
    user_id: str
    role: str
    added_by: str
    added_at: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _slugify(name: str) -> str:
    """Convert a display name to a URL-safe slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug or "project"


def _require_storage(storage: StorageBackend) -> None:
    if not hasattr(storage, "create_project"):
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Project management requires SQLite or PostgreSQL backend.",
        )


def _project_to_response(
    p: Project, role: str | None = None, member_count: int = 0
) -> ProjectResponse:
    return ProjectResponse(
        id=p.id,
        name=p.name,
        slug=p.slug,
        created_by=p.created_by,
        created_at=p.created_at.isoformat(),
        member_count=member_count,
        your_role=role,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=list[ProjectResponse], summary="List projects visible to caller")
async def list_projects(
    request: Request,
    storage: StorageBackend = Depends(get_storage),
) -> list[ProjectResponse]:
    """Return all projects the caller can access.

    Global admins see all projects.
    Regular users see only projects where they are a member.
    """
    _require_storage(storage)

    # 1. Session-user path (dashboard users authenticated via Next.js proxy)
    user_id, user_role = get_session_user(request)
    if user_id:
        if user_role == "admin":
            projects = await storage.list_projects()
        else:
            projects = await storage.list_projects_for_user(user_id)
        result = []
        for p in projects:
            members = await storage.list_members(p.id)
            result.append(_project_to_response(p, member_count=len(members)))
        return result

    env_keys: list[str] = getattr(request.app.state, "api_keys", [])
    api_key = _read_api_key(request) or ""

    # 2. Auth disabled — only when NO keys exist anywhere (env or DB)
    has_env_keys = bool(env_keys)
    has_db_keys = False
    list_fn = getattr(storage, "list_api_keys", None)
    if list_fn is not None and inspect.iscoroutinefunction(list_fn):
        try:
            db_keys = await list_fn()
            has_db_keys = any(not k.is_revoked for k in db_keys)
        except Exception:  # noqa: BLE001
            pass
    auth_disabled = not has_env_keys and not has_db_keys

    # Global admin check
    is_admin = auth_disabled or api_key in env_keys
    if not is_admin and hasattr(storage, "get_api_key_by_hash") and api_key:
        import hashlib

        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        record = await storage.get_api_key_by_hash(key_hash)
        if record and record.role.value == "admin":
            is_admin = True

    if is_admin:
        projects = await storage.list_projects()
    else:
        # Use api_key record id as user proxy
        projects = []
        if api_key and hasattr(storage, "get_api_key_by_hash"):
            import hashlib

            key_hash = hashlib.sha256(api_key.encode()).hexdigest()
            record = await storage.get_api_key_by_hash(key_hash)
            if record:
                projects = await storage.list_projects_for_user(record.user_id or record.id)

    result = []
    for p in projects:
        members = await storage.list_members(p.id)
        result.append(_project_to_response(p, member_count=len(members)))
    return result


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=http_status.HTTP_201_CREATED,
    summary="Create a new project",
)
async def create_project(
    body: CreateProjectRequest,
    request: Request,
    storage: StorageBackend = Depends(get_storage),
) -> ProjectResponse:
    """Create a new project. The caller becomes the owner automatically."""
    _require_storage(storage)

    slug = body.slug or _slugify(body.name)
    # Ensure slug uniqueness — append short uuid if taken
    existing = await storage.get_project_by_slug(slug)
    if existing:
        slug = f"{slug}-{uuid.uuid4().hex[:6]}"

    # Determine creator id — priority: session user > API key > first admin > system
    creator_id = "system"

    # 1. Session user forwarded by the dashboard proxy (most common path)
    session_user_id, _ = get_session_user(request)
    if session_user_id:
        creator_id = session_user_id
    else:
        # 2. Direct API key call (SDK / programmatic access)
        import hashlib

        api_key = _read_api_key(request) or ""
        if api_key and hasattr(storage, "get_api_key_by_hash"):
            key_hash = hashlib.sha256(api_key.encode()).hexdigest()
            record = await storage.get_api_key_by_hash(key_hash)
            if record:
                creator_id = record.user_id or record.id
        elif not api_key and hasattr(storage, "list_users"):
            # 3. Auth disabled — use the first admin user as creator
            try:
                users = await storage.list_users()
                admins = [u for u in users if getattr(u, "role", None) and u.role.value == "admin"]
                if admins:
                    creator_id = admins[0].id
            except Exception:  # noqa: BLE001
                pass

    project = Project(
        id=uuid.uuid4().hex,
        name=body.name.strip(),
        slug=slug,
        created_by=creator_id,
        created_at=datetime.now(UTC),
    )
    await storage.create_project(project)

    # Auto-add creator as owner
    await storage.add_member(
        ProjectMember(
            project_id=project.id,
            user_id=creator_id,
            role=ProjectRole.OWNER,
            added_by=creator_id,
            added_at=datetime.now(UTC),
        )
    )

    logger.info(
        "audit.project.created", project_id=project.id, name=project.name, creator=creator_id
    )
    append_audit(
        "project.created",
        creator_id,
        request.client.host if request.client else "unknown",
        {"project_id": project.id, "name": project.name},
        storage=storage,
    )
    return _project_to_response(project, role="owner", member_count=1)


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
    summary="Get project detail",
)
async def get_project(
    project_id: str,
    storage: StorageBackend = Depends(get_storage),
    access: ProjectAccess = Depends(get_project_access),
) -> ProjectResponse:
    """Return project detail including the caller's role."""
    members = await storage.list_members(project_id)
    return _project_to_response(access.project, role=access.role.value, member_count=len(members))


@router.patch(
    "/{project_id}",
    response_model=ProjectResponse,
    summary="Rename a project (owner only)",
)
async def update_project(
    project_id: str,
    body: UpdateProjectRequest,
    request: Request,
    storage: StorageBackend = Depends(get_storage),
    access: ProjectAccess = Depends(get_project_access),
) -> ProjectResponse:
    """Rename or re-slug a project. Requires owner role."""
    if not access.is_owner:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Only project owners can rename a project.",
        )

    slug = body.slug or _slugify(body.name)
    existing = await storage.get_project_by_slug(slug)
    if existing and existing.id != project_id:
        slug = f"{slug}-{uuid.uuid4().hex[:6]}"

    await storage.update_project(project_id, body.name.strip(), slug)
    updated = await storage.get_project(project_id)
    members = await storage.list_members(project_id)
    logger.info("audit.project.updated", project_id=project_id, name=body.name)
    append_audit(
        "project.updated",
        None,
        request.client.host if request.client else "unknown",
        {"project_id": project_id, "name": body.name.strip(), "slug": slug},
        storage=storage,
    )
    return _project_to_response(updated, role=access.role.value, member_count=len(members))  # type: ignore[arg-type]


@router.delete(
    "/{project_id}",
    status_code=http_status.HTTP_204_NO_CONTENT,
    summary="Delete a project (owner or global admin)",
)
async def delete_project(
    project_id: str,
    request: Request,
    storage: StorageBackend = Depends(get_storage),
    access: ProjectAccess = Depends(get_project_access),
) -> None:
    """Delete a project and all its memberships. Irreversible."""
    if not access.is_owner:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Only project owners can delete a project.",
        )
    await storage.delete_project(project_id)
    client_ip = request.client.host if request.client else "unknown"
    logger.info("audit.project.deleted", project_id=project_id, client_ip=client_ip)
    append_audit("project.deleted", None, client_ip, {"project_id": project_id}, storage=storage)


# ---------------------------------------------------------------------------
# Member management
# ---------------------------------------------------------------------------


@router.get(
    "/{project_id}/members",
    response_model=list[MemberResponse],
    summary="List project members",
)
async def list_members(
    project_id: str,
    storage: StorageBackend = Depends(get_storage),
    access: ProjectAccess = Depends(get_project_access),
) -> list[MemberResponse]:
    members = await storage.list_members(project_id)
    return [
        MemberResponse(
            user_id=m.user_id,
            role=m.role.value,
            added_by=m.added_by,
            added_at=m.added_at.isoformat(),
        )
        for m in members
    ]


@router.post(
    "/{project_id}/members",
    response_model=MemberResponse,
    status_code=http_status.HTTP_201_CREATED,
    summary="Add a member to the project (owner only)",
)
async def add_member(
    project_id: str,
    body: AddMemberRequest,
    request: Request,
    storage: StorageBackend = Depends(get_storage),
    access: ProjectAccess = Depends(get_project_access),
) -> MemberResponse:
    if not access.is_owner:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Only project owners can add members.",
        )
    now = datetime.now(UTC)
    api_key = request.headers.get("X-API-Key", "")
    adder_id = "system"
    if api_key and hasattr(storage, "get_api_key_by_hash"):
        import hashlib

        record = await storage.get_api_key_by_hash(hashlib.sha256(api_key.encode()).hexdigest())
        if record:
            adder_id = record.user_id or record.id

    member = ProjectMember(
        project_id=project_id,
        user_id=body.user_id,
        role=body.role,
        added_by=adder_id,
        added_at=now,
    )
    await storage.add_member(member)
    logger.info(
        "audit.project.member_added",
        project_id=project_id,
        user_id=body.user_id,
        role=body.role.value,
    )
    append_audit(
        "project.member_added",
        adder_id,
        request.client.host if request.client else "unknown",
        {"project_id": project_id, "user_id": body.user_id, "role": body.role.value},
        storage=storage,
    )
    return MemberResponse(
        user_id=member.user_id,
        role=member.role.value,
        added_by=member.added_by,
        added_at=member.added_at.isoformat(),
    )


@router.patch(
    "/{project_id}/members/{user_id}",
    response_model=MemberResponse,
    summary="Change a member's role (owner only)",
)
async def update_member_role(
    project_id: str,
    user_id: str,
    body: UpdateMemberRoleRequest,
    storage: StorageBackend = Depends(get_storage),
    access: ProjectAccess = Depends(get_project_access),
) -> MemberResponse:
    if not access.is_owner:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Only project owners can change member roles.",
        )
    found = await storage.update_member_role(project_id, user_id, body.role.value)
    if not found:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Member not found.")
    member = await storage.get_member(project_id, user_id)
    assert member is not None  # we just updated it; can't be None
    return MemberResponse(
        user_id=member.user_id,
        role=member.role.value,
        added_by=member.added_by,
        added_at=member.added_at.isoformat(),
    )


@router.delete(
    "/{project_id}/members/{user_id}",
    status_code=http_status.HTTP_204_NO_CONTENT,
    summary="Remove a member from the project (owner only)",
)
async def remove_member(
    project_id: str,
    user_id: str,
    storage: StorageBackend = Depends(get_storage),
    access: ProjectAccess = Depends(get_project_access),
) -> None:
    if not access.is_owner:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Only project owners can remove members.",
        )
    found = await storage.remove_member(project_id, user_id)
    if not found:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Member not found.")
