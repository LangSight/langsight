# LangSight — Build Progress

> Last updated: 2026-03-23 (DateRangeFilter + Timestamp components, session detail page redesign, lineage graph node/toolbar/minimap redesign, graph builder extraction)
> Maintained by: docs-keeper agent — update after every feature, architectural decision, or milestone

**Project framing**: LangSight is an **agent runtime reliability platform** — prevent loops, enforce budgets, detect cascading failures, monitor MCP health, and scan for CVEs. Not another prompt, eval, or simulation platform. **Prevent. Detect. Monitor. Map.** Langfuse watches the brain. LangSight watches the hands. Agent-level instrumentation captures all tool types. MCP servers additionally receive proactive health checks, security scanning, schema drift detection, and alerting because the MCP protocol is standard and inspectable. (changed from original: was "observability platform" positioning; pivoted to "runtime reliability" 2026-03-22)

---

## Dashboard UX Polish (2026-03-23)

### DateRangeFilter component

- `dashboard/components/date-range-filter.tsx` — reusable date range control for all data pages.
- Five presets: `1h`, `6h`, `24h`, `7d`, `30d` (active preset highlighted with primary teal).
- Custom date picker: dropdown with From/To `<input type="date">` fields. Apply converts to ISO strings (`T00:00:00` / `T23:59:59`). Clicking outside closes via `mousedown` listener.
- Integrated into Sessions, Costs, Health, Agents, and Servers pages.

### Timestamp component

- `dashboard/components/timestamp.tsx` — semantic `<time>` element with relative + exact display.
- Default: "16h ago · Mar 22, 14:30:05" (exact at 60% opacity).
- Compact: "16h ago" only; exact time in `title` attribute (tooltip on hover). Used in sessions list "Started" column and health uptime dot tooltips.
- Used across sessions, session detail, health, agents, servers, and settings pages.

### Session detail page redesigned

- `dashboard/app/(dashboard)/sessions/[id]/page.tsx` — wide-screen optimized layout.
- Right-panel uses `MetricTile` sub-components (rounded tile, colored left border: primary or danger).
- `SectionLabel` sub-component standardizes panel section headings.
- `useSessionGraph` hook wraps `buildSessionGraph` in `useMemo`; recomputes only when trace, expandedGroups, or expandedEdges change.

### Graph builder extracted

- `dashboard/lib/session-graph.ts` — `buildSessionGraph(trace, expandedGroups, expandedEdges): SessionGraphResult`.
- Isolates all graph-construction logic from the session detail page; improves testability.
- `findRepeatedCall`: detects the most-repeated (tool, input) pair in a span list.
- `buildCallLabels`: generates per-call sequence labels (e.g. `read_file [1/3]`) to disambiguate repeated tools on one edge.

### Lineage graph nodes, toolbar, minimap redesigned

- `dashboard/components/lineage-graph.tsx` — node cards redesigned with compact metric pills (calls, errors, avg latency). Tighter padding. Loop annotation row shows repeated tool name + count.
- Agent nodes: teal gradient header. Server nodes: slate gradient. Selection: glass-morphism glow.
- Back-edges (cycles): rendered as self-loop arcs on the right side of the source node.
- Minimap: now uses `ResizeObserver` for live container size. Auto-fits graph into viewport on first render via `hasFitted` ref guard.

---

## v0.2.0 Dashboard UX Changes (2026-03-20)

### Session detail — graph toolbar, minimap, timeline, PayloadSlideout (2026-03-20)

- Graph toolbar (top-left overlay): search bar with node highlight/dim, zoom slider (25-250%), Expand All / Collapse All, Failures toggle. Keyboard shortcuts: `/` search, `f` fit, `e` error, `+`/`-` zoom, `Esc` deselect.
- Minimap (150×90px, bottom-right): full-graph overview with draggable viewport rectangle.
- Timeline bar (above graph): one colored segment per `tool_call` span; click to select node.
- `PayloadSlideout` component: full-width slide-over with JSON + line numbers, copy, word wrap toggle, tab selector, Esc to close.
- Per-tool edge expansion: circular `+` button on edges with call count (e.g. `5×`) — splits server node into per-tool sub-nodes.
- "View in Catalog" links from node detail panels navigate to `/agents` or `/servers`.

### MCP Servers catalog at `/servers` (2026-03-20)

- New page using the same adaptive 3-state layout as Agents.
- Detail panel: About (editable), Tools (declared tools from SDK auto-capture + reliability metrics), Health (uptime%, trend chart, last 15 checks), Consumers (from lineage).
- "MCP Servers" added to sidebar primary nav between Agents and Costs.
- New PostgreSQL tables: `server_metadata` (editable catalog data), `server_tools` (declared tool schemas).
- New API: `GET/PUT /api/servers/metadata`, `GET/PUT /api/servers/{name}/tools`.

### Agents catalog — 3-state adaptive layout (2026-03-20)

- State 1 (no agent selected): full-width sortable table with Needs Attention banner.
- State 2 (agent selected): 280px sidebar + detail panel (About / Overview / Topology / Sessions tabs).
- State 3 (Topology tab active): sidebar collapses to 56px icon rail, graph fills full width.
- Editable metadata fields (description, owner, tags, status, runbook URL) on the About tab.
- New component: `dashboard/components/editable-field.tsx` — `EditableText`, `EditableTextarea`, `EditableTags`, `EditableUrl`.
- New component: `dashboard/components/agent-topology.tsx` — `LineageGraph` scoped to a single agent.

### SDK automatic tool schema capture (2026-03-20)

- `MCPClientProxy.list_tools()` intercepted; tool names, descriptions, and input schemas fire-and-forget posted to `PUT /api/servers/{server_name}/tools` on every call.
- Fail-open: `list_tools()` returns normally even if the backend is unreachable.
- Tools tab in the MCP Servers catalog now populates automatically without needing the health checker to run.

### Session debugging moved to a dedicated page

- `/sessions/[id]` is now the primary session debugging surface
- Two tabs:
  - `Details` — timeline + interactive lineage graph + right-side detail panel
  - `Trace` — nested span tree with inline payload and error expansion
- Replay and session comparison are now initiated from the session detail page rather than the older sessions-table workflow

### Shared lineage graph renderer

- React Flow has been replaced with a shared raw SVG + `dagre` renderer in `dashboard/components/lineage-graph.tsx`
- The same renderer now powers:
  - session-level flow inspection
  - per-agent topology on the Agents page
  - fleet-wide topology in the Agents page modal
- `/lineage` now redirects to `/agents`; topology exploration is consolidated under the Agents experience

---

## v0.2.0 Infrastructure Changes (2026-03-19)

### SQLite removed — DualStorage is the production topology

| Change | Details |
|--------|---------|
| `storage/sqlite.py` | DELETED — `SQLiteBackend` no longer exists |
| `storage/dual.py` | NEW — `DualStorage` routes metadata → Postgres, analytics → ClickHouse |
| `storage/factory.py` | Updated — `open_storage()` dispatches `mode="dual"` (default); raises `ConfigError` on `mode="sqlite"` with migration message |
| `config.py` `StorageConfig.mode` | Default changed from `"sqlite"` → `"dual"` |
| `docker-compose.yml` | Postgres port 5432 + ClickHouse 8123/9000 exposed to host; `${VAR:?error}` required-var enforcement; `.env.example` added |

### SDK auth header fix (CRITICAL)

SDK was sending `Authorization: Bearer <key>`, API only read `X-API-Key`. Traces were silently dropped in authenticated deployments. Fixed in `dependencies.py` via `_read_api_key()` which now reads both headers. SDK now sends `X-API-Key`. Both forms permanently accepted.

### Proxy trust — CIDR-based (was hardcoded loopback)

`LANGSIGHT_TRUSTED_PROXY_CIDRS` env var (default: `127.0.0.1/32,::1/128`; Docker default: adds `172.16.0.0/12,10.0.0.0/8`). `parse_trusted_proxy_networks()` + `_is_proxy_request()` in `dependencies.py`. Previously hardcoded `{127.0.0.1, ::1}` — broken for Docker deployments where Next.js runs in a separate container.

### Alert config + audit logs persisted to DB

- `alert_config` — Postgres singleton upsert; previously in `app.state` (lost on restart)
- `audit_logs` — Postgres append-only table; previously in-memory ring buffer (lost on restart)
- `append_audit()` uses `asyncio.create_task` — never blocks request path

### RBAC hardened

- API key CRUD endpoints now require admin role
- SLO write endpoints now require admin role
- `list_projects` session-user path fixed
- `get_active_project_id` and `get_project_access` check DB keys for auth-disabled logic

### Integration test infrastructure

- `tests/conftest.py`: `require_postgres`, `require_clickhouse`, `require_all_services` fixtures with auto-skip
- `tests/integration/storage/test_postgres_storage.py`: full Postgres tests against real DB
- Regression tests migrated from SQLiteBackend to PostgresBackend

### Test metrics (v0.2.0)

| Metric | Value |
|--------|-------|
| Unit tests | 694 |
| Coverage | 77% (threshold: 75%) |
| ruff | All checks passed |
| mypy | Success: no issues (68 source files) |

---

## Security Assessment — Action Required (2026-03-18)

A security review was conducted against the codebase as of 2026-03-18. The overall assessment is: **strong OSS alpha with critical gaps that must be resolved before production positioning**.

### P0 — Blockers (must fix before any public deployment)

| ID | Finding | Location |
|----|---------|----------|
| P0.1 | API is unauthenticated | `api/main.py` line 56 (wildcard CORS), no auth dependency on routers line 63. Anyone who can reach port 8000 can trigger scans, ingest spans, and read all data. |
| P0.2 | Dashboard auth is demo-only | `dashboard/lib/auth.ts` — hardcoded users, any password accepted, static secret fallback. UI appears productized; identity layer is not. |

### P1 — Important (fix before broader adoption)

| ID | Finding | Location |
|----|---------|----------|
| P1.1 | Docker Compose uses insecure defaults | ClickHouse default user, default Postgres password, databases exposed to host network, known dashboard secret as default value |
| P1.2 | README overstates production completeness | Claims per-session costs in sessions output, but cost field is absent from `langsight sessions` CLI; cost engine `total` is a placeholder |

### Production Readiness Gaps

The following items are required before LangSight can be positioned as production-grade:

| # | Gap | Priority |
|---|-----|----------|
| 1 | Real authn/authz for API (API keys or OIDC) and dashboard | P0 |
| 2 | Hardened deployment assets — no default secrets, no public DB ports, TLS, secret injection | P1 |
| 3 | Schema migration strategy — Alembic for Postgres, ClickHouse migration tooling | P1 |
| 4 | Honest feature matrix — separate shipped features from roadmap items | P1 |
| 5 | Operational hardening — rate limiting, audit logging, Prometheus metrics, readiness/liveness probes | P1 |
| 6 | Security posture docs — threat model, deployment topology, vulnerability disclosure policy | P1 |

### Current Honest Positioning

LangSight v0.2.0 is a **self-hosted agent runtime reliability platform** with MCP health monitoring, security scanning, session tracing, and cost attribution. It is suitable for:
- Self-hosted production deployments within trusted networks
- Internal team use with full auth/RBAC
- Local development and experimentation

(changed from original: was "observability and security toolkit" — now "runtime reliability platform" per 2026-03-22 positioning pivot)

---

## Phase 5 — Deep Runtime Reliability Features: Gap Analysis (2026-03-18)

A thorough code review identified a set of high-value runtime reliability features that are implied by the product vision but not yet built. These form Phase 5.

### Gap Table

| Feature | Gap Severity | Blocks |
|---------|-------------|--------|
| Input/output payload capture (P5.1) | ✅ Implemented (2026-03-18) | P5.2, P5.6, P5.7 |
| Session replay trace tree UI (P5.2) | ✅ Implemented (2026-03-19) | Debugging workflows |
| LLM reasoning capture (P5.3) | ✅ Implemented (2026-03-19) | Full session context |
| Statistical anomaly detection (P5.4) | ✅ Implemented (2026-03-19) | Proactive incident detection |
| Agent SLO tracking (P5.5) | ✅ Implemented (2026-03-19) | SLO-based alerting |
| Side-by-side session comparison (P5.6) | ✅ Implemented (2026-03-19) | Playground replay |
| Playground replay (P5.7) | ✅ Implemented (2026-03-19) | Iterative debugging |

### What IS built (confirmed from code review)

- `ToolCallSpan` fields: `span_id`, `parent_span_id`, `span_type` (`tool_call`/`agent`/`handoff`), `trace_id`, `session_id`, `server_name`, `tool_name`, `started_at`, `ended_at`, `latency_ms`, `status`, `error`, `agent_name`
- ClickHouse `mcp_tool_calls` table with all the above columns
- `mv_tool_reliability` materialized view (hourly aggregates: `success_rate`, `avg_latency`, `error_calls`)
- `mv_agent_sessions` materialized view (per-session: `tool_calls`, `failed_calls`, `duration_ms`, `servers_used`)
- `get_session_trace(session_id)` — returns flat span list ordered by time (tree reconstruction done by caller)
- `get_agent_sessions()` — session list with aggregates
- `get_tool_reliability()` — tool metrics from MV
- `MCPClientProxy.call_tool()` — captures timing, status, error — **NOT args/result**
- SDK sends spans fire-and-forget via `asyncio.create_task`
- OTLP parser extracts MCP spans from OTLP/JSON payloads; extracts `gen_ai.agent.name` but **not prompt/completion content**
- Cost engine: `get_cost_call_counts()` groups by server/tool/agent/session

### What is NOT built (the gaps)

- ~~`input_args` and `output_result` fields on `ToolCallSpan`~~ — **built (P5.1, 2026-03-18)**: `input_args`/`output_result` on `ToolCallSpan`; `input_json`/`output_json` columns in ClickHouse `mcp_tool_calls`; `redact_payloads` config flag
- ~~LLM reasoning capture (`gen_ai.prompt`, `gen_ai.completion`) not extracted from OTLP spans~~ — **built (P5.3, 2026-03-19)**: OTLP spans with `gen_ai.prompt`/`gen_ai.completion` (or `llm.prompts`/`llm.completions`) are parsed into agent spans with `llm_input`/`llm_output`; "Prompt"/"Completion" panels visible in session trace tree; `intValue`/`doubleValue`/`boolValue` OTLP attributes now also handled
- ~~No confirmed dashboard UI that renders a session as a visual trace timeline/tree~~ — **built (P5.2, 2026-03-19)**: sessions page trace tree now shows inline payload panels per span; `SpanNode` API and TypeScript type include `input_json`/`output_json`
- ~~No statistical baseline learning — alerts are purely threshold-based~~ — **built (P5.4, 2026-03-19)**: `AnomalyDetector` computes z-score per tool against 7-day ClickHouse baseline; `warning` at |z|>=2, `critical` at |z|>=3; minimum stddev guards prevent false positives; `GET /api/reliability/anomalies` endpoint; dashboard "Anomalies Detected" card with critical/warning breakdown
- ~~No `AgentSLO` model, no SLO evaluator, no burn rate calculation~~ — **built (P5.5, 2026-03-19)**: `SLOMetric` StrEnum, `AgentSLO` and `SLOEvaluation` Pydantic models; `agent_slos` table in SQLite and PostgreSQL; `SLOEvaluator` evaluates session data; `success_rate` = clean/total sessions; `latency_p99` uses `max(duration_ms)` as conservative proxy; `/api/slos` CRUD; dashboard Overview "Agent SLOs" panel; CLI commands deferred
- ~~No session comparison API endpoint or UI~~ — **built (P5.6, 2026-03-19, refined 2026-03-20)**: `compare_sessions()` on ClickHouse backend; `GET /api/agents/sessions/compare?a=&b=` endpoint; comparison now runs from the dedicated `/sessions/[id]` page and renders an inline side-by-side diff table with matched/diverged/only-in-one-session states and latency deltas
- ~~No playground replay~~ — **built (P5.7, 2026-03-19, refined 2026-03-20)**: `ReplayEngine` in `src/langsight/replay/engine.py`; `replay_of` field on `ToolCallSpan` and `mcp_tool_calls`; `POST /api/agents/sessions/{id}/replay` endpoint; Replay action now lives on the dedicated session detail page

### Implementation Order and Rationale

The order is determined by dependency. P5.1 is the foundation — without payload capture, session replay (P5.2), comparison (P5.6), and replay (P5.7) are all blocked or severely limited. P5.3, P5.4, and P5.5 are independent and can proceed in parallel once P5.1 is done. P5.6 requires P5.1. P5.7 requires both P5.1 and P5.6.

```
P5.1 (Payload Capture)
  ├── P5.2 (Session Replay UI)         — blocked on P5.1
  ├── P5.3 (LLM Reasoning Capture)     — independent, can run in parallel
  ├── P5.4 (Anomaly Detection)         — independent, can run in parallel
  ├── P5.5 (SLO Tracking)              — independent, can run in parallel
  └── P5.6 (Session Comparison)        — blocked on P5.1
        └── P5.7 (Playground Replay)   — blocked on P5.1 + P5.6
```

---

## Phase 6 — Project-Level RBAC: Planned (2026-03-19)

A project is the top-level isolation boundary. Every piece of reliability data belongs to a project. Users hold project-level roles (`owner`, `member`, `viewer`). Global admins retain cross-project visibility. Non-members receive HTTP 404 on any project endpoint to prevent enumeration.

### Sub-phases

| ID | Description | Status |
|----|-------------|--------|
| P6.1 | Data model — `Project`, `ProjectMember` Pydantic models; `projects` + `project_members` tables; `project_id` columns on `mcp_tool_calls`, `agent_slos`, `api_keys`; Alembic migration | NOT STARTED |
| P6.2 | Storage layer — project + member CRUD protocol methods; implemented on `SQLiteBackend` and `PostgresBackend` | NOT STARTED |
| P6.3 | API middleware — `get_project` dependency (404 for non-members, global admin bypass); `require_project_role` factory; `/api/projects` router with 9 endpoints | NOT STARTED |
| P6.4 | Scope existing endpoints — optional `project_id` query param on sessions, reliability, costs, SLOs, and traces ingestion endpoints | NOT STARTED |
| P6.5 | SDK — `project_id` param on `LangSightClient`; propagated to every `ToolCallSpan` | NOT STARTED |
| P6.6 | Dashboard — project switcher in sidebar; active project in localStorage; Settings > Projects tab for create/invite/manage | NOT STARTED |
| P6.7 | Bootstrap — `_bootstrap_default_project()` creates "Default" project with admin as owner on first API startup; idempotent | NOT STARTED |

---

## Phase 7 — Model-Based Cost Tracking: Planned (2026-03-19)

Token-aware cost engine. LLM spans carry `input_tokens`/`output_tokens`/`model_id` from OTLP attributes and are priced against a managed `model_pricing` table seeded with 16 models across Anthropic, OpenAI, Google, Meta, and AWS. Non-LLM tool spans continue to use the existing call-based `CostRule` pricing from `.langsight.yaml`. The costs breakdown response splits `llm_cost_usd` from `tool_cost_usd`. Settings page adds a model pricing management table. Costs page adds a "By Model" token breakdown.

### Sub-phases

| ID | Description | Status |
|----|-------------|--------|
| P7.1 | `model_pricing` table + 16 seed rows + `StorageBackend` protocol methods; Alembic migration | NOT STARTED |
| P7.2 | `input_tokens`, `output_tokens`, `model_id` fields on `ToolCallSpan`; ClickHouse DDL; OTLP parser extraction | NOT STARTED |
| P7.3 | `ModelPricingLookup` helper; token-based vs call-based cost routing; `project_id` scoping on all cost endpoints; `llm_cost_usd`/`tool_cost_usd` split in response | NOT STARTED |
| P7.4 | `GET /api/costs/models`, `POST /api/costs/models`, `PATCH /api/costs/models/{id}`, `DELETE /api/costs/models/{id}` — admin-gated CRUD with audit trail | NOT STARTED |
| P7.5 | Dashboard Settings: `ModelPricingSection` component — table grouped by provider, inline edit, "Add custom model" modal | NOT STARTED |
| P7.6 | Dashboard Costs: "LLM Tokens Cost" + "Tool Calls Cost" summary cards; "By Model" token breakdown table | NOT STARTED |

---

## Current Status: Release 0.1.0 — Shipped ✅

```
Phase 1 (CLI MVP)               ████████████████ 100% — COMPLETE ✅
Phase 2 (SDK + Framework Integ) ████████████████ 100% — COMPLETE ✅
Phase 3 (OTEL + Costs)          ████████████████  95% — COMPLETE ✅
Release 0.1.0                   ████████████████ 100% — SHIPPED ✅ (PyPI + GitHub)
Phase 4 (Dashboard + Website)   ██████████████░░  90% — costs API + agents page added, Vercel deploy pending
Security Hardening (S.1-S.10)   ░░░░░░░░░░░░░░░░   0% — NOT STARTED
Phase 5 (Deep Reliability)      ████████████████ 100% — COMPLETE ✅ P5.1 (2026-03-18), P5.2-P5.7 (2026-03-19)
Phase 6 (Project-Level RBAC)    ░░░░░░░░░░░░░░░░   0% — NOT STARTED
Phase 7 (Model-Based Costs)     ░░░░░░░░░░░░░░░░   0% — NOT STARTED
```

---

## Metrics

| Metric | Value |
|--------|-------|
| Test count | 694 unit tests |
| Coverage | 77% (threshold 75%) |
| ruff | All checks passed |
| mypy | Success: no issues (68 source files) |
| CLI commands live | 8 (`init`, `mcp-health`, `security-scan`, `monitor`, `investigate`, `costs`, `sessions`, `serve`) |
| Storage backends | 2 active (PostgreSQL metadata, ClickHouse analytics) — SQLite removed v0.2.0 |
| Storage modes | `postgres` \| `clickhouse` \| `dual` (default: `dual`) |
| Framework integrations | 5 (LangChain/Langflow/LangGraph/LangServe, CrewAI, Pydantic AI, LibreChat, OTEL) |
| LLM providers for investigate | 4 (Claude, OpenAI, Gemini, Ollama) |
| Mintlify docs pages | 28 |
| PyPI release | `langsight==0.1.0` published |
| GitHub release | `v0.1.0` tagged |
| Marketing website | Built (`website/app/page.tsx`) — Vercel deploy pending |
| Product dashboard | Built (`dashboard/`) — production auth (NextAuth + API keys), full RBAC |

---

## Phase 1 — COMPLETE ✅ (100%)

### Infrastructure & Tooling
| Item | Status | Date | Notes |
|------|--------|------|-------|
| GitHub repo | ✅ Done | 2026-03-16 | github.com/LangSight/langsight |
| README.md | ✅ Done | 2026-03-16 | Full feature overview, architecture, CLI reference, roadmap |
| CLAUDE.md | ✅ Done | 2026-03-16 | Engineering standards, agent workflow, testing mandate |
| Product docs (5 files) | ✅ Done | 2026-03-16 | spec, architecture, UI/features, impl plan, risk assessment |
| .gitignore | ✅ Done | 2026-03-16 | Covers .env, .venv, .claude/skills/, secrets |
| skills-lock.json | ✅ Done | 2026-03-16 | 52 active project skills locked |
| 6 specialised agents | ✅ Done | 2026-03-16 | tester, security-reviewer, debugger, release-engineer, docs-keeper, git-keeper |

### Test MCP Servers (`test-mcps/`)
| Item | Status | Date | Notes |
|------|--------|------|-------|
| `postgres-mcp` | ✅ Done | 2026-03-16 | 5 tools, asyncpg pool, SELECT-only guard, FastMCP |
| `s3-mcp` | ✅ Done | 2026-03-16 | 7 tools, boto3 session, pagination, fnmatch search |
| `docker-compose.yml` | ✅ Done | 2026-03-16 | postgres:16-alpine, health check, resource limits, named volume |
| `seed.sql` | ✅ Done | 2026-03-16 | 5 tables, 10 customers, 10 orders, 5 agent_conversations |

### Core Source (`src/langsight/`)
| Item | Status | Date | Notes |
|------|--------|------|-------|
| `pyproject.toml` | ✅ Done | 2026-03-16 | src layout, uv, ruff, mypy strict, entry point |
| `exceptions.py` | ✅ Done | 2026-03-16 | LangSightError hierarchy |
| `models.py` | ✅ Done | 2026-03-16 | MCPServer, HealthCheckResult, ToolInfo, enums |
| `config.py` | ✅ Done | 2026-03-16 | .langsight.yaml loader, AlertConfig, StorageConfig, Settings |
| `health/transports.py` | ✅ Done | 2026-03-16 | stdio + SSE via MCP SDK, hash_tools() |
| `health/checker.py` | ✅ Done | 2026-03-16 | concurrent check_many(), storage-aware, drift detection |
| `health/schema_tracker.py` | ✅ Done | 2026-03-16 | drift detection — baseline + compare across runs |
| `storage/base.py` | ✅ Done | 2026-03-16 | StorageBackend Protocol — SaaS-safe abstraction |
| `storage/sqlite.py` | DELETED | 2026-03-19 | SQLite backend removed — use `mode: dual` or `mode: postgres` instead |
| `storage/dual.py` | ✅ Done | 2026-03-19 | DualStorage — routes metadata → Postgres, analytics → ClickHouse |
| `storage/postgres.py` | ✅ Done | 2026-03-17 | PostgreSQL backend, asyncpg direct (no SQLAlchemy) |
| `storage/factory.py` | ✅ Done | 2026-03-19 | `open_storage()` factory — dispatches `postgres`/`clickhouse`/`dual`; raises ConfigError on unknown mode |
| `security/models.py` | ✅ Done | 2026-03-16 | Severity, SecurityFinding, ScanResult |
| `security/owasp_checker.py` | ✅ Done | 2026-03-16 | 5 OWASP MCP checks |
| `security/poisoning_detector.py` | ✅ Done | 2026-03-16 | injection phrases, exfiltration, URLs, hidden unicode, base64 |
| `security/cve_checker.py` | ✅ Done | 2026-03-16 | OSV API, pyproject.toml + package.json, fail-open |
| `security/scanner.py` | ✅ Done | 2026-03-16 | concurrent: OWASP + poisoning + CVE |
| `alerts/engine.py` | ✅ Done | 2026-03-16 | state-transition alerts (DOWN/recovery/drift/latency), deduplication |
| `alerts/slack.py` | ✅ Done | 2026-03-16 | Slack Block Kit, fail-open |
| `alerts/webhook.py` | ✅ Done | 2026-03-16 | generic JSON webhook, fail-open |
| `cli/main.py` | ✅ Done | 2026-03-16 | Click entry point |
| `cli/mcp_health.py` | ✅ Done | 2026-03-16 | Rich table, --json, exit 1 on DOWN/DEGRADED, SQLite wired |
| `cli/security_scan.py` | ✅ Done | 2026-03-16 | Rich table, --json, --ci flag |
| `cli/monitor.py` | ✅ Done | 2026-03-16 | `langsight monitor --once/--interval`, fires alerts on transitions |
| `cli/init.py` | ✅ Done | 2026-03-16 | auto-discovers Claude Desktop, Cursor, VS Code MCP configs |
| `api/main.py` | ✅ Done | 2026-03-17 | FastAPI app factory, `langsight serve` |
| `api/routers/health.py` | ✅ Done | 2026-03-17 | `/api/health/*` endpoints |
| `api/routers/security.py` | ✅ Done | 2026-03-17 | `/api/security/scan` endpoint |
| `api/main.py` (`@app.get("/api/status")`) | ✅ Done | 2026-03-17 | `/api/status` endpoint defined inline in main.py (no separate status.py) |

### CI/CD
| Item | Status | Date | Notes |
|------|--------|------|-------|
| GitHub Actions — lint | ✅ Done | 2026-03-17 | ruff check + ruff format + mypy |
| GitHub Actions — unit/regression | ✅ Done | 2026-03-17 | pytest, 88% coverage gate |
| GitHub Actions — integration | ✅ Done | 2026-03-17 | docker compose up, real MCP servers |

### Tests
| Item | Status | Coverage | Notes |
|------|--------|----------|-------|
| `test_exceptions.py` | ✅ Done | 100% | |
| `test_models.py` | ✅ Done | 100% | |
| `test_config.py` | ✅ Done | 98% | |
| `health/test_checker.py` | ✅ Done | 85% | mocked ping + storage |
| `health/test_schema_tracker.py` | ✅ Done | 100% | mocked storage |
| `storage/test_sqlite.py` | ✅ Done | 100% | real in-memory SQLite |
| `storage/test_postgres.py` | ✅ Done | — | |
| `cli/test_mcp_health.py` | ✅ Done | — | Click CliRunner, mocked storage |
| `cli/test_security_scan.py` | ✅ Done | — | |
| `cli/test_monitor.py` | ✅ Done | — | |
| `api/test_health_router.py` | ✅ Done | — | |
| `integration/health/test_checker_integration.py` | ✅ Done | — | requires docker compose up |
| `regression/test_health_pipeline.py` | ✅ Done | — | 10 tests: baseline, no-drift, drift, down, recovery |
| `unit/test_cost_engine.py` | ✅ Done | 2026-03-18 | 86 lines — `AgentCostEntry`, `SessionCostEntry`, `aggregate_cost_rows()` |
| `unit/api/test_costs_router.py` | ✅ Done | 2026-03-18 | 134 lines — all three cost endpoints |
| `integration/storage/test_costs_integration.py` | ✅ Done | 2026-03-18 | ClickHouse `get_cost_call_counts()` integration |
| **Overall coverage** | | **85.39%** | target: 80% ✅ (385 tests) |

### Phase 1 — Additional Items Completed (beyond original scope)
| Item | Status | Date | Notes |
|------|--------|------|-------|
| `cli/costs.py` | ✅ Done | 2026-03-17 | Full cost attribution engine with ClickHouse backend |
| PyPI packaging | ✅ Done | 2026-03-18 | `langsight==0.1.0` published to PyPI; dist/ wheel + sdist generated |

---

## Phase 2 — COMPLETE ✅ (100%)

### SDK Wrapper
| Item | Status | Date | Notes |
|------|--------|------|-------|
| `src/langsight/sdk/__init__.py` | ✅ Done | 2026-03-17 | `LangSightClient(url, api_key)` |
| `src/langsight/sdk/client.py` | ✅ Done | 2026-03-17 | async HTTP client, fire-and-forget span POST |
| `src/langsight/sdk/client.py` (`wrap()`) | ✅ Done | 2026-03-17 | `LangSightClient.wrap(mcp_client)` proxy — intercepts all `call_tool()` (no separate wrap.py) |
| `src/langsight/sdk/models.py` | ✅ Done | 2026-03-17 | `ToolCallSpan` with `parent_span_id`, `span_type`, `agent_name` |
| `api/routers/traces.py` | ✅ Done | 2026-03-17 | `POST /api/traces/spans` + `POST /api/traces/otlp` |
| Tests for SDK | ✅ Done | 2026-03-17 | |

### Agent Sessions and Multi-Agent Tracing
| Item | Status | Date | Notes |
|------|--------|------|-------|
| `parent_span_id` field on `ToolCallSpan` | ✅ Done | 2026-03-17 | Same model as OTEL distributed tracing |
| `span_type` field on `ToolCallSpan` | ✅ Done | 2026-03-17 | `tool_call` \| `agent` \| `handoff` |
| `agent_name` field on `ToolCallSpan` | ✅ Done | 2026-03-17 | For per-agent reliability metrics |
| Agent spans (lifecycle) | ✅ Done | 2026-03-17 | `ToolCallSpan.agent_span()` |
| Handoff spans | ✅ Done | 2026-03-17 | `ToolCallSpan.handoff_span()` |
| `api/routers/agents.py` | ✅ Done | 2026-03-17 | `GET /api/agents/sessions`, `GET /api/agents/sessions/{id}` |
| `cli/sessions.py` | ✅ Done | 2026-03-17 | `langsight sessions` and `langsight sessions --id <id>` with Rich tree |
| ClickHouse `mv_agent_sessions` | ✅ Done | 2026-03-17 | Materialized view — pre-aggregates session-level metrics |
| SDK session propagation via `wrap()` + `parent_span_id` | ✅ Done | 2026-03-17 | `session_id` and `trace_id` propagated via `ToolCallSpan` fields — no `agent_session()` context manager exists; propagation is explicit via span fields |
| Tests for session grouping + tree reconstruction | ✅ Done | 2026-03-17 | |

### Framework Integrations
| Item | Status | Date | Notes |
|------|--------|------|-------|
| `src/langsight/integrations/crewai.py` | ✅ Done | 2026-03-17 | `LangSightCrewAICallback` |
| `src/langsight/integrations/pydantic_ai.py` | ✅ Done | 2026-03-17 | Pydantic AI `Tool` decorator |
| `src/langsight/integrations/base.py` | ✅ Done | 2026-03-17 | Shared span-recording logic |
| `src/langsight/integrations/langchain.py` | ✅ Done | 2026-03-17 | `LangSightLangChainCallback` — covers LangChain, Langflow, LangGraph, LangServe |

### LibreChat Plugin
| Item | Status | Date | Notes |
|------|--------|------|-------|
| `integrations/librechat/langsight-plugin.js` | ✅ Done | 2026-03-17 | ~50 lines, `LANGSIGHT_URL` env var pattern |
| `integrations/librechat/README.md` | ✅ Done | 2026-03-17 | Installation instructions |

### Investigate Command
| Item | Status | Date | Notes |
|------|--------|------|-------|
| `src/langsight/cli/investigate.py` | ✅ Done | 2026-03-17 | `langsight investigate "description"` |
| Evidence collector | ✅ Done | 2026-03-17 | Queries health history, alerts, schema changes |
| Claude Agent SDK integration | ✅ Done | 2026-03-17 | Structured RCA output |
| Rule-based fallback | ✅ Done | 2026-03-17 | Deterministic heuristics when no API key |
| 4 LLM providers | ✅ Done | 2026-03-17 | Claude, OpenAI, Gemini, Ollama |

---

## Phase 3 — COMPLETE ✅ (95%)

| Item | Status | Date | Notes |
|------|--------|------|-------|
| `POST /api/traces/otlp` | ✅ Done | 2026-03-17 | Accepts OTLP/JSON spans (`request.json()` — not binary protobuf) |
| OTEL Collector config | ✅ Done | 2026-03-17 | Receives 4317/4318, exports to LangSight |
| ClickHouse backend | ✅ Done | 2026-03-17 | `StorageBackend` implementation |
| `mcp_tool_calls` ClickHouse table | ✅ Done | 2026-03-17 | `parent_span_id` + `span_type` columns, MergeTree, TTL 90 days |
| `mv_agent_sessions` materialized view | ✅ Done | 2026-03-17 | Pre-aggregates session-level metrics |
| Tool reliability engine | ✅ Done | 2026-03-17 | Success rate, p95 latency, error taxonomy from ClickHouse |
| `langsight costs` command | ✅ Done | 2026-03-17 | Cost attribution engine, configurable pricing rules |
| Cost attribution engine | ✅ Done | 2026-03-17 | Anomaly detection included |
| Root-level Docker Compose | ✅ Done | 2026-03-17 | ClickHouse + PostgreSQL + OTEL Collector + API |
| docs-site/ (28 Mintlify pages) | ✅ Done | 2026-03-17 | Full docs covering all features |
| `docs-site/cli/sessions.mdx` | ✅ Done | 2026-03-18 | Written and present at `docs-site/cli/sessions.mdx` |
| `costs/engine.py` — `AgentCostEntry` + `SessionCostEntry` dataclasses | ✅ Done | 2026-03-18 | Per-agent and per-session cost aggregation types |
| `costs/engine.py` — `aggregate_cost_rows()` helper | ✅ Done | 2026-03-18 | Shared aggregation logic used by all three cost endpoints |
| `storage/clickhouse.py` — `get_cost_call_counts()` | ✅ Done | 2026-03-18 | ClickHouse query for per-tool call counts, used by costs router |
| `api/routers/costs.py` | ✅ Done | 2026-03-18 | `GET /api/costs/breakdown`, `GET /api/costs/by-agent`, `GET /api/costs/by-session` |
| Costs router registered in `api/main.py` | ✅ Done | 2026-03-18 | `config_path` also stored in `app.state` for router access |

---

## Release 0.1.0 Checklist — SHIPPED ✅

| Task | ID | Status | Notes |
|------|----|--------|-------|
| `uv build` — generate `dist/` | R.1 | ✅ Done | `dist/langsight-0.1.0-py3-none-any.whl` + `langsight-0.1.0.tar.gz` |
| `uv publish` to PyPI | R.2 | ✅ Done | https://pypi.org/project/langsight/ |
| `git tag v0.1.0` + GitHub release | R.3 | ✅ Done | GitHub release `v0.1.0` exists |
| Mintlify deployment | R.4 | Pending (manual) | Manual step — connect `docs-site/` on mintlify.com dashboard |
| Write `docs-site/cli/sessions.mdx` | R.5 | ✅ Done | `docs-site/cli/sessions.mdx` exists |
| README PyPI version badge | R.6 | ✅ Done | Badge present in `README.md` |

---

## Phase 4 — 85% Complete (POST-0.1.0)

**Note**: Marketing website (`website/`) and product dashboard (`dashboard/`) shipped post-0.1.0. Both are built. Website awaits Vercel deployment. Dashboard auth now runs through NextAuth + the authenticated proxy path; current follow-up work is UX/documentation alignment rather than demo-auth removal.

### Marketing Website (langsight.dev)
| Item | Status | Date | Notes |
|------|--------|------|-------|
| Next.js + Tailwind project setup | ✅ Done | 2026-03-18 | `website/app/page.tsx` exists |
| Hero section | ✅ Done | 2026-03-18 | Tagline + GitHub CTA |
| Features overview section | ✅ Done | 2026-03-18 | Health, security, SDK, investigate |
| How it works section | ✅ Done | 2026-03-18 | 3-step: init → monitor → investigate |
| Integrations section | ✅ Done | 2026-03-18 | Claude Desktop, Cursor, LibreChat, CrewAI, Pydantic AI |
| Providers section | ✅ Done | 2026-03-18 | Claude, OpenAI, Gemini, Ollama |
| Pricing section | ✅ Done | 2026-03-18 | OSS free + SaaS tiers placeholder |
| Vercel deployment | Pending (manual) | — | Manual step — connect repo on vercel.com |

### Product Dashboard v2 (app.langsight.dev)
| Item | Status | Date | Notes |
|------|--------|------|-------|
| Next.js 15 dashboard project setup | ✅ Done | 2026-03-18 | shadcn/ui, App Router, `dashboard/` directory |
| Auth layer (demo mode) | ✅ Done | 2026-03-18 | Hardcoded users, any password accepted — **demo only, not production** (P0.2) |
| Overview page | ✅ Done | 2026-03-18 | Fleet health score, active alerts, top degraded tools (`dashboard/app/(dashboard)/page.tsx`) |
| Tool Health page | ✅ Done | 2026-03-18 | Renamed from "MCP Health" — server list, drill-down (`dashboard/app/(dashboard)/health/page.tsx`) |
| Sessions page | ✅ Done | 2026-03-18 | Agent session list (`dashboard/app/(dashboard)/sessions/page.tsx`) |
| Agents page | ✅ Done | 2026-03-18 | NEW — per-agent summary: sessions/calls/failures/cost/duration/servers (`dashboard/app/(dashboard)/agents/page.tsx`) |
| MCP Security page | ✅ Done | 2026-03-18 | Renamed from "Security Posture" — OWASP compliance, CVE list (`dashboard/app/(dashboard)/security/page.tsx`) |
| Cost Attribution page (upgraded) | ✅ Done | 2026-03-18 | Full breakdown tables by tool, agent, and session (`dashboard/app/(dashboard)/costs/page.tsx`) |
| Dashboard nav reordered | ✅ Done | 2026-03-18 | Agent-first hierarchy: Overview → Sessions → Agents → Costs → Tool Health → MCP Security (`dashboard/components/sidebar.tsx`) |
| Real auth (API keys or OIDC) | Not started | — | Required before production deployment — P0 gap (S.3) |

---

## Key Decisions Made

| Decision | Rationale | Date |
|----------|-----------|------|
| CLI-first (Phase 1) | Fastest path to value, no infra required | 2026-03-16 |
| SQLite for local mode | Zero-dependency local storage, no Docker needed for users | 2026-03-16 |
| MCP Python SDK for transport | Use official SDK instead of raw JSON-RPC | 2026-03-16 |
| asyncio.gather for concurrent checks | Health check N servers in parallel, not sequentially | 2026-03-16 |
| Module-level globals for MCP connections | Simpler than FastMCP context API, works reliably | 2026-03-16 |
| test-mcps built with skills | Used python-mcp-server-generator + mcp-builder + docker-expert | 2026-03-16 |
| FastAPI REST API in Phase 1 (ahead of plan) | Needed for `langsight serve`; adds no deps already in use | 2026-03-17 |
| PostgresBackend + open_storage() factory in Phase 1 | Required to make API testable without Docker | 2026-03-17 |
| **SDK-first before OTEL** | Engineers won't configure OTEL collectors before seeing value. Langfuse grew via `from langfuse.openai import OpenAI`. We need the same 2-line integration path. | 2026-03-17 |
| **LibreChat plugin, not OTEL** | LibreChat does not emit OTEL natively — it uses env vars for Langfuse. Following the same pattern (`LANGSIGHT_URL`) is lower friction and requires no LibreChat core changes. | 2026-03-17 |
| **Framework adapters alongside SDK** | CrewAI and Pydantic AI users should not need to find and wrap the MCP client manually — adapter objects are more idiomatic in those frameworks. | 2026-03-17 |
| **OTEL + ClickHouse moved to Phase 3** | Infrastructure tier comes after SDK proves adoption. Teams that already run OTEL can point at LangSight's collector in Phase 3 with zero code changes. | 2026-03-17 |
| **Ship 0.1.0 before dashboard** | CLI + SDK + API + docs cover 100% of the value proposition for OSS adopters. Dashboard adds frontend complexity and blocks release by 2-4 weeks. Ship what works; dashboard follows in Phase 4. | 2026-03-17 |

---

## Verified End-to-End (Phase 1)

```
$ langsight mcp-health   # Run 1 — baselines stored
  schema_tracker.baseline_stored  server=langsight-postgres  hash=bcf0ec26dff44929
  schema_tracker.baseline_stored  server=langsight-s3        hash=d2125e3aff0a9aca
  langsight-postgres  ✓ up   590ms   5 tools
  langsight-s3        ✓ up   660ms   7 tools
  2/2 servers healthy  →  saved to ~/.langsight/data.db

$ langsight mcp-health   # Run 2 — no drift
  schema_tracker.no_drift  server=langsight-postgres
  schema_tracker.no_drift  server=langsight-s3
  2/2 servers healthy
```
