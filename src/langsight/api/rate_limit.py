"""Global rate limiter — single instance shared by all routers.

All rate-limited endpoints import ``limiter`` from this module.
SlowAPIMiddleware in main.py reads ``app.state.limiter`` which is set
to this same instance, so default_limits and per-route @limiter.limit()
decorators all work together.

Default: 200 requests/minute per IP.  Per-route overrides:
  /api/traces/spans:         2000/min  (high-frequency SDK ingestion)
  /api/traces/otlp:            60/min  (OTEL collector batches)
  /api/users/accept-invite:     5/min  (invite brute-force protection)
  /api/users/verify:           10/min  (login brute-force protection)
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])
