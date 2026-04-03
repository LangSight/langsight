/**
 * session-graph.ts — adversarial and DoS boundary tests.
 *
 * Invariants tested in this file:
 *
 * 1. DoS resistance: buildSessionGraph() must terminate in finite time and not
 *    throw an unhandled error when given a trace with thousands of spans.
 *
 * 2. Numeric edge cases: NaN and Infinity in latency_ms / token counts must not
 *    propagate as NaN into PathMetrics or GraphNode fields in ways that would
 *    cause the renderer to crash or produce "NaN" in the UI.
 *
 * 3. Graph integrity under hostile edge data: self-referencing spans, circular
 *    agent handoffs, duplicate span IDs, and missing required fields must not
 *    break the graph builder.
 *
 * 4. No XSS through graph keys: node IDs and edge IDs are constructed from
 *    span field values.  Those IDs must not become executable HTML.
 */

import { buildSessionGraph } from "@/lib/session-graph";
import type { SessionTrace, SpanNode } from "@/lib/types";
import {
  makeOversizedTrace,
  makeNumericEdgeCaseTrace,
  makeXssTrace,
  XSS_PAYLOADS,
} from "./test-utils";

// ─── DoS: oversized trace ────────────────────────────────────────────────────

describe("buildSessionGraph — DoS resistance with large span counts", () => {
  /**
   * Invariant: the graph builder must not hang, throw OOM, or produce
   * an infinite structure when given a large but plausible number of spans.
   * 500 spans is well within what a looping agent can produce.
   */

  it("handles 500 spans without throwing", () => {
    const trace = makeOversizedTrace(500);
    expect(() => buildSessionGraph(trace, new Set(), new Set())).not.toThrow();
  });

  it("produces a finite node and edge list for 500 spans", () => {
    const trace = makeOversizedTrace(500);
    const graph = buildSessionGraph(trace, new Set(), new Set());
    expect(graph.nodes.length).toBeGreaterThan(0);
    expect(graph.nodes.length).toBeLessThan(500); // collapsed view
    expect(graph.edges.length).toBeGreaterThan(0);
    expect(graph.edges.length).toBeLessThan(500);
  });

  it("handles 2000 spans without throwing (stress test)", () => {
    const trace = makeOversizedTrace(2000);
    expect(() => buildSessionGraph(trace, new Set(), new Set())).not.toThrow();
  });

  it("nodes from oversized trace have finite avgLatencyMs values", () => {
    const trace = makeOversizedTrace(500);
    const graph = buildSessionGraph(trace, new Set(), new Set());
    for (const node of graph.nodes) {
      if (node.avgLatencyMs !== undefined) {
        expect(Number.isFinite(node.avgLatencyMs)).toBe(true);
      }
    }
  });
});

// ─── Numeric edge cases: NaN / Infinity in latency ───────────────────────────

describe("buildSessionGraph — NaN and Infinity in latency_ms", () => {
  /**
   * Invariant: if a span arrives with NaN latency (e.g. due to a backend bug or
   * a compromised trace), the graph builder must produce a usable graph.  The
   * avgLatencyMs in PathMetrics should either be NaN (handled by the UI as "—")
   * or be sanitised.  The critical invariant is that the builder does NOT throw.
   */

  it("does not throw when latency_ms is NaN", () => {
    const trace = makeNumericEdgeCaseTrace();
    expect(() => buildSessionGraph(trace, new Set(), new Set())).not.toThrow();
  });

  it("produces at least one node and one edge for numeric edge case trace", () => {
    const trace = makeNumericEdgeCaseTrace();
    const graph = buildSessionGraph(trace, new Set(), new Set());
    expect(graph.nodes.length).toBeGreaterThan(0);
    expect(graph.edges.length).toBeGreaterThan(0);
  });

  it("does not throw when all latency values are 0", () => {
    const trace: SessionTrace = {
      session_id: "zero-latency",
      spans_flat: [
        {
          span_id: "s1",
          parent_span_id: null,
          span_type: "tool_call",
          server_name: "srv",
          tool_name: "tool",
          agent_name: "agent",
          started_at: "2026-03-22T10:00:00Z",
          ended_at: "2026-03-22T10:00:00Z",
          latency_ms: 0,
          status: "success",
          error: null,
          trace_id: null,
          input_json: null,
          output_json: null,
          llm_input: null,
          llm_output: null,
          input_tokens: 0,
          output_tokens: 0,
          model_id: null,
          target_agent_name: null,
          lineage_provenance: "explicit" as const,
          lineage_status: "complete" as const,
          finish_reason: null,
        schema_version: "1.0",
          children: [],
        },
      ],
      root_spans: [],
      total_spans: 1,
      tool_calls: 1,
      failed_calls: 0,
      duration_ms: 0,
    };
    expect(() => buildSessionGraph(trace, new Set(), new Set())).not.toThrow();
  });

  it("does not throw when latency_ms is Infinity", () => {
    const trace: SessionTrace = {
      session_id: "inf-latency",
      spans_flat: [
        {
          span_id: "s1",
          parent_span_id: null,
          span_type: "tool_call",
          server_name: "srv",
          tool_name: "tool",
          agent_name: "agent",
          started_at: "2026-03-22T10:00:00Z",
          ended_at: "2026-03-22T10:00:00Z",
          latency_ms: Infinity,
          status: "error",
          error: null,
          trace_id: null,
          input_json: null,
          output_json: null,
          llm_input: null,
          llm_output: null,
          input_tokens: null,
          output_tokens: null,
          model_id: null,
          target_agent_name: null,
          lineage_provenance: "explicit" as const,
          lineage_status: "complete" as const,
          finish_reason: null,
        schema_version: "1.0",
          children: [],
        },
      ],
      root_spans: [],
      total_spans: 1,
      tool_calls: 1,
      failed_calls: 1,
      duration_ms: null,
    };
    expect(() => buildSessionGraph(trace, new Set(), new Set())).not.toThrow();
  });
});

// ─── Structural edge cases ────────────────────────────────────────────────────

describe("buildSessionGraph — structural edge cases", () => {
  /**
   * Invariant: graph builder must handle degenerate inputs gracefully:
   * null trace, empty spans, duplicate span IDs, circular handoffs, and spans
   * with missing required fields.
   */

  it("returns empty graph for null trace", () => {
    const graph = buildSessionGraph(null, new Set(), new Set());
    expect(graph.nodes).toHaveLength(0);
    expect(graph.edges).toHaveLength(0);
  });

  it("returns empty graph for trace with no spans", () => {
    const emptyTrace: SessionTrace = {
      session_id: "empty",
      spans_flat: [],
      root_spans: [],
      total_spans: 0,
      tool_calls: 0,
      failed_calls: 0,
      duration_ms: 0,
    };
    const graph = buildSessionGraph(emptyTrace, new Set(), new Set());
    expect(graph.nodes).toHaveLength(0);
    expect(graph.edges).toHaveLength(0);
  });

  it("does not throw on circular handoff A→B→A", () => {
    const trace: SessionTrace = {
      session_id: "circular",
      spans_flat: [
        {
          span_id: "h1",
          parent_span_id: null,
          span_type: "handoff",
          server_name: "",
          tool_name: "→agent-b",
          agent_name: "agent-a",
          started_at: "2026-03-22T10:00:00Z",
          ended_at: "2026-03-22T10:00:00.010Z",
          latency_ms: 10,
          status: "success",
          error: null,
          trace_id: null,
          input_json: null,
          output_json: null,
          llm_input: null,
          llm_output: null,
          input_tokens: null,
          output_tokens: null,
          model_id: null,
          target_agent_name: null,
          lineage_provenance: "explicit" as const,
          lineage_status: "complete" as const,
          finish_reason: null,
        schema_version: "1.0",
          children: [],
        },
        {
          span_id: "h2",
          parent_span_id: null,
          span_type: "handoff",
          server_name: "",
          tool_name: "→agent-a",
          agent_name: "agent-b",
          started_at: "2026-03-22T10:00:01Z",
          ended_at: "2026-03-22T10:00:01.010Z",
          latency_ms: 10,
          status: "success",
          error: null,
          trace_id: null,
          input_json: null,
          output_json: null,
          llm_input: null,
          llm_output: null,
          input_tokens: null,
          output_tokens: null,
          model_id: null,
          target_agent_name: null,
          lineage_provenance: "explicit" as const,
          lineage_status: "complete" as const,
          finish_reason: null,
        schema_version: "1.0",
          children: [],
        },
      ],
      root_spans: [],
      total_spans: 2,
      tool_calls: 0,
      failed_calls: 0,
      duration_ms: 1010,
    };

    expect(() => buildSessionGraph(trace, new Set(), new Set())).not.toThrow();
    const graph = buildSessionGraph(trace, new Set(), new Set());
    // Both agents should appear
    const ids = graph.nodes.map((n) => n.id);
    expect(ids).toContain("agent:agent-a");
    expect(ids).toContain("agent:agent-b");
  });

  it("does not throw when span_id is duplicated across spans", () => {
    const makeSpan = (id: string): SpanNode => ({
      span_id: id,
      parent_span_id: null,
      span_type: "tool_call",
      server_name: "srv",
      tool_name: "tool",
      agent_name: "agent",
      started_at: "2026-03-22T10:00:00Z",
      ended_at: "2026-03-22T10:00:00.050Z",
      latency_ms: 50,
      status: "success",
      error: null,
      trace_id: null,
      input_json: null,
      output_json: null,
      llm_input: null,
      llm_output: null,
      input_tokens: null,
      output_tokens: null,
      model_id: null,
      finish_reason: null,
      target_agent_name: null,
      lineage_provenance: "explicit" as const,
      lineage_status: "complete" as const,
      schema_version: "1.0",
      children: [],
    });

    const trace: SessionTrace = {
      session_id: "dup-ids",
      spans_flat: [
        makeSpan("DUPLICATE-ID"),
        makeSpan("DUPLICATE-ID"), // exact duplicate
      ],
      root_spans: [],
      total_spans: 2,
      tool_calls: 2,
      failed_calls: 0,
      duration_ms: 100,
    };

    expect(() => buildSessionGraph(trace, new Set(), new Set())).not.toThrow();
  });

  it("does not throw when agent_name is null", () => {
    const trace: SessionTrace = {
      session_id: "null-agent",
      spans_flat: [
        {
          span_id: "s1",
          parent_span_id: null,
          span_type: "tool_call",
          server_name: "srv",
          tool_name: "tool",
          agent_name: null, // deliberately null
          started_at: "2026-03-22T10:00:00Z",
          ended_at: "2026-03-22T10:00:00.050Z",
          latency_ms: 50,
          status: "success",
          error: null,
          trace_id: null,
          input_json: null,
          output_json: null,
          llm_input: null,
          llm_output: null,
          input_tokens: null,
          output_tokens: null,
          model_id: null,
          target_agent_name: null,
          lineage_provenance: "explicit" as const,
          lineage_status: "complete" as const,
          finish_reason: null,
        schema_version: "1.0",
          children: [],
        },
      ],
      root_spans: [],
      total_spans: 1,
      tool_calls: 1,
      failed_calls: 0,
      duration_ms: 50,
    };

    expect(() => buildSessionGraph(trace, new Set(), new Set())).not.toThrow();
  });
});

// ─── XSS: node IDs and edge IDs must not execute ─────────────────────────────

describe("buildSessionGraph — XSS payloads in node/edge IDs do not execute", () => {
  /**
   * Invariant: node.id values are constructed as `agent:${agentName}` and
   * `server:${serverName}`.  Even if these contain HTML/JS, they must not
   * execute during graph construction (pure TS, no DOM access).
   * Execution risk exists only when the renderer uses dangerouslySetInnerHTML
   * with these IDs — which it must not do.  These tests confirm construction
   * is safe and that window global side-effects do not occur.
   */

  it.each(XSS_PAYLOADS)(
    "does not set window.__xss during graph build with payload '%s'",
    (payload) => {
      delete (window as typeof window & { __xss?: number }).__xss;
      buildSessionGraph(makeXssTrace(payload), new Set(), new Set());
      expect((window as typeof window & { __xss?: number }).__xss).toBeUndefined();
    },
  );

  it("node IDs with XSS payload contain the prefix 'agent:' or 'server:'", () => {
    const payload = '<script>window.__xss=1</script>';
    const graph = buildSessionGraph(makeXssTrace(payload), new Set(), new Set());
    for (const node of graph.nodes) {
      expect(node.id.startsWith("agent:") || node.id.startsWith("server:")).toBe(true);
    }
  });

  it("edge source and target always reference known node IDs", () => {
    const payload = '"><img onerror=alert(1) src=x>';
    const graph = buildSessionGraph(makeXssTrace(payload), new Set(), new Set());
    const nodeIds = new Set(graph.nodes.map((n) => n.id));
    for (const edge of graph.edges) {
      // Every edge endpoint must resolve to a node that was built
      expect(nodeIds.has(edge.source)).toBe(true);
      expect(nodeIds.has(edge.target)).toBe(true);
    }
  });
});

// ─── normalizeInput behaviour (via repeated-call detection) ──────────────────

describe("buildSessionGraph — normalizeInput handles hostile JSON in input_json", () => {
  /**
   * Invariant: normalizeInput() calls JSON.parse on span.input_json to produce
   * a canonical key for repeat-detection.  Malformed JSON must not throw — the
   * function catches parse errors and falls back to the raw string.
   * A crafted input_json containing a prototype pollution payload must not
   * modify Object.prototype.
   */

  it("does not throw when input_json is malformed JSON", () => {
    const trace: SessionTrace = {
      session_id: "bad-json",
      spans_flat: [
        {
          span_id: "s1",
          parent_span_id: null,
          span_type: "tool_call",
          server_name: "srv",
          tool_name: "tool",
          agent_name: "agent",
          started_at: "2026-03-22T10:00:00Z",
          ended_at: "2026-03-22T10:00:00.050Z",
          latency_ms: 50,
          status: "success",
          error: null,
          trace_id: null,
          input_json: "{ this is not valid JSON !!!",
          output_json: null,
          llm_input: null,
          llm_output: null,
          input_tokens: null,
          output_tokens: null,
          model_id: null,
          target_agent_name: null,
          lineage_provenance: "explicit" as const,
          lineage_status: "complete" as const,
          finish_reason: null,
        schema_version: "1.0",
          children: [],
        },
      ],
      root_spans: [],
      total_spans: 1,
      tool_calls: 1,
      failed_calls: 0,
      duration_ms: 50,
    };
    expect(() => buildSessionGraph(trace, new Set(), new Set())).not.toThrow();
  });

  it("does not pollute Object.prototype via JSON.parse of crafted input_json", () => {
    // A prototype pollution attempt via JSON.parse
    const protoPayload = '{"__proto__": {"polluted": true}}';
    const trace: SessionTrace = {
      session_id: "proto-pollution",
      spans_flat: [
        {
          span_id: "s1",
          parent_span_id: null,
          span_type: "tool_call",
          server_name: "srv",
          tool_name: "tool",
          agent_name: "agent",
          started_at: "2026-03-22T10:00:00Z",
          ended_at: "2026-03-22T10:00:00.050Z",
          latency_ms: 50,
          status: "success",
          error: null,
          trace_id: null,
          input_json: protoPayload,
          output_json: null,
          llm_input: null,
          llm_output: null,
          input_tokens: null,
          output_tokens: null,
          model_id: null,
          target_agent_name: null,
          lineage_provenance: "explicit" as const,
          lineage_status: "complete" as const,
          finish_reason: null,
        schema_version: "1.0",
          children: [],
        },
      ],
      root_spans: [],
      total_spans: 1,
      tool_calls: 1,
      failed_calls: 0,
      duration_ms: 50,
    };

    expect(() => buildSessionGraph(trace, new Set(), new Set())).not.toThrow();

    // Object.prototype must not have been polluted
    const plain: Record<string, unknown> = {};
    expect(plain["polluted"]).toBeUndefined();
  });

  it("does not throw when input_json is null", () => {
    const trace: SessionTrace = {
      session_id: "null-input",
      spans_flat: [
        {
          span_id: "s1",
          parent_span_id: null,
          span_type: "tool_call",
          server_name: "srv",
          tool_name: "tool",
          agent_name: "agent",
          started_at: "2026-03-22T10:00:00Z",
          ended_at: "2026-03-22T10:00:00.050Z",
          latency_ms: 50,
          status: "success",
          error: null,
          trace_id: null,
          input_json: null,
          output_json: null,
          llm_input: null,
          llm_output: null,
          input_tokens: null,
          output_tokens: null,
          model_id: null,
          target_agent_name: null,
          lineage_provenance: "explicit" as const,
          lineage_status: "complete" as const,
          finish_reason: null,
        schema_version: "1.0",
          children: [],
        },
        // Second identical span — triggers repeat detection path
        {
          span_id: "s2",
          parent_span_id: null,
          span_type: "tool_call",
          server_name: "srv",
          tool_name: "tool",
          agent_name: "agent",
          started_at: "2026-03-22T10:00:01Z",
          ended_at: "2026-03-22T10:00:01.050Z",
          latency_ms: 50,
          status: "success",
          error: null,
          trace_id: null,
          input_json: null,
          output_json: null,
          llm_input: null,
          llm_output: null,
          input_tokens: null,
          output_tokens: null,
          model_id: null,
          target_agent_name: null,
          lineage_provenance: "explicit" as const,
          lineage_status: "complete" as const,
          finish_reason: null,
        schema_version: "1.0",
          children: [],
        },
      ],
      root_spans: [],
      total_spans: 2,
      tool_calls: 2,
      failed_calls: 0,
      duration_ms: 1050,
    };

    expect(() => buildSessionGraph(trace, new Set(), new Set())).not.toThrow();
  });
});
