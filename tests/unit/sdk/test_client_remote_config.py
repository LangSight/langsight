"""
Unit tests for LangSightClient remote prevention config feature (v0.3).

Covers:
- _apply_remote_config: overrides loop threshold, disables loop, overrides budget,
  clears budget, overrides circuit breaker, disables circuit breaker
- _fetch_prevention_config: returns None on HTTP 404, returns None on connection error
- wrap(): schedules _apply_remote_config when agent_name given, skips when not given
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from langsight.sdk.budget import BudgetConfig
from langsight.sdk.circuit_breaker import CircuitBreakerConfig
from langsight.sdk.client import LangSightClient
from langsight.sdk.loop_detector import LoopAction, LoopDetectorConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _client_with_all_prevention() -> LangSightClient:
    """Return a client with all prevention features enabled via constructor."""
    return LangSightClient(
        url="http://test",
        loop_detection=True,
        loop_threshold=3,
        loop_action="terminate",
        max_steps=20,
        max_cost_usd=1.00,
        circuit_breaker=True,
        circuit_breaker_threshold=5,
        circuit_breaker_cooldown=60.0,
        circuit_breaker_half_open_max=2,
    )


def _client_no_prevention() -> LangSightClient:
    """Return a client with all prevention features disabled."""
    return LangSightClient(url="http://test")


# ---------------------------------------------------------------------------
# _apply_remote_config — loop detection
# ---------------------------------------------------------------------------


class TestApplyRemoteConfigLoop:
    async def test_overrides_loop_threshold_with_remote_value(self) -> None:
        client = LangSightClient(
            url="http://test", loop_detection=True, loop_threshold=3
        )
        config = {
            "loop_enabled": True,
            "loop_threshold": 10,
            "loop_action": "terminate",
            "cb_enabled": False,
        }
        with patch.object(
            client, "_fetch_prevention_config", return_value=config
        ):
            await client._apply_remote_config("orchestrator", None)
        assert client._loop_config is not None
        assert client._loop_config.threshold == 10

    async def test_overrides_loop_action_to_warn(self) -> None:
        client = LangSightClient(
            url="http://test", loop_detection=True, loop_action="terminate"
        )
        config = {
            "loop_enabled": True,
            "loop_threshold": 3,
            "loop_action": "warn",
            "cb_enabled": False,
        }
        with patch.object(
            client, "_fetch_prevention_config", return_value=config
        ):
            await client._apply_remote_config("orchestrator", None)
        assert client._loop_config is not None
        assert client._loop_config.action == LoopAction.WARN

    async def test_disables_loop_when_loop_enabled_false(self) -> None:
        client = LangSightClient(
            url="http://test", loop_detection=True, loop_threshold=3
        )
        config = {"loop_enabled": False, "cb_enabled": False}
        with patch.object(
            client, "_fetch_prevention_config", return_value=config
        ):
            await client._apply_remote_config("orchestrator", None)
        assert client._loop_config is None

    async def test_enables_loop_when_previously_disabled(self) -> None:
        """loop_detection=False at constructor but remote says True."""
        client = _client_no_prevention()
        assert client._loop_config is None
        config = {
            "loop_enabled": True,
            "loop_threshold": 5,
            "loop_action": "warn",
            "cb_enabled": False,
        }
        with patch.object(
            client, "_fetch_prevention_config", return_value=config
        ):
            await client._apply_remote_config("orchestrator", None)
        assert client._loop_config is not None
        assert client._loop_config.threshold == 5

    async def test_does_nothing_when_fetch_returns_none(self) -> None:
        client = LangSightClient(
            url="http://test", loop_detection=True, loop_threshold=3
        )
        with patch.object(
            client, "_fetch_prevention_config", return_value=None
        ):
            await client._apply_remote_config("orchestrator", None)
        # Constructor value must be unchanged
        assert client._loop_config is not None
        assert client._loop_config.threshold == 3


# ---------------------------------------------------------------------------
# _apply_remote_config — budget
# ---------------------------------------------------------------------------


class TestApplyRemoteConfigBudget:
    async def test_overrides_max_steps_with_remote_value(self) -> None:
        client = LangSightClient(url="http://test", max_steps=20)
        config = {
            "loop_enabled": False,
            "cb_enabled": False,
            "max_steps": 50,
            "max_cost_usd": None,
            "max_wall_time_s": None,
        }
        with patch.object(
            client, "_fetch_prevention_config", return_value=config
        ):
            await client._apply_remote_config("orchestrator", None)
        assert client._budget_config is not None
        assert client._budget_config.max_steps == 50

    async def test_overrides_max_cost_usd(self) -> None:
        client = LangSightClient(url="http://test", max_cost_usd=1.00)
        config = {
            "loop_enabled": False,
            "cb_enabled": False,
            "max_steps": None,
            "max_cost_usd": 5.00,
            "max_wall_time_s": None,
        }
        with patch.object(
            client, "_fetch_prevention_config", return_value=config
        ):
            await client._apply_remote_config("orchestrator", None)
        assert client._budget_config is not None
        assert client._budget_config.max_cost_usd == 5.00

    async def test_clears_budget_when_all_limits_explicitly_null(self) -> None:
        """If remote explicitly sets all limits to null, budget is disabled."""
        client = LangSightClient(url="http://test", max_steps=20)
        config = {
            "loop_enabled": False,
            "cb_enabled": False,
            "max_steps": None,
            "max_cost_usd": None,
            "max_wall_time_s": None,
        }
        with patch.object(
            client, "_fetch_prevention_config", return_value=config
        ):
            await client._apply_remote_config("orchestrator", None)
        # max_steps key present but None → budget explicitly cleared
        assert client._budget_config is None

    async def test_leaves_budget_unchanged_when_no_budget_keys_in_remote_config(
        self,
    ) -> None:
        """Remote config with no budget keys at all should not touch existing budget."""
        client = LangSightClient(url="http://test", max_steps=20)
        assert client._budget_config is not None
        config = {
            "loop_enabled": False,
            "cb_enabled": False,
            # No max_steps / max_cost_usd / max_wall_time_s keys
        }
        with patch.object(
            client, "_fetch_prevention_config", return_value=config
        ):
            await client._apply_remote_config("orchestrator", None)
        # Budget should be untouched
        assert client._budget_config is not None
        assert client._budget_config.max_steps == 20

    async def test_overrides_budget_soft_alert_fraction(self) -> None:
        client = LangSightClient(url="http://test", max_steps=20, budget_soft_alert=0.80)
        config = {
            "loop_enabled": False,
            "cb_enabled": False,
            "max_steps": 20,
            "budget_soft_alert": 0.50,
        }
        with patch.object(
            client, "_fetch_prevention_config", return_value=config
        ):
            await client._apply_remote_config("orchestrator", None)
        assert client._budget_config is not None
        assert client._budget_config.soft_alert_fraction == 0.50

    async def test_creates_budget_config_when_previously_none(self) -> None:
        client = _client_no_prevention()
        assert client._budget_config is None
        config = {
            "loop_enabled": False,
            "cb_enabled": False,
            "max_steps": 30,
        }
        with patch.object(
            client, "_fetch_prevention_config", return_value=config
        ):
            await client._apply_remote_config("orchestrator", None)
        assert client._budget_config is not None
        assert client._budget_config.max_steps == 30


# ---------------------------------------------------------------------------
# _apply_remote_config — circuit breaker
# ---------------------------------------------------------------------------


class TestApplyRemoteConfigCircuitBreaker:
    async def test_overrides_circuit_breaker_failure_threshold(self) -> None:
        client = LangSightClient(
            url="http://test",
            circuit_breaker=True,
            circuit_breaker_threshold=5,
        )
        config = {
            "loop_enabled": False,
            "cb_enabled": True,
            "cb_failure_threshold": 10,
            "cb_cooldown_seconds": 60.0,
            "cb_half_open_max_calls": 2,
        }
        with patch.object(
            client, "_fetch_prevention_config", return_value=config
        ):
            await client._apply_remote_config("orchestrator", None)
        assert client._cb_default_config is not None
        assert client._cb_default_config.failure_threshold == 10

    async def test_disables_circuit_breaker_when_cb_enabled_false(self) -> None:
        client = LangSightClient(url="http://test", circuit_breaker=True)
        config = {"loop_enabled": False, "cb_enabled": False}
        with patch.object(
            client, "_fetch_prevention_config", return_value=config
        ):
            await client._apply_remote_config("orchestrator", None)
        assert client._cb_default_config is None

    async def test_enables_circuit_breaker_when_previously_disabled(self) -> None:
        client = _client_no_prevention()
        assert client._cb_default_config is None
        config = {
            "loop_enabled": False,
            "cb_enabled": True,
            "cb_failure_threshold": 3,
            "cb_cooldown_seconds": 30.0,
            "cb_half_open_max_calls": 1,
        }
        with patch.object(
            client, "_fetch_prevention_config", return_value=config
        ):
            await client._apply_remote_config("orchestrator", None)
        assert client._cb_default_config is not None
        assert client._cb_default_config.failure_threshold == 3

    async def test_overrides_cooldown_seconds(self) -> None:
        client = LangSightClient(
            url="http://test",
            circuit_breaker=True,
            circuit_breaker_cooldown=60.0,
        )
        config = {
            "loop_enabled": False,
            "cb_enabled": True,
            "cb_failure_threshold": 5,
            "cb_cooldown_seconds": 120.0,
            "cb_half_open_max_calls": 2,
        }
        with patch.object(
            client, "_fetch_prevention_config", return_value=config
        ):
            await client._apply_remote_config("orchestrator", None)
        assert client._cb_default_config is not None
        assert client._cb_default_config.cooldown_seconds == 120.0

    async def test_overrides_half_open_max_calls(self) -> None:
        client = LangSightClient(
            url="http://test",
            circuit_breaker=True,
            circuit_breaker_half_open_max=2,
        )
        config = {
            "loop_enabled": False,
            "cb_enabled": True,
            "cb_failure_threshold": 5,
            "cb_cooldown_seconds": 60.0,
            "cb_half_open_max_calls": 5,
        }
        with patch.object(
            client, "_fetch_prevention_config", return_value=config
        ):
            await client._apply_remote_config("orchestrator", None)
        assert client._cb_default_config is not None
        assert client._cb_default_config.half_open_max_calls == 5


# ---------------------------------------------------------------------------
# _fetch_prevention_config — HTTP behaviour
# ---------------------------------------------------------------------------


class TestFetchPreventionConfig:
    async def test_returns_none_on_http_404(self) -> None:
        client = LangSightClient(url="http://test")
        mock_http = MagicMock()
        mock_http.is_closed = False
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_http.get = AsyncMock(return_value=mock_response)
        client._http = mock_http

        result = await client._fetch_prevention_config("orchestrator", None)
        assert result is None

    async def test_returns_none_on_connection_error(self) -> None:
        """Fail-open: any exception → return None, never raise."""
        client = LangSightClient(url="http://test")
        mock_http = MagicMock()
        mock_http.is_closed = False
        mock_http.get = AsyncMock(
            side_effect=ConnectionError("cannot connect to api")
        )
        client._http = mock_http

        result = await client._fetch_prevention_config("orchestrator", None)
        assert result is None

    async def test_returns_none_on_any_unexpected_exception(self) -> None:
        client = LangSightClient(url="http://test")
        mock_http = MagicMock()
        mock_http.is_closed = False
        mock_http.get = AsyncMock(side_effect=RuntimeError("unexpected"))
        client._http = mock_http

        result = await client._fetch_prevention_config("orchestrator", None)
        assert result is None

    async def test_returns_parsed_json_on_http_200(self) -> None:
        client = LangSightClient(url="http://test")
        mock_http = MagicMock()
        mock_http.is_closed = False
        payload = {
            "loop_enabled": True,
            "loop_threshold": 7,
            "loop_action": "warn",
            "cb_enabled": False,
        }
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = MagicMock(return_value=payload)
        mock_http.get = AsyncMock(return_value=mock_response)
        client._http = mock_http

        result = await client._fetch_prevention_config("orchestrator", None)
        assert result == payload

    async def test_appends_project_id_query_param_when_given(self) -> None:
        client = LangSightClient(url="http://test")
        mock_http = MagicMock()
        mock_http.is_closed = False
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = MagicMock(return_value={})
        mock_http.get = AsyncMock(return_value=mock_response)
        client._http = mock_http

        await client._fetch_prevention_config("orchestrator", "proj-abc")
        url_called = mock_http.get.call_args[0][0]
        assert "project_id=proj-abc" in url_called

    async def test_does_not_append_project_id_when_none(self) -> None:
        client = LangSightClient(url="http://test")
        mock_http = MagicMock()
        mock_http.is_closed = False
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_http.get = AsyncMock(return_value=mock_response)
        client._http = mock_http

        await client._fetch_prevention_config("orchestrator", None)
        url_called = mock_http.get.call_args[0][0]
        assert "project_id" not in url_called

    async def test_includes_agent_name_in_url_path(self) -> None:
        client = LangSightClient(url="http://test")
        mock_http = MagicMock()
        mock_http.is_closed = False
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_http.get = AsyncMock(return_value=mock_response)
        client._http = mock_http

        await client._fetch_prevention_config("billing-agent", None)
        url_called = mock_http.get.call_args[0][0]
        assert "billing-agent" in url_called


# ---------------------------------------------------------------------------
# wrap() — task scheduling behaviour
# ---------------------------------------------------------------------------


class TestWrapRemoteConfigScheduling:
    async def test_wrap_with_agent_name_schedules_apply_remote_config(self) -> None:
        """When agent_name is provided, wrap() must fire _apply_remote_config as a task."""
        client = LangSightClient(url="http://test")
        mock_mcp = MagicMock()
        applied: list[str] = []

        async def _fake_apply(agent_name: str, project_id) -> None:
            applied.append(agent_name)

        with patch.object(client, "_apply_remote_config", side_effect=_fake_apply):
            client.wrap(mock_mcp, server_name="pg", agent_name="orchestrator")
            # Let the event loop run the scheduled task
            await asyncio.sleep(0)

        assert "orchestrator" in applied

    async def test_wrap_without_agent_name_does_not_schedule_remote_config(
        self,
    ) -> None:
        """Without agent_name, wrap() must not attempt remote config fetch."""
        client = LangSightClient(url="http://test")
        mock_mcp = MagicMock()

        with patch.object(client, "_apply_remote_config", new_callable=AsyncMock) as mock_apply:
            client.wrap(mock_mcp, server_name="pg")
            await asyncio.sleep(0)

        mock_apply.assert_not_called()

    async def test_wrap_passes_project_id_to_apply_remote_config(self) -> None:
        client = LangSightClient(url="http://test", project_id="proj-abc")
        mock_mcp = MagicMock()
        captured: list[tuple] = []

        async def _fake_apply(agent_name: str, project_id) -> None:
            captured.append((agent_name, project_id))

        with patch.object(client, "_apply_remote_config", side_effect=_fake_apply):
            client.wrap(mock_mcp, server_name="pg", agent_name="orchestrator")
            await asyncio.sleep(0)

        assert len(captured) == 1
        assert captured[0] == ("orchestrator", "proj-abc")

    async def test_wrap_project_id_override_takes_precedence(self) -> None:
        """project_id passed directly to wrap() overrides the client-level default."""
        client = LangSightClient(url="http://test", project_id="proj-default")
        mock_mcp = MagicMock()
        captured: list[tuple] = []

        async def _fake_apply(agent_name: str, project_id) -> None:
            captured.append((agent_name, project_id))

        with patch.object(client, "_apply_remote_config", side_effect=_fake_apply):
            client.wrap(
                mock_mcp,
                server_name="pg",
                agent_name="orchestrator",
                project_id="proj-override",
            )
            await asyncio.sleep(0)

        assert captured[0][1] == "proj-override"

    def test_wrap_tolerates_no_event_loop_without_raising(self) -> None:
        """In a sync context without an event loop, wrap() must not raise."""
        # asyncio.create_task raises RuntimeError → wrap() catches and swallows it.
        # We intercept at the asyncio.create_task call so the coroutine is never
        # handed to the event loop; we close it manually to suppress the warning.
        client = LangSightClient(url="http://test")
        mock_mcp = MagicMock()
        captured_coros: list = []

        def _fake_create_task(coro):
            captured_coros.append(coro)
            raise RuntimeError("no event loop")

        with patch("asyncio.create_task", side_effect=_fake_create_task):
            proxy = client.wrap(mock_mcp, server_name="pg", agent_name="orchestrator")

        # Close any coroutines that were created but never awaited
        for coro in captured_coros:
            coro.close()

        assert proxy is not None
