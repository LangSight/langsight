"""
Adversarial tests for the fallback-vs-failure boundary in tag_from_spans().

Security invariant: a tool that only ever errors must produce TOOL_FAILURE, not
SUCCESS_WITH_FALLBACK. Misclassifying a hard failure as a graceful fallback would
hide real breakage from operators — a silent health-signal regression.

The two cases that matter:

1. Single tool, errors only, no eventual success:
       tool_a: [error, error, error]
   Expected: TOOL_FAILURE (no "success" in statuses → any_fallback stays False)

2. Mixed session — one tool recovers, another never does:
       tool_a: [error, success]   ← this would qualify as fallback
       tool_b: [error, error]     ← this has any_unresolved_error = True
   Expected: TOOL_FAILURE (any_unresolved_error blocks SUCCESS_WITH_FALLBACK)

These cover the `any_unresolved_error` guard at line 103 of engine.py.
Without that guard both cases would return SUCCESS_WITH_FALLBACK — masking
the unresolved errors.
"""

from __future__ import annotations

import pytest

from langsight.tagging.engine import HealthTag, tag_from_spans

pytestmark = pytest.mark.security


def _tool_call(
    tool_name: str,
    status: str,
    error: str | None = None,
) -> dict:
    """Build a minimal tool_call span dict."""
    return {
        "tool_name": tool_name,
        "status": status,
        "error": error,
        "span_type": "tool_call",
    }


def _agent_span(status: str = "success") -> dict:
    """Build an agent (LLM generation) span — excluded from fallback detection."""
    return {
        "tool_name": "",
        "status": status,
        "error": None,
        "span_type": "agent",
    }


class TestToolWithOnlyErrors:
    """A tool that accumulates only error statuses must be TOOL_FAILURE, never SUCCESS_WITH_FALLBACK.

    Invariant: any_unresolved_error=True blocks the SUCCESS_WITH_FALLBACK path
    even when some other tool in the same session qualifies as a fallback.
    """

    def test_single_error_call_is_tool_failure(self) -> None:
        """One error call, no retry — most basic failure case."""
        spans = [_tool_call("tool_a", "error", "connection refused")]
        assert tag_from_spans(spans) == HealthTag.TOOL_FAILURE

    def test_repeated_errors_on_same_tool_is_tool_failure(self) -> None:
        """Same tool called 3 times, all error — must not be misread as fallback."""
        spans = [
            _tool_call("tool_a", "error", "retry 1"),
            _tool_call("tool_a", "error", "retry 2"),
            _tool_call("tool_a", "error", "retry 3"),
        ]
        result = tag_from_spans(spans)
        assert result == HealthTag.TOOL_FAILURE, (
            f"Expected TOOL_FAILURE for a tool with only errors, got {result!r}"
        )

    def test_all_errors_is_not_success_with_fallback(self) -> None:
        """Explicit negative assertion — the wrong tag must never appear."""
        spans = [
            _tool_call("tool_a", "error", "err-1"),
            _tool_call("tool_a", "error", "err-2"),
        ]
        assert tag_from_spans(spans) != HealthTag.SUCCESS_WITH_FALLBACK

    def test_timeout_only_is_tool_failure_via_timeout_path(self) -> None:
        """A tool that only times out should reach TIMEOUT (not SUCCESS_WITH_FALLBACK).

        timeout counts as a failure in the fallback check, and without a
        matching success, it leaves any_unresolved_error=True.
        """
        spans = [_tool_call("tool_a", "timeout", "read timeout")]
        result = tag_from_spans(spans)
        # TIMEOUT has higher priority than TOOL_FAILURE — both are correct here.
        # The point is: NOT SUCCESS_WITH_FALLBACK.
        assert result in (HealthTag.TIMEOUT, HealthTag.TOOL_FAILURE)
        assert result != HealthTag.SUCCESS_WITH_FALLBACK

    def test_mixed_error_and_timeout_on_same_tool_is_not_fallback(self) -> None:
        """Errors + timeouts on the same tool, no success = unresolved = TOOL_FAILURE."""
        spans = [
            _tool_call("tool_a", "error", "connection reset"),
            _tool_call("tool_a", "timeout", "read timeout"),
        ]
        result = tag_from_spans(spans)
        assert result != HealthTag.SUCCESS_WITH_FALLBACK
        # timeout flag set → TIMEOUT wins (higher priority than TOOL_FAILURE)
        assert result == HealthTag.TIMEOUT


class TestMixedToolsFallbackBlocked:
    """When tool_a recovers but tool_b never does, the session must be TOOL_FAILURE.

    This is the `any_fallback and not any_unresolved_error` guard.
    tool_a having a fallback is not enough to declare the session a graceful recovery
    when tool_b is still in a permanent error state.
    """

    def test_tool_a_fallback_plus_tool_b_only_errors_is_tool_failure(self) -> None:
        """Canonical mixed case from the task description."""
        spans = [
            _tool_call("tool_a", "error", "transient"),
            _tool_call("tool_a", "success"),
            _tool_call("tool_b", "error", "permanent"),
        ]
        result = tag_from_spans(spans)
        assert result == HealthTag.TOOL_FAILURE, (
            f"Expected TOOL_FAILURE (tool_b has unresolved errors), got {result!r}"
        )

    def test_tool_a_fallback_plus_tool_b_only_errors_is_not_success_with_fallback(
        self,
    ) -> None:
        """Explicit negative assertion for the most dangerous misclassification."""
        spans = [
            _tool_call("tool_a", "error", "transient"),
            _tool_call("tool_a", "success"),
            _tool_call("tool_b", "error", "permanent"),
        ]
        assert tag_from_spans(spans) != HealthTag.SUCCESS_WITH_FALLBACK

    def test_three_tools_one_unresolved_blocks_fallback(self) -> None:
        """tool_a recovers, tool_b recovers, tool_c only errors → TOOL_FAILURE."""
        spans = [
            _tool_call("tool_a", "error", "e1"),
            _tool_call("tool_a", "success"),
            _tool_call("tool_b", "error", "e2"),
            _tool_call("tool_b", "success"),
            _tool_call("tool_c", "error", "fatal"),
        ]
        result = tag_from_spans(spans)
        assert result == HealthTag.TOOL_FAILURE

    def test_all_tools_recover_is_success_with_fallback(self) -> None:
        """Confirm the positive case: every tool that failed also eventually succeeded."""
        spans = [
            _tool_call("tool_a", "error", "transient"),
            _tool_call("tool_a", "success"),
            _tool_call("tool_b", "error", "transient"),
            _tool_call("tool_b", "success"),
        ]
        result = tag_from_spans(spans)
        assert result == HealthTag.SUCCESS_WITH_FALLBACK

    def test_interleaved_calls_order_does_not_affect_result(self) -> None:
        """The classification depends on the SET of statuses per tool, not call order.

        Interleaving calls from tool_a and tool_b should not trick the tagger
        into treating tool_b's errors as resolved by tool_a's success.
        """
        spans = [
            _tool_call("tool_a", "error", "e-a"),
            _tool_call("tool_b", "error", "e-b-1"),
            _tool_call("tool_a", "success"),         # tool_a recovers
            _tool_call("tool_b", "error", "e-b-2"),  # tool_b never recovers
        ]
        assert tag_from_spans(spans) == HealthTag.TOOL_FAILURE

    def test_tool_b_only_errors_with_no_tool_a_fallback_is_tool_failure(self) -> None:
        """Both tools fail, neither recovers — both paths in tool_results unresolved."""
        spans = [
            _tool_call("tool_a", "error", "e-a"),
            _tool_call("tool_b", "error", "e-b"),
        ]
        assert tag_from_spans(spans) == HealthTag.TOOL_FAILURE


class TestAgentSpansExcludedFromFallbackDetection:
    """LLM generation spans (span_type='agent') must not participate in fallback detection.

    The engine excludes agent spans from the tool_results bucket so that an LLM
    retry cycle (agent error + agent success on the same model) never produces a
    false SUCCESS_WITH_FALLBACK tag.

    Important: agent spans with status=error STILL set the global has_error flag,
    so a session with only agent-error spans resolves to TOOL_FAILURE — not
    SUCCESS_WITH_FALLBACK and not SUCCESS. This is intentional and tested below.
    """

    def test_agent_error_plus_success_is_tool_failure_not_fallback(self) -> None:
        """Agent retry (LLM error then success) sets has_error, never SUCCESS_WITH_FALLBACK.

        The agent span is excluded from tool_results (no fallback bucket entry),
        but has_error=True from the error span still causes TOOL_FAILURE to be
        returned. This is the correct behaviour — the LLM itself had an error.
        """
        spans = [
            _agent_span("error"),   # LLM generation failed — sets has_error=True
            _agent_span("success"), # LLM generation retried successfully
        ]
        result = tag_from_spans(spans)
        # Agent spans are excluded from tool_results, so no fallback path is taken.
        # has_error=True → TOOL_FAILURE. Must never be SUCCESS_WITH_FALLBACK.
        assert result == HealthTag.TOOL_FAILURE
        assert result != HealthTag.SUCCESS_WITH_FALLBACK

    def test_agent_error_with_unresolved_tool_error_is_tool_failure(self) -> None:
        """Agent retries + MCP tool only errors = TOOL_FAILURE, not SUCCESS_WITH_FALLBACK."""
        spans = [
            _agent_span("error"),
            _agent_span("success"),
            _tool_call("query", "error", "mcp error"),  # unresolved
        ]
        result = tag_from_spans(spans)
        assert result == HealthTag.TOOL_FAILURE
        assert result != HealthTag.SUCCESS_WITH_FALLBACK

    def test_agent_span_with_empty_tool_name_not_mixed_into_tool_fallback(self) -> None:
        """Agent spans have empty tool_name and span_type='agent'.

        They must not be accidentally bucketed into the '' key of tool_results
        and then misidentify an LLM retry as a tool fallback.
        """
        spans = [
            # LLM calls with empty tool_name and span_type=agent
            {"tool_name": "", "status": "error", "span_type": "agent", "error": "gen fail"},
            {"tool_name": "", "status": "success", "span_type": "agent", "error": None},
            # MCP tool call that fails and never recovers
            _tool_call("list_tables", "error", "db down"),
        ]
        result = tag_from_spans(spans)
        assert result == HealthTag.TOOL_FAILURE
        assert result != HealthTag.SUCCESS_WITH_FALLBACK


class TestFallbackRequiresSameToolSuccess:
    """SUCCESS_WITH_FALLBACK requires the same tool to have both a failure AND a success.

    These tests guard the `tool_has_success` branch inside the tool_results loop.
    """

    def test_success_on_different_tool_does_not_grant_fallback(self) -> None:
        """tool_a only errors, tool_b only succeeds — cross-tool recovery is not fallback."""
        spans = [
            _tool_call("tool_a", "error", "permanent"),
            _tool_call("tool_b", "success"),
        ]
        result = tag_from_spans(spans)
        assert result == HealthTag.TOOL_FAILURE
        assert result != HealthTag.SUCCESS_WITH_FALLBACK

    def test_single_success_on_its_own_is_plain_success(self) -> None:
        spans = [_tool_call("query", "success")]
        assert tag_from_spans(spans) == HealthTag.SUCCESS

    def test_two_successes_same_tool_is_not_fallback(self) -> None:
        """Calling the same tool twice successfully is routine, not a fallback."""
        spans = [
            _tool_call("query", "success"),
            _tool_call("query", "success"),
        ]
        assert tag_from_spans(spans) == HealthTag.SUCCESS
