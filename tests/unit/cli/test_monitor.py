from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml
from click.testing import CliRunner

from langsight.alerts.engine import Alert, AlertSeverity, AlertType
from langsight.cli.main import cli
from langsight.cli.monitor import _deliver_alerts
from langsight.config import AlertConfig, LangSightConfig, Settings
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
    s.get_health_history = AsyncMock(return_value=[])
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
        cfg.write_text(yaml.dump({"servers": [], "auth_disabled": True}))
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


def _make_alert() -> Alert:
    return Alert(
        server_name="pg",
        alert_type=AlertType.SERVER_DOWN,
        severity=AlertSeverity.CRITICAL,
        title="MCP server 'pg' is DOWN",
        message="Server 'pg' has been unreachable for 2 consecutive checks.",
    )


def _config_with_slack(url: str | None) -> LangSightConfig:
    return LangSightConfig(
        servers=[],
        alerts=AlertConfig(slack_webhook=url),
    )


class TestDeliverAlerts:
    """Unit tests for _deliver_alerts webhook priority: DB > YAML > env var."""

    @pytest.mark.asyncio
    async def test_db_webhook_takes_priority_over_yaml(self) -> None:
        storage = MagicMock()
        storage.get_alert_config = AsyncMock(return_value={"slack_webhook": "https://hooks.slack.com/db"})
        config = _config_with_slack("https://hooks.slack.com/yaml")
        settings = Settings(slack_webhook=None)

        with patch("langsight.cli.monitor.slack_module.send_alerts", new_callable=AsyncMock, return_value=1) as mock_send:
            await _deliver_alerts([_make_alert()], config, settings, storage)
            mock_send.assert_awaited_once()
            assert mock_send.call_args[0][0] == "https://hooks.slack.com/db"

    @pytest.mark.asyncio
    async def test_falls_back_to_yaml_when_db_empty(self) -> None:
        storage = MagicMock()
        storage.get_alert_config = AsyncMock(return_value={"slack_webhook": None})
        config = _config_with_slack("https://hooks.slack.com/yaml")
        settings = Settings(slack_webhook=None)

        with patch("langsight.cli.monitor.slack_module.send_alerts", new_callable=AsyncMock, return_value=1) as mock_send:
            await _deliver_alerts([_make_alert()], config, settings, storage)
            mock_send.assert_awaited_once()
            assert mock_send.call_args[0][0] == "https://hooks.slack.com/yaml"

    @pytest.mark.asyncio
    async def test_falls_back_to_env_when_db_and_yaml_empty(self) -> None:
        storage = MagicMock()
        storage.get_alert_config = AsyncMock(return_value=None)
        config = _config_with_slack(None)
        settings = Settings(slack_webhook="https://hooks.slack.com/env")

        with patch("langsight.cli.monitor.slack_module.send_alerts", new_callable=AsyncMock, return_value=1) as mock_send:
            await _deliver_alerts([_make_alert()], config, settings, storage)
            mock_send.assert_awaited_once()
            assert mock_send.call_args[0][0] == "https://hooks.slack.com/env"

    @pytest.mark.asyncio
    async def test_no_slack_sent_when_no_webhook_anywhere(self) -> None:
        storage = MagicMock()
        storage.get_alert_config = AsyncMock(return_value=None)
        config = _config_with_slack(None)
        settings = Settings(slack_webhook=None)

        with patch("langsight.cli.monitor.slack_module.send_alerts", new_callable=AsyncMock) as mock_send:
            await _deliver_alerts([_make_alert()], config, settings, storage)
            mock_send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_db_failure_fails_open_uses_yaml(self) -> None:
        """If DB raises, fall through to YAML without blocking alert delivery."""
        storage = MagicMock()
        storage.get_alert_config = AsyncMock(side_effect=RuntimeError("db down"))
        config = _config_with_slack("https://hooks.slack.com/yaml")
        settings = Settings(slack_webhook=None)

        with patch("langsight.cli.monitor.slack_module.send_alerts", new_callable=AsyncMock, return_value=1) as mock_send:
            await _deliver_alerts([_make_alert()], config, settings, storage)
            mock_send.assert_awaited_once()
            assert mock_send.call_args[0][0] == "https://hooks.slack.com/yaml"

    @pytest.mark.asyncio
    async def test_no_storage_uses_yaml(self) -> None:
        config = _config_with_slack("https://hooks.slack.com/yaml")
        settings = Settings(slack_webhook=None)

        with patch("langsight.cli.monitor.slack_module.send_alerts", new_callable=AsyncMock, return_value=1) as mock_send:
            await _deliver_alerts([_make_alert()], config, settings, storage=None)
            mock_send.assert_awaited_once()
            assert mock_send.call_args[0][0] == "https://hooks.slack.com/yaml"
