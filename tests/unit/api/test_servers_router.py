"""
Unit tests for the servers API router.

Endpoints covered:
  GET  /api/servers/metadata                         → list_server_metadata
  PUT  /api/servers/metadata/{server_name}           → upsert_server_metadata
  GET  /api/servers/metadata/{server_name}           → get_server_metadata
  DELETE /api/servers/metadata/{server_name}         → delete_server_metadata
  POST /api/servers/{server_name}/tools              → record_tool_schemas
  GET  /api/servers/{server_name}/tools              → get_tool_schemas

All storage calls are mocked — no Postgres connection required.
Auth is disabled in tests by setting app.state.api_keys = [].
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

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    cfg = tmp_path / ".langsight.yaml"
    cfg.write_text(yaml.dump({"servers": [], "auth_disabled": True}))
    return cfg


@pytest.fixture
async def client(config_file: Path):
    """ASGI test client with a fully mocked storage backend.

    Auth is disabled (api_keys=[]) so every request goes through.
    Tests that need specific storage return values set them on mock_storage.
    """
    app = create_app(config_path=config_file)

    mock_storage = MagicMock()
    # Baseline stubs — prevent AttributeError from auth dependency checks
    mock_storage.list_api_keys = AsyncMock(return_value=[])
    mock_storage.get_health_history = AsyncMock(return_value=[])
    mock_storage.close = AsyncMock()

    app.state.storage = mock_storage
    app.state.config = load_config(config_file)
    app.state.api_keys = []  # disable auth for all tests in this module

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, mock_storage


def _server_row(
    server_name: str,
    description: str = "",
    owner: str = "",
    tags: list | None = None,
    transport: str = "",
    runbook_url: str = "",
    project_id: str | None = None,
) -> dict:
    """Return a fake server_metadata row that matches the DB shape."""
    now = datetime.now(UTC)
    return {
        "id": "abc123",
        "server_name": server_name,
        "description": description,
        "owner": owner,
        "tags": tags or [],
        "transport": transport,
        "runbook_url": runbook_url,
        "project_id": project_id,
        "created_at": now,
        "updated_at": now,
    }


def _tool_row(server_name: str, tool_name: str, description: str = "") -> dict:
    """Return a fake server_tools row that matches the DB shape."""
    now = datetime.now(UTC)
    return {
        "id": "tool-id-1",
        "server_name": server_name,
        "tool_name": tool_name,
        "description": description,
        "input_schema": {"type": "object"},
        "first_seen_at": now,
        "last_seen_at": now,
    }


# ---------------------------------------------------------------------------
# GET /api/servers/metadata
# ---------------------------------------------------------------------------

class TestListServerMetadata:
    async def test_list_server_metadata_empty(self, client) -> None:
        """Returns an empty list when storage has no server metadata."""
        c, mock_storage = client
        mock_storage.get_all_server_metadata = AsyncMock(return_value=[])

        response = await c.get("/api/servers/metadata")

        assert response.status_code == 200
        assert response.json() == []

    async def test_list_server_metadata_returns_all_rows(self, client) -> None:
        """Returns all server metadata rows from storage as a list."""
        c, mock_storage = client
        mock_storage.get_all_server_metadata = AsyncMock(return_value=[
            _server_row("postgres-mcp", description="Primary Postgres", transport="stdio"),
            _server_row("s3-mcp", description="S3 access", transport="sse"),
        ])

        response = await c.get("/api/servers/metadata")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        names = {r["server_name"] for r in data}
        assert names == {"postgres-mcp", "s3-mcp"}

    async def test_list_server_metadata_calls_storage_with_project_id(self, client) -> None:
        """?project_id query param is forwarded to storage.get_all_server_metadata."""
        c, mock_storage = client
        mock_storage.get_all_server_metadata = AsyncMock(return_value=[])

        await c.get("/api/servers/metadata?project_id=proj-1")

        mock_storage.get_all_server_metadata.assert_called_once()
        kwargs = mock_storage.get_all_server_metadata.call_args[1]
        assert kwargs["project_id"] == "proj-1"

    async def test_list_server_metadata_calls_storage_with_none_project_id_when_omitted(
        self, client
    ) -> None:
        """When project_id is omitted, None is forwarded to storage."""
        c, mock_storage = client
        mock_storage.get_all_server_metadata = AsyncMock(return_value=[])

        await c.get("/api/servers/metadata")

        mock_storage.get_all_server_metadata.assert_called_once()
        kwargs = mock_storage.get_all_server_metadata.call_args[1]
        assert kwargs["project_id"] is None

    async def test_list_server_metadata_response_shape(self, client) -> None:
        """Each item in the response has all required fields."""
        c, mock_storage = client
        mock_storage.get_all_server_metadata = AsyncMock(return_value=[
            _server_row("pg", description="Test", owner="team", tags=["prod"], transport="stdio"),
        ])

        response = await c.get("/api/servers/metadata")

        item = response.json()[0]
        for field in ("id", "server_name", "description", "owner", "tags",
                      "transport", "runbook_url", "project_id", "created_at", "updated_at"):
            assert field in item, f"Missing field: {field}"


# ---------------------------------------------------------------------------
# PUT /api/servers/metadata/{server_name}
# ---------------------------------------------------------------------------

class TestUpsertServerMetadata:
    async def test_upsert_server_metadata_creates(self, client) -> None:
        """PUT /api/servers/metadata/{name} returns the upserted row."""
        c, mock_storage = client
        mock_storage.upsert_server_metadata = AsyncMock(
            return_value=_server_row(
                "postgres-mcp",
                description="Primary Postgres MCP",
                owner="data-team",
                tags=["postgres", "production"],
                transport="stdio",
                runbook_url="https://wiki.example.com/pg",
            )
        )

        response = await c.put(
            "/api/servers/metadata/postgres-mcp",
            json={
                "description": "Primary Postgres MCP",
                "owner": "data-team",
                "tags": ["postgres", "production"],
                "transport": "stdio",
                "runbook_url": "https://wiki.example.com/pg",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["server_name"] == "postgres-mcp"
        assert data["description"] == "Primary Postgres MCP"
        assert data["owner"] == "data-team"
        assert data["transport"] == "stdio"

    async def test_upsert_server_metadata_calls_storage_with_correct_args(self, client) -> None:
        """Storage.upsert_server_metadata is called with all body fields and server_name."""
        c, mock_storage = client
        mock_storage.upsert_server_metadata = AsyncMock(
            return_value=_server_row("my-server")
        )

        await c.put(
            "/api/servers/metadata/my-server",
            json={
                "description": "My server",
                "owner": "eng",
                "tags": ["tag1"],
                "transport": "sse",
                "runbook_url": "https://runbook",
            },
        )

        mock_storage.upsert_server_metadata.assert_called_once()
        kwargs = mock_storage.upsert_server_metadata.call_args[1]
        assert kwargs["server_name"] == "my-server"
        assert kwargs["description"] == "My server"
        assert kwargs["owner"] == "eng"
        assert kwargs["tags"] == ["tag1"]
        assert kwargs["transport"] == "sse"
        assert kwargs["runbook_url"] == "https://runbook"

    async def test_upsert_server_metadata_with_defaults(self, client) -> None:
        """PUT with an empty body uses defaults; storage is still called."""
        c, mock_storage = client
        mock_storage.upsert_server_metadata = AsyncMock(
            return_value=_server_row("bare-server")
        )

        response = await c.put(
            "/api/servers/metadata/bare-server",
            json={},
        )

        assert response.status_code == 200
        mock_storage.upsert_server_metadata.assert_called_once()


# ---------------------------------------------------------------------------
# GET /api/servers/metadata/{server_name}
# ---------------------------------------------------------------------------

class TestGetServerMetadata:
    async def test_get_server_metadata_returns_row(self, client) -> None:
        """GET /api/servers/metadata/{name} returns the stored row."""
        c, mock_storage = client
        mock_storage.get_server_metadata = AsyncMock(
            return_value=_server_row("postgres-mcp", description="Primary Postgres")
        )

        response = await c.get("/api/servers/metadata/postgres-mcp")

        assert response.status_code == 200
        data = response.json()
        assert data["server_name"] == "postgres-mcp"
        assert data["description"] == "Primary Postgres"

    async def test_get_server_metadata_not_found(self, client) -> None:
        """GET /api/servers/metadata/{name} returns 404 when storage returns None."""
        c, mock_storage = client
        mock_storage.get_server_metadata = AsyncMock(return_value=None)

        response = await c.get("/api/servers/metadata/nonexistent-server")

        assert response.status_code == 404
        assert "nonexistent-server" in response.json()["detail"]

    async def test_get_server_metadata_calls_storage_with_name(self, client) -> None:
        """The server_name path segment is forwarded to storage.get_server_metadata."""
        c, mock_storage = client
        mock_storage.get_server_metadata = AsyncMock(
            return_value=_server_row("target-server")
        )

        await c.get("/api/servers/metadata/target-server")

        mock_storage.get_server_metadata.assert_called_once()
        pos_args = mock_storage.get_server_metadata.call_args[0]
        assert pos_args[0] == "target-server"

    async def test_get_server_metadata_passes_project_id(self, client) -> None:
        """?project_id is forwarded to storage.get_server_metadata."""
        c, mock_storage = client
        mock_storage.get_server_metadata = AsyncMock(
            return_value=_server_row("pg")
        )

        await c.get("/api/servers/metadata/pg?project_id=proj-xyz")

        kwargs = mock_storage.get_server_metadata.call_args[1]
        assert kwargs["project_id"] == "proj-xyz"


# ---------------------------------------------------------------------------
# DELETE /api/servers/metadata/{server_name}
# ---------------------------------------------------------------------------

class TestDeleteServerMetadata:
    async def test_delete_server_metadata_success(self, client) -> None:
        """DELETE /api/servers/metadata/{name} returns 204 when deleted."""
        c, mock_storage = client
        mock_storage.delete_server_metadata = AsyncMock(return_value=True)

        response = await c.delete("/api/servers/metadata/postgres-mcp")

        assert response.status_code == 204

    async def test_delete_server_metadata_not_found(self, client) -> None:
        """DELETE /api/servers/metadata/{name} returns 404 when storage returns False."""
        c, mock_storage = client
        mock_storage.delete_server_metadata = AsyncMock(return_value=False)

        response = await c.delete("/api/servers/metadata/ghost-server")

        assert response.status_code == 404
        assert "ghost-server" in response.json()["detail"]

    async def test_delete_server_metadata_calls_storage_with_name(self, client) -> None:
        """The path segment server_name is forwarded to storage.delete_server_metadata."""
        c, mock_storage = client
        mock_storage.delete_server_metadata = AsyncMock(return_value=True)

        await c.delete("/api/servers/metadata/to-be-deleted")

        mock_storage.delete_server_metadata.assert_called_once_with("to-be-deleted", project_id=None)


# ---------------------------------------------------------------------------
# POST /api/servers/{server_name}/tools
# ---------------------------------------------------------------------------

class TestRecordToolSchemas:
    async def test_record_tool_schemas_success(self, client) -> None:
        """POST /{name}/tools with a tool list returns {"upserted": N}."""
        c, mock_storage = client
        mock_storage.upsert_server_tools = AsyncMock(return_value=None)

        tools = [
            {"name": "query", "description": "Run SQL", "input_schema": {"type": "object"}},
            {"name": "list_tables", "description": "List tables", "input_schema": {}},
            {"name": "describe_table", "description": "Describe a table", "input_schema": {}},
        ]

        response = await c.post(
            "/api/servers/postgres-mcp/tools",
            json={"tools": tools},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["upserted"] == 3

    async def test_record_tool_schemas_empty_tools(self, client) -> None:
        """POST /{name}/tools with an empty tools list returns {"upserted": 0}."""
        c, mock_storage = client
        mock_storage.upsert_server_tools = AsyncMock(return_value=None)

        response = await c.post(
            "/api/servers/postgres-mcp/tools",
            json={"tools": []},
        )

        assert response.status_code == 200
        assert response.json() == {"upserted": 0}

    async def test_record_tool_schemas_empty_tools_skips_storage_call(self, client) -> None:
        """When tools is empty, upsert_server_tools is not called at all."""
        c, mock_storage = client
        mock_storage.upsert_server_tools = AsyncMock(return_value=None)

        await c.post("/api/servers/postgres-mcp/tools", json={"tools": []})

        mock_storage.upsert_server_tools.assert_not_called()

    async def test_record_tool_schemas_calls_storage_with_server_name(self, client) -> None:
        """Storage.upsert_server_tools is called with the server_name from the URL path."""
        c, mock_storage = client
        mock_storage.upsert_server_tools = AsyncMock(return_value=None)

        await c.post(
            "/api/servers/my-target-server/tools",
            json={"tools": [{"name": "t1", "description": "", "input_schema": {}}]},
        )

        call_args = mock_storage.upsert_server_tools.call_args
        assert call_args[0][0] == "my-target-server"

    async def test_record_tool_schemas_passes_tools_to_storage(self, client) -> None:
        """The tools list from the request body is forwarded to upsert_server_tools."""
        c, mock_storage = client
        mock_storage.upsert_server_tools = AsyncMock(return_value=None)

        tools = [{"name": "query", "description": "Run SQL", "input_schema": {}}]

        await c.post("/api/servers/pg/tools", json={"tools": tools})

        call_args = mock_storage.upsert_server_tools.call_args
        forwarded_tools = call_args[0][1]
        assert len(forwarded_tools) == 1
        assert forwarded_tools[0]["name"] == "query"

    async def test_record_tool_schemas_upserted_count_equals_tool_count(self, client) -> None:
        """The upserted count in the response equals the number of tools sent."""
        c, mock_storage = client
        mock_storage.upsert_server_tools = AsyncMock(return_value=None)

        for tool_count in [1, 5, 10]:
            tools = [
                {"name": f"tool_{i}", "description": "", "input_schema": {}}
                for i in range(tool_count)
            ]
            response = await c.post("/api/servers/pg/tools", json={"tools": tools})
            assert response.json()["upserted"] == tool_count


# ---------------------------------------------------------------------------
# GET /api/servers/{server_name}/tools
# ---------------------------------------------------------------------------

class TestGetToolSchemas:
    async def test_get_tool_schemas(self, client) -> None:
        """GET /{name}/tools returns the tool list from storage."""
        c, mock_storage = client
        mock_storage.get_server_tools = AsyncMock(return_value=[
            _tool_row("postgres-mcp", "query", "Run SQL"),
            _tool_row("postgres-mcp", "list_tables", "List tables"),
            _tool_row("postgres-mcp", "describe_table", "Describe a table"),
        ])

        response = await c.get("/api/servers/postgres-mcp/tools")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
        tool_names = {t["tool_name"] for t in data}
        assert tool_names == {"query", "list_tables", "describe_table"}

    async def test_get_tool_schemas_empty(self, client) -> None:
        """GET /{name}/tools returns an empty list when no tools are stored."""
        c, mock_storage = client
        mock_storage.get_server_tools = AsyncMock(return_value=[])

        response = await c.get("/api/servers/unknown-server/tools")

        assert response.status_code == 200
        assert response.json() == []

    async def test_get_tool_schemas_calls_storage_with_server_name(self, client) -> None:
        """The server_name from the URL path is forwarded to storage.get_server_tools."""
        c, mock_storage = client
        mock_storage.get_server_tools = AsyncMock(return_value=[])

        await c.get("/api/servers/target-server/tools")

        mock_storage.get_server_tools.assert_called_once_with("target-server", project_id=None)

    async def test_get_tool_schemas_response_shape(self, client) -> None:
        """Each tool in the response has the required fields."""
        c, mock_storage = client
        mock_storage.get_server_tools = AsyncMock(return_value=[
            _tool_row("pg", "query", "Run SQL"),
        ])

        response = await c.get("/api/servers/pg/tools")
        item = response.json()[0]

        for field in ("server_name", "tool_name", "description", "input_schema",
                      "first_seen_at", "last_seen_at"):
            assert field in item, f"Missing response field: {field}"

    async def test_get_tool_schemas_datetime_fields_are_strings(self, client) -> None:
        """first_seen_at and last_seen_at are serialised as strings in the response."""
        c, mock_storage = client
        mock_storage.get_server_tools = AsyncMock(return_value=[
            _tool_row("pg", "query"),
        ])

        response = await c.get("/api/servers/pg/tools")
        item = response.json()[0]

        assert isinstance(item["first_seen_at"], str)
        assert isinstance(item["last_seen_at"], str)

    async def test_get_tool_schemas_server_name_injected_when_missing(self, client) -> None:
        """If a row is missing server_name, the router injects it from the URL."""
        c, mock_storage = client
        row = _tool_row("pg", "query")
        del row["server_name"]  # simulate a row without server_name
        mock_storage.get_server_tools = AsyncMock(return_value=[row])

        response = await c.get("/api/servers/pg/tools")
        data = response.json()

        assert data[0]["server_name"] == "pg"
