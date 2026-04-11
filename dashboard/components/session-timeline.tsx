"use client";

import { useMemo, useState } from "react";
import type { SpanNode } from "@/lib/types";

interface Props {
  spans: SpanNode[];
  sessionDurationMs: number;
  onSelectNode: (nodeId: string) => void;
}

export function SessionTimeline({ spans, sessionDurationMs, onSelectNode }: Props) {
  const [hovered, setHovered] = useState<{ span: SpanNode; x: number; y: number } | null>(null);

  const segments = useMemo(() => {
    if (!spans.length || !sessionDurationMs) return [];
    const times = spans
      .filter((s) => (s.span_type === "tool_call" || s.span_type === "node") && s.started_at)
      .map((s) => ({ span: s, start: new Date(s.started_at).getTime() }))
      .sort((a, b) => a.start - b.start);
    if (!times.length) return [];
    const t0 = times[0].start;
    return times.map(({ span, start }) => ({
      span,
      leftPct: ((start - t0) / sessionDurationMs) * 100,
      widthPct: Math.max(0.5, ((span.latency_ms ?? 0) / sessionDurationMs) * 100),
      color: span.status === "success" ? "#10b981" : span.status === "error" ? "#ef4444" : "#f59e0b",
    }));
  }, [spans, sessionDurationMs]);

  if (segments.length === 0) return null;

  return (
    <div className="relative" style={{ height: 24 }}>
      <div
        className="absolute inset-x-0 top-1/2 -translate-y-1/2 rounded-full overflow-hidden"
        style={{ height: 5, background: "hsl(var(--muted))" }}
      >
        {segments.map((seg, i) => (
          <div
            key={i}
            className="absolute top-0 h-full rounded-full cursor-pointer hover:brightness-110 transition-all"
            style={{ left: `${seg.leftPct}%`, width: `${seg.widthPct}%`, background: seg.color, opacity: 0.7 }}
            onClick={() => {
              const nodeId = seg.span.server_name ? `server:${seg.span.server_name}` : seg.span.agent_name ? `agent:${seg.span.agent_name}` : null;
              if (nodeId) onSelectNode(nodeId);
            }}
            onMouseEnter={(e) => setHovered({ span: seg.span, x: e.clientX, y: e.clientY })}
            onMouseLeave={() => setHovered(null)}
          />
        ))}
      </div>
      {hovered && (
        <div
          className="fixed z-50 rounded-lg px-3 py-2 shadow-xl pointer-events-none"
          style={{ left: hovered.x + 10, top: hovered.y - 50, background: "hsl(var(--card-raised))", border: "1px solid hsl(var(--border))", animation: "fadeIn 0.1s ease" }}
        >
          <p className="text-[11px] font-semibold text-foreground">{hovered.span.server_name}/{hovered.span.tool_name}</p>
          <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
            <span style={{ fontFamily: "var(--font-geist-mono)" }}>{Math.round(hovered.span.latency_ms ?? 0)}ms</span>
            <span className={hovered.span.status === "success" ? "text-emerald-400" : "text-red-400"}>{hovered.span.status}</span>
          </div>
        </div>
      )}
    </div>
  );
}
