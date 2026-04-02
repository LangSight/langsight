"use client";

import { useEffect, useRef } from "react";

const posts = [
  {
    slug: "mcp-monitoring-production",
    title: "How to Monitor MCP Servers in Production",
    description:
      "Your agents depend on MCP servers. If one goes down, your agents fail silently. Here is how to set up proactive health monitoring, latency tracking, and uptime alerting for your entire MCP fleet.",
    date: "April 2, 2026",
    readTime: "10 min read",
    tags: ["MCP Monitoring", "Health Checks", "Production"],
    image: "/blog/mcp-monitoring-production.svg",
  },
  {
    slug: "owasp-mcp-top-10-guide",
    title: "OWASP MCP Top 10 Explained: A Practical Security Guide",
    description:
      "8,000+ MCP servers exposed without auth. 66% with critical code smells. Walk through all 10 risks with severity, real examples, detection, and remediation.",
    date: "April 2, 2026",
    readTime: "12 min read",
    tags: ["OWASP", "MCP Security", "Compliance"],
    image: "/blog/owasp-mcp-top-10-guide.svg",
  },
  {
    slug: "mcp-tool-poisoning",
    title: "MCP Tool Poisoning: How Attackers Hijack AI Agents Through Tool Descriptions",
    description:
      "A community MCP server's tool description contained hidden instructions that caused agents to exfiltrate data. Three attack patterns, detection, and defense.",
    date: "April 2, 2026",
    readTime: "9 min read",
    tags: ["Tool Poisoning", "Security", "Attack Vectors"],
    image: "/blog/mcp-tool-poisoning.svg",
  },
  {
    slug: "ai-agent-cost-attribution",
    title: "AI Agent Cost Attribution: Tracking Spend Per Tool Call",
    description:
      "A sub-agent retried geocoding-mcp endlessly. $1,800 per week. No budget limit. How to attribute costs to specific tools, agents, and sessions.",
    date: "April 2, 2026",
    readTime: "8 min read",
    tags: ["Cost Tracking", "Budget", "Production"],
    image: "/blog/ai-agent-cost-attribution.svg",
  },
  {
    slug: "mcp-schema-drift",
    title: "Schema Drift in MCP: The Silent Failure Your Agents Cannot Detect",
    description:
      "A field was renamed in a community MCP server update. Agents kept calling, got empty results, hallucinated downstream. Nobody noticed for 3 days.",
    date: "April 2, 2026",
    readTime: "8 min read",
    tags: ["Schema Drift", "MCP Health", "Silent Failures"],
    image: "/blog/mcp-schema-drift.svg",
  },
  {
    slug: "circuit-breakers-ai-agents",
    title: "Circuit Breakers for AI Agents: Preventing Cascading Failures",
    description:
      "postgres-mcp goes down. 3 agents depend on it. All sessions fail. How circuit breakers stop cascading failures in multi-agent systems.",
    date: "April 2, 2026",
    readTime: "9 min read",
    tags: ["Circuit Breaker", "Reliability", "Fault Tolerance"],
    image: "/blog/circuit-breakers-ai-agents.svg",
  },
  {
    slug: "langsight-vs-langfuse",
    title: "LangSight vs Langfuse: Different Tools for Different Problems",
    description:
      "Should you use LangSight or Langfuse? The answer: use both. They solve fundamentally different problems in your agent stack.",
    date: "April 2, 2026",
    readTime: "7 min read",
    tags: ["Comparison", "Langfuse", "Observability"],
    image: "/blog/langsight-vs-langfuse.svg",
  },
  {
    slug: "self-hosting-ai-observability",
    title: "Self-Hosting AI Observability: Why Your Data Should Never Leave",
    description:
      "Every tool call your agent makes flowing to a third-party SaaS. Including customer data, internal APIs, database queries. There is a better way.",
    date: "April 2, 2026",
    readTime: "7 min read",
    tags: ["Self-Hosted", "Data Privacy", "Open Source"],
    image: "/blog/self-hosting-ai-observability.svg",
  },
  {
    slug: "blast-radius-mapping",
    title: "Blast Radius Mapping: Understanding AI Agent Dependencies",
    description:
      "slack-mcp goes down. How many agents are affected? Which sessions will fail? Without dependency mapping, you have no idea.",
    date: "April 2, 2026",
    readTime: "8 min read",
    tags: ["Blast Radius", "Dependencies", "Reliability"],
    image: "/blog/blast-radius-mapping.svg",
  },
  {
    slug: "slos-for-ai-agents",
    title: "Setting SLOs for AI Agents: A Practical Guide",
    description:
      "Your VP asks what the reliability of your AI products is. You have no number to give. Here is how to define, measure, and enforce SLOs for non-deterministic agents.",
    date: "April 2, 2026",
    readTime: "9 min read",
    tags: ["SLOs", "Reliability Engineering", "Monitoring"],
    image: "/blog/slos-for-ai-agents.svg",
  },
  {
    slug: "ai-agent-loop-detection",
    title: "How to Detect and Stop AI Agent Loops in Production",
    description:
      "AI agent loops are the most common production failure: the same tool called 47 times, $200 burned, nothing produced. Learn how loop detection works and how to stop it automatically.",
    date: "March 22, 2026",
    readTime: "8 min read",
    tags: ["Loop Detection", "Agent Reliability", "Production"],
    image: "/blog/ai-agent-loop-detection.svg",
  },
  {
    slug: "mcp-server-security",
    title: "MCP Server Security: OWASP Top 10 for Model Context Protocol",
    description:
      "66% of community MCP servers have at least one critical security issue. Learn the OWASP MCP Top 10, tool poisoning attacks, and how to audit your MCP servers.",
    date: "March 22, 2026",
    readTime: "10 min read",
    tags: ["MCP Security", "OWASP", "CVE"],
    image: "/blog/mcp-server-security.svg",
  },
];

export default function BlogIndex() {
  const gridRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("visible");
          }
        });
      },
      { threshold: 0.08, rootMargin: "0px 0px -40px 0px" }
    );

    const els = gridRef.current?.querySelectorAll("[data-reveal]");
    els?.forEach((el) => observer.observe(el));

    return () => observer.disconnect();
  }, []);

  const featured = posts[0];
  const rest = posts.slice(1);

  return (
    <main className="min-h-screen bg-[var(--bg)] text-[var(--fg)]">
      {/* Nav */}
      <header className="sticky top-0 z-50 border-b border-[var(--border)] bg-[var(--bg)]/90 backdrop-blur-sm">
        <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
          <a href="/" className="flex items-center gap-2 font-semibold text-[var(--fg)]">
            <img src="/logo-icon.svg" alt="LangSight" className="w-7 h-7" />
            LangSight
          </a>
          <a href="/" className="text-sm text-[var(--muted)] hover:text-[var(--fg)] transition-colors">
            ← Back to home
          </a>
        </div>
      </header>

      <div ref={gridRef} className="max-w-6xl mx-auto px-6 py-16">
        {/* Hero Section */}
        <div className="mb-14" data-reveal>
          <p className="section-label mb-3">Engineering Blog</p>
          <h1 className="text-4xl sm:text-5xl font-bold tracking-tight mb-4">Blog</h1>
          <p className="text-lg text-[var(--muted)] max-w-2xl leading-relaxed">
            Practical guides on AI agent reliability, MCP security, cost attribution, and production toolchains. Written by engineers, for engineers.
          </p>
        </div>

        {/* Featured Post */}
        <a
          href={`/blog/${featured.slug}/`}
          className="group block mb-12 cursor-pointer"
          data-reveal
        >
          <div className="rounded-2xl border border-[var(--border)] overflow-hidden transition-all duration-200 hover:border-[var(--indigo)] hover:shadow-[0_0_0_1px_var(--indigo-dim),0_8px_40px_var(--indigo-glow)] hover:-translate-y-0.5">
            <div className="grid lg:grid-cols-5">
              {/* Image Area */}
              <div className="lg:col-span-3 relative overflow-hidden bg-[#0A0A0C]">
                <img
                  src={featured.image}
                  alt={featured.title}
                  className="w-full h-full object-cover"
                  style={{ aspectRatio: "1200/630", minHeight: "220px" }}
                />
                <div className="absolute bottom-4 left-5">
                  <span className="text-xs font-medium px-2.5 py-1 rounded-full bg-white/15 text-white/90 backdrop-blur-sm">
                    Featured
                  </span>
                </div>
              </div>

              {/* Content Area */}
              <div className="lg:col-span-2 p-7 sm:p-9 flex flex-col justify-center bg-[var(--surface)]">
                <div className="flex flex-wrap gap-2 mb-4">
                  {featured.tags.map((tag) => (
                    <span
                      key={tag}
                      className="text-[10px] px-2 py-0.5 rounded-full border border-[var(--border)] text-[var(--muted)] font-medium"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
                <p className="text-xs text-[var(--muted)] mb-3 font-mono">
                  LangSight Engineering · {featured.date}
                </p>
                <h2 className="text-xl sm:text-2xl font-bold mb-3 group-hover:text-[var(--indigo)] transition-colors leading-tight">
                  {featured.title}
                </h2>
                <p className="text-[var(--muted)] text-sm leading-relaxed mb-4 line-clamp-3">
                  {featured.description}
                </p>
                <div className="flex items-center gap-3 text-xs text-[var(--muted)]">
                  <span>{featured.readTime}</span>
                  <span className="text-[var(--indigo)] font-medium group-hover:underline">
                    Read article →
                  </span>
                </div>
              </div>
            </div>
          </div>
        </a>

        {/* Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {rest.map((post, i) => (
            <a
              key={post.slug}
              href={`/blog/${post.slug}/`}
              className="group block cursor-pointer"
              data-reveal
              style={{ transitionDelay: `${i * 60}ms` }}
            >
              <div className="rounded-xl border border-[var(--border)] overflow-hidden h-full flex flex-col transition-all duration-200 hover:border-[var(--indigo)] hover:shadow-[0_0_0_1px_var(--indigo-dim),0_8px_40px_var(--indigo-glow)] hover:-translate-y-0.5 bg-[var(--surface)]">
                {/* Hero Image */}
                <div className="relative overflow-hidden flex-shrink-0 bg-[#0A0A0C]" style={{ aspectRatio: "1200/630" }}>
                  <img
                    src={post.image}
                    alt={post.title}
                    className="w-full h-full object-cover"
                  />
                </div>

                {/* Content */}
                <div className="p-5 flex flex-col flex-1">
                  <p className="text-[10px] text-[var(--dimmer)] mb-2.5 font-mono">
                    LangSight Engineering · {post.date}
                  </p>
                  <h3 className="text-[0.95rem] font-bold leading-snug mb-2 group-hover:text-[var(--indigo)] transition-colors line-clamp-2">
                    {post.title}
                  </h3>
                  <p className="text-xs text-[var(--muted)] leading-relaxed mb-4 line-clamp-2 flex-1">
                    {post.description}
                  </p>
                  <div className="flex flex-wrap gap-1.5 mt-auto">
                    {post.tags.map((tag) => (
                      <span
                        key={tag}
                        className="text-[10px] px-2 py-0.5 rounded-full border border-[var(--border)] text-[var(--dimmer)] font-medium"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </a>
          ))}
        </div>

        {/* Bottom CTA */}
        <div className="mt-16 text-center" data-reveal>
          <p className="text-[var(--muted)] text-sm mb-4">
            Building agents in production? LangSight adds reliability, security, and cost controls in two lines of code.
          </p>
          <a
            href="/"
            className="inline-block text-sm font-medium px-5 py-2.5 rounded-lg bg-[var(--indigo)] text-white hover:opacity-90 transition-opacity"
          >
            Get started free →
          </a>
        </div>
      </div>

      <style>{`
        .line-clamp-2 {
          display: -webkit-box;
          -webkit-line-clamp: 2;
          -webkit-box-orient: vertical;
          overflow: hidden;
        }
        .line-clamp-3 {
          display: -webkit-box;
          -webkit-line-clamp: 3;
          -webkit-box-orient: vertical;
          overflow: hidden;
        }
      `}</style>
    </main>
  );
}
