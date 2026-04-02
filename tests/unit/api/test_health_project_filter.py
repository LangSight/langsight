"""
Unit tests for health endpoint project_id filtering.

Security invariants proven here:

  1. GET /api/health/servers/{name} passes project_id to storage.get_health_history.
     Without it, server health data from any project is exposed to any caller.

  2. GET /api/health/servers/{name}/history passes project_id to
     storage.get_health_history with the limit parameter.

  3. A server that belongs to a different project returns 404, not 200.
     The router enforces visibility via _project_server_names before calling
     storage — the server name is not in the allowed set.

  4. A server from the same project returns 200 (baseline — no over-blocking).

All tests run offline — no DB, no Docker, no network.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml
from httpx import ASGITransport, AsyncClient

from langsight.api.main import create_app
from langsight.config import load_config
from langsight.models import HealthCheckResult, ServerStatus

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _result(
    name: str = "pg-mcp",
    status: ServerStatus = ServerStatus.UP,
    latency_ms: float = 55.0,
) -> HealthCheckResult:
    return HealthCheckResult(
        server_name=name,
        status=status,
        latency_ms=latency_ms,
        tools_count=3,
        schema_hash="abc123",
        error=None,
        checked_at=datetime(2026, 3, 20, 10, 0, 0, tzinfo=UTC),
    )


def _make_config_file(tmp_path: Path, server_names: list[str] | None = None) -> Path:
    cfg = tmp_path / ".langsight.yaml"
    servers = [
        {"name": n, "transport": "stdio", "command": f"python {n}.py"}
        for n in (server_names or ["pg-mcp"])
    ]
    cfg.write_text(yaml.dump({"servers": servers}))
    return cfg


def _base_storage(
    health_results: list[HealthCheckResult] | None = None,
    server_metadata: list[dict] | None = None,
) -> MagicMock:
    """Storage mock with auth disabled (no API keys)."""
    storage = MagicMock()
    storage.close = AsyncMock()
    storage.list_api_keys = AsyncMock(return_value=[])  # auth disabled
    storage.get_health_history = AsyncMock(return_value=health_results or [_result()])
    storage.get_all_server_metadata = AsyncMock(return_value=server_metadata or [])
    return storage


async def _make_client(
    tmp_path: Path,
    storage: MagicMock,
    server_names: list[str] | None = None,
) -> AsyncClient:
    config_file = _make_config_file(tmp_path, server_names)
    app = create_app(config_path=config_file)
    app.state.storage = storage
    app.state.config = load_config(config_file)
    app.state.api_keys = []  # auth disabled — focus on project filtering logic
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ---------------------------------------------------------------------------
# 1. GET /api/health/servers/{name} — project_id passed to storage
# ---------------------------------------------------------------------------


class TestGetServerHealthPassesProjectId:
    """get_health_history must receive the project_id query param."""

    async def test_get_server_health_calls_storage_with_project_id(
        self, tmp_path: Path
    ) -> None:
        """When project_id is supplied, storage.get_health_history must receive it."""
        storage = _base_storage(
            health_results=[_result("pg-mcp")],
            server_metadata=[{"server_name": "pg-mcp"}],
        )

        async with await _make_client(tmp_path, storage) as c:
            response = await c.get(
                "/api/health/servers/pg-mcp",
                params={"project_id": "project-alpha"},
            )

        assert response.status_code == 200
        storage.get_health_history.assert_called_with(
            "pg-mcp", limit=1, project_id="project-alpha"
        )

    async def test_get_server_health_project_id_none_when_not_supplied(
        self, tmp_path: Path
    ) -> None:
        """When no project_id query param is given (admin path), project_id=None
        is forwarded to storage."""
        storage = _base_storage(health_results=[_result("pg-mcp")])

        async with await _make_client(tmp_path, storage) as c:
            response = await c.get("/api/health/servers/pg-mcp")

        assert response.status_code == 200
        storage.get_health_history.assert_called_with(
            "pg-mcp", limit=1, project_id=None
        )

    async def test_get_server_health_with_project_id_passes_it_not_none(
        self, tmp_path: Path
    ) -> None:
        """Explicitly verify project_id is NOT coerced to None when provided."""
        storage = _base_storage(
            health_results=[_result("s3-mcp")],
            server_metadata=[{"server_name": "s3-mcp"}],
        )

        async with await _make_client(tmp_path, storage, server_names=["s3-mcp"]) as c:
            await c.get(
                "/api/health/servers/s3-mcp",
                params={"project_id": "tenant-007"},
            )

        call_kwargs = storage.get_health_history.call_args
        assert call_kwargs is not None
        assert call_kwargs.kwargs.get("project_id") == "tenant-007", (
            "project_id must be forwarded to storage, not coerced to None."
        )


# ---------------------------------------------------------------------------
# 2. GET /api/health/servers/{name}/history — project_id + limit passed
# ---------------------------------------------------------------------------


class TestGetServerHistoryPassesProjectId:
    """get_health_history for the /history endpoint must receive project_id and limit."""

    async def test_history_calls_storage_with_project_id(
        self, tmp_path: Path
    ) -> None:
        """storage.get_health_history receives the project_id from the query param."""
        storage = _base_storage(
            server_metadata=[{"server_name": "pg-mcp"}],
        )

        async with await _make_client(tmp_path, storage) as c:
            response = await c.get(
                "/api/health/servers/pg-mcp/history",
                params={"project_id": "project-beta", "limit": 15},
            )

        assert response.status_code == 200
        storage.get_health_history.assert_called_with(
            "pg-mcp", limit=15, project_id="project-beta"
        )

    async def test_history_default_limit_with_project_id(
        self, tmp_path: Path
    ) -> None:
        """Default limit (10) is used when not specified, but project_id is forwarded."""
        storage = _base_storage(
            server_metadata=[{"server_name": "pg-mcp"}],
        )

        async with await _make_client(tmp_path, storage) as c:
            await c.get(
                "/api/health/servers/pg-mcp/history",
                params={"project_id": "proj-x"},
            )

        storage.get_health_history.assert_called_with(
            "pg-mcp", limit=10, project_id="proj-x"
        )

    async def test_history_without_project_id_passes_none(
        self, tmp_path: Path
    ) -> None:
        """When no project_id is given, project_id=None is passed to storage."""
        storage = _base_storage()

        async with await _make_client(tmp_path, storage) as c:
            await c.get("/api/health/servers/pg-mcp/history?limit=25")

        storage.get_health_history.assert_called_with(
            "pg-mcp", limit=25, project_id=None
        )


# ---------------------------------------------------------------------------
# 3. Server from different project returns 404
# ---------------------------------------------------------------------------


class TestGetServerHealthProjectIsolation:
    """A server not visible to a project must return 404, not 200."""

    async def test_server_from_different_project_returns_404(
        self, tmp_path: Path
    ) -> None:
        """When project_id is provided and the server is not in that project's
        metadata, the endpoint must return 404.

        This tests the _project_server_names guard in the router.
        The storage mock returns NO server metadata for the project, so
        'pg-mcp' is not in the allowed set.
        """
        storage = _base_storage(
            health_results=[_result("pg-mcp")],
            # project-b has no servers → pg-mcp not visible to project-b
            server_metadata=[],
        )

        async with await _make_client(tmp_path, storage) as c:
            response = await c.get(
                "/api/health/servers/pg-mcp",
                params={"project_id": "project-b"},
            )

        assert response.status_code == 404, (
            f"Expected 404 when server is not visible to project-b, "
            f"got {response.status_code}. "
            "Server from a different project must never be exposed."
        )

    async def test_server_from_different_project_returns_404_on_history(
        self, tmp_path: Path
    ) -> None:
        """The /history endpoint must also return 404 for cross-project servers."""
        storage = _base_storage(
            health_results=[_result("pg-mcp")],
            server_metadata=[],  # server not visible to this project
        )

        async with await _make_client(tmp_path, storage) as c:
            response = await c.get(
                "/api/health/servers/pg-mcp/history",
                params={"project_id": "project-c"},
            )

        assert response.status_code == 404, (
            "History endpoint must return 404 when server not visible to project-c."
        )

    async def test_storage_not_called_for_foreign_project_server(
        self, tmp_path: Path
    ) -> None:
        """When a server is not in the project's allowed set, storage.get_health_history
        must NOT be called — the router rejects it before reaching storage."""
        storage = _base_storage(
            health_results=[_result("pg-mcp")],
            server_metadata=[],
        )

        async with await _make_client(tmp_path, storage) as c:
            await c.get(
                "/api/health/servers/pg-mcp",
                params={"project_id": "attacker-project"},
            )

        # get_health_history must not have been called after the 404 guard
        storage.get_health_history.assert_not_called()

    async def test_storage_not_called_for_foreign_project_server_history(
        self, tmp_path: Path
    ) -> None:
        """Same guard for the /history endpoint."""
        storage = _base_storage(
            health_results=[_result("pg-mcp")],
            server_metadata=[],
        )

        async with await _make_client(tmp_path, storage) as c:
            await c.get(
                "/api/health/servers/pg-mcp/history",
                params={"project_id": "attacker-project"},
            )

        storage.get_health_history.assert_not_called()


# ---------------------------------------------------------------------------
# 4. Same-project server returns 200 (baseline — no over-blocking)
# ---------------------------------------------------------------------------


class TestGetServerHealthSameProject:
    """Servers visible to the requesting project must still return 200."""

    async def test_server_from_same_project_returns_200(
        self, tmp_path: Path
    ) -> None:
        """When project_id matches and the server is in the project's metadata,
        the endpoint must return 200."""
        storage = _base_storage(
            health_results=[_result("pg-mcp")],
            # pg-mcp is visible to project-a
            server_metadata=[{"server_name": "pg-mcp"}],
        )

        async with await _make_client(tmp_path, storage) as c:
            response = await c.get(
                "/api/health/servers/pg-mcp",
                params={"project_id": "project-a"},
            )

        assert response.status_code == 200

    async def test_server_from_same_project_returns_correct_data(
        self, tmp_path: Path
    ) -> None:
        """Response body contains the correct server health data."""
        storage = _base_storage(
            health_results=[_result("pg-mcp", status=ServerStatus.UP, latency_ms=77.0)],
            server_metadata=[{"server_name": "pg-mcp"}],
        )

        async with await _make_client(tmp_path, storage) as c:
            response = await c.get(
                "/api/health/servers/pg-mcp",
                params={"project_id": "project-a"},
            )

        data = response.json()
        assert data["server_name"] == "pg-mcp"
        assert data["status"] == "up"
        assert data["latency_ms"] == pytest.approx(77.0)

    async def test_history_from_same_project_returns_200(
        self, tmp_path: Path
    ) -> None:
        """History endpoint returns 200 for a server visible to the project."""
        storage = _base_storage(
            health_results=[_result("pg-mcp")],
            server_metadata=[{"server_name": "pg-mcp"}],
        )

        async with await _make_client(tmp_path, storage) as c:
            response = await c.get(
                "/api/health/servers/pg-mcp/history",
                params={"project_id": "project-a"},
            )

        assert response.status_code == 200
        assert isinstance(response.json(), list)

    async def test_no_project_id_returns_200_for_admin(
        self, tmp_path: Path
    ) -> None:
        """When no project_id is given (admin), all servers are visible → 200."""
        storage = _base_storage(health_results=[_result("pg-mcp")])

        async with await _make_client(tmp_path, storage) as c:
            response = await c.get("/api/health/servers/pg-mcp")

        assert response.status_code == 200
