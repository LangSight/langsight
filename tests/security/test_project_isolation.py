"""
Security regression tests — project isolation / multi-tenant data scoping.

Invariants:
  1. Non-admin authenticated users MUST supply project_id — 400 if missing.
  2. Non-admin users cannot access a project they are not a member of — 404.
  3. Admins can query with project_id=None (see all) — must not be blocked.
  4. Open installs (no auth) can query without project_id — backward compat.
  5. DB errors during membership checks must deny, not silently allow through.

The pre-fix bug: get_active_project_id returned None when project_id was absent,
which caused storage queries to run with no filter, leaking all-project data to
any authenticated user.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from tests.security.conftest import (
    _active_key_record,
    _make_request,
    _make_storage,
    _member_record,
)

pytestmark = pytest.mark.security


# ---------------------------------------------------------------------------
# project_id required for non-admins (the isolation regression)
# ---------------------------------------------------------------------------

class TestProjectIdRequiredForNonAdmins:
    async def test_viewer_session_without_project_id_gets_400(self) -> None:
        """Non-admin session user with no project_id must get 400, not a data dump."""
        from langsight.api.dependencies import get_active_project_id

        storage = _make_storage(active_db_keys=[_active_key_record()])
        req = _make_request(
            client_ip="127.0.0.1",
            headers={"X-User-Id": "viewer-1", "X-User-Role": "viewer"},
            api_keys=["env-key"],
            storage=storage,
        )
        with pytest.raises(HTTPException) as exc_info:
            await get_active_project_id(request=req, project_id=None)
        assert exc_info.value.status_code == 400
        assert "project_id" in exc_info.value.detail.lower()

    async def test_member_session_without_project_id_gets_400(self) -> None:
        """member role (not admin) also blocked without project_id."""
        from langsight.api.dependencies import get_active_project_id

        storage = _make_storage(active_db_keys=[_active_key_record(role="viewer")])
        req = _make_request(
            client_ip="127.0.0.1",
            headers={"X-User-Id": "member-1", "X-User-Role": "member"},
            api_keys=["env-key"],
            storage=storage,
        )
        with pytest.raises(HTTPException) as exc_info:
            await get_active_project_id(request=req, project_id=None)
        assert exc_info.value.status_code == 400

    async def test_non_admin_db_key_without_project_id_gets_400(self) -> None:
        """Non-admin API key with no project_id must also be blocked."""
        from langsight.api.dependencies import get_active_project_id

        viewer_record = _active_key_record(role="viewer")
        storage = _make_storage(active_db_keys=[viewer_record])
        req = _make_request(
            client_ip="10.0.0.1",
            headers={"X-API-Key": "viewer-key"},
            api_keys=[],
            storage=storage,
        )
        with pytest.raises(HTTPException) as exc_info:
            await get_active_project_id(request=req, project_id=None)
        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# Admin sees all; open install has no restriction
# ---------------------------------------------------------------------------

class TestAdminAndOpenInstallExceptions:
    async def test_admin_session_without_project_id_returns_none(self) -> None:
        """Admins can query all data — project_id=None is valid for them."""
        from langsight.api.dependencies import get_active_project_id

        storage = _make_storage(active_db_keys=[])
        req = _make_request(
            client_ip="127.0.0.1",
            headers={"X-User-Id": "admin-1", "X-User-Role": "admin"},
            api_keys=["env-key"],
            storage=storage,
        )
        result = await get_active_project_id(request=req, project_id=None)
        assert result is None

    async def test_env_key_admin_without_project_id_returns_none(self) -> None:
        """Env-var bootstrap key is always admin — no project filter enforced."""
        from langsight.api.dependencies import get_active_project_id

        storage = _make_storage(active_db_keys=[])
        req = _make_request(
            client_ip="10.0.0.1",
            headers={"X-API-Key": "bootstrap"},
            api_keys=["bootstrap"],
            storage=storage,
        )
        result = await get_active_project_id(request=req, project_id=None)
        assert result is None

    async def test_open_install_without_project_id_returns_none(self) -> None:
        """No auth configured — open install must still work without project_id."""
        from langsight.api.dependencies import get_active_project_id

        storage = _make_storage(active_db_keys=[])
        req = _make_request(client_ip="10.0.0.1", headers={}, api_keys=[], storage=storage)
        result = await get_active_project_id(request=req, project_id=None)
        assert result is None


# ---------------------------------------------------------------------------
# Cross-tenant access — non-member cannot access foreign project
# ---------------------------------------------------------------------------

class TestCrossTenantAccess:
    async def test_non_member_user_cannot_access_foreign_project(self) -> None:
        """User who is NOT a member of project-B cannot query project-B's data."""
        from langsight.api.dependencies import get_active_project_id

        storage = _make_storage(
            active_db_keys=[_active_key_record()],
            get_member_returns=None,  # not a member of any project
        )
        req = _make_request(
            client_ip="127.0.0.1",
            headers={"X-User-Id": "user-no-access", "X-User-Role": "viewer"},
            api_keys=["env-key"],
            storage=storage,
        )
        with pytest.raises(HTTPException) as exc_info:
            await get_active_project_id(request=req, project_id="project-b")
        assert exc_info.value.status_code == 404

    async def test_member_of_project_a_cannot_access_project_b(self) -> None:
        """Being a member of project-A must not grant access to project-B."""
        from langsight.api.dependencies import get_active_project_id

        # get_member returns None for project-b specifically
        storage = _make_storage(active_db_keys=[_active_key_record()])
        storage.get_member = AsyncMock(return_value=None)  # not in project-b

        req = _make_request(
            client_ip="127.0.0.1",
            headers={"X-User-Id": "user-in-project-a", "X-User-Role": "viewer"},
            api_keys=["env-key"],
            storage=storage,
        )
        with pytest.raises(HTTPException) as exc_info:
            await get_active_project_id(request=req, project_id="project-b")
        assert exc_info.value.status_code == 404

    async def test_member_of_project_can_access_their_own_project(self) -> None:
        """A genuine member must be able to access their project — not over-blocked."""
        from langsight.api.dependencies import get_active_project_id

        storage = _make_storage(active_db_keys=[_active_key_record()])
        storage.get_member = AsyncMock(return_value=_member_record("project-a", "user-1"))

        req = _make_request(
            client_ip="127.0.0.1",
            headers={"X-User-Id": "user-1", "X-User-Role": "viewer"},
            api_keys=["env-key"],
            storage=storage,
        )
        result = await get_active_project_id(request=req, project_id="project-a")
        assert result == "project-a"

    async def test_admin_can_access_any_project_without_membership(self) -> None:
        """Admin bypass: get_member must NOT be called for admin users."""
        from langsight.api.dependencies import get_active_project_id

        storage = _make_storage(active_db_keys=[])
        storage.get_member = AsyncMock(return_value=None)  # no membership

        req = _make_request(
            client_ip="127.0.0.1",
            headers={"X-User-Id": "admin-user", "X-User-Role": "admin"},
            api_keys=["env-key"],
            storage=storage,
        )
        result = await get_active_project_id(request=req, project_id="any-project")
        assert result == "any-project"
        storage.get_member.assert_not_called()


# ---------------------------------------------------------------------------
# DB error during membership check
# ---------------------------------------------------------------------------

class TestMembershipCheckFailure:
    async def test_db_error_during_membership_check_denies_access(self) -> None:
        """If get_member throws, must not silently grant cross-project access."""
        from langsight.api.dependencies import get_active_project_id

        storage = _make_storage(
            active_db_keys=[_active_key_record()],
            get_member_raises=Exception("membership query failed"),
        )
        req = _make_request(
            client_ip="127.0.0.1",
            headers={"X-User-Id": "attacker", "X-User-Role": "viewer"},
            api_keys=["env-key"],
            storage=storage,
        )
        with pytest.raises((HTTPException, Exception)):
            await get_active_project_id(request=req, project_id="victim-project")
        # Whatever is raised, it must NOT be a successful return of the project_id


# ---------------------------------------------------------------------------
# HTTP endpoint layer — project isolation on real routes
# ---------------------------------------------------------------------------

class TestEndpointProjectIsolation:
    async def test_sessions_with_no_project_id_with_admin_key_returns_200(
        self, auth_client
    ) -> None:
        """Env key (always admin) + no project_id → 200 (admin sees all).

        The 400 path for non-admins is covered at the dependency level because
        constructing a non-admin DB-key path through the full ASGI stack requires
        complex key-hash wiring. The dependency tests above cover that directly.
        """
        c, mock_storage, _ = auth_client
        mock_storage.get_agent_sessions = AsyncMock(return_value=[])
        mock_storage.list_members = AsyncMock(return_value=[])
        mock_storage.list_api_keys = AsyncMock(return_value=[])

        response = await c.get(
            "/api/agents/sessions",
            headers={"X-API-Key": "test-api-key"},
        )
        assert response.status_code == 200

    async def test_sessions_with_valid_key_and_project_id_succeeds(
        self, auth_client
    ) -> None:
        """Env key (admin) + project_id → data returned (not blocked)."""
        c, mock_storage, _ = auth_client
        mock_storage.get_agent_sessions = AsyncMock(return_value=[])
        mock_storage.list_members = AsyncMock(return_value=[])

        response = await c.get(
            "/api/agents/sessions?project_id=proj-1",
            headers={"X-API-Key": "test-api-key"},
        )
        assert response.status_code == 200

    async def test_costs_endpoint_scoped_to_project(self, auth_client) -> None:
        """Costs endpoint with project_id and valid key succeeds."""
        c, mock_storage, _ = auth_client
        mock_storage.get_cost_call_counts = AsyncMock(return_value=[])
        mock_storage.list_model_pricing = AsyncMock(return_value=[])
        mock_storage.list_members = AsyncMock(return_value=[])

        response = await c.get(
            "/api/costs/breakdown?project_id=proj-1",
            headers={"X-API-Key": "test-api-key"},
        )
        assert response.status_code == 200
