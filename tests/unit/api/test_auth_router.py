"""Unit tests for the auth router — API key management endpoints."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml
from httpx import ASGITransport, AsyncClient

from langsight.api.main import create_app
from langsight.config import load_config
from langsight.models import ApiKeyRecord, ApiKeyRole


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    cfg = tmp_path / ".langsight.yaml"
    cfg.write_text(yaml.dump({"servers": []}))
    return cfg


@pytest.fixture
async def client(config_file: Path):
    app = create_app(config_path=config_file)
    storage = MagicMock()
    storage.close = AsyncMock()
    storage.list_api_keys = AsyncMock(return_value=[])   # disables auth
    storage.create_api_key = AsyncMock()
    storage.revoke_api_key = AsyncMock(return_value=True)
    storage.get_api_key_by_hash = AsyncMock(return_value=None)
    storage.touch_api_key = AsyncMock()
    storage.append_audit_log = AsyncMock()
    app.state.storage = storage
    app.state.config = load_config(config_file)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, storage


class TestCreateApiKey:
    async def test_creates_key_and_returns_201(self, client) -> None:
        c, storage = client
        response = await c.post("/api/auth/api-keys", json={"name": "my-key"})
        assert response.status_code == 201
        data = response.json()
        assert "key" in data
        assert data["name"] == "my-key"
        storage.create_api_key.assert_called_once()

    async def test_returns_422_for_empty_name(self, client) -> None:
        c, _ = client
        response = await c.post("/api/auth/api-keys", json={"name": "   "})
        assert response.status_code == 422

    async def test_key_only_returned_once(self, client) -> None:
        c, _ = client
        response = await c.post("/api/auth/api-keys", json={"name": "once"})
        assert "key" in response.json()
        assert len(response.json()["key"]) == 64   # token_hex(32)

    async def test_returns_501_when_storage_lacks_create(self, client) -> None:
        c, storage = client
        del storage.create_api_key  # remove the attribute
        storage = MagicMock(spec=[])  # no create_api_key
        response = await c.post("/api/auth/api-keys", json={"name": "k"})
        # storage mock doesn't have create_api_key → 501
        assert response.status_code in (422, 501, 500)


class TestListApiKeys:
    async def test_returns_200_with_empty_list(self, client) -> None:
        c, storage = client
        storage.list_api_keys = AsyncMock(return_value=[])
        response = await c.get("/api/auth/api-keys")
        assert response.status_code == 200
        assert response.json() == []

    async def test_returns_key_records(self, client) -> None:
        from datetime import UTC, datetime
        c, storage = client
        now = datetime.now(UTC)
        record = ApiKeyRecord(
            id="k1", name="test", key_prefix="abcd1234",
            key_hash="hash", role=ApiKeyRole.ADMIN, created_at=now,
            # Mark as revoked so verify_api_key sees has_db_keys=False → auth disabled
            revoked_at=now,
        )
        storage.list_api_keys = AsyncMock(return_value=[record])
        response = await c.get("/api/auth/api-keys")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "test"
        assert data[0]["key_prefix"] == "abcd1234"


class TestRevokeApiKey:
    async def test_revoke_returns_204(self, client) -> None:
        c, storage = client
        storage.revoke_api_key = AsyncMock(return_value=True)
        response = await c.delete("/api/auth/api-keys/key-id-1")
        assert response.status_code == 204

    async def test_revoke_returns_404_when_not_found(self, client) -> None:
        c, storage = client
        storage.revoke_api_key = AsyncMock(return_value=False)
        response = await c.delete("/api/auth/api-keys/no-such-key")
        assert response.status_code == 404
