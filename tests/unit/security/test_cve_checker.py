from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from langsight.models import MCPServer, TransportType
from langsight.security.cve_checker import (
    _osv_severity,
    _parse_pyproject_deps,
    check_cves,
)
from langsight.security.models import Severity


def _server(command: str | None = None) -> MCPServer:
    return MCPServer(
        name="test",
        transport=TransportType.STDIO,
        command=command,
    )


class TestParsePyprojectDeps:
    def test_parses_pep621_dependencies(self, tmp_path: Path) -> None:
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            '[project]\ndependencies = ["fastmcp>=2.0.0", "asyncpg>=0.29.0"]\n'
        )
        packages = _parse_pyproject_deps(pyproject)
        names = [p["name"] for p in packages]
        assert "fastmcp" in names
        assert "asyncpg" in names

    def test_ignores_python_entry(self, tmp_path: Path) -> None:
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\ndependencies = ["python>=3.11", "click>=8"]\n')
        packages = _parse_pyproject_deps(pyproject)
        names = [p["name"] for p in packages]
        assert "python" not in names
        assert "click" in names

    def test_all_packages_have_pypi_ecosystem(self, tmp_path: Path) -> None:
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\ndependencies = ["pydantic>=2"]\n')
        packages = _parse_pyproject_deps(pyproject)
        assert all(p["ecosystem"] == "PyPI" for p in packages)

    def test_returns_empty_on_parse_error(self, tmp_path: Path) -> None:
        bad = tmp_path / "pyproject.toml"
        bad.write_text("not valid toml {{{{")
        packages = _parse_pyproject_deps(bad)
        assert packages == []

    def test_strips_extras_from_name(self, tmp_path: Path) -> None:
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\ndependencies = ["mcp[cli]>=1.0"]\n')
        packages = _parse_pyproject_deps(pyproject)
        names = [p["name"] for p in packages]
        assert "mcp" in names


class TestOsvSeverity:
    def test_critical_cvss(self) -> None:
        vuln = {"database_specific": {"severity": "CRITICAL"}}
        assert _osv_severity(vuln) == Severity.CRITICAL

    def test_high_cvss(self) -> None:
        vuln = {"database_specific": {"severity": "HIGH"}}
        assert _osv_severity(vuln) == Severity.HIGH

    def test_moderate_maps_to_medium(self) -> None:
        vuln = {"database_specific": {"severity": "MODERATE"}}
        assert _osv_severity(vuln) == Severity.MEDIUM

    def test_unknown_defaults_to_medium(self) -> None:
        vuln = {}
        assert _osv_severity(vuln) == Severity.MEDIUM


class TestCheckCves:
    async def test_returns_empty_when_no_command(self) -> None:
        findings = await check_cves(_server(command=None))
        assert findings == []

    async def test_returns_empty_when_no_dep_file_found(self, tmp_path: Path) -> None:
        server_py = tmp_path / "server.py"
        server_py.write_text("# empty")
        findings = await check_cves(_server(command=str(server_py)))
        assert findings == []

    async def test_returns_cve_findings_from_osv(self, tmp_path: Path) -> None:
        server_py = tmp_path / "server.py"
        server_py.write_text("# server")
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\ndependencies = ["vulnerable-pkg>=1.0"]\n')

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "results": [{
                "vulns": [{
                    "id": "GHSA-xxxx-yyyy-zzzz",
                    "summary": "Remote code execution",
                    "database_specific": {"severity": "CRITICAL"},
                }]
            }]
        }

        with patch("langsight.security.cve_checker.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=MockClient.return_value)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value.post = AsyncMock(return_value=mock_response)
            findings = await check_cves(_server(command=str(server_py)))

        assert len(findings) == 1
        assert findings[0].cve_id == "GHSA-xxxx-yyyy-zzzz"
        assert findings[0].severity == Severity.CRITICAL
        assert findings[0].category == "CVE"

    async def test_fails_open_on_network_error(self, tmp_path: Path) -> None:
        server_py = tmp_path / "server.py"
        server_py.write_text("# server")
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\ndependencies = ["some-pkg>=1.0"]\n')

        with patch("langsight.security.cve_checker.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=MockClient.return_value)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value.post = AsyncMock(side_effect=Exception("network error"))
            findings = await check_cves(_server(command=str(server_py)))

        assert findings == []  # fail-open: network error doesn't break scan
