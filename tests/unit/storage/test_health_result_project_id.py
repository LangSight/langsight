"""
Unit tests for project_id support in health check results.

Covers:
1. HealthCheckResult model — project_id defaults to empty string
2. ClickHouseBackend.get_health_history — project_id filter logic
3. _row_to_result — handles missing project_id column (backwards compat)
4. ClickHouseBackend.compare_sessions — forwards project_id to get_session_trace
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from langsight.models import HealthCheckResult, ServerStatus
from langsight.storage.clickhouse import ClickHouseBackend, _row_to_result

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
# HealthCheckResult model — project_id defaults to ""
# ---------------------------------------------------------------------------


class TestHealthCheckResultModel:
    def test_project_id_defaults_to_empty_string(self) -> None:
        """project_id field must default to '' when not provided."""
        result = HealthCheckResult(
            server_name="pg-mcp",
            status=ServerStatus.UP,
            latency_ms=42.0,
        )
        assert result.project_id == ""

    def test_project_id_can_be_set_explicitly(self) -> None:
        """project_id can be provided at construction time."""
        result = HealthCheckResult(
            server_name="pg-mcp",
            status=ServerStatus.UP,
            project_id="proj-abc",
        )
        assert result.project_id == "proj-abc"

    def test_project_id_accepts_empty_string_explicitly(self) -> None:
        """Explicitly passing empty string is identical to using the default."""
        result = HealthCheckResult(
            server_name="pg-mcp",
            status=ServerStatus.DOWN,
            project_id="",
        )
        assert result.project_id == ""

    def test_project_id_preserved_in_model_copy(self) -> None:
        """model_copy() preserves project_id unchanged."""
        result = HealthCheckResult(
            server_name="pg-mcp",
            status=ServerStatus.UP,
            project_id="tenant-42",
        )
        copy = result.model_copy()
        assert copy.project_id == "tenant-42"

    def test_all_other_fields_unaffected_by_project_id_default(self) -> None:
        """The project_id default does not interfere with other optional fields."""
        result = HealthCheckResult(
            server_name="s3-mcp",
            status=ServerStatus.DEGRADED,
            latency_ms=120.0,
            error="timeout",
        )
        assert result.server_name == "s3-mcp"
        assert result.status == ServerStatus.DEGRADED
        assert result.latency_ms == 120.0
        assert result.error == "timeout"
        assert result.project_id == ""


# ---------------------------------------------------------------------------
# _row_to_result — backwards compatibility (missing project_id column)
# ---------------------------------------------------------------------------


class TestRowToResultBackwardsCompat:
    def _make_row_without_project_id(self) -> tuple:
        """Simulate an old-schema row that has no project_id column."""
        return (
            "pg-mcp",         # server_name
            "up",             # status
            42.0,             # latency_ms
            5,                # tools_count
            "abc123",         # schema_hash
            None,             # error
            datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC),  # checked_at
            # NO project_id — 7 columns only
        )

    def _make_row_with_project_id(self, project_id: str = "proj-x") -> tuple:
        """Simulate a new-schema row that includes project_id."""
        return (
            "pg-mcp",         # server_name
            "up",             # status
            42.0,             # latency_ms
            5,                # tools_count
            "abc123",         # schema_hash
            None,             # error
            datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC),  # checked_at
            project_id,       # project_id
        )

    def test_row_without_project_id_defaults_to_empty_string(self) -> None:
        """Old-schema rows (no project_id column) must produce project_id=''."""
        row = self._make_row_without_project_id()
        result = _row_to_result(row)
        assert result.project_id == ""

    def test_row_with_project_id_preserves_value(self) -> None:
        """New-schema rows with project_id must preserve the exact value."""
        row = self._make_row_with_project_id("tenant-99")
        result = _row_to_result(row)
        assert result.project_id == "tenant-99"

    def test_row_with_null_project_id_defaults_to_empty_string(self) -> None:
        """A NULL/None in the project_id column must produce '' (not None)."""
        row = (
            "pg-mcp", "up", 42.0, 5, "abc123", None,
            datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC),
            None,  # project_id is NULL
        )
        result = _row_to_result(row)
        assert result.project_id == ""

    def test_row_to_result_maps_server_name(self) -> None:
        row = self._make_row_with_project_id()
        result = _row_to_result(row)
        assert result.server_name == "pg-mcp"

    def test_row_to_result_maps_status(self) -> None:
        row = self._make_row_with_project_id()
        result = _row_to_result(row)
        assert result.status == ServerStatus.UP

    def test_row_to_result_maps_latency_ms(self) -> None:
        row = self._make_row_with_project_id()
        result = _row_to_result(row)
        assert result.latency_ms == 42.0

    def test_row_to_result_maps_none_latency_to_none(self) -> None:
        row = (
            "pg-mcp", "down", None, 0, None, "timeout",
            datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC),
            "proj-x",
        )
        result = _row_to_result(row)
        assert result.latency_ms is None

    def test_row_to_result_adds_utc_tzinfo_to_naive_datetime(self) -> None:
        """checked_at without tzinfo must be treated as UTC."""
        naive_dt = datetime(2026, 3, 1, 12, 0, 0)  # no tzinfo
        row = ("pg-mcp", "up", 10.0, 2, None, None, naive_dt, "")
        result = _row_to_result(row)
        assert result.checked_at.tzinfo is not None
        assert result.checked_at.tzinfo == UTC


# ---------------------------------------------------------------------------
# get_health_history — project_id filter logic
# ---------------------------------------------------------------------------


class TestGetHealthHistoryProjectFilter:
    async def test_with_project_id_injects_project_filter_in_sql(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        """When project_id is provided, the SQL must include a project_id condition."""
        await backend.get_health_history("pg-mcp", project_id="proj-abc")

        call_args = mock_client.query.call_args
        sql: str = call_args[0][0]
        params: dict = call_args[1]["parameters"]

        assert "project_id" in sql
        assert params.get("project_id") == "proj-abc"

    async def test_with_project_id_sql_allows_global_results(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        """The project filter must also include project_id='' so CLI checks are visible."""
        await backend.get_health_history("pg-mcp", project_id="proj-abc")

        sql: str = mock_client.query.call_args[0][0]
        # The condition should allow empty project_id (global health checks from CLI)
        assert "project_id = ''" in sql or "project_id = {project_id" in sql

    async def test_without_project_id_no_project_filter_injected(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        """When project_id=None, the SQL must NOT add a project_id parameter."""
        await backend.get_health_history("pg-mcp", project_id=None)

        params: dict = mock_client.query.call_args[1]["parameters"]
        assert "project_id" not in params

    async def test_server_name_always_included_in_params(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        """server_name must always be passed as a query parameter."""
        await backend.get_health_history("s3-mcp", project_id="proj-x")

        params: dict = mock_client.query.call_args[1]["parameters"]
        assert params["server_name"] == "s3-mcp"

    async def test_limit_always_included_in_params(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        """limit must always be passed as a query parameter."""
        await backend.get_health_history("pg-mcp", limit=5, project_id=None)

        params: dict = mock_client.query.call_args[1]["parameters"]
        assert params["limit"] == 5

    async def test_returns_empty_list_when_no_rows(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        mock_client.query.return_value.result_rows = []
        result = await backend.get_health_history("pg-mcp", project_id="proj-z")
        assert result == []

    async def test_project_id_value_not_inlined_in_sql(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        """The project_id value must NOT appear literally in SQL (parameterised query guard)."""
        await backend.get_health_history("pg-mcp", project_id="'; DROP TABLE mcp_health_results; --")

        sql: str = mock_client.query.call_args[0][0]
        assert "DROP TABLE" not in sql


# ---------------------------------------------------------------------------
# compare_sessions — project_id forwarded to get_session_trace
# ---------------------------------------------------------------------------


class TestCompareSessionsProjectIdForwarding:
    async def test_project_id_forwarded_to_both_get_session_trace_calls(
        self, backend: ClickHouseBackend
    ) -> None:
        """compare_sessions must pass project_id to both get_session_trace calls."""
        with patch.object(
            backend, "get_session_trace", new_callable=AsyncMock, return_value=[]
        ) as mock_trace:
            await backend.compare_sessions("sess-a", "sess-b", project_id="proj-q")

        assert mock_trace.call_count == 2
        call_kwargs_list = [c[1] for c in mock_trace.call_args_list]
        for kwargs in call_kwargs_list:
            assert kwargs.get("project_id") == "proj-q"

    async def test_session_a_id_passed_correctly(
        self, backend: ClickHouseBackend
    ) -> None:
        """The first positional arg of the first get_session_trace call is session_a."""
        with patch.object(
            backend, "get_session_trace", new_callable=AsyncMock, return_value=[]
        ) as mock_trace:
            await backend.compare_sessions("session-alpha", "session-beta", project_id="proj-q")

        session_ids_called = [c[0][0] for c in mock_trace.call_args_list]
        assert "session-alpha" in session_ids_called

    async def test_session_b_id_passed_correctly(
        self, backend: ClickHouseBackend
    ) -> None:
        """The first positional arg of the second get_session_trace call is session_b."""
        with patch.object(
            backend, "get_session_trace", new_callable=AsyncMock, return_value=[]
        ) as mock_trace:
            await backend.compare_sessions("session-alpha", "session-beta", project_id="proj-q")

        session_ids_called = [c[0][0] for c in mock_trace.call_args_list]
        assert "session-beta" in session_ids_called

    async def test_none_project_id_forwarded_as_none(
        self, backend: ClickHouseBackend
    ) -> None:
        """project_id=None is forwarded as None, not converted to any other value."""
        with patch.object(
            backend, "get_session_trace", new_callable=AsyncMock, return_value=[]
        ) as mock_trace:
            await backend.compare_sessions("sess-a", "sess-b", project_id=None)

        for call in mock_trace.call_args_list:
            assert call[1].get("project_id") is None

    async def test_result_contains_both_session_ids(
        self, backend: ClickHouseBackend
    ) -> None:
        """The returned dict must contain the original session IDs."""
        with patch.object(
            backend, "get_session_trace", new_callable=AsyncMock, return_value=[]
        ):
            result = await backend.compare_sessions("sess-a", "sess-b", project_id=None)

        assert result["session_a"] == "sess-a"
        assert result["session_b"] == "sess-b"

    async def test_result_contains_diff_and_summary_keys(
        self, backend: ClickHouseBackend
    ) -> None:
        """The returned dict must always include diff and summary keys."""
        with patch.object(
            backend, "get_session_trace", new_callable=AsyncMock, return_value=[]
        ):
            result = await backend.compare_sessions("s1", "s2", project_id="proj-r")

        assert "diff" in result
        assert "summary" in result
