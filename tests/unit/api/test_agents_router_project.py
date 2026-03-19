"""
Unit tests for Phase 10 multi-tenancy: project_id wiring in the agents router.

Verifies that:
- GET /api/agents/sessions?project_id=p1 passes project_id to storage.get_agent_sessions
- GET /api/agents/sessions/{id}?project_id=p1 passes project_id to storage.get_session_trace
- project_id=None (omitted) is passed through correctly for both endpoints
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
    mock_storage.close = AsyncMock()

    app.state.storage = mock_storage
    app.state.config = load_config(config_file)
    # No env keys — auth disabled in tests
    app.state.api_keys = []

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, mock_storage


# ---------------------------------------------------------------------------
# GET /api/agents/sessions — project_id wiring
# ---------------------------------------------------------------------------

class TestListSessionsProjectIdWiring:
    async def test_project_id_param_passed_to_storage(self, client) -> None:
        """?project_id=p1 must be forwarded to storage.get_agent_sessions."""
        c, mock_storage = client
        mock_storage.get_agent_sessions = AsyncMock(return_value=[])

        response = await c.get("/api/agents/sessions?project_id=p1")

        assert response.status_code == 200
        mock_storage.get_agent_sessions.assert_called_once()
        kwargs = mock_storage.get_agent_sessions.call_args[1]
        assert kwargs["project_id"] == "p1"

    async def test_no_project_id_passes_none_to_storage(self, client) -> None:
        """When project_id is omitted, None must be forwarded to storage."""
        c, mock_storage = client
        mock_storage.get_agent_sessions = AsyncMock(return_value=[])

        response = await c.get("/api/agents/sessions")

        assert response.status_code == 200
        mock_storage.get_agent_sessions.assert_called_once()
        kwargs = mock_storage.get_agent_sessions.call_args[1]
        assert kwargs["project_id"] is None

    async def test_hours_and_project_id_both_forwarded(self, client) -> None:
        """Both hours and project_id must be forwarded together."""
        c, mock_storage = client
        mock_storage.get_agent_sessions = AsyncMock(return_value=[])

        response = await c.get("/api/agents/sessions?hours=48&project_id=tenant-2")

        assert response.status_code == 200
        kwargs = mock_storage.get_agent_sessions.call_args[1]
        assert kwargs["hours"] == 48
        assert kwargs["project_id"] == "tenant-2"

    async def test_returns_empty_list_without_clickhouse(self, client) -> None:
        """Without get_agent_sessions capability, returns 200 empty list."""
        c, mock_storage = client
        del mock_storage.get_agent_sessions

        response = await c.get("/api/agents/sessions?project_id=p1")

        assert response.status_code == 200
        assert response.json() == []


# ---------------------------------------------------------------------------
# GET /api/agents/sessions/{session_id} — project_id wiring
# ---------------------------------------------------------------------------

class TestGetSessionProjectIdWiring:
    async def test_project_id_param_passed_to_storage(self, client) -> None:
        """?project_id=p1 must be forwarded to storage.get_session_trace."""
        c, mock_storage = client
        mock_storage.get_session_trace = AsyncMock(return_value=[
            {
                "span_id": "s1", "parent_span_id": None,
                "span_type": "tool_call", "server_name": "pg",
                "tool_name": "query", "agent_name": "agent-1",
                "started_at": "2026-03-17T12:00:00",
                "ended_at": "2026-03-17T12:00:00.100",
                "latency_ms": 100.0, "status": "success",
                "error": None, "trace_id": "t1",
            }
        ])

        response = await c.get("/api/agents/sessions/sess-abc?project_id=p1")

        assert response.status_code == 200
        mock_storage.get_session_trace.assert_called_once()
        call_args = mock_storage.get_session_trace.call_args
        # First positional arg is session_id
        assert call_args[0][0] == "sess-abc"
        # project_id is a keyword argument
        assert call_args[1]["project_id"] == "p1"

    async def test_no_project_id_passes_none_to_storage(self, client) -> None:
        """When project_id is omitted, None must be passed to get_session_trace."""
        c, mock_storage = client
        mock_storage.get_session_trace = AsyncMock(return_value=[
            {
                "span_id": "s1", "parent_span_id": None,
                "span_type": "tool_call", "server_name": "pg",
                "tool_name": "query", "agent_name": "agent-1",
                "started_at": "2026-03-17T12:00:00",
                "ended_at": "2026-03-17T12:00:00.100",
                "latency_ms": 100.0, "status": "success",
                "error": None, "trace_id": "t1",
            }
        ])

        response = await c.get("/api/agents/sessions/sess-abc")

        assert response.status_code == 200
        kwargs = mock_storage.get_session_trace.call_args[1]
        assert kwargs["project_id"] is None

    async def test_returns_404_when_no_spans_for_project(self, client) -> None:
        """Empty span list (no matching session in project) → 404."""
        c, mock_storage = client
        mock_storage.get_session_trace = AsyncMock(return_value=[])

        response = await c.get("/api/agents/sessions/nonexistent?project_id=p1")

        assert response.status_code == 404

    async def test_returns_503_without_clickhouse_regardless_of_project_id(self, client) -> None:
        """Without ClickHouse capability, returns 503 even when project_id is given."""
        c, mock_storage = client
        del mock_storage.get_session_trace

        response = await c.get("/api/agents/sessions/sess-abc?project_id=p1")

        assert response.status_code == 503


# ---------------------------------------------------------------------------
# GET /api/costs/breakdown — project_id wiring (Phase 10 fix verification)
# ---------------------------------------------------------------------------

class TestCostsBreakdownProjectIdWiring:
    async def test_project_id_param_passed_to_storage(self, client) -> None:
        """?project_id=p1 on /api/costs/breakdown must be forwarded to storage."""


        # Need a costs-config-bearing app for this test
        c, mock_storage = client
        mock_storage.get_cost_call_counts = AsyncMock(return_value=[])

        response = await c.get("/api/costs/breakdown?project_id=p1")

        assert response.status_code == 200
        mock_storage.get_cost_call_counts.assert_called_once()
        kwargs = mock_storage.get_cost_call_counts.call_args[1]
        assert kwargs["project_id"] == "p1"

    async def test_no_project_id_passes_none_to_storage(self, client) -> None:
        """When project_id omitted, None must be forwarded to get_cost_call_counts."""
        c, mock_storage = client
        mock_storage.get_cost_call_counts = AsyncMock(return_value=[])

        response = await c.get("/api/costs/breakdown")

        assert response.status_code == 200
        kwargs = mock_storage.get_cost_call_counts.call_args[1]
        assert kwargs["project_id"] is None
