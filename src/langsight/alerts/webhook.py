"""
Generic webhook delivery — works with PagerDuty, Opsgenie, and custom endpoints.

Sends a JSON payload via HTTP POST. Fail-open: delivery failures are logged
but never raise exceptions (monitoring must not break because alerting is down).
"""

from __future__ import annotations

import httpx
import structlog

from langsight.alerts._url_validation import validate_webhook_url
from langsight.alerts.engine import Alert

logger = structlog.get_logger()

WEBHOOK_TIMEOUT = 5.0


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
        async with httpx.AsyncClient(timeout=WEBHOOK_TIMEOUT) as client:
            response = await client.post(webhook_url, json=payload)
            response.raise_for_status()
        logger.info(
            "webhook.alert_sent",
            server=alert.server_name,
            alert_type=alert.alert_type,
            url=webhook_url,
        )
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "webhook.delivery_failed",
            server=alert.server_name,
            url=webhook_url,
            error=str(exc),
        )
        return False


async def send_alerts(webhook_url: str, alerts: list[Alert]) -> int:
    """Send multiple alerts. Returns count of successfully delivered alerts."""
    sent = 0
    for alert in alerts:
        if await send_alert(webhook_url, alert):
            sent += 1
    return sent
