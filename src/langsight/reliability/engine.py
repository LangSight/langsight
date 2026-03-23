"""
Tool reliability engine — aggregates tool call spans into reliability metrics.

Queries ClickHouse (or falls back to SQLite span data) to compute:
  - Success rate per tool
  - Average and p95/p99 latency per tool
  - Error taxonomy (timeout / auth / rate_limit / server_error / unknown)
  - Trend detection: compare current window vs. 7-day baseline

P5.4 adds statistical anomaly detection:
  - AnomalyDetector computes per-tool baselines (mean + stddev) from 7-day history
  - Fires AnomalyResult when current value deviates > z_threshold standard deviations
  - Metric types: error_rate, avg_latency_ms

Used by:
  - langsight costs CLI (for call counting)
  - /api/reliability endpoints (Phase 4 dashboard)
  - /api/reliability/anomalies (P5.4)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger()

# Minimum stddev to avoid near-zero division on very stable tools.
# Treats any tool with stddev < this as having this much natural variation.
_MIN_STDDEV_ERROR_RATE = 0.01  # 1% minimum variation
_MIN_STDDEV_LATENCY_MS = 10.0  # 10ms minimum variation


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
        project_id: str | None = None,
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
            rows = await self._storage.get_tool_reliability(
                server_name=server_name, hours=hours, project_id=project_id
            )
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


@dataclass
class AnomalyResult:
    """A detected statistical anomaly for one tool metric."""

    server_name: str
    tool_name: str
    metric: str  # "error_rate" | "avg_latency_ms"
    current_value: float
    baseline_mean: float
    baseline_stddev: float
    z_score: float
    severity: str  # "warning" (z>=2) | "critical" (z>=3)
    sample_hours: int  # how many baseline hours were used

    def to_dict(self) -> dict[str, Any]:
        return {
            "server_name": self.server_name,
            "tool_name": self.tool_name,
            "metric": self.metric,
            "current_value": round(self.current_value, 4),
            "baseline_mean": round(self.baseline_mean, 4),
            "baseline_stddev": round(self.baseline_stddev, 4),
            "z_score": round(self.z_score, 2),
            "severity": self.severity,
            "sample_hours": self.sample_hours,
        }


class AnomalyDetector:
    """Detects statistically unusual tool behaviour using z-score comparison.

    Algorithm:
      1. Fetch 7-day per-tool baseline (mean + stddev) from ClickHouse mv_tool_reliability.
      2. Fetch current window metrics (default: last 1 hour).
      3. For each tool, compute z-score: (current - mean) / stddev.
      4. Return AnomalyResult for any tool where |z_score| >= z_threshold.

    Requires ClickHouse backend. Returns empty list on SQLite.

    Usage:
        detector = AnomalyDetector(storage, z_threshold=2.0)
        anomalies = await detector.detect(current_hours=1, baseline_hours=168)
    """

    def __init__(self, storage: object, z_threshold: float = 2.0) -> None:
        self._storage = storage
        self._z_threshold = z_threshold

    async def detect(
        self,
        current_hours: int = 1,
        baseline_hours: int = 168,
        project_id: str | None = None,
    ) -> list[AnomalyResult]:
        """Run anomaly detection and return a list of detected anomalies."""
        if not hasattr(self._storage, "get_baseline_stats") or not hasattr(
            self._storage, "get_tool_reliability"
        ):
            return []

        try:
            baseline_rows, current_rows = await _gather(
                self._storage.get_baseline_stats(
                    baseline_hours=baseline_hours, project_id=project_id
                ),
                self._storage.get_tool_reliability(hours=current_hours, project_id=project_id),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("anomaly_detector.query_error", error=str(exc))
            return []

        # Index baseline by (server, tool)
        baseline: dict[tuple[str, str], dict[str, Any]] = {
            (r["server_name"], r["tool_name"]): r for r in baseline_rows
        }

        anomalies: list[AnomalyResult] = []
        for row in current_rows:
            key = (row["server_name"], row["tool_name"])
            base = baseline.get(key)
            if base is None:
                continue  # no baseline yet — skip new tools

            total = int(row.get("total_calls") or 0)
            if total == 0:
                continue

            current_error_rate = float(row.get("error_calls", 0)) / total
            current_latency = float(row.get("avg_latency_ms", 0.0))
            sample_hours = int(base.get("sample_hours", 0))

            for metric, current, mean, stddev, min_stddev in [
                (
                    "error_rate",
                    current_error_rate,
                    float(base["baseline_error_mean"]),
                    float(base["baseline_error_stddev"]),
                    _MIN_STDDEV_ERROR_RATE,
                ),
                (
                    "avg_latency_ms",
                    current_latency,
                    float(base["baseline_latency_mean"]),
                    float(base["baseline_latency_stddev"]),
                    _MIN_STDDEV_LATENCY_MS,
                ),
            ]:
                effective_stddev = max(stddev, min_stddev)
                z = (current - mean) / effective_stddev
                if math.isnan(z) or math.isinf(z):
                    continue
                if abs(z) >= self._z_threshold:
                    anomalies.append(
                        AnomalyResult(
                            server_name=row["server_name"],
                            tool_name=row["tool_name"],
                            metric=metric,
                            current_value=current,
                            baseline_mean=mean,
                            baseline_stddev=effective_stddev,
                            z_score=z,
                            severity="critical" if abs(z) >= 3.0 else "warning",
                            sample_hours=sample_hours,
                        )
                    )

        anomalies.sort(key=lambda a: abs(a.z_score), reverse=True)
        logger.info("anomaly_detector.complete", found=len(anomalies))
        return anomalies


class SLOEvaluator:
    """Evaluates AgentSLOs against current session data.

    Queries mv_agent_sessions (ClickHouse) to compute the current value for
    each SLO metric, then compares against the target.

    Metric definitions:
      success_rate: (sessions_with_no_failures / total_sessions) * 100
      latency_p99:  approximated as max(duration_ms) over the window
                    (true p99 requires raw span data — this is a conservative proxy)

    Requires ClickHouse backend. Returns "no_data" status on SQLite.
    """

    def __init__(self, storage: object) -> None:
        self._storage = storage

    async def evaluate_all(self, slos: list[Any], project_id: str | None = None) -> list[Any]:
        """Evaluate all SLOs and return SLOEvaluation results."""
        from langsight.models import SLOEvaluation, SLOMetric

        if not slos:
            return []

        # Gather session data for all unique (agent, window) combinations
        windows: dict[tuple[str, int], dict[str, Any]] = {}
        for slo in slos:
            key = (slo.agent_name, slo.window_hours)
            if key not in windows:
                windows[key] = (
                    await self._fetch_session_stats(
                        slo.agent_name, slo.window_hours, project_id=project_id
                    )
                    or {}
                )

        results = []
        for slo in slos:
            stats = windows[(slo.agent_name, slo.window_hours)]
            current_value: float | None = None
            status = "no_data"

            if stats is not None:
                if slo.metric == SLOMetric.SUCCESS_RATE:
                    total = stats.get("total_sessions", 0)
                    clean = stats.get("clean_sessions", 0)
                    if total > 0:
                        current_value = round(clean / total * 100, 2)
                        status = "ok" if current_value >= slo.target else "breached"
                elif slo.metric == SLOMetric.LATENCY_P99:
                    max_dur = stats.get("max_duration_ms")
                    if max_dur is not None:
                        current_value = float(max_dur)
                        status = "ok" if current_value <= slo.target else "breached"

            results.append(
                SLOEvaluation(
                    slo_id=slo.id,
                    agent_name=slo.agent_name,
                    metric=slo.metric,
                    target=slo.target,
                    current_value=current_value,
                    window_hours=slo.window_hours,
                    status=status,
                )
            )

        return results

    async def _fetch_session_stats(
        self,
        agent_name: str,
        window_hours: int,
        project_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Fetch session summary stats for one agent over a time window."""
        if not hasattr(self._storage, "get_agent_sessions"):
            return None
        try:
            sessions = await self._storage.get_agent_sessions(
                hours=window_hours,
                agent_name=agent_name,
                limit=10_000,
                project_id=project_id,
            )
            if not sessions:
                return None
            total = len(sessions)
            clean = sum(1 for s in sessions if int(s.get("failed_calls") or 0) == 0)
            durations = [
                float(s["duration_ms"]) for s in sessions if s.get("duration_ms") is not None
            ]
            return {
                "total_sessions": total,
                "clean_sessions": clean,
                "max_duration_ms": max(durations) if durations else None,
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("slo_evaluator.fetch_error", agent=agent_name, error=str(exc))
            return None


async def _gather(*coros: Any) -> tuple[Any, ...]:
    """Run coroutines concurrently and return results as a tuple."""
    import asyncio

    return tuple(await asyncio.gather(*coros))


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
