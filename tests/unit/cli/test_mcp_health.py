from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import yaml
from click.testing import CliRunner

from langsight.cli.main import cli
from langsight.models import HealthCheckResult, MCPServer, ServerStatus, ToolInfo, TransportType

TOOL = ToolInfo(name="query", description="Execute SQL")
UP_RESULT = HealthCheckResult(
    server_name="test-pg",
    status=ServerStatus.UP,
    latency_ms=42.0,
    tools=[TOOL],
    tools_count=1,
    schema_hash="abc123def456ab12",
)
DOWN_RESULT = HealthCheckResult(
    server_name="test-pg",
    status=ServerStatus.DOWN,
    error="timeout after 5s",
)


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    cfg = tmp_path / ".langsight.yaml"
    cfg.write_text(
        yaml.dump({
            "servers": [{"name": "test-pg", "transport": "stdio", "command": "python server.py"}]
        })
    )
    return cfg


class TestMcpHealthCommand:
    def test_shows_table_on_success(self, config_file: Path) -> None:
        runner = CliRunner()
        with patch("langsight.cli.mcp_health.HealthChecker") as MockChecker:
            MockChecker.return_value.check_many = AsyncMock(return_value=[UP_RESULT])
            result = runner.invoke(cli, ["mcp-health", "--config", str(config_file)])

        assert result.exit_code == 0
        assert "test-pg" in result.output
        assert "up" in result.output

    def test_exits_1_when_server_down(self, config_file: Path) -> None:
        runner = CliRunner()
        with patch("langsight.cli.mcp_health.HealthChecker") as MockChecker:
            MockChecker.return_value.check_many = AsyncMock(return_value=[DOWN_RESULT])
            result = runner.invoke(cli, ["mcp-health", "--config", str(config_file)])

        assert result.exit_code == 1

    def test_json_flag_outputs_valid_json(self, config_file: Path) -> None:
        import json

        runner = CliRunner()
        with patch("langsight.cli.mcp_health.HealthChecker") as MockChecker:
            MockChecker.return_value.check_many = AsyncMock(return_value=[UP_RESULT])
            result = runner.invoke(cli, ["mcp-health", "--config", str(config_file), "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert data[0]["server_name"] == "test-pg"
        assert data[0]["status"] == "up"

    def test_exits_1_when_no_servers_configured(self, tmp_path: Path) -> None:
        cfg = tmp_path / ".langsight.yaml"
        cfg.write_text(yaml.dump({"servers": []}))
        runner = CliRunner()
        result = runner.invoke(cli, ["mcp-health", "--config", str(cfg)])
        assert result.exit_code == 1

    def test_shows_latency_in_table(self, config_file: Path) -> None:
        runner = CliRunner()
        with patch("langsight.cli.mcp_health.HealthChecker") as MockChecker:
            MockChecker.return_value.check_many = AsyncMock(return_value=[UP_RESULT])
            result = runner.invoke(cli, ["mcp-health", "--config", str(config_file)])

        assert "42ms" in result.output

    def test_shows_error_for_down_server(self, config_file: Path) -> None:
        runner = CliRunner()
        with patch("langsight.cli.mcp_health.HealthChecker") as MockChecker:
            MockChecker.return_value.check_many = AsyncMock(return_value=[DOWN_RESULT])
            result = runner.invoke(cli, ["mcp-health", "--config", str(config_file)])

        assert "down" in result.output  # Rich may wrap long error text across lines

    def test_multiple_servers_all_shown(self, tmp_path: Path) -> None:
        cfg = tmp_path / ".langsight.yaml"
        cfg.write_text(yaml.dump({
            "servers": [
                {"name": "pg", "transport": "stdio", "command": "python pg.py"},
                {"name": "s3", "transport": "stdio", "command": "python s3.py"},
            ]
        }))
        results = [
            HealthCheckResult(server_name="pg", status=ServerStatus.UP, latency_ms=10.0, tools_count=5),
            HealthCheckResult(server_name="s3", status=ServerStatus.UP, latency_ms=20.0, tools_count=7),
        ]
        runner = CliRunner()
        with patch("langsight.cli.mcp_health.HealthChecker") as MockChecker:
            MockChecker.return_value.check_many = AsyncMock(return_value=results)
            result = runner.invoke(cli, ["mcp-health", "--config", str(cfg)])

        assert "pg" in result.output
        assert "s3" in result.output
        assert result.exit_code == 0
