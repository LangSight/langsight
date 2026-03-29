"""
Alert engine — fires alerts on state transitions, not on every check.

Design principles:
- Alert on UP→DOWN transition, not on every DOWN result (no storm)
- Alert on DOWN→UP recovery (server back online)
- Alert on schema drift (DEGRADED state)
- Deduplicate: same server + same issue = one alert until resolved
- Configurable consecutive-failures threshold before alerting
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING

import structlog

from langsight.models import HealthCheckResult, ServerStatus
from langsight.sdk.models import PreventionEvent

if TYPE_CHECKING:
    from langsight.storage.base import StorageBackend

logger = structlog.get_logger()


class AlertSeverity(StrEnum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class AlertType(StrEnum):
    SERVER_DOWN = "server_down"
    SERVER_RECOVERED = "server_recovered"
    SCHEMA_DRIFT = "schema_drift"
    HIGH_LATENCY = "high_latency"
    # Agent-level alerts (fired from session data, not health checks)
    AGENT_FAILURE = "agent_failure"
    SLO_BREACHED = "slo_breached"
    ANOMALY_DETECTED = "anomaly_detected"
    SECURITY_FINDING = "security_finding"
    # v0.3 Prevention layer alerts
    LOOP_DETECTED = "loop_detected"
    BUDGET_WARNING = "budget_warning"
    BUDGET_EXCEEDED = "budget_exceeded"
    CIRCUIT_BREAKER_OPEN = "circuit_breaker_open"
    CIRCUIT_BREAKER_RECOVERED = "circuit_breaker_recovered"


@dataclass(frozen=True)
class Alert:
    """A fired alert — represents a state transition event."""

    server_name: str
    alert_type: AlertType
    severity: AlertSeverity
    title: str
    message: str
    fired_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    context_url: str | None = None  # deep-link into the dashboard (session, server, etc.)


@dataclass
class _ServerState:
    """Tracks the last-known state for one server."""

    last_status: ServerStatus | None = None
    consecutive_failures: int = 0
    schema_hash: str | None = None
    baseline_latency_ms: float | None = None
    alerted_down: bool = False
    alerted_drift: bool = False


class AlertEngine:
    """Evaluates health check results and fires alerts on state transitions.

    Args:
        consecutive_failures_threshold: Number of consecutive DOWN results
            required before firing a SERVER_DOWN alert (default: 2).
        latency_spike_multiplier: Multiplier over baseline latency that
            triggers a HIGH_LATENCY alert (default: 3.0).
    """

    def __init__(
        self,
        consecutive_failures_threshold: int = 2,
        latency_spike_multiplier: float = 3.0,
        storage: StorageBackend | None = None,
        project_id: str = "",
    ) -> None:
        self._threshold = consecutive_failures_threshold
        self._latency_multiplier = latency_spike_multiplier
        self._states: dict[str, _ServerState] = {}
        self._storage = storage
        self._project_id = project_id

    def seed_from_history(self, history: list[HealthCheckResult]) -> None:
        """Seed baseline state from recent health check history.

        Call on startup with the last N results per server to restore
        baseline_latency and consecutive_failures, so the first checks
        after restart don't lose alert context.
        """
        for result in history:
            state = self._states.setdefault(result.server_name, _ServerState())
            state.last_status = result.status
            if result.status == ServerStatus.UP and result.latency_ms:
                if state.baseline_latency_ms is None:
                    state.baseline_latency_ms = result.latency_ms
                else:
                    state.baseline_latency_ms = (
                        state.baseline_latency_ms * 0.9 + result.latency_ms * 0.1
                    )
                state.consecutive_failures = 0
            elif result.status == ServerStatus.DOWN:
                state.consecutive_failures += 1

    async def _persist_alerts(self, alerts: list[Alert], session_id: str | None = None) -> None:
        """Fire-and-forget persist to storage — never raises."""
        if not self._storage or not alerts:
            return
        for alert in alerts:
            try:
                await self._storage.save_fired_alert(
                    alert_id=uuid.uuid4().hex,
                    alert_type=alert.alert_type.value,
                    severity=alert.severity.value,
                    server_name=alert.server_name,
                    title=alert.title,
                    message=alert.message,
                    session_id=session_id,
                    project_id=self._project_id,
                )
            except Exception:  # noqa: BLE001
                pass  # Never let storage errors block alert delivery

    def evaluate(self, result: HealthCheckResult) -> list[Alert]:
        """Evaluate a health check result and return any new alerts to fire.

        Called after every health check. Returns a list of Alert objects
        (empty if no state transition occurred).
        """
        state = self._states.setdefault(result.server_name, _ServerState())
        alerts: list[Alert] = []

        alerts.extend(self._check_down(result, state))
        alerts.extend(self._check_recovery(result, state))
        alerts.extend(self._check_schema_drift(result, state))
        alerts.extend(self._check_latency(result, state))

        # Update state
        state.last_status = result.status
        if result.status == ServerStatus.UP:
            state.consecutive_failures = 0
            state.alerted_down = False
            if result.latency_ms and state.baseline_latency_ms is None:
                state.baseline_latency_ms = result.latency_ms
            elif result.latency_ms and state.baseline_latency_ms:
                # Rolling average — weight new value lightly
                state.baseline_latency_ms = (
                    state.baseline_latency_ms * 0.9 + result.latency_ms * 0.1
                )
        elif result.status == ServerStatus.DOWN:
            state.consecutive_failures += 1
        elif result.status == ServerStatus.DEGRADED:
            state.schema_hash = result.schema_hash

        return alerts

    def evaluate_many(self, results: list[HealthCheckResult]) -> list[Alert]:
        """Evaluate multiple health check results and return all new alerts.

        Results are processed in order — the sequence matters because each
        result updates the server's state (consecutive_failures, baseline).
        Sort results by server_name for deterministic behavior when the
        input order is undefined (e.g., asyncio.gather results).

        Not thread-safe — designed for single-threaded monitor loop.
        """
        alerts: list[Alert] = []
        for result in sorted(results, key=lambda r: r.server_name):
            alerts.extend(self.evaluate(result))
        return alerts

    # ---------------------------------------------------------------------------
    # v0.3 Prevention event evaluation
    # ---------------------------------------------------------------------------

    _EVENT_TO_ALERT: dict[str, tuple[AlertType, AlertSeverity]] = {
        "loop_detected": (AlertType.LOOP_DETECTED, AlertSeverity.WARNING),
        "budget_warning": (AlertType.BUDGET_WARNING, AlertSeverity.WARNING),
        "budget_exceeded": (AlertType.BUDGET_EXCEEDED, AlertSeverity.CRITICAL),
        "circuit_breaker_open": (AlertType.CIRCUIT_BREAKER_OPEN, AlertSeverity.CRITICAL),
        "circuit_breaker_recovered": (AlertType.CIRCUIT_BREAKER_RECOVERED, AlertSeverity.INFO),
    }

    def evaluate_prevention_event(self, event: PreventionEvent) -> list[Alert]:
        """Create alerts from SDK prevention events (loop, budget, circuit breaker).

        Unlike health-check evaluation, prevention events always produce an alert
        (they are already significant events — no threshold needed).
        """
        mapping = self._EVENT_TO_ALERT.get(event.event_type)
        if mapping is None:
            return []

        alert_type, severity = mapping
        server = event.server_name or "unknown"
        tool = event.tool_name or "unknown"
        session = event.session_id or "unknown"
        details = event.details

        title = self._prevention_title(event.event_type, server, tool)
        message = self._prevention_message(event.event_type, server, tool, session, details)

        logger.info(
            "alert_engine.prevention_event",
            event_type=event.event_type,
            server=server,
            tool=tool,
            session=session,
        )
        return [
            Alert(
                server_name=server,
                alert_type=alert_type,
                severity=severity,
                title=title,
                message=message,
            )
        ]

    @staticmethod
    def _prevention_title(event_type: str, server: str, tool: str) -> str:
        titles = {
            "loop_detected": f"Loop detected: '{tool}' on '{server}'",
            "budget_warning": f"Budget warning for session on '{server}'",
            "budget_exceeded": f"Budget exceeded for session on '{server}'",
            "circuit_breaker_open": f"Circuit breaker OPEN: '{server}' disabled",
            "circuit_breaker_recovered": f"Circuit breaker recovered: '{server}'",
        }
        return titles.get(event_type, f"Prevention event: {event_type}")

    @staticmethod
    def _prevention_message(
        event_type: str,
        server: str,
        tool: str,
        session: str,
        details: dict[str, object],
    ) -> str:
        if event_type == "loop_detected":
            pattern = details.get("pattern", "unknown")
            count = details.get("loop_count", "?")
            return (
                f"Agent loop detected on '{server}': tool '{tool}' "
                f"triggered {pattern} pattern ({count} repetitions). "
                f"Session: {session}"
            )
        if event_type == "budget_warning":
            limit = details.get("limit_type", "unknown")
            pct = details.get("threshold_pct", 0.8)
            return (
                f"Session on '{server}' has reached {pct:.0%} of {limit} budget. Session: {session}"
            )
        if event_type == "budget_exceeded":
            limit = details.get("limit_type", "unknown")
            value = details.get("actual_value", "?")
            cap = details.get("limit_value", "?")
            return (
                f"Session on '{server}' exceeded {limit} budget: "
                f"{value} (limit: {cap}). Session terminated. "
                f"Session: {session}"
            )
        if event_type == "circuit_breaker_open":
            failures = details.get("failures", "?")
            cooldown = details.get("cooldown_seconds", "?")
            return (
                f"Circuit breaker opened for '{server}' after {failures} "
                f"consecutive failures. Auto-recovery in {cooldown}s."
            )
        if event_type == "circuit_breaker_recovered":
            return f"Circuit breaker closed for '{server}'. Server recovered."
        return f"Prevention event: {event_type} on '{server}'"

    # ---------------------------------------------------------------------------
    # Private check methods
    # ---------------------------------------------------------------------------

    def _check_down(self, result: HealthCheckResult, state: _ServerState) -> list[Alert]:
        if result.status != ServerStatus.DOWN:
            return []

        new_failures = state.consecutive_failures + 1
        if new_failures < self._threshold or state.alerted_down:
            return []

        state.alerted_down = True
        logger.warning(
            "alert_engine.server_down",
            server=result.server_name,
            consecutive_failures=new_failures,
        )
        return [
            Alert(
                server_name=result.server_name,
                alert_type=AlertType.SERVER_DOWN,
                severity=AlertSeverity.CRITICAL,
                title=f"MCP server '{result.server_name}' is DOWN",
                message=(
                    f"Server '{result.server_name}' has been unreachable for "
                    f"{new_failures} consecutive checks. "
                    f"Error: {result.error or 'unknown'}"
                ),
            )
        ]

    def _check_recovery(self, result: HealthCheckResult, state: _ServerState) -> list[Alert]:
        if result.status != ServerStatus.UP:
            return []
        if state.last_status not in (ServerStatus.DOWN, ServerStatus.DEGRADED):
            return []
        if not state.alerted_down and state.last_status != ServerStatus.DEGRADED:
            return []

        logger.info("alert_engine.server_recovered", server=result.server_name)
        return [
            Alert(
                server_name=result.server_name,
                alert_type=AlertType.SERVER_RECOVERED,
                severity=AlertSeverity.INFO,
                title=f"MCP server '{result.server_name}' recovered",
                message=(
                    f"Server '{result.server_name}' is back online. "
                    f"Latency: {result.latency_ms:.0f}ms, tools: {result.tools_count}"
                ),
            )
        ]

    def _check_schema_drift(self, result: HealthCheckResult, state: _ServerState) -> list[Alert]:
        if result.status != ServerStatus.DEGRADED:
            return []
        if not result.error or "schema drift" not in result.error:
            return []
        if state.alerted_drift and state.schema_hash == result.schema_hash:
            return []

        state.alerted_drift = True
        logger.warning("alert_engine.schema_drift", server=result.server_name)
        return [
            Alert(
                server_name=result.server_name,
                alert_type=AlertType.SCHEMA_DRIFT,
                severity=AlertSeverity.WARNING,
                title=f"Schema drift detected on '{result.server_name}'",
                message=(
                    f"Tool schema changed on server '{result.server_name}'. "
                    f"Details: {result.error}. "
                    f"Verify this was an intentional deployment."
                ),
            )
        ]

    def _check_latency(self, result: HealthCheckResult, state: _ServerState) -> list[Alert]:
        if result.status != ServerStatus.UP:
            return []
        if result.latency_ms is None or state.baseline_latency_ms is None:
            return []
        if result.latency_ms < state.baseline_latency_ms * self._latency_multiplier:
            return []

        logger.warning(
            "alert_engine.high_latency",
            server=result.server_name,
            latency_ms=result.latency_ms,
            baseline_ms=state.baseline_latency_ms,
        )
        return [
            Alert(
                server_name=result.server_name,
                alert_type=AlertType.HIGH_LATENCY,
                severity=AlertSeverity.WARNING,
                title=f"High latency on '{result.server_name}'",
                message=(
                    f"Server '{result.server_name}' latency is {result.latency_ms:.0f}ms — "
                    f"{result.latency_ms / state.baseline_latency_ms:.1f}x baseline "
                    f"({state.baseline_latency_ms:.0f}ms)."
                ),
            )
        ]
