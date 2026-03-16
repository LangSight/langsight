from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from langsight.config import AlertConfig, LangSightConfig, StorageConfig, load_config
from langsight.exceptions import ConfigError
from langsight.models import TransportType


class TestLoadConfig:
    def test_returns_defaults_when_no_file_found(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        config = load_config()
        assert config.servers == []
        assert isinstance(config.alerts, AlertConfig)
        assert isinstance(config.storage, StorageConfig)

    def test_loads_from_explicit_path(self, tmp_path: Path) -> None:
        config_file = tmp_path / ".langsight.yaml"
        config_file.write_text(
            yaml.dump({
                "servers": [
                    {"name": "pg", "transport": "stdio", "command": "python server.py"}
                ]
            })
        )
        config = load_config(config_file)
        assert len(config.servers) == 1
        assert config.servers[0].name == "pg"

    def test_loads_server_transport(self, tmp_path: Path) -> None:
        config_file = tmp_path / ".langsight.yaml"
        config_file.write_text(
            yaml.dump({
                "servers": [
                    {"name": "sse-srv", "transport": "sse", "url": "http://localhost/sse"}
                ]
            })
        )
        config = load_config(config_file)
        assert config.servers[0].transport == TransportType.SSE

    def test_loads_alert_config(self, tmp_path: Path) -> None:
        config_file = tmp_path / ".langsight.yaml"
        config_file.write_text(
            yaml.dump({
                "alerts": {
                    "slack_webhook": "https://hooks.slack.com/test",
                    "error_rate_threshold": 0.1,
                }
            })
        )
        config = load_config(config_file)
        assert config.alerts.slack_webhook == "https://hooks.slack.com/test"
        assert config.alerts.error_rate_threshold == 0.1

    def test_empty_yaml_returns_defaults(self, tmp_path: Path) -> None:
        config_file = tmp_path / ".langsight.yaml"
        config_file.write_text("")
        config = load_config(config_file)
        assert config.servers == []

    def test_raises_config_error_on_invalid_yaml(self, tmp_path: Path) -> None:
        config_file = tmp_path / ".langsight.yaml"
        config_file.write_text("servers: [invalid: yaml: {{")
        with pytest.raises(ConfigError, match="Invalid YAML"):
            load_config(config_file)

    def test_raises_config_error_on_invalid_schema(self, tmp_path: Path) -> None:
        config_file = tmp_path / ".langsight.yaml"
        config_file.write_text(yaml.dump({"servers": [{"name": "x", "transport": "ftp"}]}))
        with pytest.raises(ConfigError, match="Config validation error"):
            load_config(config_file)

    def test_auto_discovers_in_current_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        config_file = tmp_path / ".langsight.yaml"
        config_file.write_text(
            yaml.dump({"servers": [{"name": "auto", "transport": "stdio", "command": "x"}]})
        )
        config = load_config()
        assert config.servers[0].name == "auto"

    def test_multiple_servers(self, tmp_path: Path) -> None:
        config_file = tmp_path / ".langsight.yaml"
        config_file.write_text(
            yaml.dump({
                "servers": [
                    {"name": "pg", "transport": "stdio", "command": "python pg.py"},
                    {"name": "s3", "transport": "stdio", "command": "python s3.py"},
                ]
            })
        )
        config = load_config(config_file)
        assert len(config.servers) == 2
        assert {s.name for s in config.servers} == {"pg", "s3"}


class TestAlertConfig:
    def test_defaults(self) -> None:
        a = AlertConfig()
        assert a.slack_webhook is None
        assert a.error_rate_threshold == 0.05
        assert a.latency_spike_multiplier == 3.0
        assert a.consecutive_failures == 3


class TestStorageConfig:
    def test_defaults(self) -> None:
        s = StorageConfig()
        assert s.mode == "sqlite"
        assert "langsight" in s.sqlite_path
