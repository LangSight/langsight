# 07 — Agent Action Lineage

## Problem

When an orchestrator agent delegates to sub-agents that call tools across multiple MCP servers, operators have no way to see the full dependency graph. Today LangSight shows per-session span trees — useful for debugging one run. But operators need to answer aggregate questions:

- "If postgres-mcp goes down, which agents break?"
- "What's the critical path through my multi-agent workflow?"
- "Which tools are called by every agent vs. only one?"
- "If I upgrade jira-mcp, what's the blast radius?"

Data pipeline teams answer these questions with **lineage graphs** (dbt, Airflow, DataHub, OpenLineage). No agent observability tool provides the equivalent for tool call chains.

## Solution

Add an **Agent Action Lineage** feature: a DAG visualization of agents, MCP servers, and tools — built from aggregated span data, not hand-drawn config. Click any node to see metrics, errors, and drill into sessions.

## Status Update (2026-03-20)

The lineage feature has shipped, but the final implementation differs from the original proposal in a few important ways:

- `GET /api/agents/lineage` is live and powers the dashboard topology views
- There is no standalone `/api/agents/lineage/{node_id}/impact` endpoint yet
- `/lineage` is no longer a standalone dashboard destination; it redirects to `/agents`
- Topology exploration lives inside the Agents page (selected-agent topology + global topology modal)
- The renderer is raw SVG + `dagre`, not React Flow
- Tool/per-call expansion happens inside the shared renderer rather than via a separate tool-level page mode

## Lineage Protocol v1.0 (2026-04-01)

The lineage protocol was hardened across the full stack to produce reliable, explicit parent/child links instead of relying on heuristic inference.

### Why this was needed

The original lineage implementation relied on parsing `tool_name` to extract handoff targets (`"→ billing-agent"` → `"billing-agent"`) and on heuristic matching to link tool calls to their parent agent spans. This caused three live bugs:
1. **Dashed edges in topology**: missing `parent_span_id` on tool calls created orphaned nodes
2. **Wrong latency attribution**: handoff spans computed latency from the wrong start/end times
3. **Orphaned tool calls**: tool calls from delegated agents had no link back to the handoff

### Protocol fields

Four new fields on `ToolCallSpan` and `mcp_tool_calls`:

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `target_agent_name` | `String` | `''` | Explicit handoff destination. Populated on `span_type="handoff"`. Replaces `tool_name` parsing. |
| `lineage_provenance` | `LowCardinality(String)` | `'explicit'` | How the parent/child link was determined. Values: `explicit`, `derived_parent`, `derived_timing`, `derived_legacy`, `inferred_otel`. |
| `lineage_status` | `LowCardinality(String)` | `'complete'` | Quality flag. Values: `complete`, `incomplete`, `orphaned`, `invalid_parent`, `session_mismatch`, `trace_mismatch`. |
| `schema_version` | `String` | `'1.0'` | Protocol version for backward/forward compat. |

### New span type: `llm_intent`

LLM tool-call decisions are now emitted as `span_type="llm_intent"` instead of `"tool_call"`. This prevents double-counting in agent-to-server reliability metrics. `llm_intent` spans still register in the pending-tool queue so the actual `tool_call` execution can claim the parent link.

Span types are now: `tool_call`, `agent`, `handoff`, `llm_intent`.

### Ingest validation

The traces ingest endpoint (`POST /api/traces/spans`) now performs three lineage checks:
1. **Parent batch check**: if `parent_span_id` is set but not found in the current batch, `lineage_status` is downgraded to `incomplete`
2. **Legacy handoff upgrade**: handoff spans without `target_agent_name` get it extracted from `tool_name` and `lineage_provenance` is set to `derived_legacy`
3. **Trace consistency warning**: if a span's parent is in a different `trace_id`, a structured log warning is emitted

### Dashboard changes

- `SpanType` union includes `"llm_intent"` (`dashboard/lib/types.ts`)
- `LineageProvenance` and `LineageStatus` type aliases added
- `SpanNode` gained 4 new fields: `target_agent_name`, `lineage_provenance`, `lineage_status`, `schema_version`
- `session-graph.ts` uses `span_type === "llm_intent"` with legacy heuristic fallback; uses `target_agent_name` for handoff detection with `tool_name` parsing as fallback

### SDK helpers

Two convenience methods on `LangSightClient`:
- `create_handoff(from_agent, to_agent, ...)` -- emits a properly linked handoff span and returns it
- `wrap_child_agent(mcp, server_name, agent_name, handoff_span)` -- wraps an MCP client for a child agent with pre-configured `parent_span_id` and `agent_name` from the handoff span

### Async-safe context

`sdk/context.py` replaced `threading.local()` with `contextvars.ContextVar` for the pending-tool tracking queue. This ensures that async tasks (e.g., concurrent agent handlers in OpenAI Agents SDK) correctly inherit the parent task's pending-tool state.

---

## Handoff Auto-Detection (v0.12.0)

### Problem

The v1.0 lineage protocol required explicit `create_handoff()` calls. In practice, many multi-agent systems express delegation through tool names (e.g. `call_analyst`, `transfer_to_billing`). Requiring manual `create_handoff()` after every LLM call was error-prone and easy to forget.

### Solution

`_maybe_emit_handoffs()` in `sdk/llm_wrapper.py` inspects every `llm_intent` span emitted after LLM generation. If the tool name matches `_HANDOFF_TOOL_RE`:

```
^(?:call|delegate|invoke|transfer_to|run|dispatch)_(.+)$
```

an explicit handoff span is automatically emitted from the current agent (resolved from `span.agent_name` or `_agent_ctx`) to the target agent (captured group). This handoff span is identical to one produced by `create_handoff()` — same fields, same provenance path.

### Coverage

| Tool name pattern | Target agent | Example |
|---|---|---|
| `call_<agent>` | `<agent>` | `call_analyst` → `analyst` |
| `delegate_<agent>` | `<agent>` | `delegate_billing` → `billing` |
| `invoke_<agent>` | `<agent>` | `invoke_researcher` → `researcher` |
| `transfer_to_<agent>` | `<agent>` | `transfer_to_support` → `support` |
| `run_<agent>` | `<agent>` | `run_summarizer` → `summarizer` |
| `dispatch_<agent>` | `<agent>` | `dispatch_validator` → `validator` |

Self-handoffs (target == source agent name) are silently suppressed to avoid spurious edges.

### Interaction with manual `create_handoff()`

Both paths produce the same span type and are not deduplicated. If your agent both names tools with the `call_*` pattern AND calls `create_handoff()` manually, you will get two handoff spans. The recommended pattern is to rely on auto-detection and remove manual `create_handoff()` calls when tool names follow the convention.

### MCP auto-patch interaction

When the LLM selects `call_analyst` and the MCP tool execution follows, the `llm_intent` span (emitted by `_process_*_response`) registers a pending parent in the context. The `_patch_mcp()` hook then claims this pending parent for the actual `call_tool()` execution, producing the chain:

```
LLM generate/model → [llm_intent: call_analyst] → [handoff: orchestrator→analyst]
                                                  → [tool_call: call_analyst via MCP]  ← parent_span_id = llm_intent span
```

The handoff span and the MCP tool_call span are siblings under the llm_intent span, giving the full lineage picture in the session graph.

---

## Data Model

All required data exists in `mcp_tool_calls`:

```
span_id, parent_span_id, span_type, trace_id, session_id,
server_name, tool_name, agent_name, status, latency_ms, project_id,
target_agent_name, lineage_provenance, lineage_status, schema_version
```

Span types: `tool_call` (agent → tool), `handoff` (agent → agent), `agent` (lifecycle), `llm_intent` (LLM decided to call a tool — not actual execution, excluded from metrics).

### Derived graph structure

**Nodes:**
- `agent:<name>` — an agent (e.g. `orchestrator`, `billing-agent`)
- `server:<name>` — an MCP server (e.g. `postgres-mcp`, `jira-mcp`)
- `tool:<server>/<tool>` — a specific tool (drill-down level)

**Edges (derived from spans):**
- `agent → server` — agent called at least one tool on this server
- `agent → agent` — handoff spans connect agents
- `agent → tool` — specific tool calls (drill-down level)

### Key insight

Edges are **not configured** — they're **observed**. The lineage graph is built from actual span data, not from a YAML file. This means:
- It reflects reality, not intent
- New tools/agents appear automatically
- Dead edges (tools no longer called) age out via the time window

---

## ClickHouse Queries

### 1. Agent-to-server edges (top-level DAG)

```sql
SELECT
    agent_name,
    server_name,
    count()                              AS call_count,
    countIf(status != 'success')         AS error_count,
    avg(latency_ms)                      AS avg_latency_ms,
    max(latency_ms)                      AS max_latency_ms,
    uniq(session_id)                     AS session_count
FROM mcp_tool_calls
WHERE started_at >= now() - INTERVAL {hours} HOUR
  AND agent_name != ''
  AND span_type = 'tool_call'
  {project_filter}
GROUP BY agent_name, server_name
ORDER BY call_count DESC
```

### 2. Agent-to-agent edges (handoffs)

(changed from original 2026-04-01: uses `target_agent_name` with fallback to `tool_name` parsing for pre-protocol data; returns `explicit_count`/`inferred_count` per edge)

```sql
SELECT
    agent_name                           AS from_agent,
    if(target_agent_name != '', target_agent_name,
       replaceOne(tool_name, '→ ', ''))  AS to_agent,
    count()                              AS handoff_count,
    countIf(lineage_provenance = 'explicit') AS explicit_count,
    countIf(lineage_provenance != 'explicit') AS inferred_count,
    uniq(session_id)                     AS session_count
FROM mcp_tool_calls
WHERE started_at >= now() - INTERVAL {hours} HOUR
  AND span_type = 'handoff'
  AND agent_name != ''
  {project_filter}
GROUP BY agent_name, to_agent
ORDER BY handoff_count DESC
```

### 3. Agent-to-tool edges (drill-down)

```sql
SELECT
    agent_name,
    server_name,
    tool_name,
    count()                              AS call_count,
    countIf(status != 'success')         AS error_count,
    avg(latency_ms)                      AS avg_latency_ms,
    uniq(session_id)                     AS session_count
FROM mcp_tool_calls
WHERE started_at >= now() - INTERVAL {hours} HOUR
  AND agent_name != ''
  AND span_type = 'tool_call'
  {project_filter}
GROUP BY agent_name, server_name, tool_name
ORDER BY call_count DESC
```

### 4. Node metrics (for node cards)

Agent summary:
```sql
SELECT
    agent_name,
    count()                                               AS total_calls,
    countIf(status != 'success')                          AS total_errors,
    avg(latency_ms)                                       AS avg_latency_ms,
    uniq(session_id)                                      AS sessions,
    groupUniqArray(server_name)                           AS servers_used
FROM mcp_tool_calls
WHERE started_at >= now() - INTERVAL {hours} HOUR
  AND agent_name != ''
  AND span_type = 'tool_call'
GROUP BY agent_name
```

Server summary:
```sql
SELECT
    server_name,
    count()                                               AS total_calls,
    countIf(status != 'success')                          AS total_errors,
    avg(latency_ms)                                       AS avg_latency_ms,
    groupUniqArray(agent_name)                            AS called_by_agents
FROM mcp_tool_calls
WHERE started_at >= now() - INTERVAL {hours} HOUR
  AND span_type = 'tool_call'
GROUP BY server_name
```

No materialized view needed for v1 — these queries are fast over the existing `mcp_tool_calls` table for 7-day windows. Add MVs later if query latency exceeds 500ms.

---

## API Design

### `GET /api/agents/lineage`

Returns the full graph for the requested time window.

**Query params:**
- `hours` (int, default 168 = 7 days) — time window
- `project_id` (string, optional) — project scope
- `level` (string, default "server") — "server" (agent→server) or "tool" (agent→server→tool)

**Response:**

```json
{
  "window_hours": 168,
  "nodes": [
    {
      "id": "agent:orchestrator",
      "type": "agent",
      "label": "orchestrator",
      "metrics": {
        "total_calls": 4820,
        "error_count": 12,
        "error_rate": 0.25,
        "avg_latency_ms": 142.5,
        "sessions": 340,
        "servers_used": ["postgres-mcp", "jira-mcp", "slack-mcp"]
      }
    },
    {
      "id": "server:postgres-mcp",
      "type": "server",
      "label": "postgres-mcp",
      "metrics": {
        "total_calls": 3200,
        "error_count": 5,
        "error_rate": 0.16,
        "avg_latency_ms": 31.2,
        "called_by_agents": ["orchestrator", "support-agent"]
      }
    }
  ],
  "edges": [
    {
      "source": "agent:orchestrator",
      "target": "server:postgres-mcp",
      "type": "calls",
      "metrics": {
        "call_count": 2100,
        "error_count": 3,
        "avg_latency_ms": 28.4,
        "session_count": 310
      }
    },
    {
      "source": "agent:orchestrator",
      "target": "agent:billing-agent",
      "type": "handoff",
      "metrics": {
        "handoff_count": 85,
        "session_count": 85
      }
    }
  ]
}
```

### `GET /api/agents/lineage/{node_id}/impact`

Blast radius analysis: "What breaks if this node goes down?"

**Response:**
```json
{
  "node": "server:postgres-mcp",
  "dependent_agents": ["orchestrator", "support-agent", "data-analyst"],
  "dependent_sessions_7d": 1240,
  "downstream_tools": [
    { "agent": "orchestrator", "tools": ["query", "list_tables"] },
    { "agent": "support-agent", "tools": ["query", "describe_table"] }
  ],
  "estimated_impact": "3 agents, 1,240 sessions in last 7 days"
}
```

---

## Dashboard UI

### Current dashboard UX

Lineage is now embedded in the **Agents** experience rather than a standalone page.

**Shipped surfaces:**
- **Agents page, selected agent** — focused topology for one agent plus summary metrics
- **Agents page, Topology modal** — fleet-wide graph of agents, MCP servers, and handoffs
- **Session detail page (`/sessions/[id]`)** — per-session lineage using the same graph renderer

**Current interactions:**
- Click node → inline detail card / side panel with metrics
- Click edge → inspect per-path call counts, errors, latency, tools, and tokens
- Expand/collapse multi-caller servers
- Expand an agent→server edge into individual tool/per-call nodes
- Pan, zoom, search, minimap, and error-path highlighting

### Technology choice

**Raw SVG + `dagre`** via `dashboard/components/lineage-graph.tsx`

Why the implementation changed:
- shared renderer across session and agent topology views
- tighter control over custom node/edge behaviour
- no React Flow runtime or dependency footprint
- easier per-edge expansion into tool and call nodes within the same canvas

---

## Implementation Status

### Shipped

| Area | Status |
|------|--------|
| `src/langsight/storage/clickhouse.py` `get_lineage_graph()` | ✅ Shipped |
| `src/langsight/api/routers/lineage.py` `GET /api/agents/lineage` | ✅ Shipped |
| `dashboard/lib/api.ts` `getLineageGraph()` | ✅ Shipped |
| `dashboard/lib/types.ts` lineage graph types | ✅ Shipped |
| Shared SVG topology renderer | ✅ Shipped |
| Agents page topology integration | ✅ Shipped |
| Session detail page lineage integration | ✅ Shipped |
| Lineage protocol v1.0 — SDK model fields (`target_agent_name`, `lineage_provenance`, `lineage_status`, `schema_version`) | ✅ Shipped (2026-04-01) |
| `llm_intent` span type — separates LLM decisions from tool executions | ✅ Shipped (2026-04-01) |
| Async-safe `contextvars` pending-tool tracking | ✅ Shipped (2026-04-01) |
| `LangSightClient.create_handoff()` / `wrap_child_agent()` helpers | ✅ Shipped (2026-04-01) |
| ClickHouse 4-column schema migration for lineage | ✅ Shipped (2026-04-01) |
| Handoff edge query with `target_agent_name` + `explicit_count`/`inferred_count` | ✅ Shipped (2026-04-01) |
| Ingest lineage validation (parent batch check, legacy upgrade, trace consistency) | ✅ Shipped (2026-04-01) |
| Lineage-aware integration adapters (OpenAI Agents, Anthropic, LangChain) | ✅ Shipped (2026-04-01) |
| Dashboard `llm_intent` + lineage types in `types.ts` and `session-graph.ts` | ✅ Shipped (2026-04-01) |

### Deferred / not shipped

| Area | Status |
|------|--------|
| `GET /api/agents/lineage/{node_id}/impact` | Not shipped |
| Dedicated `/lineage` page | Replaced by `/agents` topology experience |
| Separate React Flow node/component tree | Replaced by shared SVG renderer |
| Explicit blast-radius modal | Not shipped as a separate flow |

---

## What This Unlocks

### Immediate value
- **Impact analysis**: "postgres-mcp is down → these 3 agents are affected"
- **Architecture visibility**: "I didn't know billing-agent calls crm-mcp"
- **Bottleneck detection**: thick edge + high latency = congestion point

### Future extensions (not in v1)
- **Diff lineage across time**: "What changed in the last deploy?"
- **Lineage-based alerting**: "Alert when a new agent→server edge appears"
- **Cost flow**: overlay cost attribution on edges (cost per call × volume)
- **Lineage-based replay**: "Replay all sessions that touched this tool"
- **OpenLineage export**: emit lineage events in OpenLineage format for data catalog integration

---

## Positioning Value

This feature earns the "action-layer observability" claim honestly:

| Competitor | Has session traces | Has lineage graph |
|---|---|---|
| LangSmith | Yes (reasoning) | No |
| Langfuse | Yes (LLM calls) | No |
| Datadog LLM Obs | Yes (spans) | No |
| OpenLIT | Yes (OTEL) | No |
| Data tools (dbt, Airflow) | No | Yes (data lineage) |
| **LangSight** | **Yes (tool calls)** | **Yes (agent action lineage)** |

The marketing writes itself: "The first lineage graph for AI agent actions."

---

## Acceptance Criteria

- [x] `GET /api/agents/lineage` returns nodes + edges from real span data
- [ ] `GET /api/agents/lineage/{node_id}/impact` returns blast radius
- [x] Project scoping works on the lineage graph response
- [x] Dashboard renders an interactive DAG
- [x] Click node → detail panel with metrics
- [x] Edge thickness / labels reflect activity volume
- [x] Empty state exists when no lineage data is present
- [ ] Dedicated blast-radius interaction exists as a first-class flow
- [ ] Tests: add explicit lineage router/query coverage if not already present
- [x] Lineage protocol v1.0: explicit `target_agent_name` on handoff spans
- [x] Lineage protocol v1.0: `lineage_provenance` tracks how links were determined
- [x] Lineage protocol v1.0: `lineage_status` quality flag on every span
- [x] Lineage protocol v1.0: `schema_version` for forward compat
- [x] `llm_intent` span type separates LLM decisions from actual executions
- [x] Ingest validates lineage links on ingestion (parent batch check, legacy upgrade)
- [x] Integration adapters (OpenAI, Anthropic, LangChain) emit correct parent links
