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

    async def test_metrics_returns_503_when_token_not_set(self, client: AsyncClient) -> None:
        """Without LANGSIGHT_METRICS_TOKEN the endpoint returns 503, not open metrics."""
        r = await client.get("/metrics")
        assert r.status_code == 503

    async def test_metrics_returns_401_with_wrong_token(self, client: AsyncClient, monkeypatch) -> None:
        monkeypatch.setattr("langsight.api.metrics._METRICS_TOKEN", "correct-token")
        r = await client.get("/metrics", headers={"Authorization": "Bearer wrong-token"})
        assert r.status_code == 401

    async def test_metrics_returns_401_with_no_token_header(self, client: AsyncClient, monkeypatch) -> None:
        monkeypatch.setattr("langsight.api.metrics._METRICS_TOKEN", "correct-token")
        r = await client.get("/metrics")
        assert r.status_code == 401

    async def test_metrics_content_type_with_valid_token(self, client: AsyncClient, monkeypatch) -> None:
        monkeypatch.setattr("langsight.api.metrics._METRICS_TOKEN", "valid-token")
        r = await client.get("/metrics", headers={"Authorization": "Bearer valid-token"})
        assert r.status_code == 200
        assert "text/plain" in r.headers.get("content-type", "")

    async def test_metrics_contains_http_counter_with_valid_token(self, client: AsyncClient, monkeypatch) -> None:
        monkeypatch.setattr("langsight.api.metrics._METRICS_TOKEN", "valid-token")
        await client.get("/api/status")
        r = await client.get("/metrics", headers={"Authorization": "Bearer valid-token"})
        assert r.status_code == 200
        assert "langsight_http_requests_total" in r.text

    async def test_metrics_contains_duration_histogram_with_valid_token(self, client: AsyncClient, monkeypatch) -> None:
        monkeypatch.setattr("langsight.api.metrics._METRICS_TOKEN", "valid-token")
        await client.get("/api/status")
        r = await client.get("/metrics", headers={"Authorization": "Bearer valid-token"})
        assert r.status_code == 200
        assert "langsight_http_request_duration_seconds" in r.text

    async def test_metrics_query_string_token_rejected(self, client: AsyncClient, monkeypatch) -> None:
        """Query-string token auth must not work — Bearer header only."""
        monkeypatch.setattr("langsight.api.metrics._METRICS_TOKEN", "valid-token")
        r = await client.get("/metrics?token=valid-token")
        assert r.status_code == 401
