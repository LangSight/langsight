from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml
from httpx import ASGITransport, AsyncClient

from langsight.api.main import create_app
from langsight.config import load_config
from langsight.security.models import ScanResult, SecurityFinding, Severity


def _clean_scan(name: str = "pg") -> ScanResult:
    return ScanResult(server_name=name, findings=[])


def _critical_scan(name: str = "pg") -> ScanResult:
    return ScanResult(
        server_name=name,
        findings=[
            SecurityFinding(
                server_name=name,
                severity=Severity.CRITICAL,
                category="OWASP-MCP-01",
                title="No authentication configured",
                description="desc",
                remediation="fix it",
            )
        ],
    )


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    cfg = tmp_path / ".langsight.yaml"
    cfg.write_text(yaml.dump({
        "servers": [{"name": "pg", "transport": "stdio", "command": "python s.py"}]
    }))
    return cfg


@pytest.fixture
async def client(config_file: Path):
    mock_storage = MagicMock()
    mock_storage.get_health_history = AsyncMock(return_value=[])
    mock_storage.save_health_result = AsyncMock()
    mock_storage.get_latest_schema_hash = AsyncMock(return_value=None)
    mock_storage.save_schema_snapshot = AsyncMock()
    mock_storage.close = AsyncMock()

    app = create_app(config_path=config_file)
    app.state.storage = mock_storage
    app.state.config = load_config(config_file)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, mock_storage


class TestTriggerSecurityScan:
    async def test_returns_200(self, client) -> None:
        c, _ = client
        with patch("langsight.api.routers.security.SecurityScanner") as MockScanner:
            MockScanner.return_value.scan_many = AsyncMock(return_value=[_clean_scan()])
            assert (await c.post("/api/security/scan")).status_code == 200

    async def test_returns_list(self, client) -> None:
        c, _ = client
        with patch("langsight.api.routers.security.SecurityScanner") as MockScanner:
            MockScanner.return_value.scan_many = AsyncMock(return_value=[_clean_scan()])
            data = (await c.post("/api/security/scan")).json()
        assert isinstance(data, list)

    async def test_clean_scan_response_shape(self, client) -> None:
        c, _ = client
        with patch("langsight.api.routers.security.SecurityScanner") as MockScanner:
            MockScanner.return_value.scan_many = AsyncMock(return_value=[_clean_scan()])
            data = (await c.post("/api/security/scan")).json()
        result = data[0]
        assert result["server_name"] == "pg"
        assert result["findings_count"] == 0
        assert result["critical_count"] == 0
        assert result["highest_severity"] is None
        assert result["findings"] == []

    async def test_critical_finding_in_response(self, client) -> None:
        c, _ = client
        with patch("langsight.api.routers.security.SecurityScanner") as MockScanner:
            MockScanner.return_value.scan_many = AsyncMock(return_value=[_critical_scan()])
            data = (await c.post("/api/security/scan")).json()
        result = data[0]
        assert result["critical_count"] == 1
        assert result["highest_severity"] == "critical"
        assert len(result["findings"]) == 1
        assert result["findings"][0]["severity"] == "critical"
        assert result["findings"][0]["category"] == "OWASP-MCP-01"

    async def test_empty_servers_returns_empty_list(self, tmp_path: Path) -> None:
        cfg = tmp_path / ".langsight.yaml"
        cfg.write_text(yaml.dump({"servers": []}))
        app = create_app(config_path=cfg)
        app.state.storage = MagicMock()
        app.state.config = load_config(cfg)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            data = (await c.post("/api/security/scan")).json()
        assert data == []

    async def test_scan_with_error_field_in_response(self, client) -> None:
        c, _ = client
        error_scan = ScanResult(server_name="pg", error="scan failed: timeout")
        with patch("langsight.api.routers.security.SecurityScanner") as MockScanner:
            MockScanner.return_value.scan_many = AsyncMock(return_value=[error_scan])
            data = (await c.post("/api/security/scan")).json()
        assert data[0]["error"] == "scan failed: timeout"
