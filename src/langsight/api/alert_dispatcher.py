"""
Shared alert dispatcher — save to DB + fire Slack in one call.

Used by all API routers (traces, reliability, security) so that
every alert path honours the same webhook + alert_types toggles
configured in the dashboard (Settings → Notifications / Alerts page).

Priority mirrors _load_alert_config in alerts_config.py:
  1. DB value (set via dashboard)
  2. .langsight.yaml alerts.slack_webhook
  3. LANGSIGHT_SLACK_WEBHOOK env var

Call fire_alert() from any async router handler — it is always
fail-open: storage errors and Slack delivery failures are logged
but never propagate to the caller.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

import structlog

from langsight.alerts import slack as slack_module
from langsight.alerts.engine import Alert, AlertSeverity, AlertType
from langsight.storage.base import StorageBackend

logger = structlog.get_logger()

# Maps alert_type string values to the toggle key used in the DB
# alert_types dict.  Types absent from this map are always delivered
# (no toggle for them yet — conservative default: fire).
_ALERT_TYPE_TO_TOGGLE: dict[str, str] = {
    AlertType.SERVER_DOWN: "mcp_down",
    AlertType.SERVER_RECOVERED: "mcp_recovered",
    AlertType.AGENT_FAILURE: "agent_failure",
    AlertType.SLO_BREACHED: "slo_breached",
    AlertType.ANOMALY_DETECTED: "anomaly_critical",  # mapped per-severity below
    AlertType.SECURITY_FINDING: "security_critical",  # mapped per-severity below
}

# Severity-aware overrides for alert types that have per-severity toggles.
# Key: (alert_type_value, severity_value) → toggle key
_SEVERITY_TOGGLE: dict[tuple[str, str], str] = {
    (AlertType.ANOMALY_DETECTED, "critical"): "anomaly_critical",
    (AlertType.ANOMALY_DETECTED, "warning"): "anomaly_warning",
    (AlertType.SECURITY_FINDING, "critical"): "security_critical",
    (AlertType.SECURITY_FINDING, "high"): "security_high",
}


async def _load_config(storage: StorageBackend, project_id: str = "") -> dict[str, Any]:
    """Load alert config from DB for the given project (authoritative) with fail-open."""
    if hasattr(storage, "get_alert_config"):
        try:
            db_cfg = await storage.get_alert_config(project_id=project_id)
            if db_cfg:
                return db_cfg
        except Exception:  # noqa: BLE001
            pass
    return {}


def _resolve_webhook(db_cfg: dict[str, Any], config: Any | None) -> str | None:
    """Resolve Slack webhook URL using DB → YAML → env priority."""
    url = db_cfg.get("slack_webhook") or None
    if not url and config is not None:
        alerts_cfg = getattr(config, "alerts", None)
        if alerts_cfg is not None:
            url = getattr(alerts_cfg, "slack_webhook", None) or None
    if not url:
        url = os.environ.get("LANGSIGHT_SLACK_WEBHOOK") or None
    return url


def _toggle_key(alert_type: str, severity: str) -> str | None:
    """Return the alert_types toggle key for this alert, or None if always-on."""
    key = _SEVERITY_TOGGLE.get((alert_type, severity))
    if key:
        return key
    return _ALERT_TYPE_TO_TOGGLE.get(alert_type)


def _is_enabled(alert_types: dict[str, bool], alert_type: str, severity: str) -> bool:
    """Return True if the alert type+severity combo is enabled (default: True)."""
    key = _toggle_key(alert_type, severity)
    if key is None:
        return True  # no toggle → always fire
    return alert_types.get(key, True)  # default True if key not in DB yet


_DEDUP_TTL_SECONDS = 3600  # 1 hour — same alert won't re-fire within this window


async def fire_alert(
    storage: StorageBackend,
    alert_type: str,
    severity: str,
    server_name: str,
    title: str,
    message: str,
    session_id: str | None = None,
    project_id: str = "",
    config: Any | None = None,
    redis: Any | None = None,
) -> bool:
    """Persist an alert to the DB and deliver it to Slack if enabled.

    Returns True if the alert was accepted (toggle on), False if skipped.
    Always fail-open — never raises, never blocks the caller.

    Args:
        storage:      Storage backend (must have save_fired_alert).
        alert_type:   AlertType value string, e.g. "agent_failure".
        severity:     AlertSeverity value string: "critical" | "warning" | "info".
        server_name:  MCP server or agent name associated with the alert.
        title:        Short human-readable title (shown in Slack header).
        message:      Full message body (shown in Slack section block).
        session_id:   Optional session ID for agent-level alerts.
        project_id:   Project scope for the fired_alerts table.
        config:       LangSightConfig instance (for YAML webhook fallback).
        redis:        Optional Redis client. When provided, a SETNX dedup key
                      (langsight:alerts:dedup:{project_id}:{alert_type}:{server_name})
                      is checked before firing — duplicate alerts within 1 hour
                      across all workers are suppressed.
    """
    # Redis-backed deduplication — prevents duplicate Slack blasts across workers.
    # SETNX returns True if the key was newly created (first worker to fire this alert).
    # Subsequent workers within the TTL window get False and skip sending.
    if redis is not None:
        scope = session_id or server_name
        dedup_key = f"langsight:alerts:dedup:{project_id}:{alert_type}:{scope}"
        try:
            is_new: bool = await redis.set(dedup_key, "1", nx=True, ex=_DEDUP_TTL_SECONDS)
            if not is_new:
                logger.debug(
                    "alert_dispatcher.dedup_skipped",
                    alert_type=alert_type,
                    server=server_name,
                    dedup_key=dedup_key,
                )
                return False
        except Exception:  # noqa: BLE001
            pass  # Redis unavailable — fall through and fire (fail-open)

    db_cfg = await _load_config(storage, project_id=project_id)
    alert_types: dict[str, bool] = db_cfg.get("alert_types", {})

    if not _is_enabled(alert_types, alert_type, severity):
        logger.debug(
            "alert_dispatcher.skipped",
            alert_type=alert_type,
            severity=severity,
            server=server_name,
        )
        return False

    # 1. Persist to DB
    alert_id = uuid.uuid4().hex
    if hasattr(storage, "save_fired_alert"):
        try:
            await storage.save_fired_alert(
                alert_id=alert_id,
                alert_type=alert_type,
                severity=severity,
                server_name=server_name,
                title=title,
                message=message,
                session_id=session_id,
                project_id=project_id,
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "alert_dispatcher.save_failed",
                alert_type=alert_type,
                server=server_name,
            )

    # 2. Deliver to Slack
    webhook_url = _resolve_webhook(db_cfg, config)
    if not webhook_url:
        return True  # accepted (toggle on, DB saved), just no Slack delivery

    try:
        sev_enum = AlertSeverity(severity)
    except ValueError:
        sev_enum = AlertSeverity.INFO

    try:
        alert_type_enum = AlertType(alert_type)
    except ValueError:
        alert_type_enum = AlertType.AGENT_FAILURE

    # Build deep-link into the dashboard (LANGSIGHT_DASHBOARD_URL env var)
    dashboard_url = os.environ.get("LANGSIGHT_DASHBOARD_URL", "").rstrip("/")
    context_url: str | None = None
    if dashboard_url:
        if session_id:
            context_url = f"{dashboard_url}/sessions/{session_id}"
        elif alert_type in (
            AlertType.SERVER_DOWN,
            AlertType.SERVER_RECOVERED,
            AlertType.SCHEMA_DRIFT,
        ):
            context_url = f"{dashboard_url}/health"
        elif alert_type in (AlertType.SECURITY_FINDING,):
            context_url = f"{dashboard_url}/security"
        elif alert_type in (AlertType.ANOMALY_DETECTED,):
            context_url = f"{dashboard_url}/alerts"

    alert_obj = Alert(
        server_name=server_name,
        alert_type=alert_type_enum,
        severity=sev_enum,
        title=title,
        message=message,
        context_url=context_url,
    )

    sent = await slack_module.send_alert(webhook_url, alert_obj)
    if sent:
        logger.info(
            "alert_dispatcher.slack_sent",
            alert_type=alert_type,
            severity=severity,
            server=server_name,
        )
    return True
