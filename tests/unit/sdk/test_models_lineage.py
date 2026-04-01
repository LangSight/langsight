"""Tests for lineage hardening fields on ToolCallSpan (v1.0 protocol).

Covers:
- SpanType literal with 'llm_intent'
- LineageProvenance and LineageStatus type aliases
- New lineage fields: target_agent_name, lineage_provenance, lineage_status, schema_version
- handoff_span() sets target_agent_name and lineage_provenance explicitly
- record() accepts and passes through all lineage params
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from langsight.sdk.models import (
    LineageProvenance,
    LineageStatus,
    SpanType,
    ToolCallSpan,
    ToolCallStatus,
)


# =============================================================================
# SpanType literal
# =============================================================================


class TestSpanType:
    def test_tool_call_is_valid_span_type(self) -> None:
        span = ToolCallSpan(
            server_name="pg",
            tool_name="query",
            started_at=datetime.now(UTC),
            ended_at=datetime.now(UTC),
            status=ToolCallStatus.SUCCESS,
            span_type="tool_call",
        )
        assert span.span_type == "tool_call"

    def test_agent_is_valid_span_type(self) -> None:
        span = ToolCallSpan(
            server_name="orchestrator",
            tool_name="run",
            started_at=datetime.now(UTC),
            ended_at=datetime.now(UTC),
            status=ToolCallStatus.SUCCESS,
            span_type="agent",
        )
        assert span.span_type == "agent"

    def test_handoff_is_valid_span_type(self) -> None:
        span = ToolCallSpan(
            server_name="orchestrator",
            tool_name="\u2192 billing",
            started_at=datetime.now(UTC),
            ended_at=datetime.now(UTC),
            status=ToolCallStatus.SUCCESS,
            span_type="handoff",
        )
        assert span.span_type == "handoff"

    def test_llm_intent_is_valid_span_type(self) -> None:
        """llm_intent was added in the lineage hardening feature."""
        span = ToolCallSpan(
            server_name="openai",
            tool_name="get_weather",
            started_at=datetime.now(UTC),
            ended_at=datetime.now(UTC),
            status=ToolCallStatus.SUCCESS,
            span_type="llm_intent",
        )
        assert span.span_type == "llm_intent"

    def test_invalid_span_type_rejected(self) -> None:
        with pytest.raises(Exception):
            ToolCallSpan(
                server_name="pg",
                tool_name="query",
                started_at=datetime.now(UTC),
                ended_at=datetime.now(UTC),
                status=ToolCallStatus.SUCCESS,
                span_type="invalid_type",  # type: ignore[arg-type]
            )


# =============================================================================
# LineageProvenance type alias
# =============================================================================


class TestLineageProvenance:
    @pytest.mark.parametrize(
        "value",
        [
            "explicit",
            "derived_parent",
            "derived_timing",
            "derived_legacy",
            "inferred_otel",
        ],
    )
    def test_all_valid_provenance_values(self, value: LineageProvenance) -> None:
        span = ToolCallSpan(
            server_name="pg",
            tool_name="query",
            started_at=datetime.now(UTC),
            ended_at=datetime.now(UTC),
            status=ToolCallStatus.SUCCESS,
            lineage_provenance=value,
        )
        assert span.lineage_provenance == value

    def test_invalid_provenance_rejected(self) -> None:
        with pytest.raises(Exception):
            ToolCallSpan(
                server_name="pg",
                tool_name="query",
                started_at=datetime.now(UTC),
                ended_at=datetime.now(UTC),
                status=ToolCallStatus.SUCCESS,
                lineage_provenance="not_a_real_value",  # type: ignore[arg-type]
            )


# =============================================================================
# LineageStatus type alias
# =============================================================================


class TestLineageStatus:
    @pytest.mark.parametrize(
        "value",
        [
            "complete",
            "incomplete",
            "orphaned",
            "invalid_parent",
            "session_mismatch",
            "trace_mismatch",
        ],
    )
    def test_all_valid_status_values(self, value: LineageStatus) -> None:
        span = ToolCallSpan(
            server_name="pg",
            tool_name="query",
            started_at=datetime.now(UTC),
            ended_at=datetime.now(UTC),
            status=ToolCallStatus.SUCCESS,
            lineage_status=value,
        )
        assert span.lineage_status == value

    def test_invalid_lineage_status_rejected(self) -> None:
        with pytest.raises(Exception):
            ToolCallSpan(
                server_name="pg",
                tool_name="query",
                started_at=datetime.now(UTC),
                ended_at=datetime.now(UTC),
                status=ToolCallStatus.SUCCESS,
                lineage_status="bogus",  # type: ignore[arg-type]
            )


# =============================================================================
# Default values for lineage fields
# =============================================================================


class TestLineageFieldDefaults:
    def test_target_agent_name_defaults_to_none(self) -> None:
        span = ToolCallSpan(
            server_name="pg",
            tool_name="query",
            started_at=datetime.now(UTC),
            ended_at=datetime.now(UTC),
            status=ToolCallStatus.SUCCESS,
        )
        assert span.target_agent_name is None

    def test_lineage_provenance_defaults_to_explicit(self) -> None:
        span = ToolCallSpan(
            server_name="pg",
            tool_name="query",
            started_at=datetime.now(UTC),
            ended_at=datetime.now(UTC),
            status=ToolCallStatus.SUCCESS,
        )
        assert span.lineage_provenance == "explicit"

    def test_lineage_status_defaults_to_complete(self) -> None:
        span = ToolCallSpan(
            server_name="pg",
            tool_name="query",
            started_at=datetime.now(UTC),
            ended_at=datetime.now(UTC),
            status=ToolCallStatus.SUCCESS,
        )
        assert span.lineage_status == "complete"

    def test_schema_version_defaults_to_1_0(self) -> None:
        span = ToolCallSpan(
            server_name="pg",
            tool_name="query",
            started_at=datetime.now(UTC),
            ended_at=datetime.now(UTC),
            status=ToolCallStatus.SUCCESS,
        )
        assert span.schema_version == "1.0"


# =============================================================================
# handoff_span() — explicit lineage fields
# =============================================================================


class TestHandoffSpanLineage:
    def test_handoff_span_sets_target_agent_name(self) -> None:
        span = ToolCallSpan.handoff_span(
            from_agent="orchestrator",
            to_agent="billing-agent",
            started_at=datetime.now(UTC),
        )
        assert span.target_agent_name == "billing-agent"

    def test_handoff_span_sets_lineage_provenance_explicit(self) -> None:
        span = ToolCallSpan.handoff_span(
            from_agent="orchestrator",
            to_agent="analyst",
            started_at=datetime.now(UTC),
        )
        assert span.lineage_provenance == "explicit"

    def test_handoff_span_sets_schema_version(self) -> None:
        span = ToolCallSpan.handoff_span(
            from_agent="a",
            to_agent="b",
            started_at=datetime.now(UTC),
        )
        assert span.schema_version == "1.0"

    def test_handoff_span_sets_span_type_to_handoff(self) -> None:
        span = ToolCallSpan.handoff_span(
            from_agent="a",
            to_agent="b",
            started_at=datetime.now(UTC),
        )
        assert span.span_type == "handoff"

    def test_handoff_span_tool_name_contains_arrow(self) -> None:
        """tool_name still has arrow prefix for backward compat display."""
        span = ToolCallSpan.handoff_span(
            from_agent="orchestrator",
            to_agent="billing-agent",
            started_at=datetime.now(UTC),
        )
        assert span.tool_name == "\u2192 billing-agent"

    def test_handoff_span_server_name_is_from_agent(self) -> None:
        span = ToolCallSpan.handoff_span(
            from_agent="orchestrator",
            to_agent="billing-agent",
            started_at=datetime.now(UTC),
        )
        assert span.server_name == "orchestrator"

    def test_handoff_span_agent_name_is_from_agent(self) -> None:
        span = ToolCallSpan.handoff_span(
            from_agent="orchestrator",
            to_agent="billing-agent",
            started_at=datetime.now(UTC),
        )
        assert span.agent_name == "orchestrator"

    def test_handoff_span_inherits_trace_and_session(self) -> None:
        span = ToolCallSpan.handoff_span(
            from_agent="a",
            to_agent="b",
            started_at=datetime.now(UTC),
            trace_id="trace-abc",
            session_id="sess-123",
        )
        assert span.trace_id == "trace-abc"
        assert span.session_id == "sess-123"

    def test_handoff_span_inherits_parent_span_id(self) -> None:
        span = ToolCallSpan.handoff_span(
            from_agent="a",
            to_agent="b",
            started_at=datetime.now(UTC),
            parent_span_id="parent-xyz",
        )
        assert span.parent_span_id == "parent-xyz"

    def test_handoff_span_status_is_success(self) -> None:
        span = ToolCallSpan.handoff_span(
            from_agent="a",
            to_agent="b",
            started_at=datetime.now(UTC),
        )
        assert span.status == ToolCallStatus.SUCCESS


# =============================================================================
# record() — lineage params pass-through
# =============================================================================


class TestRecordLineageParams:
    def test_record_passes_target_agent_name(self) -> None:
        span = ToolCallSpan.record(
            server_name="pg",
            tool_name="query",
            started_at=datetime.now(UTC),
            status=ToolCallStatus.SUCCESS,
            target_agent_name="billing",
        )
        assert span.target_agent_name == "billing"

    def test_record_passes_lineage_provenance(self) -> None:
        span = ToolCallSpan.record(
            server_name="pg",
            tool_name="query",
            started_at=datetime.now(UTC),
            status=ToolCallStatus.SUCCESS,
            lineage_provenance="derived_parent",
        )
        assert span.lineage_provenance == "derived_parent"

    def test_record_passes_lineage_status(self) -> None:
        span = ToolCallSpan.record(
            server_name="pg",
            tool_name="query",
            started_at=datetime.now(UTC),
            status=ToolCallStatus.SUCCESS,
            lineage_status="incomplete",
        )
        assert span.lineage_status == "incomplete"

    def test_record_passes_schema_version(self) -> None:
        span = ToolCallSpan.record(
            server_name="pg",
            tool_name="query",
            started_at=datetime.now(UTC),
            status=ToolCallStatus.SUCCESS,
            schema_version="2.0",
        )
        assert span.schema_version == "2.0"

    def test_record_defaults_for_lineage_params(self) -> None:
        """When lineage params are omitted, record() uses the same defaults as the model."""
        span = ToolCallSpan.record(
            server_name="pg",
            tool_name="query",
            started_at=datetime.now(UTC),
            status=ToolCallStatus.SUCCESS,
        )
        assert span.target_agent_name is None
        assert span.lineage_provenance == "explicit"
        assert span.lineage_status == "complete"
        assert span.schema_version == "1.0"


# =============================================================================
# Serialization — lineage fields in model_dump
# =============================================================================


class TestLineageSerialization:
    def test_lineage_fields_in_json_dump(self) -> None:
        span = ToolCallSpan.handoff_span(
            from_agent="a",
            to_agent="b",
            started_at=datetime.now(UTC),
        )
        data = span.model_dump(mode="json")
        assert data["target_agent_name"] == "b"
        assert data["lineage_provenance"] == "explicit"
        assert data["lineage_status"] == "complete"
        assert data["schema_version"] == "1.0"

    def test_null_target_agent_in_non_handoff_span(self) -> None:
        span = ToolCallSpan.record(
            server_name="pg",
            tool_name="query",
            started_at=datetime.now(UTC),
            status=ToolCallStatus.SUCCESS,
        )
        data = span.model_dump(mode="json")
        assert data["target_agent_name"] is None
