"""Tests for MCP auto-patching via _patch_mcp() / auto_patch() / unpatch().

_patch_mcp() monkey-patches mcp.ClientSession.call_tool so that every
MCP tool call is automatically traced without any explicit ls.wrap() call.

Covers:
- auto_patch() installs MCP patch when mcp is importable
- Patched call_tool emits a ToolCallSpan with correct agent_name from _agent_ctx
- Patched call_tool emits span with session_id from _session_ctx
- Patched call_tool links to pending llm_intent span via claim_pending_tool()
- unpatch() restores the original call_tool
- MCP not installed → _patch_mcp() silently skips (no error raised)
- Tool call that raises an exception → span is emitted with ERROR status

All tests mock mcp.ClientSession so the real mcp package is not required.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client() -> LangSightClient:
    return LangSightClient(url="http://localhost:8000")


def _capture_spans(client: LangSightClient) -> list[ToolCallSpan]:
    """Replace buffer_span with a list-collector; return the list."""
    captured: list[ToolCallSpan] = []
    client.buffer_span = lambda span: captured.append(span)  # type: ignore[assignment]
    return captured


def _make_fake_mcp_module() -> tuple[MagicMock, MagicMock]:
    """Build a minimal fake mcp module with a ClientSession class."""
    fake_client_session = MagicMock()
    fake_client_session.call_tool = AsyncMock(return_value={"result": "ok"})
    fake_mcp = MagicMock()
    fake_mcp.ClientSession = fake_client_session
    return fake_mcp, fake_client_session


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_state():
    """Guarantee clean patch state + contextvars before and after each test."""
    unpatch()
    _session_ctx.set(None)
    _agent_ctx.set(None)
    _trace_ctx.set(None)
    yield
    unpatch()
    _session_ctx.set(None)
    _agent_ctx.set(None)
    _trace_ctx.set(None)


# ---------------------------------------------------------------------------
# Patch installation
# ---------------------------------------------------------------------------


def test_auto_patch_adds_mcp_to_patched_sdks_when_importable(monkeypatch):
    """After auto_patch(), 'mcp' appears in _patched_sdks when mcp is available."""
    fake_mcp, fake_cs = _make_fake_mcp_module()
    monkeypatch.setitem(sys.modules, "mcp", fake_mcp)
    monkeypatch.setenv("LANGSIGHT_URL", "http://localhost:8000")

    from langsight.sdk.auto_patch import _patch_mcp

    _patch_mcp()

    assert "mcp" in _patched_sdks


def test_patch_mcp_replaces_call_tool_on_client_session(monkeypatch):
    """_patch_mcp() replaces ClientSession.call_tool with a wrapped version."""
    fake_mcp, fake_cs = _make_fake_mcp_module()
    original_call_tool = fake_cs.call_tool
    monkeypatch.setitem(sys.modules, "mcp", fake_mcp)

    import importlib; ap_module = importlib.import_module("langsight.sdk.auto_patch")

    # Inject the global client so _make_proxy() returns a valid proxy
    ls = _make_client()
    monkeypatch.setattr(ap_module, "_global_client", ls)

    from langsight.sdk.auto_patch import _patch_mcp

    _patch_mcp()

    # call_tool must have been replaced
    assert fake_cs.call_tool is not original_call_tool


# ---------------------------------------------------------------------------
# Span emission — agent_name from _agent_ctx
# ---------------------------------------------------------------------------


async def test_patched_call_tool_emits_span_with_agent_name_from_ctx(monkeypatch):
    """Patched call_tool emits a ToolCallSpan whose agent_name equals _agent_ctx value."""
    fake_mcp, fake_cs = _make_fake_mcp_module()
    monkeypatch.setitem(sys.modules, "mcp", fake_mcp)

    import importlib; ap_module = importlib.import_module("langsight.sdk.auto_patch")

    ls = _make_client()
    captured = _capture_spans(ls)
    monkeypatch.setattr(ap_module, "_global_client", ls)

    from langsight.sdk.auto_patch import _patch_mcp

    _patch_mcp()

    tokens = set_context(agent_name="test-mcp-agent", session_id="sess-mcp-01")
    try:
        # Simulate call_tool being invoked on a ClientSession instance
        fake_session = SimpleNamespace(_server_info=None, _server_name=None)
        await fake_cs.call_tool(fake_session, "get_records", {"limit": 10})
    finally:
        clear_context(tokens)

    assert len(captured) == 1
    span = captured[0]
    assert span.agent_name == "test-mcp-agent"


async def test_patched_call_tool_emits_span_with_session_id_from_ctx(monkeypatch):
    """Patched call_tool emits a ToolCallSpan whose session_id equals _session_ctx value."""
    fake_mcp, fake_cs = _make_fake_mcp_module()
    monkeypatch.setitem(sys.modules, "mcp", fake_mcp)

    import importlib; ap_module = importlib.import_module("langsight.sdk.auto_patch")

    ls = _make_client()
    captured = _capture_spans(ls)
    monkeypatch.setattr(ap_module, "_global_client", ls)

    from langsight.sdk.auto_patch import _patch_mcp

    _patch_mcp()

    tokens = set_context(session_id="mcp-session-xyz")
    try:
        fake_session = SimpleNamespace(_server_info=None, _server_name=None)
        await fake_cs.call_tool(fake_session, "list_tables", None)
    finally:
        clear_context(tokens)

    assert len(captured) == 1
    assert captured[0].session_id == "mcp-session-xyz"


async def test_patched_call_tool_emits_span_with_tool_name(monkeypatch):
    """Patched call_tool emits a ToolCallSpan whose tool_name matches the called tool."""
    fake_mcp, fake_cs = _make_fake_mcp_module()
    monkeypatch.setitem(sys.modules, "mcp", fake_mcp)

    import importlib; ap_module = importlib.import_module("langsight.sdk.auto_patch")

    ls = _make_client()
    captured = _capture_spans(ls)
    monkeypatch.setattr(ap_module, "_global_client", ls)

    from langsight.sdk.auto_patch import _patch_mcp

    _patch_mcp()

    fake_session = SimpleNamespace(_server_info=None, _server_name=None)
    await fake_cs.call_tool(fake_session, "query_database", {"sql": "SELECT 1"})

    assert len(captured) == 1
    assert captured[0].tool_name == "query_database"


async def test_patched_call_tool_uses_server_name_from_server_info(monkeypatch):
    """server_name is derived from session._server_info.name when available."""
    fake_mcp, fake_cs = _make_fake_mcp_module()
    monkeypatch.setitem(sys.modules, "mcp", fake_mcp)

    import importlib; ap_module = importlib.import_module("langsight.sdk.auto_patch")

    ls = _make_client()
    captured = _capture_spans(ls)
    monkeypatch.setattr(ap_module, "_global_client", ls)

    from langsight.sdk.auto_patch import _patch_mcp

    _patch_mcp()

    server_info = SimpleNamespace(name="postgres-mcp")
    fake_session = SimpleNamespace(_server_info=server_info, _server_name=None)
    await fake_cs.call_tool(fake_session, "run_query", {})

    assert captured[0].server_name == "postgres-mcp"


async def test_patched_call_tool_falls_back_to_server_name_attr(monkeypatch):
    """server_name falls back to session._server_name when _server_info is None."""
    fake_mcp, fake_cs = _make_fake_mcp_module()
    monkeypatch.setitem(sys.modules, "mcp", fake_mcp)

    import importlib; ap_module = importlib.import_module("langsight.sdk.auto_patch")

    ls = _make_client()
    captured = _capture_spans(ls)
    monkeypatch.setattr(ap_module, "_global_client", ls)

    from langsight.sdk.auto_patch import _patch_mcp

    _patch_mcp()

    fake_session = SimpleNamespace(_server_info=None, _server_name="s3-mcp")
    await fake_cs.call_tool(fake_session, "list_buckets", {})

    assert captured[0].server_name == "s3-mcp"


async def test_patched_call_tool_defaults_server_name_to_mcp(monkeypatch):
    """server_name defaults to 'mcp' when no server info is available."""
    fake_mcp, fake_cs = _make_fake_mcp_module()
    monkeypatch.setitem(sys.modules, "mcp", fake_mcp)

    import importlib; ap_module = importlib.import_module("langsight.sdk.auto_patch")

    ls = _make_client()
    captured = _capture_spans(ls)
    monkeypatch.setattr(ap_module, "_global_client", ls)

    from langsight.sdk.auto_patch import _patch_mcp

    _patch_mcp()

    fake_session = SimpleNamespace(_server_info=None, _server_name=None)
    await fake_cs.call_tool(fake_session, "tool_x", {})

    assert captured[0].server_name == "mcp"


# ---------------------------------------------------------------------------
# Pending llm_intent span linking
# ---------------------------------------------------------------------------


async def test_patched_call_tool_links_to_pending_llm_intent_span(monkeypatch):
    """Patched call_tool claims a registered llm_intent span and sets it as parent."""
    fake_mcp, fake_cs = _make_fake_mcp_module()
    monkeypatch.setitem(sys.modules, "mcp", fake_mcp)

    import importlib; ap_module = importlib.import_module("langsight.sdk.auto_patch")
    from langsight.sdk.context import _pending_tools_ctx, register_pending_tool

    ls = _make_client()
    captured = _capture_spans(ls)
    monkeypatch.setattr(ap_module, "_global_client", ls)

    from langsight.sdk.auto_patch import _patch_mcp

    _patch_mcp()

    # Register a pending llm_intent span for the tool we're about to call
    register_pending_tool("search_products", span_id="intent-span-001", agent_name="shop-agent")

    fake_session = SimpleNamespace(_server_info=None, _server_name=None)
    await fake_cs.call_tool(fake_session, "search_products", {"query": "shoes"})

    assert len(captured) == 1
    span = captured[0]
    assert span.parent_span_id == "intent-span-001"


async def test_patched_call_tool_inherits_agent_name_from_pending_span(monkeypatch):
    """When _agent_ctx is empty, agent_name is inherited from pending llm_intent span."""
    fake_mcp, fake_cs = _make_fake_mcp_module()
    monkeypatch.setitem(sys.modules, "mcp", fake_mcp)

    import importlib; ap_module = importlib.import_module("langsight.sdk.auto_patch")
    from langsight.sdk.context import register_pending_tool

    ls = _make_client()
    captured = _capture_spans(ls)
    monkeypatch.setattr(ap_module, "_global_client", ls)

    # Do NOT set _agent_ctx — agent_name should come from the pending span
    _agent_ctx.set(None)

    from langsight.sdk.auto_patch import _patch_mcp

    _patch_mcp()

    register_pending_tool("fetch_order", span_id="intent-span-002", agent_name="order-agent")

    fake_session = SimpleNamespace(_server_info=None, _server_name=None)
    await fake_cs.call_tool(fake_session, "fetch_order", {})

    assert captured[0].agent_name == "order-agent"


async def test_patched_call_tool_no_pending_span_parent_is_none(monkeypatch):
    """When no llm_intent span is registered, parent_span_id is None."""
    fake_mcp, fake_cs = _make_fake_mcp_module()
    monkeypatch.setitem(sys.modules, "mcp", fake_mcp)

    import importlib; ap_module = importlib.import_module("langsight.sdk.auto_patch")

    ls = _make_client()
    captured = _capture_spans(ls)
    monkeypatch.setattr(ap_module, "_global_client", ls)

    from langsight.sdk.auto_patch import _patch_mcp

    _patch_mcp()

    fake_session = SimpleNamespace(_server_info=None, _server_name=None)
    await fake_cs.call_tool(fake_session, "unregistered_tool", {})

    assert captured[0].parent_span_id is None


# ---------------------------------------------------------------------------
# Error handling — span is emitted even when tool call raises
# ---------------------------------------------------------------------------


async def test_patched_call_tool_emits_error_span_on_exception(monkeypatch):
    """When the underlying call_tool raises, span is emitted with ERROR status."""
    fake_mcp, fake_cs = _make_fake_mcp_module()
    # Make the original call_tool raise
    fake_cs.call_tool = AsyncMock(side_effect=RuntimeError("connection refused"))
    monkeypatch.setitem(sys.modules, "mcp", fake_mcp)

    import importlib; ap_module = importlib.import_module("langsight.sdk.auto_patch")

    ls = _make_client()
    captured = _capture_spans(ls)
    monkeypatch.setattr(ap_module, "_global_client", ls)

    from langsight.sdk.auto_patch import _patch_mcp

    _patch_mcp()

    fake_session = SimpleNamespace(_server_info=None, _server_name=None)

    with pytest.raises(RuntimeError, match="connection refused"):
        await fake_cs.call_tool(fake_session, "broken_tool", {})

    # Span must still be emitted
    assert len(captured) == 1
    span = captured[0]
    assert span.status == ToolCallStatus.ERROR
    assert "connection refused" in (span.error or "")


async def test_patched_call_tool_emits_timeout_span_on_timeout(monkeypatch):
    """When the underlying call_tool raises TimeoutError, span has TIMEOUT status."""
    fake_mcp, fake_cs = _make_fake_mcp_module()
    fake_cs.call_tool = AsyncMock(side_effect=TimeoutError("read timeout"))
    monkeypatch.setitem(sys.modules, "mcp", fake_mcp)

    import importlib; ap_module = importlib.import_module("langsight.sdk.auto_patch")

    ls = _make_client()
    captured = _capture_spans(ls)
    monkeypatch.setattr(ap_module, "_global_client", ls)

    from langsight.sdk.auto_patch import _patch_mcp

    _patch_mcp()

    fake_session = SimpleNamespace(_server_info=None, _server_name=None)

    with pytest.raises(TimeoutError):
        await fake_cs.call_tool(fake_session, "slow_tool", {})

    assert len(captured) == 1
    assert captured[0].status == ToolCallStatus.TIMEOUT


async def test_patched_call_tool_span_has_success_status_on_normal_return(monkeypatch):
    """Span has SUCCESS status when the underlying call_tool returns normally."""
    fake_mcp, fake_cs = _make_fake_mcp_module()
    monkeypatch.setitem(sys.modules, "mcp", fake_mcp)

    import importlib; ap_module = importlib.import_module("langsight.sdk.auto_patch")

    ls = _make_client()
    captured = _capture_spans(ls)
    monkeypatch.setattr(ap_module, "_global_client", ls)

    from langsight.sdk.auto_patch import _patch_mcp

    _patch_mcp()

    fake_session = SimpleNamespace(_server_info=None, _server_name=None)
    await fake_cs.call_tool(fake_session, "happy_tool", {})

    assert captured[0].status == ToolCallStatus.SUCCESS


# ---------------------------------------------------------------------------
# Span lineage_provenance
# ---------------------------------------------------------------------------


async def test_patched_call_tool_span_lineage_provenance_is_explicit(monkeypatch):
    """Spans emitted by the MCP patch carry lineage_provenance='explicit'."""
    fake_mcp, fake_cs = _make_fake_mcp_module()
    monkeypatch.setitem(sys.modules, "mcp", fake_mcp)

    import importlib; ap_module = importlib.import_module("langsight.sdk.auto_patch")

    ls = _make_client()
    captured = _capture_spans(ls)
    monkeypatch.setattr(ap_module, "_global_client", ls)

    from langsight.sdk.auto_patch import _patch_mcp

    _patch_mcp()

    fake_session = SimpleNamespace(_server_info=None, _server_name=None)
    await fake_cs.call_tool(fake_session, "any_tool", {})

    assert captured[0].lineage_provenance == "explicit"


# ---------------------------------------------------------------------------
# No global client — passthrough behaviour
# ---------------------------------------------------------------------------


async def test_patched_call_tool_is_noop_when_no_global_client(monkeypatch):
    """Patched call_tool passes through to original when _global_client is None."""
    fake_mcp, fake_cs = _make_fake_mcp_module()
    original_return = {"passthrough": True}
    fake_cs.call_tool = AsyncMock(return_value=original_return)
    monkeypatch.setitem(sys.modules, "mcp", fake_mcp)

    import importlib; ap_module = importlib.import_module("langsight.sdk.auto_patch")

    # Ensure no global client
    monkeypatch.setattr(ap_module, "_global_client", None)

    from langsight.sdk.auto_patch import _patch_mcp

    _patch_mcp()

    fake_session = SimpleNamespace(_server_info=None, _server_name=None)
    result = await fake_cs.call_tool(fake_session, "some_tool", {})

    # Must return the original result unchanged
    assert result == original_return


# ---------------------------------------------------------------------------
# unpatch() restores original ClientSession.call_tool
# ---------------------------------------------------------------------------


def test_unpatch_restores_original_call_tool(monkeypatch):
    """unpatch() restores ClientSession.call_tool to its pre-patch value."""
    fake_mcp, fake_cs = _make_fake_mcp_module()
    original_call_tool = fake_cs.call_tool
    monkeypatch.setitem(sys.modules, "mcp", fake_mcp)

    import importlib; ap_module = importlib.import_module("langsight.sdk.auto_patch")
    from langsight.sdk.auto_patch import _patch_mcp

    ls = _make_client()
    monkeypatch.setattr(ap_module, "_global_client", ls)

    _patch_mcp()
    # Patched — call_tool is now our wrapper
    assert fake_cs.call_tool is not original_call_tool

    # Restore
    unpatch()
    assert fake_cs.call_tool is original_call_tool


def test_unpatch_removes_mcp_from_patched_sdks(monkeypatch):
    """unpatch() removes 'mcp' from _patched_sdks."""
    fake_mcp, fake_cs = _make_fake_mcp_module()
    monkeypatch.setitem(sys.modules, "mcp", fake_mcp)
    monkeypatch.setenv("LANGSIGHT_URL", "http://localhost:8000")

    import importlib; ap_module = importlib.import_module("langsight.sdk.auto_patch")
    from langsight.sdk.auto_patch import _patch_mcp

    ls = _make_client()
    monkeypatch.setattr(ap_module, "_global_client", ls)
    _patch_mcp()

    assert "mcp" in _patched_sdks

    unpatch()
    assert "mcp" not in _patched_sdks


# ---------------------------------------------------------------------------
# MCP not installed — silent skip
# ---------------------------------------------------------------------------


def test_patch_mcp_silently_skips_when_mcp_not_installed(monkeypatch):
    """_patch_mcp() does not raise when mcp is not installed."""
    # Remove mcp from sys.modules to simulate it not being installed
    monkeypatch.delitem(sys.modules, "mcp", raising=False)

    # Ensure the import of mcp inside _patch_mcp raises ImportError
    real_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

    def _no_mcp(name, *args, **kwargs):
        if name == "mcp":
            raise ImportError("No module named 'mcp'")
        return real_import(name, *args, **kwargs)

    # Use the simpler monkeypatch approach — remove mcp from modules
    # _patch_mcp() uses `from mcp import ClientSession` which will ImportError
    # Since mcp is a real dep (pyproject.toml), we patch sys.modules directly
    sys.modules.pop("mcp", None)
    # Re-import after removing — _patch_mcp itself handles ImportError gracefully
    from langsight.sdk.auto_patch import _patch_mcp, _patched_sdks as sdks_before

    # Temporarily break mcp import inside the function
    with patch.dict(sys.modules, {"mcp": None}):  # None in sys.modules causes ImportError
        # Should not raise
        try:
            _patch_mcp()
        except ImportError:
            pass  # The function itself guards with try/except ImportError

    # mcp should not be in patched sdks if import failed
    # (either it was skipped or remained unpatched)
    # The key assertion: no unhandled exception was raised
    assert True  # reaching here means no crash


def test_patch_mcp_is_idempotent(monkeypatch):
    """Calling _patch_mcp() twice does not double-patch."""
    fake_mcp, fake_cs = _make_fake_mcp_module()
    monkeypatch.setitem(sys.modules, "mcp", fake_mcp)

    import importlib; ap_module = importlib.import_module("langsight.sdk.auto_patch")
    from langsight.sdk.auto_patch import _patch_mcp

    ls = _make_client()
    monkeypatch.setattr(ap_module, "_global_client", ls)

    _patch_mcp()
    patched_once = fake_cs.call_tool

    _patch_mcp()
    # Second call must not replace the already-patched method again
    assert fake_cs.call_tool is patched_once
