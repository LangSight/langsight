"""Tests for lineage hardening in the Anthropic/Claude Agent SDK integration.

Covers:
- on_handoff links to parent agent span via _active_agent_spans
- on_tool_end uses _current_agent_name after handoff
- on_tool_end sets parent_span_id from _current_handoff_span_id
- Full handoff flow: handoff -> tool_start -> tool_end
- Cleanup after handoff chain
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from langsight.integrations.anthropic_sdk import LangSightClaudeAgentHooks
from langsight.sdk.client import LangSightClient
from langsight.sdk.models import ToolCallSpan, ToolCallStatus


@pytest.fixture
def client() -> LangSightClient:
    return LangSightClient(url="http://localhost:8000")


@pytest.fixture
def hooks(client: LangSightClient) -> LangSightClaudeAgentHooks:
    return LangSightClaudeAgentHooks(
        client=client,
        server_name="test-claude",
        agent_name="default-agent",
        session_id="sess-001",
        trace_id="trace-001",
    )


# =============================================================================
# Constructor — lineage tracking state
# =============================================================================


class TestClaudeAgentHooksLineageInit:
    def test_active_agent_spans_initially_empty(self, hooks: LangSightClaudeAgentHooks) -> None:
        assert hooks._active_agent_spans == {}

    def test_current_handoff_span_id_initially_none(self, hooks: LangSightClaudeAgentHooks) -> None:
        assert hooks._current_handoff_span_id is None

    def test_current_agent_name_initially_none(self, hooks: LangSightClaudeAgentHooks) -> None:
        assert hooks._current_agent_name is None


# =============================================================================
# on_handoff — links to parent agent and stores context for child
# =============================================================================


class TestClaudeAgentHooksOnHandoffLineage:
    async def test_handoff_links_to_parent_agent_span(
        self, hooks: LangSightClaudeAgentHooks, client: LangSightClient
    ) -> None:
        """Handoff span should have parent_span_id from _active_agent_spans."""
        # Simulate orchestrator having an active agent span
        hooks._active_agent_spans["orchestrator"] = "orch-span-123"

        with patch.object(client, "buffer_span") as mock_send:
            await hooks.on_handoff(from_agent="orchestrator", to_agent="billing")

        span = mock_send.call_args[0][0]
        assert span.parent_span_id == "orch-span-123"

    async def test_handoff_without_active_parent_has_no_parent(
        self, hooks: LangSightClaudeAgentHooks, client: LangSightClient
    ) -> None:
        """If from_agent has no tracked span, handoff has no parent."""
        with patch.object(client, "buffer_span") as mock_send:
            await hooks.on_handoff(from_agent="unknown-agent", to_agent="target")

        span = mock_send.call_args[0][0]
        assert span.parent_span_id is None

    async def test_handoff_stores_span_id_for_child(
        self, hooks: LangSightClaudeAgentHooks, client: LangSightClient
    ) -> None:
        with patch.object(client, "buffer_span") as mock_send:
            await hooks.on_handoff(from_agent="a", to_agent="b")

        handoff_span = mock_send.call_args[0][0]
        assert hooks._current_handoff_span_id == handoff_span.span_id

    async def test_handoff_updates_current_agent_name(
        self, hooks: LangSightClaudeAgentHooks, client: LangSightClient
    ) -> None:
        with patch.object(client, "buffer_span"):
            await hooks.on_handoff(from_agent="a", to_agent="billing-agent")

        assert hooks._current_agent_name == "billing-agent"

    async def test_handoff_span_has_target_agent_name(
        self, hooks: LangSightClaudeAgentHooks, client: LangSightClient
    ) -> None:
        with patch.object(client, "buffer_span") as mock_send:
            await hooks.on_handoff(from_agent="orchestrator", to_agent="analyst")

        span = mock_send.call_args[0][0]
        assert span.target_agent_name == "analyst"

    async def test_handoff_span_type_is_handoff(
        self, hooks: LangSightClaudeAgentHooks, client: LangSightClient
    ) -> None:
        with patch.object(client, "buffer_span") as mock_send:
            await hooks.on_handoff(from_agent="a", to_agent="b")

        span = mock_send.call_args[0][0]
        assert span.span_type == "handoff"

    async def test_handoff_fail_open(
        self, hooks: LangSightClaudeAgentHooks, client: LangSightClient
    ) -> None:
        with patch.object(client, "buffer_span", side_effect=RuntimeError("network")):
            await hooks.on_handoff(from_agent="a", to_agent="b")
        # No exception raised


# =============================================================================
# on_tool_end — uses handoff context
# =============================================================================


class TestClaudeAgentHooksOnToolEndLineage:
    async def test_tool_end_uses_current_agent_name_after_handoff(
        self, hooks: LangSightClaudeAgentHooks, client: LangSightClient
    ) -> None:
        """After a handoff, tool calls should use the delegated agent's name."""
        # Simulate handoff
        hooks._current_agent_name = "billing-agent"

        await hooks.on_tool_start("fetch_invoice")

        with patch.object(client, "buffer_span") as mock_send:
            await hooks.on_tool_end("fetch_invoice", tool_output="data")

        span = mock_send.call_args[0][0]
        assert span.agent_name == "billing-agent"

    async def test_tool_end_falls_back_to_constructor_agent_name(
        self, hooks: LangSightClaudeAgentHooks, client: LangSightClient
    ) -> None:
        """Without handoff, should use the constructor-provided agent_name."""
        assert hooks._current_agent_name is None

        await hooks.on_tool_start("search")

        with patch.object(client, "buffer_span") as mock_send:
            await hooks.on_tool_end("search", tool_output="results")

        span = mock_send.call_args[0][0]
        assert span.agent_name == "default-agent"

    async def test_tool_end_sets_parent_from_handoff_span(
        self, hooks: LangSightClaudeAgentHooks, client: LangSightClient
    ) -> None:
        hooks._current_handoff_span_id = "handoff-span-abc"

        await hooks.on_tool_start("query")

        with patch.object(client, "buffer_span") as mock_send:
            await hooks.on_tool_end("query", tool_output="rows")

        span = mock_send.call_args[0][0]
        assert span.parent_span_id == "handoff-span-abc"

    async def test_tool_end_no_handoff_has_no_parent(
        self, hooks: LangSightClaudeAgentHooks, client: LangSightClient
    ) -> None:
        assert hooks._current_handoff_span_id is None

        await hooks.on_tool_start("search")

        with patch.object(client, "buffer_span") as mock_send:
            await hooks.on_tool_end("search")

        span = mock_send.call_args[0][0]
        assert span.parent_span_id is None


# =============================================================================
# on_tool_error — uses handoff context
# =============================================================================


class TestClaudeAgentHooksOnToolErrorLineage:
    async def test_tool_error_uses_current_agent_name(
        self, hooks: LangSightClaudeAgentHooks, client: LangSightClient
    ) -> None:
        hooks._current_agent_name = "billing-agent"

        await hooks.on_tool_start("pay")

        with patch.object(client, "buffer_span") as mock_send:
            await hooks.on_tool_error("pay", error="payment failed")

        span = mock_send.call_args[0][0]
        assert span.agent_name == "billing-agent"
        assert span.status == ToolCallStatus.ERROR

    async def test_tool_error_sets_parent_from_handoff(
        self, hooks: LangSightClaudeAgentHooks, client: LangSightClient
    ) -> None:
        hooks._current_handoff_span_id = "handoff-err-123"

        await hooks.on_tool_start("fail_tool")

        with patch.object(client, "buffer_span") as mock_send:
            await hooks.on_tool_error("fail_tool", error="timeout")

        span = mock_send.call_args[0][0]
        assert span.parent_span_id == "handoff-err-123"


# =============================================================================
# Full flow: handoff -> tool_start -> tool_end
# =============================================================================


class TestClaudeAgentHooksFullFlow:
    async def test_handoff_then_tool_call(
        self, hooks: LangSightClaudeAgentHooks, client: LangSightClient
    ) -> None:
        """Full flow: orchestrator hands off to billing, billing calls a tool."""
        captured: list[ToolCallSpan] = []
        client.buffer_span = lambda span: captured.append(span)  # type: ignore[assignment]

        # Step 1: Orchestrator hands off to billing
        await hooks.on_handoff(from_agent="orchestrator", to_agent="billing")

        # Step 2: Billing's tool call
        await hooks.on_tool_start("fetch_invoice", {"id": "inv-123"})
        await hooks.on_tool_end("fetch_invoice", tool_output="invoice data")

        assert len(captured) == 2
        handoff_span = captured[0]
        tool_span = captured[1]

        assert handoff_span.span_type == "handoff"
        assert handoff_span.target_agent_name == "billing"

        assert tool_span.agent_name == "billing"
        assert tool_span.parent_span_id == handoff_span.span_id
        assert tool_span.status == ToolCallStatus.SUCCESS

    async def test_second_handoff_overwrites_context(
        self, hooks: LangSightClaudeAgentHooks, client: LangSightClient
    ) -> None:
        """Second handoff should update the current context for subsequent tools."""
        captured: list[ToolCallSpan] = []
        client.buffer_span = lambda span: captured.append(span)  # type: ignore[assignment]

        # First handoff: orchestrator -> billing
        await hooks.on_handoff(from_agent="orchestrator", to_agent="billing")
        first_handoff_span = captured[-1]

        # Second handoff: billing -> analytics
        await hooks.on_handoff(from_agent="billing", to_agent="analytics")
        second_handoff_span = captured[-1]

        # Tool call should link to the second handoff
        await hooks.on_tool_start("run_query")
        await hooks.on_tool_end("run_query", tool_output="data")
        tool_span = captured[-1]

        assert tool_span.agent_name == "analytics"
        assert tool_span.parent_span_id == second_handoff_span.span_id
        assert tool_span.parent_span_id != first_handoff_span.span_id
