"use client";

export default function LangsightVsLangfusePost() {
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
            {["Comparison", "Langfuse", "Observability"].map((tag) => (
              <span key={tag} className="text-xs px-2 py-0.5 rounded-full bg-[var(--indigo)]/10 text-[var(--indigo)] font-medium">
                {tag}
              </span>
            ))}
          </div>
          <h1 className="text-4xl font-bold leading-tight mb-4">
            LangSight vs Langfuse: Different Tools for Different Problems
          </h1>
          <p className="text-xl text-[var(--muted)] leading-relaxed mb-6">
            "Should I use LangSight or Langfuse?" We get asked this regularly. The honest answer: use both. They solve fundamentally different problems in your agent stack. Langfuse watches the brain. LangSight watches the hands. Here is exactly where each tool fits.
          </p>
          <div className="flex items-center gap-4 text-sm text-[var(--muted)] border-t border-[var(--border)] pt-6">
            <span>April 2, 2026</span>
            <span>·</span>
            <span>7 min read</span>
            <span>·</span>
            <span>LangSight Engineering</span>
          </div>
        </div>

        {/* Hero image */}
        <div className="mb-10 rounded-xl overflow-hidden border border-[var(--border)]">
          <img src="/blog/langsight-vs-langfuse.svg" alt="LangSight vs Langfuse: Different Tools for Different Problems" className="w-full" />
        </div>

        {/* Content */}
        <div className="prose-custom">

          <h2>Two layers of the same stack</h2>
          <p>
            An AI agent system has two distinct layers that need observability:
          </p>
          <p>
            <strong>The reasoning layer</strong> — what the LLM decides. Which prompts produce the best results? How do token costs vary by model? What is the quality of the LLM's output? How do different prompt versions compare? This is the brain of the system.
          </p>
          <p>
            <strong>The execution layer</strong> — what the agent does. Are the MCP servers healthy? Is a tool returning errors? Is the agent stuck in a loop? Is the session exceeding its budget? Are there security vulnerabilities in the tool ecosystem? This is the hands of the system.
          </p>
          <p>
            Langfuse is the best tool for the reasoning layer. It provides LLM tracing, prompt management, evaluations, and token cost tracking. It excels at helping you understand and improve what the LLM thinks.
          </p>
          <p>
            LangSight is built for the execution layer. It provides MCP health monitoring, security scanning, loop detection, budget enforcement, and circuit breakers. It excels at preventing runtime failures and ensuring the agent's tools are reliable and secure.
          </p>

          <h2>What each tool does well</h2>

          <div className="not-prose overflow-x-auto my-6">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="border-b border-[var(--border)]">
                  <th className="text-left py-3 px-4 text-[var(--fg)] font-semibold">Capability</th>
                  <th className="text-left py-3 px-4 text-[var(--fg)] font-semibold">Langfuse</th>
                  <th className="text-left py-3 px-4 text-[var(--fg)] font-semibold">LangSight</th>
                </tr>
              </thead>
              <tbody>
                {[
                  { cap: "LLM trace visualization", lf: "Yes", ls: "No" },
                  { cap: "Prompt management + versioning", lf: "Yes", ls: "No" },
                  { cap: "LLM evaluations (evals)", lf: "Yes", ls: "No" },
                  { cap: "Token cost tracking", lf: "Yes", ls: "Yes (per-session)" },
                  { cap: "MCP server health monitoring", lf: "No", ls: "Yes" },
                  { cap: "Security scanning (CVE, OWASP)", lf: "No", ls: "Yes" },
                  { cap: "Tool poisoning detection", lf: "No", ls: "Yes" },
                  { cap: "Loop detection", lf: "No", ls: "Yes" },
                  { cap: "Budget enforcement (hard limits)", lf: "No", ls: "Yes" },
                  { cap: "Circuit breakers", lf: "No", ls: "Yes" },
                  { cap: "Schema drift detection", lf: "No", ls: "Yes" },
                  { cap: "Blast radius mapping", lf: "No", ls: "Yes" },
                  { cap: "SLO tracking", lf: "No", ls: "Yes" },
                  { cap: "Self-hosted (Apache 2.0)", lf: "Yes", ls: "Yes" },
                  { cap: "Dataset management", lf: "Yes", ls: "No" },
                  { cap: "A/B testing prompts", lf: "Yes", ls: "No" },
                ].map((row) => (
                  <tr key={row.cap} className="border-b border-[var(--border)]/50">
                    <td className="py-3 px-4 text-[var(--muted)]">{row.cap}</td>
                    <td className="py-3 px-4">
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                        row.lf === "Yes" ? "bg-green-500/10 text-green-500" :
                        row.lf.startsWith("Yes") ? "bg-green-500/10 text-green-500" :
                        "bg-[var(--border)] text-[var(--dimmer)]"
                      }`}>{row.lf}</span>
                    </td>
                    <td className="py-3 px-4">
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                        row.ls === "Yes" ? "bg-green-500/10 text-green-500" :
                        row.ls.startsWith("Yes") ? "bg-green-500/10 text-green-500" :
                        "bg-[var(--border)] text-[var(--dimmer)]"
                      }`}>{row.ls}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <h2>The questions they answer</h2>
          <p>
            The easiest way to understand the difference is by the questions each tool answers:
          </p>

          <h3>Questions for Langfuse</h3>
          <ul>
            <li>What did the LLM decide at each step?</li>
            <li>How many tokens did this session consume?</li>
            <li>Which prompt version produces better output quality?</li>
            <li>What is the latency distribution of my LLM calls?</li>
            <li>How does GPT-4o compare to Claude 3.5 Sonnet for this use case?</li>
            <li>Where in the reasoning chain did the agent go wrong?</li>
          </ul>

          <h3>Questions for LangSight</h3>
          <ul>
            <li>Is the postgres-mcp server up right now?</li>
            <li>Are any of my MCP servers running vulnerable dependencies?</li>
            <li>Did any tool descriptions change since the last deploy?</li>
            <li>Is this agent stuck in a loop?</li>
            <li>How much did this session cost, and is it over budget?</li>
            <li>If slack-mcp goes down, which agents and sessions are affected?</li>
            <li>Are any tool descriptions poisoned with hidden instructions?</li>
            <li>What is the 7-day reliability score for my agent fleet?</li>
          </ul>

          <p>
            If your agent produces a wrong answer because the LLM misunderstood the user's intent — that is a Langfuse problem (prompt engineering, evals, model selection).
          </p>
          <p>
            If your agent produces a wrong answer because the MCP server returned corrupt data due to a schema change — that is a LangSight problem (schema drift detection, health monitoring).
          </p>

          <h2>How they work together</h2>
          <p>
            In a production stack, both tools run simultaneously and complement each other:
          </p>
          <p>
            <strong>Langfuse captures the trace:</strong> the full sequence of LLM calls, tool invocations, and reasoning steps. When you need to debug why the agent gave a specific answer, you look at the Langfuse trace to see the LLM's decision chain.
          </p>
          <p>
            <strong>LangSight monitors the infrastructure:</strong> the health of every MCP server, the security posture, the cost, and the reliability. When a Langfuse trace shows a tool call failure, LangSight tells you whether that tool has been failing for everyone (server outage) or just this session (transient error).
          </p>
          <p>
            The integration point is the tool call. When a Langfuse trace shows a tool call that took 30 seconds and returned an error, LangSight's health data provides the context: that MCP server had a p99 latency of 28 seconds for the past hour (degraded) and its circuit breaker opened twice in the last 30 minutes.
          </p>
          <p>
            Without Langfuse, you would not know that the LLM decided to call that tool in the first place (or why). Without LangSight, you would not know that the tool was degraded before the agent even tried to call it.
          </p>

          <h2>When to choose one over the other</h2>
          <p>
            If you are just starting and can only adopt one tool right now:
          </p>
          <ul>
            <li><strong>Choose Langfuse first</strong> if your primary challenge is LLM quality — the agent gives wrong answers, you need to compare prompt versions, or you need to evaluate model outputs.</li>
            <li><strong>Choose LangSight first</strong> if your primary challenge is runtime reliability — tools go down without alerting, costs are unpredictable, you have security concerns about MCP servers, or agents get stuck in loops.</li>
          </ul>
          <p>
            For any team running agents in production at scale, both tools are essential. They cover non-overlapping gaps in your observability stack.
          </p>

          <h2>A note on tone</h2>
          <p>
            We respect Langfuse. It is an excellent product, well-engineered, and the team behind it is doing important work for the LLM ecosystem. We are not competitors — we are complementary tools that solve different problems.
          </p>
          <p>
            We built LangSight because we needed runtime reliability tooling that did not exist. Langfuse does not do MCP health monitoring because that is not what it is designed for. LangSight does not do prompt management because that is not what it is designed for. Use the right tool for the right problem.
          </p>

          <h2>Key takeaways</h2>
          <ul>
            <li><strong>Different problems, different tools.</strong> Langfuse is LLM observability (reasoning quality, prompt engineering, evals). LangSight is runtime reliability (health monitoring, security, loop detection, budgets).</li>
            <li><strong>Use both for production agents.</strong> The reasoning layer and the execution layer both need observability. Skipping either leaves a critical blind spot.</li>
            <li><strong>Langfuse watches the brain. LangSight watches the hands.</strong> If the agent made a bad decision, check Langfuse. If the agent could not execute its decision, check LangSight.</li>
            <li><strong>Both are open source, both self-hostable.</strong> No vendor lock-in on either side of the stack.</li>
          </ul>

          <div className="mt-12 p-6 border border-[var(--indigo)]/30 rounded-xl bg-[var(--indigo)]/5">
            <p className="font-semibold text-[var(--indigo)] mb-2">Complete your observability stack</p>
            <p className="text-[var(--muted)] text-sm mb-4">
              LangSight adds the execution layer — MCP health, security, loops, budgets, circuit breakers — to your existing Langfuse setup. Self-host free, Apache 2.0.
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
