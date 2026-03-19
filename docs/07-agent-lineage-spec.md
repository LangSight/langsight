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

### Lineage page (`/lineage`)

New top-level nav item between "Sessions" and "Health".

**Layout:**
```
┌─────────────────────────────────────────────────────────┐
│  Agent Action Lineage          [7d ▾] [project ▾]      │
├─────────────────────────────────────────────────────────┤
│                                                         │
│   ┌──────────┐        ┌──────────────┐                  │
│   │orchestr- │───────►│ postgres-mcp │                  │
│   │ator      │──┐     │  5 tools     │                  │
│   └──────────┘  │     └──────────────┘                  │
│        │        │                                       │
│        │        │     ┌──────────────┐                  │
│        │ handoff└────►│ jira-mcp     │                  │
│        ▼              │  3 tools     │                  │
│   ┌──────────┐        └──────────────┘                  │
│   │billing-  │                                          │
│   │agent     │───────►┌──────────────┐                  │
│   └──────────┘        │ crm-mcp      │                  │
│                       │  2 tools     │                  │
│                       └──────────────┘                  │
│                                                         │
├─────────────────────────────────────────────────────────┤
│  Selected: postgres-mcp                                 │
│  Called by: orchestrator, support-agent                  │
│  3,200 calls · 0.16% error rate · avg 31ms              │
│  [View sessions →]  [Blast radius →]                    │
└─────────────────────────────────────────────────────────┘
```

**Interactions:**
- Click node → detail panel slides in from bottom (metrics, recent errors, sessions link)
- Click "Blast radius" → highlight all upstream agents that depend on this node
- Edge thickness → proportional to call volume
- Edge color → green (healthy), yellow (>1% errors), red (>5% errors)
- Time window selector (1h, 24h, 7d, 30d)
- Toggle: server level ↔ tool level (tool level expands servers into individual tools)

### Technology choice

**React Flow** (`@xyflow/react`) — the standard for DAG rendering in React:
- Built-in layout engines (dagre, elk)
- Custom node/edge components
- Pan, zoom, minimap out of the box
- Used by n8n, Langflow, Windmill, Buildship

Not D3 — too low-level for this use case. React Flow gives us interactive DAGs in ~200 lines.

---

## Implementation Plan

### Phase 1: Backend + API (1 day)

**Files:**

| File | Change |
|------|--------|
| `src/langsight/storage/clickhouse.py` | Add `get_lineage_graph()` and `get_lineage_impact()` methods |
| `src/langsight/api/routers/lineage.py` | New router: `GET /api/agents/lineage`, `GET /api/agents/lineage/{node_id}/impact` |
| `src/langsight/api/main.py` | Register lineage router |
| `tests/unit/api/test_lineage_router.py` | Unit tests with mocked storage |

**ClickHouse methods:**
```python
async def get_lineage_graph(
    self,
    hours: int = 168,
    level: str = "server",  # "server" | "tool"
    project_id: str | None = None,
) -> dict[str, Any]:
    """Return nodes + edges for the lineage DAG."""
    # 1. Query agent→server edges
    # 2. Query agent→agent handoff edges
    # 3. Optionally query agent→tool edges (level="tool")
    # 4. Query node-level metrics
    # 5. Assemble {nodes, edges} response
```

### Phase 2: Dashboard page (1-2 days)

**Files:**

| File | Change |
|------|--------|
| `dashboard/app/(dashboard)/lineage/page.tsx` | New page with React Flow graph |
| `dashboard/components/lineage/` | `AgentNode.tsx`, `ServerNode.tsx`, `ToolNode.tsx`, `LineageEdge.tsx` |
| `dashboard/lib/api.ts` | Add `getLineageGraph()`, `getLineageImpact()` |
| `dashboard/lib/types.ts` | Add `LineageGraph`, `LineageNode`, `LineageEdge` types |
| `dashboard/components/sidebar.tsx` | Add "Lineage" nav item |

**Dependencies to add:**
```bash
cd dashboard && npm install @xyflow/react dagre @types/dagre
```

**Custom nodes (React Flow):**
- `AgentNode` — blue card, shows agent name + call count + error rate sparkline
- `ServerNode` — green card (healthy) / yellow (degraded) / red (down), shows server name + tool count
- `ToolNode` — small pill inside server node (tool-level view only)

**Layout:**
- Use `dagre` for automatic left-to-right DAG layout
- Agents on the left, servers on the right, handoff edges between agents
- Edges: bezier curves, animated when data is flowing

### Phase 3: Blast radius + polish (1 day)

- Blast radius panel: click server → highlight all upstream agents in red
- "What if this server goes down?" modal with impact summary
- Edge click → show the specific tool calls between that agent and server
- Link from lineage node → filtered sessions list
- Link from health page → lineage view centered on that server

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

- [ ] `GET /api/agents/lineage` returns nodes + edges from real span data
- [ ] `GET /api/agents/lineage/{node_id}/impact` returns blast radius
- [ ] Project scoping works (non-admin users see only their project's lineage)
- [ ] Dashboard renders interactive DAG with React Flow
- [ ] Click node → detail panel with metrics
- [ ] Click "Blast radius" → highlights dependent agents
- [ ] Edge thickness reflects call volume, color reflects error rate
- [ ] Time window selector works (1h, 24h, 7d, 30d)
- [ ] Empty state: "No agent sessions recorded yet. Instrument your first agent."
- [ ] Tests: unit tests for router + ClickHouse query builder
