"""Prometheus metrics for LangSight API.

Exposes ``GET /metrics`` in Prometheus text format. This endpoint is
registered **without** authentication so Prometheus scrapers can reach it
without API keys.

Metrics exported:
  langsight_http_requests_total         — counter, labels: method, path, status
  langsight_http_request_duration_seconds — histogram, labels: method, path
  langsight_spans_ingested_total        — counter (spans received via /traces/spans + /traces/otlp)
  langsight_active_sse_connections      — gauge (live SSE clients)
  langsight_health_checks_total         — counter, labels: server, status
  langsight_storage_pool_size           — gauge, labels: backend (postgres pool info)

Usage in main.py:
    from langsight.api.metrics import metrics_router, PrometheusMiddleware
    app.include_router(metrics_router)  # no auth
    app.add_middleware(PrometheusMiddleware)
"""

from __future__ import annotations

import hmac
import os
import time
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Request, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response as StarletteResponse

# ---------------------------------------------------------------------------
# Metrics definitions
# ---------------------------------------------------------------------------

HTTP_REQUESTS = Counter(
    "langsight_http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)

HTTP_DURATION = Histogram(
    "langsight_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

SPANS_INGESTED = Counter(
    "langsight_spans_ingested_total",
    "Total tool call spans ingested",
)

ACTIVE_SSE = Gauge(
    "langsight_active_sse_connections",
    "Number of active SSE (live feed) connections",
)

SSE_EVENTS_DROPPED = Counter(
    "langsight_sse_events_dropped_total",
    "SSE events dropped because client buffer was full",
)

HEALTH_CHECKS = Counter(
    "langsight_health_checks_total",
    "Total health checks performed",
    ["server", "status"],
)

# ---------------------------------------------------------------------------
# /metrics endpoint
# ---------------------------------------------------------------------------

metrics_router = APIRouter(tags=["metrics"])


_METRICS_TOKEN = os.environ.get("LANGSIGHT_METRICS_TOKEN", "")

if not _METRICS_TOKEN:
    import logging as _logging

    _logging.getLogger(__name__).warning(
        "LANGSIGHT_METRICS_TOKEN is not set — /metrics endpoint requires a token. "
        "Set LANGSIGHT_METRICS_TOKEN=<secret> to enable Prometheus scraping. "
        "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
    )


@metrics_router.get("/metrics", include_in_schema=False)
async def prometheus_metrics(request: Request) -> Response:
    """Prometheus scrape endpoint.

    Requires LANGSIGHT_METRICS_TOKEN to be set. Pass it as:
      Authorization: Bearer <token>

    Returns 401 if the token is missing or wrong.
    Returns 503 if LANGSIGHT_METRICS_TOKEN is not configured.
    """
    if not _METRICS_TOKEN:
        # Token not configured — refuse rather than expose metrics openly.
        # Operators must explicitly set LANGSIGHT_METRICS_TOKEN to enable scraping.
        return Response(
            status_code=503,
            content="LANGSIGHT_METRICS_TOKEN is not set. Configure it to enable /metrics.",
        )
    auth_header = request.headers.get("Authorization", "")
    bearer = auth_header.removeprefix("Bearer ").strip()
    if not bearer or not hmac.compare_digest(bearer, _METRICS_TOKEN):
        return Response(status_code=401, content="Unauthorized")
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


# ---------------------------------------------------------------------------
# Request instrumentation middleware
# ---------------------------------------------------------------------------

# Paths to skip — high-frequency internal endpoints
_SKIP_PATHS = {"/metrics", "/api/liveness", "/api/readiness"}


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Record request count and duration for every API call."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[StarletteResponse]],
    ) -> StarletteResponse:
        path = request.url.path
        if path in _SKIP_PATHS:
            return await call_next(request)

        # Normalize path — collapse IDs to {id} to keep cardinality low
        normalized = _normalize_path(path)
        method = request.method

        start = time.perf_counter()
        response: StarletteResponse = await call_next(request)
        duration = time.perf_counter() - start

        HTTP_REQUESTS.labels(method=method, path=normalized, status=response.status_code).inc()
        HTTP_DURATION.labels(method=method, path=normalized).observe(duration)

        return response


def _normalize_path(path: str) -> str:
    """Collapse UUID/ID segments to keep metric cardinality bounded.

    /api/agents/sessions/abc123 → /api/agents/sessions/{id}
    /api/projects/proj-xyz/members → /api/projects/{id}/members
    """
    parts = path.strip("/").split("/")
    normalized = []
    for part in parts:
        # Heuristic: hex strings > 8 chars or parts containing hyphens with digits are IDs
        if len(part) > 8 and all(c in "0123456789abcdef-" for c in part.lower()):
            normalized.append("{id}")
        else:
            normalized.append(part)
    return "/" + "/".join(normalized)
