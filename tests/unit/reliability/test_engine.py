"""Unit tests for P5.4 — Statistical Anomaly Detection (AnomalyDetector + AnomalyResult).

All tests are pure-unit: storage is replaced by MagicMock / AsyncMock. No network,
no database, no Docker required.

asyncio_mode = "auto" is set project-wide in pyproject.toml, so no
@pytest.mark.asyncio decorator is needed on individual test methods.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from langsight.reliability.engine import (
    _MIN_STDDEV_ERROR_RATE,
    _MIN_STDDEV_LATENCY_MS,
    AnomalyDetector,
    AnomalyResult,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_storage(
    *,
    has_baseline: bool = True,
    has_reliability: bool = True,
    baseline_rows: list[dict] | None = None,
    current_rows: list[dict] | None = None,
    raise_on_call: Exception | None = None,
) -> MagicMock:
    """Build a mock storage object with configurable behaviour."""
    storage = MagicMock()

    if not has_baseline:
        # Remove the attribute entirely so hasattr() returns False
        del storage.get_baseline_stats
    if not has_reliability:
        del storage.get_tool_reliability

    if has_baseline and has_reliability:
        if raise_on_call is not None:
            storage.get_baseline_stats = AsyncMock(side_effect=raise_on_call)
            storage.get_tool_reliability = AsyncMock(side_effect=raise_on_call)
        else:
            storage.get_baseline_stats = AsyncMock(return_value=baseline_rows or [])
            storage.get_tool_reliability = AsyncMock(return_value=current_rows or [])

    return storage


def _baseline_row(
    server: str = "srv",
    tool: str = "tool_a",
    error_mean: float = 0.01,
    error_stddev: float = 0.01,
    latency_mean: float = 100.0,
    latency_stddev: float = 10.0,
    sample_hours: int = 168,
) -> dict:
    return {
        "server_name": server,
        "tool_name": tool,
        "baseline_error_mean": error_mean,
        "baseline_error_stddev": error_stddev,
        "baseline_latency_mean": latency_mean,
        "baseline_latency_stddev": latency_stddev,
        "sample_hours": sample_hours,
    }


def _current_row(
    server: str = "srv",
    tool: str = "tool_a",
    total_calls: int = 100,
    error_calls: int = 1,
    avg_latency_ms: float = 105.0,
) -> dict:
    return {
        "server_name": server,
        "tool_name": tool,
        "total_calls": total_calls,
        "success_calls": total_calls - error_calls,
        "error_calls": error_calls,
        "timeout_calls": 0,
        "avg_latency_ms": avg_latency_ms,
        "max_latency_ms": avg_latency_ms * 1.5,
    }


# ---------------------------------------------------------------------------
# TestAnomalyDetector
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAnomalyDetector:
    async def test_returns_empty_when_storage_lacks_baseline_method(self) -> None:
        """Storage without get_baseline_stats must yield an empty result without error."""
        storage = _make_storage(has_baseline=False)
        detector = AnomalyDetector(storage)
        result = await detector.detect()
        assert result == []

    async def test_returns_empty_when_storage_lacks_reliability_method(self) -> None:
        """Storage without get_tool_reliability must yield an empty result without error."""
        storage = _make_storage(has_reliability=False)
        detector = AnomalyDetector(storage)
        result = await detector.detect()
        assert result == []

    async def test_returns_empty_when_no_baseline_data(self) -> None:
        """Empty baseline list means there is nothing to compare against."""
        storage = _make_storage(
            baseline_rows=[],
            current_rows=[_current_row()],
        )
        detector = AnomalyDetector(storage)
        result = await detector.detect()
        assert result == []

    async def test_no_anomaly_when_current_within_threshold(self) -> None:
        """A tool whose z-score is below the threshold must not appear in results."""
        # z for error_rate = (0.02 - 0.01) / 0.01 = 1.0  — below default threshold 2.0
        # z for latency    = (110 - 100) / 10       = 1.0  — also below threshold
        storage = _make_storage(
            baseline_rows=[_baseline_row(error_mean=0.01, error_stddev=0.01,
                                          latency_mean=100.0, latency_stddev=10.0)],
            current_rows=[_current_row(total_calls=100, error_calls=2,
                                        avg_latency_ms=110.0)],
        )
        detector = AnomalyDetector(storage, z_threshold=2.0)
        result = await detector.detect()
        assert result == []

    async def test_warning_anomaly_on_error_rate_spike(self) -> None:
        """Error rate spike with z=4.0 should fire a critical anomaly for error_rate."""
        # baseline error_mean=0.01, stddev=0.01
        # current  error_rate = 5/100 = 0.05
        # z = (0.05 - 0.01) / 0.01 = 4.0  → critical
        storage = _make_storage(
            baseline_rows=[_baseline_row(error_mean=0.01, error_stddev=0.01,
                                          latency_mean=100.0, latency_stddev=10.0)],
            current_rows=[_current_row(total_calls=100, error_calls=5,
                                        avg_latency_ms=105.0)],
        )
        detector = AnomalyDetector(storage, z_threshold=2.0)
        result = await detector.detect()

        error_rate_anomalies = [a for a in result if a.metric == "error_rate"]
        assert len(error_rate_anomalies) == 1
        anomaly = error_rate_anomalies[0]
        assert anomaly.severity == "critical"
        assert abs(anomaly.z_score - 4.0) < 1e-9
        assert anomaly.current_value == pytest.approx(0.05)
        assert anomaly.baseline_mean == pytest.approx(0.01)
        assert anomaly.server_name == "srv"
        assert anomaly.tool_name == "tool_a"

    async def test_warning_severity_when_z_between_2_and_3(self) -> None:
        """z-score of 2.5 (between 2 and 3) must produce severity='warning'."""
        # z_error = (0.035 - 0.01) / 0.01 = 2.5
        storage = _make_storage(
            baseline_rows=[_baseline_row(error_mean=0.01, error_stddev=0.01,
                                          latency_mean=100.0, latency_stddev=10.0)],
            current_rows=[_current_row(total_calls=1000, error_calls=35,
                                        avg_latency_ms=102.0)],
        )
        detector = AnomalyDetector(storage, z_threshold=2.0)
        result = await detector.detect()

        error_anomalies = [a for a in result if a.metric == "error_rate"]
        assert len(error_anomalies) == 1
        assert error_anomalies[0].severity == "warning"
        assert abs(error_anomalies[0].z_score - 2.5) < 1e-9

    async def test_critical_severity_when_z_gte_3(self) -> None:
        """z-score >= 3.0 must produce severity='critical'."""
        # z_error = (0.045 - 0.01) / 0.01 = 3.5
        storage = _make_storage(
            baseline_rows=[_baseline_row(error_mean=0.01, error_stddev=0.01,
                                          latency_mean=100.0, latency_stddev=10.0)],
            current_rows=[_current_row(total_calls=1000, error_calls=45,
                                        avg_latency_ms=102.0)],
        )
        detector = AnomalyDetector(storage, z_threshold=2.0)
        result = await detector.detect()

        error_anomalies = [a for a in result if a.metric == "error_rate"]
        assert len(error_anomalies) == 1
        assert error_anomalies[0].severity == "critical"
        assert abs(error_anomalies[0].z_score - 3.5) < 1e-9

    async def test_skips_tool_with_zero_calls(self) -> None:
        """A current row with total_calls=0 must be silently skipped."""
        storage = _make_storage(
            baseline_rows=[_baseline_row()],
            current_rows=[_current_row(total_calls=0, error_calls=0)],
        )
        detector = AnomalyDetector(storage, z_threshold=2.0)
        result = await detector.detect()
        assert result == []

    async def test_skips_tool_with_no_baseline_entry(self) -> None:
        """A tool that appears in current data but has no baseline row must be skipped."""
        storage = _make_storage(
            # Baseline is for a *different* tool
            baseline_rows=[_baseline_row(tool="other_tool")],
            current_rows=[_current_row(tool="tool_a", total_calls=100, error_calls=50)],
        )
        detector = AnomalyDetector(storage, z_threshold=2.0)
        result = await detector.detect()
        assert result == []

    async def test_latency_anomaly_detected(self) -> None:
        """A latency spike well above baseline mean must fire an avg_latency_ms anomaly."""
        # z_latency = (250 - 100) / 10 = 15.0 → critical
        storage = _make_storage(
            baseline_rows=[_baseline_row(error_mean=0.01, error_stddev=0.01,
                                          latency_mean=100.0, latency_stddev=10.0)],
            current_rows=[_current_row(total_calls=100, error_calls=1,
                                        avg_latency_ms=250.0)],
        )
        detector = AnomalyDetector(storage, z_threshold=2.0)
        result = await detector.detect()

        latency_anomalies = [a for a in result if a.metric == "avg_latency_ms"]
        assert len(latency_anomalies) == 1
        anomaly = latency_anomalies[0]
        assert anomaly.severity == "critical"
        assert abs(anomaly.z_score - 15.0) < 1e-9
        assert anomaly.current_value == pytest.approx(250.0)
        assert anomaly.baseline_mean == pytest.approx(100.0)

    async def test_min_stddev_guard_error_rate(self) -> None:
        """When baseline stddev < _MIN_STDDEV_ERROR_RATE, effective stddev is clamped.

        baseline stddev = 0.001  →  clamped to 0.01
        current error_rate = 0.04
        z = (0.04 - 0.01) / 0.01 = 3.0  (not 30.0 as raw stddev would give)
        """
        storage = _make_storage(
            baseline_rows=[_baseline_row(error_mean=0.01, error_stddev=0.001,
                                          latency_mean=100.0, latency_stddev=10.0)],
            current_rows=[_current_row(total_calls=100, error_calls=4,
                                        avg_latency_ms=105.0)],
        )
        detector = AnomalyDetector(storage, z_threshold=2.0)
        result = await detector.detect()

        error_anomalies = [a for a in result if a.metric == "error_rate"]
        assert len(error_anomalies) == 1
        anomaly = error_anomalies[0]
        # effective_stddev was clamped to _MIN_STDDEV_ERROR_RATE
        assert anomaly.baseline_stddev == pytest.approx(_MIN_STDDEV_ERROR_RATE)
        # z = (0.04 - 0.01) / 0.01 = 3.0
        assert abs(anomaly.z_score - 3.0) < 1e-9

    async def test_min_stddev_guard_latency(self) -> None:
        """When baseline latency stddev < _MIN_STDDEV_LATENCY_MS, it is clamped.

        baseline latency stddev = 1.0  →  clamped to 10.0
        current latency = 130ms
        z = (130 - 100) / 10.0 = 3.0  (not 30.0)
        """
        storage = _make_storage(
            baseline_rows=[_baseline_row(error_mean=0.01, error_stddev=0.01,
                                          latency_mean=100.0, latency_stddev=1.0)],
            current_rows=[_current_row(total_calls=100, error_calls=1,
                                        avg_latency_ms=130.0)],
        )
        detector = AnomalyDetector(storage, z_threshold=2.0)
        result = await detector.detect()

        latency_anomalies = [a for a in result if a.metric == "avg_latency_ms"]
        assert len(latency_anomalies) == 1
        anomaly = latency_anomalies[0]
        assert anomaly.baseline_stddev == pytest.approx(_MIN_STDDEV_LATENCY_MS)
        assert abs(anomaly.z_score - 3.0) < 1e-9

    async def test_results_sorted_by_abs_z_score_descending(self) -> None:
        """Returned anomalies must be ordered highest |z| first."""
        # tool_a: z_latency ≈ 20.0, tool_b: z_error ≈ 5.0
        storage = _make_storage(
            baseline_rows=[
                _baseline_row(server="srv", tool="tool_a",
                               error_mean=0.01, error_stddev=0.01,
                               latency_mean=100.0, latency_stddev=10.0),
                _baseline_row(server="srv", tool="tool_b",
                               error_mean=0.01, error_stddev=0.01,
                               latency_mean=100.0, latency_stddev=10.0),
            ],
            current_rows=[
                # tool_a: latency z = (300-100)/10 = 20, error z = (0.01-0.01)/0.01 = 0
                _current_row(server="srv", tool="tool_a",
                              total_calls=100, error_calls=1, avg_latency_ms=300.0),
                # tool_b: latency z = 0, error z = (0.06-0.01)/0.01 = 5
                _current_row(server="srv", tool="tool_b",
                              total_calls=100, error_calls=6, avg_latency_ms=100.0),
            ],
        )
        detector = AnomalyDetector(storage, z_threshold=2.0)
        result = await detector.detect()

        assert len(result) >= 2
        z_scores = [abs(a.z_score) for a in result]
        assert z_scores == sorted(z_scores, reverse=True)
        # Highest z is tool_a latency at 20.0
        assert result[0].tool_name == "tool_a"
        assert result[0].metric == "avg_latency_ms"

    async def test_returns_empty_on_storage_error(self) -> None:
        """A storage exception during detect() must be swallowed and return empty list."""
        storage = _make_storage(raise_on_call=RuntimeError("ClickHouse unreachable"))
        detector = AnomalyDetector(storage, z_threshold=2.0)
        # Must not raise
        result = await detector.detect()
        assert result == []

    async def test_custom_z_threshold_respected(self) -> None:
        """Detector with z_threshold=3.0 must not fire on z=2.5."""
        # z_error = (0.035 - 0.01) / 0.01 = 2.5
        storage = _make_storage(
            baseline_rows=[_baseline_row(error_mean=0.01, error_stddev=0.01,
                                          latency_mean=100.0, latency_stddev=10.0)],
            current_rows=[_current_row(total_calls=1000, error_calls=35,
                                        avg_latency_ms=102.0)],
        )
        detector = AnomalyDetector(storage, z_threshold=3.0)
        result = await detector.detect()
        assert result == []

    async def test_sample_hours_propagated_from_baseline(self) -> None:
        """sample_hours on the AnomalyResult must come from the baseline row."""
        storage = _make_storage(
            baseline_rows=[_baseline_row(sample_hours=336,
                                          error_mean=0.01, error_stddev=0.01,
                                          latency_mean=100.0, latency_stddev=10.0)],
            current_rows=[_current_row(total_calls=100, error_calls=5,
                                        avg_latency_ms=105.0)],
        )
        detector = AnomalyDetector(storage, z_threshold=2.0)
        result = await detector.detect()

        assert len(result) >= 1
        assert all(a.sample_hours == 336 for a in result)


# ---------------------------------------------------------------------------
# TestAnomalyResult
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAnomalyResult:
    def _make_result(self, **kwargs) -> AnomalyResult:
        defaults = dict(
            server_name="srv",
            tool_name="tool_a",
            metric="error_rate",
            current_value=0.05,
            baseline_mean=0.01,
            baseline_stddev=0.01,
            z_score=4.0,
            severity="critical",
            sample_hours=168,
        )
        defaults.update(kwargs)
        return AnomalyResult(**defaults)

    def test_to_dict_has_all_required_keys(self) -> None:
        """to_dict() must include all nine canonical keys."""
        result = self._make_result()
        d = result.to_dict()
        expected_keys = {
            "server_name",
            "tool_name",
            "metric",
            "current_value",
            "baseline_mean",
            "baseline_stddev",
            "z_score",
            "severity",
            "sample_hours",
        }
        assert set(d.keys()) == expected_keys

    def test_to_dict_rounds_floats(self) -> None:
        """Floats in to_dict() must be rounded to 4 dp (current_value, baseline_mean,
        baseline_stddev) and 2 dp (z_score)."""
        result = self._make_result(
            current_value=0.0512345,
            baseline_mean=0.0099999,
            baseline_stddev=0.0100001,
            z_score=3.999999,
        )
        d = result.to_dict()
        assert d["current_value"] == round(0.0512345, 4)
        assert d["baseline_mean"] == round(0.0099999, 4)
        assert d["baseline_stddev"] == round(0.0100001, 4)
        assert d["z_score"] == round(3.999999, 2)

    def test_to_dict_preserves_string_fields(self) -> None:
        """String fields must pass through to_dict() unchanged."""
        result = self._make_result(
            server_name="my-server",
            tool_name="my-tool",
            metric="avg_latency_ms",
            severity="warning",
        )
        d = result.to_dict()
        assert d["server_name"] == "my-server"
        assert d["tool_name"] == "my-tool"
        assert d["metric"] == "avg_latency_ms"
        assert d["severity"] == "warning"

    def test_to_dict_preserves_sample_hours(self) -> None:
        """sample_hours (int) must survive the to_dict() round-trip unchanged."""
        result = self._make_result(sample_hours=336)
        assert result.to_dict()["sample_hours"] == 336

    def test_severity_warning_label(self) -> None:
        """AnomalyResult with severity='warning' stores the value correctly."""
        result = self._make_result(severity="warning", z_score=2.5)
        assert result.severity == "warning"
        assert result.to_dict()["severity"] == "warning"

    def test_severity_critical_label(self) -> None:
        """AnomalyResult with severity='critical' stores the value correctly."""
        result = self._make_result(severity="critical", z_score=3.5)
        assert result.severity == "critical"
        assert result.to_dict()["severity"] == "critical"
