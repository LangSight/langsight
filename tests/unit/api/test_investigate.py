"""
Unit tests for the investigate API router.

Tests cover:
- _gather_evidence(): evidence aggregation with history in/out of window
- _format_evidence(): text formatting of evidence dict
- _rule_based_report(): heuristic report for healthy, down, drift, latency, degraded
- run_investigation endpoint: LLM success, ConfigError fallback, LLM error fallback,
  empty server list, multiple servers, response shape validation
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml
from httpx import ASGITransport, AsyncClient

from langsight.api.main import create_app
from langsight.api.routers.investigate import (
    _format_evidence,
    _gather_evidence,
    _rule_based_report,
)
from langsight.config import load_config
from langsight.exceptions import ConfigError
from langsight.models import HealthCheckResult, ServerStatus

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 3, 28, 12, 0, 0, tzinfo=UTC)


def _result(
    name: str = "pg",
    status: ServerStatus = ServerStatus.UP,
    latency_ms: float | None = 50.0,
    error: str | None = None,
    offset_minutes: int = 0,
) -> HealthCheckResult:
    """Build a HealthCheckResult at _NOW minus offset_minutes."""
    return HealthCheckResult(
        server_name=name,
        status=status,
        latency_ms=latency_ms,
        checked_at=_NOW - timedelta(minutes=offset_minutes),
        error=error,
    )


# ---------------------------------------------------------------------------
# _gather_evidence() — unit tests
# ---------------------------------------------------------------------------


class TestGatherEvidence:
    async def test_counts_up_checks_correctly(self) -> None:
        storage = MagicMock()
        storage.get_health_history = AsyncMock(return_value=[
            _result(status=ServerStatus.UP, offset_minutes=5),
            _result(status=ServerStatus.UP, offset_minutes=10),
        ])
        with patch("langsight.api.routers.investigate.datetime") as mock_dt:
            mock_dt.now.return_value = _NOW
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            ev = await _gather_evidence("pg", storage, window_hours=1.0)
        assert ev["up_count"] == 2
        assert ev["down_count"] == 0
        assert ev["degraded_count"] == 0
        assert ev["total_checks"] == 2

    async def test_filters_results_outside_window(self) -> None:
        """Results older than the window must not count toward the totals."""
        storage = MagicMock()
        storage.get_health_history = AsyncMock(return_value=[
            _result(status=ServerStatus.UP, offset_minutes=30),    # inside 1h window
            _result(status=ServerStatus.DOWN, offset_minutes=90),  # outside 1h window
        ])
        with patch("langsight.api.routers.investigate.datetime") as mock_dt:
            mock_dt.now.return_value = _NOW
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            ev = await _gather_evidence("pg", storage, window_hours=1.0)
        assert ev["total_checks"] == 1
        assert ev["up_count"] == 1
        assert ev["down_count"] == 0

    async def test_empty_history_returns_no_data_status(self) -> None:
        storage = MagicMock()
        storage.get_health_history = AsyncMock(return_value=[])
        ev = await _gather_evidence("pg", storage, window_hours=1.0)
        assert ev["total_checks"] == 0
        assert ev["latest_status"] == "no_data"
        assert ev["latest_error"] is None

    async def test_computes_avg_latency(self) -> None:
        storage = MagicMock()
        storage.get_health_history = AsyncMock(return_value=[
            _result(latency_ms=100.0, offset_minutes=5),
            _result(latency_ms=200.0, offset_minutes=10),
        ])
        with patch("langsight.api.routers.investigate.datetime") as mock_dt:
            mock_dt.now.return_value = _NOW
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            ev = await _gather_evidence("pg", storage, window_hours=1.0)
        assert ev["avg_latency_ms"] == pytest.approx(150.0)

    async def test_avg_latency_is_none_when_no_latency_data(self) -> None:
        storage = MagicMock()
        storage.get_health_history = AsyncMock(return_value=[
            _result(latency_ms=None, offset_minutes=5),
        ])
        with patch("langsight.api.routers.investigate.datetime") as mock_dt:
            mock_dt.now.return_value = _NOW
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            ev = await _gather_evidence("pg", storage, window_hours=1.0)
        assert ev["avg_latency_ms"] is None

    async def test_schema_drift_events_captured(self) -> None:
        """DEGRADED results with 'schema drift' in error are captured as drift events."""
        storage = MagicMock()
        storage.get_health_history = AsyncMock(return_value=[
            _result(
                status=ServerStatus.DEGRADED,
                error="schema drift detected: hash changed",
                offset_minutes=5,
            ),
        ])
        with patch("langsight.api.routers.investigate.datetime") as mock_dt:
            mock_dt.now.return_value = _NOW
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            ev = await _gather_evidence("pg", storage, window_hours=1.0)
        assert len(ev["schema_drift_events"]) == 1
        assert "schema drift" in ev["schema_drift_events"][0]["error"]

    async def test_degraded_without_drift_text_not_in_drift_events(self) -> None:
        """DEGRADED result without 'schema drift' in error is not a drift event."""
        storage = MagicMock()
        storage.get_health_history = AsyncMock(return_value=[
            _result(
                status=ServerStatus.DEGRADED,
                error="some other degradation",
                offset_minutes=5,
            ),
        ])
        with patch("langsight.api.routers.investigate.datetime") as mock_dt:
            mock_dt.now.return_value = _NOW
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            ev = await _gather_evidence("pg", storage, window_hours=1.0)
        assert len(ev["schema_drift_events"]) == 0
        assert ev["degraded_count"] == 1

    async def test_recent_errors_capped_at_five(self) -> None:
        """recent_errors must never exceed 5 entries."""
        storage = MagicMock()
        storage.get_health_history = AsyncMock(return_value=[
            _result(status=ServerStatus.DOWN, error=f"err{i}", offset_minutes=i)
            for i in range(1, 9)
        ])
        with patch("langsight.api.routers.investigate.datetime") as mock_dt:
            mock_dt.now.return_value = _NOW
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            ev = await _gather_evidence("pg", storage, window_hours=2.0)
        assert len(ev["recent_errors"]) <= 5

    async def test_latest_status_reflects_most_recent_result(self) -> None:
        storage = MagicMock()
        storage.get_health_history = AsyncMock(return_value=[
            _result(status=ServerStatus.DOWN, offset_minutes=1),
            _result(status=ServerStatus.UP, offset_minutes=5),
        ])
        with patch("langsight.api.routers.investigate.datetime") as mock_dt:
            mock_dt.now.return_value = _NOW
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            ev = await _gather_evidence("pg", storage, window_hours=1.0)
        # First result in list (offset 1 min) is within window and newest
        assert ev["latest_status"] == "down"

    async def test_server_name_preserved_in_output(self) -> None:
        storage = MagicMock()
        storage.get_health_history = AsyncMock(return_value=[])
        ev = await _gather_evidence("my-special-server", storage, window_hours=1.0)
        assert ev["server_name"] == "my-special-server"

    async def test_window_hours_preserved_in_output(self) -> None:
        storage = MagicMock()
        storage.get_health_history = AsyncMock(return_value=[])
        ev = await _gather_evidence("pg", storage, window_hours=3.5)
        assert ev["window_hours"] == 3.5

    async def test_calls_storage_with_max_history_limit(self) -> None:
        """Storage must be queried with the module-level _MAX_HISTORY limit (20) and project_id."""
        storage = MagicMock()
        storage.get_health_history = AsyncMock(return_value=[])
        await _gather_evidence("pg", storage, window_hours=1.0)
        storage.get_health_history.assert_called_once_with("pg", limit=20, project_id=None)


# ---------------------------------------------------------------------------
# _format_evidence() — unit tests
# ---------------------------------------------------------------------------


class TestFormatEvidence:
    def _base_ev(self, **overrides) -> dict:
        base = {
            "server_name": "pg",
            "window_hours": 1.0,
            "total_checks": 10,
            "up_count": 9,
            "down_count": 1,
            "degraded_count": 0,
            "latest_status": "up",
            "latest_error": None,
            "avg_latency_ms": 55.0,
            "schema_drift_events": [],
            "recent_errors": [],
        }
        base.update(overrides)
        return base

    def test_no_data_server_shows_no_data_message(self) -> None:
        ev = self._base_ev(total_checks=0)
        text = _format_evidence({"pg": ev})
        # No trace activity → generic no-data message
        assert "No health check data" in text or "No data" in text

    def test_server_name_appears_as_heading(self) -> None:
        text = _format_evidence({"my-server": self._base_ev()})
        assert "### my-server" in text

    def test_total_checks_in_output(self) -> None:
        text = _format_evidence({"pg": self._base_ev(total_checks=10)})
        assert "Total checks: 10" in text

    def test_up_down_degraded_counts_in_output(self) -> None:
        text = _format_evidence({"pg": self._base_ev(up_count=8, degraded_count=1, down_count=1)})
        assert "UP: 8" in text
        assert "DEGRADED: 1" in text
        assert "DOWN: 1" in text

    def test_latency_formatted_as_ms(self) -> None:
        text = _format_evidence({"pg": self._base_ev(avg_latency_ms=1234.0)})
        assert "1234ms" in text

    def test_no_latency_shown_as_na(self) -> None:
        text = _format_evidence({"pg": self._base_ev(avg_latency_ms=None)})
        assert "n/a" in text

    def test_latest_error_shown_when_present(self) -> None:
        text = _format_evidence({"pg": self._base_ev(latest_error="connection refused")})
        assert "connection refused" in text

    def test_no_error_shows_none(self) -> None:
        text = _format_evidence({"pg": self._base_ev(latest_error=None)})
        assert "none" in text

    def test_schema_drift_count_in_output(self) -> None:
        drift = [{"checked_at": "2026-03-28T12:00:00+00:00", "error": "schema drift: hash X→Y"}]
        text = _format_evidence({"pg": self._base_ev(schema_drift_events=drift)})
        assert "Schema drift events: 1" in text

    def test_drift_details_included_up_to_three(self) -> None:
        drifts = [
            {"checked_at": f"2026-03-28T12:0{i}:00+00:00", "error": f"drift-{i}"}
            for i in range(5)
        ]
        text = _format_evidence({"pg": self._base_ev(schema_drift_events=drifts)})
        # Only first 3 expanded inline
        assert "drift-0" in text
        assert "drift-1" in text
        assert "drift-2" in text
        assert "drift-3" not in text

    def test_recent_errors_included_when_present(self) -> None:
        errors = [{"checked_at": "2026-03-28T12:00:00+00:00", "error": "i/o timeout"}]
        text = _format_evidence({"pg": self._base_ev(recent_errors=errors)})
        assert "i/o timeout" in text

    def test_multiple_servers_both_appear_in_output(self) -> None:
        ev_map = {
            "server-a": self._base_ev(server_name="server-a"),
            "server-b": self._base_ev(server_name="server-b", total_checks=0),
        }
        text = _format_evidence(ev_map)
        assert "### server-a" in text
        assert "### server-b" in text

    def test_window_hours_in_output(self) -> None:
        text = _format_evidence({"pg": self._base_ev(window_hours=2.5)})
        assert "2.5h" in text


# ---------------------------------------------------------------------------
# _rule_based_report() — unit tests
# ---------------------------------------------------------------------------


class TestRuleBasedReport:
    def _base_ev(self, **overrides) -> dict:
        base = {
            "server_name": "pg",
            "window_hours": 1.0,
            "total_checks": 10,
            "up_count": 10,
            "down_count": 0,
            "degraded_count": 0,
            "latest_status": "up",
            "latest_error": None,
            "avg_latency_ms": 50.0,
            "schema_drift_events": [],
            "recent_errors": [],
        }
        base.update(overrides)
        return base

    def test_all_healthy_produces_healthy_summary(self) -> None:
        report = _rule_based_report({"pg": self._base_ev()})
        assert "Healthy" in report
        assert "All servers are healthy" in report

    def test_healthy_shows_check_count(self) -> None:
        report = _rule_based_report({"pg": self._base_ev(total_checks=7)})
        assert "7 checks" in report

    def test_server_down_produces_unreachable_root_cause(self) -> None:
        ev = self._base_ev(
            latest_status="down",
            down_count=10,
            up_count=0,
            latest_error="connection refused",
        )
        report = _rule_based_report({"pg": ev})
        assert "unreachable" in report.lower()
        assert "connection refused" in report

    def test_majority_down_produces_unreachable_root_cause(self) -> None:
        """When down_pct > 50 the root cause must identify server unreachability."""
        ev = self._base_ev(
            latest_status="up",
            down_count=6,
            up_count=4,
            total_checks=10,
        )
        report = _rule_based_report({"pg": ev})
        assert "unreachable" in report.lower()

    def test_schema_drift_produces_drift_root_cause(self) -> None:
        drift_ts = "2026-03-28T12:00:00+00:00"
        ev = self._base_ev(
            latest_status="degraded",
            schema_drift_events=[{"checked_at": drift_ts, "error": "schema drift: abc→def"}],
        )
        report = _rule_based_report({"pg": ev})
        assert "schema" in report.lower() or "drift" in report.lower()
        assert drift_ts in report

    def test_high_latency_produces_latency_root_cause(self) -> None:
        # latest_status must not be "up" with down_pct==0 and no drift —
        # that branch would be treated as healthy and skip the latency check.
        # Use "degraded" with no down checks so the latency branch is reached.
        ev = self._base_ev(
            avg_latency_ms=2500.0,
            latest_status="degraded",
            up_count=10,
            down_count=0,
            degraded_count=0,
        )
        report = _rule_based_report({"pg": ev})
        assert "latency" in report.lower() or "2500ms" in report

    def test_degraded_without_drift_produces_intermittent_message(self) -> None:
        ev = self._base_ev(
            latest_status="degraded",
            degraded_count=3,
            up_count=7,
            down_count=0,
        )
        report = _rule_based_report({"pg": ev})
        assert "degradation" in report.lower() or "degraded" in report.lower()

    def test_no_data_in_window_says_no_data(self) -> None:
        ev = self._base_ev(total_checks=0)
        report = _rule_based_report({"pg": ev})
        assert "No data" in report

    def test_report_contains_rule_based_header(self) -> None:
        """Always includes the rule-based fallback note."""
        report = _rule_based_report({"pg": self._base_ev()})
        assert "rule-based" in report

    def test_report_contains_anthropic_key_hint(self) -> None:
        """Always ends with a prompt to set ANTHROPIC_API_KEY."""
        report = _rule_based_report({"pg": self._base_ev()})
        assert "ANTHROPIC_API_KEY" in report

    def test_server_name_appears_as_h2_heading(self) -> None:
        report = _rule_based_report({"my-pg": self._base_ev()})
        assert "## my-pg" in report

    def test_down_count_and_total_in_evidence_text(self) -> None:
        ev = self._base_ev(
            latest_status="down",
            down_count=8,
            total_checks=10,
            up_count=2,
            latest_error="timeout",
        )
        report = _rule_based_report({"pg": ev})
        assert "8/10" in report

    def test_multiple_servers_all_listed(self) -> None:
        report = _rule_based_report({
            "alpha": self._base_ev(),
            "beta": self._base_ev(latest_status="down", down_count=5, up_count=5),
        })
        assert "## alpha" in report
        assert "## beta" in report

    def test_not_all_healthy_when_server_has_issues(self) -> None:
        """The 'All servers are healthy' summary must NOT appear when one is down."""
        ev = self._base_ev(latest_status="down", down_count=10, up_count=0)
        report = _rule_based_report({"pg": ev})
        assert "All servers are healthy" not in report


# ---------------------------------------------------------------------------
# App + client fixture (reused across route tests)
# ---------------------------------------------------------------------------


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    cfg = tmp_path / ".langsight.yaml"
    cfg.write_text(yaml.dump({
        "servers": [
            {"name": "pg", "transport": "stdio", "command": "python server.py"},
        ]
    }))
    return cfg


@pytest.fixture
async def client(config_file: Path):
    """ASGI test client with mocked storage, auth disabled."""
    mock_storage = MagicMock()
    mock_storage.list_api_keys = AsyncMock(return_value=[])
    mock_storage.get_api_key_by_hash = AsyncMock(return_value=None)
    mock_storage.get_health_history = AsyncMock(return_value=[
        _result(status=ServerStatus.UP, offset_minutes=5),
    ])
    mock_storage.close = AsyncMock()

    app = create_app(config_path=config_file)
    app.state.storage = mock_storage
    app.state.config = load_config(config_file)
    app.state.auth_disabled = True
    app.state.api_keys = []  # auth disabled

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c, mock_storage


# ---------------------------------------------------------------------------
# run_investigation endpoint — unit tests
# ---------------------------------------------------------------------------


class TestRunInvestigation:
    # --- response shape ---

    async def test_returns_200(self, client) -> None:
        c, _ = client
        r = await c.post("/api/investigate", json={
            "server_names": ["pg"],
            "window_hours": 1.0,
            "provider": "anthropic",
        })
        assert r.status_code == 200

    async def test_response_has_required_fields(self, client) -> None:
        c, _ = client
        r = await c.post("/api/investigate", json={
            "server_names": ["pg"],
            "window_hours": 1.0,
            "provider": "anthropic",
        })
        data = r.json()
        assert "report" in data
        assert "provider_used" in data
        assert "evidence" in data
        assert "generated_at" in data

    async def test_evidence_list_has_one_entry_per_server(self, client) -> None:
        c, mock_storage = client
        mock_storage.get_health_history = AsyncMock(return_value=[
            _result(status=ServerStatus.UP, offset_minutes=5),
        ])
        r = await c.post("/api/investigate", json={
            "server_names": ["pg"],
            "window_hours": 1.0,
            "provider": "anthropic",
        })
        data = r.json()
        assert len(data["evidence"]) == 1
        assert data["evidence"][0]["server_name"] == "pg"

    async def test_evidence_item_has_all_fields(self, client) -> None:
        c, _ = client
        r = await c.post("/api/investigate", json={
            "server_names": ["pg"],
            "window_hours": 1.0,
            "provider": "anthropic",
        })
        item = r.json()["evidence"][0]
        expected_fields = {
            "server_name", "window_hours", "total_checks", "up_count",
            "down_count", "degraded_count", "latest_status", "latest_error",
            "avg_latency_ms", "schema_drift_events", "recent_errors",
        }
        assert expected_fields <= set(item.keys())

    async def test_generated_at_is_iso_format(self, client) -> None:
        c, _ = client
        r = await c.post("/api/investigate", json={
            "server_names": ["pg"],
            "window_hours": 1.0,
            "provider": "anthropic",
        })
        generated_at = r.json()["generated_at"]
        # Must parse as ISO 8601 without raising
        datetime.fromisoformat(generated_at)

    # --- LLM provider success ---

    async def test_uses_llm_report_when_provider_succeeds(self, client) -> None:
        """When LLM succeeds the report field must contain the LLM response."""
        c, _ = client
        mock_provider = AsyncMock()
        mock_provider.analyse = AsyncMock(return_value="## LLM Root Cause\nIt broke.")
        mock_provider.display_name = "Claude claude-sonnet-4-6"

        with patch(
            "langsight.investigate.providers.create_provider",
            return_value=mock_provider,
        ):
            r = await c.post("/api/investigate", json={
                "server_names": ["pg"],
                "window_hours": 1.0,
                "provider": "anthropic",
            })
        data = r.json()
        assert data["report"] == "## LLM Root Cause\nIt broke."
        assert data["provider_used"] == "Claude claude-sonnet-4-6"

    # --- ConfigError fallback ---

    async def test_falls_back_to_rule_based_on_config_error(self, client) -> None:
        """ConfigError from create_provider must produce a rule-based report."""
        c, _ = client
        with patch(
            "langsight.investigate.providers.create_provider",
            side_effect=ConfigError("No API key configured"),
        ):
            r = await c.post("/api/investigate", json={
                "server_names": ["pg"],
                "window_hours": 1.0,
                "provider": "anthropic",
            })
        data = r.json()
        assert r.status_code == 200
        assert "rule-based" in data["report"]
        assert data["provider_used"] == "rule-based"

    async def test_falls_back_to_rule_based_on_config_error_for_openai(self, client) -> None:
        """ConfigError raised for any provider (not just Anthropic) triggers fallback."""
        c, _ = client
        with patch(
            "langsight.investigate.providers.create_provider",
            side_effect=ConfigError("OPENAI_API_KEY not set"),
        ):
            r = await c.post("/api/investigate", json={
                "server_names": ["pg"],
                "window_hours": 1.0,
                "provider": "openai",
            })
        data = r.json()
        assert r.status_code == 200
        assert data["provider_used"] == "rule-based"

    # --- Generic LLM error fallback ---

    async def test_falls_back_to_rule_based_on_llm_exception(self, client) -> None:
        """Any LLM provider exception (network, API error) falls back to rule-based."""
        c, _ = client
        mock_provider = AsyncMock()
        mock_provider.analyse = AsyncMock(side_effect=RuntimeError("API rate limit exceeded"))
        mock_provider.display_name = "Claude claude-sonnet-4-6"

        with patch(
            "langsight.investigate.providers.create_provider",
            return_value=mock_provider,
        ):
            r = await c.post("/api/investigate", json={
                "server_names": ["pg"],
                "window_hours": 1.0,
                "provider": "anthropic",
            })
        data = r.json()
        assert r.status_code == 200
        assert "rule-based" in data["report"]
        assert data["provider_used"] == "rule-based"

    async def test_falls_back_to_rule_based_on_connection_error(self, client) -> None:
        """ConnectionError from LLM provider (e.g. Ollama not running) triggers fallback."""
        c, _ = client
        mock_provider = AsyncMock()
        mock_provider.analyse = AsyncMock(side_effect=ConnectionError("Connection refused"))
        mock_provider.display_name = "Ollama llama3.2"

        with patch(
            "langsight.investigate.providers.create_provider",
            return_value=mock_provider,
        ):
            r = await c.post("/api/investigate", json={
                "server_names": ["pg"],
                "window_hours": 1.0,
                "provider": "ollama",
            })
        data = r.json()
        assert r.status_code == 200
        assert data["provider_used"] == "rule-based"

    # --- Empty server list ---

    async def test_empty_server_names_returns_200(self, client) -> None:
        c, _ = client
        r = await c.post("/api/investigate", json={
            "server_names": [],
            "window_hours": 1.0,
            "provider": "anthropic",
        })
        assert r.status_code == 200

    async def test_empty_server_names_returns_empty_evidence(self, client) -> None:
        c, _ = client
        with patch(
            "langsight.investigate.providers.create_provider",
            side_effect=ConfigError("no key"),
        ):
            r = await c.post("/api/investigate", json={
                "server_names": [],
                "window_hours": 1.0,
                "provider": "anthropic",
            })
        data = r.json()
        assert data["evidence"] == []

    # --- Multiple servers ---

    async def test_multiple_servers_produce_evidence_for_each(self, client) -> None:
        c, mock_storage = client
        mock_storage.get_health_history = AsyncMock(return_value=[
            _result(status=ServerStatus.UP, offset_minutes=5),
        ])
        with patch(
            "langsight.investigate.providers.create_provider",
            side_effect=ConfigError("no key"),
        ):
            r = await c.post("/api/investigate", json={
                "server_names": ["server-a", "server-b", "server-c"],
                "window_hours": 1.0,
                "provider": "anthropic",
            })
        data = r.json()
        assert r.status_code == 200
        assert len(data["evidence"]) == 3
        evidence_names = {e["server_name"] for e in data["evidence"]}
        assert evidence_names == {"server-a", "server-b", "server-c"}

    async def test_multiple_servers_calls_storage_once_per_server(self, client) -> None:
        """Storage must be queried in parallel for each server — gather pattern."""
        c, mock_storage = client
        mock_storage.get_health_history = AsyncMock(return_value=[])
        with patch(
            "langsight.investigate.providers.create_provider",
            side_effect=ConfigError("no key"),
        ):
            await c.post("/api/investigate", json={
                "server_names": ["alpha", "beta"],
                "window_hours": 1.0,
                "provider": "anthropic",
            })
        assert mock_storage.get_health_history.call_count == 2

    # --- provider_used field ---

    async def test_provider_used_is_rule_based_on_config_error(self, client) -> None:
        c, _ = client
        with patch(
            "langsight.investigate.providers.create_provider",
            side_effect=ConfigError("no key"),
        ):
            r = await c.post("/api/investigate", json={
                "server_names": ["pg"],
                "window_hours": 1.0,
                "provider": "anthropic",
            })
        assert r.json()["provider_used"] == "rule-based"

    async def test_provider_used_reflects_llm_display_name_on_success(self, client) -> None:
        c, _ = client
        mock_provider = AsyncMock()
        mock_provider.analyse = AsyncMock(return_value="# Analysis\nAll good.")
        mock_provider.display_name = "Gemini gemini-2.0-flash"

        with patch(
            "langsight.investigate.providers.create_provider",
            return_value=mock_provider,
        ):
            r = await c.post("/api/investigate", json={
                "server_names": ["pg"],
                "window_hours": 1.0,
                "provider": "gemini",
            })
        assert r.json()["provider_used"] == "Gemini gemini-2.0-flash"

    # --- window_hours is respected ---

    async def test_custom_window_hours_forwarded_to_gather_evidence(self, client) -> None:
        """The window_hours from the request body must flow through to evidence."""
        c, _ = client
        with patch(
            "langsight.investigate.providers.create_provider",
            side_effect=ConfigError("no key"),
        ):
            r = await c.post("/api/investigate", json={
                "server_names": ["pg"],
                "window_hours": 6.0,
                "provider": "anthropic",
            })
        data = r.json()
        assert data["evidence"][0]["window_hours"] == 6.0

    # --- project_id forwarded ---

    async def test_project_id_passed_to_gather_evidence(self, client) -> None:
        """project_id from get_active_project_id dependency is forwarded to _gather_evidence.

        After the security fix, project_id comes from the auth dependency, not the
        request body. The test client has no auth, so get_active_project_id returns None.
        """
        c, mock_storage = client
        mock_storage.get_health_history = AsyncMock(return_value=[
            _result(status=ServerStatus.UP, offset_minutes=5),
        ])
        with patch(
            "langsight.api.routers.investigate._gather_evidence",
            wraps=_gather_evidence,
        ) as mock_gather:
            with patch(
                "langsight.investigate.providers.create_provider",
                side_effect=ConfigError("no key"),
            ):
                await c.post("/api/investigate", json={
                    "server_names": ["pg"],
                    "window_hours": 1.0,
                    "provider": "anthropic",
                    "project_id": "proj-abc",  # body field still accepted, but not used for scoping
                })
        # Verify the dependency-resolved project_id (None for unauthenticated test client)
        # is forwarded to _gather_evidence, not the user-supplied body.project_id
        mock_gather.assert_called_once()
        call_project_id = mock_gather.call_args[1].get("project_id") or mock_gather.call_args[0][3]
        assert call_project_id is None  # dependency returns None when no auth/project context
