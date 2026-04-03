/**
 * Extended tests for buildSessionGraph (lib/session-graph.ts).
 *
 * The original session-graph.test.ts covers the repeat-call expansion path.
 * This file covers the remaining branches:
 *   - null trace → empty result
 *   - single agent, single server, single call
 *   - handoff spans produce handoff edges
 *   - error spans mark agent and server nodes hasError
 *   - multi-caller server: collapsed vs. expanded group
 *   - edge metrics accumulation (avgLatencyMs, errorCount, tools dedup)
 *   - token and model attribution
 *   - serverCallers map construction
 *   - edgeSpans map construction
 *   - agent spans without tool_calls are still collected as agent nodes
 *   - unknown agent fallback for spans missing agent_name
 */
import type { SessionTrace, SpanNode } from "@/lib/types";
import { buildSessionGraph } from "@/lib/session-graph";

/* ── Span factory ─────────────────────────────────────────────── */
function makeSpan(overrides: Partial<SpanNode> = {}): SpanNode {
  return {
    span_id: "span-default",
    parent_span_id: null,
    span_type: "tool_call",
    server_name: "test-server",
    tool_name: "test_tool",
    agent_name: "agent-a",
    started_at: "2026-03-22T10:00:00Z",
    ended_at: "2026-03-22T10:00:00.050Z",
    latency_ms: 50,
    status: "success",
    error: null,
    trace_id: "trace-1",
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
    ...overrides,
  };
}

function makeTrace(spans: SpanNode[], overrides: Partial<SessionTrace> = {}): SessionTrace {
  return {
    session_id: "sess-test",
    spans_flat: spans,
    root_spans: [],
    total_spans: spans.length,
    tool_calls: spans.filter((s) => s.span_type === "tool_call").length,
    failed_calls: spans.filter((s) => s.status !== "success").length,
    duration_ms: 200,
    ...overrides,
  };
}

/* ── Null / empty trace ──────────────────────────────────────── */
describe("buildSessionGraph — null / empty trace", () => {
  it("returns empty result when trace is null", () => {
    const result = buildSessionGraph(null, new Set(), new Set());
    expect(result.nodes).toHaveLength(0);
    expect(result.edges).toHaveLength(0);
    expect(result.serverCallers.size).toBe(0);
    expect(result.edgeMetrics.size).toBe(0);
    expect(result.edgeSpans.size).toBe(0);
  });

  it("returns empty result for a trace with no spans", () => {
    const result = buildSessionGraph(makeTrace([]), new Set(), new Set());
    expect(result.nodes).toHaveLength(0);
    expect(result.edges).toHaveLength(0);
  });
});

/* ── Single agent, single server, single call ───────────────── */
describe("buildSessionGraph — single agent / single server / single call", () => {
  const TRACE = makeTrace([
    makeSpan({ span_id: "s1", agent_name: "agent-a", server_name: "pg-mcp", tool_name: "query", latency_ms: 80 }),
  ]);

  it("creates exactly one agent node", () => {
    const { nodes } = buildSessionGraph(TRACE, new Set(), new Set());
    const agentNodes = nodes.filter((n) => n.type === "agent");
    expect(agentNodes).toHaveLength(1);
    expect(agentNodes[0].id).toBe("agent:agent-a");
    expect(agentNodes[0].label).toBe("agent-a");
  });

  it("creates exactly one server node", () => {
    const { nodes } = buildSessionGraph(TRACE, new Set(), new Set());
    const serverNodes = nodes.filter((n) => n.type === "server");
    expect(serverNodes).toHaveLength(1);
    expect(serverNodes[0].id).toBe("server:pg-mcp");
    expect(serverNodes[0].label).toBe("pg-mcp");
  });

  it("creates exactly one calls edge from agent to server", () => {
    const { edges } = buildSessionGraph(TRACE, new Set(), new Set());
    expect(edges).toHaveLength(1);
    expect(edges[0].source).toBe("agent:agent-a");
    expect(edges[0].target).toBe("server:pg-mcp");
    expect(edges[0].type).toBe("calls");
  });

  it("edge has no label for a single call", () => {
    const { edges } = buildSessionGraph(TRACE, new Set(), new Set());
    expect(edges[0].label).toBeUndefined();
  });

  it("server node callCount is 1", () => {
    const { nodes } = buildSessionGraph(TRACE, new Set(), new Set());
    const server = nodes.find((n) => n.id === "server:pg-mcp")!;
    expect(server.callCount).toBe(1);
  });

  it("server node hasError is false for a success span", () => {
    const { nodes } = buildSessionGraph(TRACE, new Set(), new Set());
    const server = nodes.find((n) => n.id === "server:pg-mcp")!;
    expect(server.hasError).toBe(false);
  });

  it("agent node hasError is false for a success span", () => {
    const { nodes } = buildSessionGraph(TRACE, new Set(), new Set());
    const agent = nodes.find((n) => n.id === "agent:agent-a")!;
    expect(agent.hasError).toBe(false);
  });

  it("agent node callCount matches tool_call span count", () => {
    const { nodes } = buildSessionGraph(TRACE, new Set(), new Set());
    const agent = nodes.find((n) => n.id === "agent:agent-a")!;
    expect(agent.callCount).toBe(1);
  });
});

/* ── Error spans ─────────────────────────────────────────────── */
describe("buildSessionGraph — error spans", () => {
  const TRACE = makeTrace([
    makeSpan({ span_id: "s1", agent_name: "agent-a", server_name: "s3-mcp", tool_name: "put_object", status: "error", latency_ms: 200 }),
  ]);

  it("marks the server node hasError when a span has status !== success", () => {
    const { nodes } = buildSessionGraph(TRACE, new Set(), new Set());
    const server = nodes.find((n) => n.id === "server:s3-mcp")!;
    expect(server.hasError).toBe(true);
  });

  it("marks the agent node hasError when any of its tool_call spans error", () => {
    const { nodes } = buildSessionGraph(TRACE, new Set(), new Set());
    const agent = nodes.find((n) => n.id === "agent:agent-a")!;
    expect(agent.hasError).toBe(true);
  });

  it("server node errorCount equals number of error spans", () => {
    const { nodes } = buildSessionGraph(TRACE, new Set(), new Set());
    const server = nodes.find((n) => n.id === "server:s3-mcp")!;
    expect(server.errorCount).toBe(1);
  });

  it("edge has errorCount matching the span error count", () => {
    const { edges } = buildSessionGraph(TRACE, new Set(), new Set());
    expect(edges[0].errorCount).toBe(1);
  });
});

/* ── Multiple calls — edge label ─────────────────────────────── */
describe("buildSessionGraph — multiple calls produce a ×-label edge", () => {
  const TRACE = makeTrace([
    makeSpan({ span_id: "s1", agent_name: "agent-a", server_name: "pg-mcp", tool_name: "query", latency_ms: 30 }),
    makeSpan({ span_id: "s2", agent_name: "agent-a", server_name: "pg-mcp", tool_name: "query", latency_ms: 40 }),
    makeSpan({ span_id: "s3", agent_name: "agent-a", server_name: "pg-mcp", tool_name: "query", latency_ms: 50 }),
  ]);

  it("edge label is '3×' for 3 calls", () => {
    const { edges } = buildSessionGraph(TRACE, new Set(), new Set());
    const edge = edges.find((e) => e.source === "agent:agent-a" && e.target === "server:pg-mcp");
    expect(edge?.label).toBe("3×");
  });

  it("server node callCount is 3", () => {
    const { nodes } = buildSessionGraph(TRACE, new Set(), new Set());
    const server = nodes.find((n) => n.id === "server:pg-mcp")!;
    expect(server.callCount).toBe(3);
  });
});

/* ── Handoff spans ────────────────────────────────────────────── */
describe("buildSessionGraph — handoff spans", () => {
  it("handoff span produces a handoff edge between agent nodes", () => {
    const TRACE = makeTrace([
      makeSpan({ span_id: "h1", span_type: "handoff", agent_name: "agent-a", tool_name: "→ agent-b", server_name: "" }),
    ]);
    const { edges } = buildSessionGraph(TRACE, new Set(), new Set());
    const handoffEdge = edges.find((e) => e.type === "handoff");
    expect(handoffEdge).toBeDefined();
    expect(handoffEdge?.source).toBe("agent:agent-a");
    expect(handoffEdge?.target).toBe("agent:agent-b");
  });

  it("handoff creates an agent node for the target agent", () => {
    const TRACE = makeTrace([
      makeSpan({ span_id: "h1", span_type: "handoff", agent_name: "agent-a", tool_name: "→ agent-b", server_name: "" }),
    ]);
    const { nodes } = buildSessionGraph(TRACE, new Set(), new Set());
    const agentB = nodes.find((n) => n.id === "agent:agent-b");
    expect(agentB).toBeDefined();
    expect(agentB?.label).toBe("agent-b");
  });

  it("handoff edge edgeId follows the agent:src→h→agent:tgt convention", () => {
    const TRACE = makeTrace([
      makeSpan({ span_id: "h1", span_type: "handoff", agent_name: "agent-a", tool_name: "agent-b", server_name: "" }),
    ]);
    const { edges } = buildSessionGraph(TRACE, new Set(), new Set());
    const handoffEdge = edges.find((e) => e.type === "handoff")!;
    expect(handoffEdge.edgeId).toBe("agent:agent-a→h→agent:agent-b");
  });

  it("multiple handoffs between the same pair produce a count label", () => {
    const TRACE = makeTrace([
      makeSpan({ span_id: "h1", span_type: "handoff", agent_name: "agent-a", tool_name: "agent-b", server_name: "" }),
      makeSpan({ span_id: "h2", span_type: "handoff", agent_name: "agent-a", tool_name: "agent-b", server_name: "" }),
    ]);
    const { edges } = buildSessionGraph(TRACE, new Set(), new Set());
    const handoffEdge = edges.find((e) => e.type === "handoff")!;
    expect(handoffEdge.label).toBe("2 handoffs");
  });

  it("strips leading '→ ' prefix from the handoff target name", () => {
    const TRACE = makeTrace([
      makeSpan({ span_id: "h1", span_type: "handoff", agent_name: "agent-a", tool_name: "→ cleanup-agent", server_name: "" }),
    ]);
    const { nodes } = buildSessionGraph(TRACE, new Set(), new Set());
    expect(nodes.find((n) => n.id === "agent:cleanup-agent")).toBeDefined();
  });
});

/* ── Edge metrics accumulation ───────────────────────────────── */
describe("buildSessionGraph — edge metrics", () => {
  const spans: SpanNode[] = [
    makeSpan({ span_id: "s1", agent_name: "ag", server_name: "srv", tool_name: "toolA", latency_ms: 100, input_tokens: 10, output_tokens: 5, model_id: "gpt-4" }),
    makeSpan({ span_id: "s2", agent_name: "ag", server_name: "srv", tool_name: "toolB", latency_ms: 200, input_tokens: 20, output_tokens: 10, model_id: "gpt-4" }),
    makeSpan({ span_id: "s3", agent_name: "ag", server_name: "srv", tool_name: "toolA", latency_ms: 300, status: "error", input_tokens: 5, output_tokens: 0, model_id: "claude-3" }),
  ];
  const TRACE = makeTrace(spans);

  it("edgeMetrics callCount equals number of tool_call spans on that path", () => {
    const { edgeMetrics } = buildSessionGraph(TRACE, new Set(), new Set());
    const metrics = edgeMetrics.get("agent:ag→server:srv")!;
    expect(metrics.callCount).toBe(3);
  });

  it("edgeMetrics errorCount equals number of error spans", () => {
    const { edgeMetrics } = buildSessionGraph(TRACE, new Set(), new Set());
    const metrics = edgeMetrics.get("agent:ag→server:srv")!;
    expect(metrics.errorCount).toBe(1);
  });

  it("edgeMetrics avgLatencyMs is the mean of span latencies", () => {
    const { edgeMetrics } = buildSessionGraph(TRACE, new Set(), new Set());
    const metrics = edgeMetrics.get("agent:ag→server:srv")!;
    expect(metrics.avgLatencyMs).toBeCloseTo((100 + 200 + 300) / 3);
  });

  it("edgeMetrics maxLatencyMs is the maximum span latency", () => {
    const { edgeMetrics } = buildSessionGraph(TRACE, new Set(), new Set());
    const metrics = edgeMetrics.get("agent:ag→server:srv")!;
    expect(metrics.maxLatencyMs).toBe(300);
  });

  it("edgeMetrics tools contains unique tool names", () => {
    const { edgeMetrics } = buildSessionGraph(TRACE, new Set(), new Set());
    const metrics = edgeMetrics.get("agent:ag→server:srv")!;
    expect(metrics.tools).toEqual(expect.arrayContaining(["toolA", "toolB"]));
    // No duplicates
    expect(new Set(metrics.tools).size).toBe(metrics.tools.length);
  });

  it("edgeMetrics inputTokens sums all span input_tokens", () => {
    const { edgeMetrics } = buildSessionGraph(TRACE, new Set(), new Set());
    const metrics = edgeMetrics.get("agent:ag→server:srv")!;
    expect(metrics.inputTokens).toBe(10 + 20 + 5);
  });

  it("edgeMetrics outputTokens sums all span output_tokens", () => {
    const { edgeMetrics } = buildSessionGraph(TRACE, new Set(), new Set());
    const metrics = edgeMetrics.get("agent:ag→server:srv")!;
    expect(metrics.outputTokens).toBe(5 + 10 + 0);
  });

  it("edgeMetrics models deduplicates model IDs", () => {
    const { edgeMetrics } = buildSessionGraph(TRACE, new Set(), new Set());
    const metrics = edgeMetrics.get("agent:ag→server:srv")!;
    expect(metrics.models).toContain("gpt-4");
    expect(metrics.models).toContain("claude-3");
    expect(new Set(metrics.models).size).toBe(metrics.models.length);
  });
});

/* ── edgeSpans map ────────────────────────────────────────────── */
describe("buildSessionGraph — edgeSpans map", () => {
  it("edgeSpans contains the spans for each path key", () => {
    const spans = [
      makeSpan({ span_id: "s1", agent_name: "ag", server_name: "srv", tool_name: "read" }),
      makeSpan({ span_id: "s2", agent_name: "ag", server_name: "srv", tool_name: "write" }),
    ];
    const { edgeSpans } = buildSessionGraph(makeTrace(spans), new Set(), new Set());
    const spansForPath = edgeSpans.get("agent:ag→server:srv")!;
    expect(spansForPath).toHaveLength(2);
    expect(spansForPath.map((s) => s.span_id)).toContain("s1");
    expect(spansForPath.map((s) => s.span_id)).toContain("s2");
  });
});

/* ── serverCallers map ────────────────────────────────────────── */
describe("buildSessionGraph — serverCallers map", () => {
  it("serverCallers lists the agents that call each server", () => {
    const spans = [
      makeSpan({ span_id: "s1", agent_name: "agent-a", server_name: "pg-mcp", tool_name: "query" }),
    ];
    const { serverCallers } = buildSessionGraph(makeTrace(spans), new Set(), new Set());
    const callers = serverCallers.get("pg-mcp")!;
    expect(callers).toHaveLength(1);
    expect(callers[0].agentLabel).toBe("agent-a");
    expect(callers[0].agentId).toBe("agent:agent-a");
  });

  it("serverCallers lists multiple agents when they share a server", () => {
    const spans = [
      makeSpan({ span_id: "s1", agent_name: "agent-a", server_name: "shared-srv", tool_name: "read" }),
      makeSpan({ span_id: "s2", agent_name: "agent-b", server_name: "shared-srv", tool_name: "read" }),
    ];
    const { serverCallers } = buildSessionGraph(makeTrace(spans), new Set(), new Set());
    const callers = serverCallers.get("shared-srv")!;
    expect(callers).toHaveLength(2);
    const labels = callers.map((c) => c.agentLabel);
    expect(labels).toContain("agent-a");
    expect(labels).toContain("agent-b");
  });
});

/* ── Multi-caller server: collapsed vs expanded ──────────────── */
describe("buildSessionGraph — multi-caller server (expand/collapse)", () => {
  function makeMultiCallerTrace(): SessionTrace {
    return makeTrace([
      makeSpan({ span_id: "s1", agent_name: "agent-a", server_name: "shared-srv", tool_name: "read", latency_ms: 40 }),
      makeSpan({ span_id: "s2", agent_name: "agent-b", server_name: "shared-srv", tool_name: "write", latency_ms: 60 }),
    ]);
  }

  it("collapses multi-caller server into a single node by default", () => {
    const { nodes } = buildSessionGraph(makeMultiCallerTrace(), new Set(), new Set());
    const serverNodes = nodes.filter((n) => n.id === "server:shared-srv");
    // Collapsed = single node with id "server:shared-srv"
    expect(serverNodes).toHaveLength(1);
  });

  it("collapsed multi-caller node has isCollapsible = true", () => {
    const { nodes } = buildSessionGraph(makeMultiCallerTrace(), new Set(), new Set());
    const serverNode = nodes.find((n) => n.id === "server:shared-srv")!;
    expect(serverNode.isCollapsible).toBe(true);
  });

  it("collapsed multi-caller node has collapsedCount = 2", () => {
    const { nodes } = buildSessionGraph(makeMultiCallerTrace(), new Set(), new Set());
    const serverNode = nodes.find((n) => n.id === "server:shared-srv")!;
    expect(serverNode.collapsedCount).toBe(2);
  });

  it("expands into split nodes when the group is in expandedGroups", () => {
    const { nodes } = buildSessionGraph(
      makeMultiCallerTrace(),
      new Set(["server:shared-srv"]),
      new Set(),
    );
    // Split nodes have IDs like "server:shared-srv::via:agent-a"
    const splitNodes = nodes.filter((n) => n.id.includes("::via:"));
    expect(splitNodes).toHaveLength(2);
  });

  it("expanded split nodes have groupId set to the parent server ID", () => {
    const { nodes } = buildSessionGraph(
      makeMultiCallerTrace(),
      new Set(["server:shared-srv"]),
      new Set(),
    );
    const splitNodes = nodes.filter((n) => n.id.includes("::via:"));
    for (const node of splitNodes) {
      expect(node.groupId).toBe("server:shared-srv");
    }
  });

  it("expanded split nodes have splitLabel prefixed with 'via '", () => {
    const { nodes } = buildSessionGraph(
      makeMultiCallerTrace(),
      new Set(["server:shared-srv"]),
      new Set(),
    );
    const splitNodes = nodes.filter((n) => n.id.includes("::via:"));
    for (const node of splitNodes) {
      expect(node.splitLabel).toMatch(/^via /);
    }
  });
});

/* ── Agent node metrics ───────────────────────────────────────── */
describe("buildSessionGraph — agent node metrics", () => {
  it("agent node avgLatencyMs is mean of its tool_call latencies", () => {
    const spans = [
      makeSpan({ span_id: "s1", agent_name: "ag", server_name: "srv", tool_name: "t", latency_ms: 100 }),
      makeSpan({ span_id: "s2", agent_name: "ag", server_name: "srv", tool_name: "t", latency_ms: 200 }),
    ];
    const { nodes } = buildSessionGraph(makeTrace(spans), new Set(), new Set());
    const agent = nodes.find((n) => n.id === "agent:ag")!;
    expect(agent.avgLatencyMs).toBeCloseTo(150);
  });

  it("agent node errorCount is number of non-success tool_call spans", () => {
    const spans = [
      makeSpan({ span_id: "s1", agent_name: "ag", server_name: "srv", tool_name: "t", status: "success" }),
      makeSpan({ span_id: "s2", agent_name: "ag", server_name: "srv", tool_name: "t", status: "error" }),
    ];
    const { nodes } = buildSessionGraph(makeTrace(spans), new Set(), new Set());
    const agent = nodes.find((n) => n.id === "agent:ag")!;
    expect(agent.errorCount).toBe(1);
  });
});

/* ── Expanded edge (per-call split) ──────────────────────────── */
describe("buildSessionGraph — per-call expansion (expandedEdges)", () => {
  function makeRepeatTrace(): SessionTrace {
    return makeTrace([
      makeSpan({ span_id: "c1", agent_name: "ag", server_name: "srv", tool_name: "get", input_json: '"a"', latency_ms: 10 }),
      makeSpan({ span_id: "c2", agent_name: "ag", server_name: "srv", tool_name: "get", input_json: '"a"', latency_ms: 20 }),
    ]);
  }

  it("expands to per-call nodes when the edge is in expandedEdges", () => {
    const { nodes } = buildSessionGraph(
      makeRepeatTrace(),
      new Set(),
      new Set(["agent:ag→server:srv"]),
    );
    const callNodes = nodes.filter((n) => n.id.includes("::call:"));
    expect(callNodes).toHaveLength(2);
  });

  it("per-call node labels are numbered (tool #1, tool #2)", () => {
    const { nodes } = buildSessionGraph(
      makeRepeatTrace(),
      new Set(),
      new Set(["agent:ag→server:srv"]),
    );
    const labels = nodes
      .filter((n) => n.id.includes("::call:"))
      .map((n) => n.label);
    expect(labels).toContain("get #1");
    expect(labels).toContain("get #2");
  });

  it("each per-call node has callCount = 1", () => {
    const { nodes } = buildSessionGraph(
      makeRepeatTrace(),
      new Set(),
      new Set(["agent:ag→server:srv"]),
    );
    nodes.filter((n) => n.id.includes("::call:")).forEach((n) => {
      expect(n.callCount).toBe(1);
    });
  });
});

/* ── Null tokens / model gracefully handled ───────────────────── */
describe("buildSessionGraph — null tokens and model_id", () => {
  it("inputTokens defaults to 0 when span.input_tokens is null", () => {
    const spans = [makeSpan({ span_id: "s1", agent_name: "ag", server_name: "srv", tool_name: "t", input_tokens: null, output_tokens: null, model_id: null })];
    const { edgeMetrics } = buildSessionGraph(makeTrace(spans), new Set(), new Set());
    const m = edgeMetrics.get("agent:ag→server:srv")!;
    expect(m.inputTokens).toBe(0);
    expect(m.outputTokens).toBe(0);
    expect(m.models).toHaveLength(0);
  });
});

/* ── Repeat detection edge cases ──────────────────────────────── */
describe("buildSessionGraph — repeat call detection", () => {
  it("does not mark repeatCallName when all calls have different inputs", () => {
    const spans = [
      makeSpan({ span_id: "s1", agent_name: "ag", server_name: "srv", tool_name: "query", input_json: '"query1"' }),
      makeSpan({ span_id: "s2", agent_name: "ag", server_name: "srv", tool_name: "query", input_json: '"query2"' }),
    ];
    const { nodes } = buildSessionGraph(makeTrace(spans), new Set(), new Set());
    const server = nodes.find((n) => n.id === "server:srv")!;
    expect(server.repeatCallName).toBeUndefined();
  });

  it("marks repeatCallName when the same tool+input appears 2+ times", () => {
    const spans = [
      makeSpan({ span_id: "s1", agent_name: "ag", server_name: "srv", tool_name: "fetch", input_json: '"same"' }),
      makeSpan({ span_id: "s2", agent_name: "ag", server_name: "srv", tool_name: "fetch", input_json: '"same"' }),
    ];
    const { nodes } = buildSessionGraph(makeTrace(spans), new Set(), new Set());
    const server = nodes.find((n) => n.id === "server:srv")!;
    expect(server.repeatCallName).toBe("fetch");
    expect(server.repeatCallCount).toBe(2);
  });

  it("normalizes JSON input before comparing — pretty-printed and minified are equal", () => {
    const spans = [
      makeSpan({ span_id: "s1", agent_name: "ag", server_name: "srv", tool_name: "q", input_json: '{"id": 1}' }),
      makeSpan({ span_id: "s2", agent_name: "ag", server_name: "srv", tool_name: "q", input_json: '{"id":1}' }),
    ];
    const { nodes } = buildSessionGraph(makeTrace(spans), new Set(), new Set());
    const server = nodes.find((n) => n.id === "server:srv")!;
    expect(server.repeatCallName).toBe("q");
    expect(server.repeatCallCount).toBe(2);
  });

  it("treats null input as 'null' string for comparison", () => {
    const spans = [
      makeSpan({ span_id: "s1", agent_name: "ag", server_name: "srv", tool_name: "ping", input_json: null }),
      makeSpan({ span_id: "s2", agent_name: "ag", server_name: "srv", tool_name: "ping", input_json: null }),
    ];
    const { nodes } = buildSessionGraph(makeTrace(spans), new Set(), new Set());
    const server = nodes.find((n) => n.id === "server:srv")!;
    expect(server.repeatCallName).toBe("ping");
    expect(server.repeatCallCount).toBe(2);
  });
});

/* ── Multiple servers and agents ─────────────────────────────── */
describe("buildSessionGraph — multi-agent multi-server trace", () => {
  const TRACE = makeTrace([
    makeSpan({ span_id: "s1", agent_name: "orchestrator", server_name: "pg-mcp", tool_name: "query" }),
    makeSpan({ span_id: "s2", agent_name: "orchestrator", server_name: "s3-mcp", tool_name: "read_object" }),
    makeSpan({ span_id: "s3", agent_name: "worker", server_name: "pg-mcp", tool_name: "insert" }),
    makeSpan({ span_id: "h1", span_type: "handoff", agent_name: "orchestrator", tool_name: "worker", server_name: "" }),
  ]);

  it("creates agent nodes for all unique agents", () => {
    const { nodes } = buildSessionGraph(TRACE, new Set(), new Set());
    const agentIds = nodes.filter((n) => n.type === "agent").map((n) => n.id);
    expect(agentIds).toContain("agent:orchestrator");
    expect(agentIds).toContain("agent:worker");
  });

  it("creates a node for every distinct server", () => {
    const { nodes } = buildSessionGraph(TRACE, new Set(), new Set());
    // Both pg-mcp (multi-caller: orchestrator + worker) and s3-mcp are present
    const serverIds = nodes.filter((n) => n.type === "server").map((n) => n.id);
    expect(serverIds).toContain("server:s3-mcp");
    // pg-mcp is multi-caller — collapsed to single node
    expect(serverIds).toContain("server:pg-mcp");
  });

  it("creates a handoff edge from orchestrator to worker", () => {
    const { edges } = buildSessionGraph(TRACE, new Set(), new Set());
    const handoff = edges.find((e) => e.type === "handoff");
    expect(handoff?.source).toBe("agent:orchestrator");
    expect(handoff?.target).toBe("agent:worker");
  });
});
