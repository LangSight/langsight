"""Tests for MCP auto-patching via _patch_mcp() / unpatch().

_patch_mcp() monkey-patches mcp.ClientSession.call_tool so that every
MCP tool call is automatically traced without any explicit ls.wrap() call.

Covers:
- _patch_mcp() adds 'mcp' to _patched_sdks when mcp is importable
- _patch_mcp() replaces ClientSession.call_tool with a wrapped version
- Patched call_tool emits ToolCallSpan with agent_name from _agent_ctx
- Patched call_tool emits span with session_id from _session_ctx
- Patched call_tool uses server_name from session._server_info.name
- Patched call_tool falls back to session._server_name attribute
- Patched call_tool defaults server_name to 'mcp' when nothing available
- Patched call_tool sets parent_span_id from registered llm_intent span
- Patched call_tool inherits agent_name from pending span when ctx is empty
- No pending span -> parent_span_id is None
- Normal return -> span has SUCCESS status
- Exception -> span has ERROR status and re-raises
- TimeoutError -> span has TIMEOUT status and re-raises
- Span lineage_provenance is 'explicit'
- _global_client is None -> passthrough, no span emitted
- unpatch() restores original ClientSession.call_tool
- unpatch() removes 'mcp' from _patched_sdks
- _patch_mcp() silently skips when mcp is not installed
- _patch_mcp() is idempotent (double-call does not double-wrap)
"""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import langsight.sdk.auto_patch  # noqa: F401 — side-effect: registers module in sys.modules
from langsight.sdk.auto_patch import (
    _agent_ctx,
    _patched_sdks,
    _session_ctx,
    _trace_ctx,
    clear_context,
    set_context,
    unpatch,
)
from langsight.sdk.client import LangSightClient
from langsight.sdk.models import ToolCallSpan, ToolCallStatus

# Retrieve the real module object — `import langsight.sdk.auto_patch as name`
# resolves to the auto_patch() *function* re-exported from langsight.sdk.__init__,
# not the module.  sys.modules gives us the actual module with _global_client etc.
_ap_mod = sys.modules["langsight.sdk.auto_patch"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client() -> LangSightClient:
    return LangSightClient(url="http://localhost:8000")


def _capture(client: LangSightClient) -> list[ToolCallSpan]:
    captured: list[ToolCallSpan] = []
    client.buffer_span = lambda span: captured.append(span)  # type: ignore[assignment]
    return captured


def _fake_mcp() -> tuple[MagicMock, MagicMock]:
    """Return (fake_mcp_module, fake_ClientSession_class)."""
    cs = MagicMock()
    cs.call_tool = AsyncMock(return_value={"ok": True})
    mod = MagicMock()
    mod.ClientSession = cs
    return mod, cs


def _fake_session(
    server_name: str | None = None,
    server_info_name: str | None = None,
) -> SimpleNamespace:
    info = SimpleNamespace(name=server_info_name) if server_info_name else None
    return SimpleNamespace(_server_info=info, _server_name=server_name)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    unpatch()
    _session_ctx.set(None)
    _agent_ctx.set(None)
    _trace_ctx.set(None)
    monkeypatch.setattr(_ap_mod, "_global_client", None)
    yield
    unpatch()
    _session_ctx.set(None)
    _agent_ctx.set(None)
    _trace_ctx.set(None)


# ---------------------------------------------------------------------------
# Patch installation
# ---------------------------------------------------------------------------


def test_patch_mcp_adds_sdk_to_patched_set(monkeypatch):
    """_patch_mcp() records 'mcp' in _patched_sdks on success."""
    mod, _cs = _fake_mcp()
    monkeypatch.setitem(sys.modules, "mcp", mod)
    ls = _make_client()
    monkeypatch.setattr(_ap_mod, "_global_client", ls)

    _ap_mod._patch_mcp()

    assert "mcp" in _patched_sdks


def test_patch_mcp_replaces_call_tool(monkeypatch):
    """_patch_mcp() swaps ClientSession.call_tool for a tracing wrapper."""
    mod, cs = _fake_mcp()
    original = cs.call_tool
    monkeypatch.setitem(sys.modules, "mcp", mod)
    ls = _make_client()
    monkeypatch.setattr(_ap_mod, "_global_client", ls)

    _ap_mod._patch_mcp()

    assert cs.call_tool is not original


# ---------------------------------------------------------------------------
# Span emission — context variables
# ---------------------------------------------------------------------------


async def test_span_carries_agent_name_from_agent_ctx(monkeypatch):
    """agent_name on emitted span comes from _agent_ctx."""
    mod, cs = _fake_mcp()
    monkeypatch.setitem(sys.modules, "mcp", mod)
    ls = _make_client()
    spans = _capture(ls)
    monkeypatch.setattr(_ap_mod, "_global_client", ls)
    _ap_mod._patch_mcp()

    tokens = set_context(agent_name="mcp-agent", session_id="s-001")
    try:
        await cs.call_tool(_fake_session(), "get_data", {})
    finally:
        clear_context(tokens)

    assert len(spans) == 1
    assert spans[0].agent_name == "mcp-agent"


async def test_span_carries_session_id_from_session_ctx(monkeypatch):
    """session_id on emitted span comes from _session_ctx."""
    mod, cs = _fake_mcp()
    monkeypatch.setitem(sys.modules, "mcp", mod)
    ls = _make_client()
    spans = _capture(ls)
    monkeypatch.setattr(_ap_mod, "_global_client", ls)
    _ap_mod._patch_mcp()

    tokens = set_context(session_id="my-session")
    try:
        await cs.call_tool(_fake_session(), "list_rows", None)
    finally:
        clear_context(tokens)

    assert spans[0].session_id == "my-session"


async def test_span_tool_name_matches_called_tool(monkeypatch):
    """tool_name on emitted span equals the name argument passed to call_tool."""
    mod, cs = _fake_mcp()
    monkeypatch.setitem(sys.modules, "mcp", mod)
    ls = _make_client()
    spans = _capture(ls)
    monkeypatch.setattr(_ap_mod, "_global_client", ls)
    _ap_mod._patch_mcp()

    await cs.call_tool(_fake_session(), "run_query", {"sql": "SELECT 1"})

    assert spans[0].tool_name == "run_query"


# ---------------------------------------------------------------------------
# server_name derivation
# ---------------------------------------------------------------------------


async def test_server_name_from_server_info(monkeypatch):
    """server_name is read from session._server_info.name when available."""
    mod, cs = _fake_mcp()
    monkeypatch.setitem(sys.modules, "mcp", mod)
    ls = _make_client()
    spans = _capture(ls)
    monkeypatch.setattr(_ap_mod, "_global_client", ls)
    _ap_mod._patch_mcp()

    await cs.call_tool(_fake_session(server_info_name="postgres-mcp"), "q", {})

    assert spans[0].server_name == "postgres-mcp"


async def test_server_name_fallback_to_server_name_attr(monkeypatch):
    """server_name falls back to session._server_name when _server_info is absent."""
    mod, cs = _fake_mcp()
    monkeypatch.setitem(sys.modules, "mcp", mod)
    ls = _make_client()
    spans = _capture(ls)
    monkeypatch.setattr(_ap_mod, "_global_client", ls)
    _ap_mod._patch_mcp()

    await cs.call_tool(_fake_session(server_name="s3-mcp"), "list_buckets", {})

    assert spans[0].server_name == "s3-mcp"


async def test_server_name_defaults_to_mcp(monkeypatch):
    """server_name defaults to 'mcp' when neither _server_info nor _server_name is set."""
    mod, cs = _fake_mcp()
    monkeypatch.setitem(sys.modules, "mcp", mod)
    ls = _make_client()
    spans = _capture(ls)
    monkeypatch.setattr(_ap_mod, "_global_client", ls)
    _ap_mod._patch_mcp()

    await cs.call_tool(_fake_session(), "tool_x", {})

    assert spans[0].server_name == "mcp"


# ---------------------------------------------------------------------------
# Pending llm_intent span linking
# ---------------------------------------------------------------------------


async def test_parent_span_id_linked_to_registered_intent(monkeypatch):
    """parent_span_id is set to the registered llm_intent span_id for the tool."""
    from langsight.sdk.context import register_pending_tool

    mod, cs = _fake_mcp()
    monkeypatch.setitem(sys.modules, "mcp", mod)
    ls = _make_client()
    spans = _capture(ls)
    monkeypatch.setattr(_ap_mod, "_global_client", ls)
    _ap_mod._patch_mcp()

    register_pending_tool("search_products", span_id="intent-001", agent_name="shop-agent")
    await cs.call_tool(_fake_session(), "search_products", {"q": "shoes"})

    assert spans[0].parent_span_id == "intent-001"


async def test_agent_name_from_pending_span_when_ctx_empty(monkeypatch):
    """agent_name comes from pending llm_intent span when _agent_ctx is None."""
    from langsight.sdk.context import register_pending_tool

    mod, cs = _fake_mcp()
    monkeypatch.setitem(sys.modules, "mcp", mod)
    ls = _make_client()
    spans = _capture(ls)
    monkeypatch.setattr(_ap_mod, "_global_client", ls)
    _agent_ctx.set(None)
    _ap_mod._patch_mcp()

    register_pending_tool("fetch_order", span_id="intent-002", agent_name="order-agent")
    await cs.call_tool(_fake_session(), "fetch_order", {})

    assert spans[0].agent_name == "order-agent"


async def test_parent_span_id_none_when_no_pending_span(monkeypatch):
    """parent_span_id is None when no llm_intent span was registered for the tool."""
    mod, cs = _fake_mcp()
    monkeypatch.setitem(sys.modules, "mcp", mod)
    ls = _make_client()
    spans = _capture(ls)
    monkeypatch.setattr(_ap_mod, "_global_client", ls)
    _ap_mod._patch_mcp()

    await cs.call_tool(_fake_session(), "unregistered_tool", {})

    assert spans[0].parent_span_id is None


# ---------------------------------------------------------------------------
# Status on success, exception, and timeout
# ---------------------------------------------------------------------------


async def test_status_success_on_normal_return(monkeypatch):
    """Span has SUCCESS status when call_tool returns without raising."""
    mod, cs = _fake_mcp()
    monkeypatch.setitem(sys.modules, "mcp", mod)
    ls = _make_client()
    spans = _capture(ls)
    monkeypatch.setattr(_ap_mod, "_global_client", ls)
    _ap_mod._patch_mcp()

    await cs.call_tool(_fake_session(), "happy_tool", {})

    assert spans[0].status == ToolCallStatus.SUCCESS


async def test_status_error_on_exception_and_reraises(monkeypatch):
    """Exception causes ERROR span; exception propagates to caller."""
    mod, cs = _fake_mcp()
    cs.call_tool = AsyncMock(side_effect=RuntimeError("db error"))
    monkeypatch.setitem(sys.modules, "mcp", mod)
    ls = _make_client()
    spans = _capture(ls)
    monkeypatch.setattr(_ap_mod, "_global_client", ls)
    _ap_mod._patch_mcp()

    with pytest.raises(RuntimeError, match="db error"):
        await cs.call_tool(_fake_session(), "broken_tool", {})

    assert len(spans) == 1
    assert spans[0].status == ToolCallStatus.ERROR
    assert "db error" in (spans[0].error or "")


async def test_status_timeout_on_timeout_error_and_reraises(monkeypatch):
    """TimeoutError causes TIMEOUT span; exception propagates to caller."""
    mod, cs = _fake_mcp()
    cs.call_tool = AsyncMock(side_effect=TimeoutError("read timed out"))
    monkeypatch.setitem(sys.modules, "mcp", mod)
    ls = _make_client()
    spans = _capture(ls)
    monkeypatch.setattr(_ap_mod, "_global_client", ls)
    _ap_mod._patch_mcp()

    with pytest.raises(TimeoutError):
        await cs.call_tool(_fake_session(), "slow_tool", {})

    assert len(spans) == 1
    assert spans[0].status == ToolCallStatus.TIMEOUT


# ---------------------------------------------------------------------------
# Span lineage_provenance
# ---------------------------------------------------------------------------


async def test_lineage_provenance_is_explicit(monkeypatch):
    """All MCP-auto-patched spans carry lineage_provenance='explicit'."""
    mod, cs = _fake_mcp()
    monkeypatch.setitem(sys.modules, "mcp", mod)
    ls = _make_client()
    spans = _capture(ls)
    monkeypatch.setattr(_ap_mod, "_global_client", ls)
    _ap_mod._patch_mcp()

    await cs.call_tool(_fake_session(), "any_tool", {})

    assert spans[0].lineage_provenance == "explicit"


# ---------------------------------------------------------------------------
# No global client — passthrough
# ---------------------------------------------------------------------------


async def test_passthrough_when_global_client_is_none(monkeypatch):
    """When _global_client is None the original call_tool runs; no span emitted."""
    mod, cs = _fake_mcp()
    expected = {"result": "untouched"}
    cs.call_tool = AsyncMock(return_value=expected)
    monkeypatch.setitem(sys.modules, "mcp", mod)
    # _global_client stays None (autouse fixture guarantees this)
    assert _ap_mod._global_client is None

    _ap_mod._patch_mcp()

    result = await cs.call_tool(_fake_session(), "noop", {})
    assert result == expected


# ---------------------------------------------------------------------------
# unpatch()
# ---------------------------------------------------------------------------


def test_unpatch_restores_original_call_tool(monkeypatch):
    """unpatch() puts the original call_tool back on ClientSession."""
    mod, cs = _fake_mcp()
    original = cs.call_tool
    monkeypatch.setitem(sys.modules, "mcp", mod)
    ls = _make_client()
    monkeypatch.setattr(_ap_mod, "_global_client", ls)

    _ap_mod._patch_mcp()
    assert cs.call_tool is not original

    unpatch()
    assert cs.call_tool is original


def test_unpatch_removes_mcp_from_patched_sdks(monkeypatch):
    """unpatch() removes 'mcp' from _patched_sdks."""
    mod, cs = _fake_mcp()
    monkeypatch.setitem(sys.modules, "mcp", mod)
    ls = _make_client()
    monkeypatch.setattr(_ap_mod, "_global_client", ls)

    _ap_mod._patch_mcp()
    assert "mcp" in _patched_sdks

    unpatch()
    assert "mcp" not in _patched_sdks


# ---------------------------------------------------------------------------
# MCP not installed
# ---------------------------------------------------------------------------


def test_patch_mcp_silently_skips_when_mcp_absent(monkeypatch):
    """_patch_mcp() does not raise when mcp is not installed."""
    # Setting sys.modules["mcp"] = None causes ImportError on `from mcp import ...`
    monkeypatch.setitem(sys.modules, "mcp", None)

    _ap_mod._patch_mcp()  # must not raise

    assert "mcp" not in _patched_sdks


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_patch_mcp_is_idempotent(monkeypatch):
    """Calling _patch_mcp() twice does not double-wrap call_tool."""
    mod, cs = _fake_mcp()
    monkeypatch.setitem(sys.modules, "mcp", mod)
    ls = _make_client()
    monkeypatch.setattr(_ap_mod, "_global_client", ls)

    _ap_mod._patch_mcp()
    wrapper_first = cs.call_tool

    _ap_mod._patch_mcp()
    assert cs.call_tool is wrapper_first
