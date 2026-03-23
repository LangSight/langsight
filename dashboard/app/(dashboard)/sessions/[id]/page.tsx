"use client";

export const dynamic = "force-dynamic";

import { useState, useEffect, useMemo, useCallback, useRef } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import useSWR from "swr";
import {
  ChevronRight, ChevronDown, GitBranch, Clock, Zap, AlertCircle,
  Search, GitCompare, Play, ArrowLeft, Columns2, Bot, Server,
  Maximize2, Minimize2,
} from "lucide-react";
import { LineageGraph, type GraphNode, type GraphEdge, type GraphSelection } from "@/components/lineage-graph";
import { PayloadSlideout } from "@/components/payload-slideout";
import { SessionTimeline } from "@/components/session-timeline";
import { fetcher, getSessionTrace, compareSessions, replaySession } from "@/lib/api";
import { useProject } from "@/lib/project-context";
import { cn, timeAgo, formatDuration, CALL_STATUS_COLOR, SPAN_TYPE_ICON } from "@/lib/utils";
import type { AgentSession, SessionTrace, SpanNode, SessionComparison, DiffEntry, PathMetrics, ServerCallerInfo } from "@/lib/types";

/* ── Build session graph from trace spans (with per-path attribution) ── */

interface SessionGraphResult {
  nodes: GraphNode[];
  edges: GraphEdge[];
  serverCallers: Map<string, ServerCallerInfo[]>;
  edgeMetrics: Map<string, PathMetrics>;
  edgeSpans: Map<string, SpanNode[]>;
}

function useSessionGraph(
  trace: SessionTrace | null,
  expandedGroups: Set<string>,
  expandedEdges: Set<string>,
): SessionGraphResult {
  return useMemo(() => {
    const empty: SessionGraphResult = {
      nodes: [], edges: [],
      serverCallers: new Map(), edgeMetrics: new Map(), edgeSpans: new Map(),
    };
    if (!trace) return empty;

    // Step 1: collect per-path spans
    const pathData = new Map<string, { agentName: string; serverName: string; spans: SpanNode[] }>();
    const agents = new Set<string>();
    const servers = new Set<string>();
    const handoffs: { source: string; target: string; count: number }[] = [];
    const handoffMap = new Map<string, number>();
    const agentErrors = new Set<string>();

    for (const span of trace.spans_flat) {
      const agent = span.agent_name ?? "unknown";
      if (span.agent_name) agents.add(agent);

      if (span.span_type === "handoff" && span.tool_name) {
        const target = span.tool_name.replace(/^->\s*/, "").replace(/^→\s*/, "");
        if (target) {
          agents.add(target);
          const hKey = `${agent}→${target}`;
          handoffMap.set(hKey, (handoffMap.get(hKey) ?? 0) + 1);
        }
      } else if (span.span_type === "tool_call" && span.server_name) {
        const server = span.server_name;
        servers.add(server);
        if (span.status !== "success") agentErrors.add(agent);
        const pathKey = `agent:${agent}→server:${server}`;
        if (!pathData.has(pathKey)) {
          pathData.set(pathKey, { agentName: agent, serverName: server, spans: [] });
        }
        pathData.get(pathKey)!.spans.push(span);
      }
    }

    for (const [key, count] of handoffMap) {
      const [src, tgt] = key.split("→");
      handoffs.push({ source: src, target: tgt, count });
    }

    // Step 2: compute per-path metrics
    const edgeMetrics = new Map<string, PathMetrics>();
    const edgeSpans = new Map<string, SpanNode[]>();

    for (const [pathKey, data] of pathData) {
      const spans = data.spans;
      const callCount = spans.length;
      const errorCount = spans.filter((s) => s.status !== "success").length;
      const avgLatencyMs = callCount > 0
        ? spans.reduce((sum, s) => sum + (s.latency_ms ?? 0), 0) / callCount : 0;
      const maxLatencyMs = spans.reduce((max, s) => Math.max(max, s.latency_ms ?? 0), 0);
      const tools = [...new Set(spans.map((s) => s.tool_name))];
      const inputTokens = spans.reduce((s, sp) => s + (sp.input_tokens ?? 0), 0);
      const outputTokens = spans.reduce((s, sp) => s + (sp.output_tokens ?? 0), 0);
      const models = [...new Set(spans.map((s) => s.model_id).filter(Boolean))] as string[];

      edgeMetrics.set(pathKey, { callCount, errorCount, avgLatencyMs, maxLatencyMs, tools, inputTokens, outputTokens, models });
      edgeSpans.set(pathKey, spans);
    }

    // Step 3: build serverCallers map
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

    // Step 4: build nodes + edges
    const nodes: GraphNode[] = [];
    const graphEdges: GraphEdge[] = [];

    // Agent nodes
    for (const agent of agents) {
      const agentToolSpans = trace.spans_flat.filter(
        (s) => s.agent_name === agent && s.span_type === "tool_call",
      );
      const callCount = agentToolSpans.length;
      const errorCount = agentToolSpans.filter((s) => s.status !== "success").length;
      const avgLatencyMs = callCount > 0
        ? agentToolSpans.reduce((sum, s) => sum + (s.latency_ms ?? 0), 0) / callCount : 0;

      nodes.push({
        id: `agent:${agent}`, type: "agent", label: agent,
        hasError: agentErrors.has(agent),
        callCount, errorCount, avgLatencyMs,
      });
    }

    // Helper: create one node per individual call for an edge
    function addToolSplitNodes(
      sourceId: string, server: string, agentLabel: string,
      pathKey: string, spans: SpanNode[],
    ) {
      for (let i = 0; i < spans.length; i++) {
        const s = spans[i];
        const tool = s.tool_name;
        const callNodeId = `server:${server}::call:${s.span_id ?? `${tool}-${i}`}`;
        const latency = s.latency_ms ?? 0;
        const hasErr = s.status !== "success";

        nodes.push({
          id: callNodeId, type: "server", label: tool,
          hasError: hasErr,
          callCount: 1, errorCount: hasErr ? 1 : 0, avgLatencyMs: latency,
          groupId: pathKey,
          splitLabel: server,
        });

        const callPathKey = `${sourceId}→${callNodeId}`;
        edgeMetrics.set(callPathKey, {
          callCount: 1, errorCount: hasErr ? 1 : 0, avgLatencyMs: latency,
          maxLatencyMs: latency,
          tools: [tool],
          inputTokens: s.input_tokens ?? 0,
          outputTokens: s.output_tokens ?? 0,
          models: s.model_id ? [s.model_id] : [],
        });
        edgeSpans.set(callPathKey, [s]);

        graphEdges.push({
          source: sourceId, target: callNodeId, type: "calls",
          edgeId: pathKey, errorCount: hasErr ? 1 : 0, avgLatencyMs: latency,
        });
      }
    }

    // Server nodes — with per-agent and per-tool expansion
    for (const server of servers) {
      const callers = serverCallers.get(server) ?? [];
      const isMultiCaller = callers.length >= 2;
      const isAgentExpanded = expandedGroups.has(`server:${server}`);

      if (!isMultiCaller || !isAgentExpanded) {
        // Collapsed or single-caller — ALWAYS add the server node
        const allSpans = [...pathData.entries()]
          .filter(([, d]) => d.serverName === server)
          .flatMap(([, d]) => d.spans);
        const callCount = allSpans.length;
        const errorCount = allSpans.filter((s) => s.status !== "success").length;
        const avgLatencyMs = callCount > 0
          ? allSpans.reduce((sum, s) => sum + (s.latency_ms ?? 0), 0) / callCount : 0;

        const singleCaller = callers.length === 1 ? callers[0] : null;
        const singlePathKey = singleCaller ? `${singleCaller.agentId}→server:${server}` : null;
        const singlePm = singlePathKey ? edgeMetrics.get(singlePathKey) : null;

        nodes.push({
          id: `server:${server}`, type: "server", label: server,
          hasError: errorCount > 0,
          callCount, errorCount, avgLatencyMs,
          isCollapsible: isMultiCaller,
          collapsedCount: isMultiCaller ? callers.length : undefined,
          expandableEdgeId: singlePathKey && singlePm && singlePm.tools.length >= 2 ? singlePathKey : undefined,
          toolNames: singlePm && singlePm.tools.length >= 2 ? singlePm.tools : undefined,
        });

        // Agent → server edge (always present)
        for (const caller of callers) {
          const pathKey = `${caller.agentId}→server:${server}`;
          const pm = edgeMetrics.get(pathKey);
          const isEdgeExpanded = expandedEdges.has(pathKey);
          const hasMultipleTools = pm && pm.tools.length >= 2;

          graphEdges.push({
            source: caller.agentId, target: `server:${server}`, type: "calls",
            label: pm && pm.callCount > 1 ? `${pm.callCount}×` : undefined,
            edgeId: pathKey, errorCount: pm?.errorCount, avgLatencyMs: pm?.avgLatencyMs,
          });

          // Per-tool expansion: tool nodes fan out FROM the server node
          if (isEdgeExpanded && hasMultipleTools) {
            addToolSplitNodes(`server:${server}`, server, caller.agentLabel, pathKey, edgeSpans.get(pathKey) ?? []);
          }
        }
      } else {
        // Expanded per-agent: one split node per caller
        let firstSplitId: string | null = null;
        for (const caller of callers) {
          const pathKey = `${caller.agentId}→server:${server}`;
          const pm = edgeMetrics.get(pathKey)!;
          const isEdgeExpanded = expandedEdges.has(pathKey);
          const hasMultipleTools = pm.tools.length >= 2;

          if (isEdgeExpanded && hasMultipleTools) {
            addToolSplitNodes(caller.agentId, server, caller.agentLabel, pathKey, edgeSpans.get(pathKey) ?? []);
          } else {
            const splitId = `server:${server}::via:${caller.agentLabel}`;
            if (!firstSplitId) firstSplitId = splitId;

            nodes.push({
              id: splitId, type: "server", label: server,
              hasError: pm.errorCount > 0,
              callCount: pm.callCount, errorCount: pm.errorCount, avgLatencyMs: pm.avgLatencyMs,
              groupId: `server:${server}`,
              splitLabel: `via ${caller.agentLabel}`,
              isCollapsible: splitId === firstSplitId,
              collapsedCount: splitId === firstSplitId ? callers.length : undefined,
              expandableEdgeId: hasMultipleTools ? pathKey : undefined,
              toolNames: hasMultipleTools ? pm.tools : undefined,
            });

            graphEdges.push({
              source: caller.agentId, target: splitId, type: "calls",
              label: pm.callCount > 1 ? `${pm.callCount}×` : undefined,
              edgeId: pathKey, errorCount: pm.errorCount, avgLatencyMs: pm.avgLatencyMs,
            });
          }
        }
      }
    }

    // Handoff edges
    for (const h of handoffs) {
      graphEdges.push({
        source: `agent:${h.source}`, target: `agent:${h.target}`, type: "handoff",
        edgeId: `agent:${h.source}→h→agent:${h.target}`,
        label: h.count > 1 ? `${h.count} handoffs` : undefined,
      });
    }

    return { nodes, edges: graphEdges, serverCallers, edgeMetrics, edgeSpans };
  }, [trace, expandedGroups, expandedEdges]);
}

/* ── Right panel: node detail for session ──────────────────── */

function SectionLabel({ children }: { children: React.ReactNode }) {
  return <p className="text-[11px] font-semibold text-muted-foreground uppercase tracking-widest mb-3">{children}</p>;
}

function MetricTile({ label, value, mono = true }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="rounded-lg p-3" style={{ background: "hsl(var(--muted))" }}>
      <p className="text-[11px] text-muted-foreground mb-0.5">{label}</p>
      <p className={cn("text-[15px] font-bold text-foreground", mono && "font-mono")} style={mono ? { fontFamily: "var(--font-geist-mono)" } : {}}>{value}</p>
    </div>
  );
}

function SessionNodeDetail({ nodeId, trace, serverCallers }: { nodeId: string; trace: SessionTrace; serverCallers: Map<string, ServerCallerInfo[]> }) {
  const isAgent = nodeId.startsWith("agent:");
  const isPerCall = nodeId.includes("::call:");
  const name = nodeId.replace(/^(agent|server):/, "").replace(/::call:.*$/, "");

  // For per-call nodes, find the exact span by span_id
  const callSpanId = isPerCall ? nodeId.replace(/^.*::call:/, "") : null;

  const spans = isPerCall
    ? trace.spans_flat.filter((s: SpanNode) => s.span_id === callSpanId)
    : trace.spans_flat.filter((s: SpanNode) =>
        isAgent ? s.agent_name === name : (s.server_name === name && s.span_type === "tool_call")
      );

  const totalCalls = spans.length;
  const errors = spans.filter((s: SpanNode) => s.status !== "success").length;
  const avgLatency = totalCalls > 0 ? spans.reduce((sum: number, s: SpanNode) => sum + (s.latency_ms ?? 0), 0) / totalCalls : 0;
  const maxLatency = spans.reduce((max: number, s: SpanNode) => Math.max(max, s.latency_ms ?? 0), 0);
  const tools = [...new Set(spans.map((s: SpanNode) => s.tool_name))];
  const errorRate = totalCalls > 0 ? (errors / totalCalls) * 100 : 0;
  const totalInputTokens = spans.reduce((s: number, sp: SpanNode) => s + (sp.input_tokens ?? 0), 0);
  const totalOutputTokens = spans.reduce((s: number, sp: SpanNode) => s + (sp.output_tokens ?? 0), 0);
  const models = [...new Set(spans.map((s: SpanNode) => s.model_id).filter(Boolean))];

  return (
    <div className="h-full overflow-y-auto">
      {/* Header */}
      <div className="px-5 pt-5 pb-4 border-b" style={{ borderColor: "hsl(var(--border))" }}>
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0" style={{ background: "hsl(var(--primary) / 0.08)" }}>
            {isAgent ? <Bot size={18} style={{ color: "hsl(var(--primary))" }} /> : <Server size={18} className="text-muted-foreground" />}
          </div>
          <div className="min-w-0">
            <p className="text-[15px] font-semibold text-foreground truncate">{isPerCall && spans[0] ? spans[0].tool_name : name}</p>
            <div className="flex items-center gap-2 mt-0.5">
              <span className="text-[12px] text-muted-foreground">{isPerCall ? `${name} · Tool Call` : isAgent ? "Agent" : "MCP Server"}</span>
              <span className={cn("w-1.5 h-1.5 rounded-full", errors > 0 ? "bg-red-500" : "bg-emerald-500")} />
              <span className="text-[12px]" style={{ color: errors > 0 ? "#ef4444" : "#10b981" }}>
                {errors > 0 ? `${errors} error${errors > 1 ? "s" : ""}` : "All OK"}
              </span>
            </div>
            {!isPerCall && (
              <Link
                href={isAgent ? `/agents` : `/servers`}
                className="mt-1 inline-flex items-center gap-1 text-[11px] text-primary hover:underline"
              >
                View in {isAgent ? "Agent" : "Server"} Catalog →
              </Link>
            )}
          </div>
        </div>
      </div>

      {/* Overview metrics */}
      <div className="px-5 py-5">
        <SectionLabel>Overview</SectionLabel>
        <div className="grid grid-cols-2 gap-2">
          <MetricTile label="Total Calls" value={totalCalls.toLocaleString()} />
          <MetricTile label="Errors" value={errors.toLocaleString()} />
          <MetricTile label="Avg Latency" value={`${Math.round(avgLatency)}ms`} />
          <MetricTile label="Max Latency" value={`${Math.round(maxLatency)}ms`} />
        </div>
        {errorRate > 0 && (
          <div className="mt-2 rounded-lg px-3 py-2 flex items-center justify-between" style={{ background: "rgba(239,68,68,0.06)", borderLeft: "3px solid hsl(var(--danger))" }}>
            <span className="text-[11px] text-muted-foreground">Error Rate</span>
            <span className="text-[12px] font-bold" style={{ color: "#ef4444", fontFamily: "var(--font-geist-mono)" }}>{errorRate.toFixed(1)}%</span>
          </div>
        )}
      </div>

      {/* Tools */}
      {tools.length > 0 && (
        <div className="px-5 py-4 border-t" style={{ borderColor: "hsl(var(--border))" }}>
          <SectionLabel>Tools ({tools.length})</SectionLabel>
          <div className="space-y-1">
            {tools.map((tool) => {
              const toolSpans = spans.filter((s: SpanNode) => s.tool_name === tool);
              const toolErrors = toolSpans.filter((s: SpanNode) => s.status !== "success").length;
              const toolAvgMs = toolSpans.reduce((s: number, sp: SpanNode) => s + (sp.latency_ms ?? 0), 0) / toolSpans.length;
              return (
                <div key={tool} className="flex items-center justify-between rounded-lg px-3 py-2.5" style={{ background: "hsl(var(--muted))" }}>
                  <div className="flex items-center gap-2">
                    <span className={cn("w-1.5 h-1.5 rounded-full", toolErrors > 0 ? "bg-red-500" : "bg-emerald-500")} />
                    <span className="text-[12px] font-medium text-foreground">{tool}</span>
                  </div>
                  <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
                    <span className="font-mono" style={{ fontFamily: "var(--font-geist-mono)" }}>{Math.round(toolAvgMs)}ms</span>
                    <span>{toolSpans.length}×</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Per-agent breakdown (server nodes called by 2+ agents) */}
      {!isAgent && (() => {
        const callers = serverCallers.get(name) ?? [];
        if (callers.length < 2) return null;
        return (
          <div className="px-5 py-4 border-t" style={{ borderColor: "hsl(var(--border))" }}>
            <SectionLabel>By Agent ({callers.length})</SectionLabel>
            <div className="space-y-1.5">
              {callers.map((caller) => (
                <div key={caller.agentId} className="rounded-lg px-3 py-2.5" style={{ background: "hsl(var(--muted))" }}>
                  <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center gap-2">
                      <Bot size={11} style={{ color: "hsl(var(--primary))" }} />
                      <span className="text-[12px] font-medium text-foreground">{caller.agentLabel}</span>
                    </div>
                    {caller.metrics.errorCount > 0 && (
                      <span className="text-[10px]" style={{ color: "#ef4444" }}>{caller.metrics.errorCount} errors</span>
                    )}
                  </div>
                  <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
                    <span style={{ fontFamily: "var(--font-geist-mono)" }}>{caller.metrics.callCount} calls</span>
                    <span style={{ fontFamily: "var(--font-geist-mono)" }}>{Math.round(caller.metrics.avgLatencyMs)}ms avg</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        );
      })()}

      {/* Per-server breakdown (agent nodes calling 2+ servers) */}
      {isAgent && (() => {
        const serverBreakdown: { server: string; metrics: PathMetrics }[] = [];
        for (const [server, callers] of serverCallers) {
          const match = callers.find((c) => c.agentLabel === name);
          if (match) serverBreakdown.push({ server, metrics: match.metrics });
        }
        if (serverBreakdown.length < 2) return null;
        return (
          <div className="px-5 py-4 border-t" style={{ borderColor: "hsl(var(--border))" }}>
            <SectionLabel>By Server ({serverBreakdown.length})</SectionLabel>
            <div className="space-y-1.5">
              {serverBreakdown.map(({ server, metrics }) => (
                <div key={server} className="rounded-lg px-3 py-2.5" style={{ background: "hsl(var(--muted))" }}>
                  <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center gap-2">
                      <Server size={11} className="text-muted-foreground" />
                      <span className="text-[12px] font-medium text-foreground">{server}</span>
                    </div>
                    {metrics.errorCount > 0 && (
                      <span className="text-[10px]" style={{ color: "#ef4444" }}>{metrics.errorCount} errors</span>
                    )}
                  </div>
                  <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
                    <span style={{ fontFamily: "var(--font-geist-mono)" }}>{metrics.callCount} calls</span>
                    <span style={{ fontFamily: "var(--font-geist-mono)" }}>{Math.round(metrics.avgLatencyMs)}ms avg</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        );
      })()}

      {/* Token usage */}
      {totalInputTokens > 0 && (
        <div className="px-5 py-4 border-t" style={{ borderColor: "hsl(var(--border))" }}>
          <SectionLabel>Token Usage</SectionLabel>
          <div className="grid grid-cols-2 gap-2">
            <MetricTile label="Input" value={totalInputTokens.toLocaleString()} />
            <MetricTile label="Output" value={totalOutputTokens.toLocaleString()} />
          </div>
          {models.length > 0 && (
            <div className="mt-2 rounded-lg px-3 py-2 flex items-center gap-2" style={{ background: "hsl(var(--muted))" }}>
              <span className="text-[11px] text-muted-foreground">Model</span>
              {models.map((m) => (
                <code key={m} className="text-[11px] px-1.5 py-0.5 rounded" style={{ background: "hsl(var(--primary) / 0.08)", color: "hsl(var(--primary))", fontFamily: "var(--font-geist-mono)" }}>{m}</code>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Per-call detail: show input/output prominently */}
      {isPerCall && spans[0] && (
        <div className="px-5 py-4 border-t" style={{ borderColor: "hsl(var(--border))" }}>
          {spans[0].input_json && (
            <div className="mb-3">
              <SectionLabel>Input</SectionLabel>
              <pre className="text-[11px] text-foreground rounded-lg p-3 whitespace-pre-wrap break-all max-h-48 overflow-y-auto" style={{ fontFamily: "var(--font-geist-mono)", background: "hsl(var(--muted))", border: "1px solid hsl(var(--border))" }}>
                {(() => { try { return JSON.stringify(JSON.parse(spans[0].input_json!), null, 2); } catch { return spans[0].input_json; } })()}
              </pre>
            </div>
          )}
          {spans[0].output_json && (
            <div className="mb-3">
              <SectionLabel>Output</SectionLabel>
              <pre className="text-[11px] text-foreground rounded-lg p-3 whitespace-pre-wrap break-all max-h-48 overflow-y-auto" style={{ fontFamily: "var(--font-geist-mono)", background: "hsl(var(--muted))", border: "1px solid hsl(var(--border))" }}>
                {(() => { try { return JSON.stringify(JSON.parse(spans[0].output_json!), null, 2); } catch { return spans[0].output_json; } })()}
              </pre>
            </div>
          )}
          {spans[0].error && (
            <div className="mb-3">
              <SectionLabel>Error</SectionLabel>
              <div className="rounded-lg px-3 py-2.5 text-[11px]" style={{ background: "rgba(239,68,68,0.06)", color: "#ef4444", fontFamily: "var(--font-geist-mono)" }}>{spans[0].error}</div>
            </div>
          )}
          {(spans[0].input_tokens || spans[0].output_tokens) && (
            <div>
              <SectionLabel>Tokens</SectionLabel>
              <div className="flex items-center gap-4 text-[11px] text-muted-foreground">
                {spans[0].model_id && <span>Model: <code className="text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>{spans[0].model_id}</code></span>}
                {spans[0].input_tokens != null && <span>In: <strong className="text-foreground">{spans[0].input_tokens}</strong></span>}
                {spans[0].output_tokens != null && <span>Out: <strong className="text-foreground">{spans[0].output_tokens}</strong></span>}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Span timeline — hidden for per-call nodes (already showing the single span above) */}
      {!isPerCall && (
        <div className="px-5 py-4 border-t" style={{ borderColor: "hsl(var(--border))" }}>
          <SectionLabel>Calls ({spans.length})</SectionLabel>
          <div className="space-y-1.5">
            {spans.map((s: SpanNode, i: number) => (
              <details key={i} className="group rounded-lg overflow-hidden" style={{ border: "1px solid hsl(var(--border))" }}>
                <summary className="flex items-center justify-between px-3 py-2 cursor-pointer hover:bg-accent/30 transition-colors list-none">
                  <div className="flex items-center gap-2">
                    <span className={cn("w-1.5 h-1.5 rounded-full", s.status === "success" ? "bg-emerald-500" : "bg-red-500")} />
                    <span className="text-[12px] font-medium text-foreground">{s.tool_name}</span>
                    {s.error && <span className="text-[10px] text-red-400">error</span>}
                  </div>
                  <span className="text-[11px] text-muted-foreground font-mono" style={{ fontFamily: "var(--font-geist-mono)" }}>{Math.round(s.latency_ms ?? 0)}ms</span>
                </summary>
                <div className="px-3 pb-3 space-y-2" style={{ borderTop: "1px solid hsl(var(--border))" }}>
                  {s.error && (
                    <div className="mt-2 rounded-lg px-3 py-2 text-[11px]" style={{ background: "rgba(239,68,68,0.05)", color: "#ef4444" }}>{s.error}</div>
                  )}
                  {s.input_json && (
                    <div className="mt-2">
                      <p className="text-[11px] text-muted-foreground uppercase tracking-widest mb-1">Input</p>
                      <pre className="text-[10px] text-foreground rounded-lg p-2.5 whitespace-pre-wrap break-all max-h-32 overflow-y-auto" style={{ fontFamily: "var(--font-geist-mono)", background: "hsl(var(--muted))" }}>
                        {(() => { try { return JSON.stringify(JSON.parse(s.input_json), null, 2); } catch { return s.input_json; } })()}
                      </pre>
                    </div>
                  )}
                  {s.output_json && (
                    <div>
                      <p className="text-[11px] text-muted-foreground uppercase tracking-widest mb-1">Output</p>
                      <pre className="text-[10px] text-foreground rounded-lg p-2.5 whitespace-pre-wrap break-all max-h-32 overflow-y-auto" style={{ fontFamily: "var(--font-geist-mono)", background: "hsl(var(--muted))" }}>
                        {(() => { try { return JSON.stringify(JSON.parse(s.output_json), null, 2); } catch { return s.output_json; } })()}
                      </pre>
                    </div>
                  )}
                  {(s.input_tokens || s.output_tokens) && (
                    <div className="flex items-center gap-3 text-[10px] text-muted-foreground pt-1">
                      {s.model_id && <span>Model: <code className="text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>{s.model_id}</code></span>}
                      {s.input_tokens != null && <span>In: <strong className="text-foreground">{s.input_tokens}</strong></span>}
                      {s.output_tokens != null && <span>Out: <strong className="text-foreground">{s.output_tokens}</strong></span>}
                    </div>
                  )}
                </div>
              </details>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Edge detail panel ─────────────────────────────────────── */

function SessionEdgeDetail({
  source, target, metrics, spans,
}: {
  source: string;
  target: string;
  metrics: PathMetrics | null;
  spans: SpanNode[];
}) {
  const sourceName = source.replace(/^(agent|server):/, "");
  const targetName = target.replace(/^(agent|server):/, "");

  if (!metrics) {
    return (
      <div className="h-full flex items-center justify-center text-sm text-muted-foreground">
        No data for this edge
      </div>
    );
  }

  const errorRate = metrics.callCount > 0 ? (metrics.errorCount / metrics.callCount) * 100 : 0;

  return (
    <div className="h-full overflow-y-auto">
      {/* Header */}
      <div className="px-5 pt-5 pb-4 border-b" style={{ borderColor: "hsl(var(--border))" }}>
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: "hsl(var(--primary) / 0.08)" }}>
            <Bot size={14} style={{ color: "hsl(var(--primary))" }} />
          </div>
          <span className="text-[12px] font-bold text-foreground">{sourceName}</span>
          <span className="text-[11px] text-muted-foreground">{"\u2192"}</span>
          <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: "rgba(100,116,139,0.08)" }}>
            <Server size={14} className="text-muted-foreground" />
          </div>
          <span className="text-[12px] font-bold text-foreground">{targetName}</span>
        </div>
        <p className="text-[10px] text-muted-foreground mt-1.5">
          Edge — {metrics.callCount} call{metrics.callCount !== 1 ? "s" : ""} on this path
        </p>
      </div>

      {/* Metrics */}
      <div className="px-5 py-4">
        <SectionLabel>Path Metrics</SectionLabel>
        <div className="grid grid-cols-2 gap-2">
          <MetricTile label="Calls" value={metrics.callCount.toLocaleString()} />
          <MetricTile label="Errors" value={metrics.errorCount.toLocaleString()} />
          <MetricTile label="Avg Latency" value={`${Math.round(metrics.avgLatencyMs)}ms`} />
          <MetricTile label="Max Latency" value={`${Math.round(metrics.maxLatencyMs)}ms`} />
        </div>
        {errorRate > 0 && (
          <div className="mt-2 rounded-lg px-3 py-2 flex items-center justify-between" style={{ background: "rgba(239,68,68,0.06)" }}>
            <span className="text-[11px] text-muted-foreground">Error Rate</span>
            <span className="text-[12px] font-bold" style={{ color: "#ef4444", fontFamily: "var(--font-geist-mono)" }}>{errorRate.toFixed(1)}%</span>
          </div>
        )}
      </div>

      {/* Tools on this path */}
      {metrics.tools.length > 0 && (
        <div className="px-5 py-4 border-t" style={{ borderColor: "hsl(var(--border))" }}>
          <SectionLabel>Tools ({metrics.tools.length})</SectionLabel>
          <div className="space-y-1">
            {metrics.tools.map((tool) => {
              const toolSpans = spans.filter((s) => s.tool_name === tool);
              const toolErrors = toolSpans.filter((s) => s.status !== "success").length;
              const toolAvgMs = toolSpans.length > 0
                ? toolSpans.reduce((s, sp) => s + (sp.latency_ms ?? 0), 0) / toolSpans.length : 0;
              return (
                <div key={tool} className="flex items-center justify-between rounded-lg px-3 py-2.5" style={{ background: "hsl(var(--muted))" }}>
                  <div className="flex items-center gap-2">
                    <span className={cn("w-1.5 h-1.5 rounded-full", toolErrors > 0 ? "bg-red-500" : "bg-emerald-500")} />
                    <span className="text-[12px] font-medium text-foreground">{tool}</span>
                  </div>
                  <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
                    <span style={{ fontFamily: "var(--font-geist-mono)" }}>{Math.round(toolAvgMs)}ms</span>
                    <span>{toolSpans.length}×</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Token usage */}
      {metrics.inputTokens > 0 && (
        <div className="px-5 py-4 border-t" style={{ borderColor: "hsl(var(--border))" }}>
          <SectionLabel>Token Usage</SectionLabel>
          <div className="grid grid-cols-2 gap-2">
            <MetricTile label="Input" value={metrics.inputTokens.toLocaleString()} />
            <MetricTile label="Output" value={metrics.outputTokens.toLocaleString()} />
          </div>
          {metrics.models.length > 0 && (
            <div className="mt-2 rounded-lg px-3 py-2 flex items-center gap-2" style={{ background: "hsl(var(--muted))" }}>
              <span className="text-[11px] text-muted-foreground">Model</span>
              {metrics.models.map((m) => (
                <code key={m} className="text-[11px] px-1.5 py-0.5 rounded" style={{ background: "hsl(var(--primary) / 0.08)", color: "hsl(var(--primary))", fontFamily: "var(--font-geist-mono)" }}>{m}</code>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Span timeline */}
      <div className="px-5 py-4 border-t" style={{ borderColor: "hsl(var(--border))" }}>
        <SectionLabel>Calls ({spans.length})</SectionLabel>
        <div className="space-y-1.5">
          {spans.map((s: SpanNode, i: number) => (
            <details key={i} className="group rounded-lg overflow-hidden" style={{ border: "1px solid hsl(var(--border))" }}>
              <summary className="flex items-center justify-between px-3 py-2 cursor-pointer hover:bg-accent/30 transition-colors list-none">
                <div className="flex items-center gap-2">
                  <span className={cn("w-1.5 h-1.5 rounded-full", s.status === "success" ? "bg-emerald-500" : "bg-red-500")} />
                  <span className="text-[12px] font-medium text-foreground">{s.tool_name}</span>
                  {s.error && <span className="text-[10px] text-red-400">error</span>}
                </div>
                <span className="text-[11px] text-muted-foreground font-mono" style={{ fontFamily: "var(--font-geist-mono)" }}>{Math.round(s.latency_ms ?? 0)}ms</span>
              </summary>
              <div className="px-3 pb-3 space-y-2" style={{ borderTop: "1px solid hsl(var(--border))" }}>
                {s.error && (
                  <div className="mt-2 rounded-lg px-3 py-2 text-[11px]" style={{ background: "rgba(239,68,68,0.05)", color: "#ef4444" }}>{s.error}</div>
                )}
                {s.input_json && (
                  <div className="mt-2">
                    <p className="text-[11px] text-muted-foreground uppercase tracking-widest mb-1">Input</p>
                    <pre className="text-[10px] text-foreground rounded-lg p-2.5 whitespace-pre-wrap break-all max-h-32 overflow-y-auto" style={{ fontFamily: "var(--font-geist-mono)", background: "hsl(var(--muted))" }}>
                      {(() => { try { return JSON.stringify(JSON.parse(s.input_json), null, 2); } catch { return s.input_json; } })()}
                    </pre>
                  </div>
                )}
                {s.output_json && (
                  <div>
                    <p className="text-[11px] text-muted-foreground uppercase tracking-widest mb-1">Output</p>
                    <pre className="text-[10px] text-foreground rounded-lg p-2.5 whitespace-pre-wrap break-all max-h-32 overflow-y-auto" style={{ fontFamily: "var(--font-geist-mono)", background: "hsl(var(--muted))" }}>
                      {(() => { try { return JSON.stringify(JSON.parse(s.output_json), null, 2); } catch { return s.output_json; } })()}
                    </pre>
                  </div>
                )}
              </div>
            </details>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ── Payload panel ──────────────────────────────────────────── */
function PayloadPanel({ label, json }: { label: string; json: string | null }) {
  if (!json) return null;
  let formatted = json;
  try { formatted = JSON.stringify(JSON.parse(json), null, 2); } catch { /* keep raw */ }
  return (
    <div className="mt-2">
      <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-widest mb-1">{label}</p>
      <pre
        className="text-[11px] rounded-lg p-3 overflow-x-auto whitespace-pre-wrap break-all leading-relaxed max-h-44 overflow-y-auto"
        style={{
          fontFamily: "var(--font-geist-mono)",
          background: "hsl(var(--muted))",
          color: "hsl(var(--foreground))",
          border: "1px solid hsl(var(--border))",
        }}
      >
        {formatted}
      </pre>
    </div>
  );
}

/* ── Span row ───────────────────────────────────────────────── */
function SpanRow({ span, depth = 0 }: { span: SpanNode; depth?: number }) {
  const [open, setOpen] = useState(true);
  const [detailOpen, setDetailOpen] = useState(false);
  const icon = SPAN_TYPE_ICON[span.span_type] ?? "●";
  const statusColor = CALL_STATUS_COLOR[span.status] ?? "text-zinc-400";
  const hasChildren = span.children && span.children.length > 0;
  const isLlmSpan = span.span_type === "agent" && (span.llm_input || span.llm_output);
  const hasPayload = span.input_json || span.output_json || span.llm_input || span.llm_output || span.error;

  const spanColor =
    span.span_type === "handoff" ? "text-yellow-500"
    : span.span_type === "agent" ? "text-primary"
    : "text-foreground";

  return (
    <>
      <tr
        className={cn(
          "group transition-colors border-b border-border/40",
          hasPayload ? "cursor-pointer hover:bg-accent/40" : "hover:bg-accent/20",
          detailOpen && "bg-accent/20"
        )}
        onClick={() => hasPayload && setDetailOpen((o) => !o)}
      >
        <td className="py-2 pr-3">
          <div className="flex items-center" style={{ paddingLeft: `${depth * 18}px` }}>
            <button
              onClick={(e) => { e.stopPropagation(); hasChildren && setOpen((o) => !o); }}
              className={cn("flex items-center gap-1.5 min-w-0", hasChildren ? "cursor-pointer" : "cursor-default")}
            >
              {hasChildren
                ? open
                  ? <ChevronDown size={11} className="text-muted-foreground flex-shrink-0" />
                  : <ChevronRight size={11} className="text-muted-foreground flex-shrink-0" />
                : <span className="w-3 flex-shrink-0" />}
              <span className="text-xs mr-1">{icon}</span>
              <span className={cn("text-[12px] font-mono truncate", spanColor)} style={{ fontFamily: "var(--font-geist-mono)" }}>
                {span.server_name}/{span.tool_name}
              </span>
            </button>
            {hasPayload && (
              <span className="ml-2 text-[10px] text-muted-foreground opacity-0 group-hover:opacity-60 transition-opacity">
                {detailOpen ? "▲" : "▼"}
              </span>
            )}
          </div>
        </td>
        <td className="py-2 pr-3 text-[12px] text-muted-foreground">{span.agent_name || "—"}</td>
        <td className="py-2 pr-3 text-[12px]">
          <span className={cn("font-mono font-semibold", statusColor)}>
            {span.status === "success" ? "✓" : span.status === "error" ? "✗" : span.status === "prevented" ? "⊘" : "⏱"}
          </span>
        </td>
        <td className="py-2 pr-3 text-[12px] font-mono text-right text-muted-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>
          {span.latency_ms ? `${span.latency_ms.toFixed(0)}ms` : "—"}
        </td>
        <td className="py-2 text-[11px] text-red-500 truncate max-w-xs">{span.error?.slice(0, 60) ?? ""}</td>
      </tr>

      {detailOpen && hasPayload && (
        <tr style={{ background: "hsl(var(--muted) / 0.5)" }}>
          <td colSpan={5} className="px-4 pb-3 pt-1" style={{ paddingLeft: `${depth * 18 + 28}px` }}>
            {isLlmSpan ? (
              <>
                <PayloadPanel label="Prompt" json={span.llm_input ?? null} />
                <PayloadPanel label="Completion" json={span.llm_output ?? null} />
              </>
            ) : (
              <>
                <PayloadPanel label="Input" json={span.input_json ?? null} />
                <PayloadPanel label="Output" json={span.output_json ?? null} />
              </>
            )}
            {span.error && !span.output_json && !span.llm_output && (
              <div className="mt-2">
                <p className="text-[10px] font-semibold uppercase tracking-widest mb-1" style={{ color: "hsl(var(--danger))" }}>Error</p>
                <pre
                  className="text-[11px] rounded-lg p-3 whitespace-pre-wrap break-all"
                  style={{
                    fontFamily: "var(--font-geist-mono)",
                    background: "hsl(var(--danger-bg))",
                    color: "hsl(var(--danger))",
                    border: "1px solid hsl(var(--danger) / 0.2)",
                  }}
                >
                  {span.error}
                </pre>
              </div>
            )}
          </td>
        </tr>
      )}
      {open && span.children?.map((child) => (
        <SpanRow key={child.span_id} span={child} depth={depth + 1} />
      ))}
    </>
  );
}

/* ── Diff row (compare view) ──────────────────────────────────── */
function DiffRow({ entry }: { entry: DiffEntry }) {
  const latStr = (span: Record<string, unknown> | null) =>
    span?.latency_ms != null ? `${Number(span.latency_ms).toFixed(0)}ms` : "—";
  const statusStr = (span: Record<string, unknown> | null) =>
    span ? (span.status === "success" ? "✓" : span.status === "error" ? "✗" : span.status === "prevented" ? "⊘" : "⏱") : "—";
  const deltaColor =
    entry.latency_delta_pct === null ? ""
    : entry.latency_delta_pct > 0 ? "text-red-500" : "text-emerald-500";

  const rowBg =
    entry.status === "matched" ? ""
    : entry.status === "diverged" ? "bg-yellow-500/5"
    : entry.status === "only_a"  ? "bg-blue-500/5"
    : "bg-purple-500/5";

  const statusIcon =
    entry.status === "matched" ? "=" : entry.status === "diverged" ? "≠"
    : entry.status === "only_a" ? "A" : "B";

  const statusColor =
    entry.status === "matched" ? "text-emerald-500"
    : entry.status === "diverged" ? "text-yellow-500"
    : entry.status === "only_a" ? "text-blue-400"
    : "text-purple-400";

  return (
    <tr className={cn("border-b border-border/50 text-[12px]", rowBg)}>
      <td className="px-4 py-2 font-mono truncate max-w-[200px]" style={{ fontFamily: "var(--font-geist-mono)" }}>
        <span className={cn("mr-2 font-bold", statusColor)}>{statusIcon}</span>
        <span className="text-muted-foreground">{entry.tool_key}</span>
      </td>
      <td className="px-4 py-2 text-center font-mono" style={{ fontFamily: "var(--font-geist-mono)" }}>
        <span className={entry.span_a ? (CALL_STATUS_COLOR[entry.span_a.status as keyof typeof CALL_STATUS_COLOR] ?? "") : "text-muted-foreground"}>
          {statusStr(entry.span_a)}
        </span>
      </td>
      <td className="px-4 py-2 text-right font-mono text-muted-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>
        {latStr(entry.span_a)}
      </td>
      <td className="px-4 py-2 text-center font-mono" style={{ fontFamily: "var(--font-geist-mono)" }}>
        <span className={entry.span_b ? (CALL_STATUS_COLOR[entry.span_b.status as keyof typeof CALL_STATUS_COLOR] ?? "") : "text-muted-foreground"}>
          {statusStr(entry.span_b)}
        </span>
      </td>
      <td className="px-4 py-2 text-right font-mono text-muted-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>
        {latStr(entry.span_b)}
      </td>
      <td className={cn("px-4 py-2 text-right font-mono font-semibold", deltaColor)} style={{ fontFamily: "var(--font-geist-mono)" }}>
        {entry.latency_delta_pct !== null
          ? `${entry.latency_delta_pct > 0 ? "+" : ""}${entry.latency_delta_pct}%`
          : "—"}
      </td>
    </tr>
  );
}

/* ── Compare picker ───────────────────────────────────────────── */
function ComparePicker({
  sessions,
  selectedId,
  onPick,
  onCancel,
}: {
  sessions: AgentSession[];
  selectedId: string;
  onPick: (id: string) => void;
  onCancel: () => void;
}) {
  const [pickerSearch, setPickerSearch] = useState("");

  const candidates = useMemo(() => {
    return sessions
      .filter((s) => s.session_id !== selectedId)
      .filter((s) => {
        if (!pickerSearch) return true;
        const q = pickerSearch.toLowerCase();
        return (
          s.session_id.toLowerCase().includes(q) ||
          (s.agent_name ?? "").toLowerCase().includes(q)
        );
      })
      .slice(0, 10);
  }, [sessions, selectedId, pickerSearch]);

  return (
    <div
      className="mt-6 rounded-xl border overflow-hidden"
      style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
    >
      <div
        className="border-b px-4 py-3"
        style={{ background: "hsl(var(--card-raised))", borderColor: "hsl(var(--border))" }}
      >
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <GitCompare size={13} className="text-primary" />
            <span className="text-sm font-semibold text-foreground">Select a session to compare with</span>
          </div>
          <button onClick={onCancel} className="btn btn-ghost text-xs">Cancel</button>
        </div>
        <div className="mt-3">
          <div className="relative max-w-sm">
            <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              type="text"
              value={pickerSearch}
              onChange={(e) => setPickerSearch(e.target.value)}
              placeholder="Search session ID or agent..."
              className="input-base pl-8 h-[34px] text-[13px] w-full"
              autoFocus
            />
          </div>
        </div>
      </div>

      <div className="max-h-[400px] overflow-y-auto">
        {candidates.length === 0 ? (
          <p className="p-8 text-center text-sm text-muted-foreground">No matching sessions</p>
        ) : (
          <div className="divide-y" style={{ borderColor: "hsl(var(--border))" }}>
            {candidates.map((s) => (
              <button
                key={s.session_id}
                onClick={() => onPick(s.session_id)}
                className="w-full text-left px-4 py-3 hover:bg-accent/40 transition-colors flex items-center justify-between gap-4"
              >
                <div className="min-w-0">
                  <code
                    className="text-[12px] text-foreground block truncate"
                    style={{ fontFamily: "var(--font-geist-mono)" }}
                  >
                    {s.session_id.slice(0, 24)}...
                  </code>
                  <div className="flex items-center gap-2 text-[11px] text-muted-foreground mt-0.5">
                    {s.agent_name && <span>{s.agent_name}</span>}
                    <span>{s.tool_calls} calls</span>
                    {s.failed_calls > 0 && (
                      <span style={{ color: "hsl(var(--danger))" }}>{s.failed_calls} failed</span>
                    )}
                    <span>{formatDuration(s.duration_ms)}</span>
                  </div>
                </div>
                <div className="flex items-center gap-1 text-[11px] text-muted-foreground flex-shrink-0">
                  <Clock size={11} />
                  {timeAgo(s.first_call_at)}
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Compare detail ───────────────────────────────────────────── */
function CompareDetail({
  idA, idB, sessionA, sessionB, onBack, projectId,
}: {
  idA: string;
  idB: string;
  sessionA: AgentSession | undefined;
  sessionB: AgentSession | undefined;
  onBack: () => void;
  projectId?: string;
}) {
  const [cmp, setCmp] = useState<SessionComparison | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setCmp(null);
    setError(null);
    compareSessions(idA, idB, projectId)
      .then((c) => { setCmp(c); setLoading(false); })
      .catch((e) => { setError(e.message); setLoading(false); });
  }, [idA, idB, projectId]);

  return (
    <div
      className="mt-6 rounded-xl border overflow-hidden"
      style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
    >
      <div
        className="border-b px-4 py-3"
        style={{ background: "hsl(var(--card-raised))", borderColor: "hsl(var(--border))" }}
      >
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <Columns2 size={13} className="text-primary flex-shrink-0" />
            <div className="flex items-center gap-2 text-[12px] min-w-0" style={{ fontFamily: "var(--font-geist-mono)" }}>
              <div className="flex items-center gap-1.5 min-w-0">
                <span className="text-[10px] font-bold text-blue-400 bg-blue-500/10 px-1.5 py-0.5 rounded">Base</span>
                <span className="text-foreground truncate">{idA.slice(0, 12)}...</span>
                {sessionA?.agent_name && <span className="text-muted-foreground text-[11px]">({sessionA.agent_name})</span>}
              </div>
              <span className="text-muted-foreground">vs</span>
              <div className="flex items-center gap-1.5 min-w-0">
                <span className="text-[10px] font-bold text-purple-400 bg-purple-500/10 px-1.5 py-0.5 rounded">Compare</span>
                <span className="text-foreground truncate">{idB.slice(0, 12)}...</span>
                {sessionB?.agent_name && <span className="text-muted-foreground text-[11px]">({sessionB.agent_name})</span>}
              </div>
            </div>
          </div>
          <button onClick={onBack} className="btn btn-ghost text-xs">Close</button>
        </div>
        {cmp && (
          <div className="flex items-center gap-2 text-[11px] mt-2 ml-[28px]">
            <span className="text-emerald-500">{cmp.summary.matched} matched</span>
            {cmp.summary.diverged > 0 && <><span className="text-muted-foreground">·</span><span className="text-yellow-500">{cmp.summary.diverged} diverged</span></>}
            {cmp.summary.only_a > 0 && <><span className="text-muted-foreground">·</span><span className="text-blue-400">{cmp.summary.only_a} only in base</span></>}
            {cmp.summary.only_b > 0 && <><span className="text-muted-foreground">·</span><span className="text-purple-400">{cmp.summary.only_b} only in compare</span></>}
          </div>
        )}
      </div>

      <div className="overflow-x-auto">
        {loading ? (
          <div className="p-10 flex items-center justify-center">
            <div className="w-6 h-6 rounded-full border-2 border-primary border-t-transparent spin" />
          </div>
        ) : error ? (
          <div className="p-8 text-center text-sm" style={{ color: "hsl(var(--danger))" }}>
            <AlertCircle size={20} className="mx-auto mb-2" /> {error}
          </div>
        ) : !cmp || cmp.diff.length === 0 ? (
          <p className="p-8 text-center text-sm text-muted-foreground">No spans found</p>
        ) : (
          <table className="w-full">
            <thead>
              <tr style={{ borderBottom: "1px solid hsl(var(--border))", background: "hsl(var(--card-raised))" }}>
                <th className="px-4 py-2.5 text-left text-[11px] font-semibold text-muted-foreground uppercase tracking-wide">Tool</th>
                <th className="px-4 py-2.5 text-center text-[11px] font-semibold text-blue-400 uppercase tracking-wide">Base status</th>
                <th className="px-4 py-2.5 text-right text-[11px] font-semibold text-blue-400 uppercase tracking-wide">Base latency</th>
                <th className="px-4 py-2.5 text-center text-[11px] font-semibold text-purple-400 uppercase tracking-wide">Compare status</th>
                <th className="px-4 py-2.5 text-right text-[11px] font-semibold text-purple-400 uppercase tracking-wide">Compare latency</th>
                <th className="px-4 py-2.5 text-right text-[11px] font-semibold text-muted-foreground uppercase tracking-wide">Delta</th>
              </tr>
            </thead>
            <tbody>
              {cmp.diff.map((entry, i) => <DiffRow key={i} entry={entry} />)}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════ */
/* ── Session Detail Page ──────────────────────────────────────── */
/* ══════════════════════════════════════════════════════════════ */
export default function SessionDetailPage() {
  const params = useParams();
  const router = useRouter();
  const sessionId = params.id as string;

  const { activeProject } = useProject();
  const projectId = activeProject?.id;
  const p = projectId ? `&project_id=${projectId}` : "";

  /* Trace data */
  const [trace, setTrace] = useState<SessionTrace | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  /* Replay */
  const [replaying, setReplaying] = useState(false);
  const [replayError, setReplayError] = useState<string | null>(null);

  /* Tabs */
  const [activeTab, setActiveTab] = useState<"details" | "trace">("details");

  /* Graph selection + expand/collapse */
  const [selection, setSelection] = useState<GraphSelection>(null);
  // Auto-expand all multi-caller servers on first load
  const autoExpandedRef = useRef(false);
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());
  const [expandedEdges, setExpandedEdges] = useState<Set<string>>(new Set());

  const handleToggleGroup = useCallback((groupId: string) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(groupId)) next.delete(groupId);
      else next.add(groupId);
      return next;
    });
    setSelection(null);
  }, []);

  const handleToggleEdge = useCallback((edgeId: string) => {
    setExpandedEdges((prev) => {
      const next = new Set(prev);
      if (next.has(edgeId)) next.delete(edgeId);
      else next.add(edgeId);
      console.log("[toggle-edge]", edgeId, "→ expanded:", [...next]);
      return next;
    });
    setSelection(null);
  }, []);
  // Auto-expand multi-caller servers when trace first loads
  useEffect(() => {
    if (!trace || autoExpandedRef.current) return;
    autoExpandedRef.current = true;
    const callerCount = new Map<string, Set<string>>();
    for (const span of trace.spans_flat) {
      if (span.span_type === "tool_call" && span.agent_name && span.server_name) {
        if (!callerCount.has(span.server_name)) callerCount.set(span.server_name, new Set());
        callerCount.get(span.server_name)!.add(span.agent_name);
      }
    }
    const toExpand = new Set<string>();
    for (const [server, agents] of callerCount) {
      if (agents.size >= 2) toExpand.add(`server:${server}`);
    }
    if (toExpand.size > 0) setExpandedGroups(toExpand);
  }, [trace]);

  const sessionGraph = useSessionGraph(trace, expandedGroups, expandedEdges);

  const handleExpandAll = useCallback(() => {
    const groups = new Set<string>();
    for (const n of sessionGraph.nodes) if (n.isCollapsible) groups.add(n.groupId ?? n.id);
    setExpandedGroups(groups);
    const edgeIds = new Set<string>();
    for (const [pk, pm] of sessionGraph.edgeMetrics) if (pm.tools.length >= 2) edgeIds.add(pk);
    setExpandedEdges(edgeIds);
  }, [sessionGraph]);

  const handleCollapseAll = useCallback(() => {
    setExpandedGroups(new Set());
    setExpandedEdges(new Set());
    setSelection(null);
  }, []);

  /* Payload slideout */
  const [payloadSlideout, setPayloadSlideout] = useState<{ title: string; tabs: { label: string; json: string | null }[] } | null>(null);

  /* Graph fullscreen */
  const [graphFullscreen, setGraphFullscreen] = useState(false);

  /* Compare */
  const [comparePicking, setComparePicking] = useState(false);
  const [compareWith, setCompareWith] = useState<string | null>(null);

  /* Sessions list (for compare picker) */
  const { data: sessions } = useSWR<AgentSession[]>(
    `/api/agents/sessions?hours=168&limit=500${p}`,
    fetcher
  );

  /* Current session metadata from the sessions list */
  const session = useMemo(
    () => sessions?.find((s) => s.session_id === sessionId),
    [sessions, sessionId]
  );
  const compareSession = useMemo(
    () => sessions?.find((s) => s.session_id === compareWith),
    [sessions, compareWith]
  );

  /* Fetch trace */
  useEffect(() => {
    setLoading(true);
    setTrace(null);
    setError(null);
    getSessionTrace(sessionId, projectId)
      .then((t) => { setTrace(t); setLoading(false); })
      .catch((e) => { setError(e.message); setLoading(false); });
  }, [sessionId, projectId]);

  async function handleReplay() {
    setReplaying(true);
    setReplayError(null);
    try {
      await replaySession(sessionId, 10, 60, projectId);
    } catch (e: unknown) {
      setReplayError(e instanceof Error ? e.message : "Replay failed");
    } finally {
      setReplaying(false);
    }
  }

  return (
    <div className="page-in flex flex-col" style={{ height: "calc(100vh - 4rem)", paddingBottom: "1rem" }}>
      {/* ── Back + Header ──────────────────────────────────────── */}
      <div className="flex-shrink-0 pb-3">
        <button
          onClick={() => router.push("/sessions")}
          className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors mb-3"
        >
          <ArrowLeft size={14} />
          Back to Sessions
        </button>

        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 min-w-0">
            <GitBranch size={15} className="text-primary flex-shrink-0" />
            <div className="min-w-0">
              <code
                className="text-sm text-foreground block truncate"
                style={{ fontFamily: "var(--font-geist-mono)" }}
              >
                {sessionId}
              </code>
              <div className="flex items-center gap-2 text-[12px] text-muted-foreground mt-0.5">
                {session?.agent_name && (
                  <span className="text-primary font-medium">{session.agent_name}</span>
                )}
                {trace && (
                  <>
                    <span>{trace.total_spans} spans</span>
                    <span>·</span>
                    <span>{trace.tool_calls} tool calls</span>
                    {trace.failed_calls > 0 && (
                      <><span>·</span>
                      <span style={{ color: "hsl(var(--danger))" }} className="font-semibold">
                        {trace.failed_calls} failed
                      </span></>
                    )}
                    {trace.duration_ms && (
                      <><span>·</span><span>{formatDuration(trace.duration_ms)}</span></>
                    )}
                  </>
                )}
                {session && (
                  <>
                    <span>·</span>
                    <span className="flex items-center gap-1"><Clock size={11} />{timeAgo(session.first_call_at)}</span>
                  </>
                )}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2 flex-shrink-0">
            <button
              onClick={handleReplay}
              disabled={replaying || loading}
              className="btn btn-secondary text-[12px] py-1.5 px-3"
            >
              {replaying
                ? <><span className="w-3 h-3 border border-current border-t-transparent rounded-full spin" />Replaying...</>
                : <><Play size={11} />Replay</>
              }
            </button>
            <button
              onClick={() => { setComparePicking((v) => !v); setCompareWith(null); }}
              className={cn(
                "btn text-[12px] py-1.5 px-3",
                comparePicking ? "btn-primary" : "btn-secondary"
              )}
            >
              <GitCompare size={11} />Compare
            </button>
          </div>
        </div>
      </div>

      {replayError && (
        <div
          className="flex-shrink-0 rounded-lg px-4 py-2 text-xs mb-3"
          style={{ background: "hsl(var(--danger-bg))", color: "hsl(var(--danger))", border: "1px solid hsl(var(--danger) / 0.2)" }}
        >
          Replay failed: {replayError}
        </div>
      )}

      {/* ── Tab bar ────────────────────────────────────────────── */}
      <div className="flex-shrink-0 flex items-center gap-1 mb-3 border-b" style={{ borderColor: "hsl(var(--border))" }}>
        {([
          { key: "details", label: "Details", count: trace ? `${new Set(trace.spans_flat.map((s: SpanNode) => s.agent_name).filter(Boolean)).size} agents · ${new Set(trace.spans_flat.filter((s: SpanNode) => s.span_type === "tool_call").map((s: SpanNode) => s.server_name)).size} servers` : undefined },
          { key: "trace", label: "Trace", count: trace ? `${trace.total_spans} spans` : undefined },
        ] as const).map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={cn(
              "px-4 py-2.5 text-[13px] font-medium border-b-2 -mb-px transition-colors",
              activeTab === tab.key
                ? "border-primary text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            {tab.label}
            {tab.count && (
              <span className="ml-2 text-[10px] px-1.5 py-0.5 rounded-full" style={{ background: "hsl(var(--muted))" }}>
                {tab.count}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* ── Details tab — session lineage graph ─────────────────── */}
      {activeTab === "details" && (
        <div className="flex-1 flex gap-0 rounded-xl border overflow-hidden min-h-0" style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}>
          {/* Graph (70%) */}
          <div className="flex-[7] flex flex-col">
            {/* Timeline bar */}
            {trace && trace.duration_ms && (
              <div className="flex-shrink-0 px-3 pt-2">
                <SessionTimeline
                  spans={trace.spans_flat}
                  sessionDurationMs={trace.duration_ms}
                  onSelectNode={(nodeId) => setSelection({ type: "node", id: nodeId })}
                />
              </div>
            )}
            {/* Graph */}
            <div className="flex-1 relative min-h-0">
              {loading ? (
                <div className="flex items-center justify-center h-full">
                  <div className="w-6 h-6 rounded-full border-2 border-primary border-t-transparent spin" />
                </div>
              ) : !trace ? (
                <div className="flex items-center justify-center h-full text-sm text-muted-foreground">No data</div>
              ) : (
                <>
                  <LineageGraph
                    nodes={sessionGraph.nodes}
                    edges={sessionGraph.edges}
                    selection={selection}
                    onSelectionChange={setSelection}
                    expandedGroups={expandedGroups}
                    onToggleGroup={handleToggleGroup}
                    expandedEdges={expandedEdges}
                    onToggleEdge={handleToggleEdge}
                    onExpandAll={handleExpandAll}
                    onCollapseAll={handleCollapseAll}
                    nodeHeight={76}
                    className="h-full"
                  />
                  {/* Fullscreen button — top-right corner overlay */}
                  <button
                    onClick={() => setGraphFullscreen(true)}
                    className="btn btn-secondary absolute top-2 right-2 h-[26px] px-2 text-[11px] flex items-center gap-1 z-10"
                    title="Fullscreen"
                  >
                    <Maximize2 size={12} />
                  </button>
                </>
              )}
            </div>

            {/* Fullscreen overlay */}
            {graphFullscreen && trace && (
              <div className="fixed inset-0 z-50 flex flex-col" style={{ background: "hsl(var(--background))" }}>
                <div className="flex items-center justify-between px-4 py-2 border-b flex-shrink-0" style={{ borderColor: "hsl(var(--border))" }}>
                  <span className="text-[13px] font-semibold" style={{ color: "hsl(var(--foreground))" }}>Session graph — {sessionId}</span>
                  <button
                    onClick={() => setGraphFullscreen(false)}
                    className="btn btn-secondary text-xs flex items-center gap-1.5"
                  >
                    <Minimize2 size={12} /> Exit fullscreen
                  </button>
                </div>
                <div className="flex-1 relative min-h-0">
                  <LineageGraph
                    nodes={sessionGraph.nodes}
                    edges={sessionGraph.edges}
                    selection={selection}
                    onSelectionChange={setSelection}
                    expandedGroups={expandedGroups}
                    onToggleGroup={handleToggleGroup}
                    expandedEdges={expandedEdges}
                    onToggleEdge={handleToggleEdge}
                    onExpandAll={handleExpandAll}
                    onCollapseAll={handleCollapseAll}
                    nodeHeight={76}
                    className="h-full"
                  />
                </div>
              </div>
            )}
          </div>
          {/* Right panel (~36%) */}
          <div className="flex-[4] border-l overflow-y-auto" style={{ borderColor: "hsl(var(--border))", background: "hsl(var(--background))" }}>
            {selection?.type === "node" && trace ? (
              <SessionNodeDetail
                nodeId={selection.id}
                trace={trace}
                serverCallers={sessionGraph.serverCallers}
              />
            ) : selection?.type === "edge" && trace ? (
              <SessionEdgeDetail
                source={selection.source}
                target={selection.target}
                metrics={sessionGraph.edgeMetrics.get(`${selection.source}→${selection.target}`) ?? null}
                spans={sessionGraph.edgeSpans.get(`${selection.source}→${selection.target}`) ?? []}
              />
            ) : (
              <div className="flex flex-col items-center justify-center h-full px-6 py-10 gap-4">
                <div className="w-12 h-12 rounded-xl flex items-center justify-center" style={{ background: "hsl(var(--muted))" }}>
                  <GitBranch size={22} style={{ color: "hsl(var(--muted-foreground))" }} />
                </div>
                <div className="text-center space-y-1">
                  <p className="text-[13px] font-semibold" style={{ color: "hsl(var(--foreground))" }}>Session flow</p>
                  <p className="text-[12px]" style={{ color: "hsl(var(--muted-foreground))" }}>Click any agent, server, or edge to see its details for this session.</p>
                </div>
                <div className="w-full mt-2 space-y-2">
                  <div className="rounded-lg p-3 flex items-center justify-between" style={{ background: "hsl(var(--muted))" }}>
                    <span className="text-[11px]" style={{ color: "hsl(var(--muted-foreground))" }}>Total spans</span>
                    <span className="text-[12px] font-semibold" style={{ color: "hsl(var(--foreground))", fontFamily: "var(--font-geist-mono)" }}>{trace?.spans_flat?.length ?? "—"}</span>
                  </div>
                  <div className="rounded-lg p-3 flex items-center justify-between" style={{ background: "hsl(var(--muted))" }}>
                    <span className="text-[11px]" style={{ color: "hsl(var(--muted-foreground))" }}>Tool calls</span>
                    <span className="text-[12px] font-semibold" style={{ color: "hsl(var(--foreground))", fontFamily: "var(--font-geist-mono)" }}>{trace?.spans_flat?.filter((s: SpanNode) => s.span_type === "tool_call").length ?? "—"}</span>
                  </div>
                  <div className="rounded-lg p-3 flex items-center justify-between" style={{ background: "hsl(var(--muted))" }}>
                    <span className="text-[11px]" style={{ color: "hsl(var(--muted-foreground))" }}>Errors</span>
                    <span className="text-[12px] font-semibold" style={{ color: trace?.spans_flat?.some((s: SpanNode) => s.status === "error") ? "hsl(var(--danger))" : "hsl(var(--foreground))", fontFamily: "var(--font-geist-mono)" }}>{trace?.spans_flat?.filter((s: SpanNode) => s.status === "error").length ?? "—"}</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Trace tab — span tree ──────────────────────────────── */}
      {activeTab === "trace" && (
        <>
          <div
            className="flex-1 rounded-xl border overflow-hidden flex flex-col min-h-0"
            style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
          >
            <div className="flex-1 overflow-y-auto overflow-x-auto">
              {loading ? (
                <div className="p-10 flex items-center justify-center">
                  <div className="w-6 h-6 rounded-full border-2 border-primary border-t-transparent spin" />
                </div>
              ) : error ? (
                <div className="p-8 text-center text-sm" style={{ color: "hsl(var(--danger))" }}>
                  <AlertCircle size={20} className="mx-auto mb-2" />
                  {error}
                </div>
              ) : !trace || trace.root_spans.length === 0 ? (
                <p className="p-8 text-center text-sm text-muted-foreground">No spans found</p>
              ) : (
                <table className="w-full">
                  <thead>
                    <tr
                      className="sticky top-0 z-10"
                      style={{ borderBottom: "1px solid hsl(var(--border))", background: "hsl(var(--card-raised))" }}
                    >
                      {["Span", "Agent", "Status", "Latency", "Error"].map((h) => (
                        <th
                          key={h}
                          className="px-4 py-2.5 text-left text-[11px] font-semibold text-muted-foreground uppercase tracking-wide"
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {trace.root_spans.map((span) => (
                      <SpanRow key={span.span_id} span={span} depth={0} />
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>

          {/* Compare picker */}
          {comparePicking && !compareWith && sessions && (
            <ComparePicker
              sessions={sessions}
              selectedId={sessionId}
              onPick={(id) => { setCompareWith(id); setComparePicking(false); }}
              onCancel={() => setComparePicking(false)}
            />
          )}
          {compareWith && (
            <CompareDetail
              idA={sessionId}
              idB={compareWith}
              sessionA={session}
              sessionB={compareSession}
              onBack={() => { setCompareWith(null); setComparePicking(false); }}
              projectId={projectId}
            />
          )}
        </>
      )}

      {/* ── Payload slideout ── */}
      {payloadSlideout && (
        <PayloadSlideout
          open={true}
          onClose={() => setPayloadSlideout(null)}
          title={payloadSlideout.title}
          tabs={payloadSlideout.tabs}
        />
      )}
    </div>
  );
}
