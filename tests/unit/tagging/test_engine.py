"""Tests for session health tag computation."""

from __future__ import annotations

from langsight.tagging.engine import HealthTag, tag_from_spans


def _span(
    tool_name: str = "query",
    status: str = "success",
    error: str | None = None,
    span_type: str = "tool_call",
) -> dict:
    return {"tool_name": tool_name, "status": status, "error": error, "span_type": span_type}


class TestPreventionTags:
    def test_loop_detected(self) -> None:
        spans = [
            _span(status="success"),
            _span(status="prevented", error="loop_detected: repetition"),
        ]
        assert tag_from_spans(spans) == HealthTag.LOOP_DETECTED

    def test_budget_exceeded(self) -> None:
        spans = [
            _span(status="success"),
            _span(status="prevented", error="budget_exceeded: max_steps"),
        ]
        assert tag_from_spans(spans) == HealthTag.BUDGET_EXCEEDED

    def test_circuit_breaker_open(self) -> None:
        spans = [
            _span(status="prevented", error="circuit_breaker_open: server disabled"),
        ]
        assert tag_from_spans(spans) == HealthTag.CIRCUIT_BREAKER_OPEN

    def test_loop_has_higher_priority_than_budget(self) -> None:
        spans = [
            _span(status="prevented", error="loop_detected: repetition"),
            _span(status="prevented", error="budget_exceeded: max_steps"),
        ]
        assert tag_from_spans(spans) == HealthTag.LOOP_DETECTED


class TestFailureTags:
    def test_schema_drift(self) -> None:
        spans = [
            _span(status="error", error="schema drift detected on tools/list"),
        ]
        assert tag_from_spans(spans) == HealthTag.SCHEMA_DRIFT

    def test_timeout(self) -> None:
        """Timeout on a different tool from the success = no fallback = TIMEOUT."""
        spans = [
            _span(tool_name="list_tables", status="success"),
            _span(tool_name="query", status="timeout", error="connection timed out"),
        ]
        assert tag_from_spans(spans) == HealthTag.TIMEOUT

    def test_tool_failure(self) -> None:
        """Error on a tool with no successful retry = plain failure."""
        spans = [
            _span(tool_name="list_tables", status="success"),
            _span(tool_name="query", status="error", error="connection refused"),
        ]
        assert tag_from_spans(spans) == HealthTag.TOOL_FAILURE

    def test_schema_drift_higher_than_timeout(self) -> None:
        spans = [
            _span(status="timeout", error="timed out"),
            _span(status="error", error="schema drift detected"),
        ]
        assert tag_from_spans(spans) == HealthTag.SCHEMA_DRIFT

    def test_timeout_higher_than_error(self) -> None:
        spans = [
            _span(status="error", error="something wrong"),
            _span(status="timeout", error="timed out"),
        ]
        assert tag_from_spans(spans) == HealthTag.TIMEOUT


class TestSuccessTags:
    def test_all_success(self) -> None:
        spans = [
            _span(status="success"),
            _span(status="success"),
        ]
        assert tag_from_spans(spans) == HealthTag.SUCCESS

    def test_empty_spans(self) -> None:
        assert tag_from_spans([]) == HealthTag.SUCCESS

    def test_success_with_fallback(self) -> None:
        """Same tool called twice: first fails, then succeeds."""
        spans = [
            _span(tool_name="query", status="error", error="retry later"),
            _span(tool_name="query", status="success"),
        ]
        assert tag_from_spans(spans) == HealthTag.SUCCESS_WITH_FALLBACK

    def test_no_fallback_when_different_tools(self) -> None:
        """Different tools failing doesn't count as fallback."""
        spans = [
            _span(tool_name="tool_a", status="error", error="broken"),
            _span(tool_name="tool_b", status="success"),
        ]
        # tool_a has only error, tool_b has only success — no fallback
        assert tag_from_spans(spans) == HealthTag.TOOL_FAILURE

    def test_fallback_requires_same_tool_success_after_failure(self) -> None:
        """Fallback only if the same tool has both failure and success."""
        spans = [
            _span(tool_name="query", status="error", error="timeout"),
            _span(tool_name="query", status="error", error="timeout"),
            _span(tool_name="query", status="success"),
        ]
        assert tag_from_spans(spans) == HealthTag.SUCCESS_WITH_FALLBACK
