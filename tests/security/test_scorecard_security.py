"""Security tests for ScorecardEngine — poison and CVE veto rules.

These tests verify that the two most security-critical cap rules cannot be
bypassed by any combination of other positive signals. A poisoned server or
a server with an active critical CVE must ALWAYS score F, regardless of
availability, reliability, schema stability, or performance signals.
"""

from __future__ import annotations

import pytest

from langsight.health.scorecard import ScorecardEngine, ServerHealthState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _near_perfect_state(
    *,
    has_active_critical_cve: bool = False,
    is_confirmed_poisoned: bool = False,
) -> ServerHealthState:
    """Return a near-perfect server state, optionally with a fatal flaw."""
    return ServerHealthState(
        server_name="test-server",
        # Availability: 100%
        total_checks_7d=10_000,
        successful_checks_7d=10_000,
        consecutive_failures=0,
        # Security: no findings (other than the flags under test)
        critical_findings=0,
        high_findings=0,
        medium_findings=0,
        low_findings=0,
        has_active_critical_cve=has_active_critical_cve,
        is_confirmed_poisoned=is_confirmed_poisoned,
        has_authentication=True,
        # Reliability: perfect
        error_rate_pct=0.0,
        latency_cv=0.0,
        # Schema: no drift
        breaking_drifts_7d=0,
        compatible_drifts_7d=0,
        untracked_drifts=0,
        # Performance: at baseline
        current_p99_ms=50.0,
        baseline_p99_ms=50.0,
    )


# ---------------------------------------------------------------------------
# Poisoned server: always F
# ---------------------------------------------------------------------------


class TestPoisonedServerAlwaysF:
    def test_poisoned_server_cannot_score_above_f(self) -> None:
        """is_confirmed_poisoned=True must always yield grade F.

        Even a server with 100% uptime, zero findings, and perfect performance
        must receive F if tool description mutation (poisoning) is confirmed.
        """
        state = _near_perfect_state(is_confirmed_poisoned=True)
        result = ScorecardEngine.compute(state)
        assert result.grade == "F"

    def test_poisoned_server_cap_applied_is_not_none(self) -> None:
        """cap_applied must be non-None when the poison veto fires."""
        state = _near_perfect_state(is_confirmed_poisoned=True)
        result = ScorecardEngine.compute(state)
        assert result.cap_applied is not None

    def test_poisoned_server_cap_reason_mentions_poison(self) -> None:
        """The cap reason must reference poisoning (not some other reason)."""
        state = _near_perfect_state(is_confirmed_poisoned=True)
        result = ScorecardEngine.compute(state)
        assert "poison" in result.cap_applied.lower()

    def test_poisoned_plus_cve_still_f(self) -> None:
        """Both poison AND CVE set → still F (neither flag is ignored)."""
        state = _near_perfect_state(
            is_confirmed_poisoned=True,
            has_active_critical_cve=True,
        )
        result = ScorecardEngine.compute(state)
        assert result.grade == "F"

    def test_poisoned_with_high_numeric_score_still_f(self) -> None:
        """Even if the numeric score would be 95+, poisoning forces F.

        Verifies the cap is not accidentally skipped when the numeric result
        already maps to grade A.
        """
        state = _near_perfect_state(is_confirmed_poisoned=True)
        result = ScorecardEngine.compute(state)
        # Numeric score for a near-perfect server is high — cap must override
        assert result.score > 50, "Expected near-perfect numeric score"
        assert result.grade == "F", "Cap must override the numeric grade"

    @pytest.mark.parametrize("consecutive_failures", [0, 5, 9])
    def test_poisoned_server_f_regardless_of_consecutive_failures(
        self, consecutive_failures: int
    ) -> None:
        """Poison veto fires for any value of consecutive_failures."""
        state = ServerHealthState(
            server_name="poisoned",
            total_checks_7d=1000,
            successful_checks_7d=1000,
            consecutive_failures=consecutive_failures,
            is_confirmed_poisoned=True,
            has_active_critical_cve=False,
            has_authentication=True,
        )
        result = ScorecardEngine.compute(state)
        assert result.grade == "F"


# ---------------------------------------------------------------------------
# Critical CVE: always F
# ---------------------------------------------------------------------------


class TestCriticalCveAlwaysF:
    def test_critical_cve_cannot_be_overridden(self) -> None:
        """has_active_critical_cve=True must always yield grade F.

        Even a server with 100% uptime, zero other findings, and perfect
        performance must receive F if an active critical CVE is present.
        The CVE cap cannot be overridden by any positive signals.
        """
        state = _near_perfect_state(has_active_critical_cve=True)
        result = ScorecardEngine.compute(state)
        assert result.grade == "F"

    def test_critical_cve_cap_applied_is_not_none(self) -> None:
        """cap_applied must be non-None when the CVE veto fires."""
        state = _near_perfect_state(has_active_critical_cve=True)
        result = ScorecardEngine.compute(state)
        assert result.cap_applied is not None

    def test_critical_cve_cap_reason_mentions_cve(self) -> None:
        """The cap reason must reference CVE (not some other reason)."""
        state = _near_perfect_state(has_active_critical_cve=True)
        result = ScorecardEngine.compute(state)
        assert "cve" in result.cap_applied.lower() or "CVE" in result.cap_applied

    def test_critical_cve_with_high_numeric_score_still_f(self) -> None:
        """Even if the numeric score would be 95+, active CVE forces F."""
        state = _near_perfect_state(has_active_critical_cve=True)
        result = ScorecardEngine.compute(state)
        assert result.score > 50, "Expected near-perfect numeric score"
        assert result.grade == "F"

    @pytest.mark.parametrize("findings", [
        {"critical_findings": 0, "high_findings": 0},
        {"critical_findings": 1, "high_findings": 0},
        {"critical_findings": 0, "high_findings": 5},
        {"critical_findings": 3, "high_findings": 3},
    ])
    def test_critical_cve_f_regardless_of_other_findings(
        self, findings: dict
    ) -> None:
        """CVE veto fires regardless of other security finding counts."""
        state = ServerHealthState(
            server_name="cve-server",
            total_checks_7d=1000,
            successful_checks_7d=1000,
            consecutive_failures=0,
            has_active_critical_cve=True,
            is_confirmed_poisoned=False,
            has_authentication=True,
            **findings,
        )
        result = ScorecardEngine.compute(state)
        assert result.grade == "F"

    def test_no_cve_flag_does_not_force_f(self) -> None:
        """A server with has_active_critical_cve=False is NOT forced to F by CVE rule.

        Regression guard: ensures the flag has the correct polarity.
        """
        state = _near_perfect_state(has_active_critical_cve=False)
        result = ScorecardEngine.compute(state)
        assert result.grade != "F" or result.cap_applied is None or "CVE" not in (result.cap_applied or "")

    def test_no_poison_flag_does_not_force_f(self) -> None:
        """A server with is_confirmed_poisoned=False is NOT forced to F by poison rule.

        Regression guard: ensures the flag has the correct polarity.
        """
        state = _near_perfect_state(is_confirmed_poisoned=False)
        result = ScorecardEngine.compute(state)
        assert result.grade != "F" or result.cap_applied is None or "poison" not in (result.cap_applied or "").lower()


# ---------------------------------------------------------------------------
# Consecutive failures veto: always F at 10+
# ---------------------------------------------------------------------------


class TestConsecutiveFailuresVeto:
    @pytest.mark.parametrize("n", [10, 11, 20, 100])
    def test_10_or_more_consecutive_failures_forces_f(self, n: int) -> None:
        """consecutive_failures >= 10 forces grade F."""
        state = ServerHealthState(
            server_name="failing",
            total_checks_7d=1000,
            successful_checks_7d=990,
            consecutive_failures=n,
            has_active_critical_cve=False,
            is_confirmed_poisoned=False,
            has_authentication=True,
        )
        result = ScorecardEngine.compute(state)
        assert result.grade == "F"

    def test_consecutive_failures_cap_reason_mentioned(self) -> None:
        """cap_applied mentions consecutive failures when that veto fires."""
        state = ServerHealthState(
            server_name="failing",
            total_checks_7d=1000,
            successful_checks_7d=1000,
            consecutive_failures=15,
            has_active_critical_cve=False,
            is_confirmed_poisoned=False,
            has_authentication=True,
        )
        result = ScorecardEngine.compute(state)
        assert result.cap_applied is not None
        assert "consecutive" in result.cap_applied.lower()
