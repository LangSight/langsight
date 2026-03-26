"""Unit tests for langsight.cli.add — registering MCP servers to .langsight.yaml.

All external calls (HealthChecker.check) are mocked. No real MCP connections.
Config I/O is done in tmp_path so the working directory is never polluted.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml
from click.testing import CliRunner

from langsight.cli.add import (
    _append_server,
    _load_config,
    _save_config,
    _server_exists,
)
from langsight.cli.main import cli


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ok_health_result(tool_names: list[str] | None = None) -> MagicMock:
    """Return a mock HealthCheckResult that represents a healthy (UP) server."""
    result = MagicMock()
    result.status = MagicMock()
    result.status.value = "up"
    result.latency_ms = 42.0
    result.error = None
    if tool_names is not None:
        result.tools = [MagicMock(name=n) for n in tool_names]
    else:
        result.tools = []
    return result


def _down_health_result(error: str = "connection refused") -> MagicMock:
    """Return a mock HealthCheckResult that represents a DOWN server."""
    result = MagicMock()
    result.status = MagicMock()
    result.status.value = "down"
    result.latency_ms = None
    result.error = error
    result.tools = []
    return result


def _invoke_add(
    args: list[str],
    config_path: Path | None = None,
    input_text: str | None = None,
) -> object:
    """Invoke `langsight add` with the Click test runner."""
    runner = CliRunner()
    full_args = ["add"] + args
    if config_path:
        full_args += ["--config", str(config_path)]
    return runner.invoke(cli, full_args, input=input_text, catch_exceptions=False)


# ---------------------------------------------------------------------------
# Config helper unit tests (pure functions — no mocking)
# ---------------------------------------------------------------------------


class TestConfigHelpers:
    def test_load_config_returns_empty_when_missing(self, tmp_path: Path) -> None:
        """_load_config returns {} when file does not exist."""
        result = _load_config(tmp_path / "nonexistent.yaml")
        assert result == {}

    def test_load_config_parses_yaml(self, tmp_path: Path) -> None:
        """_load_config parses a valid YAML file."""
        cfg = tmp_path / "config.yaml"
        cfg.write_text(yaml.dump({"servers": [{"name": "pg"}]}))
        result = _load_config(cfg)
        assert result["servers"][0]["name"] == "pg"

    def test_server_exists_returns_true_when_found(self) -> None:
        """_server_exists returns True when a server with the given name is present."""
        config = {"servers": [{"name": "pg"}, {"name": "s3"}]}
        assert _server_exists(config, "pg") is True

    def test_server_exists_returns_false_when_not_found(self) -> None:
        """_server_exists returns False when no server has that name."""
        config = {"servers": [{"name": "pg"}]}
        assert _server_exists(config, "redis") is False

    def test_server_exists_returns_false_on_empty_config(self) -> None:
        """_server_exists returns False on empty config."""
        assert _server_exists({}, "anything") is False

    def test_append_server_creates_servers_key(self) -> None:
        """_append_server creates the 'servers' list if absent."""
        config: dict = {}
        _append_server(config, {"name": "pg"})
        assert config["servers"] == [{"name": "pg"}]

    def test_append_server_appends_to_existing_list(self) -> None:
        """_append_server appends without removing existing entries."""
        config = {"servers": [{"name": "pg"}]}
        _append_server(config, {"name": "redis"})
        assert len(config["servers"]) == 2

    def test_save_config_writes_valid_yaml(self, tmp_path: Path) -> None:
        """_save_config writes a YAML file that can be round-tripped."""
        cfg = tmp_path / "output.yaml"
        _save_config({"servers": [{"name": "test"}]}, cfg)
        assert cfg.exists()
        loaded = yaml.safe_load(cfg.read_text())
        assert loaded["servers"][0]["name"] == "test"


# ---------------------------------------------------------------------------
# add command — HTTP server
# ---------------------------------------------------------------------------


class TestAddHttpServer:
    def test_add_http_server_writes_config(self, tmp_path: Path) -> None:
        """Adding an HTTP server writes it to the config file."""
        config_path = tmp_path / ".langsight.yaml"
        mock_result = _ok_health_result(tool_names=["query"])

        with patch("langsight.cli.add._test_connection", new=AsyncMock(return_value=(True, "", 42, ["query"]))):
            result = _invoke_add(
                ["my-http-server", "--url", "https://mcp.example.com/mcp"],
                config_path=config_path,
            )

        assert result.exit_code == 0, result.output
        assert config_path.exists()
        config = yaml.safe_load(config_path.read_text())
        server = next(s for s in config["servers"] if s["name"] == "my-http-server")
        assert server["url"] == "https://mcp.example.com/mcp"
        assert server["transport"] == "streamable_http"

    def test_add_sse_server_sets_sse_transport(self, tmp_path: Path) -> None:
        """URL ending in /sse sets transport to 'sse'."""
        config_path = tmp_path / ".langsight.yaml"

        with patch("langsight.cli.add._test_connection", new=AsyncMock(return_value=(True, "", 10, []))):
            result = _invoke_add(
                ["my-sse", "--url", "http://localhost:8080/sse"],
                config_path=config_path,
            )

        assert result.exit_code == 0, result.output
        config = yaml.safe_load(config_path.read_text())
        server = next(s for s in config["servers"] if s["name"] == "my-sse")
        assert server["transport"] == "sse"

    def test_add_parses_header_pairs(self, tmp_path: Path) -> None:
        """--header KEY=VALUE pairs are parsed and stored under 'headers'."""
        config_path = tmp_path / ".langsight.yaml"

        with patch("langsight.cli.add._test_connection", new=AsyncMock(return_value=(True, "", 10, []))):
            result = _invoke_add(
                [
                    "secure-server",
                    "--url", "https://mcp.example.com/mcp",
                    "--header", "Authorization=Bearer my-token",
                    "--header", "X-Tenant=acme",
                ],
                config_path=config_path,
            )

        assert result.exit_code == 0, result.output
        config = yaml.safe_load(config_path.read_text())
        server = next(s for s in config["servers"] if s["name"] == "secure-server")
        assert server["headers"]["Authorization"] == "Bearer my-token"
        assert server["headers"]["X-Tenant"] == "acme"

    def test_add_malformed_header_pair_warns_and_skips(self, tmp_path: Path) -> None:
        """A header pair without '=' produces a warning and is skipped."""
        config_path = tmp_path / ".langsight.yaml"

        with patch("langsight.cli.add._test_connection", new=AsyncMock(return_value=(True, "", 10, []))):
            result = _invoke_add(
                [
                    "server",
                    "--url", "https://mcp.example.com/mcp",
                    "--header", "MALFORMED_NO_EQUALS",
                ],
                config_path=config_path,
            )

        assert result.exit_code == 0, result.output
        assert "Warning" in result.output or "warning" in result.output.lower()
        config = yaml.safe_load(config_path.read_text())
        server = next(s for s in config["servers"] if s["name"] == "server")
        assert "headers" not in server or "MALFORMED_NO_EQUALS" not in str(server.get("headers", {}))


# ---------------------------------------------------------------------------
# add command — stdio server
# ---------------------------------------------------------------------------


class TestAddStdioServer:
    def test_add_stdio_server_writes_config(self, tmp_path: Path) -> None:
        """Adding a stdio server writes it to the config file."""
        config_path = tmp_path / ".langsight.yaml"

        with patch("langsight.cli.add._test_connection", new=AsyncMock(return_value=(True, "", 100, []))):
            result = _invoke_add(
                ["local-db", "--command", "uv run server.py"],
                config_path=config_path,
            )

        assert result.exit_code == 0, result.output
        config = yaml.safe_load(config_path.read_text())
        server = next(s for s in config["servers"] if s["name"] == "local-db")
        assert server["command"] == "uv run server.py"
        assert server["transport"] == "stdio"

    def test_add_parses_env_pairs(self, tmp_path: Path) -> None:
        """--env KEY=VALUE pairs are parsed and stored under 'env'."""
        config_path = tmp_path / ".langsight.yaml"

        with patch("langsight.cli.add._test_connection", new=AsyncMock(return_value=(True, "", 10, []))):
            result = _invoke_add(
                [
                    "db-server",
                    "--command", "python server.py",
                    "--env", "DB_HOST=localhost",
                    "--env", "DB_PORT=5432",
                ],
                config_path=config_path,
            )

        assert result.exit_code == 0, result.output
        config = yaml.safe_load(config_path.read_text())
        server = next(s for s in config["servers"] if s["name"] == "db-server")
        assert server["env"]["DB_HOST"] == "localhost"
        assert server["env"]["DB_PORT"] == "5432"

    def test_add_malformed_env_pair_warns_and_skips(self, tmp_path: Path) -> None:
        """An env pair without '=' produces a warning and is skipped."""
        config_path = tmp_path / ".langsight.yaml"

        with patch("langsight.cli.add._test_connection", new=AsyncMock(return_value=(True, "", 10, []))):
            result = _invoke_add(
                [
                    "db-server",
                    "--command", "python server.py",
                    "--env", "MALFORMED",
                ],
                config_path=config_path,
            )

        assert result.exit_code == 0, result.output
        assert "Warning" in result.output or "warning" in result.output.lower()


# ---------------------------------------------------------------------------
# add command — validation errors
# ---------------------------------------------------------------------------


class TestAddValidation:
    def test_add_missing_url_and_command_exits(self, tmp_path: Path) -> None:
        """Providing neither --url nor --command exits with code 1."""
        result = _invoke_add(["my-server"], config_path=tmp_path / "cfg.yaml")
        assert result.exit_code == 1
        assert "url" in result.output.lower() or "command" in result.output.lower()

    def test_add_outputs_server_name_in_confirmation(self, tmp_path: Path) -> None:
        """Output mentions the server name after successful add."""
        config_path = tmp_path / ".langsight.yaml"

        with patch("langsight.cli.add._test_connection", new=AsyncMock(return_value=(True, "", 10, []))):
            result = _invoke_add(
                ["my-unique-name", "--command", "python server.py"],
                config_path=config_path,
            )

        assert "my-unique-name" in result.output


# ---------------------------------------------------------------------------
# add command — skip-check
# ---------------------------------------------------------------------------


class TestAddSkipCheck:
    def test_add_skip_check_skips_connection(self, tmp_path: Path) -> None:
        """--skip-check does not call _test_connection."""
        config_path = tmp_path / ".langsight.yaml"

        with patch("langsight.cli.add._test_connection", new=AsyncMock()) as mock_test:
            result = _invoke_add(
                ["skipped-server", "--url", "https://mcp.example.com/mcp", "--skip-check"],
                config_path=config_path,
            )

        assert result.exit_code == 0, result.output
        mock_test.assert_not_called()

    def test_add_skip_check_still_writes_config(self, tmp_path: Path) -> None:
        """--skip-check still appends the server to the config."""
        config_path = tmp_path / ".langsight.yaml"

        with patch("langsight.cli.add._test_connection", new=AsyncMock()):
            result = _invoke_add(
                ["no-check-server", "--command", "echo hi", "--skip-check"],
                config_path=config_path,
            )

        assert result.exit_code == 0, result.output
        config = yaml.safe_load(config_path.read_text())
        names = [s["name"] for s in config.get("servers", [])]
        assert "no-check-server" in names

    def test_add_skip_check_output_mentions_skipped(self, tmp_path: Path) -> None:
        """--skip-check emits a 'Skipping' message in output."""
        config_path = tmp_path / ".langsight.yaml"

        with patch("langsight.cli.add._test_connection", new=AsyncMock()):
            result = _invoke_add(
                ["skip-msg", "--command", "echo hi", "--skip-check"],
                config_path=config_path,
            )

        assert "skip" in result.output.lower()


# ---------------------------------------------------------------------------
# add command — deduplication
# ---------------------------------------------------------------------------


class TestAddDuplication:
    def test_add_duplicate_name_prompts_overwrite(self, tmp_path: Path) -> None:
        """When server name already exists, user is prompted to confirm overwrite."""
        config_path = tmp_path / ".langsight.yaml"
        # Pre-populate the config with an existing server
        _save_config({"servers": [{"name": "existing", "command": "old"}]}, config_path)

        with patch("langsight.cli.add._test_connection", new=AsyncMock(return_value=(True, "", 10, []))):
            result = _invoke_add(
                ["existing", "--command", "new"],
                config_path=config_path,
                input_text="y\n",   # user confirms overwrite
            )

        assert result.exit_code == 0, result.output
        assert "already exists" in result.output or "Overwrite" in result.output

    def test_add_duplicate_name_decline_overwrite_exits_cleanly(
        self, tmp_path: Path
    ) -> None:
        """Declining overwrite exits with code 0 (user cancelled)."""
        config_path = tmp_path / ".langsight.yaml"
        _save_config({"servers": [{"name": "existing", "command": "old"}]}, config_path)

        with patch("langsight.cli.add._test_connection", new=AsyncMock()):
            result = _invoke_add(
                ["existing", "--command", "new"],
                config_path=config_path,
                input_text="n\n",   # user declines
            )

        assert result.exit_code == 0

    def test_add_duplicate_overwrite_replaces_server(self, tmp_path: Path) -> None:
        """Confirming overwrite replaces the old server entry."""
        config_path = tmp_path / ".langsight.yaml"
        _save_config({"servers": [{"name": "pg", "command": "old-cmd"}]}, config_path)

        with patch("langsight.cli.add._test_connection", new=AsyncMock(return_value=(True, "", 10, []))):
            result = _invoke_add(
                ["pg", "--command", "new-cmd"],
                config_path=config_path,
                input_text="y\n",
            )

        config = yaml.safe_load(config_path.read_text())
        pg_entries = [s for s in config["servers"] if s["name"] == "pg"]
        assert len(pg_entries) == 1
        assert pg_entries[0]["command"] == "new-cmd"


# ---------------------------------------------------------------------------
# add command — failed connection test
# ---------------------------------------------------------------------------


class TestAddConnectionFailure:
    def test_failed_connection_prompts_add_anyway(self, tmp_path: Path) -> None:
        """When connection test fails, user is asked whether to add anyway."""
        config_path = tmp_path / ".langsight.yaml"

        with patch("langsight.cli.add._test_connection",
                   new=AsyncMock(return_value=(False, "connection refused", 0, []))):
            result = _invoke_add(
                ["dead-server", "--url", "https://gone.example.com/mcp"],
                config_path=config_path,
                input_text="n\n",   # decline to add anyway
            )

        assert result.exit_code == 1 or "failed" in result.output.lower()

    def test_failed_connection_add_anyway_yes_writes_config(self, tmp_path: Path) -> None:
        """When connection fails and user says 'yes, add anyway', config is written."""
        config_path = tmp_path / ".langsight.yaml"

        with patch("langsight.cli.add._test_connection",
                   new=AsyncMock(return_value=(False, "timeout", 0, []))):
            result = _invoke_add(
                ["unreachable", "--url", "https://gone.example.com/mcp"],
                config_path=config_path,
                input_text="y\n",   # add anyway
            )

        assert result.exit_code == 0, result.output
        config = yaml.safe_load(config_path.read_text())
        names = [s["name"] for s in config.get("servers", [])]
        assert "unreachable" in names
