# LangSight

**Your agent failed. Which tool broke — and why?**

Trace what your agents called. Find what broke, what's expensive, and what's unsafe.

[![PyPI](https://img.shields.io/pypi/v/langsight)](https://pypi.org/project/langsight/)
[![License: BSL 1.1](https://img.shields.io/badge/License-BSL%201.1-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/downloads/)
[![CI](https://github.com/sumankalyan123/langsight/actions/workflows/ci.yml/badge.svg)](https://github.com/sumankalyan123/langsight/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/docs-mintlify-green)](https://lngsight.mintlify.app)

> **Not another prompt, eval, or simulation platform.**
> LangSight monitors the runtime layer: the tools your agents depend on.

---

## What question are you trying to answer?

| Question | Best tool |
|----------|-----------|
| Did the prompt/model perform well? | LangWatch / Langfuse / LangSmith |
| Should I change prompts or eval policy? | LangWatch / Langfuse / LangSmith |
| Is my server CPU/memory healthy? | Datadog / New Relic |
| **Which tool call failed in production?** | **LangSight** |
| **Is an MCP server unhealthy or drifting?** | **LangSight** |
| **Is an MCP server exposed or risky?** | **LangSight** |
| **Why did this session cost $47 instead of $3?** | **LangSight** |

LangSight complements Langfuse, LangWatch, and LangSmith. They trace LLM reasoning. LangSight traces what agents actually *did* — and goes deep on MCP servers with health checks, security scanning, and schema drift detection.

---

## The problem

LLM quality is only half the problem. Teams already have ways to inspect prompts, completions, and eval scores. What they still cannot answer fast enough:

- **What did the agent actually call?** No trace of which tools ran, in what order
- **Which MCP server degraded?** Agents silently return bad data; you find out from users
- **Did a tool schema change?** Column names drift, agents hallucinate, nobody knows why
- **Is this MCP server unsafe to run?** 66% of community MCP servers have critical code smells
- **Which downstream tool caused the incident?** 3 days of manual log replay to find out

---

## The solution

### 1. Action traces

See the exact sequence of tool calls, handoffs, failures, and costs across a full agent session.

```
$ langsight sessions --id sess-f2a9b1

Trace: sess-f2a9b1  (support-agent)
5 tool calls · 1 failed · 2,134ms · $0.023

sess-f2a9b1
├── jira-mcp/get_issue        89ms  ✓
├── postgres-mcp/query        42ms  ✓
├──  → billing-agent          handoff
│   ├── crm-mcp/update_customer  120ms  ✓
│   └── slack-mcp/notify           —   ✗  timeout
Root cause: slack-mcp timed out at 14:32 UTC
```

### 2. MCP health

Detect down, slow, stale, or changed MCP servers before they silently corrupt agent behavior.

```
$ langsight mcp-health

Server              Status    Latency     Schema    Tools   Last Check
snowflake-mcp       ✅ UP     142ms       Stable    8       12s ago
slack-mcp           ⚠️ DEG   1,240ms     Stable    4       5s ago
jira-mcp            ❌ DOWN   —           —         —       3s ago
postgres-mcp        ✅ UP     31ms        Changed   5       15s ago
```

### 3. MCP security

Scan for CVEs, poisoning signals, weak auth, and risky server configs across your MCP fleet.

```
$ langsight security-scan

CRITICAL  jira-mcp        CVE-2025-6514  Remote code execution in mcp-remote
HIGH      slack-mcp       OWASP-MCP-01   Tool description contains injection pattern
HIGH      postgres-mcp    OWASP-MCP-04   No authentication configured
```

### 4. Cost attribution

Move from "the invoice is $4,200" to "billing-agent's geocoding MCP retries 47x per session."

```
$ langsight costs --hours 24

Tool                    Calls   Failed   Cost       % of Total
geocoding-mcp           2,340   12       $1,872     44.6%
postgres-mcp/query      890     3        $445       10.6%
claude-3.5 (LLM)       156     0        $312       7.4%
```

### 5. Fast root cause

Move from "the agent failed" to "jira-mcp returned 429s after a schema change at 14:32."

```
$ langsight investigate jira-mcp

Investigation: jira-mcp
├── Health: DOWN since 14:32 UTC (3 consecutive failures)
├── Schema: 2 tools changed (get_issue dropped 'priority' field)
├── Recent errors: 429 Too Many Requests (rate limit)
└── Recommendation: check API rate limits, restore 'priority' field
```

---

## What LangSight monitors per tool type

| Tool type | Trace calls | Health check | Security scan | Cost tracking |
|-----------|:-----------:|:------------:|:-------------:|:-------------:|
| MCP servers | Yes | Yes | Yes | Yes |
| HTTP APIs (Stripe, Sendgrid, etc.) | Yes | — | — | Yes |
| Python functions | Yes | — | — | Yes |
| Sub-agents | Yes | — | — | Yes |

MCP servers get proactive health checks and security scanning because the MCP protocol is standard and inspectable. Non-MCP tools appear in every trace but cannot be pinged or scanned.

---

## Quick start

### Prerequisites

- Docker and Docker Compose
- Python 3.11+ and [uv](https://docs.astral.sh/uv/)

### 1. Clone and start

```bash
git clone https://github.com/sumankalyan123/langsight.git
cd langsight
./scripts/quickstart.sh
```

The quickstart script generates all secrets, writes `.env`, and runs `docker compose up`. Takes ~2 minutes.

### 2. Open the dashboard

Go to **http://localhost:3003** and log in with `admin@admin.com` / `admin`.

A **Sample Project** with 25 demo agent sessions is pre-loaded so you can explore sessions, traces, and cost views immediately.

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

That's it. Two lines. Every tool call is now traced.

### Auto-discover MCP servers

```bash
langsight init
```

Auto-discovers MCP servers from Claude Desktop, Cursor, and VS Code configs. Writes `.langsight.yaml`.

> **Tip:** Add `--json` to any command for machine-readable output. Use `--ci` on `security-scan` to exit with code 1 on CRITICAL findings.

---

## Architecture

```
  Agent Frameworks                    ┌──────────────────────────────────┐
  (CrewAI, Pydantic AI,               │         LangSight Platform        │
   LangChain, LangGraph, etc.)       │                                  │
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
                                      │  │  FastAPI   │ │  Dashboard  │ │
                                      │  │  REST API  │ │  Next.js 15 │ │
                                      │  └─────┬──────┘ └─────────────┘ │
                                      │        ▼                         │
                                      │  ┌───────────┐  ┌─────────────┐ │
                                      │  │ CLI       │  │ Slack /     │ │
                                      │  │ langsight │  │ Webhook     │ │
                                      │  └───────────┘  └─────────────┘ │
                                      └──────────────────────────────────┘
```

**Dual-backend storage:**
- **PostgreSQL** — metadata: users, projects, API keys, model pricing, SLOs, alert config, audit logs
- **ClickHouse** — analytics: spans, traces, health results, reliability, costs, sessions

---

## CLI reference

| Command | Description |
|---------|-------------|
| `langsight init` | Interactive setup wizard, auto-discovers MCP servers |
| `langsight sessions` | List recent agent sessions with call counts, failures, duration |
| `langsight sessions --id <id>` | Full multi-agent trace for one session |
| `langsight mcp-health` | Health status of all configured MCP servers |
| `langsight security-scan` | CVE + OWASP MCP + poisoning detection |
| `langsight monitor` | Continuous background monitoring with alerts |
| `langsight costs` | Cost attribution by server, agent, and session |
| `langsight investigate` | AI-assisted failure investigation |
| `langsight serve` | Start the REST API server |

All commands support `--help`, `--json`, and `--verbose`.

---

## Integrations

| Framework | Integration |
|-----------|------------|
| Claude Desktop | Auto-discovered by `langsight init` |
| Cursor / VS Code | Auto-discovered by `langsight init` |
| LangChain / LangGraph | `LangSightLangChainCallback` |
| CrewAI | `LangSightCrewAICallback` |
| Pydantic AI | `@langsight_tool` decorator |
| LibreChat | Native plugin |
| Any OTEL framework | OTLP endpoint (`POST /api/traces/otlp`) |

---

## Configuration

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
  consecutive_failures: 3

storage:
  mode: dual
  postgres_url: ${LANGSIGHT_POSTGRES_URL}
```

### Environment variables

| Variable | Required | Description |
|---|---|---|
| `LANGSIGHT_API_KEYS` | Yes | Comma-separated API keys for SDK/CLI auth |
| `LANGSIGHT_POSTGRES_URL` | Yes | PostgreSQL DSN |
| `LANGSIGHT_CLICKHOUSE_URL` | No | ClickHouse HTTP URL (default: `http://localhost:8123`) |
| `AUTH_SECRET` | Yes (dashboard) | NextAuth session signing secret |
| `LANGSIGHT_ADMIN_EMAIL` | Yes (dashboard) | Initial admin login email |
| `LANGSIGHT_ADMIN_PASSWORD` | Yes (dashboard) | Initial admin login password |

> **Important:** Never commit secrets to `.langsight.yaml` or `.env`. Use environment variables with the `LANGSIGHT_` prefix.

---

## Tech stack

| Layer | Technology |
|-------|------------|
| Language | Python 3.11+ |
| CLI | Click + Rich |
| API | FastAPI (async) |
| OLAP storage | ClickHouse |
| Metadata DB | PostgreSQL (asyncpg) |
| Trace ingestion | OTEL Collector |
| Dashboard | Next.js 15 + Radix UI |
| Auth | NextAuth.js + API keys |
| Package manager | uv |

---

## Development

```bash
uv sync --dev
docker compose up -d

# Unit tests (no Docker needed)
uv run pytest -m unit

# Integration tests
uv run pytest -m integration

# All tests with coverage
uv run pytest --cov=langsight --cov-report=term-missing

# Type check + lint
uv run mypy src/ && uv run ruff check src/
```

---

## Security

LangSight monitors MCP security — it must itself be secure. If you discover a vulnerability, please report it via [GitHub Security Advisories](https://github.com/sumankalyan123/langsight/security/advisories).

---

## License

BSL 1.1 — self-host free, no usage limits. See [LICENSE](LICENSE).

Each version converts to Apache 2.0 four years after release. The only restriction: you may not offer LangSight as a hosted/managed service to third parties.
