from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from fastapi import status as http_status
from pydantic import BaseModel

from langsight.api.dependencies import get_config, get_storage
from langsight.config import LangSightConfig
from langsight.security.models import ScanResult
from langsight.security.scanner import SecurityScanner
from langsight.storage.base import StorageBackend

router = APIRouter(prefix="/security", tags=["security"])


class SecurityScanResponse(BaseModel):
    """Summary of a security scan for one server."""

    server_name: str
    scanned_at: str
    error: str | None
    findings_count: int
    critical_count: int
    high_count: int
    highest_severity: str | None
    findings: list[dict[str, Any]]


def _scan_to_response(scan: ScanResult) -> SecurityScanResponse:
    return SecurityScanResponse(
        server_name=scan.server_name,
        scanned_at=scan.scanned_at.isoformat(),
        error=scan.error,
        findings_count=len(scan.findings),
        critical_count=scan.critical_count,
        high_count=scan.high_count,
        highest_severity=scan.highest_severity.value if scan.highest_severity else None,
        findings=[
            {
                "severity": f.severity.value,
                "category": f.category,
                "title": f.title,
                "description": f.description,
                "remediation": f.remediation,
                "tool_name": f.tool_name,
                "cve_id": f.cve_id,
            }
            for f in scan.findings_by_severity()
        ],
    )


@router.post(
    "/scan",
    response_model=list[SecurityScanResponse],
    status_code=http_status.HTTP_200_OK,
    summary="Trigger on-demand security scan for all servers",
)
async def trigger_security_scan(
    storage: StorageBackend = Depends(get_storage),
    config: LangSightConfig = Depends(get_config),
) -> list[SecurityScanResponse]:
    """Run a full security scan (OWASP MCP Top 10 + CVEs + poisoning) on all servers.

    Each scan runs a health check first to retrieve the live tools list,
    then evaluates all security rules concurrently.
    """
    if not config.servers:
        return []
    scanner = SecurityScanner(storage=storage)
    scans = await scanner.scan_many(config.servers)
    return [_scan_to_response(s) for s in scans]
