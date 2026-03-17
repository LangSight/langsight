"use client";

import { useEffect, useRef, useState } from "react";

// ─────────────────────────────────────────────────────────────────────────────
// Navigation
// ─────────────────────────────────────────────────────────────────────────────
function Nav() {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 20);
    window.addEventListener("scroll", onScroll);
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <nav
      className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${
        scrolled
          ? "bg-[#09090B]/90 backdrop-blur-md border-b border-[#27272A]"
          : "bg-transparent"
      }`}
    >
      <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
        <a href="#" className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-lg bg-indigo-500 flex items-center justify-center">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M2 7h10M7 2v10M4 4l6 6M10 4l-6 6" stroke="white" strokeWidth="1.5" strokeLinecap="round"/>
            </svg>
          </div>
          <span className="font-display font-bold text-white text-lg tracking-tight">LangSight</span>
        </a>

        <div className="flex items-center gap-6">
          <a href="https://lngsight.mintlify.app" className="text-sm text-zinc-400 hover:text-white transition-colors">Docs</a>
          <a href="https://github.com/sumankalyan123/langsight" className="text-sm text-zinc-400 hover:text-white transition-colors">GitHub</a>
          <a
            href="https://pypi.org/project/langsight/"
            className="hidden sm:flex items-center gap-2 bg-[#18181B] border border-[#27272A] rounded-lg px-3 py-1.5 text-xs font-mono text-zinc-300 hover:border-indigo-500/50 transition-colors"
          >
            <span className="text-zinc-500">$</span>
            pip install langsight
          </a>
        </div>
      </div>
    </nav>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Terminal animation
// ─────────────────────────────────────────────────────────────────────────────
const TERMINAL_LINES = [
  { text: "$ langsight sessions --id sess-abc123", color: "text-zinc-400", delay: 0 },
  { text: "", delay: 200 },
  { text: "Trace: sess-abc123  (support-agent)", color: "text-white font-semibold", delay: 400 },
  { text: "3 tool calls · 1 failed · 1,371ms total", color: "text-zinc-500 text-xs", delay: 500 },
  { text: "", delay: 600 },
  { text: "sess-abc123", color: "text-indigo-400", delay: 700 },
  { text: "├── 🔧 jira-mcp/get_issue       89ms  ✓", color: "text-emerald-400", delay: 900 },
  { text: "├── 🔧 confluence-mcp/search  1,240ms  ✓", color: "text-emerald-400", delay: 1100 },
  { text: "├──  → billing-agent          handoff", color: "text-yellow-400", delay: 1300 },
  { text: "│   ├── 🔧 crm-mcp/update      120ms  ✓", color: "text-emerald-400", delay: 1500 },
  { text: "│   └── 🔧 slack-mcp/notify       —   ✗  timeout", color: "text-red-400", delay: 1700 },
  { text: "", delay: 1900 },
  { text: "Total: $0.023  |  2 agents  |  1 failure", color: "text-zinc-400 text-xs", delay: 2000 },
];

function TerminalHero() {
  const [visibleLines, setVisibleLines] = useState<number>(0);

  useEffect(() => {
    TERMINAL_LINES.forEach((line, i) => {
      setTimeout(() => setVisibleLines(i + 1), line.delay + 600);
    });
  }, []);

  return (
    <div className="terminal glow-indigo max-w-2xl w-full">
      <div className="terminal-bar">
        <div className="terminal-dot bg-red-500/70" />
        <div className="terminal-dot bg-yellow-500/70" />
        <div className="terminal-dot bg-green-500/70" />
        <span className="ml-3 text-xs text-zinc-500 font-mono">langsight — sessions</span>
      </div>
      <div className="p-5 font-mono text-sm space-y-0.5 min-h-[280px]">
        {TERMINAL_LINES.slice(0, visibleLines).map((line, i) => (
          <div
            key={i}
            className={`term-line ${line.color ?? "text-zinc-300"}`}
            style={{ animationDelay: `0ms` }}
          >
            {line.text || "\u00A0"}
          </div>
        ))}
        {visibleLines < TERMINAL_LINES.length && (
          <span className="inline-block w-2 h-4 bg-indigo-400 animate-blink" />
        )}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Hero
// ─────────────────────────────────────────────────────────────────────────────
function Hero() {
  return (
    <section className="relative min-h-screen flex flex-col items-center justify-center grid-bg overflow-hidden pt-16">
      {/* Radial glow */}
      <div className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] rounded-full bg-indigo-500/5 blur-[120px] pointer-events-none" />

      <div className="relative max-w-6xl mx-auto px-6 py-24 flex flex-col items-center text-center gap-8">
        {/* Badge */}
        <div className="animate-fade-up flex items-center gap-2 bg-indigo-500/10 border border-indigo-500/20 rounded-full px-4 py-1.5 text-xs text-indigo-400">
          <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-pulse" />
          Open source · Apache 2.0 · v0.1.0 on PyPI
        </div>

        {/* Headline */}
        <h1 className="animate-fade-up delay-100 font-display text-5xl sm:text-6xl lg:text-7xl font-bold leading-[1.05] tracking-tight max-w-4xl">
          <span className="gradient-text">See everything</span>
          <br />
          <span className="text-zinc-400">your agents call.</span>
        </h1>

        {/* Subhead */}
        <p className="animate-fade-up delay-200 text-lg text-zinc-400 max-w-xl leading-relaxed">
          Traces, costs, health checks, and security scanning for MCP servers,
          HTTP APIs, and multi-agent workflows. One SDK, two lines.
        </p>

        {/* CTAs */}
        <div className="animate-fade-up delay-300 flex flex-wrap items-center justify-center gap-3">
          <a
            href="https://github.com/sumankalyan123/langsight"
            className="flex items-center gap-2 bg-white text-black font-semibold text-sm rounded-lg px-5 py-2.5 hover:bg-zinc-100 transition-colors"
          >
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
            </svg>
            View on GitHub
          </a>
          <a
            href="https://lngsight.mintlify.app"
            className="flex items-center gap-2 bg-[#18181B] border border-[#27272A] text-white font-semibold text-sm rounded-lg px-5 py-2.5 hover:border-indigo-500/50 transition-colors"
          >
            Read the Docs →
          </a>
          <div className="flex items-center gap-2 bg-[#0D0D10] border border-[#27272A] rounded-lg px-4 py-2.5 text-xs font-mono text-zinc-400">
            pip install langsight
          </div>
        </div>

        {/* Terminal */}
        <div className="animate-fade-up delay-400 w-full mt-4">
          <TerminalHero />
        </div>
      </div>
    </section>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Problem
// ─────────────────────────────────────────────────────────────────────────────
const PROBLEMS = [
  {
    icon: "❓",
    q: "Which tool failed?",
    a: "Your agent returned a wrong answer. Was it the LLM, the prompt, or one of the 12 MCP tools in the chain? Without LangSight, you spend hours replaying requests manually.",
  },
  {
    icon: "🔍",
    q: "What did my agent call?",
    a: "You can see the LLM's output but not which tools it touched, in what order, how long each took, or which ones silently failed.",
  },
  {
    icon: "💸",
    q: "What did it cost?",
    a: "An agent retries a geocoding tool 47 times per task. At $0.005/call, a single session costs $0.23 in tool calls alone. Nobody tracks this.",
  },
];

function Problem() {
  return (
    <section className="py-24 max-w-6xl mx-auto px-6">
      <div className="text-center mb-16" data-reveal>
        <p className="text-xs text-indigo-400 font-mono uppercase tracking-widest mb-3">The problem</p>
        <h2 className="font-display text-3xl sm:text-4xl font-bold gradient-text">
          AI agents are flying blind
        </h2>
      </div>
      <div className="grid md:grid-cols-3 gap-5">
        {PROBLEMS.map((p, i) => (
          <div
            key={i}
            data-reveal
            className="feature-card bg-[#18181B] border border-[#27272A] rounded-2xl p-7 relative overflow-hidden"
            style={{ transitionDelay: `${i * 100}ms` }}
          >
            <div className="text-3xl mb-4">{p.icon}</div>
            <h3 className="font-display text-xl font-bold text-white mb-3">{p.q}</h3>
            <p className="text-zinc-400 text-sm leading-relaxed">{p.a}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Features
// ─────────────────────────────────────────────────────────────────────────────
const FEATURES = [
  {
    icon: "♥",
    title: "MCP Health Monitoring",
    desc: "Continuous availability checks, latency tracking, and schema drift detection. Get alerted when a tool goes DOWN before your agents start failing.",
    badge: "MCP only",
  },
  {
    icon: "🛡",
    title: "Security Scanning",
    desc: "CVE detection via OSV API, OWASP MCP Top 10 audit, tool poisoning detection, and auth gap analysis. No other tool does this.",
    badge: "MCP only",
  },
  {
    icon: "🔭",
    title: "Agent Session Traces",
    desc: "See every tool call your agent made in order — MCP servers, HTTP APIs, functions — with latency, status, and error details.",
    badge: "All tool types",
  },
  {
    icon: "🌳",
    title: "Multi-Agent Tree",
    desc: "When Agent A hands off to Agent B, LangSight reconstructs the full call tree using parent_span_id — exactly like distributed tracing.",
    badge: "New in 0.1.0",
  },
  {
    icon: "🔬",
    title: "AI Root Cause Analysis",
    desc: "langsight investigate sends health evidence to Claude, GPT-4o, Gemini, or Ollama and returns a prioritised remediation report.",
    badge: "4 providers",
  },
  {
    icon: "💰",
    title: "Cost Attribution",
    desc: "Configurable per-tool pricing rules. See exactly what each session cost, which tool is burning your budget, and when costs spike.",
    badge: "ClickHouse",
  },
];

function Features() {
  return (
    <section className="py-24 bg-[#0D0D10]">
      <div className="max-w-6xl mx-auto px-6">
        <div className="text-center mb-16" data-reveal>
          <p className="text-xs text-indigo-400 font-mono uppercase tracking-widest mb-3">Features</p>
          <h2 className="font-display text-3xl sm:text-4xl font-bold gradient-text">
            Full-stack agent observability
          </h2>
          <p className="mt-4 text-zinc-400 max-w-lg mx-auto">
            Instrument once at the agent level. Every tool type is traced.
            MCP servers get proactive health checks and security scanning on top.
          </p>
        </div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {FEATURES.map((f, i) => (
            <div
              key={i}
              data-reveal
              className="feature-card bg-[#18181B] border border-[#27272A] rounded-2xl p-7"
              style={{ transitionDelay: `${i * 80}ms` }}
            >
              <div className="text-2xl mb-4">{f.icon}</div>
              <div className="flex items-start justify-between gap-3 mb-3">
                <h3 className="font-display text-lg font-bold text-white leading-snug">{f.title}</h3>
                <span className="shrink-0 text-xs bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 rounded-full px-2 py-0.5 mt-0.5">
                  {f.badge}
                </span>
              </div>
              <p className="text-zinc-400 text-sm leading-relaxed">{f.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// How it works
// ─────────────────────────────────────────────────────────────────────────────
const STEPS = [
  {
    num: "01",
    title: "Install",
    code: "pip install langsight\nlangsight init",
    desc: "Auto-discovers your MCP servers from Claude Desktop, Cursor, and VS Code. Generates .langsight.yaml in 30 seconds.",
  },
  {
    num: "02",
    title: "Instrument",
    code: `from langsight.sdk import LangSightClient\n\nclient = LangSightClient(url="http://localhost:8000")\ntraced = client.wrap(mcp_session, server_name="my-mcp")`,
    desc: "Two lines. Every call_tool() is traced, fire-and-forget. Fail-open — if LangSight is unreachable, your agent keeps working.",
  },
  {
    num: "03",
    title: "Observe",
    code: "langsight sessions\nlangsight sessions --id sess-abc\nlangsight mcp-health\nlangsight security-scan",
    desc: "Full agent session traces, multi-agent trees, health dashboards, and security findings — all in the terminal.",
  },
];

function HowItWorks() {
  return (
    <section className="py-24 max-w-6xl mx-auto px-6">
      <div className="text-center mb-16" data-reveal>
        <p className="text-xs text-indigo-400 font-mono uppercase tracking-widest mb-3">How it works</p>
        <h2 className="font-display text-3xl sm:text-4xl font-bold gradient-text">
          From install to insights in 5 minutes
        </h2>
      </div>
      <div className="space-y-8">
        {STEPS.map((step, i) => (
          <div
            key={i}
            data-reveal
            className="grid lg:grid-cols-2 gap-6 items-center"
            style={{ transitionDelay: `${i * 100}ms` }}
          >
            <div className={i % 2 === 1 ? "lg:order-2" : ""}>
              <div className="font-mono text-5xl font-bold text-zinc-800 mb-4">{step.num}</div>
              <h3 className="font-display text-2xl font-bold text-white mb-3">{step.title}</h3>
              <p className="text-zinc-400 leading-relaxed">{step.desc}</p>
            </div>
            <div className={i % 2 === 1 ? "lg:order-1" : ""}>
              <div className="terminal">
                <div className="terminal-bar">
                  <div className="terminal-dot bg-red-500/70" />
                  <div className="terminal-dot bg-yellow-500/70" />
                  <div className="terminal-dot bg-green-500/70" />
                </div>
                <pre className="p-5 font-mono text-sm text-zinc-300 overflow-x-auto leading-relaxed">
                  {step.code}
                </pre>
              </div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Integrations
// ─────────────────────────────────────────────────────────────────────────────
const INTEGRATIONS = [
  { name: "LangChain", desc: "LangChain · Langflow · LangGraph", color: "text-emerald-400" },
  { name: "CrewAI", desc: "Multi-agent framework", color: "text-orange-400" },
  { name: "Pydantic AI", desc: "Type-safe agents", color: "text-blue-400" },
  { name: "LibreChat", desc: "Self-hosted chat UI", color: "text-purple-400" },
  { name: "OTLP", desc: "Any OTEL framework", color: "text-indigo-400" },
  { name: "Claude Desktop", desc: "Auto-discovered", color: "text-zinc-400" },
  { name: "Cursor", desc: "Auto-discovered", color: "text-zinc-400" },
  { name: "VS Code", desc: "Auto-discovered", color: "text-zinc-400" },
];

function Integrations() {
  return (
    <section className="py-24 bg-[#0D0D10]">
      <div className="max-w-6xl mx-auto px-6">
        <div className="text-center mb-16" data-reveal>
          <p className="text-xs text-indigo-400 font-mono uppercase tracking-widest mb-3">Integrations</p>
          <h2 className="font-display text-3xl sm:text-4xl font-bold gradient-text">
            Works with your stack
          </h2>
          <p className="mt-4 text-zinc-400 max-w-lg mx-auto">
            One callback or env var. Connects to every major Python agent framework
            and chat UI out of the box.
          </p>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {INTEGRATIONS.map((intg, i) => (
            <div
              key={i}
              data-reveal
              className="feature-card bg-[#18181B] border border-[#27272A] rounded-xl p-5 text-center"
              style={{ transitionDelay: `${i * 50}ms` }}
            >
              <div className={`font-display font-bold text-lg ${intg.color}`}>{intg.name}</div>
              <div className="text-xs text-zinc-500 mt-1">{intg.desc}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Providers
// ─────────────────────────────────────────────────────────────────────────────
const PROVIDERS = [
  {
    name: "Claude",
    by: "Anthropic",
    model: "claude-sonnet-4-6",
    note: "Adaptive thinking for deep RCA",
    color: "border-orange-500/30 hover:border-orange-500/60",
    accent: "text-orange-400",
  },
  {
    name: "GPT-4o",
    by: "OpenAI",
    model: "gpt-4o, o1-mini",
    note: "For teams already on OpenAI",
    color: "border-emerald-500/30 hover:border-emerald-500/60",
    accent: "text-emerald-400",
  },
  {
    name: "Gemini",
    by: "Google",
    model: "gemini-2.0-flash",
    note: "Free tier · 1M context",
    color: "border-blue-500/30 hover:border-blue-500/60",
    accent: "text-blue-400",
    badge: "Free",
  },
  {
    name: "Ollama",
    by: "Local",
    model: "llama3.2, mistral",
    note: "Air-gapped · No data sent",
    color: "border-purple-500/30 hover:border-purple-500/60",
    accent: "text-purple-400",
    badge: "Free",
  },
];

function Providers() {
  return (
    <section className="py-24 max-w-6xl mx-auto px-6">
      <div className="text-center mb-16" data-reveal>
        <p className="text-xs text-indigo-400 font-mono uppercase tracking-widest mb-3">AI providers</p>
        <h2 className="font-display text-3xl sm:text-4xl font-bold gradient-text">
          Use any LLM for investigations
        </h2>
        <p className="mt-4 text-zinc-400 max-w-lg mx-auto">
          <code className="text-indigo-400 font-mono">langsight investigate</code> sends health evidence to your
          preferred AI and returns a prioritised root cause report.
        </p>
      </div>
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
        {PROVIDERS.map((p, i) => (
          <div
            key={i}
            data-reveal
            className={`feature-card bg-[#18181B] border rounded-2xl p-6 transition-colors ${p.color}`}
            style={{ transitionDelay: `${i * 80}ms` }}
          >
            <div className="flex items-center justify-between mb-4">
              <span className={`font-display font-bold text-xl ${p.accent}`}>{p.name}</span>
              {p.badge && (
                <span className="text-xs bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 rounded-full px-2 py-0.5">
                  {p.badge}
                </span>
              )}
            </div>
            <div className="text-xs text-zinc-500 mb-1">{p.by}</div>
            <div className="font-mono text-xs text-zinc-400 mb-4">{p.model}</div>
            <p className="text-sm text-zinc-400">{p.note}</p>
          </div>
        ))}
      </div>
      <div className="mt-8 text-center" data-reveal>
        <p className="text-sm text-zinc-500">
          Configure in one line:{" "}
          <code className="text-indigo-400 font-mono bg-indigo-500/10 px-2 py-0.5 rounded">
            investigate.provider: gemini
          </code>
          {" "}in <code className="text-zinc-400 font-mono">.langsight.yaml</code>
        </p>
      </div>
    </section>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Open Source CTA
// ─────────────────────────────────────────────────────────────────────────────
function OpenSourceCTA() {
  return (
    <section className="py-24 bg-[#0D0D10]">
      <div className="max-w-4xl mx-auto px-6 text-center" data-reveal>
        <div className="bg-[#18181B] border border-indigo-500/20 rounded-3xl p-12 relative overflow-hidden">
          <div className="absolute inset-0 bg-gradient-to-br from-indigo-500/5 to-transparent pointer-events-none" />
          <div className="relative">
            <div className="inline-flex items-center gap-2 bg-indigo-500/10 border border-indigo-500/20 rounded-full px-4 py-1.5 text-xs text-indigo-400 mb-6">
              Apache 2.0 License
            </div>
            <h2 className="font-display text-4xl sm:text-5xl font-bold mb-4">
              <span className="gradient-text">Free forever.</span>
              <br />
              <span className="text-zinc-400">No hidden SaaS costs.</span>
            </h2>
            <p className="text-zinc-400 text-lg mb-8 max-w-xl mx-auto">
              LangSight is fully open source. The CLI, SDK, API, and all integrations
              are free. Self-host on your own infrastructure. Contribute on GitHub.
            </p>
            <div className="flex flex-wrap items-center justify-center gap-4">
              <a
                href="https://github.com/sumankalyan123/langsight"
                className="flex items-center gap-2 bg-white text-black font-semibold text-sm rounded-lg px-6 py-3 hover:bg-zinc-100 transition-colors"
              >
                <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
                </svg>
                Star on GitHub
              </a>
              <a
                href="https://lngsight.mintlify.app"
                className="flex items-center gap-2 bg-[#27272A] text-white font-semibold text-sm rounded-lg px-6 py-3 hover:bg-zinc-600 transition-colors"
              >
                Read the Docs →
              </a>
            </div>
            <div className="mt-8 flex flex-wrap justify-center gap-6 text-sm text-zinc-500">
              <span>✓ No account required</span>
              <span>✓ No telemetry by default</span>
              <span>✓ Self-hostable</span>
              <span>✓ MIT-compatible license</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Footer
// ─────────────────────────────────────────────────────────────────────────────
function Footer() {
  return (
    <footer className="border-t border-[#27272A] py-12">
      <div className="max-w-6xl mx-auto px-6 flex flex-col sm:flex-row items-center justify-between gap-4">
        <div className="flex items-center gap-2.5">
          <div className="w-6 h-6 rounded-md bg-indigo-500 flex items-center justify-center">
            <svg width="12" height="12" viewBox="0 0 14 14" fill="none">
              <path d="M2 7h10M7 2v10M4 4l6 6M10 4l-6 6" stroke="white" strokeWidth="1.5" strokeLinecap="round"/>
            </svg>
          </div>
          <span className="font-display font-bold text-white">LangSight</span>
          <span className="text-zinc-600 text-sm ml-2">Apache 2.0</span>
        </div>
        <div className="flex items-center gap-6 text-sm text-zinc-500">
          <a href="https://lngsight.mintlify.app" className="hover:text-white transition-colors">Docs</a>
          <a href="https://github.com/sumankalyan123/langsight" className="hover:text-white transition-colors">GitHub</a>
          <a href="https://pypi.org/project/langsight/" className="hover:text-white transition-colors">PyPI</a>
          <a href="https://github.com/sumankalyan123/langsight/releases" className="hover:text-white transition-colors">Changelog</a>
        </div>
      </div>
    </footer>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Scroll reveal
// ─────────────────────────────────────────────────────────────────────────────
function ScrollReveal() {
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) {
            e.target.classList.add("visible");
          }
        });
      },
      { threshold: 0.1 }
    );
    document.querySelectorAll("[data-reveal]").forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, []);
  return null;
}

// ─────────────────────────────────────────────────────────────────────────────
// Page
// ─────────────────────────────────────────────────────────────────────────────
export default function Home() {
  return (
    <>
      <ScrollReveal />
      <Nav />
      <main>
        <Hero />
        <Problem />
        <Features />
        <HowItWorks />
        <Integrations />
        <Providers />
        <OpenSourceCTA />
      </main>
      <Footer />
    </>
  );
}
