"use client";

import { useEffect, useState } from "react";

/* ── Theme ──────────────────────────────────────────────────── */
function useTheme() {
  const [dark, setDark] = useState(true);
  useEffect(() => {
    const saved = localStorage.getItem("ls-theme");
    setDark(saved ? saved === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches);
  }, []);
  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    localStorage.setItem("ls-theme", dark ? "dark" : "light");
  }, [dark]);
  return { dark, toggle: () => setDark((d) => !d) };
}

function useScrollReveal() {
  useEffect(() => {
    const obs = new IntersectionObserver(
      (entries) => entries.forEach((e) => e.isIntersecting && e.target.classList.add("visible")),
      { threshold: 0.07 }
    );
    document.querySelectorAll("[data-reveal]").forEach((el) => obs.observe(el));
    return () => obs.disconnect();
  }, []);
}

function GithubIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
    </svg>
  );
}

function Logo() {
  return (
    <a href="/" className="flex items-center gap-2.5 shrink-0">
      <div className="w-7 h-7 rounded-lg flex items-center justify-center" style={{ background: "var(--indigo)" }}>
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
          <path d="M2 7h10M7 2v10M4 4l6 6M10 4l-6 6" stroke="white" strokeWidth="1.6" strokeLinecap="round" />
        </svg>
      </div>
      <span className="font-bold text-lg tracking-tight" style={{ fontFamily: "var(--font-geist-sans)", color: "var(--text)" }}>
        LangSight
      </span>
    </a>
  );
}

function Nav({ dark, toggle }: { dark: boolean; toggle: () => void }) {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const h = () => setScrolled(window.scrollY > 24);
    window.addEventListener("scroll", h);
    return () => window.removeEventListener("scroll", h);
  }, []);
  return (
    <nav
      className="fixed top-0 left-0 right-0 z-50 transition-all duration-300"
      style={{
        background: scrolled ? "color-mix(in srgb, var(--bg) 88%, transparent)" : "transparent",
        backdropFilter: scrolled ? "blur(16px)" : "none",
        borderBottom: scrolled ? "1px solid var(--border)" : "1px solid transparent",
      }}
    >
      <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between gap-6">
        <Logo />
        <div className="hidden md:flex items-center gap-1">
          {[
            { label: "Home", href: "/" },
            { label: "Security", href: "/security" },
            { label: "Pricing", href: "/pricing" },
            { label: "Docs", href: "https://docs.langsight.dev" },
            { label: "GitHub", href: "https://github.com/LangSight/langsight" },
          ].map((l) => (
            <a key={l.label} href={l.href}
              className="px-3 py-1.5 rounded-md text-sm transition-colors"
              style={{ color: l.label === "Pricing" ? "var(--indigo)" : "var(--muted)" }}>
              {l.label}
            </a>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <button onClick={toggle} aria-label="Toggle theme"
            className="w-9 h-9 rounded-lg flex items-center justify-center"
            style={{ background: "var(--surface-2)", border: "1px solid var(--border)", color: "var(--muted)" }}>
            {dark
              ? <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>
              : <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24"><path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/></svg>
            }
          </button>
          <a href="https://docs.langsight.dev/quickstart"
            className="hidden sm:flex items-center gap-1.5 text-sm font-semibold px-4 py-2 rounded-lg transition-all hover:opacity-90"
            style={{ background: "var(--indigo)", color: "white" }}>
            Get started →
          </a>
        </div>
      </div>
    </nav>
  );
}

/* ── Feature list ───────────────────────────────────────────── */
const ALL_FEATURES = [
  { category: "Agent Runtime Reliability", items: ["Full session traces — every tool call", "Multi-agent call tree reconstruction", "Payload capture (input args + output)", "Session replay against live MCP servers", "Side-by-side session comparison", "LLM reasoning traces (llm_input / llm_output)", "Anomaly detection (z-score vs 7-day baseline)", "Agent SLO tracking (success_rate, latency_p99)"] },
  { category: "MCP Health Monitoring", items: ["Continuous proactive health checks", "Schema drift detection", "Latency tracking and p99 trends", "Slack + webhook alerts on DOWN/recovery", "Multi-transport: stdio, SSE, StreamableHTTP"] },
  { category: "MCP Security Scanning", items: ["CVE detection against public database", "5 of 10 OWASP MCP checks (MCP-01, 02, 04, 05, 06 — more coming)", "Tool poisoning detection (injection, unicode, base64)", "Auth gap analysis", "CI/CD integration with --ci flag", "JSON output for SIEM integration"] },
  { category: "Cost Attribution", items: ["Token-based pricing for LLM calls", "Per-tool call-based pricing rules", "Cost per session / per agent / per tool", "Model pricing table (admin-managed)", "Historical cost trends"] },
  { category: "Infrastructure", items: ["PostgreSQL for metadata (users, projects, API keys, SLOs)", "ClickHouse for analytics (spans, traces, costs, health)", "Dual-storage architecture — routes each operation to the right backend", "Docker Compose for self-hosted deployment", "Alembic migrations for schema management"] },
  { category: "Teams & Access", items: ["Multi-user with invite-based signup", "Project-level RBAC (owner / member / viewer)", "API key auth with role scopes", "Global admin + per-project roles", "Audit trail for auth events"] },
];

/* ── FAQ ────────────────────────────────────────────────────── */
const FAQ = [
  {
    q: "Is it really free? What's the catch?",
    a: "There is no catch. LangSight is Apache 2.0 open source. You can self-host it for free, forever, for any use including commercial. We do not have a paid tier today.",
  },
  {
    q: "Is there a cloud-hosted version?",
    a: "Not yet. We're working on a cloud-hosted option for teams who don't want to manage infrastructure. Join the waitlist below to be notified when it's available.",
  },
  {
    q: "What infrastructure do I need to self-host?",
    a: "LangSight requires Docker. Copy .env.example to .env, fill in the required passwords, then run docker compose up -d. PostgreSQL (metadata) and ClickHouse (analytics) both start automatically. The full stack is up in under 5 minutes.",
  },
  {
    q: "Does my data leave my network?",
    a: "No. LangSight is entirely self-hosted. Your agent traces, tool call payloads, and cost data never leave your infrastructure. The only outbound requests are CVE database lookups during security scans, which you can disable.",
  },
  {
    q: "What happens when a cloud tier launches?",
    a: "The self-hosted version will always remain Apache 2.0 and fully featured. Any cloud tier will be additive — managed hosting, support SLAs, enterprise SSO. We will never move existing features to a paid tier.",
  },
  {
    q: "How do I get support?",
    a: "GitHub Issues for bugs and feature requests. GitHub Discussions for questions. We respond to all issues. For production deployments, docs.langsight.dev covers every deployment scenario.",
  },
];

function FAQItem({ q, a }: { q: string; a: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div
      className="card-flat overflow-hidden"
      style={{ borderColor: open ? "var(--indigo)" : undefined }}
    >
      <button
        className="w-full px-6 py-4 flex items-center justify-between gap-4 text-left"
        onClick={() => setOpen((o) => !o)}
      >
        <span className="font-medium text-sm" style={{ color: "var(--text)", fontFamily: "var(--font-geist-sans)" }}>
          {q}
        </span>
        <span
          className="shrink-0 w-5 h-5 rounded-full flex items-center justify-center transition-transform"
          style={{
            background: open ? "var(--indigo)" : "var(--surface-2)",
            color: open ? "white" : "var(--muted)",
            transform: open ? "rotate(45deg)" : "rotate(0deg)",
          }}
        >
          <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
            <path d="M5 1v8M1 5h8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
        </span>
      </button>
      {open && (
        <div className="px-6 pb-4 text-sm leading-relaxed" style={{ color: "var(--muted)" }}>
          {a}
        </div>
      )}
    </div>
  );
}

/* ── Page ───────────────────────────────────────────────────── */
export default function PricingPage() {
  const { dark, toggle } = useTheme();
  useScrollReveal();

  return (
    <>
      <Nav dark={dark} toggle={toggle} />
      <main>

        {/* Hero */}
        <section className="relative pt-32 pb-20 grid-bg overflow-hidden">
          <div className="absolute inset-0 pointer-events-none">
            <div
              className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[400px] rounded-full blur-[150px]"
              style={{ background: "var(--indigo-glow)" }}
            />
          </div>
          <div className="relative max-w-4xl mx-auto px-6 text-center">
            <div
              className="fade-up inline-flex items-center gap-2 rounded-full px-4 py-1.5 text-xs font-medium mb-6"
              style={{ background: "var(--green-dim)", border: "1px solid rgba(34,197,94,0.2)", color: "var(--green)" }}
            >
              <span className="w-1.5 h-1.5 rounded-full" style={{ background: "var(--green)" }} />
              No credit card · No account · No usage limits
            </div>

            <h1
              className="fade-up delay-1 font-bold tracking-tight mb-6"
              style={{ fontSize: "clamp(2.2rem, 5vw, 3.5rem)", fontFamily: "var(--font-geist-sans)" }}
            >
              <span className="gradient-text">Free.</span>
              <br />
              <span className="gradient-indigo">Forever.</span>
              <br />
              <span className="gradient-text">No asterisk.</span>
            </h1>

            <p
              className="fade-up delay-2 text-lg leading-relaxed max-w-xl mx-auto mb-10"
              style={{ color: "var(--muted)" }}
            >
              LangSight is Apache 2.0 open source. Self-host the entire platform —
              CLI, SDK, API, dashboard, and every feature — at no cost. Not &ldquo;open core&rdquo;.
              Not a free tier. Just free.
            </p>

            <div className="fade-up delay-3 flex flex-wrap justify-center gap-3 mb-6">
              <a
                href="https://docs.langsight.dev/quickstart"
                className="text-sm font-semibold px-5 py-2.5 rounded-lg transition-all hover:opacity-90 hover:-translate-y-px"
                style={{ background: "var(--indigo)", color: "white" }}
              >
                Get started free →
              </a>
              <a
                href="https://github.com/LangSight/langsight"
                className="text-sm font-semibold px-5 py-2.5 rounded-lg flex items-center gap-2 transition-all hover:-translate-y-px"
                style={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text)" }}
              >
                <GithubIcon className="w-4 h-4" /> Star on GitHub
              </a>
            </div>

            <div
              className="fade-up delay-4 inline-flex items-center gap-3 rounded-xl px-4 py-2.5"
              style={{ background: "var(--surface-2)", border: "1px solid var(--border)" }}
            >
              <span style={{ fontFamily: "var(--font-geist-mono)", fontSize: "0.8rem", color: "var(--dimmer)" }}>$</span>
              <span style={{ fontFamily: "var(--font-geist-mono)", fontSize: "0.8rem", color: "var(--code-text)" }}>
                pip install langsight &amp;&amp; langsight init
              </span>
            </div>
          </div>
        </section>

        {/* Tier cards */}
        <section className="py-20" style={{ background: "var(--bg-deep)" }}>
          <div className="max-w-5xl mx-auto px-6">
            <div className="grid md:grid-cols-2 gap-6">

              {/* Open Source tier */}
              <div data-reveal className="card p-8 relative overflow-hidden">
                <div
                  className="absolute inset-0 pointer-events-none"
                  style={{ background: "linear-gradient(135deg, var(--indigo-dim) 0%, transparent 60%)" }}
                />
                <div className="relative">
                  <div className="flex items-start justify-between mb-6">
                    <div>
                      <p className="section-label mb-1">Self-hosted</p>
                      <h3
                        className="font-bold text-2xl"
                        style={{ color: "var(--text)", fontFamily: "var(--font-geist-sans)" }}
                      >
                        Open Source
                      </h3>
                    </div>
                    <div
                      className="text-xs px-2.5 py-1 rounded-full font-semibold"
                      style={{ background: "var(--green-dim)", color: "var(--green)", border: "1px solid rgba(34,197,94,0.2)" }}
                    >
                      Free forever
                    </div>
                  </div>

                  <div className="mb-6">
                    <span
                      className="font-bold"
                      style={{ fontSize: "3rem", fontFamily: "var(--font-geist-sans)", color: "var(--text)", lineHeight: 1 }}
                    >
                      $0
                    </span>
                    <span className="text-sm ml-2" style={{ color: "var(--muted)" }}>forever · Apache 2.0</span>
                  </div>

                  <a
                    href="https://docs.langsight.dev/quickstart"
                    className="block w-full text-center text-sm font-semibold px-5 py-2.5 rounded-lg mb-6 transition-all hover:opacity-90"
                    style={{ background: "var(--indigo)", color: "white" }}
                  >
                    Get started →
                  </a>

                  <div className="space-y-2.5">
                    {[
                      "Unlimited agents, sessions, tool calls",
                      "Unlimited team members",
                      "Unlimited projects with RBAC",
                      "All CLI commands",
                      "Full REST API + dashboard",
                      "PostgreSQL + ClickHouse (dual-backend)",
                      "MCP health monitoring",
                      "Prevention guardrails (loop detection, budget limits, circuit breaker)",
                      "Per-agent override config from dashboard",
                      "Security scanning (OWASP + CVE)",
                      "Cost attribution + model pricing",
                      "Session replay + comparison",
                      "Anomaly detection + SLO tracking",
                      "AI root cause analysis (bring your key)",
                      "Self-hosted — your data, your infra",
                      "Apache 2.0 — fork, modify, sell freely",
                    ].map((f, i) => (
                      <div key={i} className="flex items-center gap-2 text-sm">
                        <span style={{ color: "var(--green)" }}>✓</span>
                        <span style={{ color: "var(--muted)" }}>{f}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* Cloud tier (coming soon) */}
              <div data-reveal className="card-flat p-8 relative" style={{ transitionDelay: "80ms" }}>
                <div className="flex items-start justify-between mb-6">
                  <div>
                    <p className="section-label mb-1">Managed cloud</p>
                    <h3
                      className="font-bold text-2xl"
                      style={{ color: "var(--text)", fontFamily: "var(--font-geist-sans)" }}
                    >
                      Cloud
                    </h3>
                  </div>
                  <div
                    className="text-xs px-2.5 py-1 rounded-full font-semibold"
                    style={{ background: "var(--indigo-dim)", color: "var(--indigo)", border: "1px solid rgba(99,102,241,0.2)" }}
                  >
                    Coming soon
                  </div>
                </div>

                <div className="mb-6">
                  <span
                    className="font-bold"
                    style={{ fontSize: "3rem", fontFamily: "var(--font-geist-sans)", color: "var(--dimmer)", lineHeight: 1 }}
                  >
                    TBD
                  </span>
                  <span className="text-sm ml-2" style={{ color: "var(--dimmer)" }}>usage-based pricing</span>
                </div>

                <button
                  disabled
                  className="block w-full text-center text-sm font-semibold px-5 py-2.5 rounded-lg mb-6 cursor-not-allowed"
                  style={{ background: "var(--surface-2)", color: "var(--dimmer)", border: "1px solid var(--border)" }}
                >
                  Join waitlist →
                </button>

                <div className="space-y-2.5">
                  {[
                    "Everything in Open Source",
                    "No infrastructure to manage",
                    "Automatic backups + upgrades",
                    "99.9% uptime SLA",
                    "Enterprise SSO (SAML/OIDC)",
                    "Priority support + SLA",
                    "Dedicated Slack channel",
                    "Custom data retention",
                    "Usage-based — pay only for what you use",
                  ].map((f, i) => (
                    <div key={i} className="flex items-center gap-2 text-sm">
                      <span style={{ color: "var(--dimmer)" }}>○</span>
                      <span style={{ color: "var(--dimmer)" }}>{f}</span>
                    </div>
                  ))}
                </div>

                <div
                  className="mt-6 rounded-lg p-4 text-sm"
                  style={{ background: "var(--indigo-dim)", border: "1px solid rgba(99,102,241,0.15)" }}
                >
                  <p className="font-semibold mb-1" style={{ color: "var(--indigo)" }}>Get notified when cloud launches</p>
                  <p style={{ color: "var(--muted)" }}>
                    Leave a GitHub star and we&apos;ll announce via releases.
                    <a
                      href="https://github.com/LangSight/langsight"
                      className="ml-1 underline"
                      style={{ color: "var(--indigo)" }}
                    >
                      Star on GitHub →
                    </a>
                  </p>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* All features */}
        <section className="py-24">
          <div className="max-w-6xl mx-auto px-6">
            <div className="text-center mb-14" data-reveal>
              <p className="section-label mb-3">Everything included</p>
              <h2
                className="font-bold tracking-tight"
                style={{ fontSize: "clamp(1.5rem, 3vw, 2rem)", fontFamily: "var(--font-geist-sans)" }}
              >
                <span className="gradient-text">No feature gating. Ever.</span>
              </h2>
              <p className="mt-4 max-w-lg mx-auto text-sm" style={{ color: "var(--muted)" }}>
                Every capability listed below is available in the free open-source version.
                We will never move an existing feature to a paid tier.
              </p>
            </div>

            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
              {ALL_FEATURES.map((cat, i) => (
                <div key={i} data-reveal className="card-flat p-6" style={{ transitionDelay: `${i * 60}ms` }}>
                  <h3
                    className="font-semibold text-sm mb-4"
                    style={{ color: "var(--indigo)", fontFamily: "var(--font-geist-sans)" }}
                  >
                    {cat.category}
                  </h3>
                  <div className="space-y-2">
                    {cat.items.map((item, j) => (
                      <div key={j} className="flex items-start gap-2 text-sm">
                        <span className="shrink-0 mt-0.5" style={{ color: "var(--green)" }}>✓</span>
                        <span style={{ color: "var(--muted)" }}>{item}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* vs commercial */}
        <section className="py-20" style={{ background: "var(--bg-deep)" }}>
          <div className="max-w-4xl mx-auto px-6">
            <div className="text-center mb-12" data-reveal>
              <p className="section-label mb-3">Cost comparison</p>
              <h2
                className="font-bold tracking-tight"
                style={{ fontSize: "clamp(1.5rem, 3vw, 2rem)", fontFamily: "var(--font-geist-sans)" }}
              >
                <span className="gradient-text">$0 vs $2,000+/month</span>
              </h2>
            </div>
            <div data-reveal className="card-flat overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr style={{ borderBottom: "1px solid var(--border)", background: "var(--surface-2)" }}>
                      <th className="text-left px-6 py-3 font-medium" style={{ color: "var(--muted)" }}>What you need</th>
                      <th className="px-6 py-3 text-center font-bold" style={{ color: "var(--indigo)" }}>LangSight</th>
                      <th className="px-6 py-3 text-center font-medium" style={{ color: "var(--muted)" }}>Datadog APM</th>
                      <th className="px-6 py-3 text-center font-medium" style={{ color: "var(--muted)" }}>New Relic</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[
                      ["Monthly cost (10 services)", "$0", "~$2,400/mo", "~$1,800/mo"],
                      ["Agent action traces", "✓ Free", "✓ Paid", "✓ Paid"],
                      ["MCP health monitoring", "✓ Free", "✗", "✗"],
                      ["Security scanning", "✓ Free", "✗", "✗"],
                      ["Data leaves your network", "Never", "Always", "Always"],
                      ["Vendor lock-in", "None (Apache 2.0)", "High", "High"],
                      ["Custom retention", "Unlimited", "Pay per GB", "Pay per GB"],
                    ].map((row, i) => (
                      <tr key={i} style={{ borderBottom: i < 6 ? "1px solid var(--border-dim)" : "none" }}>
                        <td className="px-6 py-3" style={{ color: "var(--text)" }}>{row[0]}</td>
                        <td className="px-6 py-3 text-center font-medium" style={{ color: "var(--green)" }}>{row[1]}</td>
                        <td className="px-6 py-3 text-center" style={{ color: "var(--muted)" }}>{row[2]}</td>
                        <td className="px-6 py-3 text-center" style={{ color: "var(--muted)" }}>{row[3]}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </section>

        {/* FAQ */}
        <section className="py-24">
          <div className="max-w-3xl mx-auto px-6">
            <div className="text-center mb-12" data-reveal>
              <p className="section-label mb-3">FAQ</p>
              <h2
                className="font-bold tracking-tight"
                style={{ fontSize: "clamp(1.5rem, 3vw, 2rem)", fontFamily: "var(--font-geist-sans)" }}
              >
                <span className="gradient-text">Common questions</span>
              </h2>
            </div>
            <div data-reveal className="space-y-3">
              {FAQ.map((item, i) => (
                <FAQItem key={i} q={item.q} a={item.a} />
              ))}
            </div>
          </div>
        </section>

        {/* CTA */}
        <section className="py-20" style={{ background: "var(--bg-deep)" }}>
          <div className="max-w-3xl mx-auto px-6 text-center" data-reveal>
            <h2
              className="font-bold tracking-tight mb-4"
              style={{ fontSize: "clamp(1.5rem, 3vw, 2.2rem)", fontFamily: "var(--font-geist-sans)" }}
            >
              <span className="gradient-indigo">Start now. It&apos;s free.</span>
            </h2>
            <p className="text-base mb-8" style={{ color: "var(--muted)" }}>
              30 seconds to install. Two lines to instrument. No account required.
            </p>
            <div className="flex flex-wrap justify-center gap-3">
              <a
                href="https://docs.langsight.dev/quickstart"
                className="text-sm font-semibold px-5 py-2.5 rounded-lg transition-all hover:opacity-90 hover:-translate-y-px"
                style={{ background: "var(--indigo)", color: "white" }}
              >
                Quickstart guide →
              </a>
              <a
                href="https://github.com/LangSight/langsight"
                className="text-sm font-semibold px-5 py-2.5 rounded-lg flex items-center gap-2 transition-all hover:-translate-y-px"
                style={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text)" }}
              >
                <GithubIcon className="w-4 h-4" /> Star on GitHub
              </a>
            </div>
          </div>
        </section>

      </main>

      {/* Footer */}
      <footer className="py-10" style={{ borderTop: "1px solid var(--border)" }}>
        <div className="max-w-6xl mx-auto px-6 flex flex-col sm:flex-row items-center justify-between gap-4">
          <Logo />
          <div className="flex flex-wrap justify-center gap-x-6 gap-y-2 text-sm">
            {[["Home", "/"], ["Security", "/security"], ["Docs", "https://docs.langsight.dev"], ["GitHub", "https://github.com/LangSight/langsight"]].map(([l, h]) => (
              <a key={l} href={h} className="transition-colors" style={{ color: "var(--muted)" }}
                onMouseEnter={(e) => (e.currentTarget.style.color = "var(--text)")}
                onMouseLeave={(e) => (e.currentTarget.style.color = "var(--muted)")}>
                {l}
              </a>
            ))}
          </div>
          <p className="text-xs" style={{ color: "var(--dimmer)" }}>Apache 2.0 · v0.3.0</p>
        </div>
      </footer>
    </>
  );
}
