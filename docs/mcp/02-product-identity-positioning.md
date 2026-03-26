# LangSight — Product Identity & Positioning

**Date**: 2026-03-26
**Status**: Confirmed

---

## The One-Sentence Identity

> **LangSight is where engineers go when their AI agent breaks in production.**

---

## The Mental Model

Every developer space has a tool that owns "production broke, what happened":

| Space | Tool | What it tells you |
|---|---|---|
| Web apps | Sentry | "Your app threw an exception. Here's the stack trace." |
| Infrastructure | PagerDuty | "Your service went down. Here's the alert." |
| Databases | Datadog APM | "Your query is slow. Here's the execution plan." |
| **AI Agents** | **LangSight** | **"Your agent broke. Here's exactly why."** |

That slot is **unclaimed** in the AI agent space. Langfuse tells you what the LLM thought. LangSmith tells you what the prompt was. Nobody tells you why it actually failed in production — was it the agent logic, or was the MCP server broken?

---

## The Stack We Own

```
┌──────────────────────────────────────────┐
│  LLM Layer   → Langfuse, LangSmith        │  (thinking)
├──────────────────────────────────────────┤
│  Execution Layer → LangSight              │  (doing) ← OUR LANE
│  • Tools / MCP servers                   │
│  • Loops, budgets, circuit breakers      │
│  • Schema drift, health, security        │
└──────────────────────────────────────────┘
```

Langfuse watches the **brain**. LangSight watches the **hands**. Complementary, not competing.

---

## Brand Position

**LangSight = Production Reliability for AI Agents**

> **Detect. Prevent. Diagnose.**

- **When agents break** → find out why (root cause: MCP server down, schema drift, loop, budget hit)
- **Before agents break** → get alerted (server degraded, anomaly detected, security finding)
- **So agents don't break** → prevention layer (loop kill, budget enforcement, circuit breaker)

Not prompt optimization. Not evals. Not experimentation. **Production reliability.**

---

## One-Word Ownership

| Platform | Owns |
|---|---|
| Langfuse | **observability** |
| LangSight | **reliability** |

---

## MCP Layer Thesis

MCP servers are the infrastructure that AI agents run on. Infrastructure reliability is a solved problem everywhere **except AI agents**. LangSight solves it for the AI agent execution layer — specifically at the MCP/tool level where agents actually do work.

The correlation nobody else can make:
> "Agent X failed at 2:14 AM because MCP server postgres-tool had 3x latency spike due to schema drift on tool `query`."

---

## Two Entry Points, One Product

```
Entry Point 1: MCP-first (zero infra, 60 seconds to value)
──────────────────────────────────────────────────────────
pip install langsight
langsight init          ← discovers all MCP servers automatically
langsight mcp-health    ← instant health table, no Docker needed
langsight scorecard     ← shareable A-F grade per server

         ↓  "wow, this is useful, what else does it do?"

Entry Point 2: Full stack (agents + MCP, full correlation)
──────────────────────────────────────────────────────────
docker compose up
from langsight import watch; watch(agent)
         ← session traces + MCP health + root cause correlation
```

MCP monitoring is the **free sample**. Agent monitoring is the **upgrade**.

---

## Positioning vs Competitors

| vs | LangSight's edge |
|---|---|
| **Runlayer** ($11M) | OSS + free forever. No gateway/proxy required. Agent-level instrumentation. |
| **Snyk Agent Scan** | Continuous monitoring, not one-shot. Health + security combined. Schema drift with consumer impact. |
| **Cisco MCP Scanner** | Continuous vs one-shot. Plus health monitoring, cost tracking, loop detection. |
| **OpenStatus** | Deep MCP-specific checks (schema, tools, latency per tool), not just HTTP pings. |
| **MCP Doctor** | Continuous vs one-shot. Dashboard. Alerting. Historical trends. |
| **MCP Inspector** (Anthropic) | Inspector is for development/debugging. LangSight is for production monitoring. |
| **Datadog/Grafana/New Relic** | Free. OSS. MCP-specific (not generic APM with MCP bolted on). No vendor lock-in. |
| **Langfuse** | Complementary. They watch LLM reasoning. We watch tool/MCP execution. |

---

## What LangSight Is NOT

- Not a prompt optimization tool
- Not an eval/testing framework (Braintrust, Arize own this)
- Not an LLM trace viewer (Langfuse/LangSmith own this)
- Not an MCP gateway/proxy (Runlayer, Portkey own this — requires infra changes)
- Not an agent framework (mcp-use, LangGraph own this)
- Not a SaaS-first product — Apache 2.0, self-hosted, free forever
