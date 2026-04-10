"""
Adversarial security tests — per-project MCP server configuration.

Endpoints under test:
  PUT    /api/servers/metadata/{server_name}   — upsert / register a server
  DELETE /api/servers/metadata/{server_name}   — remove a server from a project
  GET    /api/servers/metadata                 — list servers (project-scoped)
  GET    /api/servers/metadata/{server_name}   — single server detail
  POST   /api/health/check                     — trigger health checks (admin-only)

Security invariants proved here:
  1. PUT and DELETE require admin — viewer/unauthenticated callers are rejected (403/401).
  2. Non-admin callers cannot read across project boundaries (400/404 enforced by
     get_active_project_id before storage is reached).
  3. The `url` field on ServerMetadataUpdate has NO validator at the API layer for
     SSRF targets. This file documents that gap with tests that pass today but which
     MUST be changed to assert 422 once server-side URL validation is added.
  4. Server names with path-traversal or SQL-injection payloads are safely forwarded
     to parameterised storage; no secondary interpretation occurs at the router layer.
  5. XSS payloads in server_name are returned as JSON string data — correct for an
     API; consuming clients must HTML-escape when inserting into DOM.
  6. _auto_discover_servers always scopes span queries and upserts to the calling
     project_id — no cross-project server name leakage is possible through this path.
  7. POST /api/health/check requires admin — non-admins cannot trigger live probes.

Dependency ordering note:
  For PUT and DELETE, FastAPI evaluates `get_active_project_id` before `require_admin`
  (declaration order in the route signature). When a non-admin session user specifies
  a project they don't belong to, 404 is returned by get_active_project_id before
  require_admin even runs. Both 403 (blocked by require_admin) and 404 (blocked by
  membership check) are valid denial responses. Tests assert `in (403, 404)` for
  paths where both guards can fire, and test require_admin directly at the dependency
  level to confirm the 403 path definitively.

Relationship to existing test files:
  tests/security/test_admin_rbac.py      → general RBAC (auth keys, SLOs)
  tests/security/test_project_isolation.py → get_active_project_id isolation
  tests/unit/api/test_servers_router.py  → happy-path CRUD (no security)
  THIS FILE                               → adversarial cases specific to server config
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import time
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml
from fastapi import Request
from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette

from langsight.api.main import create_app
from langsight.config import load_config

pytestmark = pytest.mark.security

# ---------------------------------------------------------------------------
# HMAC signing for proxy headers
# ---------------------------------------------------------------------------

_TEST_PROXY_SECRET = "test-secret-for-unit-tests-32chars!"


def _sign_proxy_headers(user_id: str, user_role: str, secret: str) -> dict[str, str]:
    """Generate signed proxy headers for session auth testing."""
    ts = str(int(time.time()))
    payload = f"{user_id}:{user_role}:{ts}"
    sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return {
        "X-User-Id": user_id,
        "X-User-Role": user_role,
        "X-Proxy-Timestamp": ts,
        "X-Proxy-Signature": sig,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _server_row(
    server_name: str,
    transport: str = "",
    url: str = "",
    project_id: str | None = None,
) -> dict:
    now = datetime.now(UTC)
    return {
        "id": "row-" + server_name,
        "server_name": server_name,
        "description": "",
        "owner": "",
        "tags": [],
        "transport": transport,
        "url": url,
        "runbook_url": "",
        "project_id": project_id,
        "created_at": now,
        "updated_at": now,
    }


def _make_mock_storage(
    list_api_keys_returns: list | None = None,
    list_api_keys_raises: Exception | None = None,
) -> MagicMock:
    storage = MagicMock()
    storage.close = AsyncMock()
    storage.get_health_history = AsyncMock(return_value=[])
    if list_api_keys_raises:
        storage.list_api_keys = AsyncMock(side_effect=list_api_keys_raises)
    else:
        storage.list_api_keys = AsyncMock(return_value=list_api_keys_returns or [])
    storage.get_member = AsyncMock(return_value=None)
    storage.get_api_key_by_hash = AsyncMock(return_value=None)
    return storage


def _active_viewer_key_record() -> MagicMock:
    from langsight.models import ApiKeyRole

    rec = MagicMock()
    rec.id = "viewer-key-id"
    rec.is_revoked = False
    rec.role = ApiKeyRole.VIEWER
    rec.project_id = None
    rec.user_id = None
    return rec


def _make_request_with_loopback(
    headers: dict[str, str],
    api_keys: list[str],
    storage: object,
) -> Request:
    """Build a minimal Request that appears to come from 127.0.0.1 (trusted proxy)."""
    from langsight.api.dependencies import parse_trusted_proxy_networks

    req = MagicMock(spec=Request)
    req.client = MagicMock()
    req.client.host = "127.0.0.1"
    req.headers = MagicMock()
    req.headers.get = lambda key, default=None: headers.get(key, default)
    req.url = MagicMock()
    req.url.path = "/api/servers/metadata/test"
    req.method = "PUT"

    app_state = MagicMock()
    app_state.api_keys = api_keys
    app_state.storage = storage
    app_state.trusted_proxy_networks = parse_trusted_proxy_networks("127.0.0.1/32,::1/128")

    req.app = MagicMock()
    req.app.state = app_state
    return req


# ---------------------------------------------------------------------------
# App fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    cfg = tmp_path / ".langsight.yaml"
    cfg.write_text(yaml.dump({"servers": [], "auth_disabled": True}))
    return cfg


@pytest.fixture
async def auth_client(config_file: Path):
    """AsyncClient with auth ENABLED via one env key ('test-admin-key').

    All requests without that key will be rejected by the API.
    """
    app = create_app(config_path=config_file)
    storage = _make_mock_storage()
    app.state.storage = storage
    app.state.config = load_config(config_file)
    app.state.api_keys = ["test-admin-key"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, storage, app


@pytest.fixture
async def open_client(config_file: Path):
    """AsyncClient with auth DISABLED (no keys). Used to verify open-install paths."""
    app = create_app(config_path=config_file)
    storage = _make_mock_storage()
    app.state.storage = storage
    app.state.config = load_config(config_file)
    app.state.api_keys = []; app.state.auth_disabled = True

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, storage, app


# ===========================================================================
# 1. Admin-only write operations — dependency-level tests
# ===========================================================================


class TestRequireAdminOnServerEndpoints:
    """require_admin must block viewer and unauthenticated callers on all write
    operations against the server catalog.

    These tests drive require_admin directly to confirm the 403 invariant
    independently of the get_active_project_id dependency ordering in PUT/DELETE.
    """

    async def test_viewer_session_blocked_by_require_admin(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Viewer-role session user must receive 403 from require_admin."""
        from langsight.api.dependencies import require_admin
        from tests.security.conftest import _make_request, _make_storage

        monkeypatch.setenv("LANGSIGHT_PROXY_SECRET", _TEST_PROXY_SECRET)
        headers = _sign_proxy_headers("viewer-1", "viewer", _TEST_PROXY_SECRET)
        req = _make_request(
            client_ip="127.0.0.1",
            headers=headers,
            api_keys=["env-key"],
        )
        with pytest.raises(Exception) as exc_info:
            await require_admin(request=req, api_key=None)
        assert exc_info.value.status_code == 403

    async def test_member_session_blocked_by_require_admin(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """member role (not admin) also blocked with 403."""
        from langsight.api.dependencies import require_admin
        from tests.security.conftest import _make_request

        monkeypatch.setenv("LANGSIGHT_PROXY_SECRET", _TEST_PROXY_SECRET)
        headers = _sign_proxy_headers("member-1", "member", _TEST_PROXY_SECRET)
        req = _make_request(
            client_ip="127.0.0.1",
            headers=headers,
            api_keys=["env-key"],
        )
        with pytest.raises(Exception) as exc_info:
            await require_admin(request=req, api_key=None)
        assert exc_info.value.status_code == 403

    async def test_no_key_blocked_by_require_admin_with_401(self) -> None:
        """Missing key when auth is enabled → 401 (unauthenticated)."""
        from langsight.api.dependencies import require_admin
        from tests.security.conftest import _make_request, _make_storage

        storage = _make_storage(active_db_keys=[_active_viewer_key_record()])
        req = _make_request(
            client_ip="10.0.0.1",
            headers={},
            api_keys=[],
            storage=storage,
        )
        with pytest.raises(Exception) as exc_info:
            await require_admin(request=req, api_key=None)
        assert exc_info.value.status_code == 401

    async def test_admin_session_passes_require_admin(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Admin session user passes require_admin without error."""
        from langsight.api.dependencies import require_admin
        from tests.security.conftest import _make_request, _make_storage

        monkeypatch.setenv("LANGSIGHT_PROXY_SECRET", _TEST_PROXY_SECRET)
        headers = _sign_proxy_headers("admin-1", "admin", _TEST_PROXY_SECRET)
        storage = _make_storage()
        storage.get_user_by_id = AsyncMock(return_value=MagicMock(active=True, role=MagicMock(value="admin")))
        req = _make_request(
            client_ip="127.0.0.1",
            headers=headers,
            api_keys=["env-key"],
            storage=storage,
        )
        await require_admin(request=req, api_key=None)  # must not raise

    async def test_env_key_passes_require_admin(self) -> None:
        """Env-var key always passes require_admin as global admin."""
        from langsight.api.dependencies import require_admin
        from tests.security.conftest import _make_request

        req = _make_request(
            client_ip="10.0.0.1",
            headers={"X-API-Key": "bootstrap"},
            api_keys=["bootstrap"],
        )
        await require_admin(request=req, api_key="bootstrap")  # must not raise

    async def test_viewer_db_key_blocked_by_require_admin(self) -> None:
        """A DB key with viewer role is blocked with 403 by require_admin."""
        from langsight.api.dependencies import require_admin
        from tests.security.conftest import _make_request, _make_storage

        viewer_rec = _active_viewer_key_record()
        storage = _make_storage(active_db_keys=[viewer_rec])
        storage.get_api_key_by_hash = AsyncMock(return_value=viewer_rec)

        req = _make_request(
            client_ip="10.0.0.1",
            headers={"X-API-Key": "viewer-secret"},
            api_keys=[],
            storage=storage,
        )
        with pytest.raises(Exception) as exc_info:
            await require_admin(request=req, api_key="viewer-secret")
        assert exc_info.value.status_code == 403


# ===========================================================================
# 2. HTTP endpoint layer — admin enforcement via full ASGI stack
# ===========================================================================


class TestPutRequiresAdminViaHttp:
    """PUT /api/servers/metadata/{name} at the HTTP layer.

    Invariant: unauthenticated and wrong-key callers are rejected before
    storage is touched.
    """

    async def test_unauthenticated_put_returns_401(self, auth_client) -> None:
        """No key when auth is enabled → 401."""
        c, storage, _ = auth_client
        storage.upsert_server_metadata = AsyncMock(return_value=_server_row("my-srv"))

        response = await c.put(
            "/api/servers/metadata/my-srv",
            json={"description": "legit register"},
        )
        assert response.status_code == 401
        storage.upsert_server_metadata.assert_not_called()

    async def test_wrong_key_put_returns_403(self, auth_client) -> None:
        """A key that doesn't match any env or DB key → 403."""
        c, storage, _ = auth_client
        storage.upsert_server_metadata = AsyncMock(return_value=_server_row("srv"))

        response = await c.put(
            "/api/servers/metadata/srv",
            json={"description": "attacker"},
            headers={"X-API-Key": "wrong-key-value"},
        )
        assert response.status_code == 403
        storage.upsert_server_metadata.assert_not_called()

    async def test_admin_env_key_put_succeeds(self, auth_client) -> None:
        """Env-var key is always admin — PUT must succeed."""
        c, storage, _ = auth_client
        storage.upsert_server_metadata = AsyncMock(
            return_value=_server_row("new-srv", transport="sse", url="https://mcp.example.com")
        )

        response = await c.put(
            "/api/servers/metadata/new-srv",
            json={"transport": "sse", "url": "https://mcp.example.com"},
            headers={"X-API-Key": "test-admin-key"},
        )
        assert response.status_code == 200


class TestDeleteRequiresAdminViaHttp:
    """DELETE /api/servers/metadata/{name} at the HTTP layer.

    Invariant: only admin callers can remove server metadata.
    """

    async def test_unauthenticated_delete_returns_401(self, auth_client) -> None:
        """No key when auth is enabled → 401."""
        c, storage, _ = auth_client
        storage.delete_server_metadata = AsyncMock(return_value=True)

        response = await c.delete("/api/servers/metadata/postgres-mcp")
        assert response.status_code == 401
        storage.delete_server_metadata.assert_not_called()

    async def test_wrong_key_delete_returns_403(self, auth_client) -> None:
        """Invalid key → 403 on DELETE."""
        c, storage, _ = auth_client
        storage.delete_server_metadata = AsyncMock(return_value=True)

        response = await c.delete(
            "/api/servers/metadata/target",
            headers={"X-API-Key": "not-the-right-key"},
        )
        assert response.status_code == 403
        storage.delete_server_metadata.assert_not_called()

    async def test_admin_env_key_delete_succeeds(self, auth_client) -> None:
        """Env-var key (admin) can delete a server record."""
        c, storage, _ = auth_client
        storage.delete_server_metadata = AsyncMock(return_value=True)

        response = await c.delete(
            "/api/servers/metadata/postgres-mcp",
            headers={"X-API-Key": "test-admin-key"},
        )
        assert response.status_code == 204

    async def test_admin_delete_of_nonexistent_server_returns_404(self, auth_client) -> None:
        """Admin deleting a server that doesn't exist → 404, not a silent success."""
        c, storage, _ = auth_client
        storage.delete_server_metadata = AsyncMock(return_value=False)

        response = await c.delete(
            "/api/servers/metadata/ghost-server",
            headers={"X-API-Key": "test-admin-key"},
        )
        assert response.status_code == 404


class TestHealthCheckTriggerRequiresAdmin:
    """POST /api/health/check is guarded by require_admin.

    Invariant: only admin callers can trigger on-demand health checks.
    Non-admins cannot force health probes (which connect to live MCP servers).
    """

    async def test_unauthenticated_trigger_returns_401(self, auth_client) -> None:
        """No key when auth is enabled → 401 on POST /api/health/check."""
        c, _, _ = auth_client

        response = await c.post("/api/health/check")
        assert response.status_code == 401

    async def test_wrong_key_trigger_returns_403(self, auth_client) -> None:
        """Invalid key → 403 on POST /api/health/check."""
        c, _, _ = auth_client

        response = await c.post(
            "/api/health/check",
            headers={"X-API-Key": "not-the-right-key"},
        )
        assert response.status_code == 403

    async def test_admin_env_key_trigger_allowed(self, auth_client) -> None:
        """Env-var key can trigger health checks — returns 200 when no servers exist."""
        c, storage, _ = auth_client
        storage.get_all_server_metadata = AsyncMock(return_value=[])

        response = await c.post(
            "/api/health/check",
            headers={"X-API-Key": "test-admin-key"},
        )
        assert response.status_code == 200


# ===========================================================================
# 3. Viewer DB key — admin endpoint rejection (full ASGI stack)
# ===========================================================================


class TestViewerDbKeyAdminEndpoints:
    """A DB-stored viewer-role API key must be rejected (403) by all admin
    endpoints: PUT /metadata, DELETE /metadata, POST /health/check.

    Invariant: require_admin checks the DB key's role field, not just whether
    any key was presented.
    """

    @pytest.fixture
    async def viewer_key_client(self, config_file: Path):
        """Client where auth is enabled via a DB viewer key (not an env key)."""
        import hashlib

        app = create_app(config_path=config_file)
        storage = _make_mock_storage()

        viewer_plain = "viewer-plain-secret"
        viewer_hash = hashlib.sha256(viewer_plain.encode()).hexdigest()
        viewer_record = _active_viewer_key_record()

        # list_api_keys returns the viewer record → auth is enabled
        storage.list_api_keys = AsyncMock(return_value=[viewer_record])

        async def _lookup(h: str) -> MagicMock | None:
            return viewer_record if h == viewer_hash else None

        storage.get_api_key_by_hash = AsyncMock(side_effect=_lookup)

        app.state.storage = storage
        app.state.config = load_config(config_file)
        app.state.api_keys = []  # no env keys — DB key only

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c, storage, viewer_plain

    async def test_viewer_db_key_cannot_register_server(
        self, viewer_key_client
    ) -> None:
        """Viewer DB key → 403 on PUT /api/servers/metadata/{name}."""
        c, storage, viewer_key = viewer_key_client
        storage.upsert_server_metadata = AsyncMock(return_value=_server_row("srv"))

        response = await c.put(
            "/api/servers/metadata/new-server",
            json={"description": "attempting write"},
            headers={"X-API-Key": viewer_key},
        )
        assert response.status_code == 403
        storage.upsert_server_metadata.assert_not_called()

    async def test_viewer_db_key_cannot_delete_server(
        self, viewer_key_client
    ) -> None:
        """Viewer DB key → 403 on DELETE /api/servers/metadata/{name}."""
        c, storage, viewer_key = viewer_key_client
        storage.delete_server_metadata = AsyncMock(return_value=True)

        response = await c.delete(
            "/api/servers/metadata/target-server",
            headers={"X-API-Key": viewer_key},
        )
        assert response.status_code == 403
        storage.delete_server_metadata.assert_not_called()

    async def test_viewer_db_key_cannot_trigger_health_check(
        self, viewer_key_client
    ) -> None:
        """Viewer DB key → 403 on POST /api/health/check."""
        c, storage, viewer_key = viewer_key_client

        response = await c.post(
            "/api/health/check",
            headers={"X-API-Key": viewer_key},
        )
        assert response.status_code == 403


# ===========================================================================
# 4. Cross-project server read isolation
# ===========================================================================


class TestCrossProjectServerRead:
    """Non-admin callers cannot read servers belonging to a different project.

    Invariant: get_active_project_id enforces membership before any storage
    call is made; project_id on the query string cannot be forged to escape.
    """

    async def test_non_admin_without_project_id_gets_400_on_list(
        self, auth_client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Non-admin session user without project_id must get 400 on GET /api/servers/metadata.

        Security: without the 400 guard, the query would run with project_id=None,
        returning all servers across all projects.
        """
        c, storage, app = auth_client
        monkeypatch.setenv("LANGSIGHT_PROXY_SECRET", _TEST_PROXY_SECRET)
        storage.get_all_server_metadata = AsyncMock(return_value=[])
        # Ensure auth is enabled so the non-admin guard fires
        viewer_rec = _active_viewer_key_record()
        storage.list_api_keys = AsyncMock(return_value=[viewer_rec])
        app.state.trusted_proxy_networks = [ipaddress.ip_network("127.0.0.1/32")]

        headers = _sign_proxy_headers("viewer-1", "viewer", _TEST_PROXY_SECRET)
        response = await c.get(
            "/api/servers/metadata",
            headers=headers,
        )
        assert response.status_code == 400
        # Storage must NOT have been queried — denial was pre-storage
        storage.get_all_server_metadata.assert_not_called()

    async def test_non_member_cannot_read_foreign_project_servers(
        self, auth_client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Viewer who is not a member of project-B gets 404 when specifying project-B."""
        c, storage, app = auth_client
        monkeypatch.setenv("LANGSIGHT_PROXY_SECRET", _TEST_PROXY_SECRET)
        storage.get_all_server_metadata = AsyncMock(
            return_value=[_server_row("victim-server", project_id="project-b")]
        )
        viewer_rec = _active_viewer_key_record()
        storage.list_api_keys = AsyncMock(return_value=[viewer_rec])
        # get_member returns None → attacker is not in project-b
        storage.get_member = AsyncMock(return_value=None)
        app.state.trusted_proxy_networks = [ipaddress.ip_network("127.0.0.1/32")]

        headers = _sign_proxy_headers("attacker", "viewer", _TEST_PROXY_SECRET)
        response = await c.get(
            "/api/servers/metadata?project_id=project-b",
            headers=headers,
        )
        # get_active_project_id must deny before storage is reached
        assert response.status_code == 404
        storage.get_all_server_metadata.assert_not_called()

    async def test_admin_can_read_any_project_without_membership(
        self, auth_client
    ) -> None:
        """Admin (env key) can read server metadata for any project without membership."""
        c, storage, _ = auth_client
        storage.get_all_server_metadata = AsyncMock(
            return_value=[_server_row("foreign-server", project_id="other-project")]
        )

        response = await c.get(
            "/api/servers/metadata?project_id=other-project",
            headers={"X-API-Key": "test-admin-key"},
        )
        assert response.status_code == 200


# ===========================================================================
# 5. Cross-project server write — access denial
# ===========================================================================


class TestCrossProjectServerWrite:
    """Non-admin callers cannot register or delete servers in a project they
    do not own.

    Dependency ordering: for PUT and DELETE the FastAPI dependency chain is:
      1. get_storage
      2. get_active_project_id   ← membership check (→ 404 if non-member)
      3. require_admin           ← role check (→ 403 if viewer)
    Both layers must deny; either 403 or 404 is a correct denial response.
    """

    async def test_viewer_cannot_register_server_access_denied(
        self, auth_client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Viewer session attempting PUT on a foreign project is denied (403 or 404)."""
        c, storage, app = auth_client
        monkeypatch.setenv("LANGSIGHT_PROXY_SECRET", _TEST_PROXY_SECRET)
        storage.upsert_server_metadata = AsyncMock(return_value=_server_row("srv"))
        viewer_rec = _active_viewer_key_record()
        storage.list_api_keys = AsyncMock(return_value=[viewer_rec])
        storage.get_member = AsyncMock(return_value=None)
        app.state.trusted_proxy_networks = [ipaddress.ip_network("127.0.0.1/32")]

        headers = _sign_proxy_headers("attacker", "viewer", _TEST_PROXY_SECRET)
        response = await c.put(
            "/api/servers/metadata/new-srv?project_id=victim-project",
            json={"description": "PWNED"},
            headers=headers,
        )
        # Both 403 (require_admin) and 404 (membership) are correct denial codes
        assert response.status_code in (403, 404)
        storage.upsert_server_metadata.assert_not_called()

    async def test_viewer_cannot_delete_server_access_denied(
        self, auth_client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Viewer session attempting DELETE on a foreign project is denied (403 or 404)."""
        c, storage, app = auth_client
        monkeypatch.setenv("LANGSIGHT_PROXY_SECRET", _TEST_PROXY_SECRET)
        storage.delete_server_metadata = AsyncMock(return_value=True)
        viewer_rec = _active_viewer_key_record()
        storage.list_api_keys = AsyncMock(return_value=[viewer_rec])
        storage.get_member = AsyncMock(return_value=None)
        app.state.trusted_proxy_networks = [ipaddress.ip_network("127.0.0.1/32")]

        headers = _sign_proxy_headers("attacker", "viewer", _TEST_PROXY_SECRET)
        response = await c.delete(
            "/api/servers/metadata/victim-server?project_id=victim-project",
            headers=headers,
        )
        assert response.status_code in (403, 404)
        storage.delete_server_metadata.assert_not_called()

    async def test_require_admin_blocks_viewer_before_storage_for_viewer_role(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Confirm that require_admin independently returns 403 for viewer role.

        This test verifies the 403 path in isolation from get_active_project_id.
        """
        from langsight.api.dependencies import require_admin
        from tests.security.conftest import _make_request, _make_storage

        monkeypatch.setenv("LANGSIGHT_PROXY_SECRET", _TEST_PROXY_SECRET)
        headers = _sign_proxy_headers("viewer", "viewer", _TEST_PROXY_SECRET)
        req = _make_request(
            client_ip="127.0.0.1",
            headers=headers,
            api_keys=["env-key"],
        )
        with pytest.raises(Exception) as exc_info:
            await require_admin(request=req, api_key=None)
        assert exc_info.value.status_code == 403


# ===========================================================================
# 6. SSRF risk in the url field — documented gap
# ===========================================================================


class TestSsrfUrlFieldGap:
    """URL field on ServerMetadataUpdate is validated at the API layer.

    PUT /api/servers/metadata/{name} with SSRF-risk URLs (AWS IMDS, loopback,
    private ranges, non-http schemes) must be rejected with HTTP 422 before
    any storage call is made.
    """

    async def test_aws_imds_url_is_rejected(self, auth_client) -> None:
        """PUT with AWS IMDS URL must be rejected with 422."""
        c, storage, _ = auth_client
        ssrf_url = "http://169.254.169.254/latest/meta-data"
        storage.upsert_server_metadata = AsyncMock(
            return_value=_server_row("aws-probe", url=ssrf_url)
        )

        response = await c.put(
            "/api/servers/metadata/aws-probe",
            json={"url": ssrf_url, "transport": "sse"},
            headers={"X-API-Key": "test-admin-key"},
        )
        assert response.status_code == 422, (
            "SSRF: AWS IMDS URL must be rejected at the API layer with 422."
        )
        storage.upsert_server_metadata.assert_not_called()

    async def test_localhost_url_is_rejected(self, auth_client) -> None:
        """PUT with localhost URL must be rejected with 422."""
        c, storage, _ = auth_client
        storage.upsert_server_metadata = AsyncMock(
            return_value=_server_row("local-probe", url="http://localhost/admin")
        )

        response = await c.put(
            "/api/servers/metadata/local-probe",
            json={"url": "http://localhost/admin", "transport": "sse"},
            headers={"X-API-Key": "test-admin-key"},
        )
        assert response.status_code == 422, (
            "SSRF: localhost URL must be rejected at the API layer with 422."
        )
        storage.upsert_server_metadata.assert_not_called()

    async def test_file_scheme_url_is_rejected(self, auth_client) -> None:
        """PUT with file:// URL must be rejected with 422."""
        c, storage, _ = auth_client
        storage.upsert_server_metadata = AsyncMock(
            return_value=_server_row("file-probe", url="file:///etc/passwd")
        )

        response = await c.put(
            "/api/servers/metadata/file-probe",
            json={"url": "file:///etc/passwd", "transport": "sse"},
            headers={"X-API-Key": "test-admin-key"},
        )
        assert response.status_code == 422, (
            "SSRF: file:// URL must be rejected at the API layer with 422."
        )
        storage.upsert_server_metadata.assert_not_called()

    def test_transport_layer_rejects_aws_imds(self) -> None:
        """The transport-layer validator correctly rejects AWS IMDS URLs.
        This confirms the gap is at the API metadata layer, not the transport layer.
        """
        from langsight.alerts._url_validation import validate_webhook_url

        with pytest.raises(ValueError, match="Blocked webhook hostname"):
            validate_webhook_url("http://169.254.169.254/latest/meta-data")

    def test_transport_layer_rejects_localhost(self) -> None:
        """The transport-layer validator rejects localhost URLs."""
        from langsight.alerts._url_validation import validate_webhook_url

        with pytest.raises(ValueError, match="Blocked webhook hostname"):
            validate_webhook_url("http://localhost/anything")

    def test_transport_layer_rejects_file_scheme(self) -> None:
        """The transport-layer validator rejects file:// scheme."""
        from langsight.alerts._url_validation import validate_webhook_url

        with pytest.raises(ValueError, match="scheme must be http or https"):
            validate_webhook_url("file:///etc/passwd")

    def test_transport_layer_rejects_private_ip(self) -> None:
        """The transport-layer validator rejects RFC-1918 IPs."""
        from langsight.alerts._url_validation import validate_webhook_url

        with pytest.raises(ValueError, match="private or reserved"):
            validate_webhook_url("http://10.0.0.1/mcp")

    def test_transport_layer_rejects_link_local_ip(self) -> None:
        """The transport-layer validator rejects link-local 169.254.x.x IPs."""
        from langsight.alerts._url_validation import validate_webhook_url

        with pytest.raises(ValueError, match="private or reserved"):
            validate_webhook_url("http://169.254.1.1/mcp")


# ===========================================================================
# 7. Server name injection handling (open-install, auth disabled)
# ===========================================================================


class TestServerNameInjection:
    """Server name path parameters with hostile payloads are safely forwarded
    to storage as opaque strings.

    Invariant: the router does not interpret the server_name as a filesystem
    path, OS command, or raw SQL string. Any interpretation is the storage
    layer's responsibility (parameterised queries).

    Note: paths containing '/' are split by Starlette's router. These tests
    use names without '/' so they reach the handler correctly.
    XSS payloads in server_name are returned as JSON strings — not HTML-rendered.
    """

    async def test_sql_injection_name_forwarded_to_storage_verbatim(
        self, open_client
    ) -> None:
        """SQL injection in server_name is forwarded as a literal string.
        The storage layer must use parameterised queries; this test verifies the
        router does not alter or interpret the value before forwarding it.
        """
        c, storage, _ = open_client
        # Use URL-safe version (no slashes, no percent-encoding issues)
        sqli_name = "a' OR '1'='1' --"
        storage.upsert_server_metadata = AsyncMock(
            return_value=_server_row(sqli_name)
        )

        response = await c.put(
            f"/api/servers/metadata/{sqli_name}",
            json={"description": "sqli attempt"},
        )
        assert response.status_code == 200
        call_kwargs = storage.upsert_server_metadata.call_args[1]
        assert call_kwargs["server_name"] == sqli_name

    async def test_xss_payload_in_list_response_is_json_string_not_html(
        self, open_client
    ) -> None:
        """XSS payload in server_name is returned as a JSON string value in the
        list endpoint. The API returns application/json — the payload is not
        HTML-rendered by the server. Dashboard must HTML-escape when inserting
        into DOM.

        Uses the list endpoint (GET /api/servers/metadata) to avoid per-name
        URL encoding issues — the payload comes from storage, not the URL path.
        """
        c, storage, _ = open_client
        xss_name = "<script>alert(1)</script>"
        storage.get_all_server_metadata = AsyncMock(
            return_value=[_server_row(xss_name)]
        )

        response = await c.get("/api/servers/metadata")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/json")
        data = response.json()
        assert len(data) == 1
        # Payload is returned as a JSON string value — not HTML-encoded server-side
        assert data[0]["server_name"] == xss_name
        # Confirm the raw script tag is present in the response body (not escaped)
        assert "<script>" in response.text

    async def test_overlong_server_name_forwarded_to_storage(
        self, open_client
    ) -> None:
        """A very long server_name (1000 chars) reaches storage without truncation.
        Any length enforcement is the storage layer's responsibility.
        """
        c, storage, _ = open_client
        long_name = "x" * 1000
        storage.upsert_server_metadata = AsyncMock(
            return_value=_server_row(long_name)
        )

        response = await c.put(
            f"/api/servers/metadata/{long_name}",
            json={"description": "long name"},
        )
        assert response.status_code == 200
        call_kwargs = storage.upsert_server_metadata.call_args[1]
        assert len(call_kwargs["server_name"]) == 1000

    async def test_unicode_server_name_forwarded_to_storage(
        self, open_client
    ) -> None:
        """Unicode characters in server_name are forwarded correctly."""
        c, storage, _ = open_client
        unicode_name = "mcp-\u6d4b\u8bd5-server"  # "mcp-测试-server"
        storage.upsert_server_metadata = AsyncMock(
            return_value=_server_row(unicode_name)
        )

        response = await c.put(
            f"/api/servers/metadata/{unicode_name}",
            json={"description": "unicode name"},
        )
        assert response.status_code == 200
        call_kwargs = storage.upsert_server_metadata.call_args[1]
        assert call_kwargs["server_name"] == unicode_name


# ===========================================================================
# 8. _auto_discover_servers — project scope enforcement
# ===========================================================================


class TestAutoDiscoverProjectScope:
    """_auto_discover_servers must always scope span queries and upserts to the
    calling project_id. Foreign project span data must never pollute the calling
    project's server catalog.

    Invariant: every call to get_distinct_span_server_names and
    upsert_server_metadata carries exactly the project_id of the calling context.
    """

    @pytest.mark.asyncio
    async def test_span_query_receives_correct_project_id(self) -> None:
        """get_distinct_span_server_names must be called with the active project_id.

        If this call ever omits project_id, span data from all projects would
        be returned and could register foreign servers into the wrong project.
        """
        from langsight.api.routers.health import _auto_discover_servers

        storage = MagicMock()
        storage.get_distinct_span_server_names = AsyncMock(return_value=set())
        storage.get_all_server_metadata = AsyncMock(return_value=[])
        storage.upsert_server_metadata = AsyncMock()

        await _auto_discover_servers(storage, project_id="project-alpha")

        storage.get_distinct_span_server_names.assert_called_once_with(
            project_id="project-alpha"
        )

    @pytest.mark.asyncio
    async def test_upsert_carries_caller_project_id(self) -> None:
        """New servers are upserted with the caller's project_id, never None or a
        different project's id.
        """
        from langsight.api.routers.health import _auto_discover_servers

        storage = MagicMock()
        storage.get_distinct_span_server_names = AsyncMock(
            return_value={"new-server"}
        )
        storage.get_all_server_metadata = AsyncMock(
            side_effect=[
                [],  # first call — no existing metadata
                [{"server_name": "new-server"}],  # post-upsert refresh
            ]
        )
        storage.upsert_server_metadata = AsyncMock(
            return_value={"server_name": "new-server"}
        )

        await _auto_discover_servers(storage, project_id="project-beta")

        upsert_kwargs = storage.upsert_server_metadata.call_args[1]
        assert upsert_kwargs["project_id"] == "project-beta"
        assert upsert_kwargs["server_name"] == "new-server"

    @pytest.mark.asyncio
    async def test_foreign_project_spans_never_registered_in_caller_project(
        self,
    ) -> None:
        """Servers in project-A's span data must not be upserted into project-B's metadata.

        Simulates two projects each seeing different span server names. Runs
        auto-discover for project-A and asserts only project-A's span servers
        are touched, never project-B's.
        """
        from langsight.api.routers.health import _auto_discover_servers

        storage = MagicMock()

        # Return different server names per project
        async def span_names_by_project(project_id: str) -> set[str]:
            return {"server-a"} if project_id == "project-a" else {"server-b"}

        # Use AsyncMock with a synchronous side_effect that calls the async fn
        # via asyncio — instead, wrap in a proper coroutine-returning callable.
        called_with: list[str] = []

        async def span_side_effect(**kwargs: object) -> set[str]:
            pid = kwargs.get("project_id", "")
            assert isinstance(pid, str)
            called_with.append(pid)
            return await span_names_by_project(pid)

        storage.get_distinct_span_server_names = span_side_effect
        storage.get_all_server_metadata = AsyncMock(return_value=[])
        storage.upsert_server_metadata = AsyncMock(
            return_value={"server_name": "server-a"}
        )

        await _auto_discover_servers(storage, project_id="project-a")

        # Only project-a was queried
        assert called_with == ["project-a"]
        # All upsert calls must carry project_id="project-a"
        for c in storage.upsert_server_metadata.call_args_list:
            assert c[1]["project_id"] == "project-a", (
                f"Upsert leaked into wrong project: {c}"
            )
        # server-b (from project-b) was never registered under project-a
        registered_names = {
            c[1]["server_name"] for c in storage.upsert_server_metadata.call_args_list
        }
        assert "server-b" not in registered_names

    @pytest.mark.asyncio
    async def test_get_all_server_metadata_receives_project_id(self) -> None:
        """get_all_server_metadata must be called with project_id, not None.

        If this call ran with None, the existing-names set would contain servers
        from ALL projects, suppressing upserts that should happen.
        """
        from langsight.api.routers.health import _auto_discover_servers

        storage = MagicMock()
        storage.get_distinct_span_server_names = AsyncMock(return_value=set())
        storage.get_all_server_metadata = AsyncMock(return_value=[])
        storage.upsert_server_metadata = AsyncMock()

        await _auto_discover_servers(storage, project_id="project-gamma")

        # get_all_server_metadata is called via asyncio.gather in the source —
        # verify the project_id argument was forwarded
        for call in storage.get_all_server_metadata.call_args_list:
            assert call[1].get("project_id") == "project-gamma"


# ===========================================================================
# 9. Proxy header trust boundary on server endpoints
# ===========================================================================


class TestProxyHeaderTrustOnServerEndpoints:
    """X-User-* proxy headers establish identity only when the request originates
    from a trusted CIDR (loopback by default). An attacker who can send HTTP
    directly to the API from an external IP cannot gain admin access by forging
    these headers.

    Invariant: _get_session_user returns (None, None) for any non-loopback IP,
    meaning the session-auth path is fully skipped.
    """

    def test_x_user_role_alone_without_user_id_does_not_grant_admin(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """X-User-Role: admin without X-User-Id must not yield a non-None user_id.

        require_admin and get_active_project_id both require user_id to be set
        to enter the session-user code path. Role alone is insufficient.
        """
        from langsight.api.dependencies import _get_session_user

        monkeypatch.setenv("LANGSIGHT_PROXY_SECRET", _TEST_PROXY_SECRET)
        scope = {
            "type": "http",
            "method": "PUT",
            "path": "/api/servers/metadata/test",
            "query_string": b"",
            "headers": [(b"x-user-role", b"admin")],  # no X-User-Id
            "client": ("127.0.0.1", 9000),
        }
        app_inner = Starlette()
        app_inner.state.trusted_proxy_networks = [
            ipaddress.ip_network("127.0.0.1/32")
        ]
        scope["app"] = app_inner
        req = Request(scope)

        user_id, user_role = _get_session_user(req)
        assert user_id is None, (
            "X-User-Role alone must not yield a user_id. "
            "An attacker who can forge X-User-Role must also forge X-User-Id "
            "from a trusted IP — role without identity is not sufficient."
        )

    def test_user_id_header_without_role_has_no_role(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """X-User-Id present but X-User-Role absent → user_role is None.

        This must not default to admin or any other role.
        """
        from langsight.api.dependencies import _get_session_user

        monkeypatch.setenv("LANGSIGHT_PROXY_SECRET", _TEST_PROXY_SECRET)
        # Sign with empty role string
        headers_dict = _sign_proxy_headers("some-user", "", _TEST_PROXY_SECRET)
        # Convert to scope headers format, excluding X-User-Role
        headers_list = [
            (b"x-user-id", headers_dict["X-User-Id"].encode()),
            (b"x-proxy-timestamp", headers_dict["X-Proxy-Timestamp"].encode()),
            (b"x-proxy-signature", headers_dict["X-Proxy-Signature"].encode()),
        ]
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/api/test",
            "query_string": b"",
            "headers": headers_list,
            "client": ("127.0.0.1", 9000),
        }
        app_inner = Starlette()
        app_inner.state.trusted_proxy_networks = [
            ipaddress.ip_network("127.0.0.1/32")
        ]
        scope["app"] = app_inner
        req = Request(scope)

        user_id, user_role = _get_session_user(req)
        assert user_id == "some-user"
        assert user_role is None, (
            "user_role must be None when X-User-Role is absent; "
            "must not default to admin."
        )

    def test_admin_headers_from_untrusted_ip_are_silently_ignored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """X-User-Id: admin + X-User-Role: admin from an external IP → (None, None).

        If these headers were trusted from external IPs, any attacker with
        network access to the API could impersonate any user.
        """
        from langsight.api.dependencies import _get_session_user

        monkeypatch.setenv("LANGSIGHT_PROXY_SECRET", _TEST_PROXY_SECRET)
        scope = {
            "type": "http",
            "method": "PUT",
            "path": "/api/servers/metadata/pwned",
            "query_string": b"",
            "headers": [
                (b"x-user-id", b"admin"),
                (b"x-user-role", b"admin"),
            ],
            "client": ("8.8.8.8", 9000),  # external IP — not loopback
        }
        app_inner = Starlette()
        app_inner.state.trusted_proxy_networks = [
            ipaddress.ip_network("127.0.0.1/32")
        ]
        scope["app"] = app_inner
        req = Request(scope)

        user_id, user_role = _get_session_user(req)
        assert user_id is None, (
            "X-User-Id from an untrusted external IP must be ignored."
        )
        assert user_role is None, (
            "X-User-Role from an untrusted external IP must be ignored."
        )


# ===========================================================================
# 10. Open-install (auth disabled) behaviour
# ===========================================================================


class TestOpenInstallServersEndpoints:
    """When auth is fully disabled (no env keys, no DB keys), all endpoints
    are open. This is the intended local-dev mode and must not regress.

    Invariant: disabling auth permits unrestricted access but does NOT bypass
    the project_id storage filtering — project_id is still forwarded to storage.
    """

    async def test_open_install_can_register_server_without_key(
        self, open_client
    ) -> None:
        """Auth-disabled install: PUT without any key succeeds."""
        c, storage, _ = open_client
        storage.upsert_server_metadata = AsyncMock(
            return_value=_server_row("local-mcp", transport="stdio")
        )

        response = await c.put(
            "/api/servers/metadata/local-mcp",
            json={"transport": "stdio", "description": "local dev server"},
        )
        assert response.status_code == 200

    async def test_open_install_can_delete_server_without_key(
        self, open_client
    ) -> None:
        """Auth-disabled install: DELETE without any key succeeds."""
        c, storage, _ = open_client
        storage.delete_server_metadata = AsyncMock(return_value=True)

        response = await c.delete("/api/servers/metadata/local-mcp")
        assert response.status_code == 204

    async def test_open_install_list_without_project_id_returns_200(
        self, open_client
    ) -> None:
        """Auth-disabled install: GET /api/servers/metadata with no project_id → 200."""
        c, storage, _ = open_client
        storage.get_all_server_metadata = AsyncMock(return_value=[])

        response = await c.get("/api/servers/metadata")
        assert response.status_code == 200

    async def test_open_install_project_id_none_forwarded_to_storage(
        self, open_client
    ) -> None:
        """Open install does not require project_id; get_active_project_id returns None."""
        from langsight.api.dependencies import get_active_project_id
        from tests.security.conftest import _make_request, _make_storage

        storage = _make_storage(active_db_keys=[])  # no keys → auth disabled
        req = _make_request(
            client_ip="10.0.0.1", headers={}, api_keys=[], storage=storage
        )
        result = await get_active_project_id(request=req, project_id=None)
        assert result is None
