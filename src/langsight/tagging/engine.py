"""
Session health tagger — auto-classifies sessions with machine-readable tags.

Computed server-side from span data after a session ends (or immediately
when a prevented span is ingested).

Tags are priority-ordered: the highest-priority matching tag wins.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger()


class HealthTag(StrEnum):
    """Machine-readable session health tags, ordered by priority (highest first)."""

    LOOP_DETECTED = "loop_detected"
    BUDGET_EXCEEDED = "budget_exceeded"
    CIRCUIT_BREAKER_OPEN = "circuit_breaker_open"
    SCHEMA_DRIFT = "schema_drift"
    TIMEOUT = "timeout"
    TOOL_FAILURE = "tool_failure"
    SUCCESS_WITH_FALLBACK = "success_with_fallback"
    SUCCESS = "success"


def tag_from_spans(spans: list[dict[str, Any]]) -> HealthTag:
    """Compute the health tag for a session from its flat list of spans.

    Priority order (highest wins):
    1. Any prevented span with "loop_detected" → LOOP_DETECTED
    2. Any prevented span with "budget_exceeded" → BUDGET_EXCEEDED
    3. Any prevented span with "circuit_breaker" → CIRCUIT_BREAKER_OPEN
    4. Any span with "schema drift" in error → SCHEMA_DRIFT
    5. Any span with status=timeout → TIMEOUT
    6. Any span with status=error → TOOL_FAILURE
    7. Retries detected (same tool called multiple times, some failed) → SUCCESS_WITH_FALLBACK
    8. All spans succeeded → SUCCESS
    """
    has_error = False
    has_timeout = False
    has_schema_drift = False

    # Track tool calls for fallback detection
    tool_results: dict[str, list[str]] = {}  # (tool_name) → [statuses]

    for span in spans:
        status = str(span.get("status", "")).lower()
        error = str(span.get("error", "") or "").lower()

        # Priority 1-3: Prevention events
        if status == "prevented":
            if "loop_detected" in error:
                return HealthTag.LOOP_DETECTED
            if "budget_exceeded" in error:
                return HealthTag.BUDGET_EXCEEDED
            if "circuit_breaker" in error:
                return HealthTag.CIRCUIT_BREAKER_OPEN

        # Priority 4: Schema drift
        if "schema drift" in error:
            has_schema_drift = True

        # Priority 5: Timeout
        if status == "timeout":
            has_timeout = True

        # Priority 6: Error
        if status == "error":
            has_error = True

        # Track for fallback detection — only MCP tool_call spans.
        # LLM generation spans (span_type="agent") are excluded: retrying the LLM
        # is not an MCP fallback. Mixing them caused false success_with_fallback tags
        # when a session ended on a Gemini/OpenAI error.
        if span.get("span_type") == "tool_call":
            tool_name = span.get("tool_name", "")
            if tool_name:
                tool_results.setdefault(tool_name, []).append(status)

    if has_schema_drift:
        return HealthTag.SCHEMA_DRIFT

    # Priority 7: Fallback detection — the session ultimately succeeded despite
    # some MCP tool call failures (retried and recovered on the SAME tool).
    # Requires at least one tool with both a failure and a success, AND no tool
    # with only failures that were never resolved (unresolved errors → TOOL_FAILURE).
    any_fallback = False
    any_unresolved_error = False
    for statuses in tool_results.values():
        tool_has_failure = any(s in ("error", "timeout") for s in statuses)
        tool_has_success = any(s == "success" for s in statuses)
        if tool_has_failure:
            if tool_has_success:
                any_fallback = True
            else:
                any_unresolved_error = True

    if any_fallback and not any_unresolved_error:
        return HealthTag.SUCCESS_WITH_FALLBACK

    if has_timeout:
        return HealthTag.TIMEOUT
    if has_error:
        return HealthTag.TOOL_FAILURE

    return HealthTag.SUCCESS
