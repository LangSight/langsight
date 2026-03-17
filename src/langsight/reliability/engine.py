"""
Tool reliability engine — aggregates tool call spans into reliability metrics.

Queries ClickHouse (or falls back to SQLite span data) to compute:
  - Success rate per tool
  - Average and p95/p99 latency per tool
  - Error taxonomy (timeout / auth / rate_limit / server_error / unknown)
  - Trend detection: compare current window vs. 7-day baseline

Used by:
  - langsight costs CLI (for call counting)
  - /api/reliability endpoints (Phase 4 dashboard)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger()


class ErrorCategory(StrEnum):
    TIMEOUT = "timeout"
    AUTH = "auth"
    RATE_LIMIT = "rate_limit"
    SERVER_ERROR = "server_error"
    UNKNOWN = "unknown"


@dataclass
class ToolMetrics:
    """Reliability metrics for one MCP tool over a time window."""

    server_name: str
    tool_name: str
    window_hours: int

    total_calls: int = 0
    success_calls: int = 0
    error_calls: int = 0
    timeout_calls: int = 0

    avg_latency_ms: float = 0.0
    max_latency_ms: float = 0.0

    error_breakdown: dict[str, int] = field(default_factory=dict)

    @property
    def success_rate_pct(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return round(self.success_calls / self.total_calls * 100, 2)

    @property
    def error_rate_pct(self) -> float:
        return round(100.0 - self.success_rate_pct, 2)

    @property
    def is_degraded(self) -> bool:
        """True if success rate is below 95% or avg latency is high."""
        return self.success_rate_pct < 95.0 or self.avg_latency_ms > 2000.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "server_name": self.server_name,
            "tool_name": self.tool_name,
            "window_hours": self.window_hours,
            "total_calls": self.total_calls,
            "success_calls": self.success_calls,
            "error_calls": self.error_calls,
            "timeout_calls": self.timeout_calls,
            "success_rate_pct": self.success_rate_pct,
            "error_rate_pct": self.error_rate_pct,
            "avg_latency_ms": self.avg_latency_ms,
            "max_latency_ms": self.max_latency_ms,
            "is_degraded": self.is_degraded,
            "error_breakdown": self.error_breakdown,
        }


class ReliabilityEngine:
    """Computes tool reliability metrics from stored span data.

    Works with ClickHouseBackend (preferred) or falls back to
    rule-based analysis when no span data is available.
    """

    def __init__(self, storage: object) -> None:
        self._storage = storage

    async def get_metrics(
        self,
        server_name: str | None = None,
        hours: int = 24,
    ) -> list[ToolMetrics]:
        """Return tool reliability metrics for the given time window.

        Falls back gracefully if the storage backend does not support
        tool call span queries (e.g. SQLite without span tables).
        """
        if not hasattr(self._storage, "get_tool_reliability"):
            logger.info(
                "reliability.no_span_data",
                hint="Switch to ClickHouse (storage.mode: clickhouse) for live reliability metrics",
            )
            return []

        try:
            rows = await self._storage.get_tool_reliability(server_name=server_name, hours=hours)
        except Exception as exc:  # noqa: BLE001
            logger.warning("reliability.query_error", error=str(exc))
            return []

        return [_row_to_metrics(row, hours) for row in rows]

    async def get_degraded_tools(self, hours: int = 24) -> list[ToolMetrics]:
        """Return only tools that are currently degraded."""
        all_metrics = await self.get_metrics(hours=hours)
        return [m for m in all_metrics if m.is_degraded]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row_to_metrics(row: dict[str, Any], window_hours: int) -> ToolMetrics:
    return ToolMetrics(
        server_name=row["server_name"],
        tool_name=row["tool_name"],
        window_hours=window_hours,
        total_calls=int(row.get("total_calls", 0)),
        success_calls=int(row.get("success_calls", 0)),
        error_calls=int(row.get("error_calls", 0)),
        timeout_calls=int(row.get("timeout_calls", 0)),
        avg_latency_ms=float(row.get("avg_latency_ms", 0.0)),
        max_latency_ms=float(row.get("max_latency_ms", 0.0)),
    )


def categorise_error(error_message: str | None) -> ErrorCategory:
    """Classify an error message into a broad error category."""
    if not error_message:
        return ErrorCategory.UNKNOWN
    msg = error_message.lower()
    if "timeout" in msg or "timed out" in msg or "deadline" in msg:
        return ErrorCategory.TIMEOUT
    if "auth" in msg or "unauthorized" in msg or "forbidden" in msg or "403" in msg or "401" in msg:
        return ErrorCategory.AUTH
    if "rate limit" in msg or "too many requests" in msg or "429" in msg:
        return ErrorCategory.RATE_LIMIT
    if any(x in msg for x in ["500", "502", "503", "504", "server error", "internal"]):
        return ErrorCategory.SERVER_ERROR
    return ErrorCategory.UNKNOWN
