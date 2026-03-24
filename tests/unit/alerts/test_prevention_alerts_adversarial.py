"""Adversarial and edge-case tests for prevention alert evaluation.

Tests: unknown event types, missing fields, duplicate events, empty details,
and interaction with existing health-check-based alerting.
"""

from __future__ import annotations

from langsight.alerts.engine import AlertEngine, AlertSeverity, AlertType
from langsight.sdk.models import PreventionEvent


class TestUnknownEventType:
    def test_truly_unknown_type_is_rejected_by_pydantic(self) -> None:
        """PreventionEvent has a Literal type constraint — unknown types are rejected."""
        import pydantic
        import pytest

        with pytest.raises(pydantic.ValidationError):
            PreventionEvent(event_type="unknown_type")

    def test_all_valid_event_types_produce_alerts(self) -> None:
        """Verify every valid event_type produces exactly one alert."""
        engine = AlertEngine()
        valid_types = [
            "loop_detected",
            "budget_warning",
            "budget_exceeded",
            "circuit_breaker_open",
            "circuit_breaker_recovered",
        ]
        for event_type in valid_types:
            event = PreventionEvent(event_type=event_type)
            alerts = engine.evaluate_prevention_event(event)
            assert len(alerts) == 1, f"{event_type} should produce exactly 1 alert"


class TestMissingFields:
    def test_no_server_name_defaults_to_unknown(self) -> None:
        engine = AlertEngine()
        event = PreventionEvent(
            event_type="loop_detected",
            tool_name="query",
        )
        alerts = engine.evaluate_prevention_event(event)
        assert alerts[0].server_name == "unknown"

    def test_no_tool_name_defaults_to_unknown(self) -> None:
        engine = AlertEngine()
        event = PreventionEvent(
            event_type="loop_detected",
            server_name="my-server",
        )
        alerts = engine.evaluate_prevention_event(event)
        assert "unknown" in alerts[0].title  # tool_name default

    def test_no_session_id_uses_unknown_in_message(self) -> None:
        engine = AlertEngine()
        event = PreventionEvent(
            event_type="loop_detected",
            server_name="srv",
            tool_name="query",
            details={"pattern": "repetition", "loop_count": 3},
        )
        alerts = engine.evaluate_prevention_event(event)
        assert "unknown" in alerts[0].message  # session "unknown"

    def test_empty_details_dict(self) -> None:
        """Empty details should not crash — fields use .get() with defaults."""
        engine = AlertEngine()
        event = PreventionEvent(
            event_type="budget_exceeded",
            server_name="srv",
            details={},
        )
        alerts = engine.evaluate_prevention_event(event)
        assert len(alerts) == 1
        # Check that default values are used
        assert "unknown" in alerts[0].message  # limit_type default

    def test_all_fields_none(self) -> None:
        """Minimal event with just event_type."""
        engine = AlertEngine()
        event = PreventionEvent(event_type="circuit_breaker_recovered")
        alerts = engine.evaluate_prevention_event(event)
        assert len(alerts) == 1
        assert alerts[0].server_name == "unknown"
        assert "recovered" in alerts[0].message.lower()


class TestDuplicateEvents:
    """Prevention events always produce alerts (no deduplication).
    This is by design: prevention events are already significant.
    """

    def test_same_event_twice_produces_two_alerts(self) -> None:
        engine = AlertEngine()
        event = PreventionEvent(
            event_type="loop_detected",
            server_name="srv",
            tool_name="query",
            session_id="sess-1",
        )
        alerts1 = engine.evaluate_prevention_event(event)
        alerts2 = engine.evaluate_prevention_event(event)
        assert len(alerts1) == 1
        assert len(alerts2) == 1

    def test_many_identical_events(self) -> None:
        engine = AlertEngine()
        event = PreventionEvent(
            event_type="budget_warning",
            server_name="srv",
            details={"limit_type": "max_steps", "threshold_pct": 0.8},
        )
        all_alerts = []
        for _ in range(100):
            all_alerts.extend(engine.evaluate_prevention_event(event))
        assert len(all_alerts) == 100


class TestAlertSeverityMapping:
    def test_loop_detected_is_warning(self) -> None:
        engine = AlertEngine()
        event = PreventionEvent(event_type="loop_detected")
        alerts = engine.evaluate_prevention_event(event)
        assert alerts[0].severity == AlertSeverity.WARNING

    def test_budget_warning_is_warning(self) -> None:
        engine = AlertEngine()
        event = PreventionEvent(event_type="budget_warning")
        alerts = engine.evaluate_prevention_event(event)
        assert alerts[0].severity == AlertSeverity.WARNING

    def test_budget_exceeded_is_critical(self) -> None:
        engine = AlertEngine()
        event = PreventionEvent(event_type="budget_exceeded")
        alerts = engine.evaluate_prevention_event(event)
        assert alerts[0].severity == AlertSeverity.CRITICAL

    def test_circuit_breaker_open_is_critical(self) -> None:
        engine = AlertEngine()
        event = PreventionEvent(event_type="circuit_breaker_open")
        alerts = engine.evaluate_prevention_event(event)
        assert alerts[0].severity == AlertSeverity.CRITICAL

    def test_circuit_breaker_recovered_is_info(self) -> None:
        engine = AlertEngine()
        event = PreventionEvent(event_type="circuit_breaker_recovered")
        alerts = engine.evaluate_prevention_event(event)
        assert alerts[0].severity == AlertSeverity.INFO


class TestAlertTypeMapping:
    def test_correct_alert_type_for_each_event(self) -> None:
        engine = AlertEngine()
        expected = {
            "loop_detected": AlertType.LOOP_DETECTED,
            "budget_warning": AlertType.BUDGET_WARNING,
            "budget_exceeded": AlertType.BUDGET_EXCEEDED,
            "circuit_breaker_open": AlertType.CIRCUIT_BREAKER_OPEN,
            "circuit_breaker_recovered": AlertType.CIRCUIT_BREAKER_RECOVERED,
        }
        for event_type, expected_alert_type in expected.items():
            event = PreventionEvent(event_type=event_type)
            alerts = engine.evaluate_prevention_event(event)
            assert alerts[0].alert_type == expected_alert_type


class TestMessageContent:
    def test_loop_message_includes_pattern(self) -> None:
        engine = AlertEngine()
        event = PreventionEvent(
            event_type="loop_detected",
            server_name="pg-mcp",
            tool_name="query",
            session_id="sess-42",
            details={"pattern": "ping_pong", "loop_count": 5},
        )
        alerts = engine.evaluate_prevention_event(event)
        msg = alerts[0].message
        assert "ping_pong" in msg
        assert "5" in msg
        assert "sess-42" in msg
        assert "pg-mcp" in msg

    def test_budget_warning_message_includes_percentage(self) -> None:
        engine = AlertEngine()
        event = PreventionEvent(
            event_type="budget_warning",
            server_name="srv",
            session_id="sess-1",
            details={"limit_type": "max_cost_usd", "threshold_pct": 0.80},
        )
        alerts = engine.evaluate_prevention_event(event)
        msg = alerts[0].message
        assert "80%" in msg
        assert "max_cost_usd" in msg

    def test_budget_exceeded_message_includes_values(self) -> None:
        engine = AlertEngine()
        event = PreventionEvent(
            event_type="budget_exceeded",
            server_name="srv",
            details={
                "limit_type": "max_steps",
                "limit_value": 25,
                "actual_value": 26,
            },
        )
        alerts = engine.evaluate_prevention_event(event)
        msg = alerts[0].message
        assert "25" in msg
        assert "26" in msg
        assert "terminated" in msg.lower()

    def test_circuit_breaker_open_message_includes_failures_and_cooldown(self) -> None:
        engine = AlertEngine()
        event = PreventionEvent(
            event_type="circuit_breaker_open",
            server_name="db-mcp",
            details={"failures": 10, "cooldown_seconds": 120},
        )
        alerts = engine.evaluate_prevention_event(event)
        msg = alerts[0].message
        assert "10" in msg
        assert "120" in msg
        assert "db-mcp" in msg

    def test_circuit_breaker_recovered_message(self) -> None:
        engine = AlertEngine()
        event = PreventionEvent(
            event_type="circuit_breaker_recovered",
            server_name="db-mcp",
        )
        alerts = engine.evaluate_prevention_event(event)
        msg = alerts[0].message
        assert "db-mcp" in msg
        assert "recovered" in msg.lower()


class TestTitleContent:
    def test_loop_title_contains_tool_and_server(self) -> None:
        engine = AlertEngine()
        event = PreventionEvent(
            event_type="loop_detected",
            server_name="pg-mcp",
            tool_name="query",
        )
        alerts = engine.evaluate_prevention_event(event)
        title = alerts[0].title
        assert "query" in title
        assert "pg-mcp" in title
        assert "Loop" in title

    def test_circuit_breaker_open_title_contains_server(self) -> None:
        engine = AlertEngine()
        event = PreventionEvent(
            event_type="circuit_breaker_open",
            server_name="redis-mcp",
        )
        alerts = engine.evaluate_prevention_event(event)
        assert "redis-mcp" in alerts[0].title
        assert "OPEN" in alerts[0].title


class TestPreventionEventInteractionWithHealthCheckAlerts:
    """Prevention events and health check evaluations use different methods
    on AlertEngine. Verify they don't interfere with each other's state.
    """

    def test_prevention_events_dont_affect_health_check_state(self) -> None:
        from langsight.models import HealthCheckResult, ServerStatus

        engine = AlertEngine()

        # Fire a prevention event
        event = PreventionEvent(
            event_type="circuit_breaker_open",
            server_name="srv",
        )
        engine.evaluate_prevention_event(event)

        # Health check state for "srv" should be unaffected
        result = HealthCheckResult(
            server_name="srv",
            status=ServerStatus.UP,
            latency_ms=50.0,
            tools_count=5,
        )
        alerts = engine.evaluate(result)
        # First UP check should not produce DOWN or recovery alerts
        down_alerts = [a for a in alerts if a.alert_type == AlertType.SERVER_DOWN]
        assert len(down_alerts) == 0

    def test_health_check_state_does_not_affect_prevention(self) -> None:
        from langsight.models import HealthCheckResult, ServerStatus

        engine = AlertEngine(consecutive_failures_threshold=1)

        # Create DOWN state via health checks
        down_result = HealthCheckResult(
            server_name="srv",
            status=ServerStatus.DOWN,
            latency_ms=None,
            tools_count=0,
            error="unreachable",
        )
        engine.evaluate(down_result)

        # Prevention event should still produce its alert independently
        event = PreventionEvent(
            event_type="loop_detected",
            server_name="srv",
            tool_name="query",
        )
        alerts = engine.evaluate_prevention_event(event)
        assert len(alerts) == 1
        assert alerts[0].alert_type == AlertType.LOOP_DETECTED
