"use client";

export default function CircuitBreakersAiAgentsPost() {
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
            {["Circuit Breaker", "Reliability", "Fault Tolerance"].map((tag) => (
              <span key={tag} className="text-xs px-2 py-0.5 rounded-full bg-[var(--indigo)]/10 text-[var(--indigo)] font-medium">
                {tag}
              </span>
            ))}
          </div>
          <h1 className="text-4xl font-bold leading-tight mb-4">
            Circuit Breakers for AI Agents: Preventing Cascading Failures
          </h1>
          <p className="text-xl text-[var(--muted)] leading-relaxed mb-6">
            Your postgres-mcp goes down at 3 AM. Three agents depend on it. Without circuit breakers, every session that touches those agents burns tokens trying to call a tool that will never respond, times out after 30 seconds, and returns an unhelpful error. With circuit breakers, the agent knows the tool is down before it tries, fails fast, and can route to a fallback.
          </p>
          <div className="flex items-center gap-4 text-sm text-[var(--muted)] border-t border-[var(--border)] pt-6">
            <span>April 2, 2026</span>
            <span>·</span>
            <span>9 min read</span>
            <span>·</span>
            <span>LangSight Engineering</span>
          </div>
        </div>

        {/* Hero image */}
        <div className="mb-10 rounded-xl overflow-hidden border border-[var(--border)] relative">
          <img src="/blog/circuit-breakers-ai-agents.png" alt="Circuit Breakers for AI Agents: Preventing Cascading Failures" className="w-full" />
          <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/30">
            <span className="text-2xl sm:text-3xl font-bold text-white tracking-wide drop-shadow-lg">Circuit Breakers</span>
            <span className="text-sm text-white/80 mt-1.5 drop-shadow-md">Prevent cascading failures across agents</span>
          </div>
        </div>

        {/* Content */}
        <div className="prose-custom">

          <h2>The cascading failure problem</h2>
          <p>
            In a traditional microservices architecture, a circuit breaker prevents a failed downstream service from taking down the entire system. When Service A calls Service B and B is down, the circuit breaker in A detects the failure pattern and stops sending requests to B — preventing thread pool exhaustion, timeout cascades, and resource waste.
          </p>
          <p>
            AI agents have the same problem, but worse. When an agent calls a tool on a downed MCP server, it does not just waste a network request. It wastes an entire LLM reasoning step. The agent decides to call the tool (LLM cost), constructs the arguments (LLM cost), waits for the timeout (wall clock time), processes the error response (LLM cost), decides to retry (LLM cost), and repeats. A single failed tool call can cost 3-4x what a successful call costs because the agent's retry and error-handling reasoning is expensive.
          </p>
          <p>
            In multi-agent systems, the cascade is even worse. Agent A calls tool X (down). Agent A fails. Agent B, which depends on Agent A's output via a handoff, also fails. Agent C, which depends on Agent B, also fails. A single MCP server outage propagates through the agent graph, failing every session that touches any agent in the dependency chain.
          </p>

          <h2>The circuit breaker pattern</h2>
          <p>
            The circuit breaker pattern, borrowed from electrical engineering and popularized in software by Netflix's Hystrix library, has three states:
          </p>

          <h3>Closed (normal operation)</h3>
          <p>
            The circuit is closed — tool calls pass through normally. The circuit breaker tracks the success and failure rates. As long as the failure rate stays below the threshold, the circuit stays closed.
          </p>

          <h3>Open (failing, stop calling)</h3>
          <p>
            When the failure count exceeds the threshold (for example, 5 consecutive failures), the circuit opens. All subsequent tool calls are immediately rejected without contacting the MCP server. The agent receives an immediate error: "Circuit open: postgres-mcp is currently unavailable."
          </p>
          <p>
            This is the key insight: instead of waiting 30 seconds for a timeout on every call, the agent gets an immediate failure. The LLM can then decide what to do — use a cached result, skip that step, or inform the user — without burning tokens on retry attempts that will never succeed.
          </p>

          <h3>Half-open (testing recovery)</h3>
          <p>
            After a cooldown period (for example, 60 seconds), the circuit transitions to half-open. One test call is allowed through to the MCP server. If it succeeds, the circuit closes (normal operation resumes). If it fails, the circuit reopens for another cooldown period.
          </p>
          <pre>{`# Circuit breaker state machine
#
#   ┌──────────┐  N failures   ┌──────────┐
#   │  CLOSED  │──────────────▶│   OPEN   │
#   │ (normal) │               │ (reject) │
#   └──────────┘               └──────────┘
#        ▲                          │
#        │  success                 │ cooldown expires
#        │                          ▼
#        │                    ┌───────────┐
#        └────────────────────│ HALF-OPEN │
#                             │  (probe)  │
#                   failure → │   reopen  │
#                             └───────────┘`}</pre>

          <h2>Why agents need circuit breakers specifically</h2>
          <p>
            Traditional circuit breakers protect services from wasting resources on failed calls. Agent circuit breakers protect against two additional costs:
          </p>
          <ul>
            <li><strong>Token waste:</strong> Every failed tool call triggers LLM reasoning about the failure, retry decisions, and error handling. With gpt-4o or Claude 3.5 Sonnet, this reasoning costs real money. A circuit breaker prevents the agent from ever reaching the "should I retry?" decision for a known-down tool.</li>
            <li><strong>Session quality:</strong> An agent that spends 3 of its 5 reasoning steps dealing with a failed tool produces a worse final answer than an agent that immediately knows the tool is down and adjusts its strategy. Fast failure enables graceful degradation.</li>
          </ul>

          <h2>Configuring circuit breakers in LangSight</h2>
          <pre>{`from langsight.sdk import LangSightClient

client = LangSightClient(
    url="http://localhost:8000",
    api_key="ls_...",

    # Circuit breaker configuration
    circuit_breaker=True,
    failure_threshold=5,     # 5 consecutive failures → open circuit
    cooldown_seconds=60,     # wait 60s before probing recovery
    half_open_max_calls=1,   # allow 1 test call in half-open state
)

traced = client.wrap(mcp_session, agent_name="support-agent")

# When a tool's circuit is open, the call returns immediately:
# ToolCircuitOpenError("postgres-mcp/query: circuit open since 03:14:22 UTC")
# The agent can handle this gracefully instead of waiting for a timeout`}</pre>
          <p>
            Configuration can also be set per tool or per MCP server:
          </p>
          <pre>{`# .langsight.yaml — per-server circuit breaker config
servers:
  - name: postgres-mcp
    transport: stdio
    command: "python server.py"
    circuit_breaker:
      enabled: true
      failure_threshold: 3      # critical tool — trip faster
      cooldown_seconds: 30      # recover faster

  - name: analytics-mcp
    transport: sse
    url: "https://mcp.internal/analytics"
    circuit_breaker:
      enabled: true
      failure_threshold: 10     # non-critical — more tolerance
      cooldown_seconds: 120     # slower recovery probe`}</pre>

          <h2>Blast radius: which agents are affected?</h2>
          <p>
            When a circuit opens, the critical question is: which agents are affected? LangSight tracks the agent-to-tool dependency graph, so when a circuit opens, the alert includes:
          </p>
          <ul>
            <li>Which agents use the affected tool</li>
            <li>How many active sessions are currently running through those agents</li>
            <li>Which handoff chains are broken (multi-agent dependencies)</li>
            <li>Estimated session failure rate during the outage</li>
          </ul>
          <pre>{`# Circuit open alert (Slack)
⚠️ Circuit OPEN: postgres-mcp/query
  Since: 2026-04-02 03:14:22 UTC
  Cause: 5 consecutive timeouts (avg 31.2s)

  Affected agents:
    support-agent      — 12 active sessions
    billing-agent      — 3 active sessions
    onboarding-agent   — 7 active sessions

  Handoff chains broken:
    triage-agent → support-agent → escalation-agent

  Estimated impact: ~120 sessions/hour
  Recovery probe: next attempt in 30s`}</pre>

          <h2>Combining circuit breakers with health monitoring</h2>
          <p>
            Circuit breakers react to failures detected during real agent sessions. Health monitoring proactively detects failures before any agent is affected. The two systems work together:
          </p>
          <ul>
            <li><strong>Health monitoring detects the outage first.</strong> A proactive health probe at 03:14:00 detects that postgres-mcp is not responding. An alert fires.</li>
            <li><strong>Circuit breaker prevents waste.</strong> At 03:14:22, the first agent session tries to call postgres-mcp. The health monitor has already flagged it as DOWN, so the circuit pre-opens. The agent gets an immediate failure instead of a 30-second timeout.</li>
            <li><strong>Health monitoring detects recovery.</strong> At 03:18:00, the health probe succeeds. The circuit transitions to half-open. The next agent session's tool call is allowed through. It succeeds. The circuit closes. A recovery alert fires.</li>
          </ul>
          <p>
            LangSight integrates health monitoring and circuit breakers into a single system. The health checker's DOWN detection automatically opens circuits. The health checker's UP detection automatically transitions circuits to half-open. This eliminates the recovery delay that would occur if the circuit breaker had to wait for a real agent session to probe recovery.
          </p>

          <h2>Graceful degradation patterns</h2>
          <p>
            A circuit breaker that rejects a tool call is only useful if the agent can handle the rejection gracefully. There are several patterns:
          </p>

          <h3>Inform and skip</h3>
          <p>
            The agent tells the user that a specific capability is temporarily unavailable. "I cannot access the database right now, but I can answer from the information I already have."
          </p>

          <h3>Fallback tool</h3>
          <p>
            Configure a fallback MCP server for critical tools. If postgres-mcp is down, route queries to a read replica MCP server. LangSight supports fallback routing in the SDK configuration.
          </p>

          <h3>Cached response</h3>
          <p>
            For tools that return relatively stable data (customer records, configuration values), cache the last successful response and return it when the circuit is open. The cached data may be stale, but stale data is often better than no data.
          </p>

          <h2>Key takeaways</h2>
          <ul>
            <li><strong>Agents waste tokens on failed tools.</strong> Without circuit breakers, every failed tool call triggers expensive LLM reasoning about retries and error handling. Circuit breakers prevent the agent from ever reaching that point.</li>
            <li><strong>Three states: closed, open, half-open.</strong> Closed is normal. Open rejects immediately. Half-open probes for recovery. This is the same pattern used in microservices, adapted for the AI agent context.</li>
            <li><strong>Combine with health monitoring.</strong> Proactive health probes can pre-open circuits before any agent session is affected. Health-detected recovery can transition circuits to half-open faster than passive detection.</li>
            <li><strong>Blast radius awareness is critical.</strong> When a circuit opens, know which agents, sessions, and handoff chains are affected. This context in the alert enables faster incident response.</li>
            <li><strong>Design for graceful degradation.</strong> A circuit breaker that rejects calls is only half the solution. The agent must handle the rejection — inform the user, use a fallback, or return cached data.</li>
          </ul>

          <h2>Related articles</h2>
          <ul>
            <li><a href="/blog/blast-radius-mapping/" style={{ color: "var(--indigo)", textDecoration: "underline" }}>Blast Radius Mapping</a> — When a circuit opens, know exactly which agents, sessions, and handoff chains are affected.</li>
            <li><a href="/blog/mcp-monitoring-production/" style={{ color: "var(--indigo)", textDecoration: "underline" }}>How to Monitor MCP Servers in Production</a> — Proactive health monitoring detects outages before circuit breakers need to trip.</li>
            <li><a href="/blog/ai-agent-loop-detection/" style={{ color: "var(--indigo)", textDecoration: "underline" }}>AI Agent Loop Detection</a> — Loops and cascading failures are related failure modes. Use both circuit breakers and loop detection together.</li>
            <li><a href="/blog/slos-for-ai-agents/" style={{ color: "var(--indigo)", textDecoration: "underline" }}>Setting SLOs for AI Agents</a> — Circuit breakers improve your SLO metrics by preventing token waste on known-failed tools.</li>
          </ul>

          <div className="mt-12 p-6 border border-[var(--indigo)]/30 rounded-xl bg-[var(--indigo)]/5">
            <p className="font-semibold text-[var(--indigo)] mb-2">Add circuit breakers to your agents</p>
            <p className="text-[var(--muted)] text-sm mb-4">
              LangSight adds circuit breakers, health monitoring, and blast radius analysis to any agent system. Prevent cascading failures before they reach your users. Self-host free, Apache 2.0.
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
        .prose-custom a {
          color: var(--indigo);
          text-decoration: underline;
          text-underline-offset: 2px;
        }
        .prose-custom a:hover {
          opacity: 0.8;
        }
      `}</style>
    </main>
  );
}
