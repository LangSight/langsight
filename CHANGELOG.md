# Changelog

All meaningful changes to LangSight are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versions follow [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### Added (2026-03-19 — S.9 Threat Model)
- S.9: `docs/06-threat-model.md` — comprehensive threat model covering 5 trust boundaries, full attack surface table for all API endpoints and the OTEL Collector, data classification table with PII risk guidance, 10 threat scenarios (T-01 through T-10) each with attack path / impact / mitigations / residual risk, recommended production deployment topology with firewall rules, 8 documented known gaps (G-01 through G-08) with severity and mitigation notes, and a vulnerability disclosure policy with response time commitments
- S.9: `docs/04-implementation-plan.md` updated — S.9 marked complete (2026-03-19); Security Hardening progress updated to 10%

### Added (2026-03-19 — P5.7 Playground Replay)
- P5.7: Playground Replay — re-execute any session's tool calls against live MCP servers using stored `input_args`; replay stored as new session and auto-compared with original in the compare drawer
- P5.7: `POST /api/agents/sessions/{id}/replay` endpoint — configurable `timeout_per_call` (default 10s) and `total_timeout` (default 60s) parameters; returns `ReplayResponse` with `replay_session_id`
- P5.7: `replay_of: str | None` field on `ToolCallSpan` and `replay_of String DEFAULT ''` column on `mcp_tool_calls` ClickHouse table — links each replay span to its original span_id
- P5.7: `ReplayEngine` in `src/langsight/replay/engine.py` — filters to `tool_call` spans with `input_json` present, re-executes each via stored `input_args`, supports stdio (StdioServerParameters) and SSE/StreamableHTTP transports, fail-open per span (errors recorded as ERROR status spans, replay continues)
- P5.7: Replay button in trace drawer header — one click to replay and auto-open compare drawer diff between original and replay session; shows spinner and "Replaying..." while in flight; inline error message on failure

### Added (2026-03-19 — P5.6 Side-by-side session comparison)
- P5.6: Side-by-side session comparison — select two sessions (A/B) in the Workflows page and click Compare to see a diff table aligned by tool call order; diverged spans (status change or >=20% latency delta) highlighted in yellow
- P5.6: `GET /api/agents/sessions/compare?a=&b=` endpoint — returns aligned diff with `matched`/`diverged`/`only_a`/`only_b` entries and summary counts (`SessionComparison` response model)
- P5.6: `compare_sessions(session_a, session_b)` method on `ClickHouseBackend` — fetches both traces concurrently via `asyncio.gather`, aligns spans by `(server_name, tool_name)` call order, computes per-entry status
- P5.6: `_diff_spans()` helper — produces diff entries; `diverged` = status changed OR latency delta >= 20%; `only_a`/`only_b` for unmatched spans
- P5.6: `DiffEntry` and `SessionComparison` TypeScript interfaces added to `dashboard/lib/types.ts`
- P5.6: `compareSessions(a, b)` function added to `dashboard/lib/api.ts` — calls `GET /api/agents/sessions/compare`
- P5.6: `CompareDrawer` and `DiffRow` components in sessions page — colour-coded diff table (matched=green, diverged=yellow, only_a/only_b=blue/purple); latency delta column; first session row click selects A (blue), second click selects B (purple), Compare button appears when both are selected

### Added (2026-03-19 — P5.5 Agent SLO Tracking)
- P5.5: Agent SLO Tracking — define `success_rate` and `latency_p99` SLOs per agent; CRUD API at `/api/slos`; `SLOEvaluator` queries session data to compute current vs target; status is `ok`, `breached`, or `no_data`
- P5.5: `agent_slos` table added to SQLite and PostgreSQL backends; all four CRUD methods (`create_slo`, `list_slos`, `get_slo`, `delete_slo`) implemented on `StorageBackend` protocol and both backends
- P5.5: `SLOMetric` StrEnum (`success_rate`, `latency_p99`), `AgentSLO` Pydantic model, and `SLOEvaluation` Pydantic model added to `src/langsight/models.py`
- P5.5: `SLOEvaluator` class in `src/langsight/reliability/engine.py` — `success_rate` computed as `(clean_sessions / total_sessions) * 100`; `latency_p99` uses `max(duration_ms)` as a conservative proxy (true p99 requires raw span data)
- P5.5: `GET /api/slos/status` — evaluate all SLOs against current session data; `GET /api/slos` — list SLO definitions; `POST /api/slos` — create SLO; `DELETE /api/slos/{slo_id}` — delete SLO
- P5.5: Dashboard Overview "Agent SLOs" panel — shows per-SLO current value vs target with coloured status dot (`ok`=green, `breached`=red, `no_data`=grey); polls `/api/slos/status` every 60s via SWR; panel only renders when at least one SLO is defined
- P5.5: `SLOStatus` TypeScript interface added to `dashboard/lib/types.ts`; `getSLOStatus()`, `listSLOs()`, `deleteSLO()` functions added to `dashboard/lib/api.ts`

### Added (2026-03-19 — P5.4 Statistical anomaly detection)
- P5.4: Statistical anomaly detection — `AnomalyDetector` in `src/langsight/reliability/engine.py` computes z-score per tool against a 7-day ClickHouse baseline; fires `warning` anomaly when |z| >= 2 and `critical` when |z| >= 3 for both `error_rate` and `avg_latency_ms` metrics
- P5.4: `get_baseline_stats(baseline_hours=168)` method on `ClickHouseBackend` — queries `mv_tool_reliability` using `stddevPop()` and `avg()`; requires >= 3 sample hours to return a row, avoiding noisy baselines
- P5.4: `AnomalyResult` dataclass — `server_name`, `tool_name`, `metric`, `current_value`, `baseline_mean`, `baseline_stddev`, `z_score`, `severity`, `sample_hours`
- P5.4: Minimum stddev guards — `_MIN_STDDEV_ERROR_RATE = 0.01` (1%) and `_MIN_STDDEV_LATENCY_MS = 10.0` ms prevent false positives on perfectly stable tools
- P5.4: `GET /api/reliability/anomalies?current_hours=1&baseline_hours=168&z_threshold=2.0` endpoint — configurable detection window and sensitivity
- P5.4: `GET /api/reliability/tools?hours=24&server_name=...` endpoint — per-tool reliability metrics
- P5.4: `dashboard/lib/types.ts` — new `AnomalyResult` TypeScript interface
- P5.4: `dashboard/lib/api.ts` — new `getAnomalies(currentHours, zThreshold)` function calling `GET /api/reliability/anomalies`
- P5.4: Dashboard Overview "Anomalies Detected" metric card — live anomaly count with critical/warning breakdown, colour-coded severity, polls every 60s via SWR (replaces static "Tool Alerts" card)

### Added (2026-03-19 — P5.3 LLM reasoning capture)
- P5.3: LLM reasoning capture — OTLP spans carrying `gen_ai.prompt`/`gen_ai.completion` (or `llm.prompts`/`llm.completions`) attributes are now extracted and stored as `span_type="agent"` spans with `llm_input`/`llm_output` fields; model name extracted from `gen_ai.request.model`/`llm.model_name` and written to `tool_name`
- P5.3: `llm_input: str | None` and `llm_output: str | None` added to `ToolCallSpan` in `src/langsight/sdk/models.py`; `ToolCallSpan.record()` accepts and passes through both fields
- P5.3: ClickHouse `mcp_tool_calls` DDL extended with `llm_input Nullable(String)` and `llm_output Nullable(String)`; `_SPAN_COLUMNS`, `_span_row()`, and `get_session_trace()` updated
- P5.3: `SpanNode` API response model (`api/routers/agents.py`) includes `llm_input` and `llm_output` fields
- P5.3: `SpanNode` TypeScript interface (`dashboard/lib/types.ts`) updated with `llm_input: string | null` and `llm_output: string | null`
- P5.3: Sessions page (`dashboard/app/(dashboard)/sessions/page.tsx`) detects LLM spans (`span_type="agent"` with `llm_input`/`llm_output`) and shows "Prompt" / "Completion" labels in the detail panel instead of generic "Input" / "Output"
- P5.3: OTLP attribute parser (`api/routers/traces.py`) now handles `intValue`, `doubleValue`, and `boolValue` in addition to `stringValue`

### Added (2026-03-19 — P5.2 session replay payload visibility)
- P5.2: Session replay payload visibility — clicking any span row in the trace tree now expands an inline panel showing formatted input arguments and output result; error details shown for failed spans with no output (requires P5.1 payload capture)
- P5.2: `SpanNode` API response model (`api/routers/agents.py`) now includes `input_json: str | None` and `output_json: str | None` fields, passed through from `get_session_trace()`
- P5.2: `SpanNode` TypeScript interface (`dashboard/lib/types.ts`) updated with `input_json: string | null` and `output_json: string | null`

### Added (2026-03-18 — P5.1 payload capture)
- P5.1: Input/output payload capture — `ToolCallSpan` now records tool call arguments (`input_args: dict | None`) and return values (`output_result: str | None`); stored in ClickHouse `mcp_tool_calls` as `input_json Nullable(String)` / `output_json Nullable(String)`
- P5.1: `redact_payloads: bool = False` config flag on `LangSightConfig` and `LangSightClient` constructor — set `true` to suppress payload capture for PII-sensitive tools; redaction is applied before transmission (payloads never leave the host process when enabled)
- P5.1: Per-wrap `redact_payloads` override on `LangSightClient.wrap()` — allows different redaction behaviour per MCP client instance without changing the global config
- P5.1: `get_session_trace()` now returns `input_json` and `output_json` in every span row

### Added (2026-03-18 — costs API + agents dashboard)
- `GET /api/costs/breakdown` — per-tool cost breakdown endpoint
- `GET /api/costs/by-agent` — per-agent cost aggregation endpoint
- `GET /api/costs/by-session` — per-session cost aggregation endpoint
- `AgentCostEntry` and `SessionCostEntry` dataclasses in `costs/engine.py` — typed aggregation records for agent-level and session-level cost rollups
- `aggregate_cost_rows()` helper in `costs/engine.py` — shared aggregation logic used across all three cost endpoints
- `get_cost_call_counts()` method on ClickHouse backend (`storage/clickhouse.py`) — per-tool call count query
- Agents dashboard page (`dashboard/app/(dashboard)/agents/page.tsx`) — per-agent summary table showing sessions, calls, failures, total cost, duration, and unique MCP servers per agent
- Costs page upgraded to full breakdown view (`dashboard/app/(dashboard)/costs/page.tsx`) — three breakdown tables: by tool, by agent, by session
- `config_path` stored in `app.state` in `api/main.py` — routers can now access the config path without a global
- `tests/unit/test_cost_engine.py` (86 lines) and `tests/unit/api/test_costs_router.py` (134 lines) — unit coverage for new cost layer
- `tests/integration/storage/test_costs_integration.py` — integration test for `get_cost_call_counts()` against real ClickHouse

### Changed (2026-03-18 — dashboard nav and page renames)
- Dashboard sidebar nav reordered to agent-first hierarchy: Overview → Sessions → Agents → Costs → Tool Health → MCP Security (`dashboard/components/sidebar.tsx`)
- "MCP Health" dashboard page renamed to "Tool Health" (`dashboard/app/(dashboard)/health/page.tsx`) — scoping is honest: the page monitors tool-level health, not only MCP
- "Security Posture" dashboard page renamed to "MCP Security" (`dashboard/app/(dashboard)/security/page.tsx`) — scoping is honest: deep security scanning is MCP-specific

### Changed (2026-03-18 — agent-first repositioning)
- Product positioning updated from "MCP observability and security platform" to "observability platform for AI agent actions — full traces of every tool call across single and multi-agent workflows, with deep MCP health monitoring and security scanning built in." MCP remains a deep feature, not the lead identity.
- `README.md`: tagline updated to lead with agent action tracing; "Why LangSight" table reordered — agent session traces and multi-agent handoffs now first and second, cost attribution moved up to third, MCP health and security remain as fourth/fifth; NOTE callout rewritten to contrast with Langfuse/LangSmith ("what your agent thought" vs "what your agent did")
- `docs/01-product-spec.md`: One-Liner updated to agent-first framing; Elevator Pitch now opens with the primary on-call question before listing tool types; Problem Statement now leads with the agent visibility gap as the primary problem rather than MCP infrastructure
- `docs-site/introduction.mdx`: frontmatter description updated; "What is LangSight?" section now opens with the Langfuse/LangSmith contrast and the primary on-call question before explaining tool type breakdown; CardGroup card copy updated — MCP cards now explicitly scoped as "for MCP servers specifically"
- `website/app/page.tsx`: hero subheadline rewritten to lead with agent action tracing and multi-agent workflows; MCP depth framed as an additional capability, not the primary hook
- `CLAUDE.md`: "What We're Building" section updated to agent-first description



### Fixed (2026-03-18 — documentation correctness)
- `README.md`: sessions example output now matches actual CLI columns (`Session`, `Agent`, `Calls`, `Failed`, `Duration`, `Servers`) — removed non-existent `Cost` column
- `README.md`: features section and CLI reference table no longer claim `langsight sessions` shows per-session cost; cost field is absent from the current implementation
- `README.md`: architecture diagram and Phase 2 roadmap no longer list OpenAI Agents SDK integration — that file (`src/langsight/integrations/openai_agents.py`) does not exist; shipped integrations are CrewAI, Pydantic AI, LangChain/Langflow/LangGraph/LangServe, and LibreChat
- `CHANGELOG.md`: removed two references to `agent_session()` context manager — no such symbol exists in `src/`; session propagation is via explicit `session_id`/`trace_id` fields on `ToolCallSpan`
- `CHANGELOG.md`: removed OpenAI Agents SDK integration adapter entry (file never shipped)
- `PROGRESS.md`: corrected `agent_session()` context manager row to accurately describe what exists (`session_id` propagated via span fields, no context manager)
- `docs/04-implementation-plan.md`: Section 2.2 framework integration task FW.3 now references `langchain.py` (shipped) instead of `openai_agents.py` (not shipped); acceptance criteria updated accordingly
- `docs/04-implementation-plan.md`: Section 1 annotated with historical note explaining that `agentguard` CLI names and `pip install agentguard` are from the original pre-rename plan; current entry point is `langsight`

Pre-production security hardening required before 0.2.0 can be positioned as production-grade.

### Planned (Phase 5: Deep Observability — next major phase after Security Hardening)
- Phase 5 gap analysis completed (2026-03-18): code review identified 7 missing features required for full session debugging capability
- ~~P5.1: Input/output payload capture~~ — **shipped (2026-03-18)**, see Added section above
- ~~P5.2: Session replay trace tree UI~~ — **shipped (2026-03-19)**, see Added section above
- ~~P5.3: LLM reasoning capture~~ — **shipped (2026-03-19)**, see Added section above
- ~~P5.4: Statistical anomaly detection~~ — **shipped (2026-03-19)**, see Added section above
- ~~P5.5: Agent SLO tracking~~ — **shipped (2026-03-19)**, see Added section above
- ~~P5.6: Side-by-side session comparison~~ — **shipped (2026-03-19)**, see Added section above
- ~~P5.7: Playground replay~~ — **shipped (2026-03-19)**, see Added section above

### Planned (Security Hardening S.1-S.10 — required before 0.2.0 production positioning)
- S.1: API key middleware for all API endpoints (currently unauthenticated — P0)
- S.2: RBAC — admin and viewer roles at router dependency level
- S.3: Dashboard real credential store or OIDC integration (currently demo-only — P0)
- S.4: Rate limiting on `POST /api/traces/spans` and `POST /api/traces/otlp`
- S.5: Audit logging for security-sensitive actions (scans triggered, auth failures, config changes)
- S.6: No default secrets in `docker-compose.yml` — require explicit env var injection
- S.7: ClickHouse and Postgres ports removed from host binding in compose (internal network only)
- S.8: Alembic migrations for Postgres; versioned SQL scripts for ClickHouse
- S.9: `docs/06-threat-model.md` — trust boundaries, attack surface, vulnerability disclosure policy
- S.10: Split `GET /api/status` into `/readiness` and `/liveness` for correct Kubernetes probe behavior

### Planned (Phase 4 remaining — manual deployment steps)
- R.4: Mintlify deployment — connect `docs-site/` on mintlify.com dashboard to `docs.langsight.io`
- Phase 4 website Vercel deployment — connect `website/` repo on vercel.com

---

## [0.1.0] — 2026-03-18

Phase 1, Phase 2, Phase 3, and Phase 4 (website + dashboard) complete. First public release: PyPI published, GitHub release tagged.

### Added

#### Phase 4: Website + Dashboard (2026-03-18)
- Marketing website built with Next.js 15 + Tailwind CSS at `website/` — all sections: hero, features, how-it-works, integrations, providers, pricing
- Product dashboard v2 built with Next.js 15 + shadcn/ui at `dashboard/` — Overview, Health, Sessions, Security, Costs pages
- `LangSightLangChainCallback` — LangChain framework integration covering LangChain agents, Langflow, LangGraph, and LangServe (`src/langsight/integrations/langchain.py`)
- PyPI release: `langsight==0.1.0` published at https://pypi.org/project/langsight/
- GitHub release `v0.1.0` tagged with full CHANGELOG notes
- `dist/langsight-0.1.0-py3-none-any.whl` and `dist/langsight-0.1.0.tar.gz` generated
- `docs-site/cli/sessions.mdx` — previously the only missing Mintlify page, now written
- README PyPI version badge added

#### Security Assessment (2026-03-18)
- Security review completed — findings documented in `PROGRESS.md` and `docs/04-implementation-plan.md`
- P0.1: `api/main.py` — wildcard CORS, no auth on routers — any client reaching port 8000 can trigger scans and read all data
- P0.2: `dashboard/lib/auth.ts` — hardcoded users, any password accepted, static secret fallback — explicitly demo-mode only
- P1.1: `docker-compose.yml` — ClickHouse default user, default Postgres password, databases exposed to host
- P1.2: Cost engine `total` is a placeholder; per-session cost field absent from `langsight sessions` CLI output

#### CLI (8 commands)
- `langsight init` — auto-discovers Claude Desktop, Cursor, VS Code MCP configs
- `langsight mcp-health` — Rich table, `--json` flag, exit 1 on DOWN/DEGRADED
- `langsight security-scan` — Rich table, `--json`, `--ci` flag (exit 1 on CRITICAL)
- `langsight monitor` — continuous monitoring daemon, `--once` and `--interval` flags
- `langsight investigate` — Claude Agent SDK RCA with rule-based fallback; supports Claude, OpenAI, Gemini, Ollama
- `langsight costs` — cost attribution report with ClickHouse backend
- `langsight sessions` — Rich table of recent agent sessions with cost + failure counts
- `langsight sessions --id <id>` — full multi-agent trace tree for one session
- `langsight serve` — starts FastAPI REST API server

#### REST API (9 endpoints)
- `GET /api/agents/sessions` — list agent sessions with aggregated cost, call count, failure count
- `GET /api/agents/sessions/{session_id}` — full span tree reconstructed via `parent_span_id`
- `GET /api/health/servers` — list MCP servers with health status
- `GET /api/health/servers/{name}` — single server health detail
- `POST /api/security/scan` — trigger security scan
- `POST /api/traces/spans` — ingest `ToolCallSpan` batches from SDK and plugins
- `POST /api/traces/otlp` — ingest standard OTLP protobuf spans
- `GET /api/status` — API health and component status

#### Multi-Agent Tracing
- `parent_span_id` field on `ToolCallSpan` — enables multi-agent call tree reconstruction (same model as OpenTelemetry)
- `span_type` field on `ToolCallSpan` — `tool_call` | `agent` | `handoff`
- `agent_name` field on `ToolCallSpan` — per-agent reliability metrics
- `ToolCallSpan.agent_span()` — lifecycle spans for agent start/end events
- `ToolCallSpan.handoff_span()` — explicit spans recording agent-to-agent delegation

#### SDK
- `LangSightClient` Python SDK — 2-line MCP client instrumentation
- `wrap(mcp_client, client)` proxy — intercepts all `call_tool()` calls, records `ToolCallSpan`

#### Framework Integrations
- `LangSightCrewAICallback` — CrewAI framework adapter
- Pydantic AI integration adapter — wraps `Tool` objects at registration
- LibreChat native plugin (`integrations/librechat/langsight-plugin.js`) — `LANGSIGHT_URL` env var pattern

#### Storage Backends
- SQLite backend (default) — zero-dependency local mode, async, DDL on first open
- PostgreSQL backend — SQLAlchemy async
- ClickHouse backend — `mcp_tool_calls` table with `parent_span_id` + `span_type`, TTL 90 days, `mv_agent_sessions` materialized view

#### Infrastructure
- Docker Compose (root) — ClickHouse + PostgreSQL + OTEL Collector + API
- GitHub Actions CI — lint (ruff + mypy), unit/regression (pytest, 85% coverage gate), integration jobs

#### Docs
- `docs-site/` — 28 Mintlify pages covering all features (quickstart, CLI reference, SDK, integrations, API, self-hosting)

### Changed
- Product framing updated to "complete observability for everything an AI agent calls" — MCP servers, HTTP APIs, Python functions, and sub-agents (2026-03-17)
- One-liner updated: "LangSight is complete observability for everything an AI agent calls — MCP servers, HTTP APIs, functions, and sub-agents — with built-in health monitoring and security scanning for MCP servers."
- Capability matrix added to docs, README, and introduction page — makes explicit which features apply to all tool types vs MCP-only
- Agent session example updated in quickstart and product spec to show mixed tool types (MCP + HTTP API + function + sub-agent) in one trace tree
- Key framing documented: agent-level observability is a superset of MCP observability; `server_name` in `ToolCallSpan` is not locked to MCP servers
- `docs/01-product-spec.md`: one-liner, elevator pitch, product vision all updated with complete framing
- `docs-site/introduction.mdx`: description, hero section, capability table, and mixed session example added
- `docs-site/quickstart.mdx`: session drill-down example updated to show mixed tool types
- `README.md`: tagline, opening paragraph, and capability table added
- `PROGRESS.md`: project description at top updated to reflect final framing

### Architecture Decisions
- **All tool types observed, MCP gets proactive depth** (2026-03-17): The SDK and OTLP ingestion paths capture every call an agent makes regardless of type. The distinction is proactive vs passive: MCP servers can be pinged, listed, schema-checked, and CVE-scanned between agent sessions. Stripe, Sendgrid, and Python functions cannot — no standard protocol exists to do that. This is not a limitation; it is the accurate model of what observability can provide per tool type.

### Added
- `LangSightClient` Python SDK wrapper — 2-line MCP client instrumentation
- `wrap(mcp_client, client)` proxy — intercepts all `call_tool()` calls, records `ToolCallSpan`
- `LangSightCrewAICallback` framework adapter for CrewAI agents
- Pydantic AI integration adapter — wraps `Tool` objects at registration
- LibreChat native plugin (`integrations/librechat/langsight-plugin.js`) — LANGSIGHT_URL env var pattern, ~50 lines
- `POST /api/traces/spans` ingestion endpoint — accepts `ToolCallSpan` batches from SDK and plugins
- `langsight investigate` command — Claude Agent SDK RCA with rule-based fallback
- `parent_span_id` field on `ToolCallSpan` — enables multi-agent call tree reconstruction; same model as OpenTelemetry distributed tracing
- `span_type` field on `ToolCallSpan` — `tool_call` | `agent` | `handoff`
- `agent_name` field on `ToolCallSpan` — for per-agent reliability metrics
- Agent spans — lifecycle spans for agent start/end events
- Handoff spans — explicit spans recording agent-to-agent delegation with parent and child agent names
- `GET /api/agents/sessions` endpoint — list agent sessions with aggregated cost, call count, failure count
- `GET /api/agents/sessions/{session_id}` endpoint — full span tree for one session, reconstructed via `parent_span_id`
- `langsight sessions` CLI command — Rich table of recent sessions with cost and failures
- `langsight sessions --id <id>` — full multi-agent trace view for one session
- `mv_agent_sessions` ClickHouse materialized view (Phase 3) — pre-aggregates session-level metrics

### Changed
- Product positioning: primary value proposition is now agent session tracing and multi-agent tree visibility; MCP health monitoring and security scanning are secondary (but still unique vs competitors)
- Product one-liner updated: "LangSight is the observability layer for AI agent tool calls — traces, costs, and reliability across single and multi-agent workflows, with built-in MCP health monitoring and security scanning."
- README tagline updated to lead with agent observability
- Quickstart updated: Step 3 is now "Trace your agent sessions"; health check moved to Step 4
- `docs/01-product-spec.md`: elevator pitch, feature list, competitor table, "What We Don't Build" all updated
- `docs/04-implementation-plan.md`: Phase 2 section 2.6 added for agent sessions/multi-agent tracing; ClickHouse schema updated with `parent_span_id`, `session_id`, `agent_name`, `span_type`

### Architecture Decisions
- **Agent-observability-first pivot** (2026-03-17): Primary user question is "what did my agent call, in what order, how long did each tool take, which ones failed, what did it cost?" MCP health is a differentiating secondary feature. Repositioning does not change the roadmap — it changes the narrative and the CLI UX entry point.
- **`parent_span_id` for multi-agent trees** (2026-03-17): Using the OpenTelemetry span parent-child model rather than a proprietary tree structure. No separate tree storage needed — reconstruction is a recursive query on flat span tables. This is the same model Jaeger and Tempo use for distributed traces.
- **SDK-first before OTEL** (2026-03-17): Engineers integrate via `LangSightClient` + `wrap()` before configuring OTEL infrastructure. OTEL remains in Phase 3 for enterprise teams that already run collectors.
- **LibreChat plugin, not OTEL** (2026-03-17): LibreChat uses env vars for Langfuse integration natively; LangSight follows the same pattern rather than requiring OTEL.
- **Framework adapters alongside SDK** (2026-03-17): CrewAI/Pydantic AI users get idiomatic integration objects instead of having to find and wrap the MCP client manually.
- **LangSight is complementary to Langfuse, not competing** (2026-03-17): Langfuse traces LLM calls (prompts, completions). LangSight traces tool calls (MCP spans). They answer different questions and are used together. This distinction is now explicit in product docs and README.

---

## [0.0.1] — 2026-03-16

Project scaffold.

### Added
- Repository structure: `src/langsight/`, `tests/`, `test-mcps/`, `docs/`, `.claude/agents/`
- `pyproject.toml`: src layout, uv, ruff, mypy strict, `langsight` entry point
- `CLAUDE.md`: engineering standards, agent workflow, testing mandate
- Product docs: 5 docs covering spec, architecture, UI/features, impl plan, risk assessment
- `.gitignore`: covers `.env`, `.venv`, `.claude/skills/`, secrets
- `skills-lock.json`: 52 active project skills
- 6 specialised agents: tester, security-reviewer, debugger, release-engineer, docs-keeper, git-keeper
