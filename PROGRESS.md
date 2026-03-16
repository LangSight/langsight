# LangSight — Build Progress

> Last updated: 2026-03-16
> Maintained by: docs-keeper agent — update after every feature, architectural decision, or milestone

---

## Current Status: Phase 1 — In Progress

```
Phase 1 (CLI MVP)      ████████░░░░░░░░  40%
Phase 2 (API + RCA)    ░░░░░░░░░░░░░░░░   0%
Phase 3 (Dashboard)    ░░░░░░░░░░░░░░░░   0%
```

---

## What's Been Built

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

### Phase 1 — Foundation (`src/langsight/`)
| Item | Status | Date | Notes |
|------|--------|------|-------|
| `pyproject.toml` | ✅ Done | 2026-03-16 | src layout, uv, ruff, mypy strict, entry point |
| `exceptions.py` | ✅ Done | 2026-03-16 | LangSightError hierarchy |
| `models.py` | ✅ Done | 2026-03-16 | MCPServer, HealthCheckResult, ToolInfo, enums |
| `config.py` | ✅ Done | 2026-03-16 | .langsight.yaml loader, AlertConfig, StorageConfig, Settings |
| `health/transports.py` | ✅ Done | 2026-03-16 | stdio + SSE via MCP SDK, hash_tools() |
| `health/checker.py` | ✅ Done | 2026-03-16 | concurrent check_many(), storage-aware, drift detection |
| `health/schema_tracker.py` | ✅ Done | 2026-03-16 | Drift detection — baseline + compare across runs |
| `storage/base.py` | ✅ Done | 2026-03-16 | StorageBackend Protocol — SaaS-safe abstraction |
| `storage/sqlite.py` | ✅ Done | 2026-03-16 | SQLite backend, async, DDL on first open, persists across runs |
| `cli/main.py` | ✅ Done | 2026-03-16 | Click entry point |
| `cli/mcp_health.py` | ✅ Done | 2026-03-16 | Rich table, --json, exit 1 on DOWN/DEGRADED, SQLite wired |

### Tests
| Item | Status | Coverage | Notes |
|------|--------|----------|-------|
| `test_exceptions.py` | ✅ Done | 100% | |
| `test_models.py` | ✅ Done | 100% | |
| `test_config.py` | ✅ Done | 98% | |
| `health/test_checker.py` | ✅ Done | 85% | mocked ping + storage |
| `health/test_schema_tracker.py` | ✅ Done | 100% | mocked storage |
| `storage/test_sqlite.py` | ✅ Done | 100% | real in-memory SQLite |
| `cli/test_mcp_health.py` | ✅ Done | — | Click CliRunner, mocked storage |
| `integration/health/test_checker_integration.py` | ✅ Done | — | requires docker compose up |
| **Overall coverage** | | **84%** | target: 80% ✅ |

### Verified End-to-End
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

---

## Phase 1 — Remaining

| Item | Priority | Notes |
|------|----------|-------|
| `health/schema_tracker.py` | ✅ Done | |
| `storage/sqlite.py` | ✅ Done | |
| `cli/security_scan.py` | High | `langsight security-scan` command |
| `security/scanner.py` | High | Orchestrate CVE + OWASP checks |
| `security/owasp_checker.py` | High | OWASP MCP Top 10 automated checks |
| `security/cve_checker.py` | Medium | CVE database matching |
| `cli/monitor.py` | Medium | `langsight monitor` — continuous background monitoring |
| `alerts/engine.py` | Medium | Alert rule evaluation + deduplication |
| `alerts/slack.py` | Medium | Slack Block Kit webhook |
| `cli/costs.py` | Low | `langsight costs` — tool call cost attribution |
| `cli/init.py` | Low | `langsight init` — interactive setup wizard |

---

## Phase 2 — Not Started

| Item | Notes |
|------|-------|
| FastAPI REST API | `/api/health`, `/api/security`, `/api/tools`, `/api/costs` |
| `langsight investigate` | AI-assisted root cause attribution (Claude Agent SDK) |
| ClickHouse + PostgreSQL backend | For production deployments |
| OTEL Collector integration | Trace ingestion from agent frameworks |

---

## Phase 3 — Not Started

| Item | Notes |
|------|-------|
| Next.js 15 dashboard | shadcn/ui, real-time health overview |
| Security posture timeline | |
| Cost attribution charts | |
| Alert management UI | |

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

---

## Metrics

| Metric | Value |
|--------|-------|
| Test count | 57 unit tests |
| Coverage | 81% |
| Source files | 10 |
| Test files | 6 |
| Lines of source code | ~450 |
| CLI commands live | 1 (`mcp-health`) |
| CLI commands planned | 6 (`init`, `mcp-health`, `security-scan`, `monitor`, `costs`, `investigate`) |
