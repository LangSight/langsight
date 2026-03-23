"""
Unit tests for project-scoped changes in the SLOs router.

Covers:
- GET /api/slos passes project_id to storage.list_slos
- POST /api/slos stamps project_id on the created SLO
- DELETE /api/slos/{id} passes project_id to storage.delete_slo
- DELETE returns 404 when storage.delete_slo returns False (cross-project guard)
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml
from httpx import ASGITransport, AsyncClient

from langsight.api.main import create_app
from langsight.config import load_config
from langsight.models import AgentSLO, SLOMetric

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    cfg = tmp_path / ".langsight.yaml"
    cfg.write_text(yaml.dump({"servers": []}))
    return cfg


def _make_storage(
    list_slos_return: list | None = None,
    delete_slo_return: bool = True,
) -> MagicMock:
    storage = MagicMock()
    storage.close = AsyncMock()
    storage.list_api_keys = AsyncMock(return_value=[])
    storage.list_members = AsyncMock(return_value=[])
    storage.create_slo = AsyncMock()
    storage.list_slos = AsyncMock(return_value=list_slos_return or [])
    storage.get_slo = AsyncMock(return_value=None)
    storage.delete_slo = AsyncMock(return_value=delete_slo_return)
    return storage


def _make_slo(project_id: str = "proj-a") -> AgentSLO:
    return AgentSLO(
        id="slo-001",
        agent_name="my-bot",
        metric=SLOMetric.SUCCESS_RATE,
        target=95.0,
        window_hours=24,
        project_id=project_id,
        created_at=datetime.now(UTC),
    )


@pytest.fixture
async def client(config_file: Path):
    """Test client with mocked storage. Auth disabled (no keys in storage)."""
    app = create_app(config_path=config_file)
    storage = _make_storage()
    app.state.storage = storage
    app.state.config = load_config(config_file)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, storage


# ---------------------------------------------------------------------------
# GET /api/slos — project_id forwarding
# ---------------------------------------------------------------------------


class TestListSLOsProjectScoping:
    async def test_passes_project_id_to_storage_when_provided(self, client) -> None:
        """list_slos must receive the project_id query param."""
        c, storage = client
        storage.list_slos = AsyncMock(return_value=[])

        response = await c.get("/api/slos?project_id=proj-alpha")

        assert response.status_code == 200
        storage.list_slos.assert_called_once()
        call_kwargs = storage.list_slos.call_args[1]
        assert call_kwargs.get("project_id") == "proj-alpha"

    async def test_passes_none_project_id_when_not_provided(self, client) -> None:
        """When no project_id is in the request, storage receives None."""
        c, storage = client
        storage.list_slos = AsyncMock(return_value=[])

        response = await c.get("/api/slos")

        assert response.status_code == 200
        storage.list_slos.assert_called_once()
        call_kwargs = storage.list_slos.call_args[1]
        assert call_kwargs.get("project_id") is None

    async def test_returns_only_slos_returned_by_storage(self, client) -> None:
        """Router returns exactly what storage gives back (storage enforces filtering)."""
        c, storage = client
        slo_a = _make_slo("proj-a")
        slo_b = _make_slo("proj-a")
        slo_b = slo_b.model_copy(update={"id": "slo-002", "agent_name": "other-bot"})
        storage.list_slos = AsyncMock(return_value=[slo_a, slo_b])

        response = await c.get("/api/slos?project_id=proj-a")

        data = response.json()
        assert len(data) == 2
        agent_names = {d["agent_name"] for d in data}
        assert agent_names == {"my-bot", "other-bot"}

    async def test_different_project_ids_produce_separate_calls(self, client) -> None:
        """Two consecutive requests with different project_ids each hit storage with their own id."""
        c, storage = client
        storage.list_slos = AsyncMock(return_value=[])

        await c.get("/api/slos?project_id=proj-x")
        await c.get("/api/slos?project_id=proj-y")

        assert storage.list_slos.call_count == 2
        first_project = storage.list_slos.call_args_list[0][1].get("project_id")
        second_project = storage.list_slos.call_args_list[1][1].get("project_id")
        assert first_project == "proj-x"
        assert second_project == "proj-y"

    async def test_returns_empty_list_when_no_slos_for_project(self, client) -> None:
        """Empty storage response produces empty JSON array."""
        c, storage = client
        storage.list_slos = AsyncMock(return_value=[])

        response = await c.get("/api/slos?project_id=nonexistent-project")

        assert response.status_code == 200
        assert response.json() == []


# ---------------------------------------------------------------------------
# POST /api/slos — project_id stamped on created SLO
# ---------------------------------------------------------------------------


class TestCreateSLOProjectScoping:
    async def test_created_slo_carries_provided_project_id(self, client) -> None:
        """POST body has no project_id — router stamps it from the active project dep."""
        c, storage = client

        response = await c.post(
            "/api/slos?project_id=proj-alpha",
            json={
                "agent_name": "billing-agent",
                "metric": "success_rate",
                "target": 99.0,
                "window_hours": 24,
            },
        )

        assert response.status_code == 201
        storage.create_slo.assert_called_once()
        saved_slo: AgentSLO = storage.create_slo.call_args[0][0]
        assert saved_slo.project_id == "proj-alpha"

    async def test_created_slo_has_empty_project_id_when_none_provided(self, client) -> None:
        """Without project_id param, the SLO is stamped with empty string."""
        c, storage = client

        response = await c.post(
            "/api/slos",
            json={
                "agent_name": "finance-agent",
                "metric": "success_rate",
                "target": 95.0,
                "window_hours": 48,
            },
        )

        assert response.status_code == 201
        saved_slo: AgentSLO = storage.create_slo.call_args[0][0]
        # project_id=None from dependency → stamped as "" by the router
        assert saved_slo.project_id == ""

    async def test_response_contains_agent_name_and_target(self, client) -> None:
        """The 201 response body reflects the submitted values."""
        c, storage = client

        response = await c.post(
            "/api/slos?project_id=proj-beta",
            json={
                "agent_name": "support-bot",
                "metric": "latency_p99",
                "target": 500.0,
                "window_hours": 12,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["agent_name"] == "support-bot"
        assert data["target"] == 500.0
        assert data["metric"] == "latency_p99"

    async def test_create_slo_called_exactly_once(self, client) -> None:
        """Storage is written to exactly once per POST."""
        c, storage = client

        await c.post(
            "/api/slos",
            json={
                "agent_name": "agent-x",
                "metric": "success_rate",
                "target": 90.0,
                "window_hours": 24,
            },
        )

        storage.create_slo.assert_called_once()

    async def test_created_slo_has_unique_id(self, client) -> None:
        """Each POST generates a fresh non-empty ID (not shared across calls)."""
        c, storage = client

        await c.post(
            "/api/slos",
            json={"agent_name": "a1", "metric": "success_rate", "target": 95.0, "window_hours": 24},
        )
        await c.post(
            "/api/slos",
            json={"agent_name": "a2", "metric": "success_rate", "target": 95.0, "window_hours": 24},
        )

        id_first = storage.create_slo.call_args_list[0][0][0].id
        id_second = storage.create_slo.call_args_list[1][0][0].id
        assert id_first != id_second
        assert id_first  # non-empty
        assert id_second  # non-empty


# ---------------------------------------------------------------------------
# DELETE /api/slos/{id} — project_id forwarded, 404 on cross-project guard
# ---------------------------------------------------------------------------


class TestDeleteSLOProjectScoping:
    async def test_delete_passes_project_id_to_storage(self, client) -> None:
        """delete_slo must receive the slo_id AND project_id from the request."""
        c, storage = client
        storage.delete_slo = AsyncMock(return_value=True)

        response = await c.delete("/api/slos/slo-001?project_id=proj-alpha")

        assert response.status_code == 204
        storage.delete_slo.assert_called_once()
        call_kwargs = storage.delete_slo.call_args[1]
        assert call_kwargs.get("project_id") == "proj-alpha"

    async def test_delete_passes_slo_id_positionally(self, client) -> None:
        """The slo_id must be forwarded as the first positional arg to storage."""
        c, storage = client
        storage.delete_slo = AsyncMock(return_value=True)

        await c.delete("/api/slos/target-slo-123?project_id=proj-gamma")

        positional_slo_id = storage.delete_slo.call_args[0][0]
        assert positional_slo_id == "target-slo-123"

    async def test_delete_returns_404_when_storage_returns_false(self, client) -> None:
        """Storage returning False means SLO not found in this project — must yield 404."""
        c, storage = client
        storage.delete_slo = AsyncMock(return_value=False)

        response = await c.delete("/api/slos/slo-from-other-project?project_id=proj-alpha")

        assert response.status_code == 404

    async def test_delete_404_detail_mentions_slo_id(self, client) -> None:
        """The 404 error body should reference the SLO id for diagnostics."""
        c, storage = client
        storage.delete_slo = AsyncMock(return_value=False)

        response = await c.delete("/api/slos/slo-xyz?project_id=proj-alpha")

        assert response.status_code == 404
        assert "slo-xyz" in response.json()["detail"]

    async def test_delete_without_project_id_passes_none_to_storage(self, client) -> None:
        """Omitting project_id means the dependency resolves to None."""
        c, storage = client
        storage.delete_slo = AsyncMock(return_value=True)

        response = await c.delete("/api/slos/slo-001")

        assert response.status_code == 204
        call_kwargs = storage.delete_slo.call_args[1]
        assert call_kwargs.get("project_id") is None

    async def test_delete_same_slo_in_different_projects_uses_correct_project(
        self, client
    ) -> None:
        """The project_id from the request — not a global default — is forwarded."""
        c, storage = client
        storage.delete_slo = AsyncMock(return_value=True)

        await c.delete("/api/slos/slo-001?project_id=proj-1")
        await c.delete("/api/slos/slo-001?project_id=proj-2")

        first_project = storage.delete_slo.call_args_list[0][1].get("project_id")
        second_project = storage.delete_slo.call_args_list[1][1].get("project_id")
        assert first_project == "proj-1"
        assert second_project == "proj-2"
