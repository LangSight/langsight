"use client";

/**
 * HeroSection — "Obsidian" redesign.
 * R3F particle constellation + decrypted headline + glassmorphism terminal.
 */

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import DecryptedText from "./decrypted-text";
import StaggeredReveal from "./staggered-reveal";

const ParticleField = dynamic(() => import("./particle-field"), {
  ssr: false,
  loading: () => null,
});

/* ── Terminal data ──────────────────────────────────────── */
const TERMINAL_LINES: { text: string; color?: string; bold?: boolean; small?: boolean; delay: number }[] = [
  { text: "$ langsight sessions --id sess-f2a9b1", color: "var(--dimmer)", delay: 0 },
  { text: "", delay: 200 },
  { text: "Trace: sess-f2a9b1  (support-agent)", bold: true, delay: 380 },
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

/* ── Glassmorphism Terminal ─────────────────────────────── */
function AnimatedTerminal() {
  const [visible, setVisible] = useState(TERMINAL_LINES.length);
  const [isDark, setIsDark] = useState(true);

  useEffect(() => {
    setVisible(0);
    const timers = TERMINAL_LINES.map((_, i) =>
      setTimeout(() => setVisible(i + 1), TERMINAL_LINES[i].delay + 1200)
    );
    return () => timers.forEach(clearTimeout);
  }, []);

  // Track theme for glass style
  useEffect(() => {
    const check = () => setIsDark(document.documentElement.classList.contains("dark"));
    check();
    const obs = new MutationObserver(check);
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => obs.disconnect();
  }, []);

  return (
    <div className="relative w-full rounded-xl group">
      {/* Animated gradient border */}
      <div
        className="absolute -inset-[1px] rounded-xl"
        style={{
          background: "linear-gradient(135deg, #6366F1, #A78BFA, #4F46E5, #7C3AED)",
          backgroundSize: "300% 300%",
          animation: "gradientShift 6s ease infinite",
          opacity: isDark ? 0.5 : 0.3,
        }}
      />
      {/* Glass inner */}
      <div
        className="relative rounded-xl overflow-hidden"
        style={{
          background: isDark ? "rgba(8,8,11,0.88)" : "rgba(255,255,255,0.82)",
          backdropFilter: "blur(24px)",
          WebkitBackdropFilter: "blur(24px)",
          boxShadow: isDark
            ? "0 30px 60px -12px rgba(0,0,0,0.7), 0 0 80px rgba(99,102,241,0.08), inset 0 1px 0 rgba(255,255,255,0.04)"
            : "0 30px 60px -12px rgba(0,0,0,0.08), 0 0 40px rgba(99,102,241,0.06), inset 0 1px 0 rgba(255,255,255,0.6)",
        }}
      >
        {/* Window bar */}
        <div
          className="flex items-center gap-2 px-4 py-3"
          style={{ borderBottom: "1px solid rgba(255,255,255,0.06)" }}
        >
          <div className="w-3 h-3 rounded-full" style={{ background: "#EF4444" }} />
          <div className="w-3 h-3 rounded-full" style={{ background: "#EAB308" }} />
          <div className="w-3 h-3 rounded-full" style={{ background: "#22C55E" }} />
          <span
            className="ml-3 text-xs"
            style={{ fontFamily: "var(--font-geist-mono)", color: "var(--dimmer)" }}
          >
            langsight · session trace
          </span>
        </div>

        {/* Terminal content */}
        <div
          className="p-5 space-y-0.5 min-h-[280px] overflow-hidden"
          style={{ fontFamily: "var(--font-geist-mono)", fontSize: "0.8rem" }}
        >
          {TERMINAL_LINES.slice(0, visible).map((line, i) => (
            <div
              key={i}
              style={{
                color: line.color ?? "var(--text)",
                fontWeight: line.bold ? 700 : 400,
                fontSize: line.small ? "0.72rem" : undefined,
                lineHeight: 1.7,
                opacity: 0,
                transform: "translateX(-4px)",
                animation: "termReveal 0.25s ease-out forwards",
                animationDelay: `${i * 20}ms`,
              }}
            >
              {line.text || "\u00A0"}
            </div>
          ))}
          {visible < TERMINAL_LINES.length && (
            <span
              className="inline-block w-2 h-4 align-middle"
              style={{ background: "var(--indigo)", animation: "blink 1s step-end infinite" }}
            />
          )}
        </div>
      </div>
    </div>
  );
}

/* ── GitHub icon ────────────────────────────────────────── */
function GithubIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
    </svg>
  );
}

/* ── Persona scenario line ──────────────────────────────── */
function PersonaLine({ emoji, text }: { emoji: string; text: string }) {
  return (
    <div
      className="flex items-center gap-2.5 text-sm rounded-lg px-3 py-2 transition-colors"
      style={{
        background: "var(--surface)",
        border: "1px solid var(--border)",
      }}
    >
      <span className="text-base shrink-0">{emoji}</span>
      <span style={{ color: "var(--muted)" }}>{text}</span>
    </div>
  );
}

/* ── Hero Section ───────────────────────────────────────── */
export default function HeroSection() {
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    const check = () => setIsMobile(window.innerWidth < 768);
    check();
    window.addEventListener("resize", check);
    return () => window.removeEventListener("resize", check);
  }, []);

  return (
    <section className="relative min-h-screen flex items-center overflow-hidden pt-16">
      {/* 3D Background — desktop only */}
      {!isMobile && (
        <div className="absolute inset-0 -z-10" aria-hidden="true">
          <ParticleField />
        </div>
      )}

      {/* Radial gradient mesh — adapts to theme */}
      <div className="absolute inset-0 -z-20 pointer-events-none" aria-hidden="true">
        <div
          className="absolute rounded-full dark:opacity-100 opacity-40"
          style={{
            top: "15%",
            left: "25%",
            width: "600px",
            height: "600px",
            background: "radial-gradient(circle, rgba(99,102,241,0.15) 0%, transparent 70%)",
            filter: "blur(80px)",
          }}
        />
        <div
          className="absolute rounded-full dark:opacity-100 opacity-30"
          style={{
            bottom: "20%",
            right: "15%",
            width: "450px",
            height: "450px",
            background: "radial-gradient(circle, rgba(167,139,250,0.1) 0%, transparent 70%)",
            filter: "blur(100px)",
          }}
        />
        <div
          className="absolute rounded-full dark:opacity-100 opacity-25"
          style={{
            top: "50%",
            left: "60%",
            width: "300px",
            height: "300px",
            background: "radial-gradient(circle, rgba(99,102,241,0.08) 0%, transparent 70%)",
            filter: "blur(60px)",
          }}
        />
      </div>

      {/* Content */}
      <div className="relative max-w-6xl mx-auto px-6 py-28 w-full">
        <div className="grid lg:grid-cols-2 gap-12 xl:gap-20 items-center">
          {/* Left: Copy */}
          <StaggeredReveal delay={200} staggerDelay={100} distance={24}>
            {/* Badge */}
            <div data-stagger-item>
              <div
                className="inline-flex items-center gap-2 rounded-full px-4 py-1.5 text-xs font-medium"
                style={{
                  background: "var(--indigo-dim)",
                  border: "1px solid var(--indigo-strong)",
                  color: "var(--indigo)",
                }}
              >
                <span
                  className="w-1.5 h-1.5 rounded-full"
                  style={{
                    background: "var(--indigo)",
                    boxShadow: "0 0 6px var(--indigo-glow)",
                    animation: "pulse 2s ease infinite",
                  }}
                />
                v0.14.18 · Self-host free · Apache 2.0
              </div>
            </div>

            {/* Headline */}
            <div data-stagger-item className="mt-7">
              <h1
                className="font-bold leading-[1.04]"
                style={{
                  fontSize: "clamp(2.8rem, 6vw, 4.5rem)",
                  fontFamily: "var(--font-geist-sans)",
                  letterSpacing: "-0.03em",
                }}
              >
                <DecryptedText
                  text="See everything your"
                  speed={35}
                  delay={600}
                  className="gradient-text"
                />
                <br />
                <DecryptedText
                  text="agents do."
                  speed={35}
                  delay={900}
                  className="gradient-text"
                />
                <br />
                <span
                  className="gradient-indigo"
                  style={{ textShadow: "0 0 60px rgba(99,102,241,0.35)" }}
                >
                  <DecryptedText
                    text="Stop what they shouldn't."
                    speed={30}
                    delay={1200}
                  />
                </span>
              </h1>
            </div>

            {/* Subheading */}
            <p
              data-stagger-item
              className="text-lg leading-relaxed max-w-lg mt-6"
              style={{ color: "var(--muted)" }}
            >
              The runtime reliability layer for AI agents. Prevent loops, enforce budgets,
              circuit-break failing tools, monitor MCP health. Instrument once — protection is automatic.
            </p>

            {/* Persona examples */}
            <div data-stagger-item className="mt-5 space-y-2">
              <PersonaLine
                emoji="🔄"
                text="Agent stuck in a loop? Killed after 3 repeat calls."
              />
              <PersonaLine
                emoji="💸"
                text="Session burning budget? Auto-stopped at your dollar limit."
              />
              <PersonaLine
                emoji="💥"
                text="MCP server went down? Circuit breaker opens, agents reroute."
              />
              <PersonaLine
                emoji="🔍"
                text="Schema drifted overnight? Detected before your agents fail."
              />
            </div>

            {/* CTAs */}
            <div data-stagger-item className="flex flex-wrap gap-3 mt-6">
              <a
                href="https://docs.langsight.dev/quickstart"
                className="text-sm font-semibold px-6 py-2.5 rounded-lg flex items-center gap-2 transition-all hover:opacity-90 hover:-translate-y-px"
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
                className="text-sm font-semibold px-6 py-2.5 rounded-lg flex items-center gap-2 transition-all hover:-translate-y-px"
                style={{
                  background: "var(--surface)",
                  border: "1px solid var(--border)",
                  color: "var(--text)",
                }}
              >
                <GithubIcon className="w-4 h-4" /> Star on GitHub
              </a>
            </div>

            {/* Install pill */}
            <div
              data-stagger-item
              className="inline-flex items-center gap-3 rounded-xl px-4 py-2.5 mt-6"
              style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
            >
              <span style={{ color: "var(--dimmer)", fontFamily: "var(--font-geist-mono)", fontSize: "0.8rem" }}>
                $
              </span>
              <span style={{ fontFamily: "var(--font-geist-mono)", fontSize: "0.8rem", color: "var(--code-text)" }}>
                pip install langsight
              </span>
              <span style={{ color: "var(--dimmer)", fontFamily: "var(--font-geist-mono)", fontSize: "0.8rem" }}>
                &&
              </span>
              <span style={{ fontFamily: "var(--font-geist-mono)", fontSize: "0.8rem", color: "var(--code-text)" }}>
                langsight init
              </span>
            </div>

            {/* Proof line */}
            <div
              data-stagger-item
              className="flex flex-wrap gap-x-5 gap-y-1 text-xs mt-5"
              style={{ color: "var(--dimmer)" }}
            >
              <span>Anthropic · CrewAI · Claude Agent SDK</span>
              <span>Postgres + ClickHouse</span>
            </div>
          </StaggeredReveal>

          {/* Right: Terminal */}
          <div
            className="lg:mt-0 mt-8"
            style={{ opacity: 0, animation: "heroFadeIn 0.8s ease-out 0.5s forwards" }}
          >
            <AnimatedTerminal />
          </div>
        </div>
      </div>

      {/* Scoped keyframes */}
      <style jsx global>{`
        @keyframes gradientShift {
          0%, 100% { background-position: 0% 50%; }
          50% { background-position: 100% 50%; }
        }
        @keyframes termReveal {
          from { opacity: 0; transform: translateX(-4px); }
          to { opacity: 1; transform: translateX(0); }
        }
        @keyframes heroFadeIn {
          from { opacity: 0; transform: translateY(20px); }
          to { opacity: 1; transform: translateY(0); }
        }
        @keyframes blink {
          50% { opacity: 0; }
        }
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
      `}</style>
    </section>
  );
}
