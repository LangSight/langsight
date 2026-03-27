from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from langsight.exceptions import MCPConnectionError, MCPHealthToolError, MCPTimeoutError
from langsight.health.checker import HealthChecker
from langsight.models import MCPServer, ServerStatus, ToolInfo, TransportType

TOOL_QUERY = ToolInfo(name="query", description="Execute SQL")
TOOL_LIST = ToolInfo(name="list_tables", description="List tables")


def _make_storage() -> MagicMock:
    """Build a storage mock that satisfies asyncio.iscoroutinefunction() checks.

    The checker calls asyncio.iscoroutinefunction() on upsert_server_tools and
    upsert_server_metadata before awaiting them.  A plain MagicMock attribute is
    NOT a coroutine function, so those guards silently skip the call.  Using
    AsyncMock makes iscoroutinefunction() return True.

    The SchemaTracker (constructed when storage is provided) also awaits:
      - get_latest_schema_hash  → returns None (first-run: no drift)
      - save_schema_snapshot
      - get_server_tools        → returns []
      - save_schema_drift_event (optional — guarded by getattr)

    All must be AsyncMock to avoid "MagicMock can't be used in 'await'" errors.
    """
    mock_storage = MagicMock()
    mock_storage.save_health_result = AsyncMock()
    mock_storage.upsert_server_metadata = AsyncMock()
    mock_storage.upsert_server_tools = AsyncMock()
    # SchemaTracker methods
    mock_storage.get_latest_schema_hash = AsyncMock(return_value=None)
    mock_storage.save_schema_snapshot = AsyncMock()
    mock_storage.get_server_tools = AsyncMock(return_value=[])
    mock_storage.save_schema_drift_event = AsyncMock()
    return mock_storage


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


class TestHealthCheckerMCPHealthToolError:
    """MCPHealthToolError from ping() must produce DEGRADED — not DOWN — results."""

    @pytest.fixture
    def server_with_health_tool(self) -> MCPServer:
        return MCPServer(
            name="datahub-mcp",
            transport=TransportType.STDIO,
            command="python server.py",
            health_tool="search_entities",
            health_tool_args={"query": "test", "limit": 1},
        )

    async def test_health_tool_error_yields_degraded_status(
        self, server_with_health_tool: MCPServer
    ) -> None:
        """DEGRADED (not DOWN) when the health probe tool returns an error."""
        checker = HealthChecker()
        with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
            mock_ping.side_effect = MCPHealthToolError(
                "health_tool 'search_entities' returned error: connection refused"
            )
            result = await checker.check(server_with_health_tool)

        assert result.status == ServerStatus.DEGRADED

    async def test_health_tool_error_not_down(
        self, server_with_health_tool: MCPServer
    ) -> None:
        """Status must be DEGRADED, never DOWN, for MCPHealthToolError."""
        checker = HealthChecker()
        with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
            mock_ping.side_effect = MCPHealthToolError("probe failed")
            result = await checker.check(server_with_health_tool)

        assert result.status != ServerStatus.DOWN

    async def test_health_tool_error_captures_error_message(
        self, server_with_health_tool: MCPServer
    ) -> None:
        """The error field must contain the exception message for dashboard display."""
        checker = HealthChecker()
        with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
            mock_ping.side_effect = MCPHealthToolError(
                "health_tool 'ping' not found in tools/list"
            )
            result = await checker.check(server_with_health_tool)

        assert result.error is not None
        assert "ping" in result.error or "health_tool" in result.error

    async def test_health_tool_error_result_saved_to_storage(
        self, server_with_health_tool: MCPServer
    ) -> None:
        """DEGRADED result must still be persisted when storage is wired."""
        mock_storage = _make_storage()
        checker = HealthChecker(storage=mock_storage)

        with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
            mock_ping.side_effect = MCPHealthToolError("backend unreachable")
            await checker.check(server_with_health_tool)

        mock_storage.save_health_result.assert_called_once()
        saved = mock_storage.save_health_result.call_args[0][0]
        assert saved.status == ServerStatus.DEGRADED

    async def test_health_tool_error_does_not_call_upsert_tools(
        self, server_with_health_tool: MCPServer
    ) -> None:
        """upsert_server_tools must NOT be called when the probe fails — no tools
        were successfully returned, so we must not overwrite the catalog with
        an empty or partial list.
        """
        mock_storage = _make_storage()
        checker = HealthChecker(storage=mock_storage)

        with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
            mock_ping.side_effect = MCPHealthToolError("backend unreachable")
            await checker.check(server_with_health_tool)

        mock_storage.upsert_server_tools.assert_not_called()

    async def test_health_tool_error_result_has_project_id(
        self, server_with_health_tool: MCPServer
    ) -> None:
        """project_id must be set on DEGRADED results for project-scoped dashboards."""
        checker = HealthChecker(project_id="proj-abc")
        with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
            mock_ping.side_effect = MCPHealthToolError("probe failed")
            result = await checker.check(server_with_health_tool)

        assert result.project_id == "proj-abc"


class TestHealthCheckerUpsertServerTools:
    """upsert_server_tools must be called on UP, skipped on DOWN."""

    @pytest.fixture
    def server(self) -> MCPServer:
        return MCPServer(name="pg", transport=TransportType.STDIO, command="echo")

    async def test_upsert_tools_called_on_up_result(self, server: MCPServer) -> None:
        """After a successful ping, upsert_server_tools is called at least once.

        The checker calls it directly AND the SchemaTracker may also call it on
        first-run baseline storage — so call_count can be 1 or 2 depending on
        whether this is a first-run vs. stable-hash scenario.
        """
        mock_storage = _make_storage()

        checker = HealthChecker(storage=mock_storage)
        with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
            mock_ping.return_value = (42.0, [TOOL_QUERY, TOOL_LIST])
            await checker.check(server)

        mock_storage.upsert_server_tools.assert_called()

    async def test_upsert_tools_called_with_correct_project_id(
        self, server: MCPServer
    ) -> None:
        """project_id passed to HealthChecker must be forwarded to upsert_server_tools."""
        mock_storage = _make_storage()

        checker = HealthChecker(storage=mock_storage, project_id="proj-xyz")
        with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
            mock_ping.return_value = (10.0, [TOOL_QUERY])
            await checker.check(server)

        kwargs = mock_storage.upsert_server_tools.call_args[1]
        assert kwargs.get("project_id") == "proj-xyz"

    async def test_upsert_tools_not_called_on_down_result(self, server: MCPServer) -> None:
        """upsert_server_tools must NOT be called when the server is DOWN."""
        mock_storage = _make_storage()

        checker = HealthChecker(storage=mock_storage)
        with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
            mock_ping.side_effect = MCPConnectionError("refused")
            await checker.check(server)

        mock_storage.upsert_server_tools.assert_not_called()

    async def test_upsert_tools_not_called_when_no_tools(self, server: MCPServer) -> None:
        """When ping returns an empty tools list, upsert_server_tools is skipped
        — the condition is `if tools:` in the checker, so empty list → no call.
        """
        mock_storage = _make_storage()

        checker = HealthChecker(storage=mock_storage)
        with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
            mock_ping.return_value = (5.0, [])  # empty tools
            await checker.check(server)

        mock_storage.upsert_server_tools.assert_not_called()

    async def test_upsert_tools_receives_serialisable_tool_dicts(
        self, server: MCPServer
    ) -> None:
        """Each dict passed to upsert_server_tools must have name, description,
        and input_schema (as JSON string) keys.
        """
        mock_storage = _make_storage()

        checker = HealthChecker(storage=mock_storage)
        with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
            mock_ping.return_value = (10.0, [TOOL_QUERY])
            await checker.check(server)

        tool_dicts = mock_storage.upsert_server_tools.call_args[0][1]
        assert len(tool_dicts) == 1
        assert tool_dicts[0]["name"] == "query"
        # input_schema is passed as a raw dict — upsert_server_tools encodes once
        assert isinstance(tool_dicts[0]["input_schema"], dict)


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
