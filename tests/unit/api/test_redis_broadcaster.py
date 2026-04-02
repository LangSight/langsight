"""
Unit tests for langsight.api.broadcast.RedisBroadcaster.

Covers:
  - publish: pushes to admin + project channels when project_id is set
  - publish: pushes only to admin channel when project_id is absent or empty
  - publish: never raises even when redis.publish fails
  - subscribe: uses the correct Redis channel for admin vs. project subscribers
  - client_count: increments on subscribe, decrements after generator exits

All tests use AsyncMock / MagicMock — no real Redis required.

The sentinel-pattern from test_broadcaster_security.py is adapted for the
Redis layer: tests verify which channels were subscribed to and which channels
received publish calls.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from langsight.api.broadcast import (
    RedisBroadcaster,
    _ADMIN_CHANNEL,
    _PROJECT_CHANNEL_PREFIX,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_redis_mock() -> MagicMock:
    """Return a mock Redis client with a pubsub() method."""
    redis = MagicMock()
    redis.publish = AsyncMock(return_value=1)
    # pubsub() returns a new mock each call (one per subscriber)
    redis.pubsub = MagicMock(side_effect=lambda: _make_pubsub_mock())
    return redis


def _make_pubsub_mock() -> MagicMock:
    """Return a mock pubsub object that never yields any messages."""
    pubsub = MagicMock()
    pubsub.subscribe = AsyncMock()
    pubsub.unsubscribe = AsyncMock()
    pubsub.aclose = AsyncMock()

    # listen() yields nothing by default (no messages)
    async def _empty_listen() -> AsyncGenerator:
        return
        yield  # make it an async generator

    pubsub.listen = _empty_listen
    return pubsub


async def _collect_first_yield(broadcaster: RedisBroadcaster, project_id: str | None) -> str:
    """Consume only the connection comment from subscribe(), then cancel."""
    gen = broadcaster.subscribe(project_id=project_id)
    first = await gen.__anext__()
    await gen.aclose()
    return first


# ===========================================================================
# Publish — channel routing
# ===========================================================================


class TestRedisBroadcasterPublish:
    @pytest.mark.asyncio
    async def test_publish_with_project_id_pushes_to_admin_and_project_channel(self) -> None:
        """publish(project_id='x') must push to admin AND project-specific channel."""
        redis = _make_redis_mock()
        broadcaster = RedisBroadcaster(redis)

        broadcaster.publish("span:new", {"project_id": "proj-x", "tool": "query"})
        # Allow ensure_future task to run
        await asyncio.sleep(0)

        # Must have published exactly twice
        assert redis.publish.await_count == 2
        calls = redis.publish.await_args_list
        channels = [call.args[0] for call in calls]

        assert _ADMIN_CHANNEL in channels
        assert f"{_PROJECT_CHANNEL_PREFIX}proj-x" in channels

    @pytest.mark.asyncio
    async def test_publish_without_project_id_pushes_only_to_admin_channel(self) -> None:
        """publish() with no project_id in data must only push to the admin channel."""
        redis = _make_redis_mock()
        broadcaster = RedisBroadcaster(redis)

        broadcaster.publish("health:check", {"server": "postgres-mcp"})
        await asyncio.sleep(0)

        assert redis.publish.await_count == 1
        assert redis.publish.await_args.args[0] == _ADMIN_CHANNEL

    @pytest.mark.asyncio
    async def test_publish_with_empty_project_id_pushes_only_to_admin_channel(self) -> None:
        """project_id='' is treated as unscoped — only admin channel receives it."""
        redis = _make_redis_mock()
        broadcaster = RedisBroadcaster(redis)

        broadcaster.publish("span:new", {"project_id": "", "tool": "list"})
        await asyncio.sleep(0)

        assert redis.publish.await_count == 1
        assert redis.publish.await_args.args[0] == _ADMIN_CHANNEL

    @pytest.mark.asyncio
    async def test_publish_does_not_raise_when_redis_unavailable(self) -> None:
        """If redis.publish raises, _publish_async must swallow it (fire-and-forget)."""
        redis = _make_redis_mock()
        redis.publish = AsyncMock(side_effect=ConnectionError("redis down"))
        broadcaster = RedisBroadcaster(redis)

        # Must not raise — the error is caught inside _publish_async
        broadcaster.publish("span:new", {"project_id": "proj-a"})
        await asyncio.sleep(0)  # let the background task run

    @pytest.mark.asyncio
    async def test_payload_is_valid_json_with_event_type_and_data(self) -> None:
        """The published payload must be valid JSON containing event_type and data keys."""
        redis = _make_redis_mock()
        broadcaster = RedisBroadcaster(redis)

        broadcaster.publish("span:new", {"project_id": "proj-y", "cost": 0.05})
        await asyncio.sleep(0)

        assert redis.publish.await_count >= 1
        # Grab any publish call and verify the payload format
        raw_payload = redis.publish.await_args_list[0].args[1]
        parsed = json.loads(raw_payload)
        assert parsed["event_type"] == "span:new"
        assert parsed["data"]["cost"] == 0.05

    def test_client_count_starts_at_zero(self) -> None:
        """A freshly constructed RedisBroadcaster has zero local clients."""
        redis = _make_redis_mock()
        broadcaster = RedisBroadcaster(redis)
        assert broadcaster.client_count == 0


# ===========================================================================
# Subscribe — correct channel selection
# ===========================================================================


class TestRedisBroadcasterSubscribeChannels:
    @pytest.mark.asyncio
    async def test_admin_subscriber_uses_admin_channel(self) -> None:
        """subscribe(None) must subscribe to the admin channel."""
        subscribed_channels: list[str] = []

        def _make_tracking_pubsub() -> MagicMock:
            pubsub = MagicMock()

            async def _subscribe(channel: str) -> None:
                subscribed_channels.append(channel)

            pubsub.subscribe = AsyncMock(side_effect=_subscribe)
            pubsub.unsubscribe = AsyncMock()
            pubsub.aclose = AsyncMock()

            async def _empty_listen() -> AsyncGenerator:
                return
                yield

            pubsub.listen = _empty_listen
            return pubsub

        redis = _make_redis_mock()
        redis.pubsub = MagicMock(side_effect=_make_tracking_pubsub)
        broadcaster = RedisBroadcaster(redis)

        gen = broadcaster.subscribe(project_id=None)
        await gen.__anext__()  # consume connection comment to start _reader task
        await asyncio.sleep(0)  # let _reader call pubsub.subscribe
        await gen.aclose()

        assert _ADMIN_CHANNEL in subscribed_channels

    @pytest.mark.asyncio
    async def test_project_subscriber_uses_project_channel(self) -> None:
        """subscribe('proj-a') must subscribe to langsight:events:proj-a."""
        subscribed_channels: list[str] = []

        def _make_tracking_pubsub() -> MagicMock:
            pubsub = MagicMock()

            async def _subscribe(channel: str) -> None:
                subscribed_channels.append(channel)

            pubsub.subscribe = AsyncMock(side_effect=_subscribe)
            pubsub.unsubscribe = AsyncMock()
            pubsub.aclose = AsyncMock()

            async def _empty_listen() -> AsyncGenerator:
                return
                yield

            pubsub.listen = _empty_listen
            return pubsub

        redis = _make_redis_mock()
        redis.pubsub = MagicMock(side_effect=_make_tracking_pubsub)
        broadcaster = RedisBroadcaster(redis)

        gen = broadcaster.subscribe(project_id="proj-a")
        await gen.__anext__()
        await asyncio.sleep(0)
        await gen.aclose()

        assert f"{_PROJECT_CHANNEL_PREFIX}proj-a" in subscribed_channels
        assert _ADMIN_CHANNEL not in subscribed_channels

    @pytest.mark.asyncio
    async def test_different_projects_use_different_channels(self) -> None:
        """Two project subscribers must land on two distinct channels."""
        subscribed_channels: list[str] = []

        def _make_tracking_pubsub() -> MagicMock:
            pubsub = MagicMock()

            async def _subscribe(channel: str) -> None:
                subscribed_channels.append(channel)

            pubsub.subscribe = AsyncMock(side_effect=_subscribe)
            pubsub.unsubscribe = AsyncMock()
            pubsub.aclose = AsyncMock()

            async def _empty_listen() -> AsyncGenerator:
                return
                yield

            pubsub.listen = _empty_listen
            return pubsub

        redis = _make_redis_mock()
        redis.pubsub = MagicMock(side_effect=_make_tracking_pubsub)
        broadcaster = RedisBroadcaster(redis)

        gen_a = broadcaster.subscribe(project_id="proj-a")
        gen_b = broadcaster.subscribe(project_id="proj-b")
        await gen_a.__anext__()
        await gen_b.__anext__()
        await asyncio.sleep(0)
        await gen_a.aclose()
        await gen_b.aclose()

        assert f"{_PROJECT_CHANNEL_PREFIX}proj-a" in subscribed_channels
        assert f"{_PROJECT_CHANNEL_PREFIX}proj-b" in subscribed_channels
        # The two channels are distinct
        assert f"{_PROJECT_CHANNEL_PREFIX}proj-a" != f"{_PROJECT_CHANNEL_PREFIX}proj-b"


# ===========================================================================
# Client count
# ===========================================================================


class TestRedisBroadcasterClientCount:
    @pytest.mark.asyncio
    async def test_client_count_increments_on_subscribe(self) -> None:
        """client_count reflects the number of active local subscribers."""
        redis = _make_redis_mock()
        broadcaster = RedisBroadcaster(redis)

        assert broadcaster.client_count == 0

        gen = broadcaster.subscribe(project_id="proj-a")
        await gen.__anext__()  # consume connection comment

        assert broadcaster.client_count == 1

        await gen.aclose()

    @pytest.mark.asyncio
    async def test_client_count_decrements_on_unsubscribe(self) -> None:
        """When the subscriber generator is closed, client_count decrements."""
        redis = _make_redis_mock()
        broadcaster = RedisBroadcaster(redis)

        gen = broadcaster.subscribe(project_id="proj-a")
        await gen.__anext__()
        assert broadcaster.client_count == 1

        await gen.aclose()
        # After close, finally block in subscribe() runs and decrements
        assert broadcaster.client_count == 0

    @pytest.mark.asyncio
    async def test_client_count_tracks_multiple_subscribers(self) -> None:
        """Multiple concurrent subscribers are counted individually."""
        redis = _make_redis_mock()
        broadcaster = RedisBroadcaster(redis)

        gen_a = broadcaster.subscribe(project_id="proj-a")
        gen_b = broadcaster.subscribe(project_id="proj-b")
        gen_c = broadcaster.subscribe(project_id=None)

        await gen_a.__anext__()
        await gen_b.__anext__()
        await gen_c.__anext__()

        assert broadcaster.client_count == 3

        await gen_a.aclose()
        assert broadcaster.client_count == 2

        await gen_b.aclose()
        await gen_c.aclose()
        assert broadcaster.client_count == 0
