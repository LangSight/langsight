from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from langsight.exceptions import ConfigError
from langsight.models import MCPServer

# ---------------------------------------------------------------------------
# Sub-configs
# ---------------------------------------------------------------------------


class AlertConfig(BaseModel):
    slack_webhook: str | None = None
    error_rate_threshold: float = 0.05
    latency_spike_multiplier: float = 3.0
    consecutive_failures: int = 3


class StorageConfig(BaseModel):
    mode: str = "sqlite"  # "sqlite" | "postgres" | "clickhouse"
    sqlite_path: str = "~/.langsight/data.db"  # mode="sqlite"
    postgres_url: str | None = None  # mode="postgres"
    clickhouse_url: str = "http://localhost:8123"  # mode="clickhouse"
    clickhouse_database: str = "langsight"  # mode="clickhouse"
    clickhouse_username: str = "default"  # mode="clickhouse"
    clickhouse_password: str = ""  # mode="clickhouse"


class InvestigateConfig(BaseModel):
    """LLM provider config for langsight investigate.

    provider: anthropic | openai | gemini | ollama
    model:    override the default model (optional)
    api_key:  override the env-var API key (optional — prefer env vars)
    base_url: override the default base URL (mainly for Ollama remotes)

    See docs/06-provider-setup.md for setup instructions.
    """

    provider: str = "anthropic"
    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None


# ---------------------------------------------------------------------------
# Top-level project config (.langsight.yaml)
# ---------------------------------------------------------------------------


class LangSightConfig(BaseModel):
    """Parsed contents of .langsight.yaml."""

    servers: list[MCPServer] = Field(default_factory=list)
    alerts: AlertConfig = Field(default_factory=AlertConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    investigate: InvestigateConfig = Field(default_factory=InvestigateConfig)


# ---------------------------------------------------------------------------
# Runtime settings (env vars / .env file)
# ---------------------------------------------------------------------------


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables (LANGSIGHT_ prefix).

    Storage settings here override whatever is in .langsight.yaml — useful
    for Docker deployments where env vars are the primary configuration method.
    """

    slack_webhook: str | None = None
    health_check_interval_seconds: int = 30
    security_scan_interval_seconds: int = 3600
    log_level: str = "INFO"

    # Storage overrides (take precedence over .langsight.yaml)
    storage_mode: str | None = None
    clickhouse_url: str | None = None
    clickhouse_database: str | None = None
    clickhouse_username: str | None = None
    clickhouse_password: str | None = None
    postgres_url: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="LANGSIGHT_",
        extra="ignore",
    )

    def apply_to_storage(self, storage: StorageConfig) -> StorageConfig:
        """Return a new StorageConfig with env var overrides applied."""
        overrides: dict = {}
        if self.storage_mode:
            overrides["mode"] = self.storage_mode
        if self.clickhouse_url:
            overrides["clickhouse_url"] = self.clickhouse_url
        if self.clickhouse_database:
            overrides["clickhouse_database"] = self.clickhouse_database
        if self.clickhouse_username:
            overrides["clickhouse_username"] = self.clickhouse_username
        if self.clickhouse_password is not None:
            overrides["clickhouse_password"] = self.clickhouse_password
        if self.postgres_url:
            overrides["postgres_url"] = self.postgres_url
        if not overrides:
            return storage
        return storage.model_copy(update=overrides)


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------

_CONFIG_SEARCH_PATHS: list[Path] = [
    Path(".langsight.yaml"),
    Path(".langsight.yml"),
    Path("~/.langsight.yaml"),
    Path("~/.langsight.yml"),
]


def load_config(path: Path | None = None) -> LangSightConfig:
    """Load LangSight config from .langsight.yaml or the specified path.

    Search order (when path is None):
      1. .langsight.yaml  (current directory)
      2. .langsight.yml   (current directory)
      3. ~/.langsight.yaml
      4. ~/.langsight.yml

    Returns an empty LangSightConfig (with defaults) when no file is found.
    Raises ConfigError when a file exists but cannot be parsed.
    """
    config_path = _resolve_path(path)

    if config_path is None:
        return LangSightConfig()

    try:
        raw = yaml.safe_load(config_path.read_text())
    except OSError as exc:
        raise ConfigError(f"Cannot read config file '{config_path}': {exc}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in '{config_path}': {exc}") from exc

    if not raw:
        return LangSightConfig()

    try:
        return LangSightConfig.model_validate(raw)
    except Exception as exc:
        raise ConfigError(f"Config validation error in '{config_path}': {exc}") from exc


def _resolve_path(path: Path | None) -> Path | None:
    """Return the first existing config path, or None if none found."""
    if path is not None:
        return path.expanduser()

    for candidate in _CONFIG_SEARCH_PATHS:
        expanded = candidate.expanduser()
        if expanded.exists():
            return expanded

    return None
