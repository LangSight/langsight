"""
Trace ingestion endpoints.

POST /api/traces/spans  — LangSight SDK (ToolCallSpan JSON)
POST /api/traces/otlp   — Standard OpenTelemetry OTLP/JSON

Phase 2: spans are logged with structlog (visible in langsight serve output).
Phase 3: spans are stored in ClickHouse via the storage backend when available.

Rate limits (S.4):
  /spans: 200 requests/minute per IP — accommodates high-frequency SDK use
  /otlp:  60 requests/minute per IP  — OTEL collector batches; lower is fine
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

import structlog
from fastapi import APIRouter, Request
from fastapi import status as http_status

from langsight.api.metrics import SPANS_INGESTED
from langsight.api.rate_limit import limiter
from langsight.sdk.models import SESSION_ID_RE, ToolCallSpan, ToolCallStatus

logger = structlog.get_logger()

router = APIRouter(prefix="/traces", tags=["traces"])

# LRU caches to avoid DB lookups on every span batch.
# Bounded at 2000 entries each — prevents unbounded memory growth in
# long-running deployments with high agent/server cardinality.
# Reset on process restart — safe because upsert is idempotent.
_LRU_MAX = 2000


class _LRUSet:
    """A set with LRU eviction — evicts the oldest entry when full."""

    def __init__(self, maxsize: int) -> None:
        self._d: OrderedDict[str, None] = OrderedDict()
        self._max = maxsize

    def __contains__(self, key: str) -> bool:
        if key in self._d:
            self._d.move_to_end(key)
            return True
        return False

    def add(self, key: str) -> None:
        if key in self._d:
            self._d.move_to_end(key)
        else:
            if len(self._d) >= self._max:
                self._d.popitem(last=False)
            self._d[key] = None

    def discard(self, key: str) -> None:
        self._d.pop(key, None)


_seen_agents: _LRUSet = _LRUSet(_LRU_MAX)
_seen_servers: _LRUSet = _LRUSet(_LRU_MAX)
_alerted_sessions: _LRUSet = _LRUSet(_LRU_MAX)  # dedup: one alert per session

# ---------------------------------------------------------------------------
# Session health tagging — cumulative, priority-preserving
# ---------------------------------------------------------------------------
# Problem: spans arrive in multiple batches. Tagging each batch independently
# means a later all-success batch can overwrite an earlier "tool_failure" tag.
#
# Solution:
#   1. Accumulate ALL spans seen per session in a bounded LRU cache.
#   2. Retag from the full accumulated span list on every batch — so the tag
#      always reflects the worst outcome seen across the entire session lifetime.
#   3. On cache miss (restart / new process instance), read the existing tag
#      from storage and never downgrade it (priority-preserving DB upsert).
#
# This handles: multi-batch sessions, process restarts, multi-instance deploys.

# Lower number = more severe. Used to compare old vs new tag priority.
_TAG_PRIORITY: dict[str, int] = {
    "loop_detected": 0,
    "budget_exceeded": 1,
    "circuit_breaker_open": 2,
    "schema_drift": 3,
    "timeout": 4,
    "tool_failure": 5,
    "success_with_fallback": 6,
    "success": 7,
}

# Bounded LRU: session_id → accumulated span dicts (all batches, this process)
_SESSION_SPANS_MAX = 500  # max concurrent active sessions tracked in memory
_session_accumulated_spans: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()


def _accumulate(session_id: str, new_spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Append new_spans to the session's span accumulator, return all spans seen."""
    if session_id in _session_accumulated_spans:
        _session_accumulated_spans.move_to_end(session_id)
    else:
        if len(_session_accumulated_spans) >= _SESSION_SPANS_MAX:
            _session_accumulated_spans.popitem(last=False)  # evict LRU session
        _session_accumulated_spans[session_id] = []
    _session_accumulated_spans[session_id].extend(new_spans)
    return _session_accumulated_spans[session_id]


async def _resolve_tag(
    storage: Any,
    session_id: str,
    new_tag: str,
    cache_hit: bool,
) -> str:
    """Return the tag to persist, never downgrading from what's already stored.

    Fast path (cache_hit=True): compare against in-memory accumulated tag.
    Slow path (cache_hit=False, e.g. after restart): read from DB once and
    compare — prevents restarts from downgrading durable tags.
    """
    if not cache_hit and hasattr(storage, "get_session_health_tag"):
        try:
            existing = await storage.get_session_health_tag(session_id)
            if existing:
                existing_p = _TAG_PRIORITY.get(existing, 99)
                new_p = _TAG_PRIORITY.get(new_tag, 99)
                return new_tag if new_p < existing_p else existing
        except Exception:  # noqa: BLE001
            pass  # fail-open — use new_tag if DB read fails
    return new_tag


# ---------------------------------------------------------------------------
# SDK endpoint
# ---------------------------------------------------------------------------


@router.post(
    "/spans",
    status_code=http_status.HTTP_202_ACCEPTED,
    summary="Ingest tool call spans from the LangSight SDK",
    response_model=dict[str, Any],
)
@limiter.limit("2000/minute")
async def ingest_spans(spans: list[ToolCallSpan], request: Request) -> dict[str, Any]:
    """Accept a batch of ToolCallSpans from the SDK.

    Phase 2: logs each span with structlog.
    Phase 3: persists to ClickHouse when storage.mode=clickhouse.
    """
    # Validate session_id format at the API boundary — reject non-UUID values
    # so arbitrary test strings cannot pollute the dashboard.
    from fastapi import HTTPException

    for span in spans:
        if span.session_id and not SESSION_ID_RE.match(span.session_id):
            raise HTTPException(
                status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"session_id must be a UUID4 (hex or standard form), "
                    f"got {span.session_id!r}. "
                    "Use LangSightClient.wrap() / wrap_llm() to auto-generate a valid session_id."
                ),
            )

    for span in spans:
        logger.info(
            "trace.span_received",
            server=span.server_name,
            tool=span.tool_name,
            status=span.status,
            latency_ms=span.latency_ms,
            trace_id=span.trace_id,
            agent=span.agent_name,
            session=span.session_id,
        )

    # Server-side payload redaction — admin toggle overrides SDK setting
    storage = getattr(request.app.state, "storage", None)
    if storage is not None and hasattr(storage, "get_instance_settings"):
        try:
            settings = await storage.get_instance_settings()
            if settings.get("redact_payloads"):
                for span in spans:
                    span.input_args = None
                    span.output_result = None
                    span.llm_input = None
                    span.llm_output = None
        except Exception:  # noqa: BLE001
            pass  # fail-open — if settings fetch fails, don't block ingestion

    # Persist to ClickHouse if the backend supports it
    if storage is not None and hasattr(storage, "save_tool_call_spans"):
        await storage.save_tool_call_spans(spans)

    # Extract project_id once — used for both health tagging and agent registration
    _batch_project_id = _extract_project_id(spans)

    # Auto-tag session health after ingestion (fail-open)
    if storage is not None and hasattr(storage, "save_session_health_tag"):
        from langsight.tagging.engine import tag_from_spans as _tag

        # Group incoming spans by session
        batch_by_session: dict[str, list[dict[str, Any]]] = {}
        for span in spans:
            if span.session_id:
                batch_by_session.setdefault(span.session_id, []).append(
                    {
                        "status": span.status,
                        "error": span.error or "",
                        "tool_name": span.tool_name,
                        "span_type": span.span_type,
                    }
                )

        for session_id, new_batch in batch_by_session.items():
            try:
                # 1. Accumulate — merge new batch into the full span history for
                #    this session. Tagging from cumulative spans is always correct:
                #    no single batch can mask an error from an earlier batch.
                cache_hit = session_id in _session_accumulated_spans
                all_spans = _accumulate(session_id, new_batch)

                # 2. Tag from ALL spans seen so far (not just this batch)
                tag_str = str(_tag(all_spans))

                # 3. Priority-preserving DB upsert:
                #    - Fast path (cache_hit): cumulative spans already produce the
                #      correct worst-case tag — just save it.
                #    - Slow path (cache miss = restart / new instance): read the
                #      existing DB tag and never downgrade it.
                final_tag = await _resolve_tag(storage, session_id, tag_str, cache_hit)
                await storage.save_session_health_tag(
                    session_id, final_tag, project_id=_batch_project_id
                )

                # 4. Fire agent_failure alert for unhealthy sessions
                if (
                    final_tag not in ("success", "success_with_fallback")
                    and session_id not in _alerted_sessions
                ):
                    from langsight.api.alert_dispatcher import fire_alert as _fire_alert

                    agent_name = next(
                        (
                            s.agent_name
                            for s in spans
                            if s.session_id == session_id and s.agent_name
                        ),
                        "unknown",
                    )
                    failed = sum(
                        1
                        for s in spans
                        if s.session_id == session_id and s.status != ToolCallStatus.SUCCESS
                    )
                    fired = await _fire_alert(
                        storage=storage,
                        alert_type="agent_failure",
                        severity="critical",
                        server_name=agent_name,
                        title=f"Agent session failed: {final_tag.replace('_', ' ')}",
                        message=(
                            f"Session `{session_id}` ended with health tag **{final_tag}**. "
                            f"Agent: {agent_name}, failed tool calls: {failed}."
                        ),
                        session_id=session_id,
                        project_id=_batch_project_id or "",
                        config=getattr(request.app.state, "config", None),
                    )
                    # Only dedup when alert was accepted (toggle on).
                    # Skipped alerts stay eligible so toggling on mid-session fires.
                    if fired:
                        _alerted_sessions.add(session_id)
            except Exception:  # noqa: BLE001
                pass  # fail-open — tagging must never block ingestion

    # Auto-register unseen agents and servers (fire-and-forget, fail-open)
    # The _seen cache is per-process — always upsert if we haven't seen it this
    # process lifetime. The storage layer uses ON CONFLICT DO UPDATE so repeated
    # calls are cheap and self-healing after volume wipes.
    if storage is not None and hasattr(storage, "upsert_agent_metadata"):
        project_id = _batch_project_id
        # Collect all unique agents and servers from this batch first,
        # then register them. Previously the server registration was nested
        # inside the agent loop and used a stale `span` variable from the
        # outer ingestion loop — only the last span's server was ever seen.
        batch_agents = {span.agent_name for span in spans if span.agent_name}
        batch_servers = {span.server_name for span in spans if span.server_name}

        for agent in batch_agents:
            cache_key = f"{project_id}:{agent}"
            if cache_key in _seen_agents:
                continue
            _seen_agents.add(cache_key)
            try:
                await storage.upsert_agent_metadata(
                    agent_name=agent,
                    description="Auto-discovered from traces",
                    owner="",
                    tags=[],
                    status="active",
                    runbook_url="",
                    project_id=project_id,
                )
                logger.debug("trace.agent_auto_registered", agent=agent)
            except Exception:  # noqa: BLE001
                _seen_agents.discard(cache_key)  # retry next time

        if hasattr(storage, "upsert_server_metadata"):
            for server in batch_servers:
                cache_key = f"{project_id}:{server}"
                if cache_key in _seen_servers:
                    continue
                _seen_servers.add(cache_key)
                try:
                    await storage.upsert_server_metadata(
                        server_name=server,
                        description="Auto-discovered from traces",
                        project_id=project_id,
                    )
                    logger.debug("trace.server_auto_registered", server=server)
                except Exception:  # noqa: BLE001
                    _seen_servers.discard(cache_key)  # retry next time

    # Update metrics + broadcast to SSE clients
    SPANS_INGESTED.inc(len(spans))
    broadcaster = getattr(request.app.state, "broadcaster", None)
    if broadcaster:
        for span in spans:
            broadcaster.publish(
                "span:new",
                {
                    "project_id": span.project_id,  # required for SSE tenant isolation
                    "session_id": span.session_id,
                    "agent_name": span.agent_name,
                    "server_name": span.server_name,
                    "tool_name": span.tool_name,
                    "status": span.status,
                    "latency_ms": span.latency_ms,
                    "started_at": span.started_at.isoformat() if span.started_at else None,
                },
            )

    return {"accepted": len(spans)}


def _extract_project_id(spans: list[ToolCallSpan]) -> str | None:
    """Return the first non-empty project_id from the span batch."""
    for span in spans:
        if span.project_id:
            return span.project_id
    return None


# ---------------------------------------------------------------------------
# OTLP/JSON endpoint
# ---------------------------------------------------------------------------


@router.post(
    "/otlp",
    status_code=http_status.HTTP_202_ACCEPTED,
    summary="Ingest spans via OpenTelemetry OTLP/JSON",
    response_model=dict[str, Any],
)
@limiter.limit("60/minute")
async def ingest_otlp(request: Request) -> dict[str, Any]:
    """Accept OTLP/JSON trace data from any OpenTelemetry-instrumented framework.

    Works with CrewAI, LangChain, Pydantic AI, OpenAI Agents SDK, and any other
    framework that exports OTLP traces. Point your OTEL exporter here:

        OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:8000/api/traces/otlp

    Extracts MCP tool call spans by matching the span name pattern
    'mcp.{server}.{tool}' or looking for 'gen_ai.tool.name' attributes.

    Phase 2: logs extracted spans.
    Phase 3: persists to ClickHouse.
    """
    body = await request.json()
    spans = _extract_mcp_spans(body)

    for span in spans:
        logger.info(
            "trace.otlp_span",
            server=span.server_name,
            tool=span.tool_name,
            status=span.status,
            latency_ms=span.latency_ms,
        )

    storage = getattr(request.app.state, "storage", None)
    if storage is not None and hasattr(storage, "save_tool_call_spans"):
        await storage.save_tool_call_spans(spans)

    return {"accepted": len(spans)}


# ---------------------------------------------------------------------------
# OTLP parsing
# ---------------------------------------------------------------------------


def _extract_mcp_spans(otlp_body: dict[str, Any]) -> list[ToolCallSpan]:
    """Extract MCP tool call spans from an OTLP/JSON payload.

    Handles the OTLP ResourceSpans → ScopeSpans → Span structure.
    Recognises MCP spans by:
      1. Span name matches 'mcp.*' or 'gen_ai.tool.*'
      2. Attribute 'gen_ai.tool.name' present
      3. Attribute 'mcp.server.name' present
    """

    extracted: list[ToolCallSpan] = []

    for resource_spans in otlp_body.get("resourceSpans", []):
        for scope_spans in resource_spans.get("scopeSpans", []):
            for span in scope_spans.get("spans", []):
                tool_span = _parse_otlp_span(span)
                if tool_span:
                    extracted.append(tool_span)

    return extracted


def _parse_otlp_span(span: dict[str, Any]) -> ToolCallSpan | None:
    """Try to parse a single OTLP span as a ToolCallSpan. Returns None if not MCP or LLM.

    Recognises two span kinds:
      1. MCP tool call spans — identified by mcp.*/gen_ai.tool.* attributes or span name pattern
      2. LLM generation spans — identified by gen_ai.completion / gen_ai.prompt attributes
         These become span_type="agent" spans carrying llm_input / llm_output.
    """
    import json as _json
    from datetime import UTC, datetime

    name: str = span.get("name", "")
    attrs: dict[str, Any] = {}
    for a in span.get("attributes", []):
        key = a["key"]
        val = a.get("value", {})
        # Support stringValue, intValue, doubleValue, boolValue, arrayValue
        if "stringValue" in val:
            attrs[key] = val["stringValue"]
        elif "intValue" in val:
            attrs[key] = val["intValue"]
        elif "doubleValue" in val:
            attrs[key] = val["doubleValue"]
        elif "boolValue" in val:
            attrs[key] = val["boolValue"]
        else:
            attrs[key] = str(val)

    # ── LLM generation span detection (P5.3 + P7.2) ───────────────────────
    # GenAI semantic conventions: gen_ai.completion / gen_ai.prompt / gen_ai.usage.*
    llm_input: str | None = None
    llm_output: str | None = None
    is_llm_span = False
    input_tokens: int | None = None
    output_tokens: int | None = None

    # Extract token counts (P7.2)
    raw_input_tokens = (
        attrs.get("gen_ai.usage.input_tokens")
        or attrs.get("gen_ai.usage.prompt_tokens")
        or attrs.get("llm.token_count.prompt")
    )
    raw_output_tokens = (
        attrs.get("gen_ai.usage.output_tokens")
        or attrs.get("gen_ai.usage.completion_tokens")
        or attrs.get("llm.token_count.completion")
    )
    if raw_input_tokens is not None:
        try:
            input_tokens = int(raw_input_tokens)
        except (ValueError, TypeError):
            pass
    if raw_output_tokens is not None:
        try:
            output_tokens = int(raw_output_tokens)
        except (ValueError, TypeError):
            pass

    raw_prompt = attrs.get("gen_ai.prompt") or attrs.get("llm.prompts")
    raw_completion = attrs.get("gen_ai.completion") or attrs.get("llm.completions")

    if raw_prompt or raw_completion or input_tokens is not None or output_tokens is not None:
        is_llm_span = True
        if raw_prompt:
            # May already be a string or a JSON-encoded messages array
            llm_input = (
                raw_prompt if isinstance(raw_prompt, str) else _json.dumps(raw_prompt, default=str)
            )
        if raw_completion:
            llm_output = (
                raw_completion
                if isinstance(raw_completion, str)
                else _json.dumps(raw_completion, default=str)
            )

    # ── MCP / tool call span detection ────────────────────────────────────
    server_name = attrs.get("mcp.server.name") or attrs.get("gen_ai.system")
    tool_name = attrs.get("gen_ai.tool.name") or attrs.get("mcp.tool.name")

    # Fall back to parsing 'mcp.server_name.tool_name' span names
    if not tool_name and name.startswith("mcp."):
        parts = name.split(".", 2)
        if len(parts) == 3:
            server_name = server_name or parts[1]
            tool_name = parts[2]

    # LLM spans: synthesise server/tool from model info if not already set
    if is_llm_span and not tool_name:
        model = attrs.get("gen_ai.request.model") or attrs.get("llm.model_name") or "llm"
        server_name = server_name or attrs.get("gen_ai.system") or "llm"
        tool_name = f"generate/{model}"

    if not tool_name:
        return None

    server_name = server_name or "unknown"

    # ── Timing ────────────────────────────────────────────────────────────
    start_ns = int(span.get("startTimeUnixNano", 0))
    end_ns = int(span.get("endTimeUnixNano", 0))
    started_at = datetime.fromtimestamp(start_ns / 1e9, tz=UTC) if start_ns else datetime.now(UTC)
    ended_at = datetime.fromtimestamp(end_ns / 1e9, tz=UTC) if end_ns else datetime.now(UTC)
    latency_ms = (end_ns - start_ns) / 1e6 if start_ns and end_ns else 0.0

    # ── Status ────────────────────────────────────────────────────────────
    otlp_status = span.get("status", {}).get("code", 0)
    error_msg = span.get("status", {}).get("message")
    if otlp_status == 2:  # STATUS_CODE_ERROR
        status = ToolCallStatus.ERROR
    elif "timeout" in (error_msg or "").lower():
        status = ToolCallStatus.TIMEOUT
    else:
        status = ToolCallStatus.SUCCESS

    # Extract model_id from multiple possible attribute locations
    extracted_model_id = (
        attrs.get("gen_ai.request.model")
        or attrs.get("llm.model_name")
        or attrs.get("gen_ai.response.model")
    )

    return ToolCallSpan(
        server_name=server_name,
        tool_name=tool_name,
        started_at=started_at,
        ended_at=ended_at,
        latency_ms=round(latency_ms, 2),
        status=status,
        error=error_msg if status != ToolCallStatus.SUCCESS else None,
        trace_id=span.get("traceId"),
        session_id=attrs.get("session.id"),
        agent_name=attrs.get("gen_ai.agent.name"),
        span_type="agent" if is_llm_span else "tool_call",
        llm_input=llm_input,
        llm_output=llm_output,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        model_id=extracted_model_id or (model if is_llm_span and not tool_name else None),
    )
