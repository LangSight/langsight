from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


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


class SLOMetric(StrEnum):
    SUCCESS_RATE = "success_rate"    # % of sessions with zero failed calls
    LATENCY_P99 = "latency_p99"      # p99 session duration in ms (approximated from avg)


class AgentSLO(BaseModel):
    """Definition of a Service Level Objective for an agent.

    Example: "customer-support-bot must have >= 95% success rate over 24h"
        AgentSLO(agent_name="customer-support-bot", metric="success_rate",
                 target=95.0, window_hours=24)
    """

    id: str  # uuid4 hex — assigned on creation
    agent_name: str
    metric: SLOMetric
    target: float   # success_rate: percentage 0-100 | latency_p99: milliseconds
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


class ApiKeyRole(StrEnum):
    ADMIN = "admin"    # full access — can trigger scans, ingest spans, manage keys
    VIEWER = "viewer"  # read-only — GET endpoints only


class ApiKeyRecord(BaseModel):
    """A stored API key (the raw key is never persisted — only the hash)."""

    id: str  # uuid4 hex
    name: str  # user-given label
    key_prefix: str  # first 8 chars of raw key — shown in UI for identification
    key_hash: str  # sha256(raw_key) — used for lookup
    role: ApiKeyRole = ApiKeyRole.ADMIN  # default admin for backwards compatibility
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

