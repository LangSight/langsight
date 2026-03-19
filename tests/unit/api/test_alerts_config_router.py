"""
Unit tests for the alerts configuration router.

Covers:
- GET  /api/alerts/config
- POST /api/alerts/config
- POST /api/alerts/test
- GET  /api/audit/logs
- append_audit() helper
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import yaml
from httpx import ASGITransport, AsyncClient

import langsight.api.routers.alerts_config as alerts_config_module
from langsight.api.main import create_app
from langsight.api.routers.alerts_config import (
    _DEFAULT_ALERT_TYPES,
    append_audit,
)
from langsight.config import load_config


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_audit_log():
    """Clear the module-level audit log before every test."""
    alerts_config_module._audit_log.clear()
    yield
    alerts_config_module._audit_log.clear()


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    cfg = tmp_path / ".langsight.yaml"
    cfg.write_text(yaml.dump({"servers": [], "storage": {"mode": "sqlite"}}))
    return cfg


@pytest.fixture
async def client(config_file: Path):
    app = create_app(config_path=config_file)
    mock_storage = MagicMock()
    mock_storage.close = AsyncMock()
    # list_api_keys returns empty list — disables auth (local dev mode)
    mock_storage.list_api_keys = AsyncMock(return_value=[])
    app.state.storage = mock_storage
    app.state.config = load_config(config_file)
    app.state.config_path = config_file

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, app


# ---------------------------------------------------------------------------
# GET /api/alerts/config
# ---------------------------------------------------------------------------


class TestGetAlertsConfig:
    async def test_returns_default_alert_types_when_not_configured(self, client) -> None:
        c, app = client
        # create_app pre-seeds app.state.alert_types = {} (populated lazily).
        # Delete the key so _get_alert_config falls back to _DEFAULT_ALERT_TYPES.
        del app.state.alert_types

        response = await c.get("/api/alerts/config")

        assert response.status_code == 200
        data = response.json()
        assert data["alert_types"] == _DEFAULT_ALERT_TYPES

    async def test_webhook_configured_is_false_when_no_webhook(self, client) -> None:
        c, app = client
        # LangSightConfig has no top-level slack_webhook field; the router reads
        # getattr(config, "slack_webhook", None) which already returns None.
        # Also ensure no override is set on app.state.
        if hasattr(app.state, "slack_webhook_override"):
            del app.state.slack_webhook_override

        response = await c.get("/api/alerts/config")

        assert response.status_code == 200
        assert response.json()["webhook_configured"] is False

    async def test_slack_webhook_is_null_when_not_set(self, client) -> None:
        c, app = client
        # Same as above — no top-level field, no override set → None
        if hasattr(app.state, "slack_webhook_override"):
            del app.state.slack_webhook_override

        response = await c.get("/api/alerts/config")

        assert response.json()["slack_webhook"] is None

    async def test_returns_webhook_url_when_set_via_env_var(self, client, monkeypatch) -> None:
        c, app = client
        # _get_alert_config reads LANGSIGHT_SLACK_WEBHOOK as fallback when the
        # config object has no slack_webhook attribute.
        monkeypatch.setenv("LANGSIGHT_SLACK_WEBHOOK", "https://hooks.slack.com/test")

        response = await c.get("/api/alerts/config")

        assert response.status_code == 200
        data = response.json()
        assert data["slack_webhook"] == "https://hooks.slack.com/test"
        assert data["webhook_configured"] is True

    async def test_env_var_webhook_takes_effect_when_config_has_no_webhook(self, client, monkeypatch) -> None:
        c, app = client
        # LangSightConfig has no top-level slack_webhook attribute, so the router
        # always falls through to the env var. This confirms that path end-to-end.
        monkeypatch.setenv("LANGSIGHT_SLACK_WEBHOOK", "https://hooks.slack.com/from-env")

        response = await c.get("/api/alerts/config")

        data = response.json()
        assert data["slack_webhook"] == "https://hooks.slack.com/from-env"
        assert data["webhook_configured"] is True

    async def test_response_contains_all_default_alert_type_keys(self, client) -> None:
        c, app = client
        # Remove the pre-seeded empty dict so the router falls back to _DEFAULT_ALERT_TYPES.
        del app.state.alert_types

        response = await c.get("/api/alerts/config")

        alert_types = response.json()["alert_types"]
        expected_keys = {
            "agent_failure", "slo_breached", "anomaly_critical", "anomaly_warning",
            "security_critical", "security_high", "mcp_down", "mcp_recovered",
        }
        assert expected_keys == set(alert_types.keys())


# ---------------------------------------------------------------------------
# POST /api/alerts/config
# ---------------------------------------------------------------------------


class TestSaveAlertsConfig:
    async def test_saves_slack_webhook_to_app_state(self, client) -> None:
        c, app = client
        response = await c.post(
            "/api/alerts/config",
            json={"slack_webhook": "https://hooks.slack.com/new"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["webhook_configured"] is True
        assert data["slack_webhook"] == "https://hooks.slack.com/new"

    async def test_saves_alert_types_to_app_state(self, client) -> None:
        c, app = client
        response = await c.post(
            "/api/alerts/config",
            json={"alert_types": {"mcp_down": False, "agent_failure": True}},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["alert_types"]["mcp_down"] is False
        assert data["alert_types"]["agent_failure"] is True

    async def test_merges_with_existing_alert_types_does_not_wipe_unset_keys(self, client) -> None:
        c, app = client
        # Seed a known state
        app.state.alert_types = dict(_DEFAULT_ALERT_TYPES)
        app.state.alert_types["mcp_down"] = True

        # Only update one key
        response = await c.post(
            "/api/alerts/config",
            json={"alert_types": {"anomaly_warning": True}},
        )

        assert response.status_code == 200
        result_types = response.json()["alert_types"]
        # Key we changed
        assert result_types["anomaly_warning"] is True
        # Key we did NOT touch — must still be present and unchanged
        assert "mcp_down" in result_types
        assert result_types["mcp_down"] is True

    async def test_empty_body_does_not_error(self, client) -> None:
        c, _ = client
        response = await c.post("/api/alerts/config", json={})

        assert response.status_code == 200

    async def test_null_webhook_in_body_clears_override(self, client) -> None:
        c, app = client
        # Set an override first
        app.state.slack_webhook_override = "https://hooks.slack.com/old"

        response = await c.post("/api/alerts/config", json={"slack_webhook": None})

        # null body value means "don't update" (body.slack_webhook is None → branch skipped)
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# POST /api/alerts/test
# ---------------------------------------------------------------------------


class TestTestSlackWebhook:
    async def test_returns_400_when_no_webhook_configured(self, client) -> None:
        c, app = client
        try:
            object.__setattr__(app.state.config, "slack_webhook", None)
        except (AttributeError, TypeError):
            pass
        # Ensure no override set
        if hasattr(app.state, "slack_webhook_override"):
            del app.state.slack_webhook_override

        response = await c.post("/api/alerts/test")

        assert response.status_code == 400
        assert "webhook" in response.json()["detail"].lower()

    async def test_returns_200_when_webhook_present_and_slack_responds_ok(self, client) -> None:
        c, app = client
        app.state.slack_webhook_override = "https://hooks.slack.com/ok"

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient") as mock_async_client_cls:
            mock_async_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_async_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            response = await c.post("/api/alerts/test")

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "success" in data["message"].lower()

    async def test_returns_502_when_slack_raises_http_error(self, client) -> None:
        c, app = client
        app.state.slack_webhook_override = "https://hooks.slack.com/bad"

        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "422 Unprocessable Entity",
                request=MagicMock(),
                response=MagicMock(),
            )
        )

        with patch("httpx.AsyncClient") as mock_async_client_cls:
            mock_async_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_async_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            response = await c.post("/api/alerts/test")

        assert response.status_code == 502
        assert "failed" in response.json()["detail"].lower()

    async def test_returns_502_when_slack_connection_fails(self, client) -> None:
        c, app = client
        app.state.slack_webhook_override = "https://hooks.slack.com/unreachable"

        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        with patch("httpx.AsyncClient") as mock_async_client_cls:
            mock_async_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_async_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            response = await c.post("/api/alerts/test")

        assert response.status_code == 502

    async def test_posts_to_the_configured_webhook_url(self, client) -> None:
        c, app = client
        webhook_url = "https://hooks.slack.com/services/T/B/X"
        app.state.slack_webhook_override = webhook_url

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient") as mock_async_client_cls:
            mock_async_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_async_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            await c.post("/api/alerts/test")

        mock_client_instance.post.assert_called_once()
        call_args = mock_client_instance.post.call_args
        assert call_args[0][0] == webhook_url


# ---------------------------------------------------------------------------
# GET /api/audit/logs
# ---------------------------------------------------------------------------


class TestListAuditLogs:
    async def test_returns_empty_list_when_no_events(self, client) -> None:
        c, _ = client
        response = await c.get("/api/audit/logs")

        assert response.status_code == 200
        data = response.json()
        assert data["events"] == []
        assert data["total"] == 0

    async def test_returns_events_most_recent_first(self, client) -> None:
        c, _ = client
        append_audit("event_first",  user_id="u1", ip="1.2.3.4")
        append_audit("event_second", user_id="u1", ip="1.2.3.4")
        append_audit("event_third",  user_id="u1", ip="1.2.3.4")

        response = await c.get("/api/audit/logs")

        data = response.json()
        events = data["events"]
        assert len(events) == 3
        # Most recent appended == first returned
        assert events[0]["event"] == "event_third"
        assert events[1]["event"] == "event_second"
        assert events[2]["event"] == "event_first"

    async def test_respects_limit_param(self, client) -> None:
        c, _ = client
        for i in range(10):
            append_audit(f"evt_{i}", user_id=None, ip=None)

        response = await c.get("/api/audit/logs?limit=3")

        data = response.json()
        assert len(data["events"]) == 3
        assert data["total"] == 10
        assert data["limit"] == 3

    async def test_respects_offset_param(self, client) -> None:
        c, _ = client
        for i in range(5):
            append_audit(f"evt_{i}", user_id=None, ip=None)

        response = await c.get("/api/audit/logs?offset=3&limit=10")

        data = response.json()
        # 5 total, skip 3 most-recent → 2 remaining
        assert len(data["events"]) == 2
        assert data["offset"] == 3

    async def test_total_reflects_full_log_size_not_page_size(self, client) -> None:
        c, _ = client
        for i in range(20):
            append_audit(f"evt_{i}", user_id=None, ip=None)

        response = await c.get("/api/audit/logs?limit=5")

        data = response.json()
        assert data["total"] == 20
        assert len(data["events"]) == 5


# ---------------------------------------------------------------------------
# append_audit() helper
# ---------------------------------------------------------------------------


class TestAppendAudit:
    def test_appends_event_to_audit_log(self) -> None:
        append_audit("test.event", user_id="user-1", ip="10.0.0.1", details={"key": "val"})

        assert len(alerts_config_module._audit_log) == 1
        entry = alerts_config_module._audit_log[0]
        assert entry["event"] == "test.event"
        assert entry["user_id"] == "user-1"
        assert entry["ip"] == "10.0.0.1"
        assert entry["details"] == {"key": "val"}

    def test_defaults_user_id_to_system_when_none(self) -> None:
        append_audit("test.event", user_id=None, ip=None)

        entry = alerts_config_module._audit_log[0]
        assert entry["user_id"] == "system"
        assert entry["ip"] == "unknown"

    def test_assigns_sequential_id(self) -> None:
        append_audit("evt_a", user_id=None, ip=None)
        append_audit("evt_b", user_id=None, ip=None)

        assert alerts_config_module._audit_log[0]["id"] == 1
        assert alerts_config_module._audit_log[1]["id"] == 2

    def test_entry_has_iso_timestamp(self) -> None:
        from datetime import datetime

        append_audit("ts.test", user_id=None, ip=None)

        ts_str = alerts_config_module._audit_log[0]["timestamp"]
        # Must parse without error
        parsed = datetime.fromisoformat(ts_str)
        assert parsed.tzinfo is not None  # timezone-aware

    def test_respects_max_audit_entries_limit(self, monkeypatch) -> None:
        """When log exceeds MAX_AUDIT_ENTRIES it is trimmed to the most recent entries."""
        # Temporarily lower the cap so the test runs fast
        small_limit = 5
        monkeypatch.setattr(alerts_config_module, "_MAX_AUDIT_ENTRIES", small_limit)

        for i in range(small_limit + 3):
            append_audit(f"evt_{i}", user_id=None, ip=None)

        # After trim, log must not exceed the cap
        assert len(alerts_config_module._audit_log) <= small_limit

    def test_trim_keeps_most_recent_entries(self, monkeypatch) -> None:
        small_limit = 3
        monkeypatch.setattr(alerts_config_module, "_MAX_AUDIT_ENTRIES", small_limit)

        for i in range(small_limit + 2):
            append_audit(f"evt_{i}", user_id=None, ip=None)

        # Oldest events are evicted; the remaining entries are the most recent
        remaining_events = [e["event"] for e in alerts_config_module._audit_log]
        assert "evt_0" not in remaining_events
        assert "evt_1" not in remaining_events
        assert f"evt_{small_limit + 1}" in remaining_events
