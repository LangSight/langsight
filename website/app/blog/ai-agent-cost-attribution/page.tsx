"use client";

export default function AiAgentCostAttributionPost() {
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
            {["Cost Tracking", "Budget", "Production"].map((tag) => (
              <span key={tag} className="text-xs px-2 py-0.5 rounded-full bg-[var(--indigo)]/10 text-[var(--indigo)] font-medium">
                {tag}
              </span>
            ))}
          </div>
          <h1 className="text-4xl font-bold leading-tight mb-4">
            AI Agent Cost Attribution: Tracking Spend Per Tool Call
          </h1>
          <p className="text-xl text-[var(--muted)] leading-relaxed mb-6">
            A sub-agent in a customer support pipeline was retrying a geocoding tool endlessly. $1,800 per week, charged to the shared AI account, invisible in the monthly bill. Nobody knew until the finance team asked why the Anthropic invoice tripled. Per-tool cost attribution would have caught this on day one.
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
        <div className="mb-10 rounded-xl overflow-hidden border border-[var(--border)] relative">
          <img src="/blog/ai-agent-cost-attribution.png" alt="AI Agent Cost Attribution: Tracking Spend Per Tool Call" className="w-full" />
          <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/30">
            <span className="text-2xl sm:text-3xl font-bold text-white tracking-wide drop-shadow-lg">Cost Attribution</span>
            <span className="text-sm text-white/80 mt-1.5 drop-shadow-md">Track every dollar across agents and tools</span>
          </div>
        </div>

        {/* Content */}
        <div className="prose-custom">

          <h2>The cost visibility problem</h2>
          <p>
            Every team running AI agents in production has the same blind spot: they know their total monthly AI spend (the Anthropic/OpenAI/AWS Bedrock invoice), but they cannot attribute that cost to specific tools, agents, or user sessions.
          </p>
          <p>
            The total spend is a single number: $4,200 this month. But which agent is responsible for $3,100 of that? Which tool calls are the most expensive? Which sessions ran up costs that should have been stopped by a budget limit? Without per-call cost attribution, you cannot answer any of these questions.
          </p>
          <p>
            This matters because AI agent costs are fundamentally unpredictable. A traditional API endpoint has relatively stable per-request cost. An AI agent session can cost $0.02 or $47 depending on how many tool calls the LLM decides to make, how many tokens each tool response contains, and whether the agent gets stuck in a loop. The variance is enormous — and without attribution, you cannot identify or fix the outliers.
          </p>

          <h2>What to track: two types of cost</h2>
          <p>
            AI agent sessions have two distinct cost categories, and you need to track both separately.
          </p>

          <h3>Token-based costs (LLM calls)</h3>
          <p>
            Every time the agent calls the LLM — to decide which tool to call, to process a tool response, to generate a final answer — you incur token costs. These are priced per input token and per output token, with rates that vary by model.
          </p>
          <pre>{`# Token cost calculation per LLM call
cost = (input_tokens * input_price_per_token) +
       (output_tokens * output_price_per_token)

# Example: Claude 3.5 Sonnet pricing
# Input: $3.00 / 1M tokens = $0.000003 per token
# Output: $15.00 / 1M tokens = $0.000015 per token

# A typical agent turn with 2,000 input + 500 output tokens:
# (2000 * 0.000003) + (500 * 0.000015) = $0.006 + $0.0075 = $0.0135`}</pre>
          <p>
            Token costs are predictable per call but unpredictable per session because the number of LLM calls depends on the agent's reasoning path. A simple query might take 2 LLM calls ($0.03). A complex query with multiple tool calls might take 15 LLM calls ($0.20). A looping agent can make 80+ LLM calls ($1.00+).
          </p>

          <h3>Call-based costs (tool invocations)</h3>
          <p>
            Some tools have per-call costs independent of tokens. A geocoding API charges $0.005 per call. A database query has compute cost. An email send has per-message cost. These costs are incurred by the tool call itself, not by the LLM processing.
          </p>
          <p>
            LangSight tracks both cost types. Token costs are calculated automatically from the model pricing table. Call-based costs are configured per tool in <code>.langsight.yaml</code>:
          </p>
          <pre>{`# .langsight.yaml — cost configuration
models:
  claude-3-5-sonnet:
    input_cost_per_1m: 3.00
    output_cost_per_1m: 15.00
  claude-3-opus:
    input_cost_per_1m: 15.00
    output_cost_per_1m: 75.00

tool_costs:
  geocoding-mcp/geocode:
    type: call_based
    cost_per_call: 0.005
  email-mcp/send_email:
    type: call_based
    cost_per_call: 0.001
  postgres-mcp/query:
    type: call_based
    cost_per_call: 0.0001  # estimate based on compute`}</pre>

          <h2>Per-session cost tracking</h2>
          <p>
            The most useful view of cost data is per session. A session is one complete agent interaction — from the initial user request to the final response. The session cost includes all LLM calls and all tool calls that occurred during that interaction.
          </p>
          <pre>{`$ langsight costs --hours 24

Session Cost Summary (last 24 hours)
┌──────────────────┬──────────┬───────┬──────────┬───────────┬────────┐
│ Session          │ Agent    │ Steps │ LLM Cost │ Tool Cost │ Total  │
├──────────────────┼──────────┼───────┼──────────┼───────────┼────────┤
│ sess_a1b2c3d4    │ support  │ 4     │ $0.054   │ $0.002    │ $0.056 │
│ sess_e5f6g7h8    │ support  │ 7     │ $0.094   │ $0.015    │ $0.109 │
│ sess_i9j0k1l2    │ analyst  │ 12    │ $0.162   │ $0.045    │ $0.207 │
│ sess_m3n4o5p6    │ support  │ 47    │ $2.340   │ $44.650   │ $47.00 │
│ ...              │ ...      │ ...   │ ...      │ ...       │ ...    │
├──────────────────┼──────────┼───────┼──────────┼───────────┼────────┤
│ Total (847 sess) │ —        │ 3,421 │ $34.20   │ $67.80    │ $102.0 │
└──────────────────┴──────────┴───────┴──────────┴───────────┴────────┘

Anomalies detected:
  sess_m3n4o5p6  $47.00 — 8.4x median session cost
    → geocoding-mcp/geocode called 8,930 times (loop detected)
    → Recommendation: enable loop detection + budget guardrail`}</pre>
          <p>
            That $47 session jumps out immediately. 47 steps. 8,930 tool calls to the geocoding endpoint. Without per-session cost tracking, this cost is buried in the aggregate monthly bill and invisible until someone manually investigates why the bill tripled.
          </p>

          <h2>Budget guardrails</h2>
          <p>
            Cost tracking tells you what happened. Budget guardrails prevent it from happening. LangSight supports two levels of budget control:
          </p>

          <h3>Soft alert: warn before it gets expensive</h3>
          <p>
            A soft budget alert fires when a session reaches a configured cost threshold. The session continues, but the team gets a notification. This is useful for monitoring without disrupting active sessions.
          </p>

          <h3>Hard limit: stop the session</h3>
          <p>
            A hard budget limit terminates the session when the cost exceeds the configured maximum. The agent receives a termination signal and the session is marked as <code>budget_exceeded</code>.
          </p>
          <pre>{`from langsight.sdk import LangSightClient

client = LangSightClient(
    url="http://localhost:8000",
    api_key="ls_...",

    # Budget guardrails
    max_cost_usd=1.00,        # hard stop at $1 per session
    budget_soft_alert=0.50,   # alert at $0.50

    # Also set step limits as a backstop
    max_steps=25,             # hard stop at 25 tool calls
    max_wall_time_s=120,      # hard stop at 2 minutes
)

# Every session through this client enforces budget limits
traced = client.wrap(mcp_session, agent_name="support-agent")`}</pre>
          <p>
            Budget guardrails and loop detection work together. Loop detection catches the specific pattern of repeated identical calls. Budget guardrails catch any session that gets expensive for any reason — loops, complex reasoning chains, expensive tools, or unexpected agent behavior.
          </p>

          <h2>Finding the expensive outliers</h2>
          <p>
            The most actionable insight from cost attribution is identifying outlier sessions. In a typical agent deployment, 80% of sessions cost under $0.10. The top 5% of sessions account for 60% of the total spend. Finding and fixing those outliers is the highest-ROI optimization.
          </p>
          <p>
            Common causes of expensive outlier sessions:
          </p>
          <ul>
            <li><strong>Loop without detection</strong> — the agent calls the same tool repeatedly. Fix: enable loop detection.</li>
            <li><strong>Expensive tool overuse</strong> — the agent calls a geocoding API 200 times when 5 would suffice. Fix: add a per-tool call limit or instruct the agent to batch requests.</li>
            <li><strong>Large context windows</strong> — tool responses are massive (database returns 10,000 rows) and each LLM call processes the entire context. Fix: paginate tool responses, summarize before returning to the LLM.</li>
            <li><strong>Wrong model selection</strong> — a simple classification task routed to Claude 3 Opus instead of Haiku. Fix: use model routing based on task complexity.</li>
          </ul>

          <h2>Cost optimization strategies</h2>
          <p>
            Once you have attribution data, optimization becomes systematic:
          </p>
          <ul>
            <li><strong>Identify the most expensive tools.</strong> Sort tools by total cost. The top 3 tools usually account for 70% of tool costs. Optimize or rate-limit those first.</li>
            <li><strong>Set per-agent budgets.</strong> Different agents have different expected costs. A simple FAQ agent should cost $0.05 per session. A complex data analysis agent might legitimately cost $0.50. Set per-agent budgets that reflect expected behavior.</li>
            <li><strong>Review outlier sessions weekly.</strong> Look at the top 10 most expensive sessions from the past week. For each one, determine if the cost was justified (complex legitimate query) or waste (loop, wrong model, excessive tool calls).</li>
            <li><strong>Tune agent instructions.</strong> If an agent is making unnecessary tool calls, update its system prompt to be more efficient. "Check the database once for all needed fields" instead of making separate queries for each field.</li>
          </ul>

          <h2>Key takeaways</h2>
          <ul>
            <li><strong>Cost attribution is essential for production agents.</strong> Without per-session, per-tool cost tracking, expensive outliers hide in aggregate bills until finance notices.</li>
            <li><strong>Track two cost types:</strong> token-based (LLM calls) and call-based (tool invocations). Both contribute to total session cost.</li>
            <li><strong>Budget guardrails prevent runaway costs.</strong> Soft alerts for visibility, hard limits for protection. Always use both together with loop detection.</li>
            <li><strong>Focus on outliers.</strong> 5% of sessions cause 60% of costs. Finding and fixing those outliers delivers the highest ROI.</li>
            <li><strong>One command to see costs:</strong> <code>langsight costs --hours 24</code> shows per-session attribution with anomaly detection built in.</li>
          </ul>

          <h2>Related articles</h2>
          <ul>
            <li><a href="/blog/ai-agent-loop-detection/" style={{ color: "var(--indigo)", textDecoration: "underline" }}>How to Detect and Stop AI Agent Loops</a> — Loops are the most common cause of runaway costs. Detect and stop them before they burn your budget.</li>
            <li><a href="/blog/slos-for-ai-agents/" style={{ color: "var(--indigo)", textDecoration: "underline" }}>Setting SLOs for AI Agents</a> — Budget adherence is one of the four SLO metrics. Learn how to define and enforce cost targets.</li>
            <li><a href="/blog/circuit-breakers-ai-agents/" style={{ color: "var(--indigo)", textDecoration: "underline" }}>Circuit Breakers for AI Agents</a> — Failed tool calls waste tokens. Circuit breakers prevent expensive retry cascades.</li>
            <li><a href="/blog/langsight-vs-langfuse/" style={{ color: "var(--indigo)", textDecoration: "underline" }}>LangSight vs Langfuse</a> — How LangSight's per-session cost tracking complements Langfuse's token-level cost tracking.</li>
          </ul>

          <div className="mt-12 p-6 border border-[var(--indigo)]/30 rounded-xl bg-[var(--indigo)]/5">
            <p className="font-semibold text-[var(--indigo)] mb-2">Track AI agent costs per tool call</p>
            <p className="text-[var(--muted)] text-sm mb-4">
              LangSight attributes costs to specific tools, agents, and sessions. Budget guardrails stop runaway spend before it hits your invoice. Self-host free, Apache 2.0.
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
