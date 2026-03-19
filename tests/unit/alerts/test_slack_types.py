"""
Unit tests for Slack emoji mapping completeness in alerts/slack.py.

Every AlertType must have an entry in _TYPE_EMOJI so that messages sent to
Slack always carry a meaningful icon rather than falling back to the generic
":bell:" default.
"""

from __future__ import annotations

import pytest

from langsight.alerts.engine import AlertType
from langsight.alerts.slack import _TYPE_EMOJI


class TestTypeEmojiMapping:
    def test_type_emoji_contains_all_eight_alert_types(self) -> None:
        """_TYPE_EMOJI must have an entry for every AlertType member."""
        missing = [t for t in AlertType if t not in _TYPE_EMOJI]
        assert missing == [], f"Missing emoji entries for: {missing}"

    def test_type_emoji_has_exactly_eight_entries(self) -> None:
        assert len(_TYPE_EMOJI) == len(AlertType)

    # Original four
    def test_server_down_emoji(self) -> None:
        assert _TYPE_EMOJI[AlertType.SERVER_DOWN] == ":x:"

    def test_server_recovered_emoji(self) -> None:
        assert _TYPE_EMOJI[AlertType.SERVER_RECOVERED] == ":white_check_mark:"

    def test_schema_drift_emoji(self) -> None:
        assert _TYPE_EMOJI[AlertType.SCHEMA_DRIFT] == ":twisted_rightwards_arrows:"

    def test_high_latency_emoji(self) -> None:
        assert _TYPE_EMOJI[AlertType.HIGH_LATENCY] == ":hourglass_flowing_sand:"

    # New four agent-level types
    def test_agent_failure_emoji(self) -> None:
        assert _TYPE_EMOJI[AlertType.AGENT_FAILURE] == ":robot_face:"

    def test_slo_breached_emoji(self) -> None:
        assert _TYPE_EMOJI[AlertType.SLO_BREACHED] == ":chart_with_downwards_trend:"

    def test_anomaly_detected_emoji(self) -> None:
        assert _TYPE_EMOJI[AlertType.ANOMALY_DETECTED] == ":mag:"

    def test_security_finding_emoji(self) -> None:
        assert _TYPE_EMOJI[AlertType.SECURITY_FINDING] == ":shield:"

    def test_all_emoji_values_are_non_empty_strings(self) -> None:
        for alert_type, emoji in _TYPE_EMOJI.items():
            assert isinstance(emoji, str), f"{alert_type} emoji is not a string"
            assert emoji.strip(), f"{alert_type} emoji is an empty/blank string"

    def test_all_emoji_values_use_colon_syntax(self) -> None:
        """Slack emoji strings must be wrapped in colons."""
        for alert_type, emoji in _TYPE_EMOJI.items():
            assert emoji.startswith(":") and emoji.endswith(":"), (
                f"{alert_type} emoji '{emoji}' does not follow :emoji_name: format"
            )

    @pytest.mark.parametrize("alert_type", list(AlertType))
    def test_each_alert_type_has_emoji_entry(self, alert_type: AlertType) -> None:
        assert alert_type in _TYPE_EMOJI, f"No emoji for {alert_type}"
