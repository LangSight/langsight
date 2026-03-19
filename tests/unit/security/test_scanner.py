from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from langsight.models import MCPServer, ServerStatus, TransportType
from langsight.security.models import ScanResult, SecurityFinding, Severity
from langsight.security.scanner import SecurityScanner


def _server(name: str = "test") -> MCPServer:
    return MCPServer(name=name, transport=TransportType.STDIO, command="python server.py")


def _finding(severity: Severity = Severity.HIGH) -> SecurityFinding:
    return SecurityFinding(
        server_name="test",
        severity=severity,
        category="TEST",
        title="Test finding",
        description="desc",
        remediation="fix",
    )


class TestSecurityScanner:
    async def test_returns_scan_result_for_server(self) -> None:
        scanner = SecurityScanner()
        with patch.object(scanner._health_checker, "check", new_callable=AsyncMock) as mock_check:
            mock_check.return_value = MagicMock(
                status=ServerStatus.UP, tools=[], tools_count=0, error=None
            )
            with patch("langsight.security.scanner.run_all_checks", return_value=[]):
                with patch("langsight.security.scanner.scan_all_tools", return_value=[]):
                    with patch("langsight.security.scanner.check_cves", new_callable=AsyncMock, return_value=[]):
                        result = await scanner.scan(_server())

        assert isinstance(result, ScanResult)
        assert result.server_name == "test"
        assert result.error is None

    async def test_aggregates_findings_from_all_checkers(self) -> None:
        owasp = [_finding(Severity.CRITICAL)]
        poison = [_finding(Severity.HIGH)]
        cve = [_finding(Severity.MEDIUM)]

        scanner = SecurityScanner()
        with patch.object(scanner._health_checker, "check", new_callable=AsyncMock) as mock_check:
            mock_check.return_value = MagicMock(
                status=ServerStatus.UP, tools=[], tools_count=0, error=None
            )
            with patch("langsight.security.scanner.run_all_checks", return_value=owasp):
                with patch("langsight.security.scanner.scan_all_tools", return_value=poison):
                    with patch("langsight.security.scanner.check_cves", new_callable=AsyncMock, return_value=cve):
                        result = await scanner.scan(_server())

        assert len(result.findings) == 3
        severities = {f.severity for f in result.findings}
        assert Severity.CRITICAL in severities
        assert Severity.HIGH in severities
        assert Severity.MEDIUM in severities

    async def test_scan_error_returns_result_with_error_field(self) -> None:
        scanner = SecurityScanner()
        with patch.object(scanner._health_checker, "check", new_callable=AsyncMock) as mock_check:
            mock_check.side_effect = RuntimeError("unexpected failure")
            result = await scanner.scan(_server())

        assert result.error is not None
        assert "scan failed" in result.error
        assert result.findings == []

    async def test_scan_many_returns_one_result_per_server(self) -> None:
        scanner = SecurityScanner()
        servers = [_server("s1"), _server("s2"), _server("s3")]
        with patch.object(scanner._health_checker, "check", new_callable=AsyncMock) as mock_check:
            mock_check.return_value = MagicMock(
                status=ServerStatus.UP, tools=[], tools_count=0, error=None
            )
            with patch("langsight.security.scanner.run_all_checks", return_value=[]):
                with patch("langsight.security.scanner.scan_all_tools", return_value=[]):
                    with patch("langsight.security.scanner.check_cves", new_callable=AsyncMock, return_value=[]):
                        results = await scanner.scan_many(servers)

        assert len(results) == 3
        assert {r.server_name for r in results} == {"s1", "s2", "s3"}

    async def test_clean_server_has_no_findings(self) -> None:
        scanner = SecurityScanner()
        with patch.object(scanner._health_checker, "check", new_callable=AsyncMock) as mock_check:
            mock_check.return_value = MagicMock(
                status=ServerStatus.UP, tools=[], tools_count=0, error=None
            )
            with patch("langsight.security.scanner.run_all_checks", return_value=[]):
                with patch("langsight.security.scanner.scan_all_tools", return_value=[]):
                    with patch("langsight.security.scanner.check_cves", new_callable=AsyncMock, return_value=[]):
                        result = await scanner.scan(_server())

        assert result.is_clean
