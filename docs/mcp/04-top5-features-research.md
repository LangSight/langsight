# Top 5 MCP Features — Competitor Research & Implementation Guide

**Date**: 2026-03-26
**Status**: Ready to implement

---

## Overview

| # | Feature | Best Competitor | Their Gap | Our Differentiation |
|---|---|---|---|---|
| 1 | **MCP Server Discovery** | Snyk Agent Scan (10+ clients) | Security-only, not monitoring | Universal discovery for health monitoring |
| 2 | **Continuous Health Monitoring** | OpenStatus (HTTP ping only) | No stdio, no protocol depth, no history | Full JSON-RPC daemon across all transports + ClickHouse history |
| 3 | **Schema Drift + Consumer Impact** | mcp-scan (SHA256 hash only) | No diff, no breaking-change classification, no consumer impact | Structural diff + breaking vs additive + "these agents break" |
| 4 | **MCP Server Scorecard (A-F)** | Nobody | Completely unoccupied | SSL Labs model applied to MCP: 5 dimensions, hard veto caps |
| 5 | **Root Cause Correlation** | Nobody | Completely unoccupied | Time-window join: failed agent session ↔ MCP health state |

---

## Feature 1: MCP Server Discovery

### What It Is
Auto-discover every MCP server configured across all IDEs on a developer's machine — without manual config.

### Who Does It Today

| Tool | Clients Covered | Approach | Purpose |
|---|---|---|---|
| **Snyk Agent Scan** | 10+ clients | Static registry of `(client, OS, config_path)` tuples in `well_known_clients.py` | Security scanning only |
| **VS Code** (built-in) | Claude Desktop only | Reads `claude_desktop_config.json` when `chat.mcp.discovery.enabled=true` | IDE integration |
| **MCP Hub** | None — explicit only | Requires `--config` argument, no auto-discovery | Server management |
| **mcp-use** | None | Programmatic only via `MCPClient.from_dict()` | Agent framework |
| **`langsight init`** (today) | **3 clients only + broken macOS path** | Hardcoded 3 paths | Config generation |

### Config File Map — All Clients, All OSes

| Client | macOS | Linux | Windows | Key Name |
|---|---|---|---|---|
| **Claude Desktop** | `~/Library/Application Support/Claude/claude_desktop_config.json` | `~/.config/Claude/claude_desktop_config.json` | `%APPDATA%\Claude\claude_desktop_config.json` | `mcpServers` |
| **Cursor** | `~/.cursor/mcp.json` | same | same | `mcpServers` |
| **VS Code** | `~/Library/Application Support/Code/User/mcp.json` | `~/.config/Code/User/mcp.json` | `%APPDATA%\Code\User\mcp.json` | **`servers`** (not mcpServers!) |
| **VS Code workspace** | `.vscode/mcp.json` in project root | same | same | `servers` |
| **Windsurf** | `~/.codeium/windsurf/mcp_config.json` | same | `%USERPROFILE%\.codeium\windsurf\mcp_config.json` | `mcpServers` |
| **Claude Code** (global) | `~/.claude.json` | same | `%USERPROFILE%\.claude.json` | `mcpServers` |
| **Claude Code** (project) | `.mcp.json` in project root | same | same | `mcpServers` |
| **Gemini CLI** | `~/.gemini/settings.json` | same | same | `mcpServers` |
| **Kiro** | `~/.kiro/settings/mcp.json` | same | same | `mcpServers` |
| **Zed** | `~/.config/zed/settings.json` | same | same | **`context_servers`** (different!) |
| **Cline** (VS Code ext) | `~/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json` | similar path | similar | `mcpServers` |
| **Continue.dev** | `~/.continue/mcpServers/*.json` | same | same | **Array format** (not object!) |

### Current Bug in `langsight init`

```python
# WRONG — Linux path used on macOS too
("Claude Desktop", Path("~/.config/claude/claude_desktop_config.json")),

# CORRECT for macOS
("Claude Desktop", Path("~/Library/Application Support/Claude/claude_desktop_config.json")),
```

### Implementation Plan

**Step 1 — `DiscoveryRegistry`**: Build a static map of `(client_name, platform, path, key_name, format)` tuples for all 10+ clients. Detect OS at runtime via `platform.system()`.

**Step 2 — Parse all 3 format variants**:
- Standard: `config["mcpServers"]` (dict) — Claude Desktop, Cursor, Windsurf, Claude Code, Gemini, Kiro, Cline
- VS Code: `config["servers"]` (dict) — different key name
- Zed: `config["context_servers"]` (dict) — completely different schema
- Continue.dev: `config["mcpServers"]` (array with `name` field)

**Step 3 — Deduplicate**: fingerprint by `command+args` hash — same server in multiple clients appears once.

**Step 4 — Project-local scan**: also check `.cursor/mcp.json`, `.mcp.json`, `.kiro/settings/mcp.json`, `.vscode/mcp.json` in CWD.

**Step 5 — Output**: unified `MCPServer` objects regardless of source.

---

## Feature 2: Continuous Health Monitoring

### What It Is
A daemon that checks all MCP servers on a schedule, stores history in ClickHouse, tracks trends, and alerts on degradation. Not a one-shot CLI command.

### Who Does It Today

| Tool | Transport | Frequency | History | Protocol Depth | Gap |
|---|---|---|---|---|---|
| **OpenStatus** | HTTP/SSE only | Configurable (1–10 min) | Tinybird (ClickHouse) | JSON-RPC `ping` only | No stdio, no schema tracking |
| **Grafana + OpenLIT** | Any (client-side) | Reactive only | Tempo + Mimir | Full call traces | Not proactive — only traces real agent calls |
| **Datadog** | Python MCP SDK | Reactive only | Datadog APM | Session + tools/list + call_tool spans | Not proactive |
| **New Relic** | Python agent | Reactive only | New Relic NRDB | MCP primitives patched | Not proactive |
| **MCP Hub** | stdio + SSE + HTTP | Live connection | **In-memory only** | Full capability tracking | No persistence, no alerting |
| **IBM Instana** | Server-side OTLP | Reactive only | Instana backend | `mcp.method.name` spans | Not proactive |

### The Critical Gap
Nobody runs a **synthetic daemon** that:
1. Proactively connects to MCP servers on a schedule (independent of agent traffic)
2. Runs a full protocol-level check across all transports including **stdio**
3. Stores time-series history in ClickHouse for trend analysis
4. Fires alerts on degradation

### The MCP Health Check Protocol (JSON-RPC level)

Full 4-step check sequence per poll:

```
Step 1: PING (reachability + latency, no session)
→ {"jsonrpc":"2.0","id":1,"method":"ping"}
← {"jsonrpc":"2.0","id":1,"result":{}}
Measure: round-trip latency ms. Timeout → DOWN.

Step 2: INITIALIZE (session negotiation + capability capture)
→ {"jsonrpc":"2.0","id":2,"method":"initialize","params":{
     "protocolVersion":"2025-03-26",
     "capabilities":{},
     "clientInfo":{"name":"langsight-monitor","version":"0.3.7"}
   }}
← captures: protocolVersion, capabilities, serverInfo.name/version

Step 3: INITIALIZED notification (required before listing)
→ {"jsonrpc":"2.0","method":"initialized"}   (no id — notification)

Step 4: TOOLS/LIST (schema snapshot)
→ {"jsonrpc":"2.0","id":3,"method":"tools/list"}
← {"jsonrpc":"2.0","id":3,"result":{"tools":[...]}}
Compute: schema hash, diff vs previous snapshot

Step 5: DISCONNECT cleanly
```

**Status classification**:
- `UP`: ping <500ms + initialize succeeds + tools/list matches last snapshot
- `DEGRADED`: ping ok but initialize slow (>1s) OR tool schema changed
- `DOWN`: ping timeout OR connection refused OR JSON-RPC error
- `STALE`: no check in >5 minutes

### Implementation Plan

**What already exists**: `langsight monitor` loop, `health/checker.py` concurrent checks, `health/schema_tracker.py` drift detection, ClickHouse health history. Foundation is there.

**What to add**:

1. **Daemon mode** — `langsight monitor --daemon` survives as background process, writes PID file. `langsight monitor --install` generates `systemd` / `launchd` unit file.

2. **Adaptive intervals** — healthy: 60s. DEGRADED: 15s. DOWN: 5s with exponential backoff. Per-server config in `.langsight.yaml`.

3. **Full protocol check** — upgrade `checker.py` to the 4-step sequence. Measure `ping_ms`, `initialize_ms`, `tools_list_ms` separately. Keep as background task so existing callers aren't blocked.

4. **StreamableHTTP transport** — add to `health/transports.py`. Many production MCP servers use this. Blocking without it.

5. **`notifications/tools/list_changed` subscription** — after initializing, subscribe to real-time tool change notifications. Nobody in the ecosystem uses this hook yet. Gives instant drift detection between polls.

6. **Hourly materialized view** in ClickHouse for trend charts (TTL: 90 days, already configured).

---

## Feature 3: Schema Drift + Consumer Impact

### What It Is
Detect when tool definitions change, classify whether the change breaks existing agents, show exactly what changed, and identify which agents are affected.

### Who Does It Today

| Tool | Drift Detection | Diff Output | Breaking vs Additive | Consumer Impact |
|---|---|---|---|---|
| **mcp-scan / Snyk** | SHA256 hash of name+description+inputSchema → W003 warning | None — "hash changed" only | None | None |
| **MCP Hub** | Real-time via `notifications/tools/list_changed` SSE | Emits new tool list | None | None |
| **Cisco MCP Scanner** | None | None | None | None |
| **LangSight today** | Schema hash in `health/schema_tracker.py` | Detects add/remove/description changes | None — binary only | None |

### The Complete Gap Nobody Fills

1. **Structural diff**: "parameter `limit` was removed from tool `query`" — not just "hash changed"
2. **Breaking vs additive classification**: removing a required param = BREAKING. Adding optional param = COMPATIBLE.
3. **Consumer impact**: "Tool `query` changed. Agents: inventory-agent, search-agent. 47 sessions in last 24h."
4. **Drift → reliability correlation**: "Schema changed at 14:23. Error rate: 2% → 34% at 14:25."
5. **`outputSchema` tracking**: added to MCP spec 2025. Nobody tracks this field.
6. **`notifications/tools/list_changed` hook**: MCP spec provides this. Nobody uses it for monitoring.

### Breaking Change Classifier

```python
def classify_drift(old_tools: list[Tool], new_tools: list[Tool]) -> SchemaDrift:
    changes = []

    for old_tool in old_tools:
        new_tool = find_by_name(new_tools, old_tool.name)

        if new_tool is None:
            changes.append(Change(type=BREAKING, kind="tool_removed", tool=old_tool.name))
            continue

        old_required = set(old_tool.inputSchema.get("required", []))
        new_required = set(new_tool.inputSchema.get("required", []))

        # Required param removed → BREAKING (agents send it, now rejected)
        for p in old_required - new_required:
            changes.append(Change(type=BREAKING, kind="required_param_removed", param=p))

        # Required param added → BREAKING (agents don't know to send it)
        for p in new_required - old_required:
            changes.append(Change(type=BREAKING, kind="required_param_added", param=p))

        # Param type changed → BREAKING
        for p, schema in old_tool.inputSchema.get("properties", {}).items():
            new_schema = new_tool.inputSchema.get("properties", {}).get(p)
            if new_schema and new_schema.get("type") != schema.get("type"):
                changes.append(Change(type=BREAKING, kind="param_type_changed", param=p))

        # New optional param → COMPATIBLE (agents still work)
        new_props = set(new_tool.inputSchema.get("properties", {}).keys())
        old_props = set(old_tool.inputSchema.get("properties", {}).keys())
        for p in new_props - old_props:
            if p not in new_required:
                changes.append(Change(type=COMPATIBLE, kind="optional_param_added", param=p))

        # Description changed → WARNING (potential poisoning vector)
        if old_tool.description != new_tool.description:
            changes.append(Change(type=WARNING, kind="description_changed"))

    for new_tool in new_tools:
        if not find_by_name(old_tools, new_tool.name):
            changes.append(Change(type=COMPATIBLE, kind="tool_added", tool=new_tool.name))

    return SchemaDrift(changes=changes, has_breaking=any(c.type == BREAKING for c in changes))
```

### Consumer Impact Query (ClickHouse)

```sql
SELECT
    agent_name,
    session_id,
    count()                       AS call_count,
    countIf(status = 'error')     AS error_count,
    avg(latency_ms)               AS avg_latency_ms
FROM mcp_tool_calls
WHERE
    server_name = :server_name
    AND tool_name  = :tool_name
    AND timestamp >= now() - INTERVAL 24 HOUR
GROUP BY agent_name, session_id
ORDER BY call_count DESC
```

### Implementation Plan

**What already exists**: `health/schema_tracker.py` stores hash, detects additions/removals/description changes. `server_tools` table in Postgres.

**What to add**:
1. New `schema_drift_events` ClickHouse table: `server_name`, `tool_name`, `drift_type`, `change_kind`, `old_value`, `new_value`, `detected_at`
2. Breaking-change classifier in `health/schema_tracker.py` (above algorithm)
3. New endpoint `GET /api/health/servers/{name}/drift-impact`
4. Alert severity: BREAKING → critical, COMPATIBLE → info, description change → warning
5. `notifications/tools/list_changed` subscription in health checker
6. "Schema History" timeline in `/health` server detail page

---

## Feature 4: MCP Server Scorecard (A-F Grade)

### What It Is
A single shareable letter grade for each MCP server. Like SSL Labs A-F grades but for MCP servers.

### Who Does It Today

| Tool | Score | Dimensions | Verdict |
|---|---|---|---|
| **MCP Doctor** | Healthy/Warnings/Critical (counts) | Tool description design quality | Design linter, not health |
| **MCP Inspector** | None | Manual test execution | Debugger, not monitor |
| **LangSight today** | Security `4/10` (spec only) | Security only | One dimension, not live |
| **Runlayer** | Binary: verified/unverified | Security scan only | Pass/fail |
| **Nobody** | **A-F composite grade** | **All dimensions** | **Gap** |

### Scoring Model (SSL Labs approach)

**5 dimensions, weighted:**

| Dimension | Weight | Key Signals |
|---|---|---|
| **Availability** | 30% | Uptime % (7-day rolling), consecutive failures, MTTR |
| **Security** | 25% | OWASP MCP Top 10 findings, CVEs, auth presence, poisoning |
| **Reliability** | 20% | Error rate, latency variance (CV = stddev/mean), timeout rate |
| **Schema Stability** | 15% | Drift frequency, breaking vs additive changes, untracked mutations |
| **Performance** | 10% | p99 latency vs 30-day baseline ratio |

**Scoring algorithm:**

```python
def compute_availability_score(uptime_7d: float) -> float:
    return min(100.0, uptime_7d * 100)

def compute_security_score(findings: list[SecurityFinding]) -> float:
    score = 100.0
    deductions = {Severity.CRITICAL: 40, Severity.HIGH: 20, Severity.MEDIUM: 10, Severity.LOW: 5}
    for f in findings:
        score -= deductions[f.severity]
    return max(0.0, score)

def compute_reliability_score(error_rate_pct: float, latency_cv: float) -> float:
    error_score    = max(0.0, 100.0 - error_rate_pct * 10)
    variance_score = max(0.0, 100.0 - latency_cv * 100)
    return error_score * 0.6 + variance_score * 0.4

def compute_schema_score(drift_events_7d: list[SchemaDrift]) -> float:
    if not drift_events_7d:                                    return 100.0
    if all(d.type == DriftType.COMPATIBLE for d in drift_events_7d): return 80.0
    if len(drift_events_7d) <= 2:                              return 60.0
    if len(drift_events_7d) <= 5:                              return 30.0
    return 0.0

def compute_performance_score(p99_ms: float, baseline_p99_ms: float) -> float:
    ratio = p99_ms / baseline_p99_ms if baseline_p99_ms else 1.0
    for threshold, score in [(1.0, 100), (1.5, 80), (2.0, 60), (3.0, 40), (5.0, 20)]:
        if ratio <= threshold:
            return float(score)
    return 0.0

def numeric_to_grade(score: float) -> str:
    if score >= 90: return "A"
    if score >= 80: return "B"
    if score >= 65: return "C"
    if score >= 50: return "D"
    return "F"
```

**Hard veto caps (override numeric score — the SSL Labs key insight):**

```python
def apply_hard_caps(grade: str, s: ServerState) -> str:
    # Automatic F — fatal flaws
    if s.consecutive_failures >= 10:   return "F"   # effectively dead
    if s.has_active_critical_cve:      return "F"   # known exploited
    if s.is_confirmed_poisoned:        return "F"   # tool description tampered

    # Cap at D
    if s.uptime_7d < 0.90:            grade = min_grade(grade, "D")

    # Cap at C
    if not s.has_authentication:       grade = min_grade(grade, "C")
    if s.untracked_drifts > 3:         grade = min_grade(grade, "C")

    # Cap at B
    if s.has_critical_security_finding: grade = min_grade(grade, "B")
    if s.p99_ms > 5000:                grade = min_grade(grade, "B")

    # A+ eligibility
    if (grade == "A"
            and s.uptime_7d >= 0.999
            and not s.any_security_findings
            and s.schema_drifts_7d == 0):
        return "A+"

    return grade
```

**SLA reference for availability scoring:**

| Uptime % | Downtime/month | Grade range |
|---|---|---|
| ≥ 99.99% | < 4 min | A+ eligible |
| ≥ 99.9% | < 43 min | A |
| ≥ 99.5% | < 3.6 hr | B |
| ≥ 99.0% | < 7.3 hr | B/C |
| ≥ 95.0% | < 36 hr | C/D |
| < 95.0% | > 36 hr | D/F |

### Implementation Plan

1. **New file**: `src/langsight/health/scorecard.py` — `MCPServerScorecard` model + `ScorecardEngine`
2. **New endpoint**: `GET /api/health/servers/{name}/scorecard` → `{score, grade, dimensions, cap_applied, computed_at}`
3. **CLI**: `langsight mcp-health --scorecard` — A-F badge per server in Rich table
4. **Daily snapshots**: ClickHouse `server_scorecard_history` — "grade over time" trend chart
5. **Dashboard**: Replace status dot in `/health` with A-F badge (green=A/B, yellow=C, orange=D, red=F)
6. **Shareable report**: `langsight scorecard --server postgres-mcp --format html` — self-contained HTML like SSL Labs

---

## Feature 5: Root Cause Correlation

### What It Is
When an agent session fails, automatically determine whether an MCP server was degraded at that time. "Agent X failed at 02:14 because postgres-tool was DOWN from 02:11–02:19."

### Who Does It Today

| Tool | Session Tracing | MCP Health | Cross-Signal Correlation |
|---|---|---|---|
| **Runlayer** | Gateway audit trail | No health history | No — security focus |
| **Braintrust** | Full agent traces | No | No — needs external infra tool |
| **Laminar** | Full traces + AI error diagnosis | No | No — agent-only |
| **Datadog Watchdog** | APM traces | Infrastructure metrics | Yes — for HTTP services, NOT MCP-aware |
| **LangSight today** | Full sessions in ClickHouse | Health history in ClickHouse | **The data is there. The join is missing.** |

### How Datadog Does It (closest analog)
Datadog Watchdog builds a service dependency map from distributed traces, then looks for anomalies that preceded a symptom working backwards up the call tree. The earliest unexplained anomaly = root cause.

LangSight equivalent: for each failed session, walk the `server_name` fields in tool call spans, find health records for those servers in the same time window, rank by proximity + severity.

### The Algorithm (time-window join)

```python
async def correlate_session_to_mcp_health(
    session_id: str,
    window_buffer_seconds: int = 300,
) -> list[RootCauseCorrelation]:

    session = await storage.get_session(session_id)
    if session.health_tag not in ("tool_failure", "budget_exceeded", "loop_detected"):
        return []

    # All MCP servers called during this session (from ToolCallSpan.server_name)
    servers_called = await storage.get_servers_called_in_session(session_id)

    correlations = []
    for server_name, call_stats in servers_called.items():

        # Health records for this server in the ±5 min window around session failure
        health_records = await storage.get_health_records(
            server_name=server_name,
            from_ts=session.started_at - timedelta(seconds=window_buffer_seconds),
            to_ts=session.ended_at   + timedelta(seconds=window_buffer_seconds),
        )

        worst = min((h.status for h in health_records), default=ServerStatus.UP)
        if worst == ServerStatus.UP:
            continue

        confidence = _score_confidence(session, call_stats, health_records, worst)

        correlations.append(RootCauseCorrelation(
            session_id=session_id,
            server_name=server_name,
            health_status=worst,
            confidence=confidence,
            explanation=_explain(session, server_name, worst, call_stats),
        ))

    return sorted(correlations, key=lambda c: c.confidence, reverse=True)


def _score_confidence(session, call_stats, health_records, worst) -> float:
    score = 0.0

    # Base: how bad was the server?
    score += 0.5 if worst == ServerStatus.DOWN     else 0.0
    score += 0.3 if worst == ServerStatus.DEGRADED else 0.0

    # Error rate on calls to this server during session
    error_rate = call_stats.error_count / max(call_stats.call_count, 1)
    score += error_rate * 0.3

    # Temporal proximity of worst health event to session failure
    closest_bad = min(
        (h for h in health_records if h.status != ServerStatus.UP),
        key=lambda h: abs((h.checked_at - session.ended_at).total_seconds()),
        default=None,
    )
    if closest_bad:
        delta_s = abs((closest_bad.checked_at - session.ended_at).total_seconds())
        score += max(0.0, 1.0 - delta_s / 300) * 0.2

    return min(1.0, score)
```

**Confidence levels:**

| Score | Meaning | Label |
|---|---|---|
| 0.9–1.0 | Server DOWN + all calls failed | RCA confirmed |
| 0.7–0.9 | Server DEGRADED + >50% calls failed | RCA likely |
| 0.4–0.7 | Server DEGRADED + some calls failed | RCA possible |
| < 0.4 | Weak temporal overlap | RCA uncertain |

### Blast Radius Query

"MCP server X was down for 8 minutes. How many sessions were affected?"

```sql
SELECT
    count(DISTINCT session_id) AS affected_sessions,
    count(DISTINCT agent_name) AS affected_agents,
    countIf(status = 'error')  AS failed_tool_calls,
    count()                    AS total_tool_calls
FROM mcp_tool_calls
WHERE
    server_name = :server_name
    AND timestamp BETWEEN :outage_start AND :outage_end
```

### Implementation Plan

**What already exists**: Agent sessions in ClickHouse, MCP health history in storage, `langsight investigate` with MCP health evidence. All data present. The join is the missing piece.

**What to add**:
1. **`investigate` v2** — extend `cli/investigate.py` to accept `--session-id`, run the time-window join, include `correlated_health_events` + confidence scores in Claude evidence bundle
2. **New endpoint**: `GET /api/sessions/{id}/root-cause` → `list[RootCauseCorrelation]` sorted by confidence
3. **New endpoint**: `GET /api/health/servers/{name}/blast-radius?from=&to=` → affected sessions/agents
4. **Session detail UI** — new "Root Cause" tab in `/sessions/{id}`: server health badges per tool call, confidence score, natural-language explanation
5. **Overview dashboard** — "Recent Root Causes" panel: last 5 auto-correlated failures

---

## Implementation Priority

| Priority | Feature | Effort | Existing | To Build |
|---|---|---|---|---|
| **P0** | Fix `langsight init` discovery | Small | 3 clients, broken macOS path | 7 more clients, fix path, project-local scanning |
| **P0** | StreamableHTTP transport | Medium | stdio + SSE only | New transport in `health/transports.py` |
| **P1** | Schema Drift structural diff | Medium | Hash detection exists | Classifier, structured diff, consumer impact query |
| **P1** | MCP Server Scorecard | Medium | Security score in spec only | `health/scorecard.py`, API endpoint, A-F UI badge |
| **P2** | Continuous monitoring daemon | Medium | `langsight monitor` exists | Daemon mode, adaptive intervals, change notifications |
| **P2** | Root Cause Correlation | Medium | Sessions + health history exist | Time-window join, confidence scoring, API + UI tab |

---

## What LangSight Does That Nobody Else Does

1. **Schema drift → consumer impact**: "Tool X changed, these agents break, here's their error rate trend"
2. **A-F scorecard across 5 dimensions**: first composite health grade for MCP servers in the market
3. **Root cause correlation**: "Agent failed because MCP server was down" — automatic, timestamped, confidence-scored
4. **Continuous stdio monitoring**: nobody else runs scheduled health checks on stdio-transport MCP servers
5. **Breaking vs additive drift classification**: not just "changed" but "will this break your agents?"

These 5 capabilities combined = **"Datadog for MCP servers"** — doesn't exist anywhere in the market as OSS.
