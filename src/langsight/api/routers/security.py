from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi import status as http_status
from pydantic import BaseModel

from langsight.api.dependencies import get_active_project_id, get_config, get_storage, require_admin
from langsight.config import LangSightConfig
from langsight.models import MCPServer, TransportType
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


def _servers_from_metadata_rows(
    rows: list[dict[str, Any]],
    config: LangSightConfig,
) -> list[MCPServer]:
    """Build MCPServer objects from project catalog rows.

    Only rows with enough information are included:
    - transport must be set to a recognised value
    - sse / streamable_http rows need a non-empty url
    - stdio rows need a non-empty command (url field is not meaningful there)

    Rows that have only a name registered (no transport / connection info) are
    silently skipped — they are display-only entries in the catalog.

    For stdio servers the url column does not carry a command; we fall back to
    any matching MCPServer in config.servers so we don't lose command/args.
    """
    config_by_name: dict[str, MCPServer] = {s.name: s for s in config.servers}
    servers: list[MCPServer] = []

    valid_transports = {t.value for t in TransportType}

    for row in rows:
        name = row.get("server_name", "")
        transport_raw = (row.get("transport") or "").strip().lower()

        if not name or transport_raw not in valid_transports:
            # Not enough info — skip silently
            continue

        transport = TransportType(transport_raw)

        if transport in (TransportType.SSE, TransportType.STREAMABLE_HTTP):
            url = (row.get("url") or "").strip()
            if not url:
                # No endpoint — skip
                continue
            servers.append(
                MCPServer(name=name, transport=transport, url=url)
            )
        elif transport == TransportType.STDIO:
            # Prefer a config entry that already has command + args + env
            if name in config_by_name:
                servers.append(config_by_name[name])
            # If not in config, we have no command to run — skip
        # Any future transport types are skipped (unknown how to connect)

    return servers


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
    # ── Project-scope: build server list from Postgres catalog ───────────
    # When a project_id is active we use the project's server catalog as the
    # authoritative source rather than filtering config.servers.  This ensures
    # servers registered via the dashboard (but absent from the YAML) are also
    # scanned, and that servers from other projects cannot be included.
    if project_id and hasattr(storage, "get_all_server_metadata"):
        project_rows = await storage.get_all_server_metadata(project_id=project_id)
        servers = _servers_from_metadata_rows(project_rows, config)
        # Fall back to config.servers if no usable rows were found (new project,
        # catalog not yet populated).
        if not servers:
            servers = list(config.servers)
    else:
        servers = list(config.servers)

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
                redis=getattr(request.app.state, "redis", None),
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
                redis=getattr(request.app.state, "redis", None),
            )

    return [_scan_to_response(s) for s in scans]
