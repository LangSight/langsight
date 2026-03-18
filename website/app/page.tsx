"use client";
import { useEffect, useState } from "react";

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
  return { dark, toggle: () => setDark(d => !d) };
}

function ThemeBtn({ dark, toggle }: { dark: boolean; toggle: () => void }) {
  return (
    <button onClick={toggle} aria-label="Toggle theme"
      className="w-9 h-9 rounded-lg flex items-center justify-center transition-all hover:scale-110"
      style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
      {dark
        ? <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>
        : <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24"><path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/></svg>
      }
    </button>
  );
}

function Nav({ dark, toggle }: { dark: boolean; toggle: () => void }) {
  const [sc, setSc] = useState(false);
  useEffect(() => { const h = () => setSc(window.scrollY > 20); window.addEventListener("scroll", h); return () => window.removeEventListener("scroll", h); }, []);
  return (
    <nav className="fixed top-0 left-0 right-0 z-50 transition-all duration-300"
      style={{ background: sc ? "color-mix(in srgb, var(--bg) 90%, transparent)" : "transparent", backdropFilter: sc ? "blur(12px)" : "none", borderBottom: sc ? "1px solid var(--border)" : "1px solid transparent" }}>
      <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
        <a href="#" className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-lg flex items-center justify-center" style={{ background: "var(--indigo)" }}>
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M2 7h10M7 2v10M4 4l6 6M10 4l-6 6" stroke="white" strokeWidth="1.5" strokeLinecap="round"/></svg>
          </div>
          <span className="font-display font-bold text-lg" style={{ color: "var(--text)" }}>LangSight</span>
        </a>
        <div className="flex items-center gap-4">
          <a href="https://lngsight.mintlify.app" className="text-sm hidden sm:block transition-colors hover:text-[var(--text)]" style={{ color: "var(--muted)" }}>Docs</a>
          <a href="https://github.com/sumankalyan123/langsight" className="text-sm hidden sm:block transition-colors hover:text-[var(--text)]" style={{ color: "var(--muted)" }}>GitHub</a>
          <ThemeBtn dark={dark} toggle={toggle} />
          <a href="https://lngsight.mintlify.app/quickstart" className="text-sm font-semibold px-4 py-2 rounded-lg hidden sm:flex items-center gap-1.5 transition-all hover:opacity-90 hover:-translate-y-px" style={{ background: "var(--indigo)", color: "white" }}>
            Get started →
          </a>
        </div>
      </div>
    </nav>
  );
}

const LINES = [
  { t: "$ langsight sessions --id sess-f2a9b1", c: "var(--muted)", d: 0 },
  { t: "", d: 180 },
  { t: "Trace: sess-f2a9b1  (support-agent)", c: "var(--text)", bold: true, d: 320 },
  { t: "5 tool calls · 1 failed · 2,134ms · $0.023", c: "var(--muted)", sm: true, d: 420 },
  { t: "", d: 520 },
  { t: "sess-f2a9b1", c: "var(--indigo)", d: 620 },
  { t: "├── 🔧 jira-mcp/get_issue       89ms  ✓", c: "var(--green)", d: 780 },
  { t: "├── 🔧 postgres-mcp/query       42ms  ✓", c: "var(--green)", d: 940 },
  { t: "├──  → billing-agent          handoff", c: "var(--yellow)", d: 1100 },
  { t: "│   ├── 🔧 crm-mcp/update      120ms  ✓", c: "var(--green)", d: 1260 },
  { t: "│   └── 🔧 slack-mcp/notify       —   ✗  timeout", c: "var(--red)", d: 1420 },
  { t: "", d: 1580 },
  { t: "Total: $0.023 · 2 agents · 1 failure", c: "var(--muted)", sm: true, d: 1680 },
];

function Terminal() {
  const [v, setV] = useState(0);
  useEffect(() => { LINES.forEach((l, i) => setTimeout(() => setV(i + 1), l.d + 700)); }, []);
  return (
    <div className="terminal w-full max-w-2xl">
      <div className="terminal-bar">
        <div className="terminal-dot bg-red-500/70"/><div className="terminal-dot bg-yellow-500/70"/><div className="terminal-dot bg-green-500/70"/>
        <span className="ml-3 text-xs font-mono" style={{ color: "var(--dimmer)" }}>langsight · sessions</span>
      </div>
      <div className="p-5 font-mono text-sm space-y-0.5 min-h-[260px]">
        {LINES.slice(0, v).map((l, i) => (
          <div key={i} className="term-line" style={{ color: l.c, fontWeight: l.bold ? 700 : 400, fontSize: l.sm ? "0.75rem" : undefined }}>{l.t || "\u00A0"}</div>
        ))}
        {v < LINES.length && <span className="cursor inline-block w-2 h-4 align-middle" style={{ background: "var(--indigo)" }}/>}
      </div>
    </div>
  );
}

function Hero() {
  return (
    <section className="relative min-h-screen flex items-center grid-bg overflow-hidden pt-16">
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[700px] h-[500px] rounded-full blur-[140px]" style={{ background: "var(--indigo-glow)" }}/>
      </div>
      <div className="relative max-w-6xl mx-auto px-6 py-28 w-full">
        <div className="grid lg:grid-cols-2 gap-14 items-center">
          <div className="space-y-7">
            <div className="fade-up inline-flex items-center gap-2 rounded-full px-4 py-1.5 text-xs" style={{ background: "var(--indigo-dim)", border: "1px solid rgba(99,102,241,0.2)", color: "var(--indigo)" }}>
              <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: "var(--indigo)" }}/>
              v0.1.0 · Open source · Apache 2.0
            </div>
            <h1 className="fade-up delay-1 font-display text-5xl lg:text-6xl font-bold leading-[1.06] tracking-tight">
              <span className="gradient-text">Stop guessing</span><br/>
              <span className="gradient-text">why your agent</span><br/>
              <span className="gradient-indigo">failed.</span>
            </h1>
            <p className="fade-up delay-2 text-lg leading-relaxed max-w-md" style={{ color: "var(--muted)" }}>
              Trace every action your AI agents take — tool calls, handoffs, costs, and failures — across single and multi-agent workflows. MCP servers get extra depth: health checks, CVE scanning, and drift detection.
              <strong style={{ color: "var(--text)" }}> Two lines to instrument. Zero infra to start.</strong>
            </p>
            <div className="fade-up delay-3 flex flex-wrap gap-3">
              <a href="https://lngsight.mintlify.app/quickstart" className="text-sm font-semibold px-5 py-2.5 rounded-lg flex items-center gap-2 transition-all hover:opacity-90 hover:-translate-y-px" style={{ background: "var(--indigo)", color: "white" }}>
                Quickstart — 5 min →
              </a>
              <a href="https://github.com/sumankalyan123/langsight" className="text-sm font-semibold px-5 py-2.5 rounded-lg flex items-center gap-2 transition-all hover:-translate-y-px" style={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text)" }}>
                <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"/></svg>
                Star on GitHub
              </a>
            </div>
            <div className="fade-up delay-4 flex flex-wrap gap-5 text-sm" style={{ color: "var(--dimmer)" }}>
              <span>✓ LangChain, CrewAI, LibreChat</span>
              <span>✓ SQLite — no Docker needed</span>
              <span>✓ 378 tests · 0 mypy errors</span>
            </div>
          </div>
          <div className="fade-up delay-3"><Terminal/></div>
        </div>
      </div>
    </section>
  );
}

const PROBLEMS = [
  { icon: "🔍", q: "Which tool broke the agent?", a: "An agent returns wrong data. Was it the LLM hallucinating, or did postgres-mcp silently time out? Without traces you spend hours replaying requests." },
  { icon: "🌳", q: "What did the full chain call?", a: "Agent A called Agent B called Agent C. Which tool failed three levels deep? LangSight reconstructs the complete multi-agent call tree automatically." },
  { icon: "💸", q: "Why is this workflow expensive?", a: "A sub-agent retries a tool 40 times per session. At $0.005/call that's $0.20 per task. Nobody notices until the invoice arrives at month end." },
];

function Problem() {
  return (
    <section className="py-24" style={{ background: "var(--bg-deep)" }}>
      <div className="max-w-6xl mx-auto px-6">
        <div className="text-center mb-14" data-reveal>
          <p className="text-xs font-mono uppercase tracking-widest mb-3" style={{ color: "var(--indigo)" }}>The problem</p>
          <h2 className="font-display text-3xl sm:text-4xl font-bold gradient-text">AI agents fail silently</h2>
          <p className="mt-4 max-w-lg mx-auto" style={{ color: "var(--muted)" }}>Modern agents chain dozens of tool calls. When something breaks, you have no idea where — or why.</p>
        </div>
        <div className="grid md:grid-cols-3 gap-5">
          {PROBLEMS.map((p, i) => (
            <div key={i} data-reveal className="card p-7" style={{ transitionDelay: `${i * 80}ms` }}>
              <div className="text-3xl mb-4">{p.icon}</div>
              <h3 className="font-display text-xl font-bold mb-3" style={{ color: "var(--text)" }}>{p.q}</h3>
              <p className="text-sm leading-relaxed" style={{ color: "var(--muted)" }}>{p.a}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

const FEATURES = [
  { icon: "🔭", title: "Agent Session Traces", desc: "Every tool call in every session — MCP servers, HTTP APIs, Python functions — with latency, status, and errors. The full picture, not just what the LLM said.", badge: "All tools", hot: true },
  { icon: "🌳", title: "Multi-Agent Call Trees", desc: "parent_span_id links sub-agent calls to the handoff that spawned them. See the exact path from orchestrator to leaf tool, reconstructed automatically.", badge: "Unique", hot: true },
  { icon: "🔬", title: "AI Root Cause Analysis", desc: "langsight investigate sends health evidence to Claude, GPT-4o, Gemini, or local Ollama and returns prioritised remediation steps. Rule-based fallback without a key.", badge: "4 LLMs" },
  { icon: "💰", title: "Cost Attribution", desc: "Per-tool pricing rules. See total cost per session, per agent, per tool. Spot which sub-agent burns 80% of your budget on retries.", badge: "ClickHouse" },
  { icon: "♥", title: "MCP Health Monitoring", desc: "Proactive health checks, schema drift detection, and Slack alerts on DOWN/recovery transitions — before your agents start failing.", badge: "MCP only" },
  { icon: "🛡", title: "MCP Security Scanning", desc: "CVE detection, all 10 OWASP MCP checks, tool poisoning detection (injection phrases, hidden unicode, base64), and auth gap analysis.", badge: "MCP only" },
];

function Features() {
  return (
    <section className="py-24">
      <div className="max-w-6xl mx-auto px-6">
        <div className="text-center mb-14" data-reveal>
          <p className="text-xs font-mono uppercase tracking-widest mb-3" style={{ color: "var(--indigo)" }}>Features</p>
          <h2 className="font-display text-3xl sm:text-4xl font-bold gradient-text">Observability for agent actions</h2>
          <p className="mt-4 max-w-xl mx-auto" style={{ color: "var(--muted)" }}>
            Instrument once. Every tool type is traced. MCP servers get proactive health checks and security scanning on top — because the protocol makes it possible.
          </p>
        </div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {FEATURES.map((f, i) => (
            <div key={i} data-reveal className="card p-7 relative" style={{ transitionDelay: `${i * 60}ms` }}>
              {f.hot && <div className="absolute top-4 right-4 text-xs px-2 py-0.5 rounded-full font-semibold" style={{ background: "var(--indigo)", color: "white" }}>New</div>}
              <div className="text-2xl mb-4">{f.icon}</div>
              <div className="flex items-start gap-2 mb-3">
                <h3 className="font-display text-lg font-bold flex-1" style={{ color: "var(--text)" }}>{f.title}</h3>
                <span className="shrink-0 text-xs rounded-full px-2 py-0.5 mt-0.5" style={{ background: "var(--indigo-dim)", color: "var(--indigo)", border: "1px solid rgba(99,102,241,0.2)" }}>{f.badge}</span>
              </div>
              <p className="text-sm leading-relaxed" style={{ color: "var(--muted)" }}>{f.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

const STEPS = [
  { n: "01", sub: "30 seconds", title: "Install & discover", code: "pip install langsight\nlangsight init\n# Auto-discovers from Claude Desktop,\n# Cursor and VS Code configs", desc: "One command discovers all your MCP servers and writes .langsight.yaml. No manual configuration." },
  { n: "02", sub: "2 lines of code", title: "Instrument your agent", code: `from langsight.sdk import LangSightClient\n\nclient = LangSightClient(url="http://localhost:8000")\ntraced = client.wrap(\n    mcp_session,\n    server_name="my-mcp",\n    agent_name="support-agent"\n)`, desc: "Wraps any MCP client. Every call_tool() is traced asynchronously — never blocks your agent. Fail-open if LangSight is unreachable." },
  { n: "03", sub: "real-time", title: "See everything", code: "langsight sessions\nlangsight sessions --id sess-abc\nlangsight mcp-health\nlangsight security-scan\nlangsight investigate", desc: "Full session traces, multi-agent trees, health status, security findings, and AI-powered root cause analysis — all in the terminal." },
];

function HowItWorks() {
  return (
    <section className="py-24" style={{ background: "var(--bg-deep)" }}>
      <div className="max-w-6xl mx-auto px-6">
        <div className="text-center mb-16" data-reveal>
          <p className="text-xs font-mono uppercase tracking-widest mb-3" style={{ color: "var(--indigo)" }}>How it works</p>
          <h2 className="font-display text-3xl sm:text-4xl font-bold gradient-text">Zero to full observability in 5 minutes</h2>
        </div>
        <div className="space-y-14">
          {STEPS.map((s, i) => (
            <div key={i} data-reveal className="grid lg:grid-cols-2 gap-10 items-center">
              <div className={i % 2 === 1 ? "lg:order-2" : ""}>
                <div className="font-mono text-5xl font-bold mb-4" style={{ color: "var(--border)" }}>{s.n}</div>
                <div className="text-xs font-mono uppercase tracking-widest mb-2" style={{ color: "var(--indigo)" }}>{s.sub}</div>
                <h3 className="font-display text-2xl font-bold mb-4" style={{ color: "var(--text)" }}>{s.title}</h3>
                <p className="leading-relaxed" style={{ color: "var(--muted)" }}>{s.desc}</p>
              </div>
              <div className={i % 2 === 1 ? "lg:order-1" : ""}>
                <div className="terminal">
                  <div className="terminal-bar"><div className="terminal-dot bg-red-500/60"/><div className="terminal-dot bg-yellow-500/60"/><div className="terminal-dot bg-green-500/60"/></div>
                  <pre className="p-5 font-mono text-sm overflow-x-auto leading-relaxed" style={{ color: "var(--code-text)" }}>{s.code}</pre>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

const INTEGRATIONS = [
  { name: "LangChain", sub: "Langflow · LangGraph", c: "#10B981" },
  { name: "CrewAI", sub: "Multi-agent", c: "#F59E0B" },
  { name: "Pydantic AI", sub: "Type-safe agents", c: "#3B82F6" },
  { name: "LibreChat", sub: "Self-hosted chat", c: "#8B5CF6" },
  { name: "OpenWebUI", sub: "Local LLM UI", c: "#EC4899" },
  { name: "OTLP", sub: "Any OTEL framework", c: "#6366F1" },
  { name: "Claude Desktop", sub: "Auto-discovered", c: "#71717A" },
  { name: "Cursor · VS Code", sub: "Auto-discovered", c: "#71717A" },
];

function Integrations() {
  return (
    <section className="py-24">
      <div className="max-w-6xl mx-auto px-6">
        <div className="text-center mb-14" data-reveal>
          <p className="text-xs font-mono uppercase tracking-widest mb-3" style={{ color: "var(--indigo)" }}>Integrations</p>
          <h2 className="font-display text-3xl sm:text-4xl font-bold gradient-text">Works with everything engineers use</h2>
          <p className="mt-4 max-w-lg mx-auto" style={{ color: "var(--muted)" }}>One callback or env var. Drop into any framework — no changes to the rest of your code.</p>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {INTEGRATIONS.map((intg, i) => (
            <div key={i} data-reveal className="card p-5 text-center" style={{ transitionDelay: `${i * 40}ms` }}>
              <div className="font-display font-bold text-lg mb-1" style={{ color: intg.c }}>{intg.name}</div>
              <div className="text-xs" style={{ color: "var(--muted)" }}>{intg.sub}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

const PROVIDERS = [
  { name: "Claude", by: "Anthropic", model: "claude-sonnet-4-6", note: "Adaptive thinking · Best RCA quality", c: "#F97316", free: false },
  { name: "GPT-4o", by: "OpenAI", model: "gpt-4o, o1-mini", note: "Fast · Strong reasoning", c: "#10B981", free: false },
  { name: "Gemini", by: "Google", model: "gemini-2.0-flash", note: "1M context · Free 1,500 req/day", c: "#3B82F6", free: true },
  { name: "Ollama", by: "Local", model: "llama3.2, mistral", note: "Air-gapped · No data sent", c: "#8B5CF6", free: true },
];

function Providers() {
  return (
    <section className="py-24" style={{ background: "var(--bg-deep)" }}>
      <div className="max-w-6xl mx-auto px-6">
        <div className="text-center mb-14" data-reveal>
          <p className="text-xs font-mono uppercase tracking-widest mb-3" style={{ color: "var(--indigo)" }}>AI providers</p>
          <h2 className="font-display text-3xl sm:text-4xl font-bold gradient-text">Use any LLM for root cause analysis</h2>
          <p className="mt-4 max-w-lg mx-auto" style={{ color: "var(--muted)" }}>
            <code className="font-mono text-sm px-1.5 py-0.5 rounded" style={{ background: "var(--indigo-dim)", color: "var(--indigo)" }}>langsight investigate</code> sends evidence to your LLM and returns a prioritised remediation report. Switch with one config line.
          </p>
        </div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
          {PROVIDERS.map((p, i) => (
            <div key={i} data-reveal className="card p-6" style={{ transitionDelay: `${i * 70}ms` }}>
              <div className="flex justify-between items-start mb-4">
                <span className="font-display font-bold text-xl" style={{ color: p.c }}>{p.name}</span>
                {p.free && <span className="text-xs rounded-full px-2 py-0.5 font-semibold" style={{ background: "rgba(22,163,74,0.1)", color: "var(--green)", border: "1px solid rgba(22,163,74,0.2)" }}>Free</span>}
              </div>
              <div className="text-xs mb-1" style={{ color: "var(--dimmer)" }}>{p.by}</div>
              <div className="font-mono text-xs mb-4" style={{ color: "var(--muted)" }}>{p.model}</div>
              <p className="text-sm" style={{ color: "var(--muted)" }}>{p.note}</p>
            </div>
          ))}
        </div>
        <div className="mt-8 text-center" data-reveal>
          <p className="text-sm" style={{ color: "var(--dimmer)" }}>
            Set in one line: <code className="font-mono px-2 py-0.5 rounded" style={{ background: "var(--indigo-dim)", color: "var(--indigo)" }}>investigate.provider: gemini</code> · Falls back to rule-based analysis without a key
          </p>
        </div>
      </div>
    </section>
  );
}


/* ── Open Source ─────────────────────────────────────────────── */
const OSS_PILLARS = [
  { icon: "🔒", title: "Your data stays yours", body: "Self-host on your own infrastructure. No data ever leaves your network. SQLite locally or ClickHouse in production — both fully under your control." },
  { icon: "🚫", title: "No vendor lock-in", body: "Apache 2.0. Fork it, embed it in your product, modify it without asking permission. We will never change the license or add closed-source features." },
  { icon: "🌍", title: "Community-driven", body: "Every feature was shaped by engineers running real agents. File an issue, submit a PR, or join the discussion — this is your project too." },
];

const COMPARE: { feature: string; ls: boolean | string; datadog: boolean | string; langfuse: boolean | string }[] = [
  { feature: "Agent action traces",               ls: true,  datadog: true,      langfuse: "partial" },
  { feature: "Multi-agent tree reconstruction",   ls: true,  datadog: false,     langfuse: false },
  { feature: "MCP server health checks",          ls: true,  datadog: false,     langfuse: false },
  { feature: "CVE + OWASP security scanning",     ls: true,  datadog: false,     langfuse: false },
  { feature: "Tool poisoning detection",          ls: true,  datadog: false,     langfuse: false },
  { feature: "Schema drift detection",            ls: true,  datadog: false,     langfuse: false },
  { feature: "Action-layer root cause analysis",  ls: true,  datadog: false,     langfuse: false },
  { feature: "Self-hostable",                     ls: true,  datadog: false,     langfuse: true },
  { feature: "Open source (Apache 2.0)",          ls: true,  datadog: false,     langfuse: true },
  { feature: "Free forever",                      ls: true,  datadog: false,     langfuse: "partial" },
];

function GHIcon() {
  return (
    <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"/>
    </svg>
  );
}

function CellVal({ v }: { v: boolean | string }) {
  if (v === true)  return <span style={{ color: "var(--green)", fontSize: "1.1em" }}>✓</span>;
  if (v === false) return <span style={{ color: "var(--red)",   fontSize: "1.1em" }}>✗</span>;
  return <span style={{ color: "var(--yellow)", fontSize: "1.1em" }}>~</span>;
}

function OpenSource() {
  return (
    <section className="py-24" style={{ background: "var(--bg-deep)" }}>
      <div className="max-w-6xl mx-auto px-6">
        <div className="text-center mb-16" data-reveal>
          <div className="inline-flex items-center gap-2 rounded-full px-4 py-1.5 text-xs mb-5"
            style={{ background: "var(--indigo-dim)", border: "1px solid rgba(99,102,241,0.2)", color: "var(--indigo)" }}>
            <GHIcon /> Apache 2.0 · Fully Open Source
          </div>
          <h2 className="font-display text-3xl sm:text-4xl font-bold gradient-text">
            Built in the open.<br />Free to use, forever.
          </h2>
          <p className="mt-4 max-w-xl mx-auto text-lg" style={{ color: "var(--muted)" }}>
            LangSight is not &quot;open core&quot; — the CLI, SDK, API, all integrations, and every feature
            on this page is fully open source. No paid tiers. No gated features. No surprises.
          </p>
          <a href="https://github.com/sumankalyan123/langsight"
            className="mt-6 inline-flex items-center gap-2 font-semibold text-sm px-5 py-2.5 rounded-lg transition-all hover:opacity-90 hover:-translate-y-px"
            style={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text)" }}>
            <GHIcon /> sumankalyan123/langsight
            <span className="ml-1 text-xs px-2 py-0.5 rounded-full font-mono"
              style={{ background: "var(--indigo-dim)", color: "var(--indigo)" }}>Apache 2.0</span>
          </a>
        </div>

        {/* 3 pillars */}
        <div className="grid md:grid-cols-3 gap-5 mb-16">
          {OSS_PILLARS.map((p, i) => (
            <div key={i} data-reveal className="card p-7" style={{ transitionDelay: `${i * 80}ms` }}>
              <div className="text-3xl mb-4">{p.icon}</div>
              <h3 className="font-display text-xl font-bold mb-3" style={{ color: "var(--text)" }}>{p.title}</h3>
              <p className="text-sm leading-relaxed" style={{ color: "var(--muted)" }}>{p.body}</p>
            </div>
          ))}
        </div>

        {/* Comparison table */}
        <div data-reveal className="card overflow-hidden">
          <div className="px-6 py-4 flex items-center justify-between"
            style={{ borderBottom: "1px solid var(--border)", background: "var(--bg-deep)" }}>
            <h3 className="font-display font-bold text-lg" style={{ color: "var(--text)" }}>
              How LangSight compares
            </h3>
            <span className="text-xs" style={{ color: "var(--dimmer)" }}>
              ✓ yes &nbsp; ✗ no &nbsp; ~ partial
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border)", background: "var(--bg-deep)" }}>
                  <th className="text-left px-6 py-3 font-medium" style={{ color: "var(--muted)" }}>Feature</th>
                  <th className="px-6 py-3 text-center font-bold text-sm"
                    style={{ color: "var(--indigo)" }}>LangSight</th>
                  <th className="px-6 py-3 text-center font-medium text-sm"
                    style={{ color: "var(--muted)" }}>Datadog</th>
                  <th className="px-6 py-3 text-center font-medium text-sm"
                    style={{ color: "var(--muted)" }}>Langfuse</th>
                </tr>
              </thead>
              <tbody>
                {COMPARE.map((row, i) => (
                  <tr key={i}
                    style={{ borderBottom: i < COMPARE.length - 1 ? "1px solid var(--border-dim)" : "none" }}>
                    <td className="px-6 py-3" style={{ color: "var(--text)" }}>{row.feature}</td>
                    <td className="px-6 py-3 text-center"><CellVal v={row.ls} /></td>
                    <td className="px-6 py-3 text-center"><CellVal v={row.datadog} /></td>
                    <td className="px-6 py-3 text-center"><CellVal v={row.langfuse} /></td>
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

function CTA() {
  return (
    <section className="py-24">
      <div className="max-w-4xl mx-auto px-6 text-center" data-reveal>
        <div className="card p-12 relative overflow-hidden">
          <div className="absolute inset-0 pointer-events-none"
            style={{ background: "linear-gradient(135deg, var(--indigo-dim) 0%, transparent 60%)" }}/>
          <div className="relative">
            <div className="text-5xl mb-6">⚡</div>
            <h2 className="font-display text-4xl sm:text-5xl font-bold mb-3">
              <span className="gradient-indigo">Start building with LangSight today.</span>
            </h2>
            <p className="text-xl mb-2 font-semibold" style={{ color: "var(--text)" }}>
              Full observability for your AI agents — free, open source, forever.
            </p>
            <p className="text-base mb-8 max-w-lg mx-auto" style={{ color: "var(--muted)" }}>
              Install in 30 seconds. Two lines to instrument. See exactly what your
              agents call, how long each tool takes, and what everything costs.
            </p>
            <div className="flex flex-wrap justify-center gap-4 mb-8">
              <a href="https://lngsight.mintlify.app/quickstart"
                className="text-base font-semibold px-7 py-3 rounded-lg flex items-center gap-2 transition-all hover:opacity-90 hover:-translate-y-px"
                style={{ background: "var(--indigo)", color: "white" }}>
                Get started free →
              </a>
              <a href="https://github.com/sumankalyan123/langsight"
                className="text-base font-semibold px-7 py-3 rounded-lg flex items-center gap-2 transition-all hover:-translate-y-px"
                style={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text)" }}>
                <GHIcon /> Star on GitHub
              </a>
            </div>
            <div className="inline-flex items-center gap-3 rounded-xl px-5 py-3 font-mono text-sm mb-8"
              style={{ background: "var(--terminal-bg)", border: "1px solid var(--border)" }}>
              <span style={{ color: "var(--dimmer)" }}>$</span>
              <span style={{ color: "var(--code-text)" }}>pip install langsight</span>
              <span style={{ color: "var(--dimmer)" }}>{'&&'}</span>
              <span style={{ color: "var(--code-text)" }}>langsight init</span>
            </div>
            <div className="flex flex-wrap justify-center gap-6 text-sm" style={{ color: "var(--dimmer)" }}>
              <span>✓ Apache 2.0 — free forever</span>
              <span>✓ No account needed</span>
              <span>✓ SQLite — zero infrastructure to start</span>
              <span>✓ 378 tests passing</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="py-10" style={{ borderTop: "1px solid var(--border)" }}>
      <div className="max-w-6xl mx-auto px-6 flex flex-col sm:flex-row items-center justify-between gap-4">
        <div className="flex items-center gap-2.5">
          <div className="w-6 h-6 rounded-md flex items-center justify-center"
            style={{ background: "var(--indigo)" }}>
            <svg width="12" height="12" viewBox="0 0 14 14" fill="none">
              <path d="M2 7h10M7 2v10M4 4l6 6M10 4l-6 6" stroke="white" strokeWidth="1.5" strokeLinecap="round"/>
            </svg>
          </div>
          <span className="font-display font-bold" style={{ color: "var(--text)" }}>LangSight</span>
          <span className="text-xs ml-2 px-2 py-0.5 rounded font-mono"
            style={{ background: "var(--indigo-dim)", color: "var(--indigo)" }}>Apache 2.0</span>
        </div>
        <div className="flex items-center gap-6 text-sm" style={{ color: "var(--muted)" }}>
          {([["Docs","https://lngsight.mintlify.app"],["GitHub","https://github.com/sumankalyan123/langsight"],["PyPI","https://pypi.org/project/langsight/"],["Changelog","https://github.com/sumankalyan123/langsight/blob/main/CHANGELOG.md"]] as [string,string][]).map(([l,h]) => (
            <a key={l} href={h} className="hover:text-[var(--text)] transition-colors">{l}</a>
          ))}
        </div>
      </div>
    </footer>
  );
}

function ScrollReveal() {
  useEffect(() => {
    const obs = new IntersectionObserver(
      (entries) => entries.forEach(e => e.isIntersecting && e.target.classList.add("visible")),
      { threshold: 0.08 }
    );
    document.querySelectorAll("[data-reveal]").forEach(el => obs.observe(el));
    return () => obs.disconnect();
  }, []);
  return null;
}

export default function Home() {
  const { dark, toggle } = useTheme();
  return (
    <>
      <ScrollReveal/>
      <Nav dark={dark} toggle={toggle}/>
      <main>
        <Hero/><Problem/><Features/><HowItWorks/><Integrations/><Providers/><OpenSource/><CTA/>
      </main>
      <Footer/>
    </>
  );
}
