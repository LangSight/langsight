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


class TestGetServerInvocations:
    """GET /api/health/servers/invocations — must not be shadowed by /{server_name}."""

    async def test_invocations_endpoint_returns_200(self, client) -> None:
        """Route is reachable and returns 200 OK."""
        c, mock_storage = client
        mock_storage.get_server_invocation_stats = AsyncMock(return_value=[])
        response = await c.get("/api/health/servers/invocations")
        assert response.status_code == 200

    async def test_invocations_returns_empty_list_when_no_data(self, client) -> None:
        """Returns [] when storage has no invocation stats."""
        c, mock_storage = client
        mock_storage.get_server_invocation_stats = AsyncMock(return_value=[])
        data = (await c.get("/api/health/servers/invocations")).json()
        assert data == []

    async def test_invocations_returns_data_from_storage(self, client) -> None:
        """Returns the list produced by storage.get_server_invocation_stats."""
        c, mock_storage = client
        mock_storage.get_server_invocation_stats = AsyncMock(return_value=[
            {
                "server_name": "postgres-mcp",
                "last_called_at": "2026-03-25T10:00:00+00:00",
                "last_call_ok": True,
                "last_call_status": "success",
                "total_calls": 42,
                "success_rate_pct": 97.6,
            }
        ])
        data = (await c.get("/api/health/servers/invocations")).json()
        assert len(data) == 1
        assert data[0]["server_name"] == "postgres-mcp"
        assert data[0]["last_call_ok"] is True
        assert data[0]["total_calls"] == 42

    async def test_invocations_returns_empty_list_when_storage_has_no_method(
        self, tmp_path: Path
    ) -> None:
        """If storage does not have get_server_invocation_stats, returns []
        (graceful degradation — old storage backends keep working).

        Uses a spec-restricted mock so getattr(storage, 'get_server_invocation_stats', None)
        truly returns None — matching the router's guard condition.
        """
        from langsight.storage.base import StorageBackend

        # Create a MagicMock that only has methods defined on StorageBackend.
        # get_server_invocation_stats is NOT on StorageBackend, so getattr
        # with default=None will return None — triggering the [] early return.
        bare_storage = MagicMock(spec=StorageBackend)
        bare_storage.list_api_keys = AsyncMock(return_value=[])
        bare_storage.get_health_history = AsyncMock(return_value=[_result()])
        bare_storage.get_distinct_health_server_names = AsyncMock(return_value=set())
        bare_storage.close = AsyncMock()

        cfg = tmp_path / ".langsight.yaml"
        cfg.write_text(yaml.dump({"servers": []}))

        app = create_app(config_path=cfg)
        app.state.storage = bare_storage
        app.state.config = load_config(cfg)
        app.state.api_keys = []

        from httpx import ASGITransport, AsyncClient
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c2:
            response = await c2.get("/api/health/servers/invocations")

        assert response.status_code == 200
        assert response.json() == []

    async def test_invocations_not_shadowed_by_server_name_route(self, client) -> None:
        """'invocations' must not be treated as a {server_name} path parameter.

        If the route ordering is wrong, GET /servers/invocations would hit
        GET /servers/{server_name} with server_name='invocations' and return
        404 instead of the invocation stats list.
        """
        c, mock_storage = client
        mock_storage.get_server_invocation_stats = AsyncMock(return_value=[])
        # This must NOT return 404
        response = await c.get("/api/health/servers/invocations")
        assert response.status_code != 404

    async def test_invocations_default_hours_param(self, client) -> None:
        """Default ?hours=168 is accepted (within the 1–720 range)."""
        c, mock_storage = client
        mock_storage.get_server_invocation_stats = AsyncMock(return_value=[])
        response = await c.get("/api/health/servers/invocations?hours=168")
        assert response.status_code == 200

    async def test_invocations_hours_out_of_range_rejected(self, client) -> None:
        """hours=0 is below the minimum of 1 — must return 422."""
        c, mock_storage = client
        response = await c.get("/api/health/servers/invocations?hours=0")
        assert response.status_code == 422

    async def test_invocations_hours_above_maximum_rejected(self, client) -> None:
        """hours=721 is above the maximum of 720 — must return 422."""
        c, mock_storage = client
        response = await c.get("/api/health/servers/invocations?hours=721")
        assert response.status_code == 422

    async def test_invocations_calls_storage_with_project_id(self, client) -> None:
        """project_id from auth must be forwarded to get_server_invocation_stats."""
        c, mock_storage = client
        mock_storage.get_server_invocation_stats = AsyncMock(return_value=[])
        await c.get("/api/health/servers/invocations")
        mock_storage.get_server_invocation_stats.assert_called_once()


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
