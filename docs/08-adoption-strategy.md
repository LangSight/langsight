# 08 — Adoption Strategy

## Current Reality (March 2026)

- 0 GitHub stars, 0 forks, 0 external contributors
- Docker + Postgres + ClickHouse required to try anything
- Positioning as "observability platform" — competing with Langfuse (6k+ stars), Phoenix (15k+ stars), LangSmith (enterprise)
- Real differentiator: MCP health/security ops. Not traces. Not dashboards.
- Product is a solid alpha with good architecture, but no external validation

**Core diagnosis**: LangSight is a tool pretending to be a platform. The path to becoming a platform starts with being an excellent tool first.

---

## Strategy: Wedge → Integrate → Expand

```
Phase 1 (Weeks 1-2):   WEDGE        → Zero-friction MCP security scanner
Phase 2 (Weeks 3-4):   INTEGRATE    → Plug into Langfuse/Phoenix, not replace them
Phase 3 (Weeks 5-8):   EXPAND       → Lineage graph + fleet intelligence
Phase 4 (Months 3-6):  PLATFORM     → Earn the platform claim with traction
```

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

postgres-mcp     ✓ healthy  ·  5 tools  ·  CVE clean  ·  Auth: none ⚠
jira-mcp         ✓ healthy  ·  3 tools  ·  CVE-2025-4821 (HIGH)
slack-mcp        ✓ healthy  ·  4 tools  ·  CVE clean  ·  Auth: OAuth2
github-mcp       ✗ DOWN     ·  connection refused
filesystem-mcp   ✓ healthy  ·  6 tools  ·  MCP-06: plaintext HTTP ⚠
s3-mcp           ✓ healthy  ·  7 tools  ·  CVE clean  ·  Auth: IAM

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
- Zero friction: `pip install` → immediate value in 30 seconds
- Solves a real anxiety: "are my MCP servers safe?"
- Shareable output: screenshot the terminal, post in Slack/Discord
- CI/CD hook: `langsight scan --ci --fail-on=high` in GitHub Actions
- Natural upgrade path: "Want a dashboard? `docker compose up`"

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

This is the `npm audit` / `trivy` equivalent for MCP servers. It positions LangSight as a security gate, not an observability platform.

### 1.3 — Content that earns stars

Write 3 blog posts / dev.to articles targeting specific pain:

1. **"I audited 50 MCP servers. Here's what I found."** — Run `langsight scan` across popular community MCP servers, publish results. This is the security research angle that gets attention.

2. **"Your Claude Desktop MCP servers have no auth. Here's how to fix it."** — Practical guide using LangSight scan output. Targets Claude Desktop power users (large, active community).

3. **"MCP security checklist for production"** — Reference the 5 OWASP checks with examples. Position LangSight as the tool that automates the checklist.

### Phase 1 success metric
- 100+ `pip install langsight` downloads in week 2
- 50+ GitHub stars
- 3+ community issues filed

---

## Phase 2: Integrate (Weeks 3-4)

**Goal**: Make LangSight a complement to existing tools, not a competitor.

### 2.1 — OTLP span exporter

LangSight already *ingests* OTLP. Add an *exporter* so tool call spans flow *out* to wherever the team already looks:

```yaml
# .langsight.yaml
export:
  otlp:
    endpoint: http://localhost:4318    # → Phoenix, Jaeger, Datadog, Grafana Tempo
  langfuse:
    public_key: pk-...
    secret_key: sk-...
    host: https://cloud.langfuse.com
```

**Why this matters**: Teams already have Langfuse or Phoenix. They won't rip it out. But they *will* add LangSight if it feeds into what they already use. LangSight becomes a **data source**, not a silo.

### 2.2 — Langfuse trace linking

If a span has a Langfuse trace ID (from the LangChain/CrewAI callback), show a "View in Langfuse →" link in the LangSight dashboard. And vice versa: publish a Langfuse integration that links back to LangSight's session trace.

**Implementation**: The LangSight SDK already captures `trace_id`. If the user also has a Langfuse callback, both tools see the same trace ID. Add a config option:
```yaml
integrations:
  langfuse_host: https://cloud.langfuse.com
```
Dashboard renders: `[View LLM reasoning in Langfuse →]` next to each session.

### 2.3 — Phoenix MCP tracing bridge

Phoenix already supports MCP tracing via OTEL. Publish a guide: "Use Phoenix for LLM traces + LangSight for MCP health/security." Show them working together with shared trace IDs.

### Phase 2 success metric
- Langfuse integration listed on langfuse.com/integrations
- 1+ blog post from a Langfuse/Phoenix user mentioning LangSight
- 200+ GitHub stars

---

## Phase 3: Expand (Weeks 5-8)

**Goal**: Ship the features that no competitor has.

### 3.1 — Agent Action Lineage (spec: 07-agent-lineage-spec.md)

The DAG visualization of agent → server → tool dependencies. Built from observed span data. This is the feature that earns "platform" positioning.

Key selling point: "Langfuse shows what your LLM decided. LangSight shows what depends on what — and what breaks when something goes down."

### 3.2 — Fleet inventory + drift intelligence

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
  ~ jira-mcp          tool 'create_issue' removed 'priority' field ⚠

Servers at risk:
  ! jira-mcp           CVE-2025-4821 (unfixed for 12 days)
  ! filesystem-mcp     no auth, 3 agents depend on it
```

This is the "fleet management" angle — borrowed from Kubernetes fleet management (Rancher, Fleet) and applied to MCP servers.

### 3.3 — Deeper OWASP checks (6-10)

Ship the remaining 5 OWASP MCP checks. Prioritize:
- MCP-07 (Insecure Plugin Design) — most actionable
- MCP-09 (Overreliance on LLM) — most novel
- MCP-03 (Training Data Poisoning) — highest fear factor

### 3.4 — CVE scanning with lockfile resolution

Current CVE scanning is package-name-only (noisy). Add lockfile parsing:
- `uv.lock`, `poetry.lock`, `package-lock.json`, `Pipfile.lock`
- Resolve exact installed versions before querying OSV
- Dramatically reduces false positives

### Phase 3 success metric
- Lineage graph demo'd in a YouTube video / tweet thread
- 500+ GitHub stars
- 5+ community PRs
- 1+ company using LangSight in production (even if small)

---

## Phase 4: Platform (Months 3-6)

Only enter this phase with evidence of traction (500+ stars, 3+ production users).

### 4.1 — Hosted demo / playground

`demo.langsight.dev` — pre-loaded with sample multi-agent data. Zero install required. Let people experience the lineage graph and session traces before committing to self-hosting.

### 4.2 — Single-binary deployment

Replace Docker Compose with a single Go/Rust binary that embeds Postgres and uses DuckDB/embedded ClickHouse for analytics. Target: `curl -fsSL install.langsight.dev | sh && langsight up`.

### 4.3 — Helm chart

For teams that want Kubernetes deployment. Include horizontal scaling, connection pooling, and ingestion queue.

### 4.4 — Team features

- SSO/OIDC (beyond password auth)
- Per-project API keys with scoped permissions
- Alert history with ack/silence/escalation
- Saved filters and search
- Export APIs (CSV, JSON, OpenLineage)

### 4.5 — Managed cloud (if traction justifies it)

Only if self-hosted adoption proves the market. Not before.

---

## What NOT to Build

These are tempting but will not help adoption:

| Temptation | Why not |
|---|---|
| LLM eval/scoring | Langfuse/Braintrust own this. Not differentiated. |
| Prompt management | LangSmith/Langfuse own this. |
| Model playground | Not related to the MCP ops wedge. |
| More dashboard pages | The dashboard is already broader than the user base justifies. |
| Enterprise features | No enterprise users yet. Build for the 1-person team first. |

---

## Messaging by Phase

### Phase 1 message (security wedge)
> "Scan your MCP servers for CVEs, auth gaps, and misconfigurations. One command. No Docker."
>
> `pip install langsight && langsight scan`

### Phase 2 message (integration)
> "LangSight plugs into your existing Langfuse/Phoenix setup. MCP health + security data flows into the tools you already use."

### Phase 3 message (lineage + fleet)
> "See which agents depend on which MCP servers. Know the blast radius before something breaks."

### Phase 4 message (platform)
> "Action-layer observability for AI agents. Traces, lineage, health, security — self-hosted or cloud."

Only claim "platform" after Phase 3 ships and has users.

---

## Success Milestones

| Milestone | Target | Signal |
|---|---|---|
| First 100 installs | Week 2 | `pip install` works, content landed |
| First 50 stars | Week 3 | Security scanning resonates |
| First external PR | Week 4 | Someone cares enough to contribute |
| First Langfuse integration user | Week 5 | Integration story works |
| First production user | Week 8 | Someone trusts it for real workloads |
| 500 stars | Month 3 | Community momentum |
| First company blog post mentioning LangSight | Month 4 | External validation |
| Hacker News front page | Month 4-6 | Lineage demo or security research post |

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| MCP doesn't become mainstream | Medium | Fatal | Ensure lineage/traces work for non-MCP tools too |
| Langfuse/Phoenix add MCP health natively | Medium | High | Move faster on fleet intelligence + lineage — harder to replicate |
| No one installs the CLI | Medium | High | Content marketing + GH Actions integration lower the bar |
| ClickHouse requirement scares small teams | High | Medium | Phase 1 is SQLite-only; Phase 4 targets single-binary |
| Solo maintainer burnout | High | Fatal | Optimize for external contributions (good-first-issues, CONTRIBUTING.md) |

---

## Resource Allocation

Assuming solo developer + AI coding assistant:

| Week | Focus | % time |
|---|---|---|
| 1 | SQLite backend for CLI-only mode, `langsight scan` command | 80% code, 20% content |
| 2 | GitHub Actions action, blog post #1 (MCP audit results) | 50% code, 50% content |
| 3 | OTLP exporter, Langfuse integration | 80% code, 20% docs |
| 4 | Blog post #2, Langfuse integration PR, community engagement | 30% code, 70% content |
| 5-6 | Lineage backend + dashboard | 90% code, 10% docs |
| 7 | Fleet inventory CLI, blog post #3 | 60% code, 40% content |
| 8 | OWASP checks 6-10, CVE lockfile resolution | 90% code, 10% docs |

Content is not optional. Without it, the code is invisible.

---

## One-Line Summary

**Stop trying to be Langfuse. Start being the `trivy` of MCP servers — then grow from there.**
