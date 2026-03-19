# LangSight: Architecture Design

> **Version**: 1.1.0
> **Date**: 2026-03-17
> **Status**: Active — updated with SDK, LibreChat integration, and integration paths (decided 2026-03-17)

---

## 1. System Architecture Overview

```
  Integration Paths (Phase 2)        LangSight Platform
  ─────────────────────────────────  ─────────────────────────────────────────────
                                     ┌───────────────────────────────────────────┐
  Python agents (CrewAI, Pydantic    │                                           │
  AI, OpenAI Agents SDK)             │  ┌───────────────┐  ┌──────────────────┐  │
         │                           │  │  MCP Health    │  │  MCP Security    │  │
         │  LangSight SDK             │  │  Checker       │  │  Scanner         │  │
         │  wrap(mcp_client)          │  │  (Python)      │  │  (Python)        │  │
         ▼                           │  └───────┬───────┘  └────────┬─────────┘  │
  ┌──────────────────┐               │          │                   │            │
  │  LangSight SDK   │──── spans ───►│  ┌───────▼───────────────────▼─────────┐  │
  │  (Python client) │               │  │   FastAPI REST API                   │  │
  └──────────────────┘               │  │   /api/health/*  /api/security/*     │  │
                                     │  │   /api/traces/spans  /api/status     │  │
  LibreChat                          │  └───────────────────┬─────────────────┘  │
         │                           │                      │                    │
         │  LANGSIGHT_URL env var     │          ┌──────────▼──────────┐          │
         │  (~50-line JS plugin)      │          │  Storage Layer      │          │
         ▼                           │          │  SQLite (local)     │          │
  ┌──────────────────┐               │          │  PostgreSQL (prod)  │          │
  │  LangSight       │──── spans ───►│          │  ClickHouse (Ph.3)  │          │
  │  LibreChat Plugin│               │          └─────────────────────┘          │
  └──────────────────┘               │                                           │
                                     │  ┌───────────────┐  ┌──────────────────┐  │
  Agent Frameworks (Phase 3)         │  │  CLI (Click)  │  │  Slack/Webhook   │  │
  (OTEL-capable: Pydantic AI,        │  │  langsight    │  │  Alerts          │  │
   Strands, AG2)                     │  └───────────────┘  └──────────────────┘  │
         │                           │                                           │
         │  OTLP spans               │  ┌──────────────────────────────────────┐  │
         ▼                           │  │  Next.js Dashboard (Phase 4)         │  │
  ┌──────────────┐                   │  └──────────────────────────────────────┘  │
  │ OTEL         │──── OTLP ────────►│                                           │
  │ Collector    │                   └───────────────────────────────────────────┘
  └──────────────┘

  MCP Servers (health-checked directly by LangSight)
  ┌──────────┐  ┌──────────┐  ┌──────────┐
  │ server-1 │  │ server-2 │  │ server-N │
  └──────────┘  └──────────┘  └──────────┘
       ▲              ▲             ▲
       └──────────────┴─────────────┘
          MCP Health Checker (JSON-RPC)
```

---

## 2. Components

### 2.1 MCP Health Checker

**Purpose**: Continuously monitors MCP server health — availability, latency, schema changes, output freshness.

**How it works**:
- Connects to MCP servers via their configured transport (stdio, SSE, StreamableHTTP)
- Runs periodic health checks:
  - **Ping**: JSON-RPC `initialize` call — is the server responding?
  - **Tools list**: `tools/list` call — has the tool schema changed?
  - **Sample invocation**: Optional — call a known-safe tool with test params to validate output
- Records results in ClickHouse (timestamp, server, status, latency, schema hash)
- Manages server state transitions: `UP → DEGRADED → DOWN → STALE`

**Key design decisions**:
- Polling-based (not event-driven) — MCP servers don't push health status
- Configurable intervals per server (default: 30s for health, 5min for schema check)
- Rate limiting built in — never send more than N checks/min to a single server
- Schema tracking via hash comparison — store full schema snapshot on change

### 2.2 MCP Security Scanner

**Purpose**: Scans MCP server configurations for security vulnerabilities, known CVEs, and active threats.

**How it works**:
- **CVE matching**: Compares server name + version against a local CVE database (sourced from NVD + GitHub Advisory + MCP-specific advisories)
- **OWASP MCP Top 10 checks**: Automated checks for each category (tool poisoning, excessive permissions, no auth, etc.)
- **Tool poisoning detection**: Captures baseline tool descriptions at first scan, alerts on mutations (hash comparison)
- **Auth audit**: Checks for missing auth, long-lived tokens, overly broad permissions
- Produces a scored report (0-10 overall, per-category scores)

**Scan modes**:
- **One-time**: `agentguard security-scan` — runs and exits
- **Continuous**: Part of `agentguard monitor` — periodic re-scans to detect rug-pull attacks

**Key design decisions**:
- CVE database is a local JSON file, updated via `agentguard update-cves` or on startup
- Tool poisoning detection requires a baseline — first scan establishes it
- Scanner reads MCP server configs from .agentguard.yaml, not from the servers themselves

### 2.3 OTEL Trace Ingestion

**Purpose**: Accepts OpenTelemetry spans from agent frameworks, extracts MCP tool call data, stores in ClickHouse.

**How it works**:
- OTEL Collector (contrib build) receives OTLP spans on ports 4317 (gRPC) / 4318 (HTTP)
- Collector exports to ClickHouse via built-in ClickHouse exporter
- AgentGuard adds materialized views on top of standard OTEL schema to extract:
  - Tool call spans (tool name, success/fail, latency, params, response)
  - LLM call spans (model, tokens, cost)
  - Agent spans (agent name, task, handoffs)

**LLM reasoning capture** (added P5.3, 2026-03-19): OTLP spans carrying `gen_ai.prompt`/`gen_ai.completion` (or `llm.prompts`/`llm.completions`) are detected in the OTLP parser and stored as `span_type="agent"` spans with `llm_input`/`llm_output` fields populated. Model name is extracted from `gen_ai.request.model` or `llm.model_name` and written to the `tool_name` column. These spans surface as "Prompt"/"Completion" panels in the session trace tree, making the full reasoning context visible alongside tool calls. The attribute parser also handles `intValue`, `doubleValue`, and `boolValue` attribute types in addition to `stringValue`.

**Key design decisions**:
- We do NOT build custom instrumentation — we accept standard OTEL GenAI spans
- Works with any framework that emits OTEL: Pydantic AI, Strands, AG2, Claude Agent SDK
- For frameworks without OTEL (OpenAI Agents SDK), community instrumentors exist
- ClickHouse schema extends the standard OTEL trace schema, not replaces it

### 2.4 Tool Reliability Engine

**Purpose**: Aggregates MCP tool call data into reliability metrics — success rates, latency distributions, error patterns.

**How it works**:
- ClickHouse materialized views aggregate tool call spans into time-bucketed metrics
- Computes: success rate, error rate, p50/p95/p99 latency, call volume, retry rate
- Categorizes failures: timeout, connection_error, invalid_response, schema_mismatch, stale_data, auth_error, rate_limited
- Correlates: tool failure rate → agent task failure rate (via trace/session IDs)

**Statistical anomaly detection** (added P5.4, 2026-03-19): `AnomalyDetector` in `src/langsight/reliability/engine.py` computes a per-tool z-score by fetching a 7-day baseline (mean + stddev via `stddevPop()`) from `mv_tool_reliability` and comparing it against the current window (default: last 1 hour). Anomalies fire at |z| >= 2.0 (configurable `z_threshold`), with severity `warning` at |z| >= 2 and `critical` at |z| >= 3. Both `error_rate` and `avg_latency_ms` metrics are evaluated. Baseline and current queries run concurrently via `asyncio.gather()`. Minimum stddev guards (`_MIN_STDDEV_ERROR_RATE = 0.01`, `_MIN_STDDEV_LATENCY_MS = 10.0`) prevent false positives on perfectly stable tools. The engine requires >= 3 sample hours in the baseline window before returning results. Exposed via `GET /api/reliability/anomalies?current_hours=1&baseline_hours=168&z_threshold=2.0` and surfaced in the dashboard Overview as an "Anomalies Detected" card.

**SLO tracking** (added P5.5, 2026-03-19): `SLOEvaluator` in `src/langsight/reliability/engine.py` evaluates user-defined `AgentSLO` records against live session data returned by `get_agent_sessions()`. Two metric types are supported: `success_rate` (computed as `(clean_sessions / total_sessions) * 100`) and `latency_p99` (uses `max(duration_ms)` as a conservative proxy — true p99 requires raw span data, not session aggregates). SLO definitions are persisted in the `agent_slos` table in both SQLite and PostgreSQL backends. Evaluation produces `SLOEvaluation` records with status `ok`, `breached`, or `no_data`. The full CRUD surface (`POST /api/slos`, `GET /api/slos`, `GET /api/slos/status`, `DELETE /api/slos/{slo_id}`) is exposed via `src/langsight/api/routers/slos.py`. The dashboard Overview page polls `/api/slos/status` every 60s and renders an "Agent SLOs" panel when SLOs are defined.

**Key design decisions**:
- All computation happens in ClickHouse (no separate analytics engine)
- Time buckets: 1min (real-time), 1hr (dashboards), 1day (trends)
- Baselines learned from 7-day rolling window of `mv_tool_reliability` data — anomalies fire on z-score deviation (P5.4, implemented 2026-03-19); threshold-based alerts remain alongside for rule-based triggers
- SLO `latency_p99` intentionally uses `max(duration_ms)` rather than a true percentile (decided 2026-03-19): session aggregates in `mv_agent_sessions` do not retain the full latency distribution needed for a real p99. `max` is conservative — it will never understate a latency SLO breach. True p99 calculation is deferred to P5.6+ when raw span windows are queryable per agent.

### 2.5 Cost Attribution Engine

**Purpose**: Calculates dollar costs per tool call, per agent, per task.

**How it works**:
- **LLM costs**: Token counts from OTEL spans × model pricing lookup table
- **External API costs**: User-configurable per-tool cost (e.g., geocoding API = $0.005/call)
- Aggregates: per-call → per-tool → per-agent → per-task → per-day
- Detects anomalies: cost spike vs 7-day baseline

**Key design decisions**:
- Model pricing stored in ClickHouse dictionary table (updatable)
- External API costs are user-configured in .agentguard.yaml
- Cost attribution by task requires session/task ID in OTEL spans (framework-dependent)

### 2.6 Alerting Engine

**Purpose**: Fires alerts when MCP health, reliability, security, or cost thresholds are breached.

**How it works**:
- Alert rules defined in .agentguard.yaml or via API
- Rule types: threshold-based (error rate > X%) and anomaly-based (deviation from baseline)
- Deduplication: same alert within cooldown window = single notification
- Channels: Slack webhook (rich Block Kit format), generic webhook (JSON payload)
- Lifecycle: FIRING → ACKNOWLEDGED → RESOLVED

**Alert types**:
| Alert | Trigger | Default Threshold |
|---|---|---|
| Server down | Health check fails N consecutive times | 3 consecutive failures |
| Latency spike | p99 latency > Nx baseline | 3x baseline |
| Error rate spike | Error rate exceeds threshold | > 5% |
| Schema change | Tool schema hash changed | Any change |
| Tool poisoning | Tool description mutated | Any mutation |
| Security CVE | New CVE matches a server | Any CRITICAL/HIGH CVE |
| Cost spike | Cost exceeds Nx baseline | 3x daily baseline |
| Quality degradation | Tool success rate drops | Below 95% |

### 2.7 CLI (`agentguard`)

**Purpose**: Primary user interface for Phase 1 and 2.

**Commands**:
| Command | Description | Phase |
|---|---|---|
| `agentguard init` | Setup wizard, generates config | 1 |
| `agentguard mcp-health` | Show MCP server health status | 1 |
| `agentguard security-scan` | Run security scan | 1 |
| `agentguard monitor` | Continuous monitoring daemon | 1 |
| `agentguard costs` | Show cost breakdown | 2 |
| `agentguard investigate "..."` | AI-powered root cause analysis | 2 |
| `agentguard config` | View/edit configuration | 1 |

**Design decisions**:
- Built with Click (Python)
- Rich terminal output with colors (via `rich` library)
- All commands support `--json` for programmatic use
- `--ci` flag on security-scan returns exit codes for CI/CD pipelines
- Config resolution: CLI flags > env vars > .agentguard.yaml > defaults

### 2.8 FastAPI REST API

**Purpose**: Serves data to the dashboard (Phase 3) and enables programmatic access.

**Key endpoint groups**:
| Group | Examples | Auth |
|---|---|---|
| `/api/health` | GET server list, GET server detail | API key |
| `/api/security` | GET scan results, POST trigger scan | API key |
| `/api/tools` | GET tool metrics, GET tool errors | API key |
| `/api/costs` | GET cost breakdown, GET cost trends | API key |
| `/api/alerts` | GET alerts, POST acknowledge, PUT rules | API key |
| `/api/slos` | GET list, POST create, DELETE by id, GET /status (evaluate all) | API key |
| `/api/config` | GET/PUT MCP server configs | API key |

**Design decisions**:
- Two auth paths coexist (decided 2026-03-19 — Phase 9):
  1. **Session headers from proxy** — dashboard users authenticate via NextAuth; the Next.js proxy injects `X-User-Id` + `X-User-Role` headers; FastAPI trusts these only from `127.0.0.1` / `::1`
  2. **X-API-Key header** — SDK and CLI direct access; no session required
- JSON responses, standard pagination (offset/limit)
- WebSocket endpoint for real-time health updates (dashboard use)
- `get_active_project_id` FastAPI dependency enforces project membership before returning a `project_id` filter; non-members receive 404 (no enumeration)

### 2.9 LangSight SDK (Phase 2)

**Purpose**: Python client library that wraps any MCP client and records tool call spans to the LangSight API. This is the primary integration path for Python agent developers.

**Design** (decided 2026-03-17 — SDK-first before OTEL):
- `LangSightClient(url, api_key, redact_payloads=False)`: async HTTP client, reads `LANGSIGHT_URL` + `LANGSIGHT_API_KEY` from env if not provided. `redact_payloads` suppresses input/output capture globally.
- `LangSightClient.wrap(mcp_client, redact_payloads=None)`: per-wrap override for `redact_payloads`; `None` inherits the client-level setting.
- `MCPClientProxy` captures tool call arguments as `input_args` and JSON-serialises return values as `output_result` on every `ToolCallSpan`. Both fields are set to `None` when `redact_payloads=True`.
- Fail-open: SDK errors are logged but never propagate to the wrapped MCP client — observability cannot break an agent
- Context manager support for lifecycle management

**Source**: `src/langsight/sdk/`

**Key design decisions**:
- Chose proxy/wrapper pattern over monkey-patching: explicit, debuggable, no magic
- Fire-and-forget HTTP POST for spans: agent latency is not impacted by LangSight availability
- `ToolCallSpan` is sent asynchronously using `asyncio.create_task()` — the wrapped `call_tool()` returns to the caller immediately after the underlying call completes
- **Payload capture is opt-out, not opt-in** (decided 2026-03-18): `input_args` and `output_result` are captured by default for maximum debuggability. Set `redact_payloads: true` in `.langsight.yaml` (or pass `redact_payloads=True` to `LangSightClient`) for tools that handle PII. Redaction is applied before transmission — payloads never leave the host process when redaction is enabled.

### 2.10 LibreChat Plugin (Phase 2)

**Purpose**: 50-line Node.js integration that intercepts LibreChat's MCP call path and sends spans to the LangSight API.

**Why a native plugin, not OTEL** (decided 2026-03-17):
- LibreChat does NOT emit OTEL natively
- LibreChat's Langfuse integration works via env vars (`LANGFUSE_SECRET_KEY`, `LANGFUSE_PUBLIC_KEY`) read by built-in code — not through an OTEL collector
- The lowest-friction integration follows the same pattern: `LANGSIGHT_URL` + `LANGSIGHT_API_KEY` env vars, plugin file copied to the LibreChat plugins directory

**How it works**:
- Plugin intercepts LibreChat's internal MCP dispatch hook
- Reads `LANGSIGHT_URL` and `LANGSIGHT_API_KEY` from the process environment
- POSTs `ToolCallSpan`-compatible JSON to `POST /api/traces/spans`
- Fails open: errors are swallowed, LibreChat continues normally

**Source**: `integrations/librechat/langsight-plugin.js`

### 2.11 Framework Adapters (Phase 2)

**Purpose**: Integration adapters for agent frameworks that have their own tool-call lifecycle hooks. Engineers add one callback/middleware object instead of wrapping the MCP client directly.

**Source**: `src/langsight/integrations/`

| File | Framework | Hook point |
|------|-----------|-----------|
| `crewai.py` | CrewAI | `Crew(callbacks=[LangSightCrewAICallback(...)])` |
| `pydantic_ai.py` | Pydantic AI | Wraps `Tool` objects at registration time |
| `openai_agents.py` | OpenAI Agents SDK | Hooks into function call events |

All adapters share a common `IntegrationBase` that handles span serialization and HTTP dispatch. Fail-open behavior is enforced at the base class level.

### 2.13 Replay Engine (Phase 5.7)

**Purpose**: Re-execute a past session's tool calls against live MCP servers using the stored `input_args`, producing a new session that can be compared with the original.

**How it works**:
- `ReplayEngine.__init__(storage, config, timeout_per_call=10s, total_timeout=60s)` — accepts per-call and total timeout values; both are configurable via the API endpoint query parameters
- `ReplayEngine.replay(session_id)` fetches the original session trace, filters to `span_type="tool_call"` spans where `input_json` is present, and re-executes each in original order via `_call_tool()`
- `_call_tool()` reconstructs a live MCP client connection using the span's `server_name` and the config entry for that server; supports stdio (`StdioServerParameters`), SSE, and StreamableHTTP transports
- Each replay span is stored as a new `ToolCallSpan` with `replay_of=<original_span_id>`, linked into a new `session_id` (the replay session)
- Fail-open per span: if `_call_tool()` raises or times out, the span is recorded with `status="ERROR"` and the replay continues to the next span
- Hard timeout enforcement: `asyncio.timeout()` applied at both the per-call and total-session level
- Returns `ReplayResult` dataclass: `original_session_id`, `replay_session_id`, `total_spans`, `replayed`, `skipped`, `failed`, `duration_ms`

**Replay → compare workflow**:
```
User clicks Replay button in TraceDrawer
        │
        ▼
POST /api/agents/sessions/{id}/replay
        │
        ▼
ReplayEngine.replay(session_id)
  ├── fetch original trace spans
  ├── for each tool_call span with input_json:
  │     ├── open live MCP connection (stdio / SSE / StreamableHTTP)
  │     ├── call tool with stored input_args
  │     └── store replay span with replay_of=original_span_id
  └── return ReplayResult with replay_session_id
        │
        ▼
Dashboard receives replay_session_id
        │
        ▼
onReplay(replaySessionId) callback auto-opens CompareDrawer
  └── GET /api/agents/sessions/compare?a={original}&b={replay}
```

**Key design decisions** (decided 2026-03-19):
- **Sequential replay, not concurrent**: Tool calls are replayed in the original order. Concurrent replay would change observable side effects and make the comparison meaningless.
- **Fail-open per span**: A single tool failure must not abort the entire replay. Engineers need to see which calls succeed and which fail on replay — aborting early hides that information.
- **`replay_of` link, not a separate table**: Replay spans are regular `ToolCallSpan` rows in `mcp_tool_calls` with a `replay_of` foreign reference to the original span. No separate replay table — the existing compare infrastructure (`compare_sessions`) works without modification.
- **No `model_override`**: The original spec included model substitution. This was deferred — replay operates at the tool-call layer and does not involve the LLM. Model substitution requires a full agent re-run, which is out of scope for P5.7.

**Source**: `src/langsight/replay/`

### 2.12 Next.js Dashboard (Phase 4)

**Purpose**: Web UI for teams that prefer a visual interface over CLI.

**Pages**: MCP Health, Tool Reliability, Security, Costs, Alerts, Settings

**Design decisions**:
- shadcn/ui component library (fast to build, consistent look)
- Polls REST API (5s for health, 30s for metrics) — no complex real-time infra
- Charts via recharts
- No SSR needed — static SPA with API calls

---

## 3. Data Flow Diagrams

### Health Check Flow
```
agentguard monitor (or cron)
    │
    ├─→ MCP Server A ──→ JSON-RPC ping ──→ response
    │       │
    │       └─→ tools/list ──→ schema snapshot
    │
    ├─→ MCP Server B ──→ ...
    │
    └─→ Write results to ClickHouse
            │
            └─→ Alerting engine checks thresholds
                    │
                    └─→ Slack webhook (if threshold breached)
```

### Security Scan Flow
```
agentguard security-scan
    │
    ├─→ Load MCP server configs from .agentguard.yaml
    │
    ├─→ For each server:
    │       ├─→ Match name/version against CVE database
    │       ├─→ Run OWASP MCP Top 10 checks
    │       ├─→ Compare tool descriptions against baseline (poisoning check)
    │       └─→ Audit auth configuration
    │
    ├─→ Compute scores (per-server, overall)
    │
    ├─→ Write results to PostgreSQL
    │
    └─→ Output report to terminal (or --json)
```

### OTEL Trace → Tool Reliability Flow
```
Agent Framework (Pydantic AI, CrewAI, etc.)
    │
    │ OTLP spans
    ▼
OTEL Collector ──→ ClickHouse (otel_traces table)
                        │
                        ▼
              Materialized Views:
              ├─→ tool_calls_mv (per-call metrics)
              ├─→ tool_reliability_mv (aggregated per tool per hour)
              └─→ cost_rollup_mv (cost per tool per day)
                        │
                        ▼
              Alerting engine ──→ Slack (if degraded)
              Dashboard API ──→ Next.js charts
```

### Root Cause Attribution Flow (Phase 2)
```
agentguard investigate "customer got wrong refund amount"
    │
    ├─→ Query ClickHouse: recent tool calls with errors
    ├─→ Query ClickHouse: MCP health data (any servers degraded?)
    ├─→ Query ClickHouse: OTEL traces matching time window
    ├─→ (Optional) Query Langfuse API: enriched trace data
    │
    └─→ Feed context to Claude Agent SDK
            │
            └─→ Claude reasons across layers:
                ├─→ Were MCP tools healthy at the time?
                ├─→ Did any tool return stale/incorrect data?
                ├─→ Did the agent choose the wrong tool?
                ├─→ Did the LLM hallucinate despite good context?
                │
                └─→ Output: root cause, confidence score,
                           blast radius, fix recommendations
```

---

## 4. Data Storage Strategy

### ClickHouse (time-series / analytics data)
| Table/View | What it stores | Retention |
|---|---|---|
| `mcp_health_checks` | Every health check result (timestamp, server, status, latency, schema_hash) | 90 days |
| `otel_traces` | Standard OTEL trace/span data from agent frameworks | 30 days |
| `mcp_tool_calls` | Every SDK/OTLP tool call span. Columns include `input_json Nullable(String)` and `output_json Nullable(String)` for payload capture (P5.1, added 2026-03-18); `llm_input Nullable(String)` and `llm_output Nullable(String)` for LLM reasoning capture (P5.3, added 2026-03-19); `replay_of String DEFAULT ''` to link replay spans back to their originals (P5.7, added 2026-03-19). MergeTree, TTL 90 days. | 90 days |
| `tool_calls_mv` | Materialized view: extracted tool call spans with metrics | 30 days |
| `tool_reliability_hourly` | Aggregated: per-tool success rate, latency percentiles, error counts per hour | 1 year |
| `cost_daily` | Aggregated: per-tool, per-agent cost per day | 1 year |
| `mcp_schema_snapshots` | Full tool schema JSON, stored on change (not on every check) | Forever |

**`mcp_tool_calls` payload columns** (added P5.1 + P5.3):
| Column | Type | Description |
|--------|------|-------------|
| `input_json` | `Nullable(String)` | JSON-serialised tool call arguments (`input_args` from `ToolCallSpan`). `NULL` when `redact_payloads=True`. (P5.1) |
| `output_json` | `Nullable(String)` | JSON-serialised tool return value (`output_result` from `ToolCallSpan`). `NULL` when `redact_payloads=True`. (P5.1) |
| `llm_input` | `Nullable(String)` | LLM prompt text extracted from OTLP `gen_ai.prompt` / `llm.prompts` attributes. Populated only on `span_type="agent"` spans originating from LLM generation spans. (P5.3) |
| `llm_output` | `Nullable(String)` | LLM completion text extracted from OTLP `gen_ai.completion` / `llm.completions` attributes. Populated only on `span_type="agent"` spans originating from LLM generation spans. (P5.3) |
| `replay_of` | `String DEFAULT ''` | When this span is a replay, contains the `span_id` of the original span being replayed. Empty string for non-replay spans. Links replay sessions back to their originals without a separate table. (P5.7, added 2026-03-19) |

### PostgreSQL (application state)
| Table | What it stores |
|---|---|
| `mcp_servers` | Registered MCP server configs (name, transport, URL, auth, tags) |
| `security_scans` | Scan results (findings, scores, timestamps) |
| `alert_rules` | User-defined alert thresholds |
| `alerts` | Fired alerts with lifecycle (firing/ack/resolved) |
| `api_keys` | API authentication keys |
| `model_pricing` | LLM model → price per 1K input/output tokens |
| `agent_slos` | User-defined SLO definitions (`agent_name`, `metric`, `target`, `window_hours`, `created_at`). Present in both SQLite and PostgreSQL backends. (P5.5, added 2026-03-19) |

---

## 5. Tech Stack Summary

| Layer | Technology | Why |
|---|---|---|
| **Core language** | Python 3.11+ | Best MCP SDK support, OTEL libraries, AI ecosystem |
| **CLI** | Click + Rich | Clean CLI framework + beautiful terminal output |
| **API** | FastAPI | Async, fast, auto-docs, Python-native |
| **OLAP** | ClickHouse | Proven for observability at scale (Langfuse, Helicone) |
| **Metadata DB** | PostgreSQL | Reliable, well-understood for app state |
| **Trace ingestion** | OTEL Collector (contrib) | Standard, ClickHouse exporter built-in |
| **Dashboard** | Next.js 15 + shadcn/ui + recharts | Fast to build, good component ecosystem |
| **MCP client** | `mcp` Python SDK | Official SDK for connecting to MCP servers |
| **RCA agent** | Claude Agent SDK | For Phase 2 root cause investigation |
| **Alerting** | Slack Block Kit + webhooks | Simple, widely used |
| **Containerization** | Docker Compose | Single `docker compose up` for full stack |
| **Testing** | pytest + httpx + testcontainers | Standard Python testing stack |
| **License** | Apache 2.0 | Maximum adoption, no ELv2 concerns |

---

## 6. Integration Points

### MCP Server Discovery
AgentGuard discovers MCP servers from:
1. `.agentguard.yaml` config file (primary)
2. Auto-detect from `~/.config/claude/claude_desktop_config.json` (Claude Desktop)
3. Auto-detect from Cursor MCP settings
4. Manual `agentguard config add-server` command

### MCP Transport Support
| Transport | How we connect | Health check method |
|---|---|---|
| **stdio** | Spawn subprocess, communicate via stdin/stdout | Send JSON-RPC initialize + tools/list |
| **SSE** | HTTP GET to SSE endpoint | Send JSON-RPC over SSE |
| **StreamableHTTP** | HTTP POST to server endpoint | Send JSON-RPC over HTTP |

### Integration Paths

LangSight supports three distinct integration paths. Engineers choose based on their stack.

**Path 1 — LangSight SDK (Phase 2, primary)**: For Python agents using MCP clients directly.

```python
from langsight.sdk import LangSightClient, wrap

client = LangSightClient()  # reads LANGSIGHT_URL from env
mcp_client = wrap(mcp_client, client)
```

**Path 2 — Framework Adapters (Phase 2)**: For agents built on CrewAI, Pydantic AI, or OpenAI Agents SDK.

```python
from langsight.integrations.crewai import LangSightCrewAICallback
crew = Crew(callbacks=[LangSightCrewAICallback()])
```

**Path 3 — OTEL Collector (Phase 3)**: For frameworks with native OTEL support. Point the OTEL exporter at LangSight's collector endpoint. No code changes needed in the agent.

| Framework | OTEL Support | Path |
|-----------|-------------|------|
| Pydantic AI | Native (`Agent.instrument_all()`) | Path 3 (OTEL) or Path 2 (adapter) |
| Strands (AWS) | Native (`pip install strands-agents[otel]`) | Path 3 (OTEL) |
| AG2/AutoGen | Native (`autogen.opentelemetry`) | Path 3 (OTEL) |
| Claude Agent SDK | Native | Path 3 (OTEL) |
| CrewAI | Via community OTEL package | Path 2 (adapter) preferred |
| OpenAI Agents SDK | Via community instrumentor | Path 2 (adapter) preferred |
| LibreChat | No OTEL — native Langfuse env var pattern | Path 4 (LibreChat plugin) |

**Path 4 — LibreChat Plugin (Phase 2)**: Copy one file to LibreChat plugins directory, set two env vars.

### Optional: Langfuse Integration
- LangSight can read traces from Langfuse API (for enriched RCA in Phase 2)
- Not required — LangSight works standalone
- Config: `langfuse_api_url` + `langfuse_api_key` in `.langsight.yaml`

---

## 7. Deployment

### Docker Compose Services
| Service | Image | Exposed Ports | Purpose |
|---|---|---|---|
| `clickhouse` | clickhouse/clickhouse-server | 8123, 9000 | OLAP storage |
| `postgres` | postgres:16 | 5432 | Metadata storage |
| `otel-collector` | otel/opentelemetry-collector-contrib | 4317, 4318 | Trace ingestion |
| `agentguard-api` | agentguard/api | 8080 | REST API |
| `agentguard-worker` | agentguard/worker | — | Health checks, scans, alerts |
| `agentguard-dashboard` | agentguard/dashboard | 3000 | Web UI (Phase 3) |

### Resource Estimates (Development)
| Service | CPU | Memory | Disk |
|---|---|---|---|
| ClickHouse | 1 core | 2 GB | 10 GB |
| PostgreSQL | 0.5 core | 512 MB | 1 GB |
| OTEL Collector | 0.5 core | 256 MB | — |
| API + Worker | 1 core | 1 GB | — |
| **Total** | **3 cores** | **~4 GB** | **~11 GB** |

### CLI-Only Mode (No Docker)
For users who just want the CLI without the full stack:
```
pip install agentguard
agentguard init
agentguard mcp-health
agentguard security-scan
```
CLI-only mode uses SQLite for local storage. No ClickHouse/PostgreSQL required.
Full stack (Docker Compose) needed for: OTEL ingestion, dashboard, continuous monitoring, alerting.

---

## 8. Authentication Architecture (added Phase 9, 2026-03-19)

### Two auth paths

```
Dashboard users:
  Browser
    │ HTTPS
    ▼
  Next.js App (dashboard/)
    │ Server-side: reads NextAuth session
    │ Injects X-User-Id + X-User-Role headers
    ▼
  Next.js proxy route
  dashboard/app/api/proxy/[...path]/route.ts
    │ Forwards to FastAPI (localhost only)
    ▼
  FastAPI
    └── _is_proxy_request(): trusts headers only from 127.0.0.1 / ::1
    └── _get_session_user(): extracts user_id + role from headers

SDK / CLI users:
  langsight CLI / Python SDK
    │ X-API-Key header
    ▼
  FastAPI
    └── verify_api_key(): validates against api_keys table
```

### Trusted proxy pattern (decided 2026-03-19)

FastAPI trusts `X-User-Id` and `X-User-Role` only when the request originates from `127.0.0.1` or `::1`. External clients that set these headers directly are ignored — the headers are treated as regular headers, not auth. This means:
- No JWT verification in FastAPI — simpler, no shared secret dependency
- Security boundary is the network: the proxy and API must be co-located (Docker Compose / same host)
- Not suitable for deployments where FastAPI is exposed publicly without a reverse proxy

### Why not Bearer token forwarding (rejected approach, decided 2026-03-19)

The original plan was to forward the NextAuth JWT as `Authorization: Bearer` to FastAPI, requiring FastAPI to verify the JWT using the shared `AUTH_SECRET`. This was rejected because:
- Adds a JWT parsing dependency (`python-jose`) to FastAPI for a path that only the proxy uses
- Requires both services to share `AUTH_SECRET` via env var coordination
- The trusted-proxy-headers pattern is equally secure when the network boundary is enforced, and simpler

### Security headers (added Phase 9, 2026-03-19)

`SecurityHeadersMiddleware` in `src/langsight/api/main.py` adds to every response:

| Header | Value |
|--------|-------|
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `X-XSS-Protection` | `1; mode=block` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Strict-Transport-Security` | `max-age=31536000` (HTTPS only) |

### Project isolation (added Phase 10, 2026-03-19)

`get_active_project_id` FastAPI dependency:
1. Reads `project_id` query param from the request
2. Verifies the caller is a member of that project (or is global admin)
3. Returns the `project_id` to pass as a DB-level filter, or `None` for global admin with no filter
4. Non-members receive HTTP 404 — project existence is not confirmed to non-members (no enumeration)

All ClickHouse queries in `storage/clickhouse.py` that read from `mcp_tool_calls` accept an optional `project_id` parameter and apply it as a `WHERE project_id = {project_id}` clause. Filtering is at the DB layer — no Python post-filter.

---

## 9. Security Considerations

- **Two auth paths**: session headers (dashboard via Next.js proxy) and X-API-Key (SDK/CLI)
- **Trusted proxy**: X-User-Id/X-User-Role headers trusted only from localhost — FastAPI must not be internet-exposed without the Next.js proxy
- **MCP credentials** stored in .langsight.yaml (gitignored) or env vars
- **No external exposure by default** — Docker network is internal, only dashboard port exposed
- **PII in traces**: `redact_payloads: true` config suppresses payload capture before transmission
- **Principle of least privilege**: Health checker uses read-only MCP operations only
- **Rate limiting**: `/api/users/verify` limited to 10 requests/minute per IP (via slowapi); health check frequency capped to avoid overloading MCP servers
- **Project isolation**: all ClickHouse queries filtered by `project_id` at DB level when a project context is active
- **Security headers**: X-Content-Type-Options, X-Frame-Options, X-XSS-Protection, Referrer-Policy, HSTS on all API responses
