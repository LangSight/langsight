"""
Unit tests for monitoring router — NULL-coercion validators and endpoint behaviour.

Regression suite for: dashboard all-charts-blank bug (2026-04-04).
Root cause: ClickHouse sum(input_tokens) returns NULL when all rows are NULL;
Pydantic v2 raises ValidationError rather than applying int = 0 default when
the field value is explicitly None.

Fix: field_validator(mode="before") coercing None → 0 on TimeseriesBucket,
ModelMetrics, and ToolMetrics.

All tests here are unit tests — no external services required.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from langsight.api.main import create_app
from langsight.api.routers.monitoring import (
    ErrorCategory,
    ModelMetrics,
    TimeseriesBucket,
    ToolMetrics,
)
from langsight.config import load_config

import yaml


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    cfg = tmp_path / ".langsight.yaml"
    cfg.write_text(
        yaml.dump({"servers": [], "storage": {"mode": "clickhouse"}})
    )
    return cfg


@pytest.fixture
def mock_storage() -> MagicMock:
    """Storage mock with all monitoring methods present (returning empty lists)."""
    storage = MagicMock()
    storage.get_health_history = AsyncMock(return_value=[])
    storage.close = AsyncMock()
    storage.get_monitoring_timeseries = AsyncMock(return_value=[])
    storage.get_monitoring_models = AsyncMock(return_value=[])
    storage.get_monitoring_tools = AsyncMock(return_value=[])
    storage.get_monitoring_trends = AsyncMock(return_value={})
    storage.get_error_breakdown = AsyncMock(return_value=[])
    storage.list_model_pricing = AsyncMock(return_value=[])
    return storage


@pytest.fixture
async def client(config_file: Path, mock_storage: MagicMock):
    app = create_app(config_path=config_file)
    app.state.storage = mock_storage
    app.state.config = load_config(config_file)
    app.state.auth_disabled = True
    app.state.config_path = config_file
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c, mock_storage


# ---------------------------------------------------------------------------
# TimeseriesBucket — validator unit tests
# ---------------------------------------------------------------------------


class TestTimeseriesBucketValidators:
    """Verify coerce_none_int and coerce_none_float on TimeseriesBucket."""

    def test_none_input_tokens_coerced_to_zero(self) -> None:
        bucket = TimeseriesBucket(bucket="2026-04-04T00:00:00Z", input_tokens=None)
        assert bucket.input_tokens == 0

    def test_none_output_tokens_coerced_to_zero(self) -> None:
        bucket = TimeseriesBucket(bucket="2026-04-04T00:00:00Z", output_tokens=None)
        assert bucket.output_tokens == 0

    def test_none_agents_coerced_to_zero(self) -> None:
        bucket = TimeseriesBucket(bucket="2026-04-04T00:00:00Z", agents=None)
        assert bucket.agents == 0

    def test_none_failed_sessions_coerced_to_zero(self) -> None:
        bucket = TimeseriesBucket(bucket="2026-04-04T00:00:00Z", failed_sessions=None)
        assert bucket.failed_sessions == 0

    def test_none_avg_latency_ms_coerced_to_zero(self) -> None:
        bucket = TimeseriesBucket(bucket="2026-04-04T00:00:00Z", avg_latency_ms=None)
        assert bucket.avg_latency_ms == 0.0

    def test_none_p99_latency_ms_coerced_to_zero(self) -> None:
        bucket = TimeseriesBucket(bucket="2026-04-04T00:00:00Z", p99_latency_ms=None)
        assert bucket.p99_latency_ms == 0.0

    def test_none_error_rate_coerced_to_zero(self) -> None:
        bucket = TimeseriesBucket(bucket="2026-04-04T00:00:00Z", error_rate=None)
        assert bucket.error_rate == 0.0

    def test_none_session_error_rate_coerced_to_zero(self) -> None:
        bucket = TimeseriesBucket(bucket="2026-04-04T00:00:00Z", session_error_rate=None)
        assert bucket.session_error_rate == 0.0

    def test_none_session_p99_ms_coerced_to_zero(self) -> None:
        bucket = TimeseriesBucket(bucket="2026-04-04T00:00:00Z", session_p99_ms=None)
        assert bucket.session_p99_ms == 0.0

    def test_all_null_fields_at_once_does_not_raise(self) -> None:
        """Simulates the exact dict that ClickHouse returns when all token values are NULL."""
        row = {
            "bucket": "2026-04-04T01:00:00Z",
            "sessions": 3,
            "tool_calls": 12,
            "errors": 1,
            "error_rate": 0.083,
            "avg_latency_ms": None,       # quantile returns NULL on empty set
            "p99_latency_ms": None,       # same
            "input_tokens": None,         # sum(input_tokens) NULL when all rows NULL
            "output_tokens": None,        # same
            "agents": None,
            "failed_sessions": None,
            "session_error_rate": None,
            "session_p99_ms": None,
        }
        # Must not raise ValidationError — was the production bug
        bucket = TimeseriesBucket(**row)
        assert bucket.input_tokens == 0
        assert bucket.output_tokens == 0
        assert bucket.avg_latency_ms == 0.0
        assert bucket.p99_latency_ms == 0.0

    def test_integer_values_preserved(self) -> None:
        """Explicit integer values must not be mangled by the coerce validator."""
        bucket = TimeseriesBucket(
            bucket="2026-04-04T00:00:00Z",
            input_tokens=500,
            output_tokens=250,
            agents=3,
            failed_sessions=1,
        )
        assert bucket.input_tokens == 500
        assert bucket.output_tokens == 250
        assert bucket.agents == 3
        assert bucket.failed_sessions == 1

    def test_float_values_preserved(self) -> None:
        bucket = TimeseriesBucket(
            bucket="2026-04-04T00:00:00Z",
            avg_latency_ms=142.5,
            p99_latency_ms=980.0,
            error_rate=0.12,
        )
        assert bucket.avg_latency_ms == pytest.approx(142.5)
        assert bucket.p99_latency_ms == pytest.approx(980.0)
        assert bucket.error_rate == pytest.approx(0.12)


# ---------------------------------------------------------------------------
# ModelMetrics — validator unit tests
# ---------------------------------------------------------------------------


class TestModelMetricsValidators:
    """Verify ModelMetrics coerces NULL fields that ClickHouse can return."""

    def test_none_input_tokens_coerced_to_zero(self) -> None:
        m = ModelMetrics(model_id="claude-3-5-sonnet", input_tokens=None)
        assert m.input_tokens == 0

    def test_none_output_tokens_coerced_to_zero(self) -> None:
        m = ModelMetrics(model_id="claude-3-5-sonnet", output_tokens=None)
        assert m.output_tokens == 0

    def test_none_calls_coerced_to_zero(self) -> None:
        m = ModelMetrics(model_id="claude-3-5-sonnet", calls=None)
        assert m.calls == 0

    def test_none_error_count_coerced_to_zero(self) -> None:
        m = ModelMetrics(model_id="claude-3-5-sonnet", error_count=None)
        assert m.error_count == 0

    def test_none_avg_latency_ms_coerced_to_zero(self) -> None:
        m = ModelMetrics(model_id="claude-3-5-sonnet", avg_latency_ms=None)
        assert m.avg_latency_ms == 0.0

    def test_full_null_row_does_not_raise(self) -> None:
        """Simulates what ClickHouse returns for a project with no LLM spans."""
        row = {
            "model_id": "gpt-4o",
            "calls": None,
            "input_tokens": None,
            "output_tokens": None,
            "avg_latency_ms": None,
            "error_count": None,
        }
        m = ModelMetrics(**row)
        assert m.calls == 0
        assert m.input_tokens == 0
        assert m.output_tokens == 0
        assert m.avg_latency_ms == 0.0
        assert m.error_count == 0

    def test_real_values_preserved(self) -> None:
        m = ModelMetrics(
            model_id="claude-3-5-sonnet",
            calls=100,
            input_tokens=50_000,
            output_tokens=10_000,
            avg_latency_ms=342.0,
            error_count=2,
        )
        assert m.calls == 100
        assert m.input_tokens == 50_000
        assert m.output_tokens == 10_000
        assert m.avg_latency_ms == pytest.approx(342.0)
        assert m.error_count == 2


# ---------------------------------------------------------------------------
# ToolMetrics — validator unit tests (regression: no validators before fix)
# ---------------------------------------------------------------------------


class TestToolMetricsValidators:
    """Verify ToolMetrics coerces NULL from avg/quantile ClickHouse functions."""

    def test_none_avg_latency_ms_coerced_to_zero(self) -> None:
        """avg(latency_ms) returns NULL when no rows match the filter."""
        m = ToolMetrics(server_name="pg", tool_name="query", avg_latency_ms=None)
        assert m.avg_latency_ms == 0.0

    def test_none_p99_latency_ms_coerced_to_zero(self) -> None:
        """quantile(0.99)(latency_ms) returns NULL when no rows match."""
        m = ToolMetrics(server_name="pg", tool_name="query", p99_latency_ms=None)
        assert m.p99_latency_ms == 0.0

    def test_none_success_rate_coerced_to_zero(self) -> None:
        m = ToolMetrics(server_name="pg", tool_name="query", success_rate=None)
        assert m.success_rate == 0.0

    def test_none_calls_per_session_coerced_to_zero(self) -> None:
        m = ToolMetrics(server_name="pg", tool_name="query", calls_per_session=None)
        assert m.calls_per_session == 0.0

    def test_none_calls_coerced_to_zero(self) -> None:
        m = ToolMetrics(server_name="pg", tool_name="query", calls=None)
        assert m.calls == 0

    def test_none_errors_coerced_to_zero(self) -> None:
        m = ToolMetrics(server_name="pg", tool_name="query", errors=None)
        assert m.errors == 0

    def test_none_content_errors_coerced_to_zero(self) -> None:
        m = ToolMetrics(server_name="pg", tool_name="query", content_errors=None)
        assert m.content_errors == 0

    def test_full_null_row_does_not_raise(self) -> None:
        """All nullable fields set to None — should produce a valid model."""
        row = {
            "server_name": "pg",
            "tool_name": "query",
            "calls": None,
            "errors": None,
            "avg_latency_ms": None,
            "p99_latency_ms": None,
            "success_rate": None,
            "calls_per_session": None,
            "content_errors": None,
        }
        m = ToolMetrics(**row)
        assert m.avg_latency_ms == 0.0
        assert m.p99_latency_ms == 0.0
        assert m.calls == 0

    def test_real_values_preserved(self) -> None:
        m = ToolMetrics(
            server_name="pg",
            tool_name="query",
            calls=200,
            errors=5,
            avg_latency_ms=45.2,
            p99_latency_ms=312.0,
            success_rate=97.5,
            calls_per_session=4.0,
            content_errors=0,
        )
        assert m.calls == 200
        assert m.avg_latency_ms == pytest.approx(45.2)
        assert m.p99_latency_ms == pytest.approx(312.0)
        assert m.success_rate == pytest.approx(97.5)


# ---------------------------------------------------------------------------
# ClickHouse storage unit tests (mocked client)
# ---------------------------------------------------------------------------


class TestGetMonitoringTimeseriesStorage:
    """get_monitoring_timeseries() returns valid dicts when ClickHouse sends NULLs."""

    @pytest.fixture
    def ch_backend(self):
        from langsight.storage.clickhouse import ClickHouseBackend

        mock_client = MagicMock()
        mock_client.command = AsyncMock()
        mock_client.insert = AsyncMock()
        mock_client.close = AsyncMock()
        return ClickHouseBackend(mock_client), mock_client

    async def test_empty_result_returns_empty_list(self, ch_backend) -> None:
        backend, mock_client = ch_backend
        mock_result = MagicMock()
        mock_result.result_rows = []
        mock_client.query = AsyncMock(return_value=mock_result)

        rows = await backend.get_monitoring_timeseries(hours=24, project_id=None)
        assert rows == []

    async def test_row_with_null_tokens_produces_valid_dict(self, ch_backend) -> None:
        """Simulates exactly what ClickHouse returns: coalesce(sum(nullable), 0) = 0.

        Even with coalesce, the Python driver can return Python None for some
        NULL-adjacent aggregates (avg, quantile on empty sets). The dict itself
        must be safe to pass to TimeseriesBucket(**row).
        """
        backend, mock_client = ch_backend
        # coalesce(sum(input_tokens), 0) guarantees int but avg/quantile may be None
        mock_result = MagicMock()
        mock_result.result_rows = [
            (
                "2026-04-04T00:00:00Z",  # bucket
                5,                        # sessions
                20,                       # tool_calls
                2,                        # errors
                0.1,                      # error_rate
                None,                     # avg_latency_ms — avg on empty LLM spans
                None,                     # p99_latency_ms — quantile on empty
                0,                        # input_tokens — coalesce(..., 0)
                0,                        # output_tokens — coalesce(..., 0)
                3,                        # agents
                1,                        # failed_sessions
                0.2,                      # session_error_rate
                None,                     # session_p99_ms — quantile on empty agent spans
            )
        ]
        mock_client.query = AsyncMock(return_value=mock_result)

        rows = await backend.get_monitoring_timeseries(hours=24)
        assert len(rows) == 1
        row = rows[0]
        assert row["bucket"] == "2026-04-04T00:00:00Z"
        assert row["input_tokens"] == 0
        assert row["output_tokens"] == 0
        # These can be None coming from the storage layer — validators handle it
        assert row["avg_latency_ms"] is None
        assert row["p99_latency_ms"] is None

        # Constructing TimeseriesBucket must not raise
        bucket = TimeseriesBucket(**row)
        assert bucket.avg_latency_ms == 0.0
        assert bucket.p99_latency_ms == 0.0
        assert bucket.input_tokens == 0

    async def test_project_id_filter_added_to_params(self, ch_backend) -> None:
        backend, mock_client = ch_backend
        mock_result = MagicMock()
        mock_result.result_rows = []
        mock_client.query = AsyncMock(return_value=mock_result)

        await backend.get_monitoring_timeseries(hours=6, project_id="proj-abc")
        call_kwargs = mock_client.query.call_args[1]
        assert call_kwargs["parameters"]["project_id"] == "proj-abc"
        assert call_kwargs["parameters"]["hours"] == 6

    async def test_no_project_id_omitted_from_params(self, ch_backend) -> None:
        backend, mock_client = ch_backend
        mock_result = MagicMock()
        mock_result.result_rows = []
        mock_client.query = AsyncMock(return_value=mock_result)

        await backend.get_monitoring_timeseries(hours=24, project_id=None)
        call_kwargs = mock_client.query.call_args[1]
        assert "project_id" not in call_kwargs["parameters"]


class TestGetMonitoringModelsStorage:
    """get_monitoring_models() returns valid dicts when ClickHouse sends NULLs."""

    @pytest.fixture
    def ch_backend(self):
        from langsight.storage.clickhouse import ClickHouseBackend

        mock_client = MagicMock()
        mock_client.command = AsyncMock()
        mock_client.insert = AsyncMock()
        mock_client.close = AsyncMock()
        return ClickHouseBackend(mock_client), mock_client

    async def test_row_with_null_tokens_produces_valid_dict(self, ch_backend) -> None:
        backend, mock_client = ch_backend
        mock_result = MagicMock()
        # coalesce(sum(input_tokens), 0) → 0, avg → None on empty
        mock_result.result_rows = [
            ("gpt-4o", 10, 0, 0, None, 1),
        ]
        mock_client.query = AsyncMock(return_value=mock_result)

        rows = await backend.get_monitoring_models(hours=24)
        assert len(rows) == 1
        m = ModelMetrics(**rows[0])
        assert m.input_tokens == 0
        assert m.output_tokens == 0
        assert m.avg_latency_ms == 0.0

    async def test_empty_result_returns_empty_list(self, ch_backend) -> None:
        backend, mock_client = ch_backend
        mock_result = MagicMock()
        mock_result.result_rows = []
        mock_client.query = AsyncMock(return_value=mock_result)

        rows = await backend.get_monitoring_models(hours=24)
        assert rows == []


# ---------------------------------------------------------------------------
# API endpoint unit tests (mocked storage via app.state)
# ---------------------------------------------------------------------------


class TestMonitoringTimeseriesEndpoint:
    """GET /api/monitoring/timeseries — endpoint-level unit tests."""

    async def test_returns_200_when_storage_returns_empty_list(self, client) -> None:
        http_client, storage = client
        storage.get_monitoring_timeseries.return_value = []
        r = await http_client.get("/api/monitoring/timeseries")
        assert r.status_code == 200
        assert r.json() == []

    async def test_returns_200_with_null_token_rows(self, client) -> None:
        """The production bug: storage returns None in token fields → must be 200, not 500."""
        http_client, storage = client
        storage.get_monitoring_timeseries.return_value = [
            {
                "bucket": "2026-04-04T01:00:00Z",
                "sessions": 5,
                "tool_calls": 20,
                "errors": 2,
                "error_rate": 0.1,
                "avg_latency_ms": None,
                "p99_latency_ms": None,
                "input_tokens": None,
                "output_tokens": None,
                "agents": None,
                "failed_sessions": None,
                "session_error_rate": None,
                "session_p99_ms": None,
            }
        ]
        r = await http_client.get("/api/monitoring/timeseries")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert len(data) == 1
        assert data[0]["input_tokens"] == 0
        assert data[0]["output_tokens"] == 0
        assert data[0]["avg_latency_ms"] == 0.0

    async def test_hours_param_forwarded_to_storage(self, client) -> None:
        http_client, storage = client
        storage.get_monitoring_timeseries.return_value = []
        r = await http_client.get("/api/monitoring/timeseries?hours=48")
        assert r.status_code == 200
        storage.get_monitoring_timeseries.assert_called_once()
        call_kwargs = storage.get_monitoring_timeseries.call_args
        assert call_kwargs.kwargs.get("hours") == 48 or call_kwargs.args[0] == 48

    async def test_hours_param_out_of_range_returns_422(self, client) -> None:
        http_client, _ = client
        r = await http_client.get("/api/monitoring/timeseries?hours=0")
        assert r.status_code == 422

    async def test_returns_empty_list_when_storage_lacks_method(self, client) -> None:
        """Endpoint must return [] not 500 when storage does not have the method."""
        http_client, storage = client
        # Remove the method from the mock so hasattr() returns False
        del storage.get_monitoring_timeseries
        r = await http_client.get("/api/monitoring/timeseries")
        assert r.status_code == 200
        assert r.json() == []

    async def test_multiple_buckets_all_coerced(self, client) -> None:
        """All buckets in a multi-row response must be coerced correctly."""
        http_client, storage = client
        storage.get_monitoring_timeseries.return_value = [
            {
                "bucket": "2026-04-04T00:00:00Z",
                "sessions": 2,
                "tool_calls": 8,
                "errors": 0,
                "error_rate": 0.0,
                "avg_latency_ms": 45.0,
                "p99_latency_ms": 120.0,
                "input_tokens": 1000,
                "output_tokens": 500,
                "agents": 1,
                "failed_sessions": 0,
                "session_error_rate": 0.0,
                "session_p99_ms": 980.0,
            },
            {
                "bucket": "2026-04-04T01:00:00Z",
                "sessions": 0,
                "tool_calls": 0,
                "errors": 0,
                "error_rate": None,
                "avg_latency_ms": None,
                "p99_latency_ms": None,
                "input_tokens": None,
                "output_tokens": None,
                "agents": None,
                "failed_sessions": None,
                "session_error_rate": None,
                "session_p99_ms": None,
            },
        ]
        r = await http_client.get("/api/monitoring/timeseries")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 2
        first, second = data
        assert first["input_tokens"] == 1000
        assert second["input_tokens"] == 0
        assert second["avg_latency_ms"] == 0.0


class TestMonitoringModelsEndpoint:
    """GET /api/monitoring/models — endpoint-level unit tests."""

    async def test_returns_200_with_null_token_rows(self, client) -> None:
        http_client, storage = client
        storage.get_monitoring_models.return_value = [
            {
                "model_id": "claude-3-5-sonnet",
                "calls": 50,
                "input_tokens": None,   # coalesce should have caught this; validators as backstop
                "output_tokens": None,
                "avg_latency_ms": None,
                "error_count": 0,
            }
        ]
        r = await http_client.get("/api/monitoring/models")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert data[0]["input_tokens"] == 0
        assert data[0]["output_tokens"] == 0
        assert data[0]["avg_latency_ms"] == 0.0

    async def test_returns_empty_list_when_storage_lacks_method(self, client) -> None:
        http_client, storage = client
        del storage.get_monitoring_models
        r = await http_client.get("/api/monitoring/models")
        assert r.status_code == 200
        assert r.json() == []


class TestMonitoringToolsEndpoint:
    """GET /api/monitoring/tools — endpoint-level unit tests."""

    async def test_returns_200_with_null_latency_rows(self, client) -> None:
        """avg/quantile return NULL for tools with no data — must be 200, not 500."""
        http_client, storage = client
        storage.get_monitoring_tools.return_value = [
            {
                "server_name": "pg",
                "tool_name": "query",
                "calls": 0,
                "errors": 0,
                "avg_latency_ms": None,    # avg() on zero rows = NULL
                "p99_latency_ms": None,    # quantile() on zero rows = NULL
                "success_rate": None,
                "calls_per_session": None,
                "content_errors": 0,
            }
        ]
        r = await http_client.get("/api/monitoring/tools")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert data[0]["avg_latency_ms"] == 0.0
        assert data[0]["p99_latency_ms"] == 0.0

    async def test_returns_empty_list_when_storage_lacks_method(self, client) -> None:
        http_client, storage = client
        del storage.get_monitoring_tools
        r = await http_client.get("/api/monitoring/tools")
        assert r.status_code == 200
        assert r.json() == []


# ---------------------------------------------------------------------------
# Regression tests — pin the exact bugs that caused the production outage
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_timeseries_bucket_none_input_tokens_does_not_raise_validation_error() -> None:
    """Regression (2026-04-04): Pydantic v2 raises ValidationError when None is
    passed to 'input_tokens: int = 0' — the default is not applied for explicit None.
    The field_validator(mode='before') fix must intercept None before type coercion."""
    from pydantic import ValidationError

    try:
        bucket = TimeseriesBucket(bucket="2026-04-04T00:00:00Z", input_tokens=None)
    except ValidationError as e:
        pytest.fail(
            f"TimeseriesBucket raised ValidationError for None input_tokens — "
            f"regression re-introduced: {e}"
        )
    assert bucket.input_tokens == 0


@pytest.mark.regression
def test_model_metrics_none_input_tokens_does_not_raise_validation_error() -> None:
    """Regression (2026-04-04): same Pydantic v2 default-vs-None issue on ModelMetrics."""
    from pydantic import ValidationError

    try:
        m = ModelMetrics(model_id="claude-3-5-sonnet", input_tokens=None)
    except ValidationError as e:
        pytest.fail(
            f"ModelMetrics raised ValidationError for None input_tokens — "
            f"regression re-introduced: {e}"
        )
    assert m.input_tokens == 0


@pytest.mark.regression
def test_tool_metrics_none_avg_latency_does_not_raise_validation_error() -> None:
    """Regression (2026-04-04): ToolMetrics had no field_validator; avg(latency_ms)
    from ClickHouse returns NULL when the tool has no calls in the time window."""
    from pydantic import ValidationError

    try:
        m = ToolMetrics(server_name="pg", tool_name="query", avg_latency_ms=None)
    except ValidationError as e:
        pytest.fail(
            f"ToolMetrics raised ValidationError for None avg_latency_ms — "
            f"regression re-introduced: {e}"
        )
    assert m.avg_latency_ms == 0.0


@pytest.mark.regression
async def test_timeseries_endpoint_returns_200_not_500_on_null_tokens(
    client,
) -> None:
    """Regression (2026-04-04): /api/monitoring/timeseries returned HTTP 500 when
    ClickHouse returned NULL for token sums on a project with no LLM spans.
    Must always return 200 with zeros."""
    http_client, storage = client
    storage.get_monitoring_timeseries.return_value = [
        {
            "bucket": "2026-04-04T00:00:00Z",
            "sessions": 1,
            "tool_calls": 1,
            "errors": 0,
            "error_rate": 0.0,
            "avg_latency_ms": None,
            "p99_latency_ms": None,
            "input_tokens": None,
            "output_tokens": None,
            "agents": None,
            "failed_sessions": None,
            "session_error_rate": None,
            "session_p99_ms": None,
        }
    ]
    r = await http_client.get("/api/monitoring/timeseries")
    assert r.status_code == 200, (
        f"HTTP 500 on /api/monitoring/timeseries with NULL token fields — "
        f"regression re-introduced. Response: {r.text}"
    )
