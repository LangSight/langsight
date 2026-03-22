# LangSight v0.3 — Agent Runtime Reliability

**Date:** 2026-03-22
**Status:** Active — Tier 1 (Prevention Layer) COMPLETE. Tier 2 (Smarter Alerting) and Tier 3 (Blast Radius) NOT STARTED.
**Author:** Suman Sahoo

---

## Positioning shift

### v0.2 (current)
"Your agent failed. Which tool broke — and why?"
Category: Agent observability

### v0.3 (next)
"Your agent failed. Which tool broke, and how do we stop it next time?"
Category: **Agent runtime reliability**

### Why
Observability (tracing, dashboards) overlaps with Langfuse/LangWatch in perception.
Runtime reliability (prevention, guardrails, blast radius) is an empty category.

LangSight is not replacing any tool. It's the **tool layer** that sits alongside:
- **Langfuse** — watches the brain (model outputs, token costs, prompts)
- **LangWatch** — tests the brain (evals, simulations, prompt optimization)
- **Datadog** — watches the body (CPU, memory, HTTP codes)
- **LangSight** — watches the hands (tools the agent calls, their health, safety, and cost)

---

## What we keep (v0.2 foundation)

| Feature | Role in v0.3 |
|---|---|
| Session tracing | Data foundation — powers loop detection, cost attribution, blast radius |
| Multi-agent tree tracing | Powers blast radius and cascade analysis |
| MCP health monitoring | Core differentiator — nobody else does this |
| MCP security scanning (CVE + OWASP + poisoning) | Core differentiator — nobody else does this |
| Schema drift detection | Core differentiator — early warning before agents break |
| Cost attribution (tool-level) | Direct value — not model-level costs (Langfuse does that) |
| Session replay + diff | Debugging tool — re-execute failed sessions to reproduce/verify fixes |
| SLO tracking | Reliability metric — success rate and latency targets per agent |
| Anomaly detection (z-score) | Pattern detection — baseline deviation alerts |
| Alerting (Slack + webhook) | Notification foundation — expand in v0.3 |
| Lineage DAG | Dependency graph — becomes blast radius in v0.3 |
| Prometheus /metrics | Integration with existing monitoring stacks |
| AI root cause analysis | Investigation tool — Claude/GPT/Gemini/Ollama |

---

## What we add (v0.3 features)

### Tier 1 — Prevention layer (weeks 1-3) — COMPLETE ✅ (shipped 2026-03-22)

These features transform LangSight from "we observe" to "we protect."

#### 1.1 Loop detection ✅

**Problem:** Most common agent failure mode. Agent calls the same tool with the same args repeatedly, burning tokens and producing no progress.

**Implementation:**
- In the SDK (`LangSightClient`), track a sliding window of recent tool calls
- Detect: same tool_name + normalized input_args called N times (configurable, default 3)
- Detect: ping-pong between two tools without state change
- Detect: retry-without-progress (same tool, same error, repeated)

**Behavior:**
- On detection: emit `loop_detected` event to API
- Configurable action: `warn` (log + alert) or `terminate` (stop the run)
- Alert includes: tool name, repeated args, loop count, session ID

**SDK config:**
```python
client = LangSightClient(
    url="http://localhost:8000",
    loop_detection=True,
    loop_threshold=3,          # same tool+args 3x = loop
    loop_action="terminate",   # or "warn"
)
```

**API event:**
```json
{
  "event": "loop_detected",
  "session_id": "sess-abc",
  "tool_name": "postgres-mcp/query",
  "repeated_args_hash": "a1b2c3",
  "loop_count": 3,
  "action_taken": "terminated"
}
```

**Dashboard:** Sessions page gets a `loop_detected` badge. Filter sessions by health tag.

**Effort:** 2-3 days

---

#### 1.2 Budget guardrails ✅

**Problem:** Agent loops or expensive tool calls cause surprise bills. No existing tool enforces cost limits at the tool layer.

**Implementation:**
- SDK tracks cumulative cost per session (sum of tool call costs + LLM token costs)
- SDK tracks step count per session
- Pre-call check: if next call would exceed budget → terminate or degrade

**Configurable limits:**
```python
client = LangSightClient(
    url="http://localhost:8000",
    max_cost_usd=1.00,        # hard stop at $1
    max_steps=25,              # hard stop at 25 tool calls
    max_wall_time_s=120,       # hard stop at 2 minutes
    budget_soft_alert=0.80,    # alert at 80% of budget
)
```

**Behavior:**
- At soft threshold (80%): emit `budget_warning` event
- At hard limit: emit `budget_exceeded` event, terminate session
- Optional: `budget_action="degrade"` → switch to cheaper model instead of terminating

**API event:**
```json
{
  "event": "budget_exceeded",
  "session_id": "sess-abc",
  "limit_type": "max_cost_usd",
  "limit_value": 1.00,
  "actual_value": 1.03,
  "action_taken": "terminated"
}
```

**Effort:** 2-3 days

---

#### 1.3 Circuit breaker per tool ✅

**Problem:** A failing MCP server causes cascading failures across all agents that depend on it. Standard pattern in microservices, completely missing in AI agent toolchains.

**Implementation:**
- Track per-tool failure rate over a sliding window
- States: `closed` (normal) → `open` (disabled) → `half_open` (testing recovery)
- When open: tool calls are rejected immediately without hitting the server

**Configuration (per server in .langsight.yaml):**
```yaml
servers:
  - name: postgres-mcp
    transport: stdio
    command: python server.py
    circuit_breaker:
      failure_threshold: 5        # 5 consecutive failures
      cooldown_seconds: 60        # disable for 60s
      half_open_max_calls: 2      # test with 2 calls before fully closing
```

**Behavior:**
- Failure threshold reached → circuit opens → alert fired
- After cooldown → half-open → allow limited calls to test recovery
- If test calls succeed → circuit closes → recovery alert fired
- If test calls fail → circuit stays open → extend cooldown

**Alert:**
```
CIRCUIT OPEN: postgres-mcp disabled after 5 consecutive failures.
Affected agents: support-agent, billing-agent (via lineage).
Auto-recovery in 60 seconds.
```

**Effort:** 3 days

---

#### 1.4 Run health tags ✅

**Problem:** Engineers can't quickly filter sessions by failure mode. Every session looks the same in the list until you open it.

**Implementation:**
- At session completion, auto-classify with a machine-readable health tag
- Tag stored in ClickHouse, filterable in dashboard and API

**Tags:**
```
success                  — all tool calls succeeded
success_with_fallback    — succeeded but used fallback/retry
loop_detected            — terminated due to loop
budget_exceeded          — terminated due to cost/step limit
tool_failure             — one or more tool calls failed
circuit_breaker_open     — tool was disabled by circuit breaker
timeout                  — session exceeded wall time
schema_drift             — tool schema changed during session
```

**Dashboard:** Sessions list shows colored tag badges. Filter dropdown by health tag.

**Effort:** 1-2 days

---

### Tier 1 — Implementation notes (shipped 2026-03-22)

**What shipped as planned:**
- Loop detection: all 3 patterns (repetition, ping-pong, retry-without-progress), configurable threshold + action
- Budget guardrails: step count, wall time, cost tracking with soft alert + hard limit
- Circuit breaker: full CLOSED/OPEN/HALF_OPEN state machine with configurable threshold, cooldown, half-open test calls
- Health tags: all 8 tags, priority ordering, dashboard `HealthTagBadge` + filter
- New alert types: `LOOP_DETECTED`, `BUDGET_WARNING`, `BUDGET_EXCEEDED`, `CIRCUIT_BREAKER_OPEN`, `CIRCUIT_BREAKER_RECOVERED`

**What changed from plan:**
- `budget_action="degrade"` (switch to cheaper model) was deferred — requires framework-specific model selection hooks. Only `terminate` behavior is implemented. (changed from original: was planned for Tier 1, now deferred to Tier 4+)
- `pricing_table` parameter added (not in original plan) — maps `model_name → (input_price_per_1k, output_price_per_1k)` for client-side cost estimation
- `LoopDetector` uses a sliding window (`deque` of configurable size, default 20) rather than full session history — bounded memory usage
- `CircuitBreakerConfig` added as optional field on `MCPServer` model for per-server overrides via `.langsight.yaml`
- `PreventionEvent` model added as SDK-originated event type for alert engine integration

**Source files:**
| File | What it does |
|---|---|
| `src/langsight/sdk/circuit_breaker.py` | Circuit breaker state machine |
| `src/langsight/sdk/loop_detector.py` | Loop detection (3 patterns) |
| `src/langsight/sdk/budget.py` | Budget tracking + soft/hard alerts |
| `src/langsight/sdk/client.py` | SDK integration — prevention in `call_tool()` |
| `src/langsight/sdk/models.py` | `ToolCallStatus.PREVENTED`, `PreventionEvent` |
| `src/langsight/tagging/engine.py` | `HealthTag` enum + `tag_from_spans()` |
| `src/langsight/alerts/engine.py` | 5 new alert types + `evaluate_prevention_event()` |
| `src/langsight/exceptions.py` | `LoopDetectedError`, `BudgetExceededError`, `CircuitBreakerOpenError` |
| `dashboard/components/health-tag-badge.tsx` | Colored health tag badges |

---

### Tier 2 — Smarter alerting (weeks 4-6)

#### 2.1 OpsGenie native integration

**Problem:** Generic webhook works but lacks proper severity mapping, dedup keys, and auto-close on recovery.

**Implementation:**
- OpsGenie Events API integration
- Map alert severity → OpsGenie priority (P1-P5)
- Dedup key: `langsight-{server_name}-{alert_type}`
- Auto-close alert when server recovers (send "close" event)
- Include runbook URL from server metadata

**Config:**
```yaml
alerts:
  opsgenie:
    api_key: ${LANGSIGHT_OPSGENIE_API_KEY}
    priority_mapping:
      critical: P1
      high: P2
      medium: P3
      low: P4
```

**Effort:** 1-2 days

---

#### 2.2 PagerDuty native integration

**Implementation:**
- PagerDuty Events API v2
- Trigger + resolve lifecycle (auto-resolve on recovery)
- Routing key per severity or per server
- Include: dedup key, custom details, links to dashboard

**Config:**
```yaml
alerts:
  pagerduty:
    routing_key: ${LANGSIGHT_PAGERDUTY_KEY}
```

**Effort:** 1-2 days

---

#### 2.3 Failure-rate alerts (pattern-based, not event-based)

**Problem:** Alerting on single failures is noisy. Engineers need pattern alerts.

**Current:** "postgres-mcp failed" (single event)
**Better:** "postgres-mcp failure rate increased from 2% to 18% in 10 minutes"

**Implementation:**
- Sliding window (configurable: 5min, 10min, 30min)
- Track success/failure rate per tool
- Alert when rate crosses threshold OR when rate spikes relative to baseline
- Dedup: one alert per pattern, not per failure

**Config:**
```yaml
alerts:
  failure_rate:
    window_minutes: 10
    threshold_percent: 15       # alert if failure rate > 15%
    spike_multiplier: 3.0       # alert if rate is 3x baseline
```

**Effort:** 2-3 days

---

#### 2.4 Deploy-aware alert correlation

**Problem:** After a deploy, failure rate spikes. Engineers see the alert but don't know what changed.

**Implementation:**
- Track `agent_version` / `workflow_version` from SDK session metadata
- When a new version appears, mark it as a "deploy event"
- Correlate alerts with deploy events within a time window
- Alert includes: "Failure rate increased 6 minutes after agent_v3.2 first appeared"

**Effort:** 2-3 days

---

### Tier 3 — Lineage as blast radius (weeks 7-10)

This is where the existing lineage DAG becomes a **reliability feature**, not just a visualization.

#### 3.1 Blast radius analysis

**Problem:** An MCP server goes down. How many agents are affected? Which are critical?

**Implementation:**
- Lineage graph already has: agent → server edges with call counts
- Add: health status overlay on each node (from health checker)
- Add: impact score = sum of affected sessions per day
- New API endpoint: `GET /api/agents/lineage/blast-radius?server=postgres-mcp`

**Response:**
```json
{
  "server": "postgres-mcp",
  "status": "down",
  "affected_agents": [
    { "name": "support-agent", "sessions_per_day": 200, "criticality": "high" },
    { "name": "billing-agent", "sessions_per_day": 50, "criticality": "medium" }
  ],
  "total_impact": 250,
  "recommendation": "Enable circuit breaker with fallback"
}
```

**Dashboard:** Lineage graph nodes colored by health. Click a down server → see affected agents + impact.

**Effort:** 3-4 days

---

#### 3.2 Impact alerts

**Problem:** Current alerts say "server X is down." Better: "server X is down, affecting 3 agents and 250 sessions/day."

**Implementation:**
- When server_down alert fires, look up lineage graph
- Enrich alert with affected agents + session counts
- Include in Slack/OpsGenie/PagerDuty payload

**Alert example:**
```
CRITICAL: postgres-mcp DOWN since 02:17 UTC

Impact:
  - support-agent: 200 sessions/day (HIGH)
  - billing-agent: 50 sessions/day (MEDIUM)
  - data-agent: 10 sessions/day (LOW)

Total: ~260 sessions/day affected
Circuit breaker: not configured (recommend enabling)
```

**Effort:** 1-2 days

---

#### 3.3 Cascade prediction

**Problem:** A server is degraded (slow but not down). If it goes fully down, what breaks?

**Implementation:**
- When server status is `degraded`, predict impact of full failure
- Show in dashboard: "If slack-mcp goes down: 2 agents affected, ~100 sessions/day"
- Proactive warning, not reactive alert

**Effort:** 2 days

---

### Tier 4 — Advanced (v0.4+, defer until user demand)

| Feature | Why defer |
|---|---|
| Tool policy engine (declarative allow/deny rules) | Enterprise complexity, no users requesting it |
| Human-in-the-loop escalation (approve/reject in Slack) | Requires deep framework integration |
| Automatic fallback routing (tool A fails → tool B) | Needs per-framework adapters, complex |
| Safe mode toggle (one-click disable autonomous execution) | Needs all above first |
| Tool argument schema validation (pre-call) | Good but less urgent than prevention |
| Tool output contract validation (post-call) | Good but less urgent than prevention |
| Run diffing (successful vs failed, model A vs B) | Session comparison already exists, extend later |

---

## Alert integration architecture (v0.3)

```
Alert Engine
    │
    ├── Channels
    │   ├── Slack (existing — Block Kit)
    │   ├── Generic Webhook (existing — PagerDuty/Opsgenie/custom)
    │   ├── OpsGenie (new — native Events API, auto-close)
    │   └── PagerDuty (new — Events API v2, trigger/resolve)
    │
    ├── Alert types
    │   ├── server_down (existing)
    │   ├── server_recovered (existing)
    │   ├── schema_drift (existing)
    │   ├── latency_spike (existing)
    │   ├── slo_breach (existing)
    │   ├── anomaly_detected (existing)
    │   ├── loop_detected (new)
    │   ├── budget_exceeded (new)
    │   ├── budget_warning (new — soft threshold)
    │   ├── circuit_breaker_open (new)
    │   ├── circuit_breaker_recovered (new)
    │   ├── failure_rate_spike (new)
    │   └── blast_radius_impact (new — enriched with lineage)
    │
    └── Alert enrichment
        ├── Affected agents (from lineage)
        ├── Sessions per day impact
        ├── Deploy correlation
        └── Recommended action
```

---

## SDK changes (v0.3)

```python
from langsight.sdk import LangSightClient

client = LangSightClient(
    url="http://localhost:8000",
    api_key="ls_...",

    # --- NEW in v0.3 ---

    # Loop detection
    loop_detection=True,
    loop_threshold=3,              # same tool+args 3x = loop
    loop_action="terminate",       # "terminate" | "warn"

    # Budget guardrails
    max_cost_usd=1.00,            # hard stop at $1
    max_steps=25,                  # hard stop at 25 tool calls
    budget_soft_alert=0.80,        # alert at 80%

    # Circuit breaker (per-server override in .langsight.yaml)
    circuit_breaker=True,
    circuit_breaker_threshold=5,   # consecutive failures
    circuit_breaker_cooldown=60,   # seconds
)
```

---

## Dashboard changes (v0.3)

| Page | Change |
|---|---|
| **Sessions** | Health tag badges (success, loop_detected, budget_exceeded, etc.) + filter by tag ✅ DONE |
| **Lineage** | Health overlay on nodes (green/yellow/red) + click server → blast radius panel |
| **Health** | Circuit breaker status per server (closed/open/half-open) |
| **Settings → Alerts** | OpsGenie + PagerDuty config panels |
| **Overview** | New metric cards: loops prevented, budget saves, circuit breaker activations |
| **Settings → Prevention** | Per-agent prevention config (thresholds for loop/budget/circuit) — see section below |

---

## Prevention Config (dashboard-managed thresholds) — NEW

**Decision:** SDK constructor params are local offline defaults only. Source of truth moves to the platform.

```
Dashboard UI (Settings → Prevention)
         ↓
   Postgres: prevention_config table (per-project, per-agent)
         ↓
   API: GET/PUT /api/agents/{name}/prevention-config
         ↓
   SDK: fetches on client.wrap(), falls back to constructor params if server unreachable
```

### Postgres schema

```sql
CREATE TABLE prevention_config (
    id            TEXT PRIMARY KEY,
    project_id    TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    agent_name    TEXT NOT NULL,
    -- Loop detection
    loop_enabled          BOOLEAN NOT NULL DEFAULT TRUE,
    loop_threshold        INTEGER NOT NULL DEFAULT 3,
    loop_action           TEXT    NOT NULL DEFAULT 'terminate',  -- 'terminate' | 'warn'
    -- Budget guardrails
    max_steps             INTEGER,           -- NULL = disabled
    max_cost_usd          NUMERIC(10, 4),   -- NULL = disabled
    max_wall_time_s       NUMERIC(10, 2),   -- NULL = disabled
    budget_soft_alert     NUMERIC(3, 2) NOT NULL DEFAULT 0.80,
    -- Circuit breaker
    cb_enabled            BOOLEAN NOT NULL DEFAULT TRUE,
    cb_failure_threshold  INTEGER NOT NULL DEFAULT 5,
    cb_cooldown_seconds   NUMERIC(10, 2) NOT NULL DEFAULT 60.0,
    cb_half_open_max      INTEGER NOT NULL DEFAULT 2,
    -- Metadata
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (project_id, agent_name)
);
```

### API endpoints

```
GET  /api/agents/{agent_name}/prevention-config
     → returns config for this agent (or project defaults if no agent-specific config)

PUT  /api/agents/{agent_name}/prevention-config
     body: { loop_enabled, loop_threshold, loop_action, max_steps, max_cost_usd, ... }
     → upsert config for this agent

DELETE /api/agents/{agent_name}/prevention-config
     → remove agent-specific config (falls back to project defaults)

GET  /api/projects/{project_id}/prevention-config
     → get project-level default config (applies to all agents without a specific config)

PUT  /api/projects/{project_id}/prevention-config
     → set project-level defaults
```

### SDK fetch

In `LangSightClient.wrap()`, after wrapping the MCP client, the SDK fetches the prevention config for this agent:

```python
config = await self._fetch_prevention_config(agent_name)
# config overrides constructor params if found
# constructor params remain as offline fallback
```

### Dashboard — Settings → Prevention tab

Per-agent table with inline edit:

| Agent | Loop | Threshold | Action | Max Steps | Max Cost | Max Time | CB |
|---|---|---|---|---|---|---|---|
| orchestrator | ✓ | 3 | terminate | 25 | $1.00 | 120s | ✓ |
| billing-agent | ✓ | 3 | terminate | 10 | $0.50 | 60s | ✓ |
| support-agent | ✓ | 5 | warn | — | — | — | ✓ |

**Effort:** 3–4 days

---

## Timeline

| Week | Deliverable | Milestone |
|---|---|---|
| 1-2 | Loop detection + budget guardrails in SDK | "We stop agents from breaking" |
| 3 | Circuit breaker + run health tags | "We auto-disable failing tools" |
| 4-5 | OpsGenie + PagerDuty + failure-rate alerts | "We page your oncall with context" |
| 6 | Deploy-aware alert correlation | "We show you what caused it" |
| 7-8 | Blast radius on lineage + impact alerts | "We tell you what else will break" |
| 9-10 | Cascade prediction + dashboard polish | "We warn you before it breaks" |

---

## Success metrics

| Metric | Target |
|---|---|
| Loops auto-stopped per week (across all users) | Track from day 1 |
| Budget overages prevented ($) | Track from day 1 |
| Circuit breaker activations | Track from day 1 |
| Mean time from alert → root cause (MTTR) | < 5 minutes |
| User NPS on alerts (signal vs noise) | > 60 |

---

## What we DON'T build (and why)

| Feature | Why not |
|---|---|
| Prompt evaluation | That's LangWatch/Langfuse territory |
| LLM output scoring | Same — not our layer |
| A/B testing prompts | Same |
| Agent simulation | That's LangWatch |
| Generic APM metrics | That's Datadog |
| Custom policy DSL | Over-engineering for zero users |

---

## One-line summary

**v0.3 transforms LangSight from "we show you what broke" to "we stop it from breaking and tell you what else will break."**
