# Auto-Capture Agent & MCP Server Reliability Platform

## Context

LangSight's moat is **agent runtime reliability** — "Your agent broke. Here's exactly why."
Langfuse watches the brain (prompts, evals). LangSight watches the hands (MCP calls, tool failures, cascading errors, budget overruns).

Today, onboarding requires manual wiring: engineers create separate callbacks per agent, manually register servers, and get flat tool-call lists instead of multi-agent trees. Production engineers expect `pip install langsight` + 2 lines → see full agent tree + health metrics.

---

## Competitive Landscape — Deep Analysis

### 1. Sentry AI Agents (`sentry_sdk.init()` + framework integrations)
**Onboarding**: `pip install sentry-sdk`, call `sentry_sdk.init()`, framework auto-detected
**What it captures**:
- Agent runs (invocations over time, error rates, duration)
- LLM calls (generation count, model used, token usage)
- Tool calls (volume, errors, per-tool duration)
- Handoffs between agents
- Model costs (estimated from token usage × pricing)
**Dashboard** (3 tabs):
- **Overview**: Traffic widget (runs + error rate), Duration, Issues, LLM Calls, Tokens Used, Tool Calls
- **Models**: Cost per model, token usage by model, token type breakdown
- **Tools**: Tool invocation volume, tool errors, per-tool duration + error counts
- **Traces**: Full execution tree with abbreviated (drawer) and detailed (full page) views
**Key insight**: They catch MCP's silent JSON-RPC errors (returned as responses, not thrown). Their trace view shows agent invocations → LLM → tool calls → handoffs as a tree.

### 2. Datadog LLM Observability (automatic SDK instrumentation)
**Onboarding**: `pip install ddtrace`, `DD_LLMOBS_ENABLED=1`, framework auto-detected
**What it captures**:
- **Operational**: Latency per operation, token usage, cost accumulation
- **Behavioral**: Tool selection patterns, agent handoffs, retries, error cascades, agent memory states, parallel activity, decision paths
- **Quality**: Functional evaluation results at individual agent steps, incorrect behaviors WITHOUT errors
**Dashboard**:
- **Graph-based execution flow**: Interactive node diagrams showing agent interactions
- **Fan-in/fan-out patterns** for parallel agents
- **Evaluation overlay on traces** — quality signals per step
- **Unified data model** — maps LangGraph, CrewAI, OpenAI Agent SDK to consistent trace format
**Key insight**: They capture behavioral correctness (wrong answer without error), not just failures. Their graph visualization for multi-agent flows is the gold standard.

### 3. Agent Monitor (cogniolab, open-source)
**Onboarding**: `monitor.wrap_openai(client)` / `monitor.wrap_anthropic(client)` / `monitor.wrap_langchain(agent)`
**What it captures**: Execution traces, per-task cost, performance metrics (p50/p95/p99), token usage, error rates
**Storage**: SQLite (dev) / PostgreSQL+TimescaleDB (prod)
**Dashboard**: Real-time traces, cost analytics, performance graphs, error replay
**Key insight**: Wrapper pattern is simple and effective. Storage split (SQLite dev / PG+TimescaleDB prod) mirrors our SQLite/ClickHouse split.

### 4. MCP Doctor (destilabs, static analysis)
**What it does**: Pre-deployment validation — tool description quality, token efficiency (>25k response = warning), security audit
**Not runtime** — complementary to monitoring. Rule-based, no LLM.
**Key insight**: We should add description quality + response size checks to `security-scan`.

### 5. Datadog MCP Client Monitoring (separate from agent monitoring)
**3 phases**: Session setup → `tools/list` registry → `call_tool` invocation
**Metrics**: Latency per phase, error rates, retry counts, tool distribution, JSON-RPC error codes
**Key insight**: Tracking all 3 MCP phases separately gives much better diagnostics than just tool calls.

### 6. OpenTelemetry GenAI SIG (standards in progress)
**Status**: Draft semantic conventions for agents, still evolving
**Namespace**: `gen_ai.agent.*` attributes
**Two patterns**: Baked-in (framework-native OTEL) or external instrumentation libraries
**Key insight**: OTEL interop matters for enterprise. Our OTLP endpoint already accepts standard traces.

### Where LangSight is unique (the moat)

| Capability | Sentry | Datadog | Langfuse | AgentMonitor | **LangSight** |
|------------|--------|---------|----------|--------------|---------------|
| Agent run tracing | ✅ | ✅ | ✅ (prompt/eval) | ✅ | ✅ |
| Multi-agent tree | ✅ (handoffs) | ✅ (graph viz) | ❌ | ❌ | ✅ parent_span_id |
| MCP tool call tracing | ✅ server-side | ✅ client-side | ❌ | ❌ | ✅ client-side |
| MCP health checks | ❌ | ❌ | ❌ | ❌ | **✅ active probing** |
| Schema drift detection | ❌ | ❌ | ❌ | ❌ | **✅ hash-based** |
| Tool poisoning detection | ❌ | ❌ | ❌ | ❌ | **✅ description mutation** |
| Loop detection + prevention | ❌ | ❌ | ❌ | ❌ | **✅ SDK-side** |
| Budget guardrails | ❌ | ❌ | ❌ | ❌ | **✅ SDK-side** |
| Circuit breaker | ❌ | ❌ | ❌ | ❌ | **✅ per-server** |
| OWASP MCP Top 10 scan | ❌ | ❌ | ❌ | ❌ | **✅ security scanner** |
| Agent SLOs | ❌ | via DD SLOs | ❌ | ❌ | **✅ native** |
| Cost tracking | ✅ (model costs) | ✅ | ✅ | ✅ | ✅ |
| Silent MCP error catch | ✅ | ❌ | ❌ | ❌ | **TODO** |

**Nobody else does prevention + active MCP health + security scanning. That's the moat.**
Sentry/Datadog observe. LangSight observes AND prevents AND secures.

---

## Part 0: Capture the Human Prompt

Every session starts with a human asking something. Without this, you see tool calls but not WHY.

### What the session trace should look like
```
Session: 845d3724-...
│
├── INPUT: "who are the top 5 customers by revenue?"
│
├── supervisor (agent, 9.2s)
│   ├── get_current_date (tool_call, 0.62ms, success)
│   ├── call_analyst (tool_call, 2944ms, success)
│   │   └── analyst (agent, 2900ms)
│   │       └── read_query (tool_call, 303ms, success)
│   └── [LLM: gemini-2.5-flash, 847 tokens]
│
├── OUTPUT: "The top 5 customers are: Company_036..."
│
├── HEALTH: ✅ healthy (no errors, no loops, under budget)
└── COST: $0.0012 (847 input + 312 output tokens)
```

### How to capture

**Auto-capture via `on_chat_model_start`** (recommended):
```python
def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs):
    if not self._session_input_captured:
        for msg in messages[0]:
            if hasattr(msg, 'type') and msg.type == 'human':
                self._session_input = msg.content
                self._session_input_captured = True
                break
```

**Plus explicit API for override**:
```python
cb.set_input(question)   # Before ainvoke
cb.set_output(answer)    # After ainvoke
```

Auto-capture fills it from LLM messages. Explicit calls override. Both work — explicit wins if set.

### Storage
- New fields on session: `input_text`, `output_text` in ClickHouse `session_metadata` table
- Or: emit as a special span with `span_type="session_io"` (simpler, no schema change)

---

## Part 1: Five Onboarding Paths

### Path A: SDK Auto-Detect (zero-config, instant)
The industry standard — `wrap()` or callback pattern. One function call, everything captured.

```python
from langsight.sdk import LangSightClient
from langsight.integrations.langchain import LangSightLangChainCallback

client = LangSightClient(url="http://localhost:8000", project_id="...")
cb = LangSightLangChainCallback(client=client, session_id=sid, trace_id=tid)

result = await supervisor.ainvoke(input, config={"callbacks": [cb]})
# That's it. Full tree captured. Agents + servers auto-discovered.
```

What happens automatically:
- Agent names detected from LangGraph graph names → auto-registered in catalog
- Server names from tool calls → auto-registered in catalog
- Tool schemas captured on `list_tools()` → stored in server_tools
- Parent-child tree built from `parent_span_id` → session trace view
- Health tag computed (healthy/degraded/failed) → per-session
- Prompt + answer captured → session context

### Path B: MCP SDK wrap() (for direct MCP usage, no LangChain)
```python
client = LangSightClient(url="http://localhost:8000", project_id="...")
traced = client.wrap(mcp_session, server_name="postgres-mcp", agent_name="my-agent")
result = await traced.call_tool("query", {"sql": "SELECT 1"})
```

### Path C: CLI Discovery (`langsight init`)
Already implemented. Scans Claude Desktop, Cursor, VS Code MCP configs.
```bash
langsight init          # Discovers MCP servers → generates .langsight.yaml
langsight mcp-health    # Active health check all discovered servers
langsight security-scan # OWASP + CVE scan all servers
langsight monitor       # Continuous monitoring loop
```

### Path D: Config File (`.langsight.yaml`)
```yaml
project: my-ai-app
agents:
  - name: supervisor
    owner: platform-team
    budget: { max_steps: 50, max_cost_usd: 1.00 }
  - name: analyst
    servers: [sqlite-mcp]
servers:
  - name: sqlite-mcp
    transport: stdio
    command: "uvx mcp-server-sqlite --db-path ./data.db"
    health_check: { interval: 30s }
    slo: { success_rate: 99.5%, p99_latency: 500ms }
```

### Path E: Dashboard UI + REST API
- Dashboard: "Add Agent" / "Add Server" buttons + auto-discovered list
- API: `PUT /api/agents/metadata/{name}`, `PUT /api/servers/metadata/{name}`
- Discovery: `POST /api/agents/discover`, `POST /api/servers/discover`

---

## Part 2: Unified LangChain Callback (Auto-Capture)

### Before → After

**Before** (3 callbacks, manual wiring):
```python
sup_cb = LangSightLangChainCallback(client=c, server_name="direct-tools", agent_name="supervisor", ...)
# Inside call_analyst tool:
ana_cb = LangSightLangChainCallback(client=c, server_name="sqlite", agent_name="analyst", ...)
```

**After** (1 callback, auto):
```python
cb = LangSightLangChainCallback(client=c, session_id=sid, trace_id=tid)
# Same cb passed to ALL ainvoke() calls — everything auto-detected
```

### Callback event flow → span tree

```
on_chain_start("supervisor", run_id=R1, parent_run_id=None)
  → Named agent, no parent → emit agent span (span_id=S1)

  on_chat_model_start(messages=[HumanMessage("top 5 customers...")])
    → Capture session input (first human message)

  on_tool_start("get_current_date", run_id=R2, parent_run_id=R1)
  on_tool_end(R2)
    → Emit tool_call span, parent=S1, agent="supervisor"

  on_tool_start("call_analyst", run_id=R3, parent_run_id=R1)
    → Push to _tool_execution_stack

    on_chain_start("analyst", run_id=R4, parent_run_id=None)
      → New agent, _tool_execution_stack has R3
      → Cross-ainvoke link: parent = call_analyst's span
      → Emit agent span (span_id=S4)

      on_tool_start("read_query", run_id=R5, parent_run_id=R4)
      on_tool_end(R5)
        → Emit tool_call span, parent=S4, agent="analyst"

    on_chain_end(R4) → Finalize analyst agent span

  on_tool_end(R3) → Pop stack, emit call_analyst tool span

on_chain_end(R1) → Finalize supervisor agent span
```

### Agent detection

Not every `on_chain_start` is an agent. Skip framework internals:

```python
_SKIP = frozenset({
    "RunnableSequence", "RunnableLambda", "RunnableParallel",
    "RunnablePassthrough", "RunnableBranch", "RunnableAssign",
    "ChannelWrite", "ChannelRead", "PregelNode",
    "ChatPromptTemplate", "PromptTemplate",
    "StrOutputParser", "JsonOutputParser",
})

def _is_agent(serialized, metadata) -> str | None:
    name = serialized.get("name", "")
    if not name or name in _SKIP:
        return None
    node = (metadata or {}).get("langgraph_node")
    if node in ("tools", "__start__", "__end__"):
        return None
    return name
```

### Cross-ainvoke parent linking

When `analyst.ainvoke()` fires inside `call_analyst` tool, there's NO `parent_run_id` from LangChain. Solution: thread-local tool stack.

```python
self._local = threading.local()

@property
def _tool_stack(self):
    if not hasattr(self._local, "stack"):
        self._local.stack = []
    return self._local.stack
```

`on_tool_start` → push. `on_chain_start` with no parent + non-empty stack → link to top. `on_tool_end` → pop. Thread-local prevents parallel sub-agent corruption.

### Backward compatibility
- `LangSightLangChainCallback(client, server_name="x", agent_name="y")` → fixed mode (existing)
- `LangSightLangChainCallback(client)` → auto-detect mode (new)
- `LangSightLangGraphCallback` → alias to unified callback

---

## Part 3: What to Capture — Attributes & Metrics

### Per-Span Attributes (already in ToolCallSpan model)

| Attribute | Type | Source | Notes |
|-----------|------|--------|-------|
| `span_id` | string | Generated | UUID per span |
| `parent_span_id` | string? | Callback | Tree construction |
| `span_type` | enum | Callback | `tool_call`, `agent`, `handoff` |
| `trace_id` | string | User | Groups entire task |
| `session_id` | string | User | Groups conversation |
| `server_name` | string | Callback/wrap | MCP server identity |
| `tool_name` | string | Callback/wrap | Tool being called |
| `agent_name` | string? | Callback | Which agent emitted this |
| `status` | enum | SDK | `success`, `error`, `timeout`, `prevented` |
| `latency_ms` | float | Computed | ended_at - started_at |
| `input_args` | json? | SDK | Tool input (redactable) |
| `output_result` | string? | SDK | Tool output (redactable) |
| `error` | string? | SDK | Error message if failed |
| `input_tokens` | int? | OTLP/LLM | LLM input tokens |
| `output_tokens` | int? | OTLP/LLM | LLM output tokens |
| `model_id` | string? | OTLP/LLM | Model used |
| `project_id` | string | SDK/API | Project isolation |

### Per-Session Metrics (computed from spans)

| Metric | How Computed | Dashboard Widget |
|--------|-------------|------------------|
| **Total duration** | last_span.ended_at - first_span.started_at | Duration chart |
| **Tool call count** | COUNT(span_type='tool_call') | Traffic widget |
| **Error count** | COUNT(status='error' OR status='timeout') | Error rate |
| **Success rate** | success_calls / total_calls × 100 | % indicator |
| **Total cost** | SUM(input_tokens × price + output_tokens × price) | Cost widget |
| **Agents used** | DISTINCT(agent_name) | Agent list |
| **Servers used** | DISTINCT(server_name) | Server list |
| **Max depth** | Max tree depth from parent_span_id | Complexity indicator |
| **Loop detected** | SDK prevention event | Warning badge |
| **Budget status** | steps_used / max_steps, cost_used / max_cost | Progress bar |
| **Health tag** | healthy / degraded / failed / looping | Status badge |

### Per-Agent Aggregate Metrics (from Sentry/Datadog patterns)

| Metric | Time Window | Dashboard |
|--------|------------|-----------|
| **Runs over time** | 1h/24h/7d/30d | Traffic chart (like Sentry) |
| **Error rate trend** | 1h/24h/7d | Line chart with threshold |
| **p50/p95/p99 duration** | 24h | Latency percentile chart |
| **Cost per run** | 24h/7d | Cost histogram |
| **Token usage by model** | 24h | Stacked bar (like Sentry Models tab) |
| **Tool call distribution** | 24h | Tool popularity chart |
| **Tool error hotspots** | 24h | Table: tool × error_rate |
| **Delegation patterns** | 7d | Which sub-agents called |
| **Loop frequency** | 7d | Count of loop-detected sessions |
| **Budget violations** | 7d | Count of budget-exceeded sessions |

### Per-MCP-Server Metrics

| Metric | Source | Dashboard |
|--------|--------|-----------|
| **Availability** | Active health probe | Uptime % badge |
| **Success rate** | Passive spans | % over time |
| **p50/p95/p99 latency** | Passive spans | Latency chart |
| **Tool call volume** | Passive spans | Traffic chart |
| **Tool errors by type** | Passive spans | Error breakdown |
| **Schema drift events** | Active probe | Timeline |
| **Tool count** | Active probe / list_tools | Current count |
| **Client agents** | Passive spans | Which agents use this server |
| **Transport type** | Config/probe | stdio/SSE/HTTP badge |
| **Last seen** | Passive spans | Timestamp |

---

## Part 4: MCP Server Health Monitoring

### Two modes (both needed)

**Passive (from traces)**: SDK intercepts `call_tool()`, records spans. Gives success rates, latency, errors from real traffic.

**Active (health probes)**: `HealthChecker` pings servers on schedule. Gives availability, schema drift, poisoning — even when no traffic is flowing.

### Silent MCP error detection (from Sentry)

MCP SDK returns errors as JSON-RPC responses, not Python exceptions. Fix in `MCPClientProxy.call_tool()`:

```python
result = await client.call_tool(name, arguments)
# MCP returns errors as content with isError=True
if hasattr(result, 'isError') and result.isError:
    status = ToolCallStatus.ERROR
    error = _extract_mcp_error(result)
```

### 3-phase MCP tracking (from Datadog)

| Phase | Operation | What to Track |
|-------|-----------|---------------|
| 1. Session setup | `stdio_client()` / `sse_client()` | Connection time, transport errors |
| 2. Registry discovery | `list_tools()` | Tool count, schema hash, latency |
| 3. Tool invocation | `call_tool()` | Already captured |

Phase 1+2 tracking is future work (separate PR). Phase 3 is already captured.

---

## Part 5: Auto-Discovery (agents + servers from traces)

### Inline auto-register on span ingestion

When `/api/traces/spans` receives spans, auto-register unseen agents/servers immediately:

```python
# In-memory cache to avoid DB lookups on every span
_seen_agents: set[str] = set()
_seen_servers: set[str] = set()

async def ingest_spans(spans, request):
    for span in spans:
        if span.agent_name and span.agent_name not in _seen_agents:
            _seen_agents.add(span.agent_name)
            await storage.upsert_agent_metadata(agent_name=span.agent_name, ...)
        if span.server_name and span.server_name not in _seen_servers:
            _seen_servers.add(span.server_name)
            await storage.upsert_server_metadata(server_name=span.server_name, ...)
```

### Batch discovery endpoints

- `POST /api/agents/discover` — scan ClickHouse for distinct `agent_name` values (mirrors existing server discover)
- `POST /api/servers/discover` — already implemented (fixed in this session)

---

## Part 6: Dashboard Structure (inspired by Sentry + Datadog)

### Agent Sessions Page (existing, enhance)
- **Traffic**: Runs over time + error rate overlay
- **Duration**: p50/p95/p99 latency distribution
- **Session list**: Table with status, duration, cost, tool calls, health tag
- Click session → **Trace view** with full tree

### Agent Detail Page (per agent)
- **Overview**: Success rate, avg duration, avg cost, runs today
- **Tools tab**: Tool call distribution, error hotspots, latency per tool
- **Models tab**: Token usage by model, cost breakdown
- **Prevention**: Loop detections, budget violations, circuit breaker events
- **Config**: Budget settings, SLO thresholds, alert rules

### MCP Server Detail Page (per server)
- **Health**: Current status (up/degraded/down), uptime %, last check time
- **Performance**: Success rate, latency percentiles, tool call volume
- **Tools**: Declared tools list with schemas, per-tool metrics
- **Schema**: Current hash, drift history timeline
- **Security**: Last scan results, OWASP findings
- **Clients**: Which agents use this server

### Topology Page (lineage view, existing `/api/agents/lineage`)
- Interactive graph: Agent nodes + Server nodes + edges from traces
- Health status overlaid on each node (green/yellow/red)
- Click node → detail page

---

## Part 7: Real-World Topology Patterns

| Pattern | Description | How LangSight Handles |
|---------|-------------|----------------------|
| **Simple** | 1 agent → 1 MCP server | `wrap()` or single callback |
| **Multi-agent orchestrator** | supervisor → analyst → writer | Unified callback + cross-ainvoke linking |
| **Shared servers** | agent-A + agent-B → same postgres-mcp | `server_name` per-span, dashboard shows which agents |
| **Dynamic agents** | orchestrator spawns agents on demand | Auto-discover on first span |
| **Sequential handoff** | intake → triage → specialist → resolution | `span_type="handoff"` captures delegation chain |
| **Human-in-the-loop** | agent → ask_human → WAIT → continue | `session_id` groups all; wall time captures wait |
| **Parallel sub-agents** | fan-out to N researchers, fan-in to synthesizer | Thread-local stack handles concurrent callbacks |
| **Multi-framework** | LangGraph + OpenAI Agents + Anthropic | Shared `trace_id` + `session_id` across integrations |
| **MCP server chains** | agent → gateway-mcp → internal-mcp | Future: server-side SDK |

---

## Implementation Plan (file by file)

### Phase A: Auto-Capture Callback (core change)

**Step 1**: `src/langsight/integrations/base.py`
- Extend `_record()` with optional `parent_span_id`, `span_type`, `server_name` override, `agent_name` override

**Step 2**: `src/langsight/integrations/langchain.py` (major rewrite)
- Merge langgraph.py chain tracking
- Add `on_chain_start`/`on_chain_end` → agent span emission
- Add `on_chat_model_start` → prompt capture
- Add `_tool_execution_stack` (thread-local) → cross-ainvoke linking
- Add `_is_agent()` detection heuristic
- Add `set_input()`/`set_output()` for explicit prompt/answer
- Auto-detect mode when `server_name` is None; fixed mode when provided

**Step 3**: `src/langsight/integrations/langgraph.py`
- Shrink to alias: `LangSightLangGraphCallback = LangSightLangChainCallback`

### Phase B: Auto-Discovery

**Step 4**: `src/langsight/storage/clickhouse.py`
- Add `get_distinct_span_agent_names(project_id)` (mirrors server version)

**Step 5**: `src/langsight/api/routers/agents.py`
- Add `POST /api/agents/discover` endpoint

**Step 6**: `src/langsight/api/routers/traces.py`
- Inline auto-register agents + servers on span ingestion
- In-memory set cache to avoid DB round-trips

### Phase C: Silent MCP Error Detection

**Step 7**: `src/langsight/sdk/client.py`
- In `MCPClientProxy.call_tool()`: check `result.isError` on MCP response
- Set `status=ERROR` when MCP returns error content

### Phase D: Tests

**Step 8**: `tests/unit/integrations/test_langchain.py` (expand)
- TestAutoDetectMode, TestAgentSpanEmission, TestCrossAinvokeLinking
- TestToolStack, TestPromptCapture, TestBackwardCompat, TestSilentMCPErrors

**Step 9**: `tests/unit/integrations/test_langgraph.py` (simplify to alias test)

**Step 10**: `tests/unit/api/test_agents_discover.py` (new)

### Phase E: E2E Validation

**Step 11**: Update e2e test app (`AI-agent-e2e/main.py`)
- Simplify to one-callback pattern
- Add `cb.set_input(question)` / `cb.set_output(answer)`
- Verify full tree: `supervisor → analyst → read_query`

---

## Files Changed (summary)

| File | Change | Size |
|------|--------|------|
| `src/langsight/integrations/base.py` | Extend `_record()` signature | S |
| `src/langsight/integrations/langchain.py` | Unified auto-capture callback | **L** |
| `src/langsight/integrations/langgraph.py` | Shrink to alias | S |
| `src/langsight/sdk/client.py` | Silent MCP error detection | S |
| `src/langsight/storage/clickhouse.py` | `get_distinct_span_agent_names()` | S |
| `src/langsight/api/routers/agents.py` | `POST /agents/discover` | M |
| `src/langsight/api/routers/traces.py` | Inline auto-register on ingestion | M |
| `tests/unit/integrations/test_langchain.py` | Expand tests | **L** |
| `tests/unit/integrations/test_langgraph.py` | Simplify to alias test | S |
| `tests/unit/api/test_agents_discover.py` | New test file | M |

---

## Verification Plan

1. `uv run pytest tests/unit/integrations/` — all tests pass
2. `uv run ruff check src/ && uv run ruff format src/` — clean
3. Rebuild: `docker compose build api && docker compose up -d api`
4. Run e2e: `cd AI-agent-e2e && time python3 main.py "who are the top 5 customers by revenue?"`
5. ClickHouse:
   - `SELECT * FROM mcp_tool_calls WHERE span_type='agent'` → supervisor, analyst
   - `SELECT tool_name, parent_span_id FROM mcp_tool_calls WHERE session_id=...` → tree
6. `POST /api/agents/discover` → auto-discovered agents
7. `GET /api/agents/sessions/{session_id}` → nested tree
8. Dashboard at localhost:3003 → session view shows full tree

---

## What's NOT in this PR (future work)

- MCP 3-phase tracking (session setup + registry latency)
- Tool description quality scoring (MCP Doctor patterns → add to security-scan)
- `mv_agent_health` materialized view (server-side agent metrics aggregation)
- Lineage graph with health status overlay
- Config-based agent registration on `langsight serve` startup
- Response size tracking (add output_bytes to ToolCallSpan)
- Behavioral correctness evaluation (Datadog pattern — wrong answer without error)
- Cascading failure detection (ML anomaly detection on cross-agent errors)
- Graph-based execution flow visualization (Datadog-style interactive node diagram)
