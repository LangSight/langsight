"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import useSWR from "swr";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  Position,
  MarkerType,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import dagre from "dagre";
import { Bot, Server, AlertTriangle, Activity } from "lucide-react";
import { useProject } from "@/lib/project-context";
import { cn } from "@/lib/utils";

/* ── Types (matches backend) ───────────────────────────────── */
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
  { label: "1h",  hours: 1 },
  { label: "24h", hours: 24 },
  { label: "7d",  hours: 24 * 7 },
  { label: "30d", hours: 24 * 30 },
];

const NODE_WIDTH = 220;
const NODE_HEIGHT = 100;

/* ── Dagre layout ──────────────────────────────────────────── */
function layoutGraph(nodes: Node[], edges: Edge[]): { nodes: Node[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "LR", nodesep: 60, ranksep: 120 });

  nodes.forEach((n) => g.setNode(n.id, { width: NODE_WIDTH, height: NODE_HEIGHT }));
  edges.forEach((e) => g.setEdge(e.source, e.target));

  dagre.layout(g);

  const laid = nodes.map((n) => {
    const pos = g.node(n.id);
    return {
      ...n,
      position: { x: pos.x - NODE_WIDTH / 2, y: pos.y - NODE_HEIGHT / 2 },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
    };
  });

  return { nodes: laid, edges };
}

/* ── Custom node: Agent ────────────────────────────────────── */
function AgentNode({ data }: { data: { label: string; metrics: Record<string, number>; selected: boolean } }) {
  const m = data.metrics;
  const errorRate = m.total_calls > 0 ? (m.error_count / m.total_calls) * 100 : 0;
  return (
    <div
      className={cn(
        "rounded-xl border-2 p-4 min-w-[200px] transition-all",
        data.selected ? "border-primary shadow-lg shadow-primary/20" : "border-indigo-500/30",
      )}
      style={{ background: "hsl(var(--card))" }}
    >
      <div className="flex items-center gap-2 mb-2">
        <div className="w-7 h-7 rounded-lg flex items-center justify-center" style={{ background: "hsl(var(--primary) / 0.15)" }}>
          <Bot size={14} style={{ color: "hsl(var(--primary))" }} />
        </div>
        <span className="text-sm font-semibold text-foreground">{data.label}</span>
      </div>
      <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
        <span>{m.sessions ?? 0} sessions</span>
        <span>{m.total_calls ?? 0} calls</span>
        {errorRate > 0 && (
          <span className="text-red-400 font-semibold">{errorRate.toFixed(1)}% err</span>
        )}
      </div>
    </div>
  );
}

/* ── Custom node: Server ───────────────────────────────────── */
function ServerNode({ data }: { data: { label: string; metrics: Record<string, number>; selected: boolean } }) {
  const m = data.metrics;
  const errorRate = m.total_calls > 0 ? (m.error_count / m.total_calls) * 100 : 0;
  const isHealthy = errorRate < 1;
  return (
    <div
      className={cn(
        "rounded-xl border-2 p-4 min-w-[200px] transition-all",
        data.selected ? "border-primary shadow-lg shadow-primary/20"
          : isHealthy ? "border-emerald-500/30" : "border-yellow-500/30",
      )}
      style={{ background: "hsl(var(--card))" }}
    >
      <div className="flex items-center gap-2 mb-2">
        <div
          className="w-7 h-7 rounded-lg flex items-center justify-center"
          style={{ background: isHealthy ? "rgba(16,185,129,0.15)" : "rgba(234,179,8,0.15)" }}
        >
          <Server size={14} style={{ color: isHealthy ? "#10b981" : "#eab308" }} />
        </div>
        <span className="text-sm font-semibold text-foreground">{data.label}</span>
      </div>
      <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
        <span>{m.total_calls ?? 0} calls</span>
        <span>{Math.round(m.avg_latency_ms ?? 0)}ms avg</span>
        {errorRate > 0 && (
          <span className="text-red-400 font-semibold">{errorRate.toFixed(1)}% err</span>
        )}
      </div>
    </div>
  );
}

const nodeTypes = { agent: AgentNode, server: ServerNode };

/* ── Detail panel ──────────────────────────────────────────── */
function DetailPanel({ node, onClose }: { node: LineageNode; onClose: () => void }) {
  const m = node.metrics;
  return (
    <div
      className="absolute bottom-4 left-4 right-4 rounded-xl border p-5 z-10 shadow-xl"
      style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          {node.type === "agent"
            ? <Bot size={16} style={{ color: "hsl(var(--primary))" }} />
            : <Server size={16} style={{ color: "#10b981" }} />}
          <span className="font-semibold text-foreground">{node.label}</span>
          <span className="text-[10px] px-2 py-0.5 rounded-full font-medium" style={{
            background: node.type === "agent" ? "hsl(var(--primary) / 0.1)" : "rgba(16,185,129,0.1)",
            color: node.type === "agent" ? "hsl(var(--primary))" : "#10b981",
          }}>
            {node.type}
          </span>
        </div>
        <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
          <AlertTriangle size={0} className="hidden" />
          ✕
        </button>
      </div>
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: "Total Calls", value: m.total_calls?.toLocaleString() ?? "0" },
          { label: "Errors", value: m.error_count?.toLocaleString() ?? "0" },
          { label: "Avg Latency", value: `${Math.round(m.avg_latency_ms ?? 0)}ms` },
          { label: "Sessions", value: m.sessions?.toLocaleString() ?? m.called_by_agents?.toString() ?? "—" },
        ].map((stat) => (
          <div key={stat.label}>
            <p className="text-[10px] text-muted-foreground uppercase tracking-wider">{stat.label}</p>
            <p className="text-lg font-bold text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>{stat.value}</p>
          </div>
        ))}
      </div>
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
    async (url: string) => {
      const res = await fetch(url);
      if (!res.ok) throw new Error("Failed to load lineage");
      return res.json();
    },
    { refreshInterval: 60_000 }
  );

  // Convert backend graph to React Flow nodes/edges
  const { rfNodes, rfEdges } = useMemo(() => {
    if (!graph || graph.nodes.length === 0) return { rfNodes: [], rfEdges: [] };

    const nodes: Node[] = graph.nodes.map((n) => ({
      id: n.id,
      type: n.type,
      position: { x: 0, y: 0 },
      data: { label: n.label, metrics: n.metrics, selected: selectedNode?.id === n.id },
    }));

    const edges: Edge[] = graph.edges.map((e, i) => ({
      id: `e-${i}`,
      source: e.source,
      target: e.target,
      type: "default",
      animated: e.type === "handoff",
      style: {
        stroke: e.type === "handoff" ? "hsl(var(--primary))" : "hsl(var(--border))",
        strokeWidth: Math.min(4, 1 + Math.log10(Math.max(1, e.metrics.call_count ?? e.metrics.handoff_count ?? 1))),
      },
      label: e.type === "handoff"
        ? `${e.metrics.handoff_count ?? 0} handoffs`
        : `${e.metrics.call_count ?? 0} calls`,
      labelStyle: { fontSize: 10, fill: "hsl(var(--muted-foreground))" },
      labelBgStyle: { fill: "hsl(var(--background))", fillOpacity: 0.8 },
      markerEnd: { type: MarkerType.ArrowClosed, width: 12, height: 12 },
    }));

    return layoutGraph(nodes, edges);
  }, [graph, selectedNode]);

  const [nodes, setNodes, onNodesChange] = useNodesState(rfNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(rfEdges);

  useEffect(() => {
    if (rfNodes.length > 0) {
      setNodes(rfNodes);
      setEdges(rfEdges);
    }
  }, [rfNodes, rfEdges, setNodes, setEdges]);

  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    const orig = graph?.nodes.find((n) => n.id === node.id);
    setSelectedNode(orig ?? null);
  }, [graph]);

  return (
    <div className="space-y-4 page-in">
      {/* Header */}
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-foreground">Agent Lineage</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Dependency graph of agents, MCP servers, and tool calls — built from observed traces
          </p>
        </div>
        <div
          className="flex rounded-lg border p-0.5"
          style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
        >
          {WINDOWS.map((w) => (
            <button
              key={w.hours}
              onClick={() => setHours(w.hours)}
              className={cn(
                "px-3 py-1.5 rounded-md text-xs font-medium transition-all",
                w.hours === hours
                  ? "bg-primary text-white shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              {w.label}
            </button>
          ))}
        </div>
      </div>

      {/* Graph */}
      <div
        className="rounded-xl border relative"
        style={{
          background: "hsl(var(--card))",
          borderColor: "hsl(var(--border))",
          height: "calc(100vh - 12rem)",
        }}
      >
        {isLoading ? (
          <div className="flex items-center justify-center h-full">
            <Activity size={20} className="animate-spin text-muted-foreground" />
            <span className="ml-2 text-sm text-muted-foreground">Loading lineage graph...</span>
          </div>
        ) : error ? (
          <div className="flex items-center justify-center h-full">
            <AlertTriangle size={18} className="text-yellow-500 mr-2" />
            <span className="text-sm text-muted-foreground">Could not load lineage data</span>
          </div>
        ) : !graph || graph.nodes.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-3">
            <div className="w-14 h-14 rounded-2xl flex items-center justify-center" style={{ background: "hsl(var(--muted))" }}>
              <Activity size={24} className="text-muted-foreground" />
            </div>
            <p className="text-sm font-semibold text-foreground">No lineage data yet</p>
            <p className="text-xs text-muted-foreground max-w-sm text-center">
              Instrument your agents with the LangSight SDK to see the dependency graph.
              The lineage is built automatically from observed traces.
            </p>
          </div>
        ) : (
          <>
            <ReactFlow
              nodes={nodes}
              edges={edges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onNodeClick={onNodeClick}
              nodeTypes={nodeTypes}
              fitView
              minZoom={0.3}
              maxZoom={2}
              proOptions={{ hideAttribution: true }}
              style={{ background: "transparent" }}
            >
              <Background gap={20} size={1} color="hsl(var(--border))" />
              <Controls
                showInteractive={false}
                style={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: "0.75rem" }}
              />
              <MiniMap
                nodeColor={(n) => n.type === "agent" ? "hsl(var(--primary))" : "#10b981"}
                maskColor="hsl(var(--background) / 0.8)"
                style={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: "0.75rem" }}
              />
            </ReactFlow>
            {selectedNode && (
              <DetailPanel node={selectedNode} onClose={() => setSelectedNode(null)} />
            )}
          </>
        )}
      </div>

      {/* Legend */}
      {graph && graph.nodes.length > 0 && (
        <div className="flex items-center gap-6 text-[11px] text-muted-foreground">
          <span className="flex items-center gap-1.5">
            <div className="w-3 h-3 rounded border-2 border-indigo-500/50" /> Agent
          </span>
          <span className="flex items-center gap-1.5">
            <div className="w-3 h-3 rounded border-2 border-emerald-500/50" /> MCP Server
          </span>
          <span className="flex items-center gap-1.5">
            <div className="w-6 h-0.5 bg-indigo-500 rounded" /> Handoff (animated)
          </span>
          <span className="flex items-center gap-1.5">
            <div className="w-6 h-0.5 rounded" style={{ background: "hsl(var(--border))" }} /> Tool calls
          </span>
          <span className="ml-auto">Edge thickness = call volume · Click a node for details</span>
        </div>
      )}
    </div>
  );
}
