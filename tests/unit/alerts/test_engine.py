from __future__ import annotations

import pytest

from langsight.alerts.engine import Alert, AlertEngine, AlertSeverity, AlertType
from langsight.models import HealthCheckResult, ServerStatus


def _result(
    name: str = "srv",
    status: ServerStatus = ServerStatus.UP,
    latency_ms: float | None = 100.0,
    error: str | None = None,
    schema_hash: str | None = "abc123",
    tools_count: int = 5,
) -> HealthCheckResult:
    return HealthCheckResult(
        server_name=name,
        status=status,
        latency_ms=latency_ms,
        error=error,
        schema_hash=schema_hash,
        tools_count=tools_count,
    )


@pytest.fixture
def engine() -> AlertEngine:
    return AlertEngine(consecutive_failures_threshold=2)


class TestServerDown:
    def test_no_alert_on_first_failure(self, engine: AlertEngine) -> None:
        alerts = engine.evaluate(_result(status=ServerStatus.DOWN))
        assert alerts == []

    def test_alert_on_threshold_reached(self, engine: AlertEngine) -> None:
        engine.evaluate(_result(status=ServerStatus.DOWN))
        alerts = engine.evaluate(_result(status=ServerStatus.DOWN))
        assert len(alerts) == 1
        assert alerts[0].alert_type == AlertType.SERVER_DOWN
        assert alerts[0].severity == AlertSeverity.CRITICAL

    def test_no_duplicate_alert_when_stays_down(self, engine: AlertEngine) -> None:
        engine.evaluate(_result(status=ServerStatus.DOWN))
        engine.evaluate(_result(status=ServerStatus.DOWN))  # fires alert
        alerts = engine.evaluate(_result(status=ServerStatus.DOWN))  # no duplicate
        assert alerts == []

    def test_alert_message_contains_server_name(self, engine: AlertEngine) -> None:
        engine.evaluate(_result(name="pg", status=ServerStatus.DOWN))
        alerts = engine.evaluate(_result(name="pg", status=ServerStatus.DOWN))
        assert "pg" in alerts[0].title
        assert "pg" in alerts[0].message

    def test_alert_message_contains_error(self, engine: AlertEngine) -> None:
        engine.evaluate(_result(status=ServerStatus.DOWN, error="connection refused"))
        alerts = engine.evaluate(_result(status=ServerStatus.DOWN, error="connection refused"))
        assert "connection refused" in alerts[0].message

    def test_threshold_1_alerts_on_first_failure(self) -> None:
        engine = AlertEngine(consecutive_failures_threshold=1)
        alerts = engine.evaluate(_result(status=ServerStatus.DOWN))
        assert len(alerts) == 1

    def test_failure_counter_resets_after_recovery(self, engine: AlertEngine) -> None:
        engine.evaluate(_result(status=ServerStatus.DOWN))
        engine.evaluate(_result(status=ServerStatus.UP))   # reset
        engine.evaluate(_result(status=ServerStatus.DOWN))
        alerts = engine.evaluate(_result(status=ServerStatus.DOWN))  # should fire again
        assert any(a.alert_type == AlertType.SERVER_DOWN for a in alerts)


class TestServerRecovery:
    def test_alert_on_recovery_after_down_alert(self, engine: AlertEngine) -> None:
        engine.evaluate(_result(status=ServerStatus.DOWN))
        engine.evaluate(_result(status=ServerStatus.DOWN))  # fires DOWN alert
        alerts = engine.evaluate(_result(status=ServerStatus.UP))
        assert any(a.alert_type == AlertType.SERVER_RECOVERED for a in alerts)

    def test_no_recovery_alert_if_never_alerted_down(self, engine: AlertEngine) -> None:
        # Only one failure — never reached threshold, no DOWN alert
        engine.evaluate(_result(status=ServerStatus.DOWN))
        alerts = engine.evaluate(_result(status=ServerStatus.UP))
        assert not any(a.alert_type == AlertType.SERVER_RECOVERED for a in alerts)

    def test_recovery_alert_is_info_severity(self, engine: AlertEngine) -> None:
        engine.evaluate(_result(status=ServerStatus.DOWN))
        engine.evaluate(_result(status=ServerStatus.DOWN))
        alerts = engine.evaluate(_result(status=ServerStatus.UP))
        recovery = next(a for a in alerts if a.alert_type == AlertType.SERVER_RECOVERED)
        assert recovery.severity == AlertSeverity.INFO

    def test_no_duplicate_recovery_alert(self, engine: AlertEngine) -> None:
        engine.evaluate(_result(status=ServerStatus.DOWN))
        engine.evaluate(_result(status=ServerStatus.DOWN))
        engine.evaluate(_result(status=ServerStatus.UP))  # recovery
        alerts = engine.evaluate(_result(status=ServerStatus.UP))
        assert not any(a.alert_type == AlertType.SERVER_RECOVERED for a in alerts)


class TestSchemaDrift:
    def test_alert_on_schema_drift(self, engine: AlertEngine) -> None:
        alerts = engine.evaluate(_result(
            status=ServerStatus.DEGRADED,
            error="schema drift: abc123 → def456",
            schema_hash="def456",
        ))
        assert any(a.alert_type == AlertType.SCHEMA_DRIFT for a in alerts)
        assert any(a.severity == AlertSeverity.WARNING for a in alerts)

    def test_no_duplicate_drift_alert_same_hash(self, engine: AlertEngine) -> None:
        engine.evaluate(_result(
            status=ServerStatus.DEGRADED,
            error="schema drift: abc → def",
            schema_hash="def456",
        ))
        alerts = engine.evaluate(_result(
            status=ServerStatus.DEGRADED,
            error="schema drift: abc → def",
            schema_hash="def456",
        ))
        assert not any(a.alert_type == AlertType.SCHEMA_DRIFT for a in alerts)

    def test_no_drift_alert_without_drift_error(self, engine: AlertEngine) -> None:
        alerts = engine.evaluate(_result(
            status=ServerStatus.DEGRADED,
            error="connection timeout",
        ))
        assert not any(a.alert_type == AlertType.SCHEMA_DRIFT for a in alerts)


class TestHighLatency:
    def test_alert_on_latency_spike(self) -> None:
        engine = AlertEngine(latency_spike_multiplier=3.0)
        # Establish baseline
        engine.evaluate(_result(latency_ms=100.0))
        # Spike
        alerts = engine.evaluate(_result(latency_ms=400.0))
        assert any(a.alert_type == AlertType.HIGH_LATENCY for a in alerts)

    def test_no_alert_below_threshold(self) -> None:
        engine = AlertEngine(latency_spike_multiplier=3.0)
        engine.evaluate(_result(latency_ms=100.0))
        alerts = engine.evaluate(_result(latency_ms=250.0))
        assert not any(a.alert_type == AlertType.HIGH_LATENCY for a in alerts)

    def test_no_alert_without_baseline(self, engine: AlertEngine) -> None:
        # First result — no baseline yet
        alerts = engine.evaluate(_result(latency_ms=9999.0))
        assert not any(a.alert_type == AlertType.HIGH_LATENCY for a in alerts)


class TestEvaluateMany:
    def test_returns_all_alerts(self, engine: AlertEngine) -> None:
        results = [
            _result("s1", status=ServerStatus.DOWN),
            _result("s1", status=ServerStatus.DOWN),  # alert fires
            _result("s2", status=ServerStatus.DOWN),
            _result("s2", status=ServerStatus.DOWN),  # alert fires
        ]
        all_alerts: list[Alert] = []
        for r in results:
            all_alerts.extend(engine.evaluate(r))
        assert len(all_alerts) == 2
        assert {a.server_name for a in all_alerts} == {"s1", "s2"}

    def test_evaluate_many_helper(self, engine: AlertEngine) -> None:
        results = [
            _result("s1", status=ServerStatus.DOWN),
            _result("s1", status=ServerStatus.DOWN),
        ]
        alerts = engine.evaluate_many(results)
        assert len(alerts) == 1
