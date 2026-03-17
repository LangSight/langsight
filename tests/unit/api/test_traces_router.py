from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml
from httpx import ASGITransport, AsyncClient

from langsight.api.main import create_app
from langsight.config import load_config
from langsight.sdk.models import ToolCallSpan, ToolCallStatus


def _span_payload(
    server: str = "pg",
    tool: str = "query",
    status: str = "success",
) -> dict:
    now = datetime.now(UTC).isoformat()
    return {
        "server_name": server,
        "tool_name": tool,
        "started_at": now,
        "ended_at": now,
        "latency_ms": 42.0,
        "status": status,
    }


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    cfg = tmp_path / ".langsight.yaml"
    cfg.write_text(yaml.dump({"servers": []}))
    return cfg


@pytest.fixture
async def client(config_file: Path):
    app = create_app(config_path=config_file)
    mock_storage = MagicMock()
    mock_storage.save_tool_call_spans = AsyncMock()
    app.state.storage = mock_storage
    app.state.config = load_config(config_file)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


class TestTracesEndpoint:
    async def test_returns_202_accepted(self, client) -> None:
        response = await client.post(
            "/api/traces/spans",
            json=[_span_payload()],
        )
        assert response.status_code == 202

    async def test_returns_accepted_count(self, client) -> None:
        spans = [_span_payload(), _span_payload(tool="list_tables")]
        data = (await client.post("/api/traces/spans", json=spans)).json()
        assert data["accepted"] == 2

    async def test_accepts_empty_list(self, client) -> None:
        response = await client.post("/api/traces/spans", json=[])
        assert response.status_code == 202
        assert response.json()["accepted"] == 0

    async def test_accepts_error_span(self, client) -> None:
        payload = _span_payload(status="error")
        payload["error"] = "connection refused"
        response = await client.post("/api/traces/spans", json=[payload])
        assert response.status_code == 202

    async def test_accepts_timeout_span(self, client) -> None:
        payload = _span_payload(status="timeout")
        response = await client.post("/api/traces/spans", json=[payload])
        assert response.status_code == 202

    async def test_rejects_invalid_status(self, client) -> None:
        payload = _span_payload(status="unknown_status")
        response = await client.post("/api/traces/spans", json=[payload])
        assert response.status_code == 422

    async def test_accepts_span_with_all_metadata(self, client) -> None:
        payload = _span_payload()
        payload.update({
            "trace_id": "trace-123",
            "agent_name": "support-agent",
            "session_id": "sess-abc",
        })
        response = await client.post("/api/traces/spans", json=[payload])
        assert response.status_code == 202
