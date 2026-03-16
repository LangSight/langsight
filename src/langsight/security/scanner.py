from __future__ import annotations

import asyncio

import structlog

from langsight.health.checker import HealthChecker
from langsight.models import MCPServer
from langsight.security.cve_checker import check_cves
from langsight.security.models import ScanResult, SecurityFinding
from langsight.security.owasp_checker import run_all_checks
from langsight.security.poisoning_detector import scan_all_tools
from langsight.storage.base import StorageBackend

logger = structlog.get_logger()


class SecurityScanner:
    """Orchestrates all security checks for MCP servers.

    Runs concurrently:
    - OWASP MCP Top 10 static checks (config + tools)
    - Tool poisoning / prompt injection detection
    - CVE scan via OSV API

    Requires a health check result for tool-level checks. If health is
    unavailable (server DOWN), only config-level checks run.

    Args:
        storage: Optional storage backend. When provided, health check results
                 are reused from the last run rather than re-fetching.
    """

    def __init__(self, storage: StorageBackend | None = None) -> None:
        self._storage = storage
        self._health_checker = HealthChecker(storage=storage)

    async def scan(self, server: MCPServer) -> ScanResult:
        """Run all security checks against one MCP server."""
        logger.info("security_scan.start", server=server.name)

        try:
            # Run health check to get live tools list for tool-level checks
            health = await self._health_checker.check(server)

            # Run all checks concurrently
            owasp_findings, poisoning_findings, cve_findings = await asyncio.gather(
                asyncio.to_thread(run_all_checks, server, health),
                asyncio.to_thread(scan_all_tools, server.name, health),
                check_cves(server),
            )

            findings: list[SecurityFinding] = [
                *owasp_findings,
                *poisoning_findings,
                *cve_findings,
            ]

            result = ScanResult(server_name=server.name, findings=findings)
            logger.info(
                "security_scan.complete",
                server=server.name,
                findings=len(findings),
                critical=result.critical_count,
                high=result.high_count,
            )
            return result

        except Exception as exc:  # noqa: BLE001
            logger.error("security_scan.error", server=server.name, error=str(exc))
            return ScanResult(
                server_name=server.name,
                error=f"scan failed: {exc}",
            )

    async def scan_many(self, servers: list[MCPServer]) -> list[ScanResult]:
        """Scan multiple MCP servers concurrently."""
        results = await asyncio.gather(*[self.scan(server) for server in servers])
        return list(results)
