"""
LangSightClient — sends ToolCallSpans to the LangSight API.

Design principles:
- Fire-and-forget: span delivery never blocks tool calls
- Fail-open: if LangSight is unreachable, tool calls still work
- Async-native: uses httpx.AsyncClient internally
- Zero config: works with just a URL

v0.3 additions:
- Prevention layer: loop detection, budget guardrails, circuit breaker
- Prevention is BLOCKING by design (must stop the call before it happens)
- Prevented calls are recorded as spans with status=PREVENTED
"""

from __future__ import annotations

import asyncio
import atexit
import json
import threading
from datetime import UTC, datetime
from typing import Any, cast

import httpx
import structlog

from langsight.exceptions import (
    BudgetExceededError,
    CircuitBreakerOpenError,
    LoopDetectedError,
)
from langsight.sdk.budget import BudgetConfig, SessionBudget
from langsight.sdk.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from langsight.sdk.loop_detector import LoopAction, LoopDetector, LoopDetectorConfig
from langsight.sdk.models import ToolCallSpan, ToolCallStatus

logger = structlog.get_logger()

_SPANS_ENDPOINT = "/api/traces/spans"
_TOOL_SCHEMA_ENDPOINT = "/api/servers/{server_name}/tools"
_SEND_TIMEOUT = 3.0
_BATCH_SIZE = 50  # flush when buffer reaches this many spans
_FLUSH_INTERVAL = 1.0  # seconds between automatic flushes
_MAX_BUFFER_SIZE = 10_000  # hard cap — drop oldest spans on overflow to prevent OOM
_MAX_SESSION_STATE = 500  # max live loop-detector/budget entries (one per session_id)
_MAX_SERVER_STATE = 100  # max live circuit-breaker entries (one per server_name)


class LangSightClient:
    """Sends observability data to the LangSight API.

    Usage:
        client = LangSightClient(url="http://localhost:8000")
        traced = client.wrap(mcp_session)

        # All tool calls now traced
        result = await traced.call_tool("query", {"sql": "SELECT 1"})

    The client is fail-open: if the LangSight server is unreachable,
    tool calls proceed normally and the error is logged.

    v0.3 Prevention layer (opt-in):
        client = LangSightClient(
            url="http://localhost:8000",
            loop_detection=True,         # stop infinite loops
            max_steps=25,                # cap tool calls per session
            circuit_breaker=True,        # disable failing servers
        )
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
        # --- v0.3 Prevention layer ---
        loop_detection: bool = False,
        loop_threshold: int = 3,
        loop_action: str = "terminate",
        max_cost_usd: float | None = None,
        max_steps: int | None = None,
        max_wall_time_s: float | None = None,
        budget_soft_alert: float = 0.80,
        pricing_table: dict[str, tuple[float, float]] | None = None,
        circuit_breaker: bool = False,
        circuit_breaker_threshold: int = 5,
        circuit_breaker_cooldown: float = 60.0,
        circuit_breaker_half_open_max: int = 2,
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
        self._lock = threading.Lock()
        self._flush_task: asyncio.Task[None] | None = None

        # Flush any remaining buffered spans on program exit — no user code needed
        atexit.register(self._flush_on_exit)

        # Loop detection config (None = disabled)
        self._loop_config: LoopDetectorConfig | None = (
            LoopDetectorConfig(
                threshold=loop_threshold,
                action=LoopAction(loop_action),
            )
            if loop_detection
            else None
        )
        self._loop_detectors: dict[str, LoopDetector] = {}

        # Budget config (None = no limits)
        has_budget = any(v is not None for v in (max_cost_usd, max_steps, max_wall_time_s))
        self._budget_config: BudgetConfig | None = (
            BudgetConfig(
                max_cost_usd=max_cost_usd,
                max_steps=max_steps,
                max_wall_time_s=max_wall_time_s,
                soft_alert_fraction=budget_soft_alert,
            )
            if has_budget
            else None
        )
        self._session_budgets: dict[str, SessionBudget] = {}
        self._pricing_table: dict[str, tuple[float, float]] = pricing_table or {}

        # Circuit breaker config (None = disabled)
        self._cb_default_config: CircuitBreakerConfig | None = (
            CircuitBreakerConfig(
                failure_threshold=circuit_breaker_threshold,
                cooldown_seconds=circuit_breaker_cooldown,
                half_open_max_calls=circuit_breaker_half_open_max,
            )
            if circuit_breaker
            else None
        )
        self._circuit_breakers: dict[str, CircuitBreaker] = {}

    # --- Prevention state accessors ---

    def _get_circuit_breaker(self, server_name: str) -> CircuitBreaker | None:
        """Return the circuit breaker for a server (creates on first access).

        Evicts the oldest entry when the cap is reached to prevent a rogue agent
        cycling through arbitrary server names from growing the dict without bound.
        """
        if self._cb_default_config is None:
            return None
        if server_name not in self._circuit_breakers:
            if len(self._circuit_breakers) >= _MAX_SERVER_STATE:
                self._circuit_breakers.pop(next(iter(self._circuit_breakers)))
            self._circuit_breakers[server_name] = CircuitBreaker(
                server_name, self._cb_default_config
            )
        return self._circuit_breakers[server_name]

    def _get_loop_detector(self, session_id: str | None) -> LoopDetector | None:
        """Return the loop detector for a session (creates on first access).

        Evicts the oldest entry when the cap is reached to prevent a rogue agent
        generating random session_ids from causing unbounded memory growth (DoS).
        """
        if self._loop_config is None:
            return None
        key = session_id or "__default__"
        if key not in self._loop_detectors:
            if len(self._loop_detectors) >= _MAX_SESSION_STATE:
                self._loop_detectors.pop(next(iter(self._loop_detectors)))
            self._loop_detectors[key] = LoopDetector(self._loop_config)
        return self._loop_detectors[key]

    def _get_session_budget(self, session_id: str | None) -> SessionBudget | None:
        """Return the budget tracker for a session (creates on first access).

        Evicts the oldest entry when the cap is reached — same DoS protection as
        _get_loop_detector.
        """
        if self._budget_config is None:
            return None
        key = session_id or "__default__"
        if key not in self._session_budgets:
            if len(self._session_budgets) >= _MAX_SESSION_STATE:
                self._session_budgets.pop(next(iter(self._session_budgets)))
            self._session_budgets[key] = SessionBudget(self._budget_config)
        return self._session_budgets[key]

    # --- Public API ---

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
            client.buffer_span(handoff)

            # Sub-agent wraps its client with parent_span_id=handoff.span_id
            billing_mcp = client.wrap(mcp, server_name="crm-mcp",
                                      agent_name="billing-agent",
                                      session_id=session_id,
                                      trace_id=trace_id,
                                      parent_span_id=handoff.span_id)
        """
        effective_redact = redact_payloads if redact_payloads is not None else self._redact_payloads
        effective_project = project_id if project_id is not None else self._project_id
        proxy = MCPClientProxy(
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
        # Kick off async remote config fetch (fire-and-forget, never blocks wrap())
        if agent_name:
            try:
                asyncio.create_task(self._apply_remote_config(agent_name, effective_project))
            except RuntimeError:
                pass  # no event loop (e.g. sync context) — constructor defaults apply
        return proxy

    def wrap_llm(
        self,
        llm_client: object,
        agent_name: str | None = None,
        session_id: str | None = None,
        trace_id: str | None = None,
    ) -> object:
        """Wrap an LLM SDK client to auto-trace tool calls from responses.

        Auto-detects the SDK (OpenAI, Anthropic, Gemini) and returns a
        transparent proxy that intercepts generation calls. Every tool_use
        block in the LLM response becomes a ToolCallSpan automatically.

        Args:
            llm_client: An OpenAI, Anthropic, or Gemini client/model object.
            agent_name: Name of the agent using this LLM.
            session_id: Groups all calls in one agent run/conversation.
            trace_id: Groups all spans across a multi-agent task.

        Returns:
            A wrapped client that auto-traces. If the SDK is not recognized,
            returns the original client unchanged (fail-open).

        Usage::

            # OpenAI
            from openai import OpenAI
            client = ls.wrap_llm(OpenAI(), agent_name="my-agent")
            response = client.chat.completions.create(model="gpt-4o", tools=[...], ...)

            # Anthropic
            from anthropic import Anthropic
            client = ls.wrap_llm(Anthropic(), agent_name="my-agent")
            response = client.messages.create(model="claude-sonnet-4-6", tools=[...], ...)

            # Gemini
            import google.generativeai as genai
            model = ls.wrap_llm(genai.GenerativeModel("gemini-2.5-flash"), agent_name="analyst")
            response = model.generate_content(prompt, tools=[...])
        """
        from langsight.sdk.llm_wrapper import wrap_llm

        return wrap_llm(
            client=llm_client,
            langsight=self,
            agent_name=agent_name,
            session_id=session_id,
            trace_id=trace_id,
        )

    def buffer_span(self, span: ToolCallSpan) -> None:
        """Synchronously buffer a span. Thread-safe, no event loop required.

        Use this from synchronous callbacks (LangChain on_tool_end etc.)
        where no running event loop is guaranteed. The flush loop or
        atexit handler will deliver buffered spans.
        """
        with self._lock:
            self._buffer.append(span)
            if len(self._buffer) > self._max_buffer_size:
                dropped = len(self._buffer) - self._max_buffer_size
                self._buffer = self._buffer[dropped:]
                logger.warning("sdk.buffer_overflow", dropped=dropped, max=self._max_buffer_size)

    async def send_span(self, span: ToolCallSpan) -> None:
        """Async wrapper around buffer_span for backward compatibility.

        .. deprecated:: 0.4.1
            Use :meth:`buffer_span` instead. ``send_span`` is kept for backward
            compatibility with existing integrations and tests.
        """
        self.buffer_span(span)

    async def send_spans(self, spans: list[ToolCallSpan]) -> None:
        """Buffer multiple spans. Backward-compatible async wrapper."""
        for span in spans:
            self.buffer_span(span)

    async def flush(self) -> None:
        """Flush all buffered spans to the API. Safe to call at any time.

        If the HTTP send fails (e.g. event loop is closing), spans are returned
        to the buffer so the atexit handler can deliver them.
        """
        with self._lock:
            if not self._buffer:
                return
            batch, self._buffer = self._buffer, []
        ok = await self._post_spans(batch)
        if not ok:
            with self._lock:
                self._buffer = batch + self._buffer

    async def _fetch_prevention_config(
        self, agent_name: str, project_id: str | None
    ) -> dict[str, Any] | None:
        """Fetch prevention config from the API. Returns None on any failure (fail-open)."""
        try:
            from urllib.parse import quote

            http = await self._get_http()
            # safe='' ensures ALL special chars (including /) are percent-encoded
            safe_agent = quote(agent_name, safe="")
            url = f"{self._url}/api/agents/{safe_agent}/prevention-config"
            if project_id:
                url = f"{url}?project_id={quote(project_id, safe='')}"
            resp = await http.get(url)
            if resp.status_code == 200:
                return cast(dict[str, Any], resp.json())
        except Exception:  # noqa: BLE001
            pass  # offline or unreachable — constructor defaults remain active
        return None

    async def _apply_remote_config(self, agent_name: str, project_id: str | None) -> None:
        """Fetch and apply remote prevention config, overriding constructor defaults.

        Called as a fire-and-forget background task from wrap(). If the API is
        unreachable, constructor defaults remain active (fail-open).
        """
        config = await self._fetch_prevention_config(agent_name, project_id)
        if not config:
            return

        # Override loop config
        loop_enabled = config.get("loop_enabled")
        if loop_enabled is not None:
            if loop_enabled:
                self._loop_config = LoopDetectorConfig(
                    threshold=int(config.get("loop_threshold", 3)),
                    action=LoopAction(config.get("loop_action", "terminate")),
                )
            else:
                self._loop_config = None

        # Override budget config
        has_any_limit = any(
            config.get(k) is not None for k in ("max_steps", "max_cost_usd", "max_wall_time_s")
        )
        if has_any_limit:
            self._budget_config = BudgetConfig(
                max_steps=config.get("max_steps"),
                max_cost_usd=config.get("max_cost_usd"),
                max_wall_time_s=config.get("max_wall_time_s"),
                soft_alert_fraction=float(config.get("budget_soft_alert", 0.80)),
            )
        elif "max_steps" in config and config["max_steps"] is None:
            # Explicitly cleared in dashboard
            self._budget_config = None

        # Override circuit breaker config
        cb_enabled = config.get("cb_enabled")
        if cb_enabled is not None:
            if cb_enabled:
                self._cb_default_config = CircuitBreakerConfig(
                    failure_threshold=int(config.get("cb_failure_threshold", 5)),
                    cooldown_seconds=float(config.get("cb_cooldown_seconds", 60.0)),
                    half_open_max_calls=int(config.get("cb_half_open_max_calls", 2)),
                )
            else:
                self._cb_default_config = None

        logger.debug(
            "sdk.remote_config_applied",
            agent=agent_name,
            loop=self._loop_config is not None,
            budget=self._budget_config is not None,
            circuit_breaker=self._cb_default_config is not None,
        )

    def _flush_on_exit(self) -> None:
        """Synchronous atexit handler — flushes buffered spans when the program exits.

        Uses a synchronous HTTP client to deliver spans, avoiding asyncio
        entirely. This works reliably even during interpreter shutdown when
        ``asyncio.run()`` and ``create_task()`` would fail.
        """
        with self._lock:
            if not self._buffer:
                return
            batch, self._buffer = self._buffer, []
        try:
            payload = [s.model_dump(mode="json") for s in batch]
            headers: dict[str, str] = {"Content-Type": "application/json"}
            if self._api_key:
                headers["X-API-Key"] = self._api_key
            # Use synchronous httpx — no event loop needed
            with httpx.Client(timeout=5.0) as sync_http:
                resp = sync_http.post(
                    f"{self._url}/api/traces/spans",
                    json=payload,
                    headers=headers,
                )
                if resp.status_code < 300:
                    logger.debug("sdk.atexit_flush_ok", count=len(batch))
                else:
                    logger.warning("sdk.atexit_flush_failed", status=resp.status_code)
        except Exception as exc:  # noqa: BLE001
            logger.warning("sdk.atexit_flush_error", count=len(batch), error=str(exc))

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

    async def __aenter__(self) -> LangSightClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

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

            url = f"{url}?project_id={quote(project_id, safe='')}"
        payload: dict[str, object] = {"tools": tools}
        try:
            http = await self._get_http()
            response = await http.post(url, json=payload)
            response.raise_for_status()
            logger.debug("sdk.tool_schemas_sent", server=server_name, count=len(tools))
        except Exception as exc:  # noqa: BLE001
            logger.debug("sdk.tool_schemas_failed", server=server_name, error=str(exc))

    # --- Internal ---

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

    async def _post_spans(self, spans: list[ToolCallSpan]) -> bool:
        """Internal: POST a batch of spans. Returns True on success, False on failure. Never raises."""
        payload = [s.model_dump(mode="json") for s in spans]
        try:
            http = await self._get_http()
            response = await http.post(
                f"{self._url}{_SPANS_ENDPOINT}",
                json=payload,
            )
            response.raise_for_status()
            logger.debug("sdk.spans_sent", count=len(spans))
            return True
        except Exception as exc:  # noqa: BLE001
            # Fail-open: log but never raise — monitoring must not break the app
            logger.warning("sdk.send_failed", error=str(exc), count=len(spans))
            return False


class MCPClientProxy:
    """Transparent proxy around an MCP client that records ToolCallSpans.

    Forwards every attribute access to the wrapped client. Only `call_tool`
    is intercepted to record observability data and enforce prevention rules.
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
                tools_payload.append(
                    {
                        "name": getattr(t, "name", str(t)),
                        "description": getattr(t, "description", "") or "",
                        "input_schema": getattr(t, "inputSchema", None)
                        or getattr(t, "input_schema", None)
                        or {},
                    }
                )
            record_coro = langsight.record_tool_schemas(server_name, tools_payload, project_id)
            try:
                asyncio.create_task(record_coro)
            except RuntimeError:
                record_coro.close()
        except Exception as exc:  # noqa: BLE001
            logger.debug("sdk.list_tools_capture_failed", server=server_name, error=str(exc))

        return result

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> object:
        """Call a tool and record a ToolCallSpan regardless of outcome.

        v0.3: Pre-call prevention checks may block the call and raise:
        - CircuitBreakerOpenError: server is disabled by circuit breaker
        - LoopDetectedError: agent loop pattern detected (if action=terminate)
        - BudgetExceededError: session budget limit exceeded

        Prevented calls are recorded as spans with status=PREVENTED.
        """
        client = object.__getattribute__(self, "_client")
        langsight: LangSightClient = object.__getattribute__(self, "_langsight")
        server_name = object.__getattribute__(self, "_server_name")
        agent_name = object.__getattribute__(self, "_agent_name")
        session_id = object.__getattribute__(self, "_session_id")
        trace_id = object.__getattribute__(self, "_trace_id")
        parent_span_id = object.__getattribute__(self, "_parent_span_id")
        redact = object.__getattribute__(self, "_redact_payloads")
        project_id = object.__getattribute__(self, "_project_id")

        # Auto-link: if no explicit parent, check if wrap_llm() registered this tool
        if not parent_span_id:
            from langsight.sdk.context import claim_pending_tool

            ctx = claim_pending_tool(name)
            if ctx is not None:
                parent_span_id = ctx.span_id
                # Inherit agent_name so the dashboard can draw agent→server edges
                if not agent_name and ctx.agent_name:
                    agent_name = ctx.agent_name

        started_at = datetime.now(UTC)

        # --- Pre-call prevention checks ---
        prevented = _check_prevention(
            langsight,
            server_name,
            session_id,
            name,
            arguments,
            started_at,
            trace_id,
            agent_name,
            parent_span_id,
            redact,
            project_id,
        )
        if prevented is not None:
            span, exc = prevented
            # Send the prevented span fire-and-forget — never let delivery failure
            # mask the prevention exception that the caller needs to handle.
            try:
                langsight.buffer_span(span)
            except Exception:  # noqa: BLE001
                pass
            raise exc

        # --- Actual tool call ---
        status = ToolCallStatus.SUCCESS
        error: str | None = None
        output_result: str | None = None

        try:
            result = await client.call_tool(name, arguments)
            # Detect silent MCP errors — MCP SDK returns errors as JSON-RPC
            # responses (isError=True) instead of raising exceptions.
            if getattr(result, "isError", False):
                status = ToolCallStatus.ERROR
                error = str(getattr(result, "content", "MCP error response"))
                logger.warning(
                    "sdk.mcp_silent_error",
                    server=server_name,
                    tool=name,
                    error=error,
                )
            else:
                # Inspect content text for semantic errors when isError=False.
                # MCP servers sometimes return error messages as valid responses.
                content_error = _detect_content_error(result)
                if content_error:
                    status = ToolCallStatus.ERROR
                    error = content_error
                    logger.warning(
                        "sdk.mcp_content_error",
                        server=server_name,
                        tool=name,
                        error=error,
                    )
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
            # Post-call prevention updates (fail-open)
            _post_call_update(
                langsight,
                server_name,
                session_id,
                name,
                arguments,
                span,
                status,
            )
            langsight.buffer_span(span)


# ---------------------------------------------------------------------------
# MCP content error detection
# ---------------------------------------------------------------------------

# Prefixes that indicate a semantic error inside a successful MCP response.
# These are common patterns returned by MCP servers that set isError=False
# but include an error message in the content (e.g. DB errors, not-found, etc.)
_CONTENT_ERROR_PREFIXES = (
    "Error:", "ERROR:", "Exception:", "Traceback (most recent",
    "[ERROR]", "[Error]", "error:", "Failed:", "FAILED:",
)


def _detect_content_error(result: object) -> str | None:
    """Return an error string if the MCP result content looks like an error.

    Only called when ``result.isError == False``. Inspects the first text
    block in ``result.content`` for known error prefixes. Returns ``None``
    if the content looks normal — does NOT flag empty content as an error
    (some tools legitimately return empty results).
    """
    try:
        content = getattr(result, "content", None)
        if not content:
            return None
        # Take the first text block
        first = content[0] if isinstance(content, (list, tuple)) else content
        text: str | None = None
        if hasattr(first, "text"):
            text = first.text
        elif isinstance(first, str):
            text = first
        if text and any(text.lstrip().startswith(p) for p in _CONTENT_ERROR_PREFIXES):
            # Truncate long error messages
            msg = text.strip()[:200]
            return f"ContentError: {msg}"
    except Exception:  # noqa: BLE001
        pass  # fail-open — detection must never break tool calls
    return None


# ---------------------------------------------------------------------------
# Prevention helper functions (module-level to keep MCPClientProxy lean)
# ---------------------------------------------------------------------------


def _check_prevention(
    langsight: LangSightClient,
    server_name: str,
    session_id: str | None,
    tool_name: str,
    arguments: dict[str, Any] | None,
    started_at: datetime,
    trace_id: str | None,
    agent_name: str | None,
    parent_span_id: str | None,
    redact: bool,
    project_id: str | None,
) -> tuple[ToolCallSpan, Exception] | None:
    """Run pre-call prevention checks. Returns (prevented_span, exception) or None."""

    def _make_prevented_span(error_msg: str) -> ToolCallSpan:
        return ToolCallSpan(
            server_name=server_name,
            tool_name=tool_name,
            started_at=started_at,
            ended_at=started_at,  # zero-duration — call never happened
            latency_ms=0.0,
            status=ToolCallStatus.PREVENTED,
            error=error_msg,
            trace_id=trace_id,
            agent_name=agent_name,
            session_id=session_id,
            parent_span_id=parent_span_id,
            span_type="tool_call",
            input_args=None if redact else arguments,
            project_id=project_id,
        )

    # 1. Circuit breaker
    cb = langsight._get_circuit_breaker(server_name)
    if cb is not None and not cb.should_allow():
        error_msg = (
            f"circuit_breaker_open: {server_name} disabled after "
            f"{cb.consecutive_failures} consecutive failures"
        )
        return (
            _make_prevented_span(error_msg),
            CircuitBreakerOpenError(server_name, cb.cooldown_remaining_s),
        )

    # 2. Loop detection
    loop_det = langsight._get_loop_detector(session_id)
    if loop_det is not None:
        detection = loop_det.check_pre_call(tool_name, arguments)
        if detection is not None:
            error_msg = (
                f"loop_detected: {detection.pattern} — "
                f"{tool_name} repeated {detection.loop_count} times"
            )
            if langsight._loop_config and langsight._loop_config.action == LoopAction.TERMINATE:
                return (
                    _make_prevented_span(error_msg),
                    LoopDetectedError(
                        tool_name=detection.tool_name,
                        loop_count=detection.loop_count,
                        args_hash=detection.args_hash,
                        pattern=detection.pattern,
                        session_id=session_id,
                    ),
                )
            # action=warn: log but don't block
            logger.warning(
                "sdk.loop_detected_warn",
                tool=tool_name,
                pattern=detection.pattern,
                loop_count=detection.loop_count,
                session_id=session_id,
            )

    # 3. Budget guardrails
    budget = langsight._get_session_budget(session_id)
    if budget is not None:
        violation = budget.check_pre_call()
        if violation is not None:
            error_msg = (
                f"budget_exceeded: {violation.limit_type} limit is "
                f"{violation.limit_value}, actual is {violation.actual_value}"
            )
            return (
                _make_prevented_span(error_msg),
                BudgetExceededError(
                    limit_type=violation.limit_type,
                    limit_value=violation.limit_value,
                    actual_value=violation.actual_value,
                    session_id=session_id,
                ),
            )
        # Check soft thresholds (log warnings)
        for warning in budget.check_soft_thresholds():
            logger.warning(
                "sdk.budget_warning",
                limit_type=warning.limit_type,
                threshold_pct=warning.threshold_pct,
                current=warning.current_value,
                limit=warning.limit_value,
                session_id=session_id,
            )

    return None


def _post_call_update(
    langsight: LangSightClient,
    server_name: str,
    session_id: str | None,
    tool_name: str,
    arguments: dict[str, Any] | None,
    span: ToolCallSpan,
    status: ToolCallStatus,
) -> None:
    """Post-call: update circuit breaker, loop detector, and budget state."""
    # Circuit breaker
    cb = langsight._get_circuit_breaker(server_name)
    if cb is not None:
        if status == ToolCallStatus.SUCCESS:
            cb.record_success()
        else:
            cb.record_failure()

    # Loop detector
    loop_det = langsight._get_loop_detector(session_id)
    if loop_det is not None:
        loop_det.record_call(tool_name, arguments, status.value, span.error)

    # Budget: increment step count and add cost if available
    budget = langsight._get_session_budget(session_id)
    if budget is not None:
        cost = 0.0
        if span.input_tokens is not None and span.output_tokens is not None and span.model_id:
            pricing = langsight._pricing_table.get(span.model_id)
            if pricing:
                input_price, output_price = pricing
                cost = (
                    span.input_tokens / 1_000_000 * input_price
                    + span.output_tokens / 1_000_000 * output_price
                )
        budget.record_step_and_cost(cost)
