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

from langsight.api.audit import append_audit  # noqa: F401 — re-export for backwards compat
from langsight.api.dependencies import get_active_project_id, require_admin
from langsight.storage.base import StorageBackend

logger = structlog.get_logger()
router = APIRouter(tags=["alerts"])


# ---------------------------------------------------------------------------
# Default alert type config
# ---------------------------------------------------------------------------

_DEFAULT_ALERT_TYPES = {
    "agent_failure": True,  # session with failed_calls > 0
    "slo_breached": True,  # SLO evaluator returns breached
    "anomaly_critical": True,  # z-score critical (|z| >= 3)
    "anomaly_warning": False,  # z-score warning (|z| >= 2)
    "security_critical": True,  # CVE / OWASP critical finding
    "security_high": False,  # OWASP high finding
    "mcp_down": True,  # MCP server DOWN
    "mcp_recovered": True,  # MCP server recovered
}


async def _load_alert_config(request: Request, project_id: str = "") -> dict[str, Any]:
    """Load alert config from DB (authoritative), falling back to env/yaml.

    Priority for webhook URL:
    1. Persisted DB value (set via POST /alerts/config)
    2. YAML config.slack_webhook
    3. LANGSIGHT_SLACK_WEBHOOK env var
    Alert types are merged: DB values override defaults.
    """
    storage: StorageBackend = request.app.state.storage
    db_cfg: dict[str, Any] | None = None
    if hasattr(storage, "get_alert_config"):
        try:
            db_cfg = await storage.get_alert_config(project_id)
        except Exception:  # noqa: BLE001
            pass

    webhook: str | None = (db_cfg or {}).get("slack_webhook") or None

    if not webhook:
        config = getattr(request.app.state, "config", None)
        if config is not None:
            webhook = getattr(config, "slack_webhook", None) or None
    if not webhook:
        webhook = os.environ.get("LANGSIGHT_SLACK_WEBHOOK") or None

    alert_types: dict[str, bool] = dict(_DEFAULT_ALERT_TYPES)
    if db_cfg and db_cfg.get("alert_types"):
        alert_types.update(db_cfg["alert_types"])

    # Internal helper returns the raw URL so the test-send endpoint can use it.
    # The GET handler masks it before responding to the client.
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
async def get_alerts_config(
    request: Request,
    project_id: str | None = Depends(get_active_project_id),
) -> AlertConfigResponse:
    """Return the current alert configuration (read from DB).

    project_id is resolved via get_active_project_id which enforces access
    control — callers can only read configs for projects they belong to.
    """
    cfg = await _load_alert_config(request, project_id or "")
    webhook = cfg["slack_webhook"]
    return AlertConfigResponse(
        # Mask the full URL — expose only a configured/not-configured flag.
        # The actual URL is kept internal for the test-send endpoint.
        slack_webhook=None,
        alert_types=cfg["alert_types"],
        webhook_configured=bool(webhook),
    )


@router.post("/alerts/config", response_model=AlertConfigResponse)
async def save_alerts_config(
    body: AlertConfigUpdate,
    request: Request,
    _: None = Depends(require_admin),
    project_id: str | None = Depends(get_active_project_id),
) -> AlertConfigResponse:
    """Persist alert configuration to the database.

    project_id is resolved via get_active_project_id which enforces access
    control — callers can only write configs for projects they belong to.
    """
    pid = project_id or ""
    # Load current values so we can merge
    current = await _load_alert_config(request, pid)

    new_webhook = body.slack_webhook if body.slack_webhook is not None else current["slack_webhook"]
    new_alert_types: dict[str, bool] = dict(current["alert_types"])
    if body.alert_types is not None:
        new_alert_types.update(body.alert_types)

    # Persist to DB
    storage: StorageBackend = request.app.state.storage
    if hasattr(storage, "save_alert_config"):
        await storage.save_alert_config(new_webhook, new_alert_types, pid)

    logger.info(
        "audit.alerts.config_updated",
        has_webhook=bool(new_webhook),
        alert_types=list(body.alert_types.keys()) if body.alert_types else [],
    )

    return AlertConfigResponse(
        slack_webhook=None,  # URL masked — expose configured flag only
        alert_types=new_alert_types,
        webhook_configured=bool(new_webhook),
    )


@router.post("/alerts/test", status_code=http_status.HTTP_200_OK)
async def test_slack_webhook(
    request: Request,
    _: None = Depends(require_admin),
) -> dict[str, Any]:
    """Send a test Slack notification to verify the webhook URL works."""
    cfg = await _load_alert_config(request)
    webhook_url = cfg["slack_webhook"]

    if not webhook_url:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="No Slack webhook URL configured. Set it in Settings → Notifications.",
        )

    # SSRF guard — validate webhook URL before making an outbound request.
    # Reuses the same validator applied to server URLs (blocks RFC-1918,
    # loopback, link-local, cloud metadata endpoints).
    from langsight.api.routers.servers import _validate_server_url

    try:
        _validate_server_url(webhook_url)
    except ValueError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"Webhook URL is not allowed: {exc}",
        ) from exc

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
                    {
                        "type": "mrkdwn",
                        "text": f"*Instance*\n`{request.url.hostname}:{request.url.port or 8000}`",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Sent at*\n{datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
                    },
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
        # Log full error internally but return generic message — exc may contain
        # the webhook URL (e.g. in httpx connection errors) which must not leak.
        logger.warning("audit.alerts.test_failed", error=str(exc))
        raise HTTPException(
            status_code=http_status.HTTP_502_BAD_GATEWAY,
            detail="Failed to send test notification. Check the webhook URL in Settings and verify Slack is reachable.",
        ) from exc


# ---------------------------------------------------------------------------
# Audit log endpoint
# ---------------------------------------------------------------------------


@router.get("/audit/logs")
async def list_audit_logs(
    request: Request,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _: None = Depends(require_admin),
) -> dict[str, Any]:
    """Return recent audit log entries (most recent first, from DB)."""
    storage: StorageBackend = request.app.state.storage
    if not hasattr(storage, "list_audit_logs"):
        return {"total": 0, "limit": limit, "offset": offset, "events": []}
    total = await storage.count_audit_logs()
    events = await storage.list_audit_logs(limit=limit, offset=offset)
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "events": events,
    }
