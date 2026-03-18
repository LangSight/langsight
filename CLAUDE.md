# LangSight — Engineering Standards

## What We're Building

LangSight is an **open-source observability platform for AI agent actions** — full traces of every tool call across single and multi-agent workflows, with deep MCP health monitoring and security scanning built in. Instrument once at the agent level and capture everything the agent touched: MCP servers, HTTP APIs, Python functions, and sub-agents. MCP servers get extra depth (health checks, CVE scanning, schema drift detection, poisoning detection) because the protocol is standard and inspectable. CLI-first, web dashboard in Phase 3, SaaS eventually.

**This is production-grade OSS.** Every line of code will be read by engineers worldwide. Write accordingly.

---

## Project Structure

```
langsight/
├── CLAUDE.md                        # This file — engineering standards + agent guide
├── CHANGELOG.md                     # All changes — maintained by docs-keeper agent
│
├── docs/                            # Product + architecture docs (owned by docs-keeper)
│   ├── 01-product-spec.md           # What we build, personas, positioning
│   ├── 02-architecture-design.md    # System architecture, components, data flows
│   ├── 03-ui-and-features-spec.md   # CLI mockups, dashboard pages, config schema
│   ├── 04-implementation-plan.md    # Phase milestones, task breakdown
│   └── 05-risks-costs-testing.md    # Risks, SaaS costs, test scenarios
│
├── .claude/
│   ├── agents/                      # Specialized agents (see Agents section below)
│   │   ├── tester.md
│   │   ├── security-reviewer.md
│   │   ├── debugger.md
│   │   ├── release-engineer.md
│   │   ├── docs-keeper.md
│   │   └── git-keeper.md
│   └── skills/                      # 53 project-local skills (see Skills section)
│
├── test-mcps/                       # Real MCP servers for dogfooding + integration tests
│   ├── docker-compose.yml           # Starts postgres container
│   ├── postgres-mcp/                # PostgreSQL MCP (query, list_tables, describe_table)
│   │   ├── server.py
│   │   ├── seed.sql
│   │   ├── pyproject.toml
│   │   └── .env.example
│   └── s3-mcp/                      # AWS S3 MCP (list_buckets, read_object, put_object)
│       ├── server.py
│       ├── pyproject.toml
│       └── .env.example
│
└── src/                             # Main product source (being built)
    └── langsight/
        ├── cli/                     # Click CLI commands
        │   ├── main.py              # Entry point: langsight --help
        │   ├── mcp_health.py        # langsight mcp-health
        │   ├── security_scan.py     # langsight security-scan
        │   ├── monitor.py           # langsight monitor
        │   ├── costs.py             # langsight costs
        │   └── investigate.py       # langsight investigate (Phase 2)
        ├── health/                  # MCP health checker
        │   ├── checker.py           # Core health check logic
        │   ├── schema_tracker.py    # Tool schema versioning + drift detection
        │   └── transports.py        # stdio / SSE / StreamableHTTP support
        ├── security/                # Security scanner
        │   ├── scanner.py           # Orchestrates all security checks
        │   ├── cve_checker.py       # CVE database matching
        │   ├── owasp_checker.py     # OWASP MCP Top 10 checks
        │   ├── auth_auditor.py      # Auth configuration audit
        │   └── poisoning_detector.py # Tool description mutation detection
        ├── alerts/                  # Alerting engine
        │   ├── engine.py            # Alert rule evaluation + deduplication
        │   ├── slack.py             # Slack Block Kit webhook
        │   └── webhook.py           # Generic webhook
        ├── storage/                 # Data storage layer
        │   ├── clickhouse.py        # ClickHouse client + queries
        │   ├── postgres.py          # asyncpg direct (no SQLAlchemy)
        │   └── sqlite.py            # Local mode (CLI-only, no Docker)
        ├── api/                     # FastAPI REST API (Phase 2)
        │   ├── main.py
        │   ├── dependencies.py
        │   └── routers/
        ├── models.py                # Pydantic domain models (MCPServer, HealthCheckResult, etc.)
        ├── config.py                # Pydantic Settings — loads .langsight.yaml + env vars
        └── exceptions.py            # Custom exceptions

tests/
├── unit/                           # Fast, no external deps, mocked
├── integration/                    # Require docker compose up (@pytest.mark.integration)
└── e2e/                            # Full CLI flow tests
```

---

## Agents

5 specialized agents live in `.claude/agents/`. Use them proactively — don't wait to be asked.

### When to invoke each agent

| Agent | Invoke when | What it does |
|---|---|---|
| `tester` | After writing or modifying any code | Writes unit + integration tests, checks coverage, flags untested paths |
| `security-reviewer` | Before every commit, after any security-sensitive code | OWASP checks, secret exposure, MCP security, CVE scan, PII review |
| `debugger` | Something is broken or a test is failing unexpectedly | Systematic root cause analysis across CLI → API → Service → DB → MCP |
| `release-engineer` | Preparing a release | Version bump, CHANGELOG, Docker build, PyPI publish, GitHub release |
| `docs-keeper` | After every architectural decision, schema change, API change, new feature | Updates all 5 docs + CHANGELOG + **PROGRESS.md** to reflect changes |
| `git-keeper` | Before every commit and push, when creating PRs | Conventional commits, branch naming, secret checks, PR descriptions |

### Agent workflow per feature

```
1. Write code (with skills active)
       ↓
2. tester            → write tests, verify coverage
       ↓
3. security-reviewer → scan for vulnerabilities
       ↓
4. docs-keeper       → update docs to reflect changes
       ↓
5. git-keeper        → conventional commit, secret check, push
```

### On release

```
release-engineer → pre-release checklist → version bump → CHANGELOG → tag → Docker → PyPI
                          ↓
                    git-keeper → tag commit, push release branch, create GitHub release PR
```

### When something breaks

```
debugger → root cause → fix → tester (add regression test) → security-reviewer (if security-related)
```

---

## Tech Stack

| Layer | Technology | Notes |
|---|---|---|
| Language | Python 3.11+ | Type hints everywhere, no exceptions |
| CLI | Click + Rich | `langsight` command |
| MCP client | `mcp` Python SDK | For connecting to MCP servers |
| API | FastAPI | Async throughout |
| OLAP | ClickHouse | Time-series health data, traces |
| Metadata DB | PostgreSQL | App state, configs, alerts |
| Trace ingestion | OTEL Collector (contrib) | Standard OTLP input |
| RCA agent | Claude Agent SDK | Phase 2 |
| Dashboard | Next.js 15 + shadcn/ui | Phase 3 |
| Package manager | uv | Fast, modern, use exclusively |
| Formatter | Ruff | Format + lint in one |
| Type checker | mypy or pyright | Strict mode |
| Testing | pytest + pytest-asyncio | Coverage target: 80%+ |
| Containerization | Docker Compose | `docker compose up` for full stack |
| License | Apache 2.0 | |

---

## Python Standards

### Type Hints — Mandatory Everywhere

```python
# ✅ Correct
async def check_server_health(server: MCPServer, timeout: int = 5) -> HealthCheckResult:
    ...

# ❌ Wrong — no type hints
async def check_server_health(server, timeout=5):
    ...
```

- Use `from __future__ import annotations` at top of every file
- Prefer `X | None` over `Optional[X]`
- Use `TypedDict` for structured dicts, `dataclass` or Pydantic models for domain objects
- No `Any` unless absolutely unavoidable — comment why if used

### Pydantic Models for All Domain Objects

```python
# ✅ Use Pydantic for all data models
class MCPServer(BaseModel):
    name: str
    transport: Literal["stdio", "sse", "streamable_http"]
    url: str | None = None
    command: str | None = None
    tags: list[str] = []

class HealthCheckResult(BaseModel):
    server_name: str
    status: Literal["up", "degraded", "down", "stale"]
    latency_ms: float | None
    checked_at: datetime
    error: str | None = None
```

### Async First

- All I/O operations must be async: database calls, MCP connections, HTTP requests
- Use `asyncio.gather()` for concurrent operations (health checking N servers in parallel)
- Never block the event loop — no `time.sleep()`, no sync DB calls in async context
- Use `asyncpg` (not psycopg2) for async PostgreSQL in the main application

### Error Handling — Explicit, Never Silent

```python
# ✅ Explicit errors with context
async def ping_server(server: MCPServer) -> HealthCheckResult:
    try:
        result = await _do_ping(server)
        return result
    except asyncio.TimeoutError:
        logger.warning("health_check.timeout", server=server.name, timeout_ms=TIMEOUT_MS)
        return HealthCheckResult(server_name=server.name, status="down", error="timeout")
    except MCPConnectionError as e:
        logger.error("health_check.connection_error", server=server.name, error=str(e))
        return HealthCheckResult(server_name=server.name, status="down", error=str(e))

# ❌ Never swallow exceptions
try:
    result = await _do_ping(server)
except Exception:
    pass  # NEVER DO THIS
```

### Structured Logging — Always

```python
import structlog
logger = structlog.get_logger()

# ✅ Structured with context
logger.info("health_check.completed", server=server.name, status="up", latency_ms=142)
logger.error("security_scan.cve_found", server=server.name, cve="CVE-2025-6514", severity="critical")

# ❌ No f-string logs
logger.info(f"Checked {server.name}: up in 142ms")
```

### Configuration — Pydantic Settings

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    postgres_url: str
    clickhouse_url: str
    slack_webhook: str | None = None
    health_check_interval_seconds: int = 30
    security_scan_interval_seconds: int = 3600

    model_config = SettingsConfig(env_file=".env", env_prefix="LANGSIGHT_")
```

- All config via env vars or `.env` file — never hardcoded
- Use `LANGSIGHT_` prefix for all env vars
- Secrets (API keys, DB passwords) via env vars only, never in config files committed to git

---

## Code Quality Rules

### Functions — Small and Focused

- Max ~40 lines per function. If longer, split it.
- Single responsibility — one function does one thing
- Early returns over nested conditionals:

```python
# ✅ Early return
async def scan_server(server: MCPServer) -> ScanResult:
    if not server.is_reachable:
        return ScanResult(server=server.name, skipped=True, reason="unreachable")

    if server.transport == "stdio" and not server.command:
        return ScanResult(server=server.name, skipped=True, reason="no command configured")

    return await _do_scan(server)

# ❌ Deeply nested
async def scan_server(server: MCPServer) -> ScanResult:
    if server.is_reachable:
        if server.transport == "stdio":
            if server.command:
                return await _do_scan(server)
```

### Naming — Descriptive, No Abbreviations

```python
# ✅
health_check_interval_seconds = 30
mcp_server_config = load_config()
async def calculate_tool_success_rate(tool_name: str, window_hours: int) -> float: ...

# ❌
hci = 30
cfg = load_config()
async def calc_sr(t, w): ...
```

### No Magic Numbers

```python
# ✅
DEFAULT_HEALTH_CHECK_TIMEOUT_SECONDS = 5
MAX_CONSECUTIVE_FAILURES_BEFORE_DOWN = 3

# ❌
if failures > 3:
    status = "down"
```

### Imports — Ordered, No Wildcards

```python
# Standard library
from __future__ import annotations
import asyncio
from datetime import datetime
from typing import Literal

# Third-party
import structlog
from pydantic import BaseModel
from fastapi import FastAPI

# Internal
from langsight.models import MCPServer, HealthCheckResult
from langsight.config import Settings
```

---

## Security Standards

**This product monitors security — it must itself be secure.**

### Never Log Sensitive Data

```python
# ✅
logger.info("mcp_connection.authenticated", server=server.name, method="api_key")

# ❌ Never log credentials, tokens, API keys
logger.info("mcp_connection.auth", api_key=server.api_key)
```

### Input Validation — Always

- All user input validated via Pydantic before use
- SQL queries use parameterized queries — never f-strings in SQL
- CLI inputs sanitized before passing to subprocesses

### Secrets Management

- Never hardcode secrets — not even in tests
- Use `.env` locally, environment variables in production
- `.env` files always in `.gitignore`
- Test secrets use environment variables with a `TEST_` prefix

### Dependency Security

- Pin major versions in `pyproject.toml`
- Run `uv audit` before releases
- No unmaintained dependencies (check last commit date)

---

## Testing Standards

### What to Test

- Every public function/method has at least one test
- Happy path + at least one error path per function
- MCP health checker: test with mock MCP server (no real network in unit tests)
- Security scanner: test with known-vulnerable configs and known-safe configs
- Alert engine: test deduplication logic, threshold triggers

### Test Structure

```python
# tests/unit/test_health_checker.py
import pytest
from unittest.mock import AsyncMock, patch
from langsight.health.checker import HealthChecker
from langsight.models import MCPServer

class TestHealthChecker:
    @pytest.fixture
    def server(self) -> MCPServer:
        return MCPServer(name="test-server", transport="stdio", command="echo")

    @pytest.mark.asyncio
    async def test_healthy_server_returns_up_status(self, server: MCPServer):
        with patch("langsight.health.checker._ping_mcp_server") as mock_ping:
            mock_ping.return_value = AsyncMock(latency_ms=42.0)
            checker = HealthChecker()
            result = await checker.check(server)
            assert result.status == "up"
            assert result.latency_ms == 42.0

    @pytest.mark.asyncio
    async def test_timeout_returns_down_status(self, server: MCPServer):
        with patch("langsight.health.checker._ping_mcp_server") as mock_ping:
            mock_ping.side_effect = asyncio.TimeoutError()
            checker = HealthChecker()
            result = await checker.check(server)
            assert result.status == "down"
            assert "timeout" in result.error.lower()
```

### No Real External Calls in Unit Tests

- Mock MCP servers, databases, AWS, Slack
- Integration tests in a separate folder (`tests/integration/`) — these DO hit real services
- Integration tests need `docker compose up` and are marked `@pytest.mark.integration`

### Coverage

- Target: 80% overall, 90% for core modules (health checker, security scanner, alert engine)
- Run: `pytest --cov=langsight --cov-report=term-missing`

---

## Testing Workflow — Mandatory

**Tests are written alongside the module, not after.** This is non-negotiable.

### Rule: One module, one test file, same commit

Every time a source file is created or modified, its test file is created or updated in the same commit:

| Source file | Test file |
|---|---|
| `src/langsight/models.py` | `tests/unit/test_models.py` |
| `src/langsight/health/checker.py` | `tests/unit/health/test_checker.py` |
| `src/langsight/security/scanner.py` | `tests/unit/security/test_scanner.py` |
| `src/langsight/cli/mcp_health.py` | `tests/unit/cli/test_mcp_health.py` |

No module ships without a corresponding test file. No exceptions.

### Invoke the tester agent after every module

```
Write module → invoke tester agent → fix gaps → commit both together
```

The tester agent writes tests, checks coverage, and flags untested paths. Do not skip it.

### pytest markers — use them consistently

```python
@pytest.mark.unit          # Fast, no external deps, always runs
@pytest.mark.integration   # Requires docker compose up (postgres-mcp + s3-mcp)
@pytest.mark.e2e           # Full CLI flow, requires full stack
```

Run targets:
```bash
uv run pytest -m unit                          # Fast — no Docker needed
uv run pytest -m integration                   # Requires: cd test-mcps && docker compose up -d
uv run pytest -m "unit or integration"         # Full local suite
uv run pytest --cov=langsight --cov-report=term-missing  # With coverage
```

### Integration tests use test-mcps

The `test-mcps/postgres-mcp` and `test-mcps/s3-mcp` servers exist specifically for integration tests. Use them:

```python
# tests/integration/health/test_checker_integration.py
import pytest
from langsight.health.checker import HealthChecker
from langsight.models import MCPServer

@pytest.mark.integration
async def test_health_check_against_real_postgres_mcp():
    server = MCPServer(
        name="langsight-postgres",
        transport="stdio",
        command="uv run python test-mcps/postgres-mcp/server.py",
    )
    checker = HealthChecker()
    result = await checker.check(server)
    assert result.status == "up"
    assert result.latency_ms is not None
```

### conftest.py fixtures — project-wide

```
tests/
├── conftest.py              # Shared fixtures: mock MCP server, sample configs
├── unit/
│   └── conftest.py          # Unit-level fixtures: in-memory SQLite, mock pools
└── integration/
    └── conftest.py          # Integration fixtures: real DB connection, real MCP server path
```

### What blocks a commit

- Any new public function without at least one test → blocked
- Coverage drops below 80% overall → blocked
- Coverage drops below 90% on health/, security/, alerts/ → blocked
- Any test that makes real network calls without `@pytest.mark.integration` → blocked

---

## CLI Standards (Click + Rich)

### Output Quality Matters — This Is the Primary UX

```python
from rich.console import Console
from rich.table import Table

console = Console()

# ✅ Use Rich for all terminal output
def display_health_results(results: list[HealthCheckResult]) -> None:
    table = Table(title="MCP Server Health")
    table.add_column("Server", style="bold")
    table.add_column("Status")
    table.add_column("p99 Latency")
    for result in results:
        status_style = "green" if result.status == "up" else "red"
        table.add_row(result.server_name, f"[{status_style}]{result.status}[/]", ...)
    console.print(table)
```

- All commands support `--json` flag for machine-readable output
- `--ci` flag on `security-scan` exits with code 1 on CRITICAL findings
- Progress indicators for long-running operations (Rich `Progress`)
- Error messages go to stderr, data goes to stdout

---

## FastAPI Standards

### Async Everywhere

```python
@router.get("/api/health/servers", response_model=list[ServerHealthSummary])
async def list_server_health(
    status: HealthStatus | None = None,
    limit: int = Query(default=50, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[ServerHealthSummary]:
    return await health_service.list_servers(db, status=status, limit=limit)
```

- All route handlers are `async`
- Dependency injection for DB sessions, services
- `response_model` on every endpoint
- Proper HTTP status codes (201 for creates, 204 for deletes, 422 for validation errors)
- No business logic in route handlers — delegate to service layer

### API Structure

```
src/langsight/api/
├── routers/
│   ├── health.py       # /api/health/...
│   ├── security.py     # /api/security/...
│   ├── tools.py        # /api/tools/...
│   ├── costs.py        # /api/costs/...
│   └── alerts.py       # /api/alerts/...
├── dependencies.py     # Shared FastAPI deps (auth, db)
└── main.py             # App factory
```

---

## Database Standards

### PostgreSQL (via asyncpg direct — no SQLAlchemy)

- All schema changes via Alembic migrations — never `CREATE TABLE` in application code
- Use `TIMESTAMPTZ` (not `TIMESTAMP`) for all timestamps — timezone aware always
- Index foreign keys and columns used in WHERE clauses
- Soft deletes where data has audit value (`deleted_at TIMESTAMPTZ`)

### ClickHouse

- Materialized views for all aggregations — never aggregate in application code at query time
- Use `ReplacingMergeTree` for upsert patterns
- TTL policies on all tables (health checks: 90 days, OTEL traces: 30 days)
- Never run `ALTER TABLE` in application startup — use migrations

---

## Git & Commit Standards

### Conventional Commits

```
feat(health): add schema drift detection for MCP tools
fix(security): handle timeout in CVE database fetch
chore(deps): upgrade fastmcp to 3.2.0
docs(cli): add usage examples for security-scan command
test(health): add tests for DOWN state transition
refactor(checker): extract ping logic into separate module
```

Format: `type(scope): description`
Types: `feat`, `fix`, `chore`, `docs`, `test`, `refactor`, `perf`

### Branch Naming

```
feature/mcp-health-checker
fix/schema-drift-false-positive
refactor/alert-deduplication
```

### PR Standards

- Every PR has tests for new code
- No PR merges with failing tests or type errors
- Keep PRs focused — one feature/fix per PR

---

## What NOT to Do

- **No premature abstraction** — don't create a base class for one implementation
- **No over-engineering** — YAGNI. Build what's needed now, not what might be needed
- **No commented-out code** — delete it, git history preserves it
- **No print() statements** — use structured logging
- **No TODO comments without a GitHub issue** — either fix it now or file an issue
- **No `except Exception: pass`** — ever
- **No hardcoded credentials** — ever, including in tests
- **No sync I/O in async functions** — blocks the event loop
- **No direct SQL string concatenation** — always parameterized queries
- **No `SELECT *`** — always name columns explicitly

---

## Performance Mindset

- Health checks for N servers run **concurrently** via `asyncio.gather()` — not sequentially
- ClickHouse queries must use partition pruning (filter on timestamp columns directly)
- Cache MCP server schema snapshots — don't re-fetch on every health check
- Batch database writes where possible (OTEL trace ingestion)
- Measure before optimizing — use `time.perf_counter()` for profiling hot paths

---

## Running the Project

```bash
# Start infrastructure
docker compose up -d

# Install dependencies
uv sync

# Run tests
uv run pytest

# Run type checker
uv run mypy src/

# Run linter/formatter
uv run ruff check src/ && uv run ruff format src/

# Run CLI
uv run langsight --help
```

---

## When Unsure

1. **Check the docs first** — `langsight/docs/` has product spec, architecture, and feature specs
2. **Ask** — don't assume. Ambiguity in requirements is better resolved upfront
3. **Simpler is better** — if two approaches work, pick the simpler one
4. **Production first** — every feature should work reliably at scale from day one, not "we'll fix it later"

---

## Skills — When to Invoke

53 project-local skills are installed. Use them proactively — don't wait to be asked.

### Invoke automatically when:

| Trigger | Skills to invoke |
|---|---|
| Starting any new feature | `/test-driven-development` — write tests first, always |
| Writing any Python code | `/python-type-safety` + `/python-error-handling` |
| Writing async Python | `/async-python-patterns` |
| Writing FastAPI endpoints | `/fastapi-templates` + `/api-design` |
| Writing any MCP client code | `/python-mcp-server-generator` + `/mcp-builder` |
| Writing database queries | `/postgresql-optimization` + `/sql-optimization` |
| Designing a schema | `/postgresql-table-design` + `/database-schema-design` |
| Writing security-related code | `/VibeSec-Skill` + `/owasp-security` + `/secrets-management` |
| Setting up observability | `/monitoring-observability` + `/distributed-tracing` + `/python-observability` |
| Writing tests | `/python-testing-patterns` + `/pytest-coverage` |
| Writing E2E tests | `/playwright-best-practices` + `/playwright-generate-test` |
| Something is broken | `/systematic-debugging` + `/debugging` |
| Reviewing code before commit | `/code-review-excellence` + `/verification-before-completion` |
| Refactoring a module | `/refactor` |
| Writing or updating README | `/create-readme` |
| Building Next.js pages (Phase 3) | `/next-best-practices` + `/nextjs-app-router-patterns` |
| Building UI components (Phase 3) | `/vercel-react-best-practices` + `/tailwind-design-system` |
| Writing Dockerfiles | `/multi-stage-dockerfile` + `/docker-expert` |
| Writing deployment config | `/deployment-automation` |

### Full skill inventory by category:

**Python core**: `modern-python`, `async-python-patterns`, `python-type-safety`, `python-error-handling`, `python-design-patterns`, `python-performance-optimization`, `python-observability`, `uv-package-manager`

**Testing**: `test-driven-development`, `python-testing-patterns`, `pytest-coverage`, `analyze-test-run`, `webapp-testing`, `playwright-best-practices`, `playwright-generate-test`, `playwright-explore-website`, `playwright-automation-fill-in-form`, `debugging`, `debugging-strategies`, `systematic-debugging`

**Security**: `VibeSec-Skill`, `owasp-security`, `security-best-practices`, `secrets-management`, `semgrep`, `gdpr-data-handling`, `pci-compliance`, `sast-configuration`

**FastAPI / API**: `fastapi-templates`, `api-design`, `api-design-principles`, `auth-implementation-patterns`, `authentication-setup`, `error-handling-patterns`

**Database**: `postgresql-optimization`, `postgresql-code-review`, `postgresql-table-design`, `database-schema-design`, `database-migration`, `sql-optimization`

**Observability**: `monitoring-observability`, `distributed-tracing`, `prometheus-configuration`, `grafana-dashboards`, `log-analysis`, `slo-implementation`, `llm-monitoring-dashboard`, `service-mesh-observability`

**MCP / Agent**: `python-mcp-server-generator`, `mcp-builder`, `mcp-cli`

**Next.js / Frontend (Phase 3)**: `next-best-practices`, `next-cache-components`, `nextjs-app-router-patterns`, `vercel-react-best-practices`, `tailwind-design-system`, `frontend-design`, `responsive-design`, `web-accessibility`, `ui-component-patterns`

**Architecture / Quality**: `architecture-patterns`, `architecture-decision-records`, `code-review-excellence`, `refactor`, `microservices-patterns`

**DevOps**: `multi-stage-dockerfile`, `docker-expert`, `deployment-automation`, `deployment-pipeline-design`, `github-actions-templates`

**Planning**: `writing-plans`, `executing-plans`, `verification-before-completion`, `brainstorming`

**Documentation**: `create-readme`
