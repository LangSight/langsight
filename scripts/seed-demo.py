#!/usr/bin/env python3
"""Seed the LangSight instance with realistic demo data.

Creates sample agent sessions, tool call spans, health results, and
security findings so the dashboard has data to display immediately
after `docker compose up`.

Usage:
    python scripts/seed-demo.py                          # defaults
    python scripts/seed-demo.py --url http://localhost:8000 --api-key ls_...
    LANGSIGHT_API_KEY=ls_... python scripts/seed-demo.py

Requires: httpx (included in langsight dev deps)
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import uuid
from datetime import UTC, datetime, timedelta

import httpx

# ── Config ────────────────────────────────────────────────────────────────────

API_URL = os.environ.get("LANGSIGHT_URL", "http://localhost:8000")
API_KEY = os.environ.get("LANGSIGHT_API_KEY", "")
PROJECT_ID = os.environ.get("LANGSIGHT_PROJECT_ID", "")

AGENTS = ["support-agent", "billing-agent", "data-analyst", "orchestrator"]
SERVERS = {
    "postgres-mcp": ["query", "list_tables", "describe_table", "get_row_count"],
    "jira-mcp": ["get_issue", "create_issue", "search_issues"],
    "slack-mcp": ["send_message", "list_channels", "get_thread"],
    "s3-mcp": ["list_objects", "read_object", "put_object"],
    "github-mcp": ["get_pr", "list_commits", "create_comment"],
}

# Which agents use which servers (realistic dependency graph)
AGENT_SERVERS = {
    "orchestrator": ["postgres-mcp", "jira-mcp", "slack-mcp"],
    "support-agent": ["postgres-mcp", "jira-mcp", "slack-mcp"],
    "billing-agent": ["postgres-mcp", "s3-mcp"],
    "data-analyst": ["postgres-mcp", "s3-mcp", "github-mcp"],
}

NUM_SESSIONS = 30
MAX_CALLS_PER_SESSION = 8


# ── Span generation ──────────────────────────────────────────────────────────


def generate_session(session_idx: int, project_id: str = "") -> list[dict]:
    """Generate a realistic agent session with tool call spans."""
    agent = random.choice(AGENTS)
    servers = AGENT_SERVERS[agent]
    session_id = uuid.uuid4().hex
    trace_id = uuid.uuid4().hex
    base_time = datetime.now(UTC) - timedelta(hours=random.randint(1, 20))

    spans = []
    num_calls = random.randint(2, MAX_CALLS_PER_SESSION)
    elapsed = 0.0

    # Occasionally create a multi-agent handoff
    has_handoff = agent == "orchestrator" and random.random() < 0.4
    handoff_span_id = None
    sub_agent = None

    for i in range(num_calls):
        # Pick server and tool
        if has_handoff and i == num_calls // 2:
            # Emit a handoff span
            sub_agent = random.choice(["billing-agent", "support-agent"])
            handoff_span_id = str(uuid.uuid4())
            latency = random.uniform(1, 5)
            spans.append({
                "span_id": handoff_span_id,
                "span_type": "handoff",
                "trace_id": trace_id,
                "session_id": session_id,
                "server_name": agent,
                "tool_name": f"-> {sub_agent}",
                "started_at": (base_time + timedelta(milliseconds=elapsed)).isoformat(),
                "ended_at": (base_time + timedelta(milliseconds=elapsed + latency)).isoformat(),
                "latency_ms": round(latency, 2),
                "status": "success",
                "agent_name": agent,
                "project_id": project_id,
            })
            elapsed += latency
            continue

        # Regular tool call
        current_agent = sub_agent if (has_handoff and handoff_span_id and i > num_calls // 2) else agent
        current_servers = AGENT_SERVERS.get(current_agent, servers)
        server = random.choice(current_servers)
        tools = SERVERS[server]
        tool = random.choice(tools)

        # Realistic latency distribution
        if server == "postgres-mcp":
            latency = random.gauss(35, 15)
        elif server == "s3-mcp":
            latency = random.gauss(120, 40)
        else:
            latency = random.gauss(80, 30)
        latency = max(5, latency)

        # Occasional failures (5% error rate, 2% timeout)
        roll = random.random()
        if roll < 0.02:
            status = "timeout"
            error = f"Tool '{tool}' timed out after 5000ms"
            latency = 5000
        elif roll < 0.07:
            status = "error"
            error = random.choice([
                f"Connection refused: {server}",
                f"Permission denied on {tool}",
                f"Invalid input: missing required field 'id'",
                f"Rate limited by upstream API",
            ])
        else:
            status = "success"
            error = None

        span = {
            "span_id": str(uuid.uuid4()),
            "span_type": "tool_call",
            "trace_id": trace_id,
            "session_id": session_id,
            "server_name": server,
            "tool_name": tool,
            "started_at": (base_time + timedelta(milliseconds=elapsed)).isoformat(),
            "ended_at": (base_time + timedelta(milliseconds=elapsed + latency)).isoformat(),
            "latency_ms": round(latency, 2),
            "status": status,
            "error": error,
            "agent_name": current_agent,
            "project_id": project_id,
        }
        if handoff_span_id and current_agent == sub_agent:
            span["parent_span_id"] = handoff_span_id

        spans.append(span)
        elapsed += latency + random.uniform(5, 50)

    return spans


# ── API calls ─────────────────────────────────────────────────────────────────


def send_spans(client: httpx.Client, spans: list[dict]) -> bool:
    """POST spans to the ingest endpoint."""
    try:
        resp = client.post("/api/traces/spans", json=spans)
        resp.raise_for_status()
        return True
    except httpx.HTTPError as e:
        print(f"  [err] Failed to send spans: {e}")
        return False


def check_api(client: httpx.Client) -> bool:
    """Verify the API is reachable."""
    try:
        resp = client.get("/api/status")
        resp.raise_for_status()
        data = resp.json()
        print(f"  API status: {data.get('status')} (v{data.get('version')})")
        return True
    except httpx.HTTPError as e:
        print(f"  [err] API not reachable: {e}")
        return False


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed LangSight with demo data")
    parser.add_argument("--url", default=API_URL, help="LangSight API URL")
    parser.add_argument("--api-key", default=API_KEY, help="API key")
    parser.add_argument("--project-id", default=PROJECT_ID, help="Project ID to scope spans to")
    parser.add_argument("--sessions", type=int, default=NUM_SESSIONS, help="Number of sessions")
    args = parser.parse_args()

    url = args.url.rstrip("/")
    api_key = args.api_key
    if not api_key:
        # Try reading from .env file
        env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.startswith("LANGSIGHT_API_KEYS="):
                        api_key = line.strip().split("=", 1)[1]
                        break

    if not api_key:
        print("[err] No API key found. Set LANGSIGHT_API_KEY env var or pass --api-key.")
        sys.exit(1)

    headers = {"X-API-Key": api_key}
    client = httpx.Client(base_url=url, headers=headers, timeout=10)

    print("──────────────────────────────────────────────────────")
    print("  LangSight Demo Seeder")
    print("──────────────────────────────────────────────────────")
    print(f"  API:      {url}")
    print(f"  Project:  {args.project_id or '(none — spans unscoped)'}")
    print(f"  Sessions: {args.sessions}")
    print("")

    if not check_api(client):
        print("\n  Is the API running? Try: docker compose up -d")
        sys.exit(1)

    total_spans = 0
    ok_sessions = 0

    for i in range(args.sessions):
        spans = generate_session(i, project_id=args.project_id)
        if send_spans(client, spans):
            ok_sessions += 1
            total_spans += len(spans)
            agent = spans[0].get("agent_name", "?")
            session_id = spans[0].get("session_id", "?")
            print(f"  [{i + 1:>3}/{args.sessions}] {agent:<20} {session_id}  ({len(spans)} spans)")
        else:
            print(f"  [{i + 1:>3}/{args.sessions}] FAILED")

    print("")
    print("──────────────────────────────────────────────────────")
    print(f"  Seeded {ok_sessions} sessions, {total_spans} spans")
    print("")
    print("  Open the dashboard: http://localhost:3003")
    print("  - Sessions page shows agent traces with call trees")
    print("  - Overview page shows health and anomaly data")
    print("  - Costs page shows per-tool cost attribution")
    print("──────────────────────────────────────────────────────")


if __name__ == "__main__":
    main()
