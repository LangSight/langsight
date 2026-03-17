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
    mode: str = "sqlite"  # "sqlite" | "postgres"
    sqlite_path: str = "~/.langsight/data.db"  # used when mode="sqlite"
    postgres_url: str | None = None  # used when mode="postgres"


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
    """Runtime settings loaded from environment variables (LANGSIGHT_ prefix)."""

    slack_webhook: str | None = None
    health_check_interval_seconds: int = 30
    security_scan_interval_seconds: int = 3600
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="LANGSIGHT_",
        extra="ignore",
    )


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
