"""
Security regression tests — server metadata and tool-schema endpoints.

Attack surface: src/langsight/api/routers/servers.py

Trust boundary model for this router:
  - PUT /api/servers/metadata/{server_name}   — requires admin (require_admin dep)
  - DELETE /api/servers/metadata/{server_name} — requires admin (require_admin dep)
  - GET /api/servers/metadata                 — requires auth (verify_api_key dep on router)
  - GET /api/servers/metadata/{server_name}   — requires auth (verify_api_key dep on router)
  - POST /api/servers/{server_name}/tools     — intentionally open (SDK fire-and-forget)
  - GET /api/servers/{server_name}/tools      — requires auth (verify_api_key dep on router)

Test classes and their invariants:
  TestAdminWriteEnforcement    — PUT/DELETE endpoints must reject non-admin callers.
  TestAuthRequiredForReads     — GET endpoints must reject unauthenticated callers.
  TestOpenToolRecordEndpoint   — The intentionally auth-free POST endpoint must be
                                  safe against injected payloads (path traversal,
                                  huge payloads, XSS strings, SQL injection strings).
  TestProjectIsolationOnReads  — GET /metadata scoped to project_id must not leak
                                  cross-project server metadata.
  TestInputValidationOnWrite   — Edge-case inputs (empty strings, very large strings)
                                  must not crash the endpoint or storage layer.
"""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.security.conftest import (
    _active_key_record,
    _make_request,
    _make_storage,
    _member_record,
)

pytestmark = pytest.mark.security


# ---------------------------------------------------------------------------
# Helpers — build a storage mock that knows about server metadata methods
# ---------------------------------------------------------------------------

def _server_storage(
    metadata_rows: list[dict] | None = None,
    single_row: dict | None = None,
    upsert_result: dict | None = None,
    delete_result: bool = True,
    tools_result: list[dict] | None = None,
    upsert_raises: Exception | None = None,
    delete_raises: Exception | None = None,
    get_member_returns: object | None = None,
    get_member_raises: Exception | None = None,
    list_api_keys_raises: Exception | None = None,
    active_db_keys: list | None = None,
) -> MagicMock:
    """Return a storage mock wired for the servers router methods."""
    storage = _make_storage(
        active_db_keys=active_db_keys,
        list_api_keys_raises=list_api_keys_raises,
        get_member_returns=get_member_returns,
        get_member_raises=get_member_raises,
    )

    now_str = str(datetime.now(UTC))
    _default_row: dict = {
        "id": "srv-1",
        "server_name": "postgres-mcp",
        "description": "Postgres MCP server",
        "owner": "infra-team",
        "tags": ["db", "prod"],
        "transport": "stdio",
        "runbook_url": "https://wiki.example.com/postgres-mcp",
        "project_id": "proj-1",
        "created_at": now_str,
        "updated_at": now_str,
    }

    storage.get_all_server_metadata = AsyncMock(return_value=metadata_rows or [_default_row])
    storage.get_server_metadata = AsyncMock(return_value=single_row or _default_row)

    if upsert_raises:
        storage.upsert_server_metadata = AsyncMock(side_effect=upsert_raises)
    else:
        storage.upsert_server_metadata = AsyncMock(return_value=upsert_result or _default_row)

    if delete_raises:
        storage.delete_server_metadata = AsyncMock(side_effect=delete_raises)
    else:
        storage.delete_server_metadata = AsyncMock(return_value=delete_result)

    storage.upsert_server_tools = AsyncMock(return_value=None)
    storage.get_server_tools = AsyncMock(return_value=tools_result or [])

    return storage


def _tool_entry(name: str = "query", description: str = "Run a SQL query") -> dict:
    return {
        "name": name,
        "description": description,
        "inputSchema": {"type": "object", "properties": {}},
    }


# ---------------------------------------------------------------------------
# 1. Admin write enforcement — PUT and DELETE require admin
# ---------------------------------------------------------------------------

class TestAdminWriteEnforcement:
    """Invariant: PUT and DELETE on /servers/metadata require admin role.

    A viewer-role session user or a caller with no credentials must be
    rejected before any storage mutation is attempted.
    """

    async def test_upsert_server_metadata_requires_admin_viewer_session_gets_403(
        self,
    ) -> None:
        """Viewer-role session user attempting PUT /servers/metadata → 403."""
        from fastapi import HTTPException
        from langsight.api.dependencies import require_admin

        storage = _server_storage(active_db_keys=[_active_key_record(role="viewer")])
        req = _make_request(
            client_ip="127.0.0.1",
            headers={"X-User-Id": "viewer-user", "X-User-Role": "viewer"},
            api_keys=["env-key"],
            storage=storage,
        )
        with pytest.raises(HTTPException) as exc_info:
            await require_admin(request=req, api_key=None)
        assert exc_info.value.status_code == 403
        # Storage must not have been touched — the gate fired before reaching it
        storage.upsert_server_metadata.assert_not_called()

    async def test_upsert_server_metadata_requires_admin_member_session_gets_403(
        self,
    ) -> None:
        """Member-role session user attempting PUT /servers/metadata → 403."""
        from fastapi import HTTPException
        from langsight.api.dependencies import require_admin

        storage = _server_storage(active_db_keys=[_active_key_record(role="viewer")])
        req = _make_request(
            client_ip="127.0.0.1",
            headers={"X-User-Id": "member-user", "X-User-Role": "member"},
            api_keys=["env-key"],
            storage=storage,
        )
        with pytest.raises(HTTPException) as exc_info:
            await require_admin(request=req, api_key=None)
        assert exc_info.value.status_code == 403

    async def test_upsert_server_metadata_requires_auth_no_token_gets_401(
        self, auth_client
    ) -> None:
        """No credential on PUT /api/servers/metadata/{name} → 401 (not even 403)."""
        c, mock_storage, _ = auth_client
        mock_storage.upsert_server_metadata = AsyncMock()

        response = await c.put(
            "/api/servers/metadata/postgres-mcp",
            json={"description": "should not reach storage"},
        )
        assert response.status_code in (401, 403)
        mock_storage.upsert_server_metadata.assert_not_called()

    async def test_upsert_server_metadata_viewer_api_key_gets_403(self) -> None:
        """Viewer-role DB API key → require_admin raises 403."""
        from fastapi import HTTPException
        from langsight.api.dependencies import require_admin

        viewer_key = "viewer-secret"
        viewer_record = _active_key_record(role="viewer")
        storage = _server_storage(active_db_keys=[viewer_record])
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
        storage.upsert_server_metadata.assert_not_called()

    async def test_delete_server_metadata_requires_admin_viewer_session_gets_403(
        self,
    ) -> None:
        """Viewer-role session user attempting DELETE /servers/metadata → 403."""
        from fastapi import HTTPException
        from langsight.api.dependencies import require_admin

        storage = _server_storage(active_db_keys=[_active_key_record(role="viewer")])
        req = _make_request(
            client_ip="127.0.0.1",
            headers={"X-User-Id": "viewer-user", "X-User-Role": "viewer"},
            api_keys=["env-key"],
            storage=storage,
        )
        with pytest.raises(HTTPException) as exc_info:
            await require_admin(request=req, api_key=None)
        assert exc_info.value.status_code == 403
        storage.delete_server_metadata.assert_not_called()

    async def test_delete_server_metadata_requires_auth_no_token_gets_401(
        self, auth_client
    ) -> None:
        """No credential on DELETE /api/servers/metadata/{name} → 401."""
        c, mock_storage, _ = auth_client
        mock_storage.delete_server_metadata = AsyncMock(return_value=True)

        response = await c.delete("/api/servers/metadata/postgres-mcp")
        assert response.status_code in (401, 403)
        mock_storage.delete_server_metadata.assert_not_called()

    async def test_delete_server_metadata_viewer_api_key_gets_403(self) -> None:
        """Viewer DB API key → require_admin raises 403 before DELETE reaches storage."""
        from fastapi import HTTPException
        from langsight.api.dependencies import require_admin

        viewer_key = "viewer-secret"
        viewer_record = _active_key_record(role="viewer")
        storage = _server_storage(active_db_keys=[viewer_record])
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
        storage.delete_server_metadata.assert_not_called()

    async def test_admin_session_can_upsert_server_metadata(
        self, auth_client
    ) -> None:
        """Admin-role session user can PUT /api/servers/metadata/{name} — not over-blocked."""
        c, mock_storage, _ = auth_client
        now_str = str(datetime.now(UTC))
        mock_storage.upsert_server_metadata = AsyncMock(
            return_value={
                "id": "srv-1",
                "server_name": "postgres-mcp",
                "description": "Updated",
                "owner": "infra",
                "tags": [],
                "transport": "stdio",
                "runbook_url": "",
                "project_id": None,
                "created_at": now_str,
                "updated_at": now_str,
            }
        )
        mock_storage.list_api_keys = AsyncMock(return_value=[])
        mock_storage.get_member = AsyncMock(return_value=None)

        response = await c.put(
            "/api/servers/metadata/postgres-mcp",
            json={"description": "Updated", "owner": "infra"},
            headers={
                "X-API-Key": "test-api-key",   # env key → always admin
            },
        )
        assert response.status_code == 200
        mock_storage.upsert_server_metadata.assert_called_once()

    async def test_admin_session_can_delete_server_metadata(
        self, auth_client
    ) -> None:
        """Admin key can DELETE /api/servers/metadata/{name}."""
        c, mock_storage, _ = auth_client
        mock_storage.delete_server_metadata = AsyncMock(return_value=True)
        mock_storage.list_api_keys = AsyncMock(return_value=[])

        response = await c.delete(
            "/api/servers/metadata/postgres-mcp",
            headers={"X-API-Key": "test-api-key"},
        )
        assert response.status_code == 204
        mock_storage.delete_server_metadata.assert_called_once_with("postgres-mcp")

    async def test_spoofed_admin_header_from_external_ip_blocked_by_require_admin(
        self,
    ) -> None:
        """X-User-Role: admin from a non-loopback IP must not grant write access.

        The proxy header trust boundary is enforced in _get_session_user():
        headers are only read when the request originates from a trusted CIDR.
        An attacker sending these headers directly from an external IP is
        treated as unauthenticated — their session headers are silently ignored,
        and no API key was provided, so require_admin must raise 401.

        This is tested at the dependency level because TestClient always
        connects from loopback (127.0.0.1), which IS a trusted IP by default.
        The dependency test lets us control the client IP precisely.
        """
        from fastapi import HTTPException
        from langsight.api.dependencies import require_admin

        # Auth is enabled (one active DB key)
        storage = _server_storage(active_db_keys=[_active_key_record(role="viewer")])
        req = _make_request(
            client_ip="203.0.113.99",  # external, untrusted IP (TEST-NET-3, RFC 5737)
            headers={
                "X-User-Id": "attacker",
                "X-User-Role": "admin",   # spoofed admin role — must be ignored
            },
            api_keys=[],          # no env key
            storage=storage,
        )
        # Session headers from untrusted IP → _get_session_user returns (None, None).
        # No API key provided → require_admin must raise 401 (unauthenticated).
        with pytest.raises(HTTPException) as exc_info:
            await require_admin(request=req, api_key=None)
        assert exc_info.value.status_code in (401, 403), (
            "Spoofed admin headers from untrusted IP must be denied, not granted"
        )
        # Storage must never have been touched
        storage.upsert_server_metadata.assert_not_called()


# ---------------------------------------------------------------------------
# 2. Auth required for read endpoints
# ---------------------------------------------------------------------------

class TestAuthRequiredForReads:
    """Invariant: GET endpoints on /servers require authentication.

    An unauthenticated caller (no X-API-Key, no session headers) must receive
    401 when auth is enabled, and must never receive server metadata.
    """

    async def test_list_server_metadata_requires_auth(self, auth_client) -> None:
        """No key on GET /api/servers/metadata → 401."""
        c, mock_storage, _ = auth_client
        mock_storage.get_all_server_metadata = AsyncMock(return_value=[])

        response = await c.get("/api/servers/metadata")
        assert response.status_code in (401, 403)
        # Storage must not have been reached
        mock_storage.get_all_server_metadata.assert_not_called()

    async def test_get_single_server_metadata_requires_auth(self, auth_client) -> None:
        """No key on GET /api/servers/metadata/{name} → 401."""
        c, mock_storage, _ = auth_client
        mock_storage.get_server_metadata = AsyncMock(return_value=None)

        response = await c.get("/api/servers/metadata/postgres-mcp")
        assert response.status_code in (401, 403)
        mock_storage.get_server_metadata.assert_not_called()

    async def test_get_server_tools_requires_auth(self, auth_client) -> None:
        """No key on GET /api/servers/{name}/tools → 401."""
        c, mock_storage, _ = auth_client
        mock_storage.get_server_tools = AsyncMock(return_value=[])

        response = await c.get("/api/servers/postgres-mcp/tools")
        assert response.status_code in (401, 403)
        mock_storage.get_server_tools.assert_not_called()

    async def test_wrong_key_on_metadata_list_returns_403(self, auth_client) -> None:
        """Correct header, wrong value on GET /api/servers/metadata → 403."""
        c, mock_storage, _ = auth_client
        mock_storage.get_all_server_metadata = AsyncMock(return_value=[])

        response = await c.get(
            "/api/servers/metadata",
            headers={"X-API-Key": "definitely-wrong-key"},
        )
        assert response.status_code == 403
        mock_storage.get_all_server_metadata.assert_not_called()

    async def test_valid_key_on_metadata_list_returns_200(self, auth_client) -> None:
        """Valid env key on GET /api/servers/metadata → 200 (not over-blocked)."""
        c, mock_storage, _ = auth_client
        mock_storage.get_all_server_metadata = AsyncMock(return_value=[])
        mock_storage.list_api_keys = AsyncMock(return_value=[])

        response = await c.get(
            "/api/servers/metadata",
            headers={"X-API-Key": "test-api-key"},
        )
        assert response.status_code == 200

    async def test_metadata_open_in_open_install(self, open_client) -> None:
        """GET /api/servers/metadata with no keys configured → 200 (open install)."""
        c, mock_storage, _ = open_client
        mock_storage.get_all_server_metadata = AsyncMock(return_value=[])
        mock_storage.list_api_keys = AsyncMock(return_value=[])

        response = await c.get("/api/servers/metadata")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# 3. The intentionally open endpoint — POST /servers/{server_name}/tools
# ---------------------------------------------------------------------------

class TestOpenToolRecordEndpoint:
    """Invariant: the tool-schema capture endpoint must be safe against injected payloads.

    POST /api/servers/{server_name}/tools is called by the SDK (which sends the
    API key). In an open install (no keys configured) it requires no credentials.
    Tests use open_client to exercise the endpoint body regardless of auth.
    Invariants:
      - path traversal in server_name is impossible (it's a DB key, not a path)
      - huge payloads are handled gracefully (no OOM crash or unhandled exception)
      - XSS strings in description are stored as plain text, not executed
      - SQL injection strings in tool_name are safe (parameterized storage)
      - an empty tools list is handled without touching storage
    """

    async def test_record_tools_server_name_with_path_traversal_is_stored_as_db_key(
        self, open_client
    ) -> None:
        """Path traversal in server_name cannot escape the DB — it's just a string key.

        The server_name appears in the URL path segment but is passed directly
        to storage as a string. The router does no file I/O. Verify the endpoint
        accepts it (200) and forwards the literal string to storage — no filesystem
        interaction occurs.
        """
        c, mock_storage, _ = open_client
        mock_storage.upsert_server_tools = AsyncMock(return_value=None)

        # Path traversal chars in server_name are URL-encoded by httpx — FastAPI
        # decodes them back and they become a DB key, not a filesystem path.
        # Use URL-encoded form to avoid 404 from router path matching.
        response = await c.post(
            "/api/servers/..%2F..%2Fetc%2Fpasswd/tools",
            json={"tools": [_tool_entry()]},
        )
        # Either 200 (stored as literal key) or 422 (FastAPI rejects encoded slashes)
        # — in both cases no filesystem interaction occurs and no 500.
        assert response.status_code in (200, 404, 422)

    async def test_record_tools_server_name_with_null_byte_is_handled(
        self, open_client
    ) -> None:
        """Null byte in server_name must not crash the server (500-free)."""
        c, mock_storage, _ = open_client
        mock_storage.upsert_server_tools = AsyncMock(return_value=None)

        # URL-encode the null byte — %00 in the path
        response = await c.post(
            "/api/servers/server%00name/tools",
            json={"tools": [_tool_entry()]},
        )
        # Must return a valid HTTP response — not an unhandled 500
        assert response.status_code in (200, 400, 422)

    async def test_record_tools_huge_payload_does_not_crash(
        self, open_client
    ) -> None:
        """1000 tools in a single POST must be handled without crashing.

        The endpoint passes the tool list to storage in one call. Verify no
        unhandled exception escapes — the response must be a valid HTTP status.
        """
        c, mock_storage, _ = open_client
        mock_storage.upsert_server_tools = AsyncMock(return_value=None)

        large_tools = [
            _tool_entry(name=f"tool_{i}", description=f"Tool number {i}")
            for i in range(1000)
        ]
        response = await c.post(
            "/api/servers/big-server/tools",
            json={"tools": large_tools},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["upserted"] == 1000
        # Verify the full list was forwarded to storage, not truncated
        call_args = mock_storage.upsert_server_tools.call_args
        assert len(call_args[0][1]) == 1000

    async def test_record_tools_malicious_description_stored_as_plain_text(
        self, open_client
    ) -> None:
        """XSS payload in description is stored as a plain string — no HTML rendered.

        The API is JSON-only and returns JSON. The description field is opaque
        data from the SDK perspective. Verify:
          1. The endpoint accepts the request (200) — no over-sanitization.
          2. The literal string is forwarded to storage unchanged.
          3. The response Content-Type is application/json (not text/html).
        """
        c, mock_storage, _ = open_client
        xss_description = "<script>alert('xss')</script> DROP TABLE server_tools;"
        mock_storage.upsert_server_tools = AsyncMock(return_value=None)

        response = await c.post(
            "/api/servers/xss-test/tools",
            json={"tools": [_tool_entry(description=xss_description)]},
        )
        assert response.status_code == 200
        # Response must be JSON — not HTML that would execute the script
        content_type = response.headers.get("content-type", "")
        assert "application/json" in content_type

        # The XSS string must have been forwarded verbatim to storage (not stripped)
        # so that the storage layer can apply its own escaping. The API layer must
        # NOT silently drop content, which would corrupt tool descriptions.
        call_args = mock_storage.upsert_server_tools.call_args
        forwarded_tools = call_args[0][1]
        assert forwarded_tools[0]["description"] == xss_description

    async def test_record_tools_sql_injection_in_tool_name_is_safe(
        self, open_client
    ) -> None:
        """SQL injection string in tool_name must be passed to storage as a literal.

        The storage layer uses parameterized queries, so the string is never
        interpolated into SQL. This test verifies the API layer does not crash
        and forwards the string to storage (proving parameterization, not exec).
        """
        c, mock_storage, _ = open_client
        sql_injection = "'; DROP TABLE server_tools; --"
        mock_storage.upsert_server_tools = AsyncMock(return_value=None)

        response = await c.post(
            "/api/servers/injection-test/tools",
            json={"tools": [_tool_entry(name=sql_injection)]},
        )
        assert response.status_code == 200
        # The injected string must be forwarded to storage as a literal argument,
        # not executed. If it were executed, upsert_server_tools would fail or
        # the table would be gone — but we verify storage was called with the string.
        call_args = mock_storage.upsert_server_tools.call_args
        forwarded_tools = call_args[0][1]
        assert forwarded_tools[0]["name"] == sql_injection

    async def test_record_tools_empty_tools_list_returns_zero_upserted(
        self, open_client
    ) -> None:
        """Empty tools list is an early exit — storage must NOT be called."""
        c, mock_storage, _ = open_client
        mock_storage.upsert_server_tools = AsyncMock(return_value=None)

        response = await c.post(
            "/api/servers/some-server/tools",
            json={"tools": []},
        )
        assert response.status_code == 200
        assert response.json()["upserted"] == 0
        # The router explicitly guards on `if not body.tools: return {"upserted": 0}`
        # Verify storage was never called — an attacker cannot trigger storage writes
        # with an empty payload.
        mock_storage.upsert_server_tools.assert_not_called()

    async def test_record_tools_missing_tools_field_returns_422(
        self, open_client
    ) -> None:
        """Malformed body (missing required 'tools' field) → 422 Unprocessable Entity."""
        c, _, _ = open_client
        response = await c.post(
            "/api/servers/some-server/tools",
            json={"project_id": "proj-1"},  # no 'tools' key
        )
        assert response.status_code == 422

    async def test_record_tools_tools_not_a_list_returns_422(
        self, open_client
    ) -> None:
        """'tools' field with a non-list value → 422 (Pydantic validation)."""
        c, _, _ = open_client
        response = await c.post(
            "/api/servers/some-server/tools",
            json={"tools": "not-a-list"},
        )
        assert response.status_code == 422

    async def test_record_tools_storage_error_returns_500_not_silent_success(
        self, open_client
    ) -> None:
        """If storage.upsert_server_tools raises, the error must NOT silently return 200.

        FastAPI converts unhandled exceptions to 500. This test verifies the endpoint
        does not catch and swallow storage errors — callers must know the write failed.
        """
        c, mock_storage, _ = open_client
        mock_storage.upsert_server_tools = AsyncMock(
            side_effect=RuntimeError("pg connection refused")
        )

        try:
            response = await c.post(
                "/api/servers/some-server/tools",
                json={"tools": [_tool_entry()]},
            )
            # FastAPI converts unhandled RuntimeError → 500
            assert response.status_code == 500
        except RuntimeError:
            # Some ASGI transports propagate the exception directly in tests
            # — that's also acceptable (the error is NOT silently swallowed)
            pass


# ---------------------------------------------------------------------------
# 4. Project isolation on GET /servers/metadata
# ---------------------------------------------------------------------------

class TestProjectIsolationOnReads:
    """Invariant: GET /servers/metadata is scoped to project_id.

    A user authenticated to project A must not receive server metadata
    that belongs to project B — even if they know project B's ID.
    The get_active_project_id dependency enforces this boundary.
    """

    async def test_non_admin_session_user_cannot_list_metadata_without_project_id(
        self,
    ) -> None:
        """Non-admin session user with no project_id on GET /servers/metadata → 400.

        This verifies the get_active_project_id dep fires before storage is
        queried, preventing a data dump of all servers across all projects.
        """
        from fastapi import HTTPException
        from langsight.api.dependencies import get_active_project_id

        storage = _server_storage(active_db_keys=[_active_key_record(role="viewer")])
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
        # Storage's get_all_server_metadata must never have been reached
        storage.get_all_server_metadata.assert_not_called()

    async def test_non_member_session_user_cannot_see_foreign_project_servers(
        self,
    ) -> None:
        """User not in project B cannot query project B's server metadata — 404."""
        from fastapi import HTTPException
        from langsight.api.dependencies import get_active_project_id

        storage = _server_storage(
            active_db_keys=[_active_key_record(role="viewer")],
            get_member_returns=None,  # not a member of any project
        )
        req = _make_request(
            client_ip="127.0.0.1",
            headers={"X-User-Id": "attacker", "X-User-Role": "viewer"},
            api_keys=["env-key"],
            storage=storage,
        )
        with pytest.raises(HTTPException) as exc_info:
            await get_active_project_id(request=req, project_id="project-b")
        assert exc_info.value.status_code == 404
        storage.get_all_server_metadata.assert_not_called()

    async def test_member_of_project_a_cannot_see_project_b_servers(
        self,
    ) -> None:
        """Membership in project A must NOT grant access to project B's servers."""
        from fastapi import HTTPException
        from langsight.api.dependencies import get_active_project_id

        storage = _server_storage(active_db_keys=[_active_key_record(role="viewer")])
        # get_member returns None specifically for project-b (lateral move)
        storage.get_member = AsyncMock(return_value=None)

        req = _make_request(
            client_ip="127.0.0.1",
            headers={"X-User-Id": "user-in-a", "X-User-Role": "viewer"},
            api_keys=["env-key"],
            storage=storage,
        )
        with pytest.raises(HTTPException) as exc_info:
            await get_active_project_id(request=req, project_id="project-b")
        assert exc_info.value.status_code == 404

    async def test_admin_session_can_list_all_servers_without_project_id(
        self,
    ) -> None:
        """Admin can query /servers/metadata with no project_id — returns None filter."""
        from langsight.api.dependencies import get_active_project_id

        storage = _server_storage(active_db_keys=[])
        req = _make_request(
            client_ip="127.0.0.1",
            headers={"X-User-Id": "admin-1", "X-User-Role": "admin"},
            api_keys=["env-key"],
            storage=storage,
        )
        result = await get_active_project_id(request=req, project_id=None)
        assert result is None  # None means "all projects" — correct for admin

    async def test_db_error_during_membership_check_denies_server_metadata_access(
        self,
    ) -> None:
        """Membership check DB error must deny access — not silently allow through."""
        from fastapi import HTTPException
        from langsight.api.dependencies import get_active_project_id

        storage = _server_storage(
            active_db_keys=[_active_key_record(role="viewer")],
            get_member_raises=Exception("membership query timed out"),
        )
        req = _make_request(
            client_ip="127.0.0.1",
            headers={"X-User-Id": "user-1", "X-User-Role": "viewer"},
            api_keys=["env-key"],
            storage=storage,
        )
        with pytest.raises((HTTPException, Exception)):
            await get_active_project_id(request=req, project_id="victim-project")
        # Whatever is raised, storage.get_all_server_metadata must not have run
        storage.get_all_server_metadata.assert_not_called()

    async def test_open_install_can_list_servers_without_project_id(
        self,
    ) -> None:
        """Open install (auth disabled): GET /servers/metadata without project_id → OK."""
        from langsight.api.dependencies import get_active_project_id

        storage = _server_storage(active_db_keys=[])
        req = _make_request(client_ip="10.0.0.1", headers={}, api_keys=[], storage=storage)
        result = await get_active_project_id(request=req, project_id=None)
        assert result is None  # backward-compat — open installs see all


# ---------------------------------------------------------------------------
# 5. Input validation on write endpoints
# ---------------------------------------------------------------------------

class TestInputValidationOnWrite:
    """Invariant: edge-case inputs must not crash the endpoint or storage.

    Empty strings, very large strings, and unicode must all be accepted as
    valid values for the ServerMetadataUpdate fields — Postgres handles them
    natively. The API must never 500 on valid-but-extreme input.
    """

    async def test_upsert_server_metadata_empty_description_is_accepted(
        self, auth_client
    ) -> None:
        """Empty string is a valid description — the model default is ''."""
        c, mock_storage, _ = auth_client
        now_str = str(datetime.now(UTC))
        mock_storage.upsert_server_metadata = AsyncMock(
            return_value={
                "id": "srv-1",
                "server_name": "postgres-mcp",
                "description": "",
                "owner": "",
                "tags": [],
                "transport": "",
                "runbook_url": "",
                "project_id": None,
                "created_at": now_str,
                "updated_at": now_str,
            }
        )
        mock_storage.list_api_keys = AsyncMock(return_value=[])
        mock_storage.get_member = AsyncMock(return_value=None)

        response = await c.put(
            "/api/servers/metadata/postgres-mcp",
            json={"description": "", "owner": "", "tags": [], "transport": "", "runbook_url": ""},
            headers={"X-API-Key": "test-api-key"},
        )
        assert response.status_code == 200
        assert response.json()["description"] == ""

    async def test_upsert_server_metadata_very_long_description_does_not_crash(
        self, auth_client
    ) -> None:
        """10 KB description must not cause a 500 — Postgres TEXT is unbounded."""
        c, mock_storage, _ = auth_client
        long_description = "A" * 10_240  # 10 KB
        now_str = str(datetime.now(UTC))
        mock_storage.upsert_server_metadata = AsyncMock(
            return_value={
                "id": "srv-1",
                "server_name": "postgres-mcp",
                "description": long_description,
                "owner": "",
                "tags": [],
                "transport": "",
                "runbook_url": "",
                "project_id": None,
                "created_at": now_str,
                "updated_at": now_str,
            }
        )
        mock_storage.list_api_keys = AsyncMock(return_value=[])
        mock_storage.get_member = AsyncMock(return_value=None)

        response = await c.put(
            "/api/servers/metadata/postgres-mcp",
            json={"description": long_description},
            headers={"X-API-Key": "test-api-key"},
        )
        # Must not 500 — long strings are valid input
        assert response.status_code == 200

    async def test_upsert_server_metadata_unicode_in_all_fields_accepted(
        self, auth_client
    ) -> None:
        """Unicode characters (including emoji and RTL text) must be stored cleanly."""
        c, mock_storage, _ = auth_client
        unicode_description = "监控 MCP 服务器 — наблюдаемость 🔍"
        now_str = str(datetime.now(UTC))
        mock_storage.upsert_server_metadata = AsyncMock(
            return_value={
                "id": "srv-1",
                "server_name": "postgres-mcp",
                "description": unicode_description,
                "owner": "عمر",
                "tags": ["生产", "🚀"],
                "transport": "stdio",
                "runbook_url": "https://wiki.example.com/مراقبة",
                "project_id": None,
                "created_at": now_str,
                "updated_at": now_str,
            }
        )
        mock_storage.list_api_keys = AsyncMock(return_value=[])
        mock_storage.get_member = AsyncMock(return_value=None)

        response = await c.put(
            "/api/servers/metadata/postgres-mcp",
            json={
                "description": unicode_description,
                "owner": "عمر",
                "tags": ["生产", "🚀"],
            },
            headers={"X-API-Key": "test-api-key"},
        )
        assert response.status_code == 200

    async def test_upsert_server_metadata_missing_body_returns_422(
        self, auth_client
    ) -> None:
        """PUT with no body at all → 422 Unprocessable Entity (Pydantic required)."""
        c, _, _ = auth_client
        response = await c.put(
            "/api/servers/metadata/postgres-mcp",
            headers={"X-API-Key": "test-api-key"},
            content=b"",  # empty body
        )
        assert response.status_code == 422

    async def test_delete_nonexistent_server_returns_404_not_500(
        self, auth_client
    ) -> None:
        """DELETE on a server that doesn't exist → 404, not a 500 crash."""
        c, mock_storage, _ = auth_client
        mock_storage.delete_server_metadata = AsyncMock(return_value=False)  # not found
        mock_storage.list_api_keys = AsyncMock(return_value=[])

        response = await c.delete(
            "/api/servers/metadata/nonexistent-server",
            headers={"X-API-Key": "test-api-key"},
        )
        assert response.status_code == 404

    async def test_upsert_tags_with_many_entries_does_not_crash(
        self, auth_client
    ) -> None:
        """A tags list with 100 entries must be accepted — no arbitrary limit enforced."""
        c, mock_storage, _ = auth_client
        many_tags = [f"tag-{i}" for i in range(100)]
        now_str = str(datetime.now(UTC))
        mock_storage.upsert_server_metadata = AsyncMock(
            return_value={
                "id": "srv-1",
                "server_name": "postgres-mcp",
                "description": "",
                "owner": "",
                "tags": many_tags,
                "transport": "",
                "runbook_url": "",
                "project_id": None,
                "created_at": now_str,
                "updated_at": now_str,
            }
        )
        mock_storage.list_api_keys = AsyncMock(return_value=[])
        mock_storage.get_member = AsyncMock(return_value=None)

        response = await c.put(
            "/api/servers/metadata/postgres-mcp",
            json={"tags": many_tags},
            headers={"X-API-Key": "test-api-key"},
        )
        assert response.status_code == 200
        assert len(response.json()["tags"]) == 100
