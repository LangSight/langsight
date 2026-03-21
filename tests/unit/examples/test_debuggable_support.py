from __future__ import annotations

import pytest

from langsight.sdk.models import ToolCallStatus


@pytest.mark.unit
async def test_success_run_captures_observability_signals() -> None:
    from langsight.examples.debuggable_support import DebuggableSupportProject

    project = DebuggableSupportProject()

    result = await project.run(
        customer_id="cust-001",
        request="Customer was charged twice and needs a refund.",
    )

    assert result.outcome == "resolved"
    assert result.diagnostics.error_count == 0
    assert set(result.captured_tools) == {"profile-mcp", "billing-mcp", "comms-mcp"}
    assert [tool["name"] for tool in result.captured_tools["billing-mcp"]] == [
        "get_invoice",
        "issue_refund",
    ]
    assert any(
        span.span_type == "handoff"
        and span.agent_name == "triage-agent"
        and "billing-agent" in span.tool_name
        for span in result.spans
    )
    assert any(
        span.server_name == "billing-mcp"
        and span.tool_name == "issue_refund"
        and span.status == ToolCallStatus.SUCCESS
        for span in result.spans
    )

    report = result.render_report()
    assert "Trace Path: triage-agent -> billing-agent -> comms-agent" in report
    assert "Errors: 0" in report


@pytest.mark.unit
async def test_failure_run_surfaces_error_trace_for_debugging() -> None:
    from langsight.examples.debuggable_support import DebuggableSupportProject

    project = DebuggableSupportProject(simulate_billing_failure=True)

    result = await project.run(
        customer_id="cust-001",
        request="Customer was charged twice and needs a refund.",
    )

    assert result.outcome == "needs_manual_review"
    assert result.diagnostics.error_count == 1
    assert result.diagnostics.failing_agent == "billing-agent"
    assert result.diagnostics.failing_server == "billing-mcp"
    assert result.diagnostics.failing_tool == "issue_refund"
    assert "ledger service unavailable" in (result.diagnostics.error_message or "")

    error_span = next(span for span in result.spans if span.status == ToolCallStatus.ERROR)
    assert error_span.agent_name == "billing-agent"
    assert error_span.server_name == "billing-mcp"
    assert error_span.tool_name == "issue_refund"

    report = result.render_report()
    assert "Root Cause: billing-agent -> billing-mcp/issue_refund" in report
    assert "ledger service unavailable" in report
    assert "Recommended next step:" in report


@pytest.mark.unit
async def test_failure_trace_keeps_parent_child_links_for_handoffs() -> None:
    from langsight.examples.debuggable_support import DebuggableSupportProject

    project = DebuggableSupportProject(simulate_billing_failure=True)

    result = await project.run(
        customer_id="cust-001",
        request="Customer was charged twice and needs a refund.",
    )

    handoff = next(
        span
        for span in result.spans
        if span.span_type == "handoff" and "billing-agent" in span.tool_name
    )
    error_span = next(span for span in result.spans if span.status == ToolCallStatus.ERROR)

    assert error_span.parent_span_id == handoff.span_id
