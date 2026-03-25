from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml
from httpx import ASGITransport, AsyncClient

from langsight.api.main import create_app
from langsight.config import load_config
from langsight.models import HealthCheckResult, ServerStatus


def _result(
    name: str = "pg",
    status: ServerStatus = ServerStatus.UP,
    latency_ms: float = 42.0,
    tools_count: int = 5,
    schema_hash: str = "abc123",
    error: str | None = None,
) -> HealthCheckResult:
    return HealthCheckResult(
        server_name=name,
        status=status,
        latency_ms=latency_ms,
        tools_count=tools_count,
        schema_hash=schema_hash,
        error=error,
        checked_at=datetime(2026, 3, 16, 12, 0, 0, tzinfo=UTC),
    )


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    cfg = tmp_path / ".langsight.yaml"
    cfg.write_text(yaml.dump({
        "servers": [
            {"name": "pg", "transport": "stdio", "command": "python server.py"},
            {"name": "s3", "transport": "stdio", "command": "python s3.py"},
        ]
    }))
    return cfg


@pytest.fixture
async def client(config_file: Path):
    """Create a test client with mocked app.state (bypasses lifespan)."""
    mock_storage = MagicMock()
    mock_storage.get_health_history = AsyncMock(return_value=[_result()])
    mock_storage.save_health_result = AsyncMock()
    mock_storage.get_latest_schema_hash = AsyncMock(return_value=None)
    mock_storage.save_schema_snapshot = AsyncMock()
    mock_storage.close = AsyncMock()

    app = create_app(config_path=config_file)
    # Inject state directly — ASGITransport doesn't trigger lifespan
    app.state.storage = mock_storage
    app.state.config = load_config(config_file)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c, mock_storage


class TestApiStatus:
    async def test_status_returns_200(self, client) -> None:
        c, _ = client
        response = await c.get("/api/status")
        assert response.status_code == 200

    async def test_status_body(self, client) -> None:
        """Verify /api/status returns only minimal public fields (no fingerprinting)."""
        c, _ = client
        data = (await c.get("/api/status")).json()
        assert data["status"] == "ok"
        assert "version" in data
        # Sensitive fields stripped — must not be present in the public response
        assert "servers_configured" not in data
        assert "auth_enabled" not in data
        assert "storage_mode" not in data


class TestListServersHealth:
    async def test_returns_200(self, client) -> None:
        c, _ = client
        assert (await c.get("/api/health/servers")).status_code == 200

    async def test_returns_list(self, client) -> None:
        c, _ = client
        data = (await c.get("/api/health/servers")).json()
        assert isinstance(data, list)

    async def test_result_has_correct_fields(self, client) -> None:
        c, _ = client
        data = (await c.get("/api/health/servers")).json()
        assert len(data) > 0
        item = data[0]
        assert "server_name" in item
        assert "status" in item
        assert "latency_ms" in item


class TestGetServerHealth:
    async def test_returns_200_for_known_server(self, client) -> None:
        c, _ = client
        assert (await c.get("/api/health/servers/pg")).status_code == 200

    async def test_returns_correct_server(self, client) -> None:
        c, _ = client
        data = (await c.get("/api/health/servers/pg")).json()
        assert data["server_name"] == "pg"
        assert data["status"] == "up"

    async def test_returns_404_for_unknown_server(self, client) -> None:
        c, mock_storage = client
        mock_storage.get_health_history.return_value = []
        assert (await c.get("/api/health/servers/unknown")).status_code == 404

    async def test_404_detail_mentions_server_name(self, client) -> None:
        c, mock_storage = client
        mock_storage.get_health_history.return_value = []
        data = (await c.get("/api/health/servers/nonexistent")).json()
        assert "nonexistent" in data["detail"]


class TestGetServerHistory:
    async def test_returns_list(self, client) -> None:
        c, _ = client
        data = (await c.get("/api/health/servers/pg/history")).json()
        assert isinstance(data, list)

    async def test_limit_param_passed_to_storage(self, client) -> None:
        c, mock_storage = client
        await c.get("/api/health/servers/pg/history?limit=25")
        mock_storage.get_health_history.assert_called_with("pg", limit=25, project_id=None)

    async def test_limit_over_100_rejected(self, client) -> None:
        c, _ = client
        assert (await c.get("/api/health/servers/pg/history?limit=500")).status_code == 422


class TestTriggerHealthCheck:
    async def test_returns_200(self, client) -> None:
        c, _ = client
        with patch("langsight.api.routers.health.HealthChecker") as MockChecker:
            MockChecker.return_value.check_many = AsyncMock(return_value=[_result()])
            assert (await c.post("/api/health/check")).status_code == 200

    async def test_returns_results_list(self, client) -> None:
        c, _ = client
        with patch("langsight.api.routers.health.HealthChecker") as MockChecker:
            MockChecker.return_value.check_many = AsyncMock(return_value=[_result()])
            data = (await c.post("/api/health/check")).json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["server_name"] == "pg"

    async def test_no_servers_returns_empty(self, tmp_path: Path) -> None:
        cfg = tmp_path / ".langsight.yaml"
        cfg.write_text(yaml.dump({"servers": []}))
        app = create_app(config_path=cfg)
        app.state.storage = MagicMock()
        app.state.config = load_config(cfg)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            data = (await c.post("/api/health/check")).json()
        assert data == []
