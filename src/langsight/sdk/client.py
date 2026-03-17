"""
LangSightClient — sends ToolCallSpans to the LangSight API.

Design principles:
- Fire-and-forget: span delivery never blocks tool calls
- Fail-open: if LangSight is unreachable, tool calls still work
- Async-native: uses httpx.AsyncClient internally
- Zero config: works with just a URL
"""

from __future__ import annotations

import asyncio

import httpx
import structlog

from langsight.sdk.models import ToolCallSpan

logger = structlog.get_logger()

_SPANS_ENDPOINT = "/api/traces/spans"
_SEND_TIMEOUT = 3.0


class LangSightClient:
    """Sends observability data to the LangSight API.

    Usage:
        client = LangSightClient(url="http://localhost:8000")
        traced = client.wrap(mcp_session)

        # All tool calls now traced
        result = await traced.call_tool("query", {"sql": "SELECT 1"})

    The client is fail-open: if the LangSight server is unreachable,
    tool calls proceed normally and the error is logged.
    """

    def __init__(
        self,
        url: str,
        api_key: str | None = None,
        timeout: float = _SEND_TIMEOUT,
    ) -> None:
        self._url = url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout

    def wrap(
        self,
        mcp_client: object,
        server_name: str = "unknown",
        agent_name: str | None = None,
        session_id: str | None = None,
        trace_id: str | None = None,
        parent_span_id: str | None = None,
    ) -> MCPClientProxy:
        """Wrap an MCP client to automatically trace all tool calls.

        Args:
            mcp_client: Any object with a `call_tool(name, arguments)` method.
            server_name: MCP server or tool source name (e.g. "postgres-mcp").
            agent_name: Name of the agent making the calls.
            session_id: Groups all calls in one agent run/conversation.
            trace_id: Groups all spans across a multi-agent task.
            parent_span_id: For multi-agent tracing — the handoff span ID
                that spawned this sub-agent. Enables tree reconstruction.

        Multi-agent example:
            # Orchestrator wraps its MCP client normally
            orchestrator_mcp = client.wrap(mcp, server_name="jira-mcp",
                                           agent_name="orchestrator",
                                           session_id=session_id,
                                           trace_id=trace_id)

            # When handing off to a sub-agent, pass the handoff span ID
            handoff = ToolCallSpan.handoff_span(
                from_agent="orchestrator", to_agent="billing-agent",
                started_at=datetime.now(UTC),
                trace_id=trace_id, session_id=session_id,
            )
            await client.send_span(handoff)

            # Sub-agent wraps its client with parent_span_id=handoff.span_id
            billing_mcp = client.wrap(mcp, server_name="crm-mcp",
                                      agent_name="billing-agent",
                                      session_id=session_id,
                                      trace_id=trace_id,
                                      parent_span_id=handoff.span_id)
        """
        return MCPClientProxy(
            mcp_client,
            langsight=self,
            server_name=server_name,
            agent_name=agent_name,
            session_id=session_id,
            trace_id=trace_id,
            parent_span_id=parent_span_id,
        )

    async def send_span(self, span: ToolCallSpan) -> None:
        """Send a single span to the LangSight API (fire-and-forget wrapper).

        Call this directly if you want to record a span outside of wrap().
        Does not raise — all errors are logged.
        """
        asyncio.create_task(self._post_span(span))

    async def send_spans(self, spans: list[ToolCallSpan]) -> None:
        """Send multiple spans in a single request."""
        asyncio.create_task(self._post_spans(spans))

    async def _post_span(self, span: ToolCallSpan) -> None:
        """Internal: POST a single span. Never raises."""
        await self._post_spans([span])

    async def _post_spans(self, spans: list[ToolCallSpan]) -> None:
        """Internal: POST a batch of spans. Never raises."""
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        payload = [s.model_dump(mode="json") for s in spans]
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as http:
                response = await http.post(
                    f"{self._url}{_SPANS_ENDPOINT}",
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
            logger.debug("sdk.spans_sent", count=len(spans))
        except Exception as exc:  # noqa: BLE001
            # Fail-open: log but never raise — monitoring must not break the app
            logger.warning("sdk.send_failed", error=str(exc), count=len(spans))


class MCPClientProxy:
    """Transparent proxy around an MCP client that records ToolCallSpans.

    Forwards every attribute access to the wrapped client. Only `call_tool`
    is intercepted to record observability data.
    """

    def __init__(
        self,
        client: object,
        langsight: LangSightClient,
        server_name: str = "unknown",
        agent_name: str | None = None,
        session_id: str | None = None,
        trace_id: str | None = None,
        parent_span_id: str | None = None,
    ) -> None:
        # Use object.__setattr__ to avoid triggering our __getattr__
        object.__setattr__(self, "_client", client)
        object.__setattr__(self, "_langsight", langsight)
        object.__setattr__(self, "_server_name", server_name)
        object.__setattr__(self, "_agent_name", agent_name)
        object.__setattr__(self, "_session_id", session_id)
        object.__setattr__(self, "_trace_id", trace_id)
        object.__setattr__(self, "_parent_span_id", parent_span_id)

    def __getattr__(self, name: str) -> object:
        """Forward all attribute access to the wrapped client."""
        return getattr(object.__getattribute__(self, "_client"), name)

    async def call_tool(self, name: str, arguments: dict | None = None) -> object:
        """Call a tool and record a ToolCallSpan regardless of outcome."""
        from datetime import UTC, datetime

        from langsight.sdk.models import ToolCallSpan, ToolCallStatus

        client = object.__getattribute__(self, "_client")
        langsight = object.__getattribute__(self, "_langsight")
        server_name = object.__getattribute__(self, "_server_name")
        agent_name = object.__getattribute__(self, "_agent_name")
        session_id = object.__getattribute__(self, "_session_id")
        trace_id = object.__getattribute__(self, "_trace_id")
        parent_span_id = object.__getattribute__(self, "_parent_span_id")

        started_at = datetime.now(UTC)
        status = ToolCallStatus.SUCCESS
        error: str | None = None

        try:
            result = await client.call_tool(name, arguments)
            return result
        except TimeoutError as exc:
            status = ToolCallStatus.TIMEOUT
            error = str(exc)
            raise
        except Exception as exc:  # noqa: BLE001
            status = ToolCallStatus.ERROR
            error = str(exc)
            raise
        finally:
            span = ToolCallSpan.record(
                server_name=server_name,
                tool_name=name,
                started_at=started_at,
                status=status,
                error=error,
                trace_id=trace_id,
                agent_name=agent_name,
                session_id=session_id,
                parent_span_id=parent_span_id,
                span_type="tool_call",
            )
            await langsight.send_span(span)
