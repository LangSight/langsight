"""Unit tests for the users management router."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml
from httpx import ASGITransport, AsyncClient

from langsight.api.main import create_app
from langsight.config import load_config
from langsight.models import InviteToken, User, UserRole


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
    storage.list_api_keys = AsyncMock(return_value=[])   # auth disabled
    storage.list_users = AsyncMock(return_value=[])
    storage.get_user_by_email = AsyncMock(return_value=None)
    storage.create_invite = AsyncMock()
    storage.update_user_role = AsyncMock(return_value=True)
    storage.deactivate_user = AsyncMock(return_value=True)
    storage.get_user_by_id = AsyncMock(return_value=None)
    storage.append_audit_log = AsyncMock()
    app.state.storage = storage
    app.state.config = load_config(config_file)
    app.state.dashboard_url = "http://localhost:3002"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, storage


def _user(uid: str = "u1", email: str = "a@test.com") -> User:
    return User(
        id=uid, email=email, password_hash="hashed",
        role=UserRole.VIEWER, active=True, invited_by=None, created_at=datetime.now(UTC),
    )


class TestListUsers:
    async def test_returns_empty_list(self, client) -> None:
        c, storage = client
        storage.list_users = AsyncMock(return_value=[])
        response = await c.get("/api/users")
        assert response.status_code == 200
        assert response.json() == []

    async def test_returns_user_records(self, client) -> None:
        c, storage = client
        storage.list_users = AsyncMock(return_value=[_user()])
        response = await c.get("/api/users")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["email"] == "a@test.com"


class TestInviteUser:
    async def test_returns_201_with_invite_url(self, client) -> None:
        c, storage = client
        storage.get_user_by_email = AsyncMock(return_value=None)
        storage.create_invite = AsyncMock()
        response = await c.post("/api/users/invite", json={"email": "new@test.com", "role": "viewer"})
        assert response.status_code == 201
        data = response.json()
        assert "invite_url" in data
        assert "new@test.com" in data["email"]
        assert "token" in data

    async def test_returns_409_when_email_exists(self, client) -> None:
        c, storage = client
        storage.get_user_by_email = AsyncMock(return_value=_user(email="exists@test.com"))
        response = await c.post("/api/users/invite", json={"email": "exists@test.com", "role": "viewer"})
        assert response.status_code == 409


class TestUpdateUserRole:
    async def test_updates_role_and_returns_200(self, client) -> None:
        c, storage = client
        user = _user()
        storage.get_user_by_id = AsyncMock(return_value=user)
        storage.update_user_role = AsyncMock(return_value=True)
        response = await c.patch("/api/users/u1/role", json={"role": "admin"})
        assert response.status_code == 200

    async def test_returns_404_when_user_not_found(self, client) -> None:
        c, storage = client
        storage.get_user_by_id = AsyncMock(return_value=None)
        response = await c.patch("/api/users/no-such/role", json={"role": "admin"})
        assert response.status_code == 404


class TestDeactivateUser:
    async def test_deactivates_and_returns_204(self, client) -> None:
        c, storage = client
        storage.deactivate_user = AsyncMock(return_value=True)
        response = await c.delete("/api/users/u1")
        assert response.status_code == 204

    async def test_returns_404_when_user_not_found(self, client) -> None:
        c, storage = client
        storage.deactivate_user = AsyncMock(return_value=False)
        response = await c.delete("/api/users/no-such")
        assert response.status_code == 404


class TestAcceptInvite:
    async def test_returns_201_and_creates_user(self, client) -> None:
        c, storage = client
        invite = InviteToken(
            token="validtoken" * 4,  # 40 chars, needs 64
            email="inv@test.com", role=UserRole.VIEWER,
            invited_by="admin", created_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(hours=72),
        )
        # Make token exactly 64 chars
        invite = InviteToken(
            token="a" * 64,
            email="inv@test.com", role=UserRole.VIEWER,
            invited_by="admin", created_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(hours=72),
        )
        storage.get_invite = AsyncMock(return_value=invite)
        storage.get_user_by_email = AsyncMock(return_value=None)
        storage.create_user = AsyncMock()
        storage.mark_invite_used = AsyncMock()
        response = await c.post("/api/users/accept-invite",
                                json={"token": "a" * 64, "password": "securepass123"})
        assert response.status_code == 201
        storage.create_user.assert_called_once()

    async def test_returns_404_for_invalid_token(self, client) -> None:
        c, storage = client
        storage.get_invite = AsyncMock(return_value=None)
        response = await c.post("/api/users/accept-invite",
                                json={"token": "b" * 64, "password": "securepass123"})
        assert response.status_code == 404
