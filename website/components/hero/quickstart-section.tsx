"use client";

/**
 * QuickstartSection — How to get started in 3 steps.
 * Shows pip install, code snippet, docker compose.
 */

import { ScrollReveal, SpotlightCard, GlowBorder, TiltCard } from "./animated-primitives";

/* ── Code block component ───────────────────────────────── */
function CodeBlock({ title, lang, code }: { title: string; lang: string; code: string }) {
  return (
    <div
      className="rounded-xl overflow-hidden"
      style={{ background: "var(--terminal-bg)", border: "1px solid var(--border)" }}
    >
      <div
        className="flex items-center justify-between px-4 py-2"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <span className="text-xs font-medium" style={{ color: "var(--muted)" }}>{title}</span>
        <span
          className="text-[10px] rounded px-1.5 py-0.5"
          style={{ background: "var(--indigo-dim)", color: "var(--indigo)", border: "1px solid var(--indigo-strong)" }}
        >
          {lang}
        </span>
      </div>
      <pre
        className="p-4 text-sm overflow-x-auto leading-relaxed"
        style={{ fontFamily: "var(--font-geist-mono)", color: "var(--code-text)" }}
      >
        {code}
      </pre>
    </div>
  );
}

/* ── Steps data ─────────────────────────────────────────── */
const STEPS = [
  {
    step: "1",
    title: "Install the SDK",
    time: "10 seconds",
    desc: "One pip install. No Docker needed for the SDK — it works standalone with any Python agent.",
    code: {
      title: "Terminal",
      lang: "bash",
      content: `pip install langsight`,
    },
  },
  {
    step: "2",
    title: "Add two lines to your agent",
    time: "30 seconds",
    desc: "auto_patch() instruments Claude Agent SDK, CrewAI, OpenAI, and Gemini automatically. Zero wrappers, zero config.",
    code: {
      title: "your_agent.py",
      lang: "python",
      content: `import langsight

langsight.auto_patch()

# That's it. Every tool call, handoff,
# and LLM interaction is now traced.
# Loop detection + budget enforcement
# are active automatically.

# Your existing agent code — unchanged:
from claude_agent_sdk import query
result = await query(prompt="...", options=options)`,
    },
  },
  {
    step: "3",
    title: "Start the dashboard",
    time: "5 minutes",
    desc: "One script generates secrets, starts Postgres + ClickHouse + API + Dashboard. You're looking at traces before your coffee is ready.",
    code: {
      title: "Terminal",
      lang: "bash",
      content: `# Clone and start the full stack
git clone https://github.com/LangSight/langsight
cd langsight

# Auto-generates secrets, starts 5 containers,
# seeds demo data
./scripts/quickstart.sh

# Dashboard: http://localhost:3002
# API:       http://localhost:8000
# Docs:      https://docs.langsight.dev`,
    },
  },
];

/* ── Section ────────────────────────────────────────────── */
export default function QuickstartSection() {
  return (
    <section className="relative py-24 overflow-hidden" style={{ background: "var(--bg)" }}>
      <div className="max-w-5xl mx-auto px-6">
        {/* Header */}
        <ScrollReveal className="text-center mb-16">
          <p
            className="text-xs font-medium uppercase tracking-[0.15em] mb-3"
            style={{ fontFamily: "var(--font-geist-mono)", color: "var(--indigo)" }}
          >
            Get started
          </p>
          <h2
            className="font-bold tracking-tight"
            style={{ fontSize: "clamp(1.8rem, 3.5vw, 2.5rem)", fontFamily: "var(--font-geist-sans)" }}
          >
            <span className="gradient-text">Zero to traced</span>
            <br />
            <span className="gradient-indigo">in 5 minutes.</span>
          </h2>
          <p className="mt-4 max-w-lg mx-auto" style={{ color: "var(--muted)" }}>
            No account needed. No vendor dependency. Self-hosted on your infra.
            Apache 2.0 — fork it, modify it, ship it.
          </p>
        </ScrollReveal>

        {/* Steps */}
        <div className="space-y-10">
          {STEPS.map((s, i) => (
            <ScrollReveal key={i} delay={i * 100}>
              <div className="grid lg:grid-cols-5 gap-6 items-start">
                {/* Left: step info */}
                <div className="lg:col-span-2">
                  <div className="flex items-center gap-3 mb-3">
                    <div
                      className="w-9 h-9 rounded-full flex items-center justify-center text-sm font-bold shrink-0"
                      style={{ background: "var(--indigo)", color: "white", boxShadow: "0 0 20px var(--indigo-glow)" }}
                    >
                      {s.step}
                    </div>
                    <div>
                      <h3 className="font-semibold text-base" style={{ color: "var(--text)", fontFamily: "var(--font-geist-sans)" }}>
                        {s.title}
                      </h3>
                      <p className="text-xs" style={{ color: "var(--dimmer)" }}>{s.time}</p>
                    </div>
                  </div>
                  <p className="text-sm leading-relaxed ml-12" style={{ color: "var(--muted)" }}>
                    {s.desc}
                  </p>
                </div>

                {/* Right: code block */}
                <div className="lg:col-span-3">
                  <TiltCard intensity={4}>
                    <CodeBlock title={s.code.title} lang={s.code.lang} code={s.code.content} />
                  </TiltCard>
                </div>
              </div>
            </ScrollReveal>
          ))}
        </div>

        {/* Bottom CTA */}
        <ScrollReveal delay={400} className="mt-16">
          <GlowBorder borderRadius="16px" glowOpacity={0.25} hoverOpacity={0.5}>
            <SpotlightCard
              className="rounded-2xl p-10 text-center"
              style={{ background: "var(--surface)" }}
              spotlightColor="rgba(99,102,241,0.08)"
            >
              <h3
                className="font-bold tracking-tight mb-3"
                style={{ fontSize: "clamp(1.4rem, 2.5vw, 1.8rem)", fontFamily: "var(--font-geist-sans)", color: "var(--text)" }}
              >
                Ready to see what your agents are really doing?
              </h3>
              <p className="text-sm mb-6 max-w-lg mx-auto" style={{ color: "var(--muted)" }}>
                Self-host on your own infrastructure. No data ever leaves your network.
                No paid tiers. No gated features. No usage limits.
              </p>

              <div className="flex flex-wrap justify-center gap-4 mb-6">
                <a
                  href="https://docs.langsight.dev/quickstart"
                  className="text-sm font-semibold px-7 py-3 rounded-lg flex items-center gap-2 transition-all hover:opacity-90 hover:-translate-y-px"
                  style={{
                    background: "var(--indigo)",
                    color: "white",
                    boxShadow: "0 0 24px rgba(99,102,241,0.35), 0 4px 12px rgba(0,0,0,0.3)",
                  }}
                >
                  Start self-hosting →
                </a>
                <a
                  href="https://github.com/LangSight/langsight"
                  className="text-sm font-semibold px-7 py-3 rounded-lg flex items-center gap-2 transition-all hover:-translate-y-px"
                  style={{ background: "var(--surface-2)", border: "1px solid var(--border)", color: "var(--text)" }}
                >
                  <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
                  </svg>
                  Star on GitHub
                </a>
              </div>

              <div className="flex flex-wrap justify-center gap-6 text-xs" style={{ color: "var(--dimmer)" }}>
                <span>Apache 2.0 — self-host free forever</span>
                <span>No account needed</span>
                <span>docker compose up — full stack in 5 min</span>
              </div>
            </SpotlightCard>
          </GlowBorder>
        </ScrollReveal>
      </div>
    </section>
  );
}
