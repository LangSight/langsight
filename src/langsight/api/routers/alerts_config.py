"""
Alerts configuration API — manage Slack webhook and alert type toggles.

GET  /api/alerts/config   — get current alert config
POST /api/alerts/config   — save alert config
POST /api/alerts/test     — send a test Slack notification
GET  /api/audit/logs      — recent audit log entries
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi import status as http_status
from pydantic import BaseModel

from langsight.api.dependencies import get_storage, require_admin
from langsight.storage.base import StorageBackend

logger = structlog.get_logger()
router = APIRouter(tags=["alerts"])

# ---------------------------------------------------------------------------
# In-memory audit log ring buffer (last 500 events)
# ---------------------------------------------------------------------------

_MAX_AUDIT_ENTRIES = 500
_audit_log: list[dict[str, Any]] = []


def append_audit(event: str, user_id: str | None, ip: str | None, details: dict[str, Any] | None = None) -> None:
    """Append an event to the in-memory audit log."""
    global _audit_log
    _audit_log.append({
        "id": len(_audit_log) + 1,
        "timestamp": datetime.now(UTC).isoformat(),
        "event": event,
        "user_id": user_id or "system",
        "ip": ip or "unknown",
        "details": details or {},
    })
    if len(_audit_log) > _MAX_AUDIT_ENTRIES:
        _audit_log = _audit_log[-_MAX_AUDIT_ENTRIES:]


# ---------------------------------------------------------------------------
# Default alert type config
# ---------------------------------------------------------------------------

_DEFAULT_ALERT_TYPES = {
    "agent_failure":    True,   # session with failed_calls > 0
    "slo_breached":     True,   # SLO evaluator returns breached
    "anomaly_critical": True,   # z-score critical (|z| >= 3)
    "anomaly_warning":  False,  # z-score warning (|z| >= 2)
    "security_critical":True,   # CVE / OWASP critical finding
    "security_high":    False,  # OWASP high finding
    "mcp_down":         True,   # MCP server DOWN
    "mcp_recovered":    True,   # MCP server recovered
}


def _get_alert_config(request: Request) -> dict[str, Any]:
    """Read alert config from app state (merged with env/yaml).

    Lookup order for webhook URL:
    1. app.state.slack_webhook_override  (set by POST /alerts/config)
    2. config.slack_webhook              (from .langsight.yaml)
    3. LANGSIGHT_SLACK_WEBHOOK env var   (deployment override)
    """
    # 1. In-memory override set via POST /alerts/config
    webhook: str | None = getattr(request.app.state, "slack_webhook_override", None)

    # 2. YAML config
    if not webhook:
        config = getattr(request.app.state, "config", None)
        if config is not None:
            webhook = getattr(config, "slack_webhook", None) or None

    # 3. Env var
    if not webhook:
        webhook = os.environ.get("LANGSIGHT_SLACK_WEBHOOK") or None

    alert_types: dict[str, bool] = getattr(
        request.app.state, "alert_types", dict(_DEFAULT_ALERT_TYPES)
    )
    return {"slack_webhook": webhook, "alert_types": alert_types}


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class AlertConfigResponse(BaseModel):
    slack_webhook: str | None
    alert_types: dict[str, bool]
    webhook_configured: bool


class AlertConfigUpdate(BaseModel):
    slack_webhook: str | None = None
    alert_types: dict[str, bool] | None = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/alerts/config", response_model=AlertConfigResponse)
async def get_alerts_config(request: Request) -> AlertConfigResponse:
    """Return the current alert configuration."""
    cfg = _get_alert_config(request)
    return AlertConfigResponse(
        slack_webhook=cfg["slack_webhook"],
        alert_types=cfg["alert_types"],
        webhook_configured=bool(cfg["slack_webhook"]),
    )


@router.post("/alerts/config", response_model=AlertConfigResponse)
async def save_alerts_config(
    body: AlertConfigUpdate,
    request: Request,
    _: None = Depends(require_admin),
) -> AlertConfigResponse:
    """Save alert configuration to app state.

    Note: webhook URL is saved in-memory. To persist across restarts,
    set LANGSIGHT_SLACK_WEBHOOK env var or add slack_webhook to .langsight.yaml.
    """
    config = getattr(request.app.state, "config", None)

    # Update slack_webhook on config object (in-memory)
    if body.slack_webhook is not None:
        if config is not None:
            try:
                object.__setattr__(config, "slack_webhook", body.slack_webhook or None)
            except (AttributeError, TypeError):
                pass
        # Also store in app state directly as fallback
        request.app.state.slack_webhook_override = body.slack_webhook or None

    # Update alert type toggles
    if body.alert_types is not None:
        existing: dict[str, bool] = getattr(
            request.app.state, "alert_types", dict(_DEFAULT_ALERT_TYPES)
        )
        existing.update(body.alert_types)
        request.app.state.alert_types = existing

    logger.info(
        "audit.alerts.config_updated",
        has_webhook=bool(body.slack_webhook),
        alert_types=list(body.alert_types.keys()) if body.alert_types else [],
    )

    cfg = _get_alert_config(request)
    # Override with explicit state if set
    webhook = getattr(request.app.state, "slack_webhook_override", cfg["slack_webhook"]) or cfg["slack_webhook"]
    return AlertConfigResponse(
        slack_webhook=webhook,
        alert_types=cfg["alert_types"],
        webhook_configured=bool(webhook),
    )


@router.post("/alerts/test", status_code=http_status.HTTP_200_OK)
async def test_slack_webhook(
    request: Request,
    _: None = Depends(require_admin),
) -> dict[str, Any]:
    """Send a test Slack notification to verify the webhook URL works."""
    cfg = _get_alert_config(request)
    webhook_override = getattr(request.app.state, "slack_webhook_override", None)
    webhook_url = webhook_override or cfg["slack_webhook"]

    if not webhook_url:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="No Slack webhook URL configured. Set it in Settings → Notifications.",
        )

    import httpx
    payload = {
        "text": ":white_check_mark: LangSight test notification",
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": ":large_green_circle: LangSight — Test Notification",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "Your Slack integration is working correctly.\nYou will receive alerts here when agent sessions fail, MCP servers go down, SLOs are breached, or anomalies are detected.",
                },
                "fields": [
                    {"type": "mrkdwn", "text": f"*Instance*\n`{request.url.hostname}:{request.url.port or 8000}`"},
                    {"type": "mrkdwn", "text": f"*Sent at*\n{datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}"},
                ],
            },
            {"type": "divider"},
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(webhook_url, json=payload)
            response.raise_for_status()
        logger.info("audit.alerts.test_sent")
        return {"ok": True, "message": "Test notification sent successfully"}
    except Exception as exc:  # noqa: BLE001
        logger.warning("audit.alerts.test_failed", error=str(exc))
        raise HTTPException(
            status_code=http_status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to send test notification: {exc}",
        )


# ---------------------------------------------------------------------------
# Audit log endpoint
# ---------------------------------------------------------------------------

@router.get("/audit/logs")
async def list_audit_logs(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _: None = Depends(require_admin),
) -> dict[str, Any]:
    """Return recent audit log entries (most recent first)."""
    events = list(reversed(_audit_log))
    total = len(events)
    page = events[offset: offset + limit]
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "events": page,
    }
