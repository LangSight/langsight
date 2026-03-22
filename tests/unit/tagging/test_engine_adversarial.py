"""Adversarial and edge-case tests for session health tag computation.

Covers: empty status strings, None errors, mismatched prevented status,
mixed prevention types, and large span volumes.
"""

from __future__ import annotations

from langsight.tagging.engine import HealthTag, tag_from_spans


def _span(
    tool_name: str = "query",
    status: str = "success",
    error: str | None = None,
) -> dict:
    return {"tool_name": tool_name, "status": status, "error": error}


# ---------------------------------------------------------------------------
# Empty status string
# ---------------------------------------------------------------------------


class TestEmptyStatusString:
    def test_empty_status_treated_as_unknown(self) -> None:
        """An empty status string should not match any known status."""
        spans = [_span(status="", error=None)]
        # Empty status is not "prevented", "error", "timeout", or "success"
        # It falls through to SUCCESS (no has_error, no has_timeout, etc.)
        assert tag_from_spans(spans) == HealthTag.SUCCESS

    def test_empty_status_with_error_message(self) -> None:
        """Empty status + error string should not trigger any special handling."""
        spans = [_span(status="", error="some error")]
        # status="" != "prevented", "timeout", "error" => no flags set
        assert tag_from_spans(spans) == HealthTag.SUCCESS


# ---------------------------------------------------------------------------
# Span with None error
# ---------------------------------------------------------------------------


class TestNoneError:
    def test_prevented_status_with_none_error(self) -> None:
        """Prevented status but None error should not match any prevention keyword."""
        spans = [_span(status="prevented", error=None)]
        # error becomes str(None or "") = "", which doesn't contain loop/budget/circuit
        # status is "prevented" but no keyword match => falls through
        assert tag_from_spans(spans) not in (
            HealthTag.LOOP_DETECTED,
            HealthTag.BUDGET_EXCEEDED,
            HealthTag.CIRCUIT_BREAKER_OPEN,
        )

    def test_error_status_with_none_error(self) -> None:
        """Error status with None error should still flag TOOL_FAILURE."""
        spans = [_span(status="error", error=None)]
        assert tag_from_spans(spans) == HealthTag.TOOL_FAILURE

    def test_timeout_status_with_none_error(self) -> None:
        """Timeout status with None error should still flag TIMEOUT."""
        spans = [_span(status="timeout", error=None)]
        assert tag_from_spans(spans) == HealthTag.TIMEOUT

    def test_success_with_none_error(self) -> None:
        spans = [_span(status="success", error=None)]
        assert tag_from_spans(spans) == HealthTag.SUCCESS


# ---------------------------------------------------------------------------
# Prevented status without matching error keyword
# ---------------------------------------------------------------------------


class TestPreventedWithoutKeyword:
    def test_prevented_with_unrecognized_error(self) -> None:
        """Prevented status with an error that doesn't match any known keyword."""
        spans = [_span(status="prevented", error="unknown_prevention_reason")]
        # "unknown_prevention_reason" doesn't contain loop_detected, budget_exceeded, or circuit_breaker
        result = tag_from_spans(spans)
        # Falls through prevention checks; no other flags set => SUCCESS
        assert result == HealthTag.SUCCESS

    def test_prevented_with_partial_keyword(self) -> None:
        """Partial keyword like 'loop' should not match 'loop_detected'."""
        spans = [_span(status="prevented", error="loop stuck")]
        # "loop stuck" does not contain "loop_detected"
        result = tag_from_spans(spans)
        assert result != HealthTag.LOOP_DETECTED

    def test_prevented_with_budget_in_error_but_not_exceeded(self) -> None:
        """Error contains 'budget' but not 'budget_exceeded'."""
        spans = [_span(status="prevented", error="budget warning issued")]
        result = tag_from_spans(spans)
        assert result != HealthTag.BUDGET_EXCEEDED


# ---------------------------------------------------------------------------
# Mixed prevention types in same session (loop + budget)
# ---------------------------------------------------------------------------


class TestMixedPreventionTypes:
    def test_loop_before_budget_returns_loop(self) -> None:
        """When loop_detected appears before budget_exceeded, loop wins (first in list)."""
        spans = [
            _span(status="success"),
            _span(status="prevented", error="loop_detected: repetition"),
            _span(status="prevented", error="budget_exceeded: max_steps"),
        ]
        assert tag_from_spans(spans) == HealthTag.LOOP_DETECTED

    def test_budget_before_loop_returns_budget(self) -> None:
        """When budget_exceeded appears first, it returns immediately."""
        spans = [
            _span(status="prevented", error="budget_exceeded: max_cost"),
            _span(status="prevented", error="loop_detected: ping_pong"),
        ]
        assert tag_from_spans(spans) == HealthTag.BUDGET_EXCEEDED

    def test_circuit_breaker_before_loop_returns_circuit_breaker(self) -> None:
        spans = [
            _span(status="prevented", error="circuit_breaker_open: srv disabled"),
            _span(status="prevented", error="loop_detected: repetition"),
        ]
        assert tag_from_spans(spans) == HealthTag.CIRCUIT_BREAKER_OPEN

    def test_all_three_prevention_types(self) -> None:
        """First prevention span encountered wins."""
        spans = [
            _span(status="success"),
            _span(status="prevented", error="circuit_breaker_open: disabled"),
            _span(status="prevented", error="loop_detected: repetition"),
            _span(status="prevented", error="budget_exceeded: max_steps"),
        ]
        assert tag_from_spans(spans) == HealthTag.CIRCUIT_BREAKER_OPEN

    def test_prevention_plus_errors_prevention_wins(self) -> None:
        """Prevention tags have higher priority than error tags."""
        spans = [
            _span(status="error", error="connection refused"),
            _span(status="timeout", error="read timeout"),
            _span(status="prevented", error="loop_detected: repetition"),
        ]
        # Loop is encountered during iteration and returns immediately
        assert tag_from_spans(spans) == HealthTag.LOOP_DETECTED

    def test_errors_before_prevention_error_tags_dont_short_circuit(self) -> None:
        """Error/timeout spans set flags but don't return early. Prevention span returns."""
        spans = [
            _span(status="timeout", error="timed out"),
            _span(status="error", error="something broke"),
            _span(status="prevented", error="budget_exceeded: max_cost"),
        ]
        assert tag_from_spans(spans) == HealthTag.BUDGET_EXCEEDED


# ---------------------------------------------------------------------------
# 1000+ spans in a session (performance)
# ---------------------------------------------------------------------------


class TestLargeSpanVolume:
    def test_1000_success_spans(self) -> None:
        spans = [_span(tool_name=f"tool_{i}", status="success") for i in range(1000)]
        result = tag_from_spans(spans)
        assert result == HealthTag.SUCCESS

    def test_1000_spans_with_last_prevented(self) -> None:
        spans = [_span(tool_name=f"tool_{i}", status="success") for i in range(999)]
        spans.append(_span(status="prevented", error="loop_detected: repetition"))
        result = tag_from_spans(spans)
        assert result == HealthTag.LOOP_DETECTED

    def test_1000_spans_with_first_prevented(self) -> None:
        """Prevention span at index 0 should still be detected."""
        spans = [_span(status="prevented", error="budget_exceeded: max_steps")]
        spans.extend([_span(tool_name=f"tool_{i}", status="success") for i in range(999)])
        result = tag_from_spans(spans)
        assert result == HealthTag.BUDGET_EXCEEDED

    def test_many_errors_then_fallback(self) -> None:
        """Same tool fails many times then succeeds once => SUCCESS_WITH_FALLBACK."""
        spans = [_span(tool_name="query", status="error", error="retry") for _ in range(500)]
        spans.append(_span(tool_name="query", status="success"))
        result = tag_from_spans(spans)
        assert result == HealthTag.SUCCESS_WITH_FALLBACK

    def test_many_different_tools_all_error(self) -> None:
        """1000 different tools all failing => TOOL_FAILURE (no fallback)."""
        spans = [
            _span(tool_name=f"tool_{i}", status="error", error=f"err_{i}")
            for i in range(1000)
        ]
        result = tag_from_spans(spans)
        assert result == HealthTag.TOOL_FAILURE


# ---------------------------------------------------------------------------
# Case sensitivity
# ---------------------------------------------------------------------------


class TestCaseSensitivity:
    def test_status_is_case_insensitive(self) -> None:
        """The tagger lowercases status, so 'PREVENTED' should match."""
        spans = [{"tool_name": "q", "status": "PREVENTED", "error": "loop_detected: rep"}]
        assert tag_from_spans(spans) == HealthTag.LOOP_DETECTED

    def test_error_keyword_is_case_insensitive(self) -> None:
        """The tagger lowercases error, so 'Loop_Detected' should match."""
        spans = [{"tool_name": "q", "status": "prevented", "error": "Loop_Detected: rep"}]
        assert tag_from_spans(spans) == HealthTag.LOOP_DETECTED

    def test_uppercase_timeout_status(self) -> None:
        spans = [{"tool_name": "q", "status": "TIMEOUT", "error": "timed out"}]
        assert tag_from_spans(spans) == HealthTag.TIMEOUT

    def test_mixed_case_error_status(self) -> None:
        spans = [{"tool_name": "q", "status": "Error", "error": "failed"}]
        assert tag_from_spans(spans) == HealthTag.TOOL_FAILURE


# ---------------------------------------------------------------------------
# Spans with missing keys
# ---------------------------------------------------------------------------


class TestMissingKeys:
    def test_span_missing_status_key(self) -> None:
        """If status key is missing, span.get('status', '') returns ''."""
        spans = [{"tool_name": "query", "error": None}]
        result = tag_from_spans(spans)
        assert result == HealthTag.SUCCESS

    def test_span_missing_error_key(self) -> None:
        """If error key is missing, span.get('error', '') returns ''."""
        spans = [{"tool_name": "query", "status": "error"}]
        result = tag_from_spans(spans)
        assert result == HealthTag.TOOL_FAILURE

    def test_span_missing_tool_name(self) -> None:
        """Missing tool_name defaults to '' and doesn't affect logic."""
        spans = [{"status": "success"}]
        result = tag_from_spans(spans)
        assert result == HealthTag.SUCCESS

    def test_completely_empty_span_dict(self) -> None:
        """An empty dict should be handled gracefully."""
        spans = [{}]
        result = tag_from_spans(spans)
        assert result == HealthTag.SUCCESS


# ---------------------------------------------------------------------------
# Schema drift edge cases
# ---------------------------------------------------------------------------


class TestSchemaDriftEdgeCases:
    def test_schema_drift_in_error_but_not_prevented(self) -> None:
        """Schema drift in error string of a non-prevented span."""
        spans = [_span(status="error", error="schema drift detected on tools/list")]
        assert tag_from_spans(spans) == HealthTag.SCHEMA_DRIFT

    def test_schema_drift_partial_match(self) -> None:
        """Just 'schema' without 'drift' should NOT match."""
        spans = [_span(status="error", error="schema error detected")]
        assert tag_from_spans(spans) != HealthTag.SCHEMA_DRIFT
        assert tag_from_spans(spans) == HealthTag.TOOL_FAILURE

    def test_schema_drift_with_prevention(self) -> None:
        """Prevention always wins over schema drift."""
        spans = [
            _span(status="error", error="schema drift detected"),
            _span(status="prevented", error="loop_detected: repetition"),
        ]
        assert tag_from_spans(spans) == HealthTag.LOOP_DETECTED


# ---------------------------------------------------------------------------
# Fallback detection edge cases
# ---------------------------------------------------------------------------


class TestFallbackEdgeCases:
    def test_single_error_no_fallback(self) -> None:
        """A tool called once with error has no second call to be a fallback."""
        spans = [_span(tool_name="query", status="error", error="oops")]
        assert tag_from_spans(spans) == HealthTag.TOOL_FAILURE

    def test_two_successes_no_error_no_fallback(self) -> None:
        """Same tool called twice, both success => SUCCESS, not fallback."""
        spans = [
            _span(tool_name="query", status="success"),
            _span(tool_name="query", status="success"),
        ]
        assert tag_from_spans(spans) == HealthTag.SUCCESS

    def test_error_then_success_different_tools_no_fallback(self) -> None:
        """Error on one tool, success on different tool => TOOL_FAILURE."""
        spans = [
            _span(tool_name="tool_a", status="error", error="broken"),
            _span(tool_name="tool_b", status="success"),
        ]
        assert tag_from_spans(spans) == HealthTag.TOOL_FAILURE

    def test_multiple_tools_with_fallback_on_one(self) -> None:
        """One tool has error+success, another is fine => SUCCESS_WITH_FALLBACK."""
        spans = [
            _span(tool_name="query", status="error", error="timeout"),
            _span(tool_name="list_tables", status="success"),
            _span(tool_name="query", status="success"),
        ]
        assert tag_from_spans(spans) == HealthTag.SUCCESS_WITH_FALLBACK

    def test_all_calls_to_tool_failed_no_fallback(self) -> None:
        """Same tool called 5 times, all error => TOOL_FAILURE."""
        spans = [
            _span(tool_name="query", status="error", error="retry")
            for _ in range(5)
        ]
        assert tag_from_spans(spans) == HealthTag.TOOL_FAILURE
