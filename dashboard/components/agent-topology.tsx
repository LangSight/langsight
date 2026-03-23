"use client";

import { useMemo, useState } from "react";
import { LineageGraph as LineageGraphComponent, type GraphNode, type GraphEdge } from "@/components/lineage-graph";
import { Bot, Server } from "lucide-react";
import { cn } from "@/lib/utils";
import type { LineageGraph } from "@/lib/types";

interface AgentTopologyProps {
  agentName: string;
  lineageGraph: LineageGraph | undefined;
  isLoading: boolean;
  className?: string;
}

export function AgentTopology({ agentName, lineageGraph, isLoading, className }: AgentTopologyProps) {
  const [selectedNode, setSelectedNode] = useState<string | null>(null);

  const { nodes, edges } = useMemo(() => {
    if (!lineageGraph) return { nodes: [] as GraphNode[], edges: [] as GraphEdge[] };

    const agentId = `agent:${agentName}`;
    const relevantEdges = lineageGraph.edges.filter(
      (e) => e.source === agentId || e.target === agentId,
    );

    const nodeIds = new Set<string>([agentId]);
    for (const e of relevantEdges) {
      nodeIds.add(e.source);
      nodeIds.add(e.target);
    }

    const gNodes: GraphNode[] = lineageGraph.nodes
      .filter((n) => nodeIds.has(n.id))
      .map((n) => ({
        id: n.id,
        type: n.type,
        label: n.label,
        hasError: (n.metrics.error_count ?? 0) > 0,
        callCount: n.metrics.total_calls ?? 0,
        errorCount: n.metrics.error_count ?? 0,
        avgLatencyMs: n.metrics.avg_latency_ms ?? 0,
      }));

    const gEdges: GraphEdge[] = relevantEdges.map((e) => ({
      source: e.source,
      target: e.target,
      type: e.type,
      label: e.type === "calls"
        ? (e.metrics.call_count > 1 ? `${e.metrics.call_count}×` : undefined)
        : (e.metrics.handoff_count > 1 ? `${e.metrics.handoff_count}×` : undefined),
      errorCount: e.metrics.error_count ?? 0,
      avgLatencyMs: e.metrics.avg_latency_ms ?? 0,
    }));

    return { nodes: gNodes, edges: gEdges };
  }, [lineageGraph, agentName]);

  // Detail for selected node
  const selectedDetail = useMemo(() => {
    if (!selectedNode || !lineageGraph) return null;
    const node = lineageGraph.nodes.find((n) => n.id === selectedNode);
    if (!node) return null;
    return node;
  }, [selectedNode, lineageGraph]);

  if (isLoading) {
    return <div className={cn("flex items-center justify-center", className ?? "h-[350px]")}><div className="skeleton w-full h-full rounded-lg" /></div>;
  }

  if (nodes.length === 0) {
    return (
      <div className={cn("flex flex-col items-center justify-center text-muted-foreground", className ?? "h-[200px]")}>
        <Server size={24} className="mb-2 opacity-40" />
        <p className="text-[12px]">No topology data for this agent</p>
        <p className="text-[10px] mt-0.5">Requires ClickHouse with trace data</p>
      </div>
    );
  }

  return (
    <div className={cn("flex flex-col", className)}>
      <div className="flex-1 min-h-0 rounded-lg overflow-hidden" style={{ border: className ? "none" : "1px solid hsl(var(--border))", background: "hsl(var(--card))" }}>
        <LineageGraphComponent
          nodes={nodes}
          edges={edges}
          selectedId={selectedNode}
          onSelect={setSelectedNode}
          nodeHeight={76}
          className="h-full"
        />
      </div>

      {/* Inline detail card for selected node */}
      {selectedDetail && (
        <div className="mt-3 rounded-lg px-4 py-3" style={{ background: "hsl(var(--muted))", border: "1px solid hsl(var(--border))" }}>
          <div className="flex items-center gap-2 mb-2">
            {selectedDetail.type === "agent"
              ? <Bot size={12} style={{ color: "hsl(var(--primary))" }} />
              : <Server size={12} className="text-muted-foreground" />}
            <span className="text-[12px] font-bold text-foreground">{selectedDetail.label}</span>
            <span className="text-[9px] text-muted-foreground">{selectedDetail.type}</span>
          </div>
          <div className="grid grid-cols-4 gap-3 text-[10px]">
            <div>
              <span className="text-muted-foreground">Calls</span>
              <p className="font-bold text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>{selectedDetail.metrics.total_calls ?? 0}</p>
            </div>
            <div>
              <span className="text-muted-foreground">Errors</span>
              <p className="font-bold" style={{ color: (selectedDetail.metrics.error_count ?? 0) > 0 ? "#ef4444" : "hsl(var(--foreground))", fontFamily: "var(--font-geist-mono)" }}>{selectedDetail.metrics.error_count ?? 0}</p>
            </div>
            <div>
              <span className="text-muted-foreground">Avg Latency</span>
              <p className="font-bold text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>{Math.round(selectedDetail.metrics.avg_latency_ms ?? 0)}ms</p>
            </div>
            <div>
              <span className="text-muted-foreground">Sessions</span>
              <p className="font-bold text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>{selectedDetail.metrics.sessions ?? 0}</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
