"""
Unit tests for Phase 9 auth changes in src/langsight/api/dependencies.py

Covers:
- _is_proxy_request(): trusted vs untrusted IPs
- _get_session_user(): header extraction gated by proxy IP
- verify_api_key(): session headers accepted as auth; 401 when keys configured and headers absent
- require_admin(): session role=admin passes; session role=viewer raises 403
- get_active_project_id(): no project_id returns None; admin passes; non-member raises 404
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Request

from langsight.api.dependencies import (
    _get_session_user,
    _is_proxy_request,
    get_active_project_id,
    require_admin,
    verify_api_key,
)
from langsight.models import ApiKeyRole

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_request(
    client_ip: str = "127.0.0.1",
    headers: dict[str, str] | None = None,
    api_keys: list[str] | None = None,
    storage: object | None = None,
) -> Request:
    """Build a minimal FastAPI Request-like object for dependency testing."""
    request = MagicMock(spec=Request)
    request.client = MagicMock()
    request.client.host = client_ip

    all_headers = headers or {}
    request.headers = MagicMock()
    request.headers.get = lambda key, default=None: all_headers.get(key, default)

    request.url = MagicMock()
    request.url.path = "/api/test"
    request.method = "GET"

    # App state
    app_state = MagicMock()
    app_state.api_keys = api_keys or []
    app_state.storage = storage or MagicMock()
    # Explicitly set to None so _is_proxy_request falls back to default loopback CIDRs
    app_state.trusted_proxy_networks = None
    request.app = MagicMock()
    request.app.state = app_state

    return request


# ---------------------------------------------------------------------------
# _is_proxy_request
# ---------------------------------------------------------------------------

class TestIsProxyRequest:
    def test_returns_true_for_loopback_ipv4(self) -> None:
        req = _make_request(client_ip="127.0.0.1")
        assert _is_proxy_request(req) is True

    def test_returns_true_for_ipv6_loopback(self) -> None:
        req = _make_request(client_ip="::1")
        assert _is_proxy_request(req) is True

    def test_returns_true_for_localhost_string(self) -> None:
        req = _make_request(client_ip="localhost")
        assert _is_proxy_request(req) is True

    def test_returns_false_for_external_ip(self) -> None:
        req = _make_request(client_ip="10.0.0.5")
        assert _is_proxy_request(req) is False

    def test_returns_false_for_public_ip(self) -> None:
        req = _make_request(client_ip="203.0.113.42")
        assert _is_proxy_request(req) is False

    def test_returns_false_when_client_is_none(self) -> None:
        req = _make_request()
        req.client = None
        assert _is_proxy_request(req) is False


# ---------------------------------------------------------------------------
# _get_session_user
# ---------------------------------------------------------------------------

def _sign_proxy_headers(user_id: str, user_role: str, secret: str) -> dict[str, str]:
    """Generate HMAC-signed proxy headers for testing."""
    import hashlib
    import hmac
    import time

    ts = str(int(time.time()))
    payload = f"{user_id}:{user_role}:{ts}"
    sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return {
        "X-User-Id": user_id,
        "X-User-Role": user_role,
        "X-Proxy-Timestamp": ts,
        "X-Proxy-Signature": sig,
    }


_TEST_PROXY_SECRET = "test-secret-for-unit-tests-32chars!"


class TestGetSessionUser:
    def test_returns_user_id_and_role_from_proxy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LANGSIGHT_PROXY_SECRET", _TEST_PROXY_SECRET)
        headers = _sign_proxy_headers("user-abc", "admin", _TEST_PROXY_SECRET)
        req = _make_request(client_ip="127.0.0.1", headers=headers)
        user_id, role = _get_session_user(req)
        assert user_id == "user-abc"
        assert role == "admin"

    def test_returns_none_when_hmac_not_configured(self) -> None:
        """Without LANGSIGHT_PROXY_SECRET, proxy auth is disabled (fail-closed)."""
        req = _make_request(
            client_ip="127.0.0.1",
            headers={"X-User-Id": "user-abc", "X-User-Role": "admin"},
        )
        user_id, role = _get_session_user(req)
        assert user_id is None
        assert role is None

    def test_returns_none_none_when_ip_not_trusted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Headers present but IP is external — must be ignored."""
        monkeypatch.setenv("LANGSIGHT_PROXY_SECRET", _TEST_PROXY_SECRET)
        headers = _sign_proxy_headers("user-abc", "admin", _TEST_PROXY_SECRET)
        req = _make_request(client_ip="10.0.0.5", headers=headers)
        user_id, role = _get_session_user(req)
        assert user_id is None
        assert role is None

    def test_returns_none_none_when_headers_absent(self) -> None:
        req = _make_request(client_ip="127.0.0.1", headers={})
        user_id, role = _get_session_user(req)
        assert user_id is None
        assert role is None

    def test_returns_none_for_empty_header_values(self) -> None:
        req = _make_request(
            client_ip="127.0.0.1",
            headers={"X-User-Id": "", "X-User-Role": ""},
        )
        user_id, role = _get_session_user(req)
        assert user_id is None
        assert role is None

    def test_viewer_role_forwarded_correctly(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LANGSIGHT_PROXY_SECRET", _TEST_PROXY_SECRET)
        headers = _sign_proxy_headers("user-xyz", "viewer", _TEST_PROXY_SECRET)
        req = _make_request(client_ip="::1", headers=headers)
        user_id, role = _get_session_user(req)
        assert user_id == "user-xyz"
        assert role == "viewer"


# ---------------------------------------------------------------------------
# verify_api_key
# ---------------------------------------------------------------------------

class TestVerifyApiKey:
    async def test_session_headers_from_proxy_bypass_key_check(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Valid HMAC-signed proxy session headers are sufficient — no API key needed."""
        monkeypatch.setenv("LANGSIGHT_PROXY_SECRET", _TEST_PROXY_SECRET)
        storage = MagicMock()
        headers = _sign_proxy_headers("user-1", "admin", _TEST_PROXY_SECRET)
        req = _make_request(
            client_ip="127.0.0.1",
            headers=headers,
            api_keys=["some-key"],
            storage=storage,
        )
        # Should not raise
        await verify_api_key(request=req, api_key=None)

    async def test_missing_session_and_no_keys_configured_passes(self) -> None:
        """Auth fully disabled when no keys are configured — local dev mode."""
        storage = MagicMock()
        # list_api_keys returns empty list
        storage.list_api_keys = AsyncMock(return_value=[])
        req = _make_request(
            client_ip="10.0.0.1",
            headers={},
            api_keys=[],
            storage=storage,
        )
        # Should not raise
        await verify_api_key(request=req, api_key=None)

    async def test_missing_key_raises_401_when_env_keys_configured(self) -> None:
        """No session, no API key, but env keys exist → 401."""
        from fastapi import HTTPException

        storage = MagicMock()
        storage.list_api_keys = AsyncMock(return_value=[])
        req = _make_request(
            client_ip="10.0.0.1",
            headers={},
            api_keys=["real-key"],
            storage=storage,
        )
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(request=req, api_key=None)
        assert exc_info.value.status_code == 401

    async def test_valid_env_key_passes(self) -> None:
        """A key present in env_keys passes without DB lookup."""
        storage = MagicMock()
        storage.list_api_keys = AsyncMock(return_value=[])
        req = _make_request(
            client_ip="10.0.0.1",
            headers={},
            api_keys=["secret-bootstrap-key"],
            storage=storage,
        )
        # Should not raise
        await verify_api_key(request=req, api_key="secret-bootstrap-key")

    async def test_invalid_key_raises_403(self) -> None:
        """A key that matches neither env nor DB → 403."""
        from fastapi import HTTPException

        storage = MagicMock()
        storage.list_api_keys = AsyncMock(return_value=[])
        storage.get_api_key_by_hash = AsyncMock(return_value=None)
        req = _make_request(
            client_ip="10.0.0.1",
            headers={},
            api_keys=["correct-key"],
            storage=storage,
        )
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(request=req, api_key="wrong-key")
        assert exc_info.value.status_code == 403

    async def test_valid_db_key_passes(self) -> None:
        """A key matching a DB record passes."""
        import hashlib

        raw_key = "db-stored-key"
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

        db_key_record = MagicMock()
        db_key_record.id = "key-id-1"
        db_key_record.is_revoked = False
        db_key_record.is_expired = False

        storage = MagicMock()
        storage.list_api_keys = AsyncMock(return_value=[db_key_record])
        storage.get_api_key_by_hash = AsyncMock(return_value=db_key_record)
        storage.touch_api_key = AsyncMock()

        req = _make_request(
            client_ip="10.0.0.1",
            headers={},
            api_keys=[],
            storage=storage,
        )
        # Should not raise
        await verify_api_key(request=req, api_key=raw_key)
        storage.get_api_key_by_hash.assert_called_once_with(key_hash)


# ---------------------------------------------------------------------------
# require_admin
# ---------------------------------------------------------------------------

class TestRequireAdmin:
    async def test_session_admin_role_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LANGSIGHT_PROXY_SECRET", _TEST_PROXY_SECRET)
        storage = MagicMock()
        storage.list_api_keys = AsyncMock(return_value=[])
        # DB check: user is still active admin
        storage.get_user_by_id = AsyncMock(return_value=MagicMock(
            active=True, role=MagicMock(value="admin")
        ))
        headers = _sign_proxy_headers("user-1", "admin", _TEST_PROXY_SECRET)
        req = _make_request(
            client_ip="127.0.0.1",
            headers=headers,
            api_keys=["some-key"],
            storage=storage,
        )
        # Should not raise
        await require_admin(request=req, api_key=None)

    async def test_session_viewer_role_raises_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A session with role=viewer must be blocked from write operations."""
        from fastapi import HTTPException

        monkeypatch.setenv("LANGSIGHT_PROXY_SECRET", _TEST_PROXY_SECRET)
        storage = MagicMock()
        headers = _sign_proxy_headers("user-1", "viewer", _TEST_PROXY_SECRET)
        req = _make_request(
            client_ip="127.0.0.1",
            headers=headers,
            api_keys=["some-key"],
            storage=storage,
        )
        with pytest.raises(HTTPException) as exc_info:
            await require_admin(request=req, api_key=None)
        assert exc_info.value.status_code == 403

    async def test_no_auth_configured_passes(self) -> None:
        """Auth disabled (no keys at all) — require_admin allows everything."""
        storage = MagicMock()
        storage.list_api_keys = AsyncMock(return_value=[])
        req = _make_request(
            client_ip="10.0.0.1",
            headers={},
            api_keys=[],
            storage=storage,
        )
        # Should not raise
        await require_admin(request=req, api_key=None)

    async def test_env_key_is_always_admin(self) -> None:
        """Env-var bootstrap keys are always treated as admin."""
        storage = MagicMock()
        storage.list_api_keys = AsyncMock(return_value=[])
        req = _make_request(
            client_ip="10.0.0.1",
            headers={},
            api_keys=["bootstrap-key"],
            storage=storage,
        )
        # Should not raise
        await require_admin(request=req, api_key="bootstrap-key")

    async def test_db_viewer_key_raises_403(self) -> None:
        """A DB key with role=viewer attempting a write → 403."""
        import hashlib

        from fastapi import HTTPException

        raw_key = "viewer-key"
        hashlib.sha256(raw_key.encode()).hexdigest()

        viewer_record = MagicMock()
        viewer_record.role = ApiKeyRole.VIEWER
        viewer_record.is_revoked = False

        storage = MagicMock()
        storage.list_api_keys = AsyncMock(return_value=[viewer_record])
        storage.get_api_key_by_hash = AsyncMock(return_value=viewer_record)

        req = _make_request(
            client_ip="10.0.0.1",
            headers={},
            api_keys=[],
            storage=storage,
        )
        with pytest.raises(HTTPException) as exc_info:
            await require_admin(request=req, api_key=raw_key)
        assert exc_info.value.status_code == 403

    async def test_db_admin_key_passes(self) -> None:
        """A DB key with role=admin passes require_admin."""

        raw_key = "admin-db-key"

        admin_record = MagicMock()
        admin_record.role = ApiKeyRole.ADMIN
        admin_record.is_revoked = False

        storage = MagicMock()
        storage.list_api_keys = AsyncMock(return_value=[admin_record])
        storage.get_api_key_by_hash = AsyncMock(return_value=admin_record)

        req = _make_request(
            client_ip="10.0.0.1",
            headers={},
            api_keys=[],
            storage=storage,
        )
        # Should not raise
        await require_admin(request=req, api_key=raw_key)

    async def test_missing_key_with_auth_enabled_raises_401(self) -> None:
        """No key provided when auth is enabled → 401 (not 403)."""
        from fastapi import HTTPException

        storage = MagicMock()
        storage.list_api_keys = AsyncMock(return_value=[])
        req = _make_request(
            client_ip="10.0.0.1",
            headers={},
            api_keys=["env-key"],
            storage=storage,
        )
        with pytest.raises(HTTPException) as exc_info:
            await require_admin(request=req, api_key=None)
        assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# get_active_project_id
# ---------------------------------------------------------------------------

class TestGetActiveProjectId:
    async def test_returns_none_when_no_project_id_provided(self) -> None:
        req = _make_request()
        result = await get_active_project_id(request=req, project_id=None)
        assert result is None

    async def test_admin_session_returns_project_id_without_membership_check(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LANGSIGHT_PROXY_SECRET", _TEST_PROXY_SECRET)
        storage = MagicMock()
        storage.list_members = AsyncMock(return_value=[])
        # DB check for admin verification
        storage.get_user_by_id = AsyncMock(return_value=MagicMock(
            active=True, role=MagicMock(value="admin")
        ))
        headers = _sign_proxy_headers("admin-user", "admin", _TEST_PROXY_SECRET)
        req = _make_request(
            client_ip="127.0.0.1",
            headers=headers,
            api_keys=["key"],
            storage=storage,
        )
        result = await get_active_project_id(request=req, project_id="proj-1")
        assert result == "proj-1"

    async def test_member_session_returns_project_id_when_membership_exists(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LANGSIGHT_PROXY_SECRET", _TEST_PROXY_SECRET)
        member_record = MagicMock()
        storage = MagicMock()
        storage.list_members = AsyncMock(return_value=[member_record])
        storage.get_member = AsyncMock(return_value=member_record)
        headers = _sign_proxy_headers("viewer-user", "viewer", _TEST_PROXY_SECRET)
        req = _make_request(
            client_ip="127.0.0.1",
            headers=headers,
            api_keys=["key"],
            storage=storage,
        )
        result = await get_active_project_id(request=req, project_id="proj-1")
        assert result == "proj-1"

    async def test_non_member_session_raises_404(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A session user who is not a member of the project → 404."""
        from fastapi import HTTPException

        monkeypatch.setenv("LANGSIGHT_PROXY_SECRET", _TEST_PROXY_SECRET)
        storage = MagicMock()
        storage.list_members = AsyncMock(return_value=[MagicMock()])  # list_members present
        storage.get_member = AsyncMock(return_value=None)  # user is NOT a member
        headers = _sign_proxy_headers("outsider", "viewer", _TEST_PROXY_SECRET)
        req = _make_request(
            client_ip="127.0.0.1",
            headers=headers,
            api_keys=["key"],
            storage=storage,
        )
        with pytest.raises(HTTPException) as exc_info:
            await get_active_project_id(request=req, project_id="proj-secret")
        assert exc_info.value.status_code == 404

    async def test_storage_without_list_members_returns_project_id(self) -> None:
        """When storage has no list_members (ClickHouse), allow the project_id through."""
        storage = MagicMock(spec=[])  # no list_members attribute
        req = _make_request(
            client_ip="10.0.0.1",
            headers={},
            api_keys=[],
            storage=storage,
        )
        result = await get_active_project_id(request=req, project_id="any-project")
        assert result == "any-project"

    async def test_auth_disabled_returns_project_id(self) -> None:
        """No keys configured at all — auth disabled — any project_id passes through."""
        storage = MagicMock()
        storage.list_members = AsyncMock(return_value=[])
        req = _make_request(
            client_ip="10.0.0.1",
            headers={},
            api_keys=[],  # no env keys
            storage=storage,
        )
        result = await get_active_project_id(request=req, project_id="proj-x")
        assert result == "proj-x"

    async def test_env_key_admin_returns_project_id(self) -> None:
        """Env-var key is always global admin — project_id passes through."""
        storage = MagicMock()
        storage.list_members = AsyncMock(return_value=[MagicMock()])
        req = _make_request(
            client_ip="10.0.0.1",
            headers={"X-API-Key": "bootstrap-key"},
            api_keys=["bootstrap-key"],
            storage=storage,
        )
        result = await get_active_project_id(request=req, project_id="proj-y")
        assert result == "proj-y"
