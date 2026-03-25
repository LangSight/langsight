"""
Unit tests for /api/settings auth enforcement.

Security invariants proven here:

  1. GET /api/settings without any API key returns 401 when auth is enabled.
     (Before the fix this returned 200 — the endpoint lacked the verify_api_key
      dependency.)

  2. PUT /api/settings without any API key returns 401.

  3. PUT /api/settings with a valid non-admin (viewer) API key returns 403.
     Only the admin role may write instance settings.

  4. GET /api/settings with a valid API key returns 200.

  5. PUT /api/settings with an admin API key returns 200 and persists the
     settings through the storage layer.

All tests run offline — no DB, no Docker, no network.
"""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml
from httpx import ASGITransport, AsyncClient

from langsight.api.main import create_app
from langsight.config import load_config
from langsight.models import ApiKeyRecord, ApiKeyRole

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# Constants used across fixtures
# ---------------------------------------------------------------------------

_ADMIN_KEY = "ls_adminkey_000000000000000000000000000000000000000000000000000"
_VIEWER_KEY = "ls_viewerkey_00000000000000000000000000000000000000000000000000"

_ADMIN_KEY_HASH = hashlib.sha256(_ADMIN_KEY.encode()).hexdigest()
_VIEWER_KEY_HASH = hashlib.sha256(_VIEWER_KEY.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_config_file(tmp_path: Path) -> Path:
    cfg = tmp_path / ".langsight.yaml"
    cfg.write_text(yaml.dump({"servers": []}))
    return cfg


def _make_admin_record() -> ApiKeyRecord:
    return ApiKeyRecord(
        id="admin-key-id",
        name="admin",
        key_prefix=_ADMIN_KEY[:8],
        key_hash=_ADMIN_KEY_HASH,
        role=ApiKeyRole.ADMIN,
        created_at=datetime.now(UTC),
    )


def _make_viewer_record() -> ApiKeyRecord:
    return ApiKeyRecord(
        id="viewer-key-id",
        name="viewer",
        key_prefix=_VIEWER_KEY[:8],
        key_hash=_VIEWER_KEY_HASH,
        role=ApiKeyRole.VIEWER,
        created_at=datetime.now(UTC),
    )


def _base_storage(keys: list[ApiKeyRecord]) -> MagicMock:
    """Storage mock with API-key auth enabled (has active DB keys)."""
    storage = MagicMock()
    storage.close = AsyncMock()
    storage.list_api_keys = AsyncMock(return_value=keys)
    storage.touch_api_key = AsyncMock()
    storage.append_audit_log = AsyncMock()
    storage.get_instance_settings = AsyncMock(return_value={"redact_payloads": False})
    storage.save_instance_settings = AsyncMock()
    return storage


async def _make_client(
    tmp_path: Path,
    storage: MagicMock,
) -> AsyncClient:
    """Create a TestClient whose app.state has the supplied storage."""
    config_file = _make_config_file(tmp_path)
    app = create_app(config_path=config_file)
    app.state.storage = storage
    app.state.config = load_config(config_file)
    app.state.api_keys = []  # no env-var bootstrap keys
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ---------------------------------------------------------------------------
# 1. GET /api/settings — auth enforcement
# ---------------------------------------------------------------------------


class TestGetSettingsAuthEnforcement:
    """GET /api/settings must require authentication when keys are configured."""

    async def test_get_settings_without_key_returns_401(self, tmp_path: Path) -> None:
        """Regression: endpoint was unprotected before the fix (returned 200).

        When at least one active API key exists in the DB, an unauthenticated
        request must receive 401, not 200.
        """
        admin = _make_admin_record()
        storage = _base_storage([admin])
        # get_api_key_by_hash returns None — no key header was sent
        storage.get_api_key_by_hash = AsyncMock(return_value=None)

        async with await _make_client(tmp_path, storage) as c:
            response = await c.get("/api/settings")

        assert response.status_code == 401, (
            f"Expected 401 (unauthenticated), got {response.status_code}. "
            "GET /api/settings must enforce verify_api_key."
        )

    async def test_get_settings_without_key_returns_www_authenticate_header(
        self, tmp_path: Path
    ) -> None:
        """401 response must include WWW-Authenticate header per RFC 9110."""
        admin = _make_admin_record()
        storage = _base_storage([admin])
        storage.get_api_key_by_hash = AsyncMock(return_value=None)

        async with await _make_client(tmp_path, storage) as c:
            response = await c.get("/api/settings")

        assert response.status_code == 401
        assert "WWW-Authenticate" in response.headers

    async def test_get_settings_with_valid_admin_key_returns_200(
        self, tmp_path: Path
    ) -> None:
        """A valid admin API key must be accepted for GET /api/settings."""
        admin = _make_admin_record()
        storage = _base_storage([admin])
        storage.get_api_key_by_hash = AsyncMock(return_value=admin)

        async with await _make_client(tmp_path, storage) as c:
            response = await c.get(
                "/api/settings",
                headers={"X-API-Key": _ADMIN_KEY},
            )

        assert response.status_code == 200

    async def test_get_settings_with_valid_key_returns_settings_body(
        self, tmp_path: Path
    ) -> None:
        """Authenticated GET must return the settings dict from storage."""
        admin = _make_admin_record()
        storage = _base_storage([admin])
        storage.get_api_key_by_hash = AsyncMock(return_value=admin)
        storage.get_instance_settings = AsyncMock(return_value={"redact_payloads": True})

        async with await _make_client(tmp_path, storage) as c:
            response = await c.get(
                "/api/settings",
                headers={"X-API-Key": _ADMIN_KEY},
            )

        assert response.status_code == 200
        assert response.json() == {"redact_payloads": True}

    async def test_get_settings_with_viewer_key_returns_200(
        self, tmp_path: Path
    ) -> None:
        """GET /api/settings requires authentication but NOT admin role.

        A viewer key should be allowed to read settings.
        """
        viewer = _make_viewer_record()
        storage = _base_storage([viewer])
        storage.get_api_key_by_hash = AsyncMock(return_value=viewer)

        async with await _make_client(tmp_path, storage) as c:
            response = await c.get(
                "/api/settings",
                headers={"X-API-Key": _VIEWER_KEY},
            )

        # GET only requires authentication (verify_api_key), not admin role
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# 2. PUT /api/settings — auth + admin-role enforcement
# ---------------------------------------------------------------------------


class TestPutSettingsAuthEnforcement:
    """PUT /api/settings must require both authentication AND admin role."""

    async def test_put_settings_without_key_returns_401(self, tmp_path: Path) -> None:
        """Unauthenticated PUT must receive 401."""
        admin = _make_admin_record()
        storage = _base_storage([admin])
        storage.get_api_key_by_hash = AsyncMock(return_value=None)

        async with await _make_client(tmp_path, storage) as c:
            response = await c.put(
                "/api/settings",
                json={"redact_payloads": True},
            )

        assert response.status_code == 401, (
            f"Expected 401 (unauthenticated), got {response.status_code}."
        )

    async def test_put_settings_with_viewer_key_returns_403(
        self, tmp_path: Path
    ) -> None:
        """A non-admin (viewer) key must receive 403 on PUT /api/settings.

        The require_admin dependency protects the write path. Viewers must
        not be able to change global settings.
        """
        viewer = _make_viewer_record()
        # list_api_keys returns the viewer key so auth is enabled
        storage = _base_storage([viewer])
        storage.get_api_key_by_hash = AsyncMock(return_value=viewer)

        async with await _make_client(tmp_path, storage) as c:
            response = await c.put(
                "/api/settings",
                json={"redact_payloads": True},
                headers={"X-API-Key": _VIEWER_KEY},
            )

        assert response.status_code == 403, (
            f"Expected 403 (viewer role blocked from write), got {response.status_code}."
        )

    async def test_put_settings_with_admin_key_returns_200(
        self, tmp_path: Path
    ) -> None:
        """An admin API key must be accepted for PUT /api/settings."""
        admin = _make_admin_record()
        storage = _base_storage([admin])
        storage.get_api_key_by_hash = AsyncMock(return_value=admin)

        async with await _make_client(tmp_path, storage) as c:
            response = await c.put(
                "/api/settings",
                json={"redact_payloads": True},
                headers={"X-API-Key": _ADMIN_KEY},
            )

        assert response.status_code == 200

    async def test_put_settings_persists_via_storage(self, tmp_path: Path) -> None:
        """PUT must call save_instance_settings on the storage backend."""
        admin = _make_admin_record()
        storage = _base_storage([admin])
        storage.get_api_key_by_hash = AsyncMock(return_value=admin)
        storage.save_instance_settings = AsyncMock()
        storage.get_instance_settings = AsyncMock(return_value={"redact_payloads": True})

        async with await _make_client(tmp_path, storage) as c:
            await c.put(
                "/api/settings",
                json={"redact_payloads": True},
                headers={"X-API-Key": _ADMIN_KEY},
            )

        storage.save_instance_settings.assert_called_once()
        call_args = storage.save_instance_settings.call_args[0]
        assert call_args[0] == {"redact_payloads": True}

    async def test_put_settings_returns_updated_settings_body(
        self, tmp_path: Path
    ) -> None:
        """PUT must return the saved settings (from get_instance_settings) in the body."""
        admin = _make_admin_record()
        storage = _base_storage([admin])
        storage.get_api_key_by_hash = AsyncMock(return_value=admin)
        storage.get_instance_settings = AsyncMock(return_value={"redact_payloads": True})

        async with await _make_client(tmp_path, storage) as c:
            response = await c.put(
                "/api/settings",
                json={"redact_payloads": True},
                headers={"X-API-Key": _ADMIN_KEY},
            )

        assert response.json() == {"redact_payloads": True}

    async def test_put_settings_viewer_cannot_toggle_redact_payloads(
        self, tmp_path: Path
    ) -> None:
        """Specific regression check: viewer must not be able to disable payload redaction.

        redact_payloads controls PII exposure in the UI. A viewer toggling it
        off would be a privilege escalation.
        """
        viewer = _make_viewer_record()
        storage = _base_storage([viewer])
        storage.get_api_key_by_hash = AsyncMock(return_value=viewer)

        async with await _make_client(tmp_path, storage) as c:
            response = await c.put(
                "/api/settings",
                json={"redact_payloads": False},
                headers={"X-API-Key": _VIEWER_KEY},
            )

        # Must be blocked — 403 from require_admin dependency
        assert response.status_code == 403
        # Storage must NOT have been called
        storage.save_instance_settings.assert_not_called()


# ---------------------------------------------------------------------------
# 3. Auth disabled (no keys) — open install
# ---------------------------------------------------------------------------


class TestSettingsAuthDisabled:
    """When no API keys are configured at all, auth is disabled (open install).

    Both GET and PUT must succeed without any X-API-Key header.
    """

    async def test_get_settings_without_key_returns_200_when_auth_disabled(
        self, tmp_path: Path
    ) -> None:
        """No keys configured → auth disabled → 200 on GET without header."""
        storage = _base_storage(keys=[])  # empty list → no active keys
        storage.get_api_key_by_hash = AsyncMock(return_value=None)

        async with await _make_client(tmp_path, storage) as c:
            response = await c.get("/api/settings")

        assert response.status_code == 200

    async def test_put_settings_without_key_returns_200_when_auth_disabled(
        self, tmp_path: Path
    ) -> None:
        """No keys configured → auth disabled → 200 on PUT without header."""
        storage = _base_storage(keys=[])
        storage.get_api_key_by_hash = AsyncMock(return_value=None)

        async with await _make_client(tmp_path, storage) as c:
            response = await c.put("/api/settings", json={"redact_payloads": False})

        assert response.status_code == 200
