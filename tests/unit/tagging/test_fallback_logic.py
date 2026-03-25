"""Edge-case tests for tagging engine fallback detection.

Specifically exercises the any_fallback / any_unresolved_error paths
with timeout statuses, mixed span_types, and boundary conditions that
are easy to accidentally break.
"""

from __future__ import annotations

import pytest

from langsight.tagging.engine import HealthTag, tag_from_spans


def _tool(
    tool_name: str,
    status: str,
    error: str | None = None,
    span_type: str = "tool_call",
) -> dict:
    return {"tool_name": tool_name, "status": status, "error": error, "span_type": span_type}


@pytest.mark.unit
class TestFallbackWithTimeout:
    def test_timeout_then_success_is_fallback(self) -> None:
        """Timeout counts as a failure for fallback detection: timeout+success = fallback."""
        spans = [
            _tool("query", "timeout"),
            _tool("query", "success"),
        ]
        assert tag_from_spans(spans) == HealthTag.SUCCESS_WITH_FALLBACK

    def test_timeout_only_no_success_is_tool_failure(self) -> None:
        """Unresolved timeout (no subsequent success on same tool) => TOOL_FAILURE."""
        spans = [
            _tool("query", "timeout"),
            _tool("query", "timeout"),
        ]
        # has_timeout=True but no fallback resolution; has_error=False
        assert tag_from_spans(spans) == HealthTag.TIMEOUT

    def test_error_and_timeout_both_resolved_by_success(self) -> None:
        """Tool with both error and timeout calls, then a success => fallback."""
        spans = [
            _tool("query", "error", "retry"),
            _tool("query", "timeout"),
            _tool("query", "success"),
        ]
        assert tag_from_spans(spans) == HealthTag.SUCCESS_WITH_FALLBACK

    def test_fallback_blocked_by_unresolved_error_on_different_tool(self) -> None:
        """Tool A has fallback (error+success), but Tool B has unresolved error.
        any_unresolved_error is True → must NOT return SUCCESS_WITH_FALLBACK."""
        spans = [
            _tool("tool_a", "error", "transient"),
            _tool("tool_a", "success"),
            _tool("tool_b", "error", "permanent"),  # never resolved
        ]
        # any_fallback=True (tool_a), any_unresolved_error=True (tool_b)
        # The guard `if any_fallback and not any_unresolved_error` prevents fallback tag
        assert tag_from_spans(spans) == HealthTag.TOOL_FAILURE

    def test_fallback_blocked_by_unresolved_timeout_on_different_tool(self) -> None:
        """Same as above but the unresolved failure is a timeout."""
        spans = [
            _tool("tool_a", "error", "transient"),
            _tool("tool_a", "success"),
            _tool("tool_b", "timeout"),  # timeout, never recovered
        ]
        # any_unresolved_error=True (tool_b: timeout without success)
        assert tag_from_spans(spans) == HealthTag.TIMEOUT

    def test_agent_spans_excluded_from_fallback_tracking(self) -> None:
        """LLM agent spans (span_type='agent') must not participate in fallback detection.

        An agent span with status=error still contributes to has_error (it is not
        filtered from the status/error flags). What IS excluded is the fallback retry
        logic: agent spans are not added to tool_results, so error+success on the same
        agent span_type does NOT produce SUCCESS_WITH_FALLBACK.
        """
        spans = [
            # Agent span with error — sets has_error=True, excluded from tool_results
            _tool("run/analyst", "error", "llm error", span_type="agent"),
            # Agent span with success — NOT tracked in tool_results for fallback
            _tool("run/analyst", "success", span_type="agent"),
            # Only tool_call spans participate in fallback detection
            _tool("mcp_tool", "success"),
        ]
        # has_error=True (from agent span), no fallback in tool_results (agent spans excluded)
        # => TOOL_FAILURE (not SUCCESS_WITH_FALLBACK)
        assert tag_from_spans(spans) == HealthTag.TOOL_FAILURE

    def test_empty_tool_name_not_tracked_in_fallback(self) -> None:
        """tool_name='' is falsy — must not be added to tool_results tracking."""
        spans = [
            {"tool_name": "", "status": "error", "error": "oops", "span_type": "tool_call"},
            {"tool_name": "", "status": "success", "error": None, "span_type": "tool_call"},
        ]
        # Empty tool_name is falsy: `if tool_name:` guard prevents tracking
        # has_error=True => TOOL_FAILURE (no fallback tracking for empty names)
        result = tag_from_spans(spans)
        assert result == HealthTag.TOOL_FAILURE

    def test_many_tools_all_with_fallback_returns_success_with_fallback(self) -> None:
        """Multiple tools each recovering means all have any_fallback=True, none unresolved."""
        spans = []
        for i in range(10):
            spans.append(_tool(f"tool_{i}", "error", "transient"))
            spans.append(_tool(f"tool_{i}", "success"))
        assert tag_from_spans(spans) == HealthTag.SUCCESS_WITH_FALLBACK

    def test_one_of_many_tools_unresolved_blocks_fallback(self) -> None:
        """9 tools with fallback, 1 unresolved => blocked from SUCCESS_WITH_FALLBACK."""
        spans = []
        for i in range(9):
            spans.append(_tool(f"tool_{i}", "error", "transient"))
            spans.append(_tool(f"tool_{i}", "success"))
        # 10th tool never resolves
        spans.append(_tool("tool_9", "error", "permanent"))
        assert tag_from_spans(spans) == HealthTag.TOOL_FAILURE
