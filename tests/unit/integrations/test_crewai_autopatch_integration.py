"""
End-to-end auto_patch integration tests for the CrewAI zero-code feature.

These tests cover the *wiring* between auto_patch() and the CrewAI callback —
things the existing unit tests do NOT cover:

  1. auto_patch() end-to-end → callback injected into a Crew instance
  2. Agent role → agent_name flow through auto_patch (not just _patch_crewai)
  3. MCP tool full flow: mcp__analytics__query_warehouse arrives at on_tool_end,
     span carries correct server_name / tool_name
  4. Session context (_session_ctx) inheritance by the callback during on_tool_start
  5. No duplicate callbacks after calling auto_patch twice on the same Crew class
  6. Regression: calling _patch_crewai() must NOT remove openai / anthropic / mcp
     from _patched_sdks (i.e. other patches survive CrewAI patching)

All dependencies on crewai are provided via MagicMock / fake module — crewai
does not need to be installed.

asyncio_mode = "auto" is set in pyproject.toml, so no @pytest.mark.asyncio
decorator is needed on async tests.
"""

from __future__ import annotations

import importlib
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

from langsight.integrations.crewai import LangSightCrewAICallback
from langsight.sdk.auto_patch import _session_ctx, unpatch
from langsight.sdk.client import LangSightClient
from langsight.sdk.models import ToolCallStatus


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_client() -> LangSightClient:
    return LangSightClient(url="http://localhost:8000")


def _install_fake_crewai(monkeypatch) -> tuple[types.ModuleType, type, type]:
    """Register a minimal fake crewai module in sys.modules.

    Returns (fake_crewai_module, FakeCrew, FakeAgent).
    The caller is responsible for removing it via monkeypatch (automatic on
    fixture teardown).
    """
    fake_crewai = types.ModuleType("crewai")

    class FakeCrew:
        def __init__(self, **kw):
            self.callbacks: list = []
            self.agents: list = []

        def kickoff(self, *args, **kw):  # required for auto_patch kickoff patch
            return "done"

    class FakeAgent:
        def __init__(self, **kw):
            self.callbacks: list = []
            self.role: str = kw.get("role", "")

    fake_crewai.Crew = FakeCrew  # type: ignore[attr-defined]
    fake_crewai.Agent = FakeAgent  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "crewai", fake_crewai)
    return fake_crewai, FakeCrew, FakeAgent


def _ap_mod():
    """Return the real langsight.sdk.auto_patch module object."""
    return importlib.import_module("langsight.sdk.auto_patch")


# ---------------------------------------------------------------------------
# Per-test reset: unpatching after each test keeps module state clean.
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    """Unpatch before and after every test; reset context vars."""
    unpatch()
    _session_ctx.set(None)
    yield
    unpatch()
    _session_ctx.set(None)


# ===========================================================================
# 1. End-to-end auto_patch integration
#    auto_patch() with a URL set and fake crewai present must inject
#    LangSightCrewAICallback into a Crew instance transparently.
# ===========================================================================

class TestAutoPatchEndToEnd:
    def test_auto_patch_injects_callback_into_crew_instance(
        self, monkeypatch
    ) -> None:
        """After langsight.auto_patch(), constructing a Crew adds the callback."""
        _, FakeCrew, _ = _install_fake_crewai(monkeypatch)
        monkeypatch.setenv("LANGSIGHT_URL", "http://localhost:8000")

        import langsight

        langsight.auto_patch()

        crew = FakeCrew()
        ls_callbacks = [c for c in crew.callbacks if isinstance(c, LangSightCrewAICallback)]
        assert len(ls_callbacks) == 1, (
            "Exactly one LangSightCrewAICallback must be injected into Crew.callbacks"
        )

    def test_auto_patch_without_url_still_patches_crewai(self, monkeypatch) -> None:
        """When LANGSIGHT_URL is not set, auto_patch returns None but CrewAI IS
        patched (deferred init). The callback has a None client and will lazily
        resolve it on first span once env is available."""
        _, FakeCrew, _ = _install_fake_crewai(monkeypatch)
        monkeypatch.delenv("LANGSIGHT_URL", raising=False)

        import langsight

        result = langsight.auto_patch()
        assert result is None  # no client yet

        crew = FakeCrew()
        # Crew IS patched — callback present with None client (lazy init)
        ls_callbacks = [c for c in crew.callbacks if isinstance(c, LangSightCrewAICallback)]
        assert len(ls_callbacks) == 1
        assert ls_callbacks[0]._client is None  # will be resolved on first span

    def test_auto_patch_returns_client_instance(self, monkeypatch) -> None:
        """auto_patch returns a LangSightClient, not None, when URL is set."""
        _install_fake_crewai(monkeypatch)
        monkeypatch.setenv("LANGSIGHT_URL", "http://localhost:8000")

        import langsight

        result = langsight.auto_patch()
        assert isinstance(result, LangSightClient)

    def test_crewai_added_to_patched_sdks_after_auto_patch(
        self, monkeypatch
    ) -> None:
        """_patched_sdks must contain 'crewai' after a successful auto_patch."""
        _install_fake_crewai(monkeypatch)
        monkeypatch.setenv("LANGSIGHT_URL", "http://localhost:8000")

        ap = _ap_mod()
        import langsight

        langsight.auto_patch()
        assert "crewai" in ap._patched_sdks


# ===========================================================================
# 2. Agent role → agent_name via auto_patch
#    The patched Agent.__init__ must extract role and call set_agent_name.
# ===========================================================================

class TestAgentRoleToAgentName:
    def test_role_becomes_agent_name_on_callback(self, monkeypatch) -> None:
        """Agent(role='SQL Analyst') → callback._agent_name == 'SQL Analyst'."""
        _, _, FakeAgent = _install_fake_crewai(monkeypatch)
        monkeypatch.setenv("LANGSIGHT_URL", "http://localhost:8000")

        import langsight

        langsight.auto_patch()

        agent = FakeAgent(role="SQL Analyst")
        ls_cbs = [c for c in agent.callbacks if isinstance(c, LangSightCrewAICallback)]
        assert len(ls_cbs) == 1
        assert ls_cbs[0]._agent_name == "SQL Analyst"

    def test_empty_role_leaves_agent_name_as_none(self, monkeypatch) -> None:
        """Agent with no role leaves callback._agent_name as None (not set_agent_name
        on an empty string, since the patcher guards with `if role`)."""
        _, _, FakeAgent = _install_fake_crewai(monkeypatch)
        monkeypatch.setenv("LANGSIGHT_URL", "http://localhost:8000")

        import langsight

        langsight.auto_patch()

        agent = FakeAgent(role="")
        ls_cbs = [c for c in agent.callbacks if isinstance(c, LangSightCrewAICallback)]
        assert len(ls_cbs) == 1
        # Empty role must NOT be set — _agent_name stays None
        assert ls_cbs[0]._agent_name is None

    def test_different_agents_get_independent_callbacks(self, monkeypatch) -> None:
        """Each Agent instance gets its own callback with its own role."""
        _, _, FakeAgent = _install_fake_crewai(monkeypatch)
        monkeypatch.setenv("LANGSIGHT_URL", "http://localhost:8000")

        import langsight

        langsight.auto_patch()

        analyst = FakeAgent(role="Data Analyst")
        engineer = FakeAgent(role="Data Engineer")

        analyst_cb = next(c for c in analyst.callbacks if isinstance(c, LangSightCrewAICallback))
        engineer_cb = next(c for c in engineer.callbacks if isinstance(c, LangSightCrewAICallback))

        assert analyst_cb._agent_name == "Data Analyst"
        assert engineer_cb._agent_name == "Data Engineer"
        assert analyst_cb is not engineer_cb


# ===========================================================================
# 3. MCP tool call full flow
#    mcp__analytics__query_warehouse → server_name="analytics", tool_name="query_warehouse"
# ===========================================================================

class TestMcpToolCallFullFlow:
    async def test_mcp_tool_name_parsed_in_full_flow(self, monkeypatch) -> None:
        """on_tool_start + on_tool_end with mcp__analytics__query_warehouse
        produces a span with server_name='analytics' and tool_name='query_warehouse'."""
        client = _make_client()
        captured: list = []
        client.buffer_span = lambda s: captured.append(s)  # type: ignore[assignment]

        cb = LangSightCrewAICallback(
            client=client,
            server_name="fallback-server",
            agent_name="warehouse-agent",
        )

        cb.on_tool_start("mcp__analytics__query_warehouse", {"sql": "SELECT 1"})
        await cb.on_tool_end("mcp__analytics__query_warehouse", [{"row": 1}])

        assert len(captured) == 1
        span = captured[0]
        assert span.server_name == "analytics"
        assert span.tool_name == "query_warehouse"
        assert span.status == ToolCallStatus.SUCCESS

    async def test_mcp_tool_error_full_flow_parsed_correctly(
        self, monkeypatch
    ) -> None:
        """on_tool_error with mcp__analytics__query_warehouse parses server name."""
        client = _make_client()
        captured: list = []
        client.buffer_span = lambda s: captured.append(s)  # type: ignore[assignment]

        cb = LangSightCrewAICallback(client=client, server_name="fallback")
        cb.on_tool_start("mcp__analytics__query_warehouse", {})
        await cb.on_tool_error(
            "mcp__analytics__query_warehouse", RuntimeError("timeout")
        )

        span = captured[0]
        assert span.server_name == "analytics"
        assert span.tool_name == "query_warehouse"
        assert span.status == ToolCallStatus.ERROR
        assert "timeout" in (span.error or "")

    async def test_non_mcp_tool_uses_fallback_server_name(self) -> None:
        """Tools not matching mcp__server__tool use the configured server_name."""
        client = _make_client()
        captured: list = []
        client.buffer_span = lambda s: captured.append(s)  # type: ignore[assignment]

        cb = LangSightCrewAICallback(client=client, server_name="my-server")
        cb.on_tool_start("query_database", "SELECT 1")
        await cb.on_tool_end("query_database", [])

        span = captured[0]
        assert span.server_name == "my-server"
        assert span.tool_name == "query_database"

    async def test_agent_name_carried_into_span(self) -> None:
        """agent_name set via set_agent_name() is carried into the buffered span."""
        client = _make_client()
        captured: list = []
        client.buffer_span = lambda s: captured.append(s)  # type: ignore[assignment]

        cb = LangSightCrewAICallback(client=client, server_name="pg")
        cb.set_agent_name("Analytics Agent")
        cb.on_tool_start("mcp__analytics__query_warehouse", {})
        await cb.on_tool_end("mcp__analytics__query_warehouse", "ok")

        span = captured[0]
        assert span.agent_name == "Analytics Agent"


# ===========================================================================
# 4. Session context inheritance via _session_ctx
#    When _session_ctx holds a value, on_tool_start must lazily adopt it.
# ===========================================================================

class TestSessionContextInheritance:
    def test_session_id_picked_up_from_context_var_on_tool_start(self) -> None:
        """Callback constructed without session_id inherits _session_ctx on
        the first on_tool_start call."""
        client = _make_client()
        cb = LangSightCrewAICallback(client=client)
        assert cb._session_id is None

        token = _session_ctx.set("sess-abc-123")
        try:
            cb.on_tool_start("ping", {})
            assert cb._session_id == "sess-abc-123"
        finally:
            _session_ctx.reset(token)

    async def test_session_id_in_context_flows_into_span(self) -> None:
        """The session_id resolved from context var appears in the buffered span."""
        client = _make_client()
        captured: list = []
        client.buffer_span = lambda s: captured.append(s)  # type: ignore[assignment]

        cb = LangSightCrewAICallback(client=client)

        token = _session_ctx.set("sess-xyz-789")
        try:
            cb.on_tool_start("mcp__db__run_query", {})
            await cb.on_tool_end("mcp__db__run_query", [])
        finally:
            _session_ctx.reset(token)

        assert len(captured) == 1
        assert captured[0].session_id == "sess-xyz-789"

    def test_explicit_session_id_not_overwritten_by_context_var(self) -> None:
        """When session_id is supplied at construction time, _session_ctx is ignored."""
        client = _make_client()
        cb = LangSightCrewAICallback(client=client, session_id="explicit-session")

        token = _session_ctx.set("context-session")
        try:
            cb.on_tool_start("tool", {})
            # explicit session must NOT be overwritten
            assert cb._session_id == "explicit-session"
        finally:
            _session_ctx.reset(token)

    def test_no_session_context_leaves_session_id_none(self) -> None:
        """When _session_ctx holds None, session_id stays None after on_tool_start."""
        client = _make_client()
        cb = LangSightCrewAICallback(client=client)
        # _session_ctx is None (reset by _reset fixture)
        cb.on_tool_start("tool", {})
        assert cb._session_id is None


# ===========================================================================
# 5. No duplicate callbacks after calling auto_patch twice
# ===========================================================================

class TestNoDuplicateCallbacks:
    def test_auto_patch_twice_injects_callback_once_into_crew(
        self, monkeypatch
    ) -> None:
        """Calling auto_patch() twice must not create duplicate callbacks.

        The second call is idempotent because _patch_crewai() guards on
        'crewai' in _patched_sdks, so the original Crew.__init__ is not
        re-patched. A single Crew() call must result in exactly one callback.
        """
        _, FakeCrew, _ = _install_fake_crewai(monkeypatch)
        monkeypatch.setenv("LANGSIGHT_URL", "http://localhost:8000")

        import langsight

        langsight.auto_patch()
        langsight.auto_patch()  # second call — must be idempotent

        crew = FakeCrew()
        ls_callbacks = [c for c in crew.callbacks if isinstance(c, LangSightCrewAICallback)]
        assert len(ls_callbacks) == 1, (
            f"Expected 1 callback, got {len(ls_callbacks)}. "
            "Duplicate injection detected — idempotency guard is broken."
        )

    def test_auto_patch_twice_injects_callback_once_into_agent(
        self, monkeypatch
    ) -> None:
        """Same idempotency guarantee for Agent instances."""
        _, _, FakeAgent = _install_fake_crewai(monkeypatch)
        monkeypatch.setenv("LANGSIGHT_URL", "http://localhost:8000")

        import langsight

        langsight.auto_patch()
        langsight.auto_patch()

        agent = FakeAgent(role="Analyst")
        ls_callbacks = [c for c in agent.callbacks if isinstance(c, LangSightCrewAICallback)]
        assert len(ls_callbacks) == 1

    def test_patch_crewai_direct_idempotency(self, monkeypatch) -> None:
        """Calling _patch_crewai() directly twice leaves Crew.__init__ identical.

        This tests the low-level guard (not going through auto_patch).
        """
        _, FakeCrew, _ = _install_fake_crewai(monkeypatch)
        ap = _ap_mod()
        ls = _make_client()
        ap._global_client = ls

        ap._patch_crewai()
        init_after_first = FakeCrew.__init__

        ap._patch_crewai()  # second call
        assert FakeCrew.__init__ is init_after_first, (
            "Crew.__init__ was replaced a second time — idempotency guard is broken."
        )


# ===========================================================================
# 6. Regression: _patch_crewai does not evict other patches from _patched_sdks
#    After _patch_crewai(), openai / anthropic / mcp patches must still be
#    present in _patched_sdks (they were added by earlier patch calls).
# ===========================================================================

class TestOtherPatchesNotBrokenByCrewAI:
    def test_openai_patch_survives_patch_crewai(self, monkeypatch) -> None:
        """Calling _patch_crewai() must not remove 'openai' from _patched_sdks."""
        _install_fake_crewai(monkeypatch)
        ap = _ap_mod()
        ls = _make_client()
        ap._global_client = ls

        # Manually mark openai as patched (simulating _patch_openai having run)
        ap._patched_sdks.add("openai")

        ap._patch_crewai()

        assert "openai" in ap._patched_sdks, (
            "_patch_crewai() must not clear or overwrite _patched_sdks contents"
        )

    def test_anthropic_patch_survives_patch_crewai(self, monkeypatch) -> None:
        """Calling _patch_crewai() must not remove 'anthropic' from _patched_sdks."""
        _install_fake_crewai(monkeypatch)
        ap = _ap_mod()
        ls = _make_client()
        ap._global_client = ls

        ap._patched_sdks.add("anthropic")
        ap._patch_crewai()

        assert "anthropic" in ap._patched_sdks

    def test_mcp_patch_survives_patch_crewai(self, monkeypatch) -> None:
        """Calling _patch_crewai() must not remove 'mcp' from _patched_sdks."""
        _install_fake_crewai(monkeypatch)
        ap = _ap_mod()
        ls = _make_client()
        ap._global_client = ls

        ap._patched_sdks.add("mcp")
        ap._patch_crewai()

        assert "mcp" in ap._patched_sdks

    def test_crewai_added_without_touching_other_sdks(self, monkeypatch) -> None:
        """After _patch_crewai(), both 'crewai' and any pre-existing SDK names
        remain in _patched_sdks."""
        _install_fake_crewai(monkeypatch)
        ap = _ap_mod()
        ls = _make_client()
        ap._global_client = ls

        # Simulate openai + anthropic + mcp already patched
        ap._patched_sdks.update({"openai", "anthropic", "mcp"})

        ap._patch_crewai()

        assert "crewai" in ap._patched_sdks
        assert ap._patched_sdks.issuperset({"openai", "anthropic", "mcp", "crewai"})

    def test_auto_patch_with_all_sdks_skipped_still_adds_crewai(
        self, monkeypatch
    ) -> None:
        """Even when openai/anthropic/mcp are absent (ImportError), crewai
        is patched and other sdk names are NOT added (no phantom entries)."""
        import builtins

        _, _, _ = _install_fake_crewai(monkeypatch)
        monkeypatch.setenv("LANGSIGHT_URL", "http://localhost:8000")

        real_import = builtins.__import__

        def _selectively_block_import(name, *args, **kwargs):
            if name in ("openai", "anthropic", "google.genai", "google.generativeai"):
                raise ImportError(f"blocked: {name}")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _selectively_block_import)

        ap = _ap_mod()
        import langsight

        langsight.auto_patch()

        assert "crewai" in ap._patched_sdks
        # Unavailable SDKs must NOT appear in _patched_sdks
        assert "openai" not in ap._patched_sdks
        assert "anthropic" not in ap._patched_sdks


# ===========================================================================
# Additional edge-case regression tests
# ===========================================================================

class TestEdgeCases:
    @pytest.mark.regression
    async def test_on_tool_end_without_prior_start_does_not_crash(self) -> None:
        """Regression: on_tool_end called with no matching on_tool_start must
        not raise — it falls back to datetime.now(UTC) for started_at."""
        client = _make_client()
        captured: list = []
        client.buffer_span = lambda s: captured.append(s)  # type: ignore[assignment]

        cb = LangSightCrewAICallback(client=client, server_name="srv")
        # No on_tool_start — should still produce a span
        await cb.on_tool_end("orphan_tool", "output")

        assert len(captured) == 1
        assert captured[0].tool_name == "orphan_tool"
        assert captured[0].status == ToolCallStatus.SUCCESS

    @pytest.mark.regression
    async def test_on_tool_error_without_prior_start_does_not_crash(self) -> None:
        """Regression: on_tool_error with no prior on_tool_start must not raise."""
        client = _make_client()
        captured: list = []
        client.buffer_span = lambda s: captured.append(s)  # type: ignore[assignment]

        cb = LangSightCrewAICallback(client=client, server_name="srv")
        await cb.on_tool_error("orphan_tool", ValueError("boom"))

        assert len(captured) == 1
        assert captured[0].status == ToolCallStatus.ERROR

    def test_set_agent_name_overrides_constructor_value(self) -> None:
        """set_agent_name() replaces whatever was passed to the constructor."""
        client = _make_client()
        cb = LangSightCrewAICallback(
            client=client, server_name="srv", agent_name="original"
        )
        cb.set_agent_name("overridden")
        assert cb._agent_name == "overridden"

    @pytest.mark.asyncio
    async def test_pending_dict_cleared_after_tool_end(self) -> None:
        """_pending entry removed after on_tool_end — no memory leak on repeated calls."""
        client = _make_client()
        captured: list = []
        client.buffer_span = lambda s: captured.append(s)  # type: ignore[assignment]

        cb = LangSightCrewAICallback(client=client, server_name="srv")

        # Simulate 3 sequential tool calls
        for i in range(3):
            name = f"tool_{i}"
            cb.on_tool_start(name, {})
            assert name in cb._pending

        # Drive them all to completion
        for i in range(3):
            await cb.on_tool_end(f"tool_{i}", f"result_{i}")

        assert len(cb._pending) == 0

    def test_callback_has_correct_server_name_from_constructor(self) -> None:
        """LangSightCrewAICallback stores the server_name passed at construction."""
        client = _make_client()
        cb = LangSightCrewAICallback(client=client, server_name="my-mcp")
        assert cb._server_name == "my-mcp"

    def test_crew_callback_client_is_global_client(self, monkeypatch) -> None:
        """The callback injected into Crew uses the _global_client set by auto_patch."""
        _, FakeCrew, _ = _install_fake_crewai(monkeypatch)
        monkeypatch.setenv("LANGSIGHT_URL", "http://localhost:8000")

        import langsight

        client = langsight.auto_patch()

        crew = FakeCrew()
        ls_cb = next(c for c in crew.callbacks if isinstance(c, LangSightCrewAICallback))
        # The callback's _client must be the same instance returned by auto_patch
        assert ls_cb._client is client

    async def test_multiple_concurrent_tool_calls_isolated(self) -> None:
        """Overlapping tool calls tracked independently in _pending by name."""
        client = _make_client()
        captured: list = []
        client.buffer_span = lambda s: captured.append(s)  # type: ignore[assignment]

        cb = LangSightCrewAICallback(client=client, server_name="srv")

        cb.on_tool_start("mcp__db__select", {})
        cb.on_tool_start("mcp__s3__list", {})

        assert "mcp__db__select" in cb._pending
        assert "mcp__s3__list" in cb._pending

        await cb.on_tool_end("mcp__db__select", [])
        assert "mcp__db__select" not in cb._pending
        assert "mcp__s3__list" in cb._pending

        await cb.on_tool_end("mcp__s3__list", [])
        assert len(cb._pending) == 0

        assert len(captured) == 2
        servers = {s.server_name for s in captured}
        assert servers == {"db", "s3"}
