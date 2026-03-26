#!/usr/bin/env python3
"""Export Gotphoto project data from ClickHouse → seed JSON files.

Usage:
    python scripts/export-seed-data.py

Reads from the running ClickHouse instance and writes:
    src/langsight/seed_data/spans.json
    src/langsight/seed_data/health_tags.json

The output uses relative timestamps (offset_s from the first span) and
integer session indices instead of UUIDs, so the seed can regenerate
fresh IDs on every startup.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import clickhouse_connect

# Gotphoto project ID (from the running instance)
import os
from dotenv import load_dotenv

load_dotenv()

PROJECT_ID = "1abac77929fd45c289b6fcf2070f4312"
CH_HOST = "localhost"
CH_PORT = 8123
CH_USER = os.getenv("CLICKHOUSE_USER", "default")
CH_PASS = os.getenv("CLICKHOUSE_PASSWORD", "")

OUT_DIR = Path(__file__).resolve().parent.parent / "src" / "langsight" / "seed_data"


def main() -> None:
    client = clickhouse_connect.get_client(
        host=CH_HOST, port=CH_PORT, username=CH_USER, password=CH_PASS,
        database="langsight",
    )

    # ── Export spans ─────────────────────────────────────────────────────
    print("Querying spans from ClickHouse...")
    result = client.query(
        """
        SELECT
            started_at,
            ended_at,
            latency_ms,
            server_name,
            tool_name,
            status,
            error,
            agent_name,
            session_id,
            span_type,
            model_id,
            input_tokens,
            output_tokens,
            parent_span_id,
            span_id
        FROM mcp_tool_calls
        WHERE project_id = {pid:String}
        ORDER BY started_at ASC
        """,
        parameters={"pid": PROJECT_ID},
    )

    cols = [
        "started_at", "ended_at", "latency_ms", "server_name", "tool_name",
        "status", "error", "agent_name", "session_id", "span_type",
        "model_id", "input_tokens", "output_tokens", "parent_span_id", "span_id",
    ]
    rows = [dict(zip(cols, row)) for row in result.result_rows]
    print(f"  Found {len(rows)} spans")

    if not rows:
        print("ERROR: No spans found. Is the Gotphoto project populated?", file=sys.stderr)
        sys.exit(1)

    # Build session_id → index map
    unique_sessions = list(dict.fromkeys(r["session_id"] for r in rows))
    session_idx_map = {sid: idx for idx, sid in enumerate(unique_sessions)}

    # Build span_id → index map (for parent linking)
    span_id_map = {r["span_id"]: idx for idx, r in enumerate(rows)}

    # Compute base timestamp
    first_ts = rows[0]["started_at"]

    spans_out = []
    for r in rows:
        offset_s = (r["started_at"] - first_ts).total_seconds()
        duration_ms = r["latency_ms"] if r["latency_ms"] else (r["ended_at"] - r["started_at"]).total_seconds() * 1000

        parent_idx = None
        if r["parent_span_id"] and r["parent_span_id"] in span_id_map:
            parent_idx = span_id_map[r["parent_span_id"]]

        spans_out.append({
            "offset_s": round(offset_s, 3),
            "duration_ms": round(duration_ms, 2),
            "server_name": r["server_name"],
            "tool_name": r["tool_name"],
            "status": r["status"],
            "error": r["error"] if r["error"] else None,
            "agent_name": r["agent_name"],
            "session_idx": session_idx_map[r["session_id"]],
            "span_type": r["span_type"],
            "model_id": r["model_id"] if r["model_id"] else None,
            "input_tokens": r["input_tokens"] if r["input_tokens"] else None,
            "output_tokens": r["output_tokens"] if r["output_tokens"] else None,
            "parent_span_idx": parent_idx,
        })

    # ── Export health tags ───────────────────────────────────────────────
    print("Querying health tags...")
    ht_result = client.query(
        """
        SELECT session_id, health_tag
        FROM session_health_tags FINAL
        WHERE project_id = {pid:String}
        """,
        parameters={"pid": PROJECT_ID},
    )

    health_out = []
    for row in ht_result.result_rows:
        sid, tag = row[0], row[1]
        if sid in session_idx_map:
            health_out.append({
                "session_idx": session_idx_map[sid],
                "health_tag": tag,
            })
    print(f"  Found {len(health_out)} health tags")

    # ── Write JSON ───────────────────────────────────────────────────────
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    spans_path = OUT_DIR / "spans.json"
    with open(spans_path, "w") as f:
        json.dump(spans_out, f, indent=None, separators=(",", ":"))
    print(f"  Wrote {spans_path} ({spans_path.stat().st_size // 1024} KB)")

    health_path = OUT_DIR / "health_tags.json"
    with open(health_path, "w") as f:
        json.dump(health_out, f, indent=2)
    print(f"  Wrote {health_path}")

    print(f"\nDone: {len(spans_out)} spans, {len(unique_sessions)} sessions, {len(health_out)} health tags")


if __name__ == "__main__":
    main()
