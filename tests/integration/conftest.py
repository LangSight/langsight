from __future__ import annotations

import os
import socket
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Integration test isolation
# ---------------------------------------------------------------------------
# Integration tests need to hit the real API, so we clear LANGSIGHT_TEST_MODE
# (set by the top-level conftest.py for unit tests). Instead we use a
# dedicated project_id="__test_auto_cleanup__" so all test data lands in
# one isolated project and can be deleted after the session.
os.environ.pop("LANGSIGHT_TEST_MODE", None)

# Dedicated project ID for all integration test data.
# All spans, sessions, and agent records created during integration tests
# use this project. The cleanup fixture below deletes it at session end.
INTEGRATION_TEST_PROJECT_ID = "__test_auto_cleanup__"


@pytest.fixture(scope="session", autouse=True)
async def cleanup_integration_test_data():
    """Delete all data for the integration test project after the test session.

    This prevents test runs from accumulating dummy sessions and projects
    in the dashboard. Uses a dedicated project ID so cleanup is safe.
    """
    yield  # let all integration tests run first

    # Clean up test data
    _api_url = os.environ.get("LANGSIGHT_URL", "http://localhost:8000")
    _api_key = os.environ.get("LANGSIGHT_API_KEY", "")
    try:
        import httpx

        headers = {"Content-Type": "application/json"}
        if _api_key:
            headers["X-API-Key"] = _api_key
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.delete(
                f"{_api_url}/api/projects/{INTEGRATION_TEST_PROJECT_ID}",
                headers=headers,
            )
            if resp.status_code in (200, 204, 404):
                pass  # deleted or already gone — both are fine
            else:
                print(
                    f"\n[conftest] Warning: could not clean up test project "
                    f"(status={resp.status_code}). "
                    f"Delete project '{INTEGRATION_TEST_PROJECT_ID}' manually."
                )
    except Exception as exc:  # noqa: BLE001
        print(f"\n[conftest] Warning: test cleanup failed: {exc}")

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
_POSTGRES_MCP_PORT = 5433  # test-mcps/docker-compose.yml maps 127.0.0.1:5433→5432


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
    """Real postgres-mcp server — requires docker compose up in test-mcps/.

    test-mcps/docker-compose.yml maps host 5433 → container 5432, so the
    subprocess must connect on port 5433 (not the server.py default of 5432).
    """
    return MCPServer(
        name="langsight-postgres",
        transport=TransportType.STDIO,
        command="uv",
        args=["run", "--project", "test-mcps/postgres-mcp", "python", POSTGRES_MCP_PATH],
        env={"POSTGRES_PORT": "5433"},
        timeout_seconds=20,
    )
