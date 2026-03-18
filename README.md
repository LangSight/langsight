# LangSight

**Complete observability for everything an AI agent calls — MCP servers, HTTP APIs, functions, and sub-agents — with built-in health monitoring and security scanning for MCP servers.**

[![PyPI](https://img.shields.io/pypi/v/langsight)](https://pypi.org/project/langsight/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
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
| Which of 15 tools failed? | 3 days of manual log replay | Root cause in the `investigate` command |
| Tool call costs | Invisible, discovered on the invoice | Per-session cost attribution in real time |
| Tool returning stale data | Agent hallucinates; you find out from users | Schema drift alert fires in <5 minutes |
| CVE in a community MCP server | Unknown until exploited | Automated CVE scan on every check |

> [!NOTE]
> 66% of MCP servers have critical code smells and 8,000+ are exposed without authentication (Invariant Labs, 2025). LangSight is the reliability and security layer that MCP infrastructure has been missing.

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
- Continuous availability checks (ping, tools list, optional sample invocation)
- Server state tracking: `UP → DEGRADED → DOWN → STALE`
- Schema drift detection — alerts when a tool's output format changes
- p50/p99 latency tracking per server and per tool

**Security Scanning** *(Secondary, unique vs competitors)*
- CVE database matching (NVD + GitHub Advisory + MCP-specific advisories)
- OWASP MCP Top 10 automated checks
- Tool poisoning detection — baseline hash comparison on every scan
- Auth configuration audit (unauthenticated server detection, token exposure)

**Alerting**
- Slack webhook alerts with configurable thresholds
- Generic webhook for PagerDuty, Opsgenie, and custom systems
- Alert deduplication — no alert storms during outages

**Root Cause Investigation** *(Phase 2)*
- Timeline correlation across MCP calls and agent sessions
- `langsight investigate` — narrows failures to a specific tool and time window

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

**Storage strategy**:
- **SQLite** — local CLI mode, no Docker required
- **ClickHouse** — time-series health data, OTEL traces, cost attribution
- **PostgreSQL** — app state, MCP configs, alert rules, API keys

---

## Quick Start

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- Docker (for full stack with ClickHouse + PostgreSQL)

### Install

```bash
# Install from PyPI (once released)
uv tool install langsight

# Or install from source
git clone https://github.com/sumankalyan123/langsight.git
cd langsight
uv sync
```

### Initialize

```bash
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
Server              Status    p99 Latency   Schema    Tools   Last Check
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
| `langsight security-scan` | CVE + OWASP MCP Top 10 security audit |
| `langsight monitor` | Start continuous background monitoring with alerts |
| `langsight costs` | Tool call cost attribution by server and agent session |
| `langsight investigate` | Root cause analysis for a specific failure |
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
  mode: sqlite                    # sqlite | postgres+clickhouse
  sqlite_path: ~/.langsight/data.db
```

> [!IMPORTANT]
> Never commit secrets to `.langsight.yaml`. Use environment variables with the `LANGSIGHT_` prefix or your existing secret management tooling.

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
- [x] `langsight security-scan` — CVE + OWASP MCP Top 10
- [x] `langsight monitor` — continuous monitoring with Slack/webhook alerts
- [x] `langsight costs` — tool call cost attribution from OTEL traces
- [x] SQLite backend (no Docker required for local use)

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

### Phase 3 — Dashboard
- [x] Next.js 15 web dashboard (`dashboard/`)
- [x] Real-time health overview across all MCP servers
- [x] Security posture timeline
- [x] Cost attribution charts by server, tool, and agent session
- [x] Alert management UI
- [x] Marketing website (`website/`)
- [x] Docs site (28 Mintlify pages, `docs-site/`)
- [x] FastAPI REST API with `langsight serve`
- [ ] Dashboard: Vercel deploy (manual step pending)
- [ ] API key auth
- [ ] RBAC

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Language | Python 3.11+ |
| CLI | Click + Rich |
| API | FastAPI (async) |
| MCP client | `mcp` Python SDK |
| OLAP storage | ClickHouse |
| Metadata DB | PostgreSQL (asyncpg direct) |
| Local mode | SQLite |
| Trace ingestion | OTEL Collector (contrib) |
| RCA agent | Claude Agent SDK (Phase 2) |
| Dashboard | Next.js 15 + shadcn/ui (Phase 3) |
| Package manager | uv |

---

## Development

```bash
# Install with dev dependencies
uv sync --dev

# Run tests
uv run pytest

# Type check
uv run mypy src/

# Lint and format
uv run ruff check src/ && uv run ruff format src/

# Start test infrastructure
cd test-mcps && docker compose up -d
```

> [!NOTE]
> Integration tests require `docker compose up -d` and are marked `@pytest.mark.integration`. Unit tests run without any external dependencies.

---

## Security

LangSight monitors MCP security — it must itself be secure. If you discover a vulnerability, please report it via [GitHub Security Advisories](https://github.com/sumankalyan123/langsight/security/advisories) rather than a public issue.

---

## License

Apache 2.0 — see [LICENSE](LICENSE).
