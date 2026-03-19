"""
Top-level pytest fixtures shared across all test suites.

Docker health checks
--------------------
Integration tests require a running Docker Compose stack:

    docker compose up -d

The `require_postgres` and `require_clickhouse` fixtures automatically
skip any test that depends on them when the service isn't reachable.
All tests under tests/integration/ depend on these fixtures.
"""
from __future__ import annotations

import os

import pytest

from langsight.models import MCPServer, TransportType

# ---------------------------------------------------------------------------
# Default DSNs — override via env vars when running against a custom instance
# ---------------------------------------------------------------------------

_POSTGRES_DSN = os.environ.get(
    "TEST_POSTGRES_URL",
    "postgresql://langsight:${POSTGRES_PASSWORD}@localhost:5432/langsight",
)
# Allow a plain test DSN without the env-var substitution
_POSTGRES_TEST_DSN = os.environ.get(
    "TEST_POSTGRES_URL",
    "postgresql://langsight:testpassword@localhost:5432/langsight",
)
_CLICKHOUSE_HOST = os.environ.get("TEST_CLICKHOUSE_HOST", "localhost")
_CLICKHOUSE_PORT = int(os.environ.get("TEST_CLICKHOUSE_PORT", "8123"))


# ---------------------------------------------------------------------------
# Docker service health checks
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def postgres_dsn() -> str:
    """Return the Postgres DSN used for integration tests.

    Override by setting TEST_POSTGRES_URL in the environment.
    Default: postgresql://langsight:testpassword@localhost:5432/langsight
    """
    return _POSTGRES_TEST_DSN


@pytest.fixture(scope="session")
def postgres_available(postgres_dsn: str) -> bool:
    """Return True if Postgres is reachable at the test DSN.

    Uses a plain TCP socket check — no event loop required, safe under
    any pytest-asyncio mode. If the port is open we trust Postgres is up.
    """
    import socket
    from urllib.parse import urlparse

    parsed = urlparse(postgres_dsn)
    host = parsed.hostname or "localhost"
    port = parsed.port or 5432
    try:
        with socket.create_connection((host, port), timeout=3):
            return True
    except OSError:
        return False


@pytest.fixture(scope="session")
def clickhouse_available() -> bool:
    """Return True if ClickHouse HTTP endpoint is reachable."""
    import urllib.request
    try:
        urllib.request.urlopen(
            f"http://{_CLICKHOUSE_HOST}:{_CLICKHOUSE_PORT}/ping", timeout=3
        )
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def require_postgres(postgres_available: bool) -> None:
    """Skip the entire session if Postgres is not available.

    Session-scoped so it can be used by module-scoped fixtures (e.g. the
    `pg` backend fixture in regression/integration tests).

    Usage:
        def test_something(require_postgres):
            ...  # only runs when 'docker compose up -d' is running
    """
    if not postgres_available:
        pytest.skip(
            "Postgres not available. Run: docker compose up -d\n"
            "Or set TEST_POSTGRES_URL to point at a running instance."
        )


@pytest.fixture(scope="session")
def require_clickhouse(clickhouse_available: bool) -> None:
    """Skip if ClickHouse is not available. Session-scoped."""
    if not clickhouse_available:
        pytest.skip(
            "ClickHouse not available. Run: docker compose up -d\n"
            "Or set TEST_CLICKHOUSE_HOST / TEST_CLICKHOUSE_PORT."
        )


@pytest.fixture(scope="session")
def require_all_services(require_postgres: None, require_clickhouse: None) -> None:
    """Skip unless both Postgres and ClickHouse are reachable."""


# ---------------------------------------------------------------------------
# MCP server fixtures (used by integration/e2e tests)
# ---------------------------------------------------------------------------

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
