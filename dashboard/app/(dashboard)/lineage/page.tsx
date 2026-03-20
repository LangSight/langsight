"use client";

import { useMemo, useState } from "react";
import useSWR from "swr";
import { Bot, Server, AlertTriangle, Activity, ArrowRight, ArrowLeft, Zap, Clock, Hash, Users } from "lucide-react";
import { fetcher } from "@/lib/api";
import { useProject } from "@/lib/project-context";
import { cn } from "@/lib/utils";
import { LineageGraph as LineageGraphComponent, type GraphNode, type GraphEdge } from "@/components/lineage-graph";

/* ── Types ─────────────────────────────────────────────────── */
interface LineageNode {
  id: string;
  type: "agent" | "server";
  label: string;
  metrics: Record<string, number>;
}
interface LineageEdge {
  source: string;
  target: string;
  type: "calls" | "handoff";
  metrics: Record<string, number>;
}
interface LineageGraph {
  window_hours: number;
  nodes: LineageNode[];
  edges: LineageEdge[];
}

/* ── Constants ─────────────────────────────────────────────── */
const WINDOWS = [
  { label: "1h", hours: 1 },
  { label: "24h", hours: 24 },
  { label: "7d", hours: 24 * 7 },
  { label: "30d", hours: 24 * 30 },
];

/* ── Status helper ─────────────────────────────────────────── */
function getNodeStatus(m: Record<string, number>): "healthy" | "degraded" | "error" {
  if (!m.total_calls || m.total_calls === 0) return "healthy";
  const errRate = (m.error_count ?? 0) / m.total_calls;
  if (errRate >= 0.1) return "error";
  if (errRate >= 0.02) return "degraded";
  return "healthy";
}

const STATUS_CONFIG = {
  healthy:  { color: "#10b981", bg: "rgba(16,185,129,0.12)", border: "rgba(16,185,129,0.4)", label: "Healthy" },
  degraded: { color: "#f59e0b", bg: "rgba(245,158,11,0.12)", border: "rgba(245,158,11,0.4)", label: "Degraded" },
  error:    { color: "#ef4444", bg: "rgba(239,68,68,0.12)",  border: "rgba(239,68,68,0.4)",  label: "Error" },
};

/* ── Right panel ───────────────────────────────────────────── */
function DetailPanel({ node, allEdges }: { node: LineageNode; allEdges: LineageEdge[] }) {
  const m = node.metrics;
  const isAgent = node.type === "agent";
  const status = getNodeStatus(m);
  const cfg = STATUS_CONFIG[status];
  const errorRate = m.total_calls > 0 ? ((m.error_count ?? 0) / m.total_calls * 100) : 0;

  const inbound = allEdges.filter((e) => e.target === node.id);
  const outbound = allEdges.filter((e) => e.source === node.id);

  return (
    <div className="h-full overflow-y-auto">
      {/* Header */}
      <div className="px-5 py-5 border-b" style={{ borderColor: "hsl(var(--border))" }}>
        <div className="flex items-center gap-3 mb-3">
          <div className="w-11 h-11 rounded-xl flex items-center justify-center" style={{ background: cfg.bg }}>
            {isAgent ? <Bot size={20} style={{ color: cfg.color }} /> : <Server size={20} style={{ color: cfg.color }} />}
          </div>
          <div>
            <p className="text-base font-bold text-foreground">{node.label}</p>
            <p className="text-[11px]" style={{ color: cfg.color }}>
              {isAgent ? "Agent" : "MCP Server"} · {cfg.label}
            </p>
          </div>
        </div>
        {/* Status bar */}
        <div className="flex items-center gap-2">
          <span
            className="text-[10px] font-bold px-2.5 py-1 rounded-full"
            style={{ background: cfg.bg, color: cfg.color }}
          >
            {cfg.label.toUpperCase()}
          </span>
          <span className="text-[11px] text-muted-foreground">
            {errorRate.toFixed(1)}% error rate
          </span>
        </div>
      </div>

      {/* Metrics grid */}
      <div className="px-5 py-4">
        <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-widest mb-3">Metrics</p>
        <div className="grid grid-cols-2 gap-2">
          {[
            { icon: <Hash size={12} />, label: "Total Calls", value: (m.total_calls ?? 0).toLocaleString() },
            { icon: <AlertTriangle size={12} />, label: "Errors", value: (m.error_count ?? 0).toLocaleString() },
            { icon: <Clock size={12} />, label: "Avg Latency", value: `${Math.round(m.avg_latency_ms ?? 0)}ms` },
            { icon: <Users size={12} />, label: isAgent ? "Sessions" : "Used by agents", value: (m.sessions ?? m.called_by_agents ?? 0).toLocaleString() },
          ].map((s) => (
            <div key={s.label} className="rounded-xl p-3 flex items-start gap-2.5" style={{ background: "hsl(var(--muted))" }}>
              <span className="text-muted-foreground mt-0.5">{s.icon}</span>
              <div>
                <p className="text-[10px] text-muted-foreground">{s.label}</p>
                <p className="text-sm font-bold text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>{s.value}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Inbound connections */}
      {inbound.length > 0 && (
        <div className="px-5 py-4 border-t" style={{ borderColor: "hsl(var(--border))" }}>
          <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-widest mb-3 flex items-center gap-1.5">
            <ArrowLeft size={10} /> Input — called by
          </p>
          <div className="space-y-1.5">
            {inbound.map((e, i) => {
              const label = e.source.replace(/^(agent|server):/, "");
              const vol = e.metrics.call_count ?? e.metrics.handoff_count ?? 0;
              return (
                <div key={i} className="flex items-center justify-between rounded-lg px-3 py-2" style={{ background: "hsl(var(--muted))" }}>
                  <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full" style={{ background: e.source.startsWith("agent:") ? "hsl(var(--primary))" : "#10b981" }} />
                    <span className="text-[12px] font-medium text-foreground">{label}</span>
                  </div>
                  <span className="text-[11px] text-muted-foreground font-mono">{vol} {e.type === "handoff" ? "handoffs" : "calls"}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Outbound connections */}
      {outbound.length > 0 && (
        <div className="px-5 py-4 border-t" style={{ borderColor: "hsl(var(--border))" }}>
          <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-widest mb-3 flex items-center gap-1.5">
            <ArrowRight size={10} /> Output — calls to
          </p>
          <div className="space-y-1.5">
            {outbound.map((e, i) => {
              const label = e.target.replace(/^(agent|server):/, "");
              const vol = e.metrics.call_count ?? e.metrics.handoff_count ?? 0;
              return (
                <div key={i} className="flex items-center justify-between rounded-lg px-3 py-2" style={{ background: "hsl(var(--muted))" }}>
                  <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full" style={{ background: e.target.startsWith("agent:") ? "hsl(var(--primary))" : "#10b981" }} />
                    <span className="text-[12px] font-medium text-foreground">{label}</span>
                  </div>
                  <span className="text-[11px] text-muted-foreground font-mono">{vol} {e.type === "handoff" ? "handoffs" : "calls"}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Blast radius (servers only) */}
      {!isAgent && inbound.length > 0 && (
        <div className="px-5 py-4 border-t" style={{ borderColor: "hsl(var(--border))" }}>
          <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-widest mb-2 flex items-center gap-1.5">
            <Zap size={10} /> Blast Radius
          </p>
          <div className="rounded-xl p-3" style={{ background: "rgba(239,68,68,0.06)", border: "1px solid rgba(239,68,68,0.15)" }}>
            <p className="text-[12px] text-foreground">
              If <strong>{node.label}</strong> goes down, <strong className="text-red-400">{inbound.length} agent{inbound.length !== 1 ? "s" : ""}</strong> will be affected:
            </p>
            <p className="text-[11px] text-muted-foreground mt-1">
              {inbound.map((e) => e.source.replace(/^agent:/, "")).join(", ")}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Empty right panel ─────────────────────────────────────── */
function EmptyDetail() {
  return (
    <div className="h-full flex flex-col items-center justify-center px-6 text-center">
      <div className="w-12 h-12 rounded-2xl flex items-center justify-center mb-4" style={{ background: "hsl(var(--muted))" }}>
        <Activity size={20} className="text-muted-foreground" />
      </div>
      <p className="text-sm font-semibold text-foreground mb-1">Select a node</p>
      <p className="text-[12px] text-muted-foreground max-w-[200px]">
        Click any agent or server in the graph to see its details, connections, and blast radius.
      </p>
    </div>
  );
}

/* ── Main page ─────────────────────────────────────────────── */
export default function LineagePage() {
  const [hours, setHours] = useState(24 * 7);
  const { activeProject } = useProject();
  const [selectedNode, setSelectedNode] = useState<LineageNode | null>(null);

  const projectParam = activeProject ? `&project_id=${activeProject.id}` : "";
  const { data: graph, isLoading, error } = useSWR<LineageGraph>(
    `/api/agents/lineage?hours=${hours}${projectParam}`,
    fetcher,
    { refreshInterval: 60_000 }
  );

  const graphNodes = useMemo<GraphNode[]>(() => {
    if (!graph) return [];
    return graph.nodes.map((n) => ({
      id: n.id,
      type: n.type,
      label: n.label,
      hasError: (n.metrics.error_count ?? 0) > 0,
      callCount: n.metrics.total_calls ?? 0,
      meta: Object.fromEntries(
        Object.entries(n.metrics).map(([k, v]) => [k, v]),
      ),
    }));
  }, [graph]);

  const graphEdges = useMemo<GraphEdge[]>(() => {
    if (!graph) return [];
    return graph.edges.map((e) => ({
      source: e.source,
      target: e.target,
      type: e.type,
    }));
  }, [graph]);

  return (
    <div className="page-in" style={{ height: "calc(100vh - 4rem)" }}>
      {/* Header */}
      <div className="flex items-center justify-between gap-4 px-1 pb-3">
        <div>
          <h1 className="text-xl font-bold text-foreground">Agent Lineage</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Dependency graph — built from observed traces
          </p>
        </div>
        <div className="flex rounded-lg border p-0.5" style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}>
          {WINDOWS.map((w) => (
            <button
              key={w.hours}
              onClick={() => setHours(w.hours)}
              className={cn("px-3 py-1.5 rounded-md text-xs font-medium transition-all", w.hours === hours ? "bg-primary text-white shadow-sm" : "text-muted-foreground hover:text-foreground")}
            >
              {w.label}
            </button>
          ))}
        </div>
      </div>

      {/* 70/30 split */}
      <div className="flex gap-0 rounded-xl border overflow-hidden" style={{ height: "calc(100% - 3.5rem)", background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}>
        {/* Left: Graph (70%) */}
        <div className="flex-[7] relative">
          {isLoading ? (
            <div className="flex items-center justify-center h-full">
              <Activity size={20} className="animate-spin text-muted-foreground" />
              <span className="ml-2 text-sm text-muted-foreground">Loading...</span>
            </div>
          ) : error ? (
            <div className="flex items-center justify-center h-full">
              <AlertTriangle size={18} className="text-yellow-500 mr-2" />
              <span className="text-sm text-muted-foreground">Could not load lineage data</span>
            </div>
          ) : !graph || graph.nodes.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full gap-3">
              <Activity size={24} className="text-muted-foreground" />
              <p className="text-sm font-semibold text-foreground">No lineage data yet</p>
              <p className="text-xs text-muted-foreground max-w-xs text-center">
                Instrument your agents with the LangSight SDK. The graph builds automatically from traces.
              </p>
            </div>
          ) : (
            <LineageGraphComponent
              nodes={graphNodes}
              edges={graphEdges}
              selectedId={selectedNode?.id ?? null}
              onSelect={(id) => {
                setSelectedNode(id ? graph?.nodes.find((n) => n.id === id) ?? null : null);
              }}
              className="h-full"
            />
          )}
        </div>

        {/* Right: Detail (30%) */}
        <div
          className="flex-[3] border-l"
          style={{ borderColor: "hsl(var(--border))", background: "hsl(var(--background))" }}
        >
          {selectedNode ? (
            <DetailPanel node={selectedNode} allEdges={graph?.edges ?? []} />
          ) : (
            <EmptyDetail />
          )}
        </div>
      </div>
    </div>
  );
}
