from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from langsight.exceptions import MCPConnectionError, MCPTimeoutError
from langsight.health.checker import HealthChecker
from langsight.models import MCPServer, ServerStatus, ToolInfo, TransportType

TOOL_QUERY = ToolInfo(name="query", description="Execute SQL")
TOOL_LIST = ToolInfo(name="list_tables", description="List tables")


@pytest.fixture
def server() -> MCPServer:
    return MCPServer(name="test-server", transport=TransportType.STDIO, command="echo")


@pytest.fixture
def checker() -> HealthChecker:
    return HealthChecker()


class TestHealthCheckerCheck:
    async def test_up_status_on_success(self, server: MCPServer, checker: HealthChecker) -> None:
        with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
            mock_ping.return_value = (42.0, [TOOL_QUERY, TOOL_LIST])
            result = await checker.check(server)

        assert result.status == ServerStatus.UP
        assert result.server_name == "test-server"
        assert result.latency_ms == 42.0
        assert result.tools_count == 2
        assert result.error is None

    async def test_schema_hash_computed_on_success(
        self, server: MCPServer, checker: HealthChecker
    ) -> None:
        with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
            mock_ping.return_value = (10.0, [TOOL_QUERY])
            result = await checker.check(server)

        assert result.schema_hash is not None
        assert len(result.schema_hash) == 16  # hash_tools returns 16-char hex

    async def test_down_status_on_timeout(
        self, server: MCPServer, checker: HealthChecker
    ) -> None:
        with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
            mock_ping.side_effect = MCPTimeoutError("timed out")
            result = await checker.check(server)

        assert result.status == ServerStatus.DOWN
        assert "timeout" in result.error  # type: ignore[operator]
        assert result.latency_ms is None

    async def test_down_status_on_connection_error(
        self, server: MCPServer, checker: HealthChecker
    ) -> None:
        with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
            mock_ping.side_effect = MCPConnectionError("connection refused")
            result = await checker.check(server)

        assert result.status == ServerStatus.DOWN
        assert "connection refused" in result.error  # type: ignore[operator]

    async def test_down_status_on_unexpected_error(
        self, server: MCPServer, checker: HealthChecker
    ) -> None:
        with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
            mock_ping.side_effect = RuntimeError("something exploded")
            result = await checker.check(server)

        assert result.status == ServerStatus.DOWN
        assert result.error is not None
        assert "unexpected error" in result.error

    async def test_result_always_has_checked_at(
        self, server: MCPServer, checker: HealthChecker
    ) -> None:
        with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
            mock_ping.side_effect = MCPTimeoutError("timeout")
            result = await checker.check(server)

        assert result.checked_at is not None

    async def test_latency_rounded_to_2dp(
        self, server: MCPServer, checker: HealthChecker
    ) -> None:
        with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
            mock_ping.return_value = (123.456789, [])
            result = await checker.check(server)

        assert result.latency_ms == 123.46


class TestHealthCheckerCheckMany:
    async def test_returns_result_per_server(self, checker: HealthChecker) -> None:
        servers = [
            MCPServer(name="srv1", transport=TransportType.STDIO, command="echo"),
            MCPServer(name="srv2", transport=TransportType.STDIO, command="echo"),
        ]
        with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
            mock_ping.return_value = (10.0, [TOOL_QUERY])
            results = await checker.check_many(servers)

        assert len(results) == 2
        assert {r.server_name for r in results} == {"srv1", "srv2"}

    async def test_partial_failure_doesnt_abort(self, checker: HealthChecker) -> None:
        servers = [
            MCPServer(name="ok", transport=TransportType.STDIO, command="echo"),
            MCPServer(name="fail", transport=TransportType.STDIO, command="echo"),
        ]

        async def side_effect(server: MCPServer) -> tuple:
            if server.name == "fail":
                raise MCPConnectionError("refused")
            return (10.0, [TOOL_QUERY])

        with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
            mock_ping.side_effect = side_effect
            results = await checker.check_many(servers)

        statuses = {r.server_name: r.status for r in results}
        assert statuses["ok"] == ServerStatus.UP
        assert statuses["fail"] == ServerStatus.DOWN

    async def test_empty_server_list(self, checker: HealthChecker) -> None:
        results = await checker.check_many([])
        assert results == []


class TestHashTools:
    def test_hash_is_stable(self) -> None:
        from langsight.health.transports import hash_tools

        tools = [TOOL_QUERY, TOOL_LIST]
        assert hash_tools(tools) == hash_tools(tools)

    def test_hash_order_independent(self) -> None:
        from langsight.health.transports import hash_tools

        assert hash_tools([TOOL_QUERY, TOOL_LIST]) == hash_tools([TOOL_LIST, TOOL_QUERY])

    def test_different_tools_different_hash(self) -> None:
        from langsight.health.transports import hash_tools

        other = ToolInfo(name="delete", description="Delete a row")
        assert hash_tools([TOOL_QUERY]) != hash_tools([other])

    def test_hash_length_is_16(self) -> None:
        from langsight.health.transports import hash_tools

        assert len(hash_tools([TOOL_QUERY])) == 16

    def test_empty_tools_has_stable_hash(self) -> None:
        from langsight.health.transports import hash_tools

        assert hash_tools([]) == hash_tools([])
