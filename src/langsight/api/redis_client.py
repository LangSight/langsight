"""Optional Redis client for LangSight.

All Redis functionality is conditional on LANGSIGHT_REDIS_URL being set.
When the URL is absent this module is a no-op and the redis package is
never imported, so single-instance deployments have zero additional deps.

Usage::

    from langsight.api.redis_client import get_redis_client, close_redis_client

    # In lifespan startup
    if settings.redis_url:
        client = await get_redis_client(settings.redis_url)
        app.state.redis = client

    # In lifespan teardown
    await close_redis_client()
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    import redis.asyncio as aioredis

logger = structlog.get_logger()

# Module-level singleton — one connection pool per worker process.
# Shared across rate_limit, broadcast, and circuit_breaker modules.
_client: Any = None  # aioredis.Redis | None


def is_redis_configured(redis_url: str | None) -> bool:
    """Return True when a Redis URL has been provided."""
    return bool(redis_url)


async def get_redis_client(redis_url: str) -> "aioredis.Redis":
    """Return a connected redis.asyncio client, creating it on first call.

    The client uses a connection pool with:
        decode_responses=True      — all keys/values are str, not bytes
        max_connections=20         — generous pool; Redis is fast
        socket_connect_timeout=5   — fail fast at startup if unreachable
        socket_keepalive=True      — maintain persistent connections

    Raises redis.exceptions.ConnectionError if Redis is unreachable.
    The error propagates to the FastAPI lifespan so the API refuses to start
    with an unreachable Redis rather than silently falling back to in-memory.
    """
    global _client
    if _client is not None:
        return _client

    import redis.asyncio as aioredis  # lazy — only imported when URL is set

    _client = aioredis.from_url(
        redis_url,
        decode_responses=True,
        max_connections=20,
        socket_connect_timeout=5,
        socket_keepalive=True,
    )
    # Ping to fail fast at startup rather than at first use
    await _client.ping()
    # Log the host/port only — strip any password from the URL
    safe_url = redis_url.split("@")[-1] if "@" in redis_url else redis_url
    logger.info("redis.connected", url=safe_url)
    return _client


async def close_redis_client() -> None:
    """Gracefully close the connection pool.

    Called from the FastAPI lifespan teardown block. Safe to call even
    when Redis was never configured (no-op when _client is None).
    """
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
        logger.info("redis.disconnected")
