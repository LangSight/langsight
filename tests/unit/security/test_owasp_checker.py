from __future__ import annotations

from langsight.models import HealthCheckResult, MCPServer, ServerStatus, ToolInfo, TransportType
from langsight.security.models import Severity
from langsight.security.owasp_checker import (
    check_destructive_tools_without_auth,
    check_no_authentication,
    check_schema_drift,
    check_tools_without_input_schema,
    check_url_transport_without_tls,
    run_all_checks,
)


def _server(
    name: str = "test",
    transport: str = "stdio",
    url: str | None = None,
    env: dict | None = None,
    args: list | None = None,
) -> MCPServer:
    return MCPServer(
        name=name,
        transport=TransportType(transport),
        url=url,
        env=env or {},
        args=args or [],
    )


def _health(
    status: ServerStatus = ServerStatus.UP,
    tools: list[ToolInfo] | None = None,
    error: str | None = None,
) -> HealthCheckResult:
    return HealthCheckResult(
        server_name="test",
        status=status,
        tools=tools or [],
        tools_count=len(tools or []),
        error=error,
    )


class TestCheckNoAuthentication:
    def test_no_auth_stdio_is_medium(self) -> None:
        findings = check_no_authentication(_server(transport="stdio"), None)
        assert len(findings) == 1
        assert findings[0].severity == Severity.MEDIUM
        assert findings[0].category == "OWASP-MCP-01"

    def test_no_auth_sse_is_critical(self) -> None:
        findings = check_no_authentication(
            _server(transport="sse", url="http://localhost/sse"), None
        )
        assert len(findings) == 1
        assert findings[0].severity == Severity.CRITICAL

    def test_auth_via_env_clears_finding(self) -> None:
        findings = check_no_authentication(
            _server(env={"API_KEY": "secret"}), None
        )
        assert findings == []

    def test_auth_via_token_env_clears_finding(self) -> None:
        findings = check_no_authentication(
            _server(env={"AUTH_TOKEN": "bearer-xyz"}), None
        )
        assert findings == []

    def test_auth_via_password_env_clears_finding(self) -> None:
        findings = check_no_authentication(
            _server(env={"DB_PASSWORD": "pass"}), None
        )
        assert findings == []


class TestCheckDestructiveToolsWithoutAuth:
    def test_delete_tool_without_auth_is_high(self) -> None:
        health = _health(tools=[ToolInfo(name="delete_record")])
        findings = check_destructive_tools_without_auth(_server(), health)
        assert len(findings) == 1
        assert findings[0].severity == Severity.HIGH
        assert findings[0].tool_name == "delete_record"

    def test_drop_table_tool_without_auth_is_high(self) -> None:
        health = _health(tools=[ToolInfo(name="drop_table")])
        findings = check_destructive_tools_without_auth(_server(), health)
        assert len(findings) == 1

    def test_exec_tool_without_auth_is_high(self) -> None:
        health = _health(tools=[ToolInfo(name="execute_command")])
        findings = check_destructive_tools_without_auth(_server(), health)
        assert len(findings) == 1

    def test_safe_tool_not_flagged(self) -> None:
        health = _health(tools=[ToolInfo(name="query"), ToolInfo(name="list_tables")])
        findings = check_destructive_tools_without_auth(_server(), health)
        assert findings == []

    def test_destructive_tool_with_auth_not_flagged(self) -> None:
        health = _health(tools=[ToolInfo(name="delete_record")])
        findings = check_destructive_tools_without_auth(
            _server(env={"API_KEY": "secret"}), health
        )
        assert findings == []

    def test_no_health_returns_empty(self) -> None:
        findings = check_destructive_tools_without_auth(_server(), None)
        assert findings == []

    def test_multiple_destructive_tools_all_flagged(self) -> None:
        health = _health(tools=[
            ToolInfo(name="delete_user"),
            ToolInfo(name="drop_table"),
            ToolInfo(name="query"),  # safe
        ])
        findings = check_destructive_tools_without_auth(_server(), health)
        assert len(findings) == 2


class TestCheckToolsWithoutInputSchema:
    def test_tool_no_schema_is_medium(self) -> None:
        health = _health(tools=[ToolInfo(name="query", input_schema={})])
        findings = check_tools_without_input_schema(_server(), health)
        assert len(findings) == 1
        assert findings[0].severity == Severity.MEDIUM

    def test_tool_with_schema_not_flagged(self) -> None:
        health = _health(tools=[ToolInfo(
            name="query",
            input_schema={"type": "object", "properties": {"sql": {"type": "string"}}},
        )])
        findings = check_tools_without_input_schema(_server(), health)
        assert findings == []

    def test_no_health_returns_empty(self) -> None:
        assert check_tools_without_input_schema(_server(), None) == []


class TestCheckSchemaDrift:
    def test_degraded_with_drift_error_is_high(self) -> None:
        health = _health(status=ServerStatus.DEGRADED, error="schema drift: abc → def")
        findings = check_schema_drift(_server(), health)
        assert len(findings) == 1
        assert findings[0].severity == Severity.HIGH
        assert findings[0].category == "OWASP-MCP-04"

    def test_up_status_no_finding(self) -> None:
        health = _health(status=ServerStatus.UP)
        assert check_schema_drift(_server(), health) == []

    def test_down_status_no_finding(self) -> None:
        health = _health(status=ServerStatus.DOWN, error="timeout")
        assert check_schema_drift(_server(), health) == []

    def test_none_health_no_finding(self) -> None:
        assert check_schema_drift(_server(), None) == []


class TestCheckUrlTransportWithoutTls:
    def test_http_sse_is_high(self) -> None:
        findings = check_url_transport_without_tls(
            _server(transport="sse", url="http://myserver.com/sse"), None
        )
        assert len(findings) == 1
        assert findings[0].severity == Severity.HIGH
        assert findings[0].category == "OWASP-MCP-06"

    def test_https_sse_not_flagged(self) -> None:
        findings = check_url_transport_without_tls(
            _server(transport="sse", url="https://myserver.com/sse"), None
        )
        assert findings == []

    def test_stdio_not_flagged(self) -> None:
        findings = check_url_transport_without_tls(_server(transport="stdio"), None)
        assert findings == []


class TestRunAllChecks:
    def test_returns_combined_findings(self) -> None:
        server = _server(transport="sse", url="http://myserver.com/sse")
        health = _health(tools=[ToolInfo(name="delete_record")])
        findings = run_all_checks(server, health)
        categories = {f.category for f in findings}
        assert "OWASP-MCP-01" in categories   # no auth
        assert "OWASP-MCP-02" in categories   # destructive tool
        assert "OWASP-MCP-06" in categories   # plaintext HTTP

    def test_clean_server_no_findings(self) -> None:
        server = _server(
            transport="sse",
            url="https://myserver.com/sse",
            env={"API_KEY": "secret"},
        )
        health = _health(tools=[ToolInfo(
            name="query",
            input_schema={"type": "object", "properties": {"sql": {"type": "string"}}},
        )])
        findings = run_all_checks(server, health)
        assert findings == []
