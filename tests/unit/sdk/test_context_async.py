"""Tests for contextvars-based pending tool context (async safety).

The context module was migrated from threading.local() to contextvars.ContextVar.
These tests verify:
- Async tasks inherit parent context (child can see parent registrations)
- Concurrent async tasks do not interfere with each other
- Register + claim still works in FIFO order
- Claim returns None when empty
- Claimed entries are consumed (no double-claim)
"""

from __future__ import annotations

import asyncio

import pytest

from langsight.sdk.context import (
    _get_pending,
    _pending_tools_ctx,
    claim_pending_tool,
    register_pending_tool,
)


@pytest.fixture(autouse=True)
def _clear_pending() -> None:
    """Reset the ContextVar to None before each test.

    This ensures each test starts fresh. Since contextvars are scoped to
    the current task context, we need to explicitly reset.
    """
    _pending_tools_ctx.set(None)


# =============================================================================
# Basic register/claim contract (async context)
# =============================================================================


class TestRegisterAndClaim:
    def test_register_and_claim_returns_pending_context(self) -> None:
        register_pending_tool("search", "span-1", agent_name="agent-a")
        ctx = claim_pending_tool("search")
        assert ctx is not None
        assert ctx.span_id == "span-1"
        assert ctx.agent_name == "agent-a"

    def test_claim_returns_none_when_empty(self) -> None:
        assert claim_pending_tool("nonexistent") is None

    def test_fifo_order_preserved(self) -> None:
        register_pending_tool("tool", "first")
        register_pending_tool("tool", "second")
        register_pending_tool("tool", "third")
        assert claim_pending_tool("tool").span_id == "first"  # type: ignore[union-attr]
        assert claim_pending_tool("tool").span_id == "second"  # type: ignore[union-attr]
        assert claim_pending_tool("tool").span_id == "third"  # type: ignore[union-attr]
        assert claim_pending_tool("tool") is None

    def test_claim_consumes_entry(self) -> None:
        register_pending_tool("search", "span-1")
        claim_pending_tool("search")
        # Second claim should return None — entry was consumed
        assert claim_pending_tool("search") is None

    def test_different_tool_names_are_independent(self) -> None:
        register_pending_tool("tool_a", "span-a")
        register_pending_tool("tool_b", "span-b")
        ctx_b = claim_pending_tool("tool_b")
        assert ctx_b is not None
        assert ctx_b.span_id == "span-b"
        ctx_a = claim_pending_tool("tool_a")
        assert ctx_a is not None
        assert ctx_a.span_id == "span-a"


# =============================================================================
# Async: parent context inherited by child tasks
# =============================================================================


class TestAsyncContextInheritance:
    @pytest.mark.asyncio
    async def test_child_task_inherits_parent_registrations(self) -> None:
        """A child asyncio.Task should see pending tools from the parent context."""
        register_pending_tool("search", "parent-span-1")

        result = []

        async def child() -> None:
            ctx = claim_pending_tool("search")
            result.append(ctx)

        await asyncio.create_task(child())

        assert len(result) == 1
        assert result[0] is not None
        assert result[0].span_id == "parent-span-1"

    @pytest.mark.asyncio
    async def test_parent_sees_unclaimed_after_child_does_not_claim(self) -> None:
        """If child task does not claim the entry, parent still can.

        Note: contextvars ContextVar with mutable default creates a shared
        reference when child inherits. This test documents the actual behavior.
        """
        register_pending_tool("search", "shared-span")

        async def child_that_does_not_claim() -> None:
            # Child does nothing with pending tools
            pass

        await asyncio.create_task(child_that_does_not_claim())

        # Parent should still be able to claim since child didn't consume it
        ctx = claim_pending_tool("search")
        assert ctx is not None
        assert ctx.span_id == "shared-span"


# =============================================================================
# Async: concurrent tasks do not interfere
# =============================================================================


class TestAsyncConcurrentTaskIsolation:
    @pytest.mark.asyncio
    async def test_concurrent_tasks_with_separate_context_do_not_interfere(self) -> None:
        """Two concurrent tasks with their own ContextVar copies stay independent.

        This tests that when a task creates a fresh ContextVar (by copying
        context before the parent registers anything), its pending queue is
        isolated from the other.
        """
        results_a: list[object] = []
        results_b: list[object] = []

        async def task_a() -> None:
            # task_a creates its own pending state via _get_pending()
            register_pending_tool("search", "task-a-span")
            # Give task_b time to register its own
            await asyncio.sleep(0.01)
            ctx = claim_pending_tool("search")
            results_a.append(ctx)

        async def task_b() -> None:
            register_pending_tool("search", "task-b-span")
            await asyncio.sleep(0.01)
            ctx = claim_pending_tool("search")
            results_b.append(ctx)

        # Create tasks with fresh context copies
        ctx_a = asyncio.current_task()  # noqa: F841

        # Run in separate context copies to get isolation
        import contextvars

        ctx_copy_a = contextvars.copy_context()
        ctx_copy_b = contextvars.copy_context()

        # Reset in each copy so they start fresh
        ctx_copy_a.run(_pending_tools_ctx.set, None)
        ctx_copy_b.run(_pending_tools_ctx.set, None)

        loop = asyncio.get_event_loop()
        fut_a = loop.run_in_executor(None, lambda: ctx_copy_a.run(asyncio.run, task_a()))
        fut_b = loop.run_in_executor(None, lambda: ctx_copy_b.run(asyncio.run, task_b()))
        await asyncio.gather(fut_a, fut_b)

        # Each task should have claimed its own span, not the other's
        assert len(results_a) == 1
        assert results_a[0] is not None
        assert results_a[0].span_id == "task-a-span"

        assert len(results_b) == 1
        assert results_b[0] is not None
        assert results_b[0].span_id == "task-b-span"

    @pytest.mark.asyncio
    async def test_sequential_async_tasks_share_parent_mutable_state(self) -> None:
        """Sequential tasks created from same parent share the mutable dict.

        This is the expected behavior with ContextVar holding a mutable
        defaultdict — child tasks get a reference to the same dict object.
        This test documents this behavior (not a bug, it's how wrap_llm +
        wrap interop works in the same agent loop).
        """
        register_pending_tool("search", "original-span")

        claimed_in_child = []

        async def child_claims() -> None:
            ctx = claim_pending_tool("search")
            claimed_in_child.append(ctx)

        await asyncio.create_task(child_claims())

        # Child consumed the entry from the shared mutable dict
        assert len(claimed_in_child) == 1
        assert claimed_in_child[0] is not None
        # Parent's queue is now empty because child consumed from shared dict
        assert claim_pending_tool("search") is None


# =============================================================================
# Edge cases
# =============================================================================


class TestContextEdgeCases:
    def test_get_pending_initializes_on_first_call(self) -> None:
        """_get_pending() creates a fresh defaultdict on first access."""
        pending = _get_pending()
        assert isinstance(pending, dict)

    def test_get_pending_returns_same_instance(self) -> None:
        """Repeated calls in the same context return the same dict."""
        p1 = _get_pending()
        p2 = _get_pending()
        assert p1 is p2

    def test_register_without_agent_name(self) -> None:
        register_pending_tool("tool", "span-1")
        ctx = claim_pending_tool("tool")
        assert ctx is not None
        assert ctx.agent_name is None

    def test_empty_tool_name(self) -> None:
        """Empty string as tool name should still work (edge case)."""
        register_pending_tool("", "span-empty")
        ctx = claim_pending_tool("")
        assert ctx is not None
        assert ctx.span_id == "span-empty"
