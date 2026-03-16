"""
OWASP MCP Top 10 automated checks.

Each check is a pure function: (MCPServer, HealthCheckResult | None) → list[SecurityFinding].
All checks are static — no network calls, no subprocess execution.

Reference: OWASP MCP Top 10 (2025)
https://owasp.org/www-project-top-10-for-large-language-model-applications/
"""

from __future__ import annotations

import re

from langsight.models import HealthCheckResult, MCPServer
from langsight.security.models import SecurityFinding, Severity

# Tools whose names suggest destructive operations — used for permission checks
_DESTRUCTIVE_TOOL_PATTERNS = re.compile(
    # Use [^a-zA-Z0-9] boundaries instead of \b — \b treats _ as word char
    # so "delete_record" would NOT match \bdelete\b but SHOULD be flagged.
    r"(?:^|[^a-zA-Z0-9])(delete|drop|truncate|remove|destroy|purge|wipe|exec|execute|run|shell|cmd)(?:[^a-zA-Z0-9]|$)",
    re.IGNORECASE,
)

# Auth-related env var patterns (presence = auth configured)
_AUTH_ENV_PATTERNS = re.compile(
    r"(api_key|apikey|token|secret|password|auth|bearer|credential)",
    re.IGNORECASE,
)


def check_no_authentication(
    server: MCPServer,
    health: HealthCheckResult | None,  # noqa: ARG001
) -> list[SecurityFinding]:
    """OWASP-MCP-01: No authentication configured.

    Checks whether the server config contains any auth-related env vars.
    Absence of auth env vars on a non-stdio server is flagged as CRITICAL.
    """
    # stdio servers on localhost are lower risk — flag as MEDIUM
    is_local_stdio = server.transport.value == "stdio"

    has_auth = any(_AUTH_ENV_PATTERNS.search(k) for k in server.env) or any(
        _AUTH_ENV_PATTERNS.search(k) for k in (server.args or [])
    )

    if has_auth:
        return []

    severity = Severity.MEDIUM if is_local_stdio else Severity.CRITICAL
    return [
        SecurityFinding(
            server_name=server.name,
            severity=severity,
            category="OWASP-MCP-01",
            title="No authentication configured",
            description=(
                f"Server '{server.name}' has no authentication credentials in its "
                f"configuration. Any process that can reach this server can call its tools."
            ),
            remediation=(
                "Add an API key or token to the server's env configuration. "
                "For SSE/HTTP transports, require bearer token authentication."
            ),
        )
    ]


def check_destructive_tools_without_auth(
    server: MCPServer,
    health: HealthCheckResult | None,
) -> list[SecurityFinding]:
    """OWASP-MCP-02: Destructive tools exposed without authentication.

    Looks for tools whose names imply destructive operations (delete, drop,
    execute, etc.) on servers that have no authentication configured.
    """
    if health is None or not health.tools:
        return []

    has_auth = any(_AUTH_ENV_PATTERNS.search(k) for k in server.env)
    if has_auth:
        return []

    findings: list[SecurityFinding] = []
    for tool in health.tools:
        if _DESTRUCTIVE_TOOL_PATTERNS.search(tool.name):
            findings.append(
                SecurityFinding(
                    server_name=server.name,
                    severity=Severity.HIGH,
                    category="OWASP-MCP-02",
                    title=f"Destructive tool '{tool.name}' exposed without authentication",
                    description=(
                        f"Tool '{tool.name}' on server '{server.name}' has a name "
                        f"suggesting destructive operations, but the server has no "
                        f"authentication configured."
                    ),
                    remediation=(
                        "Require authentication before exposing destructive tools. "
                        "Consider scoping tool permissions — read-only clients should "
                        "not have access to mutating tools."
                    ),
                    tool_name=tool.name,
                )
            )
    return findings


def check_tools_without_input_schema(
    server: MCPServer,
    health: HealthCheckResult | None,
) -> list[SecurityFinding]:
    """OWASP-MCP-05: Tools with no input schema allow unvalidated free-form input.

    An MCP tool with no inputSchema accepts arbitrary input without type
    constraints — making injection and misuse much easier.
    """
    if health is None or not health.tools:
        return []

    findings: list[SecurityFinding] = []
    for tool in health.tools:
        if not tool.input_schema or tool.input_schema == {"type": "object", "properties": {}}:
            findings.append(
                SecurityFinding(
                    server_name=server.name,
                    severity=Severity.MEDIUM,
                    category="OWASP-MCP-05",
                    title=f"Tool '{tool.name}' has no input schema",
                    description=(
                        f"Tool '{tool.name}' on server '{server.name}' does not define "
                        f"an input schema. The server cannot validate or constrain inputs, "
                        f"making injection attacks easier."
                    ),
                    remediation=(
                        "Define a strict inputSchema for this tool with required fields, "
                        "type constraints, and enum values where applicable."
                    ),
                    tool_name=tool.name,
                )
            )
    return findings


def check_schema_drift(
    server: MCPServer,
    health: HealthCheckResult | None,
) -> list[SecurityFinding]:
    """OWASP-MCP-04: Unexpected schema change (potential rug pull).

    A sudden schema change without a deployment event could indicate a
    supply chain compromise or tool poisoning attack.
    """
    from langsight.models import ServerStatus

    if health is None:
        return []
    if health.status != ServerStatus.DEGRADED:
        return []
    if health.error and "schema drift" not in health.error:
        return []

    return [
        SecurityFinding(
            server_name=server.name,
            severity=Severity.HIGH,
            category="OWASP-MCP-04",
            title="Unexpected tool schema change detected",
            description=(
                f"Server '{server.name}' tool schema changed since the last snapshot. "
                f"Details: {health.error}. "
                f"Unexpected schema changes can indicate supply chain compromise or "
                f"tool poisoning."
            ),
            remediation=(
                "Verify the schema change was intentional (planned deployment). "
                "If unexpected, treat as a potential security incident and audit "
                "the MCP server's source and dependencies."
            ),
        )
    ]


def check_url_transport_without_tls(
    server: MCPServer,
    health: HealthCheckResult | None,  # noqa: ARG001
) -> list[SecurityFinding]:
    """OWASP-MCP-06: SSE/HTTP transport using plaintext HTTP (not HTTPS).

    Plaintext MCP connections expose tool calls and responses to network
    interception and man-in-the-middle attacks.
    """
    if server.transport.value == "stdio":
        return []
    if not server.url:
        return []
    if server.url.startswith("https://"):
        return []

    return [
        SecurityFinding(
            server_name=server.name,
            severity=Severity.HIGH,
            category="OWASP-MCP-06",
            title="MCP server uses plaintext HTTP transport",
            description=(
                f"Server '{server.name}' is configured with URL '{server.url}' "
                f"which uses HTTP instead of HTTPS. Tool calls and responses are "
                f"transmitted in plaintext and are vulnerable to interception."
            ),
            remediation=(
                "Configure the MCP server to use HTTPS with a valid TLS certificate. "
                "Never use HTTP for MCP servers accessible over a network."
            ),
        )
    ]


def run_all_checks(
    server: MCPServer,
    health: HealthCheckResult | None,
) -> list[SecurityFinding]:
    """Run all OWASP MCP checks and return the combined findings."""
    checkers = [
        check_no_authentication,
        check_destructive_tools_without_auth,
        check_tools_without_input_schema,
        check_schema_drift,
        check_url_transport_without_tls,
    ]
    findings: list[SecurityFinding] = []
    for checker in checkers:
        findings.extend(checker(server, health))
    return findings
