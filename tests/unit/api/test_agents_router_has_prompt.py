"""Unit tests for the has_prompt field in GET /api/agents/sessions responses.

Follows the exact pattern from tests/unit/api/test_agents_router.py:
- ASGITransport + AsyncClient
- mock_storage injected via app.state.storage
- No real Postgres or ClickHouse
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml
from httpx import ASGITransport, AsyncClient

from langsight.api.main import create_app
from langsight.config import load_config


# ---------------------------------------------------------------------------
# Fixtures (mirrors test_agents_router.py)
# ---------------------------------------------------------------------------


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    cfg = tmp_path / ".langsight.yaml"
    cfg.write_text(yaml.dump({"servers": [], "auth_disabled": True}))
    return cfg


@pytest.fixture
async def client(config_file: Path):
    mock_storage = MagicMock()
    mock_storage.get_health_history = AsyncMock(return_value=[])
    mock_storage.list_model_pricing = AsyncMock(return_value=[])
    mock_storage.close = AsyncMock()

    app = create_app(config_path=config_file)
    app.state.storage = mock_storage
    app.state.config = load_config(config_file)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, mock_storage


def _session_row(**overrides) -> dict:
    """Return a minimal storage row dict for one agent session."""
    base = {
        "session_id": "sess-test-001",
        "agent_name": "support-agent",
        "first_call_at": "2026-04-01T10:00:00",
        "last_call_at": "2026-04-01T10:00:05",
        "tool_calls": 3,
        "failed_calls": 0,
        "total_latency_ms": 420.0,
        "servers_used": ["jira-mcp"],
        "duration_ms": 5000.0,
        "agents_used": ["support-agent"],
        "health_tag": None,
        "total_input_tokens": None,
        "total_output_tokens": None,
        "model_id": None,
        "has_prompt": False,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# TestHasPromptInSessionResponse
# ---------------------------------------------------------------------------


class TestHasPromptInSessionResponse:
    """API response includes has_prompt, populated from the storage row."""

    @pytest.mark.asyncio
    async def test_has_prompt_true_returned(self, client) -> None:
        """Storage row with has_prompt=True → API response has "has_prompt": true."""
        c, mock_storage = client
        mock_storage.get_agent_sessions = AsyncMock(
            return_value=[_session_row(has_prompt=True)]
        )
        response = await c.get("/api/agents/sessions")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["has_prompt"] is True

    @pytest.mark.asyncio
    async def test_has_prompt_false_returned(self, client) -> None:
        """Storage row with has_prompt=False → API response has "has_prompt": false."""
        c, mock_storage = client
        mock_storage.get_agent_sessions = AsyncMock(
            return_value=[_session_row(has_prompt=False)]
        )
        response = await c.get("/api/agents/sessions")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["has_prompt"] is False

    @pytest.mark.asyncio
    async def test_has_prompt_defaults_false_when_missing_from_storage(
        self, client
    ) -> None:
        """Storage row without has_prompt key → API response has "has_prompt": false.

        Older ClickHouse schemas (before the has_prompt column was added) produce
        rows that simply omit the key. The router uses r.get("has_prompt", False)
        which must default to False rather than raising KeyError.
        """
        c, mock_storage = client
        row = _session_row()
        del row["has_prompt"]  # simulate pre-migration schema row
        mock_storage.get_agent_sessions = AsyncMock(return_value=[row])
        response = await c.get("/api/agents/sessions")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["has_prompt"] is False

    @pytest.mark.asyncio
    async def test_sessions_with_and_without_prompt_in_same_response(
        self, client
    ) -> None:
        """Mixed sessions — one with has_prompt=True, one without — both serialised correctly."""
        c, mock_storage = client
        mock_storage.get_agent_sessions = AsyncMock(
            return_value=[
                _session_row(session_id="sess-with-prompt", has_prompt=True),
                _session_row(session_id="sess-no-prompt", has_prompt=False),
            ]
        )
        response = await c.get("/api/agents/sessions")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

        by_id = {s["session_id"]: s for s in data}
        assert by_id["sess-with-prompt"]["has_prompt"] is True
        assert by_id["sess-no-prompt"]["has_prompt"] is False
