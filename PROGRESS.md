# LangSight — Build Progress

> Last updated: 2026-03-18
> Maintained by: docs-keeper agent — update after every feature, architectural decision, or milestone

**Project framing**: LangSight is complete observability for everything an AI agent calls — MCP servers, HTTP APIs, Python functions, and sub-agents. Agent-level instrumentation captures all tool types in one trace. MCP servers additionally receive proactive health checks, security scanning, schema drift detection, and alerting because the MCP protocol is standard and inspectable. Non-MCP tools (HTTP APIs, functions) are passively observed in traces only.

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

LangSight v0.1.0 is a **promising self-hosted observability and security toolkit for MCP and agent workflows**. It is suitable for:
- Local development and experimentation
- Internal pilots within trusted networks
- Contributor adoption and OSS evaluation

It is **not yet suitable** for internet-facing or multi-tenant deployment without the P0/P1 gaps above resolved.

---

## Current Status: Release 0.1.0 — Shipped ✅

```
Phase 1 (CLI MVP)               ████████████████ 100% — COMPLETE ✅
Phase 2 (SDK + Framework Integ) ████████████████ 100% — COMPLETE ✅
Phase 3 (OTEL + Costs)          ████████████████  95% — COMPLETE ✅
Release 0.1.0                   ████████████████ 100% — SHIPPED ✅ (PyPI + GitHub)
Phase 4 (Dashboard + Website)   █████████████░░░  85% — website built, Vercel deploy pending
Security Hardening (S.1-S.10)   ░░░░░░░░░░░░░░░░   0% — NOT STARTED
```

---

## Metrics

| Metric | Value |
|--------|-------|
| Test count | 378 tests |
| Coverage | 83.69% |
| CLI commands live | 8 (`init`, `mcp-health`, `security-scan`, `monitor`, `investigate`, `costs`, `sessions`, `serve`) |
| API endpoints | 9 (`/api/agents/sessions`, `/api/agents/sessions/{id}`, `/api/health/*`, `/api/security/scan`, `/api/traces/spans`, `/api/traces/otlp`, `/api/status`) |
| Storage backends | 3 (SQLite, PostgreSQL, ClickHouse) |
| Framework integrations | 5 (LangChain/Langflow/LangGraph/LangServe, CrewAI, Pydantic AI, LibreChat, OTEL) |
| LLM providers for investigate | 4 (Claude, OpenAI, Gemini, Ollama) |
| Mintlify docs pages | 28 (including `sessions.mdx`) |
| PyPI release | `langsight==0.1.0` published |
| GitHub release | `v0.1.0` tagged |
| dist/ artifacts | `langsight-0.1.0-py3-none-any.whl` + `langsight-0.1.0.tar.gz` |
| Marketing website | Built (`website/app/page.tsx`) — Vercel deploy pending |
| Product dashboard | Built (`dashboard/`) — demo auth only (P0.2 gap) |
| Source files | ~50 |
| Lines of source code | ~4,000 |

---

## Phase 1 — COMPLETE ✅ (100%)

### Infrastructure & Tooling
| Item | Status | Date | Notes |
|------|--------|------|-------|
| GitHub repo | ✅ Done | 2026-03-16 | github.com/sumankalyan123/langsight |
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
| `storage/sqlite.py` | ✅ Done | 2026-03-16 | SQLite backend, async, DDL on first open, persists across runs |
| `storage/postgres.py` | ✅ Done | 2026-03-17 | PostgreSQL backend, SQLAlchemy async |
| `storage/__init__.py` | ✅ Done | 2026-03-17 | `open_storage()` factory — selects SQLite or PostgreSQL |
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
| `api/routers/status.py` | ✅ Done | 2026-03-17 | `/api/status` endpoint |

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
| **Overall coverage** | | **88%** | target: 80% ✅ |

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
| `src/langsight/sdk/wrap.py` | ✅ Done | 2026-03-17 | `wrap(mcp_client, client)` proxy — intercepts all `call_tool()` |
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
| SDK `agent_session()` context manager | ✅ Done | 2026-03-17 | Auto-propagates `session_id` + `trace_id` to nested `wrap()` calls |
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
| `POST /api/traces/otlp` | ✅ Done | 2026-03-17 | Accepts standard OTLP protobuf spans |
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

**Note**: Marketing website (`website/`) and product dashboard (`dashboard/`) shipped post-0.1.0. Both are built. Website awaits Vercel deployment. Dashboard is live with demo auth only (P0.2 gap).

### Marketing Website (langsight.io)
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

### Product Dashboard v2 (app.langsight.io)
| Item | Status | Date | Notes |
|------|--------|------|-------|
| Next.js 15 dashboard project setup | ✅ Done | 2026-03-18 | shadcn/ui, App Router, `dashboard/` directory |
| Auth layer (demo mode) | ✅ Done | 2026-03-18 | Hardcoded users, any password accepted — **demo only, not production** (P0.2) |
| Overview page | ✅ Done | 2026-03-18 | Fleet health score, active alerts, top degraded tools (`dashboard/app/(dashboard)/page.tsx`) |
| MCP Health page | ✅ Done | 2026-03-18 | Server list, drill-down (`dashboard/app/(dashboard)/health/page.tsx`) |
| Sessions page | ✅ Done | 2026-03-18 | Agent session list (`dashboard/app/(dashboard)/sessions/page.tsx`) |
| Security Posture page | ✅ Done | 2026-03-18 | OWASP compliance, CVE list (`dashboard/app/(dashboard)/security/page.tsx`) |
| Cost Attribution page | ✅ Done | 2026-03-18 | Cost breakdown, anomaly highlights (`dashboard/app/(dashboard)/costs/page.tsx`) |
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
