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
from typing import Any

import httpx
import structlog

from langsight.sdk.models import ToolCallSpan

logger = structlog.get_logger()

_SPANS_ENDPOINT = "/api/traces/spans"
_TOOL_SCHEMA_ENDPOINT = "/api/servers/{server_name}/tools"
_SEND_TIMEOUT = 3.0
_BATCH_SIZE = 50  # flush when buffer reaches this many spans
_FLUSH_INTERVAL = 1.0  # seconds between automatic flushes
_MAX_BUFFER_SIZE = 10_000  # hard cap — drop oldest spans on overflow to prevent OOM


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
        redact_payloads: bool = False,
        project_id: str | None = None,
        batch_size: int = _BATCH_SIZE,
        flush_interval: float = _FLUSH_INTERVAL,
        max_buffer_size: int = _MAX_BUFFER_SIZE,
    ) -> None:
        self._url = url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._redact_payloads = redact_payloads
        self._project_id = project_id
        self._http: httpx.AsyncClient | None = None
        self._batch_size = batch_size
        self._flush_interval = flush_interval
        self._max_buffer_size = max_buffer_size
        self._buffer: list[ToolCallSpan] = []
        self._flush_task: asyncio.Task[None] | None = None

    def wrap(
        self,
        mcp_client: object,
        server_name: str = "unknown",
        agent_name: str | None = None,
        session_id: str | None = None,
        trace_id: str | None = None,
        parent_span_id: str | None = None,
        redact_payloads: bool | None = None,
        project_id: str | None = None,
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
        effective_redact = redact_payloads if redact_payloads is not None else self._redact_payloads
        effective_project = project_id if project_id is not None else self._project_id
        return MCPClientProxy(
            mcp_client,
            langsight=self,
            server_name=server_name,
            agent_name=agent_name,
            session_id=session_id,
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            redact_payloads=effective_redact,
            project_id=effective_project,
        )

    async def send_span(self, span: ToolCallSpan) -> None:
        """Buffer a span for batched delivery. Never blocks, never raises.

        Spans are flushed automatically when the buffer reaches ``batch_size``
        or every ``flush_interval`` seconds — whichever comes first.
        If the buffer exceeds ``max_buffer_size``, oldest spans are dropped
        to prevent unbounded memory growth when the backend is slow/down.
        """
        self._buffer.append(span)
        if len(self._buffer) > self._max_buffer_size:
            dropped = len(self._buffer) - self._max_buffer_size
            self._buffer = self._buffer[dropped:]
            logger.warning("sdk.buffer_overflow", dropped=dropped, max=self._max_buffer_size)
        self._ensure_flush_loop()
        if len(self._buffer) >= self._batch_size:
            asyncio.create_task(self.flush())

    async def send_spans(self, spans: list[ToolCallSpan]) -> None:
        """Buffer multiple spans. Triggers immediate flush if threshold reached."""
        self._buffer.extend(spans)
        if len(self._buffer) > self._max_buffer_size:
            dropped = len(self._buffer) - self._max_buffer_size
            self._buffer = self._buffer[dropped:]
            logger.warning("sdk.buffer_overflow", dropped=dropped, max=self._max_buffer_size)
        self._ensure_flush_loop()
        if len(self._buffer) >= self._batch_size:
            asyncio.create_task(self.flush())

    async def flush(self) -> None:
        """Flush all buffered spans to the API. Safe to call at any time."""
        if not self._buffer:
            return
        batch, self._buffer = self._buffer, []
        await self._post_spans(batch)

    def _ensure_flush_loop(self) -> None:
        """Start the periodic flush background task if not already running."""
        if self._flush_task is None or self._flush_task.done():
            try:
                self._flush_task = asyncio.create_task(self._flush_loop())
            except RuntimeError:
                pass  # no running event loop (e.g. during shutdown)

    async def _flush_loop(self) -> None:
        """Background loop that flushes the buffer periodically."""
        try:
            while True:
                await asyncio.sleep(self._flush_interval)
                await self.flush()
        except asyncio.CancelledError:
            # Final flush on cancellation — don't lose buffered spans
            await self.flush()

    async def _get_http(self) -> httpx.AsyncClient:
        """Return a shared httpx client (connection reuse across requests)."""
        if self._http is None or self._http.is_closed:
            headers = {"Content-Type": "application/json"}
            if self._api_key:
                headers["X-API-Key"] = self._api_key
            self._http = httpx.AsyncClient(timeout=self._timeout, headers=headers)
        return self._http

    async def close(self) -> None:
        """Flush remaining spans, cancel the flush loop, and close the HTTP client."""
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        await self.flush()
        if self._http and not self._http.is_closed:
            await self._http.aclose()
            self._http = None

    async def _post_spans(self, spans: list[ToolCallSpan]) -> None:
        """Internal: POST a batch of spans. Never raises."""
        payload = [s.model_dump(mode="json") for s in spans]
        try:
            http = await self._get_http()
            response = await http.post(
                f"{self._url}{_SPANS_ENDPOINT}",
                json=payload,
            )
            response.raise_for_status()
            logger.debug("sdk.spans_sent", count=len(spans))
        except Exception as exc:  # noqa: BLE001
            # Fail-open: log but never raise — monitoring must not break the app
            logger.warning("sdk.send_failed", error=str(exc), count=len(spans))

    async def record_tool_schemas(
        self,
        server_name: str,
        tools: list[dict[str, object]],
        project_id: str | None = None,
    ) -> None:
        """Fire-and-forget: POST observed tool schemas to the backend. Never raises.

        project_id is sent as a query parameter so get_active_project_id picks
        it up from the request context — body.project_id is no longer trusted.
        """
        endpoint = _TOOL_SCHEMA_ENDPOINT.format(server_name=server_name)
        url = f"{self._url}{endpoint}"
        if project_id:
            from urllib.parse import quote
            url = f"{url}?project_id={quote(project_id)}"
        payload: dict[str, object] = {"tools": tools}
        try:
            http = await self._get_http()
            response = await http.post(url, json=payload)
            response.raise_for_status()
            logger.debug("sdk.tool_schemas_sent", server=server_name, count=len(tools))
        except Exception as exc:  # noqa: BLE001
            logger.debug("sdk.tool_schemas_failed", server=server_name, error=str(exc))


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
        redact_payloads: bool = False,
        project_id: str | None = None,
    ) -> None:
        object.__setattr__(self, "_client", client)
        object.__setattr__(self, "_langsight", langsight)
        object.__setattr__(self, "_server_name", server_name)
        object.__setattr__(self, "_agent_name", agent_name)
        object.__setattr__(self, "_session_id", session_id)
        object.__setattr__(self, "_trace_id", trace_id)
        object.__setattr__(self, "_parent_span_id", parent_span_id)
        object.__setattr__(self, "_redact_payloads", redact_payloads)
        object.__setattr__(self, "_project_id", project_id)

    def __getattr__(self, name: str) -> object:
        """Forward all attribute access to the wrapped client."""
        return getattr(object.__getattribute__(self, "_client"), name)

    async def list_tools(self) -> object:
        """Intercept list_tools() to capture declared tool schemas, then forward."""
        client = object.__getattribute__(self, "_client")
        langsight = object.__getattribute__(self, "_langsight")
        server_name = object.__getattribute__(self, "_server_name")
        project_id = object.__getattribute__(self, "_project_id")

        result = await client.list_tools()

        # Extract tool schemas from MCP SDK response (fail-open)
        try:
            tools_list = getattr(result, "tools", None) or result
            tools_payload = []
            for t in tools_list:
                tools_payload.append({
                    "name": getattr(t, "name", str(t)),
                    "description": getattr(t, "description", "") or "",
                    "input_schema": getattr(t, "inputSchema", None) or getattr(t, "input_schema", None) or {},
                })
            record_coro = langsight.record_tool_schemas(server_name, tools_payload, project_id)
            try:
                asyncio.create_task(record_coro)
            except RuntimeError:
                record_coro.close()
        except Exception as exc:  # noqa: BLE001
            logger.debug("sdk.list_tools_capture_failed", server=server_name, error=str(exc))

        return result

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> object:
        """Call a tool and record a ToolCallSpan regardless of outcome."""
        import json
        from datetime import UTC, datetime

        from langsight.sdk.models import ToolCallSpan, ToolCallStatus

        client = object.__getattribute__(self, "_client")
        langsight = object.__getattribute__(self, "_langsight")
        server_name = object.__getattribute__(self, "_server_name")
        agent_name = object.__getattribute__(self, "_agent_name")
        session_id = object.__getattribute__(self, "_session_id")
        trace_id = object.__getattribute__(self, "_trace_id")
        parent_span_id = object.__getattribute__(self, "_parent_span_id")
        redact = object.__getattribute__(self, "_redact_payloads")
        project_id = object.__getattribute__(self, "_project_id")

        started_at = datetime.now(UTC)
        status = ToolCallStatus.SUCCESS
        error: str | None = None
        output_result: str | None = None

        try:
            result = await client.call_tool(name, arguments)
            if not redact:
                try:
                    output_result = json.dumps(result, default=str)
                except Exception:  # noqa: BLE001
                    output_result = str(result)
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
                input_args=None if redact else arguments,
                output_result=output_result,
                project_id=project_id,
            )
            await langsight.send_span(span)
