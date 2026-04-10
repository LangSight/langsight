"use client";

import { Nav, Footer, useTheme } from "@/components/site-shell";

export default function SlosForAiAgentsPost() {
  const { dark, toggle } = useTheme();
  return (
    <main className="min-h-screen bg-[var(--bg)] text-[var(--fg)]">
      <Nav dark={dark} toggle={toggle} activePage="Blog" />

      <article className="max-w-3xl mx-auto px-6 py-16">
        {/* Header */}
        <div className="mb-10">
          <div className="flex flex-wrap gap-2 mb-4">
            {["SLOs", "Reliability Engineering", "Monitoring"].map((tag) => (
              <span key={tag} className="text-xs px-2 py-0.5 rounded-full bg-[var(--indigo)]/10 text-[var(--indigo)] font-medium">
                {tag}
              </span>
            ))}
          </div>
          <h1 className="text-4xl font-bold leading-tight mb-4">
            Setting SLOs for AI Agents: A Practical Guide
          </h1>
          <p className="text-xl text-[var(--muted)] leading-relaxed mb-6">
            Your VP asks: "What is the reliability of our AI products?" You have no number to give. No success rate. No latency target. No error budget. Traditional SRE practices work for deterministic services. AI agents are non-deterministic. Here is how to adapt SLOs for a world where the same input can produce different outputs.
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
          <img src="/blog/slos-for-ai-agents.png" alt="Setting SLOs for AI Agents: A Practical Guide" className="w-full" />
          <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/30">
            <span className="text-2xl sm:text-3xl font-bold text-white tracking-wide drop-shadow-lg">Agent SLOs</span>
            <span className="text-sm text-white/80 mt-1.5 drop-shadow-md">Set reliability targets that actually work</span>
          </div>
        </div>

        {/* Content */}
        <div className="prose-custom">

          <h2>Why AI agents need SLOs</h2>
          <p>
            Service Level Objectives (SLOs) are the foundation of reliability engineering. They define what "reliable enough" means for a service, expressed as a measurable target over a time window. Google's SRE book popularized the concept for traditional services: "99.9% of requests complete within 300ms over a rolling 30-day window."
          </p>
          <p>
            AI agents need SLOs for the same reason traditional services do: without a measurable target, reliability is a subjective judgment. "The agent seems to be working fine" is not an engineering statement. "The agent has a 96.3% success rate with p99 latency of 12 seconds over the past 7 days" is.
          </p>
          <p>
            But AI agents are fundamentally different from traditional services. They are non-deterministic — the same input can produce different outputs. They have variable execution paths — one session might take 2 tool calls, another might take 15. They have failure modes that traditional services do not — loops, hallucinations, budget overruns. Standard SLOs (uptime, latency, error rate) are necessary but not sufficient.
          </p>

          <h2>Four SLO metrics for AI agents</h2>
          <p>
            Based on running agent systems in production, these four metrics capture the dimensions of reliability that matter most:
          </p>

          <h3>1. Success rate</h3>
          <p>
            <strong>Definition:</strong> The percentage of sessions that complete without failure. A session "succeeds" if the agent produces a final response without hitting a loop, budget limit, tool error, or timeout. A session "fails" if it is terminated by any of these guardrails.
          </p>
          <p>
            <strong>Realistic targets:</strong> For well-tuned agents, 95-98% success rate is achievable. 99%+ is unrealistic for agents handling diverse, real-world inputs. Set the initial target conservatively (90%) and tighten as you gain confidence.
          </p>
          <pre>{`# LangSight SLO definition
{
  "agent": "support-agent",
  "metric": "success_rate",
  "target": 0.95,           # 95% of sessions succeed
  "window": "7d",            # evaluated over rolling 7 days
  "exclude": ["test", "internal"]  # exclude test sessions
}`}</pre>

          <h3>2. Latency (p99 end-to-end)</h3>
          <p>
            <strong>Definition:</strong> The 99th percentile end-to-end session duration — from the initial user request to the final agent response. This includes all LLM calls, all tool calls, and all processing time.
          </p>
          <p>
            <strong>Realistic targets:</strong> Highly variable by use case. A simple FAQ agent should complete in under 5 seconds. A data analysis agent that makes 10 tool calls might take 30 seconds. Set the target based on your specific agent's expected behavior, not based on general benchmarks.
          </p>
          <pre>{`{
  "agent": "support-agent",
  "metric": "latency_p99",
  "target_seconds": 15,     # 99% of sessions complete in < 15s
  "window": "7d"
}`}</pre>

          <h3>3. Loop rate</h3>
          <p>
            <strong>Definition:</strong> The percentage of sessions that trigger loop detection. A high loop rate indicates that the agent is frequently getting stuck, which wastes tokens and produces poor user experiences even if the loop is detected and terminated cleanly.
          </p>
          <p>
            <strong>Realistic targets:</strong> Below 2% for a well-tuned agent. If loop rate exceeds 5%, investigate the root causes — typically a specific tool that returns confusing responses or a prompt that does not handle edge cases well.
          </p>
          <pre>{`{
  "agent": "support-agent",
  "metric": "loop_rate",
  "target": 0.02,           # < 2% of sessions trigger loops
  "window": "7d"
}`}</pre>

          <h3>4. Budget adherence</h3>
          <p>
            <strong>Definition:</strong> The percentage of sessions that complete within their configured cost budget. If the budget is $1 per session, budget adherence measures how many sessions actually cost less than $1.
          </p>
          <p>
            <strong>Realistic targets:</strong> 98%+ is achievable with properly configured budgets. The 2% that exceed the budget should be outliers (complex queries that legitimately need more tool calls), not systemic issues (loops, wrong model selection).
          </p>
          <pre>{`{
  "agent": "support-agent",
  "metric": "budget_adherence",
  "target": 0.98,           # 98% of sessions within budget
  "budget_usd": 1.00,       # per-session budget
  "window": "7d"
}`}</pre>

          <h2>Setting realistic targets</h2>
          <p>
            The most common mistake when setting SLOs for AI agents is setting targets that are too aggressive. Engineers coming from traditional SRE set 99.9% targets because that is what they set for APIs. But agents are non-deterministic. A 99.9% success rate for an AI agent means only 1 in 1,000 sessions fails — which requires near-perfect prompt engineering, tools that never fail, and users who never ask edge-case questions.
          </p>
          <p>
            Start with these guidelines:
          </p>

          <div className="not-prose overflow-x-auto my-6">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="border-b border-[var(--border)]">
                  <th className="text-left py-3 px-4 text-[var(--fg)] font-semibold">Metric</th>
                  <th className="text-left py-3 px-4 text-[var(--fg)] font-semibold">Conservative</th>
                  <th className="text-left py-3 px-4 text-[var(--fg)] font-semibold">Standard</th>
                  <th className="text-left py-3 px-4 text-[var(--fg)] font-semibold">Aggressive</th>
                </tr>
              </thead>
              <tbody>
                {[
                  { metric: "Success rate", con: "90%", std: "95%", agg: "98%" },
                  { metric: "Latency p99", con: "30s", std: "15s", agg: "8s" },
                  { metric: "Loop rate", con: "< 5%", std: "< 2%", agg: "< 0.5%" },
                  { metric: "Budget adherence", con: "95%", std: "98%", agg: "99.5%" },
                ].map((row) => (
                  <tr key={row.metric} className="border-b border-[var(--border)]/50">
                    <td className="py-3 px-4 text-[var(--fg)] font-medium">{row.metric}</td>
                    <td className="py-3 px-4 text-[var(--muted)]">{row.con}</td>
                    <td className="py-3 px-4 font-mono text-[var(--indigo)]">{row.std}</td>
                    <td className="py-3 px-4 text-[var(--muted)]">{row.agg}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p>
            Start with conservative targets, measure for 2-4 weeks, then tighten based on actual data. Do not start with aggressive targets — you will immediately be in SLO violation and the SLOs will lose credibility.
          </p>

          <h2>Evaluation windows</h2>
          <p>
            SLOs are evaluated over rolling time windows. The window length determines how sensitive the SLO is to recent events:
          </p>
          <ul>
            <li><strong>1-hour window</strong> — highly sensitive to recent issues. Useful for real-time dashboards and operational monitoring. A 30-minute outage immediately violates the SLO.</li>
            <li><strong>24-hour window</strong> — balances sensitivity with stability. Good for daily standup reporting. A brief outage affects the SLO but does not dominate it.</li>
            <li><strong>7-day window</strong> — the standard for SLO reporting. Smooths out transient issues. Shows the trend. This is the window your VP should see.</li>
            <li><strong>30-day window</strong> — used for error budget calculations and quarterly reviews. Shows the big picture.</li>
          </ul>
          <p>
            LangSight evaluates SLOs across all four windows simultaneously. The dashboard shows the current value for each window, so you can see both the real-time state (1h) and the trend (7d/30d).
          </p>

          <h2>Error budgets: what to do when SLOs breach</h2>
          <p>
            An error budget is the inverse of the SLO target: if success rate target is 95%, the error budget is 5% — you can tolerate 5% of sessions failing. When the error budget is exhausted (actual failure rate exceeds 5%), you need a response policy.
          </p>
          <p>
            Borrowed from Google's SRE practices, error budget policies for agents should include:
          </p>
          <ul>
            <li><strong>Alert escalation:</strong> When error budget drops below 50%, alert the team. Below 20%, page the on-call. At 0%, freeze deployments until the root cause is fixed.</li>
            <li><strong>Deployment freeze:</strong> When error budget is exhausted, stop deploying new agent changes until the failure rate recovers. This prevents compounding issues.</li>
            <li><strong>Postmortem trigger:</strong> When error budget is exhausted, automatically create a postmortem document with the relevant session data, failure categories, and timeline.</li>
            <li><strong>Reliability sprint:</strong> If the error budget is consistently tight, allocate engineering time specifically to reliability improvements — better error handling, improved prompts, additional guardrails.</li>
          </ul>
          <pre>{`# .langsight.yaml — error budget policy
slos:
  - agent: support-agent
    success_rate:
      target: 0.95
      window: 7d
    error_budget_policy:
      alert_at: [0.50, 0.20, 0.0]      # alert at 50%, 20%, 0% remaining
      freeze_deploys_at: 0.0             # freeze at budget exhaustion
      postmortem_at: 0.0                 # auto-create postmortem`}</pre>

          <h2>Reporting to stakeholders</h2>
          <p>
            The SLO dashboard is the answer to "what is the reliability of our AI products?" For each agent, it shows:
          </p>
          <ul>
            <li>Current success rate vs target (with trend arrow)</li>
            <li>Current latency p99 vs target</li>
            <li>Error budget remaining (as a percentage and as remaining failure count)</li>
            <li>Top failure categories (loop, tool error, budget exceeded, timeout)</li>
            <li>7-day and 30-day trends</li>
          </ul>
          <p>
            This gives stakeholders a quantitative, trustworthy answer. Not "the agent seems fine" but "the support agent has a 96.3% success rate against a 95% target, with 62% of its error budget remaining for the 30-day window."
          </p>

          <h2>Key takeaways</h2>
          <ul>
            <li><strong>AI agents need SLOs adapted for non-determinism.</strong> Traditional uptime is not enough. Track success rate, latency p99, loop rate, and budget adherence.</li>
            <li><strong>Start conservative, tighten with data.</strong> Begin with 90% success rate, measure for 2-4 weeks, then raise the target based on actual performance. Do not start at 99%.</li>
            <li><strong>Use multiple evaluation windows.</strong> 1-hour for operations, 7-day for team reporting, 30-day for error budgets. Each window serves a different audience.</li>
            <li><strong>Error budget policies drive action.</strong> When the budget is exhausted, freeze deployments, trigger postmortems, and allocate reliability sprints. Without policies, SLOs are just numbers.</li>
            <li><strong>SLOs answer the reliability question.</strong> When your VP asks "how reliable are our AI products?", the SLO dashboard provides a quantitative, defensible answer.</li>
          </ul>

          <h2>Related articles</h2>
          <ul>
            <li><a href="/blog/ai-agent-loop-detection/" style={{ color: "var(--indigo)", textDecoration: "underline" }}>AI Agent Loop Detection</a> — Loop rate is one of the four SLO metrics. Learn how to detect and prevent the most common agent failure mode.</li>
            <li><a href="/blog/ai-agent-cost-attribution/" style={{ color: "var(--indigo)", textDecoration: "underline" }}>AI Agent Cost Attribution</a> — Budget adherence is an SLO metric. Per-session cost tracking makes it measurable.</li>
            <li><a href="/blog/mcp-monitoring-production/" style={{ color: "var(--indigo)", textDecoration: "underline" }}>How to Monitor MCP Servers in Production</a> — MCP health data feeds into agent availability SLOs.</li>
            <li><a href="/blog/blast-radius-mapping/" style={{ color: "var(--indigo)", textDecoration: "underline" }}>Blast Radius Mapping</a> — Understand dependencies to set appropriate per-agent SLO targets based on tool reliability.</li>
          </ul>

          <div className="mt-12 p-6 border border-[var(--indigo)]/30 rounded-xl bg-[var(--indigo)]/5">
            <p className="font-semibold text-[var(--indigo)] mb-2">Set and track SLOs for your agents</p>
            <p className="text-[var(--muted)] text-sm mb-4">
              LangSight tracks success rate, latency, loop rate, and budget adherence across multiple time windows. Error budgets with automated alerting and deployment freeze policies. Self-host free, Apache 2.0.
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
      <Footer />
    </main>
  );
}
