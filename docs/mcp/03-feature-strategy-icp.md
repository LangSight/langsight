# LangSight MCP — Feature Strategy & ICP

**Date**: 2026-03-26
**Status**: MCP focus confirmed. Agent monitoring is already built and working.

---

## Context

Agent monitoring is done. The greenfield opportunity is **MCP monitoring**. This document defines who we build for and what we prioritise.

---

## ICP — Three Tiers

### Primary: "Mark" — AI/ML Engineer at Series A–C startup (50–500 employees)

**Profile:**
- Deploying 2–10 agents to production using Claude/OpenAI + 3–20 MCP servers
- Already uses Langfuse or LangSmith for LLM traces
- Zero visibility into agent runtime behavior (loops, costs, MCP health)
- Gets paged when agents break, debugs by reading logs manually
- Budget-conscious — won't pay for Runlayer or Datadog LLM Observability

**Trigger moment**: Agent loops and burns $500 overnight, or customer-facing agent fails silently for 3 hours and nobody knows why.

**Why this ICP wins**: High pain, low existing tooling, OSS-first mindset, will champion the tool internally.

---

### Secondary: "Sarah" — Platform/DevOps Engineer at mid-market (500–5000)

**Profile:**
- Tasked with "make our AI agents production-ready"
- Manages shared MCP servers used by multiple teams
- Needs governance: cost budgets, security scanning, audit trails, RBAC
- Cares about schema drift, SLOs, multi-environment comparison

**Trigger moment**: Leadership asks "how much are we spending on agents?" and nobody can answer. Or: a team updates an MCP server schema and 3 downstream agents break.

---

### Tertiary: MCP Server Authors / OSS Maintainers

**Profile:**
- Building MCP servers published on GitHub, used by hundreds
- No visibility: is my server healthy? Are users hitting errors?
- Would embed LangSight health checks in CI/CD

**Trigger moment**: User files GitHub issue "your MCP server is broken" with no monitoring in place.

---

## Pain Points (ranked by "will someone install a new tool for this?")

| Rank | Pain Point | Who Feels It | Existing Solutions | Severity |
|---|---|---|---|---|
| 1 | **MCP server broke silently** — schema changed, server went down, agent produces garbage | Mark | OpenStatus (ping only), MCP Doctor (one-shot) | 10/10 |
| 2 | **"Why did my agent fail?"** — was it agent logic or MCP infrastructure? | Mark (2 AM) | Nobody correlates these two | 10/10 |
| 3 | **Schema drift breaks consumers** — MCP server updates params, agents break | Sarah | mcp-scan hash only, no consumer impact | 8/10 |
| 4 | **Security blind spots** — tool poisoning, prompt injection, no continuous watch | Security teams | Snyk/Cisco are one-shot only | 7/10 |
| 5 | **No cost attribution** — which MCP server/tool is burning money? | Sarah, finance | Moesif (commercial), manual parsing | 7/10 |

---

## Feature Strategy

### Tier 1 — Get Users In The Door (Adoption)

Features a user installs in 5 minutes and gets value from immediately. Zero Docker required.

| Feature | Why First | Differentiator |
|---|---|---|
| **`langsight init` fixed** — discovers all 10+ IDE configs | Nobody can use LangSight without finding their servers | We cover 10+ IDEs; Snyk Agent Scan is next-best |
| **`langsight mcp-health`** — instant health table | Most immediate value. "Show me what's broken right now." | Protocol-level check (not just HTTP ping) |
| **`langsight scorecard`** — A-F grade per server | Shareable. Engineers share screenshots. Viral artifact. | Nobody has this composite grade |
| **StreamableHTTP transport** | Can't monitor modern MCP servers without it | Table stakes going forward |

### Tier 2 — Keep Them (Retention + Stickiness)

Once installed, these make LangSight hard to remove.

| Feature | Why | Differentiator |
|---|---|---|
| **Continuous monitoring daemon** | "Set it and forget it" — health checked every 60s | OpenStatus does HTTP only; we do all transports + schema |
| **Schema drift structural diff** | "Parameter `limit` was removed from tool `query`" | mcp-scan only says "hash changed" — no detail |
| **Schema drift → consumer impact** | "3 agents use this tool, they may break" | Nobody does this |
| **Slack/webhook alerting** | Engineers live in Slack. Degradation → alert. | Already built in alert engine |

### Tier 3 — Expand Within Org (Land-and-Expand)

Mark installs it → Sarah's platform team adopts org-wide.

| Feature | Why | Differentiator |
|---|---|---|
| **Root cause correlation** | "Agent X failed because MCP server Y was DOWN" | Nobody correlates these two streams |
| **MCP SLOs** | "This server must have p99 < 200ms and 99.9% uptime" | Nobody does MCP SLOs |
| **Continuous security scanning** | OWASP + CVE + poisoning on a schedule, not one-shot | Snyk/Cisco are one-shot |
| **Multi-environment comparison** | Same server across dev/staging/prod | Nobody |

---

## What NOT to Build

| Don't Build | Why |
|---|---|
| MCP gateway/proxy | Runlayer ($11M), Portkey (OSS, 1T+ tokens/day), LiteLLM (41k stars) own this. Requires infra changes users resist. |
| LLM trace viewer | Langfuse owns this. We said complementary. |
| MCP server framework | FastMCP, Golf own this |
| Eval/testing framework | Braintrust, Arize own this |
| Agent framework | mcp-use has 9.5k stars and $6.3M |
| MCP marketplace/registry | Smithery, Glama own this |

---

## The Viral Loop

```
1. Engineer has 10+ MCP servers configured
         ↓
2. Googles "monitor MCP servers" or "MCP server health"
         ↓
3. Finds LangSight (SEO: blog posts, awesome-mcp-servers listing)
         ↓
4. pip install langsight && langsight init
         ↓
5. Sees all MCP servers discovered, health status, scorecard
         ↓
6. "Wow, 3 of my servers are degraded and I didn't know"
         ↓
7. Sets up continuous monitoring + Slack alerts
         ↓
8. Shares scorecard screenshot on Twitter/Discord
         ↓
9. Team adopts → discovers agent monitoring features too
```

---

## Distribution Channels

| Channel | Action | Priority |
|---|---|---|
| **awesome-mcp-servers** | Get listed under "Monitoring & Observability" | P0 — 30k+ stars |
| **MCP Discord / GitHub Discussions** | Share scorecards, help debug MCP issues | P0 |
| **Blog: "How to Monitor Your MCP Servers"** | SEO — nobody has written this definitive guide | P0 |
| **GitHub Action: `langsight/mcp-security-scan`** | Free CI/CD security scan — captures DevSecOps audience | P1 |
| **Blog: "MCP Security Risks Nobody's Talking About"** | Fear + education. Tool poisoning is real. | P1 |
| **Langfuse integration docs** | "Already use Langfuse? Add LangSight for MCP monitoring." | P1 |
