"""Unit tests for the shared alert dispatcher."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from langsight.api.alert_dispatcher import (
    _is_enabled,
    _resolve_webhook,
    _toggle_key,
    fire_alert,
)


# ---------------------------------------------------------------------------
# _toggle_key
# ---------------------------------------------------------------------------

class TestToggleKey:
    def test_server_down_maps_to_mcp_down(self) -> None:
        assert _toggle_key("server_down", "critical") == "mcp_down"

    def test_server_recovered_maps_to_mcp_recovered(self) -> None:
        assert _toggle_key("server_recovered", "info") == "mcp_recovered"

    def test_anomaly_critical(self) -> None:
        assert _toggle_key("anomaly_detected", "critical") == "anomaly_critical"

    def test_anomaly_warning(self) -> None:
        assert _toggle_key("anomaly_detected", "warning") == "anomaly_warning"

    def test_security_critical(self) -> None:
        assert _toggle_key("security_finding", "critical") == "security_critical"

    def test_security_high(self) -> None:
        assert _toggle_key("security_finding", "high") == "security_high"

    def test_unknown_type_returns_none(self) -> None:
        assert _toggle_key("loop_detected", "warning") is None


# ---------------------------------------------------------------------------
# _is_enabled
# ---------------------------------------------------------------------------

class TestIsEnabled:
    def test_enabled_when_toggle_true(self) -> None:
        assert _is_enabled({"mcp_down": True}, "server_down", "critical") is True

    def test_disabled_when_toggle_false(self) -> None:
        assert _is_enabled({"mcp_down": False}, "server_down", "critical") is False

    def test_defaults_true_when_key_missing(self) -> None:
        assert _is_enabled({}, "server_down", "critical") is True

    def test_always_on_for_unknown_type(self) -> None:
        # Types without a toggle key are always delivered
        assert _is_enabled({"mcp_down": False}, "loop_detected", "warning") is True


# ---------------------------------------------------------------------------
# _resolve_webhook
# ---------------------------------------------------------------------------

class TestResolveWebhook:
    def test_db_wins(self) -> None:
        db_cfg = {"slack_webhook": "https://hooks.slack.com/db"}
        assert _resolve_webhook(db_cfg, None) == "https://hooks.slack.com/db"

    def test_falls_back_to_yaml(self) -> None:
        config = MagicMock()
        config.alerts.slack_webhook = "https://hooks.slack.com/yaml"
        assert _resolve_webhook({}, config) == "https://hooks.slack.com/yaml"

    def test_falls_back_to_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LANGSIGHT_SLACK_WEBHOOK", "https://hooks.slack.com/env")
        assert _resolve_webhook({}, None) == "https://hooks.slack.com/env"

    def test_returns_none_when_nothing_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("LANGSIGHT_SLACK_WEBHOOK", raising=False)
        assert _resolve_webhook({}, None) is None


# ---------------------------------------------------------------------------
# fire_alert
# ---------------------------------------------------------------------------

def _mock_storage(db_cfg: dict | None = None) -> MagicMock:
    s = MagicMock()
    s.get_alert_config = AsyncMock(return_value=db_cfg)
    s.save_fired_alert = AsyncMock()
    return s


class TestFireAlert:
    @pytest.mark.asyncio
    async def test_saves_to_db_and_sends_slack(self) -> None:
        storage = _mock_storage({
            "slack_webhook": "https://hooks.slack.com/x",
            "alert_types": {"agent_failure": True},
        })
        with patch("langsight.api.alert_dispatcher.slack_module.send_alert", new_callable=AsyncMock, return_value=True) as mock_send:
            await fire_alert(
                storage=storage,
                alert_type="agent_failure",
                severity="critical",
                server_name="my-agent",
                title="Agent failed",
                message="Session xyz ended with tool_failure.",
            )
        storage.save_fired_alert.assert_awaited_once()
        mock_send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skips_slack_when_type_disabled(self) -> None:
        storage = _mock_storage({
            "slack_webhook": "https://hooks.slack.com/x",
            "alert_types": {"agent_failure": False},
        })
        with patch("langsight.api.alert_dispatcher.slack_module.send_alert", new_callable=AsyncMock) as mock_send:
            await fire_alert(
                storage=storage,
                alert_type="agent_failure",
                severity="critical",
                server_name="my-agent",
                title="Agent failed",
                message="Session xyz ended with tool_failure.",
            )
        # Disabled type → skipped before save_fired_alert
        storage.save_fired_alert.assert_not_awaited()
        mock_send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_saves_to_db_but_no_slack_when_no_webhook(self) -> None:
        storage = _mock_storage({
            "slack_webhook": None,
            "alert_types": {"mcp_down": True},
        })
        with patch("langsight.api.alert_dispatcher.slack_module.send_alert", new_callable=AsyncMock) as mock_send:
            await fire_alert(
                storage=storage,
                alert_type="server_down",
                severity="critical",
                server_name="pg-mcp",
                title="pg-mcp is DOWN",
                message="3 consecutive failures.",
            )
        storage.save_fired_alert.assert_awaited_once()
        mock_send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_fails_open_when_db_raises(self) -> None:
        storage = MagicMock()
        storage.get_alert_config = AsyncMock(side_effect=RuntimeError("db down"))
        storage.save_fired_alert = AsyncMock()
        # Should not raise — fail-open
        with patch("langsight.api.alert_dispatcher.slack_module.send_alert", new_callable=AsyncMock):
            await fire_alert(
                storage=storage,
                alert_type="agent_failure",
                severity="critical",
                server_name="agent",
                title="Agent failed",
                message="Error.",
            )

    @pytest.mark.asyncio
    async def test_always_on_type_fires_regardless_of_alert_types_dict(self) -> None:
        """loop_detected has no toggle — should fire even if alert_types is empty."""
        storage = _mock_storage({
            "slack_webhook": "https://hooks.slack.com/x",
            "alert_types": {},
        })
        with patch("langsight.api.alert_dispatcher.slack_module.send_alert", new_callable=AsyncMock, return_value=True) as mock_send:
            await fire_alert(
                storage=storage,
                alert_type="loop_detected",
                severity="warning",
                server_name="agent",
                title="Loop detected",
                message="Agent looped 5 times.",
            )
        mock_send.assert_awaited_once()
