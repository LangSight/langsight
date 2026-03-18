"use client";

export const dynamic = "force-dynamic";

import { useState, useEffect } from "react";
import useSWR from "swr";
import { ChevronRight, ChevronDown, GitBranch, Clock, Zap, AlertCircle } from "lucide-react";
import { fetcher, getSessionTrace } from "@/lib/api";
import { cn, timeAgo, formatDuration, CALL_STATUS_COLOR, SPAN_TYPE_ICON } from "@/lib/utils";
import type { AgentSession, SessionTrace, SpanNode } from "@/lib/types";

/* ── Trace tree ──────────────────────────────────────────────── */
function SpanLine({ depth, last }: { depth: number; last: boolean }) {
  return (
    <>
      {Array.from({ length: depth }).map((_, i) => (
        <span key={i} className="inline-block w-5 flex-shrink-0 relative">
          {i < depth - 1 && <span className="absolute left-2 top-0 bottom-0 border-l" style={{ borderColor: "hsl(var(--border))" }}/>}
        </span>
      ))}
      {depth > 0 && (
        <span className="inline-block w-5 flex-shrink-0 relative" style={{ marginLeft: -20 }}>
          <span className="absolute left-2 top-0 border-l border-b rounded-bl-sm" style={{ borderColor: "hsl(var(--border))", bottom: "50%", right: 0 }}/>
        </span>
      )}
    </>
  );
}

function SpanRow({ span, depth = 0, isLast = true }: { span: SpanNode; depth?: number; isLast?: boolean }) {
  const [open, setOpen] = useState(true);
  const icon = SPAN_TYPE_ICON[span.span_type] ?? "●";
  const statusColor = CALL_STATUS_COLOR[span.status] ?? "text-zinc-400";
  const hasChildren = span.children && span.children.length > 0;

  const spanColor = span.span_type === "handoff"
    ? "hsl(48 96% 53%)"   // yellow
    : span.span_type === "agent"
    ? "hsl(239 84% 67%)"  // indigo
    : "hsl(var(--foreground))";

  return (
    <>
      <tr className="group hover:bg-accent/30 transition-colors">
        <td className="py-2 pr-4">
          <div className="flex items-center" style={{ paddingLeft: `${depth * 20}px` }}>
            <button
              onClick={() => hasChildren && setOpen(o => !o)}
              className={cn("flex items-center gap-1.5 min-w-0", hasChildren ? "cursor-pointer" : "cursor-default")}>
              {hasChildren
                ? (open ? <ChevronDown size={12} style={{ color: "hsl(var(--muted-foreground))", flexShrink: 0 }}/> : <ChevronRight size={12} style={{ color: "hsl(var(--muted-foreground))", flexShrink: 0 }}/>)
                : <span className="w-3 flex-shrink-0"/>}
              <span className="text-xs mr-1.5">{icon}</span>
              <span className="text-xs font-mono truncate" style={{ color: spanColor }}>
                {span.server_name}/{span.tool_name}
              </span>
            </button>
          </div>
        </td>
        <td className="py-2 pr-4 text-xs" style={{ color: "hsl(var(--muted-foreground))" }}>
          {span.agent_name || "—"}
        </td>
        <td className="py-2 pr-4 text-xs">
          <span className={cn("font-mono", statusColor)}>
            {span.status === "success" ? "✓" : span.status === "error" ? "✗" : "⏱"}
          </span>
        </td>
        <td className="py-2 pr-4 text-xs font-mono text-right" style={{ color: "hsl(var(--muted-foreground))" }}>
          {span.latency_ms ? `${span.latency_ms.toFixed(0)}ms` : "—"}
        </td>
        <td className="py-2 text-xs text-red-500 truncate max-w-xs">
          {span.error?.slice(0, 50) ?? ""}
        </td>
      </tr>
      {open && span.children?.map((child, i) => (
        <SpanRow key={child.span_id} span={child} depth={depth + 1} isLast={i === (span.children?.length ?? 0) - 1}/>
      ))}
    </>
  );
}

function TraceDrawer({ sessionId, onClose }: { sessionId: string; onClose: () => void }) {
  const [trace, setTrace] = useState<SessionTrace | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getSessionTrace(sessionId)
      .then(t => { setTrace(t); setLoading(false); })
      .catch(e => { setError(e.message); setLoading(false); });
  }, [sessionId]);

  return (
    <div className="rounded-xl border mt-4 overflow-hidden" style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}>
      <div className="flex items-center justify-between px-5 py-3.5 border-b" style={{ borderColor: "hsl(var(--border))", background: "hsl(var(--muted))" }}>
        <div className="flex items-center gap-3">
          <GitBranch size={14} style={{ color: "hsl(var(--primary))" }}/>
          <code className="text-xs font-mono" style={{ color: "hsl(var(--foreground))" }}>{sessionId}</code>
          {trace && (
            <div className="flex items-center gap-2 text-[11px]" style={{ color: "hsl(var(--muted-foreground))" }}>
              <span>{trace.total_spans} spans</span>
              <span>·</span>
              <span>{trace.tool_calls} tools</span>
              {trace.failed_calls > 0 && <><span>·</span><span className="text-red-500 font-medium">{trace.failed_calls} failed</span></>}
              {trace.duration_ms && <><span>·</span><span>{formatDuration(trace.duration_ms)}</span></>}
            </div>
          )}
        </div>
        <button onClick={onClose} className="text-xs px-2 py-1 rounded hover:bg-accent transition-colors" style={{ color: "hsl(var(--muted-foreground))" }}>✕ Close</button>
      </div>
      <div className="overflow-x-auto">
        {loading ? (
          <div className="p-8 text-center">
            <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin mx-auto"/>
          </div>
        ) : error ? (
          <div className="p-6 text-center text-sm text-red-500">
            <AlertCircle size={20} className="mx-auto mb-2"/>
            {error} — make sure ClickHouse is running
          </div>
        ) : trace && trace.root_spans.length === 0 ? (
          <p className="p-6 text-center text-sm" style={{ color: "hsl(var(--muted-foreground))" }}>No spans found</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr style={{ borderBottom: "1px solid hsl(var(--border))" }}>
                {[["Span","w-64"],["Agent","w-28"],["Status","w-16"],["Latency","w-20 text-right"],["Error",""]].map(([h, cls]) => (
                  <th key={h} className={cn("px-4 py-2.5 text-left text-xs font-medium", cls)} style={{ color: "hsl(var(--muted-foreground))" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {trace?.root_spans.map((span, i) => (
                <SpanRow key={span.span_id} span={span} depth={0} isLast={i === (trace.root_spans.length - 1)}/>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

export default function SessionsPage() {
  const [hours, setHours] = useState(24);
  const [selected, setSelected] = useState<string | null>(null);

  const { data: sessions, isLoading, error } =
    useSWR<AgentSession[]>(`/api/agents/sessions?hours=${hours}&limit=100`, fetcher, { refreshInterval: 30_000 });

  const totalCalls = sessions?.reduce((n, s) => n + s.tool_calls, 0) ?? 0;
  const totalFailed = sessions?.reduce((n, s) => n + s.failed_calls, 0) ?? 0;

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold" style={{ color: "hsl(var(--foreground))" }}>Agent Sessions</h1>
          <p className="text-sm" style={{ color: "hsl(var(--muted-foreground))" }}>
            {sessions ? `${sessions.length} sessions · ${totalCalls} tool calls · ${totalFailed} failures` : "Loading…"}
          </p>
        </div>
        <select value={hours} onChange={e => setHours(Number(e.target.value))}
          className="text-sm rounded-lg px-3 py-2 border outline-none"
          style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))", color: "hsl(var(--foreground))" }}>
          {[[1,"1h"],[6,"6h"],[24,"24h"],[168,"7d"]].map(([v, l]) => (
            <option key={v} value={v}>{l}</option>
          ))}
        </select>
      </div>

      <div className="rounded-xl border overflow-hidden" style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}>
        {isLoading ? (
          <div className="divide-y" style={{ borderColor: "hsl(var(--border))" }}>
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="px-5 py-4 flex items-center justify-between">
                <div className="space-y-1.5"><span className="skeleton h-4 w-32 block rounded"/><span className="skeleton h-3 w-48 block rounded"/></div>
                <div className="flex gap-3"><span className="skeleton h-4 w-16 rounded"/><span className="skeleton h-5 w-20 rounded-full"/></div>
              </div>
            ))}
          </div>
        ) : error ? (
          <div className="p-8 text-center">
            <AlertCircle size={32} className="mx-auto mb-3 opacity-30"/>
            <p className="text-sm" style={{ color: "hsl(var(--muted-foreground))" }}>Could not load sessions — is ClickHouse running?</p>
          </div>
        ) : !sessions || sessions.length === 0 ? (
          <div className="p-12 text-center">
            <GitBranch size={40} className="mx-auto mb-4 opacity-20"/>
            <p className="font-medium mb-1" style={{ color: "hsl(var(--foreground))" }}>No sessions yet</p>
            <p className="text-sm" style={{ color: "hsl(var(--muted-foreground))" }}>Instrument your agents with the LangSight SDK</p>
          </div>
        ) : (
          <table className="w-full">
            <thead>
              <tr style={{ borderBottom: "1px solid hsl(var(--border))", background: "hsl(var(--muted))" }}>
                {[["Session ID",""],["Agent",""],["Calls","text-right"],["Failed","text-right"],["Duration","text-right"],["Servers",""],["Started",""]].map(([h, cls]) => (
                  <th key={h} className={cn("px-4 py-2.5 text-xs font-medium text-left", cls)} style={{ color: "hsl(var(--muted-foreground))" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y" style={{ borderColor: "hsl(var(--border))" }}>
              {sessions.map(s => {
                const active = selected === s.session_id;
                return (
                  <tr key={s.session_id}
                    onClick={() => setSelected(active ? null : s.session_id)}
                    className={cn("cursor-pointer transition-colors text-sm", active ? "bg-primary/5" : "hover:bg-accent/50")}>
                    <td className="px-4 py-3 font-mono text-xs" style={{ color: "hsl(var(--foreground))" }}>
                      <div className="flex items-center gap-2">
                        {active ? <ChevronDown size={12}/> : <ChevronRight size={12}/>}
                        {s.session_id.slice(0, 14)}…
                      </div>
                    </td>
                    <td className="px-4 py-3 text-xs" style={{ color: "hsl(var(--muted-foreground))" }}>{s.agent_name || "—"}</td>
                    <td className="px-4 py-3 text-xs text-right"><span className="flex items-center justify-end gap-1"><Zap size={10}/>{s.tool_calls}</span></td>
                    <td className="px-4 py-3 text-xs text-right">
                      {s.failed_calls > 0
                        ? <span className="text-red-500 font-medium">{s.failed_calls}</span>
                        : <span style={{ color: "hsl(var(--muted-foreground))" }}>0</span>}
                    </td>
                    <td className="px-4 py-3 text-xs text-right font-mono" style={{ color: "hsl(var(--muted-foreground))" }}>{formatDuration(s.duration_ms)}</td>
                    <td className="px-4 py-3 text-xs">
                      <div className="flex flex-wrap gap-1">
                        {(s.servers_used || []).slice(0, 2).map(srv => (
                          <span key={srv} className="px-1.5 py-0.5 rounded text-[10px] border" style={{ background: "hsl(var(--muted))", borderColor: "hsl(var(--border))", color: "hsl(var(--muted-foreground))" }}>{srv}</span>
                        ))}
                        {(s.servers_used?.length ?? 0) > 2 && <span className="text-[10px]" style={{ color: "hsl(var(--muted-foreground))" }}>+{s.servers_used.length - 2}</span>}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-xs" style={{ color: "hsl(var(--muted-foreground))" }}>
                      <div className="flex items-center gap-1"><Clock size={11}/>{timeAgo(s.first_call_at)}</div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {selected && <TraceDrawer sessionId={selected} onClose={() => setSelected(null)}/>}
    </div>
  );
}
