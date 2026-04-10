"use client";

import { Nav, Footer, useTheme } from "@/components/site-shell";

export default function SelfHostingAiObservabilityPost() {
  const { dark, toggle } = useTheme();
  return (
    <main className="min-h-screen bg-[var(--bg)] text-[var(--fg)]">
      <Nav dark={dark} toggle={toggle} activePage="Blog" />

      <article className="max-w-3xl mx-auto px-6 py-16">
        {/* Header */}
        <div className="mb-10">
          <div className="flex flex-wrap gap-2 mb-4">
            {["Self-Hosted", "Data Privacy", "Open Source"].map((tag) => (
              <span key={tag} className="text-xs px-2 py-0.5 rounded-full bg-[var(--indigo)]/10 text-[var(--indigo)] font-medium">
                {tag}
              </span>
            ))}
          </div>
          <h1 className="text-4xl font-bold leading-tight mb-4">
            Self-Hosting AI Observability: Why Your Data Should Never Leave
          </h1>
          <p className="text-xl text-[var(--muted)] leading-relaxed mb-6">
            Every tool call your agent makes — the tool name, the arguments, the response — is flowing to a third-party SaaS for observability. Those arguments include customer names, database queries, internal API endpoints, and sometimes API keys. Your agent traces are the most sensitive data in your stack, and they are leaving your network.
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
        <div className="mb-10 rounded-xl overflow-hidden border border-[var(--border)] relative">
          <img src="/blog/self-hosting-ai-observability.png" alt="Self-Hosting AI Observability: Why Your Data Should Never Leave" className="w-full" />
          <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/30">
            <span className="text-2xl sm:text-3xl font-bold text-white tracking-wide drop-shadow-lg">Self-Hosted</span>
            <span className="text-sm text-white/80 mt-1.5 drop-shadow-md">Your data never leaves your network</span>
          </div>
        </div>

        {/* Content */}
        <div className="prose-custom">

          <h2>What agent traces actually contain</h2>
          <p>
            An agent trace from a typical customer support session includes:
          </p>
          <ul>
            <li>The user's original message (potentially containing PII: "My name is Sarah Johnson, my account email is sarah@example.com")</li>
            <li>Every LLM prompt and response (including the system prompt with your proprietary agent logic)</li>
            <li>Every tool call with full arguments (<code>{`crm-mcp/get_customer(email="sarah@example.com")`}</code>)</li>
            <li>Every tool response (full customer record: name, email, billing address, plan details, payment method)</li>
            <li>Internal API endpoints referenced in tool configurations</li>
            <li>Database queries with table names and column names (reveals your schema)</li>
          </ul>
          <p>
            When you send this data to a cloud observability SaaS, you are sending your customer PII, your proprietary business logic, your internal infrastructure details, and your data schema to a third party. Even if that third party has excellent security practices, this creates risks that many organizations cannot accept.
          </p>

          <h2>The four risks of cloud-hosted agent observability</h2>

          <h3>1. Data residency and compliance</h3>
          <p>
            GDPR requires that European customer data stay within the EU unless specific legal mechanisms are in place. SOC 2 Type II requires that you can demonstrate control over where customer data is stored and who can access it. HIPAA requires that protected health information stays within covered entities and business associates.
          </p>
          <p>
            If your agent processes customer data (and most agents do), the traces contain that customer data. Sending traces to a US-based SaaS creates a data residency issue for EU customers. Sending traces to any third party creates a compliance documentation burden.
          </p>
          <p>
            Self-hosting eliminates this entirely. The data stays in your VPC, in your region, under your access controls. Compliance audits are straightforward: "All observability data is stored in our eu-west-1 PostgreSQL instance with encryption at rest."
          </p>

          <h3>2. Vendor lock-in</h3>
          <p>
            Cloud observability platforms store your historical trace data. If you decide to switch vendors, that historical data is either inaccessible (proprietary format) or requires a costly migration. The longer you use the platform, the harder it is to leave.
          </p>
          <p>
            With self-hosted, your data is in standard PostgreSQL and ClickHouse databases. You own the data, the format, and the access. Migrate, fork, or build custom tooling on top — no vendor permission required.
          </p>

          <h3>3. Cost scaling</h3>
          <p>
            Cloud observability pricing scales with data volume. As your agent fleet grows — more agents, more sessions, more tool calls — the observability bill grows proportionally. At scale, observability costs can rival the LLM costs themselves.
          </p>
          <p>
            A rough comparison for a team running 10 agents with 1,000 sessions per day:
          </p>

          <div className="not-prose overflow-x-auto my-6">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="border-b border-[var(--border)]">
                  <th className="text-left py-3 px-4 text-[var(--fg)] font-semibold">Platform</th>
                  <th className="text-left py-3 px-4 text-[var(--fg)] font-semibold">Monthly Cost</th>
                  <th className="text-left py-3 px-4 text-[var(--fg)] font-semibold">Data Residency</th>
                </tr>
              </thead>
              <tbody>
                {[
                  { platform: "Datadog LLM Observability", cost: "~$2,400/mo", residency: "US/EU (their infra)" },
                  { platform: "Langsmith (cloud)", cost: "~$400/mo", residency: "US (their infra)" },
                  { platform: "LangSight (self-hosted)", cost: "$0", residency: "Your VPC" },
                ].map((row) => (
                  <tr key={row.platform} className="border-b border-[var(--border)]/50">
                    <td className="py-3 px-4 text-[var(--muted)]">{row.platform}</td>
                    <td className="py-3 px-4 font-mono text-[var(--indigo)]">{row.cost}</td>
                    <td className="py-3 px-4 text-[var(--muted)]">{row.residency}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p>
            Self-hosting is not free — you pay for the compute and storage. But a PostgreSQL and ClickHouse instance for 10 agents costs roughly $50-100/month on AWS, compared to $2,400+/month for enterprise cloud observability.
          </p>

          <h3>4. Attack surface</h3>
          <p>
            Every third-party service with access to your data is part of your attack surface. A breach at your observability vendor exposes your agent traces — which contain customer PII, internal APIs, and database schemas. The observability vendor becomes the most data-rich target in your supply chain.
          </p>
          <p>
            Self-hosting contains the attack surface within your existing security perimeter. The same security controls, access policies, and monitoring that protect your production databases also protect your observability data.
          </p>

          <h2>Why self-hosting matters for AI specifically</h2>
          <p>
            Traditional infrastructure observability (CPU metrics, request latency, error rates) contains minimal sensitive data. A Prometheus metric like <code>http_requests_total</code> does not contain PII.
          </p>
          <p>
            AI agent observability is fundamentally different. Agent traces contain the full content of every interaction — user messages, LLM reasoning, tool arguments, and tool responses. This data is among the most sensitive in your entire system. It is the complete record of every action your AI took on behalf of every user.
          </p>
          <p>
            The sensitivity of agent trace data is why self-hosting is not just a nice-to-have — it is a security and compliance requirement for teams processing customer data through AI agents.
          </p>

          <h2>LangSight's self-hosted architecture</h2>
          <p>
            LangSight is designed to be self-hosted from the ground up. There is no cloud service to phone home to, no telemetry sent to our servers, and no feature gating behind a paid cloud tier.
          </p>
          <pre>{`# Full stack in one command
$ docker compose up -d

Creating langsight-postgres   ... done
Creating langsight-clickhouse ... done
Creating langsight-api        ... done
Creating langsight-dashboard  ... done

# That's it. Full observability stack running in your VPC.
# PostgreSQL: app state, configs, alerts
# ClickHouse: time-series health data, traces
# API: FastAPI, async, ~50MB memory
# Dashboard: Next.js, self-contained`}</pre>
          <p>
            The CLI mode requires even less — no Docker at all. <code>langsight init && langsight monitor</code> stores data in a local SQLite database. Suitable for individual developers and small teams who want monitoring without infrastructure overhead.
          </p>

          <h2>The Apache 2.0 advantage</h2>
          <p>
            LangSight uses the Apache 2.0 license — the most permissive open-source license commonly used for infrastructure software. This means:
          </p>
          <ul>
            <li><strong>No open-core restrictions.</strong> Every feature is available in the self-hosted version. There is no "enterprise edition" with features locked behind a commercial license.</li>
            <li><strong>Fork and modify freely.</strong> If you need to customize LangSight for your organization — add a custom alert channel, change the data model, integrate with an internal tool — you can fork and modify without restriction.</li>
            <li><strong>No contributor license agreement trap.</strong> Some open-source projects use CLAs that allow the company to relicense contributions. Apache 2.0 has clear patent grants and does not require a CLA.</li>
            <li><strong>Sell it if you want.</strong> Apache 2.0 explicitly allows commercial use. You can build a managed service on top of LangSight. You can bundle it with your product. No restrictions.</li>
          </ul>

          <h2>What about offline environments?</h2>
          <p>
            Some organizations operate in air-gapped environments — government, defense, highly regulated finance. These environments cannot connect to any external service, including for CVE lookups.
          </p>
          <p>
            LangSight supports fully offline operation. The CVE database can be bundled locally (updated via a manual process). Health monitoring, schema drift detection, loop detection, and budget enforcement all work without any external network access. The only feature that requires external connectivity is the optional CVE database update from OSV — and even this can be disabled or routed through a controlled proxy.
          </p>

          <h2>Key takeaways</h2>
          <ul>
            <li><strong>Agent traces are the most sensitive data in your stack.</strong> They contain user PII, internal APIs, database schemas, and proprietary business logic. Treat them accordingly.</li>
            <li><strong>Self-hosting eliminates data residency and compliance risks.</strong> Your data stays in your VPC, your region, under your access controls.</li>
            <li><strong>$0 vs $2,400/month.</strong> Self-hosted infrastructure costs a fraction of cloud observability pricing at scale. The cost difference grows as your agent fleet grows.</li>
            <li><strong>Apache 2.0 means no restrictions.</strong> No open-core, no enterprise edition, no feature gating. Fork, modify, sell — your choice.</li>
            <li><strong>Five minutes to deploy:</strong> <code>docker compose up -d</code> gives you the full stack. <code>langsight init</code> gives you the CLI with zero infrastructure.</li>
          </ul>

          <h2>Related articles</h2>
          <ul>
            <li><a href="/blog/langsight-vs-langfuse/" style={{ color: "var(--indigo)", textDecoration: "underline" }}>LangSight vs Langfuse</a> — Both tools are self-hostable. See how they complement each other in a production observability stack.</li>
            <li><a href="/blog/mcp-server-security/" style={{ color: "var(--indigo)", textDecoration: "underline" }}>MCP Server Security</a> — Security scanning and audit data should also stay in your network. How to run security audits self-hosted.</li>
            <li><a href="/blog/mcp-monitoring-production/" style={{ color: "var(--indigo)", textDecoration: "underline" }}>How to Monitor MCP Servers in Production</a> — Self-hosted MCP monitoring: zero external dependencies, full fleet visibility.</li>
            <li><a href="/blog/ai-agent-cost-attribution/" style={{ color: "var(--indigo)", textDecoration: "underline" }}>AI Agent Cost Attribution</a> — Self-hosted cost tracking saves you the $2,400/month cloud observability bill.</li>
          </ul>

          <div className="mt-12 p-6 border border-[var(--indigo)]/30 rounded-xl bg-[var(--indigo)]/5">
            <p className="font-semibold text-[var(--indigo)] mb-2">Keep your agent data in your network</p>
            <p className="text-[var(--muted)] text-sm mb-4">
              LangSight is self-hosted, Apache 2.0, and free forever. Full observability for your agent fleet without sending a single trace to a third party.
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
