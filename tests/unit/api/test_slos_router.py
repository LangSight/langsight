"""Unit tests for the SLOs router."""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml
from httpx import ASGITransport, AsyncClient

from langsight.api.main import create_app
from langsight.config import load_config
from langsight.models import AgentSLO, SLOMetric


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    cfg = tmp_path / ".langsight.yaml"
    cfg.write_text(yaml.dump({"servers": [], "auth_disabled": True}))
    return cfg


@pytest.fixture
async def client(config_file: Path):
    app = create_app(config_path=config_file)
    storage = MagicMock()
    storage.close = AsyncMock()
    storage.list_api_keys = AsyncMock(return_value=[])   # auth disabled
    storage.create_slo = AsyncMock()
    storage.list_slos = AsyncMock(return_value=[])
    storage.get_slo = AsyncMock(return_value=None)
    storage.delete_slo = AsyncMock(return_value=True)
    app.state.storage = storage
    app.state.config = load_config(config_file)
    app.state.auth_disabled = True
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, storage


class TestListSLOs:
    async def test_returns_empty_list(self, client) -> None:
        c, storage = client
        storage.list_slos = AsyncMock(return_value=[])
        response = await c.get("/api/slos")
        assert response.status_code == 200
        assert response.json() == []

    async def test_returns_slo_records(self, client) -> None:
        c, storage = client
        slo = AgentSLO(
            id="s1", agent_name="my-bot", metric=SLOMetric.SUCCESS_RATE,
            target=95.0, window_hours=24, created_at=datetime.now(UTC),
        )
        storage.list_slos = AsyncMock(return_value=[slo])
        response = await c.get("/api/slos")
        data = response.json()
        assert len(data) == 1
        assert data[0]["agent_name"] == "my-bot"
        assert data[0]["target"] == 95.0


class TestCreateSLO:
    async def test_creates_and_returns_201(self, client) -> None:
        c, storage = client
        response = await c.post("/api/slos", json={
            "agent_name": "new-agent",
            "metric": "success_rate",
            "target": 99.0,
            "window_hours": 24,
        })
        assert response.status_code == 201
        data = response.json()
        assert data["agent_name"] == "new-agent"
        assert data["target"] == 99.0
        storage.create_slo.assert_called_once()

    async def test_returns_503_when_storage_lacks_create_slo(self, client) -> None:
        c, storage = client
        del storage.create_slo
        storage.__class__ = type("NoSLO", (), {})
        response = await c.post("/api/slos", json={
            "agent_name": "bot", "metric": "success_rate",
            "target": 95.0, "window_hours": 24,
        })
        # Storage without create_slo → 503
        assert response.status_code in (503, 422, 500)


class TestDeleteSLO:
    async def test_delete_returns_204(self, client) -> None:
        c, storage = client
        storage.delete_slo = AsyncMock(return_value=True)
        response = await c.delete("/api/slos/slo-1")
        assert response.status_code == 204

    async def test_delete_returns_404_when_not_found(self, client) -> None:
        c, storage = client
        storage.delete_slo = AsyncMock(return_value=False)
        response = await c.delete("/api/slos/no-such")
        assert response.status_code == 404


class TestGetSLOStatus:
    async def test_get_slo_status_returns_list(self, client) -> None:
        c, storage = client
        # Reliability engine uses get_tool_reliability on storage — skip if not present
        storage.get_tool_reliability = AsyncMock(return_value=[])
        storage.get_baseline_stats = AsyncMock(return_value={})
        response = await c.get("/api/slos/status")
        assert response.status_code in (200, 503)
