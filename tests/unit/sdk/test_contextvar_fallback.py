"""Tests for contextvar fallback in wrap() and wrap_llm().

Verifies that LangSightClient.wrap() and LangSightClient.wrap_llm() read
_agent_ctx, _session_ctx, and _trace_ctx as fallbacks when no explicit
arguments are provided, and that explicit arguments always take priority.

Covers:
- wrap() inside session(agent_name=...) receives agent_name from contextvar
- wrap() inside session(session_id=...) receives session_id from contextvar
- wrap() explicit params override contextvar values
- wrap_llm() reads agent_name from contextvar
- wrap_llm() reads session_id from contextvar
- wrap_llm() explicit params override contextvar values
- wrap() outside any session generates a new session_id (old behaviour)
- wrap() inside session with trace_id propagates trace_id
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from langsight.sdk.auto_patch import (
    _agent_ctx,
    _session_ctx,
    _trace_ctx,
    clear_context,
    session,
    set_context,
    unpatch,
)
from langsight.sdk.client import LangSightClient, MCPClientProxy

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_ctx():
    """Reset all contextvars and patch state around every test."""
    unpatch()
    _session_ctx.set(None)
    _agent_ctx.set(None)
    _trace_ctx.set(None)
    yield
    unpatch()
    _session_ctx.set(None)
    _agent_ctx.set(None)
    _trace_ctx.set(None)


@pytest.fixture
def client() -> LangSightClient:
    return LangSightClient(url="http://localhost:8000")


@pytest.fixture
def fake_mcp():
    """Minimal duck-typed MCP client stub."""

    class _FakeMCP:
        async def call_tool(self, name, arguments=None):
            return {"ok": True}

    return _FakeMCP()


# ---------------------------------------------------------------------------
# wrap() — agent_name from contextvar
# ---------------------------------------------------------------------------


async def test_wrap_reads_agent_name_from_session_ctx(client, fake_mcp):
    """wrap() with no agent_name inside session() picks up agent_name from _agent_ctx."""
    async with session(agent_name="analyst"):
        proxy = client.wrap(fake_mcp, server_name="test-mcp")

    assert isinstance(proxy, MCPClientProxy)
    # Access via object.__getattribute__ to bypass __getattr__ forwarding
    assert object.__getattribute__(proxy, "_agent_name") == "analyst"


async def test_wrap_reads_session_id_from_session_ctx(client, fake_mcp):
    """wrap() with no session_id inside session() picks up session_id from _session_ctx."""
    async with session(session_id="test-sid-001") as sid:
        proxy = client.wrap(fake_mcp, server_name="test-mcp")

    assert object.__getattribute__(proxy, "_session_id") == "test-sid-001"
    assert sid == "test-sid-001"


async def test_wrap_reads_trace_id_from_session_ctx(client, fake_mcp):
    """wrap() with no trace_id inside session() picks up trace_id from _trace_ctx."""
    async with session(trace_id="trace-xyz"):
        proxy = client.wrap(fake_mcp, server_name="test-mcp")

    assert object.__getattribute__(proxy, "_trace_id") == "trace-xyz"


async def test_wrap_all_three_contextvars_propagated(client, fake_mcp):
    """wrap() inside session() propagates agent_name, session_id, and trace_id together."""
    async with session(agent_name="orchestrator", session_id="sess-full", trace_id="tr-001"):
        proxy = client.wrap(fake_mcp, server_name="test-mcp")

    assert object.__getattribute__(proxy, "_agent_name") == "orchestrator"
    assert object.__getattribute__(proxy, "_session_id") == "sess-full"
    assert object.__getattribute__(proxy, "_trace_id") == "tr-001"


# ---------------------------------------------------------------------------
# wrap() — explicit params take priority over contextvar
# ---------------------------------------------------------------------------


async def test_wrap_explicit_agent_name_overrides_contextvar(client, fake_mcp):
    """Explicit agent_name passed to wrap() beats _agent_ctx value."""
    async with session(agent_name="ctx-agent"):
        proxy = client.wrap(fake_mcp, server_name="test-mcp", agent_name="explicit-agent")

    assert object.__getattribute__(proxy, "_agent_name") == "explicit-agent"


async def test_wrap_explicit_session_id_overrides_contextvar(client, fake_mcp):
    """Explicit session_id passed to wrap() beats _session_ctx value."""
    async with session(session_id="ctx-session"):
        proxy = client.wrap(fake_mcp, server_name="test-mcp", session_id="explicit-session")

    assert object.__getattribute__(proxy, "_session_id") == "explicit-session"


async def test_wrap_explicit_trace_id_overrides_contextvar(client, fake_mcp):
    """Explicit trace_id passed to wrap() beats _trace_ctx value."""
    async with session(trace_id="ctx-trace"):
        proxy = client.wrap(fake_mcp, server_name="test-mcp", trace_id="explicit-trace")

    assert object.__getattribute__(proxy, "_trace_id") == "explicit-trace"


# ---------------------------------------------------------------------------
# wrap() — outside session context (old behaviour preserved)
# ---------------------------------------------------------------------------


def test_wrap_outside_session_generates_new_session_id(client, fake_mcp):
    """wrap() with no args and no active session generates a new non-empty session_id."""
    proxy = client.wrap(fake_mcp, server_name="test-mcp")

    sid = object.__getattribute__(proxy, "_session_id")
    assert sid is not None
    assert len(sid) > 0  # UUID hex — non-empty


def test_wrap_outside_session_agent_name_is_none(client, fake_mcp):
    """wrap() with no args and no active session has agent_name=None."""
    proxy = client.wrap(fake_mcp, server_name="test-mcp")

    assert object.__getattribute__(proxy, "_agent_name") is None


def test_wrap_outside_session_trace_id_is_none(client, fake_mcp):
    """wrap() with no args and no active session has trace_id=None."""
    proxy = client.wrap(fake_mcp, server_name="test-mcp")

    assert object.__getattribute__(proxy, "_trace_id") is None


def test_wrap_two_calls_outside_session_get_same_ctxvar_session(client, fake_mcp):
    """Two wrap() calls with no session share a session only when contextvar is set."""
    # Without any contextvar, each wrap() generates its own session_id.
    proxy_a = client.wrap(fake_mcp, server_name="mcp-a")
    proxy_b = client.wrap(fake_mcp, server_name="mcp-b")

    sid_a = object.__getattribute__(proxy_a, "_session_id")
    sid_b = object.__getattribute__(proxy_b, "_session_id")
    # Both are non-empty, but they are independently generated
    assert sid_a is not None
    assert sid_b is not None


# ---------------------------------------------------------------------------
# wrap_llm() — agent_name from contextvar
# ---------------------------------------------------------------------------


def test_wrap_llm_reads_agent_name_from_agent_ctx(client):
    """wrap_llm() with no agent_name reads from _agent_ctx."""
    tokens = set_context(agent_name="llm-analyst")
    try:
        class _FakeOpenAI:
            pass

        _FakeOpenAI.__name__ = "OpenAI"
        _FakeOpenAI.__module__ = "openai"

        fake = _FakeOpenAI()
        wrapped = client.wrap_llm(fake)
        # OpenAIProxy stores agent_name via __setattr__ → object.__getattribute__
        assert object.__getattribute__(wrapped, "_agent_name") == "llm-analyst"
    finally:
        clear_context(tokens)


def test_wrap_llm_reads_session_id_from_session_ctx(client):
    """wrap_llm() with no session_id reads from _session_ctx."""
    tokens = set_context(session_id="llm-sess-42")
    try:
        class _FakeOpenAI:
            pass

        _FakeOpenAI.__name__ = "OpenAI"
        _FakeOpenAI.__module__ = "openai"

        fake = _FakeOpenAI()
        wrapped = client.wrap_llm(fake)
        assert object.__getattribute__(wrapped, "_session_id") == "llm-sess-42"
    finally:
        clear_context(tokens)


def test_wrap_llm_reads_trace_id_from_trace_ctx(client):
    """wrap_llm() with no trace_id reads from _trace_ctx."""
    tokens = set_context(trace_id="llm-trace-99")
    try:
        class _FakeOpenAI:
            pass

        _FakeOpenAI.__name__ = "OpenAI"
        _FakeOpenAI.__module__ = "openai"

        fake = _FakeOpenAI()
        wrapped = client.wrap_llm(fake)
        assert object.__getattribute__(wrapped, "_trace_id") == "llm-trace-99"
    finally:
        clear_context(tokens)


# ---------------------------------------------------------------------------
# wrap_llm() — explicit params override contextvar
# ---------------------------------------------------------------------------


def test_wrap_llm_explicit_agent_name_overrides_contextvar(client):
    """Explicit agent_name to wrap_llm() beats _agent_ctx value."""
    tokens = set_context(agent_name="ctx-llm-agent")
    try:
        class _FakeOpenAI:
            pass

        _FakeOpenAI.__name__ = "OpenAI"
        _FakeOpenAI.__module__ = "openai"

        fake = _FakeOpenAI()
        wrapped = client.wrap_llm(fake, agent_name="explicit-llm-agent")
        assert object.__getattribute__(wrapped, "_agent_name") == "explicit-llm-agent"
    finally:
        clear_context(tokens)


def test_wrap_llm_explicit_session_id_overrides_contextvar(client):
    """Explicit session_id to wrap_llm() beats _session_ctx value."""
    tokens = set_context(session_id="ctx-llm-sess")
    try:
        class _FakeOpenAI:
            pass

        _FakeOpenAI.__name__ = "OpenAI"
        _FakeOpenAI.__module__ = "openai"

        fake = _FakeOpenAI()
        wrapped = client.wrap_llm(fake, session_id="explicit-llm-sess")
        assert object.__getattribute__(wrapped, "_session_id") == "explicit-llm-sess"
    finally:
        clear_context(tokens)


# ---------------------------------------------------------------------------
# wrap_llm() — unknown SDK (fail-open) still propagates contextvars
# ---------------------------------------------------------------------------


def test_wrap_llm_unknown_sdk_returns_original_client(client):
    """wrap_llm() with unrecognised SDK returns the original object unchanged (fail-open)."""
    _session_ctx.set(None)
    _agent_ctx.set(None)

    class _UnknownLLM:
        pass

    _UnknownLLM.__name__ = "SomeLLM"
    _UnknownLLM.__module__ = "some.unknown.sdk"

    fake = _UnknownLLM()
    result = client.wrap_llm(fake)
    # Should be the original object, not a proxy
    assert result is fake


# ---------------------------------------------------------------------------
# Isolation between async tasks
# ---------------------------------------------------------------------------


async def test_contextvar_isolated_between_concurrent_wraps(client, fake_mcp):
    """Two concurrent async tasks get independent contextvar values via session()."""
    import asyncio

    results: dict[str, str | None] = {}

    async def task_a():
        async with session(agent_name="agent-a", session_id="sess-a"):
            proxy = client.wrap(fake_mcp, server_name="mcp")
            results["a_agent"] = object.__getattribute__(proxy, "_agent_name")
            results["a_session"] = object.__getattribute__(proxy, "_session_id")
            await asyncio.sleep(0)  # yield to let task_b run

    async def task_b():
        async with session(agent_name="agent-b", session_id="sess-b"):
            proxy = client.wrap(fake_mcp, server_name="mcp")
            results["b_agent"] = object.__getattribute__(proxy, "_agent_name")
            results["b_session"] = object.__getattribute__(proxy, "_session_id")
            await asyncio.sleep(0)

    await asyncio.gather(task_a(), task_b())

    assert results["a_agent"] == "agent-a"
    assert results["a_session"] == "sess-a"
    assert results["b_agent"] == "agent-b"
    assert results["b_session"] == "sess-b"


# ---------------------------------------------------------------------------
# Shared proxy — call_tool() uses active contextvar, not stored value
# Regression: before fix, a bridge created in orchestrator context would
# attribute ALL sub-agent tool calls to "orchestrator" even when called
# from inside analyst's session() block.
# ---------------------------------------------------------------------------


async def test_proxy_call_tool_uses_active_agent_ctx_over_stored(client, fake_mcp):
    """MCPClientProxy.call_tool() emits span with active session's agent_name,
    not the agent_name locked in at proxy creation time.

    Simulates: orchestrator creates bridge → analyst uses it inside own session().
    """
    # Create proxy inside orchestrator context (locked in as "orchestrator")
    async with session(agent_name="orchestrator", session_id="sess-orch"):
        proxy = client.wrap(fake_mcp, server_name="catalog-mcp")

    assert object.__getattribute__(proxy, "_agent_name") == "orchestrator"

    # Now call it from inside analyst's session — span must use "analyst"
    with patch.object(client, "_post_spans", new_callable=AsyncMock) as mock_post:
        async with session(agent_name="analyst", session_id="sess-orch"):
            await proxy.call_tool("get_product", {"id": 1})
        await client.flush()

    mock_post.assert_called_once()
    emitted = mock_post.call_args[0][0]
    assert len(emitted) == 1
    assert emitted[0].agent_name == "analyst", (
        f"Expected agent_name='analyst', got '{emitted[0].agent_name}'. "
        "Shared proxy must adopt the active session's agent_name at call time."
    )
    assert emitted[0].session_id == "sess-orch"


async def test_proxy_call_tool_falls_back_to_stored_agent_when_no_active_ctx(client, fake_mcp):
    """When no session() is active, call_tool() falls back to the stored agent_name."""
    async with session(agent_name="orchestrator", session_id="sess-x"):
        proxy = client.wrap(fake_mcp, server_name="catalog-mcp")

    # Call outside any session context — stored values should be used
    with patch.object(client, "_post_spans", new_callable=AsyncMock) as mock_post:
        await proxy.call_tool("list_products", {})
        await client.flush()

    mock_post.assert_called_once()
    emitted = mock_post.call_args[0][0]
    assert len(emitted) == 1
    assert emitted[0].agent_name == "orchestrator"
