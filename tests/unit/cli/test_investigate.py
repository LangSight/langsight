from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml
from click.testing import CliRunner

from langsight.cli.main import cli
from langsight.cli.investigate import _parse_window, _analyse_with_rules
from langsight.models import HealthCheckResult, ServerStatus


def _result(
    name: str = "pg",
    status: ServerStatus = ServerStatus.UP,
    latency_ms: float = 100.0,
    error: str | None = None,
) -> HealthCheckResult:
    return HealthCheckResult(
        server_name=name,
        status=status,
        latency_ms=latency_ms,
        error=error,
        checked_at=datetime.now(UTC),
    )


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    cfg = tmp_path / ".langsight.yaml"
    cfg.write_text(yaml.dump({
        "servers": [{"name": "pg", "transport": "stdio", "command": "python s.py"}]
    }))
    return cfg


def _mock_storage(history: list | None = None) -> MagicMock:
    s = MagicMock()
    s.get_health_history = AsyncMock(return_value=history or [_result()])
    s.save_health_result = AsyncMock()
    s.get_latest_schema_hash = AsyncMock(return_value=None)
    s.save_schema_snapshot = AsyncMock()
    s.close = AsyncMock()
    s.__aenter__ = AsyncMock(return_value=s)
    s.__aexit__ = AsyncMock(return_value=None)
    return s


class TestParseWindow:
    def test_hours(self) -> None:
        assert _parse_window("2h") == 2.0

    def test_minutes(self) -> None:
        assert _parse_window("30m") == pytest.approx(0.5)

    def test_days(self) -> None:
        assert _parse_window("1d") == 24.0

    def test_bare_number_is_hours(self) -> None:
        assert _parse_window("3") == 3.0


class TestInvestigateCommand:
    def test_exits_1_when_no_servers(self, tmp_path: Path) -> None:
        cfg = tmp_path / ".langsight.yaml"
        cfg.write_text(yaml.dump({"servers": []}))
        runner = CliRunner()
        result = runner.invoke(cli, ["investigate", "--config", str(cfg)])
        assert result.exit_code == 1

    def test_exits_1_for_unknown_server(self, config_file: Path) -> None:
        runner = CliRunner()
        storage = _mock_storage()
        with patch("langsight.cli.investigate.open_storage", new_callable=AsyncMock, return_value=storage):
            result = runner.invoke(cli, ["investigate", "--config", str(config_file), "--server", "nonexistent"])
        assert result.exit_code == 1

    def test_json_flag_outputs_json(self, config_file: Path) -> None:
        import json
        runner = CliRunner()
        storage = _mock_storage([_result()])
        with patch("langsight.cli.investigate.open_storage", new_callable=AsyncMock, return_value=storage):
            result = runner.invoke(cli, ["investigate", "--config", str(config_file), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "pg" in data

    def test_rule_based_fallback_when_no_api_key(self, config_file: Path) -> None:
        runner = CliRunner()
        storage = _mock_storage([_result()])
        env = {"ANTHROPIC_API_KEY": ""}
        with patch("langsight.cli.investigate.open_storage", new_callable=AsyncMock, return_value=storage):
            with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}):
                result = runner.invoke(cli, ["investigate", "--config", str(config_file)])
        assert result.exit_code == 0
        assert "rule-based" in result.output.lower() or "Root Cause" in result.output

    def test_server_filter_works(self, config_file: Path) -> None:
        runner = CliRunner()
        storage = _mock_storage([_result()])
        with patch("langsight.cli.investigate.open_storage", new_callable=AsyncMock, return_value=storage):
            with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}):
                result = runner.invoke(cli, [
                    "investigate", "--config", str(config_file), "--server", "pg"
                ])
        assert result.exit_code == 0


class TestRuleBasedAnalysis:
    def test_healthy_server_shows_healthy(self) -> None:
        from io import StringIO
        from rich.console import Console

        evidence = {
            "pg": {
                "server_name": "pg", "transport": "stdio",
                "window_hours": 1.0, "total_checks": 5,
                "down_count": 0, "degraded_count": 0, "up_count": 5,
                "latest_status": "up", "latest_error": None,
                "schema_drift_events": [], "latency_ms_samples": [100.0],
                "recent_errors": [],
            }
        }
        # Should not raise
        with patch("langsight.cli.investigate.console", Console(file=StringIO())):
            _analyse_with_rules(evidence)

    def test_down_server_shows_root_cause(self) -> None:
        from io import StringIO
        from rich.console import Console

        output = StringIO()
        evidence = {
            "pg": {
                "server_name": "pg", "transport": "stdio",
                "window_hours": 1.0, "total_checks": 5,
                "down_count": 5, "degraded_count": 0, "up_count": 0,
                "latest_status": "down", "latest_error": "timeout after 5s",
                "schema_drift_events": [], "latency_ms_samples": [],
                "recent_errors": [],
            }
        }
        with patch("langsight.cli.investigate.console", Console(file=output)):
            _analyse_with_rules(evidence)

        out = output.getvalue()
        assert "Root Cause" in out or "down" in out.lower()

    def test_no_data_handled_gracefully(self) -> None:
        from io import StringIO
        from rich.console import Console

        evidence = {
            "pg": {
                "server_name": "pg", "transport": "stdio",
                "window_hours": 1.0, "total_checks": 0,
                "down_count": 0, "degraded_count": 0, "up_count": 0,
                "latest_status": "no_data", "latest_error": None,
                "schema_drift_events": [], "latency_ms_samples": [],
                "recent_errors": [],
            }
        }
        with patch("langsight.cli.investigate.console", Console(file=StringIO())):
            _analyse_with_rules(evidence)  # Should not raise
