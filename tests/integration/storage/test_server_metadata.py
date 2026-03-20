"""
Integration tests for PostgresBackend — server_metadata and server_tools tables.

Requires a running Postgres instance (from docker compose up -d).
All tests are marked @pytest.mark.integration and skipped automatically
when Postgres is not reachable — see tests/conftest.py.

Run:
    docker compose up -d
    uv run pytest tests/integration/storage/test_server_metadata.py -m integration -v
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def pg(postgres_dsn: str, require_postgres: None):
    """Open a real PostgresBackend against the test Postgres instance."""
    from langsight.storage.postgres import PostgresBackend

    backend = await PostgresBackend.open(postgres_dsn)
    yield backend
    await backend.close()


def _unique_server() -> str:
    """Return a unique server name that will not clash between parallel test runs."""
    return f"test-server-{uuid.uuid4().hex[:10]}"


def _unique_project() -> str:
    return f"test-project-{uuid.uuid4().hex[:10]}"


# ---------------------------------------------------------------------------
# server_metadata tests
# ---------------------------------------------------------------------------

class TestUpsertAndGetServerMetadata:
    async def test_upsert_and_get_server_metadata(self, pg) -> None:
        """upsert_server_metadata persists a row; get_server_metadata retrieves it by name."""
        server_name = _unique_server()
        await pg.upsert_server_metadata(
            server_name=server_name,
            description="Primary Postgres MCP",
            owner="data-team",
            tags=["postgres", "production"],
            transport="stdio",
            runbook_url="https://wiki.example.com/postgres-mcp",
        )

        row = await pg.get_server_metadata(server_name)

        assert row is not None
        assert row["server_name"] == server_name
        assert row["description"] == "Primary Postgres MCP"
        assert row["owner"] == "data-team"
        assert row["transport"] == "stdio"
        assert row["runbook_url"] == "https://wiki.example.com/postgres-mcp"

    async def test_upsert_sets_created_at_and_updated_at(self, pg) -> None:
        """Both created_at and updated_at are populated by upsert."""
        server_name = _unique_server()
        await pg.upsert_server_metadata(server_name=server_name)

        row = await pg.get_server_metadata(server_name)

        assert row is not None
        assert row["created_at"] is not None
        assert row["updated_at"] is not None

    async def test_upsert_with_minimal_fields_uses_defaults(self, pg) -> None:
        """upsert_server_metadata with only server_name uses empty-string defaults."""
        server_name = _unique_server()
        await pg.upsert_server_metadata(server_name=server_name)

        row = await pg.get_server_metadata(server_name)

        assert row is not None
        assert row["description"] == ""
        assert row["owner"] == ""
        assert row["transport"] == ""
        assert row["runbook_url"] == ""
        assert row["project_id"] is None


class TestUpsertServerMetadataUpdatesExisting:
    async def test_upsert_server_metadata_updates_existing(self, pg) -> None:
        """A second upsert with the same server_name updates all mutable fields."""
        server_name = _unique_server()

        await pg.upsert_server_metadata(
            server_name=server_name,
            description="Initial description",
            owner="team-a",
            tags=["v1"],
            transport="stdio",
        )

        await pg.upsert_server_metadata(
            server_name=server_name,
            description="Updated description",
            owner="team-b",
            tags=["v1", "v2"],
            transport="sse",
        )

        row = await pg.get_server_metadata(server_name)

        assert row is not None
        assert row["description"] == "Updated description"
        assert row["owner"] == "team-b"
        assert row["transport"] == "sse"

    async def test_upsert_latest_wins_does_not_duplicate(self, pg) -> None:
        """Upserting the same server_name twice produces exactly one row."""
        server_name = _unique_server()

        for _ in range(3):
            await pg.upsert_server_metadata(
                server_name=server_name,
                description=f"Attempt {_}",
            )

        all_rows = await pg.get_all_server_metadata()
        matching = [r for r in all_rows if r["server_name"] == server_name]
        assert len(matching) == 1


class TestGetAllServerMetadataByProject:
    async def test_get_all_server_metadata_by_project(self, pg) -> None:
        """get_all_server_metadata with project_id returns only that project's servers."""
        from datetime import UTC, datetime
        from langsight.models import Project

        # Create two distinct projects
        pid_a = uuid.uuid4().hex
        pid_b = uuid.uuid4().hex
        now = datetime.now(UTC)

        await pg.create_project(
            Project(id=pid_a, name="proj-a", slug=f"proj-a-{pid_a[:8]}", created_by="test", created_at=now)
        )
        await pg.create_project(
            Project(id=pid_b, name="proj-b", slug=f"proj-b-{pid_b[:8]}", created_by="test", created_at=now)
        )

        server_a1 = _unique_server()
        server_a2 = _unique_server()
        server_b1 = _unique_server()

        await pg.upsert_server_metadata(server_name=server_a1, project_id=pid_a)
        await pg.upsert_server_metadata(server_name=server_a2, project_id=pid_a)
        await pg.upsert_server_metadata(server_name=server_b1, project_id=pid_b)

        rows_a = await pg.get_all_server_metadata(project_id=pid_a)
        rows_b = await pg.get_all_server_metadata(project_id=pid_b)

        server_names_a = {r["server_name"] for r in rows_a}
        server_names_b = {r["server_name"] for r in rows_b}

        assert server_a1 in server_names_a
        assert server_a2 in server_names_a
        assert server_b1 not in server_names_a

        assert server_b1 in server_names_b
        assert server_a1 not in server_names_b
        assert server_a2 not in server_names_b

    async def test_get_all_server_metadata_no_filter_returns_all(self, pg) -> None:
        """get_all_server_metadata() without project_id returns servers from all projects."""
        server_name = _unique_server()
        await pg.upsert_server_metadata(server_name=server_name)

        all_rows = await pg.get_all_server_metadata()
        names = {r["server_name"] for r in all_rows}
        assert server_name in names

    async def test_get_all_server_metadata_empty_project_returns_empty_list(self, pg) -> None:
        """A project with no servers returns an empty list, not None or an error."""
        rows = await pg.get_all_server_metadata(project_id="nonexistent-project-id")
        assert rows == []


class TestDeleteServerMetadata:
    async def test_delete_server_metadata(self, pg) -> None:
        """delete_server_metadata removes the row; get_server_metadata returns None afterward."""
        server_name = _unique_server()
        await pg.upsert_server_metadata(server_name=server_name, description="to be deleted")

        # Confirm it exists
        assert await pg.get_server_metadata(server_name) is not None

        deleted = await pg.delete_server_metadata(server_name)

        assert deleted is True
        assert await pg.get_server_metadata(server_name) is None

    async def test_delete_nonexistent_server_returns_false(self, pg) -> None:
        """Attempting to delete a server that does not exist returns False."""
        result = await pg.delete_server_metadata("server-that-never-existed")
        assert result is False

    async def test_delete_is_idempotent_on_second_call(self, pg) -> None:
        """Deleting the same server twice: first returns True, second returns False."""
        server_name = _unique_server()
        await pg.upsert_server_metadata(server_name=server_name)

        first = await pg.delete_server_metadata(server_name)
        second = await pg.delete_server_metadata(server_name)

        assert first is True
        assert second is False


# ---------------------------------------------------------------------------
# server_tools tests
# ---------------------------------------------------------------------------

class TestUpsertServerTools:
    async def test_upsert_server_tools(self, pg) -> None:
        """upsert_server_tools persists the tool list; row count equals tool count."""
        server_name = _unique_server()
        tools = [
            {"name": "query", "description": "Run SQL", "input_schema": {"type": "object"}},
            {"name": "list_tables", "description": "List all tables", "input_schema": {}},
            {"name": "describe_table", "description": "Describe a table", "input_schema": {}},
        ]

        await pg.upsert_server_tools(server_name, tools)

        rows = await pg.get_server_tools(server_name)
        assert len(rows) == 3

    async def test_upsert_empty_tools_list_stores_nothing(self, pg) -> None:
        """Upserting an empty tools list is a no-op — no rows created."""
        server_name = _unique_server()
        await pg.upsert_server_tools(server_name, [])

        rows = await pg.get_server_tools(server_name)
        assert rows == []

    async def test_upsert_server_tools_sets_first_seen_at(self, pg) -> None:
        """first_seen_at is populated on the first upsert."""
        server_name = _unique_server()
        await pg.upsert_server_tools(
            server_name, [{"name": "query", "description": "", "input_schema": {}}]
        )

        rows = await pg.get_server_tools(server_name)
        assert rows[0]["first_seen_at"] is not None


class TestUpsertServerToolsUpdatesDescription:
    async def test_upsert_server_tools_updates_description(self, pg) -> None:
        """Upserting the same tool twice updates description and last_seen_at."""
        server_name = _unique_server()

        await pg.upsert_server_tools(
            server_name,
            [{"name": "query", "description": "Original description", "input_schema": {}}],
        )
        first_rows = await pg.get_server_tools(server_name)
        first_last_seen = first_rows[0]["last_seen_at"]

        await pg.upsert_server_tools(
            server_name,
            [{"name": "query", "description": "Updated description", "input_schema": {}}],
        )
        second_rows = await pg.get_server_tools(server_name)

        assert second_rows[0]["description"] == "Updated description"
        # last_seen_at should be updated (or equal if same-second resolution)
        assert second_rows[0]["last_seen_at"] >= first_last_seen

    async def test_upsert_second_call_does_not_duplicate_tool(self, pg) -> None:
        """Upserting the same (server_name, tool_name) twice creates exactly one row."""
        server_name = _unique_server()
        tool = {"name": "query", "description": "Run SQL", "input_schema": {}}

        await pg.upsert_server_tools(server_name, [tool])
        await pg.upsert_server_tools(server_name, [tool])

        rows = await pg.get_server_tools(server_name)
        assert len(rows) == 1

    async def test_upsert_updates_input_schema(self, pg) -> None:
        """A second upsert with a different input_schema replaces the stored schema."""
        server_name = _unique_server()
        v1_schema = {"type": "object", "properties": {"sql": {"type": "string"}}}
        v2_schema = {"type": "object", "properties": {"sql": {"type": "string"}, "limit": {"type": "integer"}}}

        await pg.upsert_server_tools(
            server_name,
            [{"name": "query", "description": "Run SQL", "input_schema": v1_schema}],
        )
        await pg.upsert_server_tools(
            server_name,
            [{"name": "query", "description": "Run SQL", "input_schema": v2_schema}],
        )

        rows = await pg.get_server_tools(server_name)
        stored_schema = rows[0]["input_schema"]
        # asyncpg may return a dict or JSON string — normalise
        if isinstance(stored_schema, str):
            import json
            stored_schema = json.loads(stored_schema)
        assert "limit" in stored_schema.get("properties", {})


class TestGetServerTools:
    async def test_get_server_tools_returns_all_tools_ordered_by_name(self, pg) -> None:
        """get_server_tools returns all tools for a server, ordered alphabetically by tool_name."""
        server_name = _unique_server()
        tools = [
            {"name": "zebra_tool", "description": "Z", "input_schema": {}},
            {"name": "alpha_tool", "description": "A", "input_schema": {}},
            {"name": "mango_tool", "description": "M", "input_schema": {}},
        ]

        await pg.upsert_server_tools(server_name, tools)

        rows = await pg.get_server_tools(server_name)
        assert len(rows) == 3
        names = [r["tool_name"] for r in rows]
        assert names == sorted(names), "Tools must be returned ordered by tool_name"

    async def test_get_server_tools_returns_empty_for_unknown_server(self, pg) -> None:
        """get_server_tools on a server with no tools returns an empty list."""
        rows = await pg.get_server_tools("server-that-has-no-tools")
        assert rows == []

    async def test_get_server_tools_includes_correct_fields(self, pg) -> None:
        """Each returned row has the expected keys: server_name, tool_name, description, etc."""
        server_name = _unique_server()
        await pg.upsert_server_tools(
            server_name,
            [{"name": "query", "description": "Run SQL", "input_schema": {"type": "object"}}],
        )

        rows = await pg.get_server_tools(server_name)
        row = rows[0]

        assert "server_name" in row
        assert "tool_name" in row
        assert "description" in row
        assert "input_schema" in row
        assert "first_seen_at" in row
        assert "last_seen_at" in row
        assert row["server_name"] == server_name
        assert row["tool_name"] == "query"
        assert row["description"] == "Run SQL"

    async def test_get_server_tools_isolates_by_server_name(self, pg) -> None:
        """Tools for server A are not returned when querying server B."""
        server_a = _unique_server()
        server_b = _unique_server()

        await pg.upsert_server_tools(
            server_a,
            [{"name": "tool_for_a", "description": "", "input_schema": {}}],
        )
        await pg.upsert_server_tools(
            server_b,
            [{"name": "tool_for_b", "description": "", "input_schema": {}}],
        )

        rows_a = await pg.get_server_tools(server_a)
        rows_b = await pg.get_server_tools(server_b)

        assert all(r["server_name"] == server_a for r in rows_a)
        assert all(r["server_name"] == server_b for r in rows_b)
        assert rows_a[0]["tool_name"] == "tool_for_a"
        assert rows_b[0]["tool_name"] == "tool_for_b"
