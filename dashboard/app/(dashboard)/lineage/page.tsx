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

/* ── Custom node: Agent (clean card style) ─────────────────── */
function AgentNode({ data }: { data: { label: string; metrics: Record<string, number>; selected: boolean } }) {
  return (
    <div
      className={cn(
        "rounded-2xl px-5 py-4 min-w-[180px] flex items-center gap-3.5 transition-all",
        data.selected
          ? "shadow-xl ring-2 ring-primary/40"
          : "shadow-md hover:shadow-lg hover:-translate-y-0.5",
      )}
      style={{
        background: "hsl(var(--card))",
        border: "1px solid hsl(var(--border))",
      }}
    >
      <div
        className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
        style={{ background: "hsl(var(--primary) / 0.1)" }}
      >
        <Bot size={18} style={{ color: "hsl(var(--primary))" }} />
      </div>
      <div>
        <p className="text-[13px] font-bold text-foreground leading-tight">{data.label}</p>
        <p className="text-[11px] text-muted-foreground mt-0.5">Agent</p>
      </div>
    </div>
  );
}

/* ── Custom node: Server (clean card style) ────────────────── */
function ServerNode({ data }: { data: { label: string; metrics: Record<string, number>; selected: boolean } }) {
  const m = data.metrics;
  const errorRate = m.total_calls > 0 ? (m.error_count / m.total_calls) * 100 : 0;
  const isHealthy = errorRate < 5;
  const accent = isHealthy ? "#10b981" : "#f59e0b";
  return (
    <div
      className={cn(
        "rounded-2xl px-5 py-4 min-w-[180px] flex items-center gap-3.5 transition-all",
        data.selected
          ? "shadow-xl ring-2 ring-primary/40"
          : "shadow-md hover:shadow-lg hover:-translate-y-0.5",
      )}
      style={{
        background: "hsl(var(--card))",
        border: "1px solid hsl(var(--border))",
      }}
    >
      <div
        className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
        style={{ background: `${accent}15` }}
      >
        <Server size={18} style={{ color: accent }} />
      </div>
      <div>
        <p className="text-[13px] font-bold text-foreground leading-tight">{data.label}</p>
        <p className="text-[11px] text-muted-foreground mt-0.5">MCP Server</p>
      </div>
    </div>
  );
}

const nodeTypes = { agent: AgentNode, server: ServerNode };

/* ── Right slide-over drawer ────────────────────────────────── */
function DetailDrawer({ node, edges, onClose }: {
  node: LineageNode;
  edges: LineageEdge[];
  onClose: () => void;
}) {
  const m = node.metrics;
  const isAgent = node.type === "agent";
  const accent = isAgent ? "hsl(var(--primary))" : "#10b981";

  // Find connected edges
  const connectedEdges = edges.filter(
    (e) => e.source === node.id || e.target === node.id
  );

  return (
    <>
      {/* Backdrop */}
      <div
        className="absolute inset-0 z-10"
        onClick={onClose}
        style={{ background: "transparent" }}
      />
      {/* Drawer */}
      <div
        className="absolute top-0 right-0 h-full w-[340px] z-20 border-l shadow-2xl overflow-y-auto"
        style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
      >
        {/* Header */}
        <div className="sticky top-0 z-10 px-5 py-4 border-b" style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: `${accent}15` }}>
                {isAgent ? <Bot size={18} style={{ color: accent }} /> : <Server size={18} style={{ color: accent }} />}
              </div>
              <div>
                <p className="text-sm font-bold text-foreground">{node.label}</p>
                <p className="text-[11px] text-muted-foreground">{isAgent ? "Agent" : "MCP Server"}</p>
              </div>
            </div>
            <button
              onClick={onClose}
              className="w-7 h-7 rounded-lg flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
            >
              ✕
            </button>
          </div>
        </div>

        {/* Metrics */}
        <div className="px-5 py-4">
          <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-widest mb-3">Metrics</p>
          <div className="grid grid-cols-2 gap-2">
            {[
              { label: "Total Calls", value: m.total_calls?.toLocaleString() ?? "0" },
              { label: "Errors", value: m.error_count?.toLocaleString() ?? "0" },
              { label: "Avg Latency", value: `${Math.round(m.avg_latency_ms ?? 0)}ms` },
              { label: isAgent ? "Sessions" : "Used by", value: (m.sessions ?? m.called_by_agents ?? 0).toLocaleString() },
            ].map((stat) => (
              <div key={stat.label} className="rounded-xl p-3" style={{ background: "hsl(var(--muted))" }}>
                <p className="text-[10px] text-muted-foreground font-medium mb-0.5">{stat.label}</p>
                <p className="text-lg font-bold text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>{stat.value}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Connections */}
        {connectedEdges.length > 0 && (
          <div className="px-5 py-4 border-t" style={{ borderColor: "hsl(var(--border))" }}>
            <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-widest mb-3">Connections</p>
            <div className="space-y-2">
              {connectedEdges.map((e, i) => {
                const isOutgoing = e.source === node.id;
                const otherNode = isOutgoing ? e.target : e.source;
                const otherLabel = otherNode.replace(/^(agent|server):/, "");
                const otherType = otherNode.startsWith("agent:") ? "Agent" : "MCP Server";
                const volume = e.metrics.call_count ?? e.metrics.handoff_count ?? 0;
                return (
                  <div
                    key={i}
                    className="flex items-center gap-3 rounded-lg p-2.5"
                    style={{ background: "hsl(var(--muted))" }}
                  >
                    <span className="text-[11px] text-muted-foreground w-6 text-center">
                      {isOutgoing ? "→" : "←"}
                    </span>
                    <div className="flex-1 min-w-0">
                      <p className="text-[12px] font-semibold text-foreground truncate">{otherLabel}</p>
                      <p className="text-[10px] text-muted-foreground">{otherType} · {e.type === "handoff" ? "handoff" : `${volume} calls`}</p>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Blast radius hint */}
        {!isAgent && (
          <div className="px-5 py-4 border-t" style={{ borderColor: "hsl(var(--border))" }}>
            <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-widest mb-2">Blast Radius</p>
            <p className="text-[12px] text-muted-foreground">
              If <strong className="text-foreground">{node.label}</strong> goes down,{" "}
              <strong className="text-foreground">
                {connectedEdges.filter((e) => e.target === node.id).length} agent{connectedEdges.filter((e) => e.target === node.id).length !== 1 ? "s" : ""}
              </strong>{" "}
              will be affected.
            </p>
          </div>
        )}
      </div>
    </>
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
      type: "smoothstep",
      animated: e.type === "handoff",
      style: {
        stroke: e.type === "handoff" ? "hsl(var(--primary))" : "hsl(var(--muted-foreground) / 0.3)",
        strokeWidth: e.type === "handoff" ? 2 : 1.5,
      },
      markerEnd: {
        type: MarkerType.ArrowClosed,
        width: 10,
        height: 10,
        color: e.type === "handoff" ? "hsl(var(--primary))" : "hsl(var(--muted-foreground) / 0.3)",
      },
    }));

    const laid = layoutGraph(nodes, edges);
    return { rfNodes: laid.nodes, rfEdges: laid.edges };
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
              onPaneClick={() => setSelectedNode(null)}
              nodeTypes={nodeTypes}
              fitView
              minZoom={0.3}
              maxZoom={2}
              proOptions={{ hideAttribution: true }}
              style={{ background: "transparent" }}
            >
              <Background gap={24} size={0.8} color="hsl(var(--muted-foreground) / 0.1)" />
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
              <DetailDrawer
                node={selectedNode}
                edges={graph?.edges ?? []}
                onClose={() => setSelectedNode(null)}
              />
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
