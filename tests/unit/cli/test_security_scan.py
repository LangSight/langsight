from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml
from click.testing import CliRunner

from langsight.cli.main import cli
from langsight.security.models import ScanResult, SecurityFinding, Severity


def _finding(severity: Severity, category: str = "OWASP-MCP-01") -> SecurityFinding:
    return SecurityFinding(
        server_name="test",
        severity=severity,
        category=category,
        title=f"{severity.value} finding",
        description="desc",
        remediation="fix it",
    )


CLEAN_RESULT = ScanResult(server_name="test", findings=[])
CRITICAL_RESULT = ScanResult(
    server_name="test",
    findings=[_finding(Severity.CRITICAL), _finding(Severity.HIGH)],
)


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    cfg = tmp_path / ".langsight.yaml"
    cfg.write_text(yaml.dump({
        "servers": [{"name": "test", "transport": "stdio", "command": "python server.py"}]
    }))
    return cfg


def _mock_storage() -> MagicMock:
    storage = MagicMock()
    storage.save_health_result = AsyncMock()
    storage.get_latest_schema_hash = AsyncMock(return_value=None)
    storage.save_schema_snapshot = AsyncMock()
    storage.close = AsyncMock()
    storage.__aenter__ = AsyncMock(return_value=storage)
    storage.__aexit__ = AsyncMock(return_value=None)
    return storage


class TestSecurityScanCommand:
    def test_shows_clean_for_no_findings(self, config_file: Path) -> None:
        runner = CliRunner()
        storage = _mock_storage()
        with patch("langsight.cli.security_scan.open_storage", new_callable=AsyncMock, return_value=storage):
            with patch("langsight.cli.security_scan.SecurityScanner") as MockScanner:
                MockScanner.return_value.scan_many = AsyncMock(return_value=[CLEAN_RESULT])
                result = runner.invoke(cli, ["security-scan", "--config", str(config_file)])

        assert result.exit_code == 0
        assert "CLEAN" in result.output or "No findings" in result.output

    def test_shows_findings_in_table(self, config_file: Path) -> None:
        runner = CliRunner()
        storage = _mock_storage()
        with patch("langsight.cli.security_scan.open_storage", new_callable=AsyncMock, return_value=storage):
            with patch("langsight.cli.security_scan.SecurityScanner") as MockScanner:
                MockScanner.return_value.scan_many = AsyncMock(return_value=[CRITICAL_RESULT])
                result = runner.invoke(cli, ["security-scan", "--config", str(config_file)])

        assert "CRITICAL" in result.output
        assert "HIGH" in result.output

    def test_ci_flag_exits_1_on_critical(self, config_file: Path) -> None:
        runner = CliRunner()
        storage = _mock_storage()
        with patch("langsight.cli.security_scan.open_storage", new_callable=AsyncMock, return_value=storage):
            with patch("langsight.cli.security_scan.SecurityScanner") as MockScanner:
                MockScanner.return_value.scan_many = AsyncMock(return_value=[CRITICAL_RESULT])
                result = runner.invoke(cli, ["security-scan", "--config", str(config_file), "--ci"])

        assert result.exit_code == 1

    def test_ci_flag_exits_0_on_clean(self, config_file: Path) -> None:
        runner = CliRunner()
        storage = _mock_storage()
        with patch("langsight.cli.security_scan.open_storage", new_callable=AsyncMock, return_value=storage):
            with patch("langsight.cli.security_scan.SecurityScanner") as MockScanner:
                MockScanner.return_value.scan_many = AsyncMock(return_value=[CLEAN_RESULT])
                result = runner.invoke(cli, ["security-scan", "--config", str(config_file), "--ci"])

        assert result.exit_code == 0

    def test_json_flag_outputs_valid_json(self, config_file: Path) -> None:
        runner = CliRunner()
        storage = _mock_storage()
        with patch("langsight.cli.security_scan.open_storage", new_callable=AsyncMock, return_value=storage):
            with patch("langsight.cli.security_scan.SecurityScanner") as MockScanner:
                MockScanner.return_value.scan_many = AsyncMock(return_value=[CLEAN_RESULT])
                result = runner.invoke(cli, ["security-scan", "--config", str(config_file), "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert data[0]["server_name"] == "test"

    def test_exits_1_when_no_servers(self, tmp_path: Path) -> None:
        cfg = tmp_path / ".langsight.yaml"
        cfg.write_text(yaml.dump({"servers": []}))
        runner = CliRunner()
        result = runner.invoke(cli, ["security-scan", "--config", str(cfg)])
        assert result.exit_code == 1

    def test_findings_sorted_by_severity(self, config_file: Path) -> None:
        result_with_findings = ScanResult(
            server_name="test",
            findings=[
                _finding(Severity.LOW),
                _finding(Severity.CRITICAL),
                _finding(Severity.MEDIUM),
            ],
        )
        runner = CliRunner()
        storage = _mock_storage()
        with patch("langsight.cli.security_scan.open_storage", new_callable=AsyncMock, return_value=storage):
            with patch("langsight.cli.security_scan.SecurityScanner") as MockScanner:
                MockScanner.return_value.scan_many = AsyncMock(return_value=[result_with_findings])
                result = runner.invoke(cli, ["security-scan", "--config", str(config_file)])

        # CRITICAL should appear before LOW in output
        assert result.output.index("CRITICAL") < result.output.index("LOW")
