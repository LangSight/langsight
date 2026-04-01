# LangSight: UI & Features Specification

> **Version**: 1.9.0
> **Date**: 2026-04-01
> **Status**: Active — Lineage protocol v1.0: `llm_intent` span type added to trace tree display (2026-04-01). Updated with `langsight add` command, `langsight scorecard` command, `langsight init` expanded to 10+ IDE clients with correct macOS paths, schema drift structural diff display (v0.8.0, 2026-03-26); health_tool backend probe, inputSchema string fix (v0.8.4–v0.8.5, 2026-03-27); MCP Servers page merged with Tool Health, Last Used / Last OK columns, Agents Servers tab, costs source filter rename (v0.8.6, 2026-03-27); embedded monitor loop in `langsight serve`, `LANGSIGHT_MONITOR_ENABLED`, `LANGSIGHT_MONITOR_INTERVAL_SECONDS` (v0.9.0, 2026-03-27)

---

## 1. Interface Strategy

LangSight has two interfaces, shipped in phases:

| Interface | Phase | Purpose |
|---|---|---|
| **CLI** (`langsight`) | Phase 1 | Primary interface — health checks, security scans, monitoring, investigation |
| **Web Dashboard** | Phase 3 | Visual interface for teams — dashboards, charts, alert management |

CLI is the priority. Dashboard is built on the same FastAPI backend, so CLI users get everything first.

---

## 2. CLI Specification

### 2.1 `langsight init`

Interactive setup wizard that discovers all configured MCP servers and generates `.langsight.yaml`.
Updated v0.8.0 (2026-03-26): now covers 10+ IDE clients, runs a first health check automatically.

**Project scoping note (v0.8.1)**: `langsight init` does not ask for a project ID. Project scoping is entirely dashboard-side — the engineer creates a project-scoped API key in the dashboard and exports it as `LANGSIGHT_API_KEY`. The CLI is project-agnostic. Same applies to `langsight add`.

```
$ langsight init

LangSight Init — scanning for MCP servers...

  ✓  Claude Desktop  (~/Library/Application Support/Claude/claude_desktop_config.json)  4 servers
  ✓  Cursor          (~/.cursor/mcp.json)                                                2 servers
  ✓  VS Code         (~/Library/Application Support/Code/User/mcp.json)                 1 server
  ─  Windsurf        not found
  ─  Kiro            not found

Discovered 7 MCP servers
┌───┬──────────────────┬──────────────────┬────────────────────────────────────┬───────────────┐
│ # │ Name             │ Transport        │ Command / URL                      │ Source        │
├───┼──────────────────┼──────────────────┼────────────────────────────────────┼───────────────┤
│ 1 │ snowflake-mcp    │ stdio            │ npx -y @anthropic/mcp-server-sf    │ Claude Desktop│
│ 2 │ github-mcp       │ stdio            │ npx -y @modelcontextprotocol/gh    │ Claude Desktop│
│ 3 │ slack-mcp        │ sse              │ http://localhost:3001/sse          │ Claude Desktop│
│ 4 │ jira-mcp         │ stdio            │ npx -y @scope/jira-mcp             │ Claude Desktop│
│ 5 │ postgres-mcp     │ stdio            │ uv run python server.py            │ Cursor        │
│ 6 │ filesystem-mcp   │ stdio            │ npx -y @modelcontextprotocol/fs    │ Cursor        │
│ 7 │ internal-api     │ streamable_http  │ https://mcp.internal.company.com   │ VS Code       │
└───┴──────────────────┴──────────────────┴────────────────────────────────────┴───────────────┘

Include all 7 server(s)? [Y/n]: Y

Slack webhook URL for alerts (leave blank to skip): https://hooks.slack.com/services/T.../B.../xxx

✓ Config written to .langsight.yaml
  7 MCP servers configured
  Slack alerts enabled

Running first health check...

  UP                    snowflake-mcp          142ms      8 tools
  UP                    github-mcp             310ms      12 tools
  UP                    slack-mcp              89ms       5 tools
  DOWN                  jira-mcp               —          timeout after 5s
  UP                    postgres-mcp           52ms       6 tools
  UP                    filesystem-mcp         18ms       4 tools
  UP                    internal-api           201ms      9 tools

  1 server(s) DOWN. Run langsight mcp-health for details.

Next steps:
  langsight mcp-health      # Full health status + scorecard
  langsight security-scan   # Security audit
  langsight monitor         # Start continuous monitoring
```

**Options**:
| Flag | Description |
|---|---|
| `--skip-check` | Write config without running the first health check |
| `--yes` / `-y` | Skip confirmation prompts (non-interactive/CI use) |
| `--slack-webhook <url>` | Set Slack webhook URL directly |
| `--output` / `-o` | Write config to a custom path (default: `.langsight.yaml`) |

**Auto-discovery sources** (updated v0.8.0 — all 10+ clients):

| Client | Config path (macOS) | Key |
|---|---|---|
| Claude Desktop | `~/Library/Application Support/Claude/claude_desktop_config.json` | `mcpServers` |
| Cursor | `~/.cursor/mcp.json` | `mcpServers` |
| VS Code | `~/Library/Application Support/Code/User/mcp.json` | `servers` |
| Windsurf | `~/.codeium/windsurf/mcp_config.json` | `mcpServers` |
| Claude Code | `~/.claude.json` | `mcpServers` |
| Gemini CLI | `~/.gemini/settings.json` | `mcpServers` |
| Kiro | `~/.kiro/settings/mcp.json` | `mcpServers` |
| Zed | `~/.config/zed/settings.json` | `context_servers` |
| Cline | `~/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/...` | `mcpServers` |
| Cursor (project) | `.cursor/mcp.json` in CWD | `mcpServers` |
| Claude Code (project) | `.mcp.json` in CWD | `mcpServers` |
| VS Code (project) | `.vscode/mcp.json` in CWD | `servers` |

Servers with the same command+args or URL across multiple clients are deduplicated automatically.

---

### 2.2 `langsight add`

Manually register a single MCP server. Useful for production HTTP servers that don't exist in IDE configs.
Added v0.8.0 (2026-03-26).

```
$ langsight add postgres-mcp \
    --url https://postgres-mcp.internal.company.com/mcp

Adding postgres-mcp (streamable_http)...
  Testing connection...  ✓ Connected in 38ms
  ✓ 4 tool(s): query, insert, update, list_tables

✓ 'postgres-mcp' added to .langsight.yaml

Next steps:
  langsight mcp-health postgres-mcp   # Check health
  langsight security-scan             # Security audit
  langsight monitor                   # Start continuous monitoring
```

**Options**:
| Flag | Description |
|---|---|
| `--url <url>` | HTTP/SSE/StreamableHTTP URL (remote/production servers) |
| `--command <cmd>` | Shell command to launch a stdio server (local/dev) |
| `--args <arg>` | Arguments for the stdio command (repeatable) |
| `--env KEY=VALUE` | Environment variables for stdio server (repeatable) |
| `--header KEY=VALUE` | HTTP headers for auth (repeatable, e.g. `Authorization=Bearer $TOKEN`) |
| `--skip-check` | Add without running a connection test |
| `--config` / `-c` | Config file to update (default: `.langsight.yaml`) |

**Examples**:

```bash
# Remote HTTP server with auth
langsight add github-mcp \
  --url https://github-mcp.prod.company.com/mcp \
  --header "Authorization=Bearer $GITHUB_MCP_TOKEN"

# Local stdio server
langsight add local-db \
  --command "uv run python server.py" \
  --args "--db-url postgresql://localhost/mydb"

# With environment variables
langsight add my-server \
  --command "npx -y @scope/server" \
  --env "API_KEY=secret" \
  --env "DEBUG=true"
```

---

### 2.2 `langsight mcp-health`

Shows real-time health status of all configured MCP servers.

```
$ langsight mcp-health

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
| `--scorecard` | Show A-F composite health grade alongside each server (added v0.8.0) |
| `--drift` | Show latest schema drift events and classification (added v0.8.0) |

**Status definitions**:
| Status | Meaning | Condition |
|---|---|---|
| ✅ UP | Server is healthy | Responds to health check within timeout, no errors |
| ⚠ DEGRADED | MCP layer up but backend unhealthy | Schema drift detected, OR `health_tool` probe failed (backend down) — added v0.8.4 |
| ⚠ SLOW | Server responding but degraded | p99 latency > 3x baseline |
| ⚠ STALE | Server up but returning outdated data | Output timestamps older than configured max age |
| ❌ DOWN | MCP server unreachable | 3+ consecutive health check failures (initialize/tools/list failed) |
| 🔄 CHANGED | Schema change detected | Tool schema hash differs from last check |

---

### 2.3 `langsight security-scan`

Scans all MCP servers for security vulnerabilities.

```
$ langsight security-scan

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

### 2.4 `langsight monitor`

Continuous monitoring daemon — runs health checks, security re-scans, and sends alerts.

```
$ langsight monitor

LangSight Monitor v0.1.0
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
6. Writes all results to PostgreSQL (health results, schema snapshots) and ClickHouse (spans, health metrics) via the dual backend

---

### 2.5 `langsight investigate "description"` (Phase 2)

AI-powered root cause attribution using Claude Agent SDK.

```
$ langsight investigate "customer bot said refund window is 30 days, but it's 14 days"

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
  3. Set max_age threshold for policy-kb-mcp in .langsight.yaml
```

**Options**:
| Flag | Description |
|---|---|
| `--time-range "2h"` | Limit investigation to specific time window |
| `--trace-id <id>` | Investigate a specific OTEL trace |
| `--json` | Structured JSON output |
| `--max-cost $0.50` | Cap Claude API cost for this investigation |

---

### 2.6 `langsight costs` (Phase 2)

Cost breakdown by MCP tool, agent, and time period.

```
$ langsight costs --period 7d

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

### 2.7 `langsight scorecard`

Show the A-F composite health grade for all or one MCP server. Added v0.8.0 (2026-03-26).

```
$ langsight scorecard

MCP Server Scorecard
┌──────────────────┬───────┬───────────────────────────────────────────────────────────────┐
│ Server           │ Grade │ Dimensions                                                    │
├──────────────────┼───────┼───────────────────────────────────────────────────────────────┤
│ postgres-mcp     │  A+   │ avail:100 sec:100 rel:98  schema:100 perf:95                  │
│ github-mcp       │  B    │ avail:95  sec:85  rel:90  schema:80  perf:88  [cap: high CVE] │
│ slack-mcp        │  A    │ avail:99  sec:100 rel:95  schema:100 perf:92                  │
│ jira-mcp         │  F    │ avail:0   [cap: 10+ consecutive failures]                     │
└──────────────────┴───────┴───────────────────────────────────────────────────────────────┘

$ langsight scorecard --server postgres-mcp

postgres-mcp — Grade A+  (score 98.1)

  Availability    30%   100.0   Uptime 100.000% (7d)
  Security        25%   100.0   No findings
  Reliability     20%    97.5   Error rate 0.2%
  Schema Stability 15%  100.0   No schema changes in 7 days
  Performance     10%    95.0   p99 = 145ms (baseline 142ms)
```

Grade thresholds: A+(exceptional), A(≥90), B(≥80), C(≥65), D(≥50), F(<50).
Hard veto caps override the score for fatal flaws — see architecture doc § 2.1 for full cap rules.

---

### 2.8 `langsight config`

Configuration management.

```
$ langsight config show          # Show current configuration
$ langsight config set-alert     # Configure alert threshold
$ langsight config test          # Test connections to all servers
```

> **Note**: `langsight config add-server` was replaced by `langsight add` in v0.8.0.
> Use `langsight add <name> --url <url>` or `langsight add <name> --command <cmd>` instead.

---

## 3. Configuration File

### `.langsight.yaml` Schema

```yaml
# LangSight Configuration
version: "1"

# Project scoping (optional — added v0.8.1)
# These fields are only needed if you cannot use a project-scoped API key.
# When LANGSIGHT_API_KEY is a project-scoped key, project_id is ignored here.
# See docs-site/mcp/project-scoping.mdx for the full priority resolution.
project: "production"           # human-readable slug (display only)
project_id: ""                  # project UUID — blank means global scope

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

  # Backend probe — verify the application behind the MCP server is healthy
  # (added v0.8.4): health_tool is called after tools/list on every health check.
  # If the tool call fails, the server is marked DEGRADED (backend down) rather
  # than DOWN (MCP layer unreachable). Omit to skip the probe.
  - name: datahub
    transport: streamable_http
    url: https://datahub-mcp.internal.company.com/mcp
    health_tool: search_entities           # tool to call as a liveness probe
    health_tool_args:                       # arguments passed to the tool
      query: "test"
      count: 1
    timeout_seconds: 15
    tags: [production, metadata]

# Alerting
alerts:
  slack_webhook: ${LANGSIGHT_SLACK_WEBHOOK}
  # Generic webhook (optional)
  webhook_url: https://my-service.com/langsight-alerts

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

  # LLM model pricing (auto-loaded from model_pricing DB table, can override)
  model_pricing_override:
    claude-sonnet-4-6: { input: 0.003, output: 0.015 }

# Storage backend
# (changed from original: sqlite removed 2026-03-19; docker compose up -d required)
# Valid modes: postgres | clickhouse | dual (default: dual)
storage:
  mode: dual                      # Postgres (metadata) + ClickHouse (analytics)
  postgres_url: ${LANGSIGHT_POSTGRES_URL}
  # clickhouse_url, clickhouse_database, clickhouse_username, clickhouse_password
  # are read from env vars (LANGSIGHT_CLICKHOUSE_*) or use defaults

# OTEL ingestion
otel:
  collector_endpoint: http://localhost:4318

# Privacy / PII safety
# Set to true to prevent tool call arguments and return values from being stored.
# When true, ToolCallSpan.input_args and output_result are set to None before
# transmission — payloads never leave the host process.
# Default: false (payloads captured for maximum debuggability).
redact_payloads: false

# Embedded monitor (v0.9.0) — controls the background health check loop
# started automatically by `langsight serve`. Set monitor_enabled: false to
# run the API without a background health check (advanced HA deployments only).
monitor_enabled: true              # default: true
monitor_interval_seconds: 60       # default: 60 — seconds between check cycles
```

**Environment variable overrides** (all use `LANGSIGHT_` prefix):
| Env var | Config field |
|---|---|
| `LANGSIGHT_SLACK_WEBHOOK` | `alerts.slack_webhook` |
| `LANGSIGHT_STORAGE_MODE` | `storage.mode` |
| `LANGSIGHT_PROJECT_ID` | `project_id` — fallback project UUID when using a global API key (added v0.8.1) |
| `LANGSIGHT_POSTGRES_URL` | `storage.postgres_url` |
| `LANGSIGHT_CLICKHOUSE_URL` | `storage.clickhouse_url` |
| `LANGSIGHT_API_KEYS` | API key list (comma-separated) |
| `LANGSIGHT_MONITOR_ENABLED` | `monitor_enabled` — `true` (default) or `false`. Controls embedded monitor loop in `langsight serve`. (added v0.9.0) |
| `LANGSIGHT_MONITOR_INTERVAL_SECONDS` | `monitor_interval_seconds` — seconds between embedded monitor health check cycles (default: `60`). (added v0.9.0) |
| `LANGSIGHT_TRUSTED_PROXY_CIDRS` | Trusted proxy network CIDRs (default: `127.0.0.1/32,::1/128`) |
| `LANGSIGHT_DASHBOARD_URL` | Base URL used in invite email links |
| `LANGSIGHT_CORS_ORIGINS` | Comma-separated allowed CORS origins |
| `LANGSIGHT_METRICS_TOKEN` | Optional bearer token for `GET /metrics`. When unset, endpoint is open and a warning is logged at startup. (added v0.7.0) |
| `ANTHROPIC_API_KEY` | LLM key for `langsight investigate` with `provider: anthropic`. Never set this in `.langsight.yaml`. (v0.7.0: `investigate.api_key` config field removed) |
| `OPENAI_API_KEY` | LLM key for `langsight investigate` with `provider: openai`. Never set this in `.langsight.yaml`. |
| `GEMINI_API_KEY` | LLM key for `langsight investigate` with `provider: gemini`. Never set this in `.langsight.yaml`. |

---

## 4. Web Dashboard (Phase 3 — Overview)

The dashboard is built on the same FastAPI REST API that powers the CLI.
The current IA is agent-first: **Overview → Agents → Sessions → Health → Security → Costs → Settings**.

### 4.1 Dashboard Home
- **Agent/workflow summary cards**: Active workflows, healthy agents, tool/MCP backend status, cost snapshot
- **Active alerts**: List of currently firing alerts with severity badges
- **Workflow + infrastructure split**: Agent workflows are primary; MCP/tool infrastructure is secondary drill-down

### 4.2 Agents Page (Adaptive 3-State Layout)

The Agents page renders in one of three states depending on what is selected:

**State 1 — No agent selected (full-width table)**
- Full-width sortable table with columns: Agent, Status, Sessions, Error Rate, Tool Calls, Cost, Last Active
- Sortable on all columns; sort direction persists during the session
- Needs Attention banner above the table when any agent has `status != healthy`
- Status filter bar: All / Healthy / Degraded / Failing with live counts
- Search box filters by agent name

**State 2 — Agent selected (280px sidebar + detail panel)**
- Left sidebar groups all agents; active agent is highlighted
- Detail panel shows 5 tabs:
  - **About**: Editable description, owner, tags, status (active/deprecated/experimental), runbook URL — writes to `PUT /api/agents/metadata/{name}` on blur
  - **Overview**: Stat tiles (sessions, error rate, avg duration, total cost), recent sessions list with links to `/sessions/{id}`
  - **Topology**: Per-agent subgraph using the shared SVG `lineage-graph` renderer scoped to the selected agent's edges; sidebar collapses to 56px icon rail to maximize graph area (see State 3)
  - **Sessions**: Paginated list of recent sessions for this agent
  - **Servers** (added v0.8.6): Lists the MCP servers this agent has called, derived from trace data. Columns: Server name, Tools (count of distinct tools called), Calls (total call count), Errors, Health status. Health status is sourced from `GET /api/health/servers/invocations` and the server's latest health check result. This tab gives an agent-first view of infrastructure dependencies — equivalent to the "Consumers" tab on the server side viewed in reverse.

**State 3 — Topology tab active (icon-rail sidebar + full-width graph)**
- Left sidebar collapses to 56px showing only agent status dots
- The shared `LineageGraph` component fills the remaining width
- Fleet-wide topology is available as a modal overlay from the graph toolbar

**Fleet topology modal**: Accessible from the graph toolbar in States 2 and 3; shows the full agent/server DAG for all agents in the selected project.

**Backend**: Editable metadata persisted to the `agent_metadata` PostgreSQL table via `GET /api/agents/metadata` and `PUT /api/agents/metadata/{name}`.

**Performance** (optimized 2026-03-21):
- Sessions fetch limit reduced from 500 to 100 on the agents page to reduce initial payload size
- SWR refresh intervals are staggered across data fetchers (sessions, metadata, topology) to avoid concurrent API thundering herd on mount

### 4.3 Sessions Page

**Session table**: One row per workflow/session with agent, health tag, tool-call count, failures, duration, touched backends, and two timestamp columns (relative "Started" + exact ISO "Timestamp").

**Date range filter** (added 2026-03-23): The `DateRangeFilter` component appears in the page header to the right of the title. It provides:
- Five preset buttons: `1h`, `6h`, `24h`, `7d`, `30d` — the active preset is highlighted with the primary teal accent.
- A `Range` / `Custom` calendar button that opens a dropdown picker with From/To `<input type="date">` fields. On Apply the custom range is passed as ISO strings (`T00:00:00` / `T23:59:59`); clicking any preset clears the custom range.
- The active preset or custom range is reflected in the SWR fetch URL (`?hours=<N>`). Custom range state is held in `customFrom` / `customTo` state; switching to a preset clears both.
- Clicking outside the dropdown closes it via `mousedown` document listener.
- Component path: `dashboard/components/date-range-filter.tsx`

**Filters (in addition to date range)**:
- Text search: session ID, agent name, or server name
- Status tabs: All / Clean / Failed — with live counts
- Agent dropdown (shown only when more than one agent is present)
- Health tag dropdown: All / Success / Fallback / Loop / Budget / Failure / Circuit Open / Timeout / Schema Drift

**Pagination**: 20 rows per page; sticky footer with first/previous/next/last controls and `x / total` label.

**Dedicated session detail route**: Clicking a row opens `/sessions/[id]`.

#### 4.3.1 Details tab — Lineage Graph (redesigned 2026-03-20; wide-screen layout 2026-03-23)

The Details tab is the visual debugging surface. It has three sub-regions stacked vertically:

**Timeline bar** (above the graph):
- Colored horizontal segments across the full session duration — one segment per `tool_call` span
- Colors: green = success, red = error, yellow = timeout/other
- Click a segment to select the corresponding node in the graph
- Tooltip on hover shows tool name, status, and latency

**Graph toolbar** (overlaid on graph, top-left):
- Search bar — highlights matching nodes; non-matching nodes dimmed. Keyboard shortcut: `/` to focus
- Zoom slider — range 25–250%; `+`/`-` keys increment by 10%
- Expand All / Collapse All buttons — controls server node expansion state globally
- Failures toggle — isolates the error chain, dims non-failing nodes. Keyboard shortcut: `e`
- Fit view button — fits all nodes into viewport. Keyboard shortcut: `f`
- `Esc` clears selection

**Lineage graph** (shared SVG + dagre renderer — nodes redesigned 2026-03-23):
- Agent nodes and server nodes connected by directed edges with call counts
- Node cards redesigned: compact metric pills inside each card show call count, error count, and avg latency. Node padding tightened. Agent nodes use a primary-teal gradient header; server nodes use a muted slate gradient. Glass-morphism styling with border + glow on selection.
- Tool names listed inside expanded server nodes (one row per distinct tool), up to a configurable max before "+ N more"
- Loop detection annotation: nodes with a repeated call pattern show the `repeatCallName` and `repeatCallCount` below the metric pills
- Per-tool expansion: each edge between an agent and a server shows a circular `+` button with call count (e.g. `5×`). Clicking it splits the server node into per-tool sub-nodes, one per distinct tool called
- Back-edges (cycles) rendered as self-loop arcs on the right side of the node
- "View in Agent/Server Catalog →" links visible in node detail panel, navigating to `/agents` or `/servers` with the node pre-selected
- Keyboard shortcut: `Esc` = deselect node

**Minimap** (bottom-right corner — redesigned 2026-03-23):
- 150×90px overview of the full graph with a viewport rectangle overlay
- Dragging the viewport rectangle inside the minimap pans the main graph
- Minimap uses a `ResizeObserver` to track the container size and scales accordingly
- Auto-fits the graph into the viewport on first render when both container size and layout are known
- Always visible when graph has nodes

**Right-side inspector panel** (70/30 split — graph 70%, panel 30%):
- Populated when a node, edge, or per-tool sub-node is selected
- Shows call counts, error rate, avg/p99 latency, tool list, and token usage for the selected element
- MetricTile sub-component: each metric is a rounded tile with a primary or danger accent border on the left side
- "View in Catalog" link appears for agent and server nodes

**Graph builder extraction** (2026-03-23):
- Session graph construction logic extracted from the session detail page into `dashboard/lib/session-graph.ts`
- Exports `buildSessionGraph(trace, expandedGroups, expandedEdges): SessionGraphResult`
- `SessionGraphResult` type: `{ nodes, edges, serverCallers, edgeMetrics, edgeSpans }`
- Loop detection (`findRepeatedCall`) and per-call label generation (`buildCallLabels`) live in this module
- The detail page consumes `buildSessionGraph` via the `useSessionGraph` hook (a `useMemo` wrapper) — graph recomputes only when trace, expandedGroups, or expandedEdges change

**PayloadSlideout** (full-width slide-over panel):
- Opens when a payload cell in the inspector is clicked
- Displays JSON with line numbers
- Controls: copy button, word wrap toggle, tab selector (Input / Output / Prompt / Completion)
- `Esc` closes the panel

#### 4.3.2 Trace tab

Tree of `agent`, `handoff`, `tool_call`, and `llm_intent` spans. `llm_intent` spans represent LLM tool-call decisions (not actual executions) and are shown with a distinct icon/label. Clicking a span row expands inline payload/error content. Payload visibility requires P5.1 payload capture to be active (`redact_payloads: false`, default).

#### 4.3.3 Session comparison

Compare is initiated from the session detail page. The user picks another recent session, then LangSight calls `GET /api/agents/sessions/compare?a=&b=` and renders a per-tool aligned diff table. Each diff row shows tool key, base status, base latency, compare status, compare latency, and latency delta percentage. Row colours: matched=green, diverged=yellow, only_a=blue, only_b=purple. Diverged = status changed OR latency delta >= 20%.

#### 4.3.4 Replay button (P5.7)

Replay lives in the session detail header — re-runs all `tool_call` spans in the session with their stored input args against live MCP servers. Shows spinner and "Replaying..." while in flight. On completion, calls `POST /api/agents/sessions/{id}/replay` and returns a replay session that can be compared directly with the original. Requires `redact_payloads: false` (default) so that `input_json` is present on spans.

### 4.3.5 Shared UI Components (added / updated 2026-03-23)

#### `Timestamp` component (`dashboard/components/timestamp.tsx`)

Renders both relative and exact timestamps from a single ISO string. Used across sessions list, session detail, health page uptime dots, agents page, and servers page.

**Default mode** (two spans in one `<time>` element):
```
16h ago · Mar 22, 14:30:05
```
The relative portion is displayed in normal foreground color. The exact portion (`· Mar 22, 14:30:05`) is rendered at 60% opacity in `text-muted-foreground`.

**Compact mode** (`compact` prop): renders only the relative time. The exact time is placed in the HTML `title` attribute for tooltip-on-hover. Used in tight spaces such as the sessions table "Started" column.

Both modes use the `<time dateTime={iso}>` element for semantic HTML. The `timeAgo()` and `formatExact()` helpers from `@/lib/utils` compute the display values.

#### `DateRangeFilter` component (`dashboard/components/date-range-filter.tsx`)

Reusable date range control for any dashboard page that needs time-windowed data. Pages using it as of 2026-03-23: Sessions, Costs, Health, Agents, Servers.

**Props**:
| Prop | Type | Description |
|---|---|---|
| `activeHours` | `number \| null` | Currently selected preset in hours; `null` when custom range is active |
| `onPreset` | `(hours: number) => void` | Called when a preset button is clicked |
| `onCustomRange` | `(from: string, to: string) => void` | Called with ISO strings when Apply is clicked in the date picker |
| `onClearCustom` | `() => void` | Called when custom range is cleared or preset is selected |
| `customFrom` | `string \| null` | Controlled: currently active custom from date (ISO) |
| `customTo` | `string \| null` | Controlled: currently active custom to date (ISO) |

**Presets**: `1h` (1h), `6h` (6h), `24h` (24h), `7d` (168h), `30d` (720h). Active preset highlighted with primary color; inactive presets use muted background.

**Custom range picker**: dropdown (absolute-positioned, `z-50`, blur backdrop) with From/To `<input type="date">` fields. Apply button is disabled until both dates are filled. Custom range applies `T00:00:00` to the From date and `T23:59:59` to the To date before converting to ISO strings.

### 4.4 MCP Servers Catalog — `/servers`

New page added 2026-03-20. Uses the same adaptive 3-state layout as the Agents page.

**v0.8.6 change**: The former `/health` (Tool Health) page is merged into `/servers`. The `/health` route now redirects to `/servers`. All tool reliability data is accessible from the Tools tab of each server's detail panel.

**State 1 — No server selected (full-width table)**
- Columns: Server name, Owner, Tags, Status, Latency (sparkline trend), Uptime, Tools count, **Last Used**, **Last OK?**, Last Checked
  - **Last Used** (added v0.8.6): timestamp of the most recent tool call from traces (7-day window), sourced from `GET /api/health/servers/invocations`
  - **Last OK?** (added v0.8.6): whether the most recent tool call completed without error, also from invocations data
- Sortable on all columns
- Needs Attention banner when any server is `down` or `degraded`
- Status filter bar: All / Down / Degraded / Up with live counts
- Run Check button triggers `POST /api/health/check`

**State 2 — Server selected (280px sidebar + detail panel)**
- Detail panel has 4 tabs:
  - **About**: Editable description, owner, tags, transport type, runbook URL, last error — writes to `PUT /api/servers/metadata/{name}` on blur
  - **Tools**: All declared tools with name, description, input schema summary, and reliability metrics (total calls, errors, p99 latency, success rate). Populated on every health check cycle via `upsert_server_tools` (changed from v0.8.6 — was only on schema drift; now always updated so the tab is never empty after a fresh check). Tools that exist but were never called appear with 0 calls and their description. Fixed in v0.8.6: tools now correctly saved with `project_id` — was missing, causing the tab to appear empty.
  - **Health**: Uptime percentage, latency trend chart (Recharts AreaChart), last 15 health checks table (timestamp, status, latency, tools count, error)
  - **Consumers**: Which agents call this server, derived from lineage graph data

**Backend schema** (added to `postgres.py` DDL, idempotent):
- `server_metadata` table: `id`, `server_name` (UNIQUE), `description`, `owner`, `tags` (JSONB), `transport`, `runbook_url`, `project_id` (FK → projects), `created_at`, `updated_at`
- `server_tools` table: `id`, `server_name`, `tool_name` (UNIQUE per server), `description`, `input_schema` (JSONB), `first_seen_at`, `last_seen_at`

**API endpoints** (added):
- `GET /api/servers/metadata` — list all server metadata records
- `PUT /api/servers/metadata/{name}` — upsert metadata for a server
- `GET /api/servers/{name}/tools` — list declared tools for a server
- `PUT /api/servers/{name}/tools` — bulk-upsert tool declarations (used by SDK auto-capture)
- `GET /api/health/servers/invocations` — returns `last_called_at`, `last_call_ok`, `total_calls` per server name (7-day window from tool call traces in ClickHouse) — added v0.8.6

**Sidebar navigation**: "MCP Servers" entry added between Agents and Costs in the primary nav (`href="/servers"`, `Server` icon, indigo accent). The former "Tool Health" nav entry (`/health`) has been removed; `/health` redirects to `/servers` (changed v0.8.6).

### 4.5 Tool Health / Reliability Page

**v0.8.6 change**: This page has been merged into the MCP Servers Catalog (section 4.4). The `/health` route redirects to `/servers`. Tool reliability metrics are now surfaced in the **Tools** tab of each server's detail panel.

The previous standalone content is preserved here for reference only:
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
- **Source filter** (changed v0.8.6): The server/source filter previously labelled "All servers" is now labelled **"All sources"** — reflects that costs can originate from sub-agents acting as tool providers, not only from MCP servers
- **Next layer**: Trend charts, anomaly highlights, and budget alerts

### 4.8 Alerts Page
- **Alert timeline**: Newest first, severity color-coded
- **Filters**: By severity, status (firing/ack/resolved), server, type
- **Alert detail**: What triggered, when, context data, linked health check
- **Actions**: Acknowledge, resolve, snooze
- **Alert rules**: Configure thresholds per server or globally

### 4.6.1 Accept Invite Page (added 2026-03-19)

Path: `/accept-invite?token=<invite_token>`

- Password + confirm password fields
- On submit: calls `POST /api/accept-invite` (public route — no session required; handled by a dedicated Next.js API route handler, not the authenticated proxy)
- On success: redirects to `/login` with a success toast
- Design matches the login page (same card layout, same indigo CTA button)
- Middleware updated to allow `/accept-invite` through unauthenticated — it is excluded from the session-required redirect

### 4.6.1.1 Login Page — Demo Credentials Gating (changed 2026-03-21)

The login page (`dashboard/app/(auth)/login/page.tsx`) previously displayed demo credentials (email/password) unconditionally. As of 2026-03-21, demo credentials are only shown when `NODE_ENV !== "production"`. Production deployments no longer leak default passwords in the login UI.

### 4.6.2 NavProgress Bar (added 2026-03-19)

A thin indigo bar (`2px` height) at the top of every dashboard page:
- Starts animating when a sidebar navigation link is clicked
- Completes and fades out when the new route finishes loading
- Implemented via a `NavProgress` component that listens to Next.js App Router navigation events
- Color: `--indigo: #6366F1`

### 4.6.3 Route Loading Skeleton (added 2026-03-19)

`dashboard/app/(dashboard)/loading.tsx` — Next.js App Router `loading.tsx` convention:
- Shown instantly by the framework when a page segment is loading (concurrent rendering)
- Skeleton matches the expected page layout (card placeholders, table rows)
- Eliminates blank flash between navigation clicks and data load

### 4.7 Settings Page (redesigned 2026-03-19)

The Settings page uses a **left-nav + content panel** layout. Clicking a nav item isolates its section — no long scroll. Eight sections are available:

| Nav item | Content |
|---|---|
| General | Instance name, instance URL (read-only), current version; Debug Information block for SDK setup |
| API Keys | Table of active API keys with name, prefix, created date, last used; Create / Revoke actions; `.env` snippet showing `LANGSIGHT_API_KEY` and `LANGSIGHT_API_URL` for instant SDK instrumentation |
| Model Pricing | Provider-grouped pricing table; inline edit; "Add custom model" modal; "Custom" badge on user rows |
| Members | User list with role badges; Invite by email; Change role; Deactivate — Danger Zone pattern for destructive actions |
| Projects | Project list; Create project; Rename; Delete — Danger Zone |
| Notifications | Slack webhook URL input + "Test" button (calls `POST /api/alerts/test`); alert type toggles (see table below) |
| Audit Logs | Table of last 50 auth/RBAC events sourced from the `audit_logs` Postgres table; columns: Timestamp, Actor, Action, Resource, Result; no pagination in UI (use `GET /api/audit/logs?limit=&offset=` for bulk export). Changed from original: was an in-memory ring buffer (lost on restart); now persisted to DB via async write (2026-03-19). |
| Instance | Danger Zone for destructive instance-level actions |

#### Notifications section — alert type toggles

| Toggle key | Fires when |
|---|---|
| `mcp_down` | MCP server health check transitions to DOWN |
| `mcp_recovered` | MCP server transitions from DOWN back to UP |
| `agent_failure` | Agent session ends with `failed_calls > 0` |
| `slo_breached` | SLO evaluator returns `breached` status for any defined SLO |
| `anomaly_critical` | Z-score anomaly detector crosses the critical threshold (|z| >= 3) |
| `security_critical` | CVE or OWASP check returns a CRITICAL severity finding |

#### Audit Logs section — captured events

The `audit_logs` table is append-only. The UI shows the last 50 events; full history is available via `GET /api/audit/logs?limit=&offset=`. Events captured:

- User login (success and failure)
- API key created / revoked
- User role changed
- User invited / deactivated
- Project created / deleted
- Settings saved (Notifications config, Model Pricing updates)

---

## 5. SDK — Automatic Tool Schema Capture (added 2026-03-20)

When the LangSight SDK wraps an MCP client via `MCPClientProxy`, every call to `list_tools()` is intercepted. On each interception, the tool names, descriptions, and input schemas are fire-and-forget posted to `PUT /api/servers/{server_name}/tools`.

This means:
- The **Tools** tab in the MCP Servers catalog populates automatically as agents run — no health checker or manual registration is required.
- Tools that exist in a server's schema but were never called by an instrumented agent appear with `0 calls` alongside their description (schema is known, call metrics are not).
- Fail-open: if the LangSight backend is unreachable, `list_tools()` still returns normally to the agent.

---

## 6. Feature Summary by Phase

### Phase 1 — MVP (Weeks 1-5)
| Feature | Interface | Description |
|---|---|---|
| MCP server discovery | CLI (`init`) | Auto-detect from Claude/Cursor/VS Code configs |
| Health monitoring | CLI (`mcp-health`) | Availability, latency, schema tracking |
| Security scanning | CLI (`security-scan`) | CVE matching, OWASP Top 10, tool poisoning detection |
| Continuous monitoring | CLI (`monitor`) | Daemon mode with periodic health + security checks |
| Alerting | Slack + webhook | Threshold-based alerts with deduplication |
| Storage | Postgres + ClickHouse via Docker Compose | Dual-backend production topology |
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
| MCP server (meta) | MCP | Expose LangSight tools via MCP so agents can query health |
| Documentation | — | README, quickstart, framework guides, examples |
| PyPI publish | — | `pip install langsight` |

---

## 7. Slack Alert Format

```
🔴 LangSight Alert — MCP Server Down

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

→ Run: langsight mcp-health --server jira-mcp
```

```
🟡 LangSight Alert — Schema Change Detected

Server: filesystem-mcp
Tool: read_file
Change: Parameter "encoding" added (type: string, optional)

Previous schema hash: a3f8b2c1
New schema hash: 7d2e9f04

This may affect agents relying on the previous tool interface.

→ Run: langsight security-scan --server filesystem-mcp
```
