"""
Unit tests for SSE broadcaster per-project filtering.

Covers:
- publish() only delivers events to subscribers whose project_id matches
- Admin subscribers (project_id=None) receive ALL events
- Project subscribers do NOT receive events for other projects
- Events with no project_id (global events) reach all subscribers
- Existing non-project-filtered behaviour is preserved
"""

from __future__ import annotations

import asyncio

import pytest

from langsight.api.broadcast import SSEBroadcaster

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _next(gen, timeout: float = 1.0) -> str:  # noqa: ASYNC109
    return await asyncio.wait_for(gen.__anext__(), timeout=timeout)


def _subscribe_and_get_queue(
    broadcaster: SSEBroadcaster, project_id: str | None = None
) -> asyncio.Queue:
    """Subscribe and return the internal queue before starting the generator.

    This lets tests inspect whether publish() put anything in the queue without
    needing to await the async generator (which gets cancelled by wait_for in
    Python 3.12, triggering StopAsyncIteration on the next call).
    """
    queue: asyncio.Queue = asyncio.Queue(maxsize=50)
    entry = (queue, project_id)
    broadcaster._clients.append(entry)
    return queue


# ---------------------------------------------------------------------------
# Per-project filtering — project subscriber only sees own events
# ---------------------------------------------------------------------------


class TestPublishProjectFiltering:
    async def test_project_subscriber_receives_own_project_event(self) -> None:
        """A subscriber for project-a gets events with project_id='project-a'."""
        b = SSEBroadcaster()
        gen = b.subscribe(project_id="project-a")
        await _next(gen)  # connection comment

        b.publish("span:new", {"project_id": "project-a", "tool": "query"})

        msg = await _next(gen)
        assert "span:new" in msg
        assert "query" in msg
        await gen.aclose()

    async def test_project_subscriber_does_not_receive_other_project_event(self) -> None:
        """A subscriber for project-a must NOT receive events for project-b."""
        b = SSEBroadcaster()
        queue = _subscribe_and_get_queue(b, project_id="project-a")

        b.publish("span:new", {"project_id": "project-b", "tool": "write"})

        # Give event loop a turn to process any pending delivery
        await asyncio.sleep(0)

        # The queue must be empty — the event was filtered out
        assert queue.empty(), "project-a subscriber must not receive project-b events"

    async def test_two_project_subscribers_each_get_only_their_events(self) -> None:
        """Subscribers for project-a and project-b each see only their own events."""
        b = SSEBroadcaster()
        queue_a = _subscribe_and_get_queue(b, project_id="project-a")
        queue_b = _subscribe_and_get_queue(b, project_id="project-b")

        b.publish("span:new", {"project_id": "project-a", "value": 1})
        b.publish("span:new", {"project_id": "project-b", "value": 2})

        await asyncio.sleep(0)

        # Each queue has exactly one item — its own event
        assert queue_a.qsize() == 1
        assert queue_b.qsize() == 1

        msg_a = queue_a.get_nowait()
        msg_b = queue_b.get_nowait()

        assert '"value": 1' in msg_a
        assert '"value": 2' in msg_b


# ---------------------------------------------------------------------------
# Admin subscriber (project_id=None) receives ALL events
# ---------------------------------------------------------------------------


class TestAdminSubscriberReceivesAll:
    async def test_admin_receives_project_a_event(self) -> None:
        """Admin subscriber (None) must receive events tagged with project-a."""
        b = SSEBroadcaster()
        gen_admin = b.subscribe(project_id=None)
        await _next(gen_admin)  # connection comment

        b.publish("span:new", {"project_id": "project-a", "tool": "list"})

        msg = await _next(gen_admin)
        assert "span:new" in msg
        await gen_admin.aclose()

    async def test_admin_receives_project_b_event(self) -> None:
        """Admin subscriber (None) must receive events tagged with project-b."""
        b = SSEBroadcaster()
        gen_admin = b.subscribe(project_id=None)
        await _next(gen_admin)  # connection comment

        b.publish("health:check", {"project_id": "project-b", "server": "pg-mcp"})

        msg = await _next(gen_admin)
        assert "health:check" in msg
        await gen_admin.aclose()

    async def test_admin_receives_event_with_no_project_id(self) -> None:
        """Admin subscriber receives events that have no project_id key at all."""
        b = SSEBroadcaster()
        gen_admin = b.subscribe(project_id=None)
        await _next(gen_admin)  # connection comment

        b.publish("span:new", {"tool": "query"})  # no project_id key

        msg = await _next(gen_admin)
        assert "span:new" in msg
        await gen_admin.aclose()

    async def test_admin_receives_all_events_project_subscriber_only_own(self) -> None:
        """Admin gets all; project-x subscriber gets only theirs — simultaneously."""
        b = SSEBroadcaster()
        admin_queue = _subscribe_and_get_queue(b, project_id=None)
        proj_x_queue = _subscribe_and_get_queue(b, project_id="project-x")

        b.publish("span:new", {"project_id": "project-x", "tool": "read"})
        b.publish("span:new", {"project_id": "project-y", "tool": "write"})

        await asyncio.sleep(0)

        # Admin gets both events
        assert admin_queue.qsize() == 2

        # project-x subscriber gets only the project-x event
        assert proj_x_queue.qsize() == 1
        msg_proj = proj_x_queue.get_nowait()
        assert "read" in msg_proj


# ---------------------------------------------------------------------------
# Unscoped events (no project_id) must NOT reach project-scoped subscribers
# Security fix: previously unscoped events leaked to all project subscribers.
# Admin subscribers (project_id=None) still receive everything.
# ---------------------------------------------------------------------------


class TestGlobalEventsReachAll:
    async def _assert_no_event(self, gen, timeout: float = 0.05) -> None:
        """Assert the generator yields no event within the timeout window."""
        try:
            await _next(gen, timeout=timeout)
            raise AssertionError("Expected no event but generator yielded one")
        except (asyncio.TimeoutError, StopAsyncIteration):
            pass  # correct — no event delivered

    async def test_event_with_no_project_id_does_not_reach_project_subscriber(self) -> None:
        """Unscoped events must NOT reach project-scoped subscribers — only admins."""
        b = SSEBroadcaster()
        gen = b.subscribe(project_id="project-a")
        await _next(gen)  # connection comment

        b.publish("system:reload", {"message": "config changed"})  # no project_id

        await self._assert_no_event(gen)
        await gen.aclose()

    async def test_event_with_empty_string_project_id_does_not_reach_project_subscriber(self) -> None:
        """Events with project_id='' are unscoped — must not reach project subscribers."""
        b = SSEBroadcaster()
        gen = b.subscribe(project_id="project-a")
        await _next(gen)  # connection comment

        b.publish("system:reload", {"project_id": "", "message": "ping"})

        await self._assert_no_event(gen)
        await gen.aclose()

    async def test_event_with_no_project_id_does_not_reach_multiple_project_subscribers(self) -> None:
        """Unscoped events do not reach any project-scoped subscriber."""
        b = SSEBroadcaster()
        gen_a = b.subscribe(project_id="project-a")
        gen_b = b.subscribe(project_id="project-b")
        await _next(gen_a)
        await _next(gen_b)

        b.publish("system:shutdown", {"message": "maintenance"})  # no project_id

        await self._assert_no_event(gen_a)
        await self._assert_no_event(gen_b)

        await gen_a.aclose()
        await gen_b.aclose()

    async def test_unscoped_event_reaches_admin_subscriber(self) -> None:
        """Unscoped events must still reach admin (project_id=None) subscribers."""
        b = SSEBroadcaster()
        gen = b.subscribe(project_id=None)  # admin
        await _next(gen)  # connection comment

        b.publish("system:reload", {"message": "config changed"})

        msg = await _next(gen)
        assert "system:reload" in msg
        await gen.aclose()


# ---------------------------------------------------------------------------
# Edge cases — project_id in data matches subscriber
# ---------------------------------------------------------------------------


class TestProjectIdMatchingEdgeCases:
    async def test_subscriber_does_not_receive_event_for_prefix_matched_project(self) -> None:
        """'proj' should not match 'proj-extended' — exact match only."""
        b = SSEBroadcaster()
        queue = _subscribe_and_get_queue(b, project_id="proj")

        b.publish("span:new", {"project_id": "proj-extended", "tool": "query"})

        await asyncio.sleep(0)
        assert queue.empty(), "'proj' must not match 'proj-extended'"

    async def test_project_id_matching_is_case_sensitive(self) -> None:
        """'Project-A' and 'project-a' are different project IDs."""
        b = SSEBroadcaster()
        queue = _subscribe_and_get_queue(b, project_id="project-a")

        b.publish("span:new", {"project_id": "Project-A", "tool": "query"})

        await asyncio.sleep(0)
        assert queue.empty(), "case-insensitive match must not occur"

    async def test_same_event_type_different_projects_correctly_routed(self) -> None:
        """Same event type published for different projects routes to the correct subscriber."""
        b = SSEBroadcaster()
        queue_1 = _subscribe_and_get_queue(b, project_id="tenant-1")
        queue_2 = _subscribe_and_get_queue(b, project_id="tenant-2")

        b.publish("span:new", {"project_id": "tenant-1", "cost": 0.01})
        b.publish("span:new", {"project_id": "tenant-2", "cost": 0.05})

        await asyncio.sleep(0)

        assert queue_1.qsize() == 1
        assert queue_2.qsize() == 1

        msg_1 = queue_1.get_nowait()
        msg_2 = queue_2.get_nowait()

        assert "0.01" in msg_1
        assert "0.05" in msg_2

    async def test_filtered_event_does_not_pollute_unrelated_subscriber_queue(self) -> None:
        """An event for project-z must not appear in project-x's queue."""
        b = SSEBroadcaster()
        queue_x = _subscribe_and_get_queue(b, project_id="project-x")
        queue_z = _subscribe_and_get_queue(b, project_id="project-z")

        b.publish("span:new", {"project_id": "project-x", "v": 1})
        # Do NOT publish a project-z event

        await asyncio.sleep(0)

        assert queue_x.qsize() == 1  # got its own event
        assert queue_z.empty()       # got nothing

    async def test_admin_subscriber_count_correct_after_filtered_publish(self) -> None:
        """Client count reflects actual connected clients, not filtered events."""
        b = SSEBroadcaster()
        gen_admin = b.subscribe(project_id=None)
        gen_proj = b.subscribe(project_id="project-a")
        await _next(gen_admin)
        await _next(gen_proj)

        assert b.client_count == 2

        b.publish("span:new", {"project_id": "project-b"})  # filtered for gen_proj

        await asyncio.sleep(0)
        # Still 2 connected — filtering doesn't disconnect subscribers
        assert b.client_count == 2

        await gen_admin.aclose()
        await gen_proj.aclose()
