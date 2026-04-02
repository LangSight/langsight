"""Tests for embedded monitor settings and lifespan behaviour (v0.9.0).

Covers:
- Settings.monitor_enabled / monitor_interval_seconds defaults and env overrides
- Lifespan starts monitor task when enabled + servers present
- Lifespan skips monitor when disabled
- Lifespan skips monitor when no servers configured
- API stays responsive while monitor loop is active
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml
from fastapi.testclient import TestClient

from langsight.config import Settings

# ---------------------------------------------------------------------------
# Settings field tests
# ---------------------------------------------------------------------------


class TestMonitorSettings:
    def test_monitor_enabled_default_is_true(self) -> None:
        s = Settings()
        assert s.monitor_enabled is True

    def test_monitor_interval_default_is_60(self) -> None:
        s = Settings()
        assert s.monitor_interval_seconds == 60

    def test_monitor_enabled_false_via_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LANGSIGHT_MONITOR_ENABLED", "false")
        s = Settings()
        assert s.monitor_enabled is False

    def test_monitor_enabled_true_via_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LANGSIGHT_MONITOR_ENABLED", "true")
        s = Settings()
        assert s.monitor_enabled is True

    def test_monitor_interval_override_via_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LANGSIGHT_MONITOR_INTERVAL_SECONDS", "120")
        s = Settings()
        assert s.monitor_interval_seconds == 120

    def test_monitor_interval_30s_via_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LANGSIGHT_MONITOR_INTERVAL_SECONDS", "30")
        s = Settings()
        assert s.monitor_interval_seconds == 30

    def test_settings_are_independent_instances(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Each Settings() reads env vars fresh — no shared state."""
        monkeypatch.setenv("LANGSIGHT_MONITOR_ENABLED", "false")
        s1 = Settings()
        monkeypatch.setenv("LANGSIGHT_MONITOR_ENABLED", "true")
        s2 = Settings()
        assert s1.monitor_enabled is False
        assert s2.monitor_enabled is True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config_file(tmp_path: Path, *, with_servers: bool = True) -> Path:
    servers = (
        [{"name": "test-pg", "transport": "stdio", "command": "python server.py"}]
        if with_servers
        else []
    )
    cfg = tmp_path / ".langsight.yaml"
    cfg.write_text(yaml.dump({"servers": servers}))
    return cfg


def _make_storage() -> MagicMock:
    """Mock storage with all async methods lifespan calls during bootstrap."""
    s = MagicMock()
    s.close = AsyncMock()
    s.list_model_pricing = AsyncMock(return_value=[])
    s.get_user_by_email = AsyncMock(return_value=None)
    s.create_user = AsyncMock()
    s.list_api_keys = AsyncMock(return_value=[])
    s.get_project_by_slug = AsyncMock(return_value=None)
    s.create_project = AsyncMock()
    s.add_member = AsyncMock()
    s.list_projects = AsyncMock(return_value=[])
    s.count_users = AsyncMock(return_value=0)
    s.list_users = AsyncMock(return_value=[])
    # HealthChecker storage calls
    s.save_health_result = AsyncMock()
    s.upsert_server_metadata = AsyncMock()
    s.upsert_server_tools = AsyncMock()
    s.get_latest_schema_hash = AsyncMock(return_value=None)
    s.save_schema_snapshot = AsyncMock()
    s.get_server_tools = AsyncMock(return_value=[])
    return s


# ---------------------------------------------------------------------------
# Lifespan / embedded monitor integration tests
#
# Use fastapi.testclient.TestClient (sync) which correctly sends ASGI lifespan
# startup/shutdown events. httpx.ASGITransport does NOT send lifespan events.
# ---------------------------------------------------------------------------


def test_liveness_works_with_monitor_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """API is reachable while the embedded monitor loop is active."""
    monkeypatch.setenv("LANGSIGHT_MONITOR_ENABLED", "true")
    monkeypatch.setenv("LANGSIGHT_MONITOR_INTERVAL_SECONDS", "9999")

    cfg = _make_config_file(tmp_path, with_servers=True)
    mock_storage = _make_storage()

    from langsight.api.main import create_app

    with (
        patch("langsight.api.main.open_storage", return_value=mock_storage),
        patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping,
    ):
        mock_ping.return_value = (10.0, [])
        app = create_app(config_path=cfg)
        with TestClient(app, raise_server_exceptions=True) as client:
            resp = client.get("/api/liveness")
            assert resp.status_code == 200
            assert resp.json()["status"] == "alive"


def test_liveness_works_with_monitor_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """API is reachable when embedded monitor is disabled."""
    monkeypatch.setenv("LANGSIGHT_MONITOR_ENABLED", "false")

    cfg = _make_config_file(tmp_path, with_servers=True)
    mock_storage = _make_storage()

    from langsight.api.main import create_app

    with patch("langsight.api.main.open_storage", return_value=mock_storage):
        app = create_app(config_path=cfg)
        with TestClient(app) as client:
            resp = client.get("/api/liveness")
            assert resp.status_code == 200


def test_liveness_works_with_no_servers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """API is reachable and monitor is skipped when config has no servers."""
    monkeypatch.setenv("LANGSIGHT_MONITOR_ENABLED", "true")

    cfg = _make_config_file(tmp_path, with_servers=False)
    mock_storage = _make_storage()

    from langsight.api.main import create_app

    with patch("langsight.api.main.open_storage", return_value=mock_storage):
        app = create_app(config_path=cfg)
        with TestClient(app) as client:
            resp = client.get("/api/liveness")
            assert resp.status_code == 200


def test_monitor_calls_check_many_when_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When enabled + servers present, the monitor loop calls check_many."""
    monkeypatch.setenv("LANGSIGHT_MONITOR_ENABLED", "true")
    monkeypatch.setenv("LANGSIGHT_MONITOR_INTERVAL_SECONDS", "9999")

    cfg = _make_config_file(tmp_path, with_servers=True)
    mock_storage = _make_storage()
    check_many_calls: list[int] = []

    async def fake_check_many(self, servers, **_):  # type: ignore[override]
        check_many_calls.append(len(servers))
        return []

    from langsight.api.main import create_app

    with (
        patch("langsight.api.main.open_storage", return_value=mock_storage),
        patch("langsight.health.checker.HealthChecker.check_many", new=fake_check_many),
    ):
        app = create_app(config_path=cfg)
        with TestClient(app) as client:
            import time  # noqa: PLC0415
            time.sleep(0.1)  # give monitor loop one iteration
            resp = client.get("/api/liveness")
            assert resp.status_code == 200

    assert len(check_many_calls) >= 1, "check_many should have been called at least once"
    assert check_many_calls[0] == 1, "called with 1 server from config"


def test_monitor_not_called_when_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When monitor is disabled, check_many is never called."""
    monkeypatch.setenv("LANGSIGHT_MONITOR_ENABLED", "false")

    cfg = _make_config_file(tmp_path, with_servers=True)
    mock_storage = _make_storage()
    check_many_calls: list = []

    async def fake_check_many(self, servers, **_):  # type: ignore[override]
        check_many_calls.append(servers)
        return []

    from langsight.api.main import create_app

    with (
        patch("langsight.api.main.open_storage", return_value=mock_storage),
        patch("langsight.health.checker.HealthChecker.check_many", new=fake_check_many),
    ):
        app = create_app(config_path=cfg)
        with TestClient(app) as client:
            import time  # noqa: PLC0415
            time.sleep(0.05)
            client.get("/api/liveness")

    assert len(check_many_calls) == 0


def test_monitor_not_called_when_no_servers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When config has no servers, check_many is never called."""
    monkeypatch.setenv("LANGSIGHT_MONITOR_ENABLED", "true")

    cfg = _make_config_file(tmp_path, with_servers=False)
    mock_storage = _make_storage()
    check_many_calls: list = []

    async def fake_check_many(self, servers, **_):  # type: ignore[override]
        check_many_calls.append(servers)
        return []

    from langsight.api.main import create_app

    with (
        patch("langsight.api.main.open_storage", return_value=mock_storage),
        patch("langsight.health.checker.HealthChecker.check_many", new=fake_check_many),
    ):
        app = create_app(config_path=cfg)
        with TestClient(app) as client:
            import time  # noqa: PLC0415
            time.sleep(0.05)
            client.get("/api/liveness")

    assert len(check_many_calls) == 0
