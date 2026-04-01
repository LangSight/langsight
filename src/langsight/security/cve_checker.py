"""
CVE checker using the OSV (Open Source Vulnerabilities) API.

Reads dependency files from MCP server directories and queries the OSV API
for known vulnerabilities. No API key required.

OSV API: https://google.github.io/osv.dev/api/
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

import httpx
import structlog

from langsight.models import MCPServer
from langsight.security.models import SecurityFinding, Severity

logger = structlog.get_logger()

OSV_BATCH_URL = "https://api.osv.dev/v1/querybatch"
OSV_REQUEST_TIMEOUT = 10.0
_CVE_CACHE_TTL = 3600.0  # 1 hour — CVE data doesn't change frequently


def _parse_pyproject_deps(path: Path) -> list[dict[str, str]]:
    """Extract package name + version from a pyproject.toml dependencies list."""
    try:
        import tomllib  # Python 3.11+
    except ImportError:
        return []

    try:
        data = tomllib.loads(path.read_text())
    except Exception as exc:  # noqa: BLE001
        logger.warning("cve_checker.parse_error", file=str(path), error=str(exc))
        return []

    raw_deps: list[str] = []

    # [project] dependencies
    raw_deps.extend(data.get("project", {}).get("dependencies", []))

    # [tool.poetry.dependencies] (legacy)
    raw_deps.extend(data.get("tool", {}).get("poetry", {}).get("dependencies", {}).keys())

    packages: list[dict[str, str]] = []
    for dep in raw_deps:
        if isinstance(dep, str):
            # Strip extras: "mcp[cli]>=1.0,<2" → "mcp>=1.0,<2"
            dep_no_extras = re.sub(r"\[.*?\]", "", dep)
            name = re.split(r"[><=!~\s]", dep_no_extras)[0].strip()
            if not name or name == "python":
                continue
            pkg: dict[str, str] = {"name": name, "ecosystem": "PyPI"}
            # Extract pinned version for accurate OSV matching.
            # "fastmcp==2.0.0" → "2.0.0", "httpx>=0.27" → "0.27"
            # Without a version OSV queries by name only, which returns all
            # historical CVEs regardless of whether this install is affected.
            version_match = re.search(r"[><=~!]+\s*([0-9][^\s,;]*)", dep_no_extras)
            if version_match:
                pkg["version"] = version_match.group(1).strip()
            packages.append(pkg)

    return packages


def _parse_package_json_deps(path: Path) -> list[dict[str, str]]:
    """Extract package names from a package.json dependencies."""
    try:
        data = json.loads(path.read_text())
    except Exception as exc:  # noqa: BLE001
        logger.warning("cve_checker.parse_error", file=str(path), error=str(exc))
        return []

    packages: list[dict[str, str]] = []
    for section in ("dependencies", "devDependencies"):
        for name, version_spec in data.get(section, {}).items():
            pkg: dict[str, str] = {"name": name, "ecosystem": "npm"}
            # Extract pinned version from npm version spec.
            # "^1.2.3" → "1.2.3", "~2.0.0" → "2.0.0", "1.0.0" → "1.0.0"
            if isinstance(version_spec, str):
                version_match = re.match(r"[^\d]*([0-9][^\s]*)", version_spec.strip())
                if version_match:
                    pkg["version"] = version_match.group(1)
            packages.append(pkg)

    return packages


def _find_dep_file(server: MCPServer) -> tuple[Path | None, str]:
    """Locate a dependency file near the server's command path."""
    if not server.command:
        return None, ""

    # Walk up from the command's directory looking for pyproject.toml or package.json
    cmd_path = Path(server.command)
    if not cmd_path.is_absolute():
        cmd_path = Path.cwd() / cmd_path

    search_dirs = [cmd_path.parent, cmd_path.parent.parent]
    for directory in search_dirs:
        pyproject = directory / "pyproject.toml"
        if pyproject.exists():
            return pyproject, "pyproject"
        package_json = directory / "package.json"
        if package_json.exists():
            return package_json, "npm"

    return None, ""


# Module-level cache: dep_file_path → (findings, expires_at)
_cve_cache: dict[str, tuple[list[SecurityFinding], float]] = {}


async def check_cves(server: MCPServer) -> list[SecurityFinding]:
    """Query OSV API for CVEs in the server's dependencies.

    Results are cached for 1 hour per dependency file to avoid hammering
    the OSV API when scanning many servers that share the same deps.

    Returns an empty list if no dependency file is found or if the OSV
    API is unreachable (fail-open: don't block scans on network issues).
    """
    dep_file, dep_type = _find_dep_file(server)
    if dep_file is None:
        logger.debug("cve_checker.no_dep_file", server=server.name)
        return []

    # Check cache
    cache_key = str(dep_file)
    cached = _cve_cache.get(cache_key)
    if cached and time.monotonic() < cached[1]:
        logger.debug("cve_checker.cache_hit", server=server.name, file=cache_key)
        return cached[0]

    if dep_type == "pyproject":
        packages = _parse_pyproject_deps(dep_file)
    else:
        packages = _parse_package_json_deps(dep_file)

    if not packages:
        return []

    logger.info(
        "cve_checker.scanning",
        server=server.name,
        packages=len(packages),
        ecosystem=dep_type,
    )

    # When a version is known, query OSV with version so it returns only CVEs
    # that affect the installed version. Without version, OSV returns all
    # historical CVEs for the package name regardless of installed version.
    queries = [
        {
            "package": {"name": p["name"], "ecosystem": p["ecosystem"]},
            **({"version": p["version"]} if p.get("version") else {}),
        }
        for p in packages
    ]

    try:
        async with httpx.AsyncClient(timeout=OSV_REQUEST_TIMEOUT) as client:
            response = await client.post(OSV_BATCH_URL, json={"queries": queries})
            response.raise_for_status()
            data = response.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("cve_checker.api_error", server=server.name, error=str(exc))
        return []  # fail-open: network issues don't block scans

    findings: list[SecurityFinding] = []
    for pkg, result in zip(packages, data.get("results", []), strict=False):
        vulns = result.get("vulns", [])
        for vuln in vulns:
            vuln_id = vuln.get("id", "UNKNOWN")
            severity = _osv_severity(vuln)
            findings.append(
                SecurityFinding(
                    server_name=server.name,
                    severity=severity,
                    category="CVE",
                    title=f"CVE in dependency '{pkg['name']}': {vuln_id}",
                    description=(
                        f"Package '{pkg['name']}' ({pkg['ecosystem']}) has a known "
                        f"vulnerability: {vuln_id}. "
                        f"{vuln.get('summary', 'No summary available.')}"
                    ),
                    remediation=(
                        f"Update '{pkg['name']}' to a patched version. "
                        f"Check https://osv.dev/vulnerability/{vuln_id} for fix details."
                    ),
                    cve_id=vuln_id,
                )
            )

    # Cache results for 1 hour
    _cve_cache[cache_key] = (findings, time.monotonic() + _CVE_CACHE_TTL)

    if findings:
        logger.warning(
            "cve_checker.vulnerabilities_found",
            server=server.name,
            count=len(findings),
        )

    return findings


def _osv_severity(vuln: dict[str, Any]) -> Severity:
    """Map OSV severity / CVSS score to LangSight Severity."""
    # Try CVSS score from database_specific
    for db in vuln.get("database_specific", {}).values():
        if isinstance(db, dict):
            score = db.get("cvss_score") or db.get("cvss", {}).get("score")
            if isinstance(score, (int, float)):
                if score >= 9.0:
                    return Severity.CRITICAL
                if score >= 7.0:
                    return Severity.HIGH
                if score >= 4.0:
                    return Severity.MEDIUM
                return Severity.LOW

    # Try severity field directly
    sev = vuln.get("database_specific", {}).get("severity", "").upper()
    mapping = {
        "CRITICAL": Severity.CRITICAL,
        "HIGH": Severity.HIGH,
        "MODERATE": Severity.MEDIUM,
        "MEDIUM": Severity.MEDIUM,
        "LOW": Severity.LOW,
    }
    return mapping.get(sev, Severity.MEDIUM)
