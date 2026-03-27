from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from langsight.models import HealthCheckResult, ServerStatus
from langsight.sdk.models import ToolCallSpan, ToolCallStatus
from langsight.storage.clickhouse import ClickHouseBackend


def _result(name: str = "pg", status: ServerStatus = ServerStatus.UP) -> HealthCheckResult:
    return HealthCheckResult(
        server_name=name,
        status=status,
        latency_ms=42.0,
        tools_count=5,
        schema_hash="abc123def456ab12",
        checked_at=datetime(2026, 3, 17, 12, 0, 0, tzinfo=UTC),
    )


def _span(name: str = "pg", tool: str = "query") -> ToolCallSpan:
    now = datetime.now(UTC)
    return ToolCallSpan(
        server_name=name,
        tool_name=tool,
        started_at=now,
        ended_at=now,
        latency_ms=42.0,
        status=ToolCallStatus.SUCCESS,
    )


@pytest.fixture
def mock_client() -> MagicMock:
    client = MagicMock()
    client.command = AsyncMock()
    client.insert = AsyncMock()
    client.close = AsyncMock()

    # Default empty query result
    mock_result = MagicMock()
    mock_result.result_rows = []
    client.query = AsyncMock(return_value=mock_result)
    return client


@pytest.fixture
def backend(mock_client: MagicMock) -> ClickHouseBackend:
    return ClickHouseBackend(mock_client)


class TestClickHouseBackendOpen:
    async def test_creates_schema_on_open(self, mock_client: MagicMock) -> None:
        with patch(
            "clickhouse_connect.get_async_client",
            new_callable=AsyncMock,
            return_value=mock_client,
        ):
            await ClickHouseBackend.open()

        # Should execute DDL statements
        assert mock_client.command.call_count >= 3  # at least 3 DDL statements


class TestSaveHealthResult:
    async def test_inserts_to_correct_table(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        await backend.save_health_result(_result())
        mock_client.insert.assert_called_once()
        call_args = mock_client.insert.call_args
        assert call_args[0][0] == "mcp_health_results"

    async def test_inserts_correct_values(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        r = _result("my-server", ServerStatus.DOWN)
        await backend.save_health_result(r)
        rows = mock_client.insert.call_args[0][1]
        assert rows[0][0] == "my-server"
        assert rows[0][1] == "down"


class TestGetLatestSchemaHash:
    async def test_returns_none_when_empty(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        mock_client.query.return_value.result_rows = []
        result = await backend.get_latest_schema_hash("pg")
        assert result is None

    async def test_returns_hash_from_row(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        mock_client.query.return_value.result_rows = [("abc123def456",)]
        result = await backend.get_latest_schema_hash("pg")
        assert result == "abc123def456"

    async def test_uses_parameterized_query(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        await backend.get_latest_schema_hash("my-server")
        call_kwargs = mock_client.query.call_args[1]
        assert call_kwargs["parameters"]["server_name"] == "my-server"


class TestSaveSchemaSnapshot:
    async def test_inserts_to_schema_snapshots(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        await backend.save_schema_snapshot("pg", "abc123", 5)
        mock_client.insert.assert_called_once()
        assert mock_client.insert.call_args[0][0] == "mcp_schema_snapshots"


class TestGetHealthHistory:
    async def test_returns_empty_when_no_rows(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        mock_client.query.return_value.result_rows = []
        results = await backend.get_health_history("pg")
        assert results == []

    async def test_passes_limit_to_query(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        await backend.get_health_history("pg", limit=25)
        call_kwargs = mock_client.query.call_args[1]
        assert call_kwargs["parameters"]["limit"] == 25

    async def test_converts_rows_to_results(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        now = datetime(2026, 3, 17, 12, 0, 0, tzinfo=UTC)
        mock_client.query.return_value.result_rows = [
            ("pg", "up", 42.0, 5, "abc123", None, now)
        ]
        results = await backend.get_health_history("pg")
        assert len(results) == 1
        assert results[0].server_name == "pg"
        assert results[0].status == ServerStatus.UP
        assert results[0].latency_ms == 42.0


class TestSaveToolCallSpan:
    async def test_inserts_to_tool_calls_table(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        await backend.save_tool_call_span(_span())
        mock_client.insert.assert_called_once()
        assert mock_client.insert.call_args[0][0] == "mcp_tool_calls"

    async def test_batch_insert_empty_list(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        await backend.save_tool_call_spans([])
        mock_client.insert.assert_not_called()

    async def test_batch_insert_multiple_spans(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        spans = [_span(), _span(tool="list_tables")]
        await backend.save_tool_call_spans(spans)
        mock_client.insert.assert_called_once()
        rows = mock_client.insert.call_args[0][1]
        assert len(rows) == 2


class TestGetToolReliability:
    async def test_returns_empty_when_no_data(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        mock_client.query.return_value.result_rows = []
        results = await backend.get_tool_reliability(hours=24)
        assert results == []

    async def test_filters_by_server_name(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        await backend.get_tool_reliability(server_name="pg")
        query = mock_client.query.call_args[0][0]
        assert "server_name" in query

    async def test_returns_dict_per_tool(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        # Columns: server_name, tool_name, total_calls, success_calls, error_calls,
        #          timeout_calls, avg_latency_ms, max_latency_ms,
        #          p50_latency_ms, p95_latency_ms, p99_latency_ms,
        #          err_timeout, err_connection, err_params, err_server
        mock_client.query.return_value.result_rows = [
            ("pg", "query", 100, 95, 3, 2, 42.0, 500.0, 38.0, 95.0, 120.0, 1, 0, 1, 1)
        ]
        results = await backend.get_tool_reliability()
        assert len(results) == 1
        assert results[0]["server_name"] == "pg"
        assert results[0]["tool_name"] == "query"
        assert results[0]["success_rate_pct"] == 95.0
        assert results[0]["p50_latency_ms"] == 38.0
        assert results[0]["p95_latency_ms"] == 95.0
        assert results[0]["p99_latency_ms"] == 120.0
        assert results[0]["error_breakdown"] == {"timeout": 1, "connection": 0, "params": 1, "server": 1}


class TestSpanRowPayloads:
    """P5.1 — _span_row() serialises input_args and output_result correctly."""

    @pytest.mark.unit
    def test_span_row_includes_input_json(self, backend: ClickHouseBackend) -> None:
        """Span with input_args produces a JSON string in the input_json position."""
        import json

        span = _span()
        span = span.model_copy(update={"input_args": {"k": "v"}})
        row = backend._span_row(span)

        # input_json is at index 13 (matches _SPAN_COLUMNS order)
        col_index = ClickHouseBackend._SPAN_COLUMNS.index("input_json")
        assert row[col_index] == json.dumps({"k": "v"})

    @pytest.mark.unit
    def test_span_row_input_json_none_when_no_args(self, backend: ClickHouseBackend) -> None:
        """Span with input_args=None produces None in the input_json position."""
        span = _span()
        # _span() helper leaves input_args as None by default
        assert span.input_args is None
        row = backend._span_row(span)

        col_index = ClickHouseBackend._SPAN_COLUMNS.index("input_json")
        assert row[col_index] is None

    @pytest.mark.unit
    def test_span_row_output_json_stored(self, backend: ClickHouseBackend) -> None:
        """Span with output_result set passes the value through to output_json."""
        span = _span()
        span = span.model_copy(update={"output_result": '{"rows":1}'})
        row = backend._span_row(span)

        col_index = ClickHouseBackend._SPAN_COLUMNS.index("output_json")
        assert row[col_index] == '{"rows":1}'


class TestContextManager:
    async def test_close_called_on_exit(self, mock_client: MagicMock) -> None:
        backend = ClickHouseBackend(mock_client)
        async with backend:
            pass
        mock_client.close.assert_called_once()


class TestFactoryClickHouse:
    async def test_factory_dispatches_to_clickhouse(self) -> None:
        from langsight.config import StorageConfig
        from langsight.storage.factory import open_storage

        config = StorageConfig(
            mode="clickhouse",
            clickhouse_url="http://localhost:8123",
            clickhouse_database="langsight",
        )

        mock_backend = MagicMock(spec=ClickHouseBackend)
        with patch(
            "langsight.storage.clickhouse.ClickHouseBackend.open",
            new_callable=AsyncMock,
            return_value=mock_backend,
        ):
            backend = await open_storage(config)

        assert backend is mock_backend
