"use client";

/**
 * SVG-based lineage graph — raw SVG + dagre layout.
 *
 * Features: node drag, pan/zoom, edge click/hover, node hover preview,
 * search with highlight, zoom slider, minimap, error path toggle,
 * expand/collapse, keyboard shortcuts, glass-morphism nodes, edge flow animation.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import dagre from "dagre";
import { Bot, Server, Zap, Search, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";

/* ── Types ─────────────────────────────────────────────────── */
export interface GraphNode {
  id: string;
  type: "agent" | "server";
  label: string;
  hasError: boolean;
  callCount?: number;
  isLlmCallCount?: boolean;  // true when callCount reflects LLM spans (no direct MCP calls)
  meta?: Record<string, string | number>;
  errorCount?: number;
  avgLatencyMs?: number;
  groupId?: string;
  splitLabel?: string;
  isCollapsible?: boolean;
  collapsedCount?: number;
  expandableEdgeId?: string;
  expandItemCount?: number;
  toolNames?: string[];
  repeatCallName?: string;
  repeatCallCount?: number;
  spanId?: string;  // for linking tool call nodes to delegation edges
}

export interface GraphEdge {
  source: string;
  target: string;
  type: "calls" | "handoff";
  label?: string;
  edgeId?: string;
  errorCount?: number;
  avgLatencyMs?: number;
}

export type GraphSelection =
  | { type: "node"; id: string }
  | { type: "edge"; edgeId: string; source: string; target: string }
  | null;

/* ── Constants ─────────────────────────────────────────────── */
const NODE_W = 250;
const DEFAULT_NODE_H = 60;
const TOOL_EXPAND_ROW_H = 18;
const RANK_SEP = 180;
const NODE_SEP = 56;
const HANDLE_R = 5;
const ARROW_SIZE = 7;
const PADDING = 60;
const MINIMAP_W = 150;
const MINIMAP_H = 90;

/* ── Colors ────────────────────────────────────────────────── */
const C_EDGE = "rgba(148,163,184,0.55)";
const C_HANDOFF = "rgba(20,184,166,0.7)";
const C_SELECTED = "#2DD4BF";

/* ── Path helpers ──────────────────────────────────────────── */
function bezier(x1: number, y1: number, x2: number, y2: number) {
  const mx = (x1 + x2) / 2;
  return `M ${x1},${y1} C ${mx},${y1} ${mx},${y2} ${x2},${y2}`;
}
function selfLoop(x: number, y: number, w: number, h: number) {
  const sx = x + w, sy = y + h * 0.3, ey = y + h * 0.7, b = 80;
  return `M ${sx},${sy} C ${sx + b},${sy - b * 0.6} ${sx + b},${ey + b * 0.6} ${sx},${ey}`;
}

/* ── Layout ────────────────────────────────────────────────── */
function nodeH(n: GraphNode, base: number) {
  return n.expandableEdgeId && (n.expandItemCount ?? 0) >= 1 ? base + TOOL_EXPAND_ROW_H : base;
}

function layout(nodes: GraphNode[], edges: GraphEdge[], baseH: number) {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "LR", nodesep: NODE_SEP, ranksep: RANK_SEP });
  const heights = new Map<string, number>();
  nodes.forEach((n) => { const h = nodeH(n, baseH); heights.set(n.id, h); g.setNode(n.id, { width: NODE_W, height: h }); });
  edges.forEach((e) => { if (e.source !== e.target) g.setEdge(e.source, e.target); });
  dagre.layout(g);
  const pos = new Map<string, { x: number; y: number }>();
  nodes.forEach((n) => { const p = g.node(n.id); const h = heights.get(n.id)!; if (p) pos.set(n.id, { x: p.x - NODE_W / 2, y: p.y - h / 2 }); });
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  pos.forEach(({ x, y }, id) => { const h = heights.get(id)!; minX = Math.min(minX, x); minY = Math.min(minY, y); maxX = Math.max(maxX, x + NODE_W); maxY = Math.max(maxY, y + h); });
  return { pos, heights, offX: -minX + PADDING, offY: -minY + PADDING, w: maxX - minX + PADDING * 2, h: maxY - minY + PADDING * 2 };
}

function backEdgeSet(edges: GraphEdge[]) {
  const fwd = new Set<string>(), back = new Set<string>();
  for (const e of edges) { const k = `${e.source}→${e.target}`, r = `${e.target}→${e.source}`; if (fwd.has(r)) back.add(k); else fwd.add(k); }
  return back;
}

/* ── Component ─────────────────────────────────────────────── */
export function LineageGraph({
  nodes, edges,
  selectedId, onSelect,
  selection, onSelectionChange,
  expandedGroups, onToggleGroup,
  expandedEdges, onToggleEdge,
  onExpandAll, onCollapseAll,
  nodeHeight, className,
}: {
  nodes: GraphNode[];
  edges: GraphEdge[];
  selectedId?: string | null;
  onSelect?: (id: string | null) => void;
  selection?: GraphSelection;
  onSelectionChange?: (sel: GraphSelection) => void;
  expandedGroups?: Set<string>;
  onToggleGroup?: (groupId: string) => void;
  expandedEdges?: Set<string>;
  onToggleEdge?: (edgeId: string) => void;
  onExpandAll?: () => void;
  onCollapseAll?: () => void;
  nodeHeight?: number;
  className?: string;
}) {
  const baseH = nodeHeight ?? DEFAULT_NODE_H;
  const sel: GraphSelection = selection ?? (selectedId ? { type: "node", id: selectedId } : null);
  const doSelect = useCallback((s: GraphSelection) => { if (onSelectionChange) onSelectionChange(s); else onSelect?.(s?.type === "node" ? s.id : null); }, [onSelectionChange, onSelect]);
  
  // Stable ref for event handlers to prevent useEffect re-binding
  const doSelectRef = useRef(doSelect);
  useEffect(() => { doSelectRef.current = doSelect; }, [doSelect]);


  const containerRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  /* ── State ── */
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [panning, setPanning] = useState(false);
  const [dragNodeId, setDragNodeId] = useState<string | null>(null);
  const [nodeOffsets, setNodeOffsets] = useState<Map<string, { dx: number; dy: number }>>(new Map());
  const lastMouse = useRef({ x: 0, y: 0 });

  const [hoveredEdge, setHoveredEdge] = useState<{ edge: GraphEdge; x: number; y: number } | null>(null);
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);

  const [searchQ, setSearchQ] = useState("");
  const [showErrors, setShowErrors] = useState(false);
  const [containerSize, setContainerSize] = useState({ w: 0, h: 0 });

  /* ── Layout ── */
  const base = useMemo(() => layout(nodes, edges, baseH), [nodes, edges, baseH]);
  const backs = useMemo(() => backEdgeSet(edges), [edges]);

  // Effective positions = dagre + user drag offsets
  const positions = useMemo(() => {
    const r = new Map<string, { x: number; y: number }>();
    for (const [id, p] of base.pos) { const o = nodeOffsets.get(id); r.set(id, o ? { x: p.x + o.dx, y: p.y + o.dy } : p); }
    return r;
  }, [base.pos, nodeOffsets]);

  // Reset offsets when node count changes (expand/collapse)
  const prevLen = useRef(nodes.length);
  if (nodes.length !== prevLen.current) { prevLen.current = nodes.length; if (nodeOffsets.size > 0) setNodeOffsets(new Map()); }

  /* ── Fit & center ── */
  const fitToCenter = useCallback(() => {
    if (!containerSize.w || !containerSize.h || !base.w || !base.h) return;
    const fitZoom = Math.min(containerSize.w / base.w, containerSize.h / base.h, 1.2);
    const fitPanX = (containerSize.w - base.w * fitZoom) / 2;
    const fitPanY = (containerSize.h - base.h * fitZoom) / 2;
    setZoom(fitZoom);
    setPan({ x: fitPanX, y: fitPanY });
    setNodeOffsets(new Map());
  }, [containerSize.w, containerSize.h, base.w, base.h]);

  // Auto-center on first render when layout + container size are both known
  const hasFitted = useRef(false);
  useEffect(() => {
    if (hasFitted.current) return;
    if (containerSize.w > 0 && containerSize.h > 0 && nodes.length > 0 && base.w > 0) {
      hasFitted.current = true;
      fitToCenter();
    }
  }, [containerSize.w, containerSize.h, nodes.length, base.w, fitToCenter]);

  /* ── Search ── */
  const matchIds = useMemo(() => {
    if (!searchQ.trim()) return null;
    const q = searchQ.toLowerCase();
    return new Set(nodes.filter((n) => n.label.toLowerCase().includes(q) || (n.splitLabel ?? "").toLowerCase().includes(q)).map((n) => n.id));
  }, [nodes, searchQ]);

  /* ── Error path ── */
  const errorIds = useMemo(() => {
    if (!showErrors) return null;
    const nids = new Set(nodes.filter((n) => n.hasError || (n.errorCount ?? 0) > 0).map((n) => n.id));
    const ekeys = new Set<string>();
    for (const e of edges) {
      if ((e.errorCount ?? 0) > 0 || nids.has(e.source) || nids.has(e.target)) {
        ekeys.add(`${e.source}→${e.target}`); nids.add(e.source); nids.add(e.target);
      }
    }
    return { n: nids, e: ekeys };
  }, [showErrors, nodes, edges]);

  /* ── Minimap ── */
  useEffect(() => {
    if (!containerRef.current) return;
    const ro = new ResizeObserver(([e]) => setContainerSize({ w: e.contentRect.width, h: e.contentRect.height }));
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, []);

  const minimap = useMemo(() => {
    if (positions.size === 0) return null;
    let mnx = Infinity, mny = Infinity, mxx = -Infinity, mxy = -Infinity;
    for (const [id, p] of positions) { const h = base.heights.get(id) ?? baseH; mnx = Math.min(mnx, p.x); mny = Math.min(mny, p.y); mxx = Math.max(mxx, p.x + NODE_W); mxy = Math.max(mxy, p.y + h); }
    const gw = mxx - mnx + PADDING * 2, gh = mxy - mny + PADDING * 2;
    return { mnx: mnx - PADDING, mny: mny - PADDING, gw, gh, s: Math.min(MINIMAP_W / gw, MINIMAP_H / gh) };
  }, [positions, base.heights, baseH]);

  /* ── Keyboard shortcuts ── */
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const tag = (document.activeElement?.tagName ?? "").toLowerCase();
      if (tag === "input" || tag === "textarea" || tag === "select") return;
      switch (e.key) {
        case "Escape": doSelectRef.current(null); setSearchQ(""); setShowErrors(false); break;
        case "+": case "=": e.preventDefault(); setZoom((z) => Math.min(2.5, z * 1.15)); break;
        case "-": e.preventDefault(); setZoom((z) => Math.max(0.25, z * 0.85)); break;
        case "f": e.preventDefault(); fitToCenter(); break;
        case "/": e.preventDefault(); searchRef.current?.focus(); break;
        case "e": e.preventDefault(); setShowErrors((v) => !v); break;
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []); // Empty dependency array ensures listener attaches only once

  /* ── Mouse handlers ── */
  const onBgDown = useCallback((e: React.MouseEvent) => { if (e.button === 0) { setPanning(true); lastMouse.current = { x: e.clientX, y: e.clientY }; } }, []);
  const onMove = useCallback((e: React.MouseEvent) => {
    const dx = e.clientX - lastMouse.current.x, dy = e.clientY - lastMouse.current.y;
    lastMouse.current = { x: e.clientX, y: e.clientY };
    if (dragNodeId) setNodeOffsets((p) => { const n = new Map(p); const ex = n.get(dragNodeId) ?? { dx: 0, dy: 0 }; n.set(dragNodeId, { dx: ex.dx + dx / zoom, dy: ex.dy + dy / zoom }); return n; });
    else if (panning) setPan((p) => ({ x: p.x + dx, y: p.y + dy }));
  }, [dragNodeId, panning, zoom]);
  const onUp = useCallback(() => { setPanning(false); setDragNodeId(null); }, []);
  const onWheel = useCallback((e: React.WheelEvent) => { e.preventDefault(); setZoom((z) => Math.max(0.25, Math.min(2.5, z * (e.deltaY > 0 ? 0.92 : 1.08)))); }, []);
  const onNodeDown = useCallback((e: React.MouseEvent, id: string) => { e.stopPropagation(); if (e.button === 0) { setDragNodeId(id); lastMouse.current = { x: e.clientX, y: e.clientY }; } }, []);

  /* ── Opacity helpers ── */
  function nodeOpacity(id: string, hasError: boolean) {
    let o = 1;
    if (matchIds !== null && !matchIds.has(id)) o *= 0.25;
    if (errorIds !== null && !errorIds.n.has(id)) o *= 0.12;
    return o;
  }
  function edgeOpacity(src: string, tgt: string, isBack: boolean, isSel: boolean) {
    let o = isBack && !isSel ? 0.4 : 1;
    if (matchIds !== null && !(matchIds.has(src) && matchIds.has(tgt))) o *= 0.12;
    if (errorIds !== null && !errorIds.e.has(`${src}→${tgt}`)) o *= 0.12;
    return o;
  }

  if (nodes.length === 0) return <div className={cn("flex items-center justify-center text-sm text-muted-foreground", className)}>No lineage data</div>;

  return (
    <div ref={containerRef} className={cn("relative overflow-hidden select-none", className)}
      style={{ cursor: dragNodeId ? "grabbing" : panning ? "grabbing" : "grab" }}
      onMouseDown={onBgDown} onMouseMove={onMove} onMouseUp={onUp} onMouseLeave={onUp} onWheel={onWheel}
      onClick={(e) => { if (e.target === e.currentTarget || (e.target as HTMLElement).tagName === "svg") doSelect(null); }}
    >
      <svg width="100%" height="100%" style={{ position: "absolute", top: 0, left: 0 }}>
        <defs>
          {[{ id: "arrow-gray", fill: "rgba(148,163,184,0.7)" }, { id: "arrow-teal", fill: "rgba(20,184,166,0.85)" }, { id: "arrow-sel", fill: C_SELECTED }].map(({ id, fill }) => (
            <marker key={id} id={id} viewBox={`0 0 ${ARROW_SIZE} ${ARROW_SIZE}`} refX={ARROW_SIZE} refY={ARROW_SIZE / 2} markerWidth={ARROW_SIZE} markerHeight={ARROW_SIZE} orient="auto-start-reverse">
              <path d={`M 0 0 L ${ARROW_SIZE} ${ARROW_SIZE / 2} L 0 ${ARROW_SIZE} Z`} fill={fill} />
            </marker>
          ))}
          <filter id="glow-pri" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="6" result="b" /><feFlood floodColor="#14B8A6" floodOpacity="0.3" /><feComposite in2="b" operator="in" /><feMerge><feMergeNode /><feMergeNode in="SourceGraphic" /></feMerge></filter>
          <filter id="glow-err" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="5" result="b" /><feFlood floodColor="#ef4444" floodOpacity="0.25" /><feComposite in2="b" operator="in" /><feMerge><feMergeNode /><feMergeNode in="SourceGraphic" /></feMerge></filter>
          <filter id="glow-search" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="5" result="b" /><feFlood floodColor="#f59e0b" floodOpacity="0.35" /><feComposite in2="b" operator="in" /><feMerge><feMergeNode /><feMergeNode in="SourceGraphic" /></feMerge></filter>
        </defs>

        <g transform={`translate(${pan.x},${pan.y}) scale(${zoom})`}>
          <g transform={`translate(${base.offX},${base.offY})`}>
            {/* ── Edges ── */}
            {edges.map((edge, i) => {
              const sp = positions.get(edge.source), tp = positions.get(edge.target);
              if (!sp || !tp) return null;
              const self = edge.source === edge.target, ho = edge.type === "handoff";
              const eid = edge.edgeId ?? `${edge.source}→${edge.target}`;
              const isSel = sel?.type === "edge" && sel.source === edge.source && sel.target === edge.target;
              const isBack = backs.has(`${edge.source}→${edge.target}`);
              const hasErr = (edge.errorCount ?? 0) > 0;
              const color = isSel ? C_SELECTED : hasErr ? "rgba(239,68,68,0.5)" : ho ? C_HANDOFF : C_EDGE;
              const w = isSel ? 2.5 : 1.5;
              const op = edgeOpacity(edge.source, edge.target, isBack, isSel);
              const sH = base.heights.get(edge.source) ?? baseH, tH = base.heights.get(edge.target) ?? baseH;
              let d: string, lx: number, ly: number;
              if (self) { d = selfLoop(sp.x, sp.y, NODE_W, sH); lx = sp.x + NODE_W + 45; ly = sp.y + sH / 2; }
              else { const x1 = sp.x + NODE_W, y1 = sp.y + sH / 2, x2 = tp.x, y2 = tp.y + tH / 2; d = bezier(x1, y1, x2, y2); lx = (x1 + x2) / 2; ly = (y1 + y2) / 2 - 10; }
              const mk = isSel ? "url(#arrow-sel)" : ho ? "url(#arrow-teal)" : "url(#arrow-gray)";
              return (
                <g key={`e-${i}`} opacity={op}>
                  <path d={d} fill="none" stroke="transparent" strokeWidth={16} className="cursor-pointer"
                    onClick={(e) => { e.stopPropagation(); doSelect({ type: "edge", edgeId: eid, source: edge.source, target: edge.target }); }}
                    onMouseEnter={(e) => setHoveredEdge({ edge, x: e.clientX, y: e.clientY })} onMouseLeave={() => setHoveredEdge(null)} />
                  <path d={d} fill="none" stroke={color} strokeWidth={w} strokeDasharray={ho ? "6,4" : isBack ? "4,3" : "none"} markerEnd={mk} className="pointer-events-none" style={{ transition: "stroke 0.2s" }} />
                  {!isBack && !self && <path d={d} fill="none" stroke={isSel ? "rgba(45,212,191,0.4)" : "rgba(148,163,184,0.12)"} strokeWidth={isSel ? 4 : 2} strokeDasharray="4,12" className="pointer-events-none edge-flow-anim" />}
                  {(() => {
                    const canExpandEdge = edge.edgeId && onToggleEdge;
                    const isEdgeExp = edge.edgeId ? expandedEdges?.has(edge.edgeId) : false;
                    const tgtNode = nodes.find((n) => n.id === edge.target);
                    const hasMultiCalls = (tgtNode?.expandItemCount ?? 0) >= 1;
                    // Also check for group expand on target node
                    const tgtCollapsible = tgtNode?.isCollapsible && tgtNode?.collapsedCount != null && onToggleGroup;
                    const tgtGid = tgtNode?.groupId ?? tgtNode?.id ?? "";
                    const tgtGroupExp = expandedGroups?.has(tgtGid);
                    // Show per-tool button if edge has multi tools
                    const showToolBtn = canExpandEdge && hasMultiCalls;
                    // Show group button if target is collapsible and NOT yet expanded
                    const showGroupBtn = tgtCollapsible && !tgtGroupExp;
                    // Show either tool or group button (prioritize group)
                    const showBtn = showGroupBtn || showToolBtn;
                    const btnX = lx + 22;
                    const showAny = edge.label || showBtn || (tgtNode?.splitLabel && tgtNode?.groupId);
                    if (!showAny) return null;
                    return (
                      <g>
                        {/* Label pill */}
                        {edge.label && <>
                          <rect x={lx - 16} y={ly - 9} width={32} height={16} rx={5} fill="hsl(var(--card))" stroke="hsl(var(--border))" strokeWidth={0.5} opacity={0.9} className="pointer-events-none" />
                          <text x={lx} y={ly + 2} textAnchor="middle" fill={isSel ? C_SELECTED : "hsl(var(--muted-foreground))"} fontSize={8} fontWeight={600} fontFamily="var(--font-geist-mono)" className="pointer-events-none">{edge.label}</text>
                        </>}
                        {/* Circular expand/collapse button */}
                        {showBtn && (
                          <g className="cursor-pointer" onClick={(e) => {
                            e.stopPropagation();
                            if (showGroupBtn) onToggleGroup!(tgtGid);
                            else if (showToolBtn) onToggleEdge!(edge.edgeId!);
                          }}>
                            <circle cx={btnX} cy={ly} r={9} fill="hsl(var(--primary))" opacity={0.9} />
                            <text x={btnX} y={ly + 3.5} textAnchor="middle" fill="white" fontSize={11} fontWeight={700}>+</text>
                          </g>
                        )}
                        {/* Collapse button — on edges to split nodes */}
                        {!showBtn && tgtNode?.splitLabel && tgtNode?.groupId && expandedGroups?.has(tgtNode.groupId) && onToggleGroup && (
                          <g className="cursor-pointer" onClick={(e) => { e.stopPropagation(); onToggleGroup!(tgtNode.groupId!); }}>
                            <circle cx={btnX} cy={ly} r={9} fill="hsl(var(--muted))" stroke="hsl(var(--border))" strokeWidth={0.5} />
                            <text x={btnX} y={ly + 3.5} textAnchor="middle" fill="hsl(var(--muted-foreground))" fontSize={11} fontWeight={700}>{"\u2212"}</text>
                          </g>
                        )}
                        {/* Per-tool collapse — on edges where tools are expanded */}
                        {!showBtn && !tgtNode?.splitLabel && isEdgeExp && canExpandEdge && (
                          <g className="cursor-pointer" onClick={(e) => { e.stopPropagation(); onToggleEdge!(edge.edgeId!); }}>
                            <circle cx={btnX} cy={ly} r={9} fill="hsl(var(--muted))" stroke="hsl(var(--border))" strokeWidth={0.5} />
                            <text x={btnX} y={ly + 3.5} textAnchor="middle" fill="hsl(var(--muted-foreground))" fontSize={11} fontWeight={700}>{"\u2212"}</text>
                          </g>
                        )}
                      </g>
                    );
                  })()}
                  {/* Collapse button on label-less edges (single-call per-tool splits) */}
                  {!edge.label && edge.edgeId && expandedEdges?.has(edge.edgeId) && onToggleEdge && !self && (() => {
                    return (
                      <g className="cursor-pointer" onClick={(e) => { e.stopPropagation(); onToggleEdge!(edge.edgeId!); }}>
                        <circle cx={lx} cy={ly} r={9} fill="hsl(var(--muted))" stroke="hsl(var(--border))" strokeWidth={0.5} />
                        <text x={lx} y={ly + 3.5} textAnchor="middle" fill="hsl(var(--muted-foreground))" fontSize={11} fontWeight={700}>{"\u2212"}</text>
                      </g>
                    );
                  })()}
                  {!self && (() => { const x1 = sp.x + NODE_W, y1 = sp.y + sH / 2, x2 = tp.x, y2 = tp.y + tH / 2; return <><circle cx={x1} cy={y1} r={HANDLE_R} fill={color} opacity={0.6} className="pointer-events-none" /><circle cx={x2} cy={y2} r={HANDLE_R} fill={color} opacity={0.6} className="pointer-events-none" /></>; })()}
                </g>
              );
            })}

            {/* ── Nodes ── */}
            {nodes.map((node) => {
              const p = positions.get(node.id);
              if (!p) return null;
              const h = base.heights.get(node.id) ?? baseH;
              const isSel = sel?.type === "node" && sel.id === node.id;
              const isHov = hoveredNode === node.id;
              const isAgent = node.type === "agent";
              const isToolCall = !isAgent && !!node.splitLabel; // expanded individual call node
              const hasMet = node.errorCount != null || node.avgLatencyMs != null || (node.callCount != null && node.callCount > 0);
              const errRate = (node.callCount && node.errorCount) ? node.errorCount / node.callCount : 0;
              const op = nodeOpacity(node.id, node.hasError);
              const searchMatch = matchIds !== null && matchIds.has(node.id);
              const glow = searchMatch ? "url(#glow-search)" : isSel ? "url(#glow-pri)" : node.hasError && !isSel ? "url(#glow-err)" : undefined;
              const canExpandCalls = node.expandableEdgeId && (node.expandItemCount ?? 0) >= 1;
              const isCallsExpanded = node.expandableEdgeId ? expandedEdges?.has(node.expandableEdgeId) : false;
              const expandPreview = node.repeatCallCount && node.repeatCallName
                ? `repeated ${node.repeatCallName} ${node.repeatCallCount}×`
                : node.toolNames?.slice(0, 2).join(", ");

              return (
                <g key={node.id} filter={glow} opacity={op} style={{ transition: "opacity 0.3s, filter 0.3s" }}>
                  <foreignObject x={p.x} y={p.y} width={NODE_W} height={h}
                    style={{ cursor: dragNodeId === node.id ? "grabbing" : "pointer" }}
                    onMouseDown={(e) => onNodeDown(e, node.id)}
                    onClick={(e) => { e.stopPropagation(); if (!dragNodeId) doSelect({ type: "node", id: node.id }); }}
                    onMouseEnter={() => setHoveredNode(node.id)}
                    onMouseLeave={() => setHoveredNode(null)}
                  >
                    <div className="w-full h-full rounded-xl px-4 py-2.5 flex flex-col justify-center"
                      style={{
                        background: isSel
                          ? "linear-gradient(135deg, hsl(var(--card)) 0%, hsl(var(--primary) / 0.06) 100%)"
                          : isAgent
                            ? "linear-gradient(135deg, hsl(var(--card)) 0%, hsl(var(--primary) / 0.02) 100%)"
                            : "hsl(var(--card))",
                        border: isSel ? "1.5px solid hsl(var(--primary) / 0.6)" : node.hasError ? "1px solid rgba(239,68,68,0.3)" : "1px solid hsl(var(--border))",
                        boxShadow: isSel
                          ? "0 0 24px rgba(20,184,166,0.18), 0 8px 16px rgba(0,0,0,0.12)"
                          : isHov
                            ? "0 8px 28px rgba(0,0,0,0.16), 0 0 0 1px hsl(var(--primary) / 0.18)"
                            : "0 2px 10px rgba(0,0,0,0.08), 0 0 0 0.5px hsl(var(--border))",
                        transition: "all 0.2s ease",
                        backdropFilter: "blur(12px)",
                      }}
                    >
                      {/* Row 1 — identity */}
                      <div className="flex items-center gap-2.5">
                        <div className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
                          style={{
                            background: isAgent
                              ? "linear-gradient(135deg, hsl(var(--primary) / 0.15), hsl(var(--primary) / 0.06))"
                              : isToolCall
                                ? "linear-gradient(135deg, rgba(245,158,11,0.14), rgba(245,158,11,0.05))"
                                : "linear-gradient(135deg, rgba(100,116,139,0.14), rgba(100,116,139,0.05))",
                            border: isAgent
                              ? "1px solid hsl(var(--primary) / 0.2)"
                              : isToolCall
                                ? "1px solid rgba(245,158,11,0.2)"
                                : "1px solid rgba(100,116,139,0.15)",
                          }}>
                          {isAgent
                            ? <Bot size={14} style={{ color: "hsl(var(--primary))" }} />
                            : isToolCall
                              ? <Zap size={13} style={{ color: "rgba(245,158,11,0.85)" }} />
                              : <Server size={14} className="text-muted-foreground" />}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-1.5">
                            <span className="text-[12px] font-bold text-foreground truncate" style={{ letterSpacing: "-0.01em" }}>{node.label}</span>
                            <span className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{
                              background: node.hasError ? "#ef4444" : "#10b981",
                              boxShadow: node.hasError ? "0 0 8px rgba(239,68,68,0.5)" : "0 0 6px rgba(16,185,129,0.35)",
                              animation: node.hasError ? "pulse 2s ease-in-out infinite" : undefined,
                            }} />
                          </div>
                          <span className="text-[10px] text-muted-foreground block truncate" style={{ marginTop: 1 }}>
                            {isAgent ? "Agent" : isToolCall ? "Tool Call" : "MCP Server"}{node.splitLabel ? ` \u00b7 ${node.splitLabel}` : ""}
                          </span>
                        </div>
                      </div>
                      {/* Row 2: metric pills */}
                      {hasMet && (
                        <div className="flex items-center flex-wrap gap-1.5 mt-1.5">
                          {node.callCount != null && node.callCount > 0 && <span className="text-[8px] px-1.5 py-[2px] rounded-full" style={{ background: "hsl(var(--muted))", color: "hsl(var(--muted-foreground))", fontFamily: "var(--font-geist-mono)" }}>{node.callCount} {node.isLlmCallCount ? "LLM" : node.callCount === 1 ? "call" : "calls"}</span>}
                          {node.errorCount != null && node.errorCount > 0 && <span className="text-[8px] px-1.5 py-[2px] rounded-full" style={{ background: "rgba(239,68,68,0.08)", color: "#ef4444", fontFamily: "var(--font-geist-mono)" }}>{node.errorCount} err</span>}
                          {node.avgLatencyMs != null && <span className="text-[8px] px-1.5 py-[2px] rounded-full" style={{ background: "hsl(var(--muted))", color: "hsl(var(--muted-foreground))", fontFamily: "var(--font-geist-mono)" }}>{Math.round(node.avgLatencyMs)}ms</span>}
                          {errRate > 0 && <div className="h-[3px] rounded-full overflow-hidden" style={{ background: "hsl(var(--muted))", width: 32 }}><div className="h-full rounded-full" style={{ width: `${Math.min(100, errRate * 100)}%`, background: errRate > 0.5 ? "#ef4444" : errRate > 0.1 ? "#f59e0b" : "#10b981" }} /></div>}
                        </div>
                      )}
                      {/* Row 3: call expand */}
                      {canExpandCalls && !isCallsExpanded && (
                        <button className="flex items-center gap-1 mt-1.5 w-full text-left hover:underline" style={{ fontSize: 9, color: "hsl(var(--primary))", fontFamily: "var(--font-geist-mono)" }}
                          onClick={(e) => { e.stopPropagation(); onToggleEdge?.(node.expandableEdgeId!); }}>
                          <span style={{ fontSize: 8 }}>{"\u25BE"}</span>
                          <span>{node.expandItemCount} {node.expandItemCount === 1 ? "call" : "calls"}</span>
                          {expandPreview && <span className="text-muted-foreground truncate" style={{ fontSize: 8 }}>{expandPreview}</span>}
                        </button>
                      )}
                      {canExpandCalls && isCallsExpanded && (
                        <button className="flex items-center gap-1 mt-1.5 hover:underline" style={{ fontSize: 9, color: "hsl(var(--primary))", fontFamily: "var(--font-geist-mono)" }}
                          onClick={(e) => { e.stopPropagation(); onToggleEdge?.(node.expandableEdgeId!); }}>
                          <span style={{ fontSize: 8 }}>{"\u25B4"}</span><span>collapse</span>
                        </button>
                      )}
                    </div>
                  </foreignObject>
                </g>
              );
            })}
          </g>
        </g>
      </svg>

      {/* ── Toolbar ── */}
      <div className="graph-toolbar absolute top-3 left-3 right-3 flex items-center gap-2 z-10 rounded-xl px-2 py-1.5"
        style={{ pointerEvents: "none", background: "hsl(var(--card) / 0.85)", backdropFilter: "blur(14px)", border: "1px solid hsl(var(--border))", boxShadow: "0 2px 12px rgba(0,0,0,0.08)" }}>
        {/* Search */}
        <div className="relative flex-shrink-0" style={{ pointerEvents: "auto", width: 200 }}>
          <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input ref={searchRef} type="text" value={searchQ} onChange={(e) => setSearchQ(e.target.value)}
            placeholder="Search nodes... (/)" className="input-base pl-8 pr-2 h-[30px] text-[12px]"
            onMouseDown={(e) => e.stopPropagation()} />
        </div>
        {matchIds !== null && <span className="text-[10px] text-muted-foreground flex-shrink-0" style={{ pointerEvents: "auto" }}>{matchIds.size} of {nodes.length}</span>}

        {/* Expand / Collapse all */}
        {onExpandAll && onCollapseAll && (
          <div className="flex items-center gap-1 flex-shrink-0" style={{ pointerEvents: "auto" }}>
            <button onClick={() => onExpandAll()} className="px-2.5 h-[28px] rounded-lg text-[10px] font-medium text-muted-foreground hover:text-foreground hover:bg-accent/60 transition-colors" style={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))" }} onMouseDown={(e) => e.stopPropagation()}>Expand all</button>
            <button onClick={() => onCollapseAll()} className="px-2.5 h-[28px] rounded-lg text-[10px] font-medium text-muted-foreground hover:text-foreground hover:bg-accent/60 transition-colors" style={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))" }} onMouseDown={(e) => e.stopPropagation()}>Collapse all</button>
          </div>
        )}

        {/* Error toggle */}
        <button onClick={() => setShowErrors((v) => !v)}
          className={cn("h-[28px] px-2.5 rounded-lg text-[10px] font-medium flex items-center gap-1.5 transition-colors flex-shrink-0", showErrors ? "text-red-400" : "text-muted-foreground hover:text-foreground hover:bg-accent/60")}
          style={{ pointerEvents: "auto", background: showErrors ? "rgba(239,68,68,0.08)" : "hsl(var(--card))", border: showErrors ? "1px solid rgba(239,68,68,0.25)" : "1px solid hsl(var(--border))" }}
          onMouseDown={(e) => e.stopPropagation()}>
          {showErrors && <span className="w-1.5 h-1.5 rounded-full bg-red-400" style={{ animation: "pulse 2s ease-in-out infinite" }} />}
          <AlertCircle size={11} />Failures
        </button>

        {/* Zoom — right side */}
        <div className="flex items-center gap-1.5 ml-auto flex-shrink-0 rounded-lg px-1.5 py-0.5" style={{ pointerEvents: "auto", background: "hsl(var(--muted) / 0.5)", border: "1px solid hsl(var(--border))" }}>
          <button onClick={() => setZoom((z) => Math.max(0.25, z * 0.8))} className="w-7 h-7 rounded-lg flex items-center justify-center text-xs text-muted-foreground hover:text-foreground hover:bg-accent/60 transition-colors" onMouseDown={(e) => e.stopPropagation()}>{"\u2212"}</button>
          <input type="range" min={25} max={250} value={Math.round(zoom * 100)} onChange={(e) => setZoom(Number(e.target.value) / 100)} className="w-20 h-1 cursor-pointer" onMouseDown={(e) => e.stopPropagation()} />
          <span className="text-[11px] text-muted-foreground w-9 text-center" style={{ fontFamily: "var(--font-geist-mono)" }}>{Math.round(zoom * 100)}%</span>
          <button onClick={() => setZoom((z) => Math.min(2.5, z * 1.2))} className="w-7 h-7 rounded-lg flex items-center justify-center text-xs text-muted-foreground hover:text-foreground hover:bg-accent/60 transition-colors" onMouseDown={(e) => e.stopPropagation()}>+</button>
          <button onClick={() => fitToCenter()} className="px-2.5 h-7 rounded-lg text-[10px] font-medium text-muted-foreground hover:text-foreground hover:bg-accent/60 transition-colors" onMouseDown={(e) => e.stopPropagation()}>Fit</button>
        </div>
      </div>

      {/* ── Edge tooltip ── */}
      {hoveredEdge && (
        <div className="fixed z-50 rounded-lg px-3 py-2.5 shadow-xl pointer-events-none" style={{ left: hoveredEdge.x + 14, top: hoveredEdge.y - 14, background: "hsl(var(--card-raised))", border: "1px solid hsl(var(--border))", backdropFilter: "blur(12px)", minWidth: 160, animation: "fadeIn 0.12s ease" }}>
          <p className="text-[11px] font-semibold text-foreground mb-1">{hoveredEdge.edge.source.replace(/^(agent|server):/, "")}<span className="text-muted-foreground mx-1">{"\u2192"}</span>{hoveredEdge.edge.target.replace(/^(agent|server):/, "")}</p>
          <div className="flex items-center gap-3 text-[10px]">
            <span className="text-muted-foreground">{hoveredEdge.edge.label ?? "1 call"}</span>
            {hoveredEdge.edge.errorCount != null && hoveredEdge.edge.errorCount > 0 && <span style={{ color: "#ef4444" }}>{hoveredEdge.edge.errorCount} err</span>}
            {hoveredEdge.edge.avgLatencyMs != null && <span className="text-muted-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>{Math.round(hoveredEdge.edge.avgLatencyMs)}ms</span>}
          </div>
        </div>
      )}

      {/* ── Legend ── */}
      <div className="absolute bottom-4 left-4 z-10 flex items-center gap-3 rounded-lg px-2.5 py-1.5 text-[9px] text-muted-foreground" style={{ background: "hsl(var(--card) / 0.9)", border: "1px solid hsl(var(--border))", backdropFilter: "blur(8px)" }}>
        <div className="flex items-center gap-1.5"><svg width="16" height="2"><line x1="0" y1="1" x2="16" y2="1" stroke="currentColor" strokeWidth="1.5" /></svg><span>calls</span></div>
        <div className="flex items-center gap-1.5"><svg width="16" height="2"><line x1="0" y1="1" x2="16" y2="1" stroke="currentColor" strokeWidth="1.5" strokeDasharray="3,2" /></svg><span>handoff</span></div>
      </div>

      {/* ── Minimap ── */}
      {minimap && containerSize.w > 0 && (
        <div className="absolute bottom-4 right-4 rounded-xl overflow-hidden z-10"
          style={{ width: MINIMAP_W + 4, height: MINIMAP_H + 18, background: "hsl(var(--card) / 0.92)", border: "1px solid hsl(var(--border))", backdropFilter: "blur(14px)", boxShadow: "0 4px 20px rgba(0,0,0,0.18)", cursor: "pointer", padding: 2 }}
          onMouseDown={(e) => {
            e.stopPropagation();
            const rect = e.currentTarget.getBoundingClientRect();
            const gx = (e.clientX - rect.left - 2) / minimap.s + minimap.mnx, gy = (e.clientY - rect.top - 16) / minimap.s + minimap.mny;
            setPan({ x: -(gx + base.offX) * zoom + containerSize.w / 2, y: -(gy + base.offY) * zoom + containerSize.h / 2 });
          }}>
          <div className="flex items-center justify-center py-0.5">
            <span className="text-[8px] font-semibold uppercase tracking-widest text-muted-foreground" style={{ letterSpacing: "0.1em" }}>Overview</span>
          </div>
          <svg width={MINIMAP_W} height={MINIMAP_H}>
            {nodes.map((n) => { const p = positions.get(n.id); if (!p || !minimap) return null; const nh = base.heights.get(n.id) ?? baseH; return <rect key={n.id} x={(p.x + base.offX - minimap.mnx) * minimap.s} y={(p.y + base.offY - minimap.mny) * minimap.s} width={NODE_W * minimap.s} height={nh * minimap.s} rx={2} fill={n.hasError ? "#ef4444" : n.type === "agent" ? "hsl(var(--primary))" : "rgba(148,163,184,0.6)"} opacity={0.8} />; })}
            {(() => { const vx = (-pan.x / zoom - base.offX - minimap.mnx) * minimap.s, vy = (-pan.y / zoom - base.offY - minimap.mny) * minimap.s, vw = (containerSize.w / zoom) * minimap.s, vh = (containerSize.h / zoom) * minimap.s; return <rect x={vx} y={vy} width={vw} height={vh} fill="hsl(var(--primary) / 0.1)" stroke="hsl(var(--primary))" strokeWidth={1.5} rx={2} />; })()}
          </svg>
        </div>
      )}
    </div>
  );
}
