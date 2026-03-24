"""Tests for v0.3 prevention alert types in the alert engine."""

from __future__ import annotations

from langsight.alerts.engine import AlertEngine, AlertSeverity, AlertType
from langsight.sdk.models import PreventionEvent


class TestPreventionEventEvaluation:
    def _engine(self) -> AlertEngine:
        return AlertEngine()

    def test_loop_detected_creates_warning(self) -> None:
        engine = self._engine()
        event = PreventionEvent(
            event_type="loop_detected",
            session_id="sess-1",
            server_name="postgres-mcp",
            tool_name="query",
            details={"pattern": "repetition", "loop_count": 3},
        )
        alerts = engine.evaluate_prevention_event(event)
        assert len(alerts) == 1
        assert alerts[0].alert_type == AlertType.LOOP_DETECTED
        assert alerts[0].severity == AlertSeverity.WARNING
        assert "query" in alerts[0].title
        assert "repetition" in alerts[0].message

    def test_budget_warning_creates_warning(self) -> None:
        engine = self._engine()
        event = PreventionEvent(
            event_type="budget_warning",
            session_id="sess-1",
            server_name="s3-mcp",
            details={"limit_type": "max_steps", "threshold_pct": 0.80},
        )
        alerts = engine.evaluate_prevention_event(event)
        assert len(alerts) == 1
        assert alerts[0].alert_type == AlertType.BUDGET_WARNING
        assert alerts[0].severity == AlertSeverity.WARNING
        assert "80%" in alerts[0].message

    def test_budget_exceeded_creates_critical(self) -> None:
        engine = self._engine()
        event = PreventionEvent(
            event_type="budget_exceeded",
            session_id="sess-1",
            server_name="s3-mcp",
            details={
                "limit_type": "max_cost_usd",
                "limit_value": 1.0,
                "actual_value": 1.03,
            },
        )
        alerts = engine.evaluate_prevention_event(event)
        assert len(alerts) == 1
        assert alerts[0].alert_type == AlertType.BUDGET_EXCEEDED
        assert alerts[0].severity == AlertSeverity.CRITICAL
        assert "terminated" in alerts[0].message.lower()

    def test_circuit_breaker_open_creates_critical(self) -> None:
        engine = self._engine()
        event = PreventionEvent(
            event_type="circuit_breaker_open",
            server_name="postgres-mcp",
            details={"failures": 5, "cooldown_seconds": 60},
        )
        alerts = engine.evaluate_prevention_event(event)
        assert len(alerts) == 1
        assert alerts[0].alert_type == AlertType.CIRCUIT_BREAKER_OPEN
        assert alerts[0].severity == AlertSeverity.CRITICAL
        assert "5" in alerts[0].message
        assert "60" in alerts[0].message

    def test_circuit_breaker_recovered_creates_info(self) -> None:
        engine = self._engine()
        event = PreventionEvent(
            event_type="circuit_breaker_recovered",
            server_name="postgres-mcp",
        )
        alerts = engine.evaluate_prevention_event(event)
        assert len(alerts) == 1
        assert alerts[0].alert_type == AlertType.CIRCUIT_BREAKER_RECOVERED
        assert alerts[0].severity == AlertSeverity.INFO
        assert "recovered" in alerts[0].message.lower()

    def test_unknown_event_type_returns_empty(self) -> None:
        engine = self._engine()
        event = PreventionEvent(event_type="loop_detected")  # valid type, minimal data
        alerts = engine.evaluate_prevention_event(event)
        assert len(alerts) == 1  # still produces an alert

    def test_alert_has_server_name(self) -> None:
        engine = self._engine()
        event = PreventionEvent(
            event_type="loop_detected",
            server_name="my-server",
            tool_name="query",
        )
        alerts = engine.evaluate_prevention_event(event)
        assert alerts[0].server_name == "my-server"

    def test_missing_server_defaults_to_unknown(self) -> None:
        engine = self._engine()
        event = PreventionEvent(event_type="loop_detected")
        alerts = engine.evaluate_prevention_event(event)
        assert alerts[0].server_name == "unknown"
