"""
Unit tests for the url field added to server metadata.

Covers:
  StorageBackend.upsert_server_metadata()  — signature includes url
  PostgresBackend.upsert_server_metadata() — signature includes url, stores/returns url
  ServerMetadataUpdate                     — url field accepted, defaults to ""
  ServerMetadataResponse                   — url field present, defaults to ""

All DB calls are mocked — no Postgres connection required.
"""
from __future__ import annotations

import inspect
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from langsight.api.routers.servers import ServerMetadataResponse, ServerMetadataUpdate
from langsight.storage.base import StorageBackend
from langsight.storage.postgres import PostgresBackend


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_pool() -> MagicMock:
    """Return a minimal asyncpg pool mock."""
    pool = MagicMock()
    pool.execute = AsyncMock(return_value="OK")
    pool.fetchrow = AsyncMock(return_value=None)
    pool.fetch = AsyncMock(return_value=[])
    pool.close = AsyncMock()
    return pool


def _server_db_row(
    server_name: str = "test-mcp",
    url: str = "https://mcp.example.com/sse",
    transport: str = "sse",
    project_id: str | None = "proj-1",
) -> dict:
    """Simulate the dict asyncpg.fetchrow returns after an upsert."""
    now = datetime.now(UTC)
    return {
        "id": "row-abc",
        "server_name": server_name,
        "description": "",
        "owner": "",
        "tags": "[]",
        "transport": transport,
        "url": url,
        "runbook_url": "",
        "project_id": project_id,
        "created_at": now,
        "updated_at": now,
    }


# ===========================================================================
# StorageBackend protocol — signature verification
# ===========================================================================

class TestStorageBackendUpsertServerMetadataSignature:
    """The StorageBackend Protocol must declare url as a keyword parameter."""

    def test_upsert_server_metadata_has_url_parameter(self) -> None:
        """StorageBackend.upsert_server_metadata signature includes 'url'."""
        sig = inspect.signature(StorageBackend.upsert_server_metadata)
        assert "url" in sig.parameters, (
            "StorageBackend.upsert_server_metadata is missing the 'url' parameter"
        )

    def test_url_parameter_default_is_empty_string(self) -> None:
        """The default value for 'url' in StorageBackend.upsert_server_metadata is ''."""
        sig = inspect.signature(StorageBackend.upsert_server_metadata)
        url_param = sig.parameters["url"]
        assert url_param.default == "", (
            f"Expected default '' but got {url_param.default!r}"
        )

    def test_url_is_keyword_only(self) -> None:
        """'url' must be a keyword-only parameter (declared after *)."""
        sig = inspect.signature(StorageBackend.upsert_server_metadata)
        url_param = sig.parameters["url"]
        assert url_param.kind == inspect.Parameter.KEYWORD_ONLY, (
            "'url' must be keyword-only (declared after * in signature)"
        )


# ===========================================================================
# PostgresBackend — signature and unit-level behaviour
# ===========================================================================

class TestPostgresBackendUpsertServerMetadataSignature:
    """PostgresBackend.upsert_server_metadata must expose url in its signature."""

    def test_upsert_server_metadata_has_url_parameter(self) -> None:
        """PostgresBackend.upsert_server_metadata signature includes 'url'."""
        sig = inspect.signature(PostgresBackend.upsert_server_metadata)
        assert "url" in sig.parameters, (
            "PostgresBackend.upsert_server_metadata is missing the 'url' parameter"
        )

    def test_url_parameter_default_is_empty_string(self) -> None:
        """The 'url' parameter defaults to '' in PostgresBackend.upsert_server_metadata."""
        sig = inspect.signature(PostgresBackend.upsert_server_metadata)
        assert sig.parameters["url"].default == ""

    def test_url_is_keyword_only(self) -> None:
        """'url' must be keyword-only in PostgresBackend.upsert_server_metadata."""
        sig = inspect.signature(PostgresBackend.upsert_server_metadata)
        url_param = sig.parameters["url"]
        assert url_param.kind == inspect.Parameter.KEYWORD_ONLY


class TestPostgresBackendUpsertServerMetadataUrl:
    """PostgresBackend.upsert_server_metadata stores and returns the url value."""

    @pytest.fixture
    def pool(self) -> MagicMock:
        return _mock_pool()

    @pytest.fixture
    def backend(self, pool: MagicMock) -> PostgresBackend:
        return PostgresBackend(pool)

    @pytest.mark.asyncio
    async def test_upsert_stores_url_in_returned_dict(self, backend, pool) -> None:
        """The dict returned by upsert_server_metadata includes the url field."""
        expected_url = "https://mcp.example.com/sse"
        pool.fetchrow = AsyncMock(
            return_value=_server_db_row(url=expected_url)
        )

        result = await backend.upsert_server_metadata(
            server_name="test-mcp",
            url=expected_url,
            project_id="proj-1",
        )

        assert result["url"] == expected_url

    @pytest.mark.asyncio
    async def test_upsert_url_defaults_to_empty_string(self, backend, pool) -> None:
        """Calling upsert_server_metadata without url stores an empty string."""
        pool.fetchrow = AsyncMock(
            return_value=_server_db_row(url="")
        )

        result = await backend.upsert_server_metadata(
            server_name="test-mcp",
            project_id="proj-1",
        )

        assert result["url"] == ""

    @pytest.mark.asyncio
    async def test_upsert_passes_url_to_fetchrow(self, backend, pool) -> None:
        """The url value is included in the parameters sent to asyncpg fetchrow."""
        expected_url = "https://mcp.example.com/mcp"
        pool.fetchrow = AsyncMock(
            return_value=_server_db_row(url=expected_url)
        )

        await backend.upsert_server_metadata(
            server_name="test-mcp",
            url=expected_url,
            project_id="proj-1",
        )

        assert pool.fetchrow.called
        # The url must appear somewhere in the positional args passed to fetchrow
        call_args = pool.fetchrow.call_args[0]
        assert expected_url in call_args, (
            f"url value {expected_url!r} was not passed to fetchrow. "
            f"Got: {call_args}"
        )

    @pytest.mark.asyncio
    async def test_upsert_with_none_project_id_passes_url(self, backend, pool) -> None:
        """The global (no project_id) upsert path also persists the url field."""
        expected_url = "https://global-mcp.example.com"
        pool.fetchrow = AsyncMock(
            return_value=_server_db_row(url=expected_url, project_id=None)
        )

        result = await backend.upsert_server_metadata(
            server_name="global-mcp",
            url=expected_url,
            project_id=None,
        )

        assert result["url"] == expected_url

    @pytest.mark.asyncio
    async def test_upsert_preserves_other_fields_alongside_url(
        self, backend, pool
    ) -> None:
        """Setting url does not clobber transport, description, or other fields."""
        pool.fetchrow = AsyncMock(
            return_value=_server_db_row(
                server_name="rich-mcp",
                url="https://mcp.example.com",
                transport="streamable_http",
            )
        )

        result = await backend.upsert_server_metadata(
            server_name="rich-mcp",
            description="My server",
            transport="streamable_http",
            url="https://mcp.example.com",
            project_id="proj-1",
        )

        assert result["server_name"] == "rich-mcp"
        assert result["transport"] == "streamable_http"
        assert result["url"] == "https://mcp.example.com"


# ===========================================================================
# ServerMetadataUpdate Pydantic model
# ===========================================================================

class TestServerMetadataUpdateModel:
    """ServerMetadataUpdate must accept and expose a url field."""

    def test_url_field_accepted_and_stored(self) -> None:
        """ServerMetadataUpdate can be constructed with url='https://...'."""
        m = ServerMetadataUpdate(url="https://mcp.example.com")
        assert m.url == "https://mcp.example.com"

    def test_url_defaults_to_empty_string(self) -> None:
        """When url is omitted, it defaults to ''."""
        m = ServerMetadataUpdate()
        assert m.url == ""

    def test_url_accepts_empty_string(self) -> None:
        """url='' is a valid value (server without a URL, e.g. stdio)."""
        m = ServerMetadataUpdate(url="")
        assert m.url == ""

    def test_url_field_is_string_type(self) -> None:
        """The url field is a plain str (no AnyUrl validation — flexible for MCP URLs)."""
        m = ServerMetadataUpdate(url="https://custom-mcp.internal/endpoint")
        assert isinstance(m.url, str)

    def test_other_fields_still_work_alongside_url(self) -> None:
        """Setting url alongside transport and description works correctly."""
        m = ServerMetadataUpdate(
            description="My MCP",
            transport="sse",
            url="https://mcp.example.com/sse",
        )
        assert m.description == "My MCP"
        assert m.transport == "sse"
        assert m.url == "https://mcp.example.com/sse"


# ===========================================================================
# ServerMetadataResponse Pydantic model
# ===========================================================================

class TestServerMetadataResponseModel:
    """ServerMetadataResponse must include url and default it to ''."""

    def _minimal_row(self, **overrides) -> dict:
        now = datetime.now(UTC).isoformat()
        base = {
            "id": "row-1",
            "server_name": "test-mcp",
            "description": "",
            "owner": "",
            "tags": [],
            "transport": "",
            "url": "",
            "runbook_url": "",
            "project_id": None,
            "created_at": now,
            "updated_at": now,
        }
        base.update(overrides)
        return base

    def test_url_field_present_in_model(self) -> None:
        """ServerMetadataResponse has a 'url' field in its model_fields."""
        assert "url" in ServerMetadataResponse.model_fields

    def test_url_defaults_to_empty_string(self) -> None:
        """When url is absent from the source dict, it defaults to ''."""
        row = self._minimal_row()
        del row["url"]  # simulate an older row without the column
        m = ServerMetadataResponse(**row)
        assert m.url == ""

    def test_url_round_trips_correctly(self) -> None:
        """A url value round-trips through ServerMetadataResponse without mutation."""
        expected = "https://mcp.example.com/sse"
        m = ServerMetadataResponse(**self._minimal_row(url=expected))
        assert m.url == expected

    def test_url_empty_string_round_trips(self) -> None:
        """url='' is preserved and returned as '' (not None)."""
        m = ServerMetadataResponse(**self._minimal_row(url=""))
        assert m.url == ""
        assert m.url is not None
