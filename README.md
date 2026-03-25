# LangSight

**Your agent failed. Which tool broke — and how do we stop it next time?**

Detect loops. Enforce budgets. Break failing tools. Map blast radius.
For MCP servers: health checks, security scanning, schema drift detection.

[![Website](https://img.shields.io/badge/website-langsight.dev-blue)](https://www.langsight.dev)
[![PyPI](https://img.shields.io/pypi/v/langsight)](https://pypi.org/project/langsight/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/downloads/)
[![CI](https://github.com/LangSight/langsight/actions/workflows/ci.yml/badge.svg)](https://github.com/LangSight/langsight/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/docs-langsight.dev-green)](https://docs.langsight.dev)

> **Not another prompt, eval, or simulation platform.**
> LangSight is the runtime reliability layer for AI agent toolchains.

---

## Where LangSight fits

Langfuse watches the **brain** (model outputs, token costs, evals).
LangWatch tests the **brain** (simulations, prompt optimization).
Datadog watches the **body** (CPU, memory, HTTP codes).
**LangSight watches the hands** (tools the agent calls, their health, safety, and cost).

| Question | Best tool |
|----------|-----------|
| Did the prompt/model perform well? | LangWatch / Langfuse / LangSmith |
| Should I change prompts or eval policy? | LangWatch / Langfuse / LangSmith |
| Is my server CPU/memory healthy? | Datadog / New Relic |
| **Which tool call failed in production?** | **LangSight** |
| **Is my agent stuck in a loop?** | **LangSight** |
| **Is an MCP server unhealthy or drifting?** | **LangSight** |
| **Is an MCP server exposed or risky?** | **LangSight** |
| **Why did this session cost $47 instead of $3?** | **LangSight** |
| **If this tool goes down, which agents break?** | **LangSight** |

Use LangSight alongside Langfuse and LangWatch — not instead of them.

---

## The problem

LLM quality is only half the problem. Teams already have ways to inspect prompts and eval scores. What they still cannot answer fast enough:

- **Agent stuck in a loop** — retries the same tool 47 times, burns $200, produces nothing
- **MCP server degraded silently** — schema changed, latency spiked, auth expired. Agent keeps calling, gets bad data
- **Cost explosion** — sub-agent retries geocoding-mcp endlessly. Nobody knows until the invoice arrives
- **Cascading failure** — postgres-mcp goes down. 3 agents depend on it. All sessions fail. No blast radius visibility
- **Unsafe MCP server** — 66% of community MCP servers have critical code smells. No automated scanning

---

## What LangSight does

### 1. Prevent — stop failures before users notice

```python
from langsight.sdk import LangSightClient

client = LangSightClient(
    url="http://localhost:8000",
    loop_detection=True,        # detect same tool+args called 3x → auto-stop
    max_cost_usd=1.00,          # hard budget limit per session
    max_steps=25,               # hard step limit
    circuit_breaker=True,       # auto-disable tools after 5 consecutive failures
)
```

- **Loop detection** — same tool called with same args 3x → session terminated, alert fired
- **Budget guardrails** — max cost / max steps per session → hard stop before bill shock
- **Circuit breaker** — tool fails 5x → auto-disabled for cooldown → alert → auto-recovery test

### 2. Detect — see what broke and why

```
$ langsight sessions --id sess-f2a9b1

Trace: sess-f2a9b1  (support-agent)  [LOOP_DETECTED]
5 tool calls · 1 failed · 2,134ms · $0.023

sess-f2a9b1
├── jira-mcp/get_issue        89ms  ✓
├── postgres-mcp/query        42ms  ✓
├──  → billing-agent          handoff
│   ├── crm-mcp/update    120ms  ✓
│   └── slack-mcp/notify    —   ✗  timeout
Root cause: slack-mcp timed out at 14:32 UTC
```

- **Action traces** — every tool call in every session, with latency, status, cost
- **Multi-agent trees** — full call tree across agent handoffs via `parent_span_id`
- **Run health tags** — every session auto-classified: `success`, `loop_detected`, `budget_exceeded`, `tool_failure`

### 3. Monitor — MCP health + security

```
$ langsight mcp-health

Server              Status    Latency     Schema    Circuit
snowflake-mcp       ✅ UP     142ms       Stable    closed
slack-mcp           ⚠️ DEG   1,240ms     Stable    closed
jira-mcp            ❌ DOWN   —           —         open (5 failures)
postgres-mcp        ✅ UP     31ms        Changed   closed
```

```
$ langsight security-scan

CRITICAL  jira-mcp        CVE-2025-6514  Remote code execution in mcp-remote
HIGH      slack-mcp       OWASP-MCP-01   Tool description contains injection pattern
HIGH      postgres-mcp    OWASP-MCP-04   No authentication configured
```

- **MCP health checks** — continuous ping, latency, uptime tracking
- **Schema drift detection** — tool schemas change → alert fires before agents hallucinate
- **Security scanning** — CVE (OSV), OWASP MCP Top 10, tool poisoning detection, auth audit

### 4. Attribute — cost at the tool level

```
$ langsight costs --hours 24

Tool                    Calls   Failed   Cost       % of Total
geocoding-mcp           2,340   12       $1,872     44.6%
postgres-mcp/query      890     3        $445       10.6%
claude-3.5 (LLM)       156     0        $312       7.4%
```

Not model-level costs (Langfuse does that). **Tool-level costs.** Which MCP server is burning your budget?

### 5. Map — blast radius via lineage

```
postgres-mcp ❌ DOWN

Impact:
  - support-agent: 200 sessions/day (HIGH)
  - billing-agent: 50 sessions/day (MEDIUM)
  - data-agent: 10 sessions/day (LOW)

Total: ~260 sessions/day affected
Circuit breaker: active (auto-disabled 3 minutes ago)
```

- **Lineage DAG** — which agents call which tools
- **Blast radius** — if this tool goes down, what else breaks?
- **Impact alerts** — "postgres-mcp is DOWN — 3 agents affected, 260 sessions/day"

### 6. Investigate — AI-assisted root cause

```
$ langsight investigate jira-mcp

Investigation: jira-mcp
├── Health: DOWN since 14:32 UTC (3 consecutive failures)
├── Schema: 2 tools changed (get_issue dropped 'priority' field)
├── Recent errors: 429 Too Many Requests (rate limit)
└── Recommendation: check API rate limits, restore 'priority' field
```

---

## Quick start

### Prerequisites

- Docker and Docker Compose
- Python 3.11+ and [uv](https://docs.astral.sh/uv/)

### 1. Clone and start

```bash
git clone https://github.com/LangSight/langsight.git
cd langsight
./scripts/quickstart.sh
```

Takes ~2 minutes. Generates secrets, starts 5 containers, seeds demo data.

### 2. Open the dashboard

**http://localhost:3003** — log in with `admin@admin.com` / `admin`.

### 3. Instrument your agent

```python
from langsight.sdk import LangSightClient

client = LangSightClient(url="http://localhost:8000", api_key="<from quickstart>")
traced = client.wrap(mcp_session, server_name="postgres-mcp", agent_name="my-agent")
result = await traced.call_tool("query", {"sql": "SELECT * FROM orders"})
```

Two lines. Every tool call is now traced, guarded, and cost-attributed.

---

## Alerting

| Channel | Status |
|---|---|
| Slack (Block Kit) | Shipped |
| Generic webhook | Shipped |
| OpsGenie (native Events API) | v0.3 |
| PagerDuty (Events API v2) | v0.3 |

Alert types: server down/recovered, schema drift, latency spike, SLO breach, anomaly, loop detected, budget exceeded, circuit breaker open, failure rate spike, blast radius impact.

---

## Architecture

```
  Agent Frameworks                    ┌──────────────────────────────────┐
  (LangGraph, CrewAI,                 │         LangSight Platform        │
   Pydantic AI, etc.)                │                                  │
         │                            │  ┌──────────┐ ┌──────────────┐  │
         │ SDK (trace + guard)        │  │ Health   │ │  Security    │  │
         ▼                            │  │ Checker  │ │  Scanner     │  │
  ┌─────────────┐                     │  └────┬─────┘ └──────┬───────┘  │
  │    OTEL     │────────────────────►│       │              │          │
  │  Collector  │                     │       ▼              ▼          │
  └─────────────┘                     │  ┌───────────────────────────┐  │
                                      │  │       ClickHouse          │  │
  MCP Servers                         │  │  traces · health · costs  │  │
  ┌──────────┐                        │  └───────────────────────────┘  │
  │ server-1 │◄──────────────────────►│  ┌───────────────────────────┐  │
  │ server-2 │   health + security    │  │       PostgreSQL          │  │
  │ server-N │                        │  │  users · alerts · SLOs    │  │
  └──────────┘                        │  └───────────────────────────┘  │
                                      │                                 │
                                      │  ┌──────────┐ ┌─────────────┐  │
                                      │  │ FastAPI  │ │ Dashboard   │  │
                                      │  │ REST API │ │ Next.js 15  │  │
                                      │  └──────────┘ └─────────────┘  │
                                      └──────────────────────────────────┘
```

---

## Integrations

| Framework | Integration | Docs |
|-----------|------------|------|
| **Google Gemini SDK** (direct) | `client.wrap_llm(genai_client)` | [Direct SDK guide](https://docs.langsight.dev/sdk/integrations/direct-sdk) |
| **OpenAI SDK** (direct) | `client.wrap_llm(openai_client)` | [Direct SDK guide](https://docs.langsight.dev/sdk/integrations/direct-sdk) |
| **Anthropic SDK** (direct) | `client.wrap_llm(anthropic_client)` | [Direct SDK guide](https://docs.langsight.dev/sdk/integrations/direct-sdk) |
| LangGraph | `LangSightLangGraphCallback` | [Docs](https://docs.langsight.dev) |
| LangChain / Langflow | `LangSightLangChainCallback` | [Docs](https://docs.langsight.dev) |
| CrewAI | `LangSightCrewAICallback` | [Docs](https://docs.langsight.dev) |
| OpenAI Agents SDK | `LangSightOpenAIHooks` | [Docs](https://docs.langsight.dev) |
| Anthropic / Claude Agent SDK | `AnthropicToolTracer` | [Docs](https://docs.langsight.dev) |
| Pydantic AI | `@langsight_tool` decorator | [Docs](https://docs.langsight.dev) |
| Claude Desktop / Cursor / VS Code | Auto-discovered by `langsight init` | [Docs](https://docs.langsight.dev) |
| Any OTEL framework | OTLP endpoint | [Docs](https://docs.langsight.dev) |

### Using LangSight with direct LLM SDKs (Google Gemini, OpenAI, Anthropic)

If you are building AI agents **without LangChain or LangGraph** — using the native Google Gemini SDK, OpenAI SDK, or Anthropic SDK directly — LangSight supports you via `wrap_llm()`:

```python
import langsight
from google import genai  # or openai / anthropic

ls = langsight.init()  # reads LANGSIGHT_URL, LANGSIGHT_API_KEY, LANGSIGHT_PROJECT_ID from env

raw_client = genai.Client(api_key="...")
client = ls.wrap_llm(raw_client, agent_name="my-agent", session_id="sess-001")

# All generate_content() calls are now traced automatically
response = await client.aio.models.generate_content(model="gemini-2.5-flash", ...)
```

Wrap MCP sessions with `ls.wrap()` to trace tool calls:

```python
traced_session = ls.wrap(mcp_session, server_name="my-mcp-server", agent_name="my-agent")
result = await traced_session.call_tool("my_tool", {"arg": "value"})
```

**Full guide:** [https://docs.langsight.dev/sdk/integrations/direct-sdk](https://docs.langsight.dev/sdk/integrations/direct-sdk)

---

## CLI reference

| Command | Description |
|---------|-------------|
| `langsight init` | Auto-discover MCP servers, generate config |
| `langsight sessions` | List sessions with health tags, costs, failures |
| `langsight sessions --id <id>` | Full trace for one session |
| `langsight mcp-health` | Health status + circuit breaker state |
| `langsight security-scan` | CVE + OWASP MCP + poisoning detection |
| `langsight monitor` | Continuous monitoring with alerts |
| `langsight costs` | Cost attribution by tool, agent, session |
| `langsight investigate` | AI-assisted failure investigation |

---

## Development

```bash
uv sync --dev && docker compose up -d
uv run pytest -m unit                    # no Docker needed
uv run pytest -m integration             # requires Docker
uv run pytest --cov=langsight            # with coverage
uv run mypy src/ && uv run ruff check src/
```

---

## Security

LangSight monitors MCP security — it must itself be secure. Report vulnerabilities via [GitHub Security Advisories](https://github.com/LangSight/langsight/security/advisories).

---

## License

Apache 2.0 — free to use, modify, distribute, and build on. See [LICENSE](LICENSE).

---

**Website:** [https://www.langsight.dev](https://www.langsight.dev)
**Docs:** [https://docs.langsight.dev](https://docs.langsight.dev)
**Direct SDK (Google Gemini / OpenAI / Anthropic):** [https://docs.langsight.dev/sdk/integrations/direct-sdk](https://docs.langsight.dev/sdk/integrations/direct-sdk)
