"""
Generic webhook delivery — works with PagerDuty, Opsgenie, and custom endpoints.

Sends a JSON payload via HTTP POST. Fail-open: delivery failures are logged
but never raise exceptions (monitoring must not break because alerting is down).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time

import httpx
import structlog

from langsight.alerts._url_validation import validate_webhook_url
from langsight.alerts.engine import Alert

logger = structlog.get_logger()

WEBHOOK_TIMEOUT = 5.0

# Optional shared secret for HMAC signing.  Set LANGSIGHT_WEBHOOK_SECRET to
# a random 32-byte hex string.  Receivers verify:
#   HMAC-SHA256(secret, f"{timestamp}.{body}") == X-LangSight-Signature
# When unset, the header is omitted (backward-compatible).
_WEBHOOK_SECRET = os.environ.get("LANGSIGHT_WEBHOOK_SECRET", "")


def _sign_payload(body: str) -> dict[str, str]:
    """Return signing headers if LANGSIGHT_WEBHOOK_SECRET is configured."""
    if not _WEBHOOK_SECRET:
        return {}
    ts = str(int(time.time()))
    sig = hmac.new(
        _WEBHOOK_SECRET.encode(),
        f"{ts}.{body}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return {
        "X-LangSight-Timestamp": ts,
        "X-LangSight-Signature": f"sha256={sig}",
    }


async def send_alert(webhook_url: str, alert: Alert) -> bool:
    """POST a single alert as JSON to a webhook URL.

    Returns True on success, False on failure (fail-open).
    """
    try:
        validate_webhook_url(webhook_url)
    except ValueError as exc:
        logger.error("webhook.invalid_url", error=str(exc))
        return False

    payload = {
        "server_name": alert.server_name,
        "alert_type": alert.alert_type.value,
        "severity": alert.severity.value,
        "title": alert.title,
        "message": alert.message,
        "fired_at": alert.fired_at.isoformat(),
    }
    try:
        body = json.dumps(payload)
        headers = {"Content-Type": "application/json", **_sign_payload(body)}
        async with httpx.AsyncClient(timeout=WEBHOOK_TIMEOUT) as client:
            response = await client.post(webhook_url, content=body, headers=headers)
            response.raise_for_status()
        logger.info(
            "webhook.alert_sent",
            server=alert.server_name,
            alert_type=alert.alert_type,
        )
        return True
    except Exception as exc:  # noqa: BLE001
        # Scrub exception message — httpx errors can contain the full
        # webhook URL which may include tokens or secrets.
        err_type = type(exc).__name__
        logger.warning(
            "webhook.delivery_failed",
            server=alert.server_name,
            error_type=err_type,
        )
        return False


async def send_alerts(webhook_url: str, alerts: list[Alert]) -> int:
    """Send multiple alerts. Returns count of successfully delivered alerts."""
    sent = 0
    for alert in alerts:
        if await send_alert(webhook_url, alert):
            sent += 1
    return sent
