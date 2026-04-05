"""
Unit tests for per-project MCP server isolation in the health router.

Covers:
  _auto_discover_servers()           — upsert new names only, degrade gracefully
  list_servers_health()              — project view vs global/admin view
  trigger_health_check()             — SSE-only filter when project is active

All storage calls and HealthChecker are mocked.
Auth is disabled (api_keys=[]) so every request goes through.
"""
from __future__ import annotations

import inspect
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml
from httpx import ASGITransport, AsyncClient

from langsight.api.main import create_app
from langsight.api.routers.health import _auto_discover_servers
from langsight.config import load_config
from langsight.models import HealthCheckResult, ServerStatus


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _health_result(
    name: str,
    status: ServerStatus = ServerStatus.UP,
    project_id: str = "",
) -> HealthCheckResult:
    return HealthCheckResult(
        server_name=name,
        status=status,
        latency_ms=10.0,
        checked_at=datetime.now(UTC),
        project_id=project_id,
    )


def _server_row(
    server_name: str,
    transport: str = "",
    url: str = "",
    project_id: str | None = None,
) -> dict:
    now = datetime.now(UTC)
    return {
        "id": "row-" + server_name,
        "server_name": server_name,
        "description": "",
        "owner": "",
        "tags": [],
        "transport": transport,
        "url": url,
        "runbook_url": "",
        "project_id": project_id,
        "created_at": now,
        "updated_at": now,
    }


# ---------------------------------------------------------------------------
# App fixture — wired with a config that has a global server
# ---------------------------------------------------------------------------

@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    """Config with one global server entry to verify it does NOT bleed into
    project views."""
    cfg = tmp_path / ".langsight.yaml"
    cfg.write_text(
        yaml.dump({
            "servers": [
                {"name": "global-srv", "transport": "stdio", "command": "echo"}
            ]
        })
    )
    return cfg


@pytest.fixture
async def client(config_file: Path):
    """ASGI client with a fully mocked storage backend. Auth is disabled."""
    app = create_app(config_path=config_file)

    mock_storage = MagicMock()
    # Baseline stubs required by the auth/dependency layer
    mock_storage.list_api_keys = AsyncMock(return_value=[])
    mock_storage.get_health_history = AsyncMock(return_value=[])
    mock_storage.close = AsyncMock()

    app.state.storage = mock_storage
    app.state.config = load_config(config_file)
    app.state.api_keys = []  # disable auth

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, mock_storage


# ===========================================================================
# _auto_discover_servers — unit tests (call the helper directly)
# ===========================================================================

class TestAutoDiscoverServers:
    """Direct unit tests for the _auto_discover_servers helper function."""

    @pytest.mark.asyncio
    async def test_upserts_only_new_names(self) -> None:
        """Servers already in server_metadata must NOT be upserted again.
        Only names present in spans but absent from metadata trigger an upsert.
        """
        storage = MagicMock()
        storage.get_distinct_span_server_names = AsyncMock(
            return_value={"server-a", "server-b"}
        )
        storage.get_all_server_metadata = AsyncMock(
            side_effect=[
                # First call (concurrent with span_names fetch)
                [{"server_name": "server-a"}],
                # Second call after upsert (refresh)
                [{"server_name": "server-a"}, {"server_name": "server-b"}],
            ]
        )
        storage.upsert_server_metadata = AsyncMock(
            return_value={"server_name": "server-b"}
        )

        await _auto_discover_servers(storage, project_id="proj-1")

        # Upsert called exactly once — only for server-b
        storage.upsert_server_metadata.assert_called_once()
        call_kwargs = storage.upsert_server_metadata.call_args[1]
        assert call_kwargs["server_name"] == "server-b"
        assert call_kwargs["project_id"] == "proj-1"

    @pytest.mark.asyncio
    async def test_does_not_upsert_when_all_already_registered(self) -> None:
        """When all span names already exist in metadata, upsert is never called."""
        storage = MagicMock()
        storage.get_distinct_span_server_names = AsyncMock(return_value={"server-a"})
        storage.get_all_server_metadata = AsyncMock(
            return_value=[{"server_name": "server-a"}]
        )
        storage.upsert_server_metadata = AsyncMock()

        result = await _auto_discover_servers(storage, project_id="proj-1")

        storage.upsert_server_metadata.assert_not_called()
        assert result == [{"server_name": "server-a"}]

    @pytest.mark.asyncio
    async def test_returns_empty_when_get_distinct_span_server_names_missing(self) -> None:
        """Storage without get_distinct_span_server_names must return [] cleanly,
        with no AttributeError or exception raised."""
        storage = MagicMock(spec=[])  # no methods — simulates bare storage

        result = await _auto_discover_servers(storage, project_id="proj-1")

        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_when_upsert_fn_missing(self) -> None:
        """Storage that has span names but no upsert_server_metadata returns []."""
        storage = MagicMock()
        storage.get_distinct_span_server_names = AsyncMock(return_value={"server-x"})
        # upsert_server_metadata is NOT available
        del storage.upsert_server_metadata

        result = await _auto_discover_servers(storage, project_id="proj-1")

        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_when_get_all_server_metadata_missing(self) -> None:
        """Storage missing get_all_server_metadata causes an early return of []."""
        storage = MagicMock()
        storage.get_distinct_span_server_names = AsyncMock(return_value={"server-x"})
        storage.upsert_server_metadata = AsyncMock()
        del storage.get_all_server_metadata

        result = await _auto_discover_servers(storage, project_id="proj-1")

        assert result == []

    @pytest.mark.asyncio
    async def test_upsert_passes_auto_discovered_description(self) -> None:
        """New servers are upserted with description='Auto-discovered from traces'."""
        storage = MagicMock()
        storage.get_distinct_span_server_names = AsyncMock(return_value={"fresh-server"})
        storage.get_all_server_metadata = AsyncMock(
            side_effect=[
                [],
                [{"server_name": "fresh-server"}],
            ]
        )
        storage.upsert_server_metadata = AsyncMock(
            return_value={"server_name": "fresh-server"}
        )

        await _auto_discover_servers(storage, project_id="proj-x")

        kwargs = storage.upsert_server_metadata.call_args[1]
        assert kwargs["description"] == ""  # empty — no noisy auto-discovered default

    @pytest.mark.asyncio
    async def test_returns_refreshed_metadata_after_upsert(self) -> None:
        """After upserting new names, the returned list is the post-upsert metadata."""
        storage = MagicMock()
        storage.get_distinct_span_server_names = AsyncMock(return_value={"new-srv"})
        fresh_meta = [{"server_name": "old-srv"}, {"server_name": "new-srv"}]
        storage.get_all_server_metadata = AsyncMock(
            side_effect=[
                [{"server_name": "old-srv"}],
                fresh_meta,
            ]
        )
        storage.upsert_server_metadata = AsyncMock(
            return_value={"server_name": "new-srv"}
        )

        result = await _auto_discover_servers(storage, project_id="proj-1")

        assert result == fresh_meta


# ===========================================================================
# GET /api/health/servers — project isolation
# ===========================================================================

class TestListServersHealthProjectIsolation:
    """list_servers_health() must scope results to the project when project_id
    is set, and must never leak global config.servers into a project view."""

    @pytest.mark.asyncio
    async def test_project_view_includes_auto_discovered_server_as_unknown(
        self, client
    ) -> None:
        """When project_id is set and storage returns a span name not in health
        history, the server should appear with UNKNOWN status.
        config.servers must NOT appear in the response.
        """
        c, mock_storage = client

        # Span has "analytics" — not yet in metadata
        mock_storage.get_distinct_span_server_names = AsyncMock(
            return_value={"analytics"}
        )
        # No existing metadata; after upsert returns one row
        mock_storage.get_all_server_metadata = AsyncMock(
            side_effect=[
                [],  # first call in _auto_discover_servers
                [_server_row("analytics", project_id="proj-1")],  # refresh
            ]
        )
        mock_storage.upsert_server_metadata = AsyncMock(
            return_value=_server_row("analytics", project_id="proj-1")
        )
        # No health history → ClickHouse ch_names empty
        mock_storage.get_distinct_health_server_names = AsyncMock(return_value=[])
        mock_storage.get_health_history = AsyncMock(return_value=[])

        response = await c.get("/api/health/servers?project_id=proj-1")

        assert response.status_code == 200
        names = {r["server_name"] for r in response.json()}
        assert "analytics" in names
        # global-srv from config.servers must NOT appear
        assert "global-srv" not in names

    @pytest.mark.asyncio
    async def test_auto_discovered_server_has_unknown_status_when_never_checked(
        self, client
    ) -> None:
        """A server registered via auto-discovery but never health-checked gets
        status=unknown (synthetic entry) in the response."""
        c, mock_storage = client

        mock_storage.get_distinct_span_server_names = AsyncMock(
            return_value={"new-mcp"}
        )
        mock_storage.get_all_server_metadata = AsyncMock(
            side_effect=[
                [],
                [_server_row("new-mcp", project_id="proj-1")],
            ]
        )
        mock_storage.upsert_server_metadata = AsyncMock(
            return_value=_server_row("new-mcp", project_id="proj-1")
        )
        mock_storage.get_distinct_health_server_names = AsyncMock(return_value=[])
        mock_storage.get_health_history = AsyncMock(return_value=[])

        response = await c.get("/api/health/servers?project_id=proj-1")

        data = response.json()
        assert len(data) >= 1
        entry = next((r for r in data if r["server_name"] == "new-mcp"), None)
        assert entry is not None
        assert entry["status"] == "unknown"

    @pytest.mark.asyncio
    async def test_global_admin_view_includes_config_servers(self, client) -> None:
        """When no project_id is passed, config.servers must appear in the response
        even when ClickHouse has no health data for them."""
        c, mock_storage = client

        # No ClickHouse data
        mock_storage.get_distinct_health_server_names = AsyncMock(return_value=[])
        mock_storage.get_health_history = AsyncMock(return_value=[])

        response = await c.get("/api/health/servers")

        assert response.status_code == 200
        names = {r["server_name"] for r in response.json()}
        # global-srv comes from config.servers in the fixture config_file
        assert "global-srv" in names

    @pytest.mark.asyncio
    async def test_global_admin_view_does_not_call_auto_discover(
        self, client
    ) -> None:
        """_auto_discover_servers must NOT be called when project_id is absent."""
        c, mock_storage = client

        mock_storage.get_distinct_health_server_names = AsyncMock(return_value=[])
        mock_storage.get_health_history = AsyncMock(return_value=[])
        # get_distinct_span_server_names should never be touched
        mock_storage.get_distinct_span_server_names = AsyncMock(return_value=set())

        await c.get("/api/health/servers")

        mock_storage.get_distinct_span_server_names.assert_not_called()

    @pytest.mark.asyncio
    async def test_project_view_returns_empty_when_no_spans_and_no_metadata(
        self, client
    ) -> None:
        """A project with zero trace spans and zero registered servers returns []."""
        c, mock_storage = client

        mock_storage.get_distinct_span_server_names = AsyncMock(return_value=set())
        mock_storage.get_all_server_metadata = AsyncMock(return_value=[])
        mock_storage.upsert_server_metadata = AsyncMock()
        mock_storage.get_distinct_health_server_names = AsyncMock(return_value=[])
        mock_storage.get_health_history = AsyncMock(return_value=[])

        response = await c.get("/api/health/servers?project_id=empty-proj")

        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_project_view_shows_server_with_real_health_result(
        self, client
    ) -> None:
        """A server with a stored health result appears with that result's status."""
        c, mock_storage = client

        mock_storage.get_distinct_span_server_names = AsyncMock(return_value=set())
        mock_storage.get_all_server_metadata = AsyncMock(
            return_value=[_server_row("checked-mcp", project_id="proj-1")]
        )
        mock_storage.upsert_server_metadata = AsyncMock()
        # ch_names returns this server
        mock_storage.get_distinct_health_server_names = AsyncMock(
            return_value=["checked-mcp"]
        )
        mock_storage.get_health_history = AsyncMock(
            return_value=[_health_result("checked-mcp", ServerStatus.UP, "proj-1")]
        )

        response = await c.get("/api/health/servers?project_id=proj-1")

        data = response.json()
        entry = next((r for r in data if r["server_name"] == "checked-mcp"), None)
        assert entry is not None
        assert entry["status"] == "up"


# ===========================================================================
# POST /api/health/check — project trigger filters to SSE/HTTP only
# ===========================================================================

class TestTriggerHealthCheckProjectFilter:
    """trigger_health_check with project_id must only pass SSE/streamable_http
    servers to HealthChecker.check_many. stdio servers with no url are excluded."""

    @pytest.mark.asyncio
    async def test_only_sse_server_passed_to_checker(self, client) -> None:
        """One stdio (no url) and one SSE server in metadata → only SSE is checked."""
        c, mock_storage = client

        mock_storage.get_all_server_metadata = AsyncMock(
            return_value=[
                _server_row("stdio-srv", transport="stdio", url=""),
                _server_row("sse-srv", transport="sse", url="https://mcp.example.com/sse"),
            ]
        )

        sse_result = _health_result("sse-srv", ServerStatus.UP, "proj-1")

        with patch(
            "langsight.api.routers.health.HealthChecker"
        ) as MockChecker:
            instance = MockChecker.return_value
            instance.check_many = AsyncMock(return_value=[sse_result])

            response = await c.post("/api/health/check?project_id=proj-1")

        assert response.status_code == 200
        checked = MockChecker.call_args
        assert checked is not None

        # Verify check_many received exactly the SSE server
        check_many_call = instance.check_many.call_args
        servers_passed = check_many_call[0][0]
        assert len(servers_passed) == 1
        assert servers_passed[0].name == "sse-srv"
        assert servers_passed[0].transport == "sse"

    @pytest.mark.asyncio
    async def test_streamable_http_server_passed_to_checker(self, client) -> None:
        """streamable_http transport with url is included in checkable servers."""
        c, mock_storage = client

        mock_storage.get_all_server_metadata = AsyncMock(
            return_value=[
                _server_row(
                    "http-srv",
                    transport="streamable_http",
                    url="https://mcp.example.com/mcp",
                ),
            ]
        )

        http_result = _health_result("http-srv", ServerStatus.UP, "proj-1")

        with patch("langsight.api.routers.health.HealthChecker") as MockChecker:
            instance = MockChecker.return_value
            instance.check_many = AsyncMock(return_value=[http_result])

            response = await c.post("/api/health/check?project_id=proj-1")

        assert response.status_code == 200
        servers_passed = instance.check_many.call_args[0][0]
        assert len(servers_passed) == 1
        assert servers_passed[0].name == "http-srv"

    @pytest.mark.asyncio
    async def test_no_checkable_servers_returns_empty_list(self, client) -> None:
        """When all project servers are stdio with no url, returns [] without
        calling HealthChecker at all."""
        c, mock_storage = client

        mock_storage.get_all_server_metadata = AsyncMock(
            return_value=[
                _server_row("stdio-only", transport="stdio", url=""),
            ]
        )

        with patch("langsight.api.routers.health.HealthChecker") as MockChecker:
            response = await c.post("/api/health/check?project_id=proj-1")

        assert response.status_code == 200
        assert response.json() == []
        MockChecker.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_checkable_servers_when_metadata_is_empty(self, client) -> None:
        """When the project has no registered servers at all, returns []."""
        c, mock_storage = client

        mock_storage.get_all_server_metadata = AsyncMock(return_value=[])

        with patch("langsight.api.routers.health.HealthChecker") as MockChecker:
            response = await c.post("/api/health/check?project_id=proj-1")

        assert response.status_code == 200
        assert response.json() == []
        MockChecker.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_checkable_servers_when_get_all_server_metadata_missing(
        self, client
    ) -> None:
        """When storage has no get_all_server_metadata, returns [] without error."""
        c, mock_storage = client
        del mock_storage.get_all_server_metadata

        response = await c.post("/api/health/check?project_id=proj-1")

        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_global_admin_uses_config_servers(self, client) -> None:
        """Without project_id, trigger_health_check uses config.servers (the
        global admin path)."""
        c, mock_storage = client

        global_result = _health_result("global-srv", ServerStatus.UP)

        with patch("langsight.api.routers.health.HealthChecker") as MockChecker:
            instance = MockChecker.return_value
            instance.check_many = AsyncMock(return_value=[global_result])

            response = await c.post("/api/health/check")

        assert response.status_code == 200
        # HealthChecker must have been called (config has one server)
        MockChecker.assert_called_once()
        instance.check_many.assert_called_once()

    @pytest.mark.asyncio
    async def test_sse_server_without_url_is_excluded(self, client) -> None:
        """An SSE server row with an empty url string is not checkable and must
        be excluded from check_many even if transport='sse'."""
        c, mock_storage = client

        mock_storage.get_all_server_metadata = AsyncMock(
            return_value=[
                # transport=sse but URL is empty — can't ping it
                _server_row("sse-no-url", transport="sse", url=""),
            ]
        )

        with patch("langsight.api.routers.health.HealthChecker") as MockChecker:
            response = await c.post("/api/health/check?project_id=proj-1")

        assert response.status_code == 200
        assert response.json() == []
        MockChecker.assert_not_called()

    @pytest.mark.asyncio
    async def test_checker_constructed_with_project_id(self, client) -> None:
        """When project_id is active, HealthChecker must be constructed with that
        project_id so results are stored under the correct project scope."""
        c, mock_storage = client

        mock_storage.get_all_server_metadata = AsyncMock(
            return_value=[
                _server_row("sse-srv", transport="sse", url="https://mcp.example.com"),
            ]
        )

        with patch("langsight.api.routers.health.HealthChecker") as MockChecker:
            instance = MockChecker.return_value
            instance.check_many = AsyncMock(return_value=[])

            await c.post("/api/health/check?project_id=my-project")

        init_kwargs = MockChecker.call_args[1]
        assert init_kwargs.get("project_id") == "my-project"


# ===========================================================================
# Regression tests
# ===========================================================================

class TestRegressionGlobalServerBleed:
    """Regression: global config.servers must never appear in a project-scoped
    list_servers_health response, even when the project has no servers."""

    @pytest.mark.regression
    @pytest.mark.asyncio
    async def test_global_config_servers_not_visible_in_project_view(
        self, client
    ) -> None:
        """Regression: config.servers=['personal-mcp'] must NOT bleed into a
        project-scoped view when that project has no registered servers and no
        span names. (Bug: global names were union-merged without project guard.)
        """
        c, mock_storage = client

        # Project has no trace spans and no server_metadata rows
        mock_storage.get_distinct_span_server_names = AsyncMock(return_value=set())
        mock_storage.get_all_server_metadata = AsyncMock(return_value=[])
        mock_storage.upsert_server_metadata = AsyncMock()
        mock_storage.get_distinct_health_server_names = AsyncMock(return_value=[])
        mock_storage.get_health_history = AsyncMock(return_value=[])

        # The config fixture has global-srv in config.servers
        response = await c.get("/api/health/servers?project_id=proj-1")

        assert response.status_code == 200
        names = {r["server_name"] for r in response.json()}
        # global-srv is from config.servers — must NOT appear under proj-1
        assert "global-srv" not in names
        # Result must be empty (no project servers)
        assert len(response.json()) == 0
