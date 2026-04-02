"use client";

export default function McpMonitoringProductionPost() {
  return (
    <main className="min-h-screen bg-[var(--bg)] text-[var(--fg)]">
      {/* Nav */}
      <header className="sticky top-0 z-50 border-b border-[var(--border)] bg-[var(--bg)]/90 backdrop-blur-sm">
        <div className="max-w-3xl mx-auto px-6 h-14 flex items-center justify-between">
          <a href="/" className="flex items-center gap-2 font-semibold text-[var(--fg)]">
            <img src="/logo-icon.svg" alt="LangSight" className="w-7 h-7" />
            LangSight
          </a>
          <a href="/blog/" className="text-sm text-[var(--muted)] hover:text-[var(--fg)] transition-colors">
            ← All posts
          </a>
        </div>
      </header>

      <article className="max-w-3xl mx-auto px-6 py-16">
        {/* Header */}
        <div className="mb-10">
          <div className="flex flex-wrap gap-2 mb-4">
            {["MCP Monitoring", "Health Checks", "Production"].map((tag) => (
              <span key={tag} className="text-xs px-2 py-0.5 rounded-full bg-[var(--indigo)]/10 text-[var(--indigo)] font-medium">
                {tag}
              </span>
            ))}
          </div>
          <h1 className="text-4xl font-bold leading-tight mb-4">
            How to Monitor MCP Servers in Production
          </h1>
          <p className="text-xl text-[var(--muted)] leading-relaxed mb-6">
            Your agents depend on MCP servers. If one goes down, your agents fail silently — no error message, no alert, just a confused user wondering why nothing happened. Here is how to set up proactive health monitoring, latency tracking, and uptime alerting for your entire MCP fleet.
          </p>
          <div className="flex items-center gap-4 text-sm text-[var(--muted)] border-t border-[var(--border)] pt-6">
            <span>April 2, 2026</span>
            <span>·</span>
            <span>10 min read</span>
            <span>·</span>
            <span>LangSight Engineering</span>
          </div>
        </div>

        {/* Hero image */}
        <div className="mb-10 rounded-xl overflow-hidden border border-[var(--border)]">
          <img src="/blog/mcp-monitoring-production.png" alt="How to Monitor MCP Servers in Production" className="w-full" />
        </div>

        {/* Content */}
        <div className="prose-custom">

          <h2>It is 2 AM and your agent just stopped working</h2>
          <p>
            You get paged at 2 AM. The customer support agent that handles overnight tickets has not responded to anything in 90 minutes. Thirty-seven tickets are stuck in the queue. The agent is not erroring out — it is just not doing anything.
          </p>
          <p>
            After 45 minutes of digging through logs, you find the root cause: the <code>slack-mcp</code> server that the agent uses to post responses ran out of memory and crashed at 12:14 AM. No alert fired. No health check caught it. The agent tried to call the <code>send_message</code> tool, got a timeout, retried three times, hit its retry budget, and silently gave up.
          </p>
          <p>
            This is not a hypothetical. This is the most common failure pattern for teams running MCP-based agents in production. The agent is fine. The LLM is fine. The infrastructure that the agent depends on — the MCP servers — is the blind spot.
          </p>
          <p>
            Langfuse and similar tools will show you what the LLM decided. They will not show you that the tool it tried to call has been down for two hours. You need a different layer of observability: one that watches the hands, not the brain.
          </p>

          <h2>Why MCP servers need their own monitoring</h2>
          <p>
            MCP servers are not regular APIs. They run in three different transport modes, each with fundamentally different failure characteristics. You cannot treat them like a REST endpoint behind an ALB.
          </p>
          <p>
            An MCP server might be a local subprocess communicating over stdio, an SSE endpoint streaming events over a persistent HTTP connection, or a standard HTTP server accepting JSON-RPC requests. The protocol is the same — the operational reality is completely different.
          </p>
          <p>
            Traditional monitoring tools (Datadog, Prometheus, Grafana) can monitor HTTP endpoints. They cannot monitor a subprocess that communicates over stdin/stdout. They cannot detect that an SSE connection has silently stalled — still technically open, but no longer sending events. They do not understand MCP's tool schema or know when a server has changed its tool definitions out from under your agents.
          </p>
          <p>
            MCP monitoring requires protocol awareness. You need something that speaks MCP natively, can negotiate all three transports, and understands the difference between "the server is up" and "the server is healthy."
          </p>

          <h2>The three transport types and how they fail</h2>

          <h3>stdio: process crashes, OOM, and hanging calls</h3>
          <p>
            stdio-based MCP servers run as child processes. The MCP client spawns them with a command like <code>python server.py</code> or <code>npx @mcp/postgres</code>, then communicates over stdin/stdout using JSON-RPC.
          </p>
          <p>
            Failure modes are process-level: the server process gets OOM-killed by the OS, crashes with an unhandled exception, or hangs on a blocking call (a common issue with synchronous database drivers in an async context). When a stdio process dies, the only signal is that the pipe closes. If the client is not watching for broken pipes, it may not notice for minutes.
          </p>
          <pre>{`# Common stdio failure: server hangs on blocking I/O
# The process is alive but not responding to stdin
$ ps aux | grep mcp-server
user  12847  98.2  4.1  python server.py   # alive, but stuck

# LangSight detects this via synthetic health probes
$ langsight mcp-health --server postgres-mcp
postgres-mcp    DOWN    timeout after 5000ms    no response to tools/list`}</pre>

          <h3>SSE: connection drops and event stream stalls</h3>
          <p>
            SSE (Server-Sent Events) transport uses a long-lived HTTP connection. The client connects once and receives a stream of events. This is the most common transport for remote MCP servers.
          </p>
          <p>
            SSE connections fail in ways that are hard to detect. The TCP connection can remain open even after the server process stops writing events — a half-open connection that looks healthy from the client side. Load balancers can silently close idle connections without sending a FIN. The server can fall behind on event processing, causing the event buffer to grow until it triggers backpressure or OOM.
          </p>
          <p>
            The worst failure mode is a reconnection storm: the client detects a dropped connection, reconnects, the server accepts the connection, then immediately drops it due to resource exhaustion. The client retries in a tight loop, making the server's resource situation worse.
          </p>
          <pre>{`# SSE stall detection in LangSight
# Server is "connected" but hasn't sent events in 120 seconds
$ langsight mcp-health
┌──────────────┬──────────┬──────────┬─────────────────────────────┐
│ Server       │ Status   │ Latency  │ Notes                       │
├──────────────┼──────────┼──────────┼─────────────────────────────┤
│ jira-mcp     │ STALE    │ —        │ No events in 120s (SSE)     │
│ github-mcp   │ UP       │ 89ms     │ 14 tools, schema unchanged  │
│ slack-mcp    │ DOWN     │ —        │ Connection refused           │
└──────────────┴──────────┴──────────┴─────────────────────────────┘`}</pre>

          <h3>StreamableHTTP: session management and standard HTTP failures</h3>
          <p>
            StreamableHTTP is the newest MCP transport, introduced in the MCP specification in late 2025. It combines standard HTTP request/response with optional server-initiated streaming via SSE upgrades.
          </p>
          <p>
            This transport inherits all the standard HTTP failure modes — 5xx errors, TLS certificate expiry, DNS resolution failures, connection pool exhaustion — plus MCP-specific issues around session management. StreamableHTTP servers maintain session state; if the server restarts, all active sessions are invalidated and clients must re-initialize. A rolling deployment of the MCP server can cause a wave of session re-initializations across all connected agents.
          </p>
          <p>
            Because StreamableHTTP is stateful, monitoring needs to track not just "is the server responding" but "is my session still valid." A 200 OK on the health endpoint does not mean existing sessions are functional.
          </p>

          <h2>What to monitor: the five signals</h2>
          <p>
            Effective MCP monitoring requires tracking five signals. Miss any one and you have a blind spot.
          </p>
          <ul>
            <li><strong>Latency distribution (p50, p95, p99)</strong> — Not just average latency, which hides tail latency spikes. A server with 50ms p50 but 8-second p99 will cause intermittent agent timeouts that are nearly impossible to debug without percentile tracking.</li>
            <li><strong>Error rate by category</strong> — Distinguish between transient errors (timeouts, connection resets) and permanent errors (tool not found, invalid arguments). A 2% timeout rate might be acceptable. A 0.1% "tool not found" rate means the server's schema has drifted.</li>
            <li><strong>Uptime and availability</strong> — Track availability over rolling windows: 1 hour, 24 hours, 7 days. An MCP server that goes down for 30 seconds every hour has 99.2% uptime but causes agent failures 24 times a day.</li>
            <li><strong>Schema consistency</strong> — Monitor tool count and tool schemas over time. If a server previously exposed 14 tools and now exposes 12, something changed. If a tool's input schema changed, agents tested against the old schema may start producing errors or incorrect results.</li>
            <li><strong>Tool call success rate</strong> — The most important signal: what percentage of actual tool invocations complete successfully? This is different from server uptime — the server can be "up" while specific tools fail due to backend issues (database connection pool exhausted, third-party API rate limited).</li>
          </ul>

          <h2>Proactive vs passive monitoring</h2>
          <p>
            Most agent observability platforms do passive monitoring: they record tool calls that agents make during real interactions and report on them after the fact. This is useful for understanding agent behavior, but it is useless for detecting failures before users are affected.
          </p>
          <p>
            <strong>Passive monitoring</strong> records traces of real agent sessions. You see that at 2:14 AM, the agent called <code>send_message</code> on <code>slack-mcp</code> and got a timeout. You discover this when you review traces the next morning — or when a user complains.
          </p>
          <p>
            <strong>Proactive monitoring</strong> sends synthetic health probes to every MCP server on a schedule, regardless of whether any agent is currently using it. Every 30 seconds, a probe calls <code>tools/list</code> on each server, measures latency, verifies the response schema, and compares tool definitions against the last known snapshot. If a server goes down at 12:14 AM, you get an alert at 12:14 AM — not when the first agent tries to use it 90 minutes later.
          </p>
          <p>
            LangSight does both. Proactive health probes run continuously and catch infrastructure-level failures. Passive trace collection captures real tool call patterns and identifies issues that only appear under real workloads (specific tool arguments that trigger slow queries, for example).
          </p>
          <pre>{`# Proactive: synthetic health probes every 30 seconds
$ langsight monitor --interval 30

# Passive: collect traces from OTEL-instrumented agents
# (configure OTEL collector to forward to LangSight)
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317`}</pre>

          <h2>Setting up MCP health monitoring with LangSight</h2>
          <p>
            LangSight can be monitoring your entire MCP fleet in under two minutes. Here is the setup flow.
          </p>

          <h3>Step 1: Install and auto-discover</h3>
          <pre>{`$ pip install langsight
$ langsight init

Discovering MCP servers...
  Found Claude Desktop config: 7 servers
  Found Cursor config: 3 servers
  Found VS Code config: 2 servers
  Deduplicated: 9 unique servers

Written to .langsight.yaml
  9 servers configured
  Default health check interval: 30s
  Default alert channel: stdout`}</pre>
          <p>
            <code>langsight init</code> reads your Claude Desktop, Cursor, and VS Code MCP configurations automatically. It deduplicates servers that appear in multiple configs (same command or same URL) and writes a <code>.langsight.yaml</code> with all discovered servers.
          </p>

          <h3>Step 2: First health check</h3>
          <pre>{`$ langsight mcp-health

MCP Server Health
┌──────────────────┬──────────┬──────────┬────────┬─────────────────────────────┐
│ Server           │ Status   │ Latency  │ Tools  │ Notes                       │
├──────────────────┼──────────┼──────────┼────────┼─────────────────────────────┤
│ postgres-mcp     │ UP       │ 42ms     │ 5      │ Schema unchanged            │
│ slack-mcp        │ UP       │ 156ms    │ 8      │ Schema unchanged            │
│ github-mcp       │ UP       │ 89ms     │ 14     │ Schema unchanged            │
│ jira-mcp         │ UP       │ 203ms    │ 11     │ Schema unchanged            │
│ s3-mcp           │ UP       │ 67ms     │ 4      │ Schema unchanged            │
│ filesystem-mcp   │ UP       │ 12ms     │ 6      │ Schema unchanged            │
│ redis-mcp        │ DOWN     │ —        │ —      │ Connection refused          │
│ elasticsearch-mcp│ DEGRADED │ 4,821ms  │ 7      │ Latency > 3000ms threshold  │
│ notion-mcp       │ UP       │ 312ms    │ 9      │ Schema unchanged            │
└──────────────────┴──────────┴──────────┴────────┴─────────────────────────────┘

2 issues detected:
  CRITICAL  redis-mcp           DOWN — Connection refused (port 6379)
  WARNING   elasticsearch-mcp   DEGRADED — p99 latency 4,821ms (threshold: 3,000ms)`}</pre>
          <p>
            One command, full fleet status. Each server gets a synthetic <code>tools/list</code> call that verifies the server is reachable, responding, and returning a valid tool schema. The latency column shows the round-trip time for that probe.
          </p>

          <h3>Step 3: Continuous monitoring</h3>
          <pre>{`$ langsight monitor --interval 30 --daemon

LangSight monitor started
  Checking 9 servers every 30 seconds
  Alert channels: slack (#mcp-alerts), stdout
  Schema snapshots: enabled
  PID file: /var/run/langsight-monitor.pid

Press Ctrl+C to stop (or run as systemd service)`}</pre>
          <p>
            The <code>monitor</code> command runs health probes on a loop. Every 30 seconds (configurable), each server gets a health check. State transitions (UP to DOWN, UP to DEGRADED, DOWN to UP) trigger alerts. The monitor tracks schema snapshots so it can detect when a server's tool definitions change between checks.
          </p>
          <p>
            For production deployments, run the monitor as a systemd service or Docker container. It uses minimal resources — a single Python process with async I/O, typically under 50MB of memory even with 100+ servers.
          </p>

          <h3>Step 4: Configuration</h3>
          <pre>{`# .langsight.yaml
monitoring:
  interval_seconds: 30
  timeout_seconds: 5
  consecutive_failures_before_down: 3

servers:
  - name: postgres-mcp
    transport: stdio
    command: "python /opt/mcp/postgres/server.py"
    tags: ["database", "critical"]
    thresholds:
      latency_warning_ms: 500
      latency_critical_ms: 2000

  - name: slack-mcp
    transport: sse
    url: "https://mcp.internal.company.com/slack"
    tags: ["communication", "critical"]

  - name: analytics-mcp
    transport: streamable_http
    url: "https://mcp.internal.company.com/analytics"
    tags: ["analytics", "non-critical"]
    thresholds:
      latency_warning_ms: 2000
      latency_critical_ms: 10000

alerts:
  channels:
    - type: slack
      webhook_url: "${`LANGSIGHT_SLACK_WEBHOOK`}"
      channel: "#mcp-alerts"
    - type: webhook
      url: "https://pagerduty.com/integrate/..."
      events: ["down", "schema_drift"]`}</pre>

          <h2>Alerting on degradation</h2>
          <p>
            Health checks without alerts are just dashboards you forget to look at. LangSight supports three alert channels out of the box: Slack (with Block Kit formatting), generic webhooks (PagerDuty, OpsGenie, custom), and stdout (for CI/CD and local use).
          </p>
          <p>
            Alert rules are state-machine based, not threshold-based. A single slow response does not trigger an alert. Three consecutive failures transitions the server from UP to DOWN, which fires the alert. When the server recovers, a recovery alert fires. This prevents alert fatigue from transient network blips.
          </p>
          <p>
            Alert types include:
          </p>
          <ul>
            <li><strong>Server DOWN</strong> — Server failed consecutive health checks. Includes last known status, duration of outage, and which agents are affected.</li>
            <li><strong>Latency spike</strong> — p95 latency exceeded the configured threshold for the past N checks. Includes latency trend and historical comparison.</li>
            <li><strong>Schema drift</strong> — A tool was added, removed, or had its schema changed. Includes a diff of the old and new schemas so you can assess impact before updating agents.</li>
            <li><strong>Recovery</strong> — Server transitioned from DOWN or DEGRADED back to UP. Includes total downtime duration.</li>
          </ul>
          <pre>{`# Example Slack alert for a schema drift detection
{
  "server": "github-mcp",
  "event": "schema_drift",
  "severity": "warning",
  "message": "Tool schema changed on github-mcp",
  "details": {
    "tools_added": [],
    "tools_removed": ["delete_branch"],
    "tools_modified": [{
      "name": "create_pull_request",
      "changes": "Added required field: draft (boolean)"
    }],
    "previous_snapshot": "2026-03-30T14:22:00Z",
    "current_snapshot": "2026-04-02T08:15:00Z"
  }
}`}</pre>

          <h2>The MCP server scorecard</h2>
          <p>
            Beyond point-in-time health checks, LangSight generates a scorecard for each MCP server. The scorecard grades servers A through F across four dimensions:
          </p>
          <ul>
            <li><strong>Availability</strong> — Uptime percentage over the past 7 days. A: 99.9%+, B: 99.5%+, C: 99%+, D: 95%+, F: below 95%.</li>
            <li><strong>Performance</strong> — p95 latency relative to configured thresholds. A: consistently under warning threshold, F: regularly exceeding critical threshold.</li>
            <li><strong>Security</strong> — Authentication configured, TLS enabled, no known CVEs, OWASP MCP Top 10 compliance. Each missing item drops the grade.</li>
            <li><strong>Reliability</strong> — Schema stability, error rate, mean time between failures. Servers that change schemas frequently or have high error rates get lower grades.</li>
          </ul>
          <pre>{`$ langsight mcp-health --scorecard

MCP Server Scorecard (7-day rolling)
┌──────────────────┬───────┬───────┬───────┬───────┬─────────┐
│ Server           │ Avail │ Perf  │ Sec   │ Rel   │ Overall │
├──────────────────┼───────┼───────┼───────┼───────┼─────────┤
│ postgres-mcp     │ A     │ A     │ B     │ A     │ A       │
│ github-mcp       │ A     │ B     │ A     │ A     │ A       │
│ slack-mcp        │ B     │ C     │ B     │ B     │ B       │
│ jira-mcp         │ A     │ B     │ C     │ A     │ B       │
│ elasticsearch-mcp│ C     │ D     │ B     │ C     │ C       │
│ redis-mcp        │ F     │ —     │ D     │ F     │ F       │
└──────────────────┴───────┴───────┴───────┴───────┴─────────┘`}</pre>

          <h2>Monitoring at scale: 35+ servers</h2>
          <p>
            Small teams run 3 to 5 MCP servers. Enterprise teams deploying agents across departments often run 35 or more. At that scale, a CLI table with 35 rows is not sufficient — you need filtering, grouping, and historical trends.
          </p>
          <p>
            LangSight handles this in two ways. For CLI users, the <code>--filter</code> and <code>--tag</code> flags let you focus on what matters:
          </p>
          <pre>{`# Show only servers that are not healthy
$ langsight mcp-health --filter status!=up

# Show only critical-tagged servers
$ langsight mcp-health --tag critical

# Show servers grouped by team
$ langsight mcp-health --group-by tag:team

# JSON output for custom dashboards or scripts
$ langsight mcp-health --json | jq '.servers[] | select(.status == "down")'`}</pre>
          <p>
            For teams that need historical trends, the LangSight dashboard (self-hosted, ships as a Docker container) shows latency heatmaps, uptime timelines, schema change history, and alert logs. Filter by project, tag, or status. The dashboard reads from the same data store the CLI writes to — no separate configuration required.
          </p>

          <h2>Integrating with existing observability</h2>
          <p>
            LangSight does not replace your existing monitoring stack. It integrates with it. Health check results are exported as Prometheus metrics, so you can add MCP server panels to your existing Grafana dashboards:
          </p>
          <pre>{`# Prometheus metrics exposed on :9090/metrics
langsight_mcp_health_status{server="postgres-mcp"} 1      # 1=up, 0=down
langsight_mcp_latency_p95{server="postgres-mcp"} 42.3
langsight_mcp_tool_count{server="postgres-mcp"} 5
langsight_mcp_schema_changes_total{server="postgres-mcp"} 0
langsight_mcp_errors_total{server="postgres-mcp",type="timeout"} 2`}</pre>
          <p>
            Alerts can forward to any webhook — PagerDuty, OpsGenie, custom Slack bots, or a Lambda function that auto-restarts crashed stdio processes. The alert payload is structured JSON, so integration with your incident management workflow is straightforward.
          </p>

          <h2>Key takeaways</h2>
          <ul>
            <li><strong>MCP servers are the hidden dependency.</strong> Your agents are only as reliable as the tools they call. If you monitor the LLM but not the MCP servers, you are monitoring half the system.</li>
            <li><strong>Each transport fails differently.</strong> stdio processes crash silently. SSE connections stall. StreamableHTTP sessions expire. Your monitoring must understand all three.</li>
            <li><strong>Proactive beats passive.</strong> Recording traces of real tool calls tells you what happened. Proactive health probes tell you what is about to happen. You need both, but proactive monitoring is what prevents 2 AM pages.</li>
            <li><strong>Schema drift is a production risk.</strong> When an MCP server changes its tool definitions, agents tested against the old schema will silently break. Monitor tool schemas, not just availability.</li>
            <li><strong>One command to start.</strong> <code>pip install langsight && langsight init && langsight monitor</code> gets you from zero to full fleet monitoring in under two minutes. No Docker required for local mode.</li>
          </ul>

          <div className="mt-12 p-6 border border-[var(--indigo)]/30 rounded-xl bg-[var(--indigo)]/5">
            <p className="font-semibold text-[var(--indigo)] mb-2">Monitor your MCP fleet</p>
            <p className="text-[var(--muted)] text-sm mb-4">
              LangSight adds health monitoring to your entire MCP server fleet in one command. Proactive health probes, latency tracking, schema drift detection, and alerting. Self-host free, Apache 2.0.
            </p>
            <a
              href="/"
              className="inline-block text-sm font-medium px-4 py-2 rounded-lg bg-[var(--indigo)] text-white hover:opacity-90 transition-opacity"
            >
              Get started →
            </a>
          </div>
        </div>
      </article>

      <style>{`
        .prose-custom h2 {
          font-size: 1.5rem;
          font-weight: 700;
          margin-top: 2.5rem;
          margin-bottom: 1rem;
          color: var(--fg);
        }
        .prose-custom h3 {
          font-size: 1.15rem;
          font-weight: 600;
          margin-top: 1.75rem;
          margin-bottom: 0.75rem;
          color: var(--fg);
        }
        .prose-custom p {
          margin-bottom: 1.25rem;
          line-height: 1.75;
          color: var(--muted);
        }
        .prose-custom ul {
          margin-bottom: 1.25rem;
          padding-left: 1.5rem;
          list-style: disc;
        }
        .prose-custom ol {
          margin-bottom: 1.25rem;
        }
        .prose-custom li {
          margin-bottom: 0.5rem;
          line-height: 1.75;
          color: var(--muted);
        }
        .prose-custom pre {
          background: var(--card);
          border: 1px solid var(--border);
          border-radius: 0.75rem;
          padding: 1.25rem;
          overflow-x: auto;
          font-size: 0.85rem;
          line-height: 1.6;
          margin-bottom: 1.25rem;
          color: var(--fg);
          font-family: var(--font-geist-mono), monospace;
        }
        .prose-custom code {
          background: var(--card);
          border: 1px solid var(--border);
          border-radius: 0.25rem;
          padding: 0.1rem 0.35rem;
          font-size: 0.85em;
          font-family: var(--font-geist-mono), monospace;
          color: var(--indigo);
        }
        .prose-custom pre code {
          background: none;
          border: none;
          padding: 0;
          color: var(--fg);
        }
        .prose-custom strong {
          font-weight: 600;
          color: var(--fg);
        }
      `}</style>
    </main>
  );
}
