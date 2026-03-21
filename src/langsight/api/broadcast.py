"""Server-Sent Events (SSE) broadcaster for live dashboard updates.

Architecture:
  1. Span ingestion (traces.py) calls ``broadcast.publish(event)``
  2. Connected SSE clients receive the event in real-time
  3. Dashboard uses EventSource to subscribe

The broadcaster is an in-memory asyncio pub/sub — no Redis needed for
single-instance deployments. For multi-instance, add Redis pub/sub later.

Events:
  span:new     — a new tool call span was ingested
  health:check — a health check completed
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

import structlog

logger = structlog.get_logger()

# Hard limit on connected clients to prevent resource exhaustion
_MAX_CLIENTS = 200
# Buffer size per client — old events dropped if client is slow
_CLIENT_BUFFER = 50


class SSEBroadcaster:
    """In-memory pub/sub for Server-Sent Events."""

    def __init__(self) -> None:
        self._clients: list[asyncio.Queue[str]] = []

    @property
    def client_count(self) -> int:
        return len(self._clients)

    def publish(self, event_type: str, data: dict[str, Any]) -> None:
        """Publish an event to all connected clients. Non-blocking, never raises."""
        if not self._clients:
            return
        payload = f"event: {event_type}\ndata: {json.dumps(data, default=str)}\n\n"
        for queue in self._clients:
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                # Client is too slow — drop oldest event
                try:
                    queue.get_nowait()
                    queue.put_nowait(payload)
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    pass

    async def subscribe(self) -> AsyncGenerator[str, None]:
        """Subscribe to the event stream. Yields SSE-formatted strings."""
        if len(self._clients) >= _MAX_CLIENTS:
            yield f"event: error\ndata: {json.dumps({'message': 'Too many connections'})}\n\n"
            return

        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=_CLIENT_BUFFER)
        self._clients.append(queue)

        # Send initial keepalive
        yield f": connected at {datetime.now(UTC).isoformat()}\n\n"

        try:
            while True:
                # Heartbeat every 15 seconds to keep connection alive
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield msg
                except TimeoutError:
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            self._clients.remove(queue)
