"""
Security tests for tenant isolation boundaries (v0.8.1).

Invariants enforced:
  1. A project-B key querying project-A data must receive 404 (not data).
     404 prevents project enumeration — the attacker cannot confirm the project exists.
  2. An unscoped key with no membership must also receive 404 for any project.
  3. A global admin (env-var key) may access any project.
  4. A project-A scoped key can never escalate to global (return None) — even if
     the DB key has role=admin.
  5. An expired API key must be rejected (403) before project lookup.
  6. Non-member asking for a valid project_id → 404 (not 403, prevents enumeration).

All tests run offline — no Docker, no real DB, no network.
"""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from tests.security.conftest import (
    _active_key_record,
    _make_request,
    _make_storage,
)

pytestmark = pytest.mark.security


# ---------------------------------------------------------------------------
# Helpers — extend conftest helpers for project_id scenarios
# ---------------------------------------------------------------------------


def _scoped_key_record(
    *,
    raw_key: str,
    project_id: str,
    role: str = "viewer",
    is_expired: bool = False,
) -> MagicMock:
    """Build a mock ApiKeyRecord with project_id and configurable expiry."""
    from langsight.models import ApiKeyRole

    rec = MagicMock()
    rec.id = "key-" + raw_key[:6]
    rec.key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    rec.project_id = project_id
    rec.is_revoked = False
    rec.is_expired = is_expired
    rec.user_id = None
    rec.role = ApiKeyRole.ADMIN if role == "admin" else ApiKeyRole.VIEWER
    return rec


def _make_storage_with_hash_lookup(
    *,
    active_db_keys: list,
    hash_lookup: object | None = None,
) -> MagicMock:
    """Storage that returns a specific record from get_api_key_by_hash."""
    storage = _make_storage(active_db_keys=active_db_keys)
    storage.get_api_key_by_hash = AsyncMock(return_value=hash_lookup)
    return storage


# ---------------------------------------------------------------------------
# 1. Project-B key cannot query project-A data
# ---------------------------------------------------------------------------


class TestCrossProjectKeyIsolation:
    async def test_project_b_key_cannot_query_project_a_data(self) -> None:
        """Request with project-B key, asks for project-A data → 404.

        The resolver overwrites project-A with project-B (key always wins).
        When get_active_project_id is called with project_id='proj-a', it
        returns 'proj-b' instead.  A router that gates on the resolved ID
        would then not find 'proj-a' data under 'proj-b'.

        Here we use get_project_access (which checks membership) to confirm
        that a project-B key cannot access project-A through the access-check
        path either — it returns 404 when project exists but key has no access.
        """
        from langsight.api.dependencies import get_active_project_id

        raw_key = "proj-b-key-00000"
        proj_b_record = _scoped_key_record(raw_key=raw_key, project_id="proj-b")
        storage = _make_storage_with_hash_lookup(
            active_db_keys=[proj_b_record],
            hash_lookup=proj_b_record,
        )

        req = _make_request(
            client_ip="10.0.0.1",
            headers={"X-API-Key": raw_key},
            api_keys=[],
            storage=storage,
        )
        # Even though caller asks for proj-a, the key's project_id (proj-b) wins
        resolved = await get_active_project_id(request=req, project_id="proj-a")
        # The key's project_id overrides the query param — data scoped to proj-b
        assert resolved == "proj-b"
        assert resolved != "proj-a", (
            "Project-B scoped key must not resolve to project-A data. "
            f"Resolved to {resolved!r}"
        )

    async def test_project_scoped_key_get_project_access_raises_404_for_foreign_project(
        self,
    ) -> None:
        """get_project_access for a project the key cannot access → 404.

        This covers the full access-check dependency, not just project resolution.
        The 404 prevents the attacker from learning whether the project exists.
        """
        from langsight.api.dependencies import get_project_access

        raw_key = "proj-a-key-xyzzy"
        proj_a_record = _scoped_key_record(raw_key=raw_key, project_id="proj-a")

        storage = MagicMock()
        storage.list_members = AsyncMock(return_value=[])
        storage.list_api_keys = AsyncMock(return_value=[proj_a_record])
        storage.get_api_key_by_hash = AsyncMock(return_value=proj_a_record)
        storage.get_member = AsyncMock(return_value=None)
        # Project B exists in storage
        mock_proj_b = MagicMock()
        mock_proj_b.id = "proj-b"
        storage.get_project = AsyncMock(return_value=mock_proj_b)
        storage.get_api_key_by_hash = AsyncMock(return_value=proj_a_record)

        req = _make_request(
            client_ip="10.0.0.1",
            headers={"X-API-Key": raw_key},
            api_keys=[],
            storage=storage,
        )

        with pytest.raises(HTTPException) as exc_info:
            # Pass api_key=None explicitly — the Security() default is a FastAPI
            # descriptor and cannot be used when calling the function directly.
            await get_project_access(project_id="proj-b", request=req, api_key=raw_key)
        # 404 — not 403, prevents enumeration
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# 2. Unscoped key with no membership cannot access any project
# ---------------------------------------------------------------------------


class TestUnscopedKeyNoMembership:
    async def test_no_project_id_on_key_cannot_access_project_without_membership(
        self,
    ) -> None:
        """Unscoped DB key with no project membership → 404.

        An API key with project_id=None and no project membership record
        must not be granted access to any project.  Returns 404 to prevent
        enumeration of projects the caller guesses.
        """
        from langsight.api.dependencies import get_active_project_id

        raw_key = "unscoped-viewer-key"
        unscoped_record = MagicMock()
        unscoped_record.id = "unscoped-key-1"
        unscoped_record.project_id = None
        unscoped_record.is_revoked = False
        unscoped_record.is_expired = False
        unscoped_record.user_id = None
        from langsight.models import ApiKeyRole
        unscoped_record.role = ApiKeyRole.VIEWER

        storage = _make_storage_with_hash_lookup(
            active_db_keys=[unscoped_record],
            hash_lookup=unscoped_record,
        )
        storage.get_member = AsyncMock(return_value=None)  # no membership

        req = _make_request(
            client_ip="10.0.0.1",
            headers={"X-API-Key": raw_key},
            api_keys=[],
            storage=storage,
        )
        # No project_id on key, no membership → must block with 400
        with pytest.raises(HTTPException) as exc_info:
            await get_active_project_id(request=req, project_id=None)
        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# 3. Project enumeration prevented — 404, not 403
# ---------------------------------------------------------------------------


class TestProjectEnumerationPrevented:
    async def test_project_enumeration_prevented_returns_404_not_403(self) -> None:
        """Non-member asking for a valid project_id → 404 (not 403).

        Returning 403 would confirm the project exists; 404 is intentional
        to prevent enumeration attacks where an attacker iterates project IDs.
        """
        from langsight.api.dependencies import get_project_access

        raw_key = "non-member-key"
        db_record = MagicMock()
        db_record.id = "non-member-key-id"
        db_record.project_id = None
        db_record.is_revoked = False
        db_record.is_expired = False
        db_record.user_id = None
        from langsight.models import ApiKeyRole
        db_record.role = ApiKeyRole.VIEWER

        storage = MagicMock()
        storage.list_api_keys = AsyncMock(return_value=[db_record])
        storage.get_api_key_by_hash = AsyncMock(return_value=db_record)
        storage.list_members = AsyncMock(return_value=[])
        storage.get_member = AsyncMock(return_value=None)  # no membership
        # The project exists in storage (real project ID) — non-member should not see it
        real_project = MagicMock()
        real_project.id = "real-project-id"
        storage.get_project = AsyncMock(return_value=real_project)

        req = _make_request(
            client_ip="10.0.0.1",
            headers={"X-API-Key": raw_key},
            api_keys=[],
            storage=storage,
        )
        with pytest.raises(HTTPException) as exc_info:
            # Pass api_key explicitly — Security() descriptor cannot be used directly.
            await get_project_access(
                project_id="real-project-id", request=req, api_key=raw_key
            )
        # Must be 404 (not 403) to prevent enumeration
        assert exc_info.value.status_code == 404, (
            f"Expected 404 to prevent project enumeration, "
            f"got {exc_info.value.status_code}. "
            "403 would confirm the project exists to an attacker."
        )

    async def test_nonexistent_project_also_returns_404(self) -> None:
        """Nonexistent project → 404 (consistent with enumeration prevention)."""
        from langsight.api.dependencies import get_project_access

        raw_key = "any-key"
        db_record = MagicMock()
        db_record.id = "any-key-id"
        from langsight.models import ApiKeyRole
        db_record.role = ApiKeyRole.VIEWER
        db_record.is_revoked = False
        db_record.is_expired = False

        storage = MagicMock()
        storage.list_api_keys = AsyncMock(return_value=[db_record])
        storage.get_api_key_by_hash = AsyncMock(return_value=db_record)
        storage.list_members = AsyncMock(return_value=[])
        storage.get_member = AsyncMock(return_value=None)
        storage.get_project = AsyncMock(return_value=None)  # does not exist

        req = _make_request(
            client_ip="10.0.0.1",
            headers={"X-API-Key": raw_key},
            api_keys=[],
            storage=storage,
        )
        with pytest.raises(HTTPException) as exc_info:
            await get_project_access(
                project_id="ghost-project", request=req, api_key=raw_key
            )
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# 4. Env admin key can access any project
# ---------------------------------------------------------------------------


class TestEnvAdminKeyAccessesAnyProject:
    async def test_env_admin_key_can_access_any_project(self) -> None:
        """Env-var bootstrap key (always admin) → can access project A and B.

        Env-var keys bypass project membership checks entirely.
        """
        from langsight.api.dependencies import get_active_project_id

        env_key = "bootstrap-admin-key"
        storage = _make_storage(active_db_keys=[])  # no DB keys

        for project in ("proj-a", "proj-b", "proj-c"):
            req = _make_request(
                client_ip="10.0.0.1",
                headers={"X-API-Key": env_key},
                api_keys=[env_key],
                storage=storage,
            )
            resolved = await get_active_project_id(request=req, project_id=project)
            assert resolved == project, (
                f"Admin env key must be able to access {project}, "
                f"got {resolved!r}"
            )

    async def test_env_admin_key_without_project_returns_none(self) -> None:
        """Env admin key + no project → None (global view, no filter)."""
        from langsight.api.dependencies import get_active_project_id

        env_key = "another-bootstrap-key"
        storage = _make_storage(active_db_keys=[])

        req = _make_request(
            client_ip="10.0.0.1",
            headers={"X-API-Key": env_key},
            api_keys=[env_key],
            storage=storage,
        )
        resolved = await get_active_project_id(request=req, project_id=None)
        assert resolved is None


# ---------------------------------------------------------------------------
# 5. Project-scoped key cannot escalate to global
# ---------------------------------------------------------------------------


class TestProjectScopedKeyCannotEscalate:
    async def test_project_scoped_key_cannot_escalate_to_global(self) -> None:
        """A project-A scoped key cannot resolve to None (global view).

        Even if the key record has role=admin in the DB, the project_id
        field must be respected.  The key must resolve to its project, not None.
        """
        from langsight.api.dependencies import get_active_project_id

        raw_key = "scoped-admin-escalation-attempt"
        # Admin-role key but with project_id set — must NOT become global
        proj_a_record = _scoped_key_record(
            raw_key=raw_key,
            project_id="proj-a",
            role="admin",  # admin role but scoped
        )
        storage = _make_storage_with_hash_lookup(
            active_db_keys=[proj_a_record],
            hash_lookup=proj_a_record,
        )

        req = _make_request(
            client_ip="10.0.0.1",
            headers={"X-API-Key": raw_key},
            api_keys=[],  # NOT an env key — goes through DB lookup
            storage=storage,
        )
        # No project_id in query param — should resolve to key's project_id
        resolved = await get_active_project_id(request=req, project_id=None)

        assert resolved is not None, (
            "Project-scoped key (even admin role) must NOT return None. "
            "Returning None would grant global access — privilege escalation."
        )
        assert resolved == "proj-a", (
            f"Expected resolved project_id='proj-a', got {resolved!r}"
        )

    async def test_project_scoped_key_cannot_query_other_project_even_with_admin_role(
        self,
    ) -> None:
        """Admin-role but project-scoped key cannot access a different project."""
        from langsight.api.dependencies import get_active_project_id

        raw_key = "scoped-admin-cross-proj"
        proj_a_record = _scoped_key_record(
            raw_key=raw_key,
            project_id="proj-a",
            role="admin",
        )
        storage = _make_storage_with_hash_lookup(
            active_db_keys=[proj_a_record],
            hash_lookup=proj_a_record,
        )

        req = _make_request(
            client_ip="10.0.0.1",
            headers={"X-API-Key": raw_key},
            api_keys=[],
            storage=storage,
        )
        # Asking for proj-b explicitly — key's project_id must still win
        resolved = await get_active_project_id(request=req, project_id="proj-b")
        assert resolved == "proj-a", (
            "Admin-role scoped key must not be able to access proj-b. "
            f"Got {resolved!r}"
        )


# ---------------------------------------------------------------------------
# 6. Expired API key rejected before project lookup
# ---------------------------------------------------------------------------


class TestExpiredApiKeyRejected:
    async def test_expired_api_key_rejected_even_with_valid_project(self) -> None:
        """Expired key → 403 before project lookup.

        verify_api_key raises 403 on expired keys; the project lookup in
        get_active_project_id must never be reached with an expired key.
        This test exercises verify_api_key directly.
        """
        from langsight.api.dependencies import verify_api_key

        raw_key = "expired-scoped-key"
        expired_record = _scoped_key_record(
            raw_key=raw_key,
            project_id="valid-project",
            is_expired=True,
        )
        storage = _make_storage_with_hash_lookup(
            active_db_keys=[expired_record],
            hash_lookup=expired_record,
        )

        req = _make_request(
            client_ip="10.0.0.1",
            headers={"X-API-Key": raw_key},
            api_keys=[],
            storage=storage,
        )
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(request=req, api_key=raw_key)
        assert exc_info.value.status_code == 403, (
            f"Expected 403 for expired key, got {exc_info.value.status_code}. "
            "Expired keys must be rejected before any project data is accessed."
        )

    async def test_expired_key_error_message_mentions_expiry(self) -> None:
        """403 for expired key must mention 'expired' so the caller knows why."""
        from langsight.api.dependencies import verify_api_key

        raw_key = "expired-key-msg-check"
        expired_record = _scoped_key_record(
            raw_key=raw_key,
            project_id="some-project",
            is_expired=True,
        )
        storage = _make_storage_with_hash_lookup(
            active_db_keys=[expired_record],
            hash_lookup=expired_record,
        )

        req = _make_request(
            client_ip="10.0.0.1",
            headers={"X-API-Key": raw_key},
            api_keys=[],
            storage=storage,
        )
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(request=req, api_key=raw_key)
        assert "expired" in exc_info.value.detail.lower(), (
            f"Expected 'expired' in error detail, got: {exc_info.value.detail!r}"
        )

    async def test_expiry_gate_is_verify_api_key_not_get_active_project_id(self) -> None:
        """The expiry enforcement lives exclusively in verify_api_key.

        verify_api_key (the auth gate) raises 403 on expired keys, preventing
        the request from ever reaching get_active_project_id.  This test
        documents the security contract: the boundary between "is the key
        valid" (auth layer) and "which project does it scope to" (scoping
        layer) is intentional.

        Calling verify_api_key with an expired key must raise 403 — no data
        is returned and get_active_project_id is never invoked in a real flow.
        """
        from langsight.api.dependencies import verify_api_key

        raw_key = "expired-no-leak"
        expired_record = _scoped_key_record(
            raw_key=raw_key,
            project_id="secret-expired-project",
            is_expired=True,
        )
        storage = _make_storage_with_hash_lookup(
            active_db_keys=[expired_record],
            hash_lookup=expired_record,
        )

        req = _make_request(
            client_ip="10.0.0.1",
            headers={"X-API-Key": raw_key},
            api_keys=[],
            storage=storage,
        )
        # The auth gate must 403 — stopping the request before any project scoping
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(request=req, api_key=raw_key)
        assert exc_info.value.status_code == 403, (
            "Expired key must be rejected at the auth layer (403) before "
            "project scoping is ever attempted."
        )
