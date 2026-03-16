from __future__ import annotations

import pytest

from langsight.health.checker import HealthChecker
from langsight.models import MCPServer, ServerStatus


@pytest.mark.integration
async def test_health_check_postgres_mcp_returns_up(postgres_mcp_server: MCPServer) -> None:
    """postgres-mcp should respond UP with 5 tools when docker compose is running."""
    checker = HealthChecker()
    result = await checker.check(postgres_mcp_server)

    assert result.status == ServerStatus.UP, f"Expected UP, got {result.status}: {result.error}"
    assert result.latency_ms is not None
    assert result.latency_ms > 0
    assert result.tools_count == 5
    assert result.schema_hash is not None


@pytest.mark.integration
async def test_health_check_postgres_mcp_tool_names(postgres_mcp_server: MCPServer) -> None:
    """postgres-mcp must expose exactly the expected 5 tools."""
    checker = HealthChecker()
    result = await checker.check(postgres_mcp_server)

    tool_names = {t.name for t in result.tools}
    expected = {"query", "list_tables", "describe_table", "get_row_count", "get_schema_summary"}
    assert tool_names == expected


@pytest.mark.integration
async def test_health_check_schema_hash_stable(postgres_mcp_server: MCPServer) -> None:
    """Schema hash must be identical across two consecutive checks."""
    checker = HealthChecker()
    result1 = await checker.check(postgres_mcp_server)
    result2 = await checker.check(postgres_mcp_server)

    assert result1.schema_hash == result2.schema_hash
