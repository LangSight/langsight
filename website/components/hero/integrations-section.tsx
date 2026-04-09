"use client";

/**
 * IntegrationsSection — Platform logos with magnetic hover + spotlight cards.
 */

import { ScrollReveal, SpotlightCard, MagneticHover } from "./animated-primitives";

/* ── Integration data ───────────────────────────────────── */
interface Integration {
  name: string;
  sub: string;
  status: "verified" | "beta" | "coming";
  features: string[];
  color: string;
  icon: React.ReactNode;
}

const INTEGRATIONS: Integration[] = [
  {
    name: "Anthropic SDK",
    sub: "Messages API + Streaming",
    status: "verified",
    features: ["LLM tracing", "Token capture", "Cost tracking"],
    color: "#D97706",
    icon: <svg viewBox="0 0 24 24" fill="currentColor" className="w-6 h-6"><path d="M13.827 3.52l5.862 16.96h-4.197l-5.862-16.96h4.197zM4.311 20.48L10.173 3.52h4.197L8.508 20.48H4.311z" /></svg>,
  },
  {
    name: "Claude Agent SDK",
    sub: "Multi-agent orchestration",
    status: "verified",
    features: ["Zero-code auto_patch()", "Subagent tracing", "66 spans captured"],
    color: "#D97706",
    icon: <svg viewBox="0 0 24 24" fill="currentColor" className="w-6 h-6"><path d="M4.709 15.955a3.621 3.621 0 0 0 1.942 4.736l2.015.858a3.621 3.621 0 0 0 4.736-1.942l3.889-9.128a3.621 3.621 0 0 0-1.942-4.736l-2.015-.858a3.621 3.621 0 0 0-4.736 1.942L4.709 15.955Z" /></svg>,
  },
  {
    name: "CrewAI",
    sub: "Event bus + 19 handlers",
    status: "verified",
    features: ["Native event bus", "Agent attribution", "A2A handoffs"],
    color: "#F59E0B",
    icon: <svg viewBox="0 0 24 24" fill="currentColor" className="w-6 h-6"><circle cx="12" cy="8" r="4" /><circle cx="6" cy="18" r="3" /><circle cx="18" cy="18" r="3" /><path d="M12 12v3M9 15.5L6 18M15 15.5l3 2.5" stroke="currentColor" strokeWidth="1.5" fill="none" /></svg>,
  },
  {
    name: "OpenAI SDK",
    sub: "Chat completions + Agents",
    status: "beta",
    features: ["LLM tracing", "Token capture", "Function calls"],
    color: "#10B981",
    icon: <svg viewBox="0 0 24 24" fill="currentColor" className="w-6 h-6"><path d="M22.282 9.821a5.985 5.985 0 0 0-.516-4.91 6.046 6.046 0 0 0-6.51-2.9A6.065 6.065 0 0 0 4.981 4.18a5.985 5.985 0 0 0-3.998 2.9 6.046 6.046 0 0 0 .743 7.097 5.98 5.98 0 0 0 .51 4.911 6.051 6.051 0 0 0 6.515 2.9A5.985 5.985 0 0 0 13.26 24a6.056 6.056 0 0 0 5.772-4.206 5.99 5.99 0 0 0 3.997-2.9 6.056 6.056 0 0 0-.747-7.073z" /></svg>,
  },
  {
    name: "Google Gemini",
    sub: "Generative AI SDK",
    status: "beta",
    features: ["LLM tracing", "Token capture", "generate_content"],
    color: "#4285F4",
    icon: <svg viewBox="0 0 24 24" fill="currentColor" className="w-6 h-6"><path d="M12 24A14.304 14.304 0 0 0 24 12 14.304 14.304 0 0 0 12 0 14.304 14.304 0 0 0 0 12a14.304 14.304 0 0 0 12 12z" fillOpacity="0.9" /></svg>,
  },
  {
    name: "OTLP / OpenTelemetry",
    sub: "Any OTEL-compatible framework",
    status: "verified",
    features: ["OTLP ingest", "gen_ai conventions", "Any language"],
    color: "#6366F1",
    icon: <svg viewBox="0 0 24 24" fill="currentColor" className="w-6 h-6"><circle cx="12" cy="12" r="3" /><circle cx="12" cy="4" r="2" /><circle cx="20" cy="12" r="2" /><circle cx="12" cy="20" r="2" /><circle cx="4" cy="12" r="2" /><path d="M12 6v3M15 12h3M12 15v3M9 12H6" stroke="currentColor" strokeWidth="1.2" fill="none" /></svg>,
  },
  {
    name: "LangChain / LangGraph",
    sub: "Chains + Graph agents",
    status: "coming",
    features: ["Callback handler", "Tool tracing", "Graph state"],
    color: "#1C3C3C",
    icon: <svg viewBox="0 0 24 24" fill="none" className="w-6 h-6"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" /></svg>,
  },
  {
    name: "Pydantic AI",
    sub: "Type-safe agents",
    status: "coming",
    features: ["Agent tracing", "Tool capture", "Structured output"],
    color: "#E92063",
    icon: <svg viewBox="0 0 24 24" fill="none" className="w-6 h-6"><path d="M12 2l8 4.5v11L12 22l-8-4.5v-11L12 2z" stroke="currentColor" strokeWidth="1.5" /><path d="M12 7v10M8 9.5l4 2.5 4-2.5" stroke="currentColor" strokeWidth="1.5" /></svg>,
  },
];

const STATUS_STYLES = {
  verified: { label: "Verified", bg: "rgba(34,197,94,0.12)", color: "#22C55E", border: "rgba(34,197,94,0.25)" },
  beta: { label: "Beta", bg: "rgba(234,179,8,0.12)", color: "#EAB308", border: "rgba(234,179,8,0.25)" },
  coming: { label: "Coming soon", bg: "rgba(99,102,241,0.08)", color: "var(--dimmer)", border: "rgba(99,102,241,0.15)" },
};

const CAPABILITIES = [
  { icon: "🔄", title: "Loop Detection", desc: "Pattern-based: same tool + same args = kill it" },
  { icon: "💰", title: "Budget Enforcement", desc: "Per-session cost limits with auto-kill" },
  { icon: "⚡", title: "Circuit Breakers", desc: "Tool-level, stateful, auto-recovery" },
  { icon: "🏥", title: "MCP Health Checks", desc: "5 transports, latency, status, schema drift" },
  { icon: "🛡️", title: "Security Scanning", desc: "CVE + OWASP MCP Top 10 + poisoning detection" },
  { icon: "🌳", title: "Multi-Agent Trees", desc: "Parent → child span linking across agents" },
  { icon: "📊", title: "Cost Attribution", desc: "Per-agent, per-tool, cache token breakdown" },
  { icon: "🚨", title: "Anomaly Detection", desc: "Z-score vs 7-day baseline, auto-alerts" },
];

/* ── Section ────────────────────────────────────────────── */
export default function IntegrationsSection() {
  return (
    <section className="py-24" style={{ background: "var(--bg-deep)" }}>
      <div className="max-w-6xl mx-auto px-6">
        {/* Header */}
        <ScrollReveal className="text-center mb-16">
          <p
            className="text-xs font-medium uppercase tracking-[0.15em] mb-3"
            style={{ fontFamily: "var(--font-geist-mono)", color: "var(--indigo)" }}
          >
            Integrations
          </p>
          <h2
            className="font-bold tracking-tight"
            style={{ fontSize: "clamp(1.8rem, 3.5vw, 2.5rem)", fontFamily: "var(--font-geist-sans)" }}
          >
            <span className="gradient-text">Drop into any framework.</span>
          </h2>
          <p className="mt-4 max-w-xl mx-auto" style={{ color: "var(--muted)" }}>
            One line of code. Full tracing, prevention, and cost attribution.
            Zero-code for Claude Agent SDK and CrewAI.
          </p>
        </ScrollReveal>

        {/* Integration cards with magnetic hover */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
          {INTEGRATIONS.map((intg, i) => {
            const st = STATUS_STYLES[intg.status];
            return (
              <ScrollReveal key={i} delay={i * 60}>
                <MagneticHover strength={0.15}>
                  <SpotlightCard
                    className="rounded-xl p-5 h-full transition-all duration-200"
                    style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
                    spotlightColor={`${intg.color}12`}
                  >
                    <div className="flex items-start justify-between mb-3">
                      <div
                        className="w-10 h-10 rounded-lg flex items-center justify-center"
                        style={{ background: `${intg.color}15`, color: intg.color }}
                      >
                        {intg.icon}
                      </div>
                      <span
                        className="text-[10px] font-medium rounded-full px-2 py-0.5"
                        style={{ background: st.bg, color: st.color, border: `1px solid ${st.border}` }}
                      >
                        {st.label}
                      </span>
                    </div>
                    <h3 className="font-semibold text-sm mb-1" style={{ color: "var(--text)", fontFamily: "var(--font-geist-sans)" }}>
                      {intg.name}
                    </h3>
                    <p className="text-xs mb-3" style={{ color: "var(--dimmer)" }}>{intg.sub}</p>
                    <div className="flex flex-wrap gap-1">
                      {intg.features.map((f, j) => (
                        <span
                          key={j}
                          className="text-[10px] rounded px-1.5 py-0.5"
                          style={{ background: "var(--surface-2)", color: "var(--muted)", border: "1px solid var(--border-dim)" }}
                        >
                          {f}
                        </span>
                      ))}
                    </div>
                  </SpotlightCard>
                </MagneticHover>
              </ScrollReveal>
            );
          })}
        </div>

        {/* Complement callout */}
        <ScrollReveal delay={200}>
          <SpotlightCard
            className="mt-8 rounded-xl p-6 max-w-3xl mx-auto"
            style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
          >
            <p className="font-semibold text-sm mb-1" style={{ color: "var(--text)" }}>
              Langfuse watches the brain. LangSight watches the hands.
            </p>
            <p className="text-sm" style={{ color: "var(--muted)" }}>
              Use alongside Langfuse, LangWatch, or LangSmith. They trace model reasoning.
              LangSight guards the tool layer — loops, budgets, health, security, blast radius.
            </p>
          </SpotlightCard>
        </ScrollReveal>

        {/* Capabilities */}
        <ScrollReveal className="mt-20 text-center mb-12">
          <p
            className="text-xs font-medium uppercase tracking-[0.15em] mb-3"
            style={{ fontFamily: "var(--font-geist-mono)", color: "var(--indigo)" }}
          >
            What LangSight captures
          </p>
          <h2
            className="font-bold tracking-tight"
            style={{ fontSize: "clamp(1.6rem, 3vw, 2.2rem)", fontFamily: "var(--font-geist-sans)" }}
          >
            <span className="gradient-text">Prevention + detection + monitoring.</span>
          </h2>
        </ScrollReveal>

        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {CAPABILITIES.map((cap, i) => (
            <ScrollReveal key={i} delay={i * 60}>
              <SpotlightCard
                className="rounded-xl p-5 h-full transition-all duration-200 hover:-translate-y-0.5"
                style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
              >
                <div className="text-2xl mb-3">{cap.icon}</div>
                <h3 className="font-semibold text-sm mb-1" style={{ color: "var(--text)", fontFamily: "var(--font-geist-sans)" }}>
                  {cap.title}
                </h3>
                <p className="text-xs leading-relaxed" style={{ color: "var(--muted)" }}>{cap.desc}</p>
              </SpotlightCard>
            </ScrollReveal>
          ))}
        </div>
      </div>
    </section>
  );
}
