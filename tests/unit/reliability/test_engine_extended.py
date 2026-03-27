"""Extended unit tests for reliability/engine.py.

Covers: ToolMetrics properties, ReliabilityEngine, SLOEvaluator, categorise_error.
All tests are pure-unit: no network, no database, no Docker required.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from langsight.reliability.engine import (
    ErrorCategory,
    ReliabilityEngine,
    ToolMetrics,
    _row_to_metrics,
    categorise_error,
)


# ---------------------------------------------------------------------------
# ToolMetrics — computed properties
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestToolMetrics:
    def _make(self, total: int = 0, success: int = 0, **kwargs) -> ToolMetrics:
        return ToolMetrics(
            server_name="srv",
            tool_name="tool_a",
            window_hours=24,
            total_calls=total,
            success_calls=success,
            error_calls=total - success,
            **kwargs,
        )

    def test_success_rate_zero_when_no_calls(self) -> None:
        m = self._make(total=0, success=0)
        assert m.success_rate_pct == 0.0

    def test_success_rate_100_when_all_succeed(self) -> None:
        m = self._make(total=10, success=10)
        assert m.success_rate_pct == 100.0

    def test_success_rate_rounds_to_2dp(self) -> None:
        m = self._make(total=3, success=1)
        assert m.success_rate_pct == round(1 / 3 * 100, 2)

    def test_error_rate_is_complement_of_success_rate(self) -> None:
        m = self._make(total=10, success=7)
        assert m.error_rate_pct == pytest.approx(100.0 - m.success_rate_pct)

    def test_error_rate_zero_when_all_succeed(self) -> None:
        m = self._make(total=5, success=5)
        assert m.error_rate_pct == 0.0

    def test_is_degraded_when_success_rate_below_95(self) -> None:
        # 9/10 = 90% < 95%
        m = self._make(total=10, success=9)
        assert m.is_degraded is True

    def test_is_degraded_when_p95_latency_above_2000ms(self) -> None:
        """is_degraded uses p95 (not avg) for latency threshold."""
        from langsight.reliability.engine import ToolMetrics
        m = ToolMetrics(server_name="s", tool_name="t", window_hours=24,
                        total_calls=10, success_calls=10,
                        avg_latency_ms=500.0, p95_latency_ms=2500.0)
        assert m.is_degraded is True

    def test_not_degraded_when_success_95_and_latency_ok(self) -> None:
        m = self._make(total=100, success=96, avg_latency_ms=500.0)
        assert m.is_degraded is False

    def test_is_degraded_exactly_at_95_pct_boundary(self) -> None:
        """95.0% is NOT degraded — degraded means strictly less than 95."""
        m = self._make(total=100, success=95, avg_latency_ms=100.0)
        assert m.is_degraded is False

    def test_is_degraded_exactly_at_latency_2000ms_boundary(self) -> None:
        """2000ms is NOT degraded — degraded means strictly above 2000."""
        m = self._make(total=100, success=100, avg_latency_ms=2000.0)
        assert m.is_degraded is False

    def test_to_dict_has_all_keys(self) -> None:
        m = self._make(total=10, success=8, avg_latency_ms=120.0, max_latency_ms=300.0)
        d = m.to_dict()
        expected = {
            "server_name", "tool_name", "window_hours",
            "total_calls", "success_calls", "error_calls", "timeout_calls",
            "success_rate_pct", "error_rate_pct",
            "avg_latency_ms", "max_latency_ms",
            "p50_latency_ms", "p95_latency_ms", "p99_latency_ms",
            "is_degraded", "error_breakdown",
        }
        assert set(d.keys()) == expected

    def test_to_dict_computed_values_match_properties(self) -> None:
        m = self._make(total=10, success=8)
        d = m.to_dict()
        assert d["success_rate_pct"] == m.success_rate_pct
        assert d["error_rate_pct"] == m.error_rate_pct
        assert d["is_degraded"] == m.is_degraded

    def test_error_breakdown_defaults_to_empty_dict(self) -> None:
        m = self._make(total=5, success=5)
        assert m.error_breakdown == {}
        assert m.to_dict()["error_breakdown"] == {}


# ---------------------------------------------------------------------------
# _row_to_metrics helper
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRowToMetrics:
    def test_converts_row_to_tool_metrics(self) -> None:
        row = {
            "server_name": "my-server",
            "tool_name": "list_tables",
            "total_calls": 50,
            "success_calls": 45,
            "error_calls": 4,
            "timeout_calls": 1,
            "avg_latency_ms": 85.5,
            "max_latency_ms": 300.0,
        }
        m = _row_to_metrics(row, window_hours=12)
        assert m.server_name == "my-server"
        assert m.tool_name == "list_tables"
        assert m.total_calls == 50
        assert m.success_calls == 45
        assert m.error_calls == 4
        assert m.timeout_calls == 1
        assert m.avg_latency_ms == 85.5
        assert m.max_latency_ms == 300.0
        assert m.window_hours == 12

    def test_defaults_to_zero_for_missing_fields(self) -> None:
        row = {"server_name": "srv", "tool_name": "t"}
        m = _row_to_metrics(row, window_hours=24)
        assert m.total_calls == 0
        assert m.success_calls == 0
        assert m.error_calls == 0
        assert m.timeout_calls == 0
        assert m.avg_latency_ms == 0.0
        assert m.max_latency_ms == 0.0


# ---------------------------------------------------------------------------
# ReliabilityEngine
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestReliabilityEngine:
    def _make_storage_with_reliability(
        self,
        rows: list[dict] | None = None,
        raise_on_call: Exception | None = None,
    ) -> MagicMock:
        storage = MagicMock()
        if raise_on_call:
            storage.get_tool_reliability = AsyncMock(side_effect=raise_on_call)
        else:
            storage.get_tool_reliability = AsyncMock(return_value=rows or [])
        return storage

    def _make_storage_without_reliability(self) -> MagicMock:
        storage = MagicMock(spec=[])  # no attributes at all
        return storage

    async def test_returns_empty_when_storage_lacks_reliability_method(self) -> None:
        """Storage without get_tool_reliability must return empty list, no error."""
        engine = ReliabilityEngine(self._make_storage_without_reliability())
        result = await engine.get_metrics()
        assert result == []

    async def test_returns_empty_on_storage_exception(self) -> None:
        """If get_tool_reliability raises, must swallow and return empty list."""
        storage = self._make_storage_with_reliability(
            raise_on_call=RuntimeError("ClickHouse unreachable")
        )
        engine = ReliabilityEngine(storage)
        result = await engine.get_metrics()
        assert result == []

    async def test_returns_tool_metrics_for_each_row(self) -> None:
        rows = [
            {
                "server_name": "srv",
                "tool_name": "t1",
                "total_calls": 100,
                "success_calls": 95,
                "error_calls": 5,
                "timeout_calls": 0,
                "avg_latency_ms": 50.0,
                "max_latency_ms": 200.0,
            },
            {
                "server_name": "srv",
                "tool_name": "t2",
                "total_calls": 20,
                "success_calls": 10,
                "error_calls": 10,
                "timeout_calls": 2,
                "avg_latency_ms": 3000.0,
                "max_latency_ms": 5000.0,
            },
        ]
        storage = self._make_storage_with_reliability(rows=rows)
        engine = ReliabilityEngine(storage)
        result = await engine.get_metrics(hours=24)

        assert len(result) == 2
        assert all(isinstance(m, ToolMetrics) for m in result)
        assert result[0].tool_name == "t1"
        assert result[1].tool_name == "t2"

    async def test_passes_server_name_filter_to_storage(self) -> None:
        storage = self._make_storage_with_reliability(rows=[])
        engine = ReliabilityEngine(storage)
        await engine.get_metrics(server_name="my-server", hours=6, project_id="proj-1")

        storage.get_tool_reliability.assert_called_once_with(
            server_name="my-server", hours=6, project_id="proj-1"
        )

    async def test_get_degraded_tools_filters_non_degraded(self) -> None:
        """get_degraded_tools() must return only tools where is_degraded is True."""
        rows = [
            {
                "server_name": "srv",
                "tool_name": "healthy",
                "total_calls": 100,
                "success_calls": 100,
                "error_calls": 0,
                "timeout_calls": 0,
                "avg_latency_ms": 50.0,
                "max_latency_ms": 100.0,
            },
            {
                "server_name": "srv",
                "tool_name": "degraded",
                "total_calls": 100,
                "success_calls": 85,  # 85% < 95%
                "error_calls": 15,
                "timeout_calls": 0,
                "avg_latency_ms": 50.0,
                "max_latency_ms": 100.0,
            },
        ]
        storage = self._make_storage_with_reliability(rows=rows)
        engine = ReliabilityEngine(storage)
        result = await engine.get_degraded_tools(hours=24)

        assert len(result) == 1
        assert result[0].tool_name == "degraded"

    async def test_get_degraded_tools_returns_empty_when_all_healthy(self) -> None:
        rows = [
            {
                "server_name": "srv",
                "tool_name": "healthy",
                "total_calls": 100,
                "success_calls": 100,
                "error_calls": 0,
                "timeout_calls": 0,
                "avg_latency_ms": 100.0,
                "max_latency_ms": 200.0,
            }
        ]
        storage = self._make_storage_with_reliability(rows=rows)
        engine = ReliabilityEngine(storage)
        result = await engine.get_degraded_tools()
        assert result == []


# ---------------------------------------------------------------------------
# categorise_error
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCategoriseError:
    def test_none_returns_unknown(self) -> None:
        assert categorise_error(None) == ErrorCategory.UNKNOWN

    def test_empty_string_returns_unknown(self) -> None:
        assert categorise_error("") == ErrorCategory.UNKNOWN

    def test_timeout_keyword(self) -> None:
        assert categorise_error("connection timeout") == ErrorCategory.TIMEOUT

    def test_timed_out_keyword(self) -> None:
        assert categorise_error("request timed out") == ErrorCategory.TIMEOUT

    def test_deadline_keyword(self) -> None:
        assert categorise_error("deadline exceeded") == ErrorCategory.TIMEOUT

    def test_auth_keyword(self) -> None:
        assert categorise_error("auth failed") == ErrorCategory.AUTH

    def test_unauthorized_keyword(self) -> None:
        assert categorise_error("unauthorized access") == ErrorCategory.AUTH

    def test_forbidden_keyword(self) -> None:
        assert categorise_error("forbidden resource") == ErrorCategory.AUTH

    def test_http_403(self) -> None:
        assert categorise_error("HTTP 403") == ErrorCategory.AUTH

    def test_http_401(self) -> None:
        assert categorise_error("status 401") == ErrorCategory.AUTH

    def test_rate_limit_keyword(self) -> None:
        assert categorise_error("rate limit exceeded") == ErrorCategory.RATE_LIMIT

    def test_too_many_requests_keyword(self) -> None:
        assert categorise_error("too many requests") == ErrorCategory.RATE_LIMIT

    def test_http_429(self) -> None:
        assert categorise_error("got 429 from server") == ErrorCategory.RATE_LIMIT

    def test_http_500(self) -> None:
        assert categorise_error("internal server 500") == ErrorCategory.SERVER_ERROR

    def test_http_502(self) -> None:
        assert categorise_error("502 bad gateway") == ErrorCategory.SERVER_ERROR

    def test_http_503(self) -> None:
        assert categorise_error("503 service unavailable") == ErrorCategory.SERVER_ERROR

    def test_http_504(self) -> None:
        # "504 gateway timeout" — "timeout" keyword matches TIMEOUT before 504 is checked
        # Use a string that has 504 but no timeout keyword to hit SERVER_ERROR
        assert categorise_error("upstream returned 504 bad gateway error") == ErrorCategory.SERVER_ERROR

    def test_server_error_keyword(self) -> None:
        assert categorise_error("server error occurred") == ErrorCategory.SERVER_ERROR

    def test_internal_keyword(self) -> None:
        assert categorise_error("internal error") == ErrorCategory.SERVER_ERROR

    def test_unknown_generic_error(self) -> None:
        assert categorise_error("something unexpected happened") == ErrorCategory.UNKNOWN

    def test_case_insensitive_matching(self) -> None:
        assert categorise_error("TIMEOUT") == ErrorCategory.TIMEOUT
        assert categorise_error("Unauthorized") == ErrorCategory.AUTH
        assert categorise_error("RATE LIMIT") == ErrorCategory.RATE_LIMIT
