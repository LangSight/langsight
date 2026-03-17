# LangSight — Build Progress

> Last updated: 2026-03-17
> Maintained by: docs-keeper agent — update after every feature, architectural decision, or milestone

---

## Current Status: Phase 2 — In Progress

```
Phase 1 (CLI MVP)               ████████████████  95% — COMPLETE
Phase 2 (SDK + Framework Integ) ████████░░░░░░░░  50% — IN PROGRESS
Phase 3 (OTEL + Costs)          ░░░░░░░░░░░░░░░░   0% — BACKLOG
Phase 4 (Dashboard)             ░░░░░░░░░░░░░░░░   0% — BACKLOG
```

---

## Metrics

| Metric | Value |
|--------|-------|
| Test count | 262 tests |
| Coverage | 88% |
| CLI commands live | 5 (`init`, `mcp-health`, `security-scan`, `monitor`, `serve`) |
| API endpoints | 6 (`/api/health/*`, `/api/security/scan`, `/api/status`) |
| Storage backends | 2 (SQLite, PostgreSQL) |
| Source files | ~25 |
| Lines of source code | ~1,800 |

---

## Phase 1 — COMPLETE (95%)

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

### Phase 1 — Remaining
| Item | Priority | Notes |
|------|----------|-------|
| `cli/costs.py` stub | Low | Placeholder command; full implementation Phase 3 |
| PyPI packaging | Low | `pip install langsight` via TestPyPI |

---

## Phase 2 — In Progress (50%)

### SDK Wrapper
| Item | Status | Notes |
|------|--------|-------|
| `src/langsight/sdk/__init__.py` | Not started | `LangSightClient(url, api_key)` |
| `src/langsight/sdk/client.py` | Not started | async HTTP client, fire-and-forget span POST |
| `src/langsight/sdk/wrap.py` | Not started | `wrap(mcp_client, client)` proxy |
| `src/langsight/sdk/models.py` | Not started | `ToolCallSpan` Pydantic model |
| `api/routers/traces.py` | Not started | `POST /api/traces/spans` ingestion endpoint |
| Tests for SDK | Not started | |

### Framework Integrations
| Item | Status | Notes |
|------|--------|-------|
| `src/langsight/integrations/crewai.py` | Not started | `LangSightCrewAICallback` |
| `src/langsight/integrations/pydantic_ai.py` | Not started | Pydantic AI `Tool` wrapper |
| `src/langsight/integrations/openai_agents.py` | Not started | OpenAI Agents SDK hook |
| `src/langsight/integrations/base.py` | Not started | shared span-recording logic |

### LibreChat Plugin
| Item | Status | Notes |
|------|--------|-------|
| `integrations/librechat/langsight-plugin.js` | Not started | ~50 lines, LANGSIGHT_URL env var |
| `integrations/librechat/README.md` | Not started | Installation instructions |

### Investigate Command
| Item | Status | Notes |
|------|--------|-------|
| `src/langsight/cli/investigate.py` | Not started | `langsight investigate "description"` |
| Evidence collector | Not started | query health history, alerts, schema changes |
| Claude Agent SDK integration | Not started | structured RCA output |
| Rule-based fallback | Not started | deterministic heuristics when no API key |

---

## Phase 3 — Backlog

| Item | Notes |
|------|-------|
| `POST /api/traces/otlp` | Accept standard OTLP protobuf spans |
| OTEL Collector config | Receive 4317/4318, export to LangSight |
| ClickHouse backend | `StorageBackend` implementation |
| `mcp_tool_calls` ClickHouse table | MergeTree, partitioned by day, TTL 90 days |
| Materialized views | `tool_reliability_hourly`, `tool_error_taxonomy` |
| Tool reliability engine | success rate, p95 latency, error taxonomy from ClickHouse |
| `langsight costs` command | Full implementation with ClickHouse backend |
| Cost attribution engine | configurable pricing rules, anomaly detection |
| Root-level Docker Compose | PostgreSQL + ClickHouse + OTEL Collector + API + worker |

---

## Phase 4 — Backlog

### Marketing Website (langsight.io)
| Item | Status | Notes |
|------|--------|-------|
| Next.js + Tailwind project setup | Not started | `website/` directory |
| Hero section | Not started | Tagline + GitHub CTA |
| Features overview section | Not started | Health, security, SDK, investigate |
| How it works section | Not started | 3-step: init → monitor → investigate |
| Integrations section | Not started | Claude Desktop, Cursor, LibreChat, CrewAI, Pydantic AI |
| Providers section | Not started | Claude, OpenAI, Gemini, Ollama |
| Pricing section | Not started | OSS free + SaaS tiers placeholder |
| Vercel deployment | Not started | |

### Documentation Site (docs.langsight.io)
| Item | Status | Notes |
|------|--------|-------|
| Mintlify project setup (`docs-site/mint.json`) | Not started | |
| Quickstart guide | Not started | < 5 min to first health check |
| CLI reference (6 commands) | Not started | One .mdx per command |
| Provider setup guide | Not started | Port from `docs/06-provider-setup.md` |
| SDK integration guide | Not started | |
| Framework integrations guide | Not started | CrewAI, Pydantic AI, LibreChat |
| API reference | Not started | Auto-generated from FastAPI OpenAPI spec |
| Configuration reference | Not started | `.langsight.yaml` full schema |
| Self-hosting guide | Not started | Docker Compose walkthrough |

### Product Dashboard (app.langsight.io)
| Item | Status | Notes |
|------|--------|-------|
| Next.js 15 dashboard project setup | Not started | shadcn/ui, App Router, `dashboard/` directory |
| Overview page | Not started | Fleet health score, active alerts, top degraded tools |
| MCP Health page | Not started | Server list, drill-down |
| Security Posture page | Not started | OWASP compliance, CVE list |
| Tool Reliability page | Not started | Ranked tool list, latency trends — requires Phase 3 OTEL data |
| Cost Attribution page | Not started | Cost breakdown, anomaly highlights — requires Phase 3 cost engine |
| Alert Management page | Not started | View, acknowledge, configure alerts |

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
