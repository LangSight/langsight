from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml
from click.testing import CliRunner

from langsight.cli.main import cli
from langsight.models import HealthCheckResult, ServerStatus


def _up_result(name: str = "pg") -> HealthCheckResult:
    return HealthCheckResult(
        server_name=name, status=ServerStatus.UP,
        latency_ms=42.0, tools_count=5,
    )


def _down_result(name: str = "pg") -> HealthCheckResult:
    return HealthCheckResult(
        server_name=name, status=ServerStatus.DOWN, error="timeout",
    )


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    cfg = tmp_path / ".langsight.yaml"
    cfg.write_text(yaml.dump({
        "servers": [{"name": "pg", "transport": "stdio", "command": "python s.py"}],
        "alerts": {"consecutive_failures": 2},
    }))
    return cfg


def _mock_storage() -> MagicMock:
    s = MagicMock()
    s.save_health_result = AsyncMock()
    s.get_latest_schema_hash = AsyncMock(return_value=None)
    s.save_schema_snapshot = AsyncMock()
    s.close = AsyncMock()
    s.__aenter__ = AsyncMock(return_value=s)
    s.__aexit__ = AsyncMock(return_value=None)
    return s


class TestMonitorCommand:
    def test_once_flag_runs_single_cycle(self, config_file: Path) -> None:
        runner = CliRunner()
        storage = _mock_storage()
        with patch("langsight.cli.monitor.try_open_storage", new_callable=AsyncMock, return_value=storage):
            with patch("langsight.cli.monitor.HealthChecker") as MockChecker:
                MockChecker.return_value.check_many = AsyncMock(return_value=[_up_result()])
                result = runner.invoke(cli, ["monitor", "--config", str(config_file), "--once"])

        assert result.exit_code == 0
        assert "pg" in result.output

    def test_exits_1_when_no_servers(self, tmp_path: Path) -> None:
        cfg = tmp_path / ".langsight.yaml"
        cfg.write_text(yaml.dump({"servers": []}))
        runner = CliRunner()
        result = runner.invoke(cli, ["monitor", "--config", str(cfg), "--once"])
        assert result.exit_code == 1

    def test_shows_up_status(self, config_file: Path) -> None:
        runner = CliRunner()
        storage = _mock_storage()
        with patch("langsight.cli.monitor.try_open_storage", new_callable=AsyncMock, return_value=storage):
            with patch("langsight.cli.monitor.HealthChecker") as MockChecker:
                MockChecker.return_value.check_many = AsyncMock(return_value=[_up_result()])
                result = runner.invoke(cli, ["monitor", "--config", str(config_file), "--once"])

        assert "up" in result.output

    def test_shows_down_status(self, config_file: Path) -> None:
        runner = CliRunner()
        storage = _mock_storage()
        with patch("langsight.cli.monitor.try_open_storage", new_callable=AsyncMock, return_value=storage):
            with patch("langsight.cli.monitor.HealthChecker") as MockChecker:
                MockChecker.return_value.check_many = AsyncMock(return_value=[_down_result()])
                result = runner.invoke(cli, ["monitor", "--config", str(config_file), "--once"])

        assert "down" in result.output

    def test_custom_interval_accepted(self, config_file: Path) -> None:
        runner = CliRunner()
        storage = _mock_storage()
        with patch("langsight.cli.monitor.try_open_storage", new_callable=AsyncMock, return_value=storage):
            with patch("langsight.cli.monitor.HealthChecker") as MockChecker:
                MockChecker.return_value.check_many = AsyncMock(return_value=[_up_result()])
                result = runner.invoke(
                    cli,
                    ["monitor", "--config", str(config_file), "--once", "--interval", "60"],
                )

        assert result.exit_code == 0
