from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi import status as http_status
from pydantic import BaseModel

from langsight.api.dependencies import get_active_project_id, get_config, get_storage, require_admin
from langsight.config import LangSightConfig
from langsight.security.models import ScanResult
from langsight.security.scanner import SecurityScanner
from langsight.storage.base import StorageBackend

logger = structlog.get_logger()

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
    summary="Trigger on-demand security scan for servers",
    dependencies=[Depends(require_admin)],
)
async def trigger_security_scan(
    request: Request,
    project_id: str | None = Depends(get_active_project_id),
    storage: StorageBackend = Depends(get_storage),
    config: LangSightConfig = Depends(get_config),
) -> list[SecurityScanResponse]:
    """Run a full security scan (OWASP MCP Top 10 + CVEs + poisoning).

    When *project_id* is provided, only servers registered in that project's
    metadata are scanned.  Otherwise (admin / open install) all configured
    servers are scanned.
    """
    servers = list(config.servers)

    # ── Project-scope: filter to servers that belong to this project ──────
    if project_id and hasattr(storage, "get_all_server_metadata"):
        project_servers = await storage.get_all_server_metadata(project_id=project_id)
        allowed_names = {row["server_name"] for row in project_servers}
        servers = [s for s in servers if s.name in allowed_names]

    logger.info(
        "audit.security_scan.triggered",
        client_ip=request.client.host if request.client else "unknown",
        project_id=project_id,
        server_count=len(servers),
    )
    if not servers:
        return []
    scanner = SecurityScanner(storage=storage)
    scans = await scanner.scan_many(servers)
    logger.info(
        "audit.security_scan.complete",
        project_id=project_id,
        server_count=len(scans),
        critical_total=sum(s.critical_count for s in scans),
    )

    # Fire Slack alerts for servers with critical or high findings
    from langsight.api.alert_dispatcher import fire_alert as _fire_alert

    pid = project_id or ""
    for scan in scans:
        if scan.critical_count > 0:
            top_findings = ", ".join(
                f.title for f in scan.findings_by_severity()[:3] if f.severity.value == "critical"
            )
            await _fire_alert(
                storage=storage,
                alert_type="security_critical",
                severity="critical",
                server_name=scan.server_name,
                title=f"Critical security findings on '{scan.server_name}'",
                message=(
                    f"Security scan found {scan.critical_count} critical finding(s) "
                    f"on `{scan.server_name}`: {top_findings or 'see dashboard for details'}."
                ),
                project_id=pid,
                config=config,
            )
        elif scan.high_count > 0:
            top_findings = ", ".join(
                f.title for f in scan.findings_by_severity()[:3] if f.severity.value == "high"
            )
            await _fire_alert(
                storage=storage,
                alert_type="security_high",
                severity="warning",
                server_name=scan.server_name,
                title=f"High severity findings on '{scan.server_name}'",
                message=(
                    f"Security scan found {scan.high_count} high severity finding(s) "
                    f"on `{scan.server_name}`: {top_findings or 'see dashboard for details'}."
                ),
                project_id=pid,
                config=config,
            )

    return [_scan_to_response(s) for s in scans]
