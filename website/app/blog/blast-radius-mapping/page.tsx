"use client";

export default function BlastRadiusMappingPost() {
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
            {["Blast Radius", "Dependencies", "Reliability"].map((tag) => (
              <span key={tag} className="text-xs px-2 py-0.5 rounded-full bg-[var(--indigo)]/10 text-[var(--indigo)] font-medium">
                {tag}
              </span>
            ))}
          </div>
          <h1 className="text-4xl font-bold leading-tight mb-4">
            Blast Radius Mapping: Understanding AI Agent Dependencies
          </h1>
          <p className="text-xl text-[var(--muted)] leading-relaxed mb-6">
            Your slack-mcp goes down. How many agents are affected? Which sessions will fail? How many users are impacted? Without dependency mapping, the answer to all three is "we do not know." Blast radius mapping gives you the dependency graph to answer these questions before incidents happen.
          </p>
          <div className="flex items-center gap-4 text-sm text-[var(--muted)] border-t border-[var(--border)] pt-6">
            <span>April 2, 2026</span>
            <span>·</span>
            <span>8 min read</span>
            <span>·</span>
            <span>LangSight Engineering</span>
          </div>
        </div>

        {/* Hero image */}
        <div className="mb-10 rounded-xl overflow-hidden border border-[var(--border)]">
          <img src="/blog/blast-radius-mapping.svg" alt="Blast Radius Mapping: Understanding AI Agent Dependencies" className="w-full" />
        </div>

        {/* Content */}
        <div className="prose-custom">

          <h2>What is blast radius?</h2>
          <p>
            In cloud infrastructure, "blast radius" describes the scope of impact when a component fails. AWS's Fault Injection Simulator uses the term to describe how a failure in one service propagates to dependent services. A database failure with a blast radius of 3 services is contained. A DNS failure with a blast radius of every service in the VPC is catastrophic.
          </p>
          <p>
            In AI agent systems, blast radius answers: "If this MCP server goes down, what breaks?" The answer is never just "the tool that called it." The answer includes every agent that uses that tool, every session running through those agents, every multi-agent handoff chain that touches those agents, and every end user waiting for a response.
          </p>

          <h2>Hidden dependencies in multi-agent systems</h2>
          <p>
            Simple agent deployments have straightforward dependencies: Agent A uses tools X, Y, Z on MCP server M. If M goes down, Agent A's sessions fail. The blast radius is one agent.
          </p>
          <p>
            Multi-agent systems have hidden dependencies that are not visible from any single agent's configuration:
          </p>
          <pre>{`# Visible dependency: support-agent uses postgres-mcp
support-agent → postgres-mcp/query
support-agent → postgres-mcp/get_customer
support-agent → slack-mcp/send_message

# Hidden dependency: triage-agent hands off to support-agent
triage-agent → [handoff] → support-agent

# Deeper hidden dependency: escalation-agent depends on triage
escalation-agent → [handoff] → triage-agent → [handoff] → support-agent

# If postgres-mcp goes down:
# - support-agent fails directly (uses postgres-mcp)
# - triage-agent fails indirectly (hands off to support-agent)
# - escalation-agent fails transitively (depends on triage-agent)
# Blast radius: 3 agents, not 1`}</pre>
          <p>
            The transitive dependency is the dangerous one. The escalation-agent does not directly call postgres-mcp. Its configuration does not mention postgres-mcp. But when postgres-mcp goes down, escalation-agent's sessions fail because the handoff chain is broken.
          </p>
          <p>
            Without blast radius mapping, the engineer investigating the escalation-agent failure has no idea that the root cause is a database MCP server three layers away in the dependency chain.
          </p>

          <h2>Building the dependency graph</h2>
          <p>
            LangSight builds the agent-to-tool dependency graph automatically by observing real agent sessions. Every time an agent calls a tool, LangSight records the (agent, tool, server) tuple. Every time an agent hands off to another agent, LangSight records the (parent_agent, child_agent) relationship.
          </p>
          <p>
            Over time, the dependency graph emerges from real usage patterns — not from static configuration that may be incomplete or outdated.
          </p>
          <pre>{`$ langsight investigate --topology

Agent Dependency Graph
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  escalation-agent
    └─▶ triage-agent (handoff)
         └─▶ support-agent (handoff)
              ├── postgres-mcp  [query, get_customer, update_ticket]
              ├── slack-mcp     [send_message, get_channel]
              └── jira-mcp      [create_issue, update_issue]

  billing-agent
    ├── postgres-mcp  [query, get_invoice]
    └── stripe-mcp    [get_payment, create_refund]

  onboarding-agent
    ├── postgres-mcp  [get_customer, create_account]
    ├── email-mcp     [send_welcome, send_verification]
    └── slack-mcp     [send_message]

Shared dependencies:
  postgres-mcp  → 3 agents (support, billing, onboarding)
  slack-mcp     → 2 agents (support, onboarding)
  jira-mcp      → 1 agent  (support)`}</pre>

          <h2>The blast radius panel</h2>
          <p>
            When a tool or MCP server's health status changes (UP to DOWN, UP to DEGRADED), LangSight calculates the blast radius in real time and includes it in the alert:
          </p>
          <pre>{`# Alert: postgres-mcp DOWN
# Blast radius calculation:

Direct dependents:
  support-agent      — uses 3 tools on postgres-mcp
  billing-agent      — uses 2 tools on postgres-mcp
  onboarding-agent   — uses 2 tools on postgres-mcp

Transitive dependents (via handoff chains):
  triage-agent       — hands off to support-agent
  escalation-agent   — hands off to triage-agent

Impact estimate (based on last 24h traffic):
  Sessions affected:  ~180/hour
  Users impacted:     ~120/hour
  Handoff chains broken: 2
    escalation-agent → triage-agent → support-agent
    triage-agent → support-agent

Circuit breakers opened:
  support-agent/postgres-mcp/query       — OPEN since 03:14 UTC
  billing-agent/postgres-mcp/get_invoice — OPEN since 03:14 UTC
  onboarding-agent/postgres-mcp/get_customer — OPEN since 03:14 UTC`}</pre>
          <p>
            The alert does not just say "postgres-mcp is down." It says "postgres-mcp is down, 5 agents are affected, 180 sessions per hour will fail, and 2 handoff chains are broken." This context enables faster incident response because the on-call engineer immediately understands the scope and can prioritize accordingly.
          </p>

          <h2>Using blast radius for capacity planning</h2>
          <p>
            Beyond incident response, the dependency graph is valuable for capacity planning and architecture decisions.
          </p>
          <p>
            <strong>Identify single points of failure.</strong> If postgres-mcp is used by 5 out of 7 agents, it is a single point of failure. Consider adding a read replica MCP server, implementing connection pooling, or adding caching to reduce the dependency.
          </p>
          <p>
            <strong>Plan maintenance windows.</strong> Before taking an MCP server offline for maintenance, check its blast radius. An MCP server used by one non-critical agent can be taken down during business hours. An MCP server used by five agents including the customer-facing support agent should be maintained during off-peak hours with a failover in place.
          </p>
          <p>
            <strong>Right-size circuit breaker thresholds.</strong> An MCP server with a large blast radius (5+ agents) should have aggressive circuit breaker settings (fail fast, shorter cooldowns). An MCP server used by one non-critical agent can have more lenient settings.
          </p>

          <h2>Impact-aware alerting</h2>
          <p>
            Traditional alerting treats all failures equally: any server DOWN triggers the same alert. Impact-aware alerting uses the blast radius to set alert severity dynamically.
          </p>
          <pre>{`# .langsight.yaml — impact-aware alert configuration
alerts:
  impact_aware: true
  rules:
    - condition: "server.status == DOWN"
      severity_override:
        # Blast radius >= 5 agents → page immediately
        blast_radius_agents >= 5: critical
        # Blast radius >= 3 agents → urgent alert
        blast_radius_agents >= 3: high
        # Blast radius == 1 agent → standard alert
        blast_radius_agents == 1: medium`}</pre>
          <p>
            When postgres-mcp (blast radius: 5 agents) goes down, it pages the on-call engineer immediately. When analytics-mcp (blast radius: 1 non-critical agent) goes down, it sends a standard Slack notification. The alert severity matches the actual impact, reducing alert fatigue while ensuring critical failures get immediate attention.
          </p>

          <h2>Lineage tracking for debugging</h2>
          <p>
            During incident investigation, the dependency graph helps trace failures back to their root cause. When a user reports that the escalation-agent is not working:
          </p>
          <ul>
            <li>Check escalation-agent's health → healthy</li>
            <li>Check escalation-agent's dependencies → depends on triage-agent (handoff)</li>
            <li>Check triage-agent's health → healthy, but sessions failing</li>
            <li>Check triage-agent's dependencies → depends on support-agent (handoff)</li>
            <li>Check support-agent's health → sessions failing</li>
            <li>Check support-agent's tool dependencies → postgres-mcp is DOWN</li>
          </ul>
          <p>
            The dependency graph turns a "the agent does not work" report into a "postgres-mcp is the root cause" diagnosis in seconds, following the dependency chain automatically instead of requiring manual investigation at each layer.
          </p>

          <h2>Key takeaways</h2>
          <ul>
            <li><strong>Multi-agent systems have hidden transitive dependencies.</strong> An agent three handoff layers away from a failed MCP server still fails. Without blast radius mapping, the root cause is invisible.</li>
            <li><strong>Build the graph from real usage, not configuration.</strong> LangSight observes actual agent sessions to build the dependency graph. Static configuration is always incomplete.</li>
            <li><strong>Include blast radius in every DOWN alert.</strong> "postgres-mcp is down, 5 agents affected, 180 sessions/hour impacted" enables faster triage than "postgres-mcp is down."</li>
            <li><strong>Use blast radius for capacity planning.</strong> Identify single points of failure, plan maintenance windows, and right-size circuit breaker thresholds based on dependency data.</li>
            <li><strong>Impact-aware alerting reduces noise.</strong> Page for high-blast-radius failures, notify for low-blast-radius failures. Match alert severity to actual impact.</li>
          </ul>

          <div className="mt-12 p-6 border border-[var(--indigo)]/30 rounded-xl bg-[var(--indigo)]/5">
            <p className="font-semibold text-[var(--indigo)] mb-2">Map your agent dependencies</p>
            <p className="text-[var(--muted)] text-sm mb-4">
              LangSight builds the agent-to-tool dependency graph automatically. See blast radius on every alert, plan maintenance with confidence, and trace failures to their root cause. Self-host free, Apache 2.0.
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
