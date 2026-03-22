"""
Unit tests for AlertType and AlertSeverity enum completeness.

Verifies that all 13 AlertType values exist (4 original + 4 agent-level
+ 5 v0.3 prevention) and that AlertSeverity retains its full set of values.
"""

from __future__ import annotations

import pytest

from langsight.alerts.engine import AlertSeverity, AlertType


class TestAlertTypeEnum:
    def test_all_alert_type_values_exist(self) -> None:
        expected = {
            "server_down",
            "server_recovered",
            "schema_drift",
            "high_latency",
            "agent_failure",
            "slo_breached",
            "anomaly_detected",
            "security_finding",
            # v0.3 prevention layer
            "loop_detected",
            "budget_warning",
            "budget_exceeded",
            "circuit_breaker_open",
            "circuit_breaker_recovered",
        }
        actual = {member.value for member in AlertType}
        assert actual == expected

    def test_alert_type_has_exactly_thirteen_members(self) -> None:
        assert len(AlertType) == 13

    # Original four members
    def test_server_down_value(self) -> None:
        assert AlertType.SERVER_DOWN == "server_down"

    def test_server_recovered_value(self) -> None:
        assert AlertType.SERVER_RECOVERED == "server_recovered"

    def test_schema_drift_value(self) -> None:
        assert AlertType.SCHEMA_DRIFT == "schema_drift"

    def test_high_latency_value(self) -> None:
        assert AlertType.HIGH_LATENCY == "high_latency"

    # New four agent-level members
    def test_agent_failure_value(self) -> None:
        assert AlertType.AGENT_FAILURE == "agent_failure"

    def test_slo_breached_value(self) -> None:
        assert AlertType.SLO_BREACHED == "slo_breached"

    def test_anomaly_detected_value(self) -> None:
        assert AlertType.ANOMALY_DETECTED == "anomaly_detected"

    def test_security_finding_value(self) -> None:
        assert AlertType.SECURITY_FINDING == "security_finding"

    def test_alert_type_is_str_enum(self) -> None:
        """AlertType members must be usable directly as strings."""
        assert AlertType.AGENT_FAILURE == "agent_failure"
        assert isinstance(AlertType.AGENT_FAILURE, str)

    @pytest.mark.parametrize(
        "name, expected_value",
        [
            ("AGENT_FAILURE",    "agent_failure"),
            ("SLO_BREACHED",     "slo_breached"),
            ("ANOMALY_DETECTED", "anomaly_detected"),
            ("SECURITY_FINDING", "security_finding"),
        ],
    )
    def test_new_types_accessible_by_name(self, name: str, expected_value: str) -> None:
        member = AlertType[name]
        assert member.value == expected_value


class TestAlertSeverityEnum:
    def test_critical_severity_exists(self) -> None:
        assert AlertSeverity.CRITICAL == "critical"

    def test_warning_severity_exists(self) -> None:
        assert AlertSeverity.WARNING == "warning"

    def test_info_severity_exists(self) -> None:
        assert AlertSeverity.INFO == "info"

    def test_has_exactly_three_members(self) -> None:
        assert len(AlertSeverity) == 3

    def test_alert_severity_is_str_enum(self) -> None:
        assert isinstance(AlertSeverity.CRITICAL, str)
