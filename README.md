# LangSight

**Action-layer traces for AI agents. MCP health + security built in.**

Trace every tool call your agents make — MCP servers, HTTP APIs, Python functions, sub-agents. For MCP servers specifically, get proactive health checks, schema drift detection, and security scanning.

[![PyPI](https://img.shields.io/pypi/v/langsight)](https://pypi.org/project/langsight/)
[![License: BSL 1.1](https://img.shields.io/badge/License-BSL%201.1-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/downloads/)
[![CI](https://github.com/sumankalyan123/langsight/actions/workflows/ci.yml/badge.svg)](https://github.com/sumankalyan123/langsight/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/docs-mintlify-green)](https://lngsight.mintlify.app)

Agents call three types of things: MCP servers (postgres-mcp, jira-mcp, slack-mcp), non-MCP tools (Stripe API, Sendgrid, Python functions), and sub-agents. **LangSight observes all three.** Instrument once at the agent level and you automatically capture everything the agent touched — MCP or not. MCP servers get extra depth: proactive health checks, security scanning, schema drift detection, and alerting. Non-MCP tools are observed passively — every call appears in the trace, but there is no standard protocol to ping them proactively.

---

## Why LangSight

| Problem | Without LangSight | With LangSight |
|---------|-------------------|----------------|
| What did my agent call? | No trace of which tools ran, in what order | `langsight sessions --id` shows the full call tree |
| Multi-agent handoffs | No visibility across agent boundaries | Full tree via `parent_span_id` — same model as OTEL |
| Tool call costs | Invisible, discovered on the invoice | Per-session cost attribution in real time |
| Which of 15 tools failed? | 3 days of manual log replay | `investigate` narrows it to a specific tool and time window |
| Tool returning stale data | Agent hallucinates; you find out from users | Schema drift alert fires in <5 minutes |
| CVE in a community MCP server | Unknown until exploited | Automated CVE scan via OSV database |

> [!NOTE]
> **LangSight complements Langfuse and LangSmith — it does not replace them.** Langfuse traces your LLM calls (prompts, completions, token costs, evals). LangSight traces what your agents actually *did* (tool calls, latencies, errors, handoffs). For MCP servers specifically, LangSight adds proactive health checks, CVE scanning, schema drift detection, and poisoning detection. Use both together for full-stack agent observability.

---

## What LangSight can do per tool type

| Tool type | Observe calls | Health check | Security scan | Cost tracking |
|-----------|:------------:|:------------:|:-------------:|:-------------:|
| MCP servers | Yes | Yes | Yes | Yes |
| HTTP APIs (Stripe, Sendgrid, etc.) | Yes | No | No | Yes |
| Python functions | Yes | No | No | Yes |
| Sub-agents | Yes | No | No | Yes |

MCP servers receive proactive health checks and security scanning because the MCP protocol is standard and inspectable. Non-MCP tools appear in every session trace but cannot be pinged or scanned — no standard protocol exists to do so.

---

## Features

**Agent Session Tracing** *(Primary)*
- Full ordered trace for every agent session — every tool call, every handoff, every failure
- `langsight sessions` — list sessions with call counts, failure counts, duration, and servers used
- `langsight sessions --id` — drill into a single session to see the complete call tree
- Agent reliability metrics — success rate per agent, not just per tool

**Multi-Agent Tree Tracing** *(Primary)*
- When Agent A delegates to Agent B which calls Agent C, trace the full tree
- `parent_span_id` on every span — same model as OpenTelemetry distributed tracing
- Handoff spans — explicit records of agent-to-agent delegation events
- Tree reconstruction from flat span storage via recursive parent-child query

**MCP Health Monitoring** *(Secondary, unique vs competitors)*
- Continuous availability checks (connect, initialize, tools list)
- Server state tracking: `UP → DEGRADED → DOWN`
- Schema drift detection — alerts when a tool's output format changes
- Latency tracking per server and per tool

**Security Scanning** *(Secondary, unique vs competitors)*
- CVE detection via OSV (Open Source Vulnerabilities) database
- 5 of 10 OWASP MCP Top 10 checks (MCP-01, 02, 04, 05, 06 — more coming)
- Tool poisoning detection — baseline hash comparison on every scan
- Auth configuration audit (unauthenticated server detection, token exposure)

**Alerting**
- Slack webhook alerts with configurable thresholds
- Generic webhook for PagerDuty, Opsgenie, and custom systems
- Alert deduplication — no alert storms during outages

**Failure Investigation** *(Phase 2)*
- `langsight investigate` — summarizes health history, schema drift, and recent errors for a server
- AI-assisted analysis via Claude when `ANTHROPIC_API_KEY` is set; rule-based fallback otherwise

---

## Architecture

```
  Agent Frameworks                    ┌──────────────────────────────────┐
  (CrewAI, Pydantic AI,               │         LangSight Platform        │
   LangChain, Langflow, LangGraph,
   LibreChat, etc.)                   │                                  │
         │ OTLP                       │  ┌─────────────┐ ┌────────────┐  │
         ▼                            │  │ MCP Health  │ │  Security  │  │
  ┌─────────────┐                     │  │  Checker    │ │  Scanner   │  │
  │    OTEL     │────────────────────►│  └──────┬──────┘ └─────┬──────┘  │
  │  Collector  │                     │         │               │         │
  └─────────────┘                     │         ▼               ▼         │
                                      │  ┌───────────────────────────┐   │
  MCP Servers                         │  │       ClickHouse           │   │
  ┌──────────┐                        │  │  health · traces · costs   │   │
  │ server-1 │◄──────────────────────►│  └───────────────────────────┘   │
  │ server-2 │                        │  ┌───────────────────────────┐   │
  │ server-N │                        │  │       PostgreSQL           │   │
  └──────────┘                        │  │  configs · alerts · users  │   │
                                      │  └───────────────────────────┘   │
                                      │                                  │
                                      │  ┌────────────┐ ┌─────────────┐ │
                                      │  │  FastAPI   │ │  CLI        │ │
                                      │  │  REST API  │ │  langsight  │ │
                                      │  │  (Phase 2) │ │  (Phase 1)  │ │
                                      │  └─────┬──────┘ └─────────────┘ │
                                      │        ▼                         │
                                      │  ┌───────────┐  ┌─────────────┐ │
                                      │  │ Dashboard │  │ Slack /     │ │
                                      │  │ (Phase 3) │  │ Webhook     │ │
                                      │  └───────────┘  └─────────────┘ │
                                      └──────────────────────────────────┘
```

**Storage strategy** (dual-backend architecture):
- **PostgreSQL** — metadata: users, projects, API keys, model pricing, SLOs, alert config, audit logs
- **ClickHouse** — analytics: spans, traces, health results, reliability, costs, sessions

Default mode is `dual` — both backends run together. `postgres` and `clickhouse` single-backend modes are available for constrained deployments. SQLite has been removed; `docker compose up -d` is required to run LangSight.

---

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Python 3.11+ and [uv](https://docs.astral.sh/uv/) (for CLI and SDK)

### 1. Clone and start

```bash
git clone https://github.com/sumankalyan123/langsight.git
cd langsight
./scripts/quickstart.sh
```

The quickstart script generates all secrets, writes `.env`, and runs `docker compose up`. Takes ~2 minutes on first run.

### 2. Open the dashboard

Go to **http://localhost:3003** and log in with `admin@admin.com` / `admin`.

A **Sample Project** with 25 demo agent sessions is pre-loaded so you can explore the sessions, traces, and cost views immediately. Create your own project in Settings when you're ready to trace real agents.

Useful dashboard paths once you log in:
- **Sessions** — click any row to open the dedicated session debugger at `/sessions/<id>`
- **Agents** — inspect per-agent summaries and the shared topology view
- **Settings** — create API keys, manage projects, and configure notifications

### 3. Trace your own agents

```bash
uv sync  # install the SDK
```

```python
from langsight.sdk import LangSightClient

client = LangSightClient(url="http://localhost:8000", api_key="<from quickstart output>")
traced = client.wrap(mcp_session, server_name="postgres-mcp", agent_name="my-agent")
result = await traced.call_tool("query", {"sql": "SELECT * FROM orders"})
```

### Manual setup (if you prefer)

If you'd rather configure manually instead of using the quickstart script:

```bash
cp .env.example .env
# Edit .env — set POSTGRES_PASSWORD, CLICKHOUSE_PASSWORD, LANGSIGHT_API_KEYS, AUTH_SECRET,
#             LANGSIGHT_ADMIN_EMAIL, LANGSIGHT_ADMIN_PASSWORD
docker compose up -d
```

### Auto-discover MCP servers

```bash
uv sync
langsight init
```

LangSight auto-discovers MCP servers from Claude Desktop (`~/.config/claude/claude_desktop_config.json`), Cursor (`~/.cursor/mcp.json`), and VS Code (`~/.vscode/mcp.json`). It writes a `.langsight.yaml` config file you can customize.

### Trace your agent sessions

Add two lines to your agent code:

```python
from langsight.sdk import LangSightClient

client = LangSightClient(url="http://localhost:8000")
traced = client.wrap(mcp_session, server_name="postgres-mcp", agent_name="support-agent")
result = await traced.call_tool("query", {"sql": "SELECT * FROM orders"})
```

View sessions from the CLI:

```bash
langsight sessions
```

```
Agent Sessions  (last 24h — 2 sessions)
──────────────────────────────────────────────────────────────────────────
Session          Agent              Calls   Failed   Duration   Servers
sess-f2a9b1      support-agent          5        1    1,482ms   postgres-mcp
sess-d4c7e8      data-analyst          12        0    4,210ms   postgres-mcp, s3-mcp
```

### Run a health check

```bash
langsight mcp-health
```

```
MCP Server Health                                    6 servers monitored
────────────────────────────────────────────────────────────────────────
Server              Status    Latency       Schema    Tools   Last Check
snowflake-mcp       ✅ UP     142ms         Stable    8       12s ago
github-mcp          ✅ UP     89ms          Stable    12      8s ago
slack-mcp           ⚠️ DEG   1,240ms       Stable    4       5s ago
jira-mcp            ❌ DOWN   —             —         —       3s ago
postgres-mcp        ✅ UP     31ms          Changed   5       15s ago
filesystem-mcp      ✅ UP     12ms          Stable    6       10s ago
```

### Run a security scan

```bash
langsight security-scan
```

```
Security Scan Results                               Scanned 6 servers
────────────────────────────────────────────────────────────────────────
CRITICAL  jira-mcp           CVE-2025-6514  Remote code execution in mcp-remote
HIGH      slack-mcp          OWASP-MCP-01   Tool description contains injection pattern
HIGH      postgres-mcp       OWASP-MCP-04   No authentication configured
```

### Start continuous monitoring

```bash
langsight monitor
```

> [!TIP]
> Add `--json` to any command for machine-readable output suitable for CI/CD pipelines. Use `--ci` on `security-scan` to exit with code `1` on CRITICAL findings.

---

## CLI Reference

| Command | Description |
|---------|-------------|
| `langsight init` | Interactive setup wizard, generates `.langsight.yaml` |
| `langsight sessions` | List recent agent sessions with call counts, failures, duration, and servers |
| `langsight sessions --id <id>` | Full multi-agent trace for one session |
| `langsight mcp-health` | Health status of all configured MCP servers |
| `langsight security-scan` | CVE (OSV) + OWASP MCP checks (5 of 10) + poisoning detection |
| `langsight monitor` | Start continuous background monitoring with alerts |
| `langsight costs` | Tool call cost attribution by server and agent session |
| `langsight investigate` | AI-assisted failure investigation for a server |
| `langsight serve` | Start the LangSight REST API server |

All commands support `--help`, `--json`, and `--verbose`.

---

## Configuration

LangSight is configured via `.langsight.yaml` in your project root (or `~/.langsight.yaml` for global config):

```yaml
servers:
  - name: snowflake-mcp
    transport: stdio
    command: python /path/to/snowflake_mcp/server.py
    tags: [production, data]

  - name: github-mcp
    transport: sse
    url: http://localhost:8080/sse
    tags: [production, devtools]

alerts:
  slack_webhook: ${LANGSIGHT_SLACK_WEBHOOK}
  error_rate_threshold: 0.05      # 5%
  latency_spike_multiplier: 3.0   # 3x baseline
  consecutive_failures: 3

storage:
  mode: dual                      # postgres | clickhouse | dual (default: dual)
  postgres_url: ${LANGSIGHT_POSTGRES_URL}
```

### Key environment variables

| Variable | Required | Description |
|---|---|---|
| `LANGSIGHT_API_KEYS` | Yes (production) | Comma-separated API keys for SDK/CLI auth |
| `LANGSIGHT_POSTGRES_URL` | Yes | PostgreSQL DSN |
| `LANGSIGHT_CLICKHOUSE_URL` | No (default: `http://localhost:8123`) | ClickHouse HTTP URL |
| `LANGSIGHT_TRUSTED_PROXY_CIDRS` | No | CIDRs trusted as the Next.js proxy (default: `127.0.0.1/32,::1/128`). Set to include `172.16.0.0/12,10.0.0.0/8` in Docker deployments. |
| `LANGSIGHT_DASHBOARD_URL` | No | Dashboard base URL used in invite links |
| `LANGSIGHT_CORS_ORIGINS` | No (default: `*`) | Restrict CORS in production |
| `AUTH_SECRET` | Yes (dashboard) | NextAuth session signing secret (`openssl rand -base64 32`) |
| `LANGSIGHT_ADMIN_EMAIL` | Yes (dashboard) | Initial admin login email |
| `LANGSIGHT_ADMIN_PASSWORD` | Yes (dashboard) | Initial admin login password |

> [!IMPORTANT]
> Never commit secrets to `.langsight.yaml` or `.env`. Use environment variables with the `LANGSIGHT_` prefix or your existing secret management tooling.

---

## Test MCP Servers

The `test-mcps/` directory contains two real MCP servers for local development and integration testing.

| Server | Transport | Tools |
|--------|-----------|-------|
| `postgres-mcp` | stdio | `query`, `list_tables`, `describe_table`, `get_row_count`, `get_schema_summary` |
| `s3-mcp` | stdio | `list_buckets`, `list_objects`, `get_object_metadata`, `read_object`, `put_object`, `delete_object`, `search_objects` |

### Start the test stack

```bash
# Start PostgreSQL with sample data
cd test-mcps
docker compose up -d

# Set up PostgreSQL MCP
cd postgres-mcp
cp .env.example .env
uv sync

# Set up S3 MCP
cd ../s3-mcp
cp .env.example .env   # Fill in your AWS credentials
uv sync
```

The PostgreSQL database is pre-seeded with an e-commerce schema: `customers`, `products`, `orders`, `order_items`, and `agent_conversations` — useful for testing queries, schema drift detection, and agent conversation replay.

---

## Integrations

LangSight works with every major MCP client and agent framework:

| Framework | Integration |
|-----------|------------|
| Claude Desktop | Auto-discovered by `langsight init` |
| Cursor | Auto-discovered by `langsight init` |
| VS Code | Auto-discovered by `langsight init` |
| LibreChat | Native plugin — `LANGSIGHT_URL` env var |
| LangChain | `LangSightLangChainCallback` |
| Langflow | `LangSightLangChainCallback` (LangChain-compatible) |
| LangGraph | `LangSightLangChainCallback` (LangChain-compatible) |
| LangServe | `LangSightLangChainCallback` (LangChain-compatible) |
| CrewAI | `LangSightCrewAICallback` |
| Pydantic AI | `@langsight_tool` decorator |
| Any OTEL framework | OTLP endpoint (`POST /api/traces/otlp`) |

---

## Roadmap

### Phase 1 — CLI MVP
- [x] `langsight init` with auto-discovery
- [x] `langsight mcp-health` — health checks for stdio, SSE, StreamableHTTP transports
- [x] `langsight security-scan` — CVE (OSV) + 5 of 10 OWASP MCP checks + poisoning detection
- [x] `langsight monitor` — continuous monitoring with Slack/webhook alerts
- [x] `langsight costs` — tool call cost attribution from OTEL traces
- [x] PostgreSQL + ClickHouse backends via `docker compose up -d`

### Phase 2 — SDK + Agent Tracing + Investigation
- [x] `LangSightClient` Python SDK — 2-line instrumentation for any MCP client
- [x] `parent_span_id` on `ToolCallSpan` — multi-agent tree tracing
- [x] `langsight sessions` — agent session list and trace drill-down
- [x] `GET /api/agents/sessions` and `GET /api/agents/sessions/{id}` endpoints
- [x] Agent spans (lifecycle) and Handoff spans (agent-to-agent delegation)
- [x] Framework adapters: CrewAI, Pydantic AI, LangChain, Langflow, LangGraph, LangServe, LibreChat
- [x] `langsight investigate` — AI-assisted root cause attribution (Claude Agent SDK)
- [x] ClickHouse + PostgreSQL backend for production deployments
- [x] OTLP/JSON endpoint for trace ingestion from agent frameworks (`POST /api/traces/otlp`)
- [ ] OTEL Collector infrastructure (separate service — collector config + Docker Compose wiring)

### Phase 3 — Dashboard + Auth + Multi-Tenancy
- [x] Next.js 15 web dashboard (`dashboard/`)
- [x] Real-time health overview across all MCP servers
- [x] Security posture timeline
- [x] Cost attribution charts by server, tool, and agent session
- [x] Alert management UI
- [x] Marketing website (`website/`)
- [x] Docs site (28 Mintlify pages, `docs-site/`)
- [x] FastAPI REST API with `langsight serve`
- [x] Production auth — API key auth (SDK/CLI) + NextAuth session proxy (dashboard)
- [x] RBAC — admin/viewer roles on all write endpoints
- [x] Dual-storage architecture — Postgres metadata + ClickHouse analytics
- [x] Project-level data isolation (`project_id` scoping at DB layer)
- [x] Accept-invite flow, settings page, audit logs, alert config persistence
- [ ] Dashboard: Vercel deploy (manual step pending)

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Language | Python 3.11+ |
| CLI | Click + Rich |
| API | FastAPI (async) |
| MCP client | `mcp` Python SDK |
| OLAP storage | ClickHouse (analytics: spans, health, costs) |
| Metadata DB | PostgreSQL via asyncpg (users, projects, API keys, SLOs) |
| Trace ingestion | OTEL Collector (contrib) |
| RCA agent | Claude Agent SDK (Phase 2) |
| Dashboard | Next.js 15 + shadcn/ui (Phase 3) |
| Auth | NextAuth.js (dashboard) + API key (SDK/CLI) |
| Package manager | uv |

---

## Development

```bash
# Install with dev dependencies
uv sync --dev

# Start the full stack (required for integration tests)
docker compose up -d

# Run unit tests only (no Docker required)
uv run pytest -m unit

# Run integration tests (requires docker compose up -d)
uv run pytest tests/integration/ tests/regression/ -m integration -v

# Run all tests with coverage
uv run pytest --cov=langsight --cov-report=term-missing

# Type check
uv run mypy src/

# Lint and format
uv run ruff check src/ && uv run ruff format src/
```

### Test environment variables for integration tests

```bash
TEST_POSTGRES_URL=postgresql://langsight:testpassword@localhost:5432/langsight
TEST_CLICKHOUSE_HOST=localhost
TEST_CLICKHOUSE_PORT=8123
```

> [!NOTE]
> Unit tests run without any external dependencies — they mock all I/O. Integration tests require `docker compose up -d` and are marked `@pytest.mark.integration`. The `tests/conftest.py` `require_postgres` and `require_clickhouse` fixtures auto-skip tests when Docker is not running.

---

## Security

LangSight monitors MCP security — it must itself be secure. If you discover a vulnerability, please report it via [GitHub Security Advisories](https://github.com/sumankalyan123/langsight/security/advisories) rather than a public issue.

---

## License

BSL 1.1 — self-host free, no usage limits. See [LICENSE](LICENSE).

Each version converts to Apache 2.0 four years after release. The only restriction: you may not offer LangSight as a hosted/managed service to third parties.
