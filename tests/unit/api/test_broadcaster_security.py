"""
Adversarial security tests for SSEBroadcaster project isolation.

The broadcaster delivers real-time span and health events to dashboard clients
via Server-Sent Events.  Because all tenants share one in-process broadcaster
instance, project isolation must be enforced at the fan-out layer.

Invariants proven here:

  1. Project isolation: a subscriber for project A NEVER receives an event
     published with project_id="B".  This is the primary multi-tenant data
     leak risk for the SSE stream.

  2. Admin subscriber (project_id=None) receives ALL events, including
     project-specific ones.  This is the intended behaviour — admins see
     everything.

  3. Cross-subscriber non-interference: publishing project-A events to a
     multi-subscriber broadcaster does not cause project-B subscribers to
     see them, even with many concurrent subscribers registered.

  4. Events with no project_id (empty string "" or absent key) are treated
     as global and delivered to all subscribers, including project-scoped
     ones.  This preserves backward compatibility with pre-tagging events.

Design note on timeout strategy
--------------------------------
asyncio.wait_for cancels the generator's __anext__ coroutine on timeout.
When the cancel propagates into SSEBroadcaster's inner queue.get() wait,
the generator's finally block runs and removes the client — effectively
closing the generator.  To avoid this fragility, "nothing was delivered"
checks use a sentinel pattern:

  1. Publish the foreign event that must be blocked.
  2. Publish a sentinel event for the correct project.
  3. Assert the FIRST message received is the sentinel.

This proves the foreign event was skipped (the sentinel would not be first
if the foreign event had been delivered), without relying on timeouts.

All tests run offline (no network, no DB, no Docker).
"""
from __future__ import annotations

import asyncio

import pytest

from langsight.api.broadcast import SSEBroadcaster

pytestmark = [pytest.mark.unit, pytest.mark.security]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _consume_connection_comment(gen) -> None:
    """Discard the initial ': connected at ...' comment from a subscriber."""
    first = await gen.__anext__()
    assert first.startswith(": connected at"), f"Unexpected first message: {first!r}"


async def _next_event(gen, timeout: float = 1.0) -> str:  # noqa: ASYNC109
    """Return the next event from gen, failing the test if nothing arrives."""
    return await asyncio.wait_for(gen.__anext__(), timeout=timeout)


# ===========================================================================
# 1. Project A subscriber does not receive project B events
# ===========================================================================

class TestProjectASubscriberDoesNotReceiveProjectBEvents:
    """Invariant: publishing an event with project_id='B' must deliver 0 messages
    to a subscriber registered with project_id='A'.

    Verified using the sentinel pattern: publish a blocked foreign event,
    then immediately publish a sentinel for project-a.  The first message
    received must be the sentinel — proving the foreign event was never queued.
    """

    async def test_project_scoped_subscriber_ignores_foreign_event(self) -> None:
        """Core isolation invariant: project-b event must not appear in project-a queue."""
        b = SSEBroadcaster()
        gen_a = b.subscribe(project_id="project-a")
        await _consume_connection_comment(gen_a)

        # Publish a project-b event (must be blocked) then a sentinel for project-a
        b.publish("span:new", {"tool": "foreign-tool", "project_id": "project-b"})
        b.publish("span:new", {"tool": "sentinel", "project_id": "project-a"})

        msg = await _next_event(gen_a)
        assert "foreign-tool" not in msg, (
            f"project-a received a foreign project-b event before its own: {msg!r}"
        )
        assert "sentinel" in msg, (
            f"project-a did not receive the sentinel (first message was: {msg!r})"
        )

        await gen_a.aclose()

    async def test_multiple_project_a_subscribers_all_ignore_project_b_event(self) -> None:
        """All project-A subscribers must be isolated from project-B events."""
        b = SSEBroadcaster()
        gens = [b.subscribe(project_id="project-a") for _ in range(3)]
        for g in gens:
            await _consume_connection_comment(g)

        # Foreign event (blocked) then sentinel (delivered)
        b.publish("span:new", {"tool": "foreign", "project_id": "project-b"})
        b.publish("span:new", {"tool": "sentinel", "project_id": "project-a"})

        for g in gens:
            msg = await _next_event(g)
            assert "foreign" not in msg, (
                f"A project-a subscriber received foreign project-b content: {msg!r}"
            )
            assert "sentinel" in msg

        for g in gens:
            await g.aclose()

    async def test_project_subscriber_only_receives_own_project_events(self) -> None:
        """Publish two events — one foreign and one own.  Own must arrive first."""
        b = SSEBroadcaster()
        gen_a = b.subscribe(project_id="project-a")
        await _consume_connection_comment(gen_a)

        b.publish("span:new", {"tool": "search", "project_id": "project-b"})
        b.publish("span:new", {"tool": "query", "project_id": "project-a"})

        msg = await _next_event(gen_a)
        assert "query" in msg, f"Expected project-a event first, got: {msg!r}"
        assert "search" not in msg, f"Foreign project-b data leaked into: {msg!r}"

        await gen_a.aclose()

    async def test_simultaneous_project_a_and_b_subscribers_are_isolated(self) -> None:
        """project-a and project-b subscribers must each receive only their own events."""
        b = SSEBroadcaster()
        gen_a = b.subscribe(project_id="project-a")
        gen_b = b.subscribe(project_id="project-b")
        await _consume_connection_comment(gen_a)
        await _consume_connection_comment(gen_b)

        b.publish("span:new", {"tool": "tool-a-only", "project_id": "project-a"})
        b.publish("span:new", {"tool": "tool-b-only", "project_id": "project-b"})

        msg_a = await _next_event(gen_a)
        msg_b = await _next_event(gen_b)

        assert "tool-a-only" in msg_a, f"project-a missed its own event: {msg_a!r}"
        assert "tool-b-only" not in msg_a, f"project-b event leaked to project-a: {msg_a!r}"

        assert "tool-b-only" in msg_b, f"project-b missed its own event: {msg_b!r}"
        assert "tool-a-only" not in msg_b, f"project-a event leaked to project-b: {msg_b!r}"

        await gen_a.aclose()
        await gen_b.aclose()


# ===========================================================================
# 2. Admin subscriber (project_id=None) receives ALL events
# ===========================================================================

class TestAdminSubscriberReceivesAllEvents:
    """Invariant: an admin subscriber registered with project_id=None must
    receive events for every project, including project-scoped ones."""

    async def test_admin_subscriber_receives_project_a_event(self) -> None:
        """Admin must see project-specific events published with project_id='A'."""
        b = SSEBroadcaster()
        gen_admin = b.subscribe(project_id=None)
        await _consume_connection_comment(gen_admin)

        b.publish("span:new", {"tool": "query", "project_id": "project-a"})

        msg = await _next_event(gen_admin)
        assert "project-a" in msg, (
            f"Admin subscriber did not receive a project-a event: {msg!r}"
        )

        await gen_admin.aclose()

    async def test_admin_subscriber_receives_project_b_event(self) -> None:
        """Admin must see events from all tenants — not just one project."""
        b = SSEBroadcaster()
        gen_admin = b.subscribe(project_id=None)
        await _consume_connection_comment(gen_admin)

        b.publish("health:check", {"server": "redis", "project_id": "project-b"})

        msg = await _next_event(gen_admin)
        assert "project-b" in msg

        await gen_admin.aclose()

    async def test_admin_receives_all_events_while_project_subscribers_are_filtered(
        self,
    ) -> None:
        """Admin gets everything; project-scoped subscribers get only their own.

        This verifies isolation does not accidentally block the admin subscriber
        as a side effect of the project filter logic.
        """
        b = SSEBroadcaster()
        gen_admin = b.subscribe(project_id=None)
        gen_a = b.subscribe(project_id="project-a")
        gen_b = b.subscribe(project_id="project-b")
        await _consume_connection_comment(gen_admin)
        await _consume_connection_comment(gen_a)
        await _consume_connection_comment(gen_b)

        # Publish one event per project
        b.publish("span:new", {"project_id": "project-a", "tool": "alpha"})
        b.publish("span:new", {"project_id": "project-b", "tool": "beta"})

        # Admin receives both events
        msg_admin_1 = await _next_event(gen_admin)
        msg_admin_2 = await _next_event(gen_admin)
        admin_combined = msg_admin_1 + msg_admin_2
        assert "alpha" in admin_combined, "Admin missed project-a event"
        assert "beta" in admin_combined, "Admin missed project-b event"

        # project-a subscriber gets only alpha
        msg_a = await _next_event(gen_a)
        assert "alpha" in msg_a

        # project-b subscriber gets only beta
        msg_b = await _next_event(gen_b)
        assert "beta" in msg_b

        # Verify no cross-contamination: project-a must NOT have beta in queue.
        # Publish a sentinel for project-a to confirm only sentinel arrives next.
        b.publish("span:new", {"project_id": "project-a", "tool": "sentinel-a"})
        msg_a_next = await _next_event(gen_a)
        assert "beta" not in msg_a_next, (
            f"project-b event leaked to project-a on second read: {msg_a_next!r}"
        )
        assert "sentinel-a" in msg_a_next

        await gen_admin.aclose()
        await gen_a.aclose()
        await gen_b.aclose()


# ===========================================================================
# 3. Unscoped events must NOT reach project-scoped subscribers (security fix)
# Previously unscoped events leaked to all project subscribers. Now only admin
# (project_id=None) subscribers receive them.
# ===========================================================================

class TestGlobalEventsDeliveredToAllSubscribers:
    """Security invariant: events with no project_id must NOT be delivered to
    project-scoped subscribers. Only admin (project_id=None) subscribers receive
    unscoped events. This prevents internal events leaking across tenants."""

    async def _assert_no_event(self, gen, timeout: float = 0.05) -> None:
        try:
            await _next_event(gen, timeout=timeout)
            raise AssertionError("Expected no event but generator yielded one")
        except (TimeoutError, StopAsyncIteration):
            pass

    async def test_event_with_empty_project_id_does_not_reach_project_scoped_subscriber(
        self,
    ) -> None:
        """project_id='' is unscoped — must NOT reach a project-scoped subscriber."""
        b = SSEBroadcaster()
        gen_a = b.subscribe(project_id="project-a")
        await _consume_connection_comment(gen_a)

        b.publish("health:check", {"server": "global-mcp", "project_id": ""})

        await self._assert_no_event(gen_a)
        await gen_a.aclose()

    async def test_event_without_project_id_key_does_not_reach_project_scoped_subscriber(
        self,
    ) -> None:
        """Event data without a 'project_id' key is unscoped — must not leak."""
        b = SSEBroadcaster()
        gen_a = b.subscribe(project_id="project-a")
        await _consume_connection_comment(gen_a)

        b.publish("health:check", {"server": "legacy-mcp"})

        await self._assert_no_event(gen_a)
        await gen_a.aclose()

    async def test_event_without_project_id_key_reaches_admin_subscriber(
        self,
    ) -> None:
        """Unscoped events must still reach admin (project_id=None) subscribers."""
        b = SSEBroadcaster()
        gen_admin = b.subscribe(project_id=None)
        await _consume_connection_comment(gen_admin)

        b.publish("span:new", {"tool": "ping"})

        msg = await _next_event(gen_admin)
        assert "ping" in msg

        await gen_admin.aclose()


# ===========================================================================
# 4. Many concurrent subscribers — no cross-project bleed
# ===========================================================================

class TestConcurrentSubscriberIsolation:
    """Invariant: with N project-scoped subscribers active simultaneously,
    publishing to project-X must not reach any project-Y subscriber,
    regardless of subscriber registration order or queue state."""

    async def test_ten_project_subscribers_each_isolated(self) -> None:
        """10 subscribers for 10 different projects — each receives only its own events."""
        b = SSEBroadcaster()
        project_ids = [f"project-{i:02d}" for i in range(10)]

        gens = {pid: b.subscribe(project_id=pid) for pid in project_ids}
        for g in gens.values():
            await _consume_connection_comment(g)

        # Publish one event per project
        for pid in project_ids:
            b.publish("span:new", {"project_id": pid, "marker": f"only-for-{pid}"})

        # Each subscriber receives exactly its own event
        for pid in project_ids:
            gen = gens[pid]
            msg = await _next_event(gen)
            assert f"only-for-{pid}" in msg, (
                f"project {pid} missed its own event, got: {msg!r}"
            )
            for other_pid in project_ids:
                if other_pid != pid:
                    assert f"only-for-{other_pid}" not in msg, (
                        f"Foreign event from {other_pid} leaked to {pid}: {msg!r}"
                    )

        for g in gens.values():
            await g.aclose()

    async def test_publishing_project_b_to_broadcaster_with_only_project_a_subscribers(
        self,
    ) -> None:
        """When ALL registered subscribers belong to project-a, publishing a
        project-b event must not reach any of them.

        Verified via sentinel: publish a blocked project-b event, then a sentinel
        for project-a.  The first received message must be the sentinel.
        """
        b = SSEBroadcaster()
        gens = [b.subscribe(project_id="project-a") for _ in range(5)]
        for g in gens:
            await _consume_connection_comment(g)

        # Blocked event then sentinel
        b.publish("span:new", {"project_id": "project-b", "tool": "should-not-arrive"})
        b.publish("span:new", {"project_id": "project-a", "tool": "sentinel"})

        for g in gens:
            msg = await _next_event(g)
            assert "should-not-arrive" not in msg, (
                f"project-a subscriber received foreign project-b event: {msg!r}"
            )
            assert "sentinel" in msg

        for g in gens:
            await g.aclose()
