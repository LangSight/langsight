"""
POST /api/traces/spans — span ingestion endpoint.

Accepts ToolCallSpan batches from the LangSight SDK (and any HTTP client).
Phase 2: logs spans with structlog for visibility.
Phase 3: stores in ClickHouse for reliability analysis and cost attribution.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter
from fastapi import status as http_status

from langsight.sdk.models import ToolCallSpan

logger = structlog.get_logger()

router = APIRouter(prefix="/traces", tags=["traces"])


@router.post(
    "/spans",
    status_code=http_status.HTTP_202_ACCEPTED,
    summary="Ingest tool call spans from the LangSight SDK",
    response_model=dict,
)
async def ingest_spans(spans: list[ToolCallSpan]) -> dict:
    """Accept a batch of ToolCallSpans from the SDK.

    Phase 2: spans are logged with structlog (visible in `langsight serve` output).
    Phase 3: stored in ClickHouse for reliability queries, cost attribution,
             and root cause investigation.

    Returns 202 Accepted immediately — ingestion is async.
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

    return {"accepted": len(spans)}
