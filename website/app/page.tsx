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

/* ── Scroll reveal ──────────────────────────────────────────── */
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

/* ── Icons ──────────────────────────────────────────────────── */
function GithubIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
    </svg>
  );
}

function SunIcon() {
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
      <circle cx="12" cy="12" r="5" />
      <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
      <path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z" />
    </svg>
  );
}

function ShieldIcon() {
  return (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" />
    </svg>
  );
}

function HeartPulseIcon() {
  return (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" d="M21 8.25c0-2.485-2.099-4.5-4.688-4.5-1.935 0-3.597 1.126-4.312 2.733-.715-1.607-2.377-2.733-4.313-2.733C5.1 3.75 3 5.765 3 8.25c0 7.22 9 12 9 12s9-4.78 9-12z" />
    </svg>
  );
}

function ZapIcon() {
  return (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z" />
    </svg>
  );
}

function DollarIcon() {
  return (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v12m-3-2.818l.879.659c1.171.879 3.07.879 4.242 0 1.172-.879 1.172-2.303 0-3.182C13.536 12.219 12.768 12 12 12c-.725 0-1.45-.22-2.003-.659-1.106-.879-1.106-2.303 0-3.182s2.9-.879 4.006 0l.415.33M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  );
}

/* ── Logo ───────────────────────────────────────────────────── */
function Logo() {
  return (
    <a href="/" className="flex items-center gap-2.5 shrink-0">
      <div className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0" style={{ background: "var(--indigo)" }}>
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
          {/* Outer ring — the lens */}
          <circle cx="12" cy="12" r="9" stroke="white" strokeWidth="2.5" fill="none"/>
          {/* Center dot — the focus point */}
          <circle cx="12" cy="12" r="2.5" fill="white"/>
          {/* Diagonal line — the active scan, breaks through the ring */}
          <line x1="18" y1="6" x2="23" y2="1" stroke="white" strokeWidth="2.5" strokeLinecap="round"/>
        </svg>
      </div>
      <span className="font-bold text-lg tracking-tight" style={{ fontFamily: "var(--font-geist-sans)", color: "var(--text)" }}>
        Lang<span style={{ color: "var(--indigo)" }}>Sight</span>
      </span>
    </a>
  );
}

/* ── Nav ────────────────────────────────────────────────────── */
function Nav({ dark, toggle }: { dark: boolean; toggle: () => void }) {
  const [scrolled, setScrolled] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    const handler = () => setScrolled(window.scrollY > 24);
    window.addEventListener("scroll", handler);
    return () => window.removeEventListener("scroll", handler);
  }, []);

  const navLinks = [
    { label: "Security", href: "/security" },
    { label: "Pricing", href: "/pricing" },
    { label: "Docs", href: "https://docs.langsight.dev" },
    { label: "GitHub", href: "https://github.com/LangSight/langsight" },
  ];

  return (
    <nav
      className="fixed top-0 left-0 right-0 z-50 transition-all duration-300"
      style={{
        background: scrolled ? "color-mix(in srgb, var(--bg) 88%, transparent)" : "transparent",
        backdropFilter: scrolled ? "blur(16px) saturate(180%)" : "none",
        WebkitBackdropFilter: scrolled ? "blur(16px) saturate(180%)" : "none",
        borderBottom: scrolled ? "1px solid var(--border)" : "1px solid transparent",
      }}
    >
      <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between gap-6">
        <Logo />

        {/* Desktop links */}
        <div className="hidden md:flex items-center gap-1">
          {navLinks.map((l) => (
            <a
              key={l.label}
              href={l.href}
              className="px-3 py-1.5 rounded-md text-sm transition-colors"
              style={{ color: "var(--muted)" }}
              onMouseEnter={(e) => (e.currentTarget.style.color = "var(--text)")}
              onMouseLeave={(e) => (e.currentTarget.style.color = "var(--muted)")}
            >
              {l.label}
            </a>
          ))}
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={toggle}
            aria-label="Toggle theme"
            className="w-9 h-9 rounded-lg flex items-center justify-center transition-all hover:scale-110"
            style={{ background: "var(--surface-2)", border: "1px solid var(--border)", color: "var(--muted)" }}
          >
            {dark ? <SunIcon /> : <MoonIcon />}
          </button>

          <a
            href="https://docs.langsight.dev/quickstart"
            className="hidden sm:flex items-center gap-1.5 text-sm font-semibold px-4 py-2 rounded-lg transition-all hover:opacity-90 hover:-translate-y-px"
            style={{ background: "var(--indigo)", color: "white" }}
          >
            Start self-hosting →
          </a>

          {/* Mobile hamburger */}
          <button
            className="md:hidden w-9 h-9 flex flex-col items-center justify-center gap-1.5"
            onClick={() => setMobileOpen((o) => !o)}
            aria-label="Menu"
          >
            <span className="block w-5 h-px transition-all" style={{ background: "var(--muted)" }} />
            <span className="block w-5 h-px transition-all" style={{ background: "var(--muted)" }} />
            <span className="block w-3 h-px transition-all" style={{ background: "var(--muted)" }} />
          </button>
        </div>
      </div>

      {/* Mobile menu */}
      {mobileOpen && (
        <div className="md:hidden px-6 pb-4 space-y-1" style={{ background: "var(--bg)", borderTop: "1px solid var(--border)" }}>
          {navLinks.map((l) => (
            <a
              key={l.label}
              href={l.href}
              className="block px-3 py-2.5 rounded-lg text-sm"
              style={{ color: "var(--muted)" }}
              onClick={() => setMobileOpen(false)}
            >
              {l.label}
            </a>
          ))}
          <a
            href="https://docs.langsight.dev/quickstart"
            className="block mt-2 px-3 py-2.5 rounded-lg text-sm font-semibold text-center"
            style={{ background: "var(--indigo)", color: "white" }}
          >
            Start self-hosting →
          </a>
        </div>
      )}
    </nav>
  );
}

/* ── Animated terminal ──────────────────────────────────────── */
const TERMINAL_LINES = [
  { text: "$ langsight sessions --id sess-f2a9b1", color: "var(--dimmer)", delay: 0 },
  { text: "", delay: 200 },
  { text: "Trace: sess-f2a9b1  (support-agent)", color: "var(--text)", bold: true, delay: 380 },
  { text: "5 tool calls · 1 failed · 2,134ms · $0.023", color: "var(--muted)", small: true, delay: 500 },
  { text: "", delay: 620 },
  { text: "sess-f2a9b1", color: "var(--indigo)", delay: 760 },
  { text: "├── jira-mcp/get_issue        89ms  ✓", color: "var(--green)", delay: 940 },
  { text: "├── postgres-mcp/query        42ms  ✓", color: "var(--green)", delay: 1100 },
  { text: "├──  → billing-agent          handoff", color: "var(--yellow)", delay: 1280 },
  { text: "│   ├── crm-mcp/update    120ms  ✓", color: "var(--green)", delay: 1460 },
  { text: "│   └── slack-mcp/notify    —   ✗  timeout", color: "var(--red)", delay: 1640 },
  { text: "", delay: 1800 },
  { text: "Root cause: slack-mcp timed out at 14:32 UTC", color: "var(--orange)", bold: true, delay: 1960 },
  { text: "└── Fix: check SLACK_TIMEOUT (currently 500ms)", color: "var(--dimmer)", small: true, delay: 2100 },
];

function AnimatedTerminal() {
  // Render ALL lines immediately — critical for LCP.
  // The animation replays after mount without blocking first paint.
  const [visible, setVisible] = useState(TERMINAL_LINES.length);

  useEffect(() => {
    // Replay animation once after initial paint (non-blocking)
    setVisible(0);
    const timers = TERMINAL_LINES.map((line, i) =>
      setTimeout(() => setVisible(i + 1), line.delay + 600)
    );
    return () => timers.forEach(clearTimeout);
  }, []);

  return (
    <div className="terminal w-full">
      <div className="terminal-bar">
        <div className="terminal-dot" style={{ background: "#EF4444" }} />
        <div className="terminal-dot" style={{ background: "#EAB308" }} />
        <div className="terminal-dot" style={{ background: "#22C55E" }} />
        <span
          className="ml-3 text-xs"
          style={{ fontFamily: "var(--font-geist-mono)", color: "var(--dimmer)" }}
        >
          langsight · session trace
        </span>
      </div>
      <div className="p-5 space-y-0.5 min-h-[300px] overflow-hidden" style={{ fontFamily: "var(--font-geist-mono)", fontSize: "0.82rem" }}>
        {TERMINAL_LINES.slice(0, visible).map((line, i) => (
          <div
            key={i}
            className="term-line"
            style={{
              color: line.color ?? "var(--text)",
              fontWeight: line.bold ? 700 : 400,
              fontSize: line.small ? "0.72rem" : undefined,
              lineHeight: 1.7,
            }}
          >
            {line.text || "\u00A0"}
          </div>
        ))}
        {visible < TERMINAL_LINES.length && (
          <span className="cursor inline-block w-2 h-4 align-middle" style={{ background: "var(--indigo)" }} />
        )}
      </div>
    </div>
  );
}

/* ── Hero ───────────────────────────────────────────────────── */
function Hero() {
  return (
    <section className="relative min-h-screen flex items-center grid-bg overflow-hidden pt-16">
      {/* Background glow */}
      <div className="absolute inset-0 pointer-events-none overflow-hidden">
        <div
          className="absolute top-1/4 left-1/3 w-[600px] h-[600px] rounded-full blur-[160px]"
          style={{ background: "rgba(20,184,166,0.12)" }}
        />
        <div
          className="absolute bottom-1/4 right-1/4 w-[400px] h-[400px] rounded-full blur-[140px]"
          style={{ background: "rgba(45,212,191,0.08)" }}
        />
      </div>

      <div className="relative max-w-6xl mx-auto px-6 py-28 w-full">
        <div className="grid lg:grid-cols-2 gap-12 xl:gap-20 items-center">
          {/* Left: copy */}
          <div className="space-y-8">
            {/* Badge */}
            <div
              className="fade-up inline-flex items-center gap-2 rounded-full px-4 py-1.5 text-xs font-medium"
              style={{ background: "var(--indigo-dim)", border: "1px solid rgba(45,212,191,0.25)", color: "var(--indigo)" }}
            >
              <span className="w-1.5 h-1.5 rounded-full pulse-dot" style={{ background: "var(--indigo)" }} />
              v0.2.0 · Self-host free · BSL 1.1
            </div>

            {/* Headline — lead with pain */}
            <div className="space-y-1">
              <h1
                className="font-bold leading-[1.04] tracking-tight"
                style={{ fontSize: "clamp(2.6rem, 5vw, 3.75rem)", fontFamily: "var(--font-geist-sans)" }}
              >
                <span className="gradient-text">Your agent failed.</span>
                <br />
                <span className="gradient-text">Which tool broke</span>
                <br />
                <span className="gradient-indigo">— and why?</span>
              </h1>
            </div>

            {/* Subheading */}
            <p
              className="fade-up delay-2 text-lg leading-relaxed max-w-md"
              style={{ color: "var(--muted)" }}
            >
              Trace what your agents called. Find what broke, what&apos;s expensive, and what&apos;s unsafe.
              For MCP servers, get health checks, schema drift alerts, and security scanning built in.
            </p>

            {/* Positioning bar — the most important line on the page */}
            <div
              className="fade-up delay-2 rounded-lg px-4 py-3 text-sm"
              style={{
                background: "var(--surface-2)",
                border: "1px solid var(--border)",
                color: "var(--muted)",
              }}
            >
              <strong style={{ color: "var(--text)" }}>Not another prompt, eval, or simulation platform.</strong>
              {" "}LangSight monitors the runtime layer: the tools your agents depend on.
            </div>

            {/* CTAs */}
            <div className="fade-up delay-3 flex flex-wrap gap-3">
              <a
                href="https://docs.langsight.dev/quickstart"
                className="text-sm font-semibold px-5 py-2.5 rounded-lg flex items-center gap-2 transition-all hover:opacity-90 hover:-translate-y-px"
                style={{ background: "var(--indigo)", color: "white" }}
              >
                Start self-hosting →
              </a>
              <a
                href="#failure-trace"
                className="text-sm font-semibold px-5 py-2.5 rounded-lg flex items-center gap-2 transition-all hover:-translate-y-px"
                style={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text)" }}
              >
                See an MCP failure trace
              </a>
            </div>

            {/* Install pill */}
            <div
              className="fade-up delay-4 inline-flex items-center gap-3 rounded-xl px-4 py-2.5"
              style={{ background: "var(--surface-2)", border: "1px solid var(--border)" }}
            >
              <span style={{ color: "var(--dimmer)", fontFamily: "var(--font-geist-mono)", fontSize: "0.8rem" }}>$</span>
              <span style={{ fontFamily: "var(--font-geist-mono)", fontSize: "0.8rem", color: "var(--code-text)" }}>
                pip install langsight
              </span>
              <span style={{ color: "var(--dimmer)", fontFamily: "var(--font-geist-mono)", fontSize: "0.8rem" }}>&amp;&amp;</span>
              <span style={{ fontFamily: "var(--font-geist-mono)", fontSize: "0.8rem", color: "var(--code-text)" }}>
                langsight init
              </span>
            </div>

            {/* Proof line */}
            <div
              className="fade-up delay-5 flex flex-wrap gap-x-5 gap-y-1 text-xs"
              style={{ color: "var(--dimmer)" }}
            >
              <span>LangChain · CrewAI · Pydantic AI</span>
              <span>Postgres + ClickHouse</span>
              <span>1,003 tests · 77% coverage</span>
            </div>
          </div>

          {/* Right: terminal */}
          <div className="fade-up delay-3">
            <AnimatedTerminal />
          </div>
        </div>
      </div>
    </section>
  );
}

/* ── "What question?" comparison ────────────────────────────── */
const QUESTIONS: { q: string; tool: string; us: boolean }[] = [
  { q: "Did the prompt/model perform well?", tool: "LangWatch / Langfuse / LangSmith", us: false },
  { q: "Should I change prompts or eval policy?", tool: "LangWatch / Langfuse / LangSmith", us: false },
  { q: "Is my server CPU/memory healthy?", tool: "Datadog / New Relic", us: false },
  { q: "Which tool call failed in production?", tool: "LangSight", us: true },
  { q: "Is an MCP server unhealthy or drifting?", tool: "LangSight", us: true },
  { q: "Is an MCP server exposed or risky?", tool: "LangSight", us: true },
  { q: "Why did this session cost $47 instead of $3?", tool: "LangSight", us: true },
];

function Comparison() {
  return (
    <section className="py-24" style={{ background: "var(--bg-deep)" }}>
      <div className="max-w-4xl mx-auto px-6">
        <div className="text-center mb-14" data-reveal>
          <p className="section-label mb-3">Where LangSight fits</p>
          <h2
            className="font-bold tracking-tight"
            style={{ fontSize: "clamp(1.8rem, 3.5vw, 2.5rem)", fontFamily: "var(--font-geist-sans)" }}
          >
            <span className="gradient-text">What question are you</span>
            <br />
            <span className="gradient-indigo">trying to answer?</span>
          </h2>
          <p className="mt-4 max-w-xl mx-auto" style={{ color: "var(--muted)" }}>
            Use LangSight with LangWatch, Langfuse, or LangSmith — not instead of them.
            They evaluate model behavior. LangSight monitors the tool layer underneath.
          </p>
        </div>

        <div data-reveal className="card-flat overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border)", background: "var(--surface-2)" }}>
                  <th className="text-left px-6 py-4 font-medium" style={{ color: "var(--muted)" }}>Question</th>
                  <th className="text-right px-6 py-4 font-medium" style={{ color: "var(--muted)" }}>Best tool</th>
                </tr>
              </thead>
              <tbody>
                {QUESTIONS.map((row, i) => (
                  <tr
                    key={i}
                    style={{
                      borderBottom: i < QUESTIONS.length - 1 ? "1px solid var(--border-dim)" : "none",
                      background: row.us ? "var(--indigo-dim)" : "transparent",
                    }}
                  >
                    <td className="px-6 py-3.5" style={{ color: row.us ? "var(--text)" : "var(--muted)" }}>
                      {row.us && <span style={{ color: "var(--indigo)" }}>→ </span>}
                      {row.q}
                    </td>
                    <td
                      className="px-6 py-3.5 text-right font-semibold whitespace-nowrap"
                      style={{ color: row.us ? "var(--indigo)" : "var(--dimmer)" }}
                    >
                      {row.tool}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ── Problem section ────────────────────────────────────────── */
const PROBLEMS = [
  {
    icon: <ZapIcon />,
    accent: "var(--red)",
    headline: "Which of 15 tools failed?",
    body: "Your orchestrator calls 15 tools across 4 MCP servers. Something returned bad data. Without traces, you spend hours replaying requests — in the dark.",
  },
  {
    icon: <HeartPulseIcon />,
    accent: "var(--orange)",
    headline: "MCP server degraded silently",
    body: "Schema changed. Latency spiked 10x. Auth expired. The agent keeps calling, gets bad data, and hallucinates. You find out from users, not alerts.",
  },
  {
    icon: <DollarIcon />,
    accent: "var(--yellow)",
    headline: "$4,200 in unexpected tool costs",
    body: "A sub-agent retries geocoding-mcp 47 times per session. Nobody noticed until the invoice arrived. You need cost attribution at the tool level, not the model level.",
  },
  {
    icon: <ShieldIcon />,
    accent: "var(--indigo)",
    headline: "Is this MCP server safe to run?",
    body: "66% of community MCP servers have critical code smells. Tool poisoning attacks are real. You need automated scanning, not hope.",
  },
];

function Problem() {
  return (
    <section id="failure-trace" className="py-24">
      <div className="max-w-6xl mx-auto px-6">
        <div className="text-center mb-16" data-reveal>
          <p className="section-label mb-3">The problem</p>
          <h2
            className="font-bold tracking-tight"
            style={{ fontSize: "clamp(1.8rem, 3.5vw, 2.5rem)", fontFamily: "var(--font-geist-sans)" }}
          >
            <span className="gradient-text">LLM quality is only</span>
            <br />
            <span className="gradient-indigo">half the problem.</span>
          </h2>
          <p className="mt-4 max-w-xl mx-auto text-base" style={{ color: "var(--muted)" }}>
            Teams already have ways to inspect prompts and eval scores.
            What they still cannot answer fast enough:
          </p>
        </div>

        <div className="grid sm:grid-cols-2 gap-5">
          {PROBLEMS.map((p, i) => (
            <div key={i} data-reveal className="card p-7 group" style={{ transitionDelay: `${i * 70}ms` }}>
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center mb-5 transition-transform group-hover:scale-110"
                style={{ background: `color-mix(in srgb, ${p.accent} 12%, transparent)`, color: p.accent }}
              >
                {p.icon}
              </div>
              <h3
                className="font-semibold text-base mb-2"
                style={{ color: "var(--text)", fontFamily: "var(--font-geist-sans)" }}
              >
                {p.headline}
              </h3>
              <p className="text-sm leading-relaxed" style={{ color: "var(--muted)" }}>
                {p.body}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ── Solution pillars ──────────────────────────────────────── */
const PILLARS = [
  {
    n: "01",
    title: "Action Traces",
    desc: "See the exact sequence of tool calls, handoffs, failures, and costs across a full agent session. Multi-agent trees reconstructed automatically from parent_span_id.",
    code: `$ langsight sessions --id sess-f2a9b1

sess-f2a9b1  (support-agent)
├── jira-mcp/get_issue        89ms  ✓
├── postgres-mcp/query        42ms  ✓
├──  → billing-agent          handoff
│   ├── crm-mcp/update    120ms  ✓
│   └── slack-mcp/notify    —   ✗  timeout

Root cause: slack-mcp timed out at 14:32`,
  },
  {
    n: "02",
    title: "MCP Health",
    desc: "Detect down, slow, stale, or changed MCP servers before they silently corrupt agent behavior. Schema drift detection catches breaking changes in minutes.",
    code: `$ langsight mcp-health

Server           Status   Latency   Schema    Tools
snowflake-mcp    ✅ UP    142ms     Stable    8
slack-mcp        ⚠️ DEG  1,240ms   Stable    4
jira-mcp         ❌ DOWN  —         —         —
postgres-mcp     ✅ UP    31ms      Changed   5`,
  },
  {
    n: "03",
    title: "MCP Security",
    desc: "Scan for CVEs, OWASP MCP Top 10, tool poisoning signals, weak auth, and risky configs. Run in CI with --ci to block deploys on CRITICAL findings.",
    code: `$ langsight security-scan

CRITICAL  jira-mcp      CVE-2025-6514
  Remote code execution in mcp-remote

HIGH      slack-mcp     OWASP-MCP-01
  Tool description contains injection pattern

HIGH      postgres-mcp  OWASP-MCP-04
  No authentication configured`,
  },
  {
    n: "04",
    title: "Cost Attribution",
    desc: 'Move from "the invoice is $4,200" to "billing-agent\'s geocoding MCP retries 47x per session at $0.005/call."',
    code: `$ langsight costs --hours 24

Tool                 Calls  Failed  Cost     %
geocoding-mcp        2,340  12      $1,872   44.6%
postgres-mcp/query   890    3       $445     10.6%
claude-3.5 (LLM)    156    0       $312     7.4%`,
  },
];

function Solution() {
  return (
    <section className="py-24" style={{ background: "var(--bg-deep)" }}>
      <div className="max-w-6xl mx-auto px-6">
        <div className="text-center mb-16" data-reveal>
          <p className="section-label mb-3">The solution</p>
          <h2
            className="font-bold tracking-tight"
            style={{ fontSize: "clamp(1.8rem, 3.5vw, 2.5rem)", fontFamily: "var(--font-geist-sans)" }}
          >
            <span className="gradient-text">Four pillars of</span>
            <br />
            <span className="gradient-indigo">runtime observability.</span>
          </h2>
        </div>

        <div className="space-y-16">
          {PILLARS.map((step, i) => (
            <div
              key={i}
              data-reveal
              className="grid lg:grid-cols-2 gap-10 xl:gap-16 items-center"
              style={{ transitionDelay: `${i * 80}ms` }}
            >
              <div className={i % 2 === 1 ? "lg:order-2" : ""}>
                <div className="flex items-center gap-4 mb-4">
                  <span
                    className="font-bold select-none"
                    style={{ fontFamily: "var(--font-geist-mono)", fontSize: "2.5rem", color: "var(--border)", lineHeight: 1 }}
                  >
                    {step.n}
                  </span>
                  <h3
                    className="font-bold text-2xl"
                    style={{ color: "var(--text)", fontFamily: "var(--font-geist-sans)" }}
                  >
                    {step.title}
                  </h3>
                </div>
                <p className="leading-relaxed" style={{ color: "var(--muted)" }}>{step.desc}</p>
              </div>

              <div className={i % 2 === 1 ? "lg:order-1" : ""}>
                <div className="terminal">
                  <div className="terminal-bar">
                    <div className="terminal-dot" style={{ background: "#EF444460" }} />
                    <div className="terminal-dot" style={{ background: "#EAB30860" }} />
                    <div className="terminal-dot" style={{ background: "#22C55E60" }} />
                  </div>
                  <pre
                    className="p-5 text-sm overflow-x-auto leading-relaxed"
                    style={{ fontFamily: "var(--font-geist-mono)", color: "var(--code-text)" }}
                  >
                    {step.code}
                  </pre>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ── How it works ───────────────────────────────────────────── */
function HowItWorks() {
  return (
    <section className="py-24">
      <div className="max-w-6xl mx-auto px-6">
        <div className="text-center mb-16" data-reveal>
          <p className="section-label mb-3">Get started</p>
          <h2
            className="font-bold tracking-tight"
            style={{ fontSize: "clamp(1.8rem, 3.5vw, 2.5rem)", fontFamily: "var(--font-geist-sans)" }}
          >
            <span className="gradient-text">Zero to traced</span>
            <br />
            <span className="gradient-indigo">in 5 minutes.</span>
          </h2>
        </div>

        <div className="grid md:grid-cols-3 gap-6">
          {[
            {
              step: "1",
              title: "Install & discover",
              time: "30 seconds",
              code: "pip install langsight\nlangsight init\n\n# Auto-discovered 4 MCP servers",
            },
            {
              step: "2",
              title: "Instrument your agent",
              time: "2 lines of code",
              code: 'from langsight.sdk import LangSightClient\n\nclient = LangSightClient(url="...")\ntraced = client.wrap(mcp, server_name="pg")',
            },
            {
              step: "3",
              title: "See everything",
              time: "real-time",
              code: "langsight sessions\nlangsight mcp-health\nlangsight security-scan\nlangsight costs --hours 24",
            },
          ].map((s, i) => (
            <div key={i} data-reveal className="card p-6" style={{ transitionDelay: `${i * 80}ms` }}>
              <div className="flex items-center gap-3 mb-4">
                <div
                  className="w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold"
                  style={{ background: "var(--indigo)", color: "white" }}
                >
                  {s.step}
                </div>
                <div>
                  <h3 className="font-semibold text-sm" style={{ color: "var(--text)" }}>{s.title}</h3>
                  <p className="text-xs" style={{ color: "var(--dimmer)" }}>{s.time}</p>
                </div>
              </div>
              <div className="terminal">
                <pre
                  className="p-4 text-xs overflow-x-auto leading-relaxed"
                  style={{ fontFamily: "var(--font-geist-mono)", color: "var(--code-text)" }}
                >
                  {s.code}
                </pre>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ── Features grid ─────────────────────────────────────────── */
const FEATURES = [
  {
    title: "Multi-Agent Call Trees",
    desc: "parent_span_id links sub-agent calls across any depth. See the path from orchestrator to leaf tool.",
    badge: "Core",
  },
  {
    title: "Session Replay",
    desc: "Re-execute any session against live MCP servers. Compare two runs side-by-side to see what changed.",
    badge: "v0.2",
  },
  {
    title: "Anomaly Detection",
    desc: "Z-score analysis against 7-day baseline. Warning at |z|>=2, critical at |z|>=3. No manual thresholds.",
    badge: "v0.2",
  },
  {
    title: "Agent SLO Tracking",
    desc: "Define success_rate and latency_p99 targets per agent. Get alerted before you breach availability.",
    badge: "v0.2",
  },
  {
    title: "AI Root Cause Analysis",
    desc: "langsight investigate sends evidence to Claude, GPT-4o, Gemini, or Ollama and returns remediation steps.",
    badge: "4 LLMs",
  },
  {
    title: "Prometheus Metrics",
    desc: "Native /metrics endpoint. Plug into your existing Grafana stack. Request counts, latencies, SSE connections.",
    badge: "v0.2",
  },
];

function Features() {
  return (
    <section className="py-24" style={{ background: "var(--bg-deep)" }}>
      <div className="max-w-6xl mx-auto px-6">
        <div className="text-center mb-14" data-reveal>
          <p className="section-label mb-3">And more</p>
          <h2
            className="font-bold tracking-tight"
            style={{ fontSize: "clamp(1.8rem, 3.5vw, 2.5rem)", fontFamily: "var(--font-geist-sans)" }}
          >
            <span className="gradient-text">Built for production.</span>
          </h2>
        </div>

        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {FEATURES.map((f, i) => (
            <div
              key={i}
              data-reveal
              className="card p-6 group"
              style={{ transitionDelay: `${i * 50}ms` }}
            >
              <div className="flex items-start justify-between mb-3">
                <h3
                  className="font-semibold text-sm flex-1"
                  style={{ color: "var(--text)", fontFamily: "var(--font-geist-sans)" }}
                >
                  {f.title}
                </h3>
                <span
                  className="shrink-0 text-[10px] rounded-full px-2 py-0.5"
                  style={{ background: "var(--indigo-dim)", color: "var(--indigo)", border: "1px solid rgba(45,212,191,0.2)" }}
                >
                  {f.badge}
                </span>
              </div>
              <p className="text-sm leading-relaxed" style={{ color: "var(--muted)" }}>{f.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ── Integrations ───────────────────────────────────────────── */
const INTEGRATIONS = [
  { name: "LangChain", sub: "LangGraph · Langflow", accent: "#10B981" },
  { name: "CrewAI", sub: "Multi-agent orchestration", accent: "#F59E0B" },
  { name: "Pydantic AI", sub: "Type-safe agents", accent: "#3B82F6" },
  { name: "LibreChat", sub: "Self-hosted chat", accent: "#8B5CF6" },
  { name: "OTLP", sub: "Any OpenTelemetry framework", accent: "#6366F1" },
  { name: "Claude · Cursor", sub: "Auto-discovered by init", accent: "#71717A" },
];

function Integrations() {
  return (
    <section className="py-24">
      <div className="max-w-6xl mx-auto px-6">
        <div className="text-center mb-14" data-reveal>
          <p className="section-label mb-3">Integrations</p>
          <h2
            className="font-bold tracking-tight"
            style={{ fontSize: "clamp(1.8rem, 3.5vw, 2.5rem)", fontFamily: "var(--font-geist-sans)" }}
          >
            <span className="gradient-text">Drop into any framework.</span>
          </h2>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 max-w-2xl mx-auto">
          {INTEGRATIONS.map((intg, i) => (
            <div
              key={i}
              data-reveal
              className="card p-5 text-center"
              style={{ transitionDelay: `${i * 40}ms` }}
            >
              <div
                className="font-bold text-lg mb-1"
                style={{ fontFamily: "var(--font-geist-sans)", color: intg.accent }}
              >
                {intg.name}
              </div>
              <div className="text-xs" style={{ color: "var(--muted)" }}>{intg.sub}</div>
            </div>
          ))}
        </div>

        {/* Complementary callout */}
        <div
          data-reveal
          className="mt-8 card-flat p-6 flex flex-col sm:flex-row items-start sm:items-center gap-4 max-w-2xl mx-auto"
        >
          <div className="flex-1">
            <p className="font-semibold text-sm mb-1" style={{ color: "var(--text)" }}>
              Use alongside Langfuse, LangWatch, or LangSmith
            </p>
            <p className="text-sm" style={{ color: "var(--muted)" }}>
              They trace the LLM reasoning layer (what the model decided). LangSight traces the action layer
              (what the agent called, what failed, what it cost). Different questions, same agent.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ── Self-hosted / OSS ─────────────────────────────────────── */
function SelfHosted() {
  return (
    <section className="py-24" style={{ background: "var(--bg-deep)" }}>
      <div className="max-w-6xl mx-auto px-6">
        <div className="text-center mb-16" data-reveal>
          <div
            className="inline-flex items-center gap-2 rounded-full px-4 py-1.5 text-xs font-medium mb-5"
            style={{ background: "var(--indigo-dim)", border: "1px solid rgba(45,212,191,0.2)", color: "var(--indigo)" }}
          >
            <GithubIcon className="w-3.5 h-3.5" /> BSL 1.1 · Self-host free forever
          </div>
          <h2
            className="font-bold tracking-tight"
            style={{ fontSize: "clamp(1.8rem, 3.5vw, 2.5rem)", fontFamily: "var(--font-geist-sans)" }}
          >
            <span className="gradient-text">Your data. Your infra.</span>
            <br />
            <span className="gradient-indigo">No vendor dependency.</span>
          </h2>
          <p className="mt-4 max-w-xl mx-auto text-lg" style={{ color: "var(--muted)" }}>
            Self-host on your own infrastructure. No data ever leaves your network.
            No paid tiers. No gated features. No usage limits.
          </p>
        </div>

        <div className="grid md:grid-cols-3 gap-5">
          {[
            {
              title: "Your data stays yours",
              body: "PostgreSQL + ClickHouse via docker compose up. Both fully under your control. No telemetry phoning home.",
            },
            {
              title: "No vendor lock-in",
              body: "BSL 1.1 — converts to Apache 2.0 after 4 years. Fork it, modify it, embed it. The only restriction: don't resell it as a hosted service.",
            },
            {
              title: "5-minute setup",
              body: "One script generates secrets, starts 5 containers, seeds demo data. You're looking at traces before your coffee is ready.",
            },
          ].map((p, i) => (
            <div key={i} data-reveal className="card p-7" style={{ transitionDelay: `${i * 80}ms` }}>
              <h3
                className="font-semibold text-lg mb-3"
                style={{ color: "var(--text)", fontFamily: "var(--font-geist-sans)" }}
              >
                {p.title}
              </h3>
              <p className="text-sm leading-relaxed" style={{ color: "var(--muted)" }}>{p.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ── CTA ────────────────────────────────────────────────────── */
function CTA() {
  return (
    <section className="py-24">
      <div className="max-w-3xl mx-auto px-6 text-center" data-reveal>
        <div className="card p-12 relative overflow-hidden">
          <div
            className="absolute inset-0 pointer-events-none"
            style={{ background: "linear-gradient(135deg, var(--indigo-dim) 0%, transparent 60%)" }}
          />
          <div className="relative">
            <h2
              className="font-bold tracking-tight mb-4"
              style={{ fontSize: "clamp(1.8rem, 4vw, 2.8rem)", fontFamily: "var(--font-geist-sans)" }}
            >
              <span className="gradient-text">Own the runtime layer</span>
              <br />
              <span className="gradient-indigo">of your agent systems.</span>
            </h2>
            <p className="text-lg mb-2" style={{ color: "var(--text)" }}>
              If your agents depend on MCP, LangSight keeps that dependency observable, reliable, and secure.
            </p>
            <p className="text-base mb-8 max-w-md mx-auto" style={{ color: "var(--muted)" }}>
              Trace what broke. Find what&apos;s expensive. Scan what&apos;s unsafe.
            </p>

            <div className="flex flex-wrap justify-center gap-4 mb-8">
              <a
                href="https://docs.langsight.dev/quickstart"
                className="text-base font-semibold px-7 py-3 rounded-lg flex items-center gap-2 transition-all hover:opacity-90 hover:-translate-y-px"
                style={{ background: "var(--indigo)", color: "white" }}
              >
                Start self-hosting →
              </a>
              <a
                href="https://github.com/LangSight/langsight"
                className="text-base font-semibold px-7 py-3 rounded-lg flex items-center gap-2 transition-all hover:-translate-y-px"
                style={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text)" }}
              >
                <GithubIcon className="w-4 h-4" /> Star on GitHub
              </a>
            </div>

            <div
              className="inline-flex items-center gap-3 rounded-xl px-5 py-3 mb-8"
              style={{ background: "var(--terminal-bg)", border: "1px solid var(--border)" }}
            >
              <span style={{ color: "var(--dimmer)", fontFamily: "var(--font-geist-mono)", fontSize: "0.85rem" }}>$</span>
              <span style={{ fontFamily: "var(--font-geist-mono)", fontSize: "0.85rem", color: "var(--code-text)" }}>
                pip install langsight && langsight init
              </span>
            </div>

            <div className="flex flex-wrap justify-center gap-6 text-sm" style={{ color: "var(--dimmer)" }}>
              <span>BSL 1.1 — self-host free</span>
              <span>No account needed</span>
              <span>docker compose up — full stack in 5 min</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ── Footer ─────────────────────────────────────────────────── */
function Footer() {
  const links = [
    { label: "Docs", href: "https://docs.langsight.dev" },
    { label: "GitHub", href: "https://github.com/LangSight/langsight" },
    { label: "PyPI", href: "https://pypi.org/project/langsight/" },
    { label: "Changelog", href: "https://github.com/LangSight/langsight/blob/main/CHANGELOG.md" },
    { label: "Security", href: "/security" },
    { label: "Pricing", href: "/pricing" },
  ];

  return (
    <footer className="py-10" style={{ borderTop: "1px solid var(--border)" }}>
      <div className="max-w-6xl mx-auto px-6 flex flex-col sm:flex-row items-center justify-between gap-4">
        <Logo />
        <div className="flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-sm">
          {links.map((l) => (
            <a
              key={l.label}
              href={l.href}
              className="transition-colors"
              style={{ color: "var(--muted)" }}
              onMouseEnter={(e) => (e.currentTarget.style.color = "var(--text)")}
              onMouseLeave={(e) => (e.currentTarget.style.color = "var(--muted)")}
            >
              {l.label}
            </a>
          ))}
        </div>
        <p className="text-xs" style={{ color: "var(--dimmer)" }}>
          BSL 1.1 · v0.2.0
        </p>
      </div>
    </footer>
  );
}

/* ── Page ───────────────────────────────────────────────────── */
export default function Home() {
  const { dark, toggle } = useTheme();
  useScrollReveal();

  return (
    <>
      <Nav dark={dark} toggle={toggle} />
      <main>
        <Hero />
        <Comparison />
        <Problem />
        <Solution />
        <HowItWorks />
        <Features />
        <Integrations />
        <SelfHosted />
        <CTA />
      </main>
      <Footer />
    </>
  );
}
