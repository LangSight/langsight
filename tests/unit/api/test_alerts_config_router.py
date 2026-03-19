"""
Unit tests for the alerts configuration router (storage-backed implementation).

Covers:
- GET  /api/alerts/config  — loads from DB, falls back to env/yaml
- POST /api/alerts/config  — persists to DB via save_alert_config
- POST /api/alerts/test    — sends Slack test using webhook from DB/env
- GET  /api/audit/logs     — reads from DB via list_audit_logs
- append_audit() helper    — schedules async DB write when storage provided
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import yaml
from httpx import ASGITransport, AsyncClient

from langsight.api.main import create_app
from langsight.api.routers.alerts_config import (
    _DEFAULT_ALERT_TYPES,
    append_audit,
)
from langsight.config import load_config

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    cfg = tmp_path / ".langsight.yaml"
    cfg.write_text(yaml.dump({"servers": []}))
    return cfg


@pytest.fixture
def mock_storage() -> MagicMock:
    """Mock storage with all alert/audit methods pre-configured."""
    s = MagicMock()
    s.close = AsyncMock()
    s.list_api_keys = AsyncMock(return_value=[])   # disables auth
    s.get_alert_config = AsyncMock(return_value=None)  # no saved config
    s.save_alert_config = AsyncMock()
    s.append_audit_log = AsyncMock()
    s.list_audit_logs = AsyncMock(return_value=[])
    s.count_audit_logs = AsyncMock(return_value=0)
    return s


@pytest.fixture
async def client(config_file: Path, mock_storage: MagicMock):
    app = create_app(config_path=config_file)
    app.state.storage = mock_storage
    app.state.config = load_config(config_file)
    app.state.config_path = config_file

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, app, mock_storage


# ---------------------------------------------------------------------------
# GET /api/alerts/config
# ---------------------------------------------------------------------------


class TestGetAlertsConfig:
    async def test_returns_default_alert_types_when_no_db_config(self, client) -> None:
        c, app, storage = client
        storage.get_alert_config = AsyncMock(return_value=None)

        response = await c.get("/api/alerts/config")

        assert response.status_code == 200
        data = response.json()
        assert data["alert_types"] == _DEFAULT_ALERT_TYPES

    async def test_webhook_configured_is_false_when_no_webhook(self, client) -> None:
        c, app, storage = client
        storage.get_alert_config = AsyncMock(return_value=None)

        response = await c.get("/api/alerts/config")

        assert response.status_code == 200
        assert response.json()["webhook_configured"] is False
        assert response.json()["slack_webhook"] is None

    async def test_returns_webhook_from_db_config(self, client) -> None:
        c, app, storage = client
        storage.get_alert_config = AsyncMock(return_value={
            "slack_webhook": "https://hooks.slack.com/from-db",
            "alert_types": {},
        })

        response = await c.get("/api/alerts/config")

        assert response.status_code == 200
        data = response.json()
        assert data["slack_webhook"] == "https://hooks.slack.com/from-db"
        assert data["webhook_configured"] is True

    async def test_returns_webhook_from_env_var_when_no_db_config(self, client, monkeypatch) -> None:
        c, app, storage = client
        storage.get_alert_config = AsyncMock(return_value=None)
        monkeypatch.setenv("LANGSIGHT_SLACK_WEBHOOK", "https://hooks.slack.com/from-env")

        response = await c.get("/api/alerts/config")

        data = response.json()
        assert data["slack_webhook"] == "https://hooks.slack.com/from-env"
        assert data["webhook_configured"] is True

    async def test_db_webhook_overrides_env_var(self, client, monkeypatch) -> None:
        c, app, storage = client
        storage.get_alert_config = AsyncMock(return_value={
            "slack_webhook": "https://hooks.slack.com/from-db",
            "alert_types": {},
        })
        monkeypatch.setenv("LANGSIGHT_SLACK_WEBHOOK", "https://hooks.slack.com/from-env")

        response = await c.get("/api/alerts/config")

        assert response.json()["slack_webhook"] == "https://hooks.slack.com/from-db"

    async def test_db_alert_types_merged_with_defaults(self, client) -> None:
        c, app, storage = client
        storage.get_alert_config = AsyncMock(return_value={
            "slack_webhook": None,
            "alert_types": {"mcp_down": False},
        })

        response = await c.get("/api/alerts/config")

        alert_types = response.json()["alert_types"]
        assert alert_types["mcp_down"] is False          # DB value
        assert "agent_failure" in alert_types             # default still present

    async def test_response_contains_all_default_alert_type_keys(self, client) -> None:
        c, app, storage = client
        storage.get_alert_config = AsyncMock(return_value=None)

        response = await c.get("/api/alerts/config")

        keys = set(response.json()["alert_types"].keys())
        assert keys == set(_DEFAULT_ALERT_TYPES.keys())


# ---------------------------------------------------------------------------
# POST /api/alerts/config
# ---------------------------------------------------------------------------


class TestSaveAlertsConfig:
    async def test_saves_webhook_to_db(self, client) -> None:
        c, app, storage = client
        response = await c.post(
            "/api/alerts/config",
            json={"slack_webhook": "https://hooks.slack.com/new"},
        )

        assert response.status_code == 200
        storage.save_alert_config.assert_called_once()
        call_args = storage.save_alert_config.call_args
        assert call_args[0][0] == "https://hooks.slack.com/new"  # first positional arg

    async def test_response_reflects_saved_webhook(self, client) -> None:
        c, app, storage = client
        response = await c.post(
            "/api/alerts/config",
            json={"slack_webhook": "https://hooks.slack.com/saved"},
        )

        data = response.json()
        assert data["webhook_configured"] is True
        assert data["slack_webhook"] == "https://hooks.slack.com/saved"

    async def test_saves_alert_type_toggles(self, client) -> None:
        c, app, storage = client
        response = await c.post(
            "/api/alerts/config",
            json={"alert_types": {"mcp_down": False, "agent_failure": True}},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["alert_types"]["mcp_down"] is False
        assert data["alert_types"]["agent_failure"] is True

    async def test_merges_with_existing_types(self, client) -> None:
        """Only keys in the request body should change; others remain as defaults."""
        c, app, storage = client
        response = await c.post(
            "/api/alerts/config",
            json={"alert_types": {"anomaly_warning": True}},
        )

        result_types = response.json()["alert_types"]
        assert result_types["anomaly_warning"] is True
        assert "mcp_down" in result_types   # default key still present

    async def test_empty_body_does_not_error(self, client) -> None:
        c, _, _ = client
        response = await c.post("/api/alerts/config", json={})

        assert response.status_code == 200

    async def test_save_alert_config_called_even_with_empty_body(self, client) -> None:
        c, _, storage = client
        await c.post("/api/alerts/config", json={})

        storage.save_alert_config.assert_called_once()


# ---------------------------------------------------------------------------
# POST /api/alerts/test
# ---------------------------------------------------------------------------


class TestTestSlackWebhook:
    async def test_returns_400_when_no_webhook_configured(self, client) -> None:
        c, app, storage = client
        storage.get_alert_config = AsyncMock(return_value=None)

        response = await c.post("/api/alerts/test")

        assert response.status_code == 400
        assert "webhook" in response.json()["detail"].lower()

    async def test_returns_200_when_webhook_present(self, client) -> None:
        c, app, storage = client
        storage.get_alert_config = AsyncMock(return_value={
            "slack_webhook": "https://hooks.slack.com/ok",
            "alert_types": {},
        })

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            response = await c.post("/api/alerts/test")

        assert response.status_code == 200
        assert response.json()["ok"] is True

    async def test_returns_502_on_slack_error(self, client) -> None:
        c, app, storage = client
        storage.get_alert_config = AsyncMock(return_value={
            "slack_webhook": "https://hooks.slack.com/bad",
            "alert_types": {},
        })

        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            response = await c.post("/api/alerts/test")

        assert response.status_code == 502

    async def test_posts_to_the_configured_url(self, client) -> None:
        c, app, storage = client
        webhook_url = "https://hooks.slack.com/services/T/B/X"
        storage.get_alert_config = AsyncMock(return_value={
            "slack_webhook": webhook_url,
            "alert_types": {},
        })

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            await c.post("/api/alerts/test")

        mock_client_instance.post.assert_called_once()
        assert mock_client_instance.post.call_args[0][0] == webhook_url


# ---------------------------------------------------------------------------
# GET /api/audit/logs
# ---------------------------------------------------------------------------


class TestListAuditLogs:
    async def test_returns_empty_list_when_no_events(self, client) -> None:
        c, _, storage = client
        storage.list_audit_logs = AsyncMock(return_value=[])
        storage.count_audit_logs = AsyncMock(return_value=0)

        response = await c.get("/api/audit/logs")

        assert response.status_code == 200
        data = response.json()
        assert data["events"] == []
        assert data["total"] == 0

    async def test_returns_events_from_db(self, client) -> None:
        c, _, storage = client
        db_events = [
            {"id": 3, "timestamp": "2026-01-03T12:00:00+00:00", "event": "evt_third",
             "user_id": "u1", "ip": "127.0.0.1", "details": {}},
            {"id": 2, "timestamp": "2026-01-02T12:00:00+00:00", "event": "evt_second",
             "user_id": "u1", "ip": "127.0.0.1", "details": {}},
            {"id": 1, "timestamp": "2026-01-01T12:00:00+00:00", "event": "evt_first",
             "user_id": "u1", "ip": "127.0.0.1", "details": {}},
        ]
        storage.list_audit_logs = AsyncMock(return_value=db_events)
        storage.count_audit_logs = AsyncMock(return_value=3)

        response = await c.get("/api/audit/logs")

        data = response.json()
        assert data["total"] == 3
        assert len(data["events"]) == 3
        assert data["events"][0]["event"] == "evt_third"

    async def test_passes_limit_and_offset_to_storage(self, client) -> None:
        c, _, storage = client
        storage.list_audit_logs = AsyncMock(return_value=[])
        storage.count_audit_logs = AsyncMock(return_value=100)

        await c.get("/api/audit/logs?limit=10&offset=20")

        storage.list_audit_logs.assert_called_once_with(limit=10, offset=20)

    async def test_total_comes_from_count_not_page_size(self, client) -> None:
        c, _, storage = client
        storage.list_audit_logs = AsyncMock(return_value=[{"id": 1, "event": "e",
            "timestamp": "2026-01-01T00:00:00+00:00", "user_id": "u", "ip": "x", "details": {}}])
        storage.count_audit_logs = AsyncMock(return_value=500)

        response = await c.get("/api/audit/logs?limit=1")

        assert response.json()["total"] == 500
        assert len(response.json()["events"]) == 1


# ---------------------------------------------------------------------------
# append_audit() helper
# ---------------------------------------------------------------------------


class TestAppendAudit:
    async def test_schedules_db_write_when_storage_provided(self) -> None:
        """append_audit with a storage object should schedule append_audit_log."""
        import asyncio

        storage = MagicMock()
        storage.append_audit_log = AsyncMock()

        # Run inside an event loop so create_task works
        append_audit("test.event", user_id="u1", ip="1.2.3.4",
                     details={"k": "v"}, storage=storage)

        # Drain the event loop to allow the task to execute
        await asyncio.sleep(0)

        storage.append_audit_log.assert_called_once_with(
            "test.event", "u1", "1.2.3.4", {"k": "v"}
        )

    async def test_defaults_user_id_and_ip(self) -> None:
        import asyncio

        storage = MagicMock()
        storage.append_audit_log = AsyncMock()

        append_audit("evt", user_id=None, ip=None, storage=storage)
        await asyncio.sleep(0)

        call_args = storage.append_audit_log.call_args[0]
        assert call_args[1] == "system"
        assert call_args[2] == "unknown"

    def test_no_error_without_storage(self) -> None:
        """append_audit without storage should not raise even outside a running loop."""
        # Just verify it doesn't crash
        append_audit("test.no_storage", user_id="u", ip="1.1.1.1")

    def test_no_error_when_storage_lacks_method(self) -> None:
        """Storage without append_audit_log is silently skipped."""
        storage = MagicMock(spec=[])  # no methods
        append_audit("test.no_method", user_id="u", ip="1.1.1.1", storage=storage)
