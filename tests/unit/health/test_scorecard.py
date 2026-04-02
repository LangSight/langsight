"""Unit tests for ScorecardEngine.compute() and supporting helpers.

ScorecardEngine.compute() is a pure function (no I/O, no mocking needed).
Tests verify score values, grade thresholds, cap rules, and A+ eligibility.
"""

from __future__ import annotations

import pytest

from langsight.health.scorecard import (
    ScorecardEngine,
    ScorecardResult,
    ServerHealthState,
    _numeric_to_grade,
)

# ---------------------------------------------------------------------------
# Helper: build a perfect-server state
# ---------------------------------------------------------------------------


def _perfect_state(name: str = "postgres-mcp") -> ServerHealthState:
    """A server with perfect scores across all dimensions."""
    return ServerHealthState(
        server_name=name,
        total_checks_7d=1000,
        successful_checks_7d=1000,          # 100% uptime
        consecutive_failures=0,
        critical_findings=0,
        high_findings=0,
        medium_findings=0,
        low_findings=0,
        has_active_critical_cve=False,
        is_confirmed_poisoned=False,
        has_authentication=True,
        error_rate_pct=0.0,
        latency_cv=0.0,
        breaking_drifts_7d=0,
        compatible_drifts_7d=0,
        untracked_drifts=0,
        current_p99_ms=100.0,
        baseline_p99_ms=100.0,
        security_scanned=True,
    )


# ---------------------------------------------------------------------------
# Grade threshold tests
# ---------------------------------------------------------------------------


class TestGradeThresholds:
    @pytest.mark.parametrize("score,expected_grade", [
        (95.0, "A"),
        (90.0, "A"),
        (89.9, "B"),
        (80.0, "B"),
        (79.9, "C"),
        (65.0, "C"),
        (64.9, "D"),
        (50.0, "D"),
        (49.9, "F"),
        (0.0, "F"),
    ])
    def test_grade_thresholds(self, score: float, expected_grade: str) -> None:
        """Boundary scores map to the correct letter grades."""
        assert _numeric_to_grade(score) == expected_grade


# ---------------------------------------------------------------------------
# A+ eligibility
# ---------------------------------------------------------------------------


class TestAPlusGrade:
    def test_perfect_server_gets_a_plus(self) -> None:
        """A server with 100% uptime, zero findings, zero drift → A+."""
        state = _perfect_state()
        result = ScorecardEngine.compute(state)
        assert result.grade == "A+"

    def test_a_plus_requires_all_conditions(self) -> None:
        """A+ requires 99.9%+ uptime, zero critical/high findings, zero drift."""
        # 99.9% uptime — just enough for A+
        state = ServerHealthState(
            server_name="good-server",
            total_checks_7d=1000,
            successful_checks_7d=999,    # 99.9%
            consecutive_failures=0,
            has_authentication=True,
            has_active_critical_cve=False,
            is_confirmed_poisoned=False,
            breaking_drifts_7d=0,
            compatible_drifts_7d=0,
        )
        result = ScorecardEngine.compute(state)
        assert result.grade in ("A+", "A")  # at boundary — A or A+

    def test_breaking_drift_prevents_a_plus(self) -> None:
        """A server with 100% uptime but breaking drift cannot achieve A+."""
        state = _perfect_state()
        state_with_drift = ServerHealthState(
            server_name=state.server_name,
            total_checks_7d=state.total_checks_7d,
            successful_checks_7d=state.successful_checks_7d,
            consecutive_failures=0,
            has_authentication=True,
            has_active_critical_cve=False,
            is_confirmed_poisoned=False,
            breaking_drifts_7d=1,      # one breaking drift
            compatible_drifts_7d=0,
        )
        result = ScorecardEngine.compute(state_with_drift)
        assert result.grade != "A+"

    def test_high_finding_prevents_a_plus(self) -> None:
        """A server with a high security finding cannot achieve A+."""
        state = ServerHealthState(
            server_name="server",
            total_checks_7d=1000,
            successful_checks_7d=1000,
            consecutive_failures=0,
            high_findings=1,           # one high finding
            has_authentication=True,
            has_active_critical_cve=False,
            is_confirmed_poisoned=False,
        )
        result = ScorecardEngine.compute(state)
        assert result.grade != "A+"


# ---------------------------------------------------------------------------
# Availability — zero checks
# ---------------------------------------------------------------------------


class TestZeroAvailability:
    def test_server_with_no_checks_gets_zero_availability(self) -> None:
        """A server with no checks recorded scores 0 on availability dimension."""
        state = ServerHealthState(
            server_name="new-server",
            total_checks_7d=0,
            successful_checks_7d=0,
        )
        result = ScorecardEngine.compute(state)
        avail = next(d for d in result.dimensions if d.name == "availability")
        assert avail.score == 0.0

    def test_zero_checks_results_in_low_overall_score(self) -> None:
        """Zero availability (weight 30%) pulls overall score well below A."""
        state = ServerHealthState(
            server_name="new-server",
            total_checks_7d=0,
            successful_checks_7d=0,
        )
        result = ScorecardEngine.compute(state)
        # 0 * 0.30 + 100 * (rest) → at most 70. Can't be A (needs 90)
        assert result.score < 90


# ---------------------------------------------------------------------------
# Fatal flaw veto caps (→ F)
# ---------------------------------------------------------------------------


class TestFatalFlawVetoCaps:
    def test_critical_cve_forces_f_regardless_of_score(self) -> None:
        """has_active_critical_cve=True always produces grade F, regardless of score."""
        state = _perfect_state()
        state_with_cve = ServerHealthState(
            server_name=state.server_name,
            total_checks_7d=state.total_checks_7d,
            successful_checks_7d=state.successful_checks_7d,
            has_active_critical_cve=True,   # fatal flaw
            is_confirmed_poisoned=False,
            has_authentication=True,
        )
        result = ScorecardEngine.compute(state_with_cve)
        assert result.grade == "F"
        assert result.cap_applied is not None
        assert "CVE" in result.cap_applied or "cve" in result.cap_applied.lower()

    def test_poisoned_server_forces_f(self) -> None:
        """is_confirmed_poisoned=True always produces grade F."""
        state = _perfect_state()
        state_poisoned = ServerHealthState(
            server_name=state.server_name,
            total_checks_7d=state.total_checks_7d,
            successful_checks_7d=state.successful_checks_7d,
            has_active_critical_cve=False,
            is_confirmed_poisoned=True,     # fatal flaw
            has_authentication=True,
        )
        result = ScorecardEngine.compute(state_poisoned)
        assert result.grade == "F"
        assert result.cap_applied is not None
        assert "poison" in result.cap_applied.lower()

    def test_10_consecutive_failures_forces_f(self) -> None:
        """10 or more consecutive failures forces grade F."""
        state = ServerHealthState(
            server_name="failing-server",
            total_checks_7d=100,
            successful_checks_7d=90,
            consecutive_failures=10,
            has_active_critical_cve=False,
            is_confirmed_poisoned=False,
            has_authentication=True,
        )
        result = ScorecardEngine.compute(state)
        assert result.grade == "F"
        assert result.cap_applied is not None

    def test_9_consecutive_failures_does_not_force_f(self) -> None:
        """9 consecutive failures does NOT trigger the 10+ consecutive-failure cap."""
        state = ServerHealthState(
            server_name="almost-failing",
            total_checks_7d=1000,
            successful_checks_7d=1000,
            consecutive_failures=9,
            has_active_critical_cve=False,
            is_confirmed_poisoned=False,
            has_authentication=True,
        )
        result = ScorecardEngine.compute(state)
        assert result.grade != "F" or result.cap_applied is None or "consecutive" not in result.cap_applied


# ---------------------------------------------------------------------------
# Cap at D — uptime below 90%
# ---------------------------------------------------------------------------


class TestCapAtD:
    def test_90_pct_uptime_caps_at_d(self) -> None:
        """Uptime below 90% caps the grade at D (or worse)."""
        state = ServerHealthState(
            server_name="flaky-server",
            total_checks_7d=100,
            successful_checks_7d=89,    # 89% uptime — below 90%
            consecutive_failures=0,
            has_active_critical_cve=False,
            is_confirmed_poisoned=False,
            has_authentication=True,
        )
        result = ScorecardEngine.compute(state)
        grade_order = ["A+", "A", "B", "C", "D", "F"]
        # Grade must be D or F
        assert grade_order.index(result.grade) >= grade_order.index("D")

    def test_exactly_90_pct_uptime_not_capped_at_d(self) -> None:
        """Exactly 90% uptime does NOT trigger the 'uptime below 90%' cap."""
        state = ServerHealthState(
            server_name="borderline",
            total_checks_7d=1000,
            successful_checks_7d=900,   # exactly 90%
            consecutive_failures=0,
            has_active_critical_cve=False,
            is_confirmed_poisoned=False,
            has_authentication=True,
        )
        result = ScorecardEngine.compute(state)
        # Should NOT be capped at D solely due to uptime
        assert result.cap_applied is None or "90%" not in (result.cap_applied or "")


# ---------------------------------------------------------------------------
# Cap at C — no authentication
# ---------------------------------------------------------------------------


class TestCapAtC:
    def test_no_auth_caps_at_c(self) -> None:
        """has_authentication=False caps the grade at C (or worse)."""
        state = ServerHealthState(
            server_name="open-server",
            total_checks_7d=1000,
            successful_checks_7d=1000,
            consecutive_failures=0,
            has_authentication=False,   # no auth
            has_active_critical_cve=False,
            is_confirmed_poisoned=False,
        )
        result = ScorecardEngine.compute(state)
        grade_order = ["A+", "A", "B", "C", "D", "F"]
        # Grade must be C or worse
        assert grade_order.index(result.grade) >= grade_order.index("C")

    def test_no_auth_cap_reason_mentions_authentication(self) -> None:
        """The cap_applied field mentions authentication when no auth cap fires."""
        state = ServerHealthState(
            server_name="open-server",
            total_checks_7d=1000,
            successful_checks_7d=1000,
            consecutive_failures=0,
            has_authentication=False,
            has_active_critical_cve=False,
            is_confirmed_poisoned=False,
        )
        result = ScorecardEngine.compute(state)
        if result.cap_applied:
            assert "auth" in result.cap_applied.lower()


# ---------------------------------------------------------------------------
# Cap at B — critical/high finding or high p99
# ---------------------------------------------------------------------------


class TestCapAtB:
    def test_critical_finding_caps_at_b(self) -> None:
        """A critical security finding caps the grade at B (or worse)."""
        state = ServerHealthState(
            server_name="vulnerable",
            total_checks_7d=1000,
            successful_checks_7d=1000,
            consecutive_failures=0,
            critical_findings=1,
            has_authentication=True,
            has_active_critical_cve=False,
            is_confirmed_poisoned=False,
        )
        result = ScorecardEngine.compute(state)
        grade_order = ["A+", "A", "B", "C", "D", "F"]
        assert grade_order.index(result.grade) >= grade_order.index("B")

    def test_high_finding_caps_at_b(self) -> None:
        """A high security finding caps the grade at B (or worse)."""
        state = ServerHealthState(
            server_name="risky",
            total_checks_7d=1000,
            successful_checks_7d=1000,
            consecutive_failures=0,
            high_findings=2,
            has_authentication=True,
            has_active_critical_cve=False,
            is_confirmed_poisoned=False,
        )
        result = ScorecardEngine.compute(state)
        grade_order = ["A+", "A", "B", "C", "D", "F"]
        assert grade_order.index(result.grade) >= grade_order.index("B")

    def test_high_p99_caps_at_b(self) -> None:
        """p99 latency > 5000ms caps the grade at B (or worse)."""
        state = ServerHealthState(
            server_name="slow-server",
            total_checks_7d=1000,
            successful_checks_7d=1000,
            consecutive_failures=0,
            has_authentication=True,
            has_active_critical_cve=False,
            is_confirmed_poisoned=False,
            current_p99_ms=6000.0,    # 6 seconds — above the 5s cap
        )
        result = ScorecardEngine.compute(state)
        grade_order = ["A+", "A", "B", "C", "D", "F"]
        assert grade_order.index(result.grade) >= grade_order.index("B")

    def test_p99_below_5000ms_no_b_cap(self) -> None:
        """p99 <= 5000ms does NOT trigger the high-p99 cap at B."""
        state = ServerHealthState(
            server_name="acceptable-latency",
            total_checks_7d=1000,
            successful_checks_7d=1000,
            consecutive_failures=0,
            has_authentication=True,
            has_active_critical_cve=False,
            is_confirmed_poisoned=False,
            current_p99_ms=4999.0,
        )
        result = ScorecardEngine.compute(state)
        # Should not be capped at B due to p99 specifically
        assert result.cap_applied is None or "5 s" not in (result.cap_applied or "")


# ---------------------------------------------------------------------------
# Schema stability dimension
# ---------------------------------------------------------------------------


class TestSchemaStabilityScore:
    def test_no_drift_scores_100_on_schema_stability(self) -> None:
        """Zero drift events → schema stability score of 100."""
        state = ServerHealthState(
            server_name="stable",
            breaking_drifts_7d=0,
            compatible_drifts_7d=0,
        )
        result = ScorecardEngine.compute(state)
        schema = next(d for d in result.dimensions if d.name == "schema_stability")
        assert schema.score == 100.0

    def test_breaking_drift_reduces_schema_score(self) -> None:
        """Breaking schema drifts reduce the schema stability dimension score."""
        state_no_drift = ServerHealthState(
            server_name="stable",
            breaking_drifts_7d=0,
            compatible_drifts_7d=0,
        )
        state_with_breaking = ServerHealthState(
            server_name="unstable",
            breaking_drifts_7d=1,
            compatible_drifts_7d=0,
        )
        result_stable = ScorecardEngine.compute(state_no_drift)
        result_breaking = ScorecardEngine.compute(state_with_breaking)

        schema_stable = next(d for d in result_stable.dimensions if d.name == "schema_stability")
        schema_breaking = next(d for d in result_breaking.dimensions if d.name == "schema_stability")
        assert schema_breaking.score < schema_stable.score

    def test_compatible_drift_reduces_schema_score_less_than_breaking(self) -> None:
        """Compatible drift penalises schema score less than breaking drift."""
        state_compatible = ServerHealthState(
            server_name="compat",
            breaking_drifts_7d=0,
            compatible_drifts_7d=1,
        )
        state_breaking = ServerHealthState(
            server_name="breaking",
            breaking_drifts_7d=1,
            compatible_drifts_7d=0,
        )
        result_compat = ScorecardEngine.compute(state_compatible)
        result_breaking = ScorecardEngine.compute(state_breaking)

        schema_compat = next(d for d in result_compat.dimensions if d.name == "schema_stability")
        schema_breaking = next(d for d in result_breaking.dimensions if d.name == "schema_stability")
        assert schema_compat.score > schema_breaking.score

    def test_three_or_more_breaking_drifts_zeroes_schema_score(self) -> None:
        """3+ breaking drifts in 7 days → schema stability score of 0."""
        state = ServerHealthState(
            server_name="highly-unstable",
            breaking_drifts_7d=3,
            compatible_drifts_7d=0,
        )
        result = ScorecardEngine.compute(state)
        schema = next(d for d in result.dimensions if d.name == "schema_stability")
        assert schema.score == 0.0


# ---------------------------------------------------------------------------
# Result structure
# ---------------------------------------------------------------------------


class TestScorecardResultStructure:
    def test_compute_returns_scorecard_result(self) -> None:
        """compute() returns a ScorecardResult instance."""
        state = _perfect_state()
        result = ScorecardEngine.compute(state)
        assert isinstance(result, ScorecardResult)

    def test_result_has_all_five_dimensions(self) -> None:
        """The result must contain all 5 named dimensions."""
        state = _perfect_state()
        result = ScorecardEngine.compute(state)
        dim_names = {d.name for d in result.dimensions}
        assert dim_names == {"availability", "security", "reliability", "schema_stability", "performance"}

    def test_weights_sum_to_one(self) -> None:
        """All dimension weights must sum to 1.0."""
        state = _perfect_state()
        result = ScorecardEngine.compute(state)
        total_weight = sum(d.weight for d in result.dimensions)
        assert abs(total_weight - 1.0) < 1e-9

    def test_server_name_preserved_in_result(self) -> None:
        """The server_name in the result matches the input state."""
        state = _perfect_state("my-server")
        result = ScorecardEngine.compute(state)
        assert result.server_name == "my-server"

    def test_score_between_0_and_100(self) -> None:
        """Overall score is always in the range [0, 100]."""
        for name in ["perfect", "broken", "empty"]:
            if name == "perfect":
                state = _perfect_state(name)
            elif name == "broken":
                state = ServerHealthState(
                    server_name=name,
                    total_checks_7d=10,
                    successful_checks_7d=0,
                    consecutive_failures=20,
                    critical_findings=5,
                    has_active_critical_cve=True,
                    is_confirmed_poisoned=True,
                    has_authentication=False,
                )
            else:
                state = ServerHealthState(server_name=name)

            result = ScorecardEngine.compute(state)
            assert 0.0 <= result.score <= 100.0, f"Score out of range for {name}: {result.score}"

    def test_to_dict_contains_required_keys(self) -> None:
        """ScorecardResult.to_dict() includes all expected keys."""
        state = _perfect_state()
        result = ScorecardEngine.compute(state)
        d = result.to_dict()
        assert "server_name" in d
        assert "grade" in d
        assert "score" in d
        assert "cap_applied" in d
        assert "computed_at" in d
        assert "dimensions" in d

    def test_cap_applied_is_none_for_perfect_server(self) -> None:
        """A perfect server has no cap applied — cap_applied is None."""
        state = _perfect_state()
        result = ScorecardEngine.compute(state)
        assert result.cap_applied is None


# ---------------------------------------------------------------------------
# Performance dimension
# ---------------------------------------------------------------------------


class TestPerformanceDimension:
    def test_no_p99_data_scores_100_performance(self) -> None:
        """No p99 data available → performance score of 100 (benefit of doubt)."""
        state = ServerHealthState(
            server_name="new",
            current_p99_ms=None,
        )
        result = ScorecardEngine.compute(state)
        perf = next(d for d in result.dimensions if d.name == "performance")
        assert perf.score == 100.0

    def test_p99_within_baseline_scores_100(self) -> None:
        """p99 equal to baseline → performance score of 100."""
        state = ServerHealthState(
            server_name="steady",
            current_p99_ms=200.0,
            baseline_p99_ms=200.0,
        )
        result = ScorecardEngine.compute(state)
        perf = next(d for d in result.dimensions if d.name == "performance")
        assert perf.score == 100.0

    def test_p99_5x_above_baseline_scores_zero(self) -> None:
        """p99 > 5x baseline → performance score of 0."""
        state = ServerHealthState(
            server_name="degraded",
            current_p99_ms=1100.0,
            baseline_p99_ms=200.0,  # ratio > 5
        )
        result = ScorecardEngine.compute(state)
        perf = next(d for d in result.dimensions if d.name == "performance")
        assert perf.score == 0.0


# ---------------------------------------------------------------------------
# security_scanned field
# ---------------------------------------------------------------------------


class TestSecurityScanned:
    def test_unscanned_server_security_score_is_100(self) -> None:
        """When security_scanned=False, security score defaults to 100 (no penalty)."""
        state = ServerHealthState(
            server_name="unscanned",
            security_scanned=False,
        )
        result = ScorecardEngine.compute(state)
        sec = next(d for d in result.dimensions if d.name == "security")
        assert sec.score == 100.0

    def test_unscanned_server_security_note_present(self) -> None:
        """When security_scanned=False, security dimension notes mention 'No scan data'."""
        state = ServerHealthState(
            server_name="unscanned",
            security_scanned=False,
        )
        result = ScorecardEngine.compute(state)
        sec = next(d for d in result.dimensions if d.name == "security")
        assert any("No scan data" in note for note in sec.notes)

    def test_unscanned_server_cannot_achieve_a_plus(self) -> None:
        """A perfect server that hasn't been scanned cannot achieve A+."""
        state = ServerHealthState(
            server_name="postgres-mcp",
            total_checks_7d=1000,
            successful_checks_7d=1000,
            consecutive_failures=0,
            has_active_critical_cve=False,
            is_confirmed_poisoned=False,
            has_authentication=True,
            breaking_drifts_7d=0,
            compatible_drifts_7d=0,
            security_scanned=False,  # not scanned — cannot be A+
        )
        result = ScorecardEngine.compute(state)
        assert result.grade != "A+"

    def test_scanned_server_with_no_findings_can_achieve_a_plus(self) -> None:
        """A server that has been scanned with zero findings can achieve A+."""
        state = _perfect_state()  # security_scanned=True via fixture
        result = ScorecardEngine.compute(state)
        assert result.grade == "A+"

    def test_scanned_server_with_critical_finding_deducts_security_score(self) -> None:
        """When security_scanned=True, critical findings reduce the security score."""
        state = ServerHealthState(
            server_name="vulnerable",
            security_scanned=True,
            critical_findings=1,
        )
        result = ScorecardEngine.compute(state)
        sec = next(d for d in result.dimensions if d.name == "security")
        assert sec.score < 100.0

    def test_unscanned_server_critical_findings_do_not_affect_security_score(self) -> None:
        """When security_scanned=False, critical_findings are not applied to security score."""
        state = ServerHealthState(
            server_name="vulnerable-unscanned",
            security_scanned=False,
            critical_findings=5,
        )
        result = ScorecardEngine.compute(state)
        sec = next(d for d in result.dimensions if d.name == "security")
        # Score stays at 100 — findings are ignored when unscanned
        assert sec.score == 100.0
