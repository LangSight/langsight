# Changelog

All meaningful changes to LangSight are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versions follow [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### Added
- `LangSightClient` Python SDK wrapper — 2-line MCP client instrumentation
- `wrap(mcp_client, client)` proxy — intercepts all `call_tool()` calls, records `ToolCallSpan`
- `LangSightCrewAICallback` framework adapter for CrewAI agents
- Pydantic AI integration adapter — wraps `Tool` objects at registration
- OpenAI Agents SDK integration adapter — hooks into function call events
- LibreChat native plugin (`integrations/librechat/langsight-plugin.js`) — LANGSIGHT_URL env var pattern, ~50 lines
- `POST /api/traces/spans` ingestion endpoint — accepts `ToolCallSpan` batches from SDK and plugins
- `langsight investigate` command — Claude Agent SDK RCA with rule-based fallback

### Architecture Decisions
- **SDK-first before OTEL** (2026-03-17): Engineers integrate via `LangSightClient` + `wrap()` before configuring OTEL infrastructure. OTEL remains in Phase 3 for enterprise teams that already run collectors.
- **LibreChat plugin, not OTEL** (2026-03-17): LibreChat uses env vars for Langfuse integration natively; LangSight follows the same pattern rather than requiring OTEL.
- **Framework adapters alongside SDK** (2026-03-17): CrewAI/Pydantic AI users get idiomatic integration objects instead of having to find and wrap the MCP client manually.

---

## [0.1.0-alpha] — 2026-03-17

Phase 1 complete (95%). First public-facing code state.

### Added
- CLI: `langsight init` — auto-discovers Claude Desktop, Cursor, VS Code MCP configs
- CLI: `langsight mcp-health` — Rich table, --json flag, exit 1 on DOWN/DEGRADED
- CLI: `langsight security-scan` — Rich table, --json, --ci flag (exit 1 on CRITICAL)
- CLI: `langsight monitor` — continuous monitoring daemon, `--once` and `--interval` flags
- CLI: `langsight serve` — starts FastAPI REST API server
- Health checker: concurrent `check_many()` via `asyncio.gather()`, schema drift detection
- Schema tracker: baseline + compare across runs, hash-based drift detection
- Security scanner: CVE (OSV API), OWASP MCP checks (5 rules), tool poisoning detection, auth audit
- Tool poisoning detector: injection phrases, exfiltration patterns, URLs, hidden unicode, base64
- Alerts engine: state-transition alerts (DOWN/recovery/schema drift/latency spike), deduplication
- Slack alerts: Block Kit format, fail-open
- Webhook alerts: generic JSON, fail-open
- Storage: `SQLiteBackend` — async, DDL on first open, zero-dependency local mode
- Storage: `PostgresBackend` — SQLAlchemy async, for server mode
- Storage: `open_storage()` factory — selects backend from config
- FastAPI REST API: `/api/health/*`, `/api/security/scan`, `/api/status`
- Test MCP servers: `postgres-mcp` (5 tools), `s3-mcp` (7 tools)
- GitHub Actions CI: lint (ruff + mypy), unit/regression (pytest, 88% coverage), integration
- 262 tests passing, 88% coverage

### Architecture Decisions
- **CLI-first, SQLite local mode** (2026-03-16): Zero infrastructure required for first run. SQLite is the default backend; no Docker needed for `langsight mcp-health` or `langsight security-scan`.
- **MCP Python SDK for transport** (2026-03-16): Official SDK instead of raw JSON-RPC — handles protocol edge cases, supported by Anthropic.
- **asyncio.gather for health checks** (2026-03-16): N servers checked concurrently, not sequentially. Essential for usability at any meaningful fleet size.
- **Module-level globals for MCP connections** (2026-03-16): Simpler than FastMCP context API for our use case; works reliably across test and prod.
- **FastAPI REST API in Phase 1 (ahead of original plan)** (2026-03-17): Needed for `langsight serve`; all deps (FastAPI, httpx) were already in use. No additional cost.
- **PostgresBackend + open_storage() factory in Phase 1** (2026-03-17): Required to make the API testable without Docker. Factory pattern keeps storage backend selection out of application code.

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
