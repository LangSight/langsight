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

---

## Data Model

All required data already exists in `mcp_tool_calls`:

```
span_id, parent_span_id, span_type, trace_id, session_id,
server_name, tool_name, agent_name, status, latency_ms, project_id
```

Span types: `tool_call` (agent → tool), `handoff` (agent → agent), `agent` (lifecycle).

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

```sql
SELECT
    agent_name                           AS from_agent,
    -- Extract target agent from tool_name: "→ billing-agent" → "billing-agent"
    replaceOne(tool_name, '→ ', '')      AS to_agent,
    count()                              AS handoff_count,
    uniq(session_id)                     AS session_count
FROM mcp_tool_calls
WHERE started_at >= now() - INTERVAL {hours} HOUR
  AND span_type = 'handoff'
  AND agent_name != ''
  {project_filter}
GROUP BY agent_name, tool_name
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
