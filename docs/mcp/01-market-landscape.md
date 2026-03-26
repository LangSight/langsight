# MCP Observability & Monitoring — Market Landscape

**Date**: 2026-03-26
**Status**: Comprehensive scan — 62 tools/companies across 8 categories

---

## Summary

| Category | # Tools | Key Players | LangSight Overlap |
|---|---|---|---|
| Enterprise Observability | 9 | Datadog, Grafana, New Relic, Sentry, IBM Instana | None — they're MCP producers, not MCP monitors |
| AI/LLM Observability | 10 | Langfuse, Arize, LangSmith, Braintrust, Laminar | None — they watch the brain, we watch the hands |
| MCP Gateways | 16 | Runlayer ($11M), Portkey, LiteLLM, AgentGateway | Runlayer is most direct competitor |
| MCP Security Scanning | 9 | Snyk Agent Scan, Cisco Scanner, Lasso, Operant AI | Our security scanning is continuous vs their one-shot |
| OSS Diagnostics | 5 | MCP Inspector, MCP Doctor, OpenStatus, MCP Hub | We're the only continuous + full-protocol monitor |
| OTEL Instrumentation | 5 | OpenLLMetry, SigNoz, FastMCP | Complementary — we consume OTEL, they produce it |
| Agent Frameworks | 3 | mcp-agent, mcp-use, VoltAgent | Not competing |
| API Analytics | 2 | Moesif, Stainless | Commercial only |

---

## Category 1: Enterprise Observability (MCP features bolted on)

These are traditional APM vendors that added MCP as an **output channel** — they let agents query their data via MCP. They are NOT monitoring MCP servers.

| Company | What they actually do | Type | Pricing |
|---|---|---|---|
| **Datadog** | Traces MCP client sessions (initialize, tools/list, call_tool) via ddtrace auto-instrumentation | Commercial | Paid (usage-based) |
| **Grafana Cloud** | OpenLIT auto-instruments MCP client; streams spans to Tempo + metrics to Mimir | Commercial + OSS | Free tier + paid |
| **IBM Instana** | Traceloop SDK inside MCP server process; OTLP spans with `mcp.method.name` attribute | Commercial | Enterprise |
| **New Relic** | Python agent v10.13.0+ patches core MCP primitives; `subcomponent` attribute for entity mapping | Commercial | Free tier + paid |
| **Dynatrace** | OSS MCP server exposing Dynatrace problems/logs/metrics to AI agents | Commercial + OSS | Enterprise |
| **Sentry** | MCP tool invocation tracing (Python + JS SDKs); `mcp_server_id` in span | Commercial + OSS | Free tier + paid |
| **Elastic** | MCP server for querying Elasticsearch observability data | Commercial + OSS | Free + paid |
| **Honeycomb** | Hosted MCP server (AWS Marketplace) exposing traces/metrics to agents in IDEs | Commercial | Paid |
| **Observe Inc** | AI-first MCP server with Knowledge Graph + OPAL query language for agents | Commercial | Enterprise |

**Key insight**: Every one of these is an MCP *producer* (they give agents access to their data). None of them *monitor* MCP server health, security, or schema drift.

### Key URLs
- Datadog: https://www.datadoghq.com/blog/mcp-client-monitoring/
- Grafana: https://grafana.com/docs/grafana-cloud/monitor-applications/ai-observability/mcp-observability/
- IBM Instana: https://www.ibm.com/docs/en/instana-observability/1.0.313?topic=observability-model-context-protocol-mcp
- New Relic: https://docs.newrelic.com/docs/agentic-ai/mcp/overview/
- Dynatrace: https://github.com/dynatrace-oss/dynatrace-mcp (99 stars)
- Sentry: https://docs.sentry.io/platforms/python/integrations/mcp/
- Honeycomb: https://www.infoq.com/news/2025/09/honeycomb-hosted-mcp/

---

## Category 2: AI/LLM Observability (with MCP integration)

These trace **LLM calls and agent logic** (the brain). They don't monitor MCP server health, security, or schema drift.

| Company | What they trace | License | Stars |
|---|---|---|---|
| **Langfuse** | LLM traces, prompt management; MCP server for IDE access to prompts/traces | Source-available + MIT MCP server | — |
| **Arize Phoenix** | Traces, spans, annotations, datasets via MCP | BSD-3-Clause | — |
| **Helicone** | Request logs, sessions, debugging, performance via MCP | Apache-2.0 | — |
| **LangSmith** | Agent traces, tool calls; MCP server logs every tool call to separate project | Commercial + OSS server | — |
| **Braintrust** | Agent traces, tool calls, latency, cost, quality in real-time | Commercial | — |
| **Opik (Comet)** | LLM traces, agent workflows, evaluations | OSS | 18.5k |
| **Pydantic Logfire** | Full-stack: LLM calls, MCP interactions, DB queries; Logfire MCP server | MIT | 4.1k |
| **Laminar** | Purpose-built agent tracing (OTEL-native, ClickHouse); YC S24, $3M seed | Apache-2.0 | 2.7k |
| **PostHog** | LLM analytics via MCP proxy; conversations, model performance, costs | Commercial + OSS | — |
| **W&B Weave** | Experiment tracking, agent tracing, OpenAI Agents SDK + MCP integration | Commercial | — |

### Key URLs
- Langfuse MCP: https://github.com/langfuse/mcp-server-langfuse
- Arize Phoenix: https://github.com/Arize-ai/phoenix/tree/main/js/packages/phoenix-mcp
- Helicone: https://docs.helicone.ai/integrations/tools/mcp
- LangSmith: https://github.com/langchain-ai/langsmith-mcp-server
- Opik: https://github.com/comet-ml/opik
- Logfire: https://github.com/pydantic/logfire
- Laminar: https://github.com/lmnr-ai/lmnr

---

## Category 3: MCP Gateways (monitoring via proxy)

The dominant delivery vehicle for MCP monitoring — all traffic flows through a proxy. Requires infrastructure changes that teams resist.

| Company | Key Features | License | Funding/Stars |
|---|---|---|---|
| **Runlayer** | Unified observability dashboards, PII/token masking, threat detection, approval workflows | Commercial | **$11M seed** (Khosla, Felicis) |
| **Portkey** | Logs every MCP tool invocation + LLM calls in same trace; 1T+ tokens/day | **OSS** (fully open-sourced March 2026) | — |
| **Lunar.dev MCPX** | Prometheus-compatible metrics (`tool_call_duration_ms`), audit logs, RBAC | Commercial | — |
| **Kong AI Gateway** | MCP-specific Prometheus metrics, policy enforcement (v3.12+, Oct 2025) | Commercial + OSS | — |
| **Composio** | 500+ integrations, OTEL, rate limiting, RBAC, zero data retention | Commercial | — |
| **TrueFoundry** | MCP registry, central auth, RBAC, guardrails, rich observability | Commercial | — |
| **Speakeasy Gram** | Full request/response logging, anomaly detection, OAuth 2.1 + DCR | Commercial + OSS | $29/mo+ |
| **LiteLLM** | MCP Gateway, cost tracking, guardrails, load balancing, per-key access control | **MIT** | 41k stars |
| **IBM ContextForge** | Federates MCP + A2A + REST/gRPC; OTEL tracing, Prometheus metrics, Admin UI | **OSS** | 3.5k stars |
| **Microsoft MCP Gateway** | Reverse proxy for MCP in K8s; session-aware routing, authorization | **MIT** | 547 stars |
| **AgentGateway** (Linux Foundation) | A2A + MCP gateway; security, observability, governance; written in Rust | **Apache-2.0** | 2.2k stars |
| **Cloudflare MCP Portals** | Zero Trust auth, access logging per tool request | Commercial | — |
| **Hypr MCP Gateway** | Audit logging, prompt monitoring, MCP firewall, OAuth2 + DCR | **MIT** | 90 stars |
| **Golf** (YC X25) | MCP Gateway with per-tool/team/data-source policies, audit trails | OSS framework | YC |
| **Metorial** (YC F25) | Serverless MCP runtime, sub-second cold starts, built-in security + monitoring | Commercial | YC |
| **Arcade AI** | 500+ tools, per-user OAuth, comprehensive tool interaction logging | Commercial | — |

### Key URLs
- Runlayer: https://runlayer.com/
- Portkey: https://github.com/portkey-ai/gateway
- LiteLLM: https://github.com/BerriAI/litellm
- IBM ContextForge: https://github.com/IBM/mcp-context-forge
- Microsoft MCP Gateway: https://github.com/microsoft/mcp-gateway
- AgentGateway: https://github.com/agentgateway/agentgateway
- Hypr: https://github.com/hyprmcp/mcp-gateway

---

## Category 4: MCP Security Scanning

| Tool | What it scans | Approach | License | Stars/Funding |
|---|---|---|---|---|
| **Snyk Agent Scan** (ex-Invariant mcp-scan) | 15+ risks: prompt injection, tool poisoning, shadowing, rug pulls, toxic flows | Hybrid: multi-LLM judges + deterministic rules + SHA256 hash drift | **Apache-2.0** | 2,000 stars |
| **Invariant Guardrails** | Runtime guardrails; policy-based rules; prompt injection, secrets, PII, data flows | Policy DSL with `->` flow operators; Monitor class for incremental state | **Apache-2.0** | 401 stars |
| **Cisco MCP Scanner** | Tool descriptions + server source code; 10 YARA rule files + LLM-as-judge | YARA (signatures) + LLM judge (semantic) + Cisco API (threat intel) | **Apache-2.0** | 859 stars |
| **Lasso Security Gateway** | Prompt injection, credential theft, tool poisoning; reputation scoring | Regex patterns + Presidio NLP + Lasso API; npm/Smithery/GitHub reputation | **MIT** | 361 stars, $25.6M |
| **Operant AI** | Runtime defense; discovered "Shadow Escape" zero-click exploit | Commercial | $13.5M (Felicis) |
| **MCP Manager** (Usercentrics) | PII detection, connection monitoring, configurable alerts; 20+ metadata fields | Commercial | — |
| **MintMCP** | Tool call monitoring; SOC 2 Type II | Commercial | — |
| **StackHawk** | DAST scanning (SQL injection, auth bypasses) at runtime | Commercial | — |
| **mcp-watch** | Credential exposure, tool poisoning, ANSI injection, protocol violations | **OSS** | Early |

**The gap LangSight fills**: All these tools scan **once** at install time. Nobody runs continuous security monitoring — detecting tool description mutations (rug pulls) between sessions, flagging new servers added to configs, or watching for toxic flows across sessions.

### Key URLs
- Snyk Agent Scan: https://github.com/snyk/agent-scan
- Invariant Guardrails: https://github.com/invariantlabs-ai/invariant
- Cisco Scanner: https://github.com/cisco-ai-defense/mcp-scanner
- Lasso Gateway: https://github.com/lasso-security/mcp-gateway
- Operant AI: https://www.operant.ai/solutions/mcp-gateway

---

## Category 5: OSS Diagnostics & Monitoring Tools

| Tool | Purpose | Approach | License | Stars |
|---|---|---|---|---|
| **MCP Inspector** (Anthropic official) | Interactive browser-based testing/debugging; explores tools, prompts, resources | Manual — point-and-click, not continuous | **MIT** | 9,200 |
| **MCP Doctor** (destiLabs) | Diagnostic health checks; tool description quality, schema analysis, security audit | One-shot CLI; rule-based, no LLM | **MIT** | — |
| **MCP Hub** (ravitemer) | Centralized server manager; SSE events for status changes, capability updates | Live connection manager; in-memory only, no persistence | **MIT** | 465 |
| **OpenStatus** | Uptime monitoring via JSON-RPC `ping`; multi-region checks on schedule | Synthetic HTTP/SSE ping; Tinybird (ClickHouse) history | **AGPL-3.0** | 8,500 |
| **mcp-monitor** | System metrics exposed via MCP interface | Exposes system data to LLMs | OSS | Early |

**The gap LangSight fills**:
- OpenStatus: HTTP/SSE ping only — no stdio transport, no schema tracking, no security
- MCP Doctor: one-shot — no daemon, no history, no alerting
- MCP Hub: live state only — no persistence, no trend analysis, no security

### Key URLs
- MCP Inspector: https://github.com/modelcontextprotocol/inspector
- MCP Doctor: https://github.com/destilabs/mcp-doctor
- MCP Hub: https://github.com/ravitemer/mcp-hub
- OpenStatus: https://github.com/openstatusHQ/openstatus

---

## Category 6: OTEL-Based MCP Instrumentation

| Tool | Purpose | License | Stars |
|---|---|---|---|
| **Traceloop OpenLLMetry** | Standard OTEL instrumentations for LLM + MCP; auto-patches prompts, tool calls | **Apache-2.0** | 7,000 |
| **opentelemetry-instrumentation-mcp** (PyPI) | Python library for tracing MCP SDK workflows | **Apache-2.0** | — |
| **FastMCP** (native OTEL) | Built-in OTEL tracing for tool/prompt/resource/template operations | OSS | — |
| **SigNoz** | Full OTEL platform + MCP server for agents to query logs/metrics/traces | **AGPL-3.0** | 26,300 |
| **Maple** | OTEL-native traces + MCP server for auto-diagnosis; columnar engine | OSS | Early |

---

## Category 7: Agent Frameworks with Built-in Observability

| Tool | Features | License | Stars |
|---|---|---|---|
| **mcp-agent** (LastMile AI) | Token tracking, stream watchers, lifecycle management; implements Anthropic agent patterns | **Apache-2.0** | 8,100 |
| **mcp-use / Manufact** (YC S25, $6.3M) | Visual debugger, browser-based JSON-RPC traffic viewer; Manufact Cloud adds production monitoring | OSS + Cloud | 9,500 |
| **VoltAgent** | VoltOps Console: observability, automation, deployment, evals, guardrails | OSS + Cloud | — |

---

## Category 8: API Analytics with MCP

| Tool | Features | Approach | Type |
|---|---|---|---|
| **Moesif** | JSON-RPC payload visibility; per-tool latency (P90+), failure rates, user attribution, cost per task | Middleware layer; parses `method` field to attribute metrics to specific tool | Commercial |
| **Stainless** | Real-time MCP monitoring; structured log forwarding to Splunk/Azure Monitor | Log aggregation + forwarding | Commercial |

---

## Funding Leaderboard (MCP-specific startups, 2025–2026)

| Company | Funding | Investors | Focus |
|---|---|---|---|
| **Lasso Security** | $25.6M total | Safar Partners, Rhapsody | MCP security gateway |
| **Operant AI** | $13.5M | Felicis, SineWave | Runtime MCP defense |
| **Runlayer** | $11M seed | Khosla Ventures, Felicis | MCP security + observability gateway |
| **Manufact (mcp-use)** | $6.3M | YC S25 | MCP framework + cloud |
| **Laminar** | $3M seed | YC S24 | Agent observability |
| **Golf** | YC X25 (undisclosed) | Y Combinator | MCP governance gateway |
| **Metorial** | YC F25 (undisclosed) | Y Combinator | Serverless MCP runtime |

**Total funding in MCP-specific startups**: $59M+ in ~12 months. Market is validated.

---

## LangSight Gap Analysis

### What nobody does in a single OSS tool

| Capability | Closest competitor | OSS? | LangSight status |
|---|---|---|---|
| MCP health monitoring (continuous, all transports) | OpenStatus (HTTP/SSE ping only) | Partial | Built (stdio + SSE), needs daemon + StreamableHTTP |
| MCP schema drift detection | mcp-scan (hash only, one-shot) | Yes but shallow | Built (hash), needs structural diff |
| Schema drift → consumer impact | Nobody | No | Not built — unique |
| MCP security scanning (continuous) | Snyk, Cisco (one-shot only) | Yes but one-shot | Built as one-shot, needs continuous |
| Agent loop detection + budget enforcement | Nobody OSS | No | Built |
| Root cause correlation (agent failure ↔ MCP health) | Nobody | No | Not built — unique |
| A-F composite health scorecard | Nobody | No | Not built — unique |
| All above combined | Runlayer (commercial, $11M) | **No** | LangSight is the OSS answer |

### Biggest Threat
**Runlayer** — $11M funded, MCP co-creator (David Soria Parra) as advisor, 8 unicorn customers (Gusto, dbt Labs, Instacart, Opendoor). Commercial-only. LangSight owns the OSS lane.

### Complementary Tools (not competitors)
- **Langfuse**: watches the brain (LLM reasoning). LangSight watches the hands (MCP/tool execution).
- **Snyk Agent Scan / Cisco Scanner**: one-shot security scans. LangSight: continuous monitoring.
- **OpenStatus**: uptime pings. LangSight: deep health (schema, tools, latency trends, security).
