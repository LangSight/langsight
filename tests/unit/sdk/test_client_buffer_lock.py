"""
Unit tests for the asyncio.Lock in LangSightClient buffer operations.

Covers:
- Concurrent send_span calls do not lose spans (lock protects append)
- Concurrent send_span + flush do not lose spans (lock prevents read/clear race)
- Concurrent flush calls do not double-send spans
- Buffer overflow cap is respected under concurrent load
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from langsight.sdk.client import LangSightClient
from langsight.sdk.models import ToolCallSpan, ToolCallStatus

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _span(tool: str = "query", server: str = "pg") -> ToolCallSpan:
    now = datetime.now(UTC)
    return ToolCallSpan(
        server_name=server,
        tool_name=tool,
        started_at=now,
        ended_at=now,
        latency_ms=10.0,
        status=ToolCallStatus.SUCCESS,
    )


def _client_no_flush(batch_size: int = 10_000, max_buffer_size: int = 10_000) -> LangSightClient:
    """Return a client with _post_spans patched to a no-op so flush doesn't talk to network."""
    client = LangSightClient(
        url="http://localhost:8000",
        batch_size=batch_size,
        max_buffer_size=max_buffer_size,
    )
    client._post_spans = AsyncMock()
    return client


# ---------------------------------------------------------------------------
# Concurrent send_span — no spans lost
# ---------------------------------------------------------------------------


class TestConcurrentSendSpanNoLoss:
    async def test_ten_concurrent_send_span_calls_all_buffered(self) -> None:
        """10 concurrent send_span calls must result in exactly 10 spans in the buffer."""
        client = _client_no_flush()

        await asyncio.gather(*[client.send_span(_span(f"tool-{i}")) for i in range(10)])

        assert len(client._buffer) == 10

    async def test_fifty_concurrent_send_span_calls_all_buffered(self) -> None:
        """50 concurrent send_span calls must result in exactly 50 spans in the buffer."""
        client = _client_no_flush()

        await asyncio.gather(*[client.send_span(_span(f"tool-{i}")) for i in range(50)])

        assert len(client._buffer) == 50

    async def test_buffer_contains_all_distinct_spans(self) -> None:
        """Each span sent concurrently must appear in the buffer (no silent drops)."""
        client = _client_no_flush()
        expected_tools = [f"tool-{i}" for i in range(20)]

        await asyncio.gather(*[client.send_span(_span(t)) for t in expected_tools])

        buffered_tools = {s.tool_name for s in client._buffer}
        for tool in expected_tools:
            assert tool in buffered_tools

    async def test_lock_is_an_asyncio_lock_instance(self) -> None:
        """The _lock attribute must be an asyncio.Lock (not a threading.Lock)."""
        client = LangSightClient(url="http://localhost:8000")
        assert isinstance(client._lock, asyncio.Lock)


# ---------------------------------------------------------------------------
# Concurrent send_span + flush — no spans lost
# ---------------------------------------------------------------------------


class TestConcurrentSendAndFlushNoLoss:
    async def test_send_and_flush_together_deliver_all_spans(self) -> None:
        """Concurrent send_span + flush must not lose any spans.

        The lock prevents the race condition where flush() clears the buffer
        at the same moment send_span() is appending to it.
        """
        sent_spans: list[ToolCallSpan] = []

        async def capture_post(batch: list[ToolCallSpan]) -> None:
            sent_spans.extend(batch)

        client = _client_no_flush(batch_size=10_000)
        client._post_spans = capture_post  # type: ignore[method-assign]

        # Pre-fill buffer with 5 spans then race concurrent send + flush
        for i in range(5):
            await client.send_span(_span(f"pre-{i}"))

        # Race: 10 concurrent sends + 3 explicit flushes
        tasks = [client.send_span(_span(f"concurrent-{i}")) for i in range(10)]
        tasks += [client.flush(), client.flush(), client.flush()]
        await asyncio.gather(*tasks)

        # Drain the buffer one final time
        await client.flush()

        total_delivered = len(sent_spans) + len(client._buffer)
        # 5 pre-filled + 10 concurrent = 15 total
        assert total_delivered == 15

    async def test_flush_clears_buffer_atomically(self) -> None:
        """After flush, the buffer must be empty (no partial clears)."""
        client = _client_no_flush()

        for i in range(5):
            await client.send_span(_span(f"tool-{i}"))

        await client.flush()

        assert client._buffer == []

    async def test_concurrent_flushes_do_not_double_send(self) -> None:
        """Two concurrent flush() calls must not deliver the same span twice."""
        delivered_batches: list[list[ToolCallSpan]] = []

        async def capture_post(batch: list[ToolCallSpan]) -> None:
            delivered_batches.append(batch)

        client = _client_no_flush()
        client._post_spans = capture_post  # type: ignore[method-assign]

        # Pre-fill 10 spans
        for i in range(10):
            await client.send_span(_span(f"tool-{i}"))

        # Race two flushes
        await asyncio.gather(client.flush(), client.flush())

        total_spans_delivered = sum(len(b) for b in delivered_batches)
        # Should be exactly 10 — no duplicates
        assert total_spans_delivered == 10


# ---------------------------------------------------------------------------
# Buffer overflow cap under concurrent load
# ---------------------------------------------------------------------------


class TestBufferOverflowCapConcurrent:
    async def test_buffer_never_exceeds_max_buffer_size(self) -> None:
        """Buffer size must never exceed max_buffer_size, even with concurrent sends."""
        max_buf = 20
        client = _client_no_flush(batch_size=10_000, max_buffer_size=max_buf)

        await asyncio.gather(*[client.send_span(_span(f"tool-{i}")) for i in range(50)])

        assert len(client._buffer) <= max_buf

    async def test_buffer_holds_most_recent_spans_after_overflow(self) -> None:
        """After overflow, the buffer retains the most recent spans (oldest dropped)."""
        max_buf = 5
        client = _client_no_flush(batch_size=10_000, max_buffer_size=max_buf)

        # Send sequentially so order is deterministic
        for i in range(10):
            await client.send_span(_span(f"tool-{i}"))

        # The last `max_buf` spans should be in the buffer
        # (overflow drops oldest, keeps newest)
        assert len(client._buffer) == max_buf
        remaining_tools = {s.tool_name for s in client._buffer}
        for i in range(5, 10):
            assert f"tool-{i}" in remaining_tools


# ---------------------------------------------------------------------------
# send_span + flush interaction — buffer cleared before _post_spans
# ---------------------------------------------------------------------------


class TestFlushLockSemantics:
    async def test_flush_on_empty_buffer_is_noop(self) -> None:
        """flush() on an empty buffer must not call _post_spans."""
        client = _client_no_flush()

        await client.flush()

        client._post_spans.assert_not_called()  # type: ignore[attr-defined]

    async def test_second_flush_after_first_is_noop(self) -> None:
        """A second flush after the first already cleared the buffer is a no-op."""
        call_count = 0

        async def counter_post(batch: list[ToolCallSpan]) -> None:
            nonlocal call_count
            call_count += 1

        client = _client_no_flush()
        client._post_spans = counter_post  # type: ignore[method-assign]

        await client.send_span(_span())
        await client.flush()
        await client.flush()  # buffer is empty — should be a no-op

        assert call_count == 1

    async def test_send_after_flush_adds_to_fresh_buffer(self) -> None:
        """After a flush, subsequent send_span calls accumulate in a fresh buffer."""
        client = _client_no_flush()

        await client.send_span(_span("tool-a"))
        await client.flush()

        assert client._buffer == []

        await client.send_span(_span("tool-b"))
        assert len(client._buffer) == 1
        assert client._buffer[0].tool_name == "tool-b"
