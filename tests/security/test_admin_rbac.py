"""
Security regression tests — admin-only endpoint enforcement (RBAC).

Invariants:
  1. Viewer-role session users cannot reach admin-only endpoints — 403.
  2. Viewer-role DB API keys cannot reach admin-only endpoints — 403.
  3. Admin-role session users CAN reach admin-only endpoints — 200/201.
  4. Env-var keys are always admin — admin endpoints accessible.
  5. No key when auth enabled → 401, not 403 (correct error code matters for clients).

Admin-only operations: create/list/revoke API keys, create/delete SLOs.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from tests.security.conftest import (
    _TEST_PROXY_SECRET,
    _active_key_record,
    _make_request,
    _make_storage,
    _sign_proxy_headers,
)

pytestmark = pytest.mark.security


# ---------------------------------------------------------------------------
# require_admin dependency
# ---------------------------------------------------------------------------

class TestRequireAdminDependency:
    async def test_viewer_session_blocked(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from langsight.api.dependencies import require_admin

        monkeypatch.setenv("LANGSIGHT_PROXY_SECRET", _TEST_PROXY_SECRET)
        headers = _sign_proxy_headers("viewer", "viewer", _TEST_PROXY_SECRET)
        req = _make_request(
            client_ip="127.0.0.1",
            headers=headers,
            api_keys=[],
        )
        with pytest.raises(HTTPException) as exc_info:
            await require_admin(request=req, api_key=None)
        assert exc_info.value.status_code == 403

    async def test_member_session_blocked(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from langsight.api.dependencies import require_admin

        monkeypatch.setenv("LANGSIGHT_PROXY_SECRET", _TEST_PROXY_SECRET)
        headers = _sign_proxy_headers("member", "member", _TEST_PROXY_SECRET)
        req = _make_request(
            client_ip="127.0.0.1",
            headers=headers,
            api_keys=[],
        )
        with pytest.raises(HTTPException) as exc_info:
            await require_admin(request=req, api_key=None)
        assert exc_info.value.status_code == 403

    async def test_admin_session_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from langsight.api.dependencies import require_admin
        from unittest.mock import AsyncMock, MagicMock

        monkeypatch.setenv("LANGSIGHT_PROXY_SECRET", _TEST_PROXY_SECRET)
        headers = _sign_proxy_headers("admin-1", "admin", _TEST_PROXY_SECRET)
        storage = _make_storage()
        storage.get_user_by_id = AsyncMock(return_value=MagicMock(active=True, role=MagicMock(value="admin")))
        req = _make_request(
            client_ip="127.0.0.1",
            headers=headers,
            api_keys=[],
            storage=storage,
        )
        await require_admin(request=req, api_key=None)  # must not raise

    async def test_env_key_is_always_admin(self) -> None:
        from langsight.api.dependencies import require_admin

        req = _make_request(
            client_ip="10.0.0.1",
            headers={"X-API-Key": "bootstrap"},
            api_keys=["bootstrap"],
        )
        await require_admin(request=req, api_key="bootstrap")  # must not raise

    async def test_viewer_db_key_is_blocked(self) -> None:

        from langsight.api.dependencies import require_admin

        viewer_key = "viewer-secret"
        viewer_record = _active_key_record(role="viewer")
        storage = _make_storage(active_db_keys=[viewer_record])
        storage.get_api_key_by_hash = AsyncMock(return_value=viewer_record)

        req = _make_request(
            client_ip="10.0.0.1",
            headers={"X-API-Key": viewer_key},
            api_keys=[],
            storage=storage,
        )
        with pytest.raises(HTTPException) as exc_info:
            await require_admin(request=req, api_key=viewer_key)
        assert exc_info.value.status_code == 403

    async def test_no_key_returns_401_not_403(self) -> None:
        """Missing key must be 401 (unauthenticated), not 403 (forbidden)."""
        from langsight.api.dependencies import require_admin

        storage = _make_storage(active_db_keys=[_active_key_record()])
        req = _make_request(client_ip="10.0.0.1", headers={}, api_keys=[], storage=storage)
        with pytest.raises(HTTPException) as exc_info:
            await require_admin(request=req, api_key=None)
        assert exc_info.value.status_code == 401

    async def test_admin_role_spoofed_from_external_ip_is_blocked(self) -> None:
        """Admin headers from untrusted IP must not grant admin access."""
        from langsight.api.dependencies import require_admin

        storage = _make_storage(active_db_keys=[_active_key_record()])
        req = _make_request(
            client_ip="8.8.8.8",  # untrusted external
            headers={"X-User-Id": "attacker", "X-User-Role": "admin"},
            api_keys=["real-key"],
            storage=storage,
        )
        # Session headers are ignored (untrusted IP). No API key → 401.
        with pytest.raises(HTTPException) as exc_info:
            await require_admin(request=req, api_key=None)
        assert exc_info.value.status_code in (401, 403)


# ---------------------------------------------------------------------------
# HTTP endpoint layer — admin routes reject non-admins
# ---------------------------------------------------------------------------

class TestAdminEndpointsViaHttp:
    async def test_create_api_key_requires_valid_key(self, auth_client) -> None:
        """POST /api/auth/api-keys with no key → 401."""
        c, _, _ = auth_client
        response = await c.post(
            "/api/auth/api-keys",
            json={"name": "new-key", "role": "viewer"},
        )
        assert response.status_code in (401, 403)

    async def test_list_api_keys_requires_valid_key(self, auth_client) -> None:
        c, _, _ = auth_client
        response = await c.get("/api/auth/api-keys")
        assert response.status_code in (401, 403)

    async def test_create_api_key_with_valid_admin_key_succeeds(self, auth_client) -> None:
        """Env key (admin) can create new API keys."""
        c, mock_storage, _ = auth_client
        mock_storage.create_api_key = AsyncMock()
        mock_storage.list_api_keys = AsyncMock(return_value=[])

        response = await c.post(
            "/api/auth/api-keys",
            json={"name": "ci-key", "role": "viewer"},
            headers={"X-API-Key": "test-api-key"},
        )
        assert response.status_code == 201

    async def test_create_slo_requires_valid_key(self, auth_client) -> None:
        c, _, _ = auth_client
        response = await c.post(
            "/api/slos",
            json={
                "agent_name": "my-agent",
                "metric": "success_rate",
                "target": 99.0,
                "window_hours": 24,
            },
        )
        assert response.status_code in (401, 403)

    async def test_create_slo_with_valid_admin_key_succeeds(self, auth_client) -> None:
        c, mock_storage, _ = auth_client
        mock_storage.create_slo = AsyncMock()
        mock_storage.list_slos = AsyncMock(return_value=[])

        response = await c.post(
            "/api/slos",
            json={
                "agent_name": "my-agent",
                "metric": "success_rate",
                "target": 99.0,
                "window_hours": 24,
            },
            headers={"X-API-Key": "test-api-key"},
        )
        assert response.status_code == 201
