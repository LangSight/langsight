"""Pydantic domain models for LangSight — servers, health, security, projects, SLOs."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from langsight.sdk.circuit_breaker import CircuitBreakerConfig


class ServerStatus(StrEnum):
    UP = "up"
    DEGRADED = "degraded"
    DOWN = "down"
    STALE = "stale"
    UNKNOWN = "unknown"


class TransportType(StrEnum):
    STDIO = "stdio"
    SSE = "sse"
    STREAMABLE_HTTP = "streamable_http"


class MCPServer(BaseModel):
    """Configuration for a single MCP server to monitor."""

    name: str
    transport: TransportType
    url: str | None = None
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    timeout_seconds: int = 5
    circuit_breaker: CircuitBreakerConfig | None = None  # v0.3 per-server override
    # Optional deep health probe — call this tool after tools/list to verify
    # the underlying backend is actually working (not just the MCP layer).
    # If the call fails → status=DEGRADED instead of UP.
    # Example: health_tool: search_entities
    #          health_tool_args: {query: "test", limit: 1}
    health_tool: str | None = None
    health_tool_args: dict[str, Any] = Field(default_factory=dict)

    model_config = {"frozen": True}


class ToolInfo(BaseModel):
    """Metadata about a single MCP tool as reported by tools/list."""

    name: str
    description: str | None = None
    input_schema: dict[str, Any] = Field(default_factory=dict)


class HealthCheckResult(BaseModel):
    """Result of a single health check against one MCP server."""

    server_name: str
    status: ServerStatus
    latency_ms: float | None = None
    tools: list[ToolInfo] = Field(default_factory=list)
    tools_count: int = 0
    schema_hash: str | None = None
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    error: str | None = None
    project_id: str = ""  # empty = global health check (CLI/monitor), project id = project-scoped


class ModelPricing(BaseModel):
    """Per-model LLM token pricing entry.

    Prices are per 1M tokens (standard industry convention).
    effective_to=None means currently active.
    When a provider updates prices, deactivate the old row (set effective_to)
    and insert a new row — preserving full audit history.
    """

    id: str
    provider: str  # "anthropic" | "openai" | "google" | "meta" | "custom"
    model_id: str  # matches gen_ai.request.model attribute
    display_name: str
    input_per_1m_usd: float = 0.0  # $ per 1M input tokens
    output_per_1m_usd: float = 0.0  # $ per 1M output tokens
    cache_read_per_1m_usd: float = 0.0  # $ per 1M cached input tokens (Anthropic prompt caching)
    effective_from: datetime = Field(default_factory=lambda: datetime.now(UTC))
    effective_to: datetime | None = None
    notes: str | None = None
    is_custom: bool = False  # True = user-added, False = seeded builtin

    model_config = {"frozen": True}

    @property
    def is_active(self) -> bool:
        return self.effective_to is None

    def cost_for(self, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost for a single LLM call given token counts."""
        return (
            input_tokens / 1_000_000 * self.input_per_1m_usd
            + output_tokens / 1_000_000 * self.output_per_1m_usd
        )


class ProjectRole(StrEnum):
    OWNER = "owner"  # full control — rename, invite, delete project
    MEMBER = "member"  # operational — view traces, create SLOs, trigger scans
    VIEWER = "viewer"  # read-only — view all data, no writes


class Project(BaseModel):
    """A project groups all observability data for one product or environment."""

    id: str  # uuid4 hex
    name: str  # display name, e.g. "Customer Support"
    slug: str  # url-safe unique identifier, e.g. "customer-support"
    created_by: str  # user id of creator
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = {"frozen": True}


class ProjectMember(BaseModel):
    """A user's membership in a project with a project-level role."""

    project_id: str
    user_id: str
    role: ProjectRole = ProjectRole.VIEWER
    added_by: str  # user id of whoever granted membership
    added_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = {"frozen": True}


class UserRole(StrEnum):
    ADMIN = "admin"  # full access — can invite users, trigger scans, manage API keys
    VIEWER = "viewer"  # read-only — dashboards and traces, no write operations


class User(BaseModel):
    """A dashboard user account."""

    id: str  # uuid4 hex
    email: str
    password_hash: str  # bcrypt hash — never expose raw
    role: UserRole = UserRole.VIEWER
    active: bool = True
    invited_by: str | None = None  # user id of the admin who invited them
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_login_at: datetime | None = None

    model_config = {"frozen": True}


class InviteToken(BaseModel):
    """A one-time invite token for a new user."""

    token: str  # random 32-byte hex token
    email: str  # email the invite is for
    role: UserRole = UserRole.VIEWER
    invited_by: str  # user id of admin
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime  # 72h after creation
    used_at: datetime | None = None

    @property
    def is_expired(self) -> bool:
        return datetime.now(UTC) > self.expires_at

    @property
    def is_used(self) -> bool:
        return self.used_at is not None


class SLOMetric(StrEnum):
    SUCCESS_RATE = "success_rate"  # % of sessions with zero failed calls
    LATENCY_P99 = "latency_p99"  # p99 session duration in ms (approximated from avg)


class AgentSLO(BaseModel):
    """Definition of a Service Level Objective for an agent.

    Example: "customer-support-bot must have >= 95% success rate over 24h"
        AgentSLO(agent_name="customer-support-bot", metric="success_rate",
                 target=95.0, window_hours=24)
    """

    id: str  # uuid4 hex — assigned on creation
    project_id: str = ""  # empty string = global/unscoped (pre-v0.3.2 rows)
    agent_name: str
    metric: SLOMetric
    target: float  # success_rate: percentage 0-100 | latency_p99: milliseconds
    window_hours: int = 24
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = {"frozen": True}


class SLOEvaluation(BaseModel):
    """Result of evaluating one SLO against current data."""

    slo_id: str
    agent_name: str
    metric: SLOMetric
    target: float
    current_value: float | None  # None when no data available
    window_hours: int
    status: str  # "ok" | "breached" | "no_data"
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def is_breached(self) -> bool:
        return self.status == "breached"


# ---------------------------------------------------------------------------
# Schema drift models
# ---------------------------------------------------------------------------


class DriftType(StrEnum):
    BREAKING = "breaking"  # agents using this tool will break
    COMPATIBLE = "compatible"  # agents still work, new optional capability
    WARNING = "warning"  # description changed — potential poisoning vector


class SchemaChange(BaseModel):
    """One atomic change detected between two tool schema snapshots."""

    drift_type: DriftType
    kind: str  # tool_removed | tool_added | required_param_removed |
    # required_param_added | param_type_changed |
    # optional_param_added | description_changed
    tool_name: str
    param_name: str | None = None
    old_value: str | None = None
    new_value: str | None = None


class SchemaDriftEvent(BaseModel):
    """Full drift event emitted when tool schemas change between snapshots."""

    server_name: str
    changes: list[SchemaChange]
    has_breaking: bool
    previous_hash: str | None = None
    current_hash: str
    detected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    project_id: str = ""


class ApiKeyRole(StrEnum):
    ADMIN = "admin"  # full access — can trigger scans, ingest spans, manage keys
    VIEWER = "viewer"  # read-only — GET endpoints only


class ApiKeyRecord(BaseModel):
    """A stored API key (the raw key is never persisted — only the hash)."""

    id: str  # uuid4 hex
    name: str  # user-given label
    key_prefix: str  # first 8 chars of raw key — shown in UI for identification
    key_hash: str  # sha256(raw_key) — used for lookup
    role: ApiKeyRole = ApiKeyRole.ADMIN  # default admin for backwards compatibility
    user_id: str | None = None  # owning user — used for project membership checks
    project_id: str | None = None  # when set, all CLI health checks using this key
    # are scoped to this project automatically
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None
    expires_at: datetime | None = None  # optional expiration — None means never expires

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    @property
    def is_expired(self) -> bool:
        return self.expires_at is not None and datetime.now(UTC) >= self.expires_at

    @property
    def is_active(self) -> bool:
        return not self.is_revoked and not self.is_expired


# ---------------------------------------------------------------------------
# v0.3 Prevention Config (dashboard-managed thresholds)
# ---------------------------------------------------------------------------


class PreventionConfig(BaseModel):
    """Dashboard-managed prevention thresholds for one agent.

    Stored in Postgres, fetched by the SDK on wrap(). SDK constructor params
    serve as offline fallback when the API is unreachable.

    agent_name = "*" represents the project-level default, applied to all
    agents that have no agent-specific config entry.
    """

    id: str
    project_id: str
    agent_name: str  # specific agent name or "*" for project-level default

    # Loop detection
    loop_enabled: bool = True
    loop_threshold: int = 3  # same tool+args N times = loop
    loop_action: str = "terminate"  # "terminate" | "warn"

    # Budget guardrails
    max_steps: int | None = None  # None = disabled
    max_cost_usd: float | None = None  # None = disabled
    max_wall_time_s: float | None = None  # None = disabled
    budget_soft_alert: float = 0.80

    # Circuit breaker
    cb_enabled: bool = True
    cb_failure_threshold: int = 5
    cb_cooldown_seconds: float = 60.0
    cb_half_open_max_calls: int = 2

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = {"frozen": True}
