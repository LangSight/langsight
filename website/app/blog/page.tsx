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
    gradient: "linear-gradient(135deg, #0c4a6e 0%, #0891b2 40%, #22d3ee 100%)",
    pattern: "radial-gradient(circle at 75% 25%, rgba(255,255,255,0.08) 0%, transparent 50%), radial-gradient(circle at 20% 80%, rgba(255,255,255,0.05) 0%, transparent 40%)",
  },
  {
    slug: "owasp-mcp-top-10-guide",
    title: "OWASP MCP Top 10 Explained: A Practical Security Guide",
    description:
      "8,000+ MCP servers exposed without auth. 66% with critical code smells. Walk through all 10 risks with severity, real examples, detection, and remediation.",
    date: "April 2, 2026",
    readTime: "12 min read",
    tags: ["OWASP", "MCP Security", "Compliance"],
    gradient: "linear-gradient(135deg, #7f1d1d 0%, #dc2626 50%, #f97316 100%)",
    pattern: "repeating-linear-gradient(45deg, transparent, transparent 10px, rgba(255,255,255,0.03) 10px, rgba(255,255,255,0.03) 20px)",
  },
  {
    slug: "mcp-tool-poisoning",
    title: "MCP Tool Poisoning: How Attackers Hijack AI Agents Through Tool Descriptions",
    description:
      "A community MCP server's tool description contained hidden instructions that caused agents to exfiltrate data. Three attack patterns, detection, and defense.",
    date: "April 2, 2026",
    readTime: "9 min read",
    tags: ["Tool Poisoning", "Security", "Attack Vectors"],
    gradient: "linear-gradient(135deg, #4c0519 0%, #be123c 50%, #fb7185 100%)",
    pattern: "radial-gradient(ellipse at 30% 70%, rgba(255,255,255,0.06) 0%, transparent 60%), linear-gradient(180deg, transparent 40%, rgba(0,0,0,0.2) 100%)",
  },
  {
    slug: "ai-agent-cost-attribution",
    title: "AI Agent Cost Attribution: Tracking Spend Per Tool Call",
    description:
      "A sub-agent retried geocoding-mcp endlessly. $1,800 per week. No budget limit. How to attribute costs to specific tools, agents, and sessions.",
    date: "April 2, 2026",
    readTime: "8 min read",
    tags: ["Cost Tracking", "Budget", "Production"],
    gradient: "linear-gradient(135deg, #064e3b 0%, #059669 50%, #34d399 100%)",
    pattern: "radial-gradient(circle at 80% 20%, rgba(255,255,255,0.07) 0%, transparent 45%), radial-gradient(circle at 10% 90%, rgba(255,255,255,0.04) 0%, transparent 40%)",
  },
  {
    slug: "mcp-schema-drift",
    title: "Schema Drift in MCP: The Silent Failure Your Agents Cannot Detect",
    description:
      "A field was renamed in a community MCP server update. Agents kept calling, got empty results, hallucinated downstream. Nobody noticed for 3 days.",
    date: "April 2, 2026",
    readTime: "8 min read",
    tags: ["Schema Drift", "MCP Health", "Silent Failures"],
    gradient: "linear-gradient(135deg, #78350f 0%, #d97706 50%, #fbbf24 100%)",
    pattern: "repeating-linear-gradient(-45deg, transparent, transparent 8px, rgba(255,255,255,0.04) 8px, rgba(255,255,255,0.04) 16px)",
  },
  {
    slug: "circuit-breakers-ai-agents",
    title: "Circuit Breakers for AI Agents: Preventing Cascading Failures",
    description:
      "postgres-mcp goes down. 3 agents depend on it. All sessions fail. How circuit breakers stop cascading failures in multi-agent systems.",
    date: "April 2, 2026",
    readTime: "9 min read",
    tags: ["Circuit Breaker", "Reliability", "Fault Tolerance"],
    gradient: "linear-gradient(135deg, #2e1065 0%, #7c3aed 50%, #a78bfa 100%)",
    pattern: "radial-gradient(circle at 60% 40%, rgba(255,255,255,0.06) 0%, transparent 50%), radial-gradient(circle at 90% 90%, rgba(255,255,255,0.03) 0%, transparent 30%)",
  },
  {
    slug: "langsight-vs-langfuse",
    title: "LangSight vs Langfuse: Different Tools for Different Problems",
    description:
      "Should you use LangSight or Langfuse? The answer: use both. They solve fundamentally different problems in your agent stack.",
    date: "April 2, 2026",
    readTime: "7 min read",
    tags: ["Comparison", "Langfuse", "Observability"],
    gradient: "linear-gradient(135deg, #1e1b4b 0%, #4f46e5 50%, #818cf8 100%)",
    pattern: "radial-gradient(circle at 50% 50%, rgba(255,255,255,0.05) 0%, transparent 60%)",
  },
  {
    slug: "self-hosting-ai-observability",
    title: "Self-Hosting AI Observability: Why Your Data Should Never Leave",
    description:
      "Every tool call your agent makes flowing to a third-party SaaS. Including customer data, internal APIs, database queries. There is a better way.",
    date: "April 2, 2026",
    readTime: "7 min read",
    tags: ["Self-Hosted", "Data Privacy", "Open Source"],
    gradient: "linear-gradient(135deg, #134e4a 0%, #0d9488 50%, #5eead4 100%)",
    pattern: "radial-gradient(circle at 25% 75%, rgba(255,255,255,0.06) 0%, transparent 50%), radial-gradient(circle at 85% 15%, rgba(255,255,255,0.04) 0%, transparent 35%)",
  },
  {
    slug: "blast-radius-mapping",
    title: "Blast Radius Mapping: Understanding AI Agent Dependencies",
    description:
      "slack-mcp goes down. How many agents are affected? Which sessions will fail? Without dependency mapping, you have no idea.",
    date: "April 2, 2026",
    readTime: "8 min read",
    tags: ["Blast Radius", "Dependencies", "Reliability"],
    gradient: "linear-gradient(135deg, #7c2d12 0%, #ea580c 50%, #fdba74 100%)",
    pattern: "repeating-linear-gradient(60deg, transparent, transparent 12px, rgba(255,255,255,0.03) 12px, rgba(255,255,255,0.03) 24px)",
  },
  {
    slug: "slos-for-ai-agents",
    title: "Setting SLOs for AI Agents: A Practical Guide",
    description:
      "Your VP asks what the reliability of your AI products is. You have no number to give. Here is how to define, measure, and enforce SLOs for non-deterministic agents.",
    date: "April 2, 2026",
    readTime: "9 min read",
    tags: ["SLOs", "Reliability Engineering", "Monitoring"],
    gradient: "linear-gradient(135deg, #701a75 0%, #d946ef 50%, #f0abfc 100%)",
    pattern: "radial-gradient(circle at 70% 30%, rgba(255,255,255,0.07) 0%, transparent 45%), radial-gradient(circle at 15% 85%, rgba(255,255,255,0.04) 0%, transparent 40%)",
  },
  {
    slug: "ai-agent-loop-detection",
    title: "How to Detect and Stop AI Agent Loops in Production",
    description:
      "AI agent loops are the most common production failure: the same tool called 47 times, $200 burned, nothing produced. Learn how loop detection works and how to stop it automatically.",
    date: "March 22, 2026",
    readTime: "8 min read",
    tags: ["Loop Detection", "Agent Reliability", "Production"],
    gradient: "linear-gradient(135deg, #172554 0%, #2563eb 50%, #60a5fa 100%)",
    pattern: "radial-gradient(circle at 40% 60%, rgba(255,255,255,0.06) 0%, transparent 50%)",
  },
  {
    slug: "mcp-server-security",
    title: "MCP Server Security: OWASP Top 10 for Model Context Protocol",
    description:
      "66% of community MCP servers have at least one critical security issue. Learn the OWASP MCP Top 10, tool poisoning attacks, and how to audit your MCP servers.",
    date: "March 22, 2026",
    readTime: "10 min read",
    tags: ["MCP Security", "OWASP", "CVE"],
    gradient: "linear-gradient(135deg, #450a0a 0%, #b91c1c 50%, #f87171 100%)",
    pattern: "repeating-linear-gradient(135deg, transparent, transparent 14px, rgba(255,255,255,0.02) 14px, rgba(255,255,255,0.02) 28px)",
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
              {/* Gradient Area */}
              <div
                className="lg:col-span-3 h-56 sm:h-64 lg:h-auto lg:min-h-[320px] relative overflow-hidden"
                style={{ background: featured.gradient }}
              >
                <div
                  className="absolute inset-0"
                  style={{ background: featured.pattern }}
                />
                {/* Abstract decoration */}
                <div className="absolute inset-0 flex items-center justify-center opacity-[0.12]">
                  <svg width="320" height="320" viewBox="0 0 320 320" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <circle cx="160" cy="160" r="120" stroke="white" strokeWidth="1" />
                    <circle cx="160" cy="160" r="80" stroke="white" strokeWidth="1" />
                    <circle cx="160" cy="160" r="40" stroke="white" strokeWidth="1" />
                    <line x1="40" y1="160" x2="280" y2="160" stroke="white" strokeWidth="0.5" />
                    <line x1="160" y1="40" x2="160" y2="280" stroke="white" strokeWidth="0.5" />
                  </svg>
                </div>
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
                {/* Gradient Hero */}
                <div
                  className="h-40 relative overflow-hidden flex-shrink-0"
                  style={{ background: post.gradient }}
                >
                  <div
                    className="absolute inset-0"
                    style={{ background: post.pattern }}
                  />
                  {/* Subtle geometric overlay unique per card */}
                  <div className="absolute inset-0 flex items-center justify-center opacity-[0.08]">
                    <svg width="200" height="160" viewBox="0 0 200 160" fill="none" xmlns="http://www.w3.org/2000/svg">
                      <rect x="50" y="30" width="100" height="100" rx="4" stroke="white" strokeWidth="0.5" />
                      <rect x="70" y="50" width="60" height="60" rx="2" stroke="white" strokeWidth="0.5" />
                    </svg>
                  </div>
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
