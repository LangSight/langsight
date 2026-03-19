"""
Unit tests for Phase 10 multi-tenancy: project_id filters in ClickHouseBackend.

Verifies that:
- get_cost_call_counts(project_id="p1") includes AND project_id = {project_id:String} in SQL
- get_session_trace(session_id, project_id="p1") includes project_id filter
- get_agent_sessions(project_id="p1") includes project_id filter
- All three pass project_id=None cleanly (no filter injected)

The ClickHouse client is mocked — no real ClickHouse connection is made.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from langsight.storage.clickhouse import ClickHouseBackend


@pytest.fixture
def mock_client() -> MagicMock:
    client = MagicMock()
    client.command = AsyncMock()
    client.insert = AsyncMock()
    client.close = AsyncMock()

    mock_result = MagicMock()
    mock_result.result_rows = []
    client.query = AsyncMock(return_value=mock_result)
    return client


@pytest.fixture
def backend(mock_client: MagicMock) -> ClickHouseBackend:
    return ClickHouseBackend(mock_client)


# ---------------------------------------------------------------------------
# get_cost_call_counts — project_id filter
# ---------------------------------------------------------------------------

class TestGetCostCallCountsProjectFilter:
    async def test_includes_project_id_filter_in_sql(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        """When project_id is provided, the WHERE clause must include it."""
        await backend.get_cost_call_counts(hours=24, project_id="p1")

        call_args = mock_client.query.call_args
        sql: str = call_args[0][0]
        params: dict = call_args[1]["parameters"]

        assert "project_id" in sql
        assert "{project_id:String}" in sql
        assert params["project_id"] == "p1"

    async def test_no_project_id_filter_when_none(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        """When project_id=None, the WHERE clause must NOT include a project_id condition."""
        await backend.get_cost_call_counts(hours=24, project_id=None)

        call_args = mock_client.query.call_args
        sql: str = call_args[0][0]
        params: dict = call_args[1]["parameters"]

        # project_id param should not be in the parameters dict
        assert "project_id" not in params

    async def test_hours_param_always_included(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        """The hours parameter is always passed regardless of project_id."""
        await backend.get_cost_call_counts(hours=48, project_id="p1")

        params = mock_client.query.call_args[1]["parameters"]
        assert params["hours"] == 48

    async def test_returns_empty_list_when_no_rows(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        mock_client.query.return_value.result_rows = []
        result = await backend.get_cost_call_counts(hours=24, project_id="p1")
        assert result == []

    async def test_project_id_filter_not_injected_via_string_concat(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        """The project_id value must NOT be inlined into the SQL string (SQL injection guard)."""
        await backend.get_cost_call_counts(hours=24, project_id="'; DROP TABLE mcp_tool_calls; --")

        sql: str = mock_client.query.call_args[0][0]
        # The raw value should never appear literally in the SQL
        assert "DROP TABLE" not in sql
        assert "'; DROP TABLE" not in sql


# ---------------------------------------------------------------------------
# get_session_trace — project_id filter
# ---------------------------------------------------------------------------

class TestGetSessionTraceProjectFilter:
    async def test_includes_project_id_filter_in_sql(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        """When project_id is provided, the WHERE clause must include it."""
        await backend.get_session_trace("sess-abc", project_id="p1")

        call_args = mock_client.query.call_args
        sql: str = call_args[0][0]
        params: dict = call_args[1]["parameters"]

        assert "project_id" in sql
        assert "{project_id:String}" in sql
        assert params["project_id"] == "p1"
        assert params["session_id"] == "sess-abc"

    async def test_no_project_id_filter_when_none(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        """When project_id=None, the WHERE clause must not include project_id."""
        await backend.get_session_trace("sess-abc", project_id=None)

        params: dict = mock_client.query.call_args[1]["parameters"]
        assert "project_id" not in params
        assert params["session_id"] == "sess-abc"

    async def test_always_filters_by_session_id(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        """session_id filter must be present regardless of project_id."""
        await backend.get_session_trace("my-session", project_id="tenant-x")

        sql: str = mock_client.query.call_args[0][0]
        params: dict = mock_client.query.call_args[1]["parameters"]

        assert "session_id" in sql
        assert params["session_id"] == "my-session"

    async def test_returns_empty_list_when_no_spans_found(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        mock_client.query.return_value.result_rows = []
        result = await backend.get_session_trace("nonexistent", project_id="p1")
        assert result == []

    async def test_project_id_filter_not_inlined_in_sql(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        """The project_id must be passed as a parameter, not inlined into SQL."""
        await backend.get_session_trace("sess", project_id="tenant-with-quotes'")

        sql: str = mock_client.query.call_args[0][0]
        assert "tenant-with-quotes'" not in sql


# ---------------------------------------------------------------------------
# get_agent_sessions — project_id filter (pre-existing, verify still works)
# ---------------------------------------------------------------------------

class TestGetAgentSessionsProjectFilter:
    async def test_includes_project_id_filter_in_sql(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        """Pre-Phase-10 filter — still works after Phase 10 changes."""
        await backend.get_agent_sessions(hours=24, project_id="p1")

        call_args = mock_client.query.call_args
        sql: str = call_args[0][0]
        params: dict = call_args[1]["parameters"]

        assert "project_id" in sql
        assert "{project_id:String}" in sql
        assert params["project_id"] == "p1"

    async def test_no_project_id_filter_when_none(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        await backend.get_agent_sessions(hours=24, project_id=None)

        params: dict = mock_client.query.call_args[1]["parameters"]
        assert "project_id" not in params

    async def test_agent_name_filter_combined_with_project_id(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        """Both agent_name and project_id filters can coexist in a single query."""
        await backend.get_agent_sessions(hours=24, agent_name="my-agent", project_id="p2")

        params: dict = mock_client.query.call_args[1]["parameters"]
        assert params["agent_name"] == "my-agent"
        assert params["project_id"] == "p2"

    async def test_hours_always_included(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        await backend.get_agent_sessions(hours=72, project_id="p1")

        params: dict = mock_client.query.call_args[1]["parameters"]
        assert params["hours"] == 72

    async def test_returns_empty_list_when_no_rows(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        mock_client.query.return_value.result_rows = []
        result = await backend.get_agent_sessions(hours=24, project_id="p1")
        assert result == []
