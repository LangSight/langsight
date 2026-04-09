"use client";

import { Nav, Footer, useTheme } from "@/components/site-shell";
import {
  ScrollReveal,
  SpotlightCard,
  TiltCard,
  GlowBorder,
  MagneticHover,
  SharedKeyframes,
} from "@/components/hero/animated-primitives";

/* -- Integration data ------------------------------------------------- */
interface Integration {
  id: string;
  name: string;
  status: "verified" | "beta" | "coming";
  tagline: string;
  description: string;
  setupCode: string;
  features: string[];
  color: string;
}

const INTEGRATIONS: Integration[] = [
  {
    id: "claude-agent-sdk",
    name: "Claude Agent SDK",
    status: "verified",
    tagline: "Zero-code multi-agent monitoring",
    description:
      "LangSight captures every operation in the Claude Agent SDK automatically. Multi-agent orchestration with sub-agent handoffs, tool calls across MCP servers, LLM reasoning steps, and full session reconstruction. In head-to-head benchmarks, LangSight captured 57 spans per session compared to 0 tool spans from Langfuse and LangSmith.",
    setupCode: `import langsight
from agents import Agent, Runner

# One line. Everything instrumented.
langsight.auto_patch()

agent = Agent(
    name="support-agent",
    model="claude-sonnet-4-20250514",
    mcp_servers=[postgres_mcp, slack_mcp],
)
result = await Runner.run(agent, "Check order status")

# LangSight now traces:
# - Agent reasoning (llm_input / llm_output)
# - Tool calls (postgres-mcp/query, slack-mcp/notify)
# - Sub-agent handoffs (billing-agent, etc.)
# - Tokens, cost, latency per operation`,
    features: [
      "Zero-code auto_patch() instrumentation",
      "Multi-agent call tree reconstruction",
      "Sub-agent handoff tracing with attribution",
      "MCP tool call capture (args + result)",
      "LLM reasoning traces (llm_input / llm_output)",
      "Token counts (input, output, cache)",
      "Per-session cost attribution",
      "Loop detection across agent chains",
      "Budget enforcement per session",
    ],
    color: "#D97706",
  },
  {
    id: "crewai",
    name: "CrewAI",
    status: "verified",
    tagline: "Native event bus with 19 handlers",
    description:
      "LangSight connects directly to CrewAI's event bus, capturing crew execution, task delegation, agent-to-agent handoffs, and LLM operations. No wrappers needed. Works with CrewAI 1.6.1+ and supports Anthropic, OpenAI, and Gemini as the underlying LLM provider.",
    setupCode: `import langsight
from crewai import Crew, Agent, Task

# Hooks into CrewAI's event bus automatically
langsight.auto_patch()

researcher = Agent(role="Researcher", ...)
writer = Agent(role="Writer", ...)

crew = Crew(
    agents=[researcher, writer],
    tasks=[research_task, write_task],
)
result = crew.kickoff()

# LangSight captures:
# - Crew input/output
# - Task execution per agent
# - A2A handoffs (researcher -> writer)
# - LLM spans from any provider`,
    features: [
      "Native CrewAI event bus integration (19 handlers)",
      "Crew input/output capture",
      "Task execution tracing per agent",
      "Agent-to-agent (A2A) handoff tracking",
      "LLM spans from Anthropic, OpenAI, Gemini",
      "llm_input / llm_output on every LLM call",
      "Token and cost attribution per agent",
      "Works with CrewAI 1.6.1+",
    ],
    color: "#F59E0B",
  },
  {
    id: "anthropic-sdk",
    name: "Anthropic SDK",
    status: "verified",
    tagline: "Messages API + streaming support",
    description:
      "Direct instrumentation of the Anthropic Python SDK. Captures every messages.create call including streaming responses, token counts, tool use blocks, and cost calculations based on model pricing.",
    setupCode: `import langsight
import anthropic

langsight.auto_patch()

client = anthropic.Anthropic()
response = client.messages.create(
    model="claude-sonnet-4-20250514",
    messages=[{"role": "user", "content": "..."}],
)

# Traced: model, tokens, cost, latency, content`,
    features: [
      "Messages API tracing",
      "Streaming response capture",
      "Token counts (input, output, cache read/write)",
      "Cost tracking per call",
      "Tool use block capture",
    ],
    color: "#D97706",
  },
  {
    id: "openai",
    name: "OpenAI SDK",
    status: "beta",
    tagline: "Chat completions + function calls",
    description:
      "Monitors OpenAI Chat Completions and Agents SDK. Captures model selection, token usage, function/tool calls, and streaming responses. Currently in beta with full GA planned.",
    setupCode: `import langsight
from openai import OpenAI

langsight.auto_patch()

client = OpenAI()
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "..."}],
)

# Traced: model, tokens, function calls, cost`,
    features: [
      "Chat Completions tracing",
      "Function call / tool_call capture",
      "Token usage tracking",
      "Streaming support",
      "Cost tracking per call",
    ],
    color: "#10B981",
  },
  {
    id: "gemini",
    name: "Google Gemini",
    status: "beta",
    tagline: "Generative AI SDK support",
    description:
      "Instruments Google's Generative AI SDK for Gemini models. Captures generate_content calls, token usage, and response content. Currently in beta.",
    setupCode: `import langsight
import google.generativeai as genai

langsight.auto_patch()

model = genai.GenerativeModel("gemini-2.0-flash")
response = model.generate_content("...")

# Traced: model, tokens, content, latency`,
    features: [
      "generate_content tracing",
      "Token usage capture",
      "Model selection tracking",
      "Cost attribution",
    ],
    color: "#4285F4",
  },
  {
    id: "otlp",
    name: "OTLP / OpenTelemetry",
    status: "verified",
    tagline: "Any OTEL-compatible framework",
    description:
      "LangSight accepts OTLP traces natively. If your agent framework emits OpenTelemetry spans following gen_ai semantic conventions, LangSight ingests them automatically. Works with any language or framework that supports OTLP export.",
    setupCode: `# Point your OTEL exporter at LangSight
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:8000
export OTEL_EXPORTER_OTLP_HEADERS="x-api-key=YOUR_KEY"

# Any framework that emits OTLP traces
# will appear in LangSight automatically.
# gen_ai.* semantic conventions are mapped
# to LangSight's native span types.`,
    features: [
      "OTLP/gRPC and OTLP/HTTP ingest",
      "gen_ai semantic convention mapping",
      "Works with any language (Python, Node, Go, Rust)",
      "Compatible with OpenLLMetry, Traceloop, etc.",
      "Automatic span type classification",
    ],
    color: "#6366F1",
  },
];

const STATUS_BADGE = {
  verified: { label: "Verified", bg: "rgba(34,197,94,0.12)", color: "#22C55E", border: "rgba(34,197,94,0.25)" },
  beta: { label: "Beta", bg: "rgba(234,179,8,0.12)", color: "#EAB308", border: "rgba(234,179,8,0.25)" },
  coming: { label: "Coming soon", bg: "rgba(99,102,241,0.08)", color: "var(--dimmer)", border: "rgba(99,102,241,0.15)" },
};

/* -- Page ------------------------------------------------------------- */
export default function IntegrationsPage() {
  const { dark, toggle } = useTheme();

  return (
    <>
      {/* Obsidian palette */}
      <style jsx global>{`
        :root {
          --indigo: #4F46E5;
          --indigo-dim: rgba(79,70,229,0.08);
          --indigo-glow: rgba(79,70,229,0.12);
          --indigo-strong: rgba(79,70,229,0.20);
          --terminal-bg: #F8F9FA;
          --terminal-bar: #F1F2F4;
          --code-text: #4F46E5;
        }
        .dark {
          --bg: #050507; --bg-deep: #030305;
          --surface: #0E0E12; --surface-2: #131317;
          --border: #1E1E24; --border-dim: #141418;
          --text: #E8E8ED; --muted: #9898A6; --dimmer: #5C5C6B;
          --indigo: #6366F1;
          --indigo-dim: rgba(99,102,241,0.10);
          --indigo-glow: rgba(99,102,241,0.18);
          --indigo-strong: rgba(99,102,241,0.25);
          --green: #34D399; --red: #F87171; --yellow: #FBBF24; --orange: #FB923C;
          --terminal-bg: #08080B; --terminal-bar: #0E0E12;
          --code-text: #C4B5FD;
        }
        .gradient-text {
          background: linear-gradient(135deg, var(--text) 0%, var(--muted) 100%);
          -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
        }
        .gradient-indigo {
          background: linear-gradient(135deg, #818CF8 0%, #6366F1 50%, #A78BFA 100%);
          -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
        }
      `}</style>

      <SharedKeyframes />
      <Nav dark={dark} toggle={toggle} />

      <main style={{ background: "var(--bg)" }}>
        {/* Hero */}
        <section className="relative pt-32 pb-20 overflow-hidden">
          <div className="absolute inset-0 pointer-events-none" aria-hidden="true">
            <div
              className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[400px] rounded-full blur-[140px]"
              style={{ background: "rgba(99,102,241,0.08)" }}
            />
          </div>

          <div className="relative max-w-4xl mx-auto px-6 text-center">
            <ScrollReveal>
              <div
                className="inline-flex items-center gap-2 rounded-full px-4 py-1.5 text-xs font-medium mb-6"
                style={{ background: "var(--indigo-dim)", border: "1px solid var(--indigo-strong)", color: "var(--indigo)" }}
              >
                6 Frameworks Supported
              </div>
            </ScrollReveal>

            <ScrollReveal delay={100}>
              <h1
                className="font-bold tracking-tight mb-6"
                style={{ fontSize: "clamp(2.2rem, 5vw, 3.5rem)", fontFamily: "var(--font-geist-sans)" }}
              >
                <span className="gradient-text">Monitor any AI agent framework.</span>
                <br />
                <span className="gradient-indigo">Two lines of code.</span>
              </h1>
            </ScrollReveal>

            <ScrollReveal delay={200}>
              <p className="text-lg leading-relaxed max-w-2xl mx-auto mb-8" style={{ color: "var(--muted)" }}>
                LangSight integrates with Claude Agent SDK, CrewAI, Anthropic SDK, OpenAI, Google Gemini, and any OTLP-compatible framework. Add monitoring without changing your agent code.
              </p>
            </ScrollReveal>

            <ScrollReveal delay={300}>
              <div className="flex flex-wrap justify-center gap-3">
                <MagneticHover strength={0.2}>
                  <a
                    href="https://docs.langsight.dev/quickstart"
                    className="text-sm font-semibold px-6 py-2.5 rounded-lg transition-all hover:opacity-90 hover:-translate-y-px"
                    style={{ background: "var(--indigo)", color: "white", boxShadow: "0 0 20px rgba(99,102,241,0.25)" }}
                  >
                    Start monitoring →
                  </a>
                </MagneticHover>
                <MagneticHover strength={0.2}>
                  <a
                    href="https://github.com/LangSight/langsight"
                    className="text-sm font-semibold px-6 py-2.5 rounded-lg transition-all hover:-translate-y-px"
                    style={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text)" }}
                  >
                    View on GitHub
                  </a>
                </MagneticHover>
              </div>
            </ScrollReveal>
          </div>
        </section>

        {/* Integration detail sections */}
        {INTEGRATIONS.map((intg, i) => {
          const st = STATUS_BADGE[intg.status];
          const isReversed = i % 2 === 1;

          return (
            <section
              key={intg.id}
              id={intg.id}
              className="py-20 scroll-mt-20"
              style={{ background: i % 2 === 0 ? "var(--bg)" : "var(--bg-deep)" }}
            >
              <div className="max-w-6xl mx-auto px-6">
                <div className={`grid lg:grid-cols-2 gap-12 items-start ${isReversed ? "" : ""}`}>
                  {/* Text side */}
                  <ScrollReveal direction={isReversed ? "right" : "left"} className={isReversed ? "lg:order-2" : ""}>
                    <div className="flex items-center gap-3 mb-4">
                      <span
                        className="text-[10px] font-medium rounded-full px-2.5 py-0.5"
                        style={{ background: st.bg, color: st.color, border: `1px solid ${st.border}` }}
                      >
                        {st.label}
                      </span>
                    </div>

                    <h2
                      className="font-bold tracking-tight mb-2"
                      style={{ fontSize: "clamp(1.5rem, 3vw, 2rem)", fontFamily: "var(--font-geist-sans)", color: "var(--text)" }}
                    >
                      {intg.name}
                    </h2>
                    <p className="text-sm font-medium mb-4" style={{ color: "var(--indigo)" }}>
                      {intg.tagline}
                    </p>
                    <p className="text-sm leading-relaxed mb-6" style={{ color: "var(--muted)" }}>
                      {intg.description}
                    </p>

                    <div className="space-y-2">
                      {intg.features.map((feat, j) => (
                        <div key={j} className="flex items-start gap-2 text-sm">
                          <span className="shrink-0 mt-0.5" style={{ color: "#22C55E" }}>+</span>
                          <span style={{ color: "var(--muted)" }}>{feat}</span>
                        </div>
                      ))}
                    </div>
                  </ScrollReveal>

                  {/* Code side */}
                  <ScrollReveal delay={150} direction={isReversed ? "left" : "right"} className={isReversed ? "lg:order-1" : ""}>
                    <TiltCard intensity={4}>
                      <GlowBorder borderRadius="12px" glowOpacity={0.2} hoverOpacity={0.4}>
                        <div style={{ background: "var(--terminal-bg)" }}>
                          <div className="flex items-center justify-between px-4 py-2.5" style={{ borderBottom: "1px solid var(--border)" }}>
                            <div className="flex items-center gap-2">
                              <div className="w-3 h-3 rounded-full" style={{ background: "#EF444460" }} />
                              <div className="w-3 h-3 rounded-full" style={{ background: "#EAB30860" }} />
                              <div className="w-3 h-3 rounded-full" style={{ background: "#22C55E60" }} />
                            </div>
                            <span className="text-[10px] rounded px-1.5 py-0.5"
                              style={{ background: "var(--indigo-dim)", color: "var(--indigo)", border: "1px solid var(--indigo-strong)" }}>
                              {intg.id === "otlp" ? "bash" : "python"}
                            </span>
                          </div>
                          <pre className="p-5 text-xs overflow-x-auto leading-relaxed" style={{ fontFamily: "var(--font-geist-mono)", color: "var(--code-text)" }}>
                            {intg.setupCode}
                          </pre>
                        </div>
                      </GlowBorder>
                    </TiltCard>
                  </ScrollReveal>
                </div>
              </div>
            </section>
          );
        })}

        {/* CTA */}
        <section className="py-20" style={{ background: "var(--bg)" }}>
          <ScrollReveal className="max-w-3xl mx-auto px-6">
            <GlowBorder borderRadius="16px" glowOpacity={0.2} hoverOpacity={0.45}>
              <SpotlightCard
                className="rounded-2xl p-10 text-center"
                style={{ background: "var(--surface)" }}
              >
                <h2
                  className="font-bold tracking-tight mb-4"
                  style={{ fontSize: "clamp(1.5rem, 3vw, 2.2rem)", fontFamily: "var(--font-geist-sans)" }}
                >
                  <span className="gradient-text">Your framework. Monitored in 2 lines.</span>
                </h2>
                <p className="text-base mb-8" style={{ color: "var(--muted)" }}>
                  Free, open source, self-hosted. No data leaves your network. Apache 2.0.
                </p>
                <div className="flex flex-wrap justify-center gap-3">
                  <MagneticHover strength={0.2}>
                    <a
                      href="https://docs.langsight.dev/quickstart"
                      className="text-sm font-semibold px-6 py-2.5 rounded-lg transition-all hover:opacity-90 hover:-translate-y-px"
                      style={{ background: "var(--indigo)", color: "white", boxShadow: "0 0 20px rgba(99,102,241,0.25)" }}
                    >
                      Quickstart guide →
                    </a>
                  </MagneticHover>
                  <MagneticHover strength={0.2}>
                    <a
                      href="/security"
                      className="text-sm font-semibold px-6 py-2.5 rounded-lg transition-all hover:-translate-y-px"
                      style={{ background: "var(--surface-2)", border: "1px solid var(--border)", color: "var(--text)" }}
                    >
                      MCP security scanning →
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
