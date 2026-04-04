"""
Integration smoke tests for the monitoring API endpoints.

Hits the LIVE stack at http://localhost:8000. Requires:
    docker compose up -d
    (wait for api healthy)

Run:
    uv run pytest tests/integration/api/test_monitoring_api.py -v -m integration

These tests verify that the NULL-coercion fix holds end-to-end against a real
ClickHouse backend. A project with no LLM spans must not cause HTTP 500.
"""
from __future__ import annotations

import os

import httpx
import pytest

pytestmark = pytest.mark.integration

_BASE_URL = os.environ.get("TEST_API_URL", "http://localhost:8000")
_API_KEY = os.environ.get(
    "TEST_API_KEY",
    "ls_529c7bee083fe9447a7d8ea69780ad1ec36c65ad52cc0b36ce0c2aed66446c8f",
)

# Project with no data — we use a sentinel ID that should never have real spans.
# This reliably exercises the "all NULLs" ClickHouse path.
_EMPTY_PROJECT_ID = "__integration_test_no_llm_spans__"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def api_available() -> bool:
    """Return True if the API is reachable."""
    try:
        r = httpx.get(f"{_BASE_URL}/api/liveness", timeout=3)
        return r.status_code == 200
    except Exception:  # noqa: BLE001
        return False


@pytest.fixture(scope="module", autouse=True)
def require_api(api_available: bool) -> None:
    if not api_available:
        pytest.skip("API not reachable. Run: docker compose up -d")


@pytest.fixture(scope="module")
def headers() -> dict[str, str]:
    return {"X-API-Key": _API_KEY, "Content-Type": "application/json"}


# ---------------------------------------------------------------------------
# Smoke tests — NULL-safe endpoints
# ---------------------------------------------------------------------------


class TestMonitoringTimeseriesSmoke:
    """Smoke tests: endpoint always returns 200 with valid JSON structure."""

    def test_returns_200_no_query_params(self, headers: dict[str, str]) -> None:
        r = httpx.get(
            f"{_BASE_URL}/api/monitoring/timeseries",
            headers=headers,
            timeout=10,
        )
        assert r.status_code == 200, (
            f"Expected 200, got {r.status_code}. "
            "This is the NULL-coercion regression — check if field_validators are intact."
        )
        data = r.json()
        assert isinstance(data, list)

    def test_returns_200_for_empty_project(self, headers: dict[str, str]) -> None:
        """A project with no spans at all — all token sums are NULL in ClickHouse.
        Must return 200 with an empty list (not 500 with ValidationError)."""
        r = httpx.get(
            f"{_BASE_URL}/api/monitoring/timeseries",
            headers={**headers, "X-Project-ID": _EMPTY_PROJECT_ID},
            params={"hours": 24},
            timeout=10,
        )
        assert r.status_code == 200, (
            f"HTTP {r.status_code} for empty project — NULL-coercion regression. "
            f"Response body: {r.text[:500]}"
        )
        assert isinstance(r.json(), list)

    def test_response_buckets_have_correct_schema(self, headers: dict[str, str]) -> None:
        """When buckets are returned, each must have the expected fields with correct types."""
        r = httpx.get(
            f"{_BASE_URL}/api/monitoring/timeseries",
            headers=headers,
            params={"hours": 168},  # 7 days — more likely to have data
            timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        for bucket in data:
            # Required string field
            assert isinstance(bucket["bucket"], str)
            # All numeric fields must be int or float — never null in response
            assert isinstance(bucket["sessions"], int)
            assert isinstance(bucket["tool_calls"], int)
            assert isinstance(bucket["errors"], int)
            assert isinstance(bucket["input_tokens"], int), (
                f"input_tokens is {type(bucket['input_tokens']).__name__}, expected int. "
                "NULL-coercion regression."
            )
            assert isinstance(bucket["output_tokens"], int), (
                f"output_tokens is {type(bucket['output_tokens']).__name__}, expected int. "
                "NULL-coercion regression."
            )
            assert isinstance(bucket["avg_latency_ms"], float)
            assert isinstance(bucket["p99_latency_ms"], float)

    def test_hours_param_accepted(self, headers: dict[str, str]) -> None:
        for hours in (1, 6, 24, 168):
            r = httpx.get(
                f"{_BASE_URL}/api/monitoring/timeseries",
                headers=headers,
                params={"hours": hours},
                timeout=10,
            )
            assert r.status_code == 200, f"hours={hours} → HTTP {r.status_code}"

    def test_invalid_hours_returns_422(self, headers: dict[str, str]) -> None:
        r = httpx.get(
            f"{_BASE_URL}/api/monitoring/timeseries",
            headers=headers,
            params={"hours": 0},
            timeout=5,
        )
        assert r.status_code == 422


class TestMonitoringModelsSmoke:
    """Smoke tests for /api/monitoring/models."""

    def test_returns_200(self, headers: dict[str, str]) -> None:
        r = httpx.get(
            f"{_BASE_URL}/api/monitoring/models",
            headers=headers,
            timeout=10,
        )
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_returns_200_for_empty_project(self, headers: dict[str, str]) -> None:
        r = httpx.get(
            f"{_BASE_URL}/api/monitoring/models",
            headers={**headers, "X-Project-ID": _EMPTY_PROJECT_ID},
            timeout=10,
        )
        assert r.status_code == 200, (
            f"HTTP {r.status_code} for empty project on /models — "
            f"NULL-coercion regression. Body: {r.text[:500]}"
        )

    def test_model_rows_have_non_null_numeric_fields(self, headers: dict[str, str]) -> None:
        """Every model row must have integer/float fields — never JSON null."""
        r = httpx.get(
            f"{_BASE_URL}/api/monitoring/models",
            headers=headers,
            params={"hours": 168},
            timeout=10,
        )
        assert r.status_code == 200
        for row in r.json():
            assert isinstance(row["calls"], int)
            assert isinstance(row["input_tokens"], int), (
                f"input_tokens is {type(row['input_tokens']).__name__} on /models — "
                "NULL-coercion regression."
            )
            assert isinstance(row["output_tokens"], int)
            assert isinstance(row["avg_latency_ms"], float)
            assert isinstance(row["error_count"], int)


class TestMonitoringToolsSmoke:
    """Smoke tests for /api/monitoring/tools."""

    def test_returns_200(self, headers: dict[str, str]) -> None:
        r = httpx.get(
            f"{_BASE_URL}/api/monitoring/tools",
            headers=headers,
            timeout=10,
        )
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_returns_200_for_empty_project(self, headers: dict[str, str]) -> None:
        r = httpx.get(
            f"{_BASE_URL}/api/monitoring/tools",
            headers={**headers, "X-Project-ID": _EMPTY_PROJECT_ID},
            timeout=10,
        )
        assert r.status_code == 200, (
            f"HTTP {r.status_code} for empty project on /tools — "
            f"NULL-coercion regression. Body: {r.text[:500]}"
        )

    def test_tool_rows_have_non_null_float_latency(self, headers: dict[str, str]) -> None:
        """avg_latency_ms and p99_latency_ms must never be null in the response."""
        r = httpx.get(
            f"{_BASE_URL}/api/monitoring/tools",
            headers=headers,
            params={"hours": 168},
            timeout=10,
        )
        assert r.status_code == 200
        for row in r.json():
            assert isinstance(row["avg_latency_ms"], float), (
                f"avg_latency_ms is {type(row['avg_latency_ms']).__name__} — "
                "NULL-coercion regression on ToolMetrics."
            )
            assert isinstance(row["p99_latency_ms"], float), (
                f"p99_latency_ms is {type(row['p99_latency_ms']).__name__} — "
                "NULL-coercion regression on ToolMetrics."
            )


class TestMonitoringTrendsSmoke:
    """Smoke tests for /api/monitoring/trends."""

    def test_returns_200(self, headers: dict[str, str]) -> None:
        r = httpx.get(
            f"{_BASE_URL}/api/monitoring/trends",
            headers=headers,
            timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        # All MonitoringTrends fields are nullable by design — verify shape only
        assert isinstance(data, dict)


class TestDashboardCriticalEndpointsSmoke:
    """Smoke tests for all dashboard-critical endpoints (sessions, agents, costs).

    These are not NULL-coercion bugs (the routes handle None values defensively),
    but we want a single place to assert they all return 200 so a future router
    regression is caught immediately.
    """

    def test_sessions_returns_200(self, headers: dict[str, str]) -> None:
        r = httpx.get(
            f"{_BASE_URL}/api/agents/sessions",
            headers=headers,
            timeout=10,
        )
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_costs_breakdown_returns_200(self, headers: dict[str, str]) -> None:
        r = httpx.get(
            f"{_BASE_URL}/api/costs/breakdown",
            headers=headers,
            timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        assert "total_calls" in data
        assert "total_cost_usd" in data

    def test_health_servers_returns_200(self, headers: dict[str, str]) -> None:
        r = httpx.get(
            f"{_BASE_URL}/api/health/servers",
            headers=headers,
            timeout=10,
        )
        assert r.status_code == 200

    def test_monitoring_timeseries_returns_200(self, headers: dict[str, str]) -> None:
        r = httpx.get(
            f"{_BASE_URL}/api/monitoring/timeseries",
            headers=headers,
            timeout=10,
        )
        assert r.status_code == 200

    def test_monitoring_models_returns_200(self, headers: dict[str, str]) -> None:
        r = httpx.get(
            f"{_BASE_URL}/api/monitoring/models",
            headers=headers,
            timeout=10,
        )
        assert r.status_code == 200

    def test_monitoring_tools_returns_200(self, headers: dict[str, str]) -> None:
        r = httpx.get(
            f"{_BASE_URL}/api/monitoring/tools",
            headers=headers,
            timeout=10,
        )
        assert r.status_code == 200
