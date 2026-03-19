"""
Regression tests — monitor pipeline with alert engine.

Exercises: config → HealthChecker → AlertEngine → alert firing logic
Storage is real SQLite; transport (ping) is mocked.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import yaml

from langsight.alerts.engine import AlertEngine, AlertType
from langsight.config import load_config
from langsight.exceptions import MCPTimeoutError
from langsight.health.checker import HealthChecker
from langsight.models import ToolInfo
from langsight.storage.sqlite import SQLiteBackend

pytestmark = pytest.mark.regression

TOOLS = [ToolInfo(name="query", description="Execute SQL")]


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    cfg = tmp_path / ".langsight.yaml"
    cfg.write_text(yaml.dump({
        "servers": [{"name": "pg", "transport": "stdio", "command": "python server.py"}],
        "alerts": {"consecutive_failures": 2},
    }))
    return cfg


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


class TestMonitorNormalOperation:
    async def test_no_alerts_on_healthy_servers(
        self, config_file: Path, db_path: Path
    ) -> None:
        config = load_config(config_file)
        engine = AlertEngine(consecutive_failures_threshold=2)

        async with await SQLiteBackend.open(db_path) as storage:
            with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
                mock_ping.return_value = (42.0, TOOLS)
                checker = HealthChecker(storage=storage)
                for _ in range(3):
                    results = await checker.check_many(config.servers)
                    alerts = engine.evaluate_many(results)
                    assert alerts == []


class TestMonitorDownDetection:
    async def test_no_alert_on_single_failure(
        self, config_file: Path, db_path: Path
    ) -> None:
        config = load_config(config_file)
        engine = AlertEngine(consecutive_failures_threshold=2)

        async with await SQLiteBackend.open(db_path) as storage:
            with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
                mock_ping.side_effect = MCPTimeoutError("timeout")
                checker = HealthChecker(storage=storage)
                results = await checker.check_many(config.servers)
                alerts = engine.evaluate_many(results)

        assert alerts == []

    async def test_alert_fires_after_threshold(
        self, config_file: Path, db_path: Path
    ) -> None:
        config = load_config(config_file)
        engine = AlertEngine(consecutive_failures_threshold=2)
        all_alerts = []

        async with await SQLiteBackend.open(db_path) as storage:
            with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
                mock_ping.side_effect = MCPTimeoutError("timeout")
                checker = HealthChecker(storage=storage)
                for _ in range(2):
                    results = await checker.check_many(config.servers)
                    all_alerts.extend(engine.evaluate_many(results))

        assert any(a.alert_type == AlertType.SERVER_DOWN for a in all_alerts)

    async def test_no_duplicate_down_alerts(
        self, config_file: Path, db_path: Path
    ) -> None:
        config = load_config(config_file)
        engine = AlertEngine(consecutive_failures_threshold=2)
        all_alerts = []

        async with await SQLiteBackend.open(db_path) as storage:
            with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
                mock_ping.side_effect = MCPTimeoutError("timeout")
                checker = HealthChecker(storage=storage)
                for _ in range(5):  # 5 cycles of failures
                    results = await checker.check_many(config.servers)
                    all_alerts.extend(engine.evaluate_many(results))

        down_alerts = [a for a in all_alerts if a.alert_type == AlertType.SERVER_DOWN]
        assert len(down_alerts) == 1  # only one, no duplicates


class TestMonitorRecovery:
    async def test_recovery_alert_after_down(
        self, config_file: Path, db_path: Path
    ) -> None:
        config = load_config(config_file)
        engine = AlertEngine(consecutive_failures_threshold=2)
        all_alerts = []

        async with await SQLiteBackend.open(db_path) as storage:
            checker = HealthChecker(storage=storage)

            # Two failures → DOWN alert
            with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
                mock_ping.side_effect = MCPTimeoutError("timeout")
                for _ in range(2):
                    results = await checker.check_many(config.servers)
                    all_alerts.extend(engine.evaluate_many(results))

            # Recovery
            with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
                mock_ping.return_value = (42.0, TOOLS)
                results = await checker.check_many(config.servers)
                all_alerts.extend(engine.evaluate_many(results))

        alert_types = [a.alert_type for a in all_alerts]
        assert AlertType.SERVER_DOWN in alert_types
        assert AlertType.SERVER_RECOVERED in alert_types

    async def test_failure_counter_resets_after_recovery(
        self, config_file: Path, db_path: Path
    ) -> None:
        config = load_config(config_file)
        engine = AlertEngine(consecutive_failures_threshold=2)

        async with await SQLiteBackend.open(db_path) as storage:
            checker = HealthChecker(storage=storage)

            # One failure (below threshold)
            with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
                mock_ping.side_effect = MCPTimeoutError("timeout")
                results = await checker.check_many(config.servers)
                engine.evaluate_many(results)

            # Recovery
            with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
                mock_ping.return_value = (42.0, TOOLS)
                results = await checker.check_many(config.servers)
                engine.evaluate_many(results)

            # One more failure — should not trigger alert (counter reset)
            with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
                mock_ping.side_effect = MCPTimeoutError("timeout")
                results = await checker.check_many(config.servers)
                alerts = engine.evaluate_many(results)

        assert not any(a.alert_type == AlertType.SERVER_DOWN for a in alerts)
