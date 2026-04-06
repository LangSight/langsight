"""Tests for monkey-patch auto-instrumentation."""

from __future__ import annotations

import asyncio
import sys

import pytest

from langsight.sdk.auto_patch import (
    _agent_ctx,
    _patched_sdks,
    _session_ctx,
    auto_patch,
    clear_context,
    session,
    set_context,
    unpatch,
)
from langsight.sdk.client import LangSightClient


@pytest.fixture(autouse=True)
def _reset_patch_state():
    """Ensure each test starts and ends with clean patch state."""
    unpatch()
    _session_ctx.set(None)
    _agent_ctx.set(None)
    yield
    unpatch()
    _session_ctx.set(None)
    _agent_ctx.set(None)


@pytest.fixture
def ls():
    return LangSightClient(url="http://localhost:8000")


# =============================================================================
# Context variables
# =============================================================================


class TestContextVariables:
    def test_set_and_read_session(self) -> None:
        tokens = set_context(session_id="sess-001")
        assert _session_ctx.get() == "sess-001"
        clear_context(tokens)
        assert _session_ctx.get() is None

    def test_set_and_read_agent(self) -> None:
        tokens = set_context(agent_name="orchestrator")
        assert _agent_ctx.get() == "orchestrator"
        clear_context(tokens)
        assert _agent_ctx.get() is None

    def test_set_multiple_fields(self) -> None:
        tokens = set_context(session_id="s1", agent_name="analyst")
        assert _session_ctx.get() == "s1"
        assert _agent_ctx.get() == "analyst"
        clear_context(tokens)
        assert _session_ctx.get() is None
        assert _agent_ctx.get() is None

    @pytest.mark.asyncio
    async def test_session_context_manager_generates_uuid(self) -> None:
        async with session(agent_name="orchestrator") as sid:
            assert len(sid) == 36  # UUID format
            assert _session_ctx.get() == sid
            assert _agent_ctx.get() == "orchestrator"
        # After exit, context is cleared
        assert _session_ctx.get() is None
        assert _agent_ctx.get() is None

    @pytest.mark.asyncio
    async def test_session_context_manager_accepts_explicit_id(self) -> None:
        async with session(session_id="my-session") as sid:
            assert sid == "my-session"
            assert _session_ctx.get() == "my-session"

    @pytest.mark.asyncio
    async def test_context_isolated_between_tasks(self) -> None:
        """asyncio tasks get independent copies of context variables."""
        tokens = set_context(session_id="outer-session")
        inner_session: list[str | None] = []

        async def inner_task() -> None:
            # This task inherits the parent context at creation time
            # but changes in inner don't affect outer
            set_context(session_id="inner-session")
            inner_session.append(_session_ctx.get())

        await asyncio.create_task(inner_task())
        # Outer context unchanged
        assert _session_ctx.get() == "outer-session"
        assert inner_session[0] == "inner-session"
        clear_context(tokens)


# =============================================================================
# auto_patch() - returns None when URL not set
# =============================================================================


class TestAutoPatch:
    def test_returns_none_when_url_not_set(self, monkeypatch) -> None:
        """auto_patch() without URL returns None but still installs patches
        (deferred init — client will be created on first span once env is set)."""
        monkeypatch.delenv("LANGSIGHT_URL", raising=False)
        result = auto_patch()
        assert result is None
        # Patches are installed even without URL — deferred lazy init
        assert len(_patched_sdks) > 0

    def test_returns_client_when_url_set(self, monkeypatch) -> None:
        monkeypatch.setenv("LANGSIGHT_URL", "http://localhost:8000")
        result = auto_patch()
        assert isinstance(result, LangSightClient)


# =============================================================================
# unpatch() restores originals
# =============================================================================


class TestUnpatch:
    def test_unpatch_clears_state(self, monkeypatch) -> None:
        monkeypatch.setenv("LANGSIGHT_URL", "http://localhost:8000")
        auto_patch()
        assert len(_patched_sdks) > 0
        unpatch()
        assert len(_patched_sdks) == 0


# =============================================================================
# _AutoPatchProxy emits spans with context
# =============================================================================


class TestAutoPatchProxy:
    def test_proxy_emits_with_context(self) -> None:
        """Proxy reads session_id and agent_name from context vars."""
        from langsight.sdk.auto_patch import _AutoPatchProxy

        ls = LangSightClient(url="http://localhost:8000")
        captured: list = []
        ls.buffer_span = lambda s: captured.append(s)  # type: ignore[assignment]

        tokens = set_context(session_id="sess-test", agent_name="test-agent")
        proxy = _AutoPatchProxy(ls, agent_name=_agent_ctx.get(), session_id=_session_ctx.get())

        from datetime import UTC, datetime

        from langsight.sdk.models import ToolCallSpan, ToolCallStatus

        span = ToolCallSpan.record(
            server_name="openai",
            tool_name="generate/gpt-4o",
            started_at=datetime.now(UTC),
            status=ToolCallStatus.SUCCESS,
            session_id="sess-test",
            agent_name="test-agent",
        )
        proxy._emit_spans([span])

        assert len(captured) == 1
        assert captured[0].session_id == "sess-test"
        assert captured[0].agent_name == "test-agent"
        clear_context(tokens)


# =============================================================================
# Top-level langsight.auto_patch import
# =============================================================================


class TestTopLevelImport:
    def test_importable_at_top_level(self) -> None:
        import langsight

        assert hasattr(langsight, "auto_patch")
        assert callable(langsight.auto_patch)
        assert hasattr(langsight, "session")
        assert hasattr(langsight, "set_context")
        assert hasattr(langsight, "clear_context")
        assert hasattr(langsight, "unpatch")


# =============================================================================
# _patch_crewai() — zero-code CrewAI auto-patching
# =============================================================================


class TestPatchCrewAI:
    """Tests for _patch_crewai() auto-injection of LangSightCrewAICallback."""

    def test_patch_crewai_noop_without_global_client(self) -> None:
        """_patch_crewai() is a no-op when no global client is set."""
        import importlib

        ap_mod = importlib.import_module("langsight.sdk.auto_patch")

        # Ensure global client is None and crewai not in patched set
        unpatch()
        assert ap_mod._global_client is None
        ap_mod._patch_crewai()
        assert "crewai" not in ap_mod._patched_sdks

    def _setup_fake_crewai(self, monkeypatch):
        """Helper: install a fake crewai module and set _global_client.

        Returns (fake_crewai_mod, FakeCrew, FakeAgent, ls_client, ap_module).
        ``ap_module`` is the real ``langsight.sdk.auto_patch`` module object
        (not the re-exported function from ``langsight.sdk``).
        """
        import importlib
        import sys
        import types

        # Import the REAL module object (not the function alias in langsight.sdk)
        ap_mod = importlib.import_module("langsight.sdk.auto_patch")

        fake_crewai = types.ModuleType("crewai")

        class FakeCrew:
            def __init__(self, **kw):
                self.callbacks = []
                self.agents = []

            def kickoff(self, *args, **kw):
                return "done"

        class FakeAgent:
            def __init__(self, **kw):
                self.callbacks = []
                self.role = kw.get("role", "")

        fake_crewai.Crew = FakeCrew  # type: ignore[attr-defined]
        fake_crewai.Agent = FakeAgent  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "crewai", fake_crewai)

        ls = LangSightClient(url="http://localhost:8000")
        ap_mod._global_client = ls
        return fake_crewai, FakeCrew, FakeAgent, ls, ap_mod

    def test_patch_crewai_idempotent(self, monkeypatch) -> None:
        """Calling _patch_crewai() twice does not double-patch."""
        import importlib

        ap_mod = importlib.import_module("langsight.sdk.auto_patch")
        _, FakeCrew, _, _, _ = self._setup_fake_crewai(monkeypatch)

        ap_mod._patch_crewai()
        first_init = FakeCrew.__init__

        ap_mod._patch_crewai()  # second call — should be idempotent
        assert FakeCrew.__init__ is first_init  # not re-patched

    def test_patch_crewai_patches_base_tool_run(self, monkeypatch) -> None:
        """_patch_crewai() patches BaseTool._run to capture tool calls."""
        import importlib

        ap_mod = importlib.import_module("langsight.sdk.auto_patch")
        _, FakeCrew, _, _, _ = self._setup_fake_crewai(monkeypatch)

        # Install a fake BaseTool in sys.modules for the test
        import types

        fake_base_tool_mod = types.ModuleType("crewai.tools.base_tool")

        class FakeBaseTool:
            def _run(self, *args, **kw):
                return "result"

        fake_base_tool_mod.BaseTool = FakeBaseTool  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "crewai.tools.base_tool", fake_base_tool_mod)
        monkeypatch.setitem(sys.modules, "crewai.tools", fake_base_tool_mod)
        monkeypatch.setitem(sys.modules, "crewai.agent.core", types.ModuleType("crewai.agent.core"))

        ap_mod._patch_crewai()

        # BaseTool._run should be patched
        assert "crewai_base_tool_run" in ap_mod._originals
        assert FakeBaseTool._run is not ap_mod._originals["crewai_base_tool_run"]

    def test_patch_crewai_patches_crew_kickoff(self, monkeypatch) -> None:
        """_patch_crewai() patches Crew.kickoff for auto session_id."""
        import importlib

        ap_mod = importlib.import_module("langsight.sdk.auto_patch")
        _, FakeCrew, _, _, _ = self._setup_fake_crewai(monkeypatch)

        ap_mod._patch_crewai()

        assert "crewai_kickoff" in ap_mod._originals
        assert FakeCrew.kickoff is not ap_mod._originals["crewai_kickoff"]

    def test_patch_crewai_no_duplicate_patches(self, monkeypatch) -> None:
        """Calling _patch_crewai() twice does not double-patch."""
        import importlib

        ap_mod = importlib.import_module("langsight.sdk.auto_patch")
        _, FakeCrew, _, _, _ = self._setup_fake_crewai(monkeypatch)

        ap_mod._patch_crewai()
        kickoff_after_first = FakeCrew.kickoff

        # Second call must be idempotent — crewai already in _patched_sdks
        ap_mod._patch_crewai()
        assert FakeCrew.kickoff is kickoff_after_first  # not re-patched

    def test_patch_crewai_skipped_in_skipped_missing_list(
        self, monkeypatch
    ) -> None:
        """When crewai is absent, auto_patch does not add 'crewai' to patched_sdks."""
        import importlib
        import sys

        ap_mod = importlib.import_module("langsight.sdk.auto_patch")

        # Remove crewai from sys.modules if present, ensure it fails to import
        monkeypatch.delitem(sys.modules, "crewai", raising=False)

        import builtins

        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "crewai":
                raise ImportError("no module named crewai")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)
        monkeypatch.setenv("LANGSIGHT_URL", "http://localhost:8000")

        auto_patch()
        assert "crewai" not in ap_mod._patched_sdks
