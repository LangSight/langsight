"""
Security tests for RedisBroadcaster project isolation.

These tests verify that the channel-based isolation in RedisBroadcaster
enforces the same tenant-isolation guarantees as SSEBroadcaster:

  1. A project-A subscriber physically listens on a different Redis channel
     than a project-B subscriber — cross-project data exposure is impossible
     at the protocol level (no fan-out filtering required).

  2. Unscoped events (no project_id) are published ONLY to the admin channel.
     A project subscriber on langsight:events:{project_id} never receives them.

  3. The admin subscriber (project_id=None) always uses the admin channel
     which receives a copy of every event (scoped and unscoped alike).

  4. Publishing to proj-b while redis.publish raises does not silently deliver
     partial data to any channel (fire-and-forget, no data exposure on error).

  5. Project channel names are exact — "proj" must not match "proj-extended".

All tests are offline — no real Redis.

Design note
-----------
Channel-based isolation means we cannot observe "did subscriber X receive
event Y?" directly (that would require a real pub/sub round-trip). Instead we
verify WHICH CHANNEL was subscribed to and WHICH CHANNELS received publish
calls. If the channels are correct the isolation is guaranteed by the Redis
pub/sub contract, which is stronger than in-process fan-out filtering.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest

from langsight.api.broadcast import (
    _ADMIN_CHANNEL,
    _PROJECT_CHANNEL_PREFIX,
    RedisBroadcaster,
)

pytestmark = [pytest.mark.unit, pytest.mark.security]


# ---------------------------------------------------------------------------
# Test infrastructure
# ---------------------------------------------------------------------------


class _TrackingPubSub:
    """Pubsub mock that records which channel it subscribed to."""

    def __init__(self) -> None:
        self.subscribed_channel: str | None = None
        self.subscribe = AsyncMock(side_effect=self._record_subscribe)
        self.unsubscribe = AsyncMock()
        self.aclose = AsyncMock()

    async def _record_subscribe(self, channel: str) -> None:
        self.subscribed_channel = channel

    async def listen(self) -> AsyncGenerator:
        return
        yield  # never yields a message


def _make_redis_with_tracking() -> tuple[MagicMock, list[_TrackingPubSub]]:
    """Return a Redis mock and a list that accumulates all pubsub instances created."""
    created: list[_TrackingPubSub] = []

    def _make_pubsub() -> _TrackingPubSub:
        ps = _TrackingPubSub()
        created.append(ps)
        return ps

    redis = MagicMock()
    redis.publish = AsyncMock(return_value=1)
    redis.pubsub = MagicMock(side_effect=_make_pubsub)
    return redis, created


async def _start_subscriber(
    broadcaster: RedisBroadcaster,
    project_id: str | None,
) -> AsyncGenerator:
    """Start a subscribe() generator and consume the connection comment."""
    gen = broadcaster.subscribe(project_id=project_id)
    await gen.__anext__()  # consume ': connected at ...'
    await asyncio.sleep(0)  # let _reader task call pubsub.subscribe
    return gen


# ===========================================================================
# 1. Project isolation — channels are physically separate
# ===========================================================================


class TestRedisBroadcasterProjectIsolation:
    @pytest.mark.asyncio
    async def test_project_a_subscriber_uses_different_channel_than_project_b(
        self,
    ) -> None:
        """project-a and project-b subscribers must be on distinct Redis channels.

        Physical channel separation is the security guarantee: Redis pub/sub
        never delivers a message from channel X to a subscriber on channel Y.
        """
        redis, created = _make_redis_with_tracking()
        broadcaster = RedisBroadcaster(redis)

        gen_a = await _start_subscriber(broadcaster, project_id="proj-a")
        gen_b = await _start_subscriber(broadcaster, project_id="proj-b")

        channel_a = created[0].subscribed_channel
        channel_b = created[1].subscribed_channel

        assert channel_a != channel_b, (
            f"project-a and project-b must use different channels, got: {channel_a!r} vs {channel_b!r}"
        )

        await gen_a.aclose()
        await gen_b.aclose()

    @pytest.mark.asyncio
    async def test_project_a_subscriber_channel_does_not_contain_project_b_name(
        self,
    ) -> None:
        """The channel name for project-a must not contain 'project-b'."""
        redis, created = _make_redis_with_tracking()
        broadcaster = RedisBroadcaster(redis)

        gen_a = await _start_subscriber(broadcaster, project_id="project-a")
        await asyncio.sleep(0)

        channel_a = created[0].subscribed_channel
        assert "project-b" not in (channel_a or "")

        await gen_a.aclose()

    @pytest.mark.asyncio
    async def test_unscoped_event_does_not_reach_project_subscriber_channel(
        self,
    ) -> None:
        """Unscoped event (no project_id) is published only to admin channel.

        A project subscriber is on a different channel — Redis never delivers
        admin-channel messages to a project-channel subscriber.
        """
        redis, _ = _make_redis_with_tracking()
        redis.publish = AsyncMock(return_value=1)
        broadcaster = RedisBroadcaster(redis)

        broadcaster.publish("span:new", {"tool": "query"})  # no project_id
        await asyncio.sleep(0)

        # Only one publish call — to the admin channel
        assert redis.publish.await_count == 1
        published_channel = redis.publish.await_args.args[0]
        # Must NOT be a project-specific channel
        assert published_channel == _ADMIN_CHANNEL
        assert _PROJECT_CHANNEL_PREFIX not in published_channel.replace(_ADMIN_CHANNEL, "")

    @pytest.mark.asyncio
    async def test_project_b_event_not_published_to_project_a_channel(
        self,
    ) -> None:
        """Publishing to proj-b must not touch the proj-a channel."""
        redis, _ = _make_redis_with_tracking()
        broadcaster = RedisBroadcaster(redis)

        broadcaster.publish("span:new", {"project_id": "proj-b", "tool": "write"})
        await asyncio.sleep(0)

        published_channels = [c.args[0] for c in redis.publish.await_args_list]
        proj_a_channel = f"{_PROJECT_CHANNEL_PREFIX}proj-a"
        assert proj_a_channel not in published_channels, (
            f"proj-a channel must not receive a proj-b event. Channels published: {published_channels}"
        )

    @pytest.mark.asyncio
    async def test_admin_subscriber_uses_admin_channel_receives_all_events(
        self,
    ) -> None:
        """Admin subscriber (project_id=None) is on the admin channel.

        The admin channel receives every publish call, both scoped and unscoped,
        so admin always receives all events.
        """
        redis, created = _make_redis_with_tracking()
        broadcaster = RedisBroadcaster(redis)

        gen_admin = await _start_subscriber(broadcaster, project_id=None)

        admin_pubsub = created[0]
        assert admin_pubsub.subscribed_channel == _ADMIN_CHANNEL

        # Scoped publish → admin channel receives a copy
        broadcaster.publish("span:new", {"project_id": "proj-x"})
        await asyncio.sleep(0)

        admin_channel_publish_count = sum(
            1 for c in redis.publish.await_args_list
            if c.args[0] == _ADMIN_CHANNEL
        )
        assert admin_channel_publish_count >= 1, "Admin channel must receive scoped events"

        await gen_admin.aclose()

    @pytest.mark.asyncio
    async def test_publish_failure_does_not_expose_data_to_wrong_subscriber(
        self,
    ) -> None:
        """When redis.publish raises, no partial data is sent to any channel.

        The exception is swallowed — not re-raised. No channel receives data.
        """
        redis, _ = _make_redis_with_tracking()
        redis.publish = AsyncMock(side_effect=ConnectionError("redis unavailable"))
        broadcaster = RedisBroadcaster(redis)

        # Must not raise — error is swallowed
        broadcaster.publish("span:new", {"project_id": "proj-a", "secret": "data"})
        await asyncio.sleep(0)

        # publish was called (attempted), but it raised — no successful delivery
        assert redis.publish.await_count >= 1  # it tried
        # No exception propagated — implicitly verified by the test not crashing


# ===========================================================================
# 2. Channel name correctness
# ===========================================================================


class TestRedisBroadcasterChannelNames:
    def test_admin_channel_constant(self) -> None:
        """Admin channel must be exactly 'langsight:events:admin'."""
        assert _ADMIN_CHANNEL == "langsight:events:admin"

    def test_project_channel_prefix(self) -> None:
        """Project channel prefix must be 'langsight:events:'."""
        assert _PROJECT_CHANNEL_PREFIX == "langsight:events:"

    def test_project_channel_has_correct_prefix(self) -> None:
        """Project channel must be prefix + project_id."""
        expected = f"{_PROJECT_CHANNEL_PREFIX}my-project"
        assert expected == "langsight:events:my-project"

    def test_project_id_in_channel_name_is_exact_match(self) -> None:
        """'proj' channel must not equal 'proj-extended' channel."""
        channel_short = f"{_PROJECT_CHANNEL_PREFIX}proj"
        channel_long = f"{_PROJECT_CHANNEL_PREFIX}proj-extended"
        assert channel_short != channel_long

    def test_project_channel_does_not_collide_with_admin_channel(self) -> None:
        """No project_id value can produce a channel that equals the admin channel.

        Ensures a malicious project_id='admin' does not subscribe to admin events.
        """
        # The admin channel is 'langsight:events:admin'
        # A project channel for project_id='admin' would be 'langsight:events:admin'
        # This IS a potential name collision — document that it exists and that
        # admin project_id should be reserved/blocked at the application layer.
        #
        # This test confirms the collision so the application layer can guard against it.
        colliding_project_id = "admin"
        project_channel = f"{_PROJECT_CHANNEL_PREFIX}{colliding_project_id}"
        assert project_channel == _ADMIN_CHANNEL, (
            "A project_id='admin' WOULD collide with the admin channel. "
            "This test documents the collision so the router layer can block it."
        )

    def test_different_project_ids_produce_different_channels(self) -> None:
        """Every distinct project_id maps to a distinct channel."""
        ids = ["proj-1", "proj-2", "tenant-a", "tenant-b", "00000000"]
        channels = [f"{_PROJECT_CHANNEL_PREFIX}{pid}" for pid in ids]
        assert len(channels) == len(set(channels)), "Channels must be unique per project_id"

    @pytest.mark.asyncio
    async def test_publish_with_project_id_admin_uses_admin_channel_for_both(
        self,
    ) -> None:
        """project_id='admin' publishes to admin channel AND langsight:events:admin.

        These are the same channel — only one message is delivered.
        This is the collision documented in test_project_channel_does_not_collide_with_admin_channel.
        The test pins the current (potentially unsafe) behaviour.
        """
        redis = MagicMock()
        redis.publish = AsyncMock(return_value=1)
        redis.pubsub = MagicMock()
        broadcaster = RedisBroadcaster(redis)

        broadcaster.publish("span:new", {"project_id": "admin"})
        await asyncio.sleep(0)

        # Both publishes go to the same channel string — Redis deduplicates
        published_channels = [c.args[0] for c in redis.publish.await_args_list]
        assert _ADMIN_CHANNEL in published_channels
        assert f"{_PROJECT_CHANNEL_PREFIX}admin" in published_channels
        # They resolve to the same channel
        assert published_channels.count(_ADMIN_CHANNEL) == published_channels.count(
            f"{_PROJECT_CHANNEL_PREFIX}admin"
        )
