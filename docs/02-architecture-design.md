# LangSight: Architecture Design

> **Version**: 1.8.0
> **Date**: 2026-03-27
> **Status**: Active — v0.3 Prevention Layer (Tier 1) shipped: circuit breaker, loop detection, budget guardrails integrated into SDK `call_tool()` path. New alert types for prevention events. Health tag engine for session auto-classification. Dashboard sessions page updated with health tag column and filter (2026-03-22). Prevention Config shipped (2026-03-22): dashboard-managed thresholds via `prevention_config` Postgres table, 6 API endpoints, SDK `_apply_remote_config()` background fetch on `wrap()`, Settings → Prevention dashboard tab (section 2.9.2). v0.8.4: health_tool backend probe + MCPHealthToolError (2026-03-27). v0.8.5: inputSchema string coercion in _parse_tools() (2026-03-27). v0.8.6: /health merged into /servers, invocations endpoint, Agents Servers tab, upsert_server_tools on every check, project_id fix (2026-03-27).

---

## 1. System Architecture Overview

```
  Integration Paths (Phase 2)        LangSight Platform
  ─────────────────────────────────  ─────────────────────────────────────────────
                                     ┌───────────────────────────────────────────┐
  Python agents (CrewAI, Pydantic    │                                           │
  AI, OpenAI Agents, Anthropic,      │  ┌───────────────┐  ┌──────────────────┐  │
  LangGraph)                         │  │  MCP Health    │  │  MCP Security    │  │
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
         │  (~50-line JS plugin)      │          │  Storage Layer (dual)│         │
         ▼                           │          │  Postgres (metadata) │         │
  ┌──────────────────┐               │          │  ClickHouse (analytics)        │
  │  LangSight       │──── spans ───►│          └─────────────────────┘          │
  │  LibreChat Plugin│               │                                           │
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
  - **Health tool probe**: If `health_tool` is configured, calls that tool with `health_tool_args` after `tools/list` to verify the backend is alive. A successful `tools/list` but a failing health tool probe produces `DEGRADED` (backend down) rather than `DOWN` (MCP layer unreachable). This distinction is the primary purpose of the probe — e.g. a DataHub MCP server can serve its tool manifest while the underlying DataHub REST API is down.
- Records results in ClickHouse (timestamp, server, status, latency, schema hash)
- Manages server state transitions: `UP → DEGRADED → DOWN → STALE`
- `upsert_server_tools` is called on every health check cycle (not just on schema drift) so the MCP Servers → Tools tab stays current

**Key design decisions**:
- Polling-based (not event-driven) — MCP servers don't push health status
- Configurable intervals per server (default: 30s for health, 5min for schema check)
- Rate limiting built in — never send more than N checks/min to a single server
- **Health tool probe distinguishes MCP-layer failures from backend failures** (added v0.8.4, 2026-03-27): `ping()` calls the configured `health_tool` after `tools/list`. If the probe raises `MCPHealthToolError` the server transitions to `DEGRADED` instead of `DOWN`. This preserves the semantic: `DOWN` = MCP server unreachable; `DEGRADED` = MCP server up but backend unavailable. The `MCPHealthToolError` exception is raised by `checker.py` when the tool invocation returns an error or raises. Config: `health_tool: <tool_name>`, `health_tool_args: {key: value}`. Optional — omitting it skips the probe.
- **`inputSchema` string coercion** (added v0.8.5, 2026-03-27): `_parse_tools()` now handles MCP servers (e.g. atlassian-mcp) that return `inputSchema` as a JSON string instead of a dict. The parser calls `json.loads()` when it detects a string value, making schema tracking robust against non-compliant server implementations. No config change required.
- **Schema tracking: structural diff, not just hash** (added v0.8.0, 2026-03-26): when a hash mismatch is detected, `classify_drift(old_tools, new_tools)` computes an atomic diff across tool definitions. Each change is classified as `BREAKING` (tool_removed, required_param_removed, required_param_added, param_type_changed), `COMPATIBLE` (tool_added, optional_param_added), or `WARNING` (description_changed — potential poisoning vector). The full `SchemaDriftEvent` (server, changes, has_breaking, hashes, timestamp) is stored in the `schema_drift_events` ClickHouse table. Source: `src/langsight/health/schema_tracker.py`.
- **MCP Server Scorecard** (added v0.8.0, 2026-03-26): `ScorecardEngine.compute()` produces an A-F composite grade from five weighted dimensions (Availability 30%, Security 25%, Reliability 20%, Schema Stability 15%, Performance 10%). Hard veto caps override the numeric result for fatal flaws (10+ consecutive failures → F, active critical CVE → F, confirmed poisoning → F). Exposed via `GET /api/health/servers/{name}/scorecard`. Source: `src/langsight/health/scorecard.py`.

### 2.2 MCP Security Scanner

**Purpose**: Scans MCP server configurations for security vulnerabilities, known CVEs, and active threats.

**How it works**:
- **CVE matching**: Compares server name + version against a local CVE database (sourced from NVD + GitHub Advisory + MCP-specific advisories)
- **OWASP MCP Top 10 checks**: Automated checks for each category (tool poisoning, excessive permissions, no auth, etc.)
- **Tool poisoning detection**: Captures baseline tool descriptions at first scan, alerts on mutations (hash comparison)
- **Auth audit**: Checks for missing auth, long-lived tokens, overly broad permissions
- Produces a scored report (0-10 overall, per-category scores)

**Scan modes**:
- **One-time**: `langsight security-scan` — runs and exits
- **Continuous**: Part of `langsight monitor` — periodic re-scans to detect rug-pull attacks

**Key design decisions**:
- CVE database is a local JSON file, updated via `langsight update-cves` or on startup
- Tool poisoning detection requires a baseline — first scan establishes it
- Scanner reads MCP server configs from .langsight.yaml, not from the servers themselves

### 2.3 OTEL Trace Ingestion

**Purpose**: Accepts OpenTelemetry spans from agent frameworks, extracts MCP tool call data, stores in ClickHouse.

**How it works**:
- OTEL Collector (contrib build) receives OTLP spans on ports 4317 (gRPC) / 4318 (HTTP)
- Collector exports to ClickHouse via built-in ClickHouse exporter
- LangSight adds materialized views on top of standard OTEL schema to extract:
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

**SLO tracking** (added P5.5, 2026-03-19): `SLOEvaluator` in `src/langsight/reliability/engine.py` evaluates user-defined `AgentSLO` records against live session data returned by `get_agent_sessions()`. Two metric types are supported: `success_rate` (computed as `(clean_sessions / total_sessions) * 100`) and `latency_p99` (uses `max(duration_ms)` as a conservative proxy — true p99 requires raw span data, not session aggregates). SLO definitions are persisted in the `agent_slos` table in PostgreSQL. Evaluation produces `SLOEvaluation` records with status `ok`, `breached`, or `no_data`. The full CRUD surface (`POST /api/slos`, `GET /api/slos`, `GET /api/slos/status`, `DELETE /api/slos/{slo_id}`) is exposed via `src/langsight/api/routers/slos.py`. The dashboard Overview page polls `/api/slos/status` every 60s and renders an "Agent SLOs" panel when SLOs are defined.

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
- External API costs are user-configured in .langsight.yaml
- Cost attribution by task requires session/task ID in OTEL spans (framework-dependent)

### 2.6 Alerting Engine

**Purpose**: Fires alerts when MCP health, reliability, security, cost thresholds are breached, or SDK prevention events occur.

**How it works**:
- Alert rules defined in .langsight.yaml or via API
- Rule types: threshold-based (error rate > X%) and anomaly-based (deviation from baseline)
- Prevention events: `evaluate_prevention_event()` method — always produces an alert (no threshold needed, prevention events are already significant)
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
| Loop detected | SDK loop detector fires (v0.3) | Any detection (WARNING) |
| Budget warning | Session budget crosses soft threshold (v0.3) | 80% of any budget limit (WARNING) |
| Budget exceeded | Session budget hard limit hit (v0.3) | Any limit exceeded (CRITICAL) |
| Circuit breaker open | Per-server circuit breaker trips (v0.3) | Threshold consecutive failures (CRITICAL) |
| Circuit breaker recovered | Circuit breaker returns to CLOSED (v0.3) | Auto on recovery (INFO) |

**Prevention event evaluation** (added v0.3, 2026-03-22): The `evaluate_prevention_event(event: PreventionEvent)` method maps SDK events to alert types via `_EVENT_TO_ALERT` lookup. Unlike health-check evaluation which requires threshold logic, prevention events always produce an alert — they represent significant runtime interventions.

### 2.7 CLI (`langsight`)

**Purpose**: Primary user interface for Phase 1 and 2.

**Commands**:
| Command | Description | Phase |
|---|---|---|
| `langsight init` | Setup wizard, generates config | 1 |
| `langsight mcp-health` | Show MCP server health status | 1 |
| `langsight security-scan` | Run security scan | 1 |
| `langsight monitor` | Continuous monitoring daemon | 1 |
| `langsight costs` | Show cost breakdown | 2 |
| `langsight investigate "..."` | AI-powered root cause analysis | 2 |
| `langsight config` | View/edit configuration | 1 |

**Design decisions**:
- Built with Click (Python)
- Rich terminal output with colors (via `rich` library)
- All commands support `--json` for programmatic use
- `--ci` flag on security-scan returns exit codes for CI/CD pipelines
- Config resolution: CLI flags > env vars > .langsight.yaml > defaults

### 2.7.5 DualStorage (added 2026-03-19)

**Purpose**: Production storage topology — routes each operation to the backend that is architecturally correct for it, transparently from the caller's perspective.

**How it works**:
- `DualStorage.__init__(metadata: PostgresBackend, analytics: ClickHouseBackend)`
- Implements the full `StorageBackend` protocol; callers never reference either inner backend directly
- **Postgres (metadata)**: users, projects, project members, API keys, model pricing, SLOs, invite tokens, alert config, audit logs — relational, low-volume, strong consistency required
- **ClickHouse (analytics)**: spans, traces, health results, reliability stats, costs, sessions — time-series, high-volume, append-only
- ClickHouse-specific extension methods (`get_session_trace`, `compare_sessions`, `get_cost_call_counts`, `get_tool_reliability`, `get_baseline_stats`) forwarded via `__getattr__`

**Routing table**:
```
save_health_result()        → ClickHouse
get_session_trace()         → ClickHouse
compare_sessions()          → ClickHouse
get_cost_call_counts()      → ClickHouse
get_tool_reliability()      → ClickHouse
get_baseline_stats()        → ClickHouse

save_schema_snapshot()      → Postgres
list_api_keys()             → Postgres
create_api_key()            → Postgres
get_api_key_by_hash()       → Postgres
list_users() / get_user()   → Postgres
create_slo() / list_slos()  → Postgres
list_projects()             → Postgres
append_audit()              → Postgres
save_alert_config()         → Postgres
accept_invite()             → Postgres  (fixed 2026-03-21 — was missing delegation, raised AttributeError)
```

**Source**: `src/langsight/storage/dual.py`

**Key design decisions** (decided 2026-03-19):
- **Transparent routing, not federation**: DualStorage satisfies the single `StorageBackend` protocol. No router or dependency knows it exists — adding it was a config change, not a code change across call sites.
- **SQLite removed**: SQLite was the zero-dependency CLI mode from Phase 1. Removed because: (a) Phase 2+ features (multi-tenancy, RBAC, audit logs) require relational joins and foreign keys that SQLite supports poorly at scale; (b) the dual-backend model requires two processes regardless, making the zero-dependency argument void; (c) maintenance burden of a third backend path that no production user would choose. `docker compose up -d` is now the minimum requirement. Attempting `mode: sqlite` raises `ConfigError` with a migration message.
- **Factory dispatch**: `storage/factory.py` `open_storage()` dispatches on `config.mode`: `"postgres"` | `"clickhouse"` | `"dual"` (default). Unknown modes raise `ConfigError` with an explicit migration message for former SQLite users.

### 2.8 FastAPI REST API

**Purpose**: Serves data to the dashboard (Phase 3) and enables programmatic access.

**Key endpoint groups**:
| Group | Examples | Auth |
|---|---|---|
| `/api/health` | GET server list, GET server detail | API key |
| `/api/health/servers/invocations` | GET last_called_at, last_call_ok, total_calls per server (7-day window, from tool call traces) — added v0.8.6 | API key |
| `/api/security` | GET scan results, POST trigger scan | API key |
| `/api/tools` | GET tool metrics, GET tool errors | API key |
| `/api/costs` | GET cost breakdown, GET cost trends | API key |
| `/api/alerts` | GET alerts, POST acknowledge, PUT rules | API key |
| `/api/slos` | GET list, POST create, DELETE by id, GET /status (evaluate all) | API key |
| `/api/config` | GET/PUT MCP server configs | API key |
| `/api/live/events` | SSE stream of real-time span ingestion and health check events | API key |
| `/metrics` | Prometheus scrape endpoint — text exposition format | **None** (no auth) |

**Design decisions**:
- Two auth paths coexist (decided 2026-03-19 — Phase 9):
  1. **Session headers from proxy** — dashboard users authenticate via NextAuth; the Next.js proxy injects `X-User-Id` + `X-User-Role` headers; FastAPI trusts these only from `LANGSIGHT_TRUSTED_PROXY_CIDRS` (loopback by default, expanded to internal container CIDRs in Docker deployments)
  2. **X-API-Key header** — SDK and CLI direct access; no session required
- JSON responses, standard pagination (offset/limit)
- **SSE live feed** replaces the originally planned WebSocket endpoint (decided 2026-03-21): `GET /api/live/events` streams `span:new` and `health:check` events via Server-Sent Events. SSE was chosen over WebSocket because: (a) unidirectional server-to-client is sufficient for dashboard updates; (b) SSE works through HTTP/2 and standard reverse proxies without upgrade negotiation; (c) browser `EventSource` API handles reconnection automatically. See `SSEBroadcaster` (section 2.14) for implementation details.
- **Prometheus `/metrics` endpoint** (added 2026-03-21): `GET /metrics` returns all LangSight metrics in Prometheus text exposition format. Registered without authentication so Prometheus scrapers can reach it without API keys. See section 2.15 for details.
- `get_active_project_id` FastAPI dependency enforces project membership before returning a `project_id` filter; non-members receive 404 (no enumeration)

### 2.9 LangSight SDK (Phase 2)

**Purpose**: Python client library that wraps any MCP client, records tool call spans to the LangSight API, and (v0.3) enforces runtime prevention guardrails. This is the primary integration path for Python agent developers.

**Design** (decided 2026-03-17 — SDK-first before OTEL; extended 2026-03-22 with prevention layer):
- `LangSightClient(url, api_key, redact_payloads=False)`: async HTTP client, reads `LANGSIGHT_URL` + `LANGSIGHT_API_KEY` from env if not provided. `redact_payloads` suppresses input/output capture globally.
- `LangSightClient.wrap(mcp_client, redact_payloads=None)`: per-wrap override for `redact_payloads`; `None` inherits the client-level setting.
- `MCPClientProxy` captures tool call arguments as `input_args` and JSON-serialises return values as `output_result` on every `ToolCallSpan`. Both fields are set to `None` when `redact_payloads=True`.
- Fail-open: SDK errors are logged but never propagate to the wrapped MCP client — reliability instrumentation cannot break an agent
- Context manager support for lifecycle management
- **v0.3 Prevention layer** (added 2026-03-22): opt-in loop detection, budget guardrails, and circuit breaker. Prevention is BLOCKING by design — it must stop the call before it happens. Prevented calls are recorded as spans with `status=PREVENTED`.

**Full constructor signature (v0.3)**:
```python
LangSightClient(
    url: str,
    api_key: str | None = None,
    timeout: float = 3.0,
    redact_payloads: bool = False,
    project_id: str | None = None,
    batch_size: int = 50,
    flush_interval: float = 1.0,
    max_buffer_size: int = 10_000,
    # --- v0.3 Prevention layer ---
    loop_detection: bool = False,
    loop_threshold: int = 3,
    loop_action: str = "terminate",       # "terminate" | "warn"
    max_cost_usd: float | None = None,
    max_steps: int | None = None,
    max_wall_time_s: float | None = None,
    budget_soft_alert: float = 0.80,
    pricing_table: dict[str, tuple[float, float]] | None = None,
    circuit_breaker: bool = False,
    circuit_breaker_threshold: int = 5,
    circuit_breaker_cooldown: float = 60.0,
    circuit_breaker_half_open_max: int = 2,
)
```

**Source**: `src/langsight/sdk/`

**Key design decisions**:
- Chose proxy/wrapper pattern over monkey-patching: explicit, debuggable, no magic
- Fire-and-forget HTTP POST for spans: agent latency is not impacted by LangSight availability
- `ToolCallSpan` is sent asynchronously using `asyncio.create_task()` — the wrapped `call_tool()` returns to the caller immediately after the underlying call completes
- **Payload capture is opt-out, not opt-in** (decided 2026-03-18): `input_args` and `output_result` are captured by default for maximum debuggability. Set `redact_payloads: true` in `.langsight.yaml` (or pass `redact_payloads=True` to `LangSightClient`) for tools that handle PII. Redaction is applied before transmission — payloads never leave the host process when redaction is enabled.
- **Prevention defaults to disabled** (decided 2026-03-22): all prevention params (`loop_detection`, `circuit_breaker`, budget limits) default to disabled/`None`. Existing SDK users are not affected — zero breaking changes. Engineers opt in per-feature.
- **Prevention is blocking, observability is async** (decided 2026-03-22): span recording is fire-and-forget (`asyncio.create_task`), but prevention checks are synchronous within `call_tool()`. A blocked call must raise immediately — not after the call completes. This is a deliberate asymmetry: observability must never slow an agent, but prevention must be able to stop one.

### 2.9.1 SDK Prevention Layer (v0.3, added 2026-03-22)

**Purpose**: Client-side runtime prevention that stops harmful agent behavior before it reaches MCP servers.

**Architecture**:
```
MCPClientProxy.call_tool(tool_name, args)
    │
    ├─→ PRE-CALL checks (blocking, synchronous)
    │     ├── CircuitBreaker.allow_call(server_name)
    │     │     └── OPEN? → raise CircuitBreakerOpenError
    │     ├── LoopDetector.check_pre_call(tool_name, args)
    │     │     └── loop detected + action=terminate? → raise LoopDetectedError
    │     └── SessionBudget.check_pre_call()
    │           └── steps exceeded or wall time exceeded? → raise BudgetExceededError
    │
    ├─→ ACTUAL TOOL CALL (underlying MCP client)
    │
    └─→ POST-CALL updates (non-blocking)
          ├── LoopDetector.record(tool_name, args, status, error)
          ├── SessionBudget.record_call(cost)
          │     └── cost exceeded? → raise BudgetExceededError
          │     └── soft threshold crossed? → emit BudgetWarning
          └── CircuitBreaker.record_success() / record_failure()
                └── threshold reached? → state → OPEN → emit CircuitBreakerOpen
```

**Prevented calls**: When a prevention check blocks a call, the SDK records a `ToolCallSpan` with `status=PREVENTED` and the error message describing the reason. This ensures prevented calls are visible in the session trace and dashboard.

**Three prevention subsystems**:

| Subsystem | Source | Scope | State storage |
|---|---|---|---|
| Circuit breaker | `sdk/circuit_breaker.py` | Per-server (shared across sessions) | `dict[server_name, CircuitBreaker]` on client |
| Loop detector | `sdk/loop_detector.py` | Per-session | `dict[session_id, LoopDetector]` on client |
| Budget guardrails | `sdk/budget.py` | Per-session | `dict[session_id, SessionBudget]` on client |

**Circuit breaker state machine**:
```
CLOSED ──(N consecutive failures)──► OPEN ──(cooldown elapsed)──► HALF_OPEN
  ▲                                                                  │
  └──────────(all test calls succeed)────────────────────────────────┘
                                    HALF_OPEN ──(any test call fails)──► OPEN
```
Thread-safe for single-threaded asyncio (Python GIL + cooperative scheduling — no preemption within a sync method).

**Loop detection patterns**:
1. **Repetition**: same `tool_name` + normalized `input_args` hash repeated N times in sliding window
2. **Ping-pong**: alternating between two `tool_name + args` pairs
3. **Retry-without-progress**: same tool + same error hash repeated N times

**Budget tracking**:
- **Step count** and **wall time** are checked pre-call (knowable before the call happens)
- **Cost** is checked post-call (we cannot predict the next call's cost)
- Cost limit fires on the first call that pushes over the threshold
- Soft alert at configurable fraction (default 80%) fires once per limit type per session

**Key design decisions** (decided 2026-03-22):
- **Client-side, not server-side**: Prevention must be low-latency and work even when the LangSight API is unreachable. All state is held in-memory on the `LangSightClient` instance. There is no round-trip to the server before each tool call.
- **Per-server circuit breaker, per-session everything else**: Circuit breaker state is shared across all sessions using the same client — if a server is failing for one agent session, it should be disabled for all. Loop detection and budget tracking are per-session because loops and costs are session-scoped behaviors.
- **Raise exceptions, not return errors**: Prevention violations raise typed exceptions (`LoopDetectedError`, `BudgetExceededError`, `CircuitBreakerOpenError`) so the agent framework's error handling catches them. Returning error values would be silently ignored by most frameworks.
- **`ToolCallStatus.PREVENTED`**: A new status value distinct from `ERROR` — prevented calls never reached the server. This distinction matters for reliability metrics: a prevented call is not a tool failure.

### 2.9.2 Prevention Config — Dashboard-Managed Thresholds (added 2026-03-22)

**Purpose**: Decouple prevention threshold management from code. Engineers configure loop, budget, and circuit-breaker limits in the dashboard or via API; the SDK fetches them on startup without a code deploy.

**Data flow**:
```
Dashboard UI (Settings → Prevention)
        ↓  CRUD via API
  Postgres: prevention_config table (per-project, per-agent)
        ↓  GET on wrap()
  SDK: _apply_remote_config() — background task, non-blocking
        ↓  merged over constructor defaults
  MCPClientProxy (active thresholds)
```

**`prevention_config` table** — key columns: `id`, `project_id`, `agent_name`, `loop_enabled`, `loop_threshold`, `loop_action`, `max_steps`, `max_cost_usd`, `max_wall_time_s`, `budget_soft_alert`, `cb_enabled`, `cb_failure_threshold`, `cb_cooldown_seconds`, `cb_half_open_max_calls`.

**Project default**: `agent_name="*"` row acts as the project-level fallback. Lookup order: per-agent row → project default row → SDK constructor params.

**Key design decisions** (decided 2026-03-22):
- **Constructor params as offline fallback, not the source of truth**: Thresholds set in code are kept so agents function correctly when the API is unreachable (offline mode, network partition, cold start). The platform config takes precedence when reachable.
- **Non-blocking fetch on `wrap()`**: `_apply_remote_config()` is launched via `asyncio.create_task()`. `wrap()` returns immediately; remote config is applied before the first tool call completes. A failed fetch logs a warning and leaves constructor defaults active — it never blocks the agent.
- **No per-call round-trip**: Remote config is fetched once per `wrap()` and cached in-memory for the lifetime of that proxy. This keeps the prevention path latency identical to Tier 1 (no added I/O per tool call).

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
| `langchain.py` | LangChain / Langflow / LangGraph / LangServe | Callback-based span emission |
| `openai_agents.py` | OpenAI Agents SDK | `Runner.run(agent, hooks=LangSightOpenAIHooks(...))` — implements the `RunHooks` protocol; also provides `langsight_openai_tool` decorator for individual tool functions |
| `anthropic_sdk.py` | Anthropic SDK / Claude Agent SDK | `AnthropicToolTracer.trace_response(message)` for message-level tracing; `LangSightClaudeAgentHooks` for agent lifecycle hooks; `langsight_anthropic_tool` decorator for individual tool handlers |
| `langgraph.py` | LangGraph (dedicated) | `graph.ainvoke({...}, config={"callbacks": [LangSightLangGraphCallback(...)]})` — graph-aware: tracks node names, graph-level span grouping, conditional routing visibility |

All adapters share a common `IntegrationBase` that handles span serialization and HTTP dispatch. Fail-open behavior is enforced at the base class level.

**Total integration count**: 9 (MCP SDK wrap, LangChain, LangGraph, CrewAI, Pydantic AI, OpenAI Agents, Anthropic/Claude, OTEL, LibreChat). Added 2026-03-21: OpenAI Agents, Anthropic/Claude, and dedicated LangGraph.

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
User opens `/sessions/{id}` and clicks Replay
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
Session detail page starts compare flow against the replay session
  └── GET /api/agents/sessions/compare?a={original}&b={replay}
```

**Key design decisions** (decided 2026-03-19):
- **Sequential replay, not concurrent**: Tool calls are replayed in the original order. Concurrent replay would change observable side effects and make the comparison meaningless.
- **Fail-open per span**: A single tool failure must not abort the entire replay. Engineers need to see which calls succeed and which fail on replay — aborting early hides that information.
- **`replay_of` link, not a separate table**: Replay spans are regular `ToolCallSpan` rows in `mcp_tool_calls` with a `replay_of` foreign reference to the original span. No separate replay table — the existing compare infrastructure (`compare_sessions`) works without modification.
- **No `model_override`**: The original spec included model substitution. This was deferred — replay operates at the tool-call layer and does not involve the LLM. Model substitution requires a full agent re-run, which is out of scope for P5.7.

**Source**: `src/langsight/replay/`

### 2.14 SSE Broadcaster (added 2026-03-21)

**Purpose**: Push real-time events to connected dashboard clients without requiring WebSocket infrastructure.

**How it works**:
- `SSEBroadcaster` (in `src/langsight/api/broadcast.py`) is an in-memory asyncio pub/sub
- On startup, a singleton `SSEBroadcaster` is stored on `app.state.broadcaster`
- Producers call `broadcaster.publish(event_type, data)` — non-blocking, never raises
- Consumers connect via `GET /api/live/events` (requires auth) and receive SSE-formatted events
- Each client gets a bounded `asyncio.Queue` (50 events max); oldest event is dropped if the client is too slow
- Hard limit of 200 concurrent clients to prevent resource exhaustion
- 15-second keepalive heartbeats prevent proxy timeouts

**Event types**:
| Event | Source | Payload |
|---|---|---|
| `span:new` | `traces.py` — after span ingestion | `session_id`, `agent_name`, `server_name`, `tool_name`, `status`, `latency_ms` |
| `health:check` | Health checker — after health check completion | `server_name`, `status`, `latency_ms` |

**Key design decisions** (decided 2026-03-21):
- **SSE over WebSocket**: The event flow is unidirectional (server-to-client). SSE works through HTTP/2 and reverse proxies without upgrade negotiation, and the browser `EventSource` API handles reconnection automatically.
- **In-memory, not Redis**: Single-instance deployments do not need Redis overhead. For multi-instance horizontal scaling, Redis pub/sub can be added behind the same `SSEBroadcaster` interface.
- **Bounded buffers**: Slow clients do not cause memory growth. The 50-event buffer with oldest-drop policy ensures the broadcaster never blocks producers.

**SSE tenant isolation fix** (fixed v0.6.2, 2026-03-25): `span:new` events now include `project_id` in the payload. Without it, all project-scoped SSE subscribers received live span events from every tenant on the instance. The dashboard SSE consumer now filters events by `project_id` before updating state. This was a data leakage vector: a user connected to Project A could see real-time span metadata (agent name, tool name, status) from Project B.

**Multi-worker constraint** (decided v0.6.2, 2026-03-25): The Dockerfile default for `LANGSIGHT_WORKERS` was changed from 2 to 1. The SSE broadcaster, rate limiter token buckets, and auth cache are all in-process Python state. Under multi-worker (multi-process) Uvicorn, each worker holds an independent copy: SSE events published by worker A are not delivered to clients connected to worker B; rate limit budgets are doubled; auth cache state diverges. Set `LANGSIGHT_WORKERS=1` (the new default) for all deployments. Horizontal scaling requires a Redis-backed broadcaster (Tier 1.5, not yet shipped).

**Source**: `src/langsight/api/broadcast.py`, `src/langsight/api/routers/live.py`

### 2.15 Prometheus Metrics (added 2026-03-21)

**Purpose**: Expose LangSight internal metrics in Prometheus text exposition format for scraping by Prometheus, Grafana Agent, or any compatible collector.

**How it works**:
- `GET /metrics` endpoint registered without authentication (Prometheus scrapers need direct access)
- `PrometheusMiddleware` (Starlette `BaseHTTPMiddleware`) instruments every API request with counters and histograms
- Path normalization collapses UUIDs and long hex segments to `{id}` to keep metric cardinality bounded
- High-frequency internal paths (`/metrics`, `/api/liveness`, `/api/readiness`) are excluded from instrumentation

**Metrics exported**:
| Metric | Type | Labels | Description |
|---|---|---|---|
| `langsight_http_requests_total` | Counter | `method`, `path`, `status` | Total HTTP requests processed |
| `langsight_http_request_duration_seconds` | Histogram | `method`, `path` | Request duration with buckets from 10ms to 10s |
| `langsight_spans_ingested_total` | Counter | — | Total tool call spans ingested via `/traces/spans` and `/traces/otlp` |
| `langsight_active_sse_connections` | Gauge | — | Number of active SSE live feed connections |
| `langsight_health_checks_total` | Counter | `server`, `status` | Total health checks performed |

**Middleware stack** (order matters — outermost first):
1. `CORSMiddleware` — CORS headers
2. `SecurityHeadersMiddleware` — security response headers
3. `PrometheusMiddleware` — request count + duration histograms
4. `SlowAPIMiddleware` — rate limiting

**Key design decisions** (decided 2026-03-21):
- **No auth on `/metrics`**: Prometheus scrapers typically do not send auth headers. The endpoint exposes operational metrics, not user data. Network-level access control (firewall rules, Docker internal network) provides the security boundary.
- **Path normalization**: Without normalization, endpoints like `/api/agents/sessions/{session_id}` would create unbounded label cardinality. The `_normalize_path()` heuristic collapses hex strings longer than 8 characters to `{id}`.
- **`prometheus-client` library**: The standard Python Prometheus client library (`prometheus-client>=0.21`) — no custom exposition format.

**Source**: `src/langsight/api/metrics.py`

### 2.16 Health Tag Engine (added v0.3, 2026-03-22)

**Purpose**: Auto-classify completed sessions with a machine-readable health tag computed from span data. Tags enable one-click filtering in the dashboard and structured alerting.

**How it works**:
- `tag_from_spans(spans)` evaluates a session's flat list of spans against a priority-ordered rule set
- Tags are computed server-side after a session ends (or immediately when a `PREVENTED` span is ingested)
- The highest-priority matching tag wins — a session gets exactly one tag

**Tag priority order** (highest first):
| Tag | Condition | Priority |
|---|---|---|
| `loop_detected` | Any span with `status=prevented` and `"loop_detected"` in error | 1 |
| `budget_exceeded` | Any span with `status=prevented` and `"budget_exceeded"` in error | 2 |
| `circuit_breaker_open` | Any span with `status=prevented` and `"circuit_breaker"` in error | 3 |
| `schema_drift` | Any span with `"schema drift"` in error message | 4 |
| `timeout` | Any span with `status=timeout` | 5 |
| `tool_failure` | Any span with `status=error` (no fallback recovery) | 6 |
| `success_with_fallback` | Same tool called multiple times: some failed, some succeeded | 7 |
| `success` | All spans succeeded | 8 |

**Dashboard integration**:
- `HealthTagBadge` component (`dashboard/components/health-tag-badge.tsx`) renders colored badges
- Sessions page: `health_tag` column in the session list table
- Filter dropdown: filter sessions by health tag

**Key design decisions** (decided 2026-03-22):
- **Server-side, not client-side**: Tags are computed from the full span history, not from the SDK. This ensures tags are consistent regardless of which integration path was used (SDK, OTEL, LibreChat plugin).
- **Single tag per session**: A session does not accumulate multiple tags. The priority order ensures the most severe condition wins. This simplifies dashboard filtering and alerting.
- **`PREVENTED` status drives tag selection**: Prevention events (loop, budget, circuit breaker) take highest priority because they represent active interventions — the session was stopped, not just degraded.

**Source**: `src/langsight/tagging/engine.py`

### 2.12 Next.js Dashboard (Phase 4)

**Purpose**: Web UI for teams that prefer a visual interface over CLI.

**Pages**: Overview, Agents, Sessions, Health, Security, Costs, Settings

**Dashboard interaction model** (changed from original: consolidated on 2026-03-20):
- Sessions table links into a dedicated session detail route: `/sessions/[id]`
- Session detail page has two tabs:
  - `Details` — session timeline, lineage graph, right-side inspector
  - `Trace` — nested span tree with inline payload and error expansion
- Agent topology lives under the Agents page:
  - per-agent topology for the selected agent
  - fleet-wide topology modal powered by the same graph renderer
- `/lineage` is retained only as a redirect to `/agents`

**Design decisions**:
- shadcn/ui component library (fast to build, consistent look)
- Polls REST API (5s for health, 30s for metrics) for initial data; real-time updates via SSE live feed (`GET /api/live/events`) for instant span ingestion and health check notifications (added 2026-03-21)
- Charts via recharts
- No SSR needed — static SPA with API calls
- Shared raw SVG + `dagre` lineage renderer (decided 2026-03-20): replaced the earlier standalone lineage implementation so the same graph component can power both session-level and fleet-level topology views.

---

## 3. Data Flow Diagrams

### Health Check Flow
```
langsight monitor (or cron)
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
langsight security-scan
    │
    ├─→ Load MCP server configs from .langsight.yaml
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
langsight investigate "customer got wrong refund amount"
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
| `health_results` | MCP server health check results. `project_id` column added v0.7.0 (see migration note below). | 90 days |
| `mcp_tool_calls` | Every SDK/OTLP tool call span. Columns include `input_json Nullable(String)` and `output_json Nullable(String)` for payload capture (P5.1, added 2026-03-18); `llm_input Nullable(String)` and `llm_output Nullable(String)` for LLM reasoning capture (P5.3, added 2026-03-19); `replay_of String DEFAULT ''` to link replay spans back to their originals (P5.7, added 2026-03-19). MergeTree, TTL 90 days. | 90 days |
| `tool_calls_mv` | Materialized view: extracted tool call spans with metrics | 30 days |
| `tool_reliability_hourly` | Aggregated: per-tool success rate, latency percentiles, error counts per hour | 1 year |
| `cost_daily` | Aggregated: per-tool, per-agent cost per day | 1 year |
| `mcp_schema_snapshots` | Full tool schema JSON, stored on change (not on every check) | Forever |
| `schema_drift_events` | One row per atomic schema change (tool_removed, param_type_changed, etc.) with drift_type (BREAKING/COMPATIBLE/WARNING), old/new values, hashes. Drives `GET /api/health/servers/{name}/drift-history` and `GET /api/health/servers/{name}/drift-impact`. MergeTree, TTL 90 days. (added v0.8.0, 2026-03-26) | 90 days |

**Known scaling limit — project-scoped analytics**

The materialized views (`tool_calls_mv`, `tool_reliability_hourly`, `cost_daily`) aggregate globally — they do not include `project_id` in their GROUP BY. When the dashboard filters by project, queries fall back to the raw `mcp_tool_calls` table with a WHERE clause instead of reading the pre-aggregated view.

At current scale (demo data, single-digit projects) this is invisible — ClickHouse partition pruning on `toYYYYMM(started_at)` keeps scans fast. At 100k+ spans across 50+ projects, project-scoped dashboard pages will become noticeably slower.

**When to fix:** When a real user reports slow project-filtered queries. The fix is mechanical: add `project_id` to the GROUP BY in each materialized view, or create per-project MVs. This is a migration, not a redesign. Do not pre-optimize — the real query patterns should drive the MV schema.

**`mcp_tool_calls` payload columns** (added P5.1 + P5.3):
| Column | Type | Description |
|--------|------|-------------|
| `input_json` | `Nullable(String)` | JSON-serialised tool call arguments (`input_args` from `ToolCallSpan`). `NULL` when `redact_payloads=True`. (P5.1) |
| `output_json` | `Nullable(String)` | JSON-serialised tool return value (`output_result` from `ToolCallSpan`). `NULL` when `redact_payloads=True`. (P5.1) |
| `llm_input` | `Nullable(String)` | LLM prompt text extracted from OTLP `gen_ai.prompt` / `llm.prompts` attributes. Populated only on `span_type="agent"` spans originating from LLM generation spans. (P5.3) |
| `llm_output` | `Nullable(String)` | LLM completion text extracted from OTLP `gen_ai.completion` / `llm.completions` attributes. Populated only on `span_type="agent"` spans originating from LLM generation spans. (P5.3) |
| `replay_of` | `String DEFAULT ''` | When this span is a replay, contains the `span_id` of the original span being replayed. Empty string for non-replay spans. Links replay sessions back to their originals without a separate table. (P5.7, added 2026-03-19) |

### PostgreSQL (metadata — all data that requires relational integrity)

(changed from original: SQLite removed; all metadata now lives in Postgres; decided 2026-03-19)

| Table | What it stores |
|---|---|
| `mcp_servers` | Registered MCP server configs (name, transport, URL, auth, tags) |
| `security_scans` | Scan results (findings, scores, timestamps) |
| `alert_rules` | User-defined alert thresholds |
| `alerts` | Fired alerts with lifecycle (firing/ack/resolved) |
| `alert_config` | Singleton row: Slack webhook URL + per-alert-type enable flags. Previously in-memory in `app.state`; persisted to Postgres so settings survive API restarts. (added 2026-03-19) |
| `audit_logs` | Append-only auth/RBAC events: login, API key create/revoke, role change, settings saved. Previously an in-memory ring buffer (last 50 events); now a proper DB table with async writes via `asyncio.create_task`. (added 2026-03-19) |
| `api_keys` | API authentication keys (sha256-hashed, never plaintext). `project_id UUID NULL` added v0.8.1 — non-null means the key is project-scoped; NULL means global. |
| `users` | User accounts created at invite acceptance |
| `invite_tokens` | One-time invite tokens for user onboarding |
| `projects` | Project definitions (name, created_at) |
| `project_members` | Project membership: user_id, project_id, role (owner/member/viewer) |
| `model_pricing` | LLM model → price per 1K input/output tokens (16 seed rows: Anthropic, OpenAI, Google, Meta, AWS) |
| `agent_slos` | User-defined SLO definitions (`agent_name`, `metric`, `target`, `window_hours`, `created_at`). (P5.5, added 2026-03-19) |

**v0.8.0 new API endpoints** (added 2026-03-26):

| Endpoint | Description |
|---|---|
| `GET /api/health/servers/{name}/scorecard` | A-F composite health grade — score, grade, 5 dimension scores, cap_applied |
| `GET /api/health/servers/{name}/drift-history` | Recent schema drift events, newest first. `?limit=20` |
| `GET /api/health/servers/{name}/drift-impact?tool_name=<tool>&hours=24` | Agents/sessions that called a changed tool (consumer impact) |

**v0.8.1 schema migrations** (auto-applied on API startup, idempotent):

| Table | Change | Notes |
|-------|--------|-------|
| `api_keys` | `project_id UUID NULL` added via `ALTER TABLE … ADD COLUMN IF NOT EXISTS` | Existing keys retain `NULL` (global scope). New project-scoped keys set this to the target project UUID at creation. |

**v0.8.0 schema migrations** (auto-applied on API startup, idempotent):

| Table | Change | Notes |
|-------|--------|-------|
| `schema_drift_events` (ClickHouse) | New table created via `CREATE TABLE IF NOT EXISTS` | One row per atomic schema change; 90-day TTL |

**v0.7.0 schema migrations** (auto-applied on API startup, idempotent):

| Table | Change | Notes |
|-------|--------|-------|
| `health_results` | `project_id UUID NULL` added via `ALTER TABLE … ADD COLUMN IF NOT EXISTS` | Existing rows retain `NULL`; new checks tagged with project context |
| `audit_logs` | `project_id UUID NULL` added via `ALTER TABLE … ADD COLUMN IF NOT EXISTS` | Existing audit entries retain `NULL` |
| `mv_agent_sessions` (ClickHouse) | Materialized view dropped and rebuilt with `project_id` in SELECT and GROUP BY | Backfilled from `mcp_tool_calls` on startup; no span data lost |

---

## 5. Tech Stack Summary

| Layer | Technology | Why |
|---|---|---|
| **Core language** | Python 3.11+ | Best MCP SDK support, OTEL libraries, AI ecosystem |
| **CLI** | Click + Rich | Clean CLI framework + beautiful terminal output |
| **API** | FastAPI | Async, fast, auto-docs, Python-native |
| **OLAP** | ClickHouse | Proven for observability at scale (Langfuse, Helicone); analytics path in DualStorage |
| **Metadata DB** | PostgreSQL (asyncpg direct) | Reliable, well-understood for app state; metadata path in DualStorage |
| **Trace ingestion** | OTEL Collector (contrib) | Standard, ClickHouse exporter built-in |
| **Dashboard** | Next.js 15 + shadcn/ui + recharts | Fast to build, good component ecosystem |
| **MCP client** | `mcp` Python SDK | Official SDK for connecting to MCP servers |
| **RCA agent** | Claude Agent SDK | For Phase 2 root cause investigation |
| **Alerting** | Slack Block Kit + webhooks | Simple, widely used |
| **Containerization** | Docker Compose | Single `docker compose up` for full stack |
| **Metrics** | prometheus-client | Prometheus text exposition format for `/metrics` endpoint |
| **Testing** | pytest + httpx + testcontainers | Standard Python testing stack |
| **License** | Apache 2.0 | Free to use, modify, and distribute |

---

## 6. Integration Points

### MCP Server Discovery
LangSight discovers MCP servers from (updated v0.8.0, 2026-03-26):
1. `.langsight.yaml` config file (primary)
2. Auto-detect from 10+ IDE clients via `langsight init`:
   - Claude Desktop (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS, `~/.config/Claude/...` on Linux)
   - Cursor (`~/.cursor/mcp.json`) — key: `mcpServers`
   - VS Code (`~/Library/Application Support/Code/User/mcp.json` on macOS) — key: `servers`
   - Windsurf (`~/.codeium/windsurf/mcp_config.json`) — key: `mcpServers`
   - Claude Code (`~/.claude.json`) — key: `mcpServers`
   - Gemini CLI (`~/.gemini/settings.json`) — key: `mcpServers`
   - Kiro (`~/.kiro/settings/mcp.json`) — key: `mcpServers`
   - Zed (`~/.config/zed/settings.json`) — key: `context_servers`
   - Cline (VS Code extension `globalStorage`) — key: `mcpServers`
   - Project-local: `.cursor/mcp.json`, `.mcp.json`, `.vscode/mcp.json`
3. Manual registration via `langsight add <name> --url <url>` (HTTP) or `langsight add <name> --command <cmd>` (stdio) — added v0.8.0

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

**Path 2 — Framework Adapters (Phase 2)**: For agents built on CrewAI, Pydantic AI, OpenAI Agents SDK, Anthropic/Claude, or LangGraph.

```python
from langsight.integrations.crewai import LangSightCrewAICallback
crew = Crew(callbacks=[LangSightCrewAICallback()])

from langsight.integrations.openai_agents import LangSightOpenAIHooks
result = await Runner.run(agent, input="...", hooks=LangSightOpenAIHooks(client=client))

from langsight.integrations.anthropic_sdk import AnthropicToolTracer
tracer = AnthropicToolTracer(client=client, agent_name="my-agent")
await tracer.trace_response(response)  # traces all tool_use blocks

from langsight.integrations.langgraph import LangSightLangGraphCallback
result = await graph.ainvoke({"input": "..."}, config={"callbacks": [LangSightLangGraphCallback(client=client)]})
```

**Path 3 — OTEL Collector (Phase 3)**: For frameworks with native OTEL support. Point the OTEL exporter at LangSight's collector endpoint. No code changes needed in the agent.

| Framework | OTEL Support | Path |
|-----------|-------------|------|
| Pydantic AI | Native (`Agent.instrument_all()`) | Path 3 (OTEL) or Path 2 (adapter) |
| Strands (AWS) | Native (`pip install strands-agents[otel]`) | Path 3 (OTEL) |
| AG2/AutoGen | Native (`autogen.opentelemetry`) | Path 3 (OTEL) |
| Claude Agent SDK | Native | Path 3 (OTEL) |
| CrewAI | Via community OTEL package | Path 2 (adapter) preferred |
| OpenAI Agents SDK | Via community instrumentor | Path 2 (adapter) — `LangSightOpenAIHooks` (added 2026-03-21) |
| Anthropic SDK / Claude Agent SDK | No native OTEL | Path 2 (adapter) — `AnthropicToolTracer` / `LangSightClaudeAgentHooks` (added 2026-03-21) |
| LangGraph (dedicated) | Accepts LangChain callbacks | Path 2 (adapter) — `LangSightLangGraphCallback` for graph-aware node tracing (added 2026-03-21) |
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
| `clickhouse` | clickhouse/clickhouse-server:24 | 127.0.0.1:8123, 127.0.0.1:9000 | OLAP analytics storage (localhost-only, changed from 0.0.0.0 on 2026-03-21) |
| `postgres` | postgres:16-alpine | 127.0.0.1:5432 | Metadata storage (localhost-only, changed from 0.0.0.0 on 2026-03-21) |
| `otel-collector` | otel/opentelemetry-collector-contrib:0.120.0 | 4317, 4318 | Trace ingestion |
| `api` | langsight/api:latest | 127.0.0.1:8000 | REST API — localhost-only (changed from 0.0.0.0 in v0.7.0). Use a reverse proxy for public access. |
| `dashboard` | langsight/dashboard:latest | 127.0.0.1:3003 (→ 3002) | Next.js dashboard — localhost-only (changed from 0.0.0.0 in v0.7.0). Use a reverse proxy for public access. |

All required credentials are injected via env vars. The `${VAR:?error}` pattern in `docker-compose.yml` ensures compose refuses to start with missing secrets. Copy `.env.example` → `.env` and fill in all required values before `docker compose up -d`.

**Required env vars before compose up**: `POSTGRES_PASSWORD`, `CLICKHOUSE_USER`, `CLICKHOUSE_PASSWORD`, `LANGSIGHT_API_KEYS`, `AUTH_SECRET`, `LANGSIGHT_ADMIN_EMAIL`, `LANGSIGHT_ADMIN_PASSWORD`.

### Resource Estimates (Development)
| Service | CPU | Memory | Disk |
|---|---|---|---|
| ClickHouse | 1 core | 2 GB | 10 GB |
| PostgreSQL | 0.5 core | 512 MB | 1 GB |
| OTEL Collector | 0.5 core | 256 MB | — |
| API + Worker | 1 core | 1 GB | — |
| **Total** | **3 cores** | **~4 GB** | **~11 GB** |

### Storage Modes

(changed from original: SQLite mode removed 2026-03-19; `docker compose up -d` is now the minimum requirement)

| Mode | Backends | Use case |
|------|----------|----------|
| `dual` (default) | Postgres + ClickHouse | Production — full feature set |
| `postgres` | Postgres only | Metadata only — no analytics/tracing |
| `clickhouse` | ClickHouse only | Analytics only — no user/project management |

All modes require Docker. There is no zero-dependency CLI mode. Attempting `mode: sqlite` raises `ConfigError`:
```
Unknown storage mode 'sqlite'. Valid values: 'postgres', 'clickhouse', 'dual'.
SQLite has been removed — use 'dual' (Postgres + ClickHouse) for production
or 'postgres' for metadata-only deployments.
```

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
    │ Forwards to FastAPI (Docker bridge / localhost)
    ▼
  FastAPI
    └── _is_proxy_request(): trusts headers from LANGSIGHT_TRUSTED_PROXY_CIDRS
    └── _get_session_user(): extracts user_id + role from headers

SDK / CLI users:
  langsight CLI / Python SDK
    │ X-API-Key: <key>          (primary)
    │ Authorization: Bearer <key>   (also accepted — backward compat)
    ▼
  FastAPI
    └── _read_api_key(): reads X-API-Key first, then Authorization: Bearer
    └── verify_api_key(): validates against DB key table or env var keys
```

### SDK auth header fix (fixed 2026-03-19 — CRITICAL)

The SDK was sending `Authorization: Bearer <key>` but the API only read `X-API-Key`. This caused traces to be silently dropped in any authenticated deployment — the SDK appeared to work (no errors) but spans never reached the database.

Fix: `_read_api_key()` helper in `dependencies.py` now reads both headers in priority order:
1. `X-API-Key` (direct header — preferred)
2. `Authorization: Bearer <key>` (SDK backward compat)

The SDK now sends `X-API-Key`. Both forms are accepted permanently so existing integrations are not broken.

### Trusted proxy pattern (decided 2026-03-19; updated to CIDR model 2026-03-19)

FastAPI trusts `X-User-Id` and `X-User-Role` only when the request originates from a trusted CIDR. Trust list is configured via `LANGSIGHT_TRUSTED_PROXY_CIDRS` (comma-separated CIDRs/IPs), stored on `app.state.trusted_proxy_networks` at startup, and evaluated by `parse_trusted_proxy_networks()` + `_is_proxy_request()` in `dependencies.py`.

**Why CIDR instead of hardcoded localhost** (changed from original: was `{127.0.0.1, ::1}` hardcoded, now CIDR-configurable; decided 2026-03-19): The original hardcoded loopback list broke Docker deployments where the Next.js dashboard runs in a separate container. In Docker Compose, the dashboard's source IP is `172.x.x.x`, not `127.0.0.1`. CIDR-based trust allows the compose default (`172.16.0.0/12,10.0.0.0/8`) while remaining safe on bare-metal installs.

**Docker Compose default** (`LANGSIGHT_TRUSTED_PROXY_CIDRS`):
```
127.0.0.1/32,::1/128,172.16.0.0/12,10.0.0.0/8
```

**Security properties remain unchanged**:
- No JWT verification in FastAPI — no shared secret dependency
- Security boundary is the network: the proxy and API must not be internet-exposed directly
- External clients that set `X-User-*` headers from untrusted IPs are ignored

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

### Project isolation (added Phase 10, 2026-03-19; updated v0.8.1, 2026-03-26)

**`ApiKeyRecord.project_id`** (added v0.8.1): the `api_keys` Postgres table now has a nullable `project_id UUID` column. When a project-scoped API key is created in the dashboard, its `project_id` is set to the target project's UUID. A global key leaves `project_id = NULL`.

This makes the API key itself the project selector. Engineers no longer need to pass `?project_id=` query params or configure `.langsight.yaml` — they export `LANGSIGHT_API_KEY=<project-scoped-key>` and every CLI command is automatically scoped.

**`LangSightConfig` new fields** (v0.8.1):
- `project: str = ""` — human-readable project slug (display only, not used for routing)
- `project_id: str = ""` — project UUID, used as a fallback when the API key carries no `project_id`

**`HealthChecker(project_id=config.project_id)`** — the health checker now accepts a `project_id` at construction time and stamps all `health_results` rows with it. Previously health results were written without a project tag when using the CLI without a dashboard API key.

`get_active_project_id` FastAPI dependency (priority order updated v0.8.1):
1. API key's embedded `project_id` (highest priority — "API key = project")
2. `.langsight.yaml` `project_id` field (config file override)
3. `project_id` query param (advanced / direct API use)
4. Admin with no project context → `None` (global view, no filter)
5. Non-admin with no project context → HTTP 400

Previously the dependency read the query param first, then verified membership. The key-embedded `project_id` was not consulted at all. This change means the API key is the authoritative source of project context — the client never needs to know or supply the UUID.

All ClickHouse queries in `storage/clickhouse.py` that read from `mcp_tool_calls` accept an optional `project_id` parameter and apply it as a `WHERE project_id = {project_id}` clause. Filtering is at the DB layer — no Python post-filter.

---

## 9. Security Considerations

- **Two auth paths**: session headers (dashboard via Next.js proxy) and X-API-Key / Authorization: Bearer (SDK/CLI)
- **SDK auth header**: API accepts both `X-API-Key` and `Authorization: Bearer` — SDK sends `X-API-Key` (fixed 2026-03-19; was sending Bearer which was silently ignored)
- **Trusted proxy CIDRs**: `X-User-Id`/`X-User-Role` headers trusted only from `LANGSIGHT_TRUSTED_PROXY_CIDRS` (default: loopback; Docker default adds `172.16.0.0/12,10.0.0.0/8`). Changed from hardcoded loopback-only (2026-03-19) to support Docker network topology.
- **MCP credentials** stored in .langsight.yaml (gitignored) or env vars
- **CORS default**: `LANGSIGHT_CORS_ORIGINS` defaults to `"http://localhost:3003"` (changed from wildcard `"*"` on 2026-03-21). Production deployments must explicitly configure allowed origins.
- **No external exposure by default** — Docker network is internal, only dashboard port exposed. ClickHouse and Postgres ports bind to `127.0.0.1` (changed from `0.0.0.0` on 2026-03-21).
- **PII in traces**: `redact_payloads: true` config suppresses payload capture before transmission
- **Principle of least privilege**: Health checker uses read-only MCP operations only
- **Rate limiting**: Global default of `200/minute` applied to all API endpoints via a single shared `Limiter` instance in `src/langsight/api/rate_limit.py` (added 2026-03-21; refactored to single instance 2026-03-21 to fix per-route overrides). Per-route overrides: `POST /api/traces/spans` 2000/min, `POST /api/traces/otlp` 60/min, `POST /api/users/accept-invite` 5/min, `POST /api/users/verify` 10/min. All routers import the same `limiter` instance — previously separate `Limiter` instances prevented per-route overrides from taking effect. Health check frequency capped to avoid overloading MCP servers.
- **RBAC hardened** (2026-03-19): `POST/GET/DELETE /api/auth/api-keys` require admin role; `POST/DELETE /api/slos` require admin role; `list_projects` handles session-user path correctly; `get_active_project_id` and `get_project_access` both check DB keys (not just env keys) for auth-disabled logic
- **Project isolation**: all ClickHouse queries filtered by `project_id` at DB level when a project context is active
- **Security headers on API**: X-Content-Type-Options, X-Frame-Options, X-XSS-Protection, Referrer-Policy, HSTS on all API responses (via `SecurityHeadersMiddleware`)
- **Security headers on dashboard**: Next.js dashboard also sets X-Content-Type-Options, X-Frame-Options, X-XSS-Protection, Referrer-Policy, and Permissions-Policy headers on all responses (added 2026-03-21)
- **Alert config and audit logs persisted** (2026-03-19): previously stored in `app.state` (lost on restart); now in Postgres via `alert_config` (singleton upsert) and `audit_logs` (append-only) tables. `append_audit()` schedules async DB write via `asyncio.create_task` — never blocks the request path.
- **PII masking in audit logs** (added 2026-03-21): `_mask_email()` transforms emails to `"a***@example.com"` before writing to audit logs. Raw email addresses no longer appear in audit log entries.
- **No default secrets**: `docker-compose.yml` uses `${VAR:?error}` syntax — compose refuses to start if required vars are missing. No hardcoded passwords anywhere.
- **`/api/settings` auth hardened** (fixed v0.6.2, 2026-03-25): `GET /api/settings` now requires `verify_api_key`; `PUT /api/settings` now requires `verify_api_key` + `require_admin`. Previously both endpoints were completely unprotected — any client with network access could read or overwrite global instance settings (including `redact_payloads`).
- **SSE tenant isolation** (fixed v0.6.2, 2026-03-25): `span:new` SSE events now include `project_id` in the payload. Dashboard consumers filter by `project_id` before updating state. Previously, all subscribers on any project received all tenants' live events. See section 2.14 for implementation details.
- **Health endpoint cross-tenant leak fixed** (fixed v0.6.2, 2026-03-25): `GET /api/health/servers/{name}` and `GET /api/health/servers/{name}/history` now pass `project_id` to storage queries. Previously the project-membership check passed but the underlying ClickHouse query fetched rows from all projects sharing the same `server_name`.
- **ClickHouse timeouts** (added v0.6.2, 2026-03-25): ClickHouse client now sets `connect_timeout=5s` and `send_receive_timeout=30s`. Previously no timeouts were configured — a hung ClickHouse connection would block the span ingestion path indefinitely.
- **Postgres pool sizing** (updated v0.6.2, 2026-03-25): `pg_pool_max` default raised from 20 to 50. Override via `LANGSIGHT_PG_POOL_MAX` env var. Small-instance operators should lower this to match `max_connections` in their Postgres configuration.
- **API and dashboard port binding hardened** (v0.7.0, 2026-03-26): `api` and `dashboard` Docker services now bind to `127.0.0.1` only (changed from `0.0.0.0`). Previously both services were reachable on all network interfaces. Users who need public access must place a reverse proxy (nginx, Caddy) in front of port 3003. Port 8000 must not be exposed publicly — authentication relies on the dashboard's Next.js proxy layer.
- **Password minimum length enforced** (v0.7.0, 2026-03-26): All user passwords (admin bootstrap via `LANGSIGHT_ADMIN_PASSWORD` and invited users at invite acceptance) are validated to be at least 12 characters. Shorter passwords are rejected at the API layer.
- **Webhook SSRF protection** (v0.7.0, 2026-03-26): Webhook URLs submitted to `PUT /api/settings` (Slack webhook) and alert rule creation are validated against an SSRF blocklist. Requests targeting private IP ranges (RFC 1918: 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16), loopback (127.0.0.0/8), and cloud metadata endpoints (169.254.169.254) are rejected with HTTP 422.
- **`/metrics` endpoint token** (v0.7.0, 2026-03-26): `GET /metrics` logs a warning at startup when `LANGSIGHT_METRICS_TOKEN` is not set. When the token is set, the endpoint requires `Authorization: Bearer <token>`. Unprotected metrics are acceptable in localhost-only deployments but should be secured in any publicly reachable configuration.
- **`InvestigateConfig.api_key` removed** (v0.7.0, 2026-03-26): The `api_key` field under `investigate:` in `.langsight.yaml` has been removed. LLM provider API keys must be supplied exclusively via environment variables (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`). The field was never persisted to the database — removal prevents accidental secret storage in config files.
