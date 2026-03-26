"""
Unit tests for get_active_project_id — project-scoping / tenant-isolation (v0.8.1).

Covers every priority branch in the function's resolution order:
  1. API key's project_id (project-scoped DB key) — always wins
  2. .langsight.yaml project_id field
  3. project_id query parameter
  4. Global admin / auth-disabled → None (sees all)
  5. Non-admin without project_id → HTTP 400

All tests run offline — no Docker, no real DB, no network.
"""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Test helpers (mirror security/conftest helpers, kept local to stay readable)
# ---------------------------------------------------------------------------


def _make_storage(
    *,
    db_keys: list | None = None,
    key_by_hash: object | None = None,
) -> MagicMock:
    """Minimal storage mock with list_members present (enables project logic)."""
    storage = MagicMock()
    storage.list_members = AsyncMock(return_value=[])
    storage.list_api_keys = AsyncMock(return_value=db_keys or [])
    storage.get_api_key_by_hash = AsyncMock(return_value=key_by_hash)
    storage.get_member = AsyncMock(return_value=None)
    return storage


def _make_request(
    *,
    client_ip: str = "10.0.0.1",
    headers: dict[str, str] | None = None,
    env_keys: list[str] | None = None,
    storage: object | None = None,
    config_project_id: str | None = None,
) -> MagicMock:
    """Build a minimal Request-like object for testing get_active_project_id."""
    from langsight.api.dependencies import parse_trusted_proxy_networks

    request = MagicMock()
    request.client = MagicMock()
    request.client.host = client_ip

    raw_headers: dict[str, str] = headers or {}
    request.headers = MagicMock()
    request.headers.get = lambda key, default=None: raw_headers.get(key, default)

    request.url = MagicMock()
    request.url.path = "/api/test"
    request.method = "GET"

    cfg = MagicMock()
    cfg.project_id = config_project_id if config_project_id is not None else ""

    app_state = MagicMock()
    app_state.api_keys = env_keys or []
    app_state.storage = storage or _make_storage()
    app_state.config = cfg
    app_state.trusted_proxy_networks = parse_trusted_proxy_networks("127.0.0.1/32,::1/128")

    request.app = MagicMock()
    request.app.state = app_state
    return request


def _db_key_record(
    *,
    raw_key: str,
    project_id: str | None = None,
    is_expired: bool = False,
    role: str = "viewer",
) -> MagicMock:
    """Build a mock ApiKeyRecord with configurable project_id / expiry."""
    from langsight.models import ApiKeyRole

    rec = MagicMock()
    rec.id = "key-id-1"
    rec.key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    rec.project_id = project_id
    rec.is_revoked = False
    rec.is_expired = is_expired
    rec.user_id = None
    rec.role = ApiKeyRole.ADMIN if role == "admin" else ApiKeyRole.VIEWER
    return rec


# ---------------------------------------------------------------------------
# Priority 1: project-scoped DB key always wins
# ---------------------------------------------------------------------------


class TestProjectScopedKeyPriority:
    async def test_project_scoped_key_overrides_query_param(self) -> None:
        """Key has project_id='proj-a', query param='proj-b' → returns 'proj-a'.

        The API key's project_id is the highest-priority source.  A caller
        cannot override it by also providing a query parameter.
        """
        from langsight.api.dependencies import get_active_project_id

        raw_key = "scoped-key-abc"
        record = _db_key_record(raw_key=raw_key, project_id="proj-a")
        storage = _make_storage(db_keys=[record], key_by_hash=record)

        req = _make_request(
            client_ip="10.0.0.1",
            headers={"X-API-Key": raw_key},
            env_keys=[],
            storage=storage,
        )
        result = await get_active_project_id(request=req, project_id="proj-b")
        assert result == "proj-a"

    async def test_project_scoped_key_overrides_config_project(self) -> None:
        """Key has project_id set; config also has project_id → key wins.

        Priority 1 (key) must beat Priority 2 (config file).
        """
        from langsight.api.dependencies import get_active_project_id

        raw_key = "scoped-key-xyz"
        record = _db_key_record(raw_key=raw_key, project_id="key-project")
        storage = _make_storage(db_keys=[record], key_by_hash=record)

        req = _make_request(
            client_ip="10.0.0.1",
            headers={"X-API-Key": raw_key},
            env_keys=[],
            storage=storage,
            config_project_id="config-project",
        )
        result = await get_active_project_id(request=req, project_id=None)
        assert result == "key-project"

    async def test_project_scoped_key_overrides_query_param_and_config(self) -> None:
        """Key project_id beats both query param AND config.project_id simultaneously."""
        from langsight.api.dependencies import get_active_project_id

        raw_key = "scoped-key-triple"
        record = _db_key_record(raw_key=raw_key, project_id="winner")
        storage = _make_storage(db_keys=[record], key_by_hash=record)

        req = _make_request(
            client_ip="10.0.0.1",
            headers={"X-API-Key": raw_key},
            env_keys=[],
            storage=storage,
            config_project_id="config-side",
        )
        result = await get_active_project_id(request=req, project_id="query-side")
        assert result == "winner"


# ---------------------------------------------------------------------------
# Priority 2: .langsight.yaml project_id
# ---------------------------------------------------------------------------


class TestConfigProjectIdPriority:
    async def test_config_project_id_used_when_key_unscoped(self) -> None:
        """Key has no project_id; config.project_id='abc' → returns 'abc'."""
        from langsight.api.dependencies import get_active_project_id

        raw_key = "unscoped-key"
        record = _db_key_record(raw_key=raw_key, project_id=None)
        storage = _make_storage(db_keys=[record], key_by_hash=record)

        req = _make_request(
            client_ip="10.0.0.1",
            headers={"X-API-Key": raw_key},
            env_keys=[],
            storage=storage,
            config_project_id="abc",
        )
        result = await get_active_project_id(request=req, project_id=None)
        assert result == "abc"

    async def test_config_project_id_beats_query_param_when_key_unscoped(self) -> None:
        """Config project_id (priority 2) beats query param (priority 3)."""
        from langsight.api.dependencies import get_active_project_id

        raw_key = "unscoped-key-2"
        record = _db_key_record(raw_key=raw_key, project_id=None)
        storage = _make_storage(db_keys=[record], key_by_hash=record)

        req = _make_request(
            client_ip="10.0.0.1",
            headers={"X-API-Key": raw_key},
            env_keys=[],
            storage=storage,
            config_project_id="config-wins",
        )
        result = await get_active_project_id(request=req, project_id="query-loses")
        assert result == "config-wins"

    async def test_empty_config_project_id_does_not_win(self) -> None:
        """config.project_id='' (default) must NOT be used as a project scope.

        An empty string means 'not set' — fall through to lower priority.
        """
        from langsight.api.dependencies import get_active_project_id

        storage = _make_storage(db_keys=[])

        req = _make_request(
            client_ip="10.0.0.1",
            headers={"X-API-Key": "env-admin"},
            env_keys=["env-admin"],
            storage=storage,
            config_project_id="",  # empty — must be treated as not set
        )
        # Admin with no project → should return None, not ""
        result = await get_active_project_id(request=req, project_id=None)
        assert result is None


# ---------------------------------------------------------------------------
# Priority 3: explicit project_id query parameter
# ---------------------------------------------------------------------------


class TestQueryParamFallthrough:
    async def test_unscoped_key_falls_through_to_query_param(self) -> None:
        """Key has no project_id, query param provided → returns query param."""
        from langsight.api.dependencies import get_active_project_id

        raw_key = "unscoped-key-q"
        record = _db_key_record(raw_key=raw_key, project_id=None)
        storage = _make_storage(db_keys=[record], key_by_hash=record)
        # Make the key look like admin so membership check passes
        record.role = __import__("langsight.models", fromlist=["ApiKeyRole"]).ApiKeyRole.ADMIN

        req = _make_request(
            client_ip="10.0.0.1",
            headers={"X-API-Key": raw_key},
            env_keys=[],
            storage=storage,
        )
        result = await get_active_project_id(request=req, project_id="query-proj")
        assert result == "query-proj"


# ---------------------------------------------------------------------------
# Priority 4: admin / auth-disabled → None
# ---------------------------------------------------------------------------


class TestAdminAndAuthDisabled:
    async def test_admin_key_no_project_returns_none(self) -> None:
        """Env-var key (always admin) + no project_id → returns None (sees all).

        Admins should never be forced to supply a project_id.
        """
        from langsight.api.dependencies import get_active_project_id

        storage = _make_storage(db_keys=[])
        req = _make_request(
            client_ip="10.0.0.1",
            headers={"X-API-Key": "bootstrap-admin"},
            env_keys=["bootstrap-admin"],
            storage=storage,
        )
        result = await get_active_project_id(request=req, project_id=None)
        assert result is None

    async def test_auth_disabled_returns_none(self) -> None:
        """No keys configured anywhere → open install, returns None."""
        from langsight.api.dependencies import get_active_project_id

        storage = _make_storage(db_keys=[])
        req = _make_request(
            client_ip="10.0.0.1",
            headers={},
            env_keys=[],
            storage=storage,
        )
        result = await get_active_project_id(request=req, project_id=None)
        assert result is None

    async def test_session_admin_no_project_returns_none(self) -> None:
        """Session user with role=admin + no project_id → None."""
        from langsight.api.dependencies import get_active_project_id

        storage = _make_storage(db_keys=[])
        req = _make_request(
            client_ip="127.0.0.1",  # loopback = trusted proxy
            headers={"X-User-Id": "admin-user", "X-User-Role": "admin"},
            env_keys=["some-env-key"],
            storage=storage,
        )
        result = await get_active_project_id(request=req, project_id=None)
        assert result is None


# ---------------------------------------------------------------------------
# Priority 5: non-admin without project_id → HTTP 400
# ---------------------------------------------------------------------------


class TestNonAdminRequiresProjectId:
    async def test_non_admin_no_project_raises_400(self) -> None:
        """DB key (viewer), no project_id on key, no query param → HTTP 400.

        A non-admin caller must supply a project_id. Returning None would
        expose all-project data.
        """
        from langsight.api.dependencies import get_active_project_id

        raw_key = "viewer-key-1"
        record = _db_key_record(raw_key=raw_key, project_id=None, role="viewer")
        storage = _make_storage(db_keys=[record], key_by_hash=record)

        req = _make_request(
            client_ip="10.0.0.1",
            headers={"X-API-Key": raw_key},
            env_keys=[],
            storage=storage,
        )
        with pytest.raises(HTTPException) as exc_info:
            await get_active_project_id(request=req, project_id=None)
        assert exc_info.value.status_code == 400
        assert "project_id" in exc_info.value.detail.lower()

    async def test_non_admin_no_project_error_message_helpful(self) -> None:
        """400 error message must mention project_id to guide the caller."""
        from langsight.api.dependencies import get_active_project_id

        raw_key = "viewer-key-msg"
        record = _db_key_record(raw_key=raw_key, project_id=None, role="viewer")
        storage = _make_storage(db_keys=[record], key_by_hash=record)

        req = _make_request(
            client_ip="10.0.0.1",
            headers={"X-API-Key": raw_key},
            env_keys=[],
            storage=storage,
        )
        with pytest.raises(HTTPException) as exc_info:
            await get_active_project_id(request=req, project_id=None)
        # Must be actionable — not just a generic error
        assert "project_id" in exc_info.value.detail


# ---------------------------------------------------------------------------
# Env-var keys are always global admin (never project-scoped)
# ---------------------------------------------------------------------------


class TestEnvKeyIsNotProjectScoped:
    async def test_env_key_is_not_project_scoped(self) -> None:
        """Env-var keys are always global admin — never project-scoped.

        Even if the DB has a key record with project_id, env-var keys skip the
        DB lookup path entirely and return None (global admin) when no query
        param is provided.
        """
        from langsight.api.dependencies import get_active_project_id

        env_key = "env-bootstrap-key"
        # DB has a key record with project_id set — but env key must bypass DB
        db_record = _db_key_record(raw_key=env_key, project_id="should-not-be-returned")
        storage = _make_storage(db_keys=[db_record], key_by_hash=db_record)

        req = _make_request(
            client_ip="10.0.0.1",
            headers={"X-API-Key": env_key},
            env_keys=[env_key],  # same key is also an env var key
            storage=storage,
        )
        result = await get_active_project_id(request=req, project_id=None)
        # Env key → admin → no project filter
        assert result is None

    async def test_env_key_with_query_param_returns_query_param(self) -> None:
        """Env-var admin key + explicit project_id query param → returns query param."""
        from langsight.api.dependencies import get_active_project_id

        env_key = "env-key-with-qp"
        storage = _make_storage(db_keys=[])

        req = _make_request(
            client_ip="10.0.0.1",
            headers={"X-API-Key": env_key},
            env_keys=[env_key],
            storage=storage,
        )
        result = await get_active_project_id(request=req, project_id="explicit-project")
        assert result == "explicit-project"


# ---------------------------------------------------------------------------
# Expired key — project_id from key must be ignored
# ---------------------------------------------------------------------------


class TestExpiredKeyNotUsedForScoping:
    async def test_expired_key_rejected_by_verify_api_key_before_project_scoping(
        self,
    ) -> None:
        """verify_api_key rejects an expired key with 403 before project scoping occurs.

        The security gate (verify_api_key) must fire before get_active_project_id
        is ever called.  This test verifies that the expired-key rejection happens
        at the auth layer, not the project layer.
        """
        from langsight.api.dependencies import verify_api_key

        raw_key = "expired-key"
        expired_record = _db_key_record(
            raw_key=raw_key,
            project_id="secret-project",
            is_expired=True,
        )
        storage = _make_storage(db_keys=[expired_record], key_by_hash=expired_record)

        req = _make_request(
            client_ip="10.0.0.1",
            headers={"X-API-Key": raw_key},
            env_keys=[],
            storage=storage,
        )
        # verify_api_key must 403 before the caller reaches project resolution
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(request=req, api_key=raw_key)
        assert exc_info.value.status_code == 403
        assert "expired" in exc_info.value.detail.lower()

    async def test_expired_key_get_active_project_id_uses_key_project_when_reached(
        self,
    ) -> None:
        """When get_active_project_id is called with an expired-key record it still
        returns the project_id from the record — because the expiry check is
        deliberately placed in verify_api_key (the auth gate), not here.

        This test documents the actual behaviour: the expiry guard runs in
        verify_api_key BEFORE the request reaches get_active_project_id.
        If for any reason the auth gate is bypassed, the project_id is used.
        """
        from langsight.api.dependencies import get_active_project_id

        raw_key = "expired-key-2"
        expired_record = _db_key_record(
            raw_key=raw_key,
            project_id="expired-project",
            is_expired=True,
        )
        storage = _make_storage(db_keys=[expired_record], key_by_hash=expired_record)

        req = _make_request(
            client_ip="10.0.0.1",
            headers={"X-API-Key": raw_key},
            env_keys=[],
            storage=storage,
        )
        # get_active_project_id does NOT re-check is_expired — it relies on
        # verify_api_key having already blocked the request.  The function
        # returns the key's project_id if the record has one.
        result = await get_active_project_id(request=req, project_id=None)
        # In practice this path is never reached because verify_api_key
        # would have raised 403 first.  This assertion documents the behaviour.
        assert result == "expired-project"


# ---------------------------------------------------------------------------
# Storage without project support — passthrough behaviour
# ---------------------------------------------------------------------------


class TestStorageWithoutProjectSupport:
    async def test_storage_without_list_members_passes_through(self) -> None:
        """When storage has no list_members attribute, project_id passes through unchanged.

        This preserves backward compatibility with simpler storage backends
        (e.g. SQLite-only mode) that don't support multi-tenancy.
        """
        from langsight.api.dependencies import get_active_project_id

        storage = MagicMock(spec=[])  # no attributes at all
        req = _make_request(
            client_ip="10.0.0.1",
            headers={},
            env_keys=[],
            storage=storage,
        )
        result = await get_active_project_id(request=req, project_id="some-proj")
        assert result == "some-proj"

    async def test_storage_without_list_members_passes_none_through(self) -> None:
        """None project_id also passes through when storage has no project support."""
        from langsight.api.dependencies import get_active_project_id

        storage = MagicMock(spec=[])
        req = _make_request(
            client_ip="10.0.0.1",
            headers={},
            env_keys=[],
            storage=storage,
        )
        result = await get_active_project_id(request=req, project_id=None)
        assert result is None
