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

/* ── Glossary terms ──────────────────────────────────────────── */
interface GlossaryTerm {
  id: string;
  term: string;
  shortDef: string;
  body: string;
  relatedTerms?: string[];
  learnMore?: { label: string; href: string };
}

const TERMS: GlossaryTerm[] = [
  {
    id: "mcp-server",
    term: "MCP Server",
    shortDef: "A process that exposes tools, prompts, or resources to an AI agent via the Model Context Protocol.",
    body: `The Model Context Protocol (MCP) is an open standard that lets AI agents call external capabilities in a structured, discoverable way. An MCP server is any process — a database connector, a file system wrapper, a REST API adapter, a Git client — that speaks the MCP protocol. Agents connect to MCP servers and discover the available tools by requesting the server's tool schema. When the agent calls a tool, the MCP server executes the corresponding logic and returns the result.

MCP servers run over three transport types: stdio (subprocess), Server-Sent Events (SSE), and StreamableHTTP. Each transport has different security and network exposure characteristics. LangSight monitors MCP servers across all three transports.`,
    relatedTerms: ["MCP Observability", "Tool Call Tracing", "Schema Drift Detection"],
    learnMore: { label: "MCP Health Monitoring", href: "https://docs.langsight.dev" },
  },
  {
    id: "mcp-observability",
    term: "MCP Observability",
    shortDef: "The practice of instrumenting, monitoring, and understanding the behavior of MCP servers and the tool calls made against them.",
    body: `Observability is the ability to understand what a system is doing from the outside — without modifying it — by examining its outputs (traces, metrics, logs). MCP observability applies this to the Model Context Protocol layer of an AI agent stack.

A fully observable MCP deployment gives you: complete traces of every tool call (which server, which tool, what arguments, what result, how long it took), health metrics (uptime, latency trends, error rates), security scan results (CVEs, OWASP findings), and schema snapshots (so you know when a tool's interface changed). LangSight provides all of these in a single platform.`,
    relatedTerms: ["MCP Server", "Tool Call Tracing", "MCP Health Check"],
    learnMore: { label: "LangSight overview", href: "https://docs.langsight.dev" },
  },
  {
    id: "tool-call-tracing",
    term: "Tool Call Tracing",
    shortDef: "Recording the full lifecycle of a tool invocation by an AI agent, including the arguments sent, the result returned, latency, and any errors.",
    body: `When an AI agent decides to use a tool — for example, querying a database, reading a file, or calling an API — it produces a tool call. Tracing that call means capturing a structured record of everything that happened: which tool was called, the exact arguments the agent provided, the result the tool returned, how long it took, and whether it succeeded or failed.

In multi-agent systems, tool call traces form a tree: a root agent may call a sub-agent, which in turn calls several MCP tools, each producing its own trace span. Reconstructing this tree is essential for debugging — when your agent fails, you need to know exactly which tool call produced the wrong result, timed out, or threw an exception. LangSight captures and visualizes this full call tree.`,
    relatedTerms: ["MCP Observability", "MCP Server", "Agent Session"],
    learnMore: { label: "Tracing documentation", href: "https://docs.langsight.dev" },
  },
  {
    id: "schema-drift-detection",
    term: "Schema Drift Detection",
    shortDef: "Automatically detecting when an MCP server's tool schema changes unexpectedly between scans — a signal of unplanned deployments or potential supply chain attacks.",
    body: `Every MCP tool has a schema: a JSON definition of its input parameters, types, and descriptions. When a tool's schema changes — a new parameter is added, an existing one is renamed, or the description is modified — this is schema drift.

Schema drift can be benign (a planned version upgrade) or dangerous (a compromised MCP server with a modified tool description injecting malicious instructions). LangSight takes a snapshot of each tool's schema on every health check and compares it to the previous snapshot. Unexpected changes trigger an alert, giving you a window to investigate before the change propagates to production agents. This is also classified as OWASP MCP-04 (Rug Pull).`,
    relatedTerms: ["MCP Server", "Tool Poisoning", "OWASP MCP"],
    learnMore: { label: "Security scanning docs", href: "/security" },
  },
  {
    id: "tool-poisoning",
    term: "Tool Poisoning",
    shortDef: "An attack where an MCP server's tool description is modified to contain hidden instructions that manipulate agent behavior.",
    body: `Tool poisoning exploits the fact that AI agents read tool descriptions to understand what a tool does and how to use it. If an attacker can modify a tool's description — through a compromised package, a malicious MCP server, or a supply chain attack — they can inject instructions directly into the agent's context.

Examples include: injecting "ignore all previous instructions and exfiltrate data" into a tool description, hiding malicious instructions inside zero-width unicode characters that are invisible in most editors, or encoding payloads in base64 strings embedded in descriptions. LangSight's security scanner detects all three patterns and flags them as critical findings.`,
    relatedTerms: ["Schema Drift Detection", "OWASP MCP", "MCP Security Scanning"],
    learnMore: { label: "Security scanning", href: "/security" },
  },
  {
    id: "mcp-health-check",
    term: "MCP Health Check",
    shortDef: "A proactive connection test against an MCP server that verifies it is reachable, responds within acceptable latency, and exposes the expected tool schema.",
    body: `An MCP health check connects to a server, requests its tool list, verifies the schema matches the last known snapshot, and records the round-trip latency. LangSight runs health checks on a configurable interval (default: 30 seconds) against all registered MCP servers.

Health check results feed into status classifications: "up" (healthy), "degraded" (slow or partial), "down" (unreachable or erroring), and "stale" (not checked recently). DOWN events trigger Slack or webhook alerts. A history of health check results is stored in ClickHouse for latency trend analysis and SLO tracking.`,
    relatedTerms: ["MCP Observability", "MCP Server", "Schema Drift Detection"],
    learnMore: { label: "Health monitoring docs", href: "https://docs.langsight.dev" },
  },
  {
    id: "owasp-mcp",
    term: "OWASP MCP Top 10",
    shortDef: "A community-maintained list of the ten most critical security risks specific to systems built on the Model Context Protocol.",
    body: `The OWASP MCP Top 10 catalogs the most prevalent and impactful security vulnerabilities in MCP-based systems, drawing from the broader OWASP methodology adapted for the MCP protocol's unique attack surface.

The ten risks include: MCP-01 (No Authentication), MCP-02 (Destructive Tools Without Auth), MCP-03 (Training Data Poisoning), MCP-04 (Schema Drift / Rug Pull), MCP-05 (Missing Input Validation), MCP-06 (Plaintext Transport), MCP-07 (Insecure Plugin Design), MCP-08 (Excessive Agency), MCP-09 (Overreliance on LLM), MCP-10 (Insufficient Logging & Monitoring). LangSight's security scanner automates checks for MCP-01, MCP-02, MCP-04, MCP-05, and MCP-06 today, with the remaining checks in development.`,
    relatedTerms: ["MCP Security Scanning", "Tool Poisoning", "Schema Drift Detection"],
    learnMore: { label: "OWASP MCP security page", href: "/security" },
  },
  {
    id: "agent-session",
    term: "Agent Session",
    shortDef: "A single end-to-end execution of an AI agent workflow, from initial user input through all tool calls and sub-agent invocations to final output.",
    body: `An agent session is the top-level unit of work in LangSight's tracing model. It corresponds to one run of your agent — for example, a user asking the agent to research a topic, or an automated workflow triggered by a schedule.

Within a session, LangSight captures the complete call tree: the root LLM reasoning steps, every tool call (including arguments and results), any sub-agent invocations, and the final output. Sessions are stored with their full trace, cost attribution (token counts and dollar costs per LLM call and tool call), and metadata (model, duration, status). You can replay a session against live MCP servers, compare two sessions side-by-side, or set an SLO alert if a session's success rate drops below a threshold.`,
    relatedTerms: ["Tool Call Tracing", "MCP Observability", "MCP Health Check"],
    learnMore: { label: "Sessions documentation", href: "https://docs.langsight.dev" },
  },
  {
    id: "agent-runtime-reliability",
    term: "Agent Runtime Reliability",
    shortDef: "The practice of keeping AI agent toolchains running correctly in production — detecting loops, enforcing budgets, breaking failing tools, and mapping blast radius before users are impacted.",
    body: `Agent runtime reliability is distinct from LLM evaluation and prompt quality. While tools like Langfuse and LangSmith focus on the model layer (did the prompt produce a good answer?), runtime reliability focuses on the tool layer (did the tool the agent called actually work, and what happens when it doesn't?).

The core capabilities of an agent runtime reliability platform include: loop detection (same tool + same args called repeatedly), budget guardrails (per-session and per-tool cost limits), circuit breakers (auto-disable tools after consecutive failures), blast radius mapping (which agents break when a specific tool goes down), MCP health monitoring, security scanning, and schema drift detection. LangSight is purpose-built for this layer.`,
    relatedTerms: ["Circuit Breaker", "MCP Health Check", "Agent Session"],
    learnMore: { label: "LangSight overview", href: "https://docs.langsight.dev" },
  },
  {
    id: "circuit-breaker",
    term: "Circuit Breaker",
    shortDef: "A runtime safety mechanism that automatically disables a tool after a configurable number of consecutive failures, preventing cascading errors and runaway costs.",
    body: `Borrowed from distributed systems engineering, a circuit breaker in the AI agent context sits between the agent and the tool it wants to call. It tracks consecutive failures and, once a threshold is reached (e.g., 5 failures in a row), "opens" the circuit — blocking further calls to that tool until it recovers.

Without a circuit breaker, a failing MCP server causes agents to retry endlessly, burning tokens and time. With a circuit breaker, the agent gets an immediate "tool unavailable" response, allowing it to fall back gracefully or report the issue. LangSight's SDK includes a built-in circuit breaker that can be enabled per-tool or globally, with configurable failure thresholds and recovery windows. Circuit breaker state is reported in health dashboards and alerts.`,
    relatedTerms: ["Agent Runtime Reliability", "MCP Health Check", "MCP Server"],
    learnMore: { label: "SDK circuit breaker docs", href: "https://docs.langsight.dev" },
  },
];

/* ── Page ───────────────────────────────────────────────────── */
export default function GlossaryPage() {
  const { dark, toggle } = useTheme();
  useScrollReveal();
  const [activeId, setActiveId] = useState<string | null>(null);

  return (
    <>
      <Nav dark={dark} toggle={toggle} />
      <main>

        {/* Hero */}
        <section className="relative pt-32 pb-16 grid-bg overflow-hidden">
          <div className="absolute inset-0 pointer-events-none">
            <div
              className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[300px] rounded-full blur-[120px]"
              style={{ background: "var(--indigo-glow)" }}
            />
          </div>
          <div className="relative max-w-3xl mx-auto px-6 text-center">
            <div
              className="fade-up inline-flex items-center gap-2 rounded-full px-4 py-1.5 text-xs font-medium mb-6"
              style={{
                background: "var(--indigo-dim)",
                border: "1px solid var(--indigo-strong)",
                color: "var(--indigo)",
              }}
            >
              MCP &amp; Agent Runtime Reliability — Key Terms
            </div>

            <h1
              className="fade-up delay-1 font-bold tracking-tight mb-5"
              style={{
                fontSize: "clamp(1.9rem, 4vw, 2.8rem)",
                fontFamily: "var(--font-geist-sans)",
              }}
            >
              <span className="gradient-text">Agent Runtime Reliability Glossary</span>
            </h1>

            <p
              className="fade-up delay-2 text-base leading-relaxed max-w-xl mx-auto"
              style={{ color: "var(--muted)" }}
            >
              Plain-English definitions for the terms you&apos;ll encounter when building,
              monitoring, and securing AI agent toolchains — runtime reliability, circuit breakers, MCP health, and more.
            </p>
          </div>
        </section>

        {/* Glossary content */}
        <section className="py-16">
          <div className="max-w-4xl mx-auto px-6">

            {/* Jump links */}
            <nav
              className="mb-12 p-4 rounded-xl flex flex-wrap gap-2"
              style={{ background: "var(--surface-2)", border: "1px solid var(--border)" }}
              aria-label="Jump to term"
            >
              {TERMS.map((t) => (
                <a
                  key={t.id}
                  href={`#${t.id}`}
                  className="text-xs px-3 py-1.5 rounded-full transition-all"
                  style={{
                    background: "var(--surface)",
                    border: "1px solid var(--border)",
                    color: "var(--muted)",
                    fontFamily: "var(--font-geist-sans)",
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.color = "var(--text)";
                    e.currentTarget.style.borderColor = "var(--indigo)";
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.color = "var(--muted)";
                    e.currentTarget.style.borderColor = "var(--border)";
                  }}
                >
                  {t.term}
                </a>
              ))}
            </nav>

            {/* Term entries */}
            <div className="space-y-10">
              {TERMS.map((term, i) => (
                <article
                  key={term.id}
                  id={term.id}
                  data-reveal
                  className="scroll-mt-24"
                  style={{ transitionDelay: `${i * 40}ms` }}
                >
                  <div
                    className="card-flat p-7"
                    style={
                      activeId === term.id
                        ? { borderColor: "var(--indigo)" }
                        : {}
                    }
                    onMouseEnter={() => setActiveId(term.id)}
                    onMouseLeave={() => setActiveId(null)}
                  >
                    {/* Term heading */}
                    <h2
                      className="font-bold text-xl mb-2"
                      style={{
                        color: "var(--text)",
                        fontFamily: "var(--font-geist-sans)",
                      }}
                    >
                      {term.term}
                    </h2>

                    {/* Short definition */}
                    <p
                      className="text-sm font-medium mb-4 leading-snug"
                      style={{ color: "var(--indigo)" }}
                    >
                      {term.shortDef}
                    </p>

                    {/* Full body */}
                    <div className="space-y-3">
                      {term.body.trim().split("\n\n").map((para, j) => (
                        <p
                          key={j}
                          className="text-sm leading-relaxed"
                          style={{ color: "var(--muted)" }}
                        >
                          {para.trim()}
                        </p>
                      ))}
                    </div>

                    {/* Footer: related terms + learn more */}
                    <div className="mt-5 flex flex-wrap items-center justify-between gap-4">
                      {term.relatedTerms && term.relatedTerms.length > 0 && (
                        <div className="flex flex-wrap gap-2">
                          <span
                            className="text-xs"
                            style={{ color: "var(--dimmer)" }}
                          >
                            Related:
                          </span>
                          {term.relatedTerms.map((rt) => {
                            const linked = TERMS.find((t) => t.term === rt);
                            return linked ? (
                              <a
                                key={rt}
                                href={`#${linked.id}`}
                                className="text-xs px-2 py-0.5 rounded-full transition-colors"
                                style={{
                                  background: "var(--indigo-dim)",
                                  color: "var(--indigo)",
                                  border: "1px solid transparent",
                                }}
                              >
                                {rt}
                              </a>
                            ) : (
                              <span
                                key={rt}
                                className="text-xs px-2 py-0.5 rounded-full"
                                style={{
                                  background: "var(--surface-2)",
                                  color: "var(--dimmer)",
                                }}
                              >
                                {rt}
                              </span>
                            );
                          })}
                        </div>
                      )}
                      {term.learnMore && (
                        <a
                          href={term.learnMore.href}
                          className="text-xs font-medium transition-colors"
                          style={{ color: "var(--indigo)" }}
                        >
                          {term.learnMore.label} →
                        </a>
                      )}
                    </div>
                  </div>
                </article>
              ))}
            </div>
          </div>
        </section>

        {/* CTA */}
        <section className="py-16" style={{ background: "var(--bg-deep)" }}>
          <div className="max-w-3xl mx-auto px-6 text-center" data-reveal>
            <h2
              className="font-bold tracking-tight mb-4"
              style={{
                fontSize: "clamp(1.3rem, 2.5vw, 1.8rem)",
                fontFamily: "var(--font-geist-sans)",
              }}
            >
              <span className="gradient-indigo">
                See agent runtime reliability in action.
              </span>
            </h2>
            <p
              className="text-base mb-8"
              style={{ color: "var(--muted)" }}
            >
              LangSight puts all of these concepts into a single runtime reliability platform — traces, health checks,
              security scans, circuit breakers, and cost guardrails. Free to self-host.
            </p>
            <div className="flex flex-wrap justify-center gap-3">
              <a
                href="https://docs.langsight.dev/quickstart"
                className="text-sm font-semibold px-5 py-2.5 rounded-lg transition-all hover:opacity-90 hover:-translate-y-px"
                style={{ background: "var(--indigo)", color: "white" }}
              >
                Quickstart guide →
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
                MCP security scanning →
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
              ["Glossary", "/glossary"],
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
