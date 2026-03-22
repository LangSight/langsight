"""Auto-seed comprehensive demo data on first startup.

Populates every dashboard page so users see a realistic product experience
immediately after ``docker compose up``:

- **Sessions page**: 30 agent sessions with multi-agent handoffs, errors, payloads
- **Health page**: Health check history for 5 MCP servers (mix of UP/DEGRADED/DOWN)
- **Security page**: Populated via live security scan findings
- **Costs page**: Spans with model_id + token counts for cost attribution
- **Overview page**: Anomaly data (derived from reliability queries over seeded spans)
- **SLOs**: Two sample SLO definitions

All demo data is scoped to the Sample Project via ``project_id``.

Skipped when:
- Sessions already exist (restart after first run)
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

# Model IDs for cost attribution — matches seeded model_pricing
_MODELS = [
    ("claude-sonnet-4-6", 200, 800),
    ("claude-haiku-4-5", 50, 150),
    ("gpt-4o", 300, 1200),
]

_SAMPLE_INPUTS: dict[str, dict[str, Any]] = {
    "query": {"sql": "SELECT id, name, status FROM orders WHERE created_at > '2026-03-01' LIMIT 50"},
    "list_tables": {},
    "describe_table": {"table_name": "orders"},
    "get_row_count": {"table_name": "customers"},
    "get_issue": {"issue_key": "PROJ-142"},
    "create_issue": {"project": "PROJ", "summary": "Agent-detected anomaly in billing pipeline", "type": "Bug"},
    "search_issues": {"jql": "assignee = currentUser() AND status = Open"},
    "send_message": {"channel": "#ops-alerts", "text": "Billing pipeline recovered after 12m downtime"},
    "list_channels": {},
    "get_thread": {"channel": "#support", "ts": "1711234567.000100"},
    "list_objects": {"bucket": "agent-artifacts", "prefix": "reports/2026-03/"},
    "read_object": {"bucket": "agent-artifacts", "key": "reports/2026-03/daily-summary.json"},
    "put_object": {"bucket": "agent-artifacts", "key": "reports/2026-03/anomaly-report.json"},
    "get_pr": {"repo": "acme/backend", "number": 847},
    "list_commits": {"repo": "acme/backend", "branch": "main", "limit": 10},
    "create_comment": {"repo": "acme/backend", "issue": 847, "body": "Automated review: LGTM"},
}

_NUM_SESSIONS = 30
_MAX_CALLS = 10

# Health check profiles per server
_HealthRow = tuple[str, float | None, str | None]


def _h(status: str, latency: float | None = None, error: str | None = None) -> _HealthRow:
    return (status, latency, error)


_HEALTH_PROFILES: dict[str, list[_HealthRow]] = {
    # (status, latency_ms, error)
    "postgres-mcp": [_h("up", 31.0)] * 20 + [_h("up", 45.0)] * 5 + [_h("degraded", 1240.0)] * 2,
    "jira-mcp": [_h("up", 89.0)] * 15 + [_h("down", error="Connection refused")] * 3 + [_h("up", 95.0)] * 5,
    "slack-mcp": [_h("up", 72.0)] * 18 + [_h("degraded", 980.0)] * 4 + [_h("up", 65.0)] * 3,
    "s3-mcp": [_h("up", 120.0)] * 22 + [_h("up", 150.0)] * 3,
    "github-mcp": [_h("up", 55.0)] * 12 + [_h("down", error="Rate limited (403)")] * 2 + [_h("up", 60.0)] * 8,
}


# ── Span generation ──────────────────────────────────────────────────────────


def _generate_session(project_id: str, idx: int) -> list[dict[str, Any]]:
    """Generate one realistic agent session with payloads and cost data."""
    agents = list(_AGENT_SERVERS.keys())
    agent = agents[idx % len(agents)]
    servers = _AGENT_SERVERS[agent]
    session_id = f"demo-{uuid.uuid4().hex[:8]}"
    trace_id = f"trace-{uuid.uuid4().hex[:8]}"
    # Spread sessions across the last 48 hours
    base_time = datetime.now(UTC) - timedelta(hours=random.uniform(1, 48))

    spans: list[dict[str, Any]] = []
    elapsed = 0.0
    num_calls = random.randint(3, _MAX_CALLS)

    # Orchestrator gets handoffs ~50% of the time
    has_handoff = agent == "orchestrator" and random.random() < 0.5
    handoff_id: str | None = None
    sub_agent: str | None = None

    for i in range(num_calls):
        # Handoff span at the midpoint
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

        # Regular tool call
        cur_agent = sub_agent if (handoff_id and sub_agent and i > num_calls // 2) else agent
        cur_servers = _AGENT_SERVERS.get(cur_agent, servers)
        server = random.choice(cur_servers)
        tool = random.choice(_SERVERS[server])

        # Realistic latency per server type
        base_lat = {"postgres-mcp": 35, "s3-mcp": 120, "github-mcp": 55}.get(server, 80)
        lat = max(5.0, random.gauss(base_lat, base_lat * 0.4))

        # Error distribution: 2% timeout, 5% error, 93% success
        roll = random.random()
        if roll < 0.02:
            status, error, lat = "timeout", f"Tool '{tool}' timed out after 5000ms", 5000.0
        elif roll < 0.07:
            status = "error"
            error = random.choice([
                f"Connection refused: {server}",
                f"Permission denied on {tool}",
                "Invalid input: missing required field 'id'",
                "Rate limited by upstream API",
                f"Table 'orders' not found in {server}",
            ])
        else:
            status, error = "success", None

        # Cost data — every 3rd span has LLM token usage
        model_id, input_tokens, output_tokens = None, None, None
        if i % 3 == 0:
            model, avg_in, avg_out = random.choice(_MODELS)
            model_id = model
            input_tokens = int(random.gauss(avg_in, avg_in * 0.3))
            output_tokens = int(random.gauss(avg_out, avg_out * 0.3))

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
            "input_args": _SAMPLE_INPUTS.get(tool),
            "output_result": '{"rows": 42, "status": "ok"}' if status == "success" else None,
        }
        if model_id:
            span["model_id"] = model_id
            span["input_tokens"] = max(10, input_tokens or 0)
            span["output_tokens"] = max(10, output_tokens or 0)
        if handoff_id and cur_agent == sub_agent:
            span["parent_span_id"] = handoff_id

        spans.append(span)
        elapsed += lat + random.uniform(10, 80)

    return spans


# ── Health check generation ───────────────────────────────────────────────────


def _generate_health_results() -> list[dict[str, Any]]:
    """Generate 48 hours of health check history for all servers."""
    results = []
    now = datetime.now(UTC)

    for server_name, profiles in _HEALTH_PROFILES.items():
        tool_count = len(_SERVERS.get(server_name, []))
        schema_hash = uuid.uuid4().hex[:16]

        for i, (status, latency, error) in enumerate(profiles):
            checked_at = now - timedelta(hours=48) + timedelta(hours=i * (48 / len(profiles)))
            results.append({
                "server_name": server_name,
                "status": status,
                "latency_ms": latency,
                "tools_count": tool_count,
                "schema_hash": schema_hash,
                "checked_at": checked_at.isoformat(),
                "error": error,
            })

    return results


# ── SLO generation ────────────────────────────────────────────────────────────


def _generate_slos() -> list[dict[str, Any]]:
    """Generate sample SLO definitions."""
    return [
        {
            "id": uuid.uuid4().hex,
            "agent_name": "support-agent",
            "metric": "success_rate",
            "target": 95.0,
            "window_hours": 24,
        },
        {
            "id": uuid.uuid4().hex,
            "agent_name": "orchestrator",
            "metric": "success_rate",
            "target": 99.0,
            "window_hours": 24,
        },
        {
            "id": uuid.uuid4().hex,
            "agent_name": "billing-agent",
            "metric": "latency_p99",
            "target": 3000.0,
            "window_hours": 24,
        },
    ]


# ── v0.3 Prevention layer ─────────────────────────────────────────────────────


def _make_span(
    *,
    session_id: str,
    trace_id: str,
    server: str,
    tool: str,
    agent: str,
    project_id: str,
    base_time: datetime,
    elapsed_ms: float,
    latency_ms: float,
    status: str,
    error: str | None = None,
    parent_span_id: str | None = None,
    input_args: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a raw span dict (passed to ToolCallSpan constructor)."""
    start = base_time + timedelta(milliseconds=elapsed_ms)
    end = start + timedelta(milliseconds=latency_ms)
    return {
        "span_id": str(uuid.uuid4()),
        "span_type": "tool_call",
        "trace_id": trace_id,
        "session_id": session_id,
        "server_name": server,
        "tool_name": tool,
        "started_at": start.isoformat(),
        "ended_at": end.isoformat(),
        "latency_ms": latency_ms,
        "status": status,
        "error": error,
        "agent_name": agent,
        "project_id": project_id,
        "input_args": input_args or _SAMPLE_INPUTS.get(tool),
        "output_result": '{"status": "ok"}' if status == "success" else None,
        "parent_span_id": parent_span_id,
    }


def _generate_prevention_sessions(project_id: str) -> list[tuple[str, list[dict[str, Any]]]]:
    """Generate sessions that demonstrate all v0.3 Prevention Layer features.

    Returns list of (session_id, spans) tuples so health tags can be assigned.
    """
    now = datetime.now(UTC)
    sessions: list[tuple[str, list[dict[str, Any]]]] = []

    # ── Session 1: Loop detected (repetition pattern) ────────────────────────
    sess_id = f"demo-loop-{uuid.uuid4().hex[:8]}"
    trace_id = f"trace-{uuid.uuid4().hex[:8]}"
    base = now - timedelta(hours=2)
    spans: list[dict[str, Any]] = [
        # Two successful calls with identical args
        _make_span(session_id=sess_id, trace_id=trace_id, server="postgres-mcp", tool="query",
                   agent="support-agent", project_id=project_id, base_time=base,
                   elapsed_ms=0, latency_ms=35.0, status="success",
                   input_args={"sql": "SELECT id FROM orders WHERE status = 'pending'"}),
        _make_span(session_id=sess_id, trace_id=trace_id, server="postgres-mcp", tool="query",
                   agent="support-agent", project_id=project_id, base_time=base,
                   elapsed_ms=150, latency_ms=33.0, status="success",
                   input_args={"sql": "SELECT id FROM orders WHERE status = 'pending'"}),
        # Third identical call — PREVENTED (loop detected)
        {
            "span_id": str(uuid.uuid4()),
            "span_type": "tool_call",
            "trace_id": trace_id,
            "session_id": sess_id,
            "server_name": "postgres-mcp",
            "tool_name": "query",
            "started_at": (base + timedelta(milliseconds=300)).isoformat(),
            "ended_at": (base + timedelta(milliseconds=300)).isoformat(),
            "latency_ms": 0.0,
            "status": "prevented",
            "error": "loop_detected: repetition — query repeated 3 times (args_hash=a1b2c3d4)",
            "agent_name": "support-agent",
            "project_id": project_id,
            "input_args": {"sql": "SELECT id FROM orders WHERE status = 'pending'"},
            "output_result": None,
        },
    ]
    sessions.append((sess_id, spans))

    # ── Session 2: Budget exceeded (step limit) ──────────────────────────────
    sess_id = f"demo-budget-{uuid.uuid4().hex[:8]}"
    trace_id = f"trace-{uuid.uuid4().hex[:8]}"
    base = now - timedelta(hours=5)
    spans = [
        _make_span(session_id=sess_id, trace_id=trace_id, server="jira-mcp", tool="search_issues",
                   agent="orchestrator", project_id=project_id, base_time=base,
                   elapsed_ms=0, latency_ms=90.0, status="success"),
        _make_span(session_id=sess_id, trace_id=trace_id, server="postgres-mcp", tool="query",
                   agent="orchestrator", project_id=project_id, base_time=base,
                   elapsed_ms=200, latency_ms=42.0, status="success"),
        _make_span(session_id=sess_id, trace_id=trace_id, server="slack-mcp", tool="send_message",
                   agent="orchestrator", project_id=project_id, base_time=base,
                   elapsed_ms=400, latency_ms=65.0, status="success"),
        # 4th call hits max_steps=3 — PREVENTED
        {
            "span_id": str(uuid.uuid4()),
            "span_type": "tool_call",
            "trace_id": trace_id,
            "session_id": sess_id,
            "server_name": "jira-mcp",
            "tool_name": "create_issue",
            "started_at": (base + timedelta(milliseconds=600)).isoformat(),
            "ended_at": (base + timedelta(milliseconds=600)).isoformat(),
            "latency_ms": 0.0,
            "status": "prevented",
            "error": "budget_exceeded: max_steps limit is 3, actual is 4 — session terminated",
            "agent_name": "orchestrator",
            "project_id": project_id,
            "input_args": {"project": "PROJ", "summary": "Auto-generated ticket", "type": "Task"},
            "output_result": None,
        },
    ]
    sessions.append((sess_id, spans))

    # ── Session 3: Circuit breaker open ──────────────────────────────────────
    sess_id = f"demo-circuit-{uuid.uuid4().hex[:8]}"
    trace_id = f"trace-{uuid.uuid4().hex[:8]}"
    base = now - timedelta(hours=8)
    spans = [
        # Two real failures that open the circuit
        _make_span(session_id=sess_id, trace_id=trace_id, server="jira-mcp", tool="get_issue",
                   agent="billing-agent", project_id=project_id, base_time=base,
                   elapsed_ms=0, latency_ms=5000.0, status="error",
                   error="Connection refused: jira-mcp — upstream at jira.example.com returned 503"),
        _make_span(session_id=sess_id, trace_id=trace_id, server="jira-mcp", tool="get_issue",
                   agent="billing-agent", project_id=project_id, base_time=base,
                   elapsed_ms=5100, latency_ms=5000.0, status="error",
                   error="Connection refused: jira-mcp — upstream at jira.example.com returned 503"),
        # Third call — circuit is open, PREVENTED without hitting server
        {
            "span_id": str(uuid.uuid4()),
            "span_type": "tool_call",
            "trace_id": trace_id,
            "session_id": sess_id,
            "server_name": "jira-mcp",
            "tool_name": "get_issue",
            "started_at": (base + timedelta(milliseconds=10200)).isoformat(),
            "ended_at": (base + timedelta(milliseconds=10200)).isoformat(),
            "latency_ms": 0.0,
            "status": "prevented",
            "error": "circuit_breaker_open: jira-mcp disabled after 2 consecutive failures — cooldown 60s",
            "agent_name": "billing-agent",
            "project_id": project_id,
            "input_args": {"issue_key": "BILLING-99"},
            "output_result": None,
        },
    ]
    sessions.append((sess_id, spans))

    # ── Session 4: Success with fallback ─────────────────────────────────────
    sess_id = f"demo-fallback-{uuid.uuid4().hex[:8]}"
    trace_id = f"trace-{uuid.uuid4().hex[:8]}"
    base = now - timedelta(hours=12)
    spans = [
        # First attempt fails
        _make_span(session_id=sess_id, trace_id=trace_id, server="postgres-mcp", tool="query",
                   agent="data-analyst", project_id=project_id, base_time=base,
                   elapsed_ms=0, latency_ms=5000.0, status="timeout",
                   error="Tool 'query' timed out after 5000ms"),
        # Retry succeeds
        _make_span(session_id=sess_id, trace_id=trace_id, server="postgres-mcp", tool="query",
                   agent="data-analyst", project_id=project_id, base_time=base,
                   elapsed_ms=5200, latency_ms=38.0, status="success",
                   input_args={"sql": "SELECT count(*) FROM orders"}),
        _make_span(session_id=sess_id, trace_id=trace_id, server="s3-mcp", tool="put_object",
                   agent="data-analyst", project_id=project_id, base_time=base,
                   elapsed_ms=5400, latency_ms=125.0, status="success"),
    ]
    sessions.append((sess_id, spans))

    # ── Session 5: Schema drift ───────────────────────────────────────────────
    # This is represented as a health check result (not a session) — see health seeding.
    # But we also add a session where a tool call fails due to schema mismatch.
    sess_id = f"demo-schema-{uuid.uuid4().hex[:8]}"
    trace_id = f"trace-{uuid.uuid4().hex[:8]}"
    base = now - timedelta(hours=18)
    spans = [
        _make_span(session_id=sess_id, trace_id=trace_id, server="postgres-mcp", tool="list_tables",
                   agent="data-analyst", project_id=project_id, base_time=base,
                   elapsed_ms=0, latency_ms=28.0, status="success"),
        _make_span(session_id=sess_id, trace_id=trace_id, server="postgres-mcp", tool="query",
                   agent="data-analyst", project_id=project_id, base_time=base,
                   elapsed_ms=100, latency_ms=42.0, status="error",
                   error="schema drift detected: column 'billing_status' not found — tool schema changed"),
    ]
    sessions.append((sess_id, spans))

    # ── Session 6: Clean success ──────────────────────────────────────────────
    sess_id = f"demo-success-{uuid.uuid4().hex[:8]}"
    trace_id = f"trace-{uuid.uuid4().hex[:8]}"
    base = now - timedelta(hours=1)
    spans = [
        _make_span(session_id=sess_id, trace_id=trace_id, server="postgres-mcp", tool="query",
                   agent="support-agent", project_id=project_id, base_time=base,
                   elapsed_ms=0, latency_ms=31.0, status="success"),
        _make_span(session_id=sess_id, trace_id=trace_id, server="jira-mcp", tool="create_issue",
                   agent="support-agent", project_id=project_id, base_time=base,
                   elapsed_ms=150, latency_ms=88.0, status="success"),
        _make_span(session_id=sess_id, trace_id=trace_id, server="slack-mcp", tool="send_message",
                   agent="support-agent", project_id=project_id, base_time=base,
                   elapsed_ms=350, latency_ms=67.0, status="success"),
    ]
    sessions.append((sess_id, spans))

    return sessions


# ── Public API ────────────────────────────────────────────────────────────────


async def seed_demo_data(storage: Any, project_id: str) -> None:
    """Seed comprehensive demo data into the storage backend.

    Populates sessions, health, SLOs — everything the dashboard needs.
    Only runs on first startup (skips if sessions already exist).
    """
    if os.environ.get("LANGSIGHT_SKIP_DEMO_SEED") == "1":
        logger.debug("demo_seed.skipped", reason="LANGSIGHT_SKIP_DEMO_SEED=1")
        return

    # Check if sessions already exist — skip on restart
    if hasattr(storage, "get_agent_sessions"):
        try:
            existing = await storage.get_agent_sessions(hours=168, limit=1)
            if existing:
                logger.debug("demo_seed.skipped", reason="sessions already exist")
                return
        except Exception:  # noqa: BLE001
            pass

    random.seed(42)  # deterministic for consistent demo experience

    # ── 1. Agent sessions with spans ──────────────────────────────────────
    total_spans = 0
    if hasattr(storage, "save_tool_call_spans"):
        from langsight.sdk.models import ToolCallSpan

        for idx in range(_NUM_SESSIONS):
            raw_spans = _generate_session(project_id, idx)
            models = []
            for s in raw_spans:
                started = datetime.fromisoformat(s["started_at"])
                ended = datetime.fromisoformat(s["ended_at"])
                models.append(ToolCallSpan(
                    span_id=s["span_id"],
                    parent_span_id=s.get("parent_span_id"),
                    span_type=s.get("span_type", "tool_call"),
                    trace_id=s.get("trace_id"),
                    session_id=s.get("session_id"),
                    server_name=s["server_name"],
                    tool_name=s["tool_name"],
                    started_at=started,
                    ended_at=ended,
                    latency_ms=s["latency_ms"],
                    status=s["status"],
                    error=s.get("error"),
                    agent_name=s.get("agent_name"),
                    project_id=s.get("project_id"),
                    input_args=s.get("input_args"),
                    output_result=s.get("output_result"),
                    model_id=s.get("model_id"),
                    input_tokens=s.get("input_tokens"),
                    output_tokens=s.get("output_tokens"),
                ))
            try:
                await storage.save_tool_call_spans(models)
                total_spans += len(models)
            except Exception as exc:  # noqa: BLE001
                logger.warning("demo_seed.span_error", error=str(exc))
                break

        logger.info("demo_seed.spans", sessions=_NUM_SESSIONS, spans=total_spans)

    # ── 2. Health check history ───────────────────────────────────────────
    if hasattr(storage, "save_health_result"):
        from langsight.models import HealthCheckResult, ServerStatus

        health_results = _generate_health_results()
        health_count = 0
        for h in health_results:
            try:
                result = HealthCheckResult(
                    server_name=h["server_name"],
                    status=ServerStatus(h["status"]),
                    latency_ms=h["latency_ms"],
                    tools_count=h["tools_count"],
                    schema_hash=h["schema_hash"],
                    checked_at=datetime.fromisoformat(h["checked_at"]),
                    error=h["error"],
                )
                await storage.save_health_result(result)
                health_count += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("demo_seed.health_error", error=str(exc))
                break

        logger.info("demo_seed.health", count=health_count)

    # ── 3. Schema snapshots (for drift detection) ─────────────────────────
    if hasattr(storage, "save_schema_snapshot"):
        for server_name in _SERVERS:
            tool_count = len(_SERVERS[server_name])
            schema_hash = uuid.uuid4().hex[:16]
            try:
                await storage.save_schema_snapshot(server_name, schema_hash, tool_count)
            except Exception:  # noqa: BLE001
                pass

    # ── 4. SLO definitions ────────────────────────────────────────────────
    if hasattr(storage, "create_slo"):
        from langsight.models import AgentSLO, SLOMetric

        for slo_data in _generate_slos():
            try:
                slo = AgentSLO(
                    id=slo_data["id"],
                    agent_name=slo_data["agent_name"],
                    metric=SLOMetric(slo_data["metric"]),
                    target=slo_data["target"],
                    window_hours=slo_data["window_hours"],
                    created_at=datetime.now(UTC),
                )
                await storage.create_slo(slo)
            except Exception:  # noqa: BLE001
                pass

        logger.info("demo_seed.slos", count=len(_generate_slos()))

    # ── 5. Agent metadata (catalog) ────────────────────────────────────────
    if hasattr(storage, "upsert_agent_metadata"):
        _AGENT_METADATA = [
            {
                "agent_name": "orchestrator",
                "description": "Routes incoming customer support requests to specialist agents. Handles ticket classification, priority assignment, and multi-agent delegation.",
                "owner": "Platform Team",
                "tags": ["production", "customer-facing", "routing"],
                "status": "active",
                "runbook_url": "https://wiki.example.com/agents/orchestrator",
            },
            {
                "agent_name": "support-agent",
                "description": "Resolves customer issues by querying databases, creating Jira tickets, and sending Slack notifications. Handles escalation when issues are unresolvable.",
                "owner": "Support Engineering",
                "tags": ["production", "customer-facing", "tier-1"],
                "status": "active",
                "runbook_url": "https://wiki.example.com/agents/support-agent",
            },
            {
                "agent_name": "billing-agent",
                "description": "Processes billing inquiries, generates invoices, and reconciles payment records. Reads from S3 for archived data and Postgres for live accounts.",
                "owner": "Billing Team",
                "tags": ["production", "financial", "pii"],
                "status": "active",
                "runbook_url": "",
            },
            {
                "agent_name": "data-analyst",
                "description": "Performs ad-hoc data analysis across multiple sources. Queries Postgres, reads S3 objects, and pushes results to GitHub for review.",
                "owner": "Data Engineering",
                "tags": ["internal", "analytics", "experimental"],
                "status": "experimental",
                "runbook_url": "",
            },
        ]
        meta_count = 0
        for m in _AGENT_METADATA:
            try:
                await storage.upsert_agent_metadata(
                    agent_name=m["agent_name"],
                    description=m["description"],
                    owner=m["owner"],
                    tags=m["tags"],
                    status=m["status"],
                    runbook_url=m["runbook_url"],
                    project_id=project_id,
                )
                meta_count += 1
            except Exception:  # noqa: BLE001
                pass
        logger.info("demo_seed.agent_metadata", count=meta_count)

    # ── 6. v0.3 Prevention layer sessions ────────────────────────────────────
    if hasattr(storage, "save_tool_call_spans"):
        from langsight.sdk.models import ToolCallSpan
        from langsight.tagging.engine import tag_from_spans

        prevention_sessions = _generate_prevention_sessions(project_id)
        prevention_span_count = 0
        for sess_id, raw_spans in prevention_sessions:
            models = []
            for s in raw_spans:
                started = datetime.fromisoformat(s["started_at"])
                ended = datetime.fromisoformat(s["ended_at"])
                models.append(ToolCallSpan(
                    span_id=s["span_id"],
                    parent_span_id=s.get("parent_span_id"),
                    span_type=s.get("span_type", "tool_call"),
                    trace_id=s.get("trace_id"),
                    session_id=s.get("session_id"),
                    server_name=s["server_name"],
                    tool_name=s["tool_name"],
                    started_at=started,
                    ended_at=ended,
                    latency_ms=s["latency_ms"],
                    status=s["status"],
                    error=s.get("error"),
                    agent_name=s.get("agent_name"),
                    project_id=s.get("project_id"),
                    input_args=s.get("input_args"),
                    output_result=s.get("output_result"),
                ))
            try:
                await storage.save_tool_call_spans(models)
                prevention_span_count += len(models)
            except Exception as exc:  # noqa: BLE001
                logger.warning("demo_seed.prevention_span_error", error=str(exc))
                continue

            # Compute and store health tag for each prevention session
            if hasattr(storage, "save_session_health_tag"):
                span_dicts = [
                    {"tool_name": s["tool_name"], "status": s["status"], "error": s.get("error")}
                    for s in raw_spans
                ]
                try:
                    tag = tag_from_spans(span_dicts)
                    await storage.save_session_health_tag(sess_id, tag.value, None, project_id)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("demo_seed.health_tag_error", session=sess_id, error=str(exc))

        logger.info("demo_seed.prevention_layer", sessions=len(prevention_sessions), spans=prevention_span_count)

    # ── 7. Prevention config (dashboard-managed thresholds) ──────────────────
    if hasattr(storage, "upsert_prevention_config"):
        from langsight.models import PreventionConfig

        _PREVENTION_CONFIGS = [
            {
                "agent_name": "*",
                "loop_enabled": True,
                "loop_threshold": 3,
                "loop_action": "terminate",
                "max_steps": None,
                "max_cost_usd": None,
                "max_wall_time_s": None,
                "cb_enabled": True,
                "cb_failure_threshold": 5,
                "cb_cooldown_seconds": 60.0,
                "cb_half_open_max_calls": 2,
            },
            {
                "agent_name": "orchestrator",
                "loop_threshold": 3,
                "max_steps": 25,
                "max_cost_usd": 1.00,
            },
            {
                "agent_name": "support-agent",
                "loop_threshold": 5,
                "loop_action": "warn",
                "max_steps": 15,
                "max_cost_usd": 0.50,
            },
            {
                "agent_name": "billing-agent",
                "loop_threshold": 3,
                "max_steps": 10,
                "max_cost_usd": 0.25,
                "cb_failure_threshold": 3,
                "cb_cooldown_seconds": 30.0,
            },
            {
                "agent_name": "data-analyst",
                "loop_threshold": 3,
                "loop_action": "warn",
                "max_steps": 50,
                "max_cost_usd": 2.00,
            },
        ]
        pc_count = 0
        for pc_data in _PREVENTION_CONFIGS:
            defaults = {
                "loop_enabled": True, "loop_threshold": 3, "loop_action": "terminate",
                "max_steps": None, "max_cost_usd": None, "max_wall_time_s": None,
                "budget_soft_alert": 0.80, "cb_enabled": True,
                "cb_failure_threshold": 5, "cb_cooldown_seconds": 60.0, "cb_half_open_max_calls": 2,
            }
            defaults.update(pc_data)
            try:
                pc = PreventionConfig(
                    id=uuid.uuid4().hex,
                    project_id=project_id,
                    **defaults,  # type: ignore[arg-type]
                )
                await storage.upsert_prevention_config(pc)
                pc_count += 1
            except Exception:  # noqa: BLE001
                pass
        logger.info("demo_seed.prevention_configs", count=pc_count)

    logger.info(
        "demo_seed.complete",
        project_id=project_id,
        sessions=_NUM_SESSIONS + 6,  # 30 base + 6 prevention
        spans=total_spans,
        servers=len(_SERVERS),
    )
