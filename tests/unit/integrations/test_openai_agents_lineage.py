"""Tests for lineage hardening in the OpenAI Agents SDK integration.

Covers:
- on_agent_start emits agent span and tracks in _active_agent_spans
- on_handoff sets parent_span_id from active agent span
- on_handoff stores handoff span_id in _active_handoffs for child
- on_tool_end uses runtime agent name (not constructor default)
- on_tool_end sets parent_span_id from handoff context
- on_agent_end cleans up tracking dicts
- Full flow: on_agent_start -> on_handoff -> on_tool_start -> on_tool_end
- Handoff span has target_agent_name set
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from langsight.integrations.openai_agents import LangSightOpenAIHooks
from langsight.sdk.client import LangSightClient
from langsight.sdk.models import ToolCallSpan


@pytest.fixture
def client() -> LangSightClient:
    return LangSightClient(url="http://localhost:8000")


@pytest.fixture
def hooks(client: LangSightClient) -> LangSightOpenAIHooks:
    return LangSightOpenAIHooks(
        client=client,
        server_name="test-openai",
        agent_name="default-agent",
        session_id="sess-001",
        trace_id="trace-001",
    )


def _make_agent(name: str = "my-agent") -> SimpleNamespace:
    return SimpleNamespace(name=name)


def _make_tool(name: str = "search_tool") -> SimpleNamespace:
    return SimpleNamespace(name=name)


# =============================================================================
# on_agent_start — agent span tracking
# =============================================================================


class TestOnAgentStartLineage:
    async def test_emits_agent_span(
        self, hooks: LangSightOpenAIHooks, client: LangSightClient
    ) -> None:
        agent = _make_agent("support-agent")

        with patch.object(client, "buffer_span") as mock_send:
            await hooks.on_agent_start(context=None, agent=agent)

        mock_send.assert_called_once()
        span = mock_send.call_args[0][0]
        assert span.span_type == "agent"
        assert span.agent_name == "support-agent"
        assert span.tool_name == "agent_run"
        assert span.trace_id == "trace-001"
        assert span.session_id == "sess-001"

    async def test_tracks_agent_in_active_agent_spans(
        self, hooks: LangSightOpenAIHooks, client: LangSightClient
    ) -> None:
        agent = _make_agent("support")

        with patch.object(client, "buffer_span"):
            await hooks.on_agent_start(context=None, agent=agent)

        assert id(agent) in hooks._active_agent_spans
        # The stored value should be the span_id of the emitted span
        assert isinstance(hooks._active_agent_spans[id(agent)], str)

    async def test_agent_without_handoff_has_no_parent(
        self, hooks: LangSightOpenAIHooks, client: LangSightClient
    ) -> None:
        agent = _make_agent("root-agent")

        with patch.object(client, "buffer_span") as mock_send:
            await hooks.on_agent_start(context=None, agent=agent)

        span = mock_send.call_args[0][0]
        assert span.parent_span_id is None

    async def test_agent_with_handoff_links_to_handoff_span(
        self, hooks: LangSightOpenAIHooks, client: LangSightClient
    ) -> None:
        """When a child agent starts after a handoff, its agent span should
        have parent_span_id set to the handoff span's span_id."""
        child_agent = _make_agent("billing-agent")
        # Simulate that a handoff was stored for this agent object
        hooks._active_handoffs[id(child_agent)] = "handoff-span-123"

        with patch.object(client, "buffer_span") as mock_send:
            await hooks.on_agent_start(context=None, agent=child_agent)

        span = mock_send.call_args[0][0]
        assert span.parent_span_id == "handoff-span-123"

    async def test_fail_open_on_exception(
        self, hooks: LangSightOpenAIHooks, client: LangSightClient
    ) -> None:
        with patch.object(client, "buffer_span", side_effect=RuntimeError("boom")):
            await hooks.on_agent_start(context=None, agent=_make_agent())
        # No exception raised


# =============================================================================
# on_agent_end — cleanup
# =============================================================================


class TestOnAgentEndLineage:
    async def test_cleans_up_active_agent_spans(
        self, hooks: LangSightOpenAIHooks, client: LangSightClient
    ) -> None:
        agent = _make_agent("agent-a")

        with patch.object(client, "buffer_span"):
            await hooks.on_agent_start(context=None, agent=agent)

        assert id(agent) in hooks._active_agent_spans

        await hooks.on_agent_end(context=None, agent=agent, output="done")

        assert id(agent) not in hooks._active_agent_spans

    async def test_cleans_up_active_handoffs(
        self, hooks: LangSightOpenAIHooks, client: LangSightClient
    ) -> None:
        agent = _make_agent("child-agent")
        hooks._active_handoffs[id(agent)] = "handoff-span-1"

        await hooks.on_agent_end(context=None, agent=agent, output="done")

        assert id(agent) not in hooks._active_handoffs

    async def test_agent_end_for_unknown_agent_is_noop(
        self, hooks: LangSightOpenAIHooks
    ) -> None:
        """on_agent_end for an agent not in tracking should not raise."""
        unknown = _make_agent("never-started")
        await hooks.on_agent_end(context=None, agent=unknown)
        # No exception

    async def test_fail_open(self, hooks: LangSightOpenAIHooks) -> None:
        # Corrupt the tracking dict to trigger an error
        hooks._active_agent_spans = None  # type: ignore[assignment]
        await hooks.on_agent_end(context=None, agent=_make_agent())
        # No exception raised


# =============================================================================
# on_handoff — lineage linking
# =============================================================================


class TestOnHandoffLineage:
    async def test_handoff_links_to_parent_agent_span(
        self, hooks: LangSightOpenAIHooks, client: LangSightClient
    ) -> None:
        """Handoff span's parent_span_id should be the from_agent's active span."""
        from_agent = _make_agent("orchestrator")
        to_agent = _make_agent("billing-agent")

        # Start the from_agent to create its active span
        with patch.object(client, "buffer_span") as mock_send:
            await hooks.on_agent_start(context=None, agent=from_agent)

        from_agent_span_id = hooks._active_agent_spans[id(from_agent)]

        with patch.object(client, "buffer_span") as mock_send:
            await hooks.on_handoff(
                context=None, from_agent=from_agent, to_agent=to_agent
            )

        handoff_span = mock_send.call_args[0][0]
        assert handoff_span.parent_span_id == from_agent_span_id

    async def test_handoff_stores_span_id_for_child(
        self, hooks: LangSightOpenAIHooks, client: LangSightClient
    ) -> None:
        """After handoff, the to_agent's id should map to the handoff span_id."""
        from_agent = _make_agent("a")
        to_agent = _make_agent("b")

        with patch.object(client, "buffer_span") as mock_send:
            await hooks.on_handoff(
                context=None, from_agent=from_agent, to_agent=to_agent
            )

        handoff_span = mock_send.call_args[0][0]
        assert id(to_agent) in hooks._active_handoffs
        assert hooks._active_handoffs[id(to_agent)] == handoff_span.span_id

    async def test_handoff_span_has_target_agent_name(
        self, hooks: LangSightOpenAIHooks, client: LangSightClient
    ) -> None:
        from_agent = _make_agent("orchestrator")
        to_agent = _make_agent("billing-agent")

        with patch.object(client, "buffer_span") as mock_send:
            await hooks.on_handoff(
                context=None, from_agent=from_agent, to_agent=to_agent
            )

        span = mock_send.call_args[0][0]
        assert span.target_agent_name == "billing-agent"

    async def test_handoff_span_type(
        self, hooks: LangSightOpenAIHooks, client: LangSightClient
    ) -> None:
        with patch.object(client, "buffer_span") as mock_send:
            await hooks.on_handoff(
                context=None,
                from_agent=_make_agent("a"),
                to_agent=_make_agent("b"),
            )

        span = mock_send.call_args[0][0]
        assert span.span_type == "handoff"

    async def test_handoff_without_active_agent_has_no_parent(
        self, hooks: LangSightOpenAIHooks, client: LangSightClient
    ) -> None:
        """If from_agent was never started, handoff span has no parent."""
        from_agent = _make_agent("ghost")
        to_agent = _make_agent("target")

        with patch.object(client, "buffer_span") as mock_send:
            await hooks.on_handoff(
                context=None, from_agent=from_agent, to_agent=to_agent
            )

        span = mock_send.call_args[0][0]
        assert span.parent_span_id is None


# =============================================================================
# on_tool_end / on_tool_error — lineage propagation
# =============================================================================


class TestOnToolEndLineage:
    async def test_uses_runtime_agent_name_not_constructor(
        self, hooks: LangSightOpenAIHooks, client: LangSightClient
    ) -> None:
        """on_tool_end should use agent.name, not the hooks' constructor agent_name."""
        agent = _make_agent("runtime-agent-name")
        tool = _make_tool("search")
        await hooks.on_tool_start(context=None, agent=agent, tool=tool)

        with patch.object(client, "buffer_span") as mock_send:
            await hooks.on_tool_end(context=None, agent=agent, tool=tool, result="ok")

        span = mock_send.call_args[0][0]
        assert span.agent_name == "runtime-agent-name"

    async def test_sets_parent_span_id_from_handoff_context(
        self, hooks: LangSightOpenAIHooks, client: LangSightClient
    ) -> None:
        """Tool calls from a delegated agent should link to the handoff span."""
        agent = _make_agent("billing-agent")
        tool = _make_tool("fetch_invoice")

        # Simulate handoff context
        hooks._active_handoffs[id(agent)] = "handoff-span-xyz"

        await hooks.on_tool_start(context=None, agent=agent, tool=tool)

        with patch.object(client, "buffer_span") as mock_send:
            await hooks.on_tool_end(context=None, agent=agent, tool=tool, result="ok")

        span = mock_send.call_args[0][0]
        assert span.parent_span_id == "handoff-span-xyz"

    async def test_no_handoff_context_leaves_parent_none(
        self, hooks: LangSightOpenAIHooks, client: LangSightClient
    ) -> None:
        """Without handoff context, tool span has no parent_span_id."""
        agent = _make_agent("root-agent")
        tool = _make_tool("search")
        await hooks.on_tool_start(context=None, agent=agent, tool=tool)

        with patch.object(client, "buffer_span") as mock_send:
            await hooks.on_tool_end(context=None, agent=agent, tool=tool, result="ok")

        span = mock_send.call_args[0][0]
        assert span.parent_span_id is None


class TestOnToolErrorLineage:
    async def test_error_uses_runtime_agent_name(
        self, hooks: LangSightOpenAIHooks, client: LangSightClient
    ) -> None:
        agent = _make_agent("error-agent")
        tool = _make_tool("bad_tool")
        await hooks.on_tool_start(context=None, agent=agent, tool=tool)

        with patch.object(client, "buffer_span") as mock_send:
            await hooks.on_tool_error(
                context=None, agent=agent, tool=tool, error="boom"
            )

        span = mock_send.call_args[0][0]
        assert span.agent_name == "error-agent"

    async def test_error_sets_parent_from_handoff(
        self, hooks: LangSightOpenAIHooks, client: LangSightClient
    ) -> None:
        agent = _make_agent("child")
        tool = _make_tool("fail_tool")
        hooks._active_handoffs[id(agent)] = "handoff-err-span"

        await hooks.on_tool_start(context=None, agent=agent, tool=tool)

        with patch.object(client, "buffer_span") as mock_send:
            await hooks.on_tool_error(
                context=None, agent=agent, tool=tool, error="timeout"
            )

        span = mock_send.call_args[0][0]
        assert span.parent_span_id == "handoff-err-span"


# =============================================================================
# Full flow: agent_start -> handoff -> tool_start -> tool_end
# =============================================================================


class TestFullLineageFlow:
    async def test_complete_delegation_chain(
        self, hooks: LangSightOpenAIHooks, client: LangSightClient
    ) -> None:
        """Verify the full parent chain:
        agent_span(orchestrator) -> handoff_span -> tool_span(billing tool)
        """
        captured_spans: list[ToolCallSpan] = []
        original_buffer = client.buffer_span

        def capture(span: ToolCallSpan) -> None:
            captured_spans.append(span)

        client.buffer_span = capture  # type: ignore[assignment]

        orchestrator = _make_agent("orchestrator")
        billing = _make_agent("billing-agent")
        tool = _make_tool("fetch_invoice")

        # Step 1: Orchestrator starts
        await hooks.on_agent_start(context=None, agent=orchestrator)

        # Step 2: Orchestrator hands off to billing
        await hooks.on_handoff(
            context=None, from_agent=orchestrator, to_agent=billing
        )

        # Step 3: Billing agent starts (should link to handoff)
        await hooks.on_agent_start(context=None, agent=billing)

        # Step 4: Billing agent calls a tool
        await hooks.on_tool_start(context=None, agent=billing, tool=tool)
        await hooks.on_tool_end(
            context=None, agent=billing, tool=tool, result="invoice-data"
        )

        client.buffer_span = original_buffer  # type: ignore[assignment]

        # Verify spans
        assert len(captured_spans) == 4

        orchestrator_span = captured_spans[0]
        handoff_span = captured_spans[1]
        billing_agent_span = captured_spans[2]
        tool_span = captured_spans[3]

        # Orchestrator agent span has no parent
        assert orchestrator_span.span_type == "agent"
        assert orchestrator_span.agent_name == "orchestrator"
        assert orchestrator_span.parent_span_id is None

        # Handoff links to orchestrator
        assert handoff_span.span_type == "handoff"
        assert handoff_span.parent_span_id == orchestrator_span.span_id
        assert handoff_span.target_agent_name == "billing-agent"

        # Billing agent span links to handoff
        assert billing_agent_span.span_type == "agent"
        assert billing_agent_span.agent_name == "billing-agent"
        assert billing_agent_span.parent_span_id == handoff_span.span_id

        # Tool span links to handoff (via _active_handoffs)
        assert tool_span.tool_name == "fetch_invoice"
        assert tool_span.agent_name == "billing-agent"
        assert tool_span.parent_span_id == handoff_span.span_id

    async def test_double_handoff_chain(
        self, hooks: LangSightOpenAIHooks, client: LangSightClient
    ) -> None:
        """A -> handoff -> B -> handoff -> C -> tool.
        Verify C's tool links to B's handoff span."""
        captured: list[ToolCallSpan] = []
        client.buffer_span = lambda span: captured.append(span)  # type: ignore[assignment]

        agent_a = _make_agent("agent-a")
        agent_b = _make_agent("agent-b")
        agent_c = _make_agent("agent-c")
        tool = _make_tool("final_tool")

        await hooks.on_agent_start(context=None, agent=agent_a)
        await hooks.on_handoff(context=None, from_agent=agent_a, to_agent=agent_b)
        await hooks.on_agent_start(context=None, agent=agent_b)
        await hooks.on_handoff(context=None, from_agent=agent_b, to_agent=agent_c)
        await hooks.on_agent_start(context=None, agent=agent_c)
        await hooks.on_tool_start(context=None, agent=agent_c, tool=tool)
        await hooks.on_tool_end(context=None, agent=agent_c, tool=tool, result="ok")

        # Find spans
        handoff_b_to_c = [
            s for s in captured
            if s.span_type == "handoff" and s.target_agent_name == "agent-c"
        ][0]
        tool_span = [s for s in captured if s.tool_name == "final_tool"][0]

        # C's tool should link to B->C handoff
        assert tool_span.parent_span_id == handoff_b_to_c.span_id
        assert tool_span.agent_name == "agent-c"
