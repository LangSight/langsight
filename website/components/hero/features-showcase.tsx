"use client";

/**
 * FeaturesShowcase — Alternating feature rows with real dashboard screenshots.
 * Uses TiltCard on images, ScrollReveal on everything, SpotlightCard on bullets.
 */

import { TiltCard, GlowBorder, ScrollReveal, SpotlightCard } from "./animated-primitives";

/* ── Feature data ───────────────────────────────────────── */
interface Feature {
  pillar: string;
  pillarColor: string;
  title: string;
  subtitle: string;
  bullets: string[];
  screenshot: string;
  alt: string;
}

const FEATURES: Feature[] = [
  {
    pillar: "MAP",
    pillarColor: "#6366F1",
    title: "The clearest way to see what your agents did.",
    subtitle: "A visual DAG of your entire agent session — coordinator → sub-agents → MCP servers — with call counts, latency, and full detail on click. Understand any session in seconds.",
    bullets: [
      "Visual agent topology — see who called whom at a glance",
      "Click any node for full input/output JSON, latency, tokens",
      "Handoff arrows between agents with timing",
      "Per-agent and per-server call counts + avg latency",
    ],
    screenshot: "/screenshots/session_graph_lineage.png",
    alt: "LangSight session graph showing coordinator delegating to sql_analyst, data_quality, and reporter agents connected to MCP servers",
  },
  {
    pillar: "PREVENT",
    pillarColor: "#EF4444",
    title: "Per-agent guardrails. From the dashboard.",
    subtitle: "Loop detection, budget limits, max steps — configured per agent without code changes. Set thresholds, choose warn or terminate, control costs in real-time.",
    bullets: [
      "Loop detection: fire after N consecutive repeat calls",
      "Action: Warn or Terminate — your choice per agent",
      "Budget controls: max cost per session in USD",
      "Soft alert threshold + hard kill limit",
      "Max wall time to prevent runaway sessions",
    ],
    screenshot: "/screenshots/agent_Details.png",
    alt: "LangSight agent detail page showing loop detection settings, budget controls, and max steps configuration",
  },
  {
    pillar: "MONITOR",
    pillarColor: "#6366F1",
    title: "Agent runtime health at a glance.",
    subtitle: "Sessions, tool calls, error rate, P99 latency, token usage — all in real-time. Overview, Models, and Tools tabs. 1h to 7d time ranges.",
    bullets: [
      "4 KPI cards: sessions, tool calls, error rate, avg latency",
      "Agent sessions + error rate trend charts",
      "P99 latency tracking across all agents",
      "Token usage breakdown (input, output, cache)",
    ],
    screenshot: "/screenshots/dashbaord_1_page.png",
    alt: "LangSight dashboard overview showing 124 sessions, 1032 tool calls, 6.6% error rate",
  },
  {
    pillar: "MONITOR",
    pillarColor: "#6366F1",
    title: "MCP infrastructure monitoring.",
    subtitle: "Dedicated MCP section: tool call volume, error rates, P99 latency per server. Error breakdown by type. Fleet health at a glance.",
    bullets: [
      "MCP tool calls, error rate, P99 latency per server",
      "Error breakdown: API unavailable, agent crash, auth errors",
      "Server fleet health: green dots = all healthy",
      "Correlate MCP failures with agent errors",
    ],
    screenshot: "/screenshots/dashbaord_2_page.png",
    alt: "LangSight MCP infrastructure dashboard showing tool calls, error rate, P99 latency, and 11 healthy servers",
  },
  {
    pillar: "DETECT",
    pillarColor: "#F59E0B",
    title: "Every session. Filterable. Searchable.",
    subtitle: "Session list with health tags, agent name, call count, duration, tokens, cost. Filter by status, agent, or health tag. Click to drill into full trace.",
    bullets: [
      "Health tags: success, failure, loop, budget exceeded",
      "Filter by agent, status, health tag",
      "Sort by duration, cost, token count",
      "Click to drill into full session trace + graph",
    ],
    screenshot: "/screenshots/sessions_list.png",
    alt: "LangSight sessions list showing 124 sessions with filters for status, agents, health tags",
  },
  {
    pillar: "MONITOR",
    pillarColor: "#6366F1",
    title: "Cost attribution. Per-tool. Per-agent. Per-model.",
    subtitle: "See exactly where your money goes. Total cost, LLM cost, tool call cost — broken down by service, tool, model, and cost type.",
    bullets: [
      "$1.22 total → $0.13 LLM + $1.09 tool calls",
      "Cost per call: $0.001 for tools, $0.135 for Gemini",
      "Filter by service, agent, model, cost type",
      "2.1M input tokens, 130K output tokens breakdown",
    ],
    screenshot: "/screenshots/cost_attribution_page.png",
    alt: "LangSight cost attribution page showing $1.22 total cost broken down by tool",
  },
  {
    pillar: "DETECT",
    pillarColor: "#F59E0B",
    title: "MCP health + blast radius + AI root cause.",
    subtitle: "Per-server health panel: if this server went down, how many agents and sessions are affected? AI-powered root cause investigation built in.",
    bullets: [
      "Blast radius: agents, sessions, and calls at risk",
      "Health, Tools, Consumers, Drift, Schema, Logs tabs",
      "AI root cause investigation (Anthropic, 1h-24h lookback)",
      "Click \"Run Investigation\" for automated RCA report",
    ],
    screenshot: "/screenshots/mcp_servers_page_with_health_status.png",
    alt: "LangSight MCP servers page showing blast radius analysis and AI root cause investigation",
  },
  {
    pillar: "DETECT",
    pillarColor: "#F59E0B",
    title: "8 alert types. Slack + webhooks.",
    subtitle: "Agent failure, SLO breached, anomaly (critical + warning), security findings, MCP server down/recovered. Toggle each independently.",
    bullets: [
      "Agent Failure: session with failed tool calls",
      "SLO Breached: service level objective violated",
      "Anomaly: z-score >=3 (critical) or >=2 (warning)",
      "MCP Down/Recovered: server health state changes",
      "Incomplete session tracking and tagging",
    ],
    screenshot: "/screenshots/Alerts_page.png",
    alt: "LangSight alerts page showing 8 alert rule types with toggles and Slack notifications",
  },
];

/* ── Section ────────────────────────────────────────────── */
export default function FeaturesShowcase() {
  return (
    <section className="py-24" style={{ background: "var(--bg)" }}>
      <div className="max-w-6xl mx-auto px-6">
        {/* Header */}
        <ScrollReveal className="text-center mb-20">
          <p
            className="text-xs font-medium uppercase tracking-[0.15em] mb-3"
            style={{ fontFamily: "var(--font-geist-mono)", color: "var(--indigo)" }}
          >
            The product
          </p>
          <h2
            className="font-bold tracking-tight"
            style={{ fontSize: "clamp(1.8rem, 3.5vw, 2.5rem)", fontFamily: "var(--font-geist-sans)" }}
          >
            <span className="gradient-text">Built for the engineer</span>
            <br />
            <span className="gradient-indigo">who gets paged at 2 AM.</span>
          </h2>
          <p className="mt-4 max-w-xl mx-auto" style={{ color: "var(--muted)" }}>
            Every page answers a question you'd ask during an incident.
            No dashboards for dashboards' sake.
          </p>
        </ScrollReveal>

        {/* Feature rows */}
        <div className="space-y-32">
          {FEATURES.map((feat, i) => {
            const isReversed = i % 2 === 1;
            const isHero = i === 0;

            if (isHero) {
              return (
                <div key={i}>
                  {/* Full-width hero feature */}
                  <ScrollReveal className="text-center mb-10">
                    <span
                      className="text-[10px] font-bold uppercase tracking-wider rounded px-2 py-1 inline-block mb-4"
                      style={{
                        color: feat.pillarColor,
                        background: `${feat.pillarColor}12`,
                        border: `1px solid ${feat.pillarColor}25`,
                      }}
                    >
                      {feat.pillar}
                    </span>
                    <h3
                      className="font-bold tracking-tight mb-3"
                      style={{
                        fontSize: "clamp(1.5rem, 3vw, 2rem)",
                        fontFamily: "var(--font-geist-sans)",
                        color: "var(--text)",
                      }}
                    >
                      {feat.title}
                    </h3>
                    <p className="max-w-2xl mx-auto text-sm" style={{ color: "var(--muted)" }}>
                      {feat.subtitle}
                    </p>
                  </ScrollReveal>

                  {/* Full-width screenshot with glow + tilt */}
                  <ScrollReveal delay={200}>
                    <TiltCard intensity={4} className="max-w-5xl mx-auto">
                      <GlowBorder borderRadius="12px" glowOpacity={0.3} hoverOpacity={0.55}>
                        <div style={{ background: "var(--surface)" }}>
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img src={feat.screenshot} alt={feat.alt} className="w-full h-auto block" loading="lazy" />
                        </div>
                      </GlowBorder>
                    </TiltCard>
                  </ScrollReveal>

                  {/* Bullets below */}
                  <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5 mt-10 max-w-4xl mx-auto">
                    {feat.bullets.map((b, j) => (
                      <ScrollReveal key={j} delay={300 + j * 80}>
                        <SpotlightCard
                          className="rounded-lg p-3 h-full"
                          style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
                          spotlightColor={`${feat.pillarColor}10`}
                        >
                          <div className="flex items-start gap-2">
                            <span className="text-xs mt-0.5 shrink-0" style={{ color: feat.pillarColor }}>+</span>
                            <span className="text-xs" style={{ color: "var(--muted)" }}>{b}</span>
                          </div>
                        </SpotlightCard>
                      </ScrollReveal>
                    ))}
                  </div>
                </div>
              );
            }

            // Alternating rows
            return (
              <div
                key={i}
                className="grid lg:grid-cols-2 gap-10 xl:gap-16 items-center"
              >
                {/* Text side */}
                <ScrollReveal
                  className={isReversed ? "lg:order-2" : ""}
                  direction={isReversed ? "right" : "left"}
                >
                  <span
                    className="text-[10px] font-bold uppercase tracking-wider rounded px-2 py-1 inline-block mb-4"
                    style={{
                      color: feat.pillarColor,
                      background: `${feat.pillarColor}12`,
                      border: `1px solid ${feat.pillarColor}25`,
                    }}
                  >
                    {feat.pillar}
                  </span>
                  <h3
                    className="font-bold tracking-tight mb-3"
                    style={{
                      fontSize: "clamp(1.3rem, 2.5vw, 1.7rem)",
                      fontFamily: "var(--font-geist-sans)",
                      color: "var(--text)",
                      letterSpacing: "-0.02em",
                    }}
                  >
                    {feat.title}
                  </h3>
                  <p className="text-sm leading-relaxed mb-5" style={{ color: "var(--muted)" }}>
                    {feat.subtitle}
                  </p>
                  <ul className="space-y-2">
                    {feat.bullets.map((b, j) => (
                      <li key={j} className="flex items-start gap-2.5 text-sm">
                        <span
                          className="w-1.5 h-1.5 rounded-full shrink-0 mt-1.5"
                          style={{ background: feat.pillarColor }}
                        />
                        <span style={{ color: "var(--muted)" }}>{b}</span>
                      </li>
                    ))}
                  </ul>
                </ScrollReveal>

                {/* Screenshot side with tilt + glow */}
                <ScrollReveal
                  className={isReversed ? "lg:order-1" : ""}
                  delay={150}
                  direction={isReversed ? "left" : "right"}
                >
                  <TiltCard intensity={6}>
                    <div
                      className="rounded-xl overflow-hidden"
                      style={{
                        border: "1px solid var(--border)",
                        boxShadow: "0 20px 50px -12px rgba(0,0,0,0.2), 0 0 30px rgba(99,102,241,0.04)",
                      }}
                    >
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={feat.screenshot} alt={feat.alt} className="w-full h-auto block" loading="lazy" />
                    </div>
                  </TiltCard>
                </ScrollReveal>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
