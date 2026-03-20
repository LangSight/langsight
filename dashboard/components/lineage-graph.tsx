"use client";

/**
 * SVG-based lineage graph — raw SVG + dagre layout.
 *
 * Inspired by DataHub's Visx-based lineage renderer.
 * No React Flow — full pixel control over nodes, edges, and arrows.
 */

import { useCallback, useMemo, useRef, useState } from "react";
import dagre from "dagre";
import { Bot, Server } from "lucide-react";
import { cn } from "@/lib/utils";

/* ── Types ─────────────────────────────────────────────────── */
export interface GraphNode {
  id: string;
  type: "agent" | "server";
  label: string;
  hasError: boolean;
  callCount?: number;
  meta?: Record<string, string | number>;
}

export interface GraphEdge {
  source: string;
  target: string;
  type: "calls" | "handoff";
  label?: string;
}

/* ── Constants ─────────────────────────────────────────────── */
const NODE_W = 220;
const NODE_H = 60;
const RANK_SEP = 160; // horizontal space between layers
const NODE_SEP = 50;  // vertical space between nodes
const HANDLE_R = 4;   // connection point radius
const ARROW_SIZE = 8;
const EDGE_COLOR = "#94a3b8";       // slate-400
const EDGE_HANDOFF = "#6366f1";     // indigo-500
const EDGE_WIDTH = 1.8;
const PADDING = 40;

/* ── Bezier path ───────────────────────────────────────────── */
function bezierPath(x1: number, y1: number, x2: number, y2: number): string {
  const midX = (x1 + x2) / 2;
  return `M ${x1},${y1} C ${midX},${y1} ${midX},${y2} ${x2},${y2}`;
}

/* ── Layout ────────────────────────────────────────────────── */
function layoutNodes(nodes: GraphNode[], edges: GraphEdge[]) {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "LR", nodesep: NODE_SEP, ranksep: RANK_SEP });

  nodes.forEach((n) => g.setNode(n.id, { width: NODE_W, height: NODE_H }));
  edges.forEach((e) => g.setEdge(e.source, e.target));
  dagre.layout(g);

  const positions = new Map<string, { x: number; y: number }>();
  nodes.forEach((n) => {
    const pos = g.node(n.id);
    positions.set(n.id, { x: pos.x - NODE_W / 2, y: pos.y - NODE_H / 2 });
  });

  // Compute bounds
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  positions.forEach(({ x, y }) => {
    minX = Math.min(minX, x);
    minY = Math.min(minY, y);
    maxX = Math.max(maxX, x + NODE_W);
    maxY = Math.max(maxY, y + NODE_H);
  });

  return {
    positions,
    width: maxX - minX + PADDING * 2,
    height: maxY - minY + PADDING * 2,
    offsetX: -minX + PADDING,
    offsetY: -minY + PADDING,
  };
}

/* ── Component ─────────────────────────────────────────────── */
export function LineageGraph({
  nodes,
  edges,
  selectedId,
  onSelect,
  className,
}: {
  nodes: GraphNode[];
  edges: GraphEdge[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  className?: string;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);
  const lastMouse = useRef({ x: 0, y: 0 });

  const layout = useMemo(() => layoutNodes(nodes, edges), [nodes, edges]);

  // Pan handlers
  const onMouseDown = useCallback((e: React.MouseEvent) => {
    if (e.button !== 0) return;
    setDragging(true);
    lastMouse.current = { x: e.clientX, y: e.clientY };
  }, []);

  const onMouseMove = useCallback((e: React.MouseEvent) => {
    if (!dragging) return;
    const dx = e.clientX - lastMouse.current.x;
    const dy = e.clientY - lastMouse.current.y;
    lastMouse.current = { x: e.clientX, y: e.clientY };
    setPan((p) => ({ x: p.x + dx, y: p.y + dy }));
  }, [dragging]);

  const onMouseUp = useCallback(() => setDragging(false), []);

  // Zoom handler
  const onWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? 0.9 : 1.1;
    setZoom((z) => Math.max(0.3, Math.min(2, z * delta)));
  }, []);

  if (nodes.length === 0) {
    return (
      <div className={cn("flex items-center justify-center text-sm text-muted-foreground", className)}>
        No lineage data
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className={cn("relative overflow-hidden cursor-grab active:cursor-grabbing", className)}
      onMouseDown={onMouseDown}
      onMouseMove={onMouseMove}
      onMouseUp={onMouseUp}
      onMouseLeave={onMouseUp}
      onWheel={onWheel}
      onClick={(e) => { if (e.target === e.currentTarget || (e.target as HTMLElement).tagName === "svg") onSelect(null); }}
    >
      <svg
        width="100%"
        height="100%"
        style={{ position: "absolute", top: 0, left: 0 }}
      >
        <defs>
          {/* Arrow marker — gray */}
          <marker
            id="arrow-gray"
            viewBox={`0 0 ${ARROW_SIZE} ${ARROW_SIZE}`}
            refX={ARROW_SIZE}
            refY={ARROW_SIZE / 2}
            markerWidth={ARROW_SIZE}
            markerHeight={ARROW_SIZE}
            orient="auto-start-reverse"
          >
            <path d={`M 0 0 L ${ARROW_SIZE} ${ARROW_SIZE / 2} L 0 ${ARROW_SIZE} Z`} fill={EDGE_COLOR} />
          </marker>
          {/* Arrow marker — indigo (handoffs) */}
          <marker
            id="arrow-indigo"
            viewBox={`0 0 ${ARROW_SIZE} ${ARROW_SIZE}`}
            refX={ARROW_SIZE}
            refY={ARROW_SIZE / 2}
            markerWidth={ARROW_SIZE}
            markerHeight={ARROW_SIZE}
            orient="auto-start-reverse"
          >
            <path d={`M 0 0 L ${ARROW_SIZE} ${ARROW_SIZE / 2} L 0 ${ARROW_SIZE} Z`} fill={EDGE_HANDOFF} />
          </marker>
        </defs>

        <g transform={`translate(${pan.x}, ${pan.y}) scale(${zoom})`}>
          <g transform={`translate(${layout.offsetX}, ${layout.offsetY})`}>
            {/* Edges */}
            {edges.map((edge, i) => {
              const srcPos = layout.positions.get(edge.source);
              const tgtPos = layout.positions.get(edge.target);
              if (!srcPos || !tgtPos) return null;

              const x1 = srcPos.x + NODE_W;
              const y1 = srcPos.y + NODE_H / 2;
              const x2 = tgtPos.x;
              const y2 = tgtPos.y + NODE_H / 2;
              const isHandoff = edge.type === "handoff";
              const color = isHandoff ? EDGE_HANDOFF : EDGE_COLOR;

              return (
                <g key={`edge-${i}`}>
                  <path
                    d={bezierPath(x1, y1, x2, y2)}
                    fill="none"
                    stroke={color}
                    strokeWidth={EDGE_WIDTH}
                    strokeDasharray={isHandoff ? "6,4" : "none"}
                    markerEnd={isHandoff ? "url(#arrow-indigo)" : "url(#arrow-gray)"}
                    className="transition-opacity"
                  />
                  {/* Edge label */}
                  {edge.label && (
                    <text
                      x={(x1 + x2) / 2}
                      y={(y1 + y2) / 2 - 8}
                      textAnchor="middle"
                      fill="#94a3b8"
                      fontSize={9}
                      fontWeight={600}
                    >
                      {edge.label}
                    </text>
                  )}
                  {/* Source handle dot */}
                  <circle cx={x1} cy={y1} r={HANDLE_R} fill={color} />
                  {/* Target handle dot */}
                  <circle cx={x2} cy={y2} r={HANDLE_R} fill={color} />
                </g>
              );
            })}

            {/* Nodes */}
            {nodes.map((node) => {
              const pos = layout.positions.get(node.id);
              if (!pos) return null;
              const isSelected = selectedId === node.id;
              const isAgent = node.type === "agent";

              return (
                <foreignObject
                  key={node.id}
                  x={pos.x}
                  y={pos.y}
                  width={NODE_W}
                  height={NODE_H}
                  className="cursor-pointer"
                  onClick={(e) => { e.stopPropagation(); onSelect(node.id); }}
                >
                  <div
                    className={cn(
                      "w-full h-full rounded-2xl px-4 flex items-center gap-3 transition-all",
                      isSelected ? "ring-2 ring-primary/50 shadow-lg" : "shadow-md hover:shadow-lg",
                    )}
                    style={{
                      background: "hsl(var(--card))",
                      border: isSelected ? "1.5px solid hsl(var(--primary))" : "1px solid hsl(var(--border))",
                    }}
                  >
                    <div
                      className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
                      style={{ background: isAgent ? "hsl(var(--primary) / 0.08)" : "rgba(100,116,139,0.08)" }}
                    >
                      {isAgent
                        ? <Bot size={15} style={{ color: "hsl(var(--primary))" }} />
                        : <Server size={15} className="text-muted-foreground" />}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5">
                        <span className="text-[12px] font-bold text-foreground truncate">{node.label}</span>
                        <span className={cn("w-2 h-2 rounded-full flex-shrink-0", node.hasError ? "bg-red-500" : "bg-emerald-500")} />
                      </div>
                      <span className="text-[10px] text-muted-foreground">
                        {isAgent ? "Agent" : "MCP Server"}
                        {node.callCount ? ` · ${node.callCount} calls` : ""}
                      </span>
                    </div>
                  </div>
                </foreignObject>
              );
            })}
          </g>
        </g>
      </svg>

      {/* Zoom controls */}
      <div
        className="absolute bottom-3 left-3 flex flex-col gap-1 rounded-lg overflow-hidden"
        style={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))" }}
      >
        <button
          onClick={() => setZoom((z) => Math.min(2, z * 1.2))}
          className="px-2.5 py-1.5 text-xs text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
        >
          +
        </button>
        <button
          onClick={() => setZoom((z) => Math.max(0.3, z * 0.8))}
          className="px-2.5 py-1.5 text-xs text-muted-foreground hover:text-foreground hover:bg-accent transition-colors border-t"
          style={{ borderColor: "hsl(var(--border))" }}
        >
          −
        </button>
        <button
          onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }); }}
          className="px-2.5 py-1.5 text-[9px] text-muted-foreground hover:text-foreground hover:bg-accent transition-colors border-t"
          style={{ borderColor: "hsl(var(--border))" }}
        >
          fit
        </button>
      </div>
    </div>
  );
}
