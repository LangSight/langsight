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
    cfg.write_text(
        yaml.dump(
            {
                "servers": [],
                "storage": {"mode": "clickhouse"},
                "costs": {
                    "rules": [
                        {"server": "pg-*", "tool": "query", "cost_per_call": 0.005},
                        {"server": "s3-*", "tool": "*", "cost_per_call": 0.002},
                    ]
                },
            }
        )
    )
    return cfg


@pytest.fixture
async def client(config_file: Path):
    app = create_app(config_path=config_file)
    mock_storage = MagicMock()
    mock_storage.get_health_history = AsyncMock(return_value=[])
    mock_storage.close = AsyncMock()
    mock_storage.get_cost_call_counts = AsyncMock(return_value=[])
    app.state.storage = mock_storage
    app.state.config = load_config(config_file)
    app.state.config_path = config_file

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, mock_storage


class TestCostsBreakdown:
    async def test_returns_not_supported_without_cost_capability(self, client) -> None:
        c, mock_storage = client
        del mock_storage.get_cost_call_counts

        response = await c.get("/api/costs/breakdown")

        assert response.status_code == 200
        assert response.json() == {
            "storage_mode": "clickhouse",
            "supports_costs": False,
            "hours": 24,
            "total_calls": 0,
            "total_cost_usd": 0.0,
            "by_tool": [],
            "by_agent": [],
            "by_session": [],
        }

    async def test_returns_cost_breakdown_from_storage_rows(self, client) -> None:
        c, mock_storage = client
        mock_storage.get_cost_call_counts = AsyncMock(
            return_value=[
                {
                    "server_name": "pg-main",
                    "tool_name": "query",
                    "agent_name": "support-agent",
                    "session_id": "sess-1",
                    "total_calls": 10,
                },
                {
                    "server_name": "s3-assets",
                    "tool_name": "read_object",
                    "agent_name": "support-agent",
                    "session_id": "sess-1",
                    "total_calls": 4,
                },
                {
                    "server_name": "pg-main",
                    "tool_name": "query",
                    "agent_name": "billing-agent",
                    "session_id": "sess-2",
                    "total_calls": 6,
                },
            ]
        )

        response = await c.get("/api/costs/breakdown?hours=48")

        assert response.status_code == 200
        data = response.json()
        assert data["supports_costs"] is True
        assert data["hours"] == 48
        assert data["total_calls"] == 20
        assert data["total_cost_usd"] == 0.088

        assert len(data["by_tool"]) == 2
        assert data["by_tool"][0] == {
            "server_name": "pg-main",
            "tool_name": "query",
            "total_calls": 16,
            "cost_per_call_usd": 0.005,
            "total_cost_usd": 0.08,
        }

        assert len(data["by_agent"]) == 2
        assert data["by_agent"][0] == {
            "agent_name": "support-agent",
            "total_calls": 14,
            "total_cost_usd": 0.058,
        }

        assert len(data["by_session"]) == 2
        assert data["by_session"][0] == {
            "session_id": "sess-1",
            "agent_name": "support-agent",
            "total_calls": 14,
            "total_cost_usd": 0.058,
        }

    async def test_passes_hours_param_to_storage(self, client) -> None:
        c, mock_storage = client

        await c.get("/api/costs/breakdown?hours=72")

        mock_storage.get_cost_call_counts.assert_called_once_with(hours=72)
