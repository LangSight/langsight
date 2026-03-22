"use client";

const posts = [
  {
    slug: "ai-agent-loop-detection",
    title: "How to Detect and Stop AI Agent Loops in Production",
    description:
      "AI agent loops are the most common production failure: the same tool called 47 times, $200 burned, nothing produced. Learn how loop detection works and how to stop it automatically.",
    date: "March 22, 2026",
    readTime: "8 min read",
    tags: ["Loop Detection", "Agent Reliability", "Production"],
  },
  {
    slug: "mcp-server-security",
    title: "MCP Server Security: OWASP Top 10 for Model Context Protocol",
    description:
      "66% of community MCP servers have critical security issues. Learn the OWASP MCP Top 10, tool poisoning attacks, and how to audit your MCP servers before they compromise your agents.",
    date: "March 22, 2026",
    readTime: "10 min read",
    tags: ["MCP Security", "OWASP", "CVE"],
  },
];

export default function BlogIndex() {
  return (
    <main className="min-h-screen bg-[var(--bg)] text-[var(--fg)]">
      {/* Nav */}
      <header className="sticky top-0 z-50 border-b border-[var(--border)] bg-[var(--bg)]/90 backdrop-blur-sm">
        <div className="max-w-4xl mx-auto px-6 h-14 flex items-center justify-between">
          <a href="/" className="flex items-center gap-2 font-semibold text-[var(--fg)]">
            <img src="/logo-icon.svg" alt="LangSight" className="w-7 h-7" />
            LangSight
          </a>
          <a href="/" className="text-sm text-[var(--muted)] hover:text-[var(--fg)] transition-colors">
            ← Back to home
          </a>
        </div>
      </header>

      <div className="max-w-4xl mx-auto px-6 py-16">
        <div className="mb-12">
          <h1 className="text-4xl font-bold mb-4">Blog</h1>
          <p className="text-lg text-[var(--muted)]">
            Practical guides on AI agent reliability, MCP security, and production toolchains.
          </p>
        </div>

        <div className="grid gap-8">
          {posts.map((post) => (
            <a
              key={post.slug}
              href={`/blog/${post.slug}/`}
              className="group block border border-[var(--border)] rounded-xl p-8 hover:border-[var(--indigo)] transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg"
            >
              <div className="flex flex-wrap gap-2 mb-4">
                {post.tags.map((tag) => (
                  <span
                    key={tag}
                    className="text-xs px-2 py-0.5 rounded-full bg-[var(--indigo)]/10 text-[var(--indigo)] font-medium"
                  >
                    {tag}
                  </span>
                ))}
              </div>
              <h2 className="text-xl font-bold mb-3 group-hover:text-[var(--indigo)] transition-colors">
                {post.title}
              </h2>
              <p className="text-[var(--muted)] mb-4 leading-relaxed">{post.description}</p>
              <div className="flex items-center gap-4 text-sm text-[var(--muted)]">
                <span>{post.date}</span>
                <span>·</span>
                <span>{post.readTime}</span>
              </div>
            </a>
          ))}
        </div>
      </div>
    </main>
  );
}
