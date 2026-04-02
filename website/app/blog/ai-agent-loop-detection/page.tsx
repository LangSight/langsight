"use client";

export default function AgentLoopDetectionPost() {
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
            {["Loop Detection", "Agent Reliability", "Production"].map((tag) => (
              <span key={tag} className="text-xs px-2 py-0.5 rounded-full bg-[var(--indigo)]/10 text-[var(--indigo)] font-medium">
                {tag}
              </span>
            ))}
          </div>
          <h1 className="text-4xl font-bold leading-tight mb-4">
            How to Detect and Stop AI Agent Loops in Production
          </h1>
          <p className="text-xl text-[var(--muted)] leading-relaxed mb-6">
            AI agent loops are the most common production failure mode. The agent calls the same tool with the same arguments, over and over, burning tokens and producing nothing. Here's how to detect and stop them automatically.
          </p>
          <div className="flex items-center gap-4 text-sm text-[var(--muted)] border-t border-[var(--border)] pt-6">
            <span>March 22, 2026</span>
            <span>·</span>
            <span>8 min read</span>
            <span>·</span>
            <span>LangSight Engineering</span>
          </div>
        </div>

        {/* Hero image */}
        <div className="mb-10 rounded-xl overflow-hidden border border-[var(--border)] relative">
          <img src="/blog/ai-agent-loop-detection.png" alt="How to Detect and Stop AI Agent Loops in Production" className="w-full" />
          <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/30">
            <span className="text-2xl sm:text-3xl font-bold text-white tracking-wide drop-shadow-lg">Loop Detection</span>
            <span className="text-sm text-white/80 mt-1.5 drop-shadow-md">Stop infinite agent loops before they burn your budget</span>
          </div>
        </div>

        {/* Content */}
        <div className="prose-custom">

          <h2>The $200 loop you didn't see coming</h2>
          <p>
            A support agent at a fintech company was deployed to handle billing queries. It worked perfectly in staging. On day three of production, a single session ran for 47 minutes, called <code>crm-mcp/lookup_customer</code> 89 times with identical arguments, and cost $214 before someone manually killed it.
          </p>
          <p>
            The root cause: the CRM server returned a slightly malformed response. The agent decided it needed more data, called the same tool again, got the same malformed response, and repeated. No circuit breaker. No loop detection. No budget limit. The agent was doing exactly what it was programmed to do — retry until it got a good response.
          </p>
          <p>
            This is not an edge case. It is the most common failure mode in production AI agent systems.
          </p>

          <h2>What is an AI agent loop?</h2>
          <p>
            An agent loop occurs when an agent calls the same tool (or sequence of tools) repeatedly without making meaningful progress. There are three distinct patterns:
          </p>

          <h3>1. Direct repetition</h3>
          <p>
            The simplest form: the same tool called with identical arguments multiple times in a row.
          </p>
          <pre>{`# Direct repetition pattern
postgres-mcp/query("SELECT * FROM orders WHERE id = 1234")
postgres-mcp/query("SELECT * FROM orders WHERE id = 1234")
postgres-mcp/query("SELECT * FROM orders WHERE id = 1234")
# ... 44 more times`}</pre>
          <p>
            This happens when the tool returns an error or unexpected result and the LLM's retry logic doesn't distinguish between "transient failure, retry" and "structural failure, give up."
          </p>

          <h3>2. Ping-pong between tools</h3>
          <p>
            Two tools are called alternately without state change between calls. The agent calls tool A, gets a result, calls tool B, gets a result, then calls tool A again with the same arguments.
          </p>
          <pre>{`# Ping-pong pattern
crm-mcp/get_customer(id=456)          # returns customer
billing-mcp/get_invoices(customer=456) # returns invoices
crm-mcp/get_customer(id=456)          # same call again
billing-mcp/get_invoices(customer=456) # same call again`}</pre>

          <h3>3. Retry-without-progress</h3>
          <p>
            The tool call succeeds (no error) but the response doesn't satisfy the agent's internal goal. The agent keeps calling with minor variations in arguments, never converging on a solution.
          </p>

          <h2>Why standard retry logic makes this worse</h2>
          <p>
            Most agent frameworks include retry logic for transient failures — network timeouts, rate limits, temporary server errors. This is correct behavior. But the same retry logic, applied naively, turns a recoverable tool failure into an infinite loop.
          </p>
          <p>
            The problem is that retry logic operates at the <em>tool call level</em>: "this call failed, retry it." Loop detection needs to operate at the <em>session level</em>: "this tool has been called N times with the same arguments, the session is stuck."
          </p>
          <p>
            These are different problems requiring different solutions.
          </p>

          <h2>How to detect agent loops: three approaches</h2>

          <h3>Approach 1: Argument hash comparison</h3>
          <p>
            The most reliable detection method. For each tool call, compute a normalized hash of the tool name and input arguments. If the same hash appears N times within a session window, the agent is looping.
          </p>
          <pre>{`import hashlib
import json
from collections import Counter

def normalize_args(args: dict) -> str:
    """Sort keys for consistent hashing."""
    return json.dumps(args, sort_keys=True)

def compute_call_hash(tool_name: str, args: dict) -> str:
    payload = f"{tool_name}:{normalize_args(args)}"
    return hashlib.sha256(payload.encode()).hexdigest()[:16]

class LoopDetector:
    def __init__(self, threshold: int = 3):
        self.threshold = threshold
        self.call_counts: Counter = Counter()

    def record_call(self, tool_name: str, args: dict) -> bool:
        """Returns True if a loop is detected."""
        call_hash = compute_call_hash(tool_name, args)
        self.call_counts[call_hash] += 1
        return self.call_counts[call_hash] >= self.threshold`}</pre>

          <h3>Approach 2: Sliding window rate detection</h3>
          <p>
            Argument hashing catches exact repetition. Sliding window detection catches high-frequency calls regardless of argument variation. If a tool is called more than N times in M seconds, something is wrong.
          </p>
          <pre>{`from collections import deque
from datetime import datetime, timedelta

class RateLoopDetector:
    def __init__(self, max_calls: int = 10, window_seconds: int = 60):
        self.max_calls = max_calls
        self.window = timedelta(seconds=window_seconds)
        self.call_times: dict[str, deque] = {}

    def record_call(self, tool_name: str) -> bool:
        now = datetime.utcnow()
        if tool_name not in self.call_times:
            self.call_times[tool_name] = deque()
        times = self.call_times[tool_name]
        # Remove calls outside the window
        while times and now - times[0] > self.window:
            times.popleft()
        times.append(now)
        return len(times) >= self.max_calls`}</pre>

          <h3>Approach 3: LLM output similarity</h3>
          <p>
            The most sophisticated approach: detect when the LLM is generating the same reasoning steps repeatedly. Compare semantic similarity between consecutive reasoning outputs. High similarity ({">"} 0.95 cosine) across multiple steps indicates the agent is reasoning in circles.
          </p>
          <p>
            This is computationally expensive and usually overkill. Approaches 1 and 2 catch {">"} 90% of real-world loops.
          </p>

          <h2>What to do when a loop is detected</h2>
          <p>
            You have three options, configured per agent:
          </p>

          <h3>Option 1: Warn and continue</h3>
          <p>
            Log the detection, fire an alert, but let the agent keep running. Use this when you want visibility without disruption — good for early monitoring before you're confident in your detection thresholds.
          </p>

          <h3>Option 2: Terminate the session</h3>
          <p>
            Hard stop. The session is marked <code>loop_detected</code>, the agent receives a termination signal, and a structured error is returned to the caller. This is the right default for production.
          </p>

          <h3>Option 3: Inject a recovery message</h3>
          <p>
            Instead of terminating, inject a system message telling the agent it is stuck: <em>"You have called [tool] with the same arguments 3 times without progress. Stop and summarize what you know so far, then decide on a different approach."</em> This gives the agent a chance to self-recover before forcing termination.
          </p>

          <h2>Integrating loop detection with LangSight</h2>
          <p>
            LangSight's SDK handles all three detection approaches automatically. Two lines of code:
          </p>
          <pre>{`from langsight.sdk import LangSightClient

client = LangSightClient(
    url="http://localhost:8000",
    api_key="ls_...",
    loop_detection=True,
    loop_threshold=3,        # same tool+args 3x = loop
    loop_action="terminate", # or "warn" or "inject"
)

# Wrap your MCP session
traced = client.wrap(mcp_session, server_name="crm-mcp", agent_name="support-agent")

# Every tool call is now monitored
result = await traced.call_tool("lookup_customer", {"id": 456})`}</pre>
          <p>
            When a loop is detected, LangSight fires an alert with full context: which tool was looping, how many times it was called, the session ID, and the repeated arguments. The session is tagged <code>loop_detected</code> in the dashboard and filterable in the sessions view.
          </p>

          <h2>Budget guardrails: the backstop</h2>
          <p>
            Loop detection stops infinite repetition of identical calls. Budget guardrails are the backstop for everything else — they stop any session that exceeds a cost or step limit, regardless of the cause.
          </p>
          <pre>{`client = LangSightClient(
    url="http://localhost:8000",
    max_cost_usd=1.00,    # hard stop at $1
    max_steps=25,          # hard stop at 25 tool calls
    max_wall_time_s=120,   # hard stop at 2 minutes
    budget_soft_alert=0.80 # alert at 80% of budget
)`}</pre>
          <p>
            Use both together: loop detection for the known failure pattern, budget guardrails for unknown failure patterns you haven't anticipated yet.
          </p>

          <h2>Setting the right thresholds</h2>
          <p>
            The default threshold of 3 identical calls works for most agents. But some legitimate patterns require adjustment:
          </p>
          <ul>
            <li><strong>Polling agents</strong> — agents that legitimately poll a status endpoint should use time-based windows, not count-based detection. Set a longer window or whitelist the polling tool.</li>
            <li><strong>Retry-heavy workflows</strong> — if your agent is designed to retry operations, increase the threshold to 5 or 7 to avoid false positives on transient failures.</li>
            <li><strong>Sub-agents</strong> — each sub-agent in a multi-agent system should have its own loop detector. A parent agent calling the same sub-agent multiple times is not a loop — the sub-agents calling the same tools multiple times is.</li>
          </ul>

          <h2>Key takeaways</h2>
          <ul>
            <li>Agent loops are the most common production failure. Every production agent system will experience at least one.</li>
            <li>Standard retry logic makes loops worse. Detection needs to operate at the session level, not the call level.</li>
            <li>Argument hash comparison catches {">"} 90% of real loops with zero false positives at threshold 3.</li>
            <li>Always combine loop detection with budget guardrails. Loop detection catches the known pattern; budget guardrails catch everything else.</li>
            <li>Start with <code>loop_action="warn"</code>, monitor for a week, then switch to <code>"terminate"</code> once you're confident in your thresholds.</li>
          </ul>

          <div className="mt-12 p-6 border border-[var(--indigo)]/30 rounded-xl bg-[var(--indigo)]/5">
            <p className="font-semibold text-[var(--indigo)] mb-2">Stop agent loops in production</p>
            <p className="text-[var(--muted)] text-sm mb-4">
              LangSight adds loop detection, budget guardrails, and circuit breakers to any agent in two lines of code. Self-host free.
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
        .prose-custom em {
          font-style: italic;
        }
      `}</style>
    </main>
  );
}
