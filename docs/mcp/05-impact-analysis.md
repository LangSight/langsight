# MCP Features — Impact on Existing Agent Features

**Date**: 2026-03-26
**Status**: Confirmed — no agent features broken

---

## Summary

All 5 MCP features are **additive**. No existing agent SDK, session ingestion, loop detection, budget enforcement, cost tracking, SLO, or anomaly detection code is modified.

| Feature | Agent SDK | Sessions | Cost/SLO/Anomaly | Storage Schema | Risk |
|---|---|---|---|---|---|
| 1. Fix Discovery (`langsight init`) | — | — | — | — | **Zero** |
| 2. Continuous Monitoring Daemon | — | — | — | Additive | **Low** (one timeout note) |
| 3. Schema Drift + Consumer Impact | — | — | — | Additive new table | **Low** (new fields need defaults) |
| 4. MCP Server Scorecard | — | — | — | Additive new table | **Zero** |
| 5. Root Cause Correlation | — | Read-only | — | Read-only | **Zero** |

---

## Feature 1: Fix `langsight init` (Discovery)

**Files changed**: `cli/init.py` only — `_discover_servers()` and `_parse_mcp_config()`

**Impact**: None. Pure config-file reading. No runtime code, no agent SDK, no storage changes.

**What changes**: Fix broken macOS path for Claude Desktop, add 7 more client configs (Windsurf, Gemini CLI, Claude Code, Kiro, Zed, Cline, Continue.dev).

---

## Feature 2: Continuous Health Monitoring (Daemon + StreamableHTTP)

**Files changed**: `cli/monitor.py`, `health/checker.py`, `health/transports.py`

**Impact**: One careful point.

The upgrade of `HealthChecker.check()` to run a full protocol sequence (`ping` → `initialize` → `tools/list` → disconnect) instead of just a ping changes latency from ~50ms to ~300–2000ms per check. Callers of `check()`:

- `cli/monitor.py` → `_monitor_loop()` via `check_many()`
- `api/routers/health.py` → `trigger_health_check()`
- Dashboard "Check Now" button

**Mitigation**: Keep ping as the fast primary signal. Run the full protocol check asynchronously without blocking the `HealthCheckResult` return. Callers see the same output model — no API contract changes.

```python
async def check(self, server: MCPServer) -> HealthCheckResult:
    # Fast ping — same as today, same return shape
    result = await self._ping(server)

    # Full protocol check — async, doesn't block return
    asyncio.create_task(self._full_protocol_check(server))

    return result  # HealthCheckResult shape unchanged
```

**StreamableHTTP transport**: Purely additive — new transport class in `health/transports.py`. Zero changes to existing `stdio` and `sse` transports.

**Agent features affected**: None.

---

## Feature 3: Schema Drift + Consumer Impact

**Files changed**: `health/schema_tracker.py` — extended, not replaced

**Impact**: One backward-compat note.

`SchemaTracker.check_and_update()` returns `SchemaDriftResult` dataclass. Adding new fields (`structural_diff`, `breaking_changes`, `compatible_changes`) is safe as long as new fields have default values. The caller in `health/checker.py` only reads `has_drift` and `drift_details` today — new fields are ignored by existing consumers.

```python
@dataclass
class SchemaDriftResult:
    has_drift: bool
    drift_details: str
    # New fields — all have defaults, backward compatible
    structural_diff: list[SchemaChange] = field(default_factory=list)
    has_breaking_changes: bool = False
    compatible_changes: list[SchemaChange] = field(default_factory=list)
```

**Consumer impact query**: Pure READ against existing `mcp_tool_calls` table in ClickHouse. No writes. No schema changes to existing tables.

**New table**: `schema_drift_events` in ClickHouse — purely additive, no existing tables modified.

**Agent features affected**: None.

---

## Feature 4: MCP Server Scorecard

**Files changed**: New file `health/scorecard.py` only

**Impact**: Zero. Entirely new code.

- New `health/scorecard.py` — `MCPServerScorecard` model + `ScorecardEngine`
- New API endpoint `GET /api/health/servers/{name}/scorecard`
- New ClickHouse table `server_scorecard_history` — additive
- Dashboard `/health` page: status dot → A-F badge (visual change only, same underlying data)

**Agent features affected**: None.

---

## Feature 5: Root Cause Correlation

**Files changed**: `cli/investigate.py` — extended, not replaced

**Impact**: Zero.

The existing `investigate` command's `--server` flag and LLM/rules analysis paths are preserved. The session dimension is **additive evidence** alongside existing MCP health evidence — not a replacement.

- New `GET /api/sessions/{id}/root-cause` endpoint — additive
- New `GET /api/health/servers/{name}/blast-radius` endpoint — additive
- New "Root Cause" tab in `/sessions/{id}` dashboard — additive UI
- All ClickHouse queries are **read-only** against existing tables:
  - `get_session_trace()` — already exists
  - `get_health_history()` — already exists
  - No new writes, no schema changes

**Agent features affected**: None.

---

## What Is Never Touched

The following agent features have **zero overlap** with any of the 5 MCP features:

| Component | Why safe |
|---|---|
| `sdk/client.py` — LangSightClient | No changes. MCP features don't touch SDK instrumentation. |
| Framework adapters (LangChain, CrewAI, Pydantic AI, Anthropic, OpenAI) | No changes. |
| Loop detection logic | No changes. |
| Budget enforcement (max_cost_usd, max_steps, max_wall_time_s) | No changes. |
| Circuit breaker | No changes. |
| Cost engine + pricing rules | No changes. |
| SLO evaluation (AgentSLO, SLOEvaluator) | No changes. |
| Anomaly detection (z-score, baseline) | No changes. |
| Session health tagging | No changes. |
| Alert engine (Slack/webhook) | No changes (MCP alerts reuse existing engine). |
| OTLP ingestion (`POST /api/traces/otlp`) | No changes. |
| Lineage graph | No changes (MCP topology reads same `mcp_tool_calls` data). |
| Auth, RBAC, projects | No changes. |

---

## The One Rule

When upgrading `HealthChecker.check()` for Feature 2 — keep the return contract identical. Ping gives the fast status result. Full protocol check runs in background. Existing dashboard and CLI consumers see no difference in latency or output shape.
