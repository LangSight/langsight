from __future__ import annotations

import pytest

from langsight.models import MCPServer, TransportType

POSTGRES_MCP_PATH = "test-mcps/postgres-mcp/server.py"


@pytest.fixture
def postgres_mcp_server() -> MCPServer:
    """Real postgres-mcp server — requires docker compose up in test-mcps/."""
    return MCPServer(
        name="langsight-postgres",
        transport=TransportType.STDIO,
        command="uv",
        args=["run", "--project", "test-mcps/postgres-mcp", "python", POSTGRES_MCP_PATH],
        timeout_seconds=20,
    )
