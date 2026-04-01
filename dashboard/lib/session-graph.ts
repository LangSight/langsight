import type { GraphEdge, GraphNode } from "@/components/lineage-graph";
import type { PathMetrics, ServerCallerInfo, SessionTrace, SpanNode } from "@/lib/types";

export interface SessionGraphResult {
  nodes: GraphNode[];
  edges: GraphEdge[];
  serverCallers: Map<string, ServerCallerInfo[]>;
  edgeMetrics: Map<string, PathMetrics>;
  edgeSpans: Map<string, SpanNode[]>;
}

interface RepeatInfo {
  repeatCallName?: string;
  repeatCallCount?: number;
}

function normalizeInput(value: string | null): string {
  if (value == null) return "null";
  try {
    return JSON.stringify(JSON.parse(value));
  } catch {
    return value;
  }
}

function findRepeatedCall(spans: SpanNode[]): RepeatInfo {
  const counts = new Map<string, { toolName: string; count: number }>();

  for (const span of spans) {
    const key = `${span.tool_name}\u241f${normalizeInput(span.input_json)}`;
    const entry = counts.get(key);
    if (entry) {
      entry.count += 1;
    } else {
      counts.set(key, { toolName: span.tool_name, count: 1 });
    }
  }

  let best: { toolName: string; count: number } | null = null;
  for (const entry of counts.values()) {
    if (entry.count < 2) continue;
    if (!best || entry.count > best.count) best = entry;
  }

  return best
    ? { repeatCallName: best.toolName, repeatCallCount: best.count }
    : {};
}

function buildCallLabels(spans: SpanNode[]): string[] {
  const totals = new Map<string, number>();
  const seen = new Map<string, number>();

  for (const span of spans) {
    totals.set(span.tool_name, (totals.get(span.tool_name) ?? 0) + 1);
  }

  return spans.map((span) => {
    const total = totals.get(span.tool_name) ?? 1;
    if (total < 2) return span.tool_name;

    const next = (seen.get(span.tool_name) ?? 0) + 1;
    seen.set(span.tool_name, next);
    return `${span.tool_name} #${next}`;
  });
}

export function buildSessionGraph(
  trace: SessionTrace | null,
  expandedGroups: Set<string>,
  expandedEdges: Set<string>,
): SessionGraphResult {
  const empty: SessionGraphResult = {
    nodes: [],
    edges: [],
    serverCallers: new Map(),
    edgeMetrics: new Map(),
    edgeSpans: new Map(),
  };
  if (!trace) return empty;

  const pathData = new Map<string, { agentName: string; serverName: string; spans: SpanNode[] }>();
  const agents = new Set<string>();
  const servers = new Set<string>();
  const handoffs: { source: string; target: string; count: number; parentToolSpanId?: string }[] = [];
  const handoffMap = new Map<string, number>();
  // Track which tool span triggered each delegation (for tool→agent edges)
  const delegationToolSpan = new Map<string, string>(); // "fromAgent→toAgent" → parent span_id
  const agentErrors = new Set<string>();

  // Build span lookup first — needed for LLM intent detection and delegation
  const spanById = new Map(trace.spans_flat.map((s) => [s.span_id, s]));

  // Identify LLM intent spans — these are NOT actual MCP server executions.
  // Protocol v1.0: use explicit span_type="llm_intent".
  // Legacy fallback: tool_call spans whose parent is an "agent" span.
  const llmIntentSpanIds = new Set<string>();
  for (const span of trace.spans_flat) {
    if (span.span_type === "llm_intent") {
      llmIntentSpanIds.add(span.span_id);
    } else if (span.span_type === "tool_call" && span.parent_span_id) {
      // Legacy heuristic for old data without llm_intent span type
      const parent = spanById.get(span.parent_span_id);
      if (parent?.span_type === "agent") {
        llmIntentSpanIds.add(span.span_id);
      }
    }
  }

  for (const span of trace.spans_flat) {
    const agent = span.agent_name ?? "unknown";
    if (span.agent_name) agents.add(agent);

    if (span.span_type === "handoff" && span.tool_name) {
      // Protocol v1.0: use target_agent_name if available, else parse tool_name
      const target = span.target_agent_name
        || span.tool_name.replace(/^->\s*/, "").replace(/^→\s*/, "");
      if (target) {
        agents.add(target);
        const hKey = `${agent}→${target}`;
        handoffMap.set(hKey, (handoffMap.get(hKey) ?? 0) + 1);
      }
    } else if (span.span_type === "agent" && span.status !== "success") {
      // LLM generation span failed (e.g. Gemini 503, safety filter) — mark agent as errored
      agentErrors.add(agent);
    } else if (span.span_type === "tool_call" && span.server_name) {
      // Skip LLM intent spans — they are NOT real MCP server calls
      if (llmIntentSpanIds.has(span.span_id)) continue;

      const server = span.server_name;
      servers.add(server);
      if (span.status !== "success") agentErrors.add(agent);
      const pathKey = `agent:${agent}→server:${server}`;
      if (!pathData.has(pathKey)) {
        pathData.set(pathKey, { agentName: agent, serverName: server, spans: [] });
      }
      pathData.get(pathKey)?.spans.push(span);
    }
  }

  // NOTE: cross-agent parent→child inference removed — it inflated handoff counts
  // when a shared bridge/proxy emits tool_call spans with agent_name=orchestrator
  // but parent=analyst's llm_intent span.  Only explicit handoff spans (above)
  // and llm_intent tool-name patterns (below) should create handoff edges.

  // Infer delegation from tool name patterns: if an LLM intent span is named
  // "call_X" or "delegate_X" and an agent named "X" exists in this session,
  // treat it as a delegation from the calling agent to agent X.
  for (const spanId of llmIntentSpanIds) {
    const span = spanById.get(spanId);
    if (!span) continue;
    const callerAgent = span.agent_name;
    if (!callerAgent) continue;

    const toolName = span.tool_name;
    // Match patterns: call_analyst, delegate_procurement, invoke_researcher
    const match = toolName.match(/^(?:call|delegate|invoke|run)_(.+)$/);
    if (!match) continue;
    const targetAgent = match[1];

    // Only infer if the target agent actually exists in this session
    if (!agents.has(targetAgent)) continue;

    const hKey = `${callerAgent}→${targetAgent}`;
    if (!handoffMap.has(hKey)) {
      handoffMap.set(hKey, 1);
    }
  }

  // Infer delegation by timing: if an agent has no incoming handoff edge,
  // find the agent whose last span ended closest before this agent's first
  // span started. This catches implicit delegations in application code
  // (e.g., main.py calls analyst.analyze() inside call_procurement handler).
  if (agents.size >= 2) {
    const agentsWithIncoming = new Set<string>();
    for (const key of handoffMap.keys()) {
      const tgt = key.split("→")[1];
      agentsWithIncoming.add(tgt);
    }

    // Build first-span-time per agent
    const agentFirstTime = new Map<string, number>();
    for (const span of trace.spans_flat) {
      if (!span.agent_name || !agents.has(span.agent_name)) continue;
      const t = new Date(span.started_at).getTime();
      const cur = agentFirstTime.get(span.agent_name);
      if (cur === undefined || t < cur) agentFirstTime.set(span.agent_name, t);
    }

    // Sort agents by first appearance
    const sortedAgents = [...agents].sort(
      (a, b) => (agentFirstTime.get(a) ?? 0) - (agentFirstTime.get(b) ?? 0),
    );

    for (const agent of sortedAgents) {
      if (agentsWithIncoming.has(agent)) continue;
      // Find the agent that appeared most recently before this one
      const myStart = agentFirstTime.get(agent) ?? 0;
      let bestParent: string | null = null;
      let bestTime = -Infinity;
      for (const other of sortedAgents) {
        if (other === agent) continue;
        const otherStart = agentFirstTime.get(other) ?? 0;
        if (otherStart < myStart && otherStart > bestTime) {
          bestTime = otherStart;
          bestParent = other;
        }
      }
      if (bestParent) {
        const hKey = `${bestParent}→${agent}`;
        if (!handoffMap.has(hKey)) {
          handoffMap.set(hKey, 1);
        }
      }
    }
  }

  for (const [key, count] of handoffMap) {
    const [src, tgt] = key.split("→");
    handoffs.push({ source: src, target: tgt, count, parentToolSpanId: delegationToolSpan.get(key) });
  }

  const edgeMetrics = new Map<string, PathMetrics>();
  const edgeSpans = new Map<string, SpanNode[]>();

  for (const [pathKey, data] of pathData) {
    const spans = data.spans;
    const callCount = spans.length;
    const errorCount = spans.filter((s) => s.status !== "success").length;
    const avgLatencyMs = callCount > 0
      ? spans.reduce((sum, s) => sum + (s.latency_ms ?? 0), 0) / callCount
      : 0;
    const maxLatencyMs = spans.reduce((max, s) => Math.max(max, s.latency_ms ?? 0), 0);
    const tools = [...new Set(spans.map((s) => s.tool_name))];
    const inputTokens = spans.reduce((sum, span) => sum + (span.input_tokens ?? 0), 0);
    const outputTokens = spans.reduce((sum, span) => sum + (span.output_tokens ?? 0), 0);
    const models = [...new Set(spans.map((s) => s.model_id).filter(Boolean))] as string[];

    edgeMetrics.set(pathKey, {
      callCount,
      errorCount,
      avgLatencyMs,
      maxLatencyMs,
      tools,
      inputTokens,
      outputTokens,
      models,
      ...findRepeatedCall(spans),
    });
    edgeSpans.set(pathKey, spans);
  }

  const serverCallers = new Map<string, ServerCallerInfo[]>();
  for (const server of servers) {
    const callers: ServerCallerInfo[] = [];
    for (const [pathKey, data] of pathData) {
      if (data.serverName === server) {
        callers.push({
          agentId: `agent:${data.agentName}`,
          agentLabel: data.agentName,
          metrics: edgeMetrics.get(pathKey)!,
        });
      }
    }
    serverCallers.set(server, callers);
  }

  const nodes: GraphNode[] = [];
  const graphEdges: GraphEdge[] = [];

  for (const agent of agents) {
    // Real MCP tool calls (not LLM intent spans)
    const agentToolSpans = trace.spans_flat.filter(
      (span) =>
        span.agent_name === agent &&
        span.span_type === "tool_call" &&
        !llmIntentSpanIds.has(span.span_id),
    );
    // LLM generation spans (agent type) — used for stats when no direct MCP calls
    const agentLlmSpans = trace.spans_flat.filter(
      (span) => span.agent_name === agent && span.span_type === "agent",
    );

    // Show MCP call count if any, otherwise show LLM call count
    const hasDirectCalls = agentToolSpans.length > 0;
    const countSpans = hasDirectCalls ? agentToolSpans : agentLlmSpans;
    const callCount = countSpans.length;
    const errorCount = countSpans.filter((span) => span.status !== "success").length;
    const avgLatencyMs = callCount > 0
      ? countSpans.reduce((sum, span) => sum + (span.latency_ms ?? 0), 0) / callCount
      : 0;

    nodes.push({
      id: `agent:${agent}`,
      type: "agent",
      label: agent,
      hasError: agentErrors.has(agent),
      callCount,
      errorCount,
      avgLatencyMs,
    });
  }

  function addCallSplitNodes(
    sourceId: string,
    server: string,
    pathKey: string,
    spans: SpanNode[],
  ) {
    const labels = buildCallLabels(spans);

    for (let i = 0; i < spans.length; i++) {
      const span = spans[i];
      const callNodeId = `server:${server}::call:${span.span_id ?? `${span.tool_name}-${i}`}`;
      const latency = span.latency_ms ?? 0;
      const hasErr = span.status !== "success";

      nodes.push({
        id: callNodeId,
        type: "server",
        label: labels[i],
        hasError: hasErr,
        callCount: 1,
        errorCount: hasErr ? 1 : 0,
        avgLatencyMs: latency,
        groupId: pathKey,
        splitLabel: server,
        spanId: span.span_id,
      });

      const callPathKey = `${sourceId}→${callNodeId}`;
      edgeMetrics.set(callPathKey, {
        callCount: 1,
        errorCount: hasErr ? 1 : 0,
        avgLatencyMs: latency,
        maxLatencyMs: latency,
        tools: [span.tool_name],
        inputTokens: span.input_tokens ?? 0,
        outputTokens: span.output_tokens ?? 0,
        models: span.model_id ? [span.model_id] : [],
      });
      edgeSpans.set(callPathKey, [span]);

      graphEdges.push({
        source: sourceId,
        target: callNodeId,
        type: "calls",
        edgeId: pathKey,
        errorCount: hasErr ? 1 : 0,
        avgLatencyMs: latency,
      });
    }
  }

  for (const server of servers) {
    const callers = serverCallers.get(server) ?? [];
    const isMultiCaller = callers.length >= 2;
    const isAgentExpanded = expandedGroups.has(`server:${server}`);

    if (!isMultiCaller || !isAgentExpanded) {
      const allSpans = [...pathData.entries()]
        .filter(([, data]) => data.serverName === server)
        .flatMap(([, data]) => data.spans);
      const callCount = allSpans.length;
      const errorCount = allSpans.filter((span) => span.status !== "success").length;
      const avgLatencyMs = callCount > 0
        ? allSpans.reduce((sum, span) => sum + (span.latency_ms ?? 0), 0) / callCount
        : 0;

      const singleCaller = callers.length === 1 ? callers[0] : null;
      const singlePathKey = singleCaller ? `${singleCaller.agentId}→server:${server}` : null;
      const singlePm = singlePathKey ? edgeMetrics.get(singlePathKey) : null;

      nodes.push({
        id: `server:${server}`,
        type: "server",
        label: server,
        hasError: errorCount > 0,
        callCount,
        errorCount,
        avgLatencyMs,
        isCollapsible: isMultiCaller,
        collapsedCount: isMultiCaller ? callers.length : undefined,
        expandableEdgeId: singlePathKey && singlePm && singlePm.callCount >= 1 ? singlePathKey : undefined,
        expandItemCount: singlePm?.callCount,
        toolNames: singlePm?.tools,
        repeatCallName: singlePm?.repeatCallName,
        repeatCallCount: singlePm?.repeatCallCount,
      });

      for (const caller of callers) {
        const pathKey = `${caller.agentId}→server:${server}`;
        const metrics = edgeMetrics.get(pathKey);
        const isEdgeExpanded = expandedEdges.has(pathKey);
        const hasMultipleCalls = (metrics?.callCount ?? 0) >= 1;

        graphEdges.push({
          source: caller.agentId,
          target: `server:${server}`,
          type: "calls",
          label: metrics && metrics.callCount > 1 ? `${metrics.callCount}×` : undefined,
          edgeId: pathKey,
          errorCount: metrics?.errorCount,
          avgLatencyMs: metrics?.avgLatencyMs,
        });

        if (isEdgeExpanded && hasMultipleCalls) {
          addCallSplitNodes(`server:${server}`, server, pathKey, edgeSpans.get(pathKey) ?? []);
        }
      }
    } else {
      let firstSplitId: string | null = null;
      for (const caller of callers) {
        const pathKey = `${caller.agentId}→server:${server}`;
        const metrics = edgeMetrics.get(pathKey)!;
        const isEdgeExpanded = expandedEdges.has(pathKey);
        const hasMultipleCalls = metrics.callCount >= 2;

        if (isEdgeExpanded && hasMultipleCalls) {
          addCallSplitNodes(caller.agentId, server, pathKey, edgeSpans.get(pathKey) ?? []);
        } else {
          const splitId = `server:${server}::via:${caller.agentLabel}`;
          if (!firstSplitId) firstSplitId = splitId;

          nodes.push({
            id: splitId,
            type: "server",
            label: server,
            hasError: metrics.errorCount > 0,
            callCount: metrics.callCount,
            errorCount: metrics.errorCount,
            avgLatencyMs: metrics.avgLatencyMs,
            groupId: `server:${server}`,
            splitLabel: `via ${caller.agentLabel}`,
            isCollapsible: splitId === firstSplitId,
            collapsedCount: splitId === firstSplitId ? callers.length : undefined,
            expandableEdgeId: hasMultipleCalls ? pathKey : undefined,
            expandItemCount: metrics.callCount,
            toolNames: metrics.tools,
            repeatCallName: metrics.repeatCallName,
            repeatCallCount: metrics.repeatCallCount,
          });

          graphEdges.push({
            source: caller.agentId,
            target: splitId,
            type: "calls",
            label: metrics.callCount > 1 ? `${metrics.callCount}×` : undefined,
            edgeId: pathKey,
            errorCount: metrics.errorCount,
            avgLatencyMs: metrics.avgLatencyMs,
          });
        }
      }
    }
  }

  for (const handoff of handoffs) {
    // If we know the specific tool span that triggered the delegation,
    // draw the edge from the tool call node (e.g. call_analyst) → agent node.
    // This shows: supervisor → direct-tools → call_analyst → analyst
    // instead of: supervisor ──dashed──→ analyst
    let source = `agent:${handoff.source}`;
    if (handoff.parentToolSpanId) {
      const toolNode = nodes.find((n) => n.spanId === handoff.parentToolSpanId);
      if (toolNode) source = toolNode.id;
    }
    graphEdges.push({
      source,
      target: `agent:${handoff.target}`,
      type: "handoff",
      edgeId: `agent:${handoff.source}→h→agent:${handoff.target}`,
      label: handoff.count > 1 ? `${handoff.count} handoffs` : undefined,
    });
  }

  return { nodes, edges: graphEdges, serverCallers, edgeMetrics, edgeSpans };
}
