"""Tests for monkey-patch auto-instrumentation."""

from __future__ import annotations

import asyncio

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
        monkeypatch.delenv("LANGSIGHT_URL", raising=False)
        result = auto_patch()
        assert result is None
        assert len(_patched_sdks) == 0

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
