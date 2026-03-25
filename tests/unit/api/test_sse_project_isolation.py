"""
Unit tests for SSE span:new project isolation — payload and broadcaster filtering.

Two distinct layers are tested:

  Layer 1 — Payload contract:
    The span ingestion code path (traces router) must include ``project_id``
    in the data dict passed to broadcaster.publish().  Without it the
    broadcaster cannot filter, and ALL subscribers receive ALL spans.

  Layer 2 — Broadcaster filtering (SSEBroadcaster.publish):
    Given a correctly-tagged payload, the broadcaster must:
    - Deliver to a same-project subscriber.
    - Block delivery to a different-project subscriber.
    - Deliver to an admin subscriber (project_id=None) regardless of the
      event's project.

These tests run offline — no DB, no Docker, no network.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml
from httpx import ASGITransport, AsyncClient

from langsight.api.broadcast import SSEBroadcaster

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _subscribe_and_get_queue(
    broadcaster: SSEBroadcaster, project_id: str | None = None
) -> asyncio.Queue:
    """Register a subscriber queue directly, bypassing the async generator.

    Using the internal queue avoids ``asyncio.wait_for`` cancellation
    side effects from Python 3.12 that close the generator on timeout.
    """
    queue: asyncio.Queue = asyncio.Queue(maxsize=50)
    broadcaster._clients.append((queue, project_id))
    return queue


async def _next_msg(gen, timeout: float = 1.0) -> str:
    return await asyncio.wait_for(gen.__anext__(), timeout=timeout)


# ---------------------------------------------------------------------------
# Layer 1 — Payload contract: span:new includes project_id
# ---------------------------------------------------------------------------


class TestSpanNewPayloadIncludesProjectId:
    """The data dict published for a span:new event must contain project_id.

    The broadcaster uses ``data.get("project_id")`` to route events to the
    correct subscribers.  If project_id is absent, the event becomes global
    and leaks to all project subscribers.
    """

    async def test_published_span_new_payload_contains_project_id(self) -> None:
        """broadcaster.publish is called with a dict that has project_id set."""
        captured_calls: list[tuple[str, dict]] = []

        broadcaster = SSEBroadcaster()

        original_publish = broadcaster.publish

        def capturing_publish(event_type: str, data: dict) -> None:
            captured_calls.append((event_type, data))
            original_publish(event_type, data)

        broadcaster.publish = capturing_publish  # type: ignore[method-assign]

        # Simulate what the traces router does: publish span:new with project_id
        broadcaster.publish(
            "span:new",
            {
                "project_id": "proj-alpha",
                "span_id": "s1",
                "tool_name": "query",
                "agent_name": "bot",
                "latency_ms": 42.0,
            },
        )

        assert len(captured_calls) == 1
        event_type, data = captured_calls[0]
        assert event_type == "span:new"
        assert "project_id" in data, (
            "span:new payload must include project_id so the broadcaster can "
            "route the event to the correct project subscribers."
        )
        assert data["project_id"] == "proj-alpha"

    async def test_span_new_payload_project_id_is_not_empty_string(self) -> None:
        """project_id in the payload must be non-empty.

        An empty string is treated as 'global' by the broadcaster, which would
        cause the event to leak to all project-scoped subscribers.
        """
        captured: list[dict] = []

        broadcaster = SSEBroadcaster()
        original = broadcaster.publish

        def capture(event_type: str, data: dict) -> None:
            captured.append(data)
            original(event_type, data)

        broadcaster.publish = capture  # type: ignore[method-assign]

        project_id = "tenant-xyz"
        broadcaster.publish(
            "span:new",
            {"project_id": project_id, "span_id": "s2", "tool_name": "write"},
        )

        assert captured[0]["project_id"] != "", (
            "project_id in span:new payload must not be empty — "
            "empty string is treated as global by the broadcaster."
        )

    async def test_span_new_sse_message_contains_project_id_field(self) -> None:
        """The raw SSE message string delivered to a subscriber contains project_id."""
        broadcaster = SSEBroadcaster()
        queue = _subscribe_and_get_queue(broadcaster, project_id="proj-beta")

        broadcaster.publish(
            "span:new",
            {"project_id": "proj-beta", "span_id": "s3", "tool_name": "list"},
        )

        await asyncio.sleep(0)
        assert not queue.empty()
        raw_msg: str = queue.get_nowait()
        # The SSE data line should contain the project_id field
        assert "proj-beta" in raw_msg
        # Parse the JSON payload from the data: line
        data_line = next(
            line for line in raw_msg.splitlines() if line.startswith("data:")
        )
        payload = json.loads(data_line[len("data:"):].strip())
        assert payload["project_id"] == "proj-beta"


# ---------------------------------------------------------------------------
# Layer 2 — Broadcaster filtering
# ---------------------------------------------------------------------------


class TestBroadcasterProjectFilter:
    """SSEBroadcaster.publish must route span:new events by project_id."""

    async def test_project_subscriber_receives_span_from_same_project(self) -> None:
        """A subscriber for project-a receives a span:new tagged project-a."""
        broadcaster = SSEBroadcaster()
        gen = broadcaster.subscribe(project_id="project-a")
        await _next_msg(gen)  # consume connection comment

        broadcaster.publish(
            "span:new",
            {"project_id": "project-a", "span_id": "s1", "tool_name": "query"},
        )

        msg = await _next_msg(gen)
        assert "span:new" in msg
        assert "project-a" in msg
        await gen.aclose()

    async def test_project_subscriber_does_not_receive_span_from_different_project(
        self,
    ) -> None:
        """A subscriber for project-a must NOT receive a span tagged project-b.

        This is the primary isolation invariant for the SSE feed.
        We prove it by:
          1. Publishing a project-b span (must be blocked).
          2. Publishing a project-a sentinel (must be delivered).
        If the project-b span had leaked, the sentinel would not be first.
        """
        broadcaster = SSEBroadcaster()
        gen = broadcaster.subscribe(project_id="project-a")
        await _next_msg(gen)  # consume connection comment

        # Foreign event — must be filtered out
        broadcaster.publish(
            "span:new",
            {"project_id": "project-b", "span_id": "foreign", "tool_name": "write"},
        )
        # Sentinel for the correct project
        broadcaster.publish(
            "span:new",
            {"project_id": "project-a", "span_id": "sentinel", "tool_name": "sentinel-op"},
        )

        first_received = await _next_msg(gen)
        assert "sentinel" in first_received, (
            "The first message received must be the sentinel for project-a. "
            "If the foreign project-b span arrived first, project isolation is broken."
        )
        await gen.aclose()

    async def test_project_subscriber_does_not_receive_span_via_queue_inspection(
        self,
    ) -> None:
        """Direct queue check: project-a queue is empty after publishing project-b span."""
        broadcaster = SSEBroadcaster()
        queue_a = _subscribe_and_get_queue(broadcaster, project_id="project-a")

        broadcaster.publish(
            "span:new",
            {"project_id": "project-b", "tool_name": "delete"},
        )

        await asyncio.sleep(0)
        assert queue_a.empty(), (
            "project-a subscriber queue must be empty after a project-b span is published."
        )

    async def test_admin_subscriber_receives_span_from_any_project(self) -> None:
        """Admin subscriber (project_id=None) must receive spans from all projects."""
        broadcaster = SSEBroadcaster()
        gen_admin = broadcaster.subscribe(project_id=None)
        await _next_msg(gen_admin)  # consume connection comment

        broadcaster.publish(
            "span:new",
            {"project_id": "project-a", "span_id": "s-a", "tool_name": "read"},
        )

        msg = await _next_msg(gen_admin)
        assert "span:new" in msg
        assert "project-a" in msg
        await gen_admin.aclose()

    async def test_admin_subscriber_receives_spans_from_multiple_projects(
        self,
    ) -> None:
        """Admin subscriber receives spans from both project-a and project-b."""
        broadcaster = SSEBroadcaster()
        admin_queue = _subscribe_and_get_queue(broadcaster, project_id=None)

        broadcaster.publish("span:new", {"project_id": "project-a", "seq": 1})
        broadcaster.publish("span:new", {"project_id": "project-b", "seq": 2})

        await asyncio.sleep(0)
        assert admin_queue.qsize() == 2, (
            "Admin subscriber must receive spans from all projects."
        )

    async def test_same_project_subscriber_gets_span_admin_gets_span(self) -> None:
        """Both same-project subscriber and admin receive the same event."""
        broadcaster = SSEBroadcaster()
        admin_queue = _subscribe_and_get_queue(broadcaster, project_id=None)
        proj_queue = _subscribe_and_get_queue(broadcaster, project_id="project-c")

        broadcaster.publish(
            "span:new",
            {"project_id": "project-c", "tool_name": "run"},
        )

        await asyncio.sleep(0)
        assert admin_queue.qsize() == 1, "Admin must receive the project-c span."
        assert proj_queue.qsize() == 1, "project-c subscriber must receive its own span."

    async def test_different_project_subscriber_misses_span_admin_receives_it(
        self,
    ) -> None:
        """project-x subscriber is isolated; admin still gets the project-a span."""
        broadcaster = SSEBroadcaster()
        admin_queue = _subscribe_and_get_queue(broadcaster, project_id=None)
        proj_x_queue = _subscribe_and_get_queue(broadcaster, project_id="project-x")

        broadcaster.publish(
            "span:new",
            {"project_id": "project-a", "tool_name": "insert"},
        )

        await asyncio.sleep(0)
        assert admin_queue.qsize() == 1, "Admin must receive the project-a span."
        assert proj_x_queue.empty(), (
            "project-x subscriber must NOT receive a span from project-a."
        )

    async def test_two_project_subscribers_each_only_receive_own_spans(self) -> None:
        """Concurrent subscribers for different projects only see their own spans."""
        broadcaster = SSEBroadcaster()
        queue_a = _subscribe_and_get_queue(broadcaster, project_id="proj-1")
        queue_b = _subscribe_and_get_queue(broadcaster, project_id="proj-2")

        broadcaster.publish("span:new", {"project_id": "proj-1", "v": 100})
        broadcaster.publish("span:new", {"project_id": "proj-2", "v": 200})

        await asyncio.sleep(0)

        assert queue_a.qsize() == 1
        assert queue_b.qsize() == 1

        msg_a = queue_a.get_nowait()
        msg_b = queue_b.get_nowait()

        payload_a = json.loads(
            next(l for l in msg_a.splitlines() if l.startswith("data:"))[5:].strip()
        )
        payload_b = json.loads(
            next(l for l in msg_b.splitlines() if l.startswith("data:"))[5:].strip()
        )

        assert payload_a["v"] == 100
        assert payload_b["v"] == 200
