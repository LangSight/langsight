# 08 — Adoption Strategy

> Updated 2026-03-22: Major rewrite — positioning pivot from "observability platform" to "agent runtime reliability platform." LangSight no longer competes with Langfuse/LangWatch. It is the complementary "tool layer" alongside them.

## Current Reality (March 2026)

- 0 GitHub stars, 0 forks, 0 external contributors
- Docker + Postgres + ClickHouse required to try anything
- **Positioning pivot complete**: LangSight is now "agent runtime reliability" — not observability. Observability overlaps with Langfuse (6k+ stars), Phoenix (15k+ stars), LangSmith (enterprise). Runtime reliability (prevent, detect, monitor, map) is an empty category.
- Real differentiator: loop detection, budget guardrails, circuit breakers, MCP health/security, blast radius analysis. Not traces. Not dashboards. Not evals.
- Product is a solid alpha with good architecture, but no external validation
- License: Apache 2.0 (free to use, modify, and distribute)
- Domain: langsight.dev | Repo: github.com/LangSight/langsight

**Core diagnosis**: LangSight tried to be an observability platform and got lost in Langfuse's shadow. The pivot to runtime reliability gives us an empty category. Nobody else does loop detection + budget guardrails + circuit breakers + MCP health + MCP security in one package. Own this category.

---

## Positioning: The Four Pillars

**Prevent. Detect. Monitor. Map.**

| Pillar | What it means | Key features |
|---|---|---|
| **Prevent** | Stop failures before they happen | Loop detection, budget guardrails, circuit breakers |
| **Detect** | Find threats and drift proactively | CVE scanning, OWASP MCP Top 10, tool poisoning, schema drift |
| **Monitor** | Track health and performance continuously | MCP health checks, latency tracking, SLOs, anomaly detection |
| **Map** | Understand blast radius and dependencies | Agent-to-tool lineage, dependency graphs, blast radius analysis |

**The tagline**: "Langfuse watches the brain. LangSight watches the hands."

**What we are NOT**: Another prompt, eval, or simulation platform.

---

## Strategy: Wedge → Complement → Expand

```
Phase 1 (Weeks 1-2):   WEDGE        → Zero-friction MCP security scanner
Phase 2 (Weeks 3-4):   COMPLEMENT   → Plug alongside Langfuse/LangWatch, not instead of them
Phase 3 (Weeks 5-8):   EXPAND       → Runtime guardrails + blast radius (the features nobody else has)
Phase 4 (Months 3-6):  OWN          → Own the "agent runtime reliability" category
```

(changed from original: Phase 2 was "INTEGRATE" — reframed as "COMPLEMENT" to reflect that we are a different category, not an add-on. Phase 4 was "PLATFORM" — reframed as "OWN" because we already have the platform; we need to own the positioning.)

---

## Phase 1: The Wedge (Weeks 1-2)

**Goal**: Get LangSight onto 500 machines via a zero-friction CLI tool.

### 1.1 — `pip install langsight` without Docker

The single highest-impact change. Today you need Docker + Postgres + ClickHouse to do *anything*. Most developers will bounce before `docker compose up` finishes.

**What ships:**
```bash
pip install langsight        # or: uv tool install langsight
langsight scan               # scan all MCP servers on this machine
```

Output:
```
Found 6 MCP servers (Claude Desktop: 3, Cursor: 2, VS Code: 1)

postgres-mcp     healthy  ·  5 tools  ·  CVE clean  ·  Auth: none
jira-mcp         healthy  ·  3 tools  ·  CVE-2025-4821 (HIGH)
slack-mcp        healthy  ·  4 tools  ·  CVE clean  ·  Auth: OAuth2
github-mcp       DOWN     ·  connection refused
filesystem-mcp   healthy  ·  6 tools  ·  MCP-06: plaintext HTTP
s3-mcp           healthy  ·  7 tools  ·  CVE clean  ·  Auth: IAM

2 issues found:
  CRITICAL  jira-mcp         CVE-2025-4821  Remote code execution
  WARNING   postgres-mcp     MCP-01         No authentication configured

Run 'langsight scan --fix' for remediation steps.
Run 'langsight scan --json' for CI/CD integration.
```

**What this requires technically:**
- Bring back SQLite as a lightweight local-only backend (health results + scan history only)
- `langsight scan` = `init` + `mcp-health` + `security-scan` in one command
- No API server, no dashboard, no ClickHouse, no Postgres
- Auto-discovers MCP servers from Claude Desktop, Cursor, VS Code configs
- Results stored in `~/.langsight/scan-history.db` (SQLite)

**Why this works for adoption:**
- Zero friction: `pip install` -> immediate value in 30 seconds
- Solves a real anxiety: "are my MCP servers safe?"
- Shareable output: screenshot the terminal, post in Slack/Discord
- CI/CD hook: `langsight scan --ci --fail-on=high` in GitHub Actions
- Natural upgrade path: "Want runtime guardrails and a dashboard? `docker compose up`"

### 1.2 — GitHub Actions marketplace action

```yaml
# .github/workflows/mcp-security.yml
name: MCP Security Scan
on: [push, pull_request]
jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: LangSight/langsight-scan@v1
        with:
          fail-on: high        # fail the build on HIGH+ findings
          config: .langsight.yaml
```

This is the `npm audit` / `trivy` equivalent for MCP servers. It positions LangSight as a security gate — part of the "Detect" pillar.

### 1.3 — Content that earns stars

Write 3 blog posts / dev.to articles targeting specific pain:

1. **"I audited 50 MCP servers. Here's what I found."** — Run `langsight scan` across popular community MCP servers, publish results. This is the security research angle that gets attention.

2. **"Your Claude Desktop MCP servers have no auth. Here's how to fix it."** — Practical guide using LangSight scan output. Targets Claude Desktop power users (large, active community).

3. **"Why your AI agent observability tool won't save you at 2 AM"** — Position the runtime reliability angle. Observability tells you what happened. LangSight prevents it from happening again. Loop detection, budget guardrails, circuit breakers.

### Phase 1 success metric
- 100+ `pip install langsight` downloads in week 2
- 50+ GitHub stars
- 3+ community issues filed

---

## Phase 2: Complement (Weeks 3-4)

**Goal**: Establish LangSight as the tool-layer complement alongside Langfuse/LangWatch, not a competitor.

(changed from original: was "Integrate" with the goal of "making LangSight a complement." Now explicitly positioned as a different category — we don't need to integrate to justify our existence; we need to show we solve a different problem.)

### 2.1 — "Langfuse + LangSight" guide

Publish a definitive guide: "Use Langfuse for LLM traces + LangSight for tool reliability." Show them working together with shared trace IDs.

Key message: **Langfuse watches the brain. LangSight watches the hands.** You need both.

```
Langfuse tells you: "The LLM decided to call postgres-mcp/query"
LangSight tells you: "That call failed because the MCP server was DOWN,
                      and 3 other agents are also affected (blast radius: 340 sessions)"
```

### 2.2 — OTLP span exporter

LangSight already *ingests* OTLP. Add an *exporter* so tool call spans flow *out* to wherever the team already looks:

```yaml
# .langsight.yaml
export:
  otlp:
    endpoint: http://localhost:4318    # -> Phoenix, Jaeger, Datadog, Grafana Tempo
  langfuse:
    public_key: pk-...
    secret_key: sk-...
    host: https://cloud.langfuse.com
```

**Why this matters**: Teams already have Langfuse or Phoenix for LLM observability. They won't rip them out. But they *will* add LangSight alongside if it feeds tool reliability data into what they already use. LangSight becomes a **complementary data source**, not a silo.

### 2.3 — Langfuse trace linking

If a span has a Langfuse trace ID, show a "View LLM reasoning in Langfuse ->" link in the LangSight dashboard. And vice versa: publish a Langfuse integration that links back to LangSight's tool health view.

Dashboard renders: `[View LLM reasoning in Langfuse ->]` next to each session.

### Phase 2 success metric
- Langfuse/LangWatch communities acknowledge LangSight as complementary (not competing)
- 1+ blog post from a Langfuse/Phoenix user mentioning LangSight
- 200+ GitHub stars

---

## Phase 3: Expand (Weeks 5-8)

**Goal**: Ship the runtime reliability features that no competitor has. This is where we own the category.

### 3.1 — Runtime guardrails (the "Prevent" pillar)

These are the features that make LangSight a runtime reliability platform, not just a monitor:

| Feature | What it does |
|---|---|
| **Loop detection** | Detect when an agent calls the same tool > N times in a session. Kill the loop before it burns budget. |
| **Budget guardrails** | Per-session and per-tool cost limits. Hard-stop when budget is exhausted. |
| **Circuit breakers** | When a tool fails N times, open the circuit and return a cached/fallback response instead of cascading the failure. |

These features exist in the SDK — they run at the agent level, not just the monitoring level. This is the key differentiator from every observability tool.

```python
from langsight import LangSightClient

client = LangSightClient(
    loop_detection={"max_repeat_calls": 5, "action": "warn"},
    budget_guardrails={"max_session_cost_usd": 1.00, "action": "kill"},
    circuit_breaker={"failure_threshold": 3, "cooldown_seconds": 60},
)
```

### 3.2 — Blast radius analysis (the "Map" pillar)

The DAG visualization of agent -> server -> tool dependencies, with blast radius overlay:

Key selling point: "Langfuse shows what your LLM decided. LangSight shows what breaks when `postgres-mcp` goes down — and which 340 sessions are affected."

### 3.3 — Fleet inventory + drift intelligence

```bash
langsight fleet                    # inventory of all MCP servers across your org
langsight fleet --diff 7d          # what changed in the last 7 days
```

```
MCP Fleet Status (14 servers across 3 projects)

New servers (last 7d):
  + anthropic-mcp     added by support-agent project
  + stripe-mcp        added by billing-agent project

Schema changes (last 7d):
  ~ postgres-mcp      tool 'query' input_schema changed (added 'timeout' param)
  ~ jira-mcp          tool 'create_issue' removed 'priority' field

Servers at risk:
  ! jira-mcp           CVE-2025-4821 (unfixed for 12 days)
  ! filesystem-mcp     no auth, 3 agents depend on it
```

### 3.4 — Deeper OWASP checks (6-10)

Ship the remaining 5 OWASP MCP checks. Prioritize:
- MCP-07 (Insecure Plugin Design) — most actionable
- MCP-09 (Overreliance on LLM) — most novel
- MCP-03 (Training Data Poisoning) — highest fear factor

### Phase 3 success metric
- Runtime guardrails demo'd in a YouTube video / tweet thread
- "Agent runtime reliability" appears in community discussions as a category
- 500+ GitHub stars
- 5+ community PRs
- 1+ company using LangSight in production (even if small)

---

## Phase 4: Own the Category (Months 3-6)

Only enter this phase with evidence of traction (500+ stars, 3+ production users).

### 4.1 — Hosted demo / playground

`demo.langsight.dev` — pre-loaded with sample multi-agent data showing loop detection, budget enforcement, blast radius. Zero install required.

### 4.2 — Single-binary deployment

Replace Docker Compose with a single Go/Rust binary that embeds Postgres and uses DuckDB/embedded ClickHouse for analytics. Target: `curl -fsSL install.langsight.dev | sh && langsight up`.

### 4.3 — Helm chart

For teams that want Kubernetes deployment. Include horizontal scaling, connection pooling, and ingestion queue.

### 4.4 — OpsGenie / PagerDuty native integration

Alert routing for the "Monitor" pillar. When a circuit breaker opens or an SLO breaches, page the right team.

### 4.5 — Team features

- SSO/OIDC (beyond password auth)
- Per-project API keys with scoped permissions
- Alert history with ack/silence/escalation
- Saved filters and search
- Export APIs (CSV, JSON, OpenLineage)

### 4.6 — Managed cloud (if traction justifies it)

Only if self-hosted adoption proves the market. Not before.

---

## What NOT to Build

These are tempting but will not help adoption:

| Temptation | Why not |
|---|---|
| LLM eval/scoring | Langfuse/Braintrust own this. Not our category. |
| Prompt management | LangSmith/Langfuse own this. Not our category. |
| LLM tracing | Langfuse/LangWatch own this. We are the tool layer, not the LLM layer. |
| Model playground | Not related to runtime reliability. |
| More dashboard pages | The dashboard is already broader than the user base justifies. |
| Enterprise features | No enterprise users yet. Build for the 1-person team first. |

---

## Messaging by Phase

### Phase 1 message (security wedge)
> "Scan your MCP servers for CVEs, auth gaps, and misconfigurations. One command. No Docker."
>
> `pip install langsight && langsight scan`

### Phase 2 message (complement)
> "Langfuse watches the brain. LangSight watches the hands. Use both."

### Phase 3 message (runtime reliability)
> "Your agent got stuck in a loop. LangSight would have killed it after 5 iterations. Prevent. Detect. Monitor. Map."

### Phase 4 message (category ownership)
> "Agent runtime reliability. Prevent loops, enforce budgets, monitor MCP health, scan for CVEs. Self-hosted or cloud."

---

## Competitive Framing

### We do NOT compete with:

| Tool | Their category | Our relationship |
|---|---|---|
| **Langfuse** | LLM observability (prompts, completions, evals) | Complementary — "brain vs hands" |
| **LangWatch** | LLM observability with prompt-level guardrails | Complementary — their guardrails are prompt-level; ours are tool-level |
| **LangSmith** | LLM development lifecycle | Different problem entirely |
| **Phoenix** | LLM tracing and debugging | Complementary — they trace LLM calls, we monitor tools |

### We DO compete with:

| Tool | Overlap | Our advantage |
|---|---|---|
| **MCPcat** | MCP analytics/logging | We add health monitoring, security scanning, runtime guardrails |
| **Sentry MCP** | MCP error tracking | We add proactive monitoring, CVE scanning, loop detection, blast radius |
| **Datadog AI** | Commercial APM with some MCP traces | We are deeper on MCP + cheaper (self-hosted, Apache 2.0) |
| **Nothing** | Loop detection + budget guardrails + circuit breakers | **Empty category** — nobody else does this |

### The key insight

"Agent runtime reliability" is an **empty category**. Observability is crowded (Langfuse, LangWatch, LangSmith, Phoenix, Datadog). Runtime reliability at the tool layer does not exist yet. LangSight claims it.

---

## Success Milestones

| Milestone | Target | Signal |
|---|---|---|
| First 100 installs | Week 2 | `pip install` works, content landed |
| First 50 stars | Week 3 | Security scanning resonates |
| First external PR | Week 4 | Someone cares enough to contribute |
| "Langfuse + LangSight" guide shared | Week 5 | Complement story works |
| First production user | Week 8 | Someone trusts it for real workloads |
| 500 stars | Month 3 | Community momentum |
| "Agent runtime reliability" used as a term by others | Month 4 | Category created |
| Hacker News front page | Month 4-6 | Runtime guardrails demo or security research post |

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| MCP doesn't become mainstream | Medium | Fatal | Ensure guardrails + lineage work for non-MCP tools too |
| Langfuse/LangWatch add tool-level guardrails | Low | High | Move faster on the full "prevent + detect + monitor + map" stack — hard to replicate the full surface |
| No one installs the CLI | Medium | High | Content marketing + GH Actions integration lower the bar |
| ClickHouse requirement scares small teams | High | Medium | Phase 1 is SQLite-only; Phase 4 targets single-binary |
| "Runtime reliability" framing doesn't resonate | Medium | High | A/B test messaging; fall back to "MCP security + health" if needed |
| Solo maintainer burnout | High | Fatal | Optimize for external contributions (good-first-issues, CONTRIBUTING.md) |

---

## Resource Allocation

Assuming solo developer + AI coding assistant:

| Week | Focus | % time |
|---|---|---|
| 1 | SQLite backend for CLI-only mode, `langsight scan` command | 80% code, 20% content |
| 2 | GitHub Actions action, blog post #1 (MCP audit results) | 50% code, 50% content |
| 3 | "Langfuse + LangSight" guide, OTLP exporter | 60% code, 40% content |
| 4 | Blog post #2 ("why observability won't save you"), community engagement | 30% code, 70% content |
| 5-6 | Loop detection, budget guardrails, circuit breakers (SDK) | 90% code, 10% docs |
| 7 | Blast radius + fleet inventory CLI, blog post #3 | 60% code, 40% content |
| 8 | OWASP checks 6-10, CVE lockfile resolution | 90% code, 10% docs |

Content is not optional. Without it, the code is invisible.

---

## One-Line Summary

**Stop trying to be Langfuse. Be the runtime reliability layer that Langfuse users also need. Prevent. Detect. Monitor. Map.**
