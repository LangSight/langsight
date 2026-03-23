import type { SessionTrace } from "@/lib/types";
import { buildSessionGraph } from "@/lib/session-graph";

function makeRepeatedTrace(): SessionTrace {
  return {
    session_id: "sess-repeat",
    spans_flat: [
      {
        span_id: "span-1",
        parent_span_id: "agent-1",
        span_type: "tool_call",
        server_name: "postgres-mcp",
        tool_name: "query",
        agent_name: "support-agent",
        started_at: "2026-03-22T10:00:00Z",
        ended_at: "2026-03-22T10:00:00.035Z",
        latency_ms: 35,
        status: "success",
        error: null,
        trace_id: "trace-1",
        input_json: '{"sql":"select * from tickets where id = 42"}',
        output_json: '{"rows":1}',
        llm_input: null,
        llm_output: null,
        input_tokens: null,
        output_tokens: null,
        model_id: null,
        children: [],
      },
      {
        span_id: "span-2",
        parent_span_id: "agent-1",
        span_type: "tool_call",
        server_name: "postgres-mcp",
        tool_name: "query",
        agent_name: "support-agent",
        started_at: "2026-03-22T10:00:01Z",
        ended_at: "2026-03-22T10:00:01.033Z",
        latency_ms: 33,
        status: "success",
        error: null,
        trace_id: "trace-1",
        input_json: '{"sql":"select * from tickets where id = 42"}',
        output_json: '{"rows":1}',
        llm_input: null,
        llm_output: null,
        input_tokens: null,
        output_tokens: null,
        model_id: null,
        children: [],
      },
      {
        span_id: "span-3",
        parent_span_id: "agent-1",
        span_type: "tool_call",
        server_name: "postgres-mcp",
        tool_name: "query",
        agent_name: "support-agent",
        started_at: "2026-03-22T10:00:02Z",
        ended_at: "2026-03-22T10:00:02.050Z",
        latency_ms: 50,
        status: "error",
        error: "timeout",
        trace_id: "trace-1",
        input_json: '{"sql":"select * from tickets where id = 42"}',
        output_json: null,
        llm_input: null,
        llm_output: null,
        input_tokens: null,
        output_tokens: null,
        model_id: null,
        children: [],
      },
    ],
    root_spans: [],
    total_spans: 3,
    tool_calls: 3,
    failed_calls: 1,
    duration_ms: 118,
  };
}

describe("buildSessionGraph", () => {
  test("marks repeated identical calls as expandable and highlights the repeat", () => {
    const graph = buildSessionGraph(makeRepeatedTrace(), new Set(), new Set());

    const serverNode = graph.nodes.find((node) => node.id === "server:postgres-mcp");
    expect(serverNode).toBeDefined();
    expect(serverNode?.expandableEdgeId).toBe("agent:support-agent→server:postgres-mcp");
    expect(serverNode?.expandItemCount).toBe(3);
    expect(serverNode?.repeatCallName).toBe("query");
    expect(serverNode?.repeatCallCount).toBe(3);

    const edge = graph.edges.find(
      (item) =>
        item.source === "agent:support-agent" &&
        item.target === "server:postgres-mcp",
    );
    expect(edge?.label).toBe("3×");
  });

  test("expands identical repeated calls into distinct per-call nodes", () => {
    const graph = buildSessionGraph(
      makeRepeatedTrace(),
      new Set(),
      new Set(["agent:support-agent→server:postgres-mcp"]),
    );

    const callNodes = graph.nodes
      .filter((node) => node.id.startsWith("server:postgres-mcp::call:"))
      .map((node) => node.label);

    expect(callNodes).toEqual(["query #1", "query #2", "query #3"]);
  });
});
