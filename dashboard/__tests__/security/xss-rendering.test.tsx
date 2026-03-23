/**
 * XSS rendering regression tests.
 *
 * Invariant: user-controlled strings that arrive from the API — session names,
 * agent names, server names, tool names, error messages, and ISO timestamps —
 * must never execute as JavaScript in the browser.  React's JSX escaping is
 * the primary defence; these tests confirm it holds for every surface that
 * renders such strings.
 *
 * All tests run in jsdom with zero real network calls.
 */

import { render } from "@testing-library/react";
import { Timestamp } from "@/components/timestamp";
import { buildSessionGraph } from "@/lib/session-graph";
import { timeAgo, formatExact } from "@/lib/utils";
import {
  XSS_PAYLOADS,
  makeXssTrace,
} from "./test-utils";

// ─── Guard ────────────────────────────────────────────────────────────────────

/**
 * Check that no dangerous HTML tag survived into the container innerHTML.
 * We look for the literal opening of <script, onerror=, onload=, and
 * javascript: because those are the execution vectors we care about.
 */
function assertNoExecutableMarkup(container: HTMLElement): void {
  const html = container.innerHTML;
  expect(html).not.toMatch(/<script/i);
  expect(html).not.toMatch(/onerror\s*=/i);
  expect(html).not.toMatch(/onload\s*=/i);
  expect(html).not.toMatch(/javascript:/i);
}

// ─── Timestamp component ─────────────────────────────────────────────────────

describe("Timestamp — XSS in iso prop", () => {
  /**
   * Invariant: the iso prop is passed through Date() which clamps garbage
   * inputs to "Invalid Date" before any output reaches the DOM.  Executable
   * HTML must never appear.
   */

  it.each(XSS_PAYLOADS)(
    "does not execute payload when iso='%s'",
    (payload) => {
      const { container } = render(<Timestamp iso={payload} />);
      assertNoExecutableMarkup(container);
    },
  );

  it("renders 'Invalid Date' text (not a script) for script-tag iso", () => {
    const { container } = render(
      <Timestamp iso={'<script>window.__xss=1</script>'} />,
    );
    // Window property must not be set — jsdom would execute inline scripts
    expect((window as typeof window & { __xss?: number }).__xss).toBeUndefined();
    assertNoExecutableMarkup(container);
  });

  it("does not set window.__xss when onerror payload is used as iso", () => {
    render(<Timestamp iso={'<img src=x onerror="window.__xss=1">'} />);
    expect((window as typeof window & { __xss?: number }).__xss).toBeUndefined();
  });

  it("renders compact mode without executing payload", () => {
    const { container } = render(
      <Timestamp iso={'<svg onload="window.__xss=1">'} compact />,
    );
    assertNoExecutableMarkup(container);
    expect((window as typeof window & { __xss?: number }).__xss).toBeUndefined();
  });

  it("places a valid ISO string in dateTime attribute for valid input", () => {
    // The component normalizes via new Date().toISOString() — same point in time,
    // may have .000Z suffix.  Hostile input gets dateTime="" (empty, not raw HTML).
    const safeIso = "2026-03-22T10:00:00Z";
    const { container } = render(<Timestamp iso={safeIso} />);
    const el = container.querySelector("time");
    expect(el).not.toBeNull();
    const dt = el?.getAttribute("dateTime") ?? "";
    // Represents the same moment (normalization allowed)
    expect(new Date(dt).getTime()).toBe(new Date(safeIso).getTime());
    // Must be a valid ISO string pattern
    expect(dt).toMatch(/^\d{4}-\d{2}-\d{2}T/);
  });
});

// ─── timeAgo / formatExact — utility functions ───────────────────────────────

describe("timeAgo — XSS payloads produce safe strings", () => {
  /**
   * Invariant: timeAgo() returns a plain text string.  Even when given garbage
   * input it must not return a string containing HTML tags or JavaScript URIs.
   */

  it.each(XSS_PAYLOADS)(
    "returns a plain-text string for payload '%s'",
    (payload) => {
      const result = timeAgo(payload);
      expect(result).not.toMatch(/<script/i);
      expect(result).not.toMatch(/onerror/i);
      expect(result).not.toMatch(/javascript:/i);
      // Must be a string, not throw
      expect(typeof result).toBe("string");
    },
  );

  it("returns NaN-based output for empty string without throwing", () => {
    expect(() => timeAgo("")).not.toThrow();
  });
});

describe("formatExact — XSS payloads produce safe strings", () => {
  /**
   * Invariant: formatExact() returns a locale-formatted date string.  Garbage
   * inputs produce "Invalid Date" variants — never HTML.
   */

  it.each(XSS_PAYLOADS)(
    "returns a non-HTML string for payload '%s'",
    (payload) => {
      const result = formatExact(payload);
      expect(result).not.toMatch(/<script/i);
      expect(result).not.toMatch(/onerror/i);
      expect(result).not.toMatch(/javascript:/i);
      expect(typeof result).toBe("string");
    },
  );
});

// ─── buildSessionGraph — XSS in span fields ──────────────────────────────────

describe("buildSessionGraph — XSS payloads in span fields", () => {
  /**
   * Invariant: buildSessionGraph() processes raw API data before it is handed
   * to the LineageGraph SVG renderer.  XSS payloads in agent_name, server_name,
   * tool_name, or span_id must appear as literal strings in node/edge labels,
   * never as parsed HTML.  The test verifies the graph is built (does not throw)
   * and that the label strings are not transformed into HTML.
   */

  it.each(XSS_PAYLOADS)(
    "builds graph without throwing for XSS payload '%s' in all string fields",
    (payload) => {
      const trace = makeXssTrace(payload);
      expect(() =>
        buildSessionGraph(trace, new Set(), new Set()),
      ).not.toThrow();
    },
  );

  it("preserves XSS payload as a literal label string, not parsed HTML", () => {
    const payload = '<script>window.__xss=1</script>';
    const graph = buildSessionGraph(makeXssTrace(payload), new Set(), new Set());

    // Node labels are raw strings from the API — the graph builder is not a
    // sanitizer and intentionally preserves them verbatim.  The invariant is that
    // the RENDERER must use React text interpolation ({node.label}), which
    // escapes the string into a safe text node.  What we verify here is:
    // 1. The builder does not crash.
    // 2. The label equals the raw payload — confirming no accidental HTML decode.
    // 3. No window-level side-effect was triggered during construction.
    const agentNode = graph.nodes.find((n) => n.type === "agent");
    expect(agentNode).toBeDefined();
    expect(agentNode?.label).toBe(payload);
    expect((window as typeof window & { __xss?: number }).__xss).toBeUndefined();
  });

  it("does not execute script payloads during graph construction", () => {
    const payload = '<script>window.__xss_graph=1</script>';
    buildSessionGraph(makeXssTrace(payload), new Set(), new Set());
    expect(
      (window as typeof window & { __xss_graph?: number }).__xss_graph,
    ).toBeUndefined();
  });

  it("produces correct node types even for extreme payloads", () => {
    const payload = '"><img src=x onerror=alert(1)>';
    const graph = buildSessionGraph(makeXssTrace(payload), new Set(), new Set());
    expect(graph.nodes.every((n) => n.type === "agent" || n.type === "server")).toBe(true);
  });
});
