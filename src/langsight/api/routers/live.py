"""Live event stream — Server-Sent Events for real-time dashboard updates.

GET /api/live/events — SSE stream of span ingestion and health check events.
Requires authentication (same as all other API routes).

The dashboard connects via EventSource and receives events like:
  event: span:new
  data: {"session_id": "...", "tool_name": "query", "status": "success", ...}

  event: health:check
  data: {"server_name": "postgres-mcp", "status": "up", "latency_ms": 42}
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import APIRouter, Request
from starlette.responses import StreamingResponse

from langsight.api.metrics import ACTIVE_SSE

router = APIRouter(prefix="/live", tags=["live"])


@router.get(
    "/events",
    summary="Live event stream (SSE)",
    response_class=StreamingResponse,
    responses={200: {"description": "SSE event stream", "content": {"text/event-stream": {}}}},
)
async def live_events(request: Request) -> StreamingResponse:
    """Subscribe to real-time events via Server-Sent Events.

    Events are pushed when:
    - A new span is ingested (event: span:new)
    - A health check completes (event: health:check)

    The stream sends keepalive comments every 15 seconds to prevent
    proxy timeouts. Connect with EventSource in the browser.
    """
    broadcaster = request.app.state.broadcaster

    async def event_generator() -> AsyncGenerator[str, None]:
        ACTIVE_SSE.inc()
        try:
            async for event in broadcaster.subscribe():
                # Check if client disconnected
                if await request.is_disconnected():
                    break
                yield event
        finally:
            ACTIVE_SSE.dec()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable nginx buffering
        },
    )
