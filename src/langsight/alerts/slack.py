"""
Slack Block Kit webhook delivery for LangSight alerts.

Sends rich, formatted Slack messages using the Incoming Webhooks API.
No Slack SDK dependency — plain HTTP POST via httpx.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from langsight.alerts.engine import Alert, AlertSeverity, AlertType

logger = structlog.get_logger()

_SEVERITY_EMOJI = {
    AlertSeverity.CRITICAL: ":red_circle:",
    AlertSeverity.WARNING: ":warning:",
    AlertSeverity.INFO: ":large_green_circle:",
}

_TYPE_EMOJI = {
    AlertType.SERVER_DOWN:      ":x:",
    AlertType.SERVER_RECOVERED: ":white_check_mark:",
    AlertType.SCHEMA_DRIFT:     ":twisted_rightwards_arrows:",
    AlertType.HIGH_LATENCY:     ":hourglass_flowing_sand:",
    AlertType.AGENT_FAILURE:    ":robot_face:",
    AlertType.SLO_BREACHED:     ":chart_with_downwards_trend:",
    AlertType.ANOMALY_DETECTED: ":mag:",
    AlertType.SECURITY_FINDING: ":shield:",
}

SLACK_TIMEOUT = 5.0


async def send_alert(webhook_url: str, alert: Alert) -> bool:
    """Send a single alert to a Slack webhook.

    Returns True if delivery succeeded, False otherwise (fail-open).
    """
    payload = _build_payload(alert)
    try:
        async with httpx.AsyncClient(timeout=SLACK_TIMEOUT) as client:
            response = await client.post(webhook_url, json=payload)
            response.raise_for_status()
        logger.info(
            "slack.alert_sent",
            server=alert.server_name,
            alert_type=alert.alert_type,
        )
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "slack.delivery_failed",
            server=alert.server_name,
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


def _build_payload(alert: Alert) -> dict[str, Any]:
    """Build a Slack Block Kit message payload."""
    severity_emoji = _SEVERITY_EMOJI.get(alert.severity, ":bell:")
    type_emoji = _TYPE_EMOJI.get(alert.alert_type, ":bell:")

    return {
        "text": f"{severity_emoji} {alert.title}",  # fallback for notifications
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{type_emoji} {alert.title}",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": alert.message,
                },
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Server*\n`{alert.server_name}`",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Severity*\n{severity_emoji} {alert.severity.value.upper()}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Type*\n{alert.alert_type.value}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Time*\n{alert.fired_at.strftime('%Y-%m-%d %H:%M:%S UTC')}",
                    },
                ],
            },
            {"type": "divider"},
        ],
    }
