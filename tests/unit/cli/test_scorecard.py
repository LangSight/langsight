"""Unit tests for ``langsight scorecard`` CLI command.

Coverage:
  - Healthy servers → table printed, exit 0
  - JSON output (--json flag)
  - --server filters to a single server
  - --server with unknown name → exit 1
  - No servers configured → exit 1
  - DOWN server → grade reflects outage (consecutive_failures, uptime)
  - --fail-below exits 1 when grade is worse than threshold
  - --fail-below exits 0 when all grades meet the threshold
  - Server names appear in table output
  - Grade column present in output
  - JSON output contains all required keys
  - _build_state populates from current health result when no storage
  - _build_state populates from history when storage is available
  - _dimension_pts formats correctly
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml
from click.testing import CliRunner

from langsight.cli.main import cli
from langsight.cli.scorecard import _build_state, _dimension_pts
from langsight.health.scorecard import ScorecardEngine, ScorecardResult, ServerHealthState
from langsight.models import HealthCheckResult, ServerStatus

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

UP_RESULT = HealthCheckResult(
    server_name="test-pg",
    status=ServerStatus.UP,
    latency_ms=42.0,
    tools_count=5,
    schema_hash="abc123def456ab12",
)
DOWN_RESULT = HealthCheckResult(
    server_name="test-pg",
    status=ServerStatus.DOWN,
    latency_ms=None,
    error="connection refused",
)


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    cfg = tmp_path / ".langsight.yaml"
    cfg.write_text(
        yaml.dump({
            "servers": [{"name": "test-pg", "transport": "stdio", "command": "python server.py"}]
        })
    )
    return cfg


@pytest.fixture
def two_server_config(tmp_path: Path) -> Path:
    cfg = tmp_path / ".langsight.yaml"
    cfg.write_text(
        yaml.dump({
            "servers": [
                {"name": "pg", "transport": "stdio", "command": "python pg.py"},
                {"name": "s3", "transport": "stdio", "command": "python s3.py"},
            ]
        })
    )
    return cfg


def _mock_storage() -> MagicMock:
    storage = MagicMock()
    storage.get_health_history = AsyncMock(return_value=[])
    storage.close = AsyncMock()
    return storage


def _up_scorecard(server_name: str = "test-pg") -> ScorecardResult:
    state = ServerHealthState(
        server_name=server_name,
        total_checks_7d=1,
        successful_checks_7d=1,
        current_p99_ms=42.0,
    )
    return ScorecardEngine.compute(state)


# ---------------------------------------------------------------------------
# Basic invocation
# ---------------------------------------------------------------------------

class TestScorecardCommand:
    def test_shows_table_on_success(self, config_file: Path) -> None:
        runner = CliRunner()
        storage = _mock_storage()
        with patch("langsight.cli.scorecard.try_open_storage", new_callable=AsyncMock, return_value=storage):
            with patch("langsight.cli.scorecard.HealthChecker") as MockChecker:
                MockChecker.return_value.check_many = AsyncMock(return_value=[UP_RESULT])
                result = runner.invoke(cli, ["scorecard", "--config", str(config_file)])

        assert result.exit_code == 0
        assert "test-pg" in result.output

    def test_grade_column_present(self, config_file: Path) -> None:
        runner = CliRunner()
        storage = _mock_storage()
        with patch("langsight.cli.scorecard.try_open_storage", new_callable=AsyncMock, return_value=storage):
            with patch("langsight.cli.scorecard.HealthChecker") as MockChecker:
                MockChecker.return_value.check_many = AsyncMock(return_value=[UP_RESULT])
                result = runner.invoke(cli, ["scorecard", "--config", str(config_file)])

        assert result.exit_code == 0
        assert "Grade" in result.output

    def test_both_server_names_shown_with_two_servers(self, two_server_config: Path) -> None:
        pg_result = HealthCheckResult(server_name="pg", status=ServerStatus.UP, latency_ms=30.0)
        s3_result = HealthCheckResult(server_name="s3", status=ServerStatus.UP, latency_ms=60.0)
        runner = CliRunner()
        storage = _mock_storage()
        with patch("langsight.cli.scorecard.try_open_storage", new_callable=AsyncMock, return_value=storage):
            with patch("langsight.cli.scorecard.HealthChecker") as MockChecker:
                MockChecker.return_value.check_many = AsyncMock(return_value=[pg_result, s3_result])
                result = runner.invoke(cli, ["scorecard", "--config", str(two_server_config)])

        assert result.exit_code == 0
        assert "pg" in result.output
        assert "s3" in result.output

    def test_exits_1_when_no_servers_configured(self, tmp_path: Path) -> None:
        cfg = tmp_path / ".langsight.yaml"
        cfg.write_text(yaml.dump({"servers": []}))
        runner = CliRunner()
        result = runner.invoke(cli, ["scorecard", "--config", str(cfg)])
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# --json flag
# ---------------------------------------------------------------------------

class TestJsonOutput:
    def test_json_flag_outputs_valid_json(self, config_file: Path) -> None:
        runner = CliRunner()
        storage = _mock_storage()
        with patch("langsight.cli.scorecard.try_open_storage", new_callable=AsyncMock, return_value=storage):
            with patch("langsight.cli.scorecard.HealthChecker") as MockChecker:
                MockChecker.return_value.check_many = AsyncMock(return_value=[UP_RESULT])
                result = runner.invoke(cli, ["scorecard", "--config", str(config_file), "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 1

    def test_json_contains_required_keys(self, config_file: Path) -> None:
        runner = CliRunner()
        storage = _mock_storage()
        with patch("langsight.cli.scorecard.try_open_storage", new_callable=AsyncMock, return_value=storage):
            with patch("langsight.cli.scorecard.HealthChecker") as MockChecker:
                MockChecker.return_value.check_many = AsyncMock(return_value=[UP_RESULT])
                result = runner.invoke(cli, ["scorecard", "--config", str(config_file), "--json"])

        data = json.loads(result.output)
        entry = data[0]
        assert "server_name" in entry
        assert "grade" in entry
        assert "score" in entry
        assert "dimensions" in entry
        assert "cap_applied" in entry
        assert "computed_at" in entry

    def test_json_server_name_matches(self, config_file: Path) -> None:
        runner = CliRunner()
        storage = _mock_storage()
        with patch("langsight.cli.scorecard.try_open_storage", new_callable=AsyncMock, return_value=storage):
            with patch("langsight.cli.scorecard.HealthChecker") as MockChecker:
                MockChecker.return_value.check_many = AsyncMock(return_value=[UP_RESULT])
                result = runner.invoke(cli, ["scorecard", "--config", str(config_file), "--json"])

        data = json.loads(result.output)
        assert data[0]["server_name"] == "test-pg"

    def test_json_dimensions_has_five_entries(self, config_file: Path) -> None:
        runner = CliRunner()
        storage = _mock_storage()
        with patch("langsight.cli.scorecard.try_open_storage", new_callable=AsyncMock, return_value=storage):
            with patch("langsight.cli.scorecard.HealthChecker") as MockChecker:
                MockChecker.return_value.check_many = AsyncMock(return_value=[UP_RESULT])
                result = runner.invoke(cli, ["scorecard", "--config", str(config_file), "--json"])

        data = json.loads(result.output)
        assert len(data[0]["dimensions"]) == 5


# ---------------------------------------------------------------------------
# --server filter
# ---------------------------------------------------------------------------

class TestServerFilter:
    def test_server_flag_filters_to_one_server(self, two_server_config: Path) -> None:
        pg_result = HealthCheckResult(server_name="pg", status=ServerStatus.UP, latency_ms=30.0)
        runner = CliRunner()
        storage = _mock_storage()
        with patch("langsight.cli.scorecard.try_open_storage", new_callable=AsyncMock, return_value=storage):
            with patch("langsight.cli.scorecard.HealthChecker") as MockChecker:
                MockChecker.return_value.check_many = AsyncMock(return_value=[pg_result])
                result = runner.invoke(
                    cli, ["scorecard", "--config", str(two_server_config), "--server", "pg"]
                )

        assert result.exit_code == 0
        assert "pg" in result.output

    def test_unknown_server_name_exits_1(self, config_file: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli, ["scorecard", "--config", str(config_file), "--server", "no-such-server"]
        )
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# --fail-below
# ---------------------------------------------------------------------------

class TestFailBelow:
    def test_fail_below_a_exits_1_when_grade_is_b(self, config_file: Path) -> None:
        """A server with critical finding gets capped at B — fails --fail-below A."""
        critical_result = HealthCheckResult(
            server_name="test-pg",
            status=ServerStatus.UP,
            latency_ms=100.0,
        )
        runner = CliRunner()
        storage = _mock_storage()
        # Patch ScorecardEngine.compute to return a B grade
        b_grade_state = ServerHealthState(
            server_name="test-pg",
            total_checks_7d=1,
            successful_checks_7d=1,
            critical_findings=1,  # forces cap at B
        )
        b_result = ScorecardEngine.compute(b_grade_state)
        with patch("langsight.cli.scorecard.try_open_storage", new_callable=AsyncMock, return_value=storage):
            with patch("langsight.cli.scorecard.HealthChecker") as MockChecker:
                MockChecker.return_value.check_many = AsyncMock(return_value=[critical_result])
                with patch("langsight.cli.scorecard.ScorecardEngine") as MockEngine:
                    MockEngine.compute.return_value = b_result
                    result = runner.invoke(
                        cli, ["scorecard", "--config", str(config_file), "--fail-below", "A"]
                    )

        assert result.exit_code == 1

    def test_fail_below_b_exits_0_when_all_grades_meet_threshold(self, config_file: Path) -> None:
        runner = CliRunner()
        storage = _mock_storage()
        a_result = _up_scorecard("test-pg")  # A or A+ grade
        with patch("langsight.cli.scorecard.try_open_storage", new_callable=AsyncMock, return_value=storage):
            with patch("langsight.cli.scorecard.HealthChecker") as MockChecker:
                MockChecker.return_value.check_many = AsyncMock(return_value=[UP_RESULT])
                with patch("langsight.cli.scorecard.ScorecardEngine") as MockEngine:
                    MockEngine.compute.return_value = a_result
                    result = runner.invoke(
                        cli, ["scorecard", "--config", str(config_file), "--fail-below", "B"]
                    )

        assert result.exit_code == 0

    def test_fail_below_invalid_choice_exits_2(self, config_file: Path) -> None:
        """Only A, B, C, D are valid --fail-below values."""
        runner = CliRunner()
        result = runner.invoke(
            cli, ["scorecard", "--config", str(config_file), "--fail-below", "Z"]
        )
        assert result.exit_code == 2


# ---------------------------------------------------------------------------
# _build_state helper (unit-level, no Click involved)
# ---------------------------------------------------------------------------

class TestBuildState:
    @pytest.mark.asyncio
    async def test_up_result_seeds_one_successful_check(self) -> None:
        state = await _build_state("my-srv", UP_RESULT, storage=None)
        assert state.total_checks_7d == 1
        assert state.successful_checks_7d == 1
        assert state.consecutive_failures == 0

    @pytest.mark.asyncio
    async def test_down_result_seeds_one_failed_check(self) -> None:
        state = await _build_state("my-srv", DOWN_RESULT, storage=None)
        assert state.total_checks_7d == 1
        assert state.successful_checks_7d == 0
        assert state.consecutive_failures == 1

    @pytest.mark.asyncio
    async def test_latency_passed_as_current_p99(self) -> None:
        state = await _build_state("my-srv", UP_RESULT, storage=None)
        assert state.current_p99_ms == pytest.approx(42.0)

    @pytest.mark.asyncio
    async def test_no_storage_returns_without_history(self) -> None:
        """When storage is None, _build_state returns early with seed data only."""
        state = await _build_state("my-srv", UP_RESULT, storage=None)
        # No history enrichment — baseline is still None
        assert state.baseline_p99_ms is None

    @pytest.mark.asyncio
    async def test_storage_enriches_from_history(self) -> None:
        """When storage returns history, state reflects actual 7-day data."""
        from datetime import UTC, datetime, timedelta
        history = [
            HealthCheckResult(
                server_name="my-srv",
                status=ServerStatus.UP,
                latency_ms=100.0,
                checked_at=datetime.now(UTC) - timedelta(hours=1),
            ),
            HealthCheckResult(
                server_name="my-srv",
                status=ServerStatus.UP,
                latency_ms=200.0,
                checked_at=datetime.now(UTC) - timedelta(hours=2),
            ),
            HealthCheckResult(
                server_name="my-srv",
                status=ServerStatus.DOWN,
                latency_ms=None,
                checked_at=datetime.now(UTC) - timedelta(hours=3),
            ),
        ]
        storage = MagicMock()
        storage.get_health_history = AsyncMock(return_value=history)

        state = await _build_state("my-srv", UP_RESULT, storage=storage)
        assert state.total_checks_7d == 3
        assert state.successful_checks_7d == 2
        assert state.consecutive_failures == 0  # most recent is UP

    @pytest.mark.asyncio
    async def test_storage_counts_consecutive_failures(self) -> None:
        """Consecutive failures are counted from the most-recent records."""
        from datetime import UTC, datetime, timedelta
        history = [
            HealthCheckResult(
                server_name="my-srv",
                status=ServerStatus.DOWN,
                checked_at=datetime.now(UTC) - timedelta(minutes=5),
            ),
            HealthCheckResult(
                server_name="my-srv",
                status=ServerStatus.DOWN,
                checked_at=datetime.now(UTC) - timedelta(minutes=10),
            ),
            HealthCheckResult(
                server_name="my-srv",
                status=ServerStatus.UP,
                latency_ms=50.0,
                checked_at=datetime.now(UTC) - timedelta(minutes=15),
            ),
        ]
        storage = MagicMock()
        storage.get_health_history = AsyncMock(return_value=history)

        state = await _build_state("my-srv", DOWN_RESULT, storage=storage)
        assert state.consecutive_failures == 2

    @pytest.mark.asyncio
    async def test_storage_error_falls_back_to_seed(self) -> None:
        """If storage.get_health_history raises, _build_state falls back to seed data."""
        storage = MagicMock()
        storage.get_health_history = AsyncMock(side_effect=RuntimeError("DB offline"))

        state = await _build_state("my-srv", UP_RESULT, storage=storage)
        # Falls back to seed — single check from live result
        assert state.total_checks_7d == 1
        assert state.successful_checks_7d == 1


# ---------------------------------------------------------------------------
# _dimension_pts helper
# ---------------------------------------------------------------------------

class TestDimensionPts:
    def test_perfect_availability_shows_30_of_30(self) -> None:
        state = ServerHealthState(
            server_name="srv",
            total_checks_7d=100,
            successful_checks_7d=100,
        )
        result = ScorecardEngine.compute(state)
        pts = _dimension_pts(result, "availability")
        assert pts == "30/30"

    def test_unknown_dimension_name_returns_dash(self) -> None:
        state = ServerHealthState(server_name="srv")
        result = ScorecardEngine.compute(state)
        pts = _dimension_pts(result, "nonexistent_dimension")
        assert pts == "—"

    def test_security_max_pts_is_25(self) -> None:
        state = ServerHealthState(server_name="srv")
        result = ScorecardEngine.compute(state)
        pts = _dimension_pts(result, "security")
        assert pts.endswith("/25")

    def test_reliability_max_pts_is_20(self) -> None:
        state = ServerHealthState(server_name="srv")
        result = ScorecardEngine.compute(state)
        pts = _dimension_pts(result, "reliability")
        assert pts.endswith("/20")

    def test_schema_stability_max_pts_is_15(self) -> None:
        state = ServerHealthState(server_name="srv")
        result = ScorecardEngine.compute(state)
        pts = _dimension_pts(result, "schema_stability")
        assert pts.endswith("/15")

    def test_performance_max_pts_is_10(self) -> None:
        state = ServerHealthState(server_name="srv")
        result = ScorecardEngine.compute(state)
        pts = _dimension_pts(result, "performance")
        assert pts.endswith("/10")
