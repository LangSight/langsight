"""
Regression tests — monitor pipeline with alert engine.

Exercises: config → HealthChecker → AlertEngine → alert firing logic
Storage is real Postgres; transport (ping) is mocked.

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

from langsight.alerts.engine import AlertEngine, AlertType
from langsight.config import load_config
from langsight.exceptions import MCPTimeoutError
from langsight.health.checker import HealthChecker
from langsight.models import ToolInfo

pytestmark = [pytest.mark.regression, pytest.mark.integration]

TOOLS = [ToolInfo(name="query", description="Execute SQL")]


@pytest.fixture(scope="module")
async def pg(require_postgres, postgres_dsn):
    from langsight.storage.postgres import PostgresBackend
    backend = await PostgresBackend.open(postgres_dsn)
    yield backend
    await backend.close()


@pytest.fixture
def server_name() -> str:
    return f"monitor-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def config_file(tmp_path: Path, server_name: str) -> Path:
    cfg = tmp_path / ".langsight.yaml"
    cfg.write_text(yaml.dump({
        "servers": [{"name": server_name, "transport": "stdio", "command": "python server.py"}],
        "alerts": {"consecutive_failures": 2},
    }))
    return cfg


class TestMonitorNormalOperation:
    async def test_no_alerts_on_healthy_servers(self, pg, config_file: Path) -> None:
        config = load_config(config_file)
        engine = AlertEngine(consecutive_failures_threshold=2)
        checker = HealthChecker(storage=pg)

        with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
            mock_ping.return_value = (42.0, TOOLS)
            for _ in range(3):
                results = await checker.check_many(config.servers)
                assert engine.evaluate_many(results) == []


class TestMonitorDownDetection:
    async def test_no_alert_on_single_failure(self, pg, config_file: Path) -> None:
        config = load_config(config_file)
        engine = AlertEngine(consecutive_failures_threshold=2)

        with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
            mock_ping.side_effect = MCPTimeoutError("timeout")
            results = await HealthChecker(storage=pg).check_many(config.servers)
            alerts = engine.evaluate_many(results)

        assert alerts == []

    async def test_alert_fires_after_threshold(self, pg, config_file: Path) -> None:
        config = load_config(config_file)
        engine = AlertEngine(consecutive_failures_threshold=2)
        all_alerts = []
        checker = HealthChecker(storage=pg)

        with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
            mock_ping.side_effect = MCPTimeoutError("timeout")
            for _ in range(2):
                results = await checker.check_many(config.servers)
                all_alerts.extend(engine.evaluate_many(results))

        assert any(a.alert_type == AlertType.SERVER_DOWN for a in all_alerts)

    async def test_no_duplicate_down_alerts(self, pg, config_file: Path) -> None:
        config = load_config(config_file)
        engine = AlertEngine(consecutive_failures_threshold=2)
        all_alerts = []
        checker = HealthChecker(storage=pg)

        with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
            mock_ping.side_effect = MCPTimeoutError("timeout")
            for _ in range(5):
                results = await checker.check_many(config.servers)
                all_alerts.extend(engine.evaluate_many(results))

        down_alerts = [a for a in all_alerts if a.alert_type == AlertType.SERVER_DOWN]
        assert len(down_alerts) == 1


class TestMonitorRecovery:
    async def test_recovery_alert_after_down(self, pg, config_file: Path) -> None:
        config = load_config(config_file)
        engine = AlertEngine(consecutive_failures_threshold=2)
        checker = HealthChecker(storage=pg)
        all_alerts = []

        with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
            mock_ping.side_effect = MCPTimeoutError("timeout")
            for _ in range(2):
                results = await checker.check_many(config.servers)
                all_alerts.extend(engine.evaluate_many(results))

        with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
            mock_ping.return_value = (42.0, TOOLS)
            results = await checker.check_many(config.servers)
            all_alerts.extend(engine.evaluate_many(results))

        alert_types = [a.alert_type for a in all_alerts]
        assert AlertType.SERVER_DOWN in alert_types
        assert AlertType.SERVER_RECOVERED in alert_types

    async def test_failure_counter_resets_after_recovery(self, pg, config_file: Path) -> None:
        config = load_config(config_file)
        engine = AlertEngine(consecutive_failures_threshold=2)
        checker = HealthChecker(storage=pg)

        with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
            mock_ping.side_effect = MCPTimeoutError("timeout")
            results = await checker.check_many(config.servers)
            engine.evaluate_many(results)

        with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
            mock_ping.return_value = (42.0, TOOLS)
            results = await checker.check_many(config.servers)
            engine.evaluate_many(results)

        with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
            mock_ping.side_effect = MCPTimeoutError("timeout")
            results = await checker.check_many(config.servers)
            alerts = engine.evaluate_many(results)

        assert not any(a.alert_type == AlertType.SERVER_DOWN for a in alerts)
