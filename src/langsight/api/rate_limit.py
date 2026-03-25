"""Global rate limiter — single instance shared by all routers.

All rate-limited endpoints import ``limiter`` from this module.
SlowAPIMiddleware in main.py reads ``app.state.limiter`` which is set
to this same instance, so default_limits and per-route @limiter.limit()
decorators all work together.

Default: 200 requests/minute per caller.  Per-route overrides:
  /api/traces/spans:         2000/min  (high-frequency SDK ingestion)
  /api/traces/otlp:            60/min  (OTEL collector batches)
  /api/users/accept-invite:     5/min  (invite brute-force protection)
  /api/users/verify:           10/min  (login brute-force protection)

Key resolution order (first match wins):
  1. X-Forwarded-For header — set by the Next.js dashboard proxy, so each
     browser user gets their own bucket instead of sharing the proxy's IP.
  2. X-API-Key header prefix — separates direct SDK callers by their key.
  3. TCP remote address — fallback for direct/unauthed connections.
"""

from __future__ import annotations

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def _rate_limit_key(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # Only trust X-Forwarded-For when the TCP connection comes from a known
        # proxy network (LANGSIGHT_TRUSTED_PROXY_CIDRS). Accepting it from any
        # caller lets attackers spoof IPs and bypass per-IP rate limits.
        client_host = request.client.host if request.client else ""
        trusted = False
        if client_host:
            try:
                import ipaddress
                networks = getattr(
                    getattr(request, "app", None),
                    "state",
                    None,
                )
                networks = getattr(networks, "trusted_proxy_networks", []) if networks else []
                client_ip = ipaddress.ip_address(client_host)
                trusted = any(client_ip in net for net in networks)
            except Exception:  # noqa: BLE001
                trusted = False
        if trusted:
            return forwarded.split(",")[0].strip()
    api_key = request.headers.get("X-API-Key")
    if api_key:
        # Use a prefix — enough for bucketing, avoids retaining the full secret
        return f"key:{api_key[:16]}"
    return get_remote_address(request)


limiter = Limiter(key_func=_rate_limit_key, default_limits=["200/minute"])
