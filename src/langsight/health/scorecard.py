"""MCP Server Scorecard — A-F composite health grade.

Inspired by SSL Labs' rating methodology: compute a weighted numeric score
across five dimensions, then apply hard veto caps that can override the
numeric result for fatal flaws.

Dimensions and weights:
  Availability    30 %  — uptime over a 7-day rolling window
  Security        25 %  — OWASP / CVE / poisoning findings
  Reliability     20 %  — error rate and latency variance
  Schema Stability 15 % — drift frequency and breaking-change count
  Performance     10 %  — p99 latency vs 30-day baseline

Grade thresholds:
  A+  90–100, zero findings, zero drift, 99.9 %+ uptime
  A   90–100
  B   80–89
  C   65–79
  D   50–64
  F   < 50  (also forced by any fatal flaw via cap rules)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DimensionScore:
    name: str
    score: float  # 0–100
    weight: float  # fraction that contributes to overall
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ScorecardResult:
    server_name: str
    grade: str  # A+ | A | B | C | D | F
    score: float  # 0–100 weighted composite
    dimensions: list[DimensionScore]
    cap_applied: str | None  # which cap forced the grade down, if any
    computed_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "server_name": self.server_name,
            "grade": self.grade,
            "score": round(self.score, 1),
            "cap_applied": self.cap_applied,
            "computed_at": self.computed_at.isoformat(),
            "dimensions": [
                {
                    "name": d.name,
                    "score": round(d.score, 1),
                    "weight": d.weight,
                    "notes": d.notes,
                }
                for d in self.dimensions
            ],
        }


# ---------------------------------------------------------------------------
# Input state (caller populates this from storage queries)
# ---------------------------------------------------------------------------


@dataclass
class ServerHealthState:
    """All signals needed to compute a scorecard for one MCP server."""

    server_name: str

    # Availability
    total_checks_7d: int = 0
    successful_checks_7d: int = 0
    consecutive_failures: int = 0

    # Security findings (from latest security scan)
    critical_findings: int = 0
    high_findings: int = 0
    medium_findings: int = 0
    low_findings: int = 0
    has_active_critical_cve: bool = False
    is_confirmed_poisoned: bool = False
    has_authentication: bool = True  # assume true unless scan says otherwise

    # Reliability (from mcp_tool_calls, last 24 h)
    error_rate_pct: float = 0.0  # 0–100
    latency_cv: float = 0.0  # coefficient of variation = stddev/mean

    # Schema Stability (from schema_drift_events, last 7 d)
    breaking_drifts_7d: int = 0
    compatible_drifts_7d: int = 0
    untracked_drifts: int = 0  # drifts with no consumer impact data

    # Performance (p99 latency vs 30-day baseline)
    current_p99_ms: float | None = None
    baseline_p99_ms: float | None = None

    # Whether a security scan has been run for this server.
    # When False the security dimension score is treated as unknown.
    security_scanned: bool = field(default=False)


# ---------------------------------------------------------------------------
# Scoring functions
# ---------------------------------------------------------------------------


def _availability_score(state: ServerHealthState) -> tuple[float, list[str]]:
    notes: list[str] = []
    if state.total_checks_7d == 0:
        notes.append("No health checks recorded in the last 7 days")
        return 0.0, notes

    uptime = state.successful_checks_7d / state.total_checks_7d
    score = uptime * 100

    if uptime >= 0.9999:
        notes.append(f"Uptime {uptime * 100:.3f}% (exceptional)")
    elif uptime >= 0.999:
        notes.append(f"Uptime {uptime * 100:.2f}%")
    else:
        notes.append(f"Uptime {uptime * 100:.1f}%")

    if state.consecutive_failures > 0:
        notes.append(f"{state.consecutive_failures} consecutive failures")

    return score, notes


def _security_score(state: ServerHealthState) -> tuple[float, list[str]]:
    notes: list[str] = []
    score = 100.0

    if not state.security_scanned:
        notes.append("No scan data — run langsight security-scan")
        return score, notes

    deductions = [
        (state.critical_findings, 40, "critical finding(s)"),
        (state.high_findings, 20, "high finding(s)"),
        (state.medium_findings, 10, "medium finding(s)"),
        (state.low_findings, 5, "low finding(s)"),
    ]
    for count, penalty, label in deductions:
        if count:
            score -= count * penalty
            notes.append(f"{count} {label}")

    if not state.has_authentication:
        score -= 20
        notes.append("No authentication configured")

    return max(0.0, score), notes


def _reliability_score(state: ServerHealthState) -> tuple[float, list[str]]:
    notes: list[str] = []

    error_score = max(0.0, 100.0 - state.error_rate_pct * 10)
    variance_score = max(0.0, 100.0 - state.latency_cv * 100)
    score = error_score * 0.6 + variance_score * 0.4

    if state.error_rate_pct > 0:
        notes.append(f"Error rate {state.error_rate_pct:.1f}%")
    if state.latency_cv > 0.5:
        notes.append(f"High latency variance (CV={state.latency_cv:.2f})")

    return score, notes


def _schema_stability_score(state: ServerHealthState) -> tuple[float, list[str]]:
    notes: list[str] = []
    total_drifts = state.breaking_drifts_7d + state.compatible_drifts_7d

    if total_drifts == 0:
        return 100.0, ["No schema changes in 7 days"]

    if state.breaking_drifts_7d > 0:
        notes.append(f"{state.breaking_drifts_7d} breaking change(s)")
    if state.compatible_drifts_7d > 0:
        notes.append(f"{state.compatible_drifts_7d} compatible change(s)")

    # Breaking changes penalise more than compatible ones
    if state.breaking_drifts_7d >= 3:
        return 0.0, notes
    if state.breaking_drifts_7d >= 1:
        score = max(0.0, 60.0 - state.breaking_drifts_7d * 20)
        return score, notes
    if total_drifts <= 2:
        return 80.0, notes
    if total_drifts <= 5:
        return 60.0, notes
    return 30.0, notes


def _performance_score(state: ServerHealthState) -> tuple[float, list[str]]:
    notes: list[str] = []

    if state.current_p99_ms is None:
        return 100.0, ["No p99 data available"]

    if state.baseline_p99_ms is None or state.baseline_p99_ms == 0:
        # No baseline — score on absolute latency
        p99 = state.current_p99_ms
        notes.append(f"p99 = {p99:.0f}ms (no baseline)")
        if p99 <= 200:
            return 100.0, notes
        if p99 <= 500:
            return 80.0, notes
        if p99 <= 1000:
            return 60.0, notes
        if p99 <= 3000:
            return 40.0, notes
        return 20.0, notes

    ratio = state.current_p99_ms / state.baseline_p99_ms
    notes.append(f"p99 = {state.current_p99_ms:.0f}ms (baseline {state.baseline_p99_ms:.0f}ms)")

    thresholds = [(1.0, 100), (1.5, 80), (2.0, 60), (3.0, 40), (5.0, 20)]
    for threshold, score in thresholds:
        if ratio <= threshold:
            return float(score), notes
    return 0.0, notes


# ---------------------------------------------------------------------------
# Grade helpers
# ---------------------------------------------------------------------------

_GRADE_ORDER = ["A+", "A", "B", "C", "D", "F"]


def _numeric_to_grade(score: float) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 65:
        return "C"
    if score >= 50:
        return "D"
    return "F"


def _min_grade(a: str, b: str) -> str:
    """Return the worse of two grades (further from A+)."""
    ia = _GRADE_ORDER.index(a) if a in _GRADE_ORDER else len(_GRADE_ORDER)
    ib = _GRADE_ORDER.index(b) if b in _GRADE_ORDER else len(_GRADE_ORDER)
    return _GRADE_ORDER[max(ia, ib)]


def _apply_caps(grade: str, state: ServerHealthState) -> tuple[str, str | None]:
    """Apply hard veto rules that can force a grade down regardless of score.

    Returns (final_grade, cap_reason | None).
    """
    # ── Automatic F — fatal flaws ──────────────────────────────────────────
    if state.consecutive_failures >= 10:
        return "F", "10+ consecutive failures — server is effectively unreachable"
    if state.has_active_critical_cve:
        return "F", "Active critical CVE with known exploit"
    if state.is_confirmed_poisoned:
        return "F", "Tool description mutation detected (poisoning)"

    cap_reason: str | None = None

    # ── Cap at D ──────────────────────────────────────────────────────────
    if state.total_checks_7d > 0:
        uptime = state.successful_checks_7d / state.total_checks_7d
        if uptime < 0.90:
            new = _min_grade(grade, "D")
            if new != grade:
                grade, cap_reason = new, f"Uptime below 90% ({uptime * 100:.1f}%)"

    # ── Cap at C ──────────────────────────────────────────────────────────
    if not state.has_authentication:
        new = _min_grade(grade, "C")
        if new != grade:
            grade, cap_reason = new, "No authentication configured"
    if state.untracked_drifts > 3:
        new = _min_grade(grade, "C")
        if new != grade:
            grade, cap_reason = new, f"{state.untracked_drifts} untracked schema drifts"

    # ── Cap at B ──────────────────────────────────────────────────────────
    if state.critical_findings > 0 or state.high_findings > 0:
        new = _min_grade(grade, "B")
        if new != grade:
            grade, cap_reason = new, "Critical/high security finding present"
    if state.current_p99_ms and state.current_p99_ms > 5000:
        new = _min_grade(grade, "B")
        if new != grade:
            grade, cap_reason = new, f"p99 latency {state.current_p99_ms:.0f}ms > 5 s"

    # ── A+ eligibility ────────────────────────────────────────────────────
    # Security dimension must be known (scan has run) to qualify for A+.
    if grade == "A" and state.security_scanned:
        uptime = (
            state.successful_checks_7d / state.total_checks_7d if state.total_checks_7d > 0 else 0.0
        )
        if (
            uptime >= 0.999
            and state.critical_findings == 0
            and state.high_findings == 0
            and state.breaking_drifts_7d == 0
            and state.compatible_drifts_7d == 0
        ):
            grade = "A+"

    return grade, cap_reason


# ---------------------------------------------------------------------------
# ScorecardEngine
# ---------------------------------------------------------------------------


class ScorecardEngine:
    """Computes A-F health grades for MCP servers.

    Usage:
        state = ServerHealthState(server_name="postgres-mcp", ...)
        result = ScorecardEngine.compute(state)
        print(result.grade, result.score)
    """

    WEIGHTS = {
        "availability": 0.30,
        "security": 0.25,
        "reliability": 0.20,
        "schema_stability": 0.15,
        "performance": 0.10,
    }

    @classmethod
    def compute(cls, state: ServerHealthState) -> ScorecardResult:
        """Compute the full scorecard for a server state snapshot."""
        avail_score, avail_notes = _availability_score(state)
        sec_score, sec_notes = _security_score(state)
        rel_score, rel_notes = _reliability_score(state)
        schema_score, schema_notes = _schema_stability_score(state)
        perf_score, perf_notes = _performance_score(state)

        dimensions = [
            DimensionScore("availability", avail_score, cls.WEIGHTS["availability"], avail_notes),
            DimensionScore("security", sec_score, cls.WEIGHTS["security"], sec_notes),
            DimensionScore("reliability", rel_score, cls.WEIGHTS["reliability"], rel_notes),
            DimensionScore(
                "schema_stability", schema_score, cls.WEIGHTS["schema_stability"], schema_notes
            ),
            DimensionScore("performance", perf_score, cls.WEIGHTS["performance"], perf_notes),
        ]

        weighted = sum(d.score * d.weight for d in dimensions)
        grade = _numeric_to_grade(weighted)
        grade, cap_applied = _apply_caps(grade, state)

        return ScorecardResult(
            server_name=state.server_name,
            grade=grade,
            score=weighted,
            dimensions=dimensions,
            cap_applied=cap_applied,
        )
