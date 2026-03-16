"""
Tool poisoning / prompt injection detector.

Scans MCP tool names and descriptions for patterns used in:
- Prompt injection attacks ("ignore previous instructions")
- Data exfiltration via tool descriptions
- Hidden instruction injection (base64, unicode tricks)
- External URL injection in descriptions

Reference: OWASP MCP Top 10 — MCP-03 Tool Poisoning
"""

from __future__ import annotations

import base64
import re

from langsight.models import HealthCheckResult, ToolInfo
from langsight.security.models import SecurityFinding, Severity

# ---------------------------------------------------------------------------
# Pattern library
# ---------------------------------------------------------------------------

# Direct prompt injection phrases
_INJECTION_PHRASES = re.compile(
    r"\b("
    r"ignore (previous|prior|above|all) instructions?"
    r"|disregard (previous|prior|above|all) instructions?"
    r"|forget (previous|prior|above|all) instructions?"
    r"|override (system |previous )?(prompt|instructions?)"
    r"|do not follow (previous |the )?(instructions?|rules?)"
    r"|bypass (safety|security|restrictions?|guidelines?|filters?)"
    r"|act as (if you (are|were)|an? (unrestricted|jailbroken))"
    r"|you are now (an? )?(unrestricted|jailbroken|evil|dan)"
    r"|jailbreak"
    r"|pretend (you|to be) (have no|without) (restrictions?|limits?)"
    r")",
    re.IGNORECASE,
)

# Data exfiltration patterns
_EXFILTRATION_PATTERNS = re.compile(
    r"\b("
    r"send (all |the )?(data|contents?|results?|output) to"
    r"|exfiltrate"
    r"|forward (this |all )?(to|data)"
    r"|leak (this |the )?(data|contents?|info)"
    r"|transmit (to|all)"
    r"|report (to|back) (https?://|www\.)"
    r")",
    re.IGNORECASE,
)

# Suspicious external URLs embedded in tool descriptions
_EXTERNAL_URL = re.compile(
    r"https?://(?!localhost|127\.|0\.0\.0\.0|::1)[^\s\"'>]+",
    re.IGNORECASE,
)

# Base64 blobs that may hide instructions (>30 chars of base64-alphabet chars)
_BASE64_BLOB = re.compile(r"[A-Za-z0-9+/]{30,}={0,2}")

# Hidden unicode — zero-width spaces, direction overrides
_HIDDEN_UNICODE = re.compile(r"[\u200b\u200c\u200d\u200e\u200f\u202a-\u202e\u2060-\u2064\ufeff]")


def _check_base64_injection(text: str) -> bool:
    """Return True if text contains a base64 blob that decodes to an injection phrase."""
    for match in _BASE64_BLOB.finditer(text):
        blob = match.group()
        # Pad to valid length
        padded = blob + "=" * (4 - len(blob) % 4 if len(blob) % 4 else 0)
        try:
            decoded = base64.b64decode(padded).decode("utf-8", errors="ignore")
            if _INJECTION_PHRASES.search(decoded) or _EXFILTRATION_PATTERNS.search(decoded):
                return True
        except Exception:  # noqa: BLE001
            pass
    return False


def scan_tool(server_name: str, tool: ToolInfo) -> list[SecurityFinding]:
    """Scan a single tool's name and description for poisoning patterns."""
    findings: list[SecurityFinding] = []
    text = f"{tool.name} {tool.description or ''}"

    # Direct injection phrases
    if _INJECTION_PHRASES.search(text):
        findings.append(
            SecurityFinding(
                server_name=server_name,
                severity=Severity.CRITICAL,
                category="OWASP-MCP-03",
                title=f"Tool '{tool.name}' contains prompt injection pattern",
                description=(
                    f"Tool '{tool.name}' description contains phrases used in prompt "
                    f"injection attacks (e.g. 'ignore previous instructions'). "
                    f"This can manipulate AI agent behaviour."
                ),
                remediation=(
                    "Review and rewrite the tool description. Remove any instruction-like "
                    "language that could be interpreted as a system prompt override."
                ),
                tool_name=tool.name,
            )
        )

    # Data exfiltration patterns
    if _EXFILTRATION_PATTERNS.search(text):
        findings.append(
            SecurityFinding(
                server_name=server_name,
                severity=Severity.CRITICAL,
                category="OWASP-MCP-03",
                title=f"Tool '{tool.name}' contains data exfiltration pattern",
                description=(
                    f"Tool '{tool.name}' description contains language associated with "
                    f"data exfiltration attacks."
                ),
                remediation=(
                    "Remove any references to sending or transmitting data to external "
                    "destinations from tool descriptions."
                ),
                tool_name=tool.name,
            )
        )

    # External URLs in descriptions
    url_matches = _EXTERNAL_URL.findall(text)
    if url_matches:
        findings.append(
            SecurityFinding(
                server_name=server_name,
                severity=Severity.HIGH,
                category="OWASP-MCP-03",
                title=f"Tool '{tool.name}' description contains external URL",
                description=(
                    f"Tool '{tool.name}' description contains external URL(s): "
                    f"{', '.join(url_matches[:3])}. "
                    f"URLs in tool descriptions can be used for data exfiltration or "
                    f"to direct agents to malicious resources."
                ),
                remediation=(
                    "Remove external URLs from tool descriptions. "
                    "Reference documentation via a trusted internal path instead."
                ),
                tool_name=tool.name,
            )
        )

    # Hidden unicode characters
    if _HIDDEN_UNICODE.search(text):
        findings.append(
            SecurityFinding(
                server_name=server_name,
                severity=Severity.HIGH,
                category="OWASP-MCP-03",
                title=f"Tool '{tool.name}' contains hidden unicode characters",
                description=(
                    f"Tool '{tool.name}' description contains invisible unicode characters "
                    f"(zero-width spaces, direction overrides) that can hide malicious "
                    f"instructions from human reviewers."
                ),
                remediation=(
                    "Strip all zero-width and direction-override unicode characters "
                    "from tool names and descriptions."
                ),
                tool_name=tool.name,
            )
        )

    # Base64-encoded injection
    if _check_base64_injection(text):
        findings.append(
            SecurityFinding(
                server_name=server_name,
                severity=Severity.CRITICAL,
                category="OWASP-MCP-03",
                title=f"Tool '{tool.name}' contains base64-encoded injection",
                description=(
                    f"Tool '{tool.name}' description contains base64-encoded text that "
                    f"decodes to a prompt injection pattern."
                ),
                remediation=(
                    "Remove all base64-encoded content from tool descriptions. "
                    "Tool descriptions should be human-readable plain text only."
                ),
                tool_name=tool.name,
            )
        )

    return findings


def scan_all_tools(
    server_name: str,
    health: HealthCheckResult | None,
) -> list[SecurityFinding]:
    """Scan all tools on a server for poisoning patterns."""
    if health is None or not health.tools:
        return []
    findings: list[SecurityFinding] = []
    for tool in health.tools:
        findings.extend(scan_tool(server_name, tool))
    return findings
