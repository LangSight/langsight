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
