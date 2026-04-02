"use client";

import { useEffect, useState } from "react";
// Shared shell — canonical source; local defs below kept until full migration
import { Nav as _Nav, Footer as _Footer, Logo as _Logo, useTheme as _useTheme, useScrollReveal as _useScrollReveal } from "@/components/site-shell"; void _Nav; void _Footer; void _Logo; void _useTheme; void _useScrollReveal;

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

/* ── Logo ───────────────────────────────────────────────────── */
function Logo() {
  return (
    <a href="/" className="flex items-center gap-2.5 shrink-0">
      <div
        className="w-7 h-7 rounded-lg flex items-center justify-center"
        style={{ background: "var(--indigo)" }}
      >
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
          <path
            d="M2 7h10M7 2v10M4 4l6 6M10 4l-6 6"
            stroke="white"
            strokeWidth="1.6"
            strokeLinecap="round"
          />
        </svg>
      </div>
      <span
        className="font-bold text-lg tracking-tight"
        style={{ fontFamily: "var(--font-geist-sans)", color: "var(--text)" }}
      >
        LangSight
      </span>
    </a>
  );
}

/* ── Nav ────────────────────────────────────────────────────── */
function Nav({ dark, toggle }: { dark: boolean; toggle: () => void }) {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const h = () => setScrolled(window.scrollY > 24);
    window.addEventListener("scroll", h);
    return () => window.removeEventListener("scroll", h);
  }, []);
  return (
    <nav
      className="fixed top-0 left-0 right-0 z-50 transition-all duration-300"
      style={{
        background: scrolled
          ? "color-mix(in srgb, var(--bg) 88%, transparent)"
          : "transparent",
        backdropFilter: scrolled ? "blur(16px)" : "none",
        borderBottom: scrolled
          ? "1px solid var(--border)"
          : "1px solid transparent",
      }}
    >
      <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between gap-6">
        <Logo />
        <div className="hidden md:flex items-center gap-1">
          {[
            { label: "Home", href: "/" },
            { label: "Security", href: "/security" },
            { label: "Pricing", href: "/pricing" },
            { label: "Docs", href: "https://docs.langsight.dev" },
            { label: "GitHub", href: "https://github.com/LangSight/langsight" },
          ].map((l) => (
            <a
              key={l.label}
              href={l.href}
              className="px-3 py-1.5 rounded-md text-sm transition-colors"
              style={{ color: "var(--muted)" }}
              onMouseEnter={(e) =>
                (e.currentTarget.style.color = "var(--text)")
              }
              onMouseLeave={(e) =>
                (e.currentTarget.style.color = "var(--muted)")
              }
            >
              {l.label}
            </a>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={toggle}
            aria-label="Toggle theme"
            className="w-9 h-9 rounded-lg flex items-center justify-center"
            style={{
              background: "var(--surface-2)",
              border: "1px solid var(--border)",
              color: "var(--muted)",
            }}
          >
            {dark ? (
              <svg
                className="w-4 h-4"
                fill="none"
                stroke="currentColor"
                strokeWidth={2}
                viewBox="0 0 24 24"
              >
                <circle cx="12" cy="12" r="5" />
                <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" />
              </svg>
            ) : (
              <svg
                className="w-4 h-4"
                fill="none"
                stroke="currentColor"
                strokeWidth={2}
                viewBox="0 0 24 24"
              >
                <path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z" />
              </svg>
            )}
          </button>
          <a
            href="https://docs.langsight.dev/quickstart"
            className="hidden sm:flex items-center gap-1.5 text-sm font-semibold px-4 py-2 rounded-lg transition-all hover:opacity-90 hover:-translate-y-px"
            style={{ background: "var(--indigo)", color: "white" }}
          >
            Get started →
          </a>
        </div>
      </div>
    </nav>
  );
}

/* ── Comparison data ─────────────────────────────────────────── */
type CheckValue = "yes" | "no" | "partial" | string;

interface ComparisonRow {
  feature: string;
  langsight: CheckValue;
  langfuse: CheckValue;
  langwatch: CheckValue;
  note?: string;
}

const COMPARISON_ROWS: ComparisonRow[] = [
  {
    feature: "MCP server health monitoring",
    langsight: "yes",
    langfuse: "no",
    langwatch: "no",
    note: "LangSight is the only platform with native MCP health checks.",
  },
  {
    feature: "MCP security scanning (CVE + OWASP)",
    langsight: "yes",
    langfuse: "no",
    langwatch: "no",
    note: "CVE detection and 5 of 10 OWASP MCP checks, built-in.",
  },
  {
    feature: "Tool poisoning detection",
    langsight: "yes",
    langfuse: "no",
    langwatch: "no",
    note: "Injection, unicode, and base64-encoded payload detection.",
  },
  {
    feature: "Schema drift detection",
    langsight: "yes",
    langfuse: "no",
    langwatch: "no",
    note:
      "Alerts when a tool's schema changes unexpectedly between scans.",
  },
  {
    feature: "Agent tool call tracing",
    langsight: "yes",
    langfuse: "yes",
    langwatch: "yes",
  },
  {
    feature: "LLM input / output capture",
    langsight: "yes",
    langfuse: "yes",
    langwatch: "yes",
  },
  {
    feature: "Multi-agent call tree",
    langsight: "yes",
    langfuse: "partial",
    langwatch: "partial",
  },
  {
    feature: "Cost attribution per tool call",
    langsight: "yes",
    langfuse: "yes",
    langwatch: "partial",
  },
  {
    feature: "Anomaly detection",
    langsight: "yes",
    langfuse: "no",
    langwatch: "partial",
  },
  {
    feature: "SLO tracking",
    langsight: "yes",
    langfuse: "no",
    langwatch: "partial",
  },
  {
    feature: "CI/CD security gate (--ci flag)",
    langsight: "yes",
    langfuse: "no",
    langwatch: "no",
  },
  {
    feature: "Self-hosted (free forever)",
    langsight: "yes",
    langfuse: "yes",
    langwatch: "yes",
  },
  {
    feature: "Data leaves your network",
    langsight: "Never",
    langfuse: "Optional",
    langwatch: "Optional",
  },
  {
    feature: "License",
    langsight: "Apache 2.0",
    langfuse: "MIT / ELv2",
    langwatch: "Apache 2.0",
  },
  {
    feature: "Primary focus",
    langsight: "Agent runtime reliability",
    langfuse: "LLM evals + tracing",
    langwatch: "LLM quality + guardrails",
  },
];

function CellValue({ value }: { value: CheckValue }) {
  if (value === "yes") {
    return <span style={{ color: "var(--green)", fontWeight: 600 }}>Yes</span>;
  }
  if (value === "no") {
    return <span style={{ color: "var(--dimmer)" }}>—</span>;
  }
  if (value === "partial") {
    return <span style={{ color: "var(--yellow)" }}>Partial</span>;
  }
  return <span style={{ color: "var(--muted)", fontSize: "0.8rem" }}>{value}</span>;
}

/* ── Page ───────────────────────────────────────────────────── */
export default function AlternativesPage() {
  const { dark, toggle } = useTheme();
  useScrollReveal();

  return (
    <>
      <Nav dark={dark} toggle={toggle} />
      <main>

        {/* Hero */}
        <section className="relative pt-32 pb-20 grid-bg overflow-hidden">
          <div className="absolute inset-0 pointer-events-none">
            <div
              className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[400px] rounded-full blur-[150px]"
              style={{ background: "var(--indigo-glow)" }}
            />
          </div>
          <div className="relative max-w-4xl mx-auto px-6 text-center">
            <div
              className="fade-up inline-flex items-center gap-2 rounded-full px-4 py-1.5 text-xs font-medium mb-6"
              style={{
                background: "var(--indigo-dim)",
                border: "1px solid var(--indigo-strong)",
                color: "var(--indigo)",
              }}
            >
              LangSight vs Langfuse vs LangWatch
            </div>

            <h1
              className="fade-up delay-1 font-bold tracking-tight mb-6"
              style={{
                fontSize: "clamp(2rem, 4.5vw, 3.2rem)",
                fontFamily: "var(--font-geist-sans)",
              }}
            >
              <span className="gradient-text">Not another LLM eval platform.</span>
              <br />
              <span className="gradient-indigo">Agent runtime reliability, built for MCP.</span>
            </h1>

            <p
              className="fade-up delay-2 text-lg leading-relaxed max-w-2xl mx-auto mb-10"
              style={{ color: "var(--muted)" }}
            >
              Langfuse and LangWatch are excellent tools for LLM evaluation and prompt quality.
              LangSight solves a different problem: monitoring and securing the{" "}
              <strong style={{ color: "var(--text)" }}>tools your agents call at runtime</strong> —
              the MCP servers, HTTP APIs, and functions that break silently without anyone noticing.
            </p>

            <div className="fade-up delay-3 flex flex-wrap justify-center gap-3">
              <a
                href="https://docs.langsight.dev/quickstart"
                className="text-sm font-semibold px-5 py-2.5 rounded-lg transition-all hover:opacity-90 hover:-translate-y-px"
                style={{ background: "var(--indigo)", color: "white" }}
              >
                Try LangSight free →
              </a>
              <a
                href="https://github.com/LangSight/langsight"
                className="text-sm font-semibold px-5 py-2.5 rounded-lg flex items-center gap-2 transition-all hover:-translate-y-px"
                style={{
                  background: "var(--surface)",
                  border: "1px solid var(--border)",
                  color: "var(--text)",
                }}
              >
                <GithubIcon className="w-4 h-4" /> View on GitHub
              </a>
            </div>
          </div>
        </section>

        {/* Positioning summary cards */}
        <section className="py-16" style={{ background: "var(--bg-deep)" }}>
          <div className="max-w-5xl mx-auto px-6">
            <div className="grid md:grid-cols-3 gap-5">
              {[
                {
                  name: "LangSight",
                  badge: "MCP-native",
                  badgeColor: "var(--indigo)",
                  badgeBg: "var(--indigo-dim)",
                  desc: "Agent runtime reliability for AI toolchains. Purpose-built for MCP health monitoring, security scanning, circuit breakers, guardrails, and tool call tracing.",
                  highlight: true,
                },
                {
                  name: "Langfuse",
                  badge: "LLM eval & tracing",
                  badgeColor: "var(--muted)",
                  badgeBg: "var(--surface-2)",
                  desc: "Strong platform for LLM prompt engineering, evals, and cost tracking. Not designed for MCP server health or security — complementary to LangSight.",
                  highlight: false,
                },
                {
                  name: "LangWatch",
                  badge: "Quality & guardrails",
                  badgeColor: "var(--muted)",
                  badgeBg: "var(--surface-2)",
                  desc: "Focuses on LLM output quality, guardrails, and safety evaluations. Does not cover MCP infrastructure health, CVE scanning, or tool-level security.",
                  highlight: false,
                },
              ].map((card) => (
                <div
                  key={card.name}
                  data-reveal
                  className="card-flat p-6"
                  style={
                    card.highlight
                      ? { borderColor: "var(--indigo)", boxShadow: "0 0 0 1px var(--indigo)" }
                      : {}
                  }
                >
                  <div className="flex items-center justify-between mb-3">
                    <h2
                      className="font-bold text-lg"
                      style={{
                        color: card.highlight ? "var(--text)" : "var(--muted)",
                        fontFamily: "var(--font-geist-sans)",
                      }}
                    >
                      {card.name}
                    </h2>
                    <span
                      className="text-xs px-2 py-0.5 rounded-full font-medium"
                      style={{
                        color: card.badgeColor,
                        background: card.badgeBg,
                        border: `1px solid ${card.badgeBg}`,
                      }}
                    >
                      {card.badge}
                    </span>
                  </div>
                  <p className="text-sm leading-relaxed" style={{ color: "var(--muted)" }}>
                    {card.desc}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Comparison table */}
        <section className="py-24">
          <div className="max-w-5xl mx-auto px-6">
            <div className="text-center mb-12" data-reveal>
              <p className="section-label mb-3">Feature comparison</p>
              <h2
                className="font-bold tracking-tight"
                style={{
                  fontSize: "clamp(1.5rem, 3vw, 2rem)",
                  fontFamily: "var(--font-geist-sans)",
                }}
              >
                <span className="gradient-text">What each platform covers</span>
              </h2>
              <p className="mt-3 text-sm max-w-lg mx-auto" style={{ color: "var(--muted)" }}>
                Green rows are unique to LangSight — capabilities no other platform offers today.
              </p>
            </div>

            <div data-reveal className="card-flat overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr
                      style={{
                        borderBottom: "1px solid var(--border)",
                        background: "var(--surface-2)",
                      }}
                    >
                      <th
                        className="text-left px-6 py-3 font-medium"
                        style={{ color: "var(--muted)" }}
                      >
                        Feature
                      </th>
                      <th
                        className="px-5 py-3 text-center font-bold"
                        style={{ color: "var(--indigo)" }}
                      >
                        LangSight
                      </th>
                      <th
                        className="px-5 py-3 text-center font-medium"
                        style={{ color: "var(--muted)" }}
                      >
                        Langfuse
                      </th>
                      <th
                        className="px-5 py-3 text-center font-medium"
                        style={{ color: "var(--muted)" }}
                      >
                        LangWatch
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {COMPARISON_ROWS.map((row, i) => {
                      const isUnique =
                        row.langsight === "yes" &&
                        row.langfuse === "no" &&
                        row.langwatch === "no";
                      return (
                        <tr
                          key={i}
                          style={{
                            borderBottom:
                              i < COMPARISON_ROWS.length - 1
                                ? "1px solid var(--border-dim)"
                                : "none",
                            background: isUnique
                              ? "color-mix(in srgb, var(--indigo-dim) 60%, transparent)"
                              : "transparent",
                          }}
                        >
                          <td className="px-6 py-3" style={{ color: "var(--text)" }}>
                            <span>{row.feature}</span>
                            {row.note && (
                              <span
                                className="block text-xs mt-0.5"
                                style={{ color: "var(--dimmer)" }}
                              >
                                {row.note}
                              </span>
                            )}
                          </td>
                          <td className="px-5 py-3 text-center">
                            <CellValue value={row.langsight} />
                          </td>
                          <td className="px-5 py-3 text-center">
                            <CellValue value={row.langfuse} />
                          </td>
                          <td className="px-5 py-3 text-center">
                            <CellValue value={row.langwatch} />
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>

            <p
              className="mt-4 text-xs text-center"
              style={{ color: "var(--dimmer)" }}
            >
              Comparison based on publicly available documentation as of March 2026. Features may
              change — check each project's docs for the latest.
            </p>
          </div>
        </section>

        {/* Use together callout */}
        <section className="py-16" style={{ background: "var(--bg-deep)" }}>
          <div className="max-w-3xl mx-auto px-6 text-center" data-reveal>
            <h2
              className="font-bold tracking-tight mb-4"
              style={{
                fontSize: "clamp(1.3rem, 2.5vw, 1.8rem)",
                fontFamily: "var(--font-geist-sans)",
              }}
            >
              <span className="gradient-indigo">LangSight + Langfuse work great together.</span>
            </h2>
            <p
              className="text-base leading-relaxed mb-8"
              style={{ color: "var(--muted)" }}
            >
              Use Langfuse for prompt evaluation and LLM quality. Use LangSight for the runtime
              layer — MCP health, security, and tool call tracing. They solve different problems at
              different layers of the stack. No overlap, no conflict.
            </p>
            <div className="flex flex-wrap justify-center gap-3">
              <a
                href="https://docs.langsight.dev/quickstart"
                className="text-sm font-semibold px-5 py-2.5 rounded-lg transition-all hover:opacity-90 hover:-translate-y-px"
                style={{ background: "var(--indigo)", color: "white" }}
              >
                Get started with LangSight →
              </a>
              <a
                href="/security"
                className="text-sm font-semibold px-5 py-2.5 rounded-lg transition-all hover:-translate-y-px"
                style={{
                  background: "var(--surface)",
                  border: "1px solid var(--border)",
                  color: "var(--text)",
                }}
              >
                See security scanning →
              </a>
            </div>
          </div>
        </section>

      </main>

      {/* Footer */}
      <footer className="py-10" style={{ borderTop: "1px solid var(--border)" }}>
        <div className="max-w-6xl mx-auto px-6 flex flex-col sm:flex-row items-center justify-between gap-4">
          <Logo />
          <div className="flex flex-wrap justify-center gap-x-6 gap-y-2 text-sm">
            {[
              ["Home", "/"],
              ["Security", "/security"],
              ["Pricing", "/pricing"],
              ["Alternatives", "/alternatives"],
              ["Docs", "https://docs.langsight.dev"],
              ["GitHub", "https://github.com/LangSight/langsight"],
            ].map(([l, h]) => (
              <a
                key={l}
                href={h}
                className="transition-colors"
                style={{ color: "var(--muted)" }}
                onMouseEnter={(e) => (e.currentTarget.style.color = "var(--text)")}
                onMouseLeave={(e) => (e.currentTarget.style.color = "var(--muted)")}
              >
                {l}
              </a>
            ))}
          </div>
          <p className="text-xs" style={{ color: "var(--dimmer)" }}>
            Apache 2.0 · v0.14.0
          </p>
        </div>
      </footer>
    </>
  );
}
