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

from langsight.api.metrics import SSE_EVENTS_DROPPED

logger = structlog.get_logger()

# Hard limit on connected clients to prevent resource exhaustion
_MAX_CLIENTS = 200
# Buffer size per client — old events dropped if client is slow
_CLIENT_BUFFER = 50


class SSEBroadcaster:
    """In-memory pub/sub for Server-Sent Events.

    Supports per-project filtering: subscribers pass a project_id and only
    receive events for that project. Admin subscribers (project_id=None)
    receive all events.
    """

    def __init__(self) -> None:
        # Each entry: (queue, project_id) — project_id=None means admin/all events
        self._clients: list[tuple[asyncio.Queue[str], str | None]] = []

    @property
    def client_count(self) -> int:
        return len(self._clients)

    def publish(self, event_type: str, data: dict[str, Any]) -> None:
        """Publish an event to matching clients. Non-blocking, never raises."""
        if not self._clients:
            return
        event_project = data.get("project_id") or ""
        payload = f"event: {event_type}\ndata: {json.dumps(data, default=str)}\n\n"
        for queue, sub_project in self._clients:
            # Admin subscriber (sub_project=None) sees all events.
            # Project subscriber only sees events that either:
            #   (a) belong to their project, or
            #   (b) are explicitly unscoped (event_project="") AND they are admin.
            # Previously, unscoped events (event_project="") were sent to every
            # project subscriber because the filter only ran when event_project
            # was truthy — leaking cross-project internal events.
            if sub_project is None:
                pass  # admin — receives everything
            elif not event_project:
                continue  # unscoped event — project subscribers must not see it
            elif sub_project != event_project:
                continue  # different project
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                try:
                    queue.get_nowait()
                    queue.put_nowait(payload)
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    pass
                SSE_EVENTS_DROPPED.inc()
                logger.debug("sse.event_dropped", event_type=event_type, clients=len(self._clients))

    async def subscribe(self, project_id: str | None = None) -> AsyncGenerator[str, None]:
        """Subscribe to the event stream filtered by project_id.

        project_id=None receives all events (admin).
        project_id=<id> receives only events for that project.
        """
        if len(self._clients) >= _MAX_CLIENTS:
            yield f"event: error\ndata: {json.dumps({'message': 'Too many connections'})}\n\n"
            return

        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=_CLIENT_BUFFER)
        entry = (queue, project_id)
        self._clients.append(entry)

        yield f": connected at {datetime.now(UTC).isoformat()}\n\n"

        try:
            while True:
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield msg
                except TimeoutError:
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            self._clients.remove(entry)
