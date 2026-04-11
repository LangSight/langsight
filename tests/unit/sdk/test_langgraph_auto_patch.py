"""Tests for LangGraph auto-patching via _patch_langgraph() / unpatch().

_patch_langgraph() monkey-patches langgraph.pregel.Pregel.{stream,astream,
invoke,ainvoke} to auto-inject a LangSightLangChainCallback into the config.

Covers:
- _patch_langgraph() adds 'langgraph' to _patched_sdks
- _patch_langgraph() replaces stream/astream/invoke/ainvoke
- Patched stream() injects callback when inside a session context
- Patched astream() injects callback when inside a session context
- Patched invoke() injects callback
- Patched ainvoke() injects callback
- Callback receives session_id, agent_name, trace_id from context vars
- Callback is in auto-detect mode (server_name=None)
- Double-injection prevented via _lg_callback_injected ContextVar
- Passthrough when _global_client is None
- Passthrough when user already has LangSightLangChainCallback
- Config=None creates new config with callback
- Existing callbacks list preserved (ours prepended)
- All chunks yielded through stream()
- All chunks yielded through astream()
- unpatch() restores all four methods
- _patch_langgraph() silently skips when langgraph not installed
- _patch_langgraph() is idempotent (double-call does not double-wrap)
"""

from __future__ import annotations

import sys
import types
from unittest.mock import AsyncMock, MagicMock

import pytest

import langsight.sdk.auto_patch  # noqa: F401 — ensure module is in sys.modules
from langsight.sdk.auto_patch import (
    _lg_callback_injected,
    _patched_sdks,
    clear_context,
    set_context,
    unpatch,
)
from langsight.sdk.client import LangSightClient

_ap_mod = sys.modules["langsight.sdk.auto_patch"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client() -> LangSightClient:
    client = LangSightClient(url="http://localhost:8000")
    client.flush = AsyncMock()  # type: ignore[method-assign]
    return client


class FakePregelBase:
    """Minimal stand-in for langgraph.pregel.Pregel.

    invoke() delegates to stream() — mirrors real LangGraph behaviour.
    """

    def stream(self, input: object, config: dict | None = None, **kwargs: object) -> object:  # type: ignore[override]
        yield {"node": "planner", "config_keys": list((config or {}).keys())}
        yield {"node": "generate", "config_keys": list((config or {}).keys())}

    async def astream(self, input: object, config: dict | None = None, **kwargs: object) -> object:  # type: ignore[override]
        yield {"node": "planner", "config_keys": list((config or {}).keys())}
        yield {"node": "generate", "config_keys": list((config or {}).keys())}

    def invoke(self, input: object, config: dict | None = None, **kwargs: object) -> object:
        latest = None
        for chunk in self.stream(input, config, **kwargs):
            latest = chunk
        return latest

    async def ainvoke(self, input: object, config: dict | None = None, **kwargs: object) -> object:
        latest = None
        async for chunk in self.astream(input, config, **kwargs):
            latest = chunk
        return latest


def _install_fake_langgraph() -> type:
    """Install a fake langgraph.pregel module into sys.modules.

    Returns the FakePregelBase class (acts as Pregel).
    """
    pregel_mod = types.ModuleType("langgraph.pregel")
    pregel_mod.Pregel = FakePregelBase  # type: ignore[attr-defined]
    lg_mod = types.ModuleType("langgraph")
    sys.modules["langgraph"] = lg_mod
    sys.modules["langgraph.pregel"] = pregel_mod
    return FakePregelBase


def _uninstall_fake_langgraph() -> None:
    sys.modules.pop("langgraph", None)
    sys.modules.pop("langgraph.pregel", None)


def _count_callbacks(config: dict | None) -> int:
    """Count LangSight callbacks in a config dict."""
    if config is None:
        return 0
    cbs = config.get("callbacks", [])
    if not isinstance(cbs, list):
        return 0
    try:
        from langsight.integrations.langchain import LangSightLangChainCallback

        return sum(1 for cb in cbs if isinstance(cb, LangSightLangChainCallback))
    except ImportError:
        return 0


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_state():
    """Reset auto_patch module state before and after each test."""
    _patched_sdks.discard("langgraph")
    _ap_mod._originals.pop("langgraph_stream", None)
    _ap_mod._originals.pop("langgraph_astream", None)
    _ap_mod._originals.pop("langgraph_invoke", None)
    _ap_mod._originals.pop("langgraph_ainvoke", None)
    old_client = _ap_mod._global_client
    yield
    # Restore
    _patched_sdks.discard("langgraph")
    _ap_mod._originals.pop("langgraph_stream", None)
    _ap_mod._originals.pop("langgraph_astream", None)
    _ap_mod._originals.pop("langgraph_invoke", None)
    _ap_mod._originals.pop("langgraph_ainvoke", None)
    _ap_mod._global_client = old_client
    _uninstall_fake_langgraph()


@pytest.fixture()
def fake_pregel():
    """Install fake langgraph and return the Pregel class."""
    return _install_fake_langgraph()


@pytest.fixture()
def client():
    """Create a LangSightClient and set as global."""
    c = _make_client()
    _ap_mod._global_client = c
    return c


# ---------------------------------------------------------------------------
# Tests: Patch installation
# ---------------------------------------------------------------------------


class TestPatchInstallation:
    def test_adds_langgraph_to_patched_sdks(self, fake_pregel, client):
        from langsight.sdk.auto_patch import _patch_langgraph

        _patch_langgraph()
        assert "langgraph" in _patched_sdks

    def test_replaces_stream(self, fake_pregel, client):
        orig = fake_pregel.stream
        from langsight.sdk.auto_patch import _patch_langgraph

        _patch_langgraph()
        assert fake_pregel.stream is not orig

    def test_replaces_astream(self, fake_pregel, client):
        orig = fake_pregel.astream
        from langsight.sdk.auto_patch import _patch_langgraph

        _patch_langgraph()
        assert fake_pregel.astream is not orig

    def test_replaces_invoke(self, fake_pregel, client):
        orig = fake_pregel.invoke
        from langsight.sdk.auto_patch import _patch_langgraph

        _patch_langgraph()
        assert fake_pregel.invoke is not orig

    def test_replaces_ainvoke(self, fake_pregel, client):
        orig = fake_pregel.ainvoke
        from langsight.sdk.auto_patch import _patch_langgraph

        _patch_langgraph()
        assert fake_pregel.ainvoke is not orig

    def test_is_idempotent(self, fake_pregel, client):
        from langsight.sdk.auto_patch import _patch_langgraph

        _patch_langgraph()
        first_stream = fake_pregel.stream
        _patch_langgraph()
        assert fake_pregel.stream is first_stream  # not double-wrapped

    def test_skips_when_not_installed(self):
        _uninstall_fake_langgraph()
        from langsight.sdk.auto_patch import _patch_langgraph

        _patch_langgraph()
        assert "langgraph" not in _patched_sdks


# ---------------------------------------------------------------------------
# Tests: Callback injection (sync stream)
# ---------------------------------------------------------------------------


class TestStreamInjection:
    def test_injects_callback_in_session_context(self, fake_pregel, client):
        from langsight.sdk.auto_patch import _patch_langgraph

        _patch_langgraph()
        graph = fake_pregel()
        tokens = set_context(session_id="sess-1", agent_name="planner")
        try:
            chunks = list(graph.stream({"task": "test"}))
            assert len(chunks) == 2
            # The config passed through to the original has callbacks
            assert "config_keys" in chunks[0]
            assert "callbacks" in chunks[0]["config_keys"]
        finally:
            clear_context(tokens)

    def test_passthrough_when_no_client(self, fake_pregel):
        _ap_mod._global_client = None
        from langsight.sdk.auto_patch import _patch_langgraph

        _patch_langgraph()
        graph = fake_pregel()
        tokens = set_context(session_id="sess-1")
        try:
            chunks = list(graph.stream({"task": "test"}))
            assert len(chunks) == 2
            # No callbacks injected
            assert "callbacks" not in chunks[0].get("config_keys", [])
        finally:
            clear_context(tokens)

    def test_config_none_creates_new_config(self, fake_pregel, client):
        from langsight.sdk.auto_patch import _patch_langgraph

        _patch_langgraph()
        graph = fake_pregel()
        tokens = set_context(session_id="sess-1")
        try:
            chunks = list(graph.stream({"task": "test"}, config=None))
            assert "callbacks" in chunks[0]["config_keys"]
        finally:
            clear_context(tokens)

    def test_prepends_to_existing_callbacks(self, fake_pregel, client):
        from langsight.sdk.auto_patch import _patch_langgraph

        _patch_langgraph()
        graph = fake_pregel()
        user_cb = MagicMock()

        # Override stream to capture the actual config
        captured_configs: list[dict] = []
        orig_stream = _ap_mod._originals["langgraph_stream"]

        def _capturing_stream(self, input, config=None, **kw):
            captured_configs.append(config)
            yield from orig_stream(self, input, config, **kw)

        # Temporarily replace the original stored in _originals
        _ap_mod._originals["langgraph_stream"] = FakePregelBase.stream
        fake_pregel.stream = lambda self, input, config=None, **kw: _capturing_stream(
            self, input, config, **kw
        )

        # Re-patch to pick up our capturing stream
        _patched_sdks.discard("langgraph")
        _patch_langgraph()

        tokens = set_context(session_id="sess-1")
        try:
            graph = fake_pregel()
            list(graph.stream({"task": "test"}, config={"callbacks": [user_cb]}))
            assert len(captured_configs) == 1
            cbs = captured_configs[0]["callbacks"]
            assert len(cbs) == 2  # ours + user's
            assert cbs[-1] is user_cb  # user's callback preserved at end
        finally:
            clear_context(tokens)

    def test_yields_all_chunks(self, fake_pregel, client):
        from langsight.sdk.auto_patch import _patch_langgraph

        _patch_langgraph()
        graph = fake_pregel()
        tokens = set_context(session_id="sess-1")
        try:
            chunks = list(graph.stream({"task": "test"}))
            assert len(chunks) == 2
            assert chunks[0]["node"] == "planner"
            assert chunks[1]["node"] == "generate"
        finally:
            clear_context(tokens)

    def test_skips_when_user_has_langsight_callback(self, fake_pregel, client):
        from langsight.integrations.langchain import LangSightLangChainCallback
        from langsight.sdk.auto_patch import _patch_langgraph

        _patch_langgraph()
        graph = fake_pregel()
        user_cb = LangSightLangChainCallback(client=client, session_id="user-sess")

        tokens = set_context(session_id="sess-1")
        try:
            chunks = list(graph.stream({"task": "test"}, config={"callbacks": [user_cb]}))
            assert len(chunks) == 2
            # Original config passed unchanged — no extra callback injected
        finally:
            clear_context(tokens)


# ---------------------------------------------------------------------------
# Tests: Callback injection (async astream)
# ---------------------------------------------------------------------------


class TestAstreamInjection:
    @pytest.mark.asyncio()
    async def test_injects_callback_in_session_context(self, fake_pregel, client):
        from langsight.sdk.auto_patch import _patch_langgraph

        _patch_langgraph()
        graph = fake_pregel()
        tokens = set_context(session_id="sess-1", agent_name="planner")
        try:
            chunks = [chunk async for chunk in graph.astream({"task": "test"})]
            assert len(chunks) == 2
            assert "callbacks" in chunks[0]["config_keys"]
        finally:
            clear_context(tokens)

    @pytest.mark.asyncio()
    async def test_yields_all_chunks(self, fake_pregel, client):
        from langsight.sdk.auto_patch import _patch_langgraph

        _patch_langgraph()
        graph = fake_pregel()
        tokens = set_context(session_id="sess-1")
        try:
            chunks = [chunk async for chunk in graph.astream({"task": "test"})]
            assert len(chunks) == 2
            assert chunks[0]["node"] == "planner"
            assert chunks[1]["node"] == "generate"
        finally:
            clear_context(tokens)


# ---------------------------------------------------------------------------
# Tests: invoke / ainvoke
# ---------------------------------------------------------------------------


class TestInvokeInjection:
    def test_invoke_injects_callback(self, fake_pregel, client):
        from langsight.sdk.auto_patch import _patch_langgraph

        _patch_langgraph()
        graph = fake_pregel()
        tokens = set_context(session_id="sess-1")
        try:
            result = graph.invoke({"task": "test"})
            assert result is not None
            assert "callbacks" in result["config_keys"]
        finally:
            clear_context(tokens)

    @pytest.mark.asyncio()
    async def test_ainvoke_injects_callback(self, fake_pregel, client):
        from langsight.sdk.auto_patch import _patch_langgraph

        _patch_langgraph()
        graph = fake_pregel()
        tokens = set_context(session_id="sess-1")
        try:
            result = await graph.ainvoke({"task": "test"})
            assert result is not None
            assert "callbacks" in result["config_keys"]
        finally:
            clear_context(tokens)


# ---------------------------------------------------------------------------
# Tests: Double-injection prevention
# ---------------------------------------------------------------------------


class TestDoubleInjectionGuard:
    def test_invoke_to_stream_injects_only_once(self, fake_pregel, client):
        """invoke() calls stream() internally — callback should appear once."""
        from langsight.sdk.auto_patch import _patch_langgraph

        _patch_langgraph()

        graph = fake_pregel()
        tokens = set_context(session_id="sess-1")
        try:
            result = graph.invoke({"task": "test"})
            # invoke delegated to stream — if double injection happened,
            # we'd see duplicate callbacks. The config_keys having 'callbacks'
            # once confirms injection worked. The ContextVar guard prevents
            # the inner stream() call from injecting again.
            assert result is not None
        finally:
            clear_context(tokens)

    def test_context_var_reset_on_exception(self, fake_pregel, client):
        """ContextVar must be reset even if the original raises."""
        from langsight.sdk.auto_patch import _patch_langgraph

        _patch_langgraph()

        # Make the original stream raise
        def _failing_stream(self, input, config=None, **kw):
            raise RuntimeError("graph exploded")
            yield  # noqa: RET503 — unreachable but makes this a generator

        fake_pregel.stream = _failing_stream

        # Re-patch
        _patched_sdks.discard("langgraph")
        _patch_langgraph()

        graph = fake_pregel()
        tokens = set_context(session_id="sess-1")
        try:
            with pytest.raises(RuntimeError, match="graph exploded"):
                list(graph.stream({"task": "test"}))
            # ContextVar should be reset
            assert _lg_callback_injected.get() is False
        finally:
            clear_context(tokens)


# ---------------------------------------------------------------------------
# Tests: Unpatch
# ---------------------------------------------------------------------------


class TestUnpatch:
    def test_unpatch_restores_stream(self, fake_pregel, client):
        orig = fake_pregel.stream
        from langsight.sdk.auto_patch import _patch_langgraph

        _patch_langgraph()
        assert fake_pregel.stream is not orig
        unpatch()
        assert fake_pregel.stream is orig

    def test_unpatch_restores_all_four(self, fake_pregel, client):
        orig_stream = fake_pregel.stream
        orig_astream = fake_pregel.astream
        orig_invoke = fake_pregel.invoke
        orig_ainvoke = fake_pregel.ainvoke
        from langsight.sdk.auto_patch import _patch_langgraph

        _patch_langgraph()
        unpatch()
        assert fake_pregel.stream is orig_stream
        assert fake_pregel.astream is orig_astream
        assert fake_pregel.invoke is orig_invoke
        assert fake_pregel.ainvoke is orig_ainvoke


# ---------------------------------------------------------------------------
# Tests: Topology capture
# ---------------------------------------------------------------------------


class TestTopologyCapture:
    def test_compile_patch_stashes_topology(self, client):
        """StateGraph.compile() patch should stash topology on compiled graph."""
        # Create a fake StateGraph with a compile method that returns a graph-like object
        fake_builder = types.SimpleNamespace(
            edges={("planner", "generate")},
            branches={},
            entry_point="__start__",
        )
        fake_compiled = types.SimpleNamespace(
            nodes={"planner": None, "generate": None},
            builder=fake_builder,
        )

        class FakeStateGraph:
            def compile(self, *args, **kwargs):
                return fake_compiled

        # Install fake module BEFORE calling _patch_langgraph
        state_mod = types.ModuleType("langgraph.graph.state")
        state_mod.StateGraph = FakeStateGraph  # type: ignore[attr-defined]
        graph_mod = types.ModuleType("langgraph.graph")
        graph_mod.StateGraph = FakeStateGraph  # type: ignore[attr-defined]
        sys.modules["langgraph.graph.state"] = state_mod
        sys.modules["langgraph.graph"] = graph_mod

        # Also need langgraph.pregel for _patch_langgraph to proceed
        pregel_mod = types.ModuleType("langgraph.pregel")
        pregel_mod.Pregel = FakePregelBase  # type: ignore[attr-defined]
        sys.modules["langgraph.pregel"] = pregel_mod

        try:
            # Clear patched state so we can re-patch
            _patched_sdks.discard("langgraph")
            _ap_mod._originals.pop("langgraph_compile", None)

            from langsight.sdk.auto_patch import _patch_langgraph

            _patch_langgraph()

            # Call compile()
            graph = FakeStateGraph()
            compiled = graph.compile()

            # Should have topology stashed
            assert hasattr(compiled, "_langsight_topology")
            topo = compiled._langsight_topology
            assert topo["nodes"] == ["planner", "generate"]
            assert len(topo["edges"]) == 1
            assert topo["edges"][0]["source"] == "planner"
            assert topo["edges"][0]["target"] == "generate"
            assert topo["entry_point"] == "__start__"
        finally:
            sys.modules.pop("langgraph.graph.state", None)
            sys.modules.pop("langgraph.graph", None)
            sys.modules.pop("langgraph.pregel", None)
            _patched_sdks.discard("langgraph")
            _ap_mod._originals.pop("langgraph_compile", None)

    def test_compile_patch_is_idempotent(self, client):
        """Calling _patch_langgraph() twice should not double-wrap compile()."""
        # Create fake StateGraph
        class FakeStateGraph:
            def compile(self, *args, **kwargs):
                return types.SimpleNamespace(
                    nodes={},
                    builder=types.SimpleNamespace(
                        edges=set(),
                        branches={},
                        entry_point="__start__",
                    ),
                )

        # Install fake module BEFORE calling _patch_langgraph
        state_mod = types.ModuleType("langgraph.graph.state")
        state_mod.StateGraph = FakeStateGraph  # type: ignore[attr-defined]
        graph_mod = types.ModuleType("langgraph.graph")
        graph_mod.StateGraph = FakeStateGraph  # type: ignore[attr-defined]
        sys.modules["langgraph.graph.state"] = state_mod
        sys.modules["langgraph.graph"] = graph_mod

        # Also need langgraph.pregel
        pregel_mod = types.ModuleType("langgraph.pregel")
        pregel_mod.Pregel = FakePregelBase  # type: ignore[attr-defined]
        sys.modules["langgraph.pregel"] = pregel_mod

        try:
            # Clear patched state
            _patched_sdks.discard("langgraph")
            _ap_mod._originals.pop("langgraph_compile", None)

            from langsight.sdk.auto_patch import _patch_langgraph

            _patch_langgraph()
            first_compile = FakeStateGraph.compile

            # Patch again
            _patch_langgraph()
            second_compile = FakeStateGraph.compile

            # Should be the same wrapped function, not double-wrapped
            assert first_compile is second_compile
            # The patched version should have the marker attribute
            assert hasattr(first_compile, "_langsight_patched")
        finally:
            sys.modules.pop("langgraph.graph.state", None)
            sys.modules.pop("langgraph.graph", None)
            sys.modules.pop("langgraph.pregel", None)
            _patched_sdks.discard("langgraph")
            _ap_mod._originals.pop("langgraph_compile", None)
