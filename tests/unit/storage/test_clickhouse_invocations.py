"""Unit tests for ClickHouseBackend.get_server_invocation_stats.

All ClickHouse calls are mocked — no running ClickHouse instance needed.
"""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from langsight.storage.clickhouse import ClickHouseBackend


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


def _make_row(
    server_name: str,
    last_called_at: datetime,
    last_call_status: str,
    total_calls: int,
    success_calls: int,
) -> tuple:
    """Build a raw ClickHouse result_row in the order the query returns columns."""
    return (server_name, last_called_at, last_call_status, total_calls, success_calls)


# ---------------------------------------------------------------------------
# Return shape
# ---------------------------------------------------------------------------


class TestGetServerInvocationStatsReturnShape:
    """Verify the returned dicts have the correct keys and value types."""

    async def test_empty_result_when_no_rows(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        """Returns an empty list when ClickHouse has no matching rows."""
        mock_client.query.return_value.result_rows = []
        rows = await backend.get_server_invocation_stats()
        assert rows == []

    async def test_returns_list_of_dicts(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        """Each element in the result is a dict."""
        now = datetime.now(UTC)
        mock_client.query.return_value.result_rows = [
            _make_row("pg-mcp", now, "success", 10, 9),
        ]
        rows = await backend.get_server_invocation_stats()
        assert isinstance(rows, list)
        assert isinstance(rows[0], dict)

    async def test_result_contains_server_name(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        now = datetime.now(UTC)
        mock_client.query.return_value.result_rows = [
            _make_row("postgres-mcp", now, "success", 5, 5),
        ]
        rows = await backend.get_server_invocation_stats()
        assert rows[0]["server_name"] == "postgres-mcp"

    async def test_result_contains_last_called_at(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        now = datetime(2026, 3, 25, 10, 0, 0, tzinfo=UTC)
        mock_client.query.return_value.result_rows = [
            _make_row("pg", now, "success", 1, 1),
        ]
        rows = await backend.get_server_invocation_stats()
        assert "last_called_at" in rows[0]
        # Must be ISO-format string
        assert rows[0]["last_called_at"] == now.isoformat()

    async def test_result_contains_last_call_status(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        now = datetime.now(UTC)
        mock_client.query.return_value.result_rows = [
            _make_row("pg", now, "error", 3, 1),
        ]
        rows = await backend.get_server_invocation_stats()
        assert rows[0]["last_call_status"] == "error"

    async def test_result_contains_total_calls(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        now = datetime.now(UTC)
        mock_client.query.return_value.result_rows = [
            _make_row("pg", now, "success", 42, 40),
        ]
        rows = await backend.get_server_invocation_stats()
        assert rows[0]["total_calls"] == 42

    async def test_result_contains_success_rate_pct(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        now = datetime.now(UTC)
        mock_client.query.return_value.result_rows = [
            _make_row("pg", now, "success", 10, 8),
        ]
        rows = await backend.get_server_invocation_stats()
        assert "success_rate_pct" in rows[0]


# ---------------------------------------------------------------------------
# last_call_ok logic
# ---------------------------------------------------------------------------


class TestGetServerInvocationStatsLastCallOk:
    """last_call_ok must be True only when last_call_status == 'success'."""

    async def test_last_call_ok_true_when_status_success(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        now = datetime.now(UTC)
        mock_client.query.return_value.result_rows = [
            _make_row("pg", now, "success", 5, 5),
        ]
        rows = await backend.get_server_invocation_stats()
        assert rows[0]["last_call_ok"] is True

    async def test_last_call_ok_false_when_status_error(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        now = datetime.now(UTC)
        mock_client.query.return_value.result_rows = [
            _make_row("pg", now, "error", 5, 3),
        ]
        rows = await backend.get_server_invocation_stats()
        assert rows[0]["last_call_ok"] is False

    async def test_last_call_ok_false_when_status_timeout(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        now = datetime.now(UTC)
        mock_client.query.return_value.result_rows = [
            _make_row("pg", now, "timeout", 2, 1),
        ]
        rows = await backend.get_server_invocation_stats()
        assert rows[0]["last_call_ok"] is False

    async def test_last_call_ok_false_when_status_unknown(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        """Any status that is not exactly 'success' must yield last_call_ok=False."""
        now = datetime.now(UTC)
        mock_client.query.return_value.result_rows = [
            _make_row("pg", now, "anything_else", 1, 0),
        ]
        rows = await backend.get_server_invocation_stats()
        assert rows[0]["last_call_ok"] is False


# ---------------------------------------------------------------------------
# success_rate_pct calculation
# ---------------------------------------------------------------------------


class TestGetServerInvocationStatsSuccessRate:
    async def test_success_rate_100_when_all_succeed(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        now = datetime.now(UTC)
        mock_client.query.return_value.result_rows = [
            _make_row("pg", now, "success", 10, 10),
        ]
        rows = await backend.get_server_invocation_stats()
        assert rows[0]["success_rate_pct"] == 100.0

    async def test_success_rate_0_when_none_succeed(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        now = datetime.now(UTC)
        mock_client.query.return_value.result_rows = [
            _make_row("pg", now, "error", 5, 0),
        ]
        rows = await backend.get_server_invocation_stats()
        assert rows[0]["success_rate_pct"] == 0.0

    async def test_success_rate_partial(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        now = datetime.now(UTC)
        mock_client.query.return_value.result_rows = [
            _make_row("pg", now, "success", 4, 3),
        ]
        rows = await backend.get_server_invocation_stats()
        assert rows[0]["success_rate_pct"] == pytest.approx(75.0, abs=0.1)

    async def test_success_rate_no_div_by_zero_when_total_zero(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        """total=0 must not raise ZeroDivisionError (guarded by `or 1`)."""
        now = datetime.now(UTC)
        mock_client.query.return_value.result_rows = [
            _make_row("pg", now, "success", 0, 0),
        ]
        rows = await backend.get_server_invocation_stats()
        # Should not raise; value can be 0.0 or 100.0 depending on guard
        assert isinstance(rows[0]["success_rate_pct"], float)


# ---------------------------------------------------------------------------
# project_id filter
# ---------------------------------------------------------------------------


class TestGetServerInvocationStatsProjectFilter:
    async def test_no_project_id_does_not_add_filter(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        """When project_id is None, the query must not include project_id parameter."""
        await backend.get_server_invocation_stats(project_id=None)
        call_kwargs = mock_client.query.call_args[1]
        assert "project_id" not in call_kwargs.get("parameters", {})

    async def test_project_id_is_added_to_query_parameters(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        """When project_id is set, it must appear in the query parameters dict."""
        await backend.get_server_invocation_stats(project_id="proj-abc")
        call_kwargs = mock_client.query.call_args[1]
        assert call_kwargs.get("parameters", {}).get("project_id") == "proj-abc"

    async def test_project_id_filter_appears_in_query_string(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        """The raw SQL must include 'project_id' when a filter is requested."""
        await backend.get_server_invocation_stats(project_id="proj-xyz")
        sql = mock_client.query.call_args[0][0]
        assert "project_id" in sql

    async def test_no_project_id_query_string_excludes_filter(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        """Without project_id, no project_id placeholder appears in the raw SQL."""
        await backend.get_server_invocation_stats(project_id=None)
        sql = mock_client.query.call_args[0][0]
        # The filter string is only injected when project_id is provided
        assert "{project_id:String}" not in sql


# ---------------------------------------------------------------------------
# hours parameter
# ---------------------------------------------------------------------------


class TestGetServerInvocationStatsHours:
    async def test_hours_defaults_to_168(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        """Default look-back must be 168 hours (7 days)."""
        await backend.get_server_invocation_stats()
        params = mock_client.query.call_args[1].get("parameters", {})
        assert params.get("hours") == 168

    async def test_hours_custom_value_forwarded(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        await backend.get_server_invocation_stats(hours=24)
        params = mock_client.query.call_args[1].get("parameters", {})
        assert params.get("hours") == 24


# ---------------------------------------------------------------------------
# last_called_at edge cases
# ---------------------------------------------------------------------------


class TestGetServerInvocationStatsLastCalledAt:
    async def test_last_called_at_none_when_row_timestamp_none(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        """When ClickHouse returns None for last_called_at, the dict value is None."""
        mock_client.query.return_value.result_rows = [
            _make_row("pg", None, "success", 1, 1),
        ]
        rows = await backend.get_server_invocation_stats()
        assert rows[0]["last_called_at"] is None

    async def test_multiple_servers_all_included(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        """All rows returned by ClickHouse must appear in the result."""
        now = datetime.now(UTC)
        mock_client.query.return_value.result_rows = [
            _make_row("server-a", now, "success", 10, 10),
            _make_row("server-b", now, "error", 5, 2),
            _make_row("server-c", now, "success", 1, 1),
        ]
        rows = await backend.get_server_invocation_stats()
        assert len(rows) == 3
        names = {r["server_name"] for r in rows}
        assert names == {"server-a", "server-b", "server-c"}
