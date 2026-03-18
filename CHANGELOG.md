# Changelog

All meaningful changes to LangSight are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versions follow [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

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
