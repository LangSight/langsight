"""Server-Sent Events (SSE) broadcaster for live dashboard updates.

Architecture:
  1. Span ingestion (traces.py) calls ``broadcast.publish(event)``
  2. Connected SSE clients receive the event in real-time
  3. Dashboard uses EventSource to subscribe

Two implementations:
  SSEBroadcaster   — in-memory asyncio.Queue, single-instance deployments
  RedisBroadcaster — Redis pub/sub, multi-worker deployments

Both expose the same API:
    broadcaster.publish(event_type, data)   → sync, fire-and-forget
    broadcaster.subscribe(project_id=None)  → AsyncGenerator[str, None]
    broadcaster.client_count                → int (approximate for Redis)

Channel layout (RedisBroadcaster):
    langsight:events:admin          — all events (admin, project_id=None)
    langsight:events:{project_id}   — per-project events

Security: unscoped events (project_id='') are published only to the admin
channel. Project-scoped subscribers are on their own channel so they can
never receive events from other projects.

Events:
  span:new     — a new tool call span was ingested
  health:check — a health check completed
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog

from langsight.api.metrics import SSE_EVENTS_DROPPED

if TYPE_CHECKING:
    import redis.asyncio as aioredis

_ADMIN_CHANNEL = "langsight:events:admin"
_PROJECT_CHANNEL_PREFIX = "langsight:events:"

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


class RedisBroadcaster:
    """Redis pub/sub broadcaster for multi-worker SSE delivery.

    Uses a background ``_reader`` asyncio task per subscriber that drains
    ``pubsub.listen()`` into a local ``asyncio.Queue``. The SSE generator
    reads from that queue with a 15-second timeout for keepalives —
    identical pattern to ``SSEBroadcaster``.

    Security invariants:
    - Project subscribers are on channel ``langsight:events:{project_id}``.
      They physically cannot receive events published to other channels.
    - Unscoped events (no project_id) are published only to the admin
      channel, never to project channels.
    - Admin subscribers (project_id=None) listen on ``langsight:events:admin``
      which receives every event.

    ``client_count`` is per-worker approximate — used for logging/metrics only.
    """

    def __init__(self, redis_client: aioredis.Redis) -> None:
        self._redis = redis_client
        self._local_client_count: int = 0

    @property
    def client_count(self) -> int:
        return self._local_client_count

    def publish(self, event_type: str, data: dict[str, Any]) -> None:
        """Publish event to Redis. Non-blocking — schedules an async task."""
        asyncio.ensure_future(self._publish_async(event_type, data))

    async def _publish_async(self, event_type: str, data: dict[str, Any]) -> None:
        """Push to admin channel always; also push to project channel when scoped."""
        event_project = data.get("project_id") or ""
        payload = json.dumps({"event_type": event_type, "data": data}, default=str)
        try:
            await self._redis.publish(_ADMIN_CHANNEL, payload)
            if event_project:
                await self._redis.publish(f"{_PROJECT_CHANNEL_PREFIX}{event_project}", payload)
        except Exception as exc:  # noqa: BLE001
            logger.warning("redis.publish_failed", error=str(exc))

    async def subscribe(self, project_id: str | None = None) -> AsyncGenerator[str, None]:
        """Subscribe to the Redis-backed event stream.

        project_id=None  → listens on langsight:events:admin (all events)
        project_id='x'   → listens on langsight:events:x (own events only)
        """
        channel = _ADMIN_CHANNEL if project_id is None else f"{_PROJECT_CHANNEL_PREFIX}{project_id}"

        if self._local_client_count >= _MAX_CLIENTS:
            yield f"event: error\ndata: {json.dumps({'message': 'Too many connections'})}\n\n"
            return

        pubsub = self._redis.pubsub()
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=_CLIENT_BUFFER)
        self._local_client_count += 1

        async def _reader() -> None:
            """Drain pubsub.listen() into the local queue."""
            try:
                await pubsub.subscribe(channel)
                async for message in pubsub.listen():
                    if message["type"] != "message":
                        continue
                    try:
                        queue.put_nowait(message["data"])
                    except asyncio.QueueFull:
                        try:
                            queue.get_nowait()
                            queue.put_nowait(message["data"])
                        except (asyncio.QueueEmpty, asyncio.QueueFull):
                            pass
                        SSE_EVENTS_DROPPED.inc()
            except asyncio.CancelledError:
                pass
            except Exception as exc:  # noqa: BLE001
                logger.warning("redis.subscriber_error", error=str(exc))

        reader_task = asyncio.ensure_future(_reader())

        try:
            yield f": connected at {datetime.now(UTC).isoformat()}\n\n"
            while True:
                try:
                    raw = await asyncio.wait_for(queue.get(), timeout=15.0)
                    parsed = json.loads(raw)
                    event_type = parsed["event_type"]
                    event_data = parsed["data"]
                    yield f"event: {event_type}\ndata: {json.dumps(event_data, default=str)}\n\n"
                except TimeoutError:
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            self._local_client_count -= 1
            reader_task.cancel()
            try:
                await reader_task
            except asyncio.CancelledError:
                pass
            try:
                await pubsub.unsubscribe(channel)
                await pubsub.aclose()  # type: ignore[no-untyped-call]
            except Exception:  # noqa: BLE001
                pass
