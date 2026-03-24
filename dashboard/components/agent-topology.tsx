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

      {/* Inline detail bar for selected node */}
      {selectedDetail && (
        <div className="flex-shrink-0 flex items-center gap-4 px-4 py-2 border-t" style={{ borderColor: "hsl(var(--border))", background: "hsl(var(--card))" }}>
          <div className="flex items-center gap-2">
            {selectedDetail.type === "agent"
              ? <Bot size={11} style={{ color: "hsl(var(--primary))" }} />
              : <Server size={11} className="text-muted-foreground" />}
            <span className="text-[11px] font-bold text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>{selectedDetail.label}</span>
            <span className="text-[9px] text-muted-foreground">{selectedDetail.type}</span>
          </div>
          <div className="flex items-center gap-4 text-[10px] ml-auto">
            {[
              { label: "Calls", value: String(selectedDetail.metrics.total_calls ?? 0) },
              { label: "Errors", value: String(selectedDetail.metrics.error_count ?? 0), danger: (selectedDetail.metrics.error_count ?? 0) > 0 },
              { label: "Avg Latency", value: `${Math.round(selectedDetail.metrics.avg_latency_ms ?? 0)}ms` },
              { label: "Sessions", value: String(selectedDetail.metrics.sessions ?? 0) },
            ].map((s) => (
              <div key={s.label} className="flex items-center gap-1.5">
                <span className="text-muted-foreground">{s.label}</span>
                <span className="font-semibold" style={{ fontFamily: "var(--font-geist-mono)", color: s.danger ? "#ef4444" : "hsl(var(--foreground))" }}>{s.value}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
