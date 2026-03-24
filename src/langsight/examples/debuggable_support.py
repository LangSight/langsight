from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from mcp.server.fastmcp import FastMCP

from langsight.sdk.client import LangSightClient
from langsight.sdk.models import ToolCallSpan, ToolCallStatus


def _extract_structured_result(result: object) -> dict[str, Any]:
    """Normalize FastMCP call_tool() output to the structured payload."""
    if isinstance(result, tuple) and len(result) == 2 and isinstance(result[1], dict):
        return result[1]
    if isinstance(result, dict):
        return result
    return {"result": result}


@dataclass(slots=True)
class DebugDiagnostics:
    error_count: int
    failing_agent: str | None
    failing_server: str | None
    failing_tool: str | None
    error_message: str | None
    trace_path: list[str]
    recommended_next_step: str

    @property
    def summary(self) -> str:
        if self.error_count == 0:
            return "No tool failures detected in this run."
        return (
            f"{self.failing_agent} failed on "
            f"{self.failing_server}/{self.failing_tool}: {self.error_message}"
        )


@dataclass(slots=True)
class DemoRunResult:
    outcome: str
    session_id: str
    trace_id: str
    customer_id: str
    request: str
    final_message: str
    spans: list[ToolCallSpan]
    captured_tools: dict[str, list[dict[str, object]]]
    diagnostics: DebugDiagnostics

    def render_report(self) -> str:
        trace_path = " -> ".join(self.diagnostics.trace_path)
        lines = [
            "Debuggable Support Demo",
            f"Trace Path: {trace_path}",
            f"Outcome: {self.outcome}",
            f"Errors: {self.diagnostics.error_count}",
        ]
        if self.diagnostics.error_count:
            lines.extend(
                [
                    "Root Cause: "
                    f"{self.diagnostics.failing_agent} -> "
                    f"{self.diagnostics.failing_server}/{self.diagnostics.failing_tool}",
                    f"Error Detail: {self.diagnostics.error_message}",
                    f"Recommended next step: {self.diagnostics.recommended_next_step}",
                ]
            )
        else:
            lines.append("Root Cause: none")
        return "\n".join(lines)


class RecordingLangSightClient(LangSightClient):
    """In-memory LangSight client for offline observability verification."""

    def __init__(self) -> None:
        super().__init__(url="http://localhost:8000")
        self.recorded_spans: list[ToolCallSpan] = []
        self.captured_tools: dict[str, list[dict[str, object]]] = {}

    def reset(self) -> None:
        self.recorded_spans.clear()
        self.captured_tools.clear()

    def buffer_span(self, span: ToolCallSpan) -> None:
        self.recorded_spans.append(span)

    async def send_span(self, span: ToolCallSpan) -> None:
        self.buffer_span(span)

    async def record_tool_schemas(
        self,
        server_name: str,
        tools: list[dict[str, object]],
        project_id: str | None = None,
    ) -> None:
        del project_id
        self.captured_tools[server_name] = tools


class DebuggableSupportProject:
    """Offline demo showing how LangSight captures traces and debugging context."""

    def __init__(
        self,
        *,
        simulate_billing_failure: bool = False,
        client: RecordingLangSightClient | None = None,
    ) -> None:
        self._simulate_billing_failure = simulate_billing_failure
        self._client = client or RecordingLangSightClient()
        self._customers = {
            "cust-001": {
                "customer_id": "cust-001",
                "email": "customer@example.com",
                "plan": "pro",
                "slack_channel": "#support-escalations",
            }
        }
        self._invoices = {
            "cust-001": {
                "invoice_id": "inv-1001",
                "amount": 49.0,
                "currency": "USD",
                "charge_status": "duplicate_charge",
            }
        }
        self._servers = {
            "profile-mcp": self._build_profile_server(),
            "billing-mcp": self._build_billing_server(),
            "comms-mcp": self._build_comms_server(),
        }

    async def run(self, *, customer_id: str, request: str) -> DemoRunResult:
        self._client.reset()
        session_id = f"sess-{uuid4().hex[:8]}"
        trace_id = f"trace-{uuid4().hex[:8]}"

        triage = self._client.wrap(
            self._servers["profile-mcp"],
            server_name="profile-mcp",
            agent_name="triage-agent",
            session_id=session_id,
            trace_id=trace_id,
        )
        await triage.list_tools()
        await asyncio.sleep(0)
        profile = _extract_structured_result(
            await triage.call_tool("lookup_customer", {"customer_id": customer_id})
        )

        billing_handoff = ToolCallSpan.handoff_span(
            from_agent="triage-agent",
            to_agent="billing-agent",
            started_at=datetime.now(UTC),
            trace_id=trace_id,
            session_id=session_id,
        )
        self._client.buffer_span(billing_handoff)

        billing = self._client.wrap(
            self._servers["billing-mcp"],
            server_name="billing-mcp",
            agent_name="billing-agent",
            session_id=session_id,
            trace_id=trace_id,
            parent_span_id=billing_handoff.span_id,
        )
        await billing.list_tools()
        await asyncio.sleep(0)
        invoice = _extract_structured_result(
            await billing.call_tool("get_invoice", {"customer_id": customer_id})
        )

        outcome = "resolved"
        final_message = "Refund processed and customer notified."
        try:
            refund = _extract_structured_result(
                await billing.call_tool(
                    "issue_refund",
                    {
                        "customer_id": customer_id,
                        "invoice_id": invoice["invoice_id"],
                        "amount": invoice["amount"],
                    },
                )
            )
        except Exception:
            refund = None
            outcome = "needs_manual_review"
            final_message = "Refund failed and was escalated for manual investigation."

        comms_handoff = ToolCallSpan.handoff_span(
            from_agent="billing-agent",
            to_agent="comms-agent",
            started_at=datetime.now(UTC),
            trace_id=trace_id,
            session_id=session_id,
            parent_span_id=billing_handoff.span_id,
        )
        self._client.buffer_span(comms_handoff)

        comms = self._client.wrap(
            self._servers["comms-mcp"],
            server_name="comms-mcp",
            agent_name="comms-agent",
            session_id=session_id,
            trace_id=trace_id,
            parent_span_id=comms_handoff.span_id,
        )
        await comms.list_tools()
        await asyncio.sleep(0)
        await comms.call_tool(
            "post_update",
            {
                "channel": profile["slack_channel"],
                "message": self._compose_update(
                    customer_id=customer_id,
                    request=request,
                    refund=refund,
                    outcome=outcome,
                ),
            },
        )

        diagnostics = self._build_diagnostics(self._client.recorded_spans)
        return DemoRunResult(
            outcome=outcome,
            session_id=session_id,
            trace_id=trace_id,
            customer_id=customer_id,
            request=request,
            final_message=final_message,
            spans=list(self._client.recorded_spans),
            captured_tools=dict(self._client.captured_tools),
            diagnostics=diagnostics,
        )

    def _build_profile_server(self) -> FastMCP:
        server = FastMCP("profile-mcp")
        customers = self._customers

        @server.tool()
        def lookup_customer(customer_id: str) -> dict[str, Any]:
            customer = customers.get(customer_id)
            if customer is None:
                raise ValueError(f"Unknown customer_id: {customer_id}")
            return customer

        return server

    def _build_billing_server(self) -> FastMCP:
        server = FastMCP("billing-mcp")
        invoices = self._invoices
        simulate_billing_failure = self._simulate_billing_failure

        @server.tool()
        def get_invoice(customer_id: str) -> dict[str, Any]:
            invoice = invoices.get(customer_id)
            if invoice is None:
                raise ValueError(f"No invoice found for customer_id: {customer_id}")
            return invoice

        @server.tool()
        def issue_refund(customer_id: str, invoice_id: str, amount: float) -> dict[str, Any]:
            if simulate_billing_failure:
                raise RuntimeError("ledger service unavailable while issuing refund")
            return {
                "customer_id": customer_id,
                "invoice_id": invoice_id,
                "amount": amount,
                "status": "refunded",
            }

        return server

    def _build_comms_server(self) -> FastMCP:
        server = FastMCP("comms-mcp")

        @server.tool()
        def post_update(channel: str, message: str) -> dict[str, str]:
            return {"channel": channel, "message": message, "status": "posted"}

        return server

    def _compose_update(
        self,
        *,
        customer_id: str,
        request: str,
        refund: dict[str, Any] | None,
        outcome: str,
    ) -> str:
        if refund is not None:
            return (
                f"{customer_id}: {request} "
                f"Refund status={refund['status']} amount={refund['amount']}."
            )
        return (
            f"{customer_id}: {request} Escalated because automated refund flow failed ({outcome})."
        )

    def _build_diagnostics(self, spans: list[ToolCallSpan]) -> DebugDiagnostics:
        error_spans = [span for span in spans if span.status == ToolCallStatus.ERROR]
        failing_span = error_spans[0] if error_spans else None
        trace_path = self._trace_path(spans)
        if failing_span is None:
            return DebugDiagnostics(
                error_count=0,
                failing_agent=None,
                failing_server=None,
                failing_tool=None,
                error_message=None,
                trace_path=trace_path,
                recommended_next_step="No action required.",
            )
        return DebugDiagnostics(
            error_count=len(error_spans),
            failing_agent=failing_span.agent_name,
            failing_server=failing_span.server_name,
            failing_tool=failing_span.tool_name,
            error_message=failing_span.error,
            trace_path=trace_path,
            recommended_next_step=(
                "Replay billing-mcp.issue_refund with the captured payload and inspect "
                "the upstream ledger dependency."
            ),
        )

    def _trace_path(self, spans: list[ToolCallSpan]) -> list[str]:
        path: list[str] = []
        for span in spans:
            if span.agent_name and span.agent_name not in path:
                path.append(span.agent_name)
            if span.span_type == "handoff":
                target = span.tool_name.replace("→", "", 1).strip()
                if target and target not in path:
                    path.append(target)
        return path
