"use client";

/**
 * BenchmarkSection — Capability matrix with animated grid bg,
 * spring counters, glowing rows, and scroll reveals.
 */

import { useEffect, useRef, useState } from "react";
import { AnimatedGridBg, ScrollReveal, SpotlightCard, GlowBorder } from "./animated-primitives";

/* ── Animated counter with spring bounce ────────────────── */
function CountUp({ target, suffix = "", duration = 1500, delay = 0 }: { target: number; suffix?: string; duration?: number; delay?: number }) {
  const [count, setCount] = useState(0);
  const ref = useRef<HTMLSpanElement>(null);
  const started = useRef(false);

  useEffect(() => {
    if (!ref.current) return;
    const obs = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && !started.current) {
          started.current = true;
          const start = performance.now() + delay;
          const tick = (now: number) => {
            const elapsed = Math.max(0, now - start);
            const progress = Math.min(elapsed / duration, 1);
            // Spring overshoot easing
            const spring = 1 - Math.pow(1 - progress, 3) * Math.cos(progress * Math.PI * 0.8);
            const eased = Math.min(spring, 1);
            setCount(Math.round(eased * target));
            if (progress < 1) requestAnimationFrame(tick);
          };
          requestAnimationFrame(tick);
        }
      },
      { threshold: 0.3 }
    );
    obs.observe(ref.current);
    return () => obs.disconnect();
  }, [target, duration, delay]);

  return <span ref={ref}>{count}{suffix}</span>;
}

/* ── Capability matrix data ─────────────────────────────── */
interface Row {
  capability: string;
  category: "prevent" | "detect" | "monitor" | "observe";
  langsight: "yes" | "no";
  langsmith: "yes" | "no" | "partial";
  langfuse: "yes" | "no" | "partial";
  opik: "yes" | "no" | "partial";
}

const ROWS: Row[] = [
  { capability: "Loop detection (pattern-based)", category: "prevent", langsight: "yes", langsmith: "no", langfuse: "no", opik: "no" },
  { capability: "Budget enforcement (auto-kill)", category: "prevent", langsight: "yes", langsmith: "no", langfuse: "no", opik: "no" },
  { capability: "Circuit breakers (tool-level)", category: "prevent", langsight: "yes", langsmith: "no", langfuse: "no", opik: "no" },
  { capability: "MCP health monitoring", category: "detect", langsight: "yes", langsmith: "no", langfuse: "no", opik: "no" },
  { capability: "Schema drift detection", category: "detect", langsight: "yes", langsmith: "no", langfuse: "no", opik: "no" },
  { capability: "Security scanning (CVE + OWASP)", category: "detect", langsight: "yes", langsmith: "no", langfuse: "no", opik: "no" },
  { capability: "Anomaly detection (z-score)", category: "monitor", langsight: "yes", langsmith: "no", langfuse: "no", opik: "no" },
  { capability: "Blast radius mapping", category: "monitor", langsight: "yes", langsmith: "no", langfuse: "no", opik: "no" },
  { capability: "Agent tracing", category: "observe", langsight: "yes", langsmith: "yes", langfuse: "yes", opik: "yes" },
  { capability: "Cost tracking", category: "observe", langsight: "yes", langsmith: "yes", langfuse: "yes", opik: "yes" },
  { capability: "LLM evals", category: "observe", langsight: "no", langsmith: "yes", langfuse: "yes", opik: "yes" },
];

const CELL: Record<string, { label: string; color: string; bg: string }> = {
  yes: { label: "Yes", color: "#22C55E", bg: "rgba(34,197,94,0.10)" },
  no: { label: "—", color: "var(--dimmer)", bg: "transparent" },
  partial: { label: "Partial", color: "#EAB308", bg: "rgba(234,179,8,0.08)" },
};

const CAT_LABELS: Record<string, { label: string; color: string }> = {
  prevent: { label: "PREVENT", color: "#EF4444" },
  detect: { label: "DETECT", color: "#F59E0B" },
  monitor: { label: "MONITOR", color: "#6366F1" },
  observe: { label: "OBSERVE", color: "var(--dimmer)" },
};

/* ── Section ────────────────────────────────────────────── */
export default function BenchmarkSection() {
  const tableRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = tableRef.current;
    if (!el) return;
    let cancelled = false;
    const run = async () => {
      const { animate, stagger } = await import("animejs");
      if (cancelled) return;
      const obs = new IntersectionObserver(
        (entries) => {
          if (entries[0].isIntersecting) {
            animate(el.querySelectorAll("tr[data-row]"), {
              opacity: [0, 1],
              translateX: [-10, 0],
              delay: stagger(35),
              duration: 450,
              easing: "easeOutCubic",
            });
            obs.disconnect();
          }
        },
        { threshold: 0.1 }
      );
      obs.observe(el);
    };
    run();
    return () => { cancelled = true; };
  }, []);

  return (
    <section className="relative py-24 overflow-hidden" style={{ background: "var(--bg-deep)" }}>
      {/* Animated dot grid background */}
      <AnimatedGridBg />

      <div className="relative max-w-5xl mx-auto px-6">
        {/* Header */}
        <ScrollReveal className="text-center mb-14">
          <p
            className="text-xs font-medium uppercase tracking-[0.15em] mb-3"
            style={{ fontFamily: "var(--font-geist-mono)", color: "var(--indigo)" }}
          >
            Why LangSight exists
          </p>
          <h2
            className="font-bold tracking-tight"
            style={{ fontSize: "clamp(1.8rem, 3.5vw, 2.5rem)", fontFamily: "var(--font-geist-sans)" }}
          >
            <span className="gradient-text">Observability tools watch.</span>
            <br />
            <span className="gradient-indigo">LangSight prevents.</span>
          </h2>
          <p className="mt-4 max-w-2xl mx-auto text-sm" style={{ color: "var(--muted)" }}>
            Every platform in the market traces what happened <em>after</em> the fact.
            Nobody stops loops, enforces budgets, or circuit-breaks failing tools at runtime.
            That's the gap LangSight fills.
          </p>
        </ScrollReveal>

        {/* Stats bar with spotlight hover */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-14">
          {[
            { n: 8, suffix: "", label: "Unique capabilities", sub: "no competitor has", accent: false },
            { n: 0, suffix: "", label: "Competitors with", sub: "runtime prevention", accent: true },
            { n: 66, suffix: "x", label: "More spans captured", sub: "vs LangSmith (April '26)", accent: false },
            { n: 0, suffix: "", label: "Vendor lock-in", sub: "Apache 2.0, self-hosted", accent: false },
          ].map((s, i) => (
            <ScrollReveal key={i} delay={i * 100}>
              <SpotlightCard
                className="rounded-xl p-6 text-center h-full"
                style={{
                  background: s.accent ? "var(--indigo-dim)" : "var(--surface)",
                  border: `1px solid ${s.accent ? "var(--indigo-strong)" : "var(--border)"}`,
                }}
                spotlightColor={s.accent ? "rgba(99,102,241,0.15)" : "rgba(99,102,241,0.06)"}
              >
                <div
                  className="font-bold leading-none mb-1"
                  style={{
                    fontSize: "2.5rem",
                    fontFamily: "var(--font-geist-sans)",
                    color: s.accent ? "var(--indigo)" : "var(--text)",
                    letterSpacing: "-0.03em",
                  }}
                >
                  <CountUp target={s.n} suffix={s.suffix} duration={1200} delay={i * 150} />
                </div>
                <div className="text-xs font-semibold" style={{ color: "var(--text)" }}>{s.label}</div>
                <div className="text-[10px] mt-0.5" style={{ color: "var(--dimmer)" }}>{s.sub}</div>
              </SpotlightCard>
            </ScrollReveal>
          ))}
        </div>

        {/* Capability matrix with glow border */}
        <ScrollReveal delay={200}>
          <GlowBorder borderRadius="12px" glowOpacity={0.2} hoverOpacity={0.4}>
            <div
              ref={tableRef}
              className="rounded-xl overflow-hidden"
              style={{ background: "var(--surface)" }}
            >
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr style={{ borderBottom: "1px solid var(--border)", background: "var(--surface-2)" }}>
                      <th className="text-left px-5 py-3 font-medium text-xs uppercase tracking-wider" style={{ color: "var(--dimmer)", minWidth: "220px" }}>
                        Capability
                      </th>
                      <th className="text-center px-4 py-3 font-semibold text-xs uppercase tracking-wider" style={{ color: "var(--indigo)", minWidth: "90px" }}>
                        LangSight
                      </th>
                      <th className="text-center px-4 py-3 font-medium text-xs uppercase tracking-wider" style={{ color: "var(--dimmer)", minWidth: "90px" }}>
                        LangSmith
                      </th>
                      <th className="text-center px-4 py-3 font-medium text-xs uppercase tracking-wider" style={{ color: "var(--dimmer)", minWidth: "90px" }}>
                        Langfuse
                      </th>
                      <th className="text-center px-4 py-3 font-medium text-xs uppercase tracking-wider" style={{ color: "var(--dimmer)", minWidth: "90px" }}>
                        Opik
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {ROWS.map((row, i) => {
                      const cat = CAT_LABELS[row.category];
                      const isPrevention = row.category === "prevent";
                      return (
                        <tr
                          key={i}
                          data-row
                          style={{
                            opacity: 0,
                            borderBottom: i < ROWS.length - 1 ? "1px solid var(--border-dim)" : "none",
                            background: isPrevention ? "var(--indigo-dim)" : "transparent",
                          }}
                        >
                          <td className="px-5 py-3 flex items-center gap-2">
                            <span
                              className="text-[9px] font-bold uppercase tracking-wider rounded px-1.5 py-0.5 shrink-0"
                              style={{ color: cat.color, background: `${cat.color}15`, border: `1px solid ${cat.color}25` }}
                            >
                              {cat.label}
                            </span>
                            <span style={{ color: isPrevention ? "var(--text)" : "var(--muted)", fontWeight: isPrevention ? 600 : 400 }}>
                              {row.capability}
                            </span>
                          </td>
                          {(["langsight", "langsmith", "langfuse", "opik"] as const).map((platform) => {
                            const cell = CELL[row[platform]];
                            return (
                              <td key={platform} className="px-4 py-3 text-center">
                                <span
                                  className="text-xs font-medium rounded-full px-2 py-0.5"
                                  style={{ color: cell.color, background: cell.bg }}
                                >
                                  {cell.label}
                                </span>
                              </td>
                            );
                          })}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </GlowBorder>
        </ScrollReveal>

        {/* Key insight callout */}
        <ScrollReveal delay={300}>
          <SpotlightCard
            className="mt-8 rounded-xl p-6 max-w-3xl mx-auto"
            style={{
              background: "var(--indigo-dim)",
              border: "1px solid var(--indigo-strong)",
            }}
            spotlightColor="rgba(99,102,241,0.12)"
          >
            <p className="text-sm" style={{ color: "var(--text)" }}>
              <strong>The bottom 3 rows are shared territory</strong> — every platform traces and tracks costs.
              The <strong>top 8 rows are empty for everyone except LangSight.</strong> That's the moat:
              runtime prevention at the tool layer.
            </p>
            <p className="text-xs mt-3" style={{ color: "var(--dimmer)" }}>
              As of April 2026, LangSight also captures 66x more spans than LangSmith in head-to-head
              benchmarks on Claude Agent SDK — but that's observability. The real difference is prevention.
            </p>
          </SpotlightCard>
        </ScrollReveal>
      </div>
    </section>
  );
}
