# AgentGuard: UI & Features Specification

> **Version**: 1.0.0-draft
> **Date**: 2026-03-15
> **Status**: Draft — CLI mockups and feature overview, detailed wireframes added during build

---

## 1. Interface Strategy

AgentGuard has two interfaces, shipped in phases:

| Interface | Phase | Purpose |
|---|---|---|
| **CLI** (`agentguard`) | Phase 1 | Primary interface — health checks, security scans, monitoring, investigation |
| **Web Dashboard** | Phase 3 | Visual interface for teams — dashboards, charts, alert management |

CLI is the priority. Dashboard is built on the same FastAPI backend, so CLI users get everything first.

---

## 2. CLI Specification

### 2.1 `agentguard init`

Interactive setup wizard that generates `.agentguard.yaml`.

```
$ agentguard init

🔍 Scanning for MCP server configurations...

Found MCP servers in:
  ✅ ~/.config/claude/claude_desktop_config.json (4 servers)
  ✅ ~/.cursor/mcp.json (2 servers)

Discovered 6 MCP servers:
  1. snowflake-mcp      (stdio)     ~/.config/claude/claude_desktop_config.json
  2. github-mcp         (stdio)     ~/.config/claude/claude_desktop_config.json
  3. slack-mcp          (sse)       ~/.config/claude/claude_desktop_config.json
  4. jira-mcp           (stdio)     ~/.config/claude/claude_desktop_config.json
  5. postgres-mcp       (stdio)     ~/.cursor/mcp.json
  6. filesystem-mcp     (stdio)     ~/.cursor/mcp.json

Include all servers? [Y/n]: Y

Alert notifications:
  Slack webhook URL (optional): https://hooks.slack.com/services/T.../B.../xxx
  Alert threshold - error rate: [5%]:
  Alert threshold - latency spike: [3x baseline]:

✅ Configuration written to .agentguard.yaml
   6 MCP servers configured
   Slack alerts enabled

Next steps:
  agentguard mcp-health      Check server health
  agentguard security-scan   Run security audit
  agentguard monitor         Start continuous monitoring
```

**Auto-discovery sources**:
- `~/.config/claude/claude_desktop_config.json` (Claude Desktop)
- `~/.cursor/mcp.json` (Cursor)
- `~/.vscode/mcp.json` (VS Code)
- Manual entry via `agentguard config add-server`

---

### 2.2 `agentguard mcp-health`

Shows real-time health status of all configured MCP servers.

```
$ agentguard mcp-health

MCP Server Health                                    6 servers monitored
────────────────────────────────────────────────────────────────────────
Server              Status    p99 Latency   Schema    Tools   Last Check
snowflake-mcp       ✅ UP     142ms         Stable    8       12s ago
github-mcp          ✅ UP     310ms         Stable    12      8s ago
slack-mcp           ✅ UP     89ms          Stable    5       45s ago
jira-mcp            ❌ DOWN   —             —         —       Last seen 2h ago
postgres-mcp        ⚠ SLOW    4.2s          Stable    6       3s ago
filesystem-mcp      ✅ UP     52ms          Changed!  4       15s ago

Alerts:
  🔴 jira-mcp has been down for 2h — 3 consecutive health checks failed
  🟡 postgres-mcp latency spiked 20x (200ms → 4.2s) in the last hour
  🟡 filesystem-mcp schema changed — tool "read_file" added parameter "encoding"

Summary: 3 healthy, 1 degraded, 1 down, 1 schema change
```

**Options**:
| Flag | Description |
|---|---|
| `--watch` | Continuous mode, refreshes every 30s |
| `--server <name>` | Show detail for one server |
| `--json` | JSON output for scripting |
| `--verbose` | Show individual tool health within each server |

**Status definitions**:
| Status | Meaning | Condition |
|---|---|---|
| ✅ UP | Server is healthy | Responds to health check within timeout, no errors |
| ⚠ SLOW | Server responding but degraded | p99 latency > 3x baseline |
| ⚠ STALE | Server up but returning outdated data | Output timestamps older than configured max age |
| ❌ DOWN | Server not responding | 3+ consecutive health check failures |
| 🔄 CHANGED | Schema change detected | Tool schema hash differs from last check |

---

### 2.3 `agentguard security-scan`

Scans all MCP servers for security vulnerabilities.

```
$ agentguard security-scan

Scanning 6 MCP server configurations...

🔴 CRITICAL (2 findings)

  filesystem-mcp: Symlink escape vulnerability (CVE-2025-6514)
    Category: OWASP-MCP-03 (Tool Poisoning / Path Traversal)
    Impact: Allows arbitrary file read outside sandbox
    Fix: Update mcp-remote to >= 2.1.0

  jira-mcp: No authentication configured
    Category: OWASP-MCP-05 (Insufficient Access Controls)
    Impact: Any network client can call this server
    Fix: Add API key or OAuth authentication

🟡 WARNING (3 findings)

  slack-mcp: Overly broad permissions
    Category: OWASP-MCP-06 (Excessive Permissions)
    Impact: Can post to any channel, read any message
    Fix: Scope to specific channels via Slack app permissions

  github-mcp: Long-lived API token (created 14 months ago)
    Category: OWASP-MCP-05 (Insufficient Access Controls)
    Impact: Compromised token gives extended access
    Fix: Rotate to short-lived tokens, use GitHub App auth

  postgres-mcp: Tool description changed since last scan
    Category: OWASP-MCP-01 (Tool Poisoning)
    Impact: Possible tool poisoning — description mutation detected
    Fix: Review tool description diff, re-baseline if intentional

✅ PASS (1 server)

  snowflake-mcp: Key-pair auth, read-only role, query timeout set

────────────────────────────────────────────────────────────────────────
OWASP MCP Top 10 Scorecard:
  MCP-01  Tool Poisoning              ⚠ 1 warning (description mutation)
  MCP-02  Excessive Agency            ✅ Pass
  MCP-03  Tool Poisoning (Injection)  🔴 1 critical (CVE-2025-6514)
  MCP-04  Tool Argument Injection     ✅ Pass
  MCP-05  Insufficient Access Control 🔴 1 critical, 1 warning
  MCP-06  Excessive Permissions       ⚠ 1 warning
  MCP-07  Insecure Data Handling      ✅ Pass
  MCP-08  Insufficient Logging        ⚠ Not assessed (requires monitoring data)
  MCP-09  Improper Error Handling     ✅ Pass
  MCP-10  Inadequate Sandboxing       ✅ Pass

Overall Security Score: 4/10 — Needs improvement
```

**Options**:
| Flag | Description |
|---|---|
| `--fix` | Show detailed remediation steps for each finding |
| `--json` | JSON output for scripting/CI |
| `--ci` | Exit code 1 if any CRITICAL finding (for CI/CD gates) |
| `--server <name>` | Scan a single server |
| `--baseline` | Capture current tool descriptions as baseline (for poisoning detection) |

---

### 2.4 `agentguard monitor`

Continuous monitoring daemon — runs health checks, security re-scans, and sends alerts.

```
$ agentguard monitor

AgentGuard Monitor v0.1.0
  Monitoring 6 MCP servers
  Health check interval: 30s
  Security re-scan interval: 1h
  Alerts: Slack (configured)

[22:14:01] Health check complete — 5 UP, 1 DOWN (jira-mcp)
[22:14:01] 🔴 Alert sent: jira-mcp DOWN for 2h 14m
[22:14:31] Health check complete — 5 UP, 1 DOWN (jira-mcp)
[22:15:01] Health check complete — 6 UP, 0 DOWN
[22:15:01] ✅ Alert resolved: jira-mcp is back UP (downtime: 2h 15m)
[22:15:05] Schema change detected: filesystem-mcp → tool "read_file" modified
[22:15:05] 🟡 Alert sent: filesystem-mcp schema change
[23:14:01] Security re-scan complete — Score: 4/10 (unchanged)

Press Ctrl+C to stop
```

**What it does on each cycle**:
1. Health checks all servers (configurable interval, default 30s)
2. Compares results against alert thresholds
3. Deduplicates alerts (same alert within cooldown = no re-send)
4. Periodically re-scans security (default 1h)
5. Tracks schema changes (hash comparison)
6. Writes all results to ClickHouse (if running) or SQLite (CLI-only mode)

---

### 2.5 `agentguard investigate "description"` (Phase 2)

AI-powered root cause attribution using Claude Agent SDK.

```
$ agentguard investigate "customer bot said refund window is 30 days, but it's 14 days"

🔍 Investigating...

Reading data sources:
  ✅ MCP health data (last 24h)
  ✅ OTEL traces (last 24h, 847 tool calls)
  ✅ Tool reliability metrics

─── Investigation Report ───────────────────────────────────────────────

MCP Tool Health at Time of Incident:
  policy-kb-mcp    ⚠ STALE    Serving data from July 2025 (8 months old)
  crm-mcp          ✅ UP       Normal operation
  jira-mcp         ✅ UP       Normal operation

Tool Call Analysis:
  policy-kb-mcp was called 3 times during the conversation
  All 3 calls returned successfully (HTTP 200) but with STALE data
  The tool's source was updated Nov 2025, tool still serves July 2025 version

Root Cause: STALE MCP TOOL DATA
  Confidence: 92%
  The policy-kb-mcp tool is returning outdated information.
  Refund policy changed from 30 days to 14 days in Nov 2025,
  but the tool's underlying data was never refreshed.

Blast Radius:
  Estimated ~340 conversations affected since Nov 2025
  All conversations involving refund policy queries

Recommended Fix:
  1. Refresh policy-kb-mcp data source to latest version
  2. Add freshness monitoring: alert when source is updated but tool data isn't
  3. Set max_age threshold for policy-kb-mcp in .agentguard.yaml
```

**Options**:
| Flag | Description |
|---|---|
| `--time-range "2h"` | Limit investigation to specific time window |
| `--trace-id <id>` | Investigate a specific OTEL trace |
| `--json` | Structured JSON output |
| `--max-cost $0.50` | Cap Claude API cost for this investigation |

---

### 2.6 `agentguard costs` (Phase 2)

Cost breakdown by MCP tool, agent, and time period.

```
$ agentguard costs --period 7d

Cost Report — Last 7 Days                           Total: $47.23
────────────────────────────────────────────────────────────────────────

By MCP Tool:
  Tool                    Calls      Avg Cost    Total     Trend
  snowflake-mcp           2,341      $0.008      $18.73    📈 +15%
  policy-kb-mcp           1,892      $0.003      $5.68     ✅ stable
  github-mcp              1,204      $0.012      $14.45    📈 +40% ⚠
  crm-mcp                   847      $0.005      $4.24     ✅ stable
  slack-mcp                 512      $0.002      $1.02     ✅ stable
  jira-mcp                  438      $0.007      $3.07     📉 -20%

By Agent:
  Agent                   Tasks      Total Cost  Avg/Task
  customer-support-bot    312        $28.14      $0.09
  code-review-agent       89         $14.45      $0.16
  data-analyst-agent      47         $4.64       $0.10

⚠ Anomaly: github-mcp costs up 40% — call volume increased from 860 to 1,204
```

**Options**:
| Flag | Description |
|---|---|
| `--period <duration>` | Time period: 1d, 7d, 30d (default: 7d) |
| `--tool <name>` | Filter by specific tool |
| `--agent <name>` | Filter by specific agent |
| `--json` | JSON output |

---

### 2.7 `agentguard config`

Configuration management.

```
$ agentguard config show          # Show current configuration
$ agentguard config add-server    # Add an MCP server interactively
$ agentguard config set-alert     # Configure alert threshold
$ agentguard config test          # Test connections to all servers
```

---

## 3. Configuration File

### `.agentguard.yaml` Schema

```yaml
# AgentGuard Configuration
version: "1"

# MCP servers to monitor
servers:
  - name: snowflake-mcp
    transport: stdio
    command: npx
    args: ["-y", "@anthropic/mcp-server-snowflake"]
    env:
      SNOWFLAKE_ACCOUNT: "xxx"
    tags: [production, data]
    health_check_interval: 30s
    max_latency: 500ms

  - name: slack-mcp
    transport: sse
    url: http://localhost:3001/sse
    tags: [production, comms]

  - name: policy-kb-mcp
    transport: streamable_http
    url: http://localhost:8080/mcp
    max_data_age: 24h        # Alert if data older than this
    tags: [production, knowledge]

# Alerting
alerts:
  slack_webhook: https://hooks.slack.com/services/T.../B.../xxx
  # Generic webhook (optional)
  webhook_url: https://my-service.com/agentguard-alerts

  thresholds:
    server_down_after: 3          # consecutive failures before DOWN alert
    latency_spike_multiplier: 3   # alert when p99 > Nx baseline
    error_rate_percent: 5         # alert when error rate > X%
    cost_spike_multiplier: 3      # alert when daily cost > Nx baseline

  cooldown: 15m                   # Don't re-send same alert within this window

# Cost tracking (optional)
costs:
  # External API costs per tool (user-configured)
  tool_costs:
    snowflake-mcp: 0.008          # $ per call
    github-mcp: 0.012

  # LLM model pricing (auto-loaded, can override)
  model_pricing_override:
    claude-sonnet-4-6: { input: 0.003, output: 0.015 }

# Storage (for CLI-only mode, uses SQLite; full stack uses ClickHouse/PostgreSQL)
storage:
  mode: sqlite                    # sqlite | full
  sqlite_path: ~/.agentguard/data.db

# OTEL ingestion (full stack mode only)
otel:
  collector_endpoint: http://localhost:4318

# Privacy / PII safety
# Set to true to prevent tool call arguments and return values from being stored.
# When true, ToolCallSpan.input_args and output_result are set to None before
# transmission — payloads never leave the host process.
# Default: false (payloads captured for maximum debuggability).
redact_payloads: false
```

**Environment variable overrides**: Any config value can be overridden via env var with `AGENTGUARD_` prefix:
- `AGENTGUARD_SLACK_WEBHOOK` → `alerts.slack_webhook`
- `AGENTGUARD_STORAGE_MODE` → `storage.mode`

---

## 4. Web Dashboard (Phase 3 — Overview)

The dashboard is built on the same FastAPI REST API that powers the CLI.
The current IA is agent-first: **Overview → Agents → Workflows → Tools & MCPs → Security → Costs**.

### 4.1 Dashboard Home
- **Agent/workflow summary cards**: Active workflows, healthy agents, tool/MCP backend status, cost snapshot
- **Active alerts**: List of currently firing alerts with severity badges
- **Workflow + infrastructure split**: Agent workflows are primary; MCP/tool infrastructure is secondary drill-down

### 4.2 Agents Page
- **Agent fleet view**: Per-agent session count, tool calls, failures, runtime, and cost
- **Agent drill-down**: Touched tools/MCPs, recent workflows, operational summary

### 4.3 Workflows Page
- **Session table**: One row per workflow/session with agent, tool-call count, failures, duration, and touched backends
- **Trace drawer**: Tree of `agent`, `handoff`, and `tool_call` spans for one workflow. Clicking a span row expands an inline panel showing formatted input arguments and return value; error details shown for failed spans. Payload visibility requires P5.1 payload capture to be active (`redact_payloads: false`, default).
- **Session comparison**: Click one session row to select it as A (row highlighted blue); click a second row to select it as B (row highlighted purple); a Compare button appears. Clicking Compare opens a diff drawer that calls `GET /api/agents/sessions/compare?a=&b=` and renders a per-tool aligned diff table. Each diff row shows tool key, A status, A latency, B status, B latency, and latency delta percentage. Row colours: matched=green, diverged=yellow, only_a=blue, only_b=purple. Diverged = status changed OR latency delta >= 20%.
- **Replay button** (P5.7): Replay button in trace drawer header — re-runs all `tool_call` spans in the session with their stored input args against live MCP servers. Shows spinner and "Replaying..." while in flight. On completion, calls `POST /api/agents/sessions/{id}/replay` and receives a `replay_session_id`; the compare drawer auto-opens between the original and replay sessions. Inline error message shown below drawer header on failure. Configurable per-call timeout (default 10s) and total session timeout (default 60s). Requires `redact_payloads: false` (default) so that `input_json` is present on spans.

### 4.4 Tools & MCPs Page
- **Server list table**: Name, status badge, p99 latency, schema status, tools count, last check time
- **Click server → detail view**: Latency time-series chart, availability history, schema changelog, tool list with per-tool latency
- **Filters**: By status, transport type, tag

### 4.5 Tool Reliability Page
- **Metrics table**: Tool name, success rate (with sparkline), p50/p95/p99 latency, error rate, call volume
- **Color coding**: Green (>95% success), Yellow (80-95%), Red (<80%)
- **Click tool → drill-down**: Error breakdown by category, latency histogram, recent failures with trace links

### 4.6 Security Page
- **OWASP MCP Top 10 scorecard**: Visual card per category (pass/warn/fail)
- **Vulnerability list**: Sortable by severity, filterable by server
- **Tool poisoning alerts**: Description diff viewer (before/after)
- **Remediation panel**: Fix suggestions per finding

### 4.7 Cost Analytics Page
- **Shipped now**: Summary cards plus live breakdowns by tool, by agent, and by session
- **Data source**: `/api/costs/breakdown` from ClickHouse-backed traced tool calls
- **Next layer**: Trend charts, anomaly highlights, and budget alerts

### 4.8 Alerts Page
- **Alert timeline**: Newest first, severity color-coded
- **Filters**: By severity, status (firing/ack/resolved), server, type
- **Alert detail**: What triggered, when, context data, linked health check
- **Actions**: Acknowledge, resolve, snooze
- **Alert rules**: Configure thresholds per server or globally

### 4.7 Settings Page
- MCP server management (add/edit/remove/test connection)
- Alert configuration
- Slack webhook setup + test
- API key management
- Model pricing table

---

## 5. Feature Summary by Phase

### Phase 1 — MVP (Weeks 1-5)
| Feature | Interface | Description |
|---|---|---|
| MCP server discovery | CLI (`init`) | Auto-detect from Claude/Cursor/VS Code configs |
| Health monitoring | CLI (`mcp-health`) | Availability, latency, schema tracking |
| Security scanning | CLI (`security-scan`) | CVE matching, OWASP Top 10, tool poisoning detection |
| Continuous monitoring | CLI (`monitor`) | Daemon mode with periodic health + security checks |
| Alerting | Slack + webhook | Threshold-based alerts with deduplication |
| Local storage | SQLite | CLI-only mode, no Docker required |
| Config management | CLI (`config`) + YAML | Server management, alert thresholds |

### Phase 2 — Differentiate (Weeks 6-10)
| Feature | Interface | Description |
|---|---|---|
| OTEL trace ingestion | OTEL Collector | Accept GenAI spans from agent frameworks |
| Tool reliability metrics | CLI (`mcp-health --verbose`) | Success rate, latency percentiles, error categorization |
| Cost attribution | CLI (`costs`) | Per-tool, per-agent, per-task dollar costs |
| Root cause attribution | CLI (`investigate`) | AI-powered investigation using Claude Agent SDK |
| Full storage backend | ClickHouse + PostgreSQL | Docker Compose, time-series analytics |

### Phase 3 — Dashboard + Polish (Weeks 11-16)
| Feature | Interface | Description |
|---|---|---|
| Web dashboard | Next.js | 6 pages: Home, Health, Reliability, Security, Costs, Alerts |
| Integration testing | — | Verified with CrewAI, Pydantic AI, OpenAI Agents SDK |
| MCP server (meta) | MCP | Expose AgentGuard tools via MCP so agents can query health |
| Documentation | — | README, quickstart, framework guides, examples |
| PyPI publish | — | `pip install agentguard` |

---

## 6. Slack Alert Format

```
🔴 AgentGuard Alert — MCP Server Down

Server: jira-mcp
Status: DOWN (was UP)
Since: 2026-03-15 20:01:00 UTC (2h 14m ago)
Last successful check: 2026-03-15 19:59:30 UTC

Details:
  Transport: stdio
  Error: Connection refused — process not running
  Consecutive failures: 8

Impact:
  Agents using jira-mcp may fail or return incomplete results.

→ Run: agentguard mcp-health --server jira-mcp
```

```
🟡 AgentGuard Alert — Schema Change Detected

Server: filesystem-mcp
Tool: read_file
Change: Parameter "encoding" added (type: string, optional)

Previous schema hash: a3f8b2c1
New schema hash: 7d2e9f04

This may affect agents relying on the previous tool interface.

→ Run: agentguard security-scan --server filesystem-mcp
```
