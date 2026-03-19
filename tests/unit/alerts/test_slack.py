from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from langsight.alerts.engine import Alert, AlertSeverity, AlertType
from langsight.alerts.slack import _build_payload, send_alert, send_alerts


def _alert(
    alert_type: AlertType = AlertType.SERVER_DOWN,
    severity: AlertSeverity = AlertSeverity.CRITICAL,
) -> Alert:
    return Alert(
        server_name="test-srv",
        alert_type=alert_type,
        severity=severity,
        title="Test server is DOWN",
        message="Server has been unreachable for 2 checks.",
        fired_at=datetime(2026, 3, 16, 12, 0, 0, tzinfo=UTC),
    )


class TestBuildPayload:
    def test_payload_has_text_fallback(self) -> None:
        payload = _build_payload(_alert())
        assert "text" in payload
        assert "test-srv" in payload["text"] or "DOWN" in payload["text"]

    def test_payload_has_blocks(self) -> None:
        payload = _build_payload(_alert())
        assert "blocks" in payload
        assert len(payload["blocks"]) >= 2

    def test_header_block_contains_title(self) -> None:
        payload = _build_payload(_alert())
        header = next(b for b in payload["blocks"] if b["type"] == "header")
        assert "DOWN" in header["text"]["text"]

    def test_section_contains_server_name(self) -> None:
        payload = _build_payload(_alert())
        section = next(b for b in payload["blocks"] if b["type"] == "section")
        fields_text = " ".join(f["text"] for f in section["fields"])
        assert "test-srv" in fields_text

    def test_recovery_uses_correct_emoji(self) -> None:
        payload = _build_payload(_alert(alert_type=AlertType.SERVER_RECOVERED))
        header = next(b for b in payload["blocks"] if b["type"] == "header")
        assert ":white_check_mark:" in header["text"]["text"]


class TestSendAlert:
    async def test_returns_true_on_success(self) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        with patch("langsight.alerts.slack.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=MockClient.return_value)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value.post = AsyncMock(return_value=mock_response)
            result = await send_alert("https://hooks.slack.com/test", _alert())
        assert result is True

    async def test_returns_false_on_network_error(self) -> None:
        with patch("langsight.alerts.slack.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=MockClient.return_value)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value.post = AsyncMock(side_effect=Exception("network error"))
            result = await send_alert("https://hooks.slack.com/test", _alert())
        assert result is False  # fail-open

    async def test_send_alerts_returns_sent_count(self) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        with patch("langsight.alerts.slack.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=MockClient.return_value)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value.post = AsyncMock(return_value=mock_response)
            count = await send_alerts(
                "https://hooks.slack.com/test",
                [_alert(), _alert(alert_type=AlertType.SCHEMA_DRIFT)],
            )
        assert count == 2
