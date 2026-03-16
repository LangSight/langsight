from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from langsight.models import (
    HealthCheckResult,
    MCPServer,
    ServerStatus,
    ToolInfo,
    TransportType,
)


class TestMCPServer:
    def test_minimal_stdio_server(self) -> None:
        s = MCPServer(name="test", transport=TransportType.STDIO, command="python srv.py")
        assert s.name == "test"
        assert s.transport == TransportType.STDIO
        assert s.timeout_seconds == 5
        assert s.args == []
        assert s.env == {}
        assert s.tags == []

    def test_minimal_sse_server(self) -> None:
        s = MCPServer(name="sse-srv", transport=TransportType.SSE, url="http://localhost/sse")
        assert s.url == "http://localhost/sse"

    def test_is_immutable(self) -> None:
        s = MCPServer(name="test", transport=TransportType.STDIO)
        with pytest.raises(ValidationError):
            s.name = "other"  # type: ignore[misc]

    def test_transport_string_coercion(self) -> None:
        s = MCPServer(name="test", transport="stdio")  # type: ignore[arg-type]
        assert s.transport == TransportType.STDIO

    def test_invalid_transport_raises(self) -> None:
        with pytest.raises(ValidationError):
            MCPServer(name="test", transport="ftp")  # type: ignore[arg-type]

    def test_args_and_env_populated(self) -> None:
        s = MCPServer(
            name="test",
            transport=TransportType.STDIO,
            command="python",
            args=["server.py", "--debug"],
            env={"LOG_LEVEL": "DEBUG"},
        )
        assert s.args == ["python", "server.py", "--debug"] or s.args == ["server.py", "--debug"]
        assert s.env["LOG_LEVEL"] == "DEBUG"


class TestToolInfo:
    def test_minimal_tool(self) -> None:
        t = ToolInfo(name="query")
        assert t.name == "query"
        assert t.description is None
        assert t.input_schema == {}

    def test_full_tool(self) -> None:
        t = ToolInfo(
            name="query",
            description="Execute SQL",
            input_schema={"type": "object", "properties": {"sql": {"type": "string"}}},
        )
        assert t.description == "Execute SQL"
        assert "sql" in t.input_schema["properties"]


class TestHealthCheckResult:
    def test_defaults(self) -> None:
        r = HealthCheckResult(server_name="srv", status=ServerStatus.UP)
        assert r.latency_ms is None
        assert r.tools == []
        assert r.tools_count == 0
        assert r.error is None
        assert r.schema_hash is None
        assert isinstance(r.checked_at, datetime)

    def test_checked_at_is_utc(self) -> None:
        r = HealthCheckResult(server_name="srv", status=ServerStatus.UP)
        assert r.checked_at.tzinfo == timezone.utc

    def test_down_with_error(self) -> None:
        r = HealthCheckResult(
            server_name="srv",
            status=ServerStatus.DOWN,
            error="timeout after 5s",
        )
        assert r.status == ServerStatus.DOWN
        assert r.error == "timeout after 5s"

    def test_up_with_tools(self) -> None:
        tools = [ToolInfo(name="query"), ToolInfo(name="list_tables")]
        r = HealthCheckResult(
            server_name="srv",
            status=ServerStatus.UP,
            latency_ms=42.5,
            tools=tools,
            tools_count=2,
            schema_hash="abc123def456",
        )
        assert r.latency_ms == 42.5
        assert r.tools_count == 2
        assert r.schema_hash == "abc123def456"

    def test_status_enum_values(self) -> None:
        for status in ServerStatus:
            r = HealthCheckResult(server_name="srv", status=status)
            assert r.status == status

    def test_serialises_to_json(self) -> None:
        r = HealthCheckResult(server_name="srv", status=ServerStatus.UP, latency_ms=10.0)
        data = r.model_dump(mode="json")
        assert data["server_name"] == "srv"
        assert data["status"] == "up"
        assert data["latency_ms"] == 10.0
        assert isinstance(data["checked_at"], str)
