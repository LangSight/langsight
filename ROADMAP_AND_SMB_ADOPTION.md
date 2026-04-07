# LangSight — Roadmap & SMB Adoption

## Where we are today (v0.14.x)

**Working in production:**
- Session tracing with full parent-child span hierarchy (crew → task → agent → tool → LLM)
- CrewAI native event bus integration (19 handlers, zero-code instrumentation)
- Anthropic, OpenAI, Gemini SDK patches with token/cost/prompt capture
- MCP health checks, schema drift detection, circuit breakers
- OWASP MCP Top 10 security scanning
- Cost attribution by agent, session, model
- Projects + RBAC (invite-based, project-scoped API keys)
- Live SSE dashboard, anomaly detection, SLO tracking
- Alerts via Slack + generic webhook
- Multi-worker horizontal scaling via Redis

**Not yet built (commonly assumed from the name):**
- OpsGenie / PagerDuty native integrations (generic webhook works as fallback today)
- Bedrock SDK patch (LLM spans not captured for AWS Bedrock provider)
- 100-user load tested and benchmarked (see `load-tests/` for k6 scripts)

---

## SMB adoption blockers — what to fix first

| Blocker | Why it matters | Status |
|---|---|---|
| No "LangChain RAG + LangSight" quickstart | Most SMB AI teams use LangChain | Planned v0.15 |
| No upgrade path docs (v0.x → v0.y) | Operators fear upgrading without migration guide | Planned v0.15 |
| Feature matrix missing | Unclear which features need Postgres vs ClickHouse | Planned v0.15 |
| README overstated alerting (OpsGenie/PagerDuty) | Marked "v0.3" — now corrected to "Planned" | Fixed v0.14 |
| Empty ROADMAP | Evaluators couldn't see direction | Fixed v0.14 (this file) |
| Production defaults exposed ports + weak secrets | Partially fixed in v0.14 hardening | Ongoing |

---

## Near-term priorities

### v0.15 — Scale + guides
- [ ] ClickHouse materialized view for sessions list (constant query time at any volume)
- [ ] Health check results TTL/cleanup job (Postgres table grows unbounded today)
- [ ] Bedrock SDK patch
- [ ] SMB quickstart: "LangChain RAG in 10 minutes" guide
- [ ] Dashboard: agents/page.tsx + servers/page.tsx component split (900+/800+ lines today)
- [ ] Upgrade path documentation

### v0.16 — Auth + integrations
- [ ] API key scopes (read-only keys for dashboard-only access)
- [ ] OIDC/SSO (Okta, Google Workspace)
- [ ] OpsGenie native integration
- [ ] PagerDuty native integration
- [ ] Alert routing rules by project/server/agent

### v0.17 — Intelligence
- [ ] Smart budget forecasting (soft alert at 70% burn rate)
- [ ] Multi-tool correlation ("Postgres slow → Slack timeout → agent retry loop")
- [ ] Per-agent prevention rules UI (dashboard overrides without redeployment)
- [ ] Auto-remediation suggestions in `langsight investigate`

---

## Deployment sizing

| Users | Agent runs/day | Config |
|---|---|---|
| 1–10 | < 100 | 1 worker, no Redis |
| 10–50 | 100–1,000 | 1 worker, dual storage (Postgres + ClickHouse) |
| 50–200 | 1,000–10,000 | 4 workers + Redis, 4GB ClickHouse |
| 200+ | > 10,000 | Dedicated ClickHouse instance |

See [self-hosting/scaling.mdx](docs-site/self-hosting/scaling.mdx) for benchmarks and exact config.

---

## Contributing

Issues and PRs welcome. For large features, open an issue first.
License: Apache 2.0
