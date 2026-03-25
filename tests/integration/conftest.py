from __future__ import annotations

import os
import socket
from pathlib import Path

import pytest

# Load .env so integration tests pick up CLICKHOUSE_PASSWORD, POSTGRES_PASSWORD etc.
_ENV_FILE = Path(__file__).parents[2] / ".env"
if _ENV_FILE.exists():
    for _line in _ENV_FILE.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

from langsight.models import MCPServer, TransportType

POSTGRES_MCP_PATH = "test-mcps/postgres-mcp/server.py"
_POSTGRES_MCP_HOST = "127.0.0.1"
_POSTGRES_MCP_PORT = 5432


def _postgres_mcp_reachable() -> bool:
    """Return True if the test-mcps postgres is reachable on localhost:5432."""
    try:
        with socket.create_connection((_POSTGRES_MCP_HOST, _POSTGRES_MCP_PORT), timeout=2):
            return True
    except OSError:
        return False


@pytest.fixture(autouse=False)
def require_postgres_mcp() -> None:
    """Skip the test if the test-mcps postgres is not reachable.

    Run `cd test-mcps && docker compose up -d` to start it locally.
    In CI this service is not available in the standard integration job.
    """
    if not _postgres_mcp_reachable():
        pytest.skip("test-mcps postgres not reachable — run: cd test-mcps && docker compose up -d")


@pytest.fixture
def postgres_mcp_server(require_postgres_mcp: None) -> MCPServer:
    """Real postgres-mcp server — requires docker compose up in test-mcps/."""
    return MCPServer(
        name="langsight-postgres",
        transport=TransportType.STDIO,
        command="uv",
        args=["run", "--project", "test-mcps/postgres-mcp", "python", POSTGRES_MCP_PATH],
        timeout_seconds=20,
    )
