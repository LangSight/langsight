from __future__ import annotations

from langsight.security.models import ScanResult, SecurityFinding, Severity


def _finding(severity: Severity, title: str = "Test") -> SecurityFinding:
    return SecurityFinding(
        server_name="srv",
        severity=severity,
        category="TEST",
        title=title,
        description="desc",
        remediation="fix it",
    )


class TestSeverityOrdering:
    def test_critical_higher_than_high(self) -> None:
        findings = [_finding(Severity.HIGH), _finding(Severity.CRITICAL)]
        result = ScanResult(server_name="srv", findings=findings)
        sorted_findings = result.findings_by_severity()
        assert sorted_findings[0].severity == Severity.CRITICAL

    def test_all_severities_sorted(self) -> None:
        severities = [Severity.LOW, Severity.CRITICAL, Severity.INFO, Severity.HIGH, Severity.MEDIUM]
        findings = [_finding(s) for s in severities]
        result = ScanResult(server_name="srv", findings=findings)
        sorted_findings = result.findings_by_severity()
        assert [f.severity for f in sorted_findings] == [
            Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO
        ]


class TestScanResult:
    def test_is_clean_when_no_findings(self) -> None:
        result = ScanResult(server_name="srv")
        assert result.is_clean is True

    def test_not_clean_when_findings_exist(self) -> None:
        result = ScanResult(server_name="srv", findings=[_finding(Severity.LOW)])
        assert result.is_clean is False

    def test_critical_count(self) -> None:
        result = ScanResult(server_name="srv", findings=[
            _finding(Severity.CRITICAL),
            _finding(Severity.CRITICAL),
            _finding(Severity.HIGH),
        ])
        assert result.critical_count == 2

    def test_high_count(self) -> None:
        result = ScanResult(server_name="srv", findings=[
            _finding(Severity.HIGH),
            _finding(Severity.MEDIUM),
        ])
        assert result.high_count == 1

    def test_highest_severity_none_when_empty(self) -> None:
        result = ScanResult(server_name="srv")
        assert result.highest_severity is None

    def test_highest_severity_returns_worst(self) -> None:
        result = ScanResult(server_name="srv", findings=[
            _finding(Severity.LOW),
            _finding(Severity.HIGH),
            _finding(Severity.MEDIUM),
        ])
        assert result.highest_severity == Severity.HIGH
