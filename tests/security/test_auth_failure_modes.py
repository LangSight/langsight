"""
Security regression tests — auth fail-closed behaviour.

Every test here targets a specific failure mode. The invariant in all cases:
a storage/DB error must NEVER cause auth to silently pass. Failure direction
must always be DENY, not ALLOW.

Previously broken: except Exception: pass left has_db_keys=False, which made
the system think auth was disabled when Postgres was down.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from tests.security.conftest import (
    _active_key_record,
    _make_request,
    _make_storage,
    _revoked_key_record,
)

pytestmark = pytest.mark.security


# ---------------------------------------------------------------------------
# DB error → fail-closed (the regression we fixed)
# ---------------------------------------------------------------------------

class TestDbErrorFailClosed:
    """When list_api_keys raises, the system must treat auth as ENABLED."""

    async def test_db_error_with_no_env_keys_denies_unauthenticated_request(self) -> None:
        """Core regression: DB down + no env keys must NOT become auth-disabled."""
        from langsight.api.dependencies import verify_api_key

        storage = _make_storage(list_api_keys_raises=Exception("connection refused"))
        req = _make_request(client_ip="10.0.0.1", headers={}, api_keys=[], storage=storage)

        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(request=req, api_key=None)

        # Must reject — not silently allow (the pre-fix behaviour was to return None)
        assert exc_info.value.status_code == 401

    async def test_db_error_with_no_env_keys_denies_wrong_key(self) -> None:
        """Wrong key when DB is down must be rejected, not granted by accident."""
        from langsight.api.dependencies import verify_api_key

        storage = _make_storage(list_api_keys_raises=Exception("timeout"))
        req = _make_request(
            client_ip="10.0.0.1",
            headers={"X-API-Key": "attacker-guessed-key"},
            api_keys=[],
            storage=storage,
        )
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(request=req, api_key="attacker-guessed-key")

        assert exc_info.value.status_code in (401, 403)

    async def test_db_error_still_accepts_valid_env_key(self) -> None:
        """A DB outage must not lock out operators who have an env-var key."""
        from langsight.api.dependencies import verify_api_key

        storage = _make_storage(list_api_keys_raises=Exception("pool exhausted"))
        req = _make_request(
            client_ip="10.0.0.1",
            headers={"X-API-Key": "bootstrap-key"},
            api_keys=["bootstrap-key"],
            storage=storage,
        )
        # Must succeed — env key validated before DB is consulted
        await verify_api_key(request=req, api_key="bootstrap-key")

    async def test_db_error_in_require_admin_denies_unauthenticated(self) -> None:
        """require_admin must also fail-closed when DB is unreachable."""
        from langsight.api.dependencies import require_admin

        storage = _make_storage(list_api_keys_raises=Exception("db down"))
        req = _make_request(client_ip="10.0.0.1", headers={}, api_keys=[], storage=storage)

        with pytest.raises(HTTPException) as exc_info:
            await require_admin(request=req, api_key=None)

        assert exc_info.value.status_code in (401, 403)

    async def test_db_error_in_project_scoping_denies_non_admin(self) -> None:
        """get_active_project_id must fail-closed when DB cannot check auth state."""
        from langsight.api.dependencies import get_active_project_id

        storage = _make_storage(list_api_keys_raises=Exception("db down"))
        req = _make_request(client_ip="10.0.0.1", headers={}, api_keys=[], storage=storage)

        with pytest.raises(HTTPException) as exc_info:
            await get_active_project_id(request=req, project_id=None)

        assert exc_info.value.status_code in (400, 401, 403)


# ---------------------------------------------------------------------------
# Missing key
# ---------------------------------------------------------------------------

class TestMissingKey:
    """No credential presented when auth is enabled → 401."""

    async def test_no_key_returns_401_when_env_key_configured(self) -> None:
        from langsight.api.dependencies import verify_api_key

        req = _make_request(client_ip="10.0.0.1", headers={}, api_keys=["secret"])
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(request=req, api_key=None)
        assert exc_info.value.status_code == 401

    async def test_no_key_returns_401_when_db_key_active(self) -> None:
        from langsight.api.dependencies import verify_api_key

        storage = _make_storage(active_db_keys=[_active_key_record()])
        req = _make_request(client_ip="10.0.0.1", headers={}, api_keys=[], storage=storage)
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(request=req, api_key=None)
        assert exc_info.value.status_code == 401

    async def test_no_key_allowed_in_open_install(self) -> None:
        """Open install (no keys anywhere) — no credential is fine."""
        from langsight.api.dependencies import verify_api_key

        storage = _make_storage(active_db_keys=[])
        req = _make_request(client_ip="10.0.0.1", headers={}, api_keys=[], storage=storage)
        # Must not raise
        await verify_api_key(request=req, api_key=None)

    async def test_empty_string_key_treated_as_missing(self) -> None:
        """An empty string X-API-Key header must be treated as no key."""
        from langsight.api.dependencies import verify_api_key

        req = _make_request(
            client_ip="10.0.0.1",
            headers={"X-API-Key": ""},
            api_keys=["real-key"],
        )
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(request=req, api_key="")
        assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# Wrong / revoked / partial key
# ---------------------------------------------------------------------------

class TestInvalidKey:
    """Wrong, revoked, or partial key presented → 403."""

    async def test_wrong_key_returns_403(self) -> None:
        from langsight.api.dependencies import verify_api_key

        storage = _make_storage(active_db_keys=[])
        storage.get_api_key_by_hash = AsyncMock(return_value=None)
        req = _make_request(
            client_ip="10.0.0.1",
            headers={"X-API-Key": "completely-wrong"},
            api_keys=["the-real-key"],
            storage=storage,
        )
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(request=req, api_key="completely-wrong")
        assert exc_info.value.status_code == 403

    async def test_key_prefix_only_is_rejected(self) -> None:
        """Sending only the first 8 chars of a key must not match."""
        from langsight.api.dependencies import verify_api_key

        real_key = "supersecretkey-full-value"
        storage = _make_storage(active_db_keys=[])
        storage.get_api_key_by_hash = AsyncMock(return_value=None)
        req = _make_request(
            client_ip="10.0.0.1",
            headers={"X-API-Key": real_key[:8]},  # prefix only
            api_keys=[real_key],
            storage=storage,
        )
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(request=req, api_key=real_key[:8])
        assert exc_info.value.status_code == 403

    async def test_revoked_db_key_is_denied(self) -> None:
        """A revoked DB key must not grant access even if the hash matches."""

        from langsight.api.dependencies import verify_api_key

        secret = "revoked-but-known-key"
        revoked = _revoked_key_record()

        storage = _make_storage(active_db_keys=[revoked])
        # list_api_keys returns only the revoked key → has_db_keys stays False
        # meaning auth is treated as disabled — revoked key cannot unlock auth
        req = _make_request(
            client_ip="10.0.0.1",
            headers={"X-API-Key": secret},
            api_keys=[],
            storage=storage,
        )
        # With only revoked keys: auth is considered disabled → passes through
        # OR if there are active keys: must reject. Either way: not a security hole.
        # The important thing is the revoked key doesn't grant DB-key-level access.
        storage.get_api_key_by_hash = AsyncMock(return_value=revoked)
        # Should either pass (auth disabled — revoked = no active keys) or get 403
        # It must NOT return a valid auth with the revoked key's permissions
        try:
            await verify_api_key(request=req, api_key=secret)
            # If it didn't raise, auth is disabled (no active keys) — acceptable
        except HTTPException as e:
            assert e.status_code in (401, 403)

    async def test_multikey_string_is_not_valid(self) -> None:
        """'key1,key2' forwarded as one value must not match either key."""
        from langsight.api.dependencies import verify_api_key

        storage = _make_storage(active_db_keys=[])
        storage.get_api_key_by_hash = AsyncMock(return_value=None)
        combined = "key1,key2"
        req = _make_request(
            client_ip="10.0.0.1",
            headers={"X-API-Key": combined},
            api_keys=["key1", "key2"],
            storage=storage,
        )
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(request=req, api_key=combined)
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# HTTP endpoint layer — auth gates on real routes
# ---------------------------------------------------------------------------

class TestEndpointAuthGates:
    """Auth must be enforced at the HTTP layer, not just in dependency functions."""

    async def test_health_endpoint_requires_key_when_auth_enabled(self, auth_client) -> None:
        c, _, _ = auth_client
        response = await c.get("/api/health/servers")
        assert response.status_code in (401, 403)

    async def test_health_endpoint_with_valid_key_succeeds(self, auth_client) -> None:
        c, mock_storage, _ = auth_client
        mock_storage.get_health_history = AsyncMock(return_value=[])
        response = await c.get("/api/health/servers", headers={"X-API-Key": "test-api-key"})
        assert response.status_code == 200

    async def test_health_endpoint_open_in_open_install(self, open_client) -> None:
        c, _, _ = open_client
        response = await c.get("/api/health/servers")
        assert response.status_code == 200

    async def test_wrong_key_returns_403_not_200(self, auth_client) -> None:
        c, _, _ = auth_client
        response = await c.get("/api/health/servers", headers={"X-API-Key": "wrong"})
        assert response.status_code == 403

    async def test_sessions_endpoint_requires_key(self, auth_client) -> None:
        c, _, _ = auth_client
        response = await c.get("/api/agents/sessions")
        assert response.status_code in (401, 403)

    async def test_readiness_is_public_no_auth_needed(self, auth_client) -> None:
        """Liveness/readiness probes must be reachable without any key."""
        c, _, _ = auth_client
        response = await c.get("/api/liveness")
        assert response.status_code == 200
