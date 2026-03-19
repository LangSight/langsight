"""Auto-seed demo data on first startup.

Creates a "Demo Project" with sample agent sessions so the dashboard
has data to explore immediately after `docker compose up`. Only runs
when no sessions exist yet (detected via get_agent_sessions).

Skipped silently when:
- Sessions already exist (re-start after first run)
- Storage backend doesn't support span ingestion (postgres-only mode)
- LANGSIGHT_SKIP_DEMO_SEED=1 is set
"""

from __future__ import annotations

import os
import random
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

logger = structlog.get_logger()

# ── Demo topology ─────────────────────────────────────────────────────────────

_AGENTS = ["support-agent", "billing-agent", "data-analyst", "orchestrator"]

_SERVERS: dict[str, list[str]] = {
    "postgres-mcp": ["query", "list_tables", "describe_table", "get_row_count"],
    "jira-mcp": ["get_issue", "create_issue", "search_issues"],
    "slack-mcp": ["send_message", "list_channels", "get_thread"],
    "s3-mcp": ["list_objects", "read_object", "put_object"],
    "github-mcp": ["get_pr", "list_commits", "create_comment"],
}

_AGENT_SERVERS: dict[str, list[str]] = {
    "orchestrator": ["postgres-mcp", "jira-mcp", "slack-mcp"],
    "support-agent": ["postgres-mcp", "jira-mcp", "slack-mcp"],
    "billing-agent": ["postgres-mcp", "s3-mcp"],
    "data-analyst": ["postgres-mcp", "s3-mcp", "github-mcp"],
}

_NUM_SESSIONS = 25
_MAX_CALLS = 8


# ── Span generation ──────────────────────────────────────────────────────────

def _generate_session(project_id: str) -> list[dict[str, Any]]:
    """Generate one realistic agent session."""
    agent = random.choice(_AGENTS)
    servers = _AGENT_SERVERS[agent]
    session_id = f"demo-{uuid.uuid4().hex[:8]}"
    trace_id = f"trace-{uuid.uuid4().hex[:8]}"
    base_time = datetime.now(UTC) - timedelta(hours=random.randint(1, 48))

    spans: list[dict[str, Any]] = []
    elapsed = 0.0
    num_calls = random.randint(3, _MAX_CALLS)

    has_handoff = agent == "orchestrator" and random.random() < 0.4
    handoff_id: str | None = None
    sub_agent: str | None = None

    for i in range(num_calls):
        if has_handoff and i == num_calls // 2:
            sub_agent = random.choice(["billing-agent", "support-agent"])
            handoff_id = str(uuid.uuid4())
            lat = random.uniform(1, 5)
            spans.append({
                "span_id": handoff_id,
                "span_type": "handoff",
                "trace_id": trace_id,
                "session_id": session_id,
                "server_name": agent,
                "tool_name": f"-> {sub_agent}",
                "started_at": (base_time + timedelta(milliseconds=elapsed)).isoformat(),
                "ended_at": (base_time + timedelta(milliseconds=elapsed + lat)).isoformat(),
                "latency_ms": round(lat, 2),
                "status": "success",
                "agent_name": agent,
                "project_id": project_id,
            })
            elapsed += lat
            continue

        cur_agent = sub_agent if (handoff_id and sub_agent and i > num_calls // 2) else agent
        cur_servers = _AGENT_SERVERS.get(cur_agent, servers)
        server = random.choice(cur_servers)
        tool = random.choice(_SERVERS[server])

        lat = max(5.0, random.gauss({"postgres-mcp": 35, "s3-mcp": 120}.get(server, 80), 25))
        roll = random.random()
        if roll < 0.02:
            status, error, lat = "timeout", f"Tool '{tool}' timed out", 5000.0
        elif roll < 0.07:
            status = "error"
            error = random.choice([
                f"Connection refused: {server}",
                f"Permission denied on {tool}",
                "Invalid input: missing required field 'id'",
            ])
        else:
            status, error = "success", None

        span: dict[str, Any] = {
            "span_id": str(uuid.uuid4()),
            "span_type": "tool_call",
            "trace_id": trace_id,
            "session_id": session_id,
            "server_name": server,
            "tool_name": tool,
            "started_at": (base_time + timedelta(milliseconds=elapsed)).isoformat(),
            "ended_at": (base_time + timedelta(milliseconds=elapsed + lat)).isoformat(),
            "latency_ms": round(lat, 2),
            "status": status,
            "error": error,
            "agent_name": cur_agent,
            "project_id": project_id,
        }
        if handoff_id and cur_agent == sub_agent:
            span["parent_span_id"] = handoff_id
        spans.append(span)
        elapsed += lat + random.uniform(5, 50)

    return spans


# ── Public API ────────────────────────────────────────────────────────────────


async def seed_demo_data(storage: Any, project_id: str) -> None:
    """Seed demo sessions into the storage backend. Only runs on first startup."""
    if os.environ.get("LANGSIGHT_SKIP_DEMO_SEED") == "1":
        logger.debug("demo_seed.skipped", reason="LANGSIGHT_SKIP_DEMO_SEED=1")
        return

    # Check if sessions already exist — skip if so
    if hasattr(storage, "get_agent_sessions"):
        try:
            existing = await storage.get_agent_sessions(hours=168, limit=1)
            if existing:
                logger.debug("demo_seed.skipped", reason="sessions already exist")
                return
        except Exception:  # noqa: BLE001
            pass

    if not hasattr(storage, "save_spans"):
        logger.debug("demo_seed.skipped", reason="storage lacks save_spans")
        return

    random.seed(42)  # deterministic for consistent demo experience
    total_spans = 0
    for _ in range(_NUM_SESSIONS):
        spans = _generate_session(project_id)
        try:
            await storage.save_spans(spans)
            total_spans += len(spans)
        except Exception as exc:  # noqa: BLE001
            logger.warning("demo_seed.save_error", error=str(exc))
            return

    logger.info("demo_seed.complete", sessions=_NUM_SESSIONS, spans=total_spans, project_id=project_id)
