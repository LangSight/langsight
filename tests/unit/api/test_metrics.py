"""Tests for Prometheus /metrics endpoint and instrumentation."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from langsight.api.metrics import _normalize_path


# ---------------------------------------------------------------------------
# Path normalization
# ---------------------------------------------------------------------------

class TestNormalizePath:
    def test_simple_path_unchanged(self) -> None:
        assert _normalize_path("/api/health/servers") == "/api/health/servers"

    def test_uuid_collapsed(self) -> None:
        assert _normalize_path("/api/agents/sessions/a1b2c3d4e5f6a7b8c9") == "/api/agents/sessions/{id}"

    def test_hex_id_collapsed(self) -> None:
        assert _normalize_path("/api/projects/abc123def456789a/members") == "/api/projects/{id}/members"

    def test_short_segment_preserved(self) -> None:
        assert _normalize_path("/api/slos/status") == "/api/slos/status"

    def test_root_path(self) -> None:
        assert _normalize_path("/") == "/"

    def test_metrics_path(self) -> None:
        assert _normalize_path("/metrics") == "/metrics"


# ---------------------------------------------------------------------------
# /metrics endpoint
# ---------------------------------------------------------------------------

class TestMetricsEndpoint:
    @pytest.fixture
    async def client(self, tmp_path):
        import yaml
        from langsight.api.main import create_app
        from langsight.config import load_config

        cfg = tmp_path / ".langsight.yaml"
        cfg.write_text(yaml.dump({"servers": []}))

        app = create_app(config_path=cfg)
        storage = MagicMock()
        storage.close = AsyncMock()
        storage.list_api_keys = AsyncMock(return_value=[])
        storage.get_health_history = AsyncMock(return_value=[])
        app.state.storage = storage
        app.state.config = load_config(cfg)
        app.state.api_keys = []

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c

    async def test_metrics_returns_200(self, client: AsyncClient) -> None:
        r = await client.get("/metrics")
        assert r.status_code == 200

    async def test_metrics_content_type(self, client: AsyncClient) -> None:
        r = await client.get("/metrics")
        assert "text/plain" in r.headers["content-type"] or "text/plain" in r.headers.get("content-type", "")

    async def test_metrics_contains_http_counter(self, client: AsyncClient) -> None:
        # Make a request first to generate metrics
        await client.get("/api/status")
        r = await client.get("/metrics")
        assert "langsight_http_requests_total" in r.text

    async def test_metrics_contains_duration_histogram(self, client: AsyncClient) -> None:
        await client.get("/api/status")
        r = await client.get("/metrics")
        assert "langsight_http_request_duration_seconds" in r.text

    async def test_metrics_no_auth_required(self, client: AsyncClient) -> None:
        """Metrics endpoint should be accessible without API key."""
        r = await client.get("/metrics")
        assert r.status_code == 200  # Not 401 or 403
