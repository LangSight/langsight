"""
Security regression tests — session replay project isolation.

Invariant: replay re-executes tool calls against live MCP servers. It must
be scoped to the caller's project. A user who knows a session_id from another
project must not be able to trigger its replay.

The fix: engine.replay() now accepts project_id and passes it to
get_session_trace(), so ClickHouse scopes the lookup to the project.

Previously broken: the router validated project membership but then the engine
called get_session_trace(session_id) without project_id, leaking the session
to anyone with a valid project membership elsewhere.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.security


# ---------------------------------------------------------------------------
# Engine-level: project_id forwarded correctly
# ---------------------------------------------------------------------------

class TestReplayEngineProjectScoping:
    async def test_replay_passes_project_id_to_get_session_trace(self) -> None:
        """project_id must flow from engine.replay() into get_session_trace()."""
        from langsight.replay.engine import ReplayEngine

        storage = MagicMock()
        storage.get_session_trace = AsyncMock(return_value=[])  # no spans → ValueError

        engine = ReplayEngine(storage=storage, config=MagicMock())

        with pytest.raises(ValueError, match="not found"):
            await engine.replay("session-abc", project_id="project-x")

        storage.get_session_trace.assert_called_once_with(
            "session-abc", project_id="project-x"
        )

    async def test_replay_with_none_project_id_passes_none_not_skips(self) -> None:
        """Admin path: project_id=None must be explicitly forwarded, not dropped."""
        from langsight.replay.engine import ReplayEngine

        storage = MagicMock()
        storage.get_session_trace = AsyncMock(return_value=[])

        engine = ReplayEngine(storage=storage, config=MagicMock())

        with pytest.raises(ValueError):
            await engine.replay("session-xyz", project_id=None)

        # Verify None was passed through — not silently converted to something else
        storage.get_session_trace.assert_called_once_with(
            "session-xyz", project_id=None
        )

    async def test_replay_returns_not_found_for_empty_project_scoped_result(self) -> None:
        """get_session_trace returning [] (session not in this project) → ValueError.

        This is the cross-project attack path: attacker knows a foreign session_id,
        supplies their own project_id, and storage returns no spans because the
        session belongs to a different project.
        """
        from langsight.replay.engine import ReplayEngine

        storage = MagicMock()
        storage.get_session_trace = AsyncMock(return_value=[])  # scoped → no match

        engine = ReplayEngine(storage=storage, config=MagicMock())

        with pytest.raises(ValueError) as exc_info:
            await engine.replay("foreign-session-id", project_id="my-project")

        assert "not found" in str(exc_info.value).lower()

    async def test_replay_does_not_call_get_session_trace_without_clickhouse(self) -> None:
        """Engine must short-circuit with RuntimeError when backend lacks get_session_trace."""
        from langsight.replay.engine import ReplayEngine

        storage = MagicMock(spec=[])  # no get_session_trace attribute

        engine = ReplayEngine(storage=storage, config=MagicMock())

        with pytest.raises(RuntimeError, match="ClickHouse"):
            await engine.replay("any-session", project_id="proj-1")


# ---------------------------------------------------------------------------
# Router-level: replay endpoint wires project_id
# ---------------------------------------------------------------------------

class TestReplayRouterProjectWiring:
    async def test_replay_endpoint_requires_key_when_auth_enabled(
        self, auth_client
    ) -> None:
        """POST /api/agents/sessions/{id}/replay with no key → 401."""
        c, _, _ = auth_client
        response = await c.post("/api/agents/sessions/sess-123/replay")
        assert response.status_code in (401, 403)

    async def test_replay_endpoint_with_admin_key_and_missing_session_returns_404(
        self, auth_client
    ) -> None:
        """Env-key admin, session not found → 404 (not 500, not a data leak)."""
        c, mock_storage, _ = auth_client
        # Simulate ClickHouse returning no spans for this session
        mock_storage.get_session_trace = AsyncMock(return_value=[])

        response = await c.post(
            "/api/agents/sessions/nonexistent-session/replay?project_id=proj-1",
            headers={"X-API-Key": "test-api-key"},
        )
        assert response.status_code == 404

    async def test_replay_endpoint_returns_503_without_clickhouse(
        self, auth_client
    ) -> None:
        """Storage without get_session_trace → 503, not 500 or auth bypass."""
        c, mock_storage, _ = auth_client
        # Remove ClickHouse capability
        del mock_storage.get_session_trace

        response = await c.post(
            "/api/agents/sessions/any-session/replay",
            headers={"X-API-Key": "test-api-key"},
        )
        assert response.status_code == 503


# ---------------------------------------------------------------------------
# Verify project_id actually limits what storage receives
# ---------------------------------------------------------------------------

class TestReplayStorageReceivesProjectFilter:
    async def test_storage_receives_correct_project_id_not_none(self) -> None:
        """When a non-admin replays with project_id=my-proj, storage gets my-proj.

        This is the critical property: storage must filter to the project, not
        receive None (which would be unfiltered cross-project access).
        """
        from langsight.replay.engine import ReplayEngine

        storage = MagicMock()
        # Return empty to trigger ValueError (session not found in project)
        storage.get_session_trace = AsyncMock(return_value=[])
        engine = ReplayEngine(storage=storage, config=MagicMock())

        with pytest.raises(ValueError):
            await engine.replay("sess-foreign", project_id="my-proj")

        # The key assertion: storage was told to look in "my-proj", not None
        args, kwargs = storage.get_session_trace.call_args
        assert kwargs.get("project_id") == "my-proj", (
            "Storage must receive the project_id filter — None would expose "
            "cross-project sessions"
        )
