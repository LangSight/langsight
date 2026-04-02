"""
Integration tests for RedisBroadcaster requiring a live Redis instance.

These tests verify that two independently constructed RedisBroadcaster
instances sharing a single Redis server correctly route events through
the pub/sub channel layer — something that cannot be proven with mocks.

Skipped automatically when TEST_REDIS_URL is not reachable.
Start Redis with:
    docker compose --profile redis up -d

Environment variables:
    TEST_REDIS_URL   — default: redis://localhost:6379

Isolation guarantees proven here (beyond what unit tests can cover):
  1. An event published on broadcaster_a is received by broadcaster_b's subscriber.
  2. A project-a event published on broadcaster_a is NOT received by broadcaster_b's
     project-b subscriber (different channel).
  3. An admin subscriber on broadcaster_b receives cross-instance scoped events.

These invariants require real Redis pub/sub to exercise the full message path.
"""

from __future__ import annotations

import asyncio
import os
import socket
from urllib.parse import urlparse

import pytest

pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# Redis availability fixture
# ---------------------------------------------------------------------------

_DEFAULT_REDIS_URL = "redis://localhost:6379"


@pytest.fixture(scope="session")
def redis_url() -> str:
    return os.environ.get("TEST_REDIS_URL", _DEFAULT_REDIS_URL)


@pytest.fixture(scope="session", autouse=False)
def require_redis(redis_url: str) -> None:
    """Skip the entire module when Redis is not reachable.

    Uses a plain TCP socket check — no event loop required.
    """
    parsed = urlparse(redis_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 6379
    try:
        with socket.create_connection((host, port), timeout=2):
            return  # Redis is up
    except OSError:
        pytest.skip(
            f"Redis not available at {redis_url}. "
            "Start with: docker compose --profile redis up -d\n"
            "Or set TEST_REDIS_URL to point at a running instance."
        )


# ---------------------------------------------------------------------------
# Broadcaster factory
# ---------------------------------------------------------------------------


async def _make_broadcaster(redis_url: str):
    """Create a RedisBroadcaster backed by a fresh aioredis client."""
    import redis.asyncio as aioredis

    from langsight.api.broadcast import RedisBroadcaster

    client = aioredis.from_url(redis_url, decode_responses=True)
    await client.ping()
    return RedisBroadcaster(client), client


# ---------------------------------------------------------------------------
# Helper: collect N messages from a subscribe() generator with a timeout
# ---------------------------------------------------------------------------


async def _collect(gen, n: int, timeout: float = 3.0) -> list[str]:
    """Collect n non-comment messages from the SSE generator."""
    results: list[str] = []
    deadline = asyncio.get_event_loop().time() + timeout
    async for raw in gen:
        if raw.startswith(":"):
            continue  # skip keepalive and connection comments
        results.append(raw)
        if len(results) >= n:
            break
        if asyncio.get_event_loop().time() > deadline:
            break
    return results


# ===========================================================================
# Cross-instance event delivery
# ===========================================================================


class TestRedisBroadcasterCrossInstance:
    @pytest.mark.asyncio
    async def test_event_published_on_instance_a_received_by_instance_b(
        self, require_redis: None, redis_url: str
    ) -> None:
        """Event published via broadcaster_a reaches broadcaster_b's project subscriber."""
        broadcaster_a, client_a = await _make_broadcaster(redis_url)
        broadcaster_b, client_b = await _make_broadcaster(redis_url)

        project_id = "integ-test-proj-cross"

        # Subscribe on broadcaster_b
        gen_b = broadcaster_b.subscribe(project_id=project_id)
        # Consume connection comment and give _reader task time to subscribe
        await gen_b.__anext__()
        await asyncio.sleep(0.1)  # allow pubsub.subscribe to complete

        # Publish on broadcaster_a
        broadcaster_a.publish("span:new", {"project_id": project_id, "marker": "cross-instance"})
        await asyncio.sleep(0.1)  # allow publish to reach Redis

        # Collect from broadcaster_b
        try:
            messages = await asyncio.wait_for(_collect(gen_b, n=1, timeout=3.0), timeout=5.0)
        finally:
            await gen_b.aclose()
            await client_a.aclose()
            await client_b.aclose()

        assert len(messages) == 1, f"Expected 1 message across Redis, got: {messages}"
        assert "cross-instance" in messages[0]
        assert "span:new" in messages[0]

    @pytest.mark.asyncio
    async def test_project_isolation_across_instances(
        self, require_redis: None, redis_url: str
    ) -> None:
        """broadcaster_a publishes to proj-a; broadcaster_b's proj-b subscriber must not receive it."""
        broadcaster_a, client_a = await _make_broadcaster(redis_url)
        broadcaster_b, client_b = await _make_broadcaster(redis_url)

        # Subscribe broadcaster_b to proj-b
        gen_b = broadcaster_b.subscribe(project_id="integ-test-proj-b")
        await gen_b.__anext__()
        await asyncio.sleep(0.1)

        # Publish to proj-a on broadcaster_a
        broadcaster_a.publish("span:new", {"project_id": "integ-test-proj-a", "secret": "proj-a-data"})

        # Also publish sentinel to proj-b to confirm the subscriber is alive
        broadcaster_a.publish("span:new", {"project_id": "integ-test-proj-b", "marker": "sentinel"})
        await asyncio.sleep(0.1)

        try:
            messages = await asyncio.wait_for(_collect(gen_b, n=1, timeout=3.0), timeout=5.0)
        finally:
            await gen_b.aclose()
            await client_a.aclose()
            await client_b.aclose()

        # The sentinel for proj-b must be the first (and only) message received
        assert len(messages) >= 1
        assert "sentinel" in messages[0], (
            f"First message must be the sentinel, not a proj-a event. Got: {messages[0]!r}"
        )
        assert "proj-a-data" not in messages[0], (
            f"proj-b subscriber must not receive proj-a events. Got: {messages[0]!r}"
        )

    @pytest.mark.asyncio
    async def test_admin_subscriber_receives_cross_instance_events(
        self, require_redis: None, redis_url: str
    ) -> None:
        """Admin subscriber on broadcaster_b receives scoped events from broadcaster_a."""
        broadcaster_a, client_a = await _make_broadcaster(redis_url)
        broadcaster_b, client_b = await _make_broadcaster(redis_url)

        # Admin subscriber on broadcaster_b
        gen_admin = broadcaster_b.subscribe(project_id=None)
        await gen_admin.__anext__()
        await asyncio.sleep(0.1)

        # Scoped publish on broadcaster_a → must reach admin on broadcaster_b
        broadcaster_a.publish("span:new", {"project_id": "integ-test-proj-admin", "marker": "admin-cross"})
        await asyncio.sleep(0.1)

        try:
            messages = await asyncio.wait_for(_collect(gen_admin, n=1, timeout=3.0), timeout=5.0)
        finally:
            await gen_admin.aclose()
            await client_a.aclose()
            await client_b.aclose()

        assert len(messages) >= 1, "Admin subscriber must receive scoped events from another instance"
        assert "admin-cross" in messages[0], (
            f"Expected marker in admin message. Got: {messages[0]!r}"
        )
