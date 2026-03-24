"""
Tests for multi-agent tracing: parent_span_id, handoff spans, agent spans.
"""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from langsight.sdk.client import LangSightClient, MCPClientProxy
from langsight.sdk.models import ToolCallSpan, ToolCallStatus


class TestToolCallSpanNewFields:
    def test_default_span_type_is_tool_call(self) -> None:
        now = datetime.now(UTC)
        span = ToolCallSpan(
            server_name="pg", tool_name="query",
            started_at=now, ended_at=now, latency_ms=0,
            status=ToolCallStatus.SUCCESS,
        )
        assert span.span_type == "tool_call"
        assert span.parent_span_id is None

    def test_parent_span_id_stored(self) -> None:
        now = datetime.now(UTC)
        span = ToolCallSpan(
            server_name="pg", tool_name="query",
            started_at=now, ended_at=now, latency_ms=0,
            status=ToolCallStatus.SUCCESS,
            parent_span_id="parent-123",
        )
        assert span.parent_span_id == "parent-123"

    def test_record_passes_parent_span_id(self) -> None:
        span = ToolCallSpan.record(
            server_name="pg", tool_name="query",
            started_at=datetime.now(UTC),
            status=ToolCallStatus.SUCCESS,
            parent_span_id="parent-abc",
            span_type="tool_call",
        )
        assert span.parent_span_id == "parent-abc"
        assert span.span_type == "tool_call"


class TestHandoffSpan:
    def test_creates_handoff_span(self) -> None:
        span = ToolCallSpan.handoff_span(
            from_agent="orchestrator",
            to_agent="billing-agent",
            started_at=datetime.now(UTC),
            trace_id="trace-123",
            session_id="sess-abc",
        )
        assert span.span_type == "handoff"
        assert span.agent_name == "orchestrator"
        assert "billing-agent" in span.tool_name
        assert span.trace_id == "trace-123"
        assert span.session_id == "sess-abc"
        assert span.status == ToolCallStatus.SUCCESS

    def test_handoff_span_has_unique_span_id(self) -> None:
        now = datetime.now(UTC)
        s1 = ToolCallSpan.handoff_span("a", "b", now)
        s2 = ToolCallSpan.handoff_span("a", "b", now)
        assert s1.span_id != s2.span_id


class TestAgentSpan:
    def test_creates_agent_span(self) -> None:
        span = ToolCallSpan.agent_span(
            agent_name="support-agent",
            task="resolve ticket #123",
            started_at=datetime.now(UTC),
            trace_id="trace-123",
        )
        assert span.span_type == "agent"
        assert span.agent_name == "support-agent"
        assert span.tool_name == "resolve ticket #123"

    def test_agent_span_with_parent(self) -> None:
        span = ToolCallSpan.agent_span(
            agent_name="sub-agent",
            task="sub-task",
            started_at=datetime.now(UTC),
            parent_span_id="handoff-span-id",
        )
        assert span.parent_span_id == "handoff-span-id"


class TestMultiAgentSDKIntegration:
    async def test_wrap_accepts_parent_span_id(self) -> None:
        client = LangSightClient(url="http://localhost:8000")
        mock_mcp = MagicMock()
        proxy = client.wrap(
            mock_mcp,
            server_name="crm-mcp",
            agent_name="billing-agent",
            session_id="sess-123",
            trace_id="trace-abc",
            parent_span_id="handoff-span-id",
        )
        assert isinstance(proxy, MCPClientProxy)
        assert object.__getattribute__(proxy, "_parent_span_id") == "handoff-span-id"

    async def test_tool_call_span_inherits_parent_span_id(self) -> None:
        mock_mcp = MagicMock()
        mock_mcp.call_tool = AsyncMock(return_value={})
        langsight = LangSightClient(url="http://localhost:8000")

        with patch.object(langsight, "buffer_span") as mock_send:
            proxy = langsight.wrap(
                mock_mcp,
                server_name="crm-mcp",
                parent_span_id="handoff-abc",
            )
            await proxy.call_tool("update_customer", {})

        span: ToolCallSpan = mock_send.call_args[0][0]
        assert span.parent_span_id == "handoff-abc"
        assert span.span_type == "tool_call"

    async def test_full_multi_agent_flow(self) -> None:
        """Simulate: orchestrator calls jira, hands off to billing-agent."""
        langsight = LangSightClient(url="http://localhost:8000")
        sent_spans: list[ToolCallSpan] = []

        def capture_span(span: ToolCallSpan) -> None:
            sent_spans.append(span)

        with patch.object(langsight, "_post_spans", new_callable=AsyncMock):
            with patch.object(langsight, "buffer_span", side_effect=capture_span):

                # Orchestrator calls jira-mcp
                mock_jira = MagicMock()
                mock_jira.call_tool = AsyncMock(return_value={"issue": "PROJ-42"})
                orch_mcp = langsight.wrap(
                    mock_jira, server_name="jira-mcp",
                    agent_name="orchestrator",
                    session_id="sess-123", trace_id="trace-abc",
                )
                await orch_mcp.call_tool("get_issue", {"id": "PROJ-42"})

                # Orchestrator emits handoff span
                handoff = ToolCallSpan.handoff_span(
                    from_agent="orchestrator", to_agent="billing-agent",
                    started_at=datetime.now(UTC),
                    trace_id="trace-abc", session_id="sess-123",
                )
                langsight.buffer_span(handoff)

                # Billing agent calls crm-mcp with parent_span_id = handoff.span_id
                mock_crm = MagicMock()
                mock_crm.call_tool = AsyncMock(return_value={})
                billing_mcp = langsight.wrap(
                    mock_crm, server_name="crm-mcp",
                    agent_name="billing-agent",
                    session_id="sess-123", trace_id="trace-abc",
                    parent_span_id=handoff.span_id,
                )
                await billing_mcp.call_tool("update_customer", {"id": "CUST-1"})

        # 3 spans: tool_call (jira) + handoff + tool_call (crm)
        assert len(sent_spans) == 3

        jira_span = next(s for s in sent_spans if s.server_name == "jira-mcp")
        handoff_span = next(s for s in sent_spans if s.span_type == "handoff")
        crm_span = next(s for s in sent_spans if s.server_name == "crm-mcp")

        # All share the same trace + session
        assert jira_span.trace_id == "trace-abc"
        assert handoff_span.trace_id == "trace-abc"
        assert crm_span.trace_id == "trace-abc"

        # CRM span is a child of the handoff span
        assert crm_span.parent_span_id == handoff_span.span_id

        # Span types correct
        assert jira_span.span_type == "tool_call"
        assert handoff_span.span_type == "handoff"
        assert crm_span.span_type == "tool_call"
