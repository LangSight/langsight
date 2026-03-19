from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from langsight.sdk.models import ToolCallSpan, ToolCallStatus


class TestToolCallSpan:
    def test_default_span_id_is_uuid(self) -> None:
        span = ToolCallSpan(
            server_name="pg",
            tool_name="query",
            started_at=datetime.now(UTC),
            ended_at=datetime.now(UTC),
            latency_ms=42.0,
            status=ToolCallStatus.SUCCESS,
        )
        assert len(span.span_id) == 36  # UUID format
        assert "-" in span.span_id

    def test_each_span_has_unique_id(self) -> None:
        now = datetime.now(UTC)
        s1 = ToolCallSpan(server_name="pg", tool_name="q", started_at=now, ended_at=now, latency_ms=0, status=ToolCallStatus.SUCCESS)
        s2 = ToolCallSpan(server_name="pg", tool_name="q", started_at=now, ended_at=now, latency_ms=0, status=ToolCallStatus.SUCCESS)
        assert s1.span_id != s2.span_id

    def test_optional_fields_default_to_none(self) -> None:
        now = datetime.now(UTC)
        span = ToolCallSpan(server_name="pg", tool_name="q", started_at=now, ended_at=now, latency_ms=0, status=ToolCallStatus.SUCCESS)
        assert span.trace_id is None
        assert span.error is None
        assert span.agent_name is None
        assert span.session_id is None

    def test_serialises_to_json(self) -> None:
        now = datetime.now(UTC)
        span = ToolCallSpan(server_name="pg", tool_name="query", started_at=now, ended_at=now, latency_ms=42.0, status=ToolCallStatus.SUCCESS)
        data = span.model_dump(mode="json")
        assert data["server_name"] == "pg"
        assert data["status"] == "success"
        assert data["latency_ms"] == 42.0


class TestToolCallSpanRecord:
    def test_computes_latency_automatically(self) -> None:
        started = datetime.now(UTC) - timedelta(milliseconds=100)
        span = ToolCallSpan.record(
            server_name="pg",
            tool_name="query",
            started_at=started,
            status=ToolCallStatus.SUCCESS,
        )
        assert span.latency_ms >= 100.0
        assert span.latency_ms < 5000.0  # sanity check

    def test_ended_at_is_after_started_at(self) -> None:
        started = datetime.now(UTC)
        span = ToolCallSpan.record(server_name="pg", tool_name="q", started_at=started, status=ToolCallStatus.SUCCESS)
        assert span.ended_at >= span.started_at

    def test_error_status_stores_message(self) -> None:
        span = ToolCallSpan.record(
            server_name="pg",
            tool_name="query",
            started_at=datetime.now(UTC),
            status=ToolCallStatus.ERROR,
            error="connection refused",
        )
        assert span.status == ToolCallStatus.ERROR
        assert span.error == "connection refused"

    def test_metadata_attached(self) -> None:
        span = ToolCallSpan.record(
            server_name="pg",
            tool_name="query",
            started_at=datetime.now(UTC),
            status=ToolCallStatus.SUCCESS,
            trace_id="trace-123",
            agent_name="support-agent",
            session_id="sess-abc",
        )
        assert span.trace_id == "trace-123"
        assert span.agent_name == "support-agent"
        assert span.session_id == "sess-abc"


class TestToolCallSpanPayloads:
    """P5.1 — payload capture: input_args and output_result fields."""

    @pytest.mark.unit
    def test_tool_call_span_defaults_payloads_to_none(self) -> None:
        """record() with no payload kwargs leaves both fields as None."""
        span = ToolCallSpan.record(
            server_name="pg",
            tool_name="query",
            started_at=datetime.now(UTC),
            status=ToolCallStatus.SUCCESS,
        )
        assert span.input_args is None
        assert span.output_result is None

    @pytest.mark.unit
    def test_tool_call_span_stores_input_args(self) -> None:
        """input_args dict is stored verbatim on the span."""
        args = {"sql": "SELECT 1", "limit": 100}
        span = ToolCallSpan.record(
            server_name="pg",
            tool_name="query",
            started_at=datetime.now(UTC),
            status=ToolCallStatus.SUCCESS,
            input_args=args,
        )
        assert span.input_args == {"sql": "SELECT 1", "limit": 100}

    @pytest.mark.unit
    def test_tool_call_span_stores_output_result(self) -> None:
        """output_result string is stored verbatim on the span."""
        span = ToolCallSpan.record(
            server_name="pg",
            tool_name="query",
            started_at=datetime.now(UTC),
            status=ToolCallStatus.SUCCESS,
            output_result='{"rows": 1}',
        )
        assert span.output_result == '{"rows": 1}'

    @pytest.mark.unit
    def test_tool_call_span_serialises_to_json(self) -> None:
        """model_dump(mode='json') includes input_args and output_result keys."""
        span = ToolCallSpan.record(
            server_name="pg",
            tool_name="query",
            started_at=datetime.now(UTC),
            status=ToolCallStatus.SUCCESS,
            input_args={"sql": "SELECT 1"},
            output_result='{"rows": 1}',
        )
        data = span.model_dump(mode="json")
        assert "input_args" in data
        assert "output_result" in data
        assert data["input_args"] == {"sql": "SELECT 1"}
        assert data["output_result"] == '{"rows": 1}'
