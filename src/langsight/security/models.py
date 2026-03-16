from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


# Severity ordering for sorting and comparison (higher index = more severe)
_SEVERITY_ORDER = [Severity.INFO, Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]


@dataclass(frozen=True)
class SecurityFinding:
    """A single security issue found on an MCP server."""

    server_name: str
    severity: Severity
    category: str  # e.g. "OWASP-MCP-01", "POISONING", "CVE"
    title: str
    description: str
    remediation: str
    tool_name: str | None = None  # set when finding is specific to one tool
    cve_id: str | None = None  # set for CVE findings


@dataclass
class ScanResult:
    """All security findings for one MCP server."""

    server_name: str
    findings: list[SecurityFinding] = field(default_factory=list)
    scanned_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    error: str | None = None  # set if the scan itself failed

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.CRITICAL)

    @property
    def high_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.HIGH)

    @property
    def highest_severity(self) -> Severity | None:
        if not self.findings:
            return None
        return max(self.findings, key=lambda f: _SEVERITY_ORDER.index(f.severity)).severity

    @property
    def is_clean(self) -> bool:
        return len(self.findings) == 0

    def findings_by_severity(self) -> list[SecurityFinding]:
        """Return findings sorted by severity descending (CRITICAL first)."""
        return sorted(
            self.findings,
            key=lambda f: _SEVERITY_ORDER.index(f.severity),
            reverse=True,
        )
