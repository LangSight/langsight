from __future__ import annotations

from pathlib import Path
from typing import Any

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
    mode: str = "dual"  # "postgres" | "clickhouse" | "dual" (default: production topology)
    # "dual" = Postgres (metadata: users/projects/API keys/SLOs) +
    #          ClickHouse (analytics: spans/health/costs/reliability)
    postgres_url: str | None = None  # required for mode="postgres" or "dual"
    pg_pool_min: int = 2  # asyncpg pool min connections
    pg_pool_max: int = 50  # asyncpg pool max connections
    # 50 handles ~200 concurrent API requests at typical <50ms query latency.
    # Tune down via LANGSIGHT_PG_POOL_MAX if your Postgres server is small
    # (e.g. managed free-tier with max_connections=25 — set to 15).
    clickhouse_url: str = "http://localhost:8123"  # mode="clickhouse"
    clickhouse_database: str = "langsight"  # mode="clickhouse"
    clickhouse_username: str = "default"  # mode="clickhouse"
    clickhouse_password: str = ""  # mode="clickhouse"


class InvestigateConfig(BaseModel):
    """LLM provider config for langsight investigate.

    provider: anthropic | openai | gemini | ollama
    model:    override the default model (optional)
    base_url: override the default base URL (mainly for Ollama remotes)

    LLM API keys must be set via environment variables (ANTHROPIC_API_KEY,
    OPENAI_API_KEY, etc.) — never store them in .langsight.yaml.

    See docs/06-provider-setup.md for setup instructions.
    """

    provider: str = "anthropic"
    model: str | None = None
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
    # P5.1 — payload capture
    # Set to True to prevent tool call arguments and return values from being
    # stored. Use this when tools may handle PII (names, emails, financial data).
    redact_payloads: bool = False
    # Project scoping — optional.
    # When set, all CLI health checks are stored under this project_id so they
    # appear in the correct project dashboard instead of the global (unscoped) view.
    # The API key's project_id takes precedence when a project-scoped key is used.
    #
    # Example .langsight.yaml:
    #   project: production          # human-readable slug
    #   project_id: "abc123"         # UUID from the dashboard (preferred)
    project: str = ""  # project slug (display only — resolved to id at query time)
    project_id: str = ""  # project UUID — used directly for storage scoping


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

    # --- Embedded monitor (runs inside `langsight serve`) -------------------
    # Set LANGSIGHT_MONITOR_ENABLED=false to disable the built-in loop and
    # run `langsight monitor` as a separate process instead.
    monitor_enabled: bool = True
    # Interval between health-check cycles when the embedded loop is active.
    # Default 60s (gentler than CLI default of 30s — serves more users).
    monitor_interval_seconds: int = 60

    # --- Auth ------------------------------------------------------------------
    # Comma-separated list of valid API keys, e.g. "key1,key2".
    # When empty (default), authentication is DISABLED — safe for local dev only.
    # Set at least one key before exposing the API on a network.
    api_keys: str = ""
    # CORS allowed origins.  Override with LANGSIGHT_CORS_ORIGINS for production.
    cors_origins: str = "http://localhost:3003"
    # Dashboard base URL used when constructing invite links.
    # Must point to the Next.js dashboard, NOT the FastAPI backend.
    # Example: https://langsight.example.com
    dashboard_url: str | None = None
    # Comma-separated CIDRs or IPs trusted as the Next.js proxy.
    # Requests from these addresses may carry X-User-Id / X-User-Role headers.
    # In Docker/K8s, add the container network range (e.g. 172.16.0.0/12).
    trusted_proxy_cidrs: str = "127.0.0.1/32,::1/128"

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

    def parsed_api_keys(self) -> list[str]:
        """Return the list of valid API keys (empty = auth disabled)."""
        return [k.strip() for k in self.api_keys.split(",") if k.strip()]

    def parsed_cors_origins(self) -> list[str]:
        """Return the list of allowed CORS origins."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def apply_to_storage(self, storage: StorageConfig) -> StorageConfig:
        """Return a new StorageConfig with env var overrides applied."""
        overrides: dict[str, Any] = {}
        if self.storage_mode:
            overrides["mode"] = self.storage_mode
        if self.clickhouse_url:
            overrides["clickhouse_url"] = self.clickhouse_url
        if self.clickhouse_database:
            overrides["clickhouse_database"] = self.clickhouse_database
        if self.clickhouse_username:
            overrides["clickhouse_username"] = self.clickhouse_username
        if self.clickhouse_password:  # empty string must not override YAML-set password
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
