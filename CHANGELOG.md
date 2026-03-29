# Changelog

All meaningful changes to LangSight are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added
- **Docs: `docs-site/alerts.mdx`** — new "Alerts & Notifications" reference page covering both alert pipelines (CLI monitor and API/Dashboard), all eight alert types with their toggle keys and deduplication rules, Slack webhook configuration priority order (Dashboard > YAML > env var), Alert Inbox lifecycle (firing → acknowledged → snoozed → resolved), inbox REST API (`GET /api/alerts/inbox`, `POST /api/alerts/{id}/ack`, `POST /api/alerts/{id}/resolve`, `POST /api/alerts/{id}/snooze`), structured log events for debugging, and end-to-end test instructions.
- **Docs: `docs-site/mint.json`** — `alerts` added to the "Reliability Features" navigation group.

### Changed
- **Docs: `docs-site/self-hosting/configuration.mdx`** — "Slack alert configuration" section updated to reflect that the webhook URL and alert toggles are now persisted to Postgres (not in-memory), the full alert type table updated to include `anomaly_warning` and `security_high` types added in v0.10.0, and a cross-reference to the new `/alerts` page added.
- **Docs: `docs-site/cli/monitor.mdx`** — added `<Note>` cross-referencing the new Alerts & Notifications page for alert type details and deduplication behaviour.

## [0.10.1] - 2026-03-29

### Fixed
- `--json` flags (`mcp-health`, `scorecard`, `scan`) now produce clean stdout — structlog routed to stderr
- All mypy type errors resolved: bool casts on storage returns, `dict[str, Any]` type params, stale `# type: ignore` comments removed
- `factory.py`: removed reference to non-existent `StorageConfig.sqlite_path` attribute

### Changed
- Pre-push hook now mandatorily checks mypy and ruff format — type errors and formatting issues can no longer reach CI

## [0.10.0] - 2026-03-29

### Added
- **`langsight scorecard` CLI command** (`src/langsight/cli/scorecard.py`) — A-F composite health grades for MCP servers. Aggregates uptime, latency percentiles, error rate, and security findings into a single grade per server. Was referenced in docs but never shipped; now implemented and registered in the CLI.
- **`POST /api/investigate` endpoint** — AI-powered root-cause analysis (RCA) for MCP server incidents. Accepts a server name and optional time window; returns a structured RCA report including probable causes, blast radius, and recommended remediation steps. Backed by the Claude Agent SDK.
- **Persistent Alert Inbox** (`fired_alerts` Postgres table) — alerts now persist beyond process lifetime with a full lifecycle: `firing` → `acknowledged` → `resolved` or `snoozed`. New REST API: `GET /api/alerts/inbox`, `POST /api/alerts/{id}/ack`, `POST /api/alerts/{id}/resolve`, `POST /api/alerts/{id}/snooze`. Dashboard: new `/alerts` page with inbox view.
- **GitHub Actions marketplace action** (`.github/actions/langsight-scan/`) — zero-config action that runs `langsight scan --ci` as a pre-deploy gate. Fails the workflow on CRITICAL or HIGH security findings. Published to the GitHub Actions marketplace.

### Fixed
- **SQLite WAL mode + busy_timeout in `SQLiteBackend.open()`** — concurrent writes from `langsight scan` no longer raise `OperationalError: database is locked`. WAL journal mode and a 5-second busy timeout are now set on every new SQLite connection.

### Tests
- 57 new unit tests for the `POST /api/investigate` router — 100% line coverage on the investigate module.
- Scorecard CLI tests covering grade computation, `--json` output, and empty-history edge cases.
- SQLite WAL concurrency tests validating that parallel writes complete without lock contention.

## [0.9.2] - 2026-03-27

### Added
- **`langsight scan` command** — zero-Docker MCP health + security audit in a single command. Auto-discovers MCP server configs from Claude Desktop, Cursor, VS Code, and Windsurf IDE config files (or reads `.langsight.yaml` if present). Runs health checks and security scans in parallel and renders a combined Rich table: server name, status, latency, tools count, and security findings count. A second findings table lists severity, server, category, and finding text. Pass `--fix` to show remediation steps inline. Pass `--ci` to exit `1` on any CRITICAL or HIGH finding for use as a CI/CD gate. No Postgres, ClickHouse, or Docker required — all results are persisted to SQLite.
- **SQLite storage backend** (`src/langsight/storage/sqlite.py`) — local SQLite backend used exclusively by `langsight scan`. Stores health check results (`health_results`), tool list snapshots (`schema_snapshots`), and schema drift events (`schema_drift_events`). Default path: `~/.langsight/scan.db`; override with `--db`. Schema drift is detected automatically across consecutive scans.
- **Docs: `docs-site/cli/scan.mdx`** — full reference page for `langsight scan` covering auto-discovery IDE config table, example terminal output, all flags with `<ParamField>` docs, CI/CD integration with GitHub Actions example, SQLite history section, JSON output schema, and comparison table vs `mcp-health` / `security-scan`.
- **Docs: `docs-site/mint.json`** — `cli/scan` added as the first entry in the CLI Reference navigation group, reflecting its role as the zero-friction entry point.

## [0.9.1] - 2026-03-27

### Added
- **Schema Drift Detection — dashboard UI** — the MCP Servers detail panel **Drift tab** now shows a full structural diff UI: summary chips (`N breaking · N warning · N compatible`), per-event cards with coloured left borders and BEFORE/AFTER value boxes, `change_kind` badges, and an **Affected Agents (24h)** section that auto-loads which agents called the changed tool. A **"View full schemas (before/after)"** toggle reveals syntax-highlighted JSON of the complete tool input schema. Docs: `docs-site/mcp/schema-drift.mdx` (Dashboard section added).
- **Tool Schema Viewer** — new **Schema tab** in the MCP Servers detail panel showing every tool's full input schema: parameter names, types, required/optional badges, descriptions, enum value chips, and a raw JSON toggle. Schemas are captured automatically when any instrumented agent calls `list_tools()` — no manual registration. REST API: `GET /api/servers/{name}/tools`. Docs: `docs-site/mcp/tool-schemas.mdx`.
- **Blast Radius** — new panel at the top of the MCP Servers **Health tab** showing outage impact in real time. Computes which agents and sessions are affected based on last 24h tool-call traffic. Classifies severity as `CRITICAL`, `HIGH`, `MEDIUM`, or `LOW`. Shows a red "Active Outage" banner for `DOWN`/`DEGRADED` servers and a grey pre-emptive view for `UP` servers. Python module: `src/langsight/rca/blast_radius.py`. REST API: `GET /api/health/servers/{name}/blast-radius`. Docs: `docs-site/mcp/blast-radius.mdx`.
- **Prevention Config (Guards)** — new **Guards tab** in the agent detail panel for configuring per-agent safety controls: loop detection (threshold, `warn`/`terminate` action, `max_steps`), budget controls (hard cost cap, soft alert threshold, max wall time), and circuit breaker (failure threshold, cooldown, half-open max calls). Supports two-level config inheritance: project default + agent-level override. REST API: `GET/PUT/DELETE /api/agents/{name}/prevention-config`, `GET/PUT /api/projects/prevention-config`. Docs: `docs-site/agents/prevention-config.mdx`.
- **Docs site navigation** — new "Agents" nav group added to `docs-site/mint.json`; `mcp/tool-schemas` and `mcp/blast-radius` added to the "MCP Monitoring" group.

## [0.9.0] - 2026-03-27

### Added
- **Embedded monitor loop in `langsight serve`** — `langsight serve` now starts a background health check loop alongside the API. Before v0.9.0, production deployments required two separate processes (`langsight serve` + `langsight monitor`). Now one command starts everything. The loop runs every 60 seconds by default and writes results to the same ClickHouse and Postgres instances as the API.
- **`LANGSIGHT_MONITOR_ENABLED` env var** — controls whether `langsight serve` starts the embedded monitor loop (default: `true`). Set `false` to run the API without a background health check, then use a separate `langsight monitor` process (advanced HA deployments).
- **`LANGSIGHT_MONITOR_INTERVAL_SECONDS` env var** — configures the health check cycle interval for the embedded monitor (default: `60`).
- **`monitor_enabled` and `monitor_interval_seconds` config keys** — equivalent YAML config keys in `.langsight.yaml`.
- **Docs: MCP authentication guide** — `docs-site/mcp/authentication.mdx` covering all four auth patterns: no auth (stdio), Bearer token (HTTP/SSE), OAuth via mcp-remote, and env var injection.
- **Docs: MCP Servers dashboard guide** — `docs-site/mcp/mcp-servers-dashboard.mdx` covering the unified `/servers` page, all four detail panel tabs, Run Check button, and Last Ping vs Last Tool Call distinction.
- **Docs: Production deployment guide** — `docs-site/self-hosting/production.mdx` covering the embedded monitor, Docker Compose setup for stdio and HTTP servers, separate monitor pattern, and CI/CD pre-deploy health checks.

### Changed
- **`langsight serve` output** — startup message now includes embedded monitor status: `Monitor: enabled (60s interval)` or `Monitor: disabled`.
- **`monitor_enabled` and `monitor_interval_seconds`** added to the full `.langsight.yaml` schema in configuration docs.
- **`cli/serve.mdx`** updated to document the embedded monitor and the two new env vars.

## [0.8.6] - 2026-03-27

### Added
- **`GET /api/health/servers/invocations`** — new endpoint returning `last_called_at`, `last_call_ok`, and `total_calls` per server name, derived from tool call traces over a 7-day window in ClickHouse.
- **MCP Servers: "Last Used" and "Last OK?" columns** — the `/servers` table now shows when each server was last invoked by an agent and whether that call succeeded, sourced from the new invocations endpoint.
- **Agents → Servers tab** — the agent detail panel gains a fifth "Servers" tab listing every MCP server the agent has called: server name, tools count, total calls, error count, and health status. Gives an agent-first view of infrastructure dependencies.

### Changed
- **Tool Health page merged into MCP Servers** — `/health` now permanently redirects to `/servers`. Tool reliability metrics are accessible from the Tools tab of each server's detail panel. The standalone Tool Health nav entry has been removed.
- **Cost page source filter renamed** — the "All servers" filter in the Cost Analytics page is now labelled "All sources" to reflect that costs can originate from sub-agents acting as tool providers, not only from MCP servers.
- **`upsert_server_tools` called on every health check** — previously only called when schema drift was detected. Now called unconditionally so the MCP Servers → Tools tab is populated after the first health check, not only after a schema change.

### Fixed
- **Tools tab `project_id` bug** — tools were not saved with `project_id`, causing the MCP Servers → Tools tab to appear empty for project-scoped installs. `upsert_server_tools` now correctly stamps `project_id` on every tool record.

## [0.8.5] - 2026-03-27

### Fixed
- **`_parse_tools()` handles `inputSchema` as JSON string** — MCP servers that return `inputSchema` as a serialised JSON string (e.g. atlassian-mcp) instead of a dict now parse correctly. `_parse_tools()` calls `json.loads()` when it detects a string value, making schema tracking robust against non-compliant server implementations. Previously these servers would cause a `TypeError` during schema hash computation and surface as schema drift on every check.

## [0.8.4] - 2026-03-27

### Added
- **`health_tool` backend probe** — new per-server config fields `health_tool` and `health_tool_args`. When set, `ping()` calls the specified tool (with the given args) after `tools/list` to verify the backend application is alive. A failing probe marks the server `DEGRADED` instead of `DOWN`, preserving the semantic distinction: `DOWN` means the MCP layer is unreachable; `DEGRADED` means the MCP layer is up but the backend is down. The probe is optional — omitting `health_tool` skips it.
- **`MCPHealthToolError` exception** — raised by `checker.py` when the health tool probe fails (tool invocation error, unexpected response, or timeout). Caught in `ping()` to produce the `DEGRADED` status.

### Config example
```yaml
servers:
  - name: datahub
    transport: streamable_http
    url: https://datahub-mcp.internal.company.com/mcp
    health_tool: search_entities
    health_tool_args:
      query: "test"
      count: 1
    timeout_seconds: 15
```

## [0.8.1] - 2026-03-26

### Added
- **Project-scoped API keys** — `ApiKeyRecord` gains `project_id: str | None`. Creating an API key in the dashboard now lets you select a project. That key automatically scopes all CLI commands and SDK calls to that project — no `--project` flag, no config changes needed.
- **`LangSightConfig` project fields** — two new fields: `project: str = ""` (human-readable slug, display only) and `project_id: str = ""` (UUID fallback when the API key carries no project). Set via `.langsight.yaml` or `LANGSIGHT_PROJECT_ID` env var.
- **`HealthChecker` project stamping** — `HealthChecker` now accepts `project_id` at construction and stamps all `health_results` rows with it. Previously health results written via the CLI had no project tag.

### Changed
- **`get_active_project_id` priority order updated**: API key's embedded `project_id` is now highest priority (was not consulted before). Full order: (1) API key project_id, (2) `.langsight.yaml` project_id, (3) query param, (4) admin/auth-disabled → None, (5) non-admin without project → HTTP 400.

### Schema
- `api_keys` table: `project_id UUID NULL` added via `ALTER TABLE … ADD COLUMN IF NOT EXISTS`. Existing keys retain `NULL` (global scope). Auto-applied on API startup, idempotent.

## [0.8.0] - 2026-03-26

### Added
- **MCP Server Discovery** — `langsight init` now auto-discovers 10+ IDE clients: Claude Desktop (correct macOS path `~/Library/Application Support/Claude/`), Cursor, VS Code, Windsurf, Claude Code, Gemini CLI, Kiro, Zed, and Cline. Handles all config key variants: `mcpServers`, `servers` (VS Code), and `context_servers` (Zed). Also scans project-local configs. Runs a first health check immediately after discovery. New `--skip-check` flag to bypass the post-discovery check.
- **`langsight add` command** — new CLI command for manual MCP server registration. Supports `--url` for HTTP/production servers and `--command` for stdio/local servers. Runs a connection test on add and displays discovered tools. Additional options: `--header KEY=VALUE`, `--env KEY=VALUE`, `--args`, `--skip-check`, `--config`.
- **Schema drift structural diff** — drift detection now produces a structured per-change diff instead of a bare hash comparison. Every change is classified as BREAKING (`tool_removed`, `required_param_removed`, `required_param_added`, `param_type_changed`), COMPATIBLE (`tool_added`, `optional_param_added`), or WARNING (`description_changed`). New ClickHouse table: `schema_drift_events`. New API endpoints: `GET /api/health/servers/{name}/drift-history` and `GET /api/health/servers/{name}/drift-impact`.
- **MCP Server Scorecard** — new `GET /api/health/servers/{name}/scorecard` endpoint returns an A-F composite health grade across 5 weighted dimensions: Availability (30%), Security (25%), Reliability (20%), Schema Stability (15%), Performance (10%). Hard veto caps override the score to F on any of: 10+ consecutive failures, active critical CVE, or confirmed poisoning detection.
- New domain models: `DriftType` enum (BREAKING, COMPATIBLE, WARNING), `SchemaChange`, and `SchemaDriftEvent`.

### Fixed
- `langsight init` macOS path for Claude Desktop corrected from `~/.config/claude/` (Linux path) to `~/Library/Application Support/Claude/`.
- `langsight init` transport detection replaced fragile substring match on full URL with URL path segment parsing — eliminates false-positive transport classifications on non-standard server URLs.

## [0.7.3] - 2026-03-26

### Fixed
- SDK: `buffer_span()` now calls `_ensure_flush_loop()` on every invocation — previously the flush loop was defined but never started, causing all spans to accumulate in memory and only deliver at process exit via `atexit`. Spans now flush every 1 s in real time. `asyncio.get_running_loop()` is used so the call is a safe no-op in sync contexts. 6 new tests added.
- API: `POST /ingest/spans` now validates `session_id` as a UUID4 at the ingestion boundary, returning HTTP 422 for non-UUID values (e.g. `"live-test-2"`) — previously arbitrary strings passed through and polluted session-keyed dashboard views. SDK always generates UUID4 via `_new_session_id()`.

## [0.7.2] - 2026-03-26

### Fixed
- SDK: `buffer_span()` now calls `_ensure_flush_loop()` on every invocation — previously the flush loop was defined but never started, causing all spans to accumulate in memory and only deliver at process exit via `atexit`. Spans now flush every 1 s in real time. `asyncio.get_running_loop()` is used so the call is a safe no-op in sync contexts.

## [0.7.1] - 2026-03-26

### Fixed
- Live page: SSE contract corrected — backend `span:new` payload now includes `started_at`; frontend listener switched from broken `onmessage`/sessions handler to `addEventListener("span:new")`
- Live page: `mv_agent_sessions` ClickHouse materialized view rebuilt with correct `*State`/`*Merge` AggregatingMergeTree combinators — previously produced incorrect session aggregates
- Live page: `mergeSpan`, `SpanEvent`, and `LiveRow` extracted to `lib/live-utils.ts` for testability; 22 TypeScript unit tests added
- Tests: 11 Python SSE contract tests added covering `span:new` payload shape
- Integration tests: `POSTGRES_PORT=5433` now passed to `postgres-mcp` subprocess — previously the subprocess inherited the wrong default port, causing integration tests to fail when postgres-mcp was running

## [0.7.0] - 2026-03-26

### Breaking Changes
- `InvestigateConfig.api_key` removed from `.langsight.yaml` schema — LLM API keys must now be supplied via environment variables (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`). Any `.langsight.yaml` files containing `investigate.api_key` must be updated before upgrading.
- `mv_agent_sessions` ClickHouse materialized view rebuilt with new schema (`project_id` column added) — operators running self-hosted installs must drop and recreate this view on upgrade (migration script provided in `scripts/migrate_0_7_0.sh`).

### Security
- S2: Playwright auth bypass (`/api/auth/debug`) now gated by `NODE_ENV !== production` — endpoint was reachable in production builds
- H1/SSRF: SSRF validation added to all outbound webhook URLs in `slack.py` and `webhook.py` — private/loopback/link-local destinations are now rejected
- H2/PII: email address removed from login-success audit log entries — was written in plaintext to `audit_logs`
- H4: Invite password minimum raised from 8 to 12 characters — now matches the admin bootstrap policy
- H5/H6: API (port 8000) and dashboard (port 3003) now bind to `127.0.0.1` only in `docker-compose.yml` — previously bound to `0.0.0.0`, exposing unauthenticated ports on all interfaces
- H7/B1: `health_results` table gains `project_id` column via `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` — existing installs are unaffected; new column enables per-tenant scoping of health data
- C2: `mv_agent_sessions` materialized view rebuilt with `project_id` — previously all tenants' sessions were mixed in the view, breaking tenant isolation for session-level aggregates
- C3: `api_key` removed from `InvestigateConfig` — LLM keys via environment variables only, never stored in config files on disk
- H1: `get_session_health_tag()` now scoped by `project_id` — previously returned health tags across all projects sharing the same session ID
- M2/B3: `hmac.compare_digest` replaces plain `in` operator for environment key comparison — prevents timing-oracle attacks on API key validation
- H2: Startup warning emitted when `LANGSIGHT_METRICS_TOKEN` is not set — operators are no longer silently running with an unprotected metrics endpoint
- M7: `audit_logs` table gains `project_id` column via `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` — enables per-tenant audit log isolation
- H4: `SELECT *` on `users` table replaced with an explicit safe column list — `password_hash` is now excluded from general-purpose user queries and remains only in the authentication code path
- Settings `PUT /api/settings` now routes through the authenticated proxy — was previously writable without authentication
- Quickstart script now generates a random admin password instead of the hardcoded default `"admin"`
- Dashboard admin credentials removed from the `dashboard` container definition in `docker-compose.yml`

### Fixed
- Integration tests: postgres-mcp reachability skip guard now checks port 5433 (not 5432) — test suite was skipping integration tests incorrectly when postgres-mcp was running
- Dashboard: sidebar test labels corrected to `Dashboard` (was `Overview`) — caused test failures after nav label rename
- Lineage graph: test assertions updated to match new edge schema — tests were asserting stale field names

## [0.6.2] - 2026-03-25

### Security
- `GET /api/settings` now requires authentication — was publicly readable without any API key
- `PUT /api/settings` now requires authentication + admin role — was writable by anyone with network access
- SSE `span:new` events now include `project_id` in the payload — without it, all project-scoped SSE subscribers received all tenants' live span events
- Health detail and history endpoints now pass `project_id` to storage — previously the project-membership guard passed but the storage query returned rows from all projects sharing the same server name

### Performance
- ClickHouse client now sets `connect_timeout=5s` and `send_receive_timeout=30s` — previously no timeouts were configured, allowing hung connections to block span ingestion indefinitely
- Postgres connection pool `pg_pool_max` raised from 20 to 50 — `LANGSIGHT_PG_POOL_MAX` env var documented for operators who need to lower this on small instances

### Fixed
- SDK: `_loop_detectors` and `_session_budgets` now use LRU eviction (`OrderedDict.move_to_end`) instead of FIFO — previously an active session could be evicted mid-run if 501 sessions existed, resetting its loop detector
- SDK: `trace(agent_name="x")` now works correctly as both a decorator and a context manager — previously the decorator pattern silently returned a context manager object instead of wrapping the function
- SDK: `_fetch_prevention_config` now logs `sdk.prevention_config.fetch_failed` when the API is unreachable — previously failed silently, making it impossible to debug misconfigured or offline deployments
- ClickHouse: lineage self-join now qualifies `project_id` as `child.project_id` and `parent.project_id` — unqualified `project_id` in a self-join produces ambiguous SQL
- Dockerfile: default `LANGSIGHT_WORKERS` changed from 2 to 1 — SSE broadcaster, rate limiter, and auth cache are all in-process; multi-worker deployments produced inconsistent SSE delivery, doubled rate-limit budgets, and stale auth state
- Integration tests: `conftest.py` now loads `.env` automatically via `python-dotenv` — previously test runs outside a shell with exported vars silently used wrong DB credentials
- Integration tests: all ClickHouse client construction now passes `CLICKHOUSE_USER` and `CLICKHOUSE_PASSWORD` from env — previously the test client used the default anonymous user

## [0.6.1] - 2026-03-25

### Fixed
- `wrap(session_id="")` now auto-generates a session ID instead of forwarding an empty string. Empty string was treated as a valid ID (`session_id if session_id is not None`), bypassing generation and producing an unusable session key. Fixed to `session_id if session_id else _new_session_id()`.

### Security
- Regression test added: `test_empty_string_session_id_is_auto_replaced` — verifies empty string triggers auto-generation and the result is a valid 32-char hex ID.

### Added
- **`docs-site/database-connections.mdx`** — new self-hosting reference page documenting how to connect to PostgreSQL (port 5432) and ClickHouse (HTTP 8123, native 9000) using DBeaver, psql, and clickhouse-client. Covers default Docker Compose credentials, key tables for both databases, important `mcp_tool_calls` column reference, sample queries for sessions, error breakdown, token usage, and slowest tools, and a warning about not exposing ports publicly without authentication and TLS. Added to the Self-Hosting group in `mint.json`.

- **SLO tab in agent detail panel** — clicking an agent row now exposes a fifth tab (**SLOs**) alongside About, Overview, Topology, and Sessions. The tab lists every SLO defined for the agent as a card (metric, status badge, target, current value, window, delete button). An inline **+ Add SLO** form lets you create `success_rate` or `latency_p99` SLOs with a chosen target and window (1h / 6h / 24h / 7d) without leaving the page. The tab refreshes immediately after creation.
- **`docs-site/agents.mdx` — Configuring SLOs section** — documents the SLOs tab layout, each card field, the + Add SLO form, metric definitions, target guidance for Success Rate and Latency p99, and window selection guidance. SLOs tab entry added to the detail panel tabs reference. State 2 layout description updated from four tabs to five.
- **`docs-site/slos.mdx` — dashboard creation path** — added "From the Agents page (recommended)" as the primary creation method. Removed the stale "(coming soon — use API for now)" note. Corrected `success_rate` metric definition to match session health tag semantics (`success` / `success_with_fallback`). Corrected `latency_p99` example target from `30000ms` to `5000ms` to match the agent panel guidance.
- **SLO badges on Agents page** — each agent row now shows a `SLO ✓` (green) or `SLO ✗` (red) badge next to the agent name. Badge reflects the worst SLO status across all SLOs defined for that agent (precedence: breached > no_data > ok). No badge shown when no SLOs are defined. Refreshes every 2 minutes. Clicking the agent row opens the detail panel where individual SLO values are shown.
- **Week-over-week trend badges on Dashboard Overview tab** — when the 7d time window is selected, the Sessions, Error Rate, and Avg Latency stat cards each show a `↑X.X% vs last 7d` or `↓X.X% vs last 7d` badge. Colour is context-sensitive: for Sessions, up is green (more activity = good); for Error Rate and Avg Latency, up is red (worse = bad). Badges are hidden for 1h, 6h, and 24h windows. Requires data in both the current and the previous 7-day window.
- **`docs-site/agents.mdx` — SLO Badges section** — documents badge states, multi-SLO worst-status resolution, 2-minute refresh interval, and triage workflow. Cross-links to `/slos`.
- **`docs-site/dashboard.mdx` — Week-over-week trend badges section** — documents badge format, colour inversion logic per card, 7d-only visibility, engineer interpretation examples, and relationship with SLO targets.
- **Agent Health Score** — Agents page now shows a Health column with a colour-coded progress bar (green >= 90%, amber 70–89%, red < 70%) showing the percentage of sessions that completed as `success` or `success_with_fallback`. Sub-label shows `X/Y sessions`. Column is sortable. Status dot (healthy/degraded/failing) is now driven by this score.
- **Error Breakdown** — Dashboard Overview tab now shows a per-category horizontal bar chart at the bottom of the page when errors exist in the selected time window. Categories: Safety Filter, Max Tokens Hit, API Unavailable, Timeout, Rate Limited (429), Auth Error (401/403), Agent Crash, Other. Respects the selected time range.
- **Calls/Session column** — Dashboard Tools tab now shows average tool calls per session as `X.X×`. Highlighted amber when > 5× to flag potential loops or redundant call patterns.
- **Silent Failures column** — Dashboard Tools tab now shows a count of `isError=False` tool calls whose response content contained error text (`Error:`, `Exception:`, `Traceback`, `[ERROR]`, `Failed:`). Shown in amber when > 0. Only applies to `tool_call` spans (MCP calls). Detects failures that are invisible to standard error rate metrics.
- **Context Window Pressure (Ctx Usage column)** — Dashboard Models tab now shows average context window utilisation per model as a percentage (`avg input tokens per call ÷ model context limit × 100`). Red when > 80%, amber when > 50%, grey when <= 50%, `—` when model limit is unknown. Supported models: Gemini 2.5/2.0/1.5, GPT-4o, o3/o3-mini, Claude Opus/Sonnet/Haiku 4.x.
- **Tokens/Session column** — Agents page table now shows average total tokens (input + output) consumed per session per agent. Large values abbreviated (`2.4k`, `18k`). Identifies prompt bloat and expensive agents.
- **Loops column** — Agents page table now shows a red badge with the count of loop detection events (prevented calls) per agent in the selected time window. Shows `—` when clean. Loop types: repetition (same tool+args 3× in a row), ping-pong (A→B→A→B alternation), retry without progress.
- **`docs-site/agents.mdx`** — new Mintlify page documenting the Agents catalog, health score calculation, status thresholds, and three-state layout
- **`docs-site/dashboard.mdx`** — new Mintlify page documenting the Dashboard Overview and Tools tabs, including Error Breakdown and Calls/Session
- **`docs-site/agents.mdx` — Token Efficiency section** — documents Tokens/Session column: calculation, display format, use cases (cost attribution, prompt bloat detection), relationship with Cost column
- **`docs-site/agents.mdx` — Loop Detection Count section** — documents Loops column: three loop patterns, badge display, triage workflow (filter sessions by `loop_detected` tag, inspect `status=prevented` spans), cross-link to Session Health
- **`docs-site/dashboard.mdx` — Silent Failures section** — documents Silent Failures column: detection prefixes, display, interpretation table, relationship with error rate; updated Tools tab column reference
- **`docs-site/dashboard.mdx` — Context Window Pressure section** — documents Ctx Usage column: calculation, colour thresholds, full model context limit table, relationship with Max Tokens Hit in Error Breakdown; added Models tab column reference

### Removed
- **Session Replay and Session Compare** — both features removed from the product. `docs-site/session-replay.mdx` deleted. All cross-references removed from `introduction.mdx`, `agents.mdx`, `session-health.mdx`, `cli/sessions.mdx`, `api-reference/overview.mdx`, `api-reference/traces.mdx`, `self-hosting/configuration.mdx`, and `sdk/python.mdx`. Removed from `mint.json` navigation. The `/api/agents/sessions/compare` and `/api/agents/sessions/{id}/replay` endpoints and the `replay_of` span field are no longer documented.

### Fixed (docs)
- **`session-health.mdx` triage workflow** — removed stale reference to the Compare button (feature removed). Updated to instruct users to use the Failures toggle and filter the Sessions page instead.
- **`agents.mdx` Sessions tab** — removed broken link to `/session-replay`. Sessions now open the session detail page with lineage graph and span trace.
- **`self-hosting/configuration.mdx` and `sdk/python.mdx`** — updated `redact_payloads` warning to remove Playground Replay mention.

---

## [0.6.0] — 2026-03-25

### Breaking Changes

- **`wrap()` auto-generates `session_id` when none is supplied** — previously, omitting `session_id` caused all proxies to share the `__default__` session, merging their loop-detection and budget state. From v0.6.0, each `wrap()` call without an explicit `session_id` receives a unique `uuid4().hex` ID, so two proxies are fully independent by default. To link sub-agents to a parent session, pass `session_id=proxy.session_id` explicitly when constructing the child proxy.

### Added

- **`MCPProxy.session_id` property** — exposes the SDK-issued session ID so parent agents can pass it to sub-agents for explicit chaining (`child = wrap(..., session_id=parent.session_id)`).
- **`sdk/_ids.py`** — internal `_new_session_id()` generator using `uuid4().hex` (32-char hex string, no prefix, no truncation). All session ID generation across the codebase now routes through this single function.
- **Prevention Config** — dashboard-managed per-agent thresholds for loop detection, budget enforcement, and circuit-breaker behaviour. Stored in the Postgres `prevention_config` table. Six new API endpoints (create, read, update, delete, list per agent, get project default). SDK fetches the active config on every `wrap()` call and applies it at runtime without code changes.
- **`PreventionConfig` Pydantic model** — domain model for prevention thresholds; used by both the API layer and the SDK config fetch path.
- **Prevention tab in Settings dashboard** — per-agent and project-default prevention thresholds are now configurable directly from the dashboard. Fields: loop repetition threshold, loop ping-pong threshold, max budget (USD), circuit-breaker failure window, and circuit-breaker cooldown. Changes take effect on the next `wrap()` call.

### Fixed

- **`HealthTag.SUCCESS_WITH_FALLBACK` never fired** — the health-tag engine checked `if not has_error` before evaluating the fallback path, but fallback resolution by definition requires a prior error. Fixed to track resolved vs. unresolved errors per tool across the session, so `SUCCESS_WITH_FALLBACK` is now correctly emitted when an error is recovered from.
- **Session ID format inconsistency** — demo seed data, example scripts, e2e runner, and integration fixtures all now use `uuid4().hex` (32-char, no prefixes, no truncation) via the shared `_new_session_id()` generator. Eliminates format mismatches that caused cross-component session lookup failures.

### Tests

- 200+ new tests added: adversarial coverage for loop/budget isolation across independent sessions, integration tests for Prevention Config API round-trips, regression tests for `HealthTag.SUCCESS_WITH_FALLBACK` triggering, and session ID format contract tests.
- Removed stale `compare_sessions` and `replay_isolation` tests (both features removed in v0.5.x).

---

## [0.5.6] — 2026-03-24

### Added
- **`langsight.trace()`** — decorator and context manager that wraps entire agent functions. Captures any exception raised between LLM calls (`status=error`), `asyncio.CancelledError` (`status=timeout`). Follows Langfuse `@observe` and LangWatch `with trace()` patterns. Never swallows exceptions — always re-raises.
- **`finish_reason` / safety filter detection** — LLM generation spans now detect and record `status=error` for: empty `choices`/`candidates` (safety filter), `finish_reason=SAFETY/RECITATION/content_filter`, truncated responses (`MAX_TOKENS/length`). Neither Langfuse nor LangWatch do this — LangSight unique.
- **MCP content error detection** — `wrap()` now inspects tool result text content for error patterns (`"Error: ..."`, `"Exception: ..."`, `"Traceback"`, `"[ERROR]"`) even when `isError=False`. Neither Langfuse nor LangWatch inspect MCP result content.

---

## [0.5.5] — 2026-03-24

### Added
- **`langsight.auto_patch()`** — monkey-patches OpenAI, Anthropic, google.genai, and google.generativeai SDK classes at import time. Zero explicit `wrap_llm()` calls needed. Follows Langfuse/Sentry/Datadog patterns.
- **`langsight.session()`** async context manager — sets `session_id` and `agent_name` for all LLM calls inside the block.
- **`langsight.set_context()` / `clear_context()`** — explicit context propagation using `contextvars.ContextVar` (async-safe, task-isolated).
- **`langsight.unpatch()`** — restore original SDK methods (useful for testing).

---

## [0.5.4] — 2026-03-24

### Fixed
- **`asyncio.CancelledError` handled as `timeout`** — `asyncio.wait_for()` timeouts now record `status=timeout` instead of being missed entirely. Follows Langfuse and Datadog patterns (both explicitly handle task cancellation).
- **`BaseException` scope** — all LLM proxy `except` clauses now catch `BaseException` (was `Exception`), matching Datadog's implementation. Prevents silent span loss on `KeyboardInterrupt` and other base exceptions.
- **Error includes exception class name** — `error` field is now `"RateLimitError: quota exceeded"` instead of just `"quota exceeded"`, enabling precise alerting rules (matches Langfuse's `status_message` pattern).

---

## [0.5.3] — 2026-03-24

### Fixed
- **Agent failure detection** — all `wrap_llm()` proxies (OpenAI, Anthropic, Gemini legacy, google.genai) now use try/except/finally so LLM API errors (timeouts, 429s, 500s) record a span with `status=error` or `status=timeout` instead of silently dropping the call. Previously, a failed LLM call produced no span at all.

---

## [0.5.2] — 2026-03-24

### Fixed
- **Cross-layer span linking** — MCP execution spans from `wrap()` now auto-link to LLM function_call spans from `wrap_llm()` via thread-local context propagation. Dashboard lineage graph shows connected trees instead of orphaned MCP nodes. Works across all SDKs (OpenAI, Anthropic, Gemini).
- **Agent name propagation** — MCP execution spans inherit `agent_name` from the LLM context so the dashboard can draw agent→server edges correctly.

---

## [0.5.0] — 2026-03-24

### Added
- **`langsight.init()`** — one-line setup from env vars (`LANGSIGHT_URL`, `LANGSIGHT_API_KEY`, `LANGSIGHT_PROJECT_ID`), returns `None` when URL not set (like Sentry)
- **`google.genai.Client` support** — `wrap_llm()` now auto-detects the new `google-genai` SDK and intercepts `client.models.generate_content()` (sync) and `client.aio.models.generate_content()` (async) via `GenaiClientProxy`
- **Separate docs pages** — Gemini SDK, OpenAI SDK, and Anthropic SDK each have dedicated integration pages

### Fixed
- **`_emit_spans()` in LLM wrappers** now uses sync `buffer_span()` instead of the old `send_spans()` async/threading pattern (was missed in v0.4 migration)
- **Gemini auto-detection** — `google.genai.Client` no longer silently falls through to the legacy `GeminiProxy` which couldn't intercept the new SDK's nested API surface

---

## [0.4.0] — 2026-03-24

### Added
- **Unified LangChain/LangGraph callback** — single callback auto-detects agents, builds parent-child tree, captures prompts
- **`wrap_llm()`** — instrument direct OpenAI, Anthropic, and Gemini SDK calls
- **Agent + server auto-discovery** — auto-register from trace ingestion
- **Silent MCP error detection** — catch `isError` on JSON-RPC responses
- **Token capture + cost computation** — via `on_llm_end` + model_pricing table
- **Project-scoped security scan** — only scan servers belonging to active project
- **Global `redact_payloads` setting** — admin toggle to strip all payloads server-side
- **Sessions page overhaul** — horizontal scroll, sortable columns, numbered pagination, health tag fallback
- **Session detail redesign** — clean inline rows, rich default summary, all agents in header
- **Agents page polish** — merged timestamp columns, edge legend, topology detail bar
- **Mintlify docs** — updated for all new SDK features and auto-discovery

### Fixed
- Security scan showed findings from all projects (now project-scoped)
- "1 calls" grammar → "1 call" singular
- Dashboard agent count showed session math instead of distinct names
- Timestamps off by 1 hour (ClickHouse naive datetime → UTC fix)
Versions follow [Semantic Versioning](https://semver.org/).

---

## [0.4.0] - 2026-03-23 — Unified Callback, Direct LLM Tracing, Auto-Discovery

### Added

- **Unified LangChain callback with auto-detect mode** (`src/langsight/integrations/langchain.py`): `LangSightLangChainCallback` now supports two modes. Omit `server_name` to enable auto-detect — agent names are detected from LangGraph graph names via `on_chain_start`, parent-child trees are built via `parent_run_id` and a thread-local tool stack for cross-`ainvoke` linking, and the first human message is auto-captured as the session prompt. Pass `server_name` for backward-compatible fixed mode.
- **`on_chain_start` / `on_chain_end` agent spans**: named agents in LangGraph workflows emit `span_type="agent"` spans with auto-computed latency, error propagation, and parent linking. Framework-internal names (`RunnableSequence`, `ChannelWrite`, `ChatOpenAI`, etc.) are filtered out.
- **`on_chat_model_start` prompt capture**: the first human message in a conversation is auto-captured as the session input. Override with `cb.set_input(text)`.
- **`set_input()` / `set_output()` explicit prompt/answer capture**: public API on the callback for frameworks where auto-capture is insufficient.
- **`LangSightLangGraphCallback` is now an alias** (`src/langsight/integrations/langgraph.py`): points to `LangSightLangChainCallback`. Existing import paths still work.
- **`wrap_llm()` for direct SDK tracing** (`src/langsight/sdk/llm_wrapper.py`, `src/langsight/sdk/client.py`): new `client.wrap_llm()` method wraps OpenAI, Anthropic, and Gemini SDK clients. Intercepts generation calls and auto-traces LLM generation spans (model, tokens, cost) and tool_use blocks from responses as `tool_call` spans with parent linking.
- **Auto-discovery of agents and servers from traces** (`src/langsight/api/routers/traces.py`): `POST /api/traces/spans` now auto-registers unseen `agent_name` and `server_name` values in the catalog. Best-effort, fail-open, in-process deduplication.
- **Batch discovery endpoints**: `POST /api/agents/discover` and `POST /api/servers/discover` scan ClickHouse for all distinct values and register any missing from the catalog (admin only).
- **Silent MCP error detection** (`src/langsight/sdk/client.py`): `MCPClientProxy.call_tool()` now detects `result.isError` (MCP JSON-RPC error responses) and marks the span as `status=error` instead of `success`.
- **Global payload redaction toggle** (`src/langsight/api/main.py`): `GET /api/settings` and `PUT /api/settings` endpoints for instance-level settings. When `redact_payloads` is enabled server-side, the server strips `input_args`, `output_result`, `llm_input`, and `llm_output` from all incoming spans before storage, overriding individual SDK settings.

### Changed

- **LangGraph callback merged into LangChain callback**: the separate `LangSightLangGraphCallback` class in `langgraph.py` is replaced by an alias to the unified `LangSightLangChainCallback`. All node-level and graph-level context tracking is handled by the unified callback.
- **Cross-ainvoke parent linking is module-level**: the thread-local tool execution stack is shared across all callback instances in the same thread, enabling automatic parent linking when sub-agents are invoked from within tool execution contexts.

### Docs

- **LangChain integration page rewritten** (`docs-site/sdk/integrations/langchain.mdx`): documents auto-detect mode, fixed mode, prompt capture, cross-ainvoke linking, and the updated span field table.
- **New Direct SDK page** (`docs-site/sdk/integrations/direct-sdk.mdx`): documents `wrap_llm()` for OpenAI, Anthropic, and Gemini with full code examples and span field tables.
- **New Auto-Discovery guide** (`docs-site/guides/auto-discovery.mdx`): documents zero-config agent/server registration and batch backfill endpoints.
- **LangGraph page updated** (`docs-site/sdk/integrations/langgraph.mdx`): reflects alias status, auto-detect mode, migration from v0.3.
- **Python SDK page updated** (`docs-site/sdk/python.mdx`): added silent MCP error detection section, auto parent linking section, and `wrap_llm()` cross-reference.
- **Configuration page updated** (`docs-site/self-hosting/configuration.mdx`): added global payload redaction section with API examples.
- **API reference updated** (`docs-site/api-reference/overview.mdx`): added Auto-Discovery and Instance Settings endpoint tables.
- **Introduction updated** (`docs-site/introduction.mdx`): added `wrap_llm()` to integrations table.
- **Navigation updated** (`docs-site/mint.json`): added `sdk/integrations/direct-sdk` and `guides/auto-discovery` pages.

---

## [0.3.7] - 2026-03-23 — Reliable Span Delivery on Flush Failure

### Fixed

- **`_post_spans()` now returns `bool`** (`src/langsight/sdk/client.py`): the method returns `True` on a successful HTTP delivery and `False` on any failure, instead of returning `None` unconditionally. This makes the return value testable and lets callers distinguish success from failure without catching exceptions.
- **`flush()` rescues spans on send failure** (`src/langsight/sdk/client.py`): when `_post_spans()` returns `False`, `flush()` prepends the batch back to the front of the internal buffer. The `atexit` handler therefore has a second chance to deliver those spans in its own thread, ensuring no spans are silently dropped when the event loop closes during process teardown.

---

## [0.3.6] - 2026-03-23 — Tool Input/Output Capture and Flush Reliability

### Added

- **Tool argument and result capture** (`src/langsight/integrations/base.py`): `_record()` now accepts `input_str` (tool arguments) and `output` (tool result). Both fields are stored on the span. When `redact_payloads=True` is configured on the client, neither field is captured, preventing accidental PII ingestion.
- **LangChain tool payload capture** (`src/langsight/integrations/langchain.py`): `on_tool_start` stores `input_str`; `on_tool_end` passes the tool result as `output` to `_record()`. Spans now carry full tool invocation context.
- **LangGraph node payload capture** (`src/langsight/integrations/langgraph.py`): same as LangChain — `input_str` and `output` captured on node-level spans so every node execution is fully observable.

### Fixed

- **Spans lost when event loop closes during flush** (`src/langsight/sdk/client.py`): `flush()` now catches `_post_spans` failures and returns the batch to the front of the buffer. The `atexit` handler can then deliver the spans in its own thread, so no spans are silently dropped when the event loop is already closing at process teardown.

---

## [0.3.5] - 2026-03-23 — Graceful Shutdown Flush for LangSightClient

### Fixed

- **Buffered spans lost on process exit** (`src/langsight/sdk/client.py`): `LangSightClient` now registers an `atexit` handler that flushes any in-flight buffered spans in a background thread when the process exits. Users no longer need `async with LangSightClient()` or an explicit `await client.close()` call to guarantee delivery. This also eliminates the `Event loop is closed` `RuntimeWarning` that appeared in LangChain and LangGraph integrations during normal process teardown.

---

## [0.3.4] - 2026-03-23 — project_id Stamping Fix for Integrations

### Fixed

- **`project_id` missing on all integration spans** (`src/langsight/integrations/base.py`): `_record()` now stamps `project_id` from `client._project_id` on every span before dispatch. Without this fix, all spans produced by LangChain/LangGraph callbacks landed in ClickHouse with `project_id=""` and were invisible to the project dashboard.
- **`project_id` missing on tool spans** (`src/langsight/integrations/langgraph.py`): `on_tool_end` and `on_tool_error` handlers now also stamp `project_id`, consistent with the base fix above.
- **`Event loop is closed` warnings on shutdown** (`src/langsight/integrations/langchain.py`, `src/langsight/integrations/langgraph.py`): `_fire_and_forget()` now checks `loop.is_running() and not loop.is_closed()` before calling `create_task`, eliminating the spurious `RuntimeWarning` that appeared when the event loop had already shut down during process teardown.

---

## [0.3.3] - 2026-03-23 — LangChain-Core Compatibility Fix

### Fixed

- **LangChain integration import order** (`src/langsight/integrations/langchain.py`, `src/langsight/integrations/langgraph.py`): both modules now attempt to import `BaseCallbackHandler` from `langchain_core.callbacks.base` first, falling back to `langchain.callbacks.base` only if `langchain_core` is not available. LangGraph users no longer need the full `langchain` package — `pip install langsight langgraph` is sufficient.

---

## [0.3.2] - 2026-03-23 — Buffer Safety, Bootstrap, and Hardening

### Added (2026-03-23 — Dashboard UX polish)

- **`DateRangeFilter` component** (`dashboard/components/date-range-filter.tsx`): global date range control with five presets (`1h`, `6h`, `24h`, `7d`, `30d`) and a custom date picker dropdown (From/To `<input type="date">` with Apply button). Active preset highlighted with primary teal; custom range shows an indigo-tinted "Custom" label. Clicking outside the dropdown closes it via `mousedown` listener. Integrated into Sessions, Costs, Health, Agents, and Servers pages.
- **`Timestamp` component** (`dashboard/components/timestamp.tsx`): semantic `<time>` element that displays relative time ("16h ago") alongside exact time at 60% opacity ("Mar 22, 14:30:05"). Compact mode shows only relative time with exact value in the HTML `title` attribute (tooltip on hover). Used across sessions list, session detail, health page uptime dots, agents page, servers page, and settings.
- **Graph builder module** (`dashboard/lib/session-graph.ts`): `buildSessionGraph(trace, expandedGroups, expandedEdges): SessionGraphResult` extracts all session-to-graph construction logic from the session detail page. Exposes `findRepeatedCall` (detects same tool + same args repeated N times) and `buildCallLabels` (sequence labels for disambiguating repeated tools on the same edge). `SessionGraphResult` type carries `nodes`, `edges`, `serverCallers`, `edgeMetrics`, `edgeSpans`.

### Changed (2026-03-23 — Dashboard UX polish)

- **Session detail page redesigned** (`dashboard/app/(dashboard)/sessions/[id]/page.tsx`): layout optimized for wide screens to maximize lineage graph area. `SessionNodeDetail` right-panel converted to `MetricTile` sub-components (rounded tiles with left accent border, primary or danger color). `SectionLabel` sub-component standardizes panel headings. Graph construction delegated to `useSessionGraph` hook (`useMemo` over `buildSessionGraph`).
- **Lineage graph nodes redesigned** (`dashboard/components/lineage-graph.tsx`): node cards now display compact metric pills (call count, error count, avg latency) inside each card. Node padding tightened for denser graphs. Loop detection annotation row shows `repeatCallName` + `repeatCallCount` when a repeated call pattern is present. Agent nodes use a teal gradient header; server nodes use slate. Selection: glass-morphism border + glow. Back-edges (cycles) rendered as self-loop arcs on the right side of the source node. Minimap uses `ResizeObserver` for live container size tracking and auto-fits the graph into the viewport on first render.
- **Timestamp labels corrected** across pages (Sessions, Health, Agents, Servers, Settings): switched from raw `timeAgo()` string interpolation to the `Timestamp` component, ensuring consistent relative + exact time display and semantic `<time>` elements.

### Changed (2026-03-22 — Positioning: observability → runtime reliability)

- **Positioning pivot**: LangSight is now positioned as "agent runtime reliability" — not observability. Observability overlaps with Langfuse/LangWatch. Runtime reliability (prevent, detect, monitor, map) is an empty category.
- **README rewritten**: new headline "how do we stop it next time?", 6 sections (Prevent, Detect, Monitor, Attribute, Map, Investigate), SDK config examples for loop detection / budget guardrails / circuit breaker.
- **Website homepage rewritten**: hero updated, solution pillars reordered to Prevent → Detect → Monitor → Map, problem cards reframed (loops, cascading failures, cost explosions, schema drift), comparison table expanded (9 rows), CTA updated.
- **Mintlify docs introduction rewritten**: 4 pillars, "Langfuse watches the brain, LangSight watches the hands", blast radius section, updated integration table.
- **Mintlify colors**: indigo → teal (`#14B8A6` / `#2DD4BF`), nav group renamed "Observability Features" → "Reliability Features".
- **pyproject.toml description**: "Agent runtime reliability — prevent loops, enforce budgets, monitor MCP health, scan for CVEs".
- **FastAPI description**: updated in `api/main.py` OpenAPI spec.
- **CLI help text**: updated in `cli/main.py`.
- **Dashboard metadata**: updated in `dashboard/app/layout.tsx` and settings page.
- **Website metadata**: all page layouts (pricing, security, glossary, alternatives) updated from "observability" to "runtime reliability".
- **v0.3 plan documented**: `docs/09-v03-runtime-reliability-plan.md` — 10-week roadmap covering loop detection, budget guardrails, circuit breakers, OpsGenie/PagerDuty, blast radius on lineage.
- **Internal docs updated**: all 7 internal engineering docs (`01-product-spec.md` through `08-adoption-strategy.md`) updated to reflect "runtime reliability" positioning, BSL 1.1 license, langsight.dev domain, and LangSight/langsight GitHub org. CLAUDE.md "What We're Building" section rewritten. PROGRESS.md framing updated. `04-implementation-plan.md` and `05-risks-costs-testing.md` license sections updated from Apache 2.0 to BSL 1.1.

### Added (2026-03-22 — Website, branding, infrastructure)

- **BSL 1.1 license**: switched from MIT to Business Source License 1.1. Self-host free, no usage limits. Converts to Apache 2.0 on 2030-03-21. Only restriction: cannot offer LangSight as a hosted service.
- **GitHub org**: repo moved from `sumankalyan123/langsight` to `LangSight/langsight`.
- **langsight.dev domain**: purchased, deployed to Cloudflare Pages.
- **docs.langsight.dev**: Mintlify custom domain configured.
- **Teal design system**: website color scheme changed from indigo to teal (`#14B8A6` light / `#2DD4BF` dark).
- **Logo**: scope mark (ring + dot + diagonal line) on teal background. SVG + PNG kit (512, 256, 128, 64, 32, 16px).
- **Brand assets**: `og-image.svg`, `twitter-banner.svg`, `linkedin-banner.svg`, favicon, apple-touch-icon.
- **Google Analytics GA4**: `G-S6E7SBNNXL` added to website layout.
- **Cloudflare Web Analytics**: enabled on langsight.dev.
- **Security headers**: `_headers` file for Cloudflare Pages — HSTS, CSP, COOP, XFO, nosniff.
- **SEO**: JSON-LD SoftwareApplication schema, robots.txt, sitemap.xml (5 pages), per-page metadata layouts.
- **New pages**: `/alternatives` (LangSight vs Langfuse vs LangWatch comparison), `/glossary` (8 MCP/observability terms).
- **SEO skills installed**: `seo-audit` + `programmatic-seo` from marketingskills.
- **seo-optimizer agent**: `.claude/agents/seo-optimizer.md`.

### Fixed (2026-03-22 — Performance + accessibility)

- **Next.js upgraded**: 15.2.3 → 15.5.14 (patches CVE-2025-66478).
- **Lighthouse Performance 100**: terminal animation deferred via `requestAnimationFrame`, H1 `fade-up` removed for immediate LCP, `will-change` on all animated elements.
- **Lighthouse Accessibility**: light mode teal darkened from `#14B8A6` to `#0F766E` (5.6:1 contrast ratio on white, WCAG AA compliant).
- **SSE event drop counter**: `langsight_sse_events_dropped_total` Prometheus counter + debug logging when broadcaster drops events.
- **Dashboard fetch timeouts**: 15-second `AbortSignal.timeout()` on all `fetch()` calls.
- **API version**: reads from `importlib.metadata` instead of hardcoded `"0.1.0"`.

### Added (2026-03-21 — Prometheus metrics + SSE live event feed)

- **Prometheus `/metrics` endpoint** — `src/langsight/api/metrics.py`: `GET /metrics` returns all LangSight metrics in Prometheus text exposition format, no authentication required. Metrics exported: `langsight_http_requests_total` (counter, method/path/status), `langsight_http_request_duration_seconds` (histogram, method/path), `langsight_spans_ingested_total` (counter), `langsight_active_sse_connections` (gauge), `langsight_health_checks_total` (counter, server/status). `PrometheusMiddleware` instruments all API requests with path normalization (collapses UUIDs to `{id}`) to keep cardinality bounded. Skips `/metrics`, `/api/liveness`, `/api/readiness`.
- **SSE live event feed** — `src/langsight/api/broadcast.py` + `src/langsight/api/routers/live.py`: `GET /api/live/events` streams Server-Sent Events to connected dashboard clients. Events: `span:new` (fired on span ingestion in `traces.py`), `health:check` (fired on health check completion). `SSEBroadcaster` is an in-memory asyncio pub/sub — max 200 concurrent clients, 50-event buffer per client (oldest dropped when full), 15-second keepalive heartbeats. The `/api/live/events` endpoint requires authentication (same as all other API routes). `ACTIVE_SSE` gauge tracks connected clients in Prometheus.
- **New dependency**: `prometheus-client>=0.21` added to `pyproject.toml`.
- **Tests**: 20 new tests (11 for Prometheus metrics, 9 for SSE broadcaster). Total: 957 tests passing.

### Added (2026-03-21 — SDK integrations: OpenAI Agents, Anthropic/Claude, LangGraph)

- **SDK: OpenAI Agents integration** — `src/langsight/integrations/openai_agents.py`: `LangSightOpenAIHooks` class implementing the `RunHooks` protocol; hooks into `on_tool_start`/`on_tool_end` to trace every tool call automatically. Also provides `langsight_openai_tool` decorator for tracing individual tool functions.
- **SDK: Anthropic/Claude integration** — `src/langsight/integrations/anthropic_sdk.py`: `AnthropicToolTracer` traces `tool_use` content blocks from Anthropic SDK message responses; `LangSightClaudeAgentHooks` provides lifecycle hooks for the Claude Agent SDK agent loop; `langsight_anthropic_tool` decorator for individual tool handlers. Works with both the `anthropic` package and `claude_agent_sdk`.
- **SDK: LangGraph integration** — `src/langsight/integrations/langgraph.py`: `LangSightLangGraphCallback` extends the LangChain callback with graph-aware context — tracks which graph node is executing, groups spans at the graph level, and surfaces conditional routing. Works with both sync `invoke()` and async `ainvoke()`.
- **Docs-site: 3 new integration pages** — `docs-site/sdk/integrations/openai-agents.mdx`, `docs-site/sdk/integrations/anthropic.mdx`, `docs-site/sdk/integrations/langgraph.mdx` added to Mintlify site; `mint.json` navigation updated with all three pages in "SDK & Integrations" group.
- **Integration count now 9**: MCP (SDK wrap), LangChain, LangGraph, CrewAI, Pydantic AI, OpenAI Agents, Anthropic/Claude, OTEL, LibreChat.

### Fixed (2026-03-21 — rate limiter: single instance + latency_ms auto-compute)

- **Rate limiter: single global instance** — created `src/langsight/api/rate_limit.py` exporting a single `limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])`. All routers (`main.py`, `traces.py`, `users.py`) now import from this module instead of creating separate `Limiter` instances. Per-route overrides now work correctly: traces=2000/min, otlp=60/min, accept-invite=5/min, verify=10/min.
- **`latency_ms` auto-compute** — `ToolCallSpan.latency_ms` changed from required to optional (`float | None = None`). A `model_validator(mode="after")` auto-computes it from `ended_at - started_at` when omitted. SDK users and OTLP ingestion no longer need to calculate latency manually.

### Fixed (2026-03-21 — principal engineer audit: security, correctness, scale, Docker)

- **Security: AWS credential leak** — removed `test-mcps/s3-mcp/.env` volume mount from the production API service in `docker-compose.yml`; AWS credentials are no longer exposed to the API container
- **Security: DB port binding** — ClickHouse and Postgres ports in `docker-compose.yml` now bind to `127.0.0.1` instead of `0.0.0.0`; databases are no longer reachable from external hosts
- **Security: demo credentials gated** — login page (`dashboard/app/(auth)/login/page.tsx`) now only displays demo credentials when `NODE_ENV !== "production"`; production deployments no longer leak default passwords in the UI
- **Security: CORS default tightened** — `LANGSIGHT_CORS_ORIGINS` default changed from `"*"` (wildcard) to `"http://localhost:3003"` in `config.py`; production deployments must explicitly configure allowed origins
- **Security: global rate limiting** — added `SlowAPIMiddleware` with `default_limits=["200/minute"]` on all API endpoints; previously only ingestion routes were rate-limited
- **Security: dashboard security headers** — Next.js dashboard now sets `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `X-XSS-Protection: 1; mode=block`, `Referrer-Policy: strict-origin-when-cross-origin`, and `Permissions-Policy` headers on all responses
- **Security: PII masking in audit logs** — `_mask_email()` in the API now produces `"a***@example.com"` when logging user actions; raw emails no longer appear in audit log entries
- **Correctness: DualStorage.accept_invite** — `DualStorage` was missing delegation to `self._meta.accept_invite()`; calling `accept_invite()` through the dual backend raised `AttributeError`; now correctly routes to `PostgresBackend`
- **Correctness: delete metadata** — `delete_agent_metadata` and `delete_server_metadata` in `postgres.py` now check `!= "DELETE 0"` instead of `.endswith("1")`; previously failed silently when deleting rows with multi-digit affected counts
- **Correctness: session compare 404** — `GET /api/agents/sessions/compare` no longer returns 404 for spans that lack a `project_id` (pre-tagging data); the compare endpoint now handles `None` project_id gracefully
- **Correctness: typo fix** — `getServerHistoty` renamed to `getServerHistory` in `dashboard/lib/api.ts` and all consuming pages
- **Performance: health page lazy loading** — removed O(N) health history preload on `/health` page mount; history is now fetched lazily when a server row is expanded, reducing initial page load time proportional to server count
- **Performance: agents page SWR staggering** — reduced sessions fetch limit from 500 to 100 on the agents page and staggered SWR refresh intervals across data fetchers to avoid concurrent API thundering herd
- **Performance: executemany batch** — `upsert_server_tools` in `postgres.py` replaced N sequential `execute()` calls with a single `executemany()` batch, reducing DB round trips from O(N) to O(1)
- **Cleanup: top-level imports** — moved `import json`, `import uuid`, and `from datetime import datetime` out of function bodies to module top-level in `postgres.py`
- **Docker: dashboard health check** — changed health check URL from `http://localhost:3002` to `http://127.0.0.1:3002` in both `Dockerfile` and `docker-compose.yml`; Alpine Linux `wget` resolves `localhost` to `::1` (IPv6) first while the server listens on IPv4 only, causing false unhealthy status
- **Docker: dashboard hostname binding** — added `HOSTNAME=0.0.0.0` to the dashboard service in `Dockerfile` and `docker-compose.yml`; Next.js standalone mode was binding to `127.0.0.1` inside the container, making the dashboard unreachable from the Docker network
- **Correctness: list_projects role resolution** — `list_projects()` now resolves the caller's role per project; `your_role` was previously always `null` in the response

### Added (2026-03-21 — CI + test improvements)

- **CI: Dashboard type check job** — new GitHub Actions job runs `tsc --noEmit` on the Next.js dashboard; TypeScript errors in dashboard code now block CI
- **Test: DualStorage protocol conformance** — `TestProtocolConformance` class in `test_dual.py` introspects the `StorageBackend` protocol and verifies `DualStorage` explicitly implements every method; prevents silent `__getattr__` fallback hiding missing delegation
- **Test: accept_invite routing** — new test verifies `accept_invite` calls are correctly routed to the metadata backend in `DualStorage`

### Added (2026-03-20 — session detail graph toolbar, MCP Servers catalog, agents catalog, SDK tool-schema capture)

- Session detail lineage graph: graph toolbar with search bar (highlights/dims nodes), zoom slider (25-250%), Expand All / Collapse All buttons, and Failures toggle that isolates the error chain
- Session detail lineage graph: minimap (150×90px, bottom-right) showing full graph with draggable viewport rectangle
- Session detail lineage graph: timeline bar above graph — one colored segment per `tool_call` span (green/red/yellow); click to select the node in the graph
- Session detail lineage graph: `PayloadSlideout` component — full-width slide-over panel with JSON line numbers, copy button, word wrap toggle, tab selector (Input/Output/Prompt/Completion), Esc to close
- Session detail lineage graph: per-tool edge expansion — circular `+` button on edges with call count (e.g. `5×`) splits the server node into per-tool sub-nodes
- Session detail lineage graph: "View in Agent/Server Catalog →" link in node detail panels navigates to `/agents` or `/servers` with the node pre-selected
- Keyboard shortcuts on session detail graph: `/` focus search, `f` fit view, `e` toggle error highlight, `+`/`-` zoom, `Esc` deselect
- Agents catalog: 3-state adaptive layout — State 1 (full-width sortable table with Needs Attention banner), State 2 (280px grouped sidebar + detail panel), State 3 (56px icon-rail + full-width topology graph when Topology tab is active)
- Agents catalog: editable metadata fields (description, owner, tags, status, runbook URL) on the About tab; writes to `PUT /api/agents/metadata/{name}` on blur
- MCP Servers catalog at `/servers`: same 3-state adaptive layout as Agents; "MCP Servers" added to sidebar primary nav between Agents and Costs
- MCP Servers catalog detail panel — 4 tabs: About (editable metadata), Tools (declared tools with reliability metrics), Health (uptime%, trend chart, last 15 checks), Consumers (agents that call this server from lineage data)
- PostgreSQL tables `server_metadata` and `server_tools` added to DDL; both idempotent on schema init
- New API endpoints: `GET /api/servers/metadata`, `PUT /api/servers/metadata/{name}`, `GET /api/servers/{name}/tools`, `PUT /api/servers/{name}/tools`
- SDK `MCPClientProxy.list_tools()` intercepted — tool names, descriptions, and input schemas fire-and-forget posted to `PUT /api/servers/{server_name}/tools` on every call; fail-open (MCP client returns normally if backend is unreachable)
- `dashboard/components/payload-slideout.tsx` — new reusable component
- `dashboard/components/session-timeline.tsx` — new reusable component
- `dashboard/components/agent-topology.tsx` — new component wrapping `LineageGraph` scoped to a single agent's edges
- `dashboard/components/editable-field.tsx` — new reusable `EditableText`, `EditableTextarea`, `EditableTags`, `EditableUrl` components
- `dashboard/app/(dashboard)/servers/page.tsx` — new page at `/servers`

### Added (2026-03-20 — session detail + agent topology UX)

- `dashboard/app/(dashboard)/sessions/[id]/page.tsx` — dedicated full-page session debugger. Session rows now drill into `/sessions/{id}` instead of relying on the older inline workflow interaction model.
- Session detail page now has two working surfaces:
  - `Details` tab — session timeline, interactive lineage graph, and a 70/30 split detail panel for selected agents, servers, edges, and individual tool calls
  - `Trace` tab — nested span tree with inline payload/error expansion for tool and LLM spans
- Session compare flow moved onto the session detail page: compare target is picked from recent sessions, then rendered inline as a side-by-side diff table.
- Agents page gained topology exploration:
  - per-agent topology tab using the shared lineage graph
  - global topology modal for fleet-wide agent/server relationships

### Changed (2026-03-20 — lineage navigation + rendering)

- `/lineage` dashboard route now redirects to `/agents`; lineage exploration is consolidated under the Agents experience rather than a separate standalone page.
- `dashboard/components/lineage-graph.tsx` replaced the React Flow-based implementation with a raw SVG + `dagre` renderer shared by session and agent topology views.
- The lineage graph now supports expand/collapse for multi-caller servers and per-tool/per-call breakdowns directly inside the shared renderer.

### Removed (2026-03-20 — React Flow dependency)

- `@xyflow/react` removed from the dashboard package after the SVG lineage renderer shipped.
- `dashboard/package-lock.json` and `dashboard/package.json` cleaned up to drop the unused React Flow dependency chain.

### Breaking (2026-03-19 — SQLite removed)

- `mode: sqlite` in `.langsight.yaml` now raises `ConfigError` with migration guidance. Valid modes: `postgres` | `clickhouse` | `dual`. Migrate by switching to `mode: dual` and running `docker compose up -d`.
- `storage/sqlite.py` deleted. `SQLiteBackend` class no longer exists. Remove any direct imports.
- `open_storage()` factory no longer returns `SQLiteBackend`. Code that checked `isinstance(storage, SQLiteBackend)` will break.

### Added (2026-03-19 — Dual-storage architecture)

- `src/langsight/storage/dual.py` — `DualStorage` class: routes metadata ops to `PostgresBackend` and analytics ops to `ClickHouseBackend`. Satisfies the full `StorageBackend` protocol transparently; callers need no changes.
- `src/langsight/storage/factory.py` — `open_storage()` now dispatches `mode="dual"` to `DualStorage(metadata=PostgresBackend, analytics=ClickHouseBackend)`. Default `StorageConfig.mode` changed from `"sqlite"` to `"dual"`.
- `docker-compose.yml`: Postgres port `5432` and ClickHouse ports `8123`/`9000` now exposed to host (required for integration tests). `LANGSIGHT_STORAGE_MODE: dual` set as API container default. Required env vars enforced via `${VAR:?error}` syntax — compose refuses to start with missing secrets.
- `.env.example` — new file: documents all required and optional env vars with instructions.

### Added (2026-03-19 — Integration test infrastructure)

- `tests/conftest.py`: `require_postgres`, `require_clickhouse`, `require_all_services` session-scoped fixtures; auto-skip tests when Docker service is not reachable.
- `tests/integration/storage/test_postgres_storage.py` — full Postgres storage integration tests against real DB with uuid-based server names.
- Regression tests migrated from `SQLiteBackend` to `PostgresBackend`.

### Fixed (2026-03-19 — SDK auth header, CRITICAL)

- SDK was sending `Authorization: Bearer <key>`; API only read `X-API-Key`. Traces were silently dropped in any authenticated deployment (no error, just missing data).
- Fixed: `_read_api_key()` helper in `src/langsight/api/dependencies.py` reads `X-API-Key` first, then `Authorization: Bearer` as fallback. SDK now sends `X-API-Key`. Both forms accepted permanently for backward compatibility.

### Fixed (2026-03-19 — Docker proxy trust model, CRITICAL)

- `_TRUSTED_PROXY_IPS` was hardcoded to `{127.0.0.1, ::1}` — broken in Docker where the Next.js dashboard container has a `172.x.x.x` source IP, not loopback.
- Fixed: `parse_trusted_proxy_networks(cidrs_str)` in `dependencies.py` parses `LANGSIGHT_TRUSTED_PROXY_CIDRS` env var into `ipaddress.ip_network` objects stored on `app.state.trusted_proxy_networks` at startup. `_is_proxy_request()` checks the client IP against this CIDR list.
- Docker Compose default: `LANGSIGHT_TRUSTED_PROXY_CIDRS=127.0.0.1/32,::1/128,172.16.0.0/12,10.0.0.0/8`.

### Added (2026-03-19 — Alert config + audit log persistence)

- `alert_config` table in Postgres — singleton upsert row storing Slack webhook URL and per-alert-type enable flags. Previously stored in `app.state` (lost on API restart).
- `audit_logs` table in Postgres — append-only auth/RBAC event log. Previously an in-memory ring buffer (last 50 events, lost on restart). `append_audit()` now schedules an async DB write via `asyncio.create_task` — never blocks the request path.

### Changed (2026-03-19 — RBAC hardened)

- `POST /api/auth/api-keys`, `GET /api/auth/api-keys`, `DELETE /api/auth/api-keys/{id}` — now require admin role via `require_admin()` dependency.
- `POST /api/slos`, `DELETE /api/slos/{slo_id}` — now require admin role.
- `list_projects` — handles session-user path (X-User-Id headers) correctly; previously fell through to env-var key check.
- `get_active_project_id` and `get_project_access` — both check DB keys (not just env keys) for auth-disabled logic to prevent false "auth disabled" state when only DB keys exist.

### Added (2026-03-19 — Dashboard: accept-invite, NavProgress, loading skeleton)

- `/accept-invite` page — password + confirm password fields; calls `POST /api/accept-invite` (public Next.js API route, no session required); on success redirects to `/login`. Middleware updated to allow `/accept-invite` through unauthenticated.
- `NavProgress` component — thin indigo bar at top of dashboard; animates on sidebar link click, completes on route change.
- `dashboard/app/(dashboard)/loading.tsx` — Next.js App Router loading skeleton shown instantly during navigation; eliminates blank flash.
- Sidebar route prefetch — all sidebar routes prefetched on component mount for instant navigation.
- `health/page.tsx` — fixed `useState` → `useEffect` for HistoryPanel data fetch (was causing SSR hydration mismatch).
- Settings page — URL hash persistence on load; no flicker on refresh; section state driven by `window.location.hash`.

### Added (2026-03-19 — Settings redesign + Notifications + Audit Logs)

- Settings page: left-nav + content panel layout — 8 grouped sections replacing the previous single-scroll page (General, API Keys, Model Pricing, Members, Projects, Notifications, Audit Logs, Instance)
- Settings → General: Debug Information section showing instance URL and current version for SDK quick setup
- Settings → API Keys: `.env` snippet with `LANGSIGHT_API_KEY` and `LANGSIGHT_API_URL` for instant SDK instrumentation
- Settings → Notifications: Slack webhook URL field with inline test button; per-alert-type toggle switches for `mcp_down`, `mcp_recovered`, `agent_failure`, `slo_breached`, `anomaly_critical`, `security_critical`
- Settings → Audit Logs: table of last 50 auth/RBAC events; columns: timestamp, actor, action, resource, result. Initially backed by in-memory ring buffer; subsequently migrated to `audit_logs` Postgres table (see persistence fix above).
- `GET /api/alerts/config` — read current Slack webhook URL and per-type alert preferences
- `POST /api/alerts/config` — save Slack webhook URL and alert type preferences
- `POST /api/alerts/test` — send a test Slack Block Kit message to the configured webhook
- `GET /api/audit/logs` — list recent audit log events with `limit` and `offset` query params
- `AlertType.AGENT_FAILURE` — fires when an agent session has `failed_calls > 0`
- `AlertType.SLO_BREACHED` — fires when the SLO evaluator returns a breached status
- `AlertType.ANOMALY_DETECTED` — fires when z-score crosses the critical threshold
- `AlertType.SECURITY_FINDING` — fires on a CVE or OWASP critical finding

### Changed (2026-03-19 — Settings redesign + Notifications + Audit Logs)

- Settings page no longer uses a single scrolling layout — each of the 8 sections is isolated behind a left-nav click (changed from original: was single long scroll, now left-nav + content panel)
- Danger Zone pattern applied to destructive actions in Settings (consistent with GitHub/Vercel conventions)

### Added (2026-03-19 — Phase 9: Production Auth + Phase 10: Multi-Tenancy)

- `dashboard/app/api/proxy/[...path]/route.ts` — catch-all Next.js proxy route; reads NextAuth session server-side and injects `X-User-Id` + `X-User-Role` headers before forwarding to FastAPI; all dashboard API calls now go through `/api/proxy/*`; unauthenticated requests return 401 before reaching FastAPI
- `get_active_project_id` FastAPI dependency (`src/langsight/api/dependencies.py`) — verifies project membership before returning `project_id` filter; non-members receive 404 (no enumeration); global admin with no `project_id` query param bypasses filter and sees all data
- `SecurityHeadersMiddleware` in `src/langsight/api/main.py` — adds `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `X-XSS-Protection: 1; mode=block`, `Referrer-Policy: strict-origin-when-cross-origin`, and `Strict-Transport-Security: max-age=31536000` (HTTPS only) to every API response
- `_is_proxy_request()` and `_get_session_user()` helpers in `src/langsight/api/dependencies.py` — trust `X-User-Id` / `X-User-Role` headers only when request originates from `127.0.0.1` or `::1`
- `require_admin()` dependency — checks session role for dashboard write operations

### Changed (2026-03-19 — Phase 9: Production Auth + Phase 10: Multi-Tenancy)

- `dashboard/lib/api.ts`: `BASE` changed from `/api` to `/api/proxy` — all dashboard requests are now authenticated via the NextAuth session proxy; `NEXT_PUBLIC_LANGSIGHT_API_KEY` is no longer required in the browser
- `dashboard/lib/auth.ts`: session callbacks now expose `userId` and `userRole` so the proxy can forward them as `X-User-Id` / `X-User-Role`
- `src/langsight/api/dependencies.py`: `verify_api_key()` now accepts session headers as auth — no API key required for dashboard users going through the proxy
- ClickHouse `get_cost_call_counts()` and `get_session_trace()` now accept optional `project_id` parameter; filter applied as `WHERE project_id = {project_id}` at DB level (no Python post-filter)
- `src/langsight/api/routers/agents.py`: `list_sessions` and `get_session` use `get_active_project_id` dependency — sessions are project-scoped
- `src/langsight/api/routers/costs.py`: `get_costs_breakdown` uses `get_active_project_id` dependency — replaces Python post-filter with DB-level isolation
- Dashboard pages (Overview, Sessions, Agents, Costs): all `useProject()` hook consumers now include `project_id` in SWR cache keys and fetch URLs when a project is active

### Security (2026-03-19 — Phase 9: Production Auth + Phase 10: Multi-Tenancy)

- `/api/users/verify` rate limited to 10 requests/minute per IP via `slowapi` — prevents brute-force against the login endpoint
- `X-User-Id` / `X-User-Role` headers trusted only from localhost proxy (`127.0.0.1` / `::1`) — external clients cannot spoof session identity

### Added (2026-03-19 — S.9 Threat Model)
- S.9: `docs/06-threat-model.md` — comprehensive threat model covering 5 trust boundaries, full attack surface table for all API endpoints and the OTEL Collector, data classification table with PII risk guidance, 10 threat scenarios (T-01 through T-10) each with attack path / impact / mitigations / residual risk, recommended production deployment topology with firewall rules, 8 documented known gaps (G-01 through G-08) with severity and mitigation notes, and a vulnerability disclosure policy with response time commitments
- S.9: `docs/04-implementation-plan.md` updated — S.9 marked complete (2026-03-19); Security Hardening progress updated to 10%

### Added (2026-03-19 — P5.7 Playground Replay)
- P5.7: Playground Replay — re-execute any session's tool calls against live MCP servers using stored `input_args`; replay stored as new session and auto-compared with original in the compare drawer
- P5.7: `POST /api/agents/sessions/{id}/replay` endpoint — configurable `timeout_per_call` (default 10s) and `total_timeout` (default 60s) parameters; returns `ReplayResponse` with `replay_session_id`
- P5.7: `replay_of: str | None` field on `ToolCallSpan` and `replay_of String DEFAULT ''` column on `mcp_tool_calls` ClickHouse table — links each replay span to its original span_id
- P5.7: `ReplayEngine` in `src/langsight/replay/engine.py` — filters to `tool_call` spans with `input_json` present, re-executes each via stored `input_args`, supports stdio (StdioServerParameters) and SSE/StreamableHTTP transports, fail-open per span (errors recorded as ERROR status spans, replay continues)
- P5.7: Replay button in trace drawer header — one click to replay and auto-open compare drawer diff between original and replay session; shows spinner and "Replaying..." while in flight; inline error message on failure

### Added (2026-03-19 — P5.6 Side-by-side session comparison)
- P5.6: Side-by-side session comparison — select two sessions (A/B) in the Workflows page and click Compare to see a diff table aligned by tool call order; diverged spans (status change or >=20% latency delta) highlighted in yellow
- P5.6: `GET /api/agents/sessions/compare?a=&b=` endpoint — returns aligned diff with `matched`/`diverged`/`only_a`/`only_b` entries and summary counts (`SessionComparison` response model)
- P5.6: `compare_sessions(session_a, session_b)` method on `ClickHouseBackend` — fetches both traces concurrently via `asyncio.gather`, aligns spans by `(server_name, tool_name)` call order, computes per-entry status
- P5.6: `_diff_spans()` helper — produces diff entries; `diverged` = status changed OR latency delta >= 20%; `only_a`/`only_b` for unmatched spans
- P5.6: `DiffEntry` and `SessionComparison` TypeScript interfaces added to `dashboard/lib/types.ts`
- P5.6: `compareSessions(a, b)` function added to `dashboard/lib/api.ts` — calls `GET /api/agents/sessions/compare`
- P5.6: `CompareDrawer` and `DiffRow` components in sessions page — colour-coded diff table (matched=green, diverged=yellow, only_a/only_b=blue/purple); latency delta column; first session row click selects A (blue), second click selects B (purple), Compare button appears when both are selected

### Added (2026-03-19 — P5.5 Agent SLO Tracking)
- P5.5: Agent SLO Tracking — define `success_rate` and `latency_p99` SLOs per agent; CRUD API at `/api/slos`; `SLOEvaluator` queries session data to compute current vs target; status is `ok`, `breached`, or `no_data`
- P5.5: `agent_slos` table added to SQLite and PostgreSQL backends; all four CRUD methods (`create_slo`, `list_slos`, `get_slo`, `delete_slo`) implemented on `StorageBackend` protocol and both backends
- P5.5: `SLOMetric` StrEnum (`success_rate`, `latency_p99`), `AgentSLO` Pydantic model, and `SLOEvaluation` Pydantic model added to `src/langsight/models.py`
- P5.5: `SLOEvaluator` class in `src/langsight/reliability/engine.py` — `success_rate` computed as `(clean_sessions / total_sessions) * 100`; `latency_p99` uses `max(duration_ms)` as a conservative proxy (true p99 requires raw span data)
- P5.5: `GET /api/slos/status` — evaluate all SLOs against current session data; `GET /api/slos` — list SLO definitions; `POST /api/slos` — create SLO; `DELETE /api/slos/{slo_id}` — delete SLO
- P5.5: Dashboard Overview "Agent SLOs" panel — shows per-SLO current value vs target with coloured status dot (`ok`=green, `breached`=red, `no_data`=grey); polls `/api/slos/status` every 60s via SWR; panel only renders when at least one SLO is defined
- P5.5: `SLOStatus` TypeScript interface added to `dashboard/lib/types.ts`; `getSLOStatus()`, `listSLOs()`, `deleteSLO()` functions added to `dashboard/lib/api.ts`

### Added (2026-03-19 — P5.4 Statistical anomaly detection)
- P5.4: Statistical anomaly detection — `AnomalyDetector` in `src/langsight/reliability/engine.py` computes z-score per tool against a 7-day ClickHouse baseline; fires `warning` anomaly when |z| >= 2 and `critical` when |z| >= 3 for both `error_rate` and `avg_latency_ms` metrics
- P5.4: `get_baseline_stats(baseline_hours=168)` method on `ClickHouseBackend` — queries `mv_tool_reliability` using `stddevPop()` and `avg()`; requires >= 3 sample hours to return a row, avoiding noisy baselines
- P5.4: `AnomalyResult` dataclass — `server_name`, `tool_name`, `metric`, `current_value`, `baseline_mean`, `baseline_stddev`, `z_score`, `severity`, `sample_hours`
- P5.4: Minimum stddev guards — `_MIN_STDDEV_ERROR_RATE = 0.01` (1%) and `_MIN_STDDEV_LATENCY_MS = 10.0` ms prevent false positives on perfectly stable tools
- P5.4: `GET /api/reliability/anomalies?current_hours=1&baseline_hours=168&z_threshold=2.0` endpoint — configurable detection window and sensitivity
- P5.4: `GET /api/reliability/tools?hours=24&server_name=...` endpoint — per-tool reliability metrics
- P5.4: `dashboard/lib/types.ts` — new `AnomalyResult` TypeScript interface
- P5.4: `dashboard/lib/api.ts` — new `getAnomalies(currentHours, zThreshold)` function calling `GET /api/reliability/anomalies`
- P5.4: Dashboard Overview "Anomalies Detected" metric card — live anomaly count with critical/warning breakdown, colour-coded severity, polls every 60s via SWR (replaces static "Tool Alerts" card)

### Added (2026-03-19 — P5.3 LLM reasoning capture)
- P5.3: LLM reasoning capture — OTLP spans carrying `gen_ai.prompt`/`gen_ai.completion` (or `llm.prompts`/`llm.completions`) attributes are now extracted and stored as `span_type="agent"` spans with `llm_input`/`llm_output` fields; model name extracted from `gen_ai.request.model`/`llm.model_name` and written to `tool_name`
- P5.3: `llm_input: str | None` and `llm_output: str | None` added to `ToolCallSpan` in `src/langsight/sdk/models.py`; `ToolCallSpan.record()` accepts and passes through both fields
- P5.3: ClickHouse `mcp_tool_calls` DDL extended with `llm_input Nullable(String)` and `llm_output Nullable(String)`; `_SPAN_COLUMNS`, `_span_row()`, and `get_session_trace()` updated
- P5.3: `SpanNode` API response model (`api/routers/agents.py`) includes `llm_input` and `llm_output` fields
- P5.3: `SpanNode` TypeScript interface (`dashboard/lib/types.ts`) updated with `llm_input: string | null` and `llm_output: string | null`
- P5.3: Sessions page (`dashboard/app/(dashboard)/sessions/page.tsx`) detects LLM spans (`span_type="agent"` with `llm_input`/`llm_output`) and shows "Prompt" / "Completion" labels in the detail panel instead of generic "Input" / "Output"
- P5.3: OTLP attribute parser (`api/routers/traces.py`) now handles `intValue`, `doubleValue`, and `boolValue` in addition to `stringValue`

### Added (2026-03-19 — P5.2 session replay payload visibility)
- P5.2: Session replay payload visibility — clicking any span row in the trace tree now expands an inline panel showing formatted input arguments and output result; error details shown for failed spans with no output (requires P5.1 payload capture)
- P5.2: `SpanNode` API response model (`api/routers/agents.py`) now includes `input_json: str | None` and `output_json: str | None` fields, passed through from `get_session_trace()`
- P5.2: `SpanNode` TypeScript interface (`dashboard/lib/types.ts`) updated with `input_json: string | null` and `output_json: string | null`

### Added (2026-03-18 — P5.1 payload capture)
- P5.1: Input/output payload capture — `ToolCallSpan` now records tool call arguments (`input_args: dict | None`) and return values (`output_result: str | None`); stored in ClickHouse `mcp_tool_calls` as `input_json Nullable(String)` / `output_json Nullable(String)`
- P5.1: `redact_payloads: bool = False` config flag on `LangSightConfig` and `LangSightClient` constructor — set `true` to suppress payload capture for PII-sensitive tools; redaction is applied before transmission (payloads never leave the host process when enabled)
- P5.1: Per-wrap `redact_payloads` override on `LangSightClient.wrap()` — allows different redaction behaviour per MCP client instance without changing the global config
- P5.1: `get_session_trace()` now returns `input_json` and `output_json` in every span row

### Added (2026-03-18 — costs API + agents dashboard)
- `GET /api/costs/breakdown` — per-tool cost breakdown endpoint
- `GET /api/costs/by-agent` — per-agent cost aggregation endpoint
- `GET /api/costs/by-session` — per-session cost aggregation endpoint
- `AgentCostEntry` and `SessionCostEntry` dataclasses in `costs/engine.py` — typed aggregation records for agent-level and session-level cost rollups
- `aggregate_cost_rows()` helper in `costs/engine.py` — shared aggregation logic used across all three cost endpoints
- `get_cost_call_counts()` method on ClickHouse backend (`storage/clickhouse.py`) — per-tool call count query
- Agents dashboard page (`dashboard/app/(dashboard)/agents/page.tsx`) — per-agent summary table showing sessions, calls, failures, total cost, duration, and unique MCP servers per agent
- Costs page upgraded to full breakdown view (`dashboard/app/(dashboard)/costs/page.tsx`) — three breakdown tables: by tool, by agent, by session
- `config_path` stored in `app.state` in `api/main.py` — routers can now access the config path without a global
- `tests/unit/test_cost_engine.py` (86 lines) and `tests/unit/api/test_costs_router.py` (134 lines) — unit coverage for new cost layer
- `tests/integration/storage/test_costs_integration.py` — integration test for `get_cost_call_counts()` against real ClickHouse

### Changed (2026-03-18 — dashboard nav and page renames)
- Dashboard sidebar nav reordered to agent-first hierarchy: Overview → Sessions → Agents → Costs → Tool Health → MCP Security (`dashboard/components/sidebar.tsx`)
- "MCP Health" dashboard page renamed to "Tool Health" (`dashboard/app/(dashboard)/health/page.tsx`) — scoping is honest: the page monitors tool-level health, not only MCP
- "Security Posture" dashboard page renamed to "MCP Security" (`dashboard/app/(dashboard)/security/page.tsx`) — scoping is honest: deep security scanning is MCP-specific

### Changed (2026-03-18 — agent-first repositioning)
- Product positioning updated from "MCP observability and security platform" to "observability platform for AI agent actions — full traces of every tool call across single and multi-agent workflows, with deep MCP health monitoring and security scanning built in." MCP remains a deep feature, not the lead identity.
- `README.md`: tagline updated to lead with agent action tracing; "Why LangSight" table reordered — agent session traces and multi-agent handoffs now first and second, cost attribution moved up to third, MCP health and security remain as fourth/fifth; NOTE callout rewritten to contrast with Langfuse/LangSmith ("what your agent thought" vs "what your agent did")
- `docs/01-product-spec.md`: One-Liner updated to agent-first framing; Elevator Pitch now opens with the primary on-call question before listing tool types; Problem Statement now leads with the agent visibility gap as the primary problem rather than MCP infrastructure
- `docs-site/introduction.mdx`: frontmatter description updated; "What is LangSight?" section now opens with the Langfuse/LangSmith contrast and the primary on-call question before explaining tool type breakdown; CardGroup card copy updated — MCP cards now explicitly scoped as "for MCP servers specifically"
- `website/app/page.tsx`: hero subheadline rewritten to lead with agent action tracing and multi-agent workflows; MCP depth framed as an additional capability, not the primary hook
- `CLAUDE.md`: "What We're Building" section updated to agent-first description



### Fixed (2026-03-18 — documentation correctness)
- `README.md`: sessions example output now matches actual CLI columns (`Session`, `Agent`, `Calls`, `Failed`, `Duration`, `Servers`) — removed non-existent `Cost` column
- `README.md`: features section and CLI reference table no longer claim `langsight sessions` shows per-session cost; cost field is absent from the current implementation
- `README.md`: architecture diagram and Phase 2 roadmap no longer list OpenAI Agents SDK integration — that file (`src/langsight/integrations/openai_agents.py`) does not exist; shipped integrations are CrewAI, Pydantic AI, LangChain/Langflow/LangGraph/LangServe, and LibreChat
- `CHANGELOG.md`: removed two references to `agent_session()` context manager — no such symbol exists in `src/`; session propagation is via explicit `session_id`/`trace_id` fields on `ToolCallSpan`
- `CHANGELOG.md`: removed OpenAI Agents SDK integration adapter entry (file never shipped)
- `PROGRESS.md`: corrected `agent_session()` context manager row to accurately describe what exists (`session_id` propagated via span fields, no context manager)
- `docs/04-implementation-plan.md`: Section 2.2 framework integration task FW.3 now references `langchain.py` (shipped) instead of `openai_agents.py` (not shipped); acceptance criteria updated accordingly
- `docs/04-implementation-plan.md`: Section 1 annotated with historical note explaining that `agentguard` CLI names and `pip install agentguard` are from the original pre-rename plan; current entry point is `langsight`

Pre-production security hardening required before 0.2.0 can be positioned as production-grade.

### Planned (Phase 7: Model-Based Cost Tracking — planned 2026-03-19)

- P7.1: `model_pricing` table (SQLite + Postgres) with `(provider, model_id, effective_from)` unique constraint; 16 seed rows for Anthropic (4 models), OpenAI (5 models), Google (3 models), Meta (2 models), AWS (2 models); `StorageBackend` protocol methods: `create_model_pricing`, `list_model_pricing`, `get_model_pricing_by_model_id`, `update_model_pricing`, `deactivate_model_pricing`; Alembic migration `add_model_pricing`
- P7.2: `input_tokens: int | None`, `output_tokens: int | None`, `model_id: str | None` fields on `ToolCallSpan`; `mcp_tool_calls` ClickHouse DDL extended with `input_tokens Nullable(UInt32)`, `output_tokens Nullable(UInt32)`, `model_id String DEFAULT ''`; OTLP parser extracts `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.request.model` from span attributes
- P7.3: `ModelPricingLookup` helper class in `costs/engine.py` — indexes active pricing rows by `model_id`, `cost_for()` returns 0.0 for unknown models (fail-open); cost engine routes per span: token-based for spans with `model_id` + token counts, call-based CostRule fallback otherwise; `CostEntry` gains `cost_type: "token_based" | "call_based"`; all three cost endpoints (`/breakdown`, `/by-agent`, `/by-session`) gain optional `project_id` query param; `/breakdown` response gains `llm_cost_usd` and `tool_cost_usd` top-level fields
- P7.4: `GET /api/costs/models` — list all pricing entries; `POST /api/costs/models` — add custom model (admin only); `PATCH /api/costs/models/{id}` — price update with audit trail (deactivates old row, inserts new); `DELETE /api/costs/models/{id}` — deactivate (soft delete, admin only)
- P7.5: `ModelPricingSection` component in Settings page — table grouped by provider, inline edit form, "Add custom model" modal; "Custom" badge on user-added rows; inactive rows hidden by default behind "Show history" toggle
- P7.6: Costs page gains "LLM Tokens Cost" and "Tool Calls Cost" summary cards; "Top Model" card; "By Model" table with columns: Model | Provider | Input Tokens | Output Tokens | Total Cost | % of Spend

### Planned (Phase 6: Project-Level RBAC — planned 2026-03-19)

- P6.1: Data model — `Project` and `ProjectMember` Pydantic models; `projects` + `project_members` tables (SQLite + Postgres); `project_id` column on ClickHouse `mcp_tool_calls`, `agent_slos`, `api_keys`; Alembic migration
- P6.2: Storage layer — project + member CRUD protocol methods on `StorageBackend`; implemented on `SQLiteBackend` and `PostgresBackend`; `list_projects_for_user(user_id)` for membership-scoped project lists
- P6.3: API middleware — `get_project` FastAPI dependency (global admin bypass, HTTP 404 for non-members); `require_project_role` dependency factory; new `/api/projects` router with 9 endpoints (list, create, get, rename, delete, list-members, add-member, change-role, remove-member)
- P6.4: Scope existing endpoints — optional `project_id` query param on `GET /api/agents/sessions`, reliability, costs, SLOs, and OTLP/span ingestion endpoints; compare endpoint rejects cross-project pairs with HTTP 400
- P6.5: SDK — `project_id: str | None` param on `LangSightClient.__init__()`; field on `ToolCallSpan`; propagated to every emitted span
- P6.6: Dashboard — project switcher dropdown in sidebar; active project stored in `localStorage`; all API calls scoped by `?project_id=`; Settings > Projects tab for create/invite/manage
- P6.7: Bootstrap — `_bootstrap_default_project()` creates "Default" project with admin as owner on first API startup; idempotent on subsequent restarts

### Planned (Phase 5: Deep Observability — next major phase after Security Hardening)
- Phase 5 gap analysis completed (2026-03-18): code review identified 7 missing features required for full session debugging capability
- ~~P5.1: Input/output payload capture~~ — **shipped (2026-03-18)**, see Added section above
- ~~P5.2: Session replay trace tree UI~~ — **shipped (2026-03-19)**, see Added section above
- ~~P5.3: LLM reasoning capture~~ — **shipped (2026-03-19)**, see Added section above
- ~~P5.4: Statistical anomaly detection~~ — **shipped (2026-03-19)**, see Added section above
- ~~P5.5: Agent SLO tracking~~ — **shipped (2026-03-19)**, see Added section above
- ~~P5.6: Side-by-side session comparison~~ — **shipped (2026-03-19)**, see Added section above
- ~~P5.7: Playground replay~~ — **shipped (2026-03-19)**, see Added section above

### Planned (Security Hardening S.1-S.10 — required before 0.2.0 production positioning)
- S.1: API key middleware for all API endpoints (currently unauthenticated — P0)
- S.2: RBAC — admin and viewer roles at router dependency level
- S.3: Dashboard real credential store or OIDC integration (currently demo-only — P0)
- S.4: Rate limiting on `POST /api/traces/spans` and `POST /api/traces/otlp`
- S.5: Audit logging for security-sensitive actions (scans triggered, auth failures, config changes)
- S.6: No default secrets in `docker-compose.yml` — require explicit env var injection
- S.7: ClickHouse and Postgres ports removed from host binding in compose (internal network only)
- S.8: Alembic migrations for Postgres; versioned SQL scripts for ClickHouse
- S.9: `docs/06-threat-model.md` — trust boundaries, attack surface, vulnerability disclosure policy
- S.10: Split `GET /api/status` into `/readiness` and `/liveness` for correct Kubernetes probe behavior

### Planned (Phase 4 remaining — manual deployment steps)
- R.4: Mintlify deployment — connect `docs-site/` on mintlify.com dashboard to `docs.langsight.dev`
- Phase 4 website Vercel deployment — connect `website/` repo on vercel.com

### Fixed (2026-03-23 — Audit pass 1: OOM, rate limiting, isolation, correctness)

- **SDK dict caps** — `_loop_detectors`, `_session_budgets`, and `_circuit_breakers` dicts capped at 500 / 100 / 500 entries respectively with FIFO eviction; prevents OOM DoS via unbounded growth from random `session_id` values.
- **Rate limiter key** — rate limiter now keys on `X-Forwarded-For` first, then `X-API-Key` prefix (first 8 chars), then TCP address; each dashboard user gets an independent bucket instead of sharing one global bucket behind the proxy.
- **Session compare cross-project leak** — `/api/agents/compare` was returning unfiltered cross-project spans; result is now replaced with project-scoped spans before returning.
- **Overview health URL missing `project_id`** — health URL on the Overview page now includes the active `project_id` query param; non-admin users no longer see a wrong or empty server list.
- **Health listing sequential loop** — `/api/health/servers` now uses `asyncio.gather()` to fetch all server health entries concurrently instead of a sequential loop.
- **ClickHouse `get_untagged_sessions()` invalid WHERE** — `max(ended_at)` filter moved from `WHERE` to `HAVING` clause; was causing ClickHouse to reject the query for aggregates in non-aggregate context.
- **`mv_tool_reliability` missing `project_id`** — materialized view `GROUP BY` now includes `project_id`; multi-tenant reliability queries were merging data across projects.
- **SDK missing `async with` support** — `LangSightClient` now implements `__aenter__` / `__aexit__` for safe `async with client:` usage and guaranteed flush on exit.
- **`/api/status` version fallback** — version field now falls back to reading `pyproject.toml` directly when the `langsight` package is not installed (e.g. development installs without `pip install -e .`).
- **`test-mcps` Postgres port conflict** — `test-mcps/docker-compose.yml` Postgres port changed from `5432` to `5433` to avoid conflict with the main stack's Postgres container.

### Fixed (2026-03-23 — Audit pass 2: concurrency, startup, fingerprinting, schema)

- **SDK buffer lock** — `send_span`, `send_spans`, and `flush` in `LangSightClient` are now protected by `asyncio.Lock`; concurrent flushes could previously corrupt the buffer or lose spans.
- **`otel-collector` startup dependency** — `otel-collector` docker-compose service no longer depends on `api: service_healthy`; SDK clients no longer receive connection-refused errors during API cold starts.
- **Default project bootstrap** — `_bootstrap_default_project()` is now called on API startup; new installs get a real "Default" project automatically instead of only the seed "Sample Project".
- **`/api/status` fingerprinting** — `servers_configured`, `auth_enabled`, and `storage_mode` fields removed from the unauthenticated `/api/status` response; these fields were exposable to unauthenticated callers and useful for fingerprinting the deployment.
- **`mcp_health_results` missing `project_id`** — ClickHouse `mcp_health_results` table DDL now includes a `project_id` column; an `ALTER TABLE IF EXISTS` migration is applied for existing installs to add the column without data loss.

## [0.3.1] - 2026-03-22 — Prevention Config

### Added

- **`prevention_config` Postgres table** — per-project, per-agent prevention thresholds persisted in the platform. `agent_name="*"` row is the project-level default that applies to all agents without a specific config entry.
- **`PreventionConfig` domain model** (`models.py`) — fields: `id`, `project_id`, `agent_name`, `loop_enabled`, `loop_threshold`, `loop_action`, `max_steps`, `max_cost_usd`, `max_wall_time_s`, `budget_soft_alert`, `cb_enabled`, `cb_failure_threshold`, `cb_cooldown_seconds`, `cb_half_open_max_calls`.
- **API endpoints**: `GET /api/agents/{name}/prevention-config`, `PUT /api/agents/{name}/prevention-config`, `DELETE /api/agents/{name}/prevention-config`, and project-default equivalents under `/api/projects/{id}/prevention-config`.
- **SDK: `LangSightClient._apply_remote_config()`** — background task launched on `wrap()` that fetches the agent's dashboard config and merges it over constructor defaults. Non-blocking: `wrap()` returns immediately; the remote config takes effect before the first tool call. Falls back to constructor params when the API is unreachable.
- **Dashboard: Prevention tab in Settings** — per-agent table with inline edit forms for all threshold fields. Project default row (`*`) always shown at top.
- **Demo seed**: 5 sample `prevention_config` rows covering demo agents.

## [0.3.0] - 2026-03-22 — Prevention Layer (Tier 1)

### Added

- **SDK: Circuit breaker** (`src/langsight/sdk/circuit_breaker.py`) — per-server CLOSED → OPEN → HALF_OPEN state machine. Configurable failure threshold (default 5), cooldown period (default 60s), and half-open test calls (default 2). When open, tool calls are rejected immediately without hitting the server. Recovery is automatic via half-open test calls.
- **SDK: Loop detector** (`src/langsight/sdk/loop_detector.py`) — per-session sliding window (default 20 calls) detecting three patterns: repetition (same tool + same args N times), ping-pong (alternating between two tool+args pairs), and retry-without-progress (same tool + same error repeated). Configurable threshold (default 3) and action (`warn` or `terminate`).
- **SDK: Budget guardrails** (`src/langsight/sdk/budget.py`) — per-session tracking of step count, wall time, and cumulative cost. Step count and wall time are checked pre-call; cost limit fires post-call on the first call that pushes over the threshold. Soft alert at configurable fraction (default 80%) fires once per limit type.
- **SDK: Prevention integration in `call_tool()`** — pre-call checks (circuit breaker, loop detection, budget step/wall-time) and post-call state updates (loop detector record, budget cost/step increment, circuit breaker success/failure). All prevention params default to disabled for backward compatibility.
- **New SDK constructor params**: `loop_detection`, `loop_threshold`, `loop_action`, `max_cost_usd`, `max_steps`, `max_wall_time_s`, `budget_soft_alert`, `pricing_table`, `circuit_breaker`, `circuit_breaker_threshold`, `circuit_breaker_cooldown`, `circuit_breaker_half_open_max`.
- **New alert types**: `LOOP_DETECTED`, `BUDGET_WARNING`, `BUDGET_EXCEEDED`, `CIRCUIT_BREAKER_OPEN`, `CIRCUIT_BREAKER_RECOVERED` in `alerts/engine.py`.
- **`AlertEngine.evaluate_prevention_event()`** — new method that creates alerts from SDK prevention events. Unlike health-check evaluation, prevention events always produce an alert (no threshold needed).
- **`ToolCallStatus.PREVENTED`** — new status value for tool calls blocked by prevention layer.
- **`PreventionEvent` model** (`sdk/models.py`) — SDK-originated event model for loop/budget/circuit-breaker events.
- **New exceptions**: `LoopDetectedError`, `BudgetExceededError`, `CircuitBreakerOpenError` in `exceptions.py`.
- **Health tag engine** (`src/langsight/tagging/engine.py`) — `HealthTag` enum with 8 tags: `success`, `success_with_fallback`, `loop_detected`, `budget_exceeded`, `tool_failure`, `circuit_breaker_open`, `timeout`, `schema_drift`. `tag_from_spans()` computes tags from session spans using priority ordering.
- **Dashboard: `HealthTagBadge` component** (`dashboard/components/health-tag-badge.tsx`) — colored tag badges for session health status.
- **Dashboard: Sessions page** — health tag column added to session list, filter dropdown for filtering by health tag.
- **Dashboard: `HealthTag` type** and `health_tag` field on `AgentSession` type.
- **`CircuitBreakerConfig`** added as optional field on `MCPServer` model for per-server circuit breaker overrides.

---

## [0.1.0] — 2026-03-18

Phase 1, Phase 2, Phase 3, and Phase 4 (website + dashboard) complete. First public release: PyPI published, GitHub release tagged.

### Added

#### Phase 4: Website + Dashboard (2026-03-18)
- Marketing website built with Next.js 15 + Tailwind CSS at `website/` — all sections: hero, features, how-it-works, integrations, providers, pricing
- Product dashboard v2 built with Next.js 15 + shadcn/ui at `dashboard/` — Overview, Health, Sessions, Security, Costs pages
- `LangSightLangChainCallback` — LangChain framework integration covering LangChain agents, Langflow, LangGraph, and LangServe (`src/langsight/integrations/langchain.py`)
- PyPI release: `langsight==0.1.0` published at https://pypi.org/project/langsight/
- GitHub release `v0.1.0` tagged with full CHANGELOG notes
- `dist/langsight-0.1.0-py3-none-any.whl` and `dist/langsight-0.1.0.tar.gz` generated
- `docs-site/cli/sessions.mdx` — previously the only missing Mintlify page, now written
- README PyPI version badge added

#### Security Assessment (2026-03-18)
- Security review completed — findings documented in `PROGRESS.md` and `docs/04-implementation-plan.md`
- P0.1: `api/main.py` — wildcard CORS, no auth on routers — any client reaching port 8000 can trigger scans and read all data
- P0.2: `dashboard/lib/auth.ts` — hardcoded users, any password accepted, static secret fallback — explicitly demo-mode only
- P1.1: `docker-compose.yml` — ClickHouse default user, default Postgres password, databases exposed to host
- P1.2: Cost engine `total` is a placeholder; per-session cost field absent from `langsight sessions` CLI output

#### CLI (8 commands)
- `langsight init` — auto-discovers Claude Desktop, Cursor, VS Code MCP configs
- `langsight mcp-health` — Rich table, `--json` flag, exit 1 on DOWN/DEGRADED
- `langsight security-scan` — Rich table, `--json`, `--ci` flag (exit 1 on CRITICAL)
- `langsight monitor` — continuous monitoring daemon, `--once` and `--interval` flags
- `langsight investigate` — Claude Agent SDK RCA with rule-based fallback; supports Claude, OpenAI, Gemini, Ollama
- `langsight costs` — cost attribution report with ClickHouse backend
- `langsight sessions` — Rich table of recent agent sessions with cost + failure counts
- `langsight sessions --id <id>` — full multi-agent trace tree for one session
- `langsight serve` — starts FastAPI REST API server

#### REST API (9 endpoints)
- `GET /api/agents/sessions` — list agent sessions with aggregated cost, call count, failure count
- `GET /api/agents/sessions/{session_id}` — full span tree reconstructed via `parent_span_id`
- `GET /api/health/servers` — list MCP servers with health status
- `GET /api/health/servers/{name}` — single server health detail
- `POST /api/security/scan` — trigger security scan
- `POST /api/traces/spans` — ingest `ToolCallSpan` batches from SDK and plugins
- `POST /api/traces/otlp` — ingest standard OTLP protobuf spans
- `GET /api/status` — API health and component status

#### Multi-Agent Tracing
- `parent_span_id` field on `ToolCallSpan` — enables multi-agent call tree reconstruction (same model as OpenTelemetry)
- `span_type` field on `ToolCallSpan` — `tool_call` | `agent` | `handoff`
- `agent_name` field on `ToolCallSpan` — per-agent reliability metrics
- `ToolCallSpan.agent_span()` — lifecycle spans for agent start/end events
- `ToolCallSpan.handoff_span()` — explicit spans recording agent-to-agent delegation

#### SDK
- `LangSightClient` Python SDK — 2-line MCP client instrumentation
- `wrap(mcp_client, client)` proxy — intercepts all `call_tool()` calls, records `ToolCallSpan`

#### Framework Integrations
- `LangSightCrewAICallback` — CrewAI framework adapter
- Pydantic AI integration adapter — wraps `Tool` objects at registration
- LibreChat native plugin (`integrations/librechat/langsight-plugin.js`) — `LANGSIGHT_URL` env var pattern

#### Storage Backends
- SQLite backend (default) — zero-dependency local mode, async, DDL on first open
- PostgreSQL backend — SQLAlchemy async
- ClickHouse backend — `mcp_tool_calls` table with `parent_span_id` + `span_type`, TTL 90 days, `mv_agent_sessions` materialized view

#### Infrastructure
- Docker Compose (root) — ClickHouse + PostgreSQL + OTEL Collector + API
- GitHub Actions CI — lint (ruff + mypy), unit/regression (pytest, 85% coverage gate), integration jobs

#### Docs
- `docs-site/` — 28 Mintlify pages covering all features (quickstart, CLI reference, SDK, integrations, API, self-hosting)

### Changed
- Product framing updated to "complete observability for everything an AI agent calls" — MCP servers, HTTP APIs, Python functions, and sub-agents (2026-03-17)
- One-liner updated: "LangSight is complete observability for everything an AI agent calls — MCP servers, HTTP APIs, functions, and sub-agents — with built-in health monitoring and security scanning for MCP servers."
- Capability matrix added to docs, README, and introduction page — makes explicit which features apply to all tool types vs MCP-only
- Agent session example updated in quickstart and product spec to show mixed tool types (MCP + HTTP API + function + sub-agent) in one trace tree
- Key framing documented: agent-level observability is a superset of MCP observability; `server_name` in `ToolCallSpan` is not locked to MCP servers
- `docs/01-product-spec.md`: one-liner, elevator pitch, product vision all updated with complete framing
- `docs-site/introduction.mdx`: description, hero section, capability table, and mixed session example added
- `docs-site/quickstart.mdx`: session drill-down example updated to show mixed tool types
- `README.md`: tagline, opening paragraph, and capability table added
- `PROGRESS.md`: project description at top updated to reflect final framing

### Architecture Decisions
- **All tool types observed, MCP gets proactive depth** (2026-03-17): The SDK and OTLP ingestion paths capture every call an agent makes regardless of type. The distinction is proactive vs passive: MCP servers can be pinged, listed, schema-checked, and CVE-scanned between agent sessions. Stripe, Sendgrid, and Python functions cannot — no standard protocol exists to do that. This is not a limitation; it is the accurate model of what observability can provide per tool type.

### Added
- `LangSightClient` Python SDK wrapper — 2-line MCP client instrumentation
- `wrap(mcp_client, client)` proxy — intercepts all `call_tool()` calls, records `ToolCallSpan`
- `LangSightCrewAICallback` framework adapter for CrewAI agents
- Pydantic AI integration adapter — wraps `Tool` objects at registration
- LibreChat native plugin (`integrations/librechat/langsight-plugin.js`) — LANGSIGHT_URL env var pattern, ~50 lines
- `POST /api/traces/spans` ingestion endpoint — accepts `ToolCallSpan` batches from SDK and plugins
- `langsight investigate` command — Claude Agent SDK RCA with rule-based fallback
- `parent_span_id` field on `ToolCallSpan` — enables multi-agent call tree reconstruction; same model as OpenTelemetry distributed tracing
- `span_type` field on `ToolCallSpan` — `tool_call` | `agent` | `handoff`
- `agent_name` field on `ToolCallSpan` — for per-agent reliability metrics
- Agent spans — lifecycle spans for agent start/end events
- Handoff spans — explicit spans recording agent-to-agent delegation with parent and child agent names
- `GET /api/agents/sessions` endpoint — list agent sessions with aggregated cost, call count, failure count
- `GET /api/agents/sessions/{session_id}` endpoint — full span tree for one session, reconstructed via `parent_span_id`
- `langsight sessions` CLI command — Rich table of recent sessions with cost and failures
- `langsight sessions --id <id>` — full multi-agent trace view for one session
- `mv_agent_sessions` ClickHouse materialized view (Phase 3) — pre-aggregates session-level metrics

### Changed
- Product positioning: primary value proposition is now agent session tracing and multi-agent tree visibility; MCP health monitoring and security scanning are secondary (but still unique vs competitors)
- Product one-liner updated: "LangSight is the observability layer for AI agent tool calls — traces, costs, and reliability across single and multi-agent workflows, with built-in MCP health monitoring and security scanning."
- README tagline updated to lead with agent observability
- Quickstart updated: Step 3 is now "Trace your agent sessions"; health check moved to Step 4
- `docs/01-product-spec.md`: elevator pitch, feature list, competitor table, "What We Don't Build" all updated
- `docs/04-implementation-plan.md`: Phase 2 section 2.6 added for agent sessions/multi-agent tracing; ClickHouse schema updated with `parent_span_id`, `session_id`, `agent_name`, `span_type`

### Architecture Decisions
- **Agent-observability-first pivot** (2026-03-17): Primary user question is "what did my agent call, in what order, how long did each tool take, which ones failed, what did it cost?" MCP health is a differentiating secondary feature. Repositioning does not change the roadmap — it changes the narrative and the CLI UX entry point.
- **`parent_span_id` for multi-agent trees** (2026-03-17): Using the OpenTelemetry span parent-child model rather than a proprietary tree structure. No separate tree storage needed — reconstruction is a recursive query on flat span tables. This is the same model Jaeger and Tempo use for distributed traces.
- **SDK-first before OTEL** (2026-03-17): Engineers integrate via `LangSightClient` + `wrap()` before configuring OTEL infrastructure. OTEL remains in Phase 3 for enterprise teams that already run collectors.
- **LibreChat plugin, not OTEL** (2026-03-17): LibreChat uses env vars for Langfuse integration natively; LangSight follows the same pattern rather than requiring OTEL.
- **Framework adapters alongside SDK** (2026-03-17): CrewAI/Pydantic AI users get idiomatic integration objects instead of having to find and wrap the MCP client manually.
- **LangSight is complementary to Langfuse, not competing** (2026-03-17): Langfuse traces LLM calls (prompts, completions). LangSight traces tool calls (MCP spans). They answer different questions and are used together. This distinction is now explicit in product docs and README.

---

## [0.0.1] — 2026-03-16

Project scaffold.

### Added
- Repository structure: `src/langsight/`, `tests/`, `test-mcps/`, `docs/`, `.claude/agents/`
- `pyproject.toml`: src layout, uv, ruff, mypy strict, `langsight` entry point
- `CLAUDE.md`: engineering standards, agent workflow, testing mandate
- Product docs: 5 docs covering spec, architecture, UI/features, impl plan, risk assessment
- `.gitignore`: covers `.env`, `.venv`, `.claude/skills/`, secrets
- `skills-lock.json`: 52 active project skills
- 6 specialised agents: tester, security-reviewer, debugger, release-engineer, docs-keeper, git-keeper
