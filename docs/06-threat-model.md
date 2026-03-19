# LangSight Threat Model

> **Version**: 1.0.0
> **Date**: 2026-03-19
> **Status**: Active
> **Authors**: Engineering / Security
> **Scope**: Self-hosted deployment (Docker Compose). SaaS deployment threat model is out of scope until SaaS phase begins.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Trust Boundaries](#2-trust-boundaries)
3. [Attack Surface](#3-attack-surface)
4. [Data Classification](#4-data-classification)
5. [Threat Scenarios](#5-threat-scenarios)
6. [Deployment Topology](#6-deployment-topology)
7. [Known Gaps](#7-known-gaps)
8. [Vulnerability Disclosure Policy](#8-vulnerability-disclosure-policy)

---

## 1. System Overview

LangSight is a self-hosted AI agent observability platform. It ingests OTEL spans from instrumented agents, stores them in ClickHouse, and exposes a FastAPI REST API and Next.js dashboard for querying traces, running security scans, replaying sessions, and monitoring MCP server health.

### Components

```
+---------------------+      +---------------------+      +---------------------+
|  AI Agent / SDK     |      |   Human Operator    |      |   CI / Automation   |
|  (instrumented app) |      |   (dashboard user)  |      |   (API consumer)    |
+----------+----------+      +----------+----------+      +----------+----------+
           |                            |                            |
           | OTLP (4317/4318)           | HTTPS (3003)               | HTTPS (8000)
           | or REST spans (8000)       |                            |
           v                            v                            v
+----------+----------------------------+----------------------------+----------+
|                           Docker Host (exposed ports)                         |
|                                                                               |
|   +-------------------+        +-----------------------------------+          |
|   |  OTEL Collector   |        |  Next.js Dashboard  (port 3003)   |          |
|   |  (4317 gRPC)      |        |  NextAuth session auth            |          |
|   |  (4318 HTTP)      |        +----------------+------------------+          |
|   +--------+----------+                         |                             |
|            |                                    | API calls with session key  |
|            | OTLP export                        v                             |
|            v                    +---------------+------------------+          |
|   +--------+--------------------+   FastAPI REST API  (port 8000)  |          |
|   |        X-API-Key required   |   RBAC: admin / viewer           |          |
|   +---+-------------------+-----+--+------------------------------++          |
|       |                   |        |                               |           |
|       | asyncpg           | asyncpg| ClickHouse HTTP               |           |
|       v                   v        v                               |           |
|  +----+----+        +-----+---+  +-+------------+                 |           |
|  | SQLite  |        |Postgres |  | ClickHouse   |                 |           |
|  | (local) |        |(Docker  |  | (Docker      |                 |           |
|  |         |        | network)|  |  network)    |                 |           |
|  +---------+        +---------+  +--------------+                 |           |
|                                                                               |
|   +-------------------------------------------------------------------+       |
|   |  MCP Servers  (stdio / SSE / StreamableHTTP — external processes) |       |
|   |  Connected by CLI health checker and Replay engine (admin only)   |       |
|   +-------------------------------------------------------------------+       |
+-------------------------------------------------------------------------------+
```

---

## 2. Trust Boundaries

Five distinct trust boundaries exist in a standard deployment.

### Boundary 1: Internet → LangSight exposed ports

| Port | Service | Auth required | Should be internet-exposed |
|------|---------|---------------|---------------------------|
| 8000 | FastAPI REST API | Yes — `X-API-Key` header | Yes (behind reverse proxy + TLS) |
| 3003 | Next.js dashboard | Yes — NextAuth credentials | Yes (behind reverse proxy + TLS) |
| 4317 | OTEL Collector gRPC | No (see Known Gaps) | Restricted — firewall to agent hosts only |
| 4318 | OTEL Collector HTTP | No (see Known Gaps) | Restricted — firewall to agent hosts only |
| 8123 | ClickHouse HTTP | Internal only | Never |
| 9000 | ClickHouse native | Internal only | Never |
| 5432 | PostgreSQL | Internal only | Never |
| 5433 | PostgreSQL (alt) | Internal only | Never |

### Boundary 2: Dashboard → API

The Next.js dashboard communicates with the FastAPI API using an API key stored as `LANGSIGHT_API_KEY` in the dashboard's environment. Requests carry `X-API-Key` in every server-side fetch. The dashboard session (NextAuth) determines whether the human user is authenticated to the dashboard UI; it does not bypass API authentication.

### Boundary 3: API → Databases

ClickHouse and PostgreSQL are on the internal Docker network only. The API connects via `asyncpg` (Postgres) and the ClickHouse HTTP client using credentials from environment variables (`LANGSIGHT_POSTGRES_URL`, `LANGSIGHT_CLICKHOUSE_URL`). No database port is bound to the host by default.

### Boundary 4: API / CLI → MCP Servers

Two code paths open connections to MCP servers:

- `POST /api/security/scan` — admin only; connects to the target MCP server to retrieve its tool list for security analysis.
- `POST /api/agents/sessions/{id}/replay` — admin only; re-executes stored `input_args` against live MCP servers.
- `langsight mcp-health` CLI — runs on the operator's local machine; connects to MCP servers using credentials from `.langsight.yaml`.

MCP servers are considered **semi-trusted**: they are configured by the operator, but their tool descriptions and responses are treated as potentially untrusted input (poisoning detection exists for this reason).

### Boundary 5: CLI user → Local configuration

The CLI reads `.langsight.yaml` from the working directory or `~/.langsight.yaml`. This file may contain MCP server commands and environment variable references. It is never transmitted to the API and is not stored in any database.

---

## 3. Attack Surface

### 3.1 REST API endpoints

| Endpoint | Method | Auth | Role | Rate limit | What it can access |
|----------|--------|------|------|-----------|-------------------|
| `/api/traces/spans` | POST | API key | viewer+ | 200/min | Writes spans to ClickHouse |
| `/api/traces/otlp` | POST | API key | viewer+ | 60/min | Writes OTLP spans to ClickHouse |
| `/api/agents/sessions` | GET | API key | viewer+ | none | Reads ClickHouse session data |
| `/api/agents/sessions/{id}` | GET | API key | viewer+ | none | Reads single session trace |
| `/api/agents/sessions/{id}/replay` | POST | API key | **admin** | none | Executes tool calls against live MCP servers |
| `/api/agents/sessions/compare` | GET | API key | viewer+ | none | Reads two session traces |
| `/api/security/scan` | POST | API key | **admin** | none | Opens MCP server connections |
| `/api/slos` | POST/DELETE | API key | **admin** | none | Writes SLO definitions to Postgres/SQLite |
| `/api/reliability/anomalies` | GET | API key | viewer+ | none | Reads ClickHouse aggregates |
| `/api/costs` | GET | API key | viewer+ | none | Reads ClickHouse cost aggregates |
| `/api/status` | GET | none | public | none | Returns `{"status": "ok"}` |
| `/api/auth/keys` | POST/DELETE | API key | **admin** | none | Creates/revokes API keys |

### 3.2 Dashboard

| Surface | Auth mechanism | Risk |
|---------|---------------|------|
| `GET /login` | NextAuth credentials form | Brute-force (no lockout — see Known Gaps) |
| NextAuth session cookie | `AUTH_SECRET` env var (JWT) | JWT forgery if `AUTH_SECRET` is weak |
| Dashboard → API proxy | `LANGSIGHT_API_KEY` env var | Key exposure if dashboard server is compromised |

### 3.3 OTEL Collector

| Port | Protocol | Auth | Risk |
|------|---------|------|------|
| 4317 | gRPC (OTLP) | None | Unauthenticated span injection (mitigated by network controls only) |
| 4318 | HTTP (OTLP) | None | Same as above |

Spans received by the OTEL Collector are forwarded to the API's `/api/traces/otlp` endpoint, which does require authentication. However, a direct connection to the Collector bypasses API auth entirely at the Collector level.

### 3.4 CLI tool

The CLI runs on the operator's local machine and connects directly to MCP servers defined in `.langsight.yaml`. The CLI is considered a trusted local tool — it has the same access as the operating system user running it. No network exposure.

---

## 4. Data Classification

| Category | Examples | Storage location | Retention | Sensitivity |
|----------|----------|-----------------|-----------|-------------|
| Tool call metadata | server name, tool name, timing, status, span IDs | ClickHouse `mcp_tool_calls` | 90 days TTL | Low |
| Tool payloads (opt-in) | `input_args`, `output_result` | ClickHouse `mcp_tool_calls` | 90 days TTL | **High** — may contain PII |
| LLM prompts/completions (opt-in) | `llm_input`, `llm_output` | ClickHouse `mcp_tool_calls` | 90 days TTL | **High** — may contain PII or proprietary content |
| MCP server configs | server names, commands, env var references | `.langsight.yaml` only, not stored in DB | Config file lifetime | Medium |
| API keys (raw) | `ls_live_...` prefixed keys | Never stored — shown once at creation | N/A | Critical |
| API keys (hashed) | SHA-256 hashes | SQLite `api_keys` / Postgres `api_keys` | Until revoked | Medium |
| Health check results | latency, status, schema hashes | ClickHouse `mcp_health_checks` | 90 days TTL | Low |
| Audit log entries | actor key prefix, action, timestamp, source IP | SQLite/Postgres `audit_log` | 1 year | Medium |
| Session metadata | agent name, session ID, duration, error count | ClickHouse `mcp_tool_calls` aggregated | 90 days TTL | Low |
| SLO definitions | metric type, target value, agent name | SQLite/Postgres `agent_slos` | Until deleted | Low |

### PII risk note

Tool payloads (`input_args`, `output_result`) and LLM content (`llm_input`, `llm_output`) are **not captured by default**. They are stored only when `record_payloads: true` is set in `.langsight.yaml`. If your agents process user data, these fields may contain names, email addresses, query content, or other PII.

**Mitigation**: set `redact_payloads: true` in `.langsight.yaml` to prevent payload storage. Note: this is a global flag — per-server granularity is a known gap (see Section 7).

```yaml
# .langsight.yaml
record_payloads: true       # opt-in to capturing tool inputs/outputs
redact_payloads: true       # override: do not store them even if record_payloads=true
```

---

## 5. Threat Scenarios

### T-01: Unauthenticated span ingestion (Denial of write / data pollution)

**Attacker goal**: Flood `/api/traces/spans` with junk spans to exhaust ClickHouse storage or corrupt trace data.

**Preconditions**: Attacker can reach port 8000.

**Attack path**:
```
attacker → POST /api/traces/spans (no key or stolen viewer key) → ClickHouse write
```

**Impact**: Storage exhaustion, corrupted dashboards, legitimate traces lost.

**Mitigations**:
- `X-API-Key` required — requests without a valid key receive `403`.
- Rate limit: 200 requests/min per key on `/api/traces/spans`, 60/min on `/api/traces/otlp`.
- ClickHouse TTL (90 days) caps unbounded growth.

**Residual risk**: Low. A stolen viewer key could still inject spans at the rate limit. Key rotation (admin action) revokes access.

---

### T-02: Privilege escalation via viewer key (Unauthorized admin action)

**Attacker goal**: Use a viewer-role API key to trigger a security scan or replay session.

**Attack path**:
```
attacker (viewer key) → POST /api/security/scan → 403 Forbidden
```

**Impact**: If RBAC were absent: attacker could trigger MCP server connections or replay tool calls against production infrastructure.

**Mitigations**:
- `require_admin` FastAPI dependency on all write/action endpoints.
- Role is stored alongside the key hash in `api_keys` table; checked on every request.
- Viewer keys cannot be elevated — role is set at creation time by an admin.

**Residual risk**: Negligible while RBAC is enforced consistently.

---

### T-03: Dashboard credential brute force

**Attacker goal**: Guess the admin password to gain dashboard access.

**Attack path**:
```
attacker → POST /login (NextAuth credentials) → repeat with password list
```

**Impact**: Full dashboard access; ability to view all traces, trigger replays, manage API keys.

**Mitigations**:
- `LANGSIGHT_ADMIN_EMAIL` and `LANGSIGHT_ADMIN_PASSWORD` are set via environment variables — no default credentials ship.
- Recommend strong password (document in `README.md` and `.env.example`).
- NextAuth session uses signed JWT with `AUTH_SECRET`.

**Known gap**: No account lockout or login rate limiting on the dashboard `POST /api/auth/callback/credentials` route. See Section 7.

**Residual risk**: Medium without network controls. Mitigate by placing dashboard behind a VPN or IP allowlist at the reverse proxy layer.

---

### T-04: Malicious session replay against production MCP servers

**Attacker goal**: Inject crafted session data, then trigger replay to execute arbitrary tool calls against production MCP servers.

**Attack path**:
```
attacker (admin key) → POST /api/traces/spans (inject spans with malicious input_args)
                     → POST /api/agents/sessions/{id}/replay
                     → ReplayEngine executes malicious input_args against MCP servers
```

**Impact**: Arbitrary tool execution on MCP servers — could read/write data, trigger destructive operations depending on what tools the MCP server exposes.

**Mitigations**:
- Replay requires admin key — a stolen viewer key cannot trigger replay.
- `ReplayEngine` only re-runs stored `input_args` for spans with `span_type="tool_call"` — it does not accept arbitrary input at replay time.
- MCP server must exist in the operator's `.langsight.yaml` config — replay cannot target arbitrary servers.
- Timeout caps: `timeout_per_call` (default 10s) and `total_timeout` (default 60s) limit blast radius.

**Residual risk**: Medium. A compromised admin key combined with pre-injected spans could execute tool calls. Guard admin keys strictly. Consider adding an explicit replay allowlist per MCP server.

---

### T-05: Credential leakage via structured logs

**Attacker goal**: Extract API keys, passwords, or tokens from application logs.

**Attack path**:
```
attacker reads log aggregator (Datadog, CloudWatch, etc.) → finds raw API key in log line
```

**Impact**: Key compromise; attacker gains API access at the leaked key's role.

**Mitigations**:
- Audit log entries store `key_prefix` (first 8 characters) only — never the full raw key.
- Raw keys are shown exactly once (at creation) and never stored or re-displayed.
- `LANGSIGHT_ADMIN_PASSWORD` is never passed to any logging call.
- `structlog` context processors do not log request headers by default.

**Residual risk**: Low. Audit all new log statements that touch auth context before merging.

---

### T-06: Database exposure to the internet

**Attacker goal**: Connect directly to ClickHouse (port 8123/9000) or PostgreSQL (port 5432) from the internet.

**Attack path**:
```
attacker → TCP connect to host:8123 → ClickHouse HTTP interface → arbitrary queries
```

**Impact**: Full read/write access to all trace data, API keys (hashed), SLO definitions.

**Mitigations**:
- `docker-compose.yml` uses `expose` (not `ports`) for ClickHouse and Postgres — ports are only reachable within the Docker bridge network.
- The API container is the only service that connects to the databases.
- No host-level port binding for DB ports.

**Verification**:
```bash
# Should show nothing for these ports from outside the Docker network
nmap -p 8123,9000,5432,5433 <host>
```

**Residual risk**: Low in standard Docker Compose deployment. Risk increases if an operator manually adds `ports:` mappings or uses `--network=host`.

---

### T-07: OTEL Collector abuse (unauthenticated span injection)

**Attacker goal**: Send arbitrary OTLP spans directly to the OTEL Collector on port 4317/4318, bypassing API authentication.

**Attack path**:
```
attacker → gRPC OTLP to port 4317 → OTEL Collector accepts
         → Collector forwards to API /api/traces/otlp → stored in ClickHouse
```

**Impact**: Data pollution, storage exhaustion, false traces in dashboards.

**Mitigations**:
- OTEL Collector ports should not be bound to `0.0.0.0` in production — restrict to loopback or Docker network.
- Place a firewall rule allowing only known agent hosts to reach ports 4317/4318.
- The Collector's pipeline can be configured with a `filter` processor to drop spans from unknown service names.

**Known gap**: The OTEL Collector ships with no authentication configuration. This is mitigated by network controls only. See Section 7.

**Residual risk**: Medium if ports 4317/4318 are internet-reachable. Mitigate with network-layer controls.

---

### T-08: Weak AUTH_SECRET enables JWT session forgery

**Attacker goal**: Forge a valid NextAuth session token by cracking or guessing a weak `AUTH_SECRET`.

**Attack path**:
```
attacker observes NextAuth session cookie → brute-forces or guesses AUTH_SECRET
          → forges valid session token → bypasses dashboard login
```

**Impact**: Full dashboard access without valid credentials.

**Mitigations**:
- `AUTH_SECRET` is declared with `:?` syntax in `docker-compose.yml` — the container fails to start if the variable is unset.
- Documentation and `.env.example` recommend generating with `openssl rand -base64 32` (256-bit entropy).
- A guessable value (e.g. `"secret"`, `"changeme"`) provides no protection.

**Residual risk**: Low if operator follows documented setup. Zero protection if operator uses a weak value.

---

### T-09: MCP server tool description poisoning

**Attacker goal**: Modify a registered MCP server's tool descriptions to inject instructions that manipulate the observing agent.

**Attack path**:
```
attacker modifies MCP server (supply chain or runtime tampering)
         → LangSight health check reads altered tool descriptions
         → Poisoning detector fires alert
         → If undetected: agent consuming the MCP server acts on injected instructions
```

**Impact**: Indirect prompt injection into agent workflows; potential data exfiltration or unauthorized actions.

**Mitigations**:
- `poisoning_detector.py` compares current tool descriptions against baseline schema snapshots stored in SQLite/Postgres.
- Schema hash mismatch triggers a `SCHEMA_DRIFT` alert.
- Security scanner (`owasp_checker.py`) inspects tool descriptions for known injection patterns.

**Residual risk**: Medium. Detection is reactive — the poisoning must be observed during a health check cycle before the alert fires.

---

### T-10: Insecure direct object reference on session replay

**Attacker goal**: Replay a session belonging to another tenant (in future multi-tenant deployment) or a session not accessible to the requester.

**Attack path**:
```
attacker (valid admin key) → POST /api/agents/sessions/{arbitrary_id}/replay
         → ReplayEngine executes tool calls from session they should not access
```

**Impact**: Cross-tenant data access or unauthorized tool execution.

**Mitigations (current)**: In the current single-tenant deployment, all sessions belong to the same operator. Admin key requirement limits access.

**Future gap**: Multi-tenant mode will require tenant-scoped session access control. This must be addressed before any SaaS deployment.

---

## 6. Deployment Topology

### Recommended production deployment

```
                        Internet
                            |
                   [Firewall / Security Group]
                   Allow: 443 (HTTPS only)
                   Deny: 4317, 4318, 8123, 9000, 5432, 5433, 8000, 3003 (direct)
                            |
                   [Reverse Proxy: nginx or Caddy]
                   TLS termination (Let's Encrypt or managed cert)
                   /         → proxy to localhost:3003 (dashboard)
                   /api/*    → proxy to localhost:8000 (API)
                            |
              +-------------+--------------+
              |                            |
     [Next.js Dashboard]          [FastAPI REST API]
         port 3003                    port 8000
              |                            |
              |          [Internal Docker network: langsight_net]
              |             |              |              |
        [PostgreSQL]  [ClickHouse]  [OTEL Collector]  [SQLite volume]
           5432/5433   8123/9000    4317/4318 (internal only)
```

### Firewall rules summary

| Source | Destination | Port | Action |
|--------|------------|------|--------|
| Internet | Reverse proxy | 443 | Allow |
| Internet | Reverse proxy | 80 | Allow (redirect to 443) |
| Internet | Any Docker service directly | Any | Deny |
| Agent hosts (known IPs) | OTEL Collector | 4317, 4318 | Allow (if needed externally) |
| Reverse proxy | Dashboard | 3003 | Allow (localhost only) |
| Reverse proxy | API | 8000 | Allow (localhost only) |
| API container | ClickHouse | 8123 | Allow (Docker network only) |
| API container | PostgreSQL | 5432 | Allow (Docker network only) |

### TLS requirements

- TLS termination at the reverse proxy — do not expose plain HTTP to the internet.
- Minimum TLS 1.2; prefer TLS 1.3.
- API key and session tokens transmitted only over TLS.
- Internal Docker network traffic (API → DB) is not TLS-encrypted — mitigated by network isolation (see Known Gaps).

### Environment variables — required before first start

```bash
# Generate these before deployment — do not use defaults
LANGSIGHT_POSTGRES_PASSWORD=$(openssl rand -base64 24)
AUTH_SECRET=$(openssl rand -base64 32)
LANGSIGHT_API_KEY=$(openssl rand -hex 32)

# Set these to your values
LANGSIGHT_ADMIN_EMAIL=your-admin@example.com
LANGSIGHT_ADMIN_PASSWORD=<strong-password>
```

---

## 7. Known Gaps

These are honest, documented security gaps. Each has a mitigation note and a tracking reference.

| # | Gap | Severity | Mitigation available | Tracking |
|---|-----|----------|---------------------|---------|
| G-01 | No dashboard login rate limiting or account lockout | Medium | Place behind VPN or IP allowlist at reverse proxy | S.3 follow-up |
| G-02 | OTEL Collector has no authentication | Medium | Network controls only — restrict ports 4317/4318 to known agent IPs via firewall | Post-S.10 |
| G-03 | No TLS between API and databases (internal Docker network) | Low | Docker bridge network isolation; do not bind DB ports to host | Post-S.10 |
| G-04 | No API key rotation mechanism | Low | Manual: delete old key, create new key via `/api/auth/keys` | Future release |
| G-05 | `redact_payloads` is global — no per-server payload redaction | Low | Set `redact_payloads: true` globally if any server handles PII | Future release |
| G-06 | Multi-tenant isolation not implemented | N/A (single-tenant) | Current single-tenant model is safe; must be addressed before SaaS | SaaS phase |
| G-07 | No CSRF protection on dashboard API routes | Low | NextAuth session cookies use `SameSite=Lax` by default | Future release |
| G-08 | Replay does not validate `input_args` schema against current MCP server schema | Medium | Only admin keys can trigger replay; MCP server must be in config | Post-S.10 |

---

## 8. Vulnerability Disclosure Policy

### Reporting

Security vulnerabilities should be reported through one of the following channels:

- **GitHub Private Security Advisory**: [github.com/langsight/langsight/security/advisories/new](https://github.com/langsight/langsight/security/advisories/new) (preferred)
- **Email**: security@langsight.io — PGP key available on request

Please do not open a public GitHub issue for security vulnerabilities before a patch is available.

### What to include in a report

- Description of the vulnerability and affected component
- Steps to reproduce (proof-of-concept if available)
- Potential impact assessment
- Your contact details for follow-up

### Response commitments

| Milestone | Target time |
|-----------|-------------|
| Acknowledge receipt | 48 hours |
| Initial triage and severity assessment | 5 business days |
| Patch for Critical / High severity | 14 days from triage |
| Patch for Medium severity | 30 days from triage |
| Patch for Low severity | Next scheduled release |
| Public disclosure | After patch is released and users have had reasonable time to update |

### Scope

In scope:
- `src/langsight/` — Python API, CLI, health checker, security scanner
- `dashboard/` — Next.js dashboard
- Default `docker-compose.yml` configuration
- Published PyPI package (`langsight`)

Out of scope:
- Third-party MCP servers (report to their maintainers)
- Vulnerabilities requiring physical access to the host
- Social engineering attacks

### Safe harbor

LangSight follows a coordinated disclosure model. Researchers who report vulnerabilities in good faith, follow this policy, and do not publicly disclose before a patch is available will not face legal action from the LangSight project.

---

*Document maintained by the LangSight engineering team. Last updated: 2026-03-19.*
*Next review: 2026-06-19 or after any significant architectural change.*
