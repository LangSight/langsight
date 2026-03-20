"use client";

export const dynamic = "force-dynamic";

import { useState, useEffect, useMemo } from "react";
import { useParams, useRouter } from "next/navigation";
import useSWR from "swr";
import {
  ChevronRight, ChevronDown, GitBranch, Clock, Zap, AlertCircle,
  Search, GitCompare, Play, ArrowLeft, Columns2, Bot, Server,
} from "lucide-react";
import {
  ReactFlow,
  Background,
  Handle,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  Position,
  MarkerType,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import dagre from "dagre";
import { fetcher, getSessionTrace, compareSessions, replaySession } from "@/lib/api";
import { useProject } from "@/lib/project-context";
import { cn, timeAgo, formatDuration, CALL_STATUS_COLOR, SPAN_TYPE_ICON } from "@/lib/utils";
import type { AgentSession, SessionTrace, SpanNode, SessionComparison, DiffEntry } from "@/lib/types";

/* ── Session lineage graph ──────────────────────────────────── */

function SessionLineageNode({ data }: { data: { label: string; nodeType: string; hasError: boolean } }) {
  const isAgent = data.nodeType === "agent";
  const color = data.hasError ? "#ef4444" : "#10b981";
  return (
    <div
      className="rounded-xl px-3.5 py-2.5 flex items-center gap-2.5 shadow-sm"
      style={{ background: "hsl(var(--card))", border: `2px solid ${data.hasError ? "rgba(239,68,68,0.4)" : "rgba(16,185,129,0.4)"}`, minWidth: 150 }}
    >
      <Handle type="target" position={Position.Left} style={{ background: color, width: 8, height: 8, border: "2px solid hsl(var(--card))" }} />
      <div className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0" style={{ background: `${color}15` }}>
        {isAgent ? <Bot size={13} style={{ color }} /> : <Server size={13} style={{ color }} />}
      </div>
      <div>
        <p className="text-[11px] font-bold text-foreground leading-tight">{data.label}</p>
        <p className="text-[9px]" style={{ color }}>{isAgent ? "Agent" : "MCP Server"}</p>
      </div>
      <Handle type="source" position={Position.Right} style={{ background: color, width: 8, height: 8, border: "2px solid hsl(var(--card))" }} />
    </div>
  );
}

const sessionNodeTypes = { agent: SessionLineageNode, server: SessionLineageNode };

function SessionLineage({ trace, selectedNode, onNodeClick }: {
  trace: SessionTrace;
  selectedNode: string | null;
  onNodeClick: (id: string | null) => void;
}) {
  const { graphNodes, graphEdges } = useMemo(() => {
    const agents = new Set<string>();
    const servers = new Set<string>();
    const edges = new Map<string, { from: string; to: string; type: string; hasError: boolean }>();
    const agentErrors = new Set<string>();
    const serverErrors = new Set<string>();

    for (const span of trace.spans_flat) {
      const agent = span.agent_name;
      const server = span.server_name;
      const spanType = span.span_type;
      const failed = span.status !== "success";

      if (agent) agents.add(agent);
      if (failed && agent) agentErrors.add(agent);

      if (spanType === "handoff" && agent && span.tool_name) {
        const target = span.tool_name.replace(/^->\s*/, "").replace(/^→\s*/, "");
        if (target) {
          agents.add(target);
          edges.set(`${agent}→${target}`, { from: `agent:${agent}`, to: `agent:${target}`, type: "handoff", hasError: false });
        }
      } else if (spanType === "tool_call" && agent && server) {
        servers.add(server);
        if (failed) serverErrors.add(server);
        const key = `${agent}→${server}`;
        const existing = edges.get(key);
        edges.set(key, { from: `agent:${agent}`, to: `server:${server}`, type: "calls", hasError: (existing?.hasError || failed) });
      }
    }

    const nodes: Node[] = [
      ...[...agents].map((a) => ({
        id: `agent:${a}`, type: "agent", position: { x: 0, y: 0 },
        data: { label: a, nodeType: "agent", hasError: agentErrors.has(a) },
      })),
      ...[...servers].map((s) => ({
        id: `server:${s}`, type: "server", position: { x: 0, y: 0 },
        data: { label: s, nodeType: "server", hasError: serverErrors.has(s) },
      })),
    ];

    const flowEdges: Edge[] = [...edges.values()].map((e, i) => {
      const color = e.type === "handoff" ? "#6366f1" : e.hasError ? "#ef4444" : "#10b981";
      return {
        id: `se-${i}`, source: e.from, target: e.to, type: "smoothstep",
        animated: e.type === "handoff",
        style: { stroke: color, strokeWidth: 2.5 },
        markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14, color },
        label: e.type === "handoff" ? "handoff" : undefined,
        labelStyle: { fontSize: 9, fill: "#888" },
        labelBgStyle: { fill: "hsl(var(--card))", fillOpacity: 0.9 },
      };
    });

    // Dagre layout
    const g = new dagre.graphlib.Graph();
    g.setDefaultEdgeLabel(() => ({}));
    g.setGraph({ rankdir: "LR", nodesep: 40, ranksep: 80 });
    nodes.forEach((n) => g.setNode(n.id, { width: 160, height: 50 }));
    flowEdges.forEach((e) => g.setEdge(e.source, e.target));
    dagre.layout(g);

    const laid = nodes.map((n) => {
      const p = g.node(n.id);
      return { ...n, position: { x: p.x - 80, y: p.y - 25 }, sourcePosition: Position.Right, targetPosition: Position.Left };
    });

    return { graphNodes: laid, graphEdges: flowEdges };
  }, [trace]);

  const [nodes, , onNodesChange] = useNodesState(graphNodes);
  const [edges, , onEdgesChange] = useEdgesState(graphEdges);

  if (graphNodes.length === 0) return <div className="flex items-center justify-center h-full text-sm text-muted-foreground">No graph data</div>;

  return (
    <div className="h-full w-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={(_, node) => onNodeClick(node.id)}
        onPaneClick={() => onNodeClick(null)}
        nodeTypes={sessionNodeTypes}
        fitView
        minZoom={0.5}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
        style={{ background: "transparent" }}
      >
        <Background gap={24} size={0.8} color="hsl(var(--muted-foreground) / 0.06)" />
      </ReactFlow>
    </div>
  );
}

/* ── Right panel: node detail for session ──────────────────── */
function SessionNodeDetail({ nodeId, trace }: { nodeId: string; trace: SessionTrace }) {
  const isAgent = nodeId.startsWith("agent:");
  const name = nodeId.replace(/^(agent|server):/, "");

  // Filter spans for this node
  const spans = trace.spans_flat.filter((s: SpanNode) =>
    isAgent ? s.agent_name === name : (s.server_name === name && s.span_type === "tool_call")
  );

  const totalCalls = spans.length;
  const errors = spans.filter((s: SpanNode) => s.status !== "success").length;
  const avgLatency = totalCalls > 0 ? spans.reduce((sum: number, s: SpanNode) => sum + (s.latency_ms ?? 0), 0) / totalCalls : 0;
  const tools = [...new Set(spans.map((s: SpanNode) => s.tool_name))];
  const errorRate = totalCalls > 0 ? (errors / totalCalls) * 100 : 0;
  const totalInputTokens = spans.reduce((s: number, sp: SpanNode) => s + (sp.input_tokens ?? 0), 0);
  const totalOutputTokens = spans.reduce((s: number, sp: SpanNode) => s + (sp.output_tokens ?? 0), 0);
  const models = [...new Set(spans.map((s: SpanNode) => s.model_id).filter(Boolean))];
  const statusColor = errorRate >= 10 ? "#ef4444" : errorRate >= 2 ? "#f59e0b" : "#10b981";
  const statusLabel = errorRate >= 10 ? "Error" : errorRate >= 2 ? "Degraded" : "Healthy";

  return (
    <div className="h-full overflow-y-auto">
      {/* Header */}
      <div className="px-5 py-5 border-b" style={{ borderColor: "hsl(var(--border))" }}>
        <div className="flex items-center gap-3 mb-2">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: `${statusColor}15` }}>
            {isAgent ? <Bot size={18} style={{ color: statusColor }} /> : <Server size={18} style={{ color: statusColor }} />}
          </div>
          <div>
            <p className="text-sm font-bold text-foreground">{name}</p>
            <p className="text-[11px]" style={{ color: statusColor }}>{isAgent ? "Agent" : "MCP Server"} · {statusLabel}</p>
          </div>
        </div>
      </div>

      {/* Metrics */}
      <div className="px-5 py-4">
        <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-widest mb-3">Session Metrics</p>
        <div className="grid grid-cols-2 gap-2">
          {[
            { label: "Calls", value: totalCalls.toString() },
            { label: "Errors", value: errors.toString() },
            { label: "Avg Latency", value: `${Math.round(avgLatency)}ms` },
            { label: "Error Rate", value: `${errorRate.toFixed(1)}%` },
          ].map((s) => (
            <div key={s.label} className="rounded-xl p-3" style={{ background: "hsl(var(--muted))" }}>
              <p className="text-[10px] text-muted-foreground">{s.label}</p>
              <p className="text-sm font-bold text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>{s.value}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Tools called */}
      {!isAgent && tools.length > 0 && (
        <div className="px-5 py-4 border-t" style={{ borderColor: "hsl(var(--border))" }}>
          <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-widest mb-3">Tools Called</p>
          <div className="space-y-1.5">
            {tools.map((tool) => {
              const toolSpans = spans.filter((s: SpanNode) => s.tool_name === tool);
              const toolErrors = toolSpans.filter((s: SpanNode) => s.status !== "success").length;
              return (
                <div key={tool} className="flex items-center justify-between rounded-lg px-3 py-2" style={{ background: "hsl(var(--muted))" }}>
                  <span className="text-[12px] font-medium text-foreground">{tool}</span>
                  <span className="text-[11px] text-muted-foreground">
                    {toolSpans.length}x {toolErrors > 0 && <span className="text-red-400 ml-1">({toolErrors} err)</span>}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Token usage */}
      {totalInputTokens > 0 && (
        <div className="px-5 py-4 border-t" style={{ borderColor: "hsl(var(--border))" }}>
          <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-widest mb-3">Token Usage</p>
          <div className="grid grid-cols-2 gap-2">
            {[
              { label: "Input Tokens", value: totalInputTokens.toLocaleString() },
              { label: "Output Tokens", value: totalOutputTokens.toLocaleString() },
              { label: "Total Tokens", value: (totalInputTokens + totalOutputTokens).toLocaleString() },
              { label: "Models", value: models.join(", ") || "—" },
            ].map((s) => (
              <div key={s.label} className="rounded-xl p-3" style={{ background: "hsl(var(--muted))" }}>
                <p className="text-[10px] text-muted-foreground">{s.label}</p>
                <p className="text-sm font-bold text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>{s.value}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Span details */}
      <div className="px-5 py-4 border-t" style={{ borderColor: "hsl(var(--border))" }}>
        <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-widest mb-3">Span Details</p>
        <div className="space-y-2">
          {spans.map((s: SpanNode, i: number) => (
            <div key={i} className="rounded-xl overflow-hidden" style={{ border: "1px solid hsl(var(--border))" }}>
              <div className="flex items-center justify-between px-3 py-2.5" style={{ background: "hsl(var(--muted))" }}>
                <div className="flex items-center gap-2">
                  <span className={s.status === "success" ? "text-green-500" : "text-red-500"}>
                    {s.status === "success" ? "✓" : "✗"}
                  </span>
                  <span className="text-[12px] font-semibold text-foreground">{s.tool_name}</span>
                </div>
                <span className="text-[11px] text-muted-foreground font-mono">{Math.round(s.latency_ms ?? 0)}ms</span>
              </div>
              {/* Error */}
              {s.error && (
                <div className="px-3 py-2 text-[11px]" style={{ background: "rgba(239,68,68,0.05)", color: "#ef4444" }}>
                  {s.error}
                </div>
              )}
              {/* Input */}
              {s.input_json && (
                <div className="px-3 py-2 border-t" style={{ borderColor: "hsl(var(--border))" }}>
                  <p className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">Input</p>
                  <pre className="text-[10px] text-foreground whitespace-pre-wrap break-all max-h-24 overflow-y-auto" style={{ fontFamily: "var(--font-geist-mono)" }}>
                    {(() => { try { return JSON.stringify(JSON.parse(s.input_json), null, 2); } catch { return s.input_json; } })()}
                  </pre>
                </div>
              )}
              {/* Output */}
              {s.output_json && (
                <div className="px-3 py-2 border-t" style={{ borderColor: "hsl(var(--border))" }}>
                  <p className="text-[9px] text-muted-foreground uppercase tracking-widest mb-1">Output</p>
                  <pre className="text-[10px] text-foreground whitespace-pre-wrap break-all max-h-24 overflow-y-auto" style={{ fontFamily: "var(--font-geist-mono)" }}>
                    {(() => { try { return JSON.stringify(JSON.parse(s.output_json), null, 2); } catch { return s.output_json; } })()}
                  </pre>
                </div>
              )}
              {/* Tokens */}
              {(s.input_tokens || s.output_tokens) && (
                <div className="px-3 py-2 border-t flex items-center gap-4 text-[10px] text-muted-foreground" style={{ borderColor: "hsl(var(--border))" }}>
                  {s.model_id && <span>Model: <strong className="text-foreground">{s.model_id}</strong></span>}
                  {s.input_tokens && <span>In: <strong className="text-foreground">{s.input_tokens}</strong></span>}
                  {s.output_tokens && <span>Out: <strong className="text-foreground">{s.output_tokens}</strong></span>}
                </div>
              )}
            </div>
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
            {span.status === "success" ? "✓" : span.status === "error" ? "✗" : "⏱"}
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
    span ? (span.status === "success" ? "✓" : span.status === "error" ? "✗" : "⏱") : "—";
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
  const [selectedGraphNode, setSelectedGraphNode] = useState<string | null>(null);

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
    <div className="page-in flex flex-col" style={{ height: "calc(100vh - 4rem)" }}>
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
          <div className="flex-[7] relative">
            {loading ? (
              <div className="flex items-center justify-center h-full">
                <div className="w-6 h-6 rounded-full border-2 border-primary border-t-transparent spin" />
              </div>
            ) : !trace ? (
              <div className="flex items-center justify-center h-full text-sm text-muted-foreground">No data</div>
            ) : (
              <SessionLineage
                trace={trace}
                selectedNode={selectedGraphNode}
                onNodeClick={setSelectedGraphNode}
              />
            )}
          </div>
          {/* Right panel (30%) */}
          <div className="flex-[3] border-l overflow-y-auto" style={{ borderColor: "hsl(var(--border))", background: "hsl(var(--background))" }}>
            {selectedGraphNode && trace ? (
              <SessionNodeDetail nodeId={selectedGraphNode} trace={trace} />
            ) : (
              <div className="h-full flex flex-col items-center justify-center px-5 text-center">
                <GitBranch size={20} className="text-muted-foreground mb-3" />
                <p className="text-sm font-semibold text-foreground mb-1">Session flow</p>
                <p className="text-[11px] text-muted-foreground">Click any agent or server node to see its details for this session.</p>
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
    </div>
  );
}
