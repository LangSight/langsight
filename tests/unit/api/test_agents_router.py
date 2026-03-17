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
    mock_storage = MagicMock()
    mock_storage.get_health_history = AsyncMock(return_value=[])
    mock_storage.close = AsyncMock()

    app = create_app(config_path=config_file)
    app.state.storage = mock_storage
    app.state.config = load_config(config_file)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, mock_storage


class TestListSessions:
    async def test_returns_empty_when_no_clickhouse(self, client) -> None:
        c, mock_storage = client
        # Storage without get_agent_sessions (SQLite mode)
        del mock_storage.get_agent_sessions
        response = await c.get("/api/agents/sessions")
        assert response.status_code == 200
        assert response.json() == []

    async def test_returns_sessions_from_storage(self, client) -> None:
        c, mock_storage = client
        mock_storage.get_agent_sessions = AsyncMock(return_value=[
            {
                "session_id": "sess-abc123",
                "agent_name": "support-agent",
                "first_call_at": "2026-03-17T12:00:00",
                "last_call_at": "2026-03-17T12:00:04",
                "tool_calls": 5,
                "failed_calls": 1,
                "total_latency_ms": 680.0,
                "servers_used": ["jira-mcp", "slack-mcp"],
                "duration_ms": 4000.0,
            }
        ])
        response = await c.get("/api/agents/sessions")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["session_id"] == "sess-abc123"
        assert data[0]["agent_name"] == "support-agent"
        assert data[0]["tool_calls"] == 5
        assert data[0]["failed_calls"] == 1

    async def test_passes_hours_param(self, client) -> None:
        c, mock_storage = client
        mock_storage.get_agent_sessions = AsyncMock(return_value=[])
        await c.get("/api/agents/sessions?hours=48")
        mock_storage.get_agent_sessions.assert_called_once()
        assert mock_storage.get_agent_sessions.call_args[1]["hours"] == 48


class TestGetSession:
    async def test_returns_503_without_clickhouse(self, client) -> None:
        c, mock_storage = client
        del mock_storage.get_session_trace
        response = await c.get("/api/agents/sessions/sess-abc123")
        assert response.status_code == 503

    async def test_returns_404_when_session_not_found(self, client) -> None:
        c, mock_storage = client
        mock_storage.get_session_trace = AsyncMock(return_value=[])
        response = await c.get("/api/agents/sessions/nonexistent")
        assert response.status_code == 404

    async def test_returns_session_trace(self, client) -> None:
        c, mock_storage = client
        mock_storage.get_session_trace = AsyncMock(return_value=[
            {
                "span_id": "span-1", "parent_span_id": None,
                "span_type": "tool_call", "server_name": "jira-mcp",
                "tool_name": "get_issue", "agent_name": "orchestrator",
                "started_at": "2026-03-17T12:00:00",
                "ended_at": "2026-03-17T12:00:00.089",
                "latency_ms": 89.0, "status": "success",
                "error": None, "trace_id": "trace-123",
            },
            {
                "span_id": "span-2", "parent_span_id": None,
                "span_type": "handoff", "server_name": "orchestrator",
                "tool_name": "→ billing-agent", "agent_name": "orchestrator",
                "started_at": "2026-03-17T12:00:00.090",
                "ended_at": "2026-03-17T12:00:00.090",
                "latency_ms": 0.0, "status": "success",
                "error": None, "trace_id": "trace-123",
            },
            {
                "span_id": "span-3", "parent_span_id": "span-2",
                "span_type": "tool_call", "server_name": "crm-mcp",
                "tool_name": "update_customer", "agent_name": "billing-agent",
                "started_at": "2026-03-17T12:00:00.100",
                "ended_at": "2026-03-17T12:00:00.220",
                "latency_ms": 120.0, "status": "success",
                "error": None, "trace_id": "trace-123",
            },
        ])
        response = await c.get("/api/agents/sessions/sess-abc123")
        assert response.status_code == 200
        data = response.json()

        assert data["session_id"] == "sess-abc123"
        assert data["total_spans"] == 3
        assert data["tool_calls"] == 2      # only tool_call type
        assert data["failed_calls"] == 0

        # Tree: span-3 is child of span-2 (handoff)
        roots = data["root_spans"]
        root_ids = [r["span_id"] for r in roots]
        assert "span-1" in root_ids
        assert "span-2" in root_ids
        assert "span-3" not in root_ids     # it's a child

        handoff = next(r for r in roots if r["span_id"] == "span-2")
        assert len(handoff["children"]) == 1
        assert handoff["children"][0]["span_id"] == "span-3"
