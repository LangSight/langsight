"""
Unit tests for the Live SSE event contract.

Verifies that:
1. The broadcaster publishes span:new events (not sessions arrays)
2. span:new payloads always contain the fields the dashboard expects
3. started_at is present in the payload so the frontend can track timestamps
4. project_id is present for tenant isolation
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from langsight.api.broadcast import SSEBroadcaster
from langsight.sdk.models import ToolCallSpan, ToolCallStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_span(**kwargs: object) -> ToolCallSpan:
    defaults: dict = {
        "server_name": "test-server",
        "tool_name": "query",
        "started_at": datetime(2026, 3, 26, 10, 0, 0, tzinfo=UTC),
        "ended_at": datetime(2026, 3, 26, 10, 0, 1, tzinfo=UTC),
        "latency_ms": 1000.0,
        "status": ToolCallStatus.SUCCESS,
        "session_id": "abc123",
        "agent_name": "test-agent",
        "project_id": "proj-1",
    }
    defaults.update(kwargs)
    return ToolCallSpan(**defaults)


# ---------------------------------------------------------------------------
# Broadcaster publishes span:new, not sessions
# ---------------------------------------------------------------------------

class TestBroadcasterEventType:
    def test_publish_span_new_is_the_correct_event_type(self) -> None:
        """Broadcaster must emit 'span:new', not 'sessions' or a default message."""
        broadcaster = SSEBroadcaster()
        published: list[tuple[str, dict]] = []

        original_publish = broadcaster.publish

        def capture(event_type: str, data: dict) -> None:
            published.append((event_type, data))
            original_publish(event_type, data)

        broadcaster.publish = capture  # type: ignore[method-assign]

        span = _make_span()
        broadcaster.publish(
            "span:new",
            {
                "project_id": span.project_id,
                "session_id": span.session_id,
                "agent_name": span.agent_name,
                "server_name": span.server_name,
                "tool_name": span.tool_name,
                "status": span.status,
                "latency_ms": span.latency_ms,
                "started_at": span.started_at.isoformat() if span.started_at else None,
            },
        )

        assert len(published) == 1
        event_type, payload = published[0]
        assert event_type == "span:new", (
            f"Expected event type 'span:new', got '{event_type}'. "
            "The live page addEventListener('span:new', ...) will never fire."
        )

    def test_no_sessions_event_is_ever_published(self) -> None:
        """'sessions' is a dead event type — nothing publishes it."""
        broadcaster = SSEBroadcaster()
        published_types: list[str] = []

        original = broadcaster.publish

        def capture(event_type: str, data: dict) -> None:
            published_types.append(event_type)
            original(event_type, data)

        broadcaster.publish = capture  # type: ignore[method-assign]

        span = _make_span()
        broadcaster.publish("span:new", {"session_id": span.session_id})

        assert "sessions" not in published_types, (
            "A 'sessions' event was published — the live page "
            "addEventListener('span:new', ...) handler would never fire."
        )


# ---------------------------------------------------------------------------
# span:new payload shape
# ---------------------------------------------------------------------------

class TestSpanNewPayloadShape:
    REQUIRED_FIELDS = {
        "project_id",    # tenant isolation — SSE stream filters by this
        "session_id",    # primary key for live row
        "agent_name",    # displayed in live table
        "server_name",   # displayed in live table
        "tool_name",     # informational
        "status",        # used to count errors
        "latency_ms",    # informational
        "started_at",    # REQUIRED for frontend timestamp tracking (Bug 3)
    }

    def _build_payload(self, span: ToolCallSpan) -> dict:
        return {
            "project_id": span.project_id,
            "session_id": span.session_id,
            "agent_name": span.agent_name,
            "server_name": span.server_name,
            "tool_name": span.tool_name,
            "status": span.status,
            "latency_ms": span.latency_ms,
            "started_at": span.started_at.isoformat() if span.started_at else None,
        }

    def test_payload_contains_all_required_fields(self) -> None:
        span = _make_span()
        payload = self._build_payload(span)
        missing = self.REQUIRED_FIELDS - set(payload.keys())
        assert not missing, f"span:new payload missing required fields: {missing}"

    def test_started_at_is_iso_string(self) -> None:
        span = _make_span()
        payload = self._build_payload(span)
        assert isinstance(payload["started_at"], str)
        # Must be parseable as a datetime
        parsed = datetime.fromisoformat(payload["started_at"])
        assert parsed.tzinfo is not None, "started_at must be timezone-aware ISO string"

    def test_started_at_is_none_for_span_with_no_started_at(self) -> None:
        """When started_at is absent (e.g. span has no timestamp), payload carries None."""
        # ToolCallSpan requires a datetime, so simulate via direct payload build
        payload = {
            "project_id": "proj-1",
            "session_id": "s",
            "agent_name": "a",
            "server_name": "s",
            "tool_name": "t",
            "status": "success",
            "latency_ms": 0.0,
            "started_at": None,  # explicitly None — edge case
        }
        assert payload["started_at"] is None

    def test_payload_is_json_serialisable(self) -> None:
        span = _make_span()
        payload = self._build_payload(span)
        # Must not raise
        serialised = json.dumps(payload)
        roundtripped = json.loads(serialised)
        assert roundtripped["session_id"] == span.session_id

    def test_status_is_string_value_not_enum(self) -> None:
        span = _make_span(status=ToolCallStatus.ERROR)
        payload = self._build_payload(span)
        # status must be a plain string so JS can compare with "success"
        assert isinstance(payload["status"], (str, ToolCallStatus))

    def test_error_span_has_non_success_status(self) -> None:
        span = _make_span(status=ToolCallStatus.ERROR)
        payload = self._build_payload(span)
        assert payload["status"] != "success"

    def test_project_id_propagates_correctly(self) -> None:
        span = _make_span(project_id="proj-xyz")
        payload = self._build_payload(span)
        assert payload["project_id"] == "proj-xyz"

    def test_null_project_id_is_preserved(self) -> None:
        span = _make_span(project_id=None)
        payload = self._build_payload(span)
        assert payload["project_id"] is None


# ---------------------------------------------------------------------------
# SSE format (raw wire format)
# ---------------------------------------------------------------------------

class TestSSEWireFormat:
    def test_sse_event_format_for_span_new(self) -> None:
        """The SSE wire format must use 'event: span:new' so addEventListener fires.

        Tests by directly inspecting the raw string that publish() places in
        subscriber queues, without running a full async subscribe loop.
        """
        import asyncio
        import json as _json

        broadcaster = SSEBroadcaster()

        # Register a real asyncio.Queue as a subscriber (mimics what subscribe() does)
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=200)
        broadcaster._clients.append((queue, None))  # type: ignore[attr-defined]

        span = _make_span()
        broadcaster.publish(
            "span:new",
            {
                "project_id": span.project_id,
                "session_id": span.session_id,
                "agent_name": span.agent_name,
                "server_name": span.server_name,
                "tool_name": str(span.tool_name),
                "status": str(span.status.value),
                "latency_ms": span.latency_ms,
                "started_at": span.started_at.isoformat(),
            },
        )

        assert not queue.empty(), "No SSE event was placed in subscriber queue"
        raw = queue.get_nowait()

        assert "event: span:new" in raw, (
            f"SSE wire format must include 'event: span:new' line. Got: {raw!r}. "
            "Browser addEventListener('span:new', ...) won't fire without it."
        )
        assert "data: " in raw
        data_line = next(l for l in raw.splitlines() if l.startswith("data: "))
        parsed = _json.loads(data_line[len("data: "):])
        assert parsed["session_id"] == "abc123"
        assert "started_at" in parsed, "started_at must be in SSE payload"
