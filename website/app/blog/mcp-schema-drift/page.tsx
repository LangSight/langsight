"use client";

export default function McpSchemaDriftPost() {
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
            {["Schema Drift", "MCP Health", "Silent Failures"].map((tag) => (
              <span key={tag} className="text-xs px-2 py-0.5 rounded-full bg-[var(--indigo)]/10 text-[var(--indigo)] font-medium">
                {tag}
              </span>
            ))}
          </div>
          <h1 className="text-4xl font-bold leading-tight mb-4">
            Schema Drift in MCP: The Silent Failure Your Agents Cannot Detect
          </h1>
          <p className="text-xl text-[var(--muted)] leading-relaxed mb-6">
            A field was renamed in a community MCP server update. Agents kept calling the tool with the old field name, got empty results, and hallucinated downstream answers for three days before anyone noticed. Schema drift is the silent failure that your agents cannot detect on their own.
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
          <img src="/blog/mcp-schema-drift.png" alt="Schema Drift in MCP: The Silent Failure Your Agents Cannot Detect" className="w-full" />
          <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/30">
            <span className="text-2xl sm:text-3xl font-bold text-white tracking-wide drop-shadow-lg">Schema Drift</span>
            <span className="text-sm text-white/80 mt-1.5 drop-shadow-md">The silent failure your agents can&#39;t detect</span>
          </div>
        </div>

        {/* Content */}
        <div className="prose-custom">

          <h2>What is schema drift?</h2>
          <p>
            Every MCP tool has an input schema — a JSON Schema definition that describes what arguments the tool accepts. When an agent connects to an MCP server, it calls <code>tools/list</code> and receives these schemas. The LLM uses them to construct correct tool call arguments.
          </p>
          <p>
            Schema drift occurs when the MCP server changes a tool's schema between versions. A parameter gets renamed. A field type changes from string to integer. A new required argument is added. An entire tool is removed or replaced with a different name.
          </p>
          <p>
            The agent, which was tested and deployed against the old schema, continues calling tools with the old argument names and types. Depending on how the server handles unrecognized arguments, this results in one of three outcomes — each progressively harder to detect.
          </p>

          <h2>Three failure modes of schema drift</h2>

          <h3>Mode 1: Hard failure (best case)</h3>
          <p>
            The MCP server validates incoming arguments against the new schema and rejects calls with invalid arguments. The agent gets a clear error: <code>{"\"error\": \"Unknown parameter: customer_id. Did you mean: account_id?\""}</code>
          </p>
          <p>
            This is the best outcome because it is immediately visible. The agent fails loudly, the error appears in traces, and someone investigates. Unfortunately, many MCP servers do not do strict input validation — they accept unknown arguments silently.
          </p>

          <h3>Mode 2: Partial results (harder to detect)</h3>
          <p>
            The server accepts the call but ignores the unrecognized argument. The tool returns results, but without the intended filter. Instead of returning customer #456, it returns all customers (or the first customer, or an empty result set depending on the implementation).
          </p>
          <pre>{`# Before schema drift: the agent sends the correct field name
tool_call: get_customer(customer_id=456)
→ Returns: { "name": "Acme Corp", "plan": "enterprise" }

# After schema drift: field renamed to account_id
# The agent still sends customer_id (the old name)
tool_call: get_customer(customer_id=456)
→ Returns: { "name": null, "plan": null }
# Server ignored the unknown field, returned empty result

# The agent now reasons over empty data:
"I could not find any customer with that ID. The customer
 may not exist in our system."
# WRONG — the customer exists, the field name just changed`}</pre>
          <p>
            This is the most dangerous mode. The tool call succeeds (no error), the agent gets data back, but the data is wrong or empty. The agent then confidently reasons over incorrect data and provides the user with a wrong answer — which looks correct because it is well-formatted and articulate.
          </p>

          <h3>Mode 3: Semantic shift (hardest to detect)</h3>
          <p>
            The field name stays the same but its meaning changes. A <code>status</code> field that previously accepted <code>"active" | "inactive"</code> now accepts <code>"enabled" | "disabled" | "suspended"</code>. The agent sends <code>"active"</code>, the server does not recognize it, and returns results for all statuses — or no results.
          </p>
          <p>
            Semantic shifts are nearly impossible to detect without comparing the full schema definition (including enum values, descriptions, and constraints) between versions.
          </p>

          <h2>Why agents cannot detect schema drift</h2>
          <p>
            When an agent session starts, the client calls <code>tools/list</code> and gets the current tool schemas. The agent uses these schemas for that session. But the schemas the agent was <em>tested</em> against might be different from the schemas the server is currently serving.
          </p>
          <p>
            The agent has no memory of what the schema looked like when it was tested and deployed. It sees the current schema, constructs arguments based on the LLM's understanding of the current schema, and makes the call. If the schema changed between the last deployment and the current session, the agent does not know.
          </p>
          <p>
            Even if the agent re-fetches schemas at the start of each session (which most frameworks do), this does not help. The agent's behavior was tuned against the old schema. The LLM's system prompt, examples, and training data all reference the old field names and types. The new schema is different, but the agent does not know what changed or how to adapt.
          </p>

          <h2>How LangSight tracks schema drift</h2>
          <p>
            LangSight stores a snapshot of every MCP server's tool schemas on every health check. When the health checker runs (every 30 seconds by default), it calls <code>tools/list</code>, computes a hash of the full schema response, and compares it against the last known hash.
          </p>
          <p>
            If the hash changes, LangSight generates a detailed diff showing exactly what changed:
          </p>
          <pre>{`$ langsight mcp-health

Schema drift detected on crm-mcp:

  Tool: get_customer
  Change type: BREAKING — field renamed
  Before: { "customer_id": { "type": "string", "required": true } }
  After:  { "account_id":  { "type": "string", "required": true } }

  Tool: search_contacts
  Change type: COMPATIBLE — new optional field added
  Before: { "query": { "type": "string" } }
  After:  { "query": { "type": "string" }, "limit": { "type": "integer", "default": 50 } }

  Tool: delete_customer
  Change type: REMOVED — tool no longer available

  Impact: 3 agents use crm-mcp (support-agent, onboarding-agent, billing-agent)
  Action: review changes before upgrading agents`}</pre>
          <p>
            The diff categorizes changes into three types:
          </p>
          <ul>
            <li><strong>BREAKING</strong> — field renamed, field type changed, required field added, tool removed. Agents will fail or produce incorrect results.</li>
            <li><strong>COMPATIBLE</strong> — new optional field added, new tool added, description updated. Agents will continue working but may not take advantage of new capabilities.</li>
            <li><strong>SUSPICIOUS</strong> — description changed significantly (possible poisoning), enum values changed (semantic shift). Requires manual review.</li>
          </ul>

          <h2>The rug pull attack</h2>
          <p>
            Schema drift is usually accidental — a developer renames a field without considering backward compatibility. But it can also be intentional.
          </p>
          <p>
            A "rug pull" attack works like this: an attacker publishes a useful, well-reviewed MCP server. It gains adoption — hundreds of agents depend on it. Then the attacker pushes an update that changes tool descriptions to include poisoned instructions, or changes tool schemas to redirect data to attacker-controlled endpoints.
          </p>
          <p>
            If teams auto-update MCP server dependencies (which many do), the poisoned version deploys silently. The tool names are the same. The schemas look similar. But the behavior has changed.
          </p>
          <p>
            Schema drift detection catches this because it detects any change — including description changes that might contain injection patterns. Combined with LangSight's poisoning detector, the alert includes both "the schema changed" and "the new description contains suspicious patterns."
          </p>

          <h2>Versioning strategies</h2>

          <h3>Pin exact versions</h3>
          <p>
            Never use <code>latest</code> or unpinned versions for MCP servers in production. Pin the exact version or commit hash. This ensures that schema changes only happen when you explicitly upgrade.
          </p>
          <pre>{`# .langsight.yaml — pinned versions
servers:
  - name: crm-mcp
    transport: stdio
    command: "uvx --from crm-mcp==2.1.4 crm-server"
    schema_pin: "sha256:a1b2c3d4..."  # hash of expected schema`}</pre>

          <h3>Schema pinning</h3>
          <p>
            Beyond version pinning, pin the expected schema hash. If the server returns a different schema than expected — even if the version number has not changed — LangSight alerts. This catches scenarios where a server binary is modified without changing its version (compromised supply chain).
          </p>

          <h3>Staged rollouts</h3>
          <p>
            When upgrading an MCP server version, do not upgrade all agents at once. Upgrade one agent, monitor for 24 hours, check for schema-related errors and anomalies, then roll out to the rest. LangSight's per-agent session data makes it easy to compare error rates before and after the upgrade.
          </p>

          <h2>Key takeaways</h2>
          <ul>
            <li><strong>Schema drift is the most under-monitored MCP failure mode.</strong> It causes silent data corruption, not loud errors. Agents return wrong answers confidently.</li>
            <li><strong>Three failure modes, all dangerous:</strong> hard failures (detectable), partial results (subtle), and semantic shifts (nearly invisible).</li>
            <li><strong>Agents cannot detect schema drift on their own.</strong> They see the current schema, not the difference between current and tested schema.</li>
            <li><strong>Automated detection is essential.</strong> Snapshot schemas on every health check, diff on change, categorize as BREAKING/COMPATIBLE/SUSPICIOUS.</li>
            <li><strong>Pin versions and schemas.</strong> Never auto-update MCP servers in production. Pin both the version and the expected schema hash.</li>
          </ul>

          <h2>Related articles</h2>
          <ul>
            <li><a href="/blog/mcp-monitoring-production/" style={{ color: "var(--indigo)", textDecoration: "underline" }}>How to Monitor MCP Servers in Production</a> — Schema drift detection is one of five monitoring signals. Set up proactive health checks for your entire fleet.</li>
            <li><a href="/blog/mcp-tool-poisoning/" style={{ color: "var(--indigo)", textDecoration: "underline" }}>MCP Tool Poisoning</a> — The "rug pull" attack uses schema drift as the delivery mechanism for poisoned tool descriptions.</li>
            <li><a href="/blog/owasp-mcp-top-10-guide/" style={{ color: "var(--indigo)", textDecoration: "underline" }}>OWASP MCP Top 10 Explained</a> — Schema drift is MCP-05 in the OWASP framework. See the full security risk taxonomy.</li>
            <li><a href="/blog/circuit-breakers-ai-agents/" style={{ color: "var(--indigo)", textDecoration: "underline" }}>Circuit Breakers for AI Agents</a> — When schema drift causes tool failures, circuit breakers prevent cascading failures.</li>
          </ul>

          <div className="mt-12 p-6 border border-[var(--indigo)]/30 rounded-xl bg-[var(--indigo)]/5">
            <p className="font-semibold text-[var(--indigo)] mb-2">Detect schema drift before your agents break</p>
            <p className="text-[var(--muted)] text-sm mb-4">
              LangSight snapshots tool schemas on every health check and alerts on any change — with diffs, categorization, and impact analysis. Self-host free, Apache 2.0.
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
