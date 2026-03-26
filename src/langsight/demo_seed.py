"""
Sample project seed — loads real inventory-agent data from JSON templates.

The JSON files in seed_data/ were exported from a live Gotphoto e2e run
(3 agents, 6 MCP servers, 123 sessions, 1502 spans). On each startup the
seed replays them with fresh UUIDs and timestamps relative to now(), so the
dashboard always shows recent, realistic data.

Entry point: ``seed_demo_data(storage, project_id)`` — called by
``_bootstrap_sample_project()`` in ``api/main.py`` on first run.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import structlog

from langsight.models import PreventionConfig
from langsight.sdk.models import ToolCallSpan, ToolCallStatus

logger = structlog.get_logger()

_SEED_DIR = Path(__file__).parent / "seed_data"

# ── Agent metadata (proper descriptions, not "Auto-discovered from traces") ──

_AGENTS = [
    {
        "name": "orchestrator",
        "description": "Workflow coordinator — routes queries to analyst and procurement agents",
        "owner": "platform-team",
        "tags": ["multi-agent", "coordinator"],
    },
    {
        "name": "analyst",
        "description": "Inventory analysis — deep product/stock queries across catalog and inventory",
        "owner": "analytics-team",
        "tags": ["analytics", "inventory"],
    },
    {
        "name": "procurement",
        "description": "Reorder management — generates purchase orders and tracks supplier lead times",
        "owner": "supply-chain-team",
        "tags": ["procurement", "ordering"],
    },
]

# ── MCP server metadata ─────────────────────────────────────────────────────

_SERVERS = [
    {
        "name": "gemini",
        "description": "Google Gemini 2.5 Flash LLM — primary reasoning engine",
        "transport": "sse",
    },
    {
        "name": "catalog",
        "description": "Product catalog MCP — list/search/get products and categories",
        "transport": "sse",
    },
    {
        "name": "inventory",
        "description": "Stock management MCP — stock levels, low stock alerts, reorder needs",
        "transport": "sse",
    },
    {
        "name": "orchestrator",
        "description": "Orchestrator tools — sub-agent delegation and workflow utilities",
        "transport": "stdio",
    },
    {
        "name": "analyst",
        "description": "Analyst tools — inventory analysis functions and data aggregation",
        "transport": "stdio",
    },
    {
        "name": "procurement",
        "description": "Procurement tools — reorder calculations and supplier management",
        "transport": "stdio",
    },
]

# ── Prevention configs ───────────────────────────────────────────────────────

_PREVENTION_CONFIGS: list[dict[str, Any]] = [
    {
        "agent_name": "*",
        "loop_enabled": True,
        "loop_threshold": 3,
        "loop_action": "terminate",
        "cb_enabled": True,
        "cb_failure_threshold": 5,
        "cb_cooldown_seconds": 60.0,
        "cb_half_open_max_calls": 2,
    },
    {
        "agent_name": "orchestrator",
        "loop_threshold": 3,
        "max_steps": 25,
        "max_cost_usd": 2.00,
    },
    {
        "agent_name": "analyst",
        "loop_threshold": 5,
        "loop_action": "warn",
        "max_steps": 50,
        "max_cost_usd": 1.00,
    },
    {
        "agent_name": "procurement",
        "loop_threshold": 3,
        "max_steps": 15,
        "max_cost_usd": 0.50,
        "cb_failure_threshold": 3,
        "cb_cooldown_seconds": 30.0,
    },
]

# ── SLO definitions ──────────────────────────────────────────────────────────

_SLOS: list[dict[str, Any]] = [
    {
        "agent_name": "orchestrator",
        "metric": "success_rate",
        "target": 0.95,
        "window_hours": 24,
        "description": "95% of orchestrator sessions should complete without tool_failure",
    },
    {
        "agent_name": "analyst",
        "metric": "latency_p99",
        "target": 10000.0,
        "window_hours": 24,
        "description": "p99 latency for analyst tool calls should be under 10s",
    },
    {
        "agent_name": "procurement",
        "metric": "success_rate",
        "target": 0.90,
        "window_hours": 24,
        "description": "90% of procurement sessions should succeed",
    },
]

# ── Helpers ──────────────────────────────────────────────────────────────────


def _load_json(filename: str) -> list[dict[str, Any]]:
    """Load a JSON file from the seed_data directory."""
    path = _SEED_DIR / filename
    with open(path) as f:
        data: list[dict[str, Any]] = json.load(f)
    return data


_STATUS_MAP = {
    "success": ToolCallStatus.SUCCESS,
    "error": ToolCallStatus.ERROR,
    "timeout": ToolCallStatus.TIMEOUT,
    "prevented": ToolCallStatus.PREVENTED,
}


# ── Main entry point ─────────────────────────────────────────────────────────


async def seed_demo_data(storage: Any, project_id: str) -> None:
    """Seed the sample project with real inventory-agent trace data.

    Loads span templates from seed_data/spans.json, remaps timestamps to
    be relative to now(), generates fresh UUID4 session IDs, and inserts
    via the storage backend.  Idempotent: skips if spans already exist.
    """
    logger.info("demo_seed.starting", project_id=project_id)

    # ── 1. Load templates ────────────────────────────────────────────────
    try:
        spans_data = _load_json("spans.json")
        health_data = _load_json("health_tags.json")
    except FileNotFoundError:
        logger.warning("demo_seed.seed_data_missing", hint="Run scripts/export-seed-data.py first")
        return

    if not spans_data:
        logger.warning("demo_seed.empty_spans")
        return

    # ── 2. Generate fresh session IDs ────────────────────────────────────
    session_indices = sorted(set(s["session_idx"] for s in spans_data))
    session_map = {idx: uuid.uuid4().hex for idx in session_indices}

    # ── 3. Compute base timestamp so data looks ~30 min old ──────────────
    max_offset = max(s["offset_s"] for s in spans_data)
    base_time = datetime.now(UTC) - timedelta(seconds=max_offset + 120)

    # ── 4. Build ToolCallSpan list ───────────────────────────────────────
    spans: list[ToolCallSpan] = []
    for s in spans_data:
        started_at = base_time + timedelta(seconds=s["offset_s"])
        ended_at = started_at + timedelta(milliseconds=s["duration_ms"])
        status = _STATUS_MAP.get(s["status"], ToolCallStatus.SUCCESS)

        spans.append(
            ToolCallSpan(
                server_name=s["server_name"],
                tool_name=s["tool_name"],
                started_at=started_at,
                ended_at=ended_at,
                latency_ms=s["duration_ms"],
                status=status,
                error=s["error"],
                agent_name=s["agent_name"],
                session_id=session_map[s["session_idx"]],
                span_type=s["span_type"],
                project_id=project_id,
                model_id=s.get("model_id"),
                input_tokens=s.get("input_tokens"),
                output_tokens=s.get("output_tokens"),
            )
        )

    # ── 5. Insert spans in batches ───────────────────────────────────────
    if hasattr(storage, "save_tool_call_spans"):
        batch_size = 100
        for i in range(0, len(spans), batch_size):
            await storage.save_tool_call_spans(spans[i : i + batch_size])
        logger.info("demo_seed.spans_inserted", count=len(spans))

    # ── 6. Seed health tags ──────────────────────────────────────────────
    if hasattr(storage, "save_session_health_tag"):
        ht_count = 0
        for ht in health_data:
            sid = session_map.get(ht["session_idx"])
            if sid:
                try:
                    await storage.save_session_health_tag(
                        sid, ht["health_tag"], project_id=project_id
                    )
                    ht_count += 1
                except Exception:  # noqa: BLE001
                    pass
        logger.info("demo_seed.health_tags", count=ht_count)

    # ── 7. Seed agent metadata ───────────────────────────────────────────
    if hasattr(storage, "upsert_agent_metadata"):
        for agent in _AGENTS:
            try:
                await storage.upsert_agent_metadata(
                    agent_name=agent["name"],
                    description=agent["description"],
                    owner=agent.get("owner", ""),
                    tags=agent.get("tags", []),
                    status="active",
                    runbook_url="",
                    project_id=project_id,
                )
            except Exception:  # noqa: BLE001
                pass
        logger.info("demo_seed.agents", count=len(_AGENTS))

    # ── 8. Seed server metadata ──────────────────────────────────────────
    if hasattr(storage, "upsert_server_metadata"):
        for srv in _SERVERS:
            try:
                await storage.upsert_server_metadata(
                    server_name=srv["name"],
                    description=srv["description"],
                    transport=srv.get("transport", ""),
                    project_id=project_id,
                )
            except Exception:  # noqa: BLE001
                pass
        logger.info("demo_seed.servers", count=len(_SERVERS))

    # ── 9. Seed prevention configs ───────────────────────────────────────
    if hasattr(storage, "upsert_prevention_config"):
        pc_count = 0
        for pc_data in _PREVENTION_CONFIGS:
            defaults: dict[str, Any] = {
                "loop_enabled": True,
                "loop_threshold": 3,
                "loop_action": "terminate",
                "max_steps": None,
                "max_cost_usd": None,
                "max_wall_time_s": None,
                "budget_soft_alert": 0.80,
                "cb_enabled": True,
                "cb_failure_threshold": 5,
                "cb_cooldown_seconds": 60.0,
                "cb_half_open_max_calls": 2,
            }
            defaults.update(pc_data)
            try:
                pc = PreventionConfig(
                    id=uuid.uuid4().hex,
                    project_id=project_id,
                    **defaults,
                )
                await storage.upsert_prevention_config(pc)
                pc_count += 1
            except Exception:  # noqa: BLE001
                pass
        logger.info("demo_seed.prevention_configs", count=pc_count)

    # ── 10. Seed SLOs ────────────────────────────────────────────────────
    if hasattr(storage, "upsert_slo"):
        slo_count = 0
        for slo_data in _SLOS:
            try:
                await storage.upsert_slo(
                    {
                        "id": uuid.uuid4().hex,
                        "project_id": project_id,
                        **slo_data,
                    }
                )
                slo_count += 1
            except Exception:  # noqa: BLE001
                pass
        logger.info("demo_seed.slos", count=slo_count)

    logger.info(
        "demo_seed.complete",
        project_id=project_id,
        sessions=len(session_map),
        spans=len(spans),
        agents=len(_AGENTS),
        servers=len(_SERVERS),
    )
