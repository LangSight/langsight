"use client";

import { useState } from "react";
import { Nav, Footer, useTheme } from "@/components/site-shell";
import {
  ScrollReveal,
  SpotlightCard,
  GlowBorder,
  MagneticHover,
  SharedKeyframes,
  AnimatedGridBg,
} from "@/components/hero/animated-primitives";

function GithubIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
    </svg>
  );
}

/* ── Feature list ──────────────────────────────────────── */
const ALL_FEATURES = [
  { category: "Agent Runtime Reliability", items: ["Full session traces — every tool call", "Multi-agent call tree reconstruction", "Payload capture (input args + output)", "LLM reasoning traces (llm_input / llm_output)", "Anomaly detection (z-score vs 7-day baseline)", "Agent SLO tracking (success_rate, latency_p99)"] },
  { category: "MCP Health Monitoring", items: ["Continuous proactive health checks", "Schema drift detection", "Latency tracking and p99 trends", "Slack + webhook alerts on DOWN/recovery", "Multi-transport: stdio, SSE, StreamableHTTP"] },
  { category: "MCP Security Scanning", items: ["CVE detection against public database", "5 of 10 OWASP MCP checks (more coming)", "Tool poisoning detection (injection, unicode, base64)", "Auth gap analysis", "CI/CD integration with --ci flag", "JSON output for SIEM integration"] },
  { category: "Cost Attribution", items: ["Token-based pricing for LLM calls", "Per-tool call-based pricing rules", "Cost per session / per agent / per tool", "Model pricing table (admin-managed)", "Historical cost trends"] },
  { category: "Infrastructure", items: ["PostgreSQL for metadata", "ClickHouse for analytics", "Dual-storage architecture", "Docker Compose deployment", "Alembic migrations"] },
  { category: "Teams & Access", items: ["Multi-user with invite-based signup", "Project-level RBAC (owner / member / viewer)", "API key auth with role scopes", "Global admin + per-project roles", "Audit trail for auth events"] },
];

/* ── FAQ ───────────────────────────────────────────────── */
const FAQ = [
  { q: "Is it really free? What's the catch?", a: "There is no catch. LangSight is Apache 2.0 open source. You can self-host it for free, forever, for any use including commercial. We do not have a paid tier today." },
  { q: "Is there a cloud-hosted version?", a: "Not yet. We're working on a cloud-hosted option for teams who don't want to manage infrastructure. Join the waitlist below to be notified when it's available." },
  { q: "What infrastructure do I need to self-host?", a: "LangSight requires Docker. Copy .env.example to .env, fill in the required passwords, then run docker compose up -d. PostgreSQL (metadata) and ClickHouse (analytics) both start automatically. The full stack is up in under 5 minutes." },
  { q: "Does my data leave my network?", a: "No. LangSight is entirely self-hosted. Your agent traces, tool call payloads, and cost data never leave your infrastructure. The only outbound requests are CVE database lookups during security scans, which you can disable." },
  { q: "What happens when a cloud tier launches?", a: "The self-hosted version will always remain Apache 2.0 and fully featured. Any cloud tier will be additive — managed hosting, support SLAs, enterprise SSO. We will never move existing features to a paid tier." },
  { q: "How do I get support?", a: "GitHub Issues for bugs and feature requests. GitHub Discussions for questions. We respond to all issues. For production deployments, docs.langsight.dev covers every deployment scenario." },
];

function FAQItem({ q, a }: { q: string; a: string }) {
  const [open, setOpen] = useState(false);
  return (
    <SpotlightCard
      className="rounded-xl overflow-hidden"
      style={{ background: "var(--surface)", border: `1px solid ${open ? "var(--indigo)" : "var(--border)"}`, transition: "border-color 0.2s" }}
    >
      <button className="w-full px-6 py-4 flex items-center justify-between gap-4 text-left" onClick={() => setOpen((o) => !o)}>
        <span className="font-medium text-sm" style={{ color: "var(--text)", fontFamily: "var(--font-geist-sans)" }}>{q}</span>
        <span
          className="shrink-0 w-5 h-5 rounded-full flex items-center justify-center transition-transform"
          style={{ background: open ? "var(--indigo)" : "var(--surface-2)", color: open ? "white" : "var(--muted)", transform: open ? "rotate(45deg)" : "rotate(0deg)" }}
        >
          <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
            <path d="M5 1v8M1 5h8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
        </span>
      </button>
      {open && (
        <div className="px-6 pb-4 text-sm leading-relaxed" style={{ color: "var(--muted)" }}>{a}</div>
      )}
    </SpotlightCard>
  );
}

/* ── Page ──────────────────────────────────────────────── */
export default function PricingPage() {
  const { dark, toggle } = useTheme();

  return (
    <>
      {/* Obsidian palette */}
      <style jsx global>{`
        :root {
          --indigo: #4F46E5; --indigo-dim: rgba(79,70,229,0.08); --indigo-glow: rgba(79,70,229,0.12); --indigo-strong: rgba(79,70,229,0.20);
          --terminal-bg: #F8F9FA; --code-text: #4F46E5;
        }
        .dark {
          --bg: #050507; --bg-deep: #030305; --surface: #0E0E12; --surface-2: #131317;
          --border: #1E1E24; --border-dim: #141418; --text: #E8E8ED; --muted: #9898A6; --dimmer: #5C5C6B;
          --indigo: #6366F1; --indigo-dim: rgba(99,102,241,0.10); --indigo-glow: rgba(99,102,241,0.18); --indigo-strong: rgba(99,102,241,0.25);
          --green: #34D399; --red: #F87171; --yellow: #FBBF24; --orange: #FB923C;
          --terminal-bg: #08080B; --code-text: #C4B5FD;
        }
        .gradient-text { background: linear-gradient(135deg, var(--text) 0%, var(--muted) 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
        .gradient-indigo { background: linear-gradient(135deg, #818CF8 0%, #6366F1 50%, #A78BFA 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
      `}</style>

      <div className="fixed inset-0 pointer-events-none dark:opacity-[0.025] opacity-0 transition-opacity" aria-hidden="true"
        style={{ zIndex: 90, mixBlendMode: "overlay", backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.65' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")` }}
      />

      <SharedKeyframes />
      <Nav dark={dark} toggle={toggle} activePage="Pricing" />

      <main style={{ background: "var(--bg)" }}>

        {/* ── Hero ──────────────────────────────────── */}
        <section className="relative pt-32 pb-20 overflow-hidden">
          <div className="absolute inset-0 pointer-events-none" aria-hidden="true">
            <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[400px] rounded-full blur-[150px]" style={{ background: "rgba(34,197,94,0.06)" }} />
            <div className="absolute top-1/3 right-1/3 w-[400px] h-[300px] rounded-full blur-[120px]" style={{ background: "rgba(99,102,241,0.05)" }} />
          </div>

          <div className="relative max-w-4xl mx-auto px-6 text-center">
            <ScrollReveal>
              <div className="inline-flex items-center gap-2 rounded-full px-4 py-1.5 text-xs font-medium mb-6"
                style={{ background: "rgba(34,197,94,0.10)", border: "1px solid rgba(34,197,94,0.2)", color: "#22C55E" }}>
                <span className="w-1.5 h-1.5 rounded-full" style={{ background: "#22C55E", animation: "pulse 2s ease infinite" }} />
                No credit card · No account · No usage limits
              </div>
            </ScrollReveal>

            <ScrollReveal delay={100}>
              <h1 className="font-bold tracking-tight mb-6" style={{ fontSize: "clamp(2.2rem, 5vw, 3.5rem)", fontFamily: "var(--font-geist-sans)" }}>
                <span className="gradient-text">Free.</span><br />
                <span className="gradient-indigo">Forever.</span><br />
                <span className="gradient-text">No asterisk.</span>
              </h1>
            </ScrollReveal>

            <ScrollReveal delay={200}>
              <p className="text-lg leading-relaxed max-w-xl mx-auto mb-10" style={{ color: "var(--muted)" }}>
                LangSight is Apache 2.0 open source. Self-host the entire platform —
                CLI, SDK, API, dashboard, and every feature — at no cost. Not &ldquo;open core&rdquo;.
                Not a free tier. Just free.
              </p>
            </ScrollReveal>

            <ScrollReveal delay={300}>
              <div className="flex flex-wrap justify-center gap-3 mb-6">
                <MagneticHover strength={0.2}>
                  <a href="https://docs.langsight.dev/quickstart" className="text-sm font-semibold px-6 py-2.5 rounded-lg transition-all hover:opacity-90 hover:-translate-y-px"
                    style={{ background: "var(--indigo)", color: "white", boxShadow: "0 0 20px rgba(99,102,241,0.25)" }}>
                    Get started free →
                  </a>
                </MagneticHover>
                <MagneticHover strength={0.2}>
                  <a href="https://github.com/LangSight/langsight" className="text-sm font-semibold px-6 py-2.5 rounded-lg flex items-center gap-2 transition-all hover:-translate-y-px"
                    style={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text)" }}>
                    <GithubIcon className="w-4 h-4" /> Star on GitHub
                  </a>
                </MagneticHover>
              </div>
            </ScrollReveal>

            <ScrollReveal delay={400}>
              <div className="inline-flex items-center gap-3 rounded-xl px-4 py-2.5"
                style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
                <span style={{ fontFamily: "var(--font-geist-mono)", fontSize: "0.8rem", color: "var(--dimmer)" }}>$</span>
                <span style={{ fontFamily: "var(--font-geist-mono)", fontSize: "0.8rem", color: "var(--code-text)" }}>pip install langsight && langsight init</span>
              </div>
            </ScrollReveal>
          </div>
        </section>

        {/* ── Tier cards ───────────────────────────── */}
        <section className="py-20" style={{ background: "var(--bg-deep)" }}>
          <div className="max-w-5xl mx-auto px-6">
            <div className="grid md:grid-cols-2 gap-6">
              {/* Open Source */}
              <ScrollReveal>
                <GlowBorder borderRadius="16px" glowOpacity={0.25} hoverOpacity={0.45}>
                  <SpotlightCard className="rounded-2xl p-8 h-full" style={{ background: "var(--surface)" }} spotlightColor="rgba(99,102,241,0.08)">
                    <div className="flex items-start justify-between mb-6">
                      <div>
                        <p className="text-xs font-medium uppercase tracking-[0.15em] mb-1" style={{ fontFamily: "var(--font-geist-mono)", color: "var(--indigo)" }}>Self-hosted</p>
                        <h3 className="font-bold text-2xl" style={{ color: "var(--text)", fontFamily: "var(--font-geist-sans)" }}>Open Source</h3>
                      </div>
                      <div className="text-xs px-2.5 py-1 rounded-full font-semibold" style={{ background: "rgba(34,197,94,0.10)", color: "#22C55E", border: "1px solid rgba(34,197,94,0.2)" }}>
                        Free forever
                      </div>
                    </div>

                    <div className="mb-6">
                      <span className="font-bold" style={{ fontSize: "3rem", fontFamily: "var(--font-geist-sans)", color: "var(--text)", lineHeight: 1 }}>$0</span>
                      <span className="text-sm ml-2" style={{ color: "var(--muted)" }}>forever · Apache 2.0</span>
                    </div>

                    <a href="https://docs.langsight.dev/quickstart" className="block w-full text-center text-sm font-semibold px-5 py-2.5 rounded-lg mb-6 transition-all hover:opacity-90"
                      style={{ background: "var(--indigo)", color: "white", boxShadow: "0 0 16px rgba(99,102,241,0.2)" }}>
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
                        "Anomaly detection + SLO tracking",
                        "AI root cause analysis (bring your key)",
                        "Self-hosted — your data, your infra",
                        "Apache 2.0 — fork, modify, sell freely",
                      ].map((f, i) => (
                        <div key={i} className="flex items-center gap-2 text-sm">
                          <span style={{ color: "#22C55E" }}>✓</span>
                          <span style={{ color: "var(--muted)" }}>{f}</span>
                        </div>
                      ))}
                    </div>
                  </SpotlightCard>
                </GlowBorder>
              </ScrollReveal>

              {/* Cloud (coming soon) */}
              <ScrollReveal delay={100}>
                <SpotlightCard className="rounded-2xl p-8 h-full" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
                  <div className="flex items-start justify-between mb-6">
                    <div>
                      <p className="text-xs font-medium uppercase tracking-[0.15em] mb-1" style={{ fontFamily: "var(--font-geist-mono)", color: "var(--dimmer)" }}>Managed cloud</p>
                      <h3 className="font-bold text-2xl" style={{ color: "var(--text)", fontFamily: "var(--font-geist-sans)" }}>Cloud</h3>
                    </div>
                    <div className="text-xs px-2.5 py-1 rounded-full font-semibold" style={{ background: "var(--indigo-dim)", color: "var(--indigo)", border: "1px solid var(--indigo-strong)" }}>
                      Coming soon
                    </div>
                  </div>

                  <div className="mb-6">
                    <span className="font-bold" style={{ fontSize: "3rem", fontFamily: "var(--font-geist-sans)", color: "var(--dimmer)", lineHeight: 1 }}>TBD</span>
                    <span className="text-sm ml-2" style={{ color: "var(--dimmer)" }}>usage-based pricing</span>
                  </div>

                  <button disabled className="block w-full text-center text-sm font-semibold px-5 py-2.5 rounded-lg mb-6 cursor-not-allowed"
                    style={{ background: "var(--surface-2)", color: "var(--dimmer)", border: "1px solid var(--border)" }}>
                    Join waitlist →
                  </button>

                  <div className="space-y-2.5">
                    {["Everything in Open Source", "No infrastructure to manage", "Automatic backups + upgrades", "99.9% uptime SLA", "Enterprise SSO (SAML/OIDC)", "Priority support + SLA", "Dedicated Slack channel", "Custom data retention", "Usage-based — pay only for what you use"].map((f, i) => (
                      <div key={i} className="flex items-center gap-2 text-sm">
                        <span style={{ color: "var(--dimmer)" }}>○</span>
                        <span style={{ color: "var(--dimmer)" }}>{f}</span>
                      </div>
                    ))}
                  </div>

                  <div className="mt-6 rounded-lg p-4 text-sm" style={{ background: "var(--indigo-dim)", border: "1px solid var(--indigo-strong)" }}>
                    <p className="font-semibold mb-1" style={{ color: "var(--indigo)" }}>Get notified when cloud launches</p>
                    <p style={{ color: "var(--muted)" }}>
                      Leave a GitHub star and we&apos;ll announce via releases.
                      <a href="https://github.com/LangSight/langsight" className="ml-1 underline" style={{ color: "var(--indigo)" }}>Star on GitHub →</a>
                    </p>
                  </div>
                </SpotlightCard>
              </ScrollReveal>
            </div>
          </div>
        </section>

        {/* ── All features ─────────────────────────── */}
        <section className="relative py-24 overflow-hidden">
          <AnimatedGridBg />
          <div className="relative max-w-6xl mx-auto px-6">
            <ScrollReveal className="text-center mb-14">
              <p className="text-xs font-medium uppercase tracking-[0.15em] mb-3" style={{ fontFamily: "var(--font-geist-mono)", color: "var(--indigo)" }}>Everything included</p>
              <h2 className="font-bold tracking-tight" style={{ fontSize: "clamp(1.5rem, 3vw, 2rem)", fontFamily: "var(--font-geist-sans)" }}>
                <span className="gradient-text">No feature gating. Ever.</span>
              </h2>
              <p className="mt-4 max-w-lg mx-auto text-sm" style={{ color: "var(--muted)" }}>
                Every capability listed below is available in the free open-source version.
                We will never move an existing feature to a paid tier.
              </p>
            </ScrollReveal>

            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
              {ALL_FEATURES.map((cat, i) => (
                <ScrollReveal key={i} delay={i * 60}>
                  <SpotlightCard className="rounded-xl p-6 h-full" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
                    <h3 className="font-semibold text-sm mb-4" style={{ color: "var(--indigo)", fontFamily: "var(--font-geist-sans)" }}>{cat.category}</h3>
                    <div className="space-y-2">
                      {cat.items.map((item, j) => (
                        <div key={j} className="flex items-start gap-2 text-sm">
                          <span className="shrink-0 mt-0.5" style={{ color: "#22C55E" }}>✓</span>
                          <span style={{ color: "var(--muted)" }}>{item}</span>
                        </div>
                      ))}
                    </div>
                  </SpotlightCard>
                </ScrollReveal>
              ))}
            </div>
          </div>
        </section>

        {/* ── vs commercial ────────────────────────── */}
        <section className="py-20" style={{ background: "var(--bg-deep)" }}>
          <div className="max-w-4xl mx-auto px-6">
            <ScrollReveal className="text-center mb-12">
              <p className="text-xs font-medium uppercase tracking-[0.15em] mb-3" style={{ fontFamily: "var(--font-geist-mono)", color: "var(--indigo)" }}>Cost comparison</p>
              <h2 className="font-bold tracking-tight" style={{ fontSize: "clamp(1.5rem, 3vw, 2rem)", fontFamily: "var(--font-geist-sans)" }}>
                <span className="gradient-text">$0 vs $2,000+/month</span>
              </h2>
            </ScrollReveal>

            <ScrollReveal delay={200}>
              <GlowBorder borderRadius="12px" glowOpacity={0.15} hoverOpacity={0.35}>
                <div className="rounded-xl overflow-hidden" style={{ background: "var(--surface)" }}>
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
                            <td className="px-6 py-3 text-center font-medium" style={{ color: "#22C55E" }}>{row[1]}</td>
                            <td className="px-6 py-3 text-center" style={{ color: "var(--muted)" }}>{row[2]}</td>
                            <td className="px-6 py-3 text-center" style={{ color: "var(--muted)" }}>{row[3]}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </GlowBorder>
            </ScrollReveal>
          </div>
        </section>

        {/* ── FAQ ──────────────────────────────────── */}
        <section className="py-24" style={{ background: "var(--bg)" }}>
          <div className="max-w-3xl mx-auto px-6">
            <ScrollReveal className="text-center mb-12">
              <p className="text-xs font-medium uppercase tracking-[0.15em] mb-3" style={{ fontFamily: "var(--font-geist-mono)", color: "var(--indigo)" }}>FAQ</p>
              <h2 className="font-bold tracking-tight" style={{ fontSize: "clamp(1.5rem, 3vw, 2rem)", fontFamily: "var(--font-geist-sans)" }}>
                <span className="gradient-text">Common questions</span>
              </h2>
            </ScrollReveal>

            <div className="space-y-3">
              {FAQ.map((item, i) => (
                <ScrollReveal key={i} delay={i * 50}>
                  <FAQItem q={item.q} a={item.a} />
                </ScrollReveal>
              ))}
            </div>
          </div>
        </section>

        {/* ── CTA ─────────────────────────────────── */}
        <section className="py-20" style={{ background: "var(--bg-deep)" }}>
          <ScrollReveal className="max-w-3xl mx-auto px-6">
            <GlowBorder borderRadius="16px" glowOpacity={0.2} hoverOpacity={0.45}>
              <SpotlightCard className="rounded-2xl p-10 text-center" style={{ background: "var(--surface)" }}>
                <h2 className="font-bold tracking-tight mb-4" style={{ fontSize: "clamp(1.5rem, 3vw, 2.2rem)", fontFamily: "var(--font-geist-sans)" }}>
                  <span className="gradient-indigo">Start now. It&apos;s free.</span>
                </h2>
                <p className="text-base mb-8" style={{ color: "var(--muted)" }}>
                  30 seconds to install. Two lines to instrument. No account required.
                </p>
                <div className="flex flex-wrap justify-center gap-3">
                  <MagneticHover strength={0.2}>
                    <a href="https://docs.langsight.dev/quickstart" className="text-sm font-semibold px-6 py-2.5 rounded-lg transition-all hover:opacity-90 hover:-translate-y-px"
                      style={{ background: "var(--indigo)", color: "white", boxShadow: "0 0 20px rgba(99,102,241,0.25)" }}>
                      Quickstart guide →
                    </a>
                  </MagneticHover>
                  <MagneticHover strength={0.2}>
                    <a href="https://github.com/LangSight/langsight" className="text-sm font-semibold px-6 py-2.5 rounded-lg flex items-center gap-2 transition-all hover:-translate-y-px"
                      style={{ background: "var(--surface-2)", border: "1px solid var(--border)", color: "var(--text)" }}>
                      <GithubIcon className="w-4 h-4" /> Star on GitHub
                    </a>
                  </MagneticHover>
                </div>
              </SpotlightCard>
            </GlowBorder>
          </ScrollReveal>
        </section>

      </main>
      <Footer />
    </>
  );
}
