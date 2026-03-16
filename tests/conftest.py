from __future__ import annotations

import pytest

from langsight.models import MCPServer, TransportType


@pytest.fixture
def stdio_server() -> MCPServer:
    return MCPServer(
        name="test-postgres",
        transport=TransportType.STDIO,
        command="uv",
        args=["run", "python", "test-mcps/postgres-mcp/server.py"],
        timeout_seconds=15,
    )


@pytest.fixture
def sse_server() -> MCPServer:
    return MCPServer(
        name="test-sse",
        transport=TransportType.SSE,
        url="http://localhost:8080/sse",
        timeout_seconds=5,
    )
