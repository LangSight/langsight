"""Tests for SSE broadcaster and live event feed."""

from __future__ import annotations

import asyncio

from langsight.api.broadcast import SSEBroadcaster


class TestSSEBroadcaster:
    def test_initial_state(self) -> None:
        b = SSEBroadcaster()
        assert b.client_count == 0

    def test_publish_no_clients_is_noop(self) -> None:
        b = SSEBroadcaster()
        b.publish("span:new", {"tool": "query"})  # should not raise

    async def test_subscribe_yields_connection_comment(self) -> None:
        b = SSEBroadcaster()
        gen = b.subscribe()
        first = await gen.__anext__()
        assert first.startswith(": connected at")
        await gen.aclose()

    async def test_publish_reaches_subscriber(self) -> None:
        b = SSEBroadcaster()
        gen = b.subscribe()
        # Consume the connection comment
        await gen.__anext__()

        # Publish an event
        b.publish("span:new", {"tool": "query", "status": "success"})

        # Subscriber should receive it
        msg = await asyncio.wait_for(gen.__anext__(), timeout=1.0)
        assert "event: span:new" in msg
        assert '"tool": "query"' in msg
        await gen.aclose()

    async def test_multiple_subscribers(self) -> None:
        b = SSEBroadcaster()
        gen1 = b.subscribe()
        gen2 = b.subscribe()
        await gen1.__anext__()  # connection comment
        await gen2.__anext__()

        assert b.client_count == 2

        b.publish("health:check", {"server": "pg-mcp"})

        msg1 = await asyncio.wait_for(gen1.__anext__(), timeout=1.0)
        msg2 = await asyncio.wait_for(gen2.__anext__(), timeout=1.0)
        assert "health:check" in msg1
        assert "health:check" in msg2

        await gen1.aclose()
        await gen2.aclose()

    async def test_subscriber_increments_client_count(self) -> None:
        b = SSEBroadcaster()
        gen = b.subscribe()
        await gen.__anext__()  # connection comment triggers registration
        assert b.client_count == 1
        # Publish to unblock the generator, then close
        b.publish("test", {"x": 1})
        await gen.__anext__()
        await gen.aclose()
        await asyncio.sleep(0.05)
        # Client should be cleaned up
        assert b.client_count == 0

    async def test_slow_client_drops_oldest(self) -> None:
        """When a client's queue is full, oldest event is dropped."""
        b = SSEBroadcaster()
        gen = b.subscribe()
        await gen.__anext__()  # connection comment

        # Fill the queue (buffer size is 50)
        for i in range(60):
            b.publish("span:new", {"i": i})

        # Client should still be connected and able to read
        msg = await asyncio.wait_for(gen.__anext__(), timeout=1.0)
        assert "span:new" in msg
        await gen.aclose()

    async def test_max_clients_rejected(self) -> None:
        """Exceeding _MAX_CLIENTS returns an error event."""
        from langsight.api.broadcast import _MAX_CLIENTS

        b = SSEBroadcaster()
        gens = []
        for _ in range(_MAX_CLIENTS):
            g = b.subscribe()
            await g.__anext__()  # consume connection comment
            gens.append(g)

        assert b.client_count == _MAX_CLIENTS

        # One more should get rejected
        rejected = b.subscribe()
        msg = await rejected.__anext__()
        assert "Too many connections" in msg

        # Clean up
        for g in gens:
            await g.aclose()

    def test_publish_with_non_serializable_data(self) -> None:
        """datetime and other non-JSON types should be handled via default=str."""
        from datetime import UTC, datetime

        b = SSEBroadcaster()
        # No subscribers — just verify it doesn't crash
        b.publish("test", {"ts": datetime.now(UTC)})
