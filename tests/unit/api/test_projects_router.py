"""
Unit tests for the projects router — focusing on regression cases.

Covers:
- POST /api/projects succeeds even when creator_id is a stale user not in DB
  (FK guard: add_member skipped rather than raising 500)
- DELETE /api/projects/{id} returns 204 No Content
- DELETE returns 404 for unknown project
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml
from httpx import ASGITransport, AsyncClient

from langsight.api.main import create_app
from langsight.config import load_config


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    cfg = tmp_path / ".langsight.yaml"
    cfg.write_text(yaml.dump({"servers": []}))
    return cfg


@pytest.fixture
async def client(config_file: Path):
    app = create_app(config_path=config_file)

    mock_storage = MagicMock()
    mock_storage.get_health_history = AsyncMock(return_value=[])
    mock_storage.list_model_pricing = AsyncMock(return_value=[])
    mock_storage.close = AsyncMock()
    mock_storage.get_project_by_slug = AsyncMock(return_value=None)
    mock_storage.create_project = AsyncMock()
    mock_storage.add_member = AsyncMock()
    mock_storage.list_users = AsyncMock(return_value=[])
    mock_storage.get_members = AsyncMock(return_value=[])
    mock_storage.get_project = AsyncMock(return_value=None)

    app.state.storage = mock_storage
    app.state.config = load_config(config_file)
    app.state.api_keys = []

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, mock_storage


# ---------------------------------------------------------------------------
# POST /api/projects — FK guard: stale session user not in DB
# ---------------------------------------------------------------------------


class TestCreateProjectFKGuard:
    """Regression: project creation must not 500 when creator_id is stale."""

    async def test_create_project_succeeds_when_creator_not_in_db(self, client) -> None:
        """POST /api/projects returns 201 even when get_user returns None.

        Reproduces the FK violation bug: after a DB wipe the dashboard session
        cookie still carries the old user_id. Previously add_member was called
        unconditionally, causing asyncpg.ForeignKeyViolationError → 500.
        Now the router verifies the creator exists first and skips add_member.
        """
        c, mock_storage = client
        # Simulate creator not in DB (stale session cookie scenario)
        mock_storage.get_user = AsyncMock(return_value=None)

        response = await c.post(
            "/api/projects",
            json={"name": "My Project"},
            headers={"X-User-Id": "stale-user-id-from-old-db", "X-User-Role": "admin"},
        )

        assert response.status_code == 201
        # Project was created
        mock_storage.create_project.assert_called_once()
        # add_member was NOT called — would have FK-violated
        mock_storage.add_member.assert_not_called()

    async def test_create_project_adds_member_when_creator_exists(self, client) -> None:
        """When creator_id is a real user, add_member IS called."""
        from langsight.models import User, UserRole
        from datetime import UTC, datetime

        c, mock_storage = client
        real_user = User(
            id="real-user-id",
            email="admin@example.com",
            password_hash="x",
            role=UserRole.ADMIN,
            created_at=datetime.now(UTC),
        )
        mock_storage.get_user = AsyncMock(return_value=real_user)

        response = await c.post(
            "/api/projects",
            json={"name": "Real Project"},
            headers={"X-User-Id": "real-user-id", "X-User-Role": "admin"},
        )

        assert response.status_code == 201
        mock_storage.create_project.assert_called_once()
        mock_storage.add_member.assert_called_once()

    async def test_create_project_skips_member_when_system_fallback(self, client) -> None:
        """When creator resolves to 'system' (no session, no API key), add_member is skipped."""
        c, mock_storage = client
        # No X-User-Id header → creator_id falls back to "system"

        response = await c.post("/api/projects", json={"name": "No Auth Project"})

        assert response.status_code == 201
        mock_storage.add_member.assert_not_called()


# ---------------------------------------------------------------------------
# DELETE /api/projects/{id} — returns 204
# ---------------------------------------------------------------------------


class TestDeleteProject:
    """DELETE must return 204 No Content — regression for the 502 proxy bug."""

    async def test_delete_existing_project_returns_204(self, client) -> None:
        """DELETE /api/projects/{id} returns 204 when project exists."""
        from langsight.models import Project
        from datetime import UTC, datetime

        c, mock_storage = client
        project = Project(
            id="proj-abc",
            name="To Delete",
            slug="to-delete",
            created_by="u1",
            created_at=datetime.now(UTC),
        )
        mock_storage.get_project = AsyncMock(return_value=project)
        mock_storage.delete_project = AsyncMock()

        response = await c.delete(
            "/api/projects/proj-abc",
            headers={"X-User-Id": "u1", "X-User-Role": "admin"},
        )

        assert response.status_code == 204
        assert response.content == b""

    async def test_delete_unknown_project_returns_404(self, client) -> None:
        """DELETE /api/projects/{id} returns 404 when project does not exist."""
        c, mock_storage = client
        mock_storage.get_project = AsyncMock(return_value=None)

        response = await c.delete(
            "/api/projects/nonexistent",
            headers={"X-User-Id": "u1", "X-User-Role": "admin"},
        )

        assert response.status_code == 404
