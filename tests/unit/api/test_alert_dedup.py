"""Unit tests for Redis-backed alert deduplication in fire_alert()."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_storage() -> MagicMock:
    storage = MagicMock()
    storage.save_fired_alert = AsyncMock(return_value=None)
    storage.get_alert_config = AsyncMock(return_value=None)
    return storage


def _make_redis(setnx_result: bool = True) -> MagicMock:
    """Return a mock Redis client where SET nx returns setnx_result."""
    redis = MagicMock()
    redis.set = AsyncMock(return_value=setnx_result)
    return redis


class TestFireAlertRedisDeduplification:
    @pytest.mark.asyncio
    async def test_no_redis_always_fires(self) -> None:
        """When redis=None, alert fires without any dedup check."""
        storage = _make_storage()
        with patch(
            "langsight.api.alert_dispatcher._load_config",
            new=AsyncMock(return_value={"alert_types": {}}),
        ), patch(
            "langsight.api.alert_dispatcher._resolve_webhook", return_value=None
        ):
            from langsight.api.alert_dispatcher import fire_alert

            result = await fire_alert(
                storage=storage,
                alert_type="server_down",
                severity="critical",
                server_name="postgres-mcp",
                title="Server down",
                message="postgres-mcp is unreachable",
                redis=None,
            )
        assert result is True
        storage.save_fired_alert.assert_called_once()

    @pytest.mark.asyncio
    async def test_first_alert_fires_when_setnx_succeeds(self) -> None:
        """SETNX returns True (new key) → first worker fires the alert."""
        storage = _make_storage()
        redis = _make_redis(setnx_result=True)
        with patch(
            "langsight.api.alert_dispatcher._load_config",
            new=AsyncMock(return_value={"alert_types": {}}),
        ), patch(
            "langsight.api.alert_dispatcher._resolve_webhook", return_value=None
        ):
            from langsight.api.alert_dispatcher import fire_alert

            result = await fire_alert(
                storage=storage,
                alert_type="server_down",
                severity="critical",
                server_name="postgres-mcp",
                title="Server down",
                message="postgres-mcp is unreachable",
                redis=redis,
            )
        assert result is True
        redis.set.assert_called_once()
        # Verify the dedup key structure
        call_kwargs = redis.set.call_args
        key = call_kwargs[0][0]
        assert "server_down" in key
        assert "postgres-mcp" in key
        assert call_kwargs[1]["nx"] is True
        assert call_kwargs[1]["ex"] == 3600

    @pytest.mark.asyncio
    async def test_duplicate_alert_suppressed_when_setnx_fails(self) -> None:
        """SETNX returns False (key exists) → duplicate worker skips the alert."""
        storage = _make_storage()
        redis = _make_redis(setnx_result=False)
        with patch(
            "langsight.api.alert_dispatcher._load_config",
            new=AsyncMock(return_value={"alert_types": {}}),
        ):
            from langsight.api.alert_dispatcher import fire_alert

            result = await fire_alert(
                storage=storage,
                alert_type="server_down",
                severity="critical",
                server_name="postgres-mcp",
                title="Server down",
                message="postgres-mcp is unreachable",
                redis=redis,
            )
        assert result is False
        storage.save_fired_alert.assert_not_called()

    @pytest.mark.asyncio
    async def test_redis_error_falls_through_and_fires(self) -> None:
        """If Redis raises during SETNX, fall through and fire anyway (fail-open)."""
        storage = _make_storage()
        redis = MagicMock()
        redis.set = AsyncMock(side_effect=ConnectionError("redis down"))
        with patch(
            "langsight.api.alert_dispatcher._load_config",
            new=AsyncMock(return_value={"alert_types": {}}),
        ), patch(
            "langsight.api.alert_dispatcher._resolve_webhook", return_value=None
        ):
            from langsight.api.alert_dispatcher import fire_alert

            result = await fire_alert(
                storage=storage,
                alert_type="server_down",
                severity="critical",
                server_name="postgres-mcp",
                title="Server down",
                message="postgres-mcp is unreachable",
                redis=redis,
            )
        # Fail-open: Redis error must not suppress the alert
        assert result is True
        storage.save_fired_alert.assert_called_once()

    @pytest.mark.asyncio
    async def test_dedup_key_includes_project_id(self) -> None:
        """project_id is part of the dedup key so projects don't interfere."""
        storage = _make_storage()
        redis = _make_redis(setnx_result=True)
        with patch(
            "langsight.api.alert_dispatcher._load_config",
            new=AsyncMock(return_value={"alert_types": {}}),
        ), patch(
            "langsight.api.alert_dispatcher._resolve_webhook", return_value=None
        ):
            from langsight.api.alert_dispatcher import fire_alert

            await fire_alert(
                storage=storage,
                alert_type="server_down",
                severity="critical",
                server_name="srv",
                title="t",
                message="m",
                project_id="proj-abc",
                redis=redis,
            )
        key = redis.set.call_args[0][0]
        assert "proj-abc" in key

    @pytest.mark.asyncio
    async def test_session_id_used_in_dedup_scope_when_present(self) -> None:
        """When session_id is set, it scopes the dedup key (not server_name)."""
        storage = _make_storage()
        redis = _make_redis(setnx_result=True)
        with patch(
            "langsight.api.alert_dispatcher._load_config",
            new=AsyncMock(return_value={"alert_types": {}}),
        ), patch(
            "langsight.api.alert_dispatcher._resolve_webhook", return_value=None
        ):
            from langsight.api.alert_dispatcher import fire_alert

            await fire_alert(
                storage=storage,
                alert_type="agent_failure",
                severity="critical",
                server_name="my-agent",
                title="t",
                message="m",
                session_id="sess-xyz",
                redis=redis,
            )
        key = redis.set.call_args[0][0]
        assert "sess-xyz" in key
