"""
Regression tests — full pipeline without real MCP servers.

Exercises the complete stack:
  config → HealthChecker → SchemaTracker → PostgresBackend

Transport (ping) is mocked so no MCP process is needed, but every other
layer is real: real Postgres DB, real SchemaTracker logic, real HealthChecker
state machine. If any layer breaks the chain these tests catch it.

Requires: docker compose up -d

Run with:
    uv run pytest tests/regression/ -m integration -v
"""
from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import yaml

from langsight.config import load_config
from langsight.health.checker import HealthChecker
from langsight.models import ServerStatus, ToolInfo

pytestmark = [pytest.mark.regression, pytest.mark.integration]

TOOLS_V1 = [
    ToolInfo(name="query", description="Execute SQL"),
    ToolInfo(name="list_tables", description="List tables"),
]
TOOLS_V2 = [
    ToolInfo(name="query", description="Execute SQL"),
    ToolInfo(name="list_tables", description="List tables"),
    ToolInfo(name="new_tool", description="A new tool added in v2"),  # schema change
]


@pytest.fixture
async def pg(require_postgres, postgres_dsn):
    """Real PostgresBackend — shared across tests in this module."""
    from langsight.storage.postgres import PostgresBackend
    backend = await PostgresBackend.open(postgres_dsn)
    yield backend
    await backend.close()


@pytest.fixture
def server_name() -> str:
    """Unique server name per test — prevents cross-test interference in shared DB."""
    return f"test-server-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def config_file(tmp_path: Path, server_name: str) -> Path:
    cfg = tmp_path / ".langsight.yaml"
    cfg.write_text(yaml.dump({
        "servers": [
            {"name": server_name, "transport": "stdio", "command": "python server.py"},
        ]
    }))
    return cfg


# ---------------------------------------------------------------------------
# First run — no history, baseline stored
# ---------------------------------------------------------------------------

class TestHealthPipelineBaseline:
    async def test_first_run_returns_up(self, pg, config_file: Path) -> None:
        config = load_config(config_file)
        with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
            mock_ping.return_value = (42.0, TOOLS_V1)
            results = await HealthChecker(storage=pg).check_many(config.servers)

        assert len(results) == 1
        assert results[0].status == ServerStatus.UP
        assert results[0].tools_count == 2
        assert results[0].schema_hash is not None

    async def test_baseline_persisted(self, pg, config_file: Path) -> None:
        config = load_config(config_file)
        with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
            mock_ping.return_value = (42.0, TOOLS_V1)
            await HealthChecker(storage=pg).check_many(config.servers)

        server = config.servers[0]
        stored_hash = await pg.get_latest_schema_hash(server.name)
        assert stored_hash is not None
        assert len(stored_hash) == 16


# ---------------------------------------------------------------------------
# Second run — same schema, no drift
# ---------------------------------------------------------------------------

class TestHealthPipelineNoDrift:
    async def test_second_run_same_schema_returns_up(self, pg, config_file: Path) -> None:
        config = load_config(config_file)

        with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
            mock_ping.return_value = (42.0, TOOLS_V1)
            await HealthChecker(storage=pg).check_many(config.servers)

        with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
            mock_ping.return_value = (99.0, TOOLS_V1)
            results = await HealthChecker(storage=pg).check_many(config.servers)

        assert results[0].status == ServerStatus.UP
        assert results[0].error is None

    async def test_history_grows_across_runs(self, pg, config_file: Path) -> None:
        config = load_config(config_file)
        server = config.servers[0]

        for _ in range(3):
            with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
                mock_ping.return_value = (10.0, TOOLS_V1)
                await HealthChecker(storage=pg).check_many(config.servers)

        history = await pg.get_health_history(server.name, limit=10)
        assert len(history) == 3
        assert all(r.status == ServerStatus.UP for r in history)


# ---------------------------------------------------------------------------
# Schema drift detected
# ---------------------------------------------------------------------------

class TestHealthPipelineDriftDetected:
    async def test_drift_sets_degraded_status(self, pg, config_file: Path) -> None:
        config = load_config(config_file)

        with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
            mock_ping.return_value = (42.0, TOOLS_V1)
            await HealthChecker(storage=pg).check_many(config.servers)

        with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
            mock_ping.return_value = (42.0, TOOLS_V2)
            results = await HealthChecker(storage=pg).check_many(config.servers)

        assert results[0].status == ServerStatus.DEGRADED
        assert results[0].error is not None
        assert "schema drift" in results[0].error

    async def test_new_snapshot_stored_after_drift(self, pg, config_file: Path) -> None:
        config = load_config(config_file)

        with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
            mock_ping.return_value = (42.0, TOOLS_V1)
            await HealthChecker(storage=pg).check_many(config.servers)

        with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
            mock_ping.return_value = (42.0, TOOLS_V2)
            await HealthChecker(storage=pg).check_many(config.servers)

        # Third run — V2 is now the baseline, no drift
        with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
            mock_ping.return_value = (42.0, TOOLS_V2)
            r3 = await HealthChecker(storage=pg).check_many(config.servers)

        assert r3[0].status == ServerStatus.UP
        assert r3[0].error is None

    async def test_degraded_result_in_history(self, pg, config_file: Path) -> None:
        config = load_config(config_file)
        server = config.servers[0]

        with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
            mock_ping.return_value = (42.0, TOOLS_V1)
            await HealthChecker(storage=pg).check_many(config.servers)

        with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
            mock_ping.return_value = (42.0, TOOLS_V2)
            await HealthChecker(storage=pg).check_many(config.servers)

        history = await pg.get_health_history(server.name, limit=10)
        statuses = [r.status for r in history]
        assert ServerStatus.DEGRADED in statuses


# ---------------------------------------------------------------------------
# Server DOWN
# ---------------------------------------------------------------------------

class TestHealthPipelineDownServer:
    async def test_down_result_persisted(self, pg, config_file: Path) -> None:
        from langsight.exceptions import MCPTimeoutError

        config = load_config(config_file)
        server = config.servers[0]

        with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
            mock_ping.side_effect = MCPTimeoutError("timeout")
            results = await HealthChecker(storage=pg).check_many(config.servers)

        history = await pg.get_health_history(server.name)
        assert results[0].status == ServerStatus.DOWN
        assert len(history) >= 1
        assert history[0].status == ServerStatus.DOWN

    async def test_recovery_after_down(self, pg, config_file: Path) -> None:
        from langsight.exceptions import MCPTimeoutError

        config = load_config(config_file)

        with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
            mock_ping.side_effect = MCPTimeoutError("timeout")
            await HealthChecker(storage=pg).check_many(config.servers)

        with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
            mock_ping.return_value = (42.0, TOOLS_V1)
            results = await HealthChecker(storage=pg).check_many(config.servers)

        assert results[0].status == ServerStatus.UP
