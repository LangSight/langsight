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

from typing import Any

import structlog
from fastapi import APIRouter, Request
from fastapi import status as http_status

from langsight.api.metrics import SPANS_INGESTED
from langsight.api.rate_limit import limiter
from langsight.sdk.models import ToolCallSpan, ToolCallStatus

logger = structlog.get_logger()

router = APIRouter(prefix="/traces", tags=["traces"])

# In-memory caches to avoid DB lookups on every span batch.
# Reset on process restart — safe because upsert is idempotent.
_seen_agents: set[str] = set()
_seen_servers: set[str] = set()


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

    # Auto-tag session health after ingestion (fail-open)
    if storage is not None and hasattr(storage, "save_session_health_tag"):
        from langsight.tagging.engine import tag_from_spans as _tag

        # Compute health tags for each unique session in this batch
        session_spans: dict[str, list[dict]] = {}
        for span in spans:
            if span.session_id:
                session_spans.setdefault(span.session_id, []).append(
                    {
                        "status": span.status,
                        "error": span.error or "",
                        "tool_name": span.tool_name,
                    }
                )
        for session_id, batch_spans in session_spans.items():
            try:
                tag = _tag(batch_spans)
                await storage.save_session_health_tag(session_id, str(tag))
            except Exception:  # noqa: BLE001
                pass  # fail-open — tagging must never block ingestion

    # Auto-register unseen agents and servers (fire-and-forget, fail-open)
    # The _seen cache is per-process — always upsert if we haven't seen it this
    # process lifetime. The storage layer uses ON CONFLICT DO UPDATE so repeated
    # calls are cheap and self-healing after volume wipes.
    if storage is not None and hasattr(storage, "upsert_agent_metadata"):
        project_id = _extract_project_id(spans)
        # Collect all unique agents from this batch first
        batch_agents = {span.agent_name for span in spans if span.agent_name}
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
            if span.server_name and span.server_name not in _seen_servers:
                _seen_servers.add(span.server_name)
                try:
                    await storage.upsert_server_metadata(
                        server_name=span.server_name,
                        description="Auto-discovered from traces",
                        project_id=project_id,
                    )
                    logger.debug("trace.server_auto_registered", server=span.server_name)
                except Exception:  # noqa: BLE001
                    pass

    # Update metrics + broadcast to SSE clients
    SPANS_INGESTED.inc(len(spans))
    broadcaster = getattr(request.app.state, "broadcaster", None)
    if broadcaster:
        for span in spans:
            broadcaster.publish(
                "span:new",
                {
                    "session_id": span.session_id,
                    "agent_name": span.agent_name,
                    "server_name": span.server_name,
                    "tool_name": span.tool_name,
                    "status": span.status,
                    "latency_ms": span.latency_ms,
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
