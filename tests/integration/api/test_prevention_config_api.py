"""
Integration tests for the prevention config API endpoints.

Hits the LIVE stack at http://localhost:8000. Requires:
    docker compose up -d
    (wait for api healthy)

Run:
    uv run pytest tests/integration/api/test_prevention_config_api.py -v -m integration

Tests authenticate with the API key from .env / TEST_API_KEY env var.
Tests are scoped to the Sample Project (slug: sample-project) so they don't
pollute other projects.
"""

from __future__ import annotations

import os
import uuid

import httpx
import pytest

pytestmark = pytest.mark.integration

_BASE_URL = os.environ.get("TEST_API_URL", "http://localhost:8000")
_API_KEY = os.environ.get(
    "TEST_API_KEY",
    "ls_529c7bee083fe9447a7d8ea69780ad1ec36c65ad52cc0b36ce0c2aed66446c8f",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def api_available() -> bool:
    """Return True if the API is reachable."""
    try:
        r = httpx.get(f"{_BASE_URL}/api/liveness", timeout=3)
        return r.status_code == 200
    except Exception:  # noqa: BLE001
        return False


@pytest.fixture(scope="module", autouse=True)
def require_api(api_available: bool) -> None:
    if not api_available:
        pytest.skip("API not reachable. Run: docker compose up -d")


@pytest.fixture(scope="module")
def headers() -> dict[str, str]:
    return {"X-API-Key": _API_KEY, "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def project_id(headers: dict[str, str]) -> str:
    """Get or create the Sample Project and return its ID."""
    r = httpx.get(f"{_BASE_URL}/api/projects", headers=headers, timeout=5)
    r.raise_for_status()
    for p in r.json():
        if p["slug"] == "sample-project":
            return p["id"]
    pytest.skip("Sample Project not found — run the demo seed first")


@pytest.fixture
def clean_agent(headers: dict[str, str], project_id: str):
    """Yield a unique agent name and clean up any config for it after the test."""
    agent_name = f"test-int-{uuid.uuid4().hex[:8]}"
    yield agent_name
    # Teardown
    httpx.delete(
        f"{_BASE_URL}/api/agents/{agent_name}/prevention-config",
        headers=headers,
        params={"project_id": project_id},
        timeout=5,
    )


# ---------------------------------------------------------------------------
# API: List
# ---------------------------------------------------------------------------


class TestListPreventionConfigs:
    def test_list_returns_seeded_demo_configs(
        self, headers: dict[str, str], project_id: str
    ) -> None:
        """Demo seed should have inserted 5 configs including orchestrator."""
        r = httpx.get(
            f"{_BASE_URL}/api/agents/prevention-configs",
            headers=headers,
            params={"project_id": project_id},
            timeout=5,
        )
        assert r.status_code == 200
        configs = r.json()
        names = {c["agent_name"] for c in configs}
        assert "orchestrator" in names
        assert "billing-agent" in names
        assert "*" in names  # project default

    def test_list_returns_correct_shape(
        self, headers: dict[str, str], project_id: str
    ) -> None:
        r = httpx.get(
            f"{_BASE_URL}/api/agents/prevention-configs",
            headers=headers,
            params={"project_id": project_id},
            timeout=5,
        )
        assert r.status_code == 200
        for c in r.json():
            assert "agent_name" in c
            assert "loop_threshold" in c
            assert "cb_enabled" in c
            assert "is_default" in c
            assert "updated_at" in c


# ---------------------------------------------------------------------------
# API: GET effective config
# ---------------------------------------------------------------------------


class TestGetEffectiveConfig:
    def test_get_seeded_orchestrator_config(
        self, headers: dict[str, str], project_id: str
    ) -> None:
        r = httpx.get(
            f"{_BASE_URL}/api/agents/orchestrator/prevention-config",
            headers=headers,
            params={"project_id": project_id},
            timeout=5,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["agent_name"] == "orchestrator"
        assert body["max_steps"] == 25
        assert body["max_cost_usd"] == pytest.approx(1.00)
        assert body["is_default"] is False

    def test_get_billing_agent_config(
        self, headers: dict[str, str], project_id: str
    ) -> None:
        r = httpx.get(
            f"{_BASE_URL}/api/agents/billing-agent/prevention-config",
            headers=headers,
            params={"project_id": project_id},
            timeout=5,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["cb_failure_threshold"] == 3
        assert body["cb_cooldown_seconds"] == pytest.approx(30.0)

    def test_get_unknown_agent_falls_back_to_project_default(
        self, headers: dict[str, str], project_id: str
    ) -> None:
        """An agent with no specific config should return the '*' project default."""
        r = httpx.get(
            f"{_BASE_URL}/api/agents/completely-unknown-agent-xyz/prevention-config",
            headers=headers,
            params={"project_id": project_id},
            timeout=5,
        )
        # Should return the project default, not 404
        assert r.status_code == 200
        body = r.json()
        assert body["is_default"] is True

    def test_get_returns_404_without_project_id(
        self, headers: dict[str, str]
    ) -> None:
        r = httpx.get(
            f"{_BASE_URL}/api/agents/orchestrator/prevention-config",
            headers=headers,
            timeout=5,
        )
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# API: PUT (upsert)
# ---------------------------------------------------------------------------


class TestUpsertConfig:
    def test_create_new_agent_config(
        self,
        headers: dict[str, str],
        project_id: str,
        clean_agent: str,
    ) -> None:
        body = {
            "loop_enabled": True,
            "loop_threshold": 5,
            "loop_action": "warn",
            "max_steps": 20,
            "max_cost_usd": 0.75,
            "max_wall_time_s": None,
            "budget_soft_alert": 0.80,
            "cb_enabled": True,
            "cb_failure_threshold": 3,
            "cb_cooldown_seconds": 45.0,
            "cb_half_open_max_calls": 2,
        }
        r = httpx.put(
            f"{_BASE_URL}/api/agents/{clean_agent}/prevention-config",
            headers=headers,
            params={"project_id": project_id},
            json=body,
            timeout=5,
        )
        assert r.status_code == 200
        saved = r.json()
        assert saved["loop_threshold"] == 5
        assert saved["max_steps"] == 20
        assert saved["cb_failure_threshold"] == 3
        assert saved["is_default"] is False

    def test_update_existing_config(
        self,
        headers: dict[str, str],
        project_id: str,
        clean_agent: str,
    ) -> None:
        base = {
            "loop_enabled": True, "loop_threshold": 3, "loop_action": "terminate",
            "max_steps": 10, "max_cost_usd": None, "max_wall_time_s": None,
            "budget_soft_alert": 0.80, "cb_enabled": True, "cb_failure_threshold": 5,
            "cb_cooldown_seconds": 60.0, "cb_half_open_max_calls": 2,
        }
        httpx.put(  # noqa: ASYNC210
            f"{_BASE_URL}/api/agents/{clean_agent}/prevention-config",
            headers=headers, params={"project_id": project_id}, json=base, timeout=5,
        )

        updated = {**base, "max_steps": 99, "loop_threshold": 7}
        r = httpx.put(
            f"{_BASE_URL}/api/agents/{clean_agent}/prevention-config",
            headers=headers, params={"project_id": project_id}, json=updated, timeout=5,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["max_steps"] == 99
        assert body["loop_threshold"] == 7

    def test_put_validates_loop_action(
        self, headers: dict[str, str], project_id: str, clean_agent: str
    ) -> None:
        body = {
            "loop_enabled": True, "loop_threshold": 3, "loop_action": "INVALID",
            "max_steps": None, "max_cost_usd": None, "max_wall_time_s": None,
            "budget_soft_alert": 0.80, "cb_enabled": True, "cb_failure_threshold": 5,
            "cb_cooldown_seconds": 60.0, "cb_half_open_max_calls": 2,
        }
        r = httpx.put(
            f"{_BASE_URL}/api/agents/{clean_agent}/prevention-config",
            headers=headers, params={"project_id": project_id}, json=body, timeout=5,
        )
        assert r.status_code == 422

    def test_put_validates_loop_threshold_minimum(
        self, headers: dict[str, str], project_id: str, clean_agent: str
    ) -> None:
        body = {
            "loop_enabled": True, "loop_threshold": 0, "loop_action": "terminate",
            "max_steps": None, "max_cost_usd": None, "max_wall_time_s": None,
            "budget_soft_alert": 0.80, "cb_enabled": True, "cb_failure_threshold": 5,
            "cb_cooldown_seconds": 60.0, "cb_half_open_max_calls": 2,
        }
        r = httpx.put(
            f"{_BASE_URL}/api/agents/{clean_agent}/prevention-config",
            headers=headers, params={"project_id": project_id}, json=body, timeout=5,
        )
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# API: DELETE
# ---------------------------------------------------------------------------


class TestDeleteConfig:
    def test_delete_removes_agent_config_reveals_default(
        self, headers: dict[str, str], project_id: str, clean_agent: str
    ) -> None:
        # Create agent-specific config
        body = {
            "loop_enabled": True, "loop_threshold": 3, "loop_action": "terminate",
            "max_steps": 5, "max_cost_usd": None, "max_wall_time_s": None,
            "budget_soft_alert": 0.80, "cb_enabled": True, "cb_failure_threshold": 5,
            "cb_cooldown_seconds": 60.0, "cb_half_open_max_calls": 2,
        }
        httpx.put(  # noqa: ASYNC210
            f"{_BASE_URL}/api/agents/{clean_agent}/prevention-config",
            headers=headers, params={"project_id": project_id}, json=body, timeout=5,
        )

        # Verify agent-specific config exists
        r = httpx.get(
            f"{_BASE_URL}/api/agents/{clean_agent}/prevention-config",
            headers=headers, params={"project_id": project_id}, timeout=5,
        )
        assert r.json()["is_default"] is False
        assert r.json()["max_steps"] == 5

        # Delete it
        r = httpx.delete(
            f"{_BASE_URL}/api/agents/{clean_agent}/prevention-config",
            headers=headers, params={"project_id": project_id}, timeout=5,
        )
        assert r.status_code == 204

        # Now should fall back to project default (is_default=True)
        r = httpx.get(
            f"{_BASE_URL}/api/agents/{clean_agent}/prevention-config",
            headers=headers, params={"project_id": project_id}, timeout=5,
        )
        assert r.status_code == 200
        assert r.json()["is_default"] is True

    def test_delete_non_existent_returns_404(
        self, headers: dict[str, str], project_id: str
    ) -> None:
        r = httpx.delete(
            f"{_BASE_URL}/api/agents/ghost-agent-xyz/prevention-config",
            headers=headers, params={"project_id": project_id}, timeout=5,
        )
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# SDK end-to-end fetch
# ---------------------------------------------------------------------------


class TestSDKFetch:
    async def test_sdk_fetches_config_from_running_api(
        self, headers: dict[str, str], project_id: str, clean_agent: str
    ) -> None:
        """SDK _fetch_prevention_config hits the real API and returns parsed JSON."""
        from langsight.sdk.client import LangSightClient

        # Create a config via API first
        body = {
            "loop_enabled": True, "loop_threshold": 7, "loop_action": "warn",
            "max_steps": 30, "max_cost_usd": None, "max_wall_time_s": None,
            "budget_soft_alert": 0.80, "cb_enabled": False, "cb_failure_threshold": 5,
            "cb_cooldown_seconds": 60.0, "cb_half_open_max_calls": 2,
        }
        httpx.put(  # noqa: ASYNC210
            f"{_BASE_URL}/api/agents/{clean_agent}/prevention-config",
            headers=headers, params={"project_id": project_id}, json=body, timeout=5,
        )

        # Now SDK fetch
        client = LangSightClient(
            url=_BASE_URL,
            api_key=_API_KEY,
            project_id=project_id,
            loop_detection=True,
            loop_threshold=3,  # default — should be overridden
        )
        await client._apply_remote_config(clean_agent, project_id)

        assert client._loop_config is not None
        assert client._loop_config.threshold == 7         # overridden from API
        assert client._loop_config.action.value == "warn" # overridden from API
        assert client._cb_default_config is None          # disabled in API config
        await client.close()

    async def test_sdk_falls_back_to_constructor_on_404(self) -> None:
        """When API returns 404, SDK keeps constructor defaults unchanged."""
        from langsight.sdk.client import LangSightClient

        client = LangSightClient(
            url=_BASE_URL,
            api_key=_API_KEY,
            loop_detection=True,
            loop_threshold=5,
            max_steps=10,
        )
        original_loop_threshold = client._loop_config.threshold
        original_max_steps = client._budget_config.max_steps if client._budget_config else None

        await client._apply_remote_config("definitely-not-a-real-agent-xyz", None)

        # Constructor defaults preserved
        assert client._loop_config.threshold == original_loop_threshold
        if client._budget_config:
            assert client._budget_config.max_steps == original_max_steps
        await client.close()
