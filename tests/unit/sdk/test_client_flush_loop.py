"""
Tests for the SDK flush-loop lifecycle.

The flush loop must start automatically the first time a span is buffered
in an async context, and must deliver spans within flush_interval seconds
rather than accumulating them until process exit.

Regression guard for: _ensure_flush_loop() was defined but never called,
causing all spans to accumulate in memory and only flush via atexit — making
the Live page empty during agent runs.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from langsight.sdk.client import LangSightClient
from langsight.sdk.models import ToolCallSpan, ToolCallStatus
from datetime import UTC, datetime


def _make_span(**kw) -> ToolCallSpan:
    defaults = dict(
        server_name="s",
        tool_name="t",
        started_at=datetime(2026, 3, 26, 10, 0, 0, tzinfo=UTC),
        ended_at=datetime(2026, 3, 26, 10, 0, 1, tzinfo=UTC),
        latency_ms=1000.0,
        status=ToolCallStatus.SUCCESS,
        session_id="sess-flush-test",
        agent_name="agent",
        project_id="proj-1",
    )
    defaults.update(kw)
    return ToolCallSpan(**defaults)


# ---------------------------------------------------------------------------
# _ensure_flush_loop starts the flush background task
# ---------------------------------------------------------------------------

class TestFlushLoopStarts:
    @pytest.mark.asyncio
    async def test_flush_loop_starts_after_buffer_span(self) -> None:
        """The flush loop task must be created when buffer_span is called in
        an async context — not deferred until atexit."""
        client = LangSightClient(url="http://localhost:8000", flush_interval=60.0)

        assert client._flush_task is None or client._flush_task.done(), (
            "flush_task should not exist before any span is buffered"
        )

        client.buffer_span(_make_span())

        # Allow event loop to schedule the created task
        await asyncio.sleep(0)

        assert client._flush_task is not None, (
            "_ensure_flush_loop() was not called from buffer_span(). "
            "Spans will only flush at process exit (atexit), making the "
            "Live page empty during agent runs."
        )
        assert not client._flush_task.done(), (
            "Flush loop task should be running, not already finished."
        )

        client._flush_task.cancel()
        await asyncio.sleep(0.05)  # let task finish its final flush + complete

    @pytest.mark.asyncio
    async def test_flush_loop_is_idempotent(self) -> None:
        """Calling buffer_span multiple times must not create multiple flush tasks."""
        client = LangSightClient(url="http://localhost:8000", flush_interval=60.0)

        client.buffer_span(_make_span())
        await asyncio.sleep(0)
        task_1 = client._flush_task

        client.buffer_span(_make_span())
        await asyncio.sleep(0)
        task_2 = client._flush_task

        assert task_1 is task_2, (
            "buffer_span() created a second flush task — _ensure_flush_loop "
            "must be idempotent (only create a task if none is running)."
        )

        task_1.cancel()  # type: ignore[union-attr]
        await asyncio.sleep(0.05)


# ---------------------------------------------------------------------------
# Spans are delivered within flush_interval, not at atexit
# ---------------------------------------------------------------------------

class TestFlushDelivery:
    @pytest.mark.asyncio
    async def test_spans_sent_within_flush_interval(self) -> None:
        """Spans must reach the API within flush_interval seconds of being
        buffered — not at process exit."""
        sent_batches: list[list[ToolCallSpan]] = []

        async def fake_post(spans: list[ToolCallSpan]) -> bool:
            sent_batches.append(list(spans))
            return True

        client = LangSightClient(
            url="http://localhost:8000",
            flush_interval=0.05,  # 50ms for fast test
        )
        client._post_spans = fake_post  # type: ignore[method-assign]

        span = _make_span()
        client.buffer_span(span)

        # Wait longer than flush_interval
        await asyncio.sleep(0.2)

        assert sent_batches, (
            "No spans were sent within 200ms (flush_interval=50ms). "
            "The flush loop is not running — buffer_span() must call "
            "_ensure_flush_loop() so spans are delivered in real time."
        )
        all_spans = [s for batch in sent_batches for s in batch]
        assert any(s.session_id == "sess-flush-test" for s in all_spans), (
            "The buffered span was not delivered within the flush interval."
        )

        if client._flush_task and not client._flush_task.done():
            client._flush_task.cancel()

    @pytest.mark.asyncio
    async def test_batch_flushed_when_buffer_reaches_batch_size(self) -> None:
        """When _batch_size spans accumulate, the next flush delivers them all."""
        sent_batches: list[list[ToolCallSpan]] = []

        async def fake_post(spans: list[ToolCallSpan]) -> bool:
            sent_batches.append(list(spans))
            return True

        client = LangSightClient(
            url="http://localhost:8000",
            flush_interval=0.05,
            batch_size=3,
        )
        client._post_spans = fake_post  # type: ignore[method-assign]

        for i in range(3):
            client.buffer_span(_make_span(session_id=f"sess-{i}"))

        await asyncio.sleep(0.2)

        total_sent = sum(len(b) for b in sent_batches)
        assert total_sent == 3, (
            f"Expected 3 spans to be flushed, got {total_sent}."
        )

        if client._flush_task and not client._flush_task.done():
            client._flush_task.cancel()

    @pytest.mark.asyncio
    async def test_atexit_is_last_resort_not_primary_delivery(self) -> None:
        """atexit should only send spans that were buffered after the flush
        loop had no chance to run (e.g. very short-lived process). Under
        normal async operation the buffer should be empty at exit."""
        async def fake_post(spans: list[ToolCallSpan]) -> bool:
            return True

        client = LangSightClient(
            url="http://localhost:8000",
            flush_interval=0.05,
        )
        client._post_spans = fake_post  # type: ignore[method-assign]

        client.buffer_span(_make_span())
        # Allow flush loop to run
        await asyncio.sleep(0.2)

        # Buffer should be empty — spans already flushed by the loop
        with client._lock:
            remaining = len(client._buffer)

        assert remaining == 0, (
            f"Buffer has {remaining} spans after flush interval elapsed. "
            "The flush loop did not drain the buffer — spans are still "
            "waiting for atexit delivery."
        )

        if client._flush_task and not client._flush_task.done():
            client._flush_task.cancel()


# ---------------------------------------------------------------------------
# No running event loop (sync-only callers)
# ---------------------------------------------------------------------------

class TestFlushLoopNoEventLoop:
    def test_buffer_span_does_not_raise_without_event_loop(self) -> None:
        """buffer_span() must work cleanly when called from a synchronous
        context (e.g. from a sync LangChain callback). It must not raise
        regardless of whether an event loop happens to be running."""
        client = LangSightClient(url="http://localhost:8000")
        client.buffer_span(_make_span())  # must not raise
        with client._lock:
            assert len(client._buffer) == 1, "span must be in buffer after buffer_span()"
