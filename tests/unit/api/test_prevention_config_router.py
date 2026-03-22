"""
Unit tests for the prevention config API router.

Covers all 6 endpoints:
- GET  /api/agents/prevention-configs
- GET  /api/agents/{agent_name}/prevention-config
- PUT  /api/agents/{agent_name}/prevention-config
- DELETE /api/agents/{agent_name}/prevention-config
- GET  /api/projects/prevention-config
- PUT  /api/projects/prevention-config

Validation failures (422), 404, 204, and is_default flag are all tested.

Setup notes:
- We mount ONLY the prevention_config router in a minimal FastAPI app so we
  avoid route conflicts (the full app's /api/projects/{project_id} would
  swallow /api/projects/prevention-config).
- get_active_project_id and require_admin are overridden via dependency_overrides
  so tests are fully isolated — no real auth, no DB needed.
- get_storage is overridden to inject the mock storage fixture.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from langsight.api.dependencies import get_active_project_id, get_storage, require_admin
from langsight.api.routers.prevention_config import router
from langsight.models import PreventionConfig

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 3, 22, 10, 0, 0, tzinfo=UTC)
_PROJECT_ID = "proj-abc"


def _config(
    *,
    agent_name: str = "orchestrator",
    id: str = "cfg-001",
    loop_threshold: int = 3,
    loop_action: str = "terminate",
    loop_enabled: bool = True,
    max_steps: int | None = None,
    max_cost_usd: float | None = None,
    max_wall_time_s: float | None = None,
    budget_soft_alert: float = 0.80,
    cb_enabled: bool = True,
    cb_failure_threshold: int = 5,
    cb_cooldown_seconds: float = 60.0,
    cb_half_open_max_calls: int = 2,
) -> PreventionConfig:
    return PreventionConfig(
        id=id,
        project_id=_PROJECT_ID,
        agent_name=agent_name,
        loop_enabled=loop_enabled,
        loop_threshold=loop_threshold,
        loop_action=loop_action,
        max_steps=max_steps,
        max_cost_usd=max_cost_usd,
        max_wall_time_s=max_wall_time_s,
        budget_soft_alert=budget_soft_alert,
        cb_enabled=cb_enabled,
        cb_failure_threshold=cb_failure_threshold,
        cb_cooldown_seconds=cb_cooldown_seconds,
        cb_half_open_max_calls=cb_half_open_max_calls,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _valid_body(**overrides) -> dict:
    base = {
        "loop_enabled": True,
        "loop_threshold": 3,
        "loop_action": "terminate",
        "max_steps": None,
        "max_cost_usd": None,
        "max_wall_time_s": None,
        "budget_soft_alert": 0.80,
        "cb_enabled": True,
        "cb_failure_threshold": 5,
        "cb_cooldown_seconds": 60.0,
        "cb_half_open_max_calls": 2,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_storage() -> MagicMock:
    """Mock storage with all prevention config methods pre-stubbed."""
    s = MagicMock()
    s.list_prevention_configs = AsyncMock(return_value=[])
    s.get_prevention_config = AsyncMock(return_value=None)
    s.get_effective_prevention_config = AsyncMock(return_value=None)
    s.upsert_prevention_config = AsyncMock(return_value=_config())
    s.delete_prevention_config = AsyncMock(return_value=True)
    return s


@pytest.fixture
def app_with_project(mock_storage: MagicMock) -> FastAPI:
    """Minimal app: prevention_config router + all dependencies overridden.
    get_active_project_id → returns _PROJECT_ID.
    require_admin → no-op.
    get_storage → mock_storage.
    """
    app = FastAPI()
    app.include_router(router)

    app.dependency_overrides[get_active_project_id] = lambda: _PROJECT_ID
    app.dependency_overrides[require_admin] = lambda: None
    app.dependency_overrides[get_storage] = lambda: mock_storage
    return app


@pytest.fixture
def app_no_project(mock_storage: MagicMock) -> FastAPI:
    """Same app but get_active_project_id returns None (no project)."""
    app = FastAPI()
    app.include_router(router)

    app.dependency_overrides[get_active_project_id] = lambda: None
    app.dependency_overrides[require_admin] = lambda: None
    app.dependency_overrides[get_storage] = lambda: mock_storage
    return app


@pytest.fixture
def tc(app_with_project: FastAPI) -> TestClient:
    """Sync TestClient for the project-scoped app. Used for most tests."""
    return TestClient(app_with_project, raise_server_exceptions=True)


@pytest.fixture
def tc_no_project(app_no_project: FastAPI) -> TestClient:
    """Sync TestClient for the no-project app."""
    return TestClient(app_no_project, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# GET /agents/prevention-configs
# ---------------------------------------------------------------------------


class TestListPreventionConfigs:
    def test_returns_empty_list_when_storage_has_no_configs(
        self, tc: TestClient, mock_storage: MagicMock
    ) -> None:
        mock_storage.list_prevention_configs.return_value = []
        response = tc.get("/agents/prevention-configs")
        assert response.status_code == 200
        assert response.json() == []

    def test_returns_empty_list_when_storage_lacks_method(
        self, mock_storage: MagicMock, app_with_project: FastAPI
    ) -> None:
        del mock_storage.list_prevention_configs
        with TestClient(app_with_project) as c:
            response = c.get("/agents/prevention-configs")
        assert response.status_code == 200
        assert response.json() == []

    def test_returns_configs_with_correct_fields(
        self, tc: TestClient, mock_storage: MagicMock
    ) -> None:
        mock_storage.list_prevention_configs.return_value = [
            _config(agent_name="orchestrator"),
            _config(agent_name="*", id="cfg-default"),
        ]
        response = tc.get("/agents/prevention-configs")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        names = {item["agent_name"] for item in data}
        assert names == {"orchestrator", "*"}

    def test_is_default_true_for_star_agent(
        self, tc: TestClient, mock_storage: MagicMock
    ) -> None:
        mock_storage.list_prevention_configs.return_value = [
            _config(agent_name="*", id="cfg-default"),
        ]
        response = tc.get("/agents/prevention-configs")
        data = response.json()
        assert data[0]["is_default"] is True

    def test_is_default_false_for_named_agent(
        self, tc: TestClient, mock_storage: MagicMock
    ) -> None:
        mock_storage.list_prevention_configs.return_value = [
            _config(agent_name="orchestrator"),
        ]
        response = tc.get("/agents/prevention-configs")
        data = response.json()
        assert data[0]["is_default"] is False

    def test_returns_empty_when_no_project_id(
        self, tc_no_project: TestClient
    ) -> None:
        """Without a project_id (None), the endpoint returns []."""
        response = tc_no_project.get("/agents/prevention-configs")
        assert response.status_code == 200
        assert response.json() == []


# ---------------------------------------------------------------------------
# GET /agents/{agent_name}/prevention-config
# ---------------------------------------------------------------------------


class TestGetAgentPreventionConfig:
    def test_returns_404_when_no_config_found(
        self, tc: TestClient, mock_storage: MagicMock
    ) -> None:
        mock_storage.get_effective_prevention_config.return_value = None
        response = tc.get("/agents/orchestrator/prevention-config")
        assert response.status_code == 404

    def test_returns_config_when_agent_specific_found(
        self, tc: TestClient, mock_storage: MagicMock
    ) -> None:
        mock_storage.get_effective_prevention_config.return_value = _config(
            agent_name="orchestrator", loop_threshold=7
        )
        response = tc.get("/agents/orchestrator/prevention-config")
        assert response.status_code == 200
        data = response.json()
        assert data["agent_name"] == "orchestrator"
        assert data["loop_threshold"] == 7

    def test_is_default_false_when_agent_specific_config_returned(
        self, tc: TestClient, mock_storage: MagicMock
    ) -> None:
        mock_storage.get_effective_prevention_config.return_value = _config(
            agent_name="orchestrator"
        )
        response = tc.get("/agents/orchestrator/prevention-config")
        assert response.json()["is_default"] is False

    def test_is_default_true_when_project_default_returned(
        self, tc: TestClient, mock_storage: MagicMock
    ) -> None:
        """When no agent-specific config exists, the effective config has agent_name='*'."""
        mock_storage.get_effective_prevention_config.return_value = _config(
            agent_name="*"
        )
        response = tc.get("/agents/orchestrator/prevention-config")
        assert response.status_code == 200
        assert response.json()["is_default"] is True

    def test_returns_404_when_storage_lacks_method(
        self, mock_storage: MagicMock, app_with_project: FastAPI
    ) -> None:
        del mock_storage.get_effective_prevention_config
        with TestClient(app_with_project) as c:
            response = c.get("/agents/orchestrator/prevention-config")
        assert response.status_code == 404

    def test_response_includes_updated_at_iso(
        self, tc: TestClient, mock_storage: MagicMock
    ) -> None:
        mock_storage.get_effective_prevention_config.return_value = _config()
        response = tc.get("/agents/orchestrator/prevention-config")
        assert response.status_code == 200
        data = response.json()
        assert "updated_at" in data
        assert "2026" in data["updated_at"]  # ISO 8601 format sanity check

    def test_returns_404_without_project_id(
        self, tc_no_project: TestClient
    ) -> None:
        """Without project_id (None), get_effective_prevention_config is not reached → 404."""
        response = tc_no_project.get("/agents/orchestrator/prevention-config")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# PUT /agents/{agent_name}/prevention-config
# ---------------------------------------------------------------------------


class TestUpsertAgentPreventionConfig:
    def test_creates_new_config_when_none_exists(
        self, tc: TestClient, mock_storage: MagicMock
    ) -> None:
        mock_storage.get_prevention_config.return_value = None
        mock_storage.upsert_prevention_config.return_value = _config(loop_threshold=5)
        response = tc.put(
            "/agents/orchestrator/prevention-config",
            json=_valid_body(loop_threshold=5),
        )
        assert response.status_code == 200
        mock_storage.upsert_prevention_config.assert_called_once()

    def test_preserves_existing_id_on_update(
        self, tc: TestClient, mock_storage: MagicMock
    ) -> None:
        """If a config already exists, the same ID must be reused."""
        existing = _config(id="existing-id-123")
        mock_storage.get_prevention_config.return_value = existing
        mock_storage.upsert_prevention_config.return_value = _config(
            id="existing-id-123"
        )
        tc.put(
            "/agents/orchestrator/prevention-config",
            json=_valid_body(),
        )
        saved: PreventionConfig = mock_storage.upsert_prevention_config.call_args[0][0]
        assert saved.id == "existing-id-123"

    def test_returns_422_for_invalid_loop_action(self, tc: TestClient) -> None:
        response = tc.put(
            "/agents/orchestrator/prevention-config",
            json=_valid_body(loop_action="explode"),
        )
        assert response.status_code == 422

    def test_returns_422_for_loop_threshold_below_one(self, tc: TestClient) -> None:
        response = tc.put(
            "/agents/orchestrator/prevention-config",
            json=_valid_body(loop_threshold=0),
        )
        assert response.status_code == 422

    def test_returns_422_for_negative_max_steps(self, tc: TestClient) -> None:
        response = tc.put(
            "/agents/orchestrator/prevention-config",
            json=_valid_body(max_steps=-1),
        )
        assert response.status_code == 422

    def test_returns_422_for_zero_max_cost_usd(self, tc: TestClient) -> None:
        response = tc.put(
            "/agents/orchestrator/prevention-config",
            json=_valid_body(max_cost_usd=0.0),
        )
        assert response.status_code == 422

    def test_accepts_warn_as_loop_action(
        self, tc: TestClient, mock_storage: MagicMock
    ) -> None:
        mock_storage.get_prevention_config.return_value = None
        mock_storage.upsert_prevention_config.return_value = _config(loop_action="warn")
        response = tc.put(
            "/agents/orchestrator/prevention-config",
            json=_valid_body(loop_action="warn"),
        )
        assert response.status_code == 200

    def test_accepts_optional_fields_as_null(
        self, tc: TestClient, mock_storage: MagicMock
    ) -> None:
        mock_storage.get_prevention_config.return_value = None
        mock_storage.upsert_prevention_config.return_value = _config()
        response = tc.put(
            "/agents/orchestrator/prevention-config",
            json=_valid_body(max_steps=None, max_cost_usd=None, max_wall_time_s=None),
        )
        assert response.status_code == 200

    def test_returns_422_for_cb_failure_threshold_below_one(
        self, tc: TestClient
    ) -> None:
        response = tc.put(
            "/agents/orchestrator/prevention-config",
            json=_valid_body(cb_failure_threshold=0),
        )
        assert response.status_code == 422

    def test_returns_422_for_budget_soft_alert_above_one(
        self, tc: TestClient
    ) -> None:
        response = tc.put(
            "/agents/orchestrator/prevention-config",
            json=_valid_body(budget_soft_alert=1.5),
        )
        assert response.status_code == 422

    def test_saved_config_uses_correct_agent_name(
        self, tc: TestClient, mock_storage: MagicMock
    ) -> None:
        mock_storage.get_prevention_config.return_value = None
        mock_storage.upsert_prevention_config.return_value = _config(
            agent_name="billing-agent"
        )
        tc.put(
            "/agents/billing-agent/prevention-config",
            json=_valid_body(),
        )
        saved: PreventionConfig = mock_storage.upsert_prevention_config.call_args[0][0]
        assert saved.agent_name == "billing-agent"

    def test_returns_400_without_project_id(
        self, tc_no_project: TestClient
    ) -> None:
        """Without project_id (None), the upsert handler raises 400."""
        response = tc_no_project.put(
            "/agents/orchestrator/prevention-config",
            json=_valid_body(),
        )
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# DELETE /agents/{agent_name}/prevention-config
# ---------------------------------------------------------------------------


class TestDeleteAgentPreventionConfig:
    def test_returns_204_when_config_deleted(
        self, tc: TestClient, mock_storage: MagicMock
    ) -> None:
        mock_storage.delete_prevention_config.return_value = True
        response = tc.delete("/agents/orchestrator/prevention-config")
        assert response.status_code == 204

    def test_returns_404_when_config_not_found(
        self, tc: TestClient, mock_storage: MagicMock
    ) -> None:
        mock_storage.delete_prevention_config.return_value = False
        response = tc.delete("/agents/orchestrator/prevention-config")
        assert response.status_code == 404

    def test_returns_404_when_storage_lacks_method(
        self, mock_storage: MagicMock, app_with_project: FastAPI
    ) -> None:
        del mock_storage.delete_prevention_config
        with TestClient(app_with_project) as c:
            response = c.delete("/agents/orchestrator/prevention-config")
        assert response.status_code == 404

    def test_calls_storage_with_correct_agent_name(
        self, tc: TestClient, mock_storage: MagicMock
    ) -> None:
        mock_storage.delete_prevention_config.return_value = True
        tc.delete("/agents/billing-agent/prevention-config")
        mock_storage.delete_prevention_config.assert_called_once()
        args = mock_storage.delete_prevention_config.call_args[0]
        assert "billing-agent" in args

    def test_returns_404_without_project_id(
        self, tc_no_project: TestClient
    ) -> None:
        """Without project_id (None), the delete handler raises 404."""
        response = tc_no_project.delete("/agents/orchestrator/prevention-config")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /projects/prevention-config
# ---------------------------------------------------------------------------


class TestGetProjectPreventionConfig:
    def test_returns_404_when_no_project_default(
        self, tc: TestClient, mock_storage: MagicMock
    ) -> None:
        mock_storage.get_prevention_config.return_value = None
        response = tc.get("/projects/prevention-config")
        assert response.status_code == 404

    def test_returns_project_default_when_set(
        self, tc: TestClient, mock_storage: MagicMock
    ) -> None:
        mock_storage.get_prevention_config.return_value = _config(agent_name="*")
        response = tc.get("/projects/prevention-config")
        assert response.status_code == 200
        data = response.json()
        assert data["agent_name"] == "*"
        assert data["is_default"] is True

    def test_queries_with_star_agent_name(
        self, tc: TestClient, mock_storage: MagicMock
    ) -> None:
        mock_storage.get_prevention_config.return_value = _config(agent_name="*")
        tc.get("/projects/prevention-config")
        call_args = mock_storage.get_prevention_config.call_args[0]
        assert "*" in call_args

    def test_returns_404_when_storage_lacks_method(
        self, mock_storage: MagicMock, app_with_project: FastAPI
    ) -> None:
        del mock_storage.get_prevention_config
        with TestClient(app_with_project) as c:
            response = c.get("/projects/prevention-config")
        assert response.status_code == 404

    def test_returns_404_without_project_id(
        self, tc_no_project: TestClient
    ) -> None:
        response = tc_no_project.get("/projects/prevention-config")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# PUT /projects/prevention-config
# ---------------------------------------------------------------------------


class TestUpsertProjectPreventionConfig:
    def test_creates_project_default_when_none_exists(
        self, tc: TestClient, mock_storage: MagicMock
    ) -> None:
        mock_storage.get_prevention_config.return_value = None
        mock_storage.upsert_prevention_config.return_value = _config(agent_name="*")
        response = tc.put("/projects/prevention-config", json=_valid_body())
        assert response.status_code == 200
        saved: PreventionConfig = mock_storage.upsert_prevention_config.call_args[0][0]
        assert saved.agent_name == "*"

    def test_preserves_existing_id_on_update(
        self, tc: TestClient, mock_storage: MagicMock
    ) -> None:
        existing = _config(agent_name="*", id="default-id-abc")
        mock_storage.get_prevention_config.return_value = existing
        mock_storage.upsert_prevention_config.return_value = _config(
            agent_name="*", id="default-id-abc"
        )
        tc.put("/projects/prevention-config", json=_valid_body())
        saved: PreventionConfig = mock_storage.upsert_prevention_config.call_args[0][0]
        assert saved.id == "default-id-abc"

    def test_saved_config_has_star_agent_name(
        self, tc: TestClient, mock_storage: MagicMock
    ) -> None:
        mock_storage.get_prevention_config.return_value = None
        mock_storage.upsert_prevention_config.return_value = _config(agent_name="*")
        tc.put("/projects/prevention-config", json=_valid_body())
        saved: PreventionConfig = mock_storage.upsert_prevention_config.call_args[0][0]
        assert saved.agent_name == "*"

    def test_returns_422_for_invalid_loop_action(self, tc: TestClient) -> None:
        response = tc.put(
            "/projects/prevention-config",
            json=_valid_body(loop_action="crash"),
        )
        assert response.status_code == 422

    def test_is_default_true_in_response(
        self, tc: TestClient, mock_storage: MagicMock
    ) -> None:
        mock_storage.get_prevention_config.return_value = None
        mock_storage.upsert_prevention_config.return_value = _config(agent_name="*")
        response = tc.put("/projects/prevention-config", json=_valid_body())
        assert response.json()["is_default"] is True

    def test_returns_400_without_project_id(
        self, tc_no_project: TestClient
    ) -> None:
        response = tc_no_project.put(
            "/projects/prevention-config", json=_valid_body()
        )
        assert response.status_code == 400
