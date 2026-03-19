"use client";

import { useEffect, useRef, useState } from "react";

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

/* ── Logo ───────────────────────────────────────────────────── */
function Logo() {
  return (
    <a href="/" className="flex items-center gap-2.5 shrink-0">
      <div
        className="w-7 h-7 rounded-lg flex items-center justify-center"
        style={{ background: "var(--indigo)" }}
      >
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
    { label: "Docs", href: "https://lngsight.mintlify.app" },
    { label: "GitHub", href: "https://github.com/sumankalyan123/langsight" },
  ];

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
            href="https://lngsight.mintlify.app/quickstart"
            className="hidden sm:flex items-center gap-1.5 text-sm font-semibold px-4 py-2 rounded-lg transition-all hover:opacity-90 hover:-translate-y-px"
            style={{ background: "var(--indigo)", color: "white" }}
          >
            Get started →
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
            href="https://lngsight.mintlify.app/quickstart"
            className="block mt-2 px-3 py-2.5 rounded-lg text-sm font-semibold text-center"
            style={{ background: "var(--indigo)", color: "white" }}
          >
            Get started →
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
  { text: "├── 🔧 jira-mcp/get_issue        89ms  ✓", color: "var(--green)", delay: 940 },
  { text: "├── 🔧 postgres-mcp/query        42ms  ✓", color: "var(--green)", delay: 1100 },
  { text: "├──  → billing-agent          handoff", color: "var(--yellow)", delay: 1280 },
  { text: "│   ├── 🔧 crm-mcp/update_customer  120ms  ✓", color: "var(--green)", delay: 1460 },
  { text: "│   └── 🔧 slack-mcp/notify           —   ✗  timeout", color: "var(--red)", delay: 1640 },
  { text: "", delay: 1800 },
  { text: "Root cause: slack-mcp timed out at 14:32 UTC", color: "var(--orange)", bold: true, delay: 1960 },
  { text: "└── Fix: check SLACK_TIMEOUT config (currently 500ms)", color: "var(--dimmer)", small: true, delay: 2100 },
];

function AnimatedTerminal() {
  const [visible, setVisible] = useState(0);

  useEffect(() => {
    TERMINAL_LINES.forEach((line, i) => {
      setTimeout(() => setVisible(i + 1), line.delay + 800);
    });
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
          langsight · sessions
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
          className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[600px] rounded-full blur-[160px]"
          style={{ background: "var(--indigo-glow)" }}
        />
      </div>

      <div className="relative max-w-6xl mx-auto px-6 py-28 w-full">
        <div className="grid lg:grid-cols-2 gap-12 xl:gap-20 items-center">
          {/* Left: copy */}
          <div className="space-y-8">
            {/* Badge */}
            <div
              className="fade-up inline-flex items-center gap-2 rounded-full px-4 py-1.5 text-xs font-medium"
              style={{ background: "var(--indigo-dim)", border: "1px solid rgba(99,102,241,0.25)", color: "var(--indigo)" }}
            >
              <span className="w-1.5 h-1.5 rounded-full pulse-dot" style={{ background: "var(--indigo)" }} />
              v0.2.0 · Open source · Apache 2.0
            </div>

            {/* Headline */}
            <div className="space-y-1">
              <h1
                className="fade-up delay-1 font-bold leading-[1.04] tracking-tight"
                style={{ fontSize: "clamp(2.6rem, 5vw, 3.75rem)", fontFamily: "var(--font-geist-sans)" }}
              >
                <span className="gradient-text">Your agent broke.</span>
                <br />
                <span className="gradient-text">Here&apos;s exactly</span>
                <br />
                <span className="gradient-indigo">why.</span>
              </h1>
            </div>

            {/* Subheading */}
            <p
              className="fade-up delay-2 text-lg leading-relaxed max-w-md"
              style={{ color: "var(--muted)" }}
            >
              LangSight traces every tool call your AI agents make — MCP servers, HTTP APIs,
              sub-agents, the full multi-agent tree. Deep health monitoring and CVE scanning
              for MCP infrastructure built in.{" "}
              <strong style={{ color: "var(--text)" }}>Two lines to instrument. Self-host in 5 minutes.</strong>
            </p>

            {/* CTAs */}
            <div className="fade-up delay-3 flex flex-wrap gap-3">
              <a
                href="https://lngsight.mintlify.app/quickstart"
                className="text-sm font-semibold px-5 py-2.5 rounded-lg flex items-center gap-2 transition-all hover:opacity-90 hover:-translate-y-px"
                style={{ background: "var(--indigo)", color: "white" }}
              >
                Get started free →
              </a>
              <a
                href="https://github.com/sumankalyan123/langsight"
                className="text-sm font-semibold px-5 py-2.5 rounded-lg flex items-center gap-2 transition-all hover:-translate-y-px"
                style={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text)" }}
              >
                <GithubIcon className="w-4 h-4" />
                Star on GitHub
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
              <span>✓ LangChain · CrewAI · Pydantic AI · LibreChat</span>
              <span>✓ Postgres + ClickHouse · dual-backend architecture</span>
              <span>✓ 694 tests · 0 mypy errors</span>
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

/* ── Problem section ────────────────────────────────────────── */
const PROBLEMS = [
  {
    icon: "🔥",
    time: "2:17 AM",
    headline: "Agent down. Which tool broke it?",
    body: "Your orchestrator agent calls 12 tools across 4 MCP servers. Something returned bad data. Without traces, you spend hours replaying requests manually — in the dark.",
  },
  {
    icon: "🌳",
    time: "On every deploy",
    headline: "Sub-agent called what, exactly?",
    body: "Agent A delegated to Agent B which called Agent C. Which tool failed three levels deep? LangSight reconstructs the full multi-agent call tree automatically from parent_span_id.",
  },
  {
    icon: "💸",
    time: "End of month",
    headline: "$4,200 in unexpected tool costs",
    body: "A sub-agent retries a geocoding MCP 47× per session. At $0.005/call that's $0.24 per task. Nobody noticed until the invoice arrived. LangSight surfaces this in real time.",
  },
  {
    icon: "🛡",
    time: "Before it's too late",
    headline: "Is this MCP server safe?",
    body: "66% of community MCP servers have critical code smells. 8,000+ are exposed with no auth. Tool poisoning attacks are real and growing. You need automated scanning, not hope.",
  },
];

function Problem() {
  return (
    <section className="py-24" style={{ background: "var(--bg-deep)" }}>
      <div className="max-w-6xl mx-auto px-6">
        <div className="text-center mb-16" data-reveal>
          <p className="section-label mb-3">The problem</p>
          <h2
            className="font-bold tracking-tight"
            style={{ fontSize: "clamp(1.8rem, 3.5vw, 2.5rem)", fontFamily: "var(--font-geist-sans)" }}
          >
            <span className="gradient-text">AI agents fail silently.</span>
          </h2>
          <p className="mt-4 max-w-xl mx-auto text-base" style={{ color: "var(--muted)" }}>
            Modern agents chain dozens of tool calls across multiple servers and sub-agents.
            When something breaks, you have no idea where — or why.
          </p>
        </div>

        <div className="grid sm:grid-cols-2 gap-5">
          {PROBLEMS.map((p, i) => (
            <div key={i} data-reveal className="card p-7" style={{ transitionDelay: `${i * 70}ms` }}>
              <div className="flex items-start justify-between mb-4">
                <span className="text-2xl">{p.icon}</span>
                <span
                  className="text-xs px-2 py-0.5 rounded-full"
                  style={{ fontFamily: "var(--font-geist-mono)", background: "var(--surface-2)", color: "var(--dimmer)" }}
                >
                  {p.time}
                </span>
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

/* ── How it works ───────────────────────────────────────────── */
const STEPS = [
  {
    n: "01",
    sub: "30 seconds",
    title: "Install & discover",
    desc: "One command discovers all your MCP servers from Claude Desktop, Cursor, and VS Code configs. Writes .langsight.yaml automatically. No manual configuration.",
    code: `pip install langsight
langsight init

# Auto-discovered 4 MCP servers:
#   ✓ postgres-mcp    (stdio)
#   ✓ jira-mcp        (stdio)
#   ✓ slack-mcp       (sse)
#   ✓ filesystem-mcp  (stdio)`,
  },
  {
    n: "02",
    sub: "2 lines of code",
    title: "Instrument your agent",
    desc: "Wraps any MCP client. Every call_tool() is traced asynchronously — never blocks your agent. Fail-open: if LangSight is unreachable, your agent continues normally.",
    code: `from langsight.sdk import LangSightClient

client = LangSightClient(url="http://localhost:8000")

# Wrap your existing MCP session
traced = client.wrap(
    mcp_session,
    server_name="postgres-mcp",
    agent_name="support-agent",
)

# Use exactly as before — all calls traced
result = await traced.call_tool("query", {...})`,
  },
  {
    n: "03",
    sub: "real-time",
    title: "See everything",
    desc: "Full session traces, multi-agent trees, MCP health status, security findings, cost attribution, anomaly detection, and AI root cause analysis — in the terminal and the dashboard.",
    code: `langsight sessions          # all recent sessions
langsight sessions --id X   # full trace for session
langsight mcp-health        # server health status
langsight security-scan     # CVE + OWASP + poisoning
langsight costs --hours 24  # cost breakdown
langsight investigate       # AI root cause analysis`,
  },
];

function HowItWorks() {
  return (
    <section className="py-24">
      <div className="max-w-6xl mx-auto px-6">
        <div className="text-center mb-16" data-reveal>
          <p className="section-label mb-3">How it works</p>
          <h2
            className="font-bold tracking-tight"
            style={{ fontSize: "clamp(1.8rem, 3.5vw, 2.5rem)", fontFamily: "var(--font-geist-sans)" }}
          >
            <span className="gradient-text">Zero to full observability</span>
            <br />
            <span className="gradient-indigo">in 5 minutes.</span>
          </h2>
        </div>

        <div className="space-y-20">
          {STEPS.map((step, i) => (
            <div
              key={i}
              data-reveal
              className={`grid lg:grid-cols-2 gap-10 xl:gap-16 items-center`}
              style={{ transitionDelay: `${i * 80}ms` }}
            >
              <div className={i % 2 === 1 ? "lg:order-2" : ""}>
                <div
                  className="font-bold mb-3 select-none"
                  style={{ fontFamily: "var(--font-geist-mono)", fontSize: "3.5rem", color: "var(--border)", lineHeight: 1 }}
                >
                  {step.n}
                </div>
                <p className="section-label mb-2">{step.sub}</p>
                <h3
                  className="font-bold text-2xl mb-4"
                  style={{ color: "var(--text)", fontFamily: "var(--font-geist-sans)" }}
                >
                  {step.title}
                </h3>
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

/* ── Features ───────────────────────────────────────────────── */
const FEATURES = [
  {
    icon: "🔭",
    badge: "All tools",
    title: "Agent Session Traces",
    desc: "Every tool call in every session — MCP servers, HTTP APIs, Python functions — with latency, status, input args, output, and errors. The full picture, not just LLM logs.",
    hot: true,
  },
  {
    icon: "🌳",
    badge: "Unique",
    title: "Multi-Agent Call Trees",
    desc: "parent_span_id links sub-agent calls to the handoff that spawned them. See the exact path from orchestrator to leaf tool, reconstructed automatically across any depth.",
    hot: true,
  },
  {
    icon: "📽",
    badge: "New in v0.2",
    title: "Session Replay",
    desc: "Re-execute any session against live MCP servers using stored input args. Side-by-side comparison of two sessions shows exactly what changed between runs.",
    hot: true,
  },
  {
    icon: "💰",
    badge: "ClickHouse",
    title: "Cost Attribution",
    desc: "Token-based pricing for LLM calls. Per-tool rules for MCP calls. See total cost per session, per agent, per tool. Spot which sub-agent burns 80% of your budget.",
  },
  {
    icon: "♥",
    badge: "MCP only",
    title: "MCP Health Monitoring",
    desc: "Proactive health checks, schema drift detection, and Slack alerts on DOWN/recovery transitions — before your agents start failing.",
  },
  {
    icon: "🛡",
    badge: "MCP only",
    title: "MCP Security Scanning",
    desc: "CVE detection, all 10 OWASP MCP checks, tool poisoning detection (injection phrases, hidden unicode, base64 encoded instructions), and auth gap analysis.",
  },
  {
    icon: "📊",
    badge: "New in v0.2",
    title: "Anomaly Detection",
    desc: "Z-score analysis against 7-day ClickHouse baseline. Warning at |z|≥2, critical at |z|≥3. Guards against false positives with minimum standard deviation thresholds.",
  },
  {
    icon: "🎯",
    badge: "New in v0.2",
    title: "Agent SLO Tracking",
    desc: "Define success_rate and latency_p99 SLOs per agent. Evaluate against real session data. Get alerted before you breach your availability targets.",
  },
  {
    icon: "🤖",
    badge: "4 LLMs",
    title: "AI Root Cause Analysis",
    desc: "langsight investigate sends health evidence to Claude, GPT-4o, Gemini, or local Ollama and returns prioritised remediation steps. Rule-based fallback without a key.",
  },
];

function Features() {
  return (
    <section className="py-24" style={{ background: "var(--bg-deep)" }}>
      <div className="max-w-6xl mx-auto px-6">
        <div className="text-center mb-16" data-reveal>
          <p className="section-label mb-3">Features</p>
          <h2
            className="font-bold tracking-tight"
            style={{ fontSize: "clamp(1.8rem, 3.5vw, 2.5rem)", fontFamily: "var(--font-geist-sans)" }}
          >
            <span className="gradient-text">Observability for everything</span>
            <br />
            <span className="gradient-text">your agents call.</span>
          </h2>
          <p className="mt-4 max-w-xl mx-auto" style={{ color: "var(--muted)" }}>
            Instrument once at the agent level. Every tool type is traced. MCP servers get proactive
            health checks and security scanning on top — because the protocol makes it inspectable.
          </p>
        </div>

        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {FEATURES.map((f, i) => (
            <div
              key={i}
              data-reveal
              className="card p-7 relative"
              style={{ transitionDelay: `${i * 50}ms` }}
            >
              {f.hot && (
                <div
                  className="absolute top-4 right-4 text-[10px] px-2 py-0.5 rounded-full font-semibold"
                  style={{ background: "var(--indigo)", color: "white" }}
                >
                  {f.badge}
                </div>
              )}
              <div className="text-2xl mb-4">{f.icon}</div>
              <div className="flex items-start gap-2 mb-3">
                <h3
                  className="font-semibold text-base flex-1"
                  style={{ color: "var(--text)", fontFamily: "var(--font-geist-sans)" }}
                >
                  {f.title}
                </h3>
                {!f.hot && (
                  <span
                    className="shrink-0 text-[10px] rounded-full px-2 py-0.5 mt-0.5"
                    style={{ background: "var(--indigo-dim)", color: "var(--indigo)", border: "1px solid rgba(99,102,241,0.2)" }}
                  >
                    {f.badge}
                  </span>
                )}
              </div>
              <p className="text-sm leading-relaxed" style={{ color: "var(--muted)" }}>{f.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ── Personas ───────────────────────────────────────────────── */
const PERSONAS = [
  {
    role: "AI/ML Engineer",
    name: "Mark",
    tagline: "Gets paged when the agent fails",
    pain: "Spends 30% of debugging time figuring out which tool caused the failure. Can't tell if it's the LLM's choice or the tool's response.",
    wins: [
      "Session trace shows the exact tool that returned bad data at 14:32 UTC",
      "Schema drift alert fires before agents start hallucinating column names",
      "MTTR drops from 3 hours to 15 minutes",
    ],
    commands: ["langsight sessions --id <id>", "langsight investigate", "langsight mcp-health"],
  },
  {
    role: "Platform Engineer",
    name: "Marcus",
    tagline: "Owns the MCP infrastructure for 40 engineers",
    pain: "35 MCP servers with no standardised health checks. Can't answer which versions are running or catch schema changes before they break agents.",
    wins: [
      "Fleet health dashboard: every server status, version, and latency at a glance",
      "Schema drift detection catches breaking changes before deploy",
      "Achieves 99.9% MCP uptime with proactive alerting",
    ],
    commands: ["langsight mcp-health --all", "langsight serve", "langsight monitor"],
  },
  {
    role: "Security Engineer",
    name: "Aisha",
    tagline: "Responsible for AI system security and compliance",
    pain: "22 community MCP servers with no automated CVE scanning. Tool poisoning attacks moving from theoretical to practical.",
    wins: [
      "Full OWASP MCP Top 10 audit with actionable remediation steps",
      "Tool poisoning detection: alerts on hidden unicode, injected instructions, base64 payloads",
      "Auth audit: which servers have auth, what type, what gaps exist",
    ],
    commands: ["langsight security-scan", "langsight security-scan --ci", "langsight security-scan --format json"],
  },
  {
    role: "Engineering Lead",
    name: "David",
    tagline: "Needs to report AI reliability to the board",
    pain: "Has LLM-level metrics (token costs, latency) but nothing at the tool level. Cannot answer 'what is the reliability of our AI products?' with data.",
    wins: [
      "Cost attribution per tool, per team, per session — identifies $20K/month savings",
      "SLO tracking: are we meeting the 99.5% agent availability target?",
      "Quarterly AI reliability report with tool-level granularity",
    ],
    commands: ["langsight costs --hours 720", "uv run langsight serve (dashboard)"],
  },
];

function Personas() {
  const [active, setActive] = useState(0);
  const p = PERSONAS[active];

  return (
    <section className="py-24">
      <div className="max-w-6xl mx-auto px-6">
        <div className="text-center mb-12" data-reveal>
          <p className="section-label mb-3">Built for your team</p>
          <h2
            className="font-bold tracking-tight"
            style={{ fontSize: "clamp(1.8rem, 3.5vw, 2.5rem)", fontFamily: "var(--font-geist-sans)" }}
          >
            <span className="gradient-text">One tool. Every role.</span>
          </h2>
        </div>

        {/* Tabs */}
        <div
          data-reveal
          className="flex flex-wrap gap-2 justify-center mb-8 p-1.5 rounded-xl w-fit mx-auto"
          style={{ background: "var(--surface-2)", border: "1px solid var(--border)" }}
        >
          {PERSONAS.map((persona, i) => (
            <button
              key={i}
              onClick={() => setActive(i)}
              className={`persona-tab${active === i ? " active" : ""}`}
            >
              {persona.role}
            </button>
          ))}
        </div>

        {/* Card */}
        <div data-reveal className="card-flat p-8 grid md:grid-cols-2 gap-8">
          <div>
            <p className="section-label mb-1">{p.role}</p>
            <h3
              className="font-bold text-2xl mb-1"
              style={{ color: "var(--text)", fontFamily: "var(--font-geist-sans)" }}
            >
              {p.name}
            </h3>
            <p className="text-sm mb-5" style={{ color: "var(--muted)" }}>{p.tagline}</p>

            <div
              className="rounded-lg p-4 mb-5 text-sm"
              style={{ background: "var(--red-dim)", border: "1px solid rgba(239,68,68,0.15)", color: "var(--muted)" }}
            >
              <span className="font-semibold" style={{ color: "var(--red)" }}>Pain: </span>
              {p.pain}
            </div>

            <div className="space-y-2">
              {p.wins.map((win, i) => (
                <div key={i} className="flex items-start gap-2 text-sm">
                  <span style={{ color: "var(--green)" }} className="mt-0.5 shrink-0">✓</span>
                  <span style={{ color: "var(--muted)" }}>{win}</span>
                </div>
              ))}
            </div>
          </div>

          <div>
            <p className="text-xs font-medium mb-3" style={{ color: "var(--dimmer)" }}>Key commands</p>
            <div className="terminal">
              <div className="terminal-bar">
                <div className="terminal-dot" style={{ background: "#EF444460" }} />
                <div className="terminal-dot" style={{ background: "#EAB30860" }} />
                <div className="terminal-dot" style={{ background: "#22C55E60" }} />
              </div>
              <div className="p-5 space-y-2">
                {p.commands.map((cmd, i) => (
                  <div
                    key={i}
                    className="text-sm"
                    style={{ fontFamily: "var(--font-geist-mono)", color: "var(--code-text)" }}
                  >
                    <span style={{ color: "var(--dimmer)" }}>$ </span>{cmd}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ── Integrations ───────────────────────────────────────────── */
const INTEGRATIONS = [
  { name: "LangChain", sub: "Langflow · LangGraph", accent: "#10B981" },
  { name: "CrewAI", sub: "Multi-agent orchestration", accent: "#F59E0B" },
  { name: "Pydantic AI", sub: "Type-safe agents", accent: "#3B82F6" },
  { name: "LibreChat", sub: "Self-hosted chat", accent: "#8B5CF6" },
  { name: "OpenWebUI", sub: "Local LLM UI", accent: "#EC4899" },
  { name: "OTLP", sub: "Any OpenTelemetry framework", accent: "#6366F1" },
  { name: "Claude Desktop", sub: "Auto-discovered by init", accent: "#71717A" },
  { name: "Cursor · VS Code", sub: "Auto-discovered by init", accent: "#71717A" },
];

function Integrations() {
  return (
    <section className="py-24" style={{ background: "var(--bg-deep)" }}>
      <div className="max-w-6xl mx-auto px-6">
        <div className="text-center mb-14" data-reveal>
          <p className="section-label mb-3">Integrations</p>
          <h2
            className="font-bold tracking-tight"
            style={{ fontSize: "clamp(1.8rem, 3.5vw, 2.5rem)", fontFamily: "var(--font-geist-sans)" }}
          >
            <span className="gradient-text">Works with every AI framework</span>
          </h2>
          <p className="mt-4 max-w-lg mx-auto" style={{ color: "var(--muted)" }}>
            One callback or two lines of SDK code. Drop into any framework without changing the rest of your agent.
          </p>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
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

        {/* Langfuse complementary callout */}
        <div
          data-reveal
          className="mt-8 card-flat p-6 flex flex-col sm:flex-row items-start sm:items-center gap-4"
        >
          <div
            className="shrink-0 w-10 h-10 rounded-xl flex items-center justify-center text-lg"
            style={{ background: "var(--indigo-dim)", border: "1px solid rgba(99,102,241,0.2)" }}
          >
            🤝
          </div>
          <div className="flex-1">
            <p className="font-semibold text-sm mb-1" style={{ color: "var(--text)" }}>
              Works alongside Langfuse — not instead of it
            </p>
            <p className="text-sm" style={{ color: "var(--muted)" }}>
              Langfuse traces the LLM reasoning layer (what the model decided). LangSight traces the action layer
              (what the agent called, in what order, what failed, what it cost). They answer different questions.
              Use both together for complete observability.
            </p>
          </div>
          <a
            href="https://lngsight.mintlify.app/sdk/integrations/langfuse"
            className="shrink-0 text-xs font-semibold px-3 py-1.5 rounded-lg transition-all hover:opacity-80"
            style={{ background: "var(--indigo-dim)", color: "var(--indigo)", border: "1px solid rgba(99,102,241,0.2)" }}
          >
            Integration guide →
          </a>
        </div>
      </div>
    </section>
  );
}

/* ── Open Source / Compare ──────────────────────────────────── */
const OSS_PILLARS = [
  {
    icon: "🔒",
    title: "Your data stays yours",
    body: "Self-host on your own infrastructure. No data ever leaves your network. PostgreSQL + ClickHouse via docker compose up -d — both fully under your control.",
  },
  {
    icon: "🚫",
    title: "No vendor lock-in",
    body: "Apache 2.0. Fork it, embed it in your product, modify it without permission. We will never change the license or add closed-source features.",
  },
  {
    icon: "🌍",
    title: "Community-driven",
    body: "Every feature was shaped by engineers running real agents. File an issue, submit a PR, or join the discussion — this is your project too.",
  },
];

const COMPARE: { feature: string; ls: boolean | string; datadog: boolean | string; langfuse: boolean | string }[] = [
  { feature: "Agent action traces",             ls: true,  datadog: true,  langfuse: "partial" },
  { feature: "Multi-agent tree reconstruction", ls: true,  datadog: false, langfuse: false },
  { feature: "Session replay & comparison",     ls: true,  datadog: false, langfuse: false },
  { feature: "Anomaly detection (z-score)",     ls: true,  datadog: true,  langfuse: false },
  { feature: "Agent SLO tracking",              ls: true,  datadog: true,  langfuse: false },
  { feature: "MCP server health checks",        ls: true,  datadog: false, langfuse: false },
  { feature: "CVE + OWASP security scanning",   ls: true,  datadog: false, langfuse: false },
  { feature: "Tool poisoning detection",        ls: true,  datadog: false, langfuse: false },
  { feature: "Schema drift detection",          ls: true,  datadog: false, langfuse: false },
  { feature: "Self-hostable",                   ls: true,  datadog: false, langfuse: true  },
  { feature: "Open source (Apache 2.0)",        ls: true,  datadog: false, langfuse: true  },
  { feature: "Free forever",                    ls: true,  datadog: false, langfuse: "partial" },
];

function Cell({ v }: { v: boolean | string }) {
  if (v === true)    return <span className="text-base" style={{ color: "var(--green)" }}>✓</span>;
  if (v === false)   return <span className="text-base" style={{ color: "var(--dimmer)" }}>✗</span>;
  return <span className="text-base" style={{ color: "var(--yellow)" }}>~</span>;
}

function OpenSource() {
  return (
    <section className="py-24">
      <div className="max-w-6xl mx-auto px-6">
        <div className="text-center mb-16" data-reveal>
          <div
            className="inline-flex items-center gap-2 rounded-full px-4 py-1.5 text-xs font-medium mb-5"
            style={{ background: "var(--indigo-dim)", border: "1px solid rgba(99,102,241,0.2)", color: "var(--indigo)" }}
          >
            <GithubIcon className="w-3.5 h-3.5" /> Apache 2.0 · Fully Open Source
          </div>
          <h2
            className="font-bold tracking-tight"
            style={{ fontSize: "clamp(1.8rem, 3.5vw, 2.5rem)", fontFamily: "var(--font-geist-sans)" }}
          >
            <span className="gradient-text">Built in the open.</span>
            <br />
            <span className="gradient-indigo">Free to use, forever.</span>
          </h2>
          <p className="mt-4 max-w-xl mx-auto text-lg" style={{ color: "var(--muted)" }}>
            Not &ldquo;open core&rdquo; — the CLI, SDK, API, all integrations, and every feature on this page is
            fully open source. No paid tiers. No gated features. No surprises.
          </p>
          <a
            href="https://github.com/sumankalyan123/langsight"
            className="mt-6 inline-flex items-center gap-2 font-semibold text-sm px-5 py-2.5 rounded-lg transition-all hover:opacity-90 hover:-translate-y-px"
            style={{ background: "var(--surface-2)", border: "1px solid var(--border)", color: "var(--text)" }}
          >
            <GithubIcon className="w-4 h-4" /> sumankalyan123/langsight
            <span
              className="ml-1 text-xs px-2 py-0.5 rounded-full"
              style={{ fontFamily: "var(--font-geist-mono)", background: "var(--indigo-dim)", color: "var(--indigo)" }}
            >
              Apache 2.0
            </span>
          </a>
        </div>

        <div className="grid md:grid-cols-3 gap-5 mb-16">
          {OSS_PILLARS.map((p, i) => (
            <div key={i} data-reveal className="card p-7" style={{ transitionDelay: `${i * 80}ms` }}>
              <div className="text-3xl mb-4">{p.icon}</div>
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

        {/* Compare table */}
        <div data-reveal className="card-flat overflow-hidden">
          <div
            className="px-6 py-4 flex items-center justify-between"
            style={{ borderBottom: "1px solid var(--border)", background: "var(--surface-2)" }}
          >
            <h3
              className="font-semibold text-base"
              style={{ color: "var(--text)", fontFamily: "var(--font-geist-sans)" }}
            >
              How LangSight compares
            </h3>
            <span className="text-xs" style={{ color: "var(--dimmer)" }}>✓ yes · ✗ no · ~ partial</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border)", background: "var(--surface-2)" }}>
                  <th className="text-left px-6 py-3 font-medium" style={{ color: "var(--muted)" }}>Feature</th>
                  <th className="px-6 py-3 text-center font-bold" style={{ color: "var(--indigo)" }}>LangSight</th>
                  <th className="px-6 py-3 text-center font-medium" style={{ color: "var(--muted)" }}>Datadog</th>
                  <th className="px-6 py-3 text-center font-medium" style={{ color: "var(--muted)" }}>Langfuse *</th>
                </tr>
              </thead>
              <tbody>
                {COMPARE.map((row, i) => (
                  <tr
                    key={i}
                    style={{ borderBottom: i < COMPARE.length - 1 ? "1px solid var(--border-dim)" : "none" }}
                  >
                    <td className="px-6 py-3" style={{ color: "var(--text)" }}>{row.feature}</td>
                    <td className="px-6 py-3 text-center"><Cell v={row.ls} /></td>
                    <td className="px-6 py-3 text-center"><Cell v={row.datadog} /></td>
                    <td className="px-6 py-3 text-center"><Cell v={row.langfuse} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="px-6 py-3 text-xs" style={{ color: "var(--dimmer)", borderTop: "1px solid var(--border-dim)" }}>
            * Langfuse is complementary, not competing — it traces LLM reasoning; LangSight traces agent actions. Use both together.
          </div>
        </div>
      </div>
    </section>
  );
}

/* ── CTA ────────────────────────────────────────────────────── */
function CTA() {
  return (
    <section className="py-24" style={{ background: "var(--bg-deep)" }}>
      <div className="max-w-3xl mx-auto px-6 text-center" data-reveal>
        <div className="card p-12 relative overflow-hidden">
          <div
            className="absolute inset-0 pointer-events-none"
            style={{ background: "linear-gradient(135deg, var(--indigo-dim) 0%, transparent 60%)" }}
          />
          <div className="relative">
            <div className="text-5xl mb-6">⚡</div>
            <h2
              className="font-bold tracking-tight mb-3"
              style={{ fontSize: "clamp(1.8rem, 4vw, 2.8rem)", fontFamily: "var(--font-geist-sans)" }}
            >
              <span className="gradient-indigo">Start in 5 minutes.</span>
            </h2>
            <p className="text-lg font-semibold mb-2" style={{ color: "var(--text)" }}>
              Full observability for your AI agents — free, open source, forever.
            </p>
            <p className="text-base mb-8 max-w-md mx-auto" style={{ color: "var(--muted)" }}>
              Install in 30 seconds. Two lines to instrument. See exactly what your agents call,
              how long each tool takes, and what everything costs.
            </p>

            <div className="flex flex-wrap justify-center gap-4 mb-8">
              <a
                href="https://lngsight.mintlify.app/quickstart"
                className="text-base font-semibold px-7 py-3 rounded-lg flex items-center gap-2 transition-all hover:opacity-90 hover:-translate-y-px"
                style={{ background: "var(--indigo)", color: "white" }}
              >
                Get started free →
              </a>
              <a
                href="https://github.com/sumankalyan123/langsight"
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
                pip install langsight
              </span>
              <span style={{ color: "var(--dimmer)", fontFamily: "var(--font-geist-mono)", fontSize: "0.85rem" }}>&amp;&amp;</span>
              <span style={{ fontFamily: "var(--font-geist-mono)", fontSize: "0.85rem", color: "var(--code-text)" }}>
                langsight init
              </span>
            </div>

            <div className="flex flex-wrap justify-center gap-6 text-sm" style={{ color: "var(--dimmer)" }}>
              <span>✓ Apache 2.0 — free forever</span>
              <span>✓ No account needed</span>
              <span>✓ docker compose up -d — full stack in &lt;5 min</span>
              <span>✓ 694 tests passing</span>
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
    { label: "Docs", href: "https://lngsight.mintlify.app" },
    { label: "GitHub", href: "https://github.com/sumankalyan123/langsight" },
    { label: "PyPI", href: "https://pypi.org/project/langsight/" },
    { label: "Changelog", href: "https://github.com/sumankalyan123/langsight/blob/main/CHANGELOG.md" },
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
          Apache 2.0 · v0.2.0
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
        <Problem />
        <HowItWorks />
        <Features />
        <Personas />
        <Integrations />
        <OpenSource />
        <CTA />
      </main>
      <Footer />
    </>
  );
}
