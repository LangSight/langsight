from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from langsight.cli.main import cli
from langsight.cli.init import _parse_mcp_config


def _claude_config(tmp_path: Path, servers: dict) -> Path:
    cfg = tmp_path / "claude_desktop_config.json"
    cfg.write_text(json.dumps({"mcpServers": servers}))
    return cfg


class TestParseMcpConfig:
    def test_parses_stdio_server(self, tmp_path: Path) -> None:
        cfg = _claude_config(tmp_path, {
            "postgres": {"command": "python", "args": ["server.py"]}
        })
        servers = _parse_mcp_config(cfg, "Claude Desktop")
        assert len(servers) == 1
        assert servers[0]["name"] == "postgres"
        assert servers[0]["transport"] == "stdio"
        assert servers[0]["command"] == "python"

    def test_parses_sse_server(self, tmp_path: Path) -> None:
        cfg = _claude_config(tmp_path, {
            "my-sse": {"url": "http://localhost:8080/sse"}
        })
        servers = _parse_mcp_config(cfg, "Claude Desktop")
        assert servers[0]["transport"] == "sse"
        assert servers[0]["url"] == "http://localhost:8080/sse"

    def test_parses_env_vars(self, tmp_path: Path) -> None:
        cfg = _claude_config(tmp_path, {
            "pg": {"command": "python", "env": {"DB_HOST": "localhost"}}
        })
        servers = _parse_mcp_config(cfg, "Claude Desktop")
        assert servers[0]["env"]["DB_HOST"] == "localhost"

    def test_empty_config_returns_empty(self, tmp_path: Path) -> None:
        cfg = tmp_path / "mcp.json"
        cfg.write_text(json.dumps({}))
        servers = _parse_mcp_config(cfg, "Cursor")
        assert servers == []

    def test_multiple_servers(self, tmp_path: Path) -> None:
        cfg = _claude_config(tmp_path, {
            "pg": {"command": "python"},
            "s3": {"command": "python"},
        })
        servers = _parse_mcp_config(cfg, "Claude Desktop")
        assert len(servers) == 2
        assert {s["name"] for s in servers} == {"pg", "s3"}


class TestInitCommand:
    def test_exits_1_when_no_mcp_configs_found(self, tmp_path: Path) -> None:
        runner = CliRunner()
        # Patch to non-existent paths so no real configs are discovered
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("langsight.cli.init._MCP_CONFIG_SOURCES", [
                ("Claude Desktop", tmp_path / "nonexistent.json"),
            ])
            result = runner.invoke(cli, ["init", "--yes"])
        assert result.exit_code == 1
        assert "No MCP servers found" in result.output

    def test_writes_config_file(self, tmp_path: Path) -> None:
        cfg_json = tmp_path / "claude_desktop_config.json"
        cfg_json.write_text(json.dumps({
            "mcpServers": {"pg": {"command": "python", "args": ["server.py"]}}
        }))

        output = tmp_path / ".langsight.yaml"
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr(
                    "langsight.cli.init._MCP_CONFIG_SOURCES",
                    [("Claude Desktop", cfg_json)],
                )
                result = runner.invoke(
                    cli,
                    ["init", "--yes", "--output", str(output)],
                )

        assert result.exit_code == 0
        assert output.exists()
        config = yaml.safe_load(output.read_text())
        assert len(config["servers"]) == 1
        assert config["servers"][0]["name"] == "pg"

    def test_includes_slack_webhook(self, tmp_path: Path) -> None:
        cfg_json = tmp_path / "claude_desktop_config.json"
        cfg_json.write_text(json.dumps({
            "mcpServers": {"pg": {"command": "python"}}
        }))
        output = tmp_path / ".langsight.yaml"
        runner = CliRunner()
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "langsight.cli.init._MCP_CONFIG_SOURCES",
                [("Claude Desktop", cfg_json)],
            )
            result = runner.invoke(cli, [
                "init", "--yes",
                "--slack-webhook", "https://hooks.slack.com/test",
                "--output", str(output),
            ])

        config = yaml.safe_load(output.read_text())
        assert config["alerts"]["slack_webhook"] == "https://hooks.slack.com/test"

    def test_shows_discovered_servers_in_output(self, tmp_path: Path) -> None:
        cfg_json = tmp_path / "claude_desktop_config.json"
        cfg_json.write_text(json.dumps({
            "mcpServers": {"my-postgres": {"command": "python"}}
        }))
        output = tmp_path / ".langsight.yaml"
        runner = CliRunner()
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "langsight.cli.init._MCP_CONFIG_SOURCES",
                [("Claude Desktop", cfg_json)],
            )
            result = runner.invoke(cli, ["init", "--yes", "--output", str(output)])

        assert "my-postgres" in result.output
