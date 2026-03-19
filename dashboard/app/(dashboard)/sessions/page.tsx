"use client";

export const dynamic = "force-dynamic";

import { useState, useEffect, useMemo } from "react";
import useSWR from "swr";
import {
  ChevronRight, ChevronDown, GitBranch, Clock, Zap, AlertCircle,
  Search, Filter, ChevronLeft, ChevronsLeft, ChevronsRight, GitCompare,
} from "lucide-react";
import { fetcher, getSessionTrace, compareSessions, replaySession } from "@/lib/api";
import { cn, timeAgo, formatDuration, CALL_STATUS_COLOR, SPAN_TYPE_ICON } from "@/lib/utils";
import type { AgentSession, SessionTrace, SpanNode, SessionComparison, DiffEntry, ReplayResponse } from "@/lib/types";

const PAGE_SIZE = 20;

/* ── Trace tree ──────────────────────────────────────────────── */

function PayloadPanel({ label, json }: { label: string; json: string | null }) {
  if (!json) return null;
  let formatted = json;
  try { formatted = JSON.stringify(JSON.parse(json), null, 2); } catch { /* keep raw */ }
  return (
    <div className="mt-1.5">
      <p className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider mb-1">{label}</p>
      <pre className="text-[11px] font-mono bg-muted/60 rounded-md p-2.5 overflow-x-auto whitespace-pre-wrap break-all leading-relaxed text-foreground max-h-48 overflow-y-auto">
        {formatted}
      </pre>
    </div>
  );
}

function SpanRow({ span, depth = 0 }: { span: SpanNode; depth?: number }) {
  const [open, setOpen] = useState(true);
  const [detailOpen, setDetailOpen] = useState(false);
  const icon = SPAN_TYPE_ICON[span.span_type] ?? "●";
  const statusColor = CALL_STATUS_COLOR[span.status] ?? "text-zinc-400";
  const hasChildren = span.children && span.children.length > 0;
  const isLlmSpan = span.span_type === "agent" && (span.llm_input || span.llm_output);
  const hasPayload = span.input_json || span.output_json || span.llm_input || span.llm_output || span.error;

  const spanColor = span.span_type === "handoff"
    ? "text-yellow-400"
    : span.span_type === "agent"
    ? "text-primary"
    : "text-foreground";

  return (
    <>
      <tr
        className={cn("group transition-colors", hasPayload ? "cursor-pointer hover:bg-accent/40" : "hover:bg-accent/30", detailOpen && "bg-accent/20")}
        onClick={() => hasPayload && setDetailOpen(o => !o)}
      >
        <td className="py-2 pr-4">
          <div className="flex items-center" style={{ paddingLeft: `${depth * 20}px` }}>
            <button
              onClick={e => { e.stopPropagation(); hasChildren && setOpen(o => !o); }}
              className={cn("flex items-center gap-1.5 min-w-0", hasChildren ? "cursor-pointer" : "cursor-default")}>
              {hasChildren
                ? (open ? <ChevronDown size={12} className="text-muted-foreground flex-shrink-0"/> : <ChevronRight size={12} className="text-muted-foreground flex-shrink-0"/>)
                : <span className="w-3 flex-shrink-0"/>}
              <span className="text-xs mr-1.5">{icon}</span>
              <span className={cn("text-xs font-mono truncate", spanColor)}>
                {span.server_name}/{span.tool_name}
              </span>
            </button>
            {hasPayload && (
              <span className="ml-2 text-[10px] text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity">
                {detailOpen ? "▲ hide" : "▼ inspect"}
              </span>
            )}
          </div>
        </td>
        <td className="py-2 pr-4 text-xs text-muted-foreground">{span.agent_name || "—"}</td>
        <td className="py-2 pr-4 text-xs">
          <span className={cn("font-mono", statusColor)}>
            {span.status === "success" ? "✓" : span.status === "error" ? "✗" : "⏱"}
          </span>
        </td>
        <td className="py-2 pr-4 text-xs font-mono text-right text-muted-foreground">
          {span.latency_ms ? `${span.latency_ms.toFixed(0)}ms` : "—"}
        </td>
        <td className="py-2 text-xs text-red-500 truncate max-w-xs">{span.error?.slice(0, 50) ?? ""}</td>
      </tr>
      {detailOpen && hasPayload && (
        <tr className="bg-accent/10">
          <td colSpan={5} className="px-4 pb-3 pt-1" style={{ paddingLeft: `${depth * 20 + 28}px` }}>
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
              <div className="mt-1.5">
                <p className="text-[10px] font-medium text-red-500 uppercase tracking-wider mb-1">Error</p>
                <pre className="text-[11px] font-mono bg-red-500/10 rounded-md p-2.5 text-red-400 whitespace-pre-wrap break-all">
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

function TraceDrawer({ sessionId, onClose, onReplay }: {
  sessionId: string;
  onClose: () => void;
  onReplay: (replaySessionId: string) => void;
}) {
  const [trace, setTrace] = useState<SessionTrace | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [replaying, setReplaying] = useState(false);
  const [replayError, setReplayError] = useState<string | null>(null);

  useEffect(() => {
    getSessionTrace(sessionId)
      .then(t => { setTrace(t); setLoading(false); })
      .catch(e => { setError(e.message); setLoading(false); });
  }, [sessionId]);

  async function handleReplay() {
    setReplaying(true);
    setReplayError(null);
    try {
      const result: ReplayResponse = await replaySession(sessionId);
      onReplay(result.replay_session_id);
    } catch (e: unknown) {
      setReplayError(e instanceof Error ? e.message : "Replay failed");
    } finally {
      setReplaying(false);
    }
  }

  return (
    <div className="rounded-xl border border-border mt-4 overflow-hidden bg-card">
      <div className="flex items-center justify-between px-5 py-3.5 border-b border-border bg-muted">
        <div className="flex items-center gap-3">
          <GitBranch size={14} className="text-primary"/>
          <code className="text-xs font-mono text-foreground">{sessionId}</code>
          {trace && (
            <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
              <span>{trace.total_spans} spans</span>
              <span>·</span>
              <span>{trace.tool_calls} tools</span>
              {trace.failed_calls > 0 && <><span>·</span><span className="text-red-500 font-medium">{trace.failed_calls} failed</span></>}
              {trace.duration_ms && <><span>·</span><span>{formatDuration(trace.duration_ms)}</span></>}
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleReplay}
            disabled={replaying || loading}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border border-primary/30 bg-primary/10 text-primary hover:bg-primary/20 transition-colors disabled:opacity-50 disabled:cursor-not-allowed">
            {replaying
              ? <><span className="w-3 h-3 border border-primary border-t-transparent rounded-full animate-spin"/>Replaying…</>
              : <><GitCompare size={11}/>Replay</>}
          </button>
          <button onClick={onClose} className="text-xs px-2 py-1 rounded text-muted-foreground hover:bg-accent transition-colors">✕ Close</button>
        </div>
      </div>
      {replayError && (
        <div className="px-5 py-2 text-xs text-red-500 border-b border-border bg-red-500/5">
          Replay failed: {replayError}
        </div>
      )}
      <div className="overflow-x-auto">
        {loading ? (
          <div className="p-8 text-center">
            <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin mx-auto"/>
          </div>
        ) : error ? (
          <div className="p-6 text-center text-sm text-red-500">
            <AlertCircle size={20} className="mx-auto mb-2"/> {error}
          </div>
        ) : trace && trace.root_spans.length === 0 ? (
          <p className="p-6 text-center text-sm text-muted-foreground">No spans found</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                {["Span","Agent","Status","Latency","Error"].map(h => (
                  <th key={h} className="px-4 py-2.5 text-left text-xs font-medium text-muted-foreground">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {trace?.root_spans.map(span => (
                <SpanRow key={span.span_id} span={span} depth={0} />
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

/* ── Compare drawer ──────────────────────────────────────────── */

const DIFF_COLOR: Record<DiffEntry["status"], string> = {
  matched: "text-emerald-500",
  diverged: "text-yellow-400",
  only_a:  "text-blue-400",
  only_b:  "text-purple-400",
};

const DIFF_BG: Record<DiffEntry["status"], string> = {
  matched: "",
  diverged: "bg-yellow-500/5",
  only_a:  "bg-blue-500/5",
  only_b:  "bg-purple-500/5",
};

function DiffRow({ entry }: { entry: DiffEntry }) {
  const latStr = (span: Record<string, unknown> | null) =>
    span?.latency_ms != null ? `${Number(span.latency_ms).toFixed(0)}ms` : "—";
  const statusStr = (span: Record<string, unknown> | null) =>
    span ? (span.status === "success" ? "✓" : span.status === "error" ? "✗" : "⏱") : "—";
  const deltaColor = entry.latency_delta_pct === null ? ""
    : entry.latency_delta_pct > 0 ? "text-red-400" : "text-emerald-400";
  return (
    <tr className={cn("border-b border-border text-xs", DIFF_BG[entry.status])}>
      <td className="px-3 py-2 font-mono text-muted-foreground truncate max-w-[180px]">
        <span className={cn("mr-1.5", DIFF_COLOR[entry.status])}>
          {entry.status === "matched" ? "=" : entry.status === "diverged" ? "≠" : entry.status === "only_a" ? "A" : "B"}
        </span>
        {entry.tool_key}
      </td>
      <td className="px-3 py-2 text-center">
        <span className={cn("font-mono", entry.span_a ? (CALL_STATUS_COLOR[entry.span_a.status as string] ?? "") : "text-muted-foreground")}>
          {statusStr(entry.span_a)}
        </span>
      </td>
      <td className="px-3 py-2 text-right font-mono text-muted-foreground">{latStr(entry.span_a)}</td>
      <td className="px-3 py-2 text-center">
        <span className={cn("font-mono", entry.span_b ? (CALL_STATUS_COLOR[entry.span_b.status as string] ?? "") : "text-muted-foreground")}>
          {statusStr(entry.span_b)}
        </span>
      </td>
      <td className="px-3 py-2 text-right font-mono text-muted-foreground">{latStr(entry.span_b)}</td>
      <td className={cn("px-3 py-2 text-right font-mono", deltaColor)}>
        {entry.latency_delta_pct !== null
          ? `${entry.latency_delta_pct > 0 ? "+" : ""}${entry.latency_delta_pct}%`
          : "—"}
      </td>
    </tr>
  );
}

function CompareDrawer({ idA, idB, onClose }: { idA: string; idB: string; onClose: () => void }) {
  const [cmp, setCmp] = useState<SessionComparison | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    compareSessions(idA, idB)
      .then(c => { setCmp(c); setLoading(false); })
      .catch(e => { setError(e.message); setLoading(false); });
  }, [idA, idB]);
  return (
    <div className="rounded-xl border border-border mt-4 overflow-hidden bg-card">
      <div className="flex items-center justify-between px-5 py-3.5 border-b border-border bg-muted">
        <div className="flex items-center gap-3">
          <GitCompare size={14} className="text-primary"/>
          <div className="flex items-center gap-2 text-xs font-mono">
            <span className="text-blue-400">{idA.slice(0, 12)}…</span>
            <span className="text-muted-foreground">vs</span>
            <span className="text-purple-400">{idB.slice(0, 12)}…</span>
          </div>
          {cmp && (
            <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
              <span className="text-emerald-500">{cmp.summary.matched} matched</span>
              {cmp.summary.diverged > 0 && <><span>·</span><span className="text-yellow-400">{cmp.summary.diverged} diverged</span></>}
              {cmp.summary.only_a > 0 && <><span>·</span><span className="text-blue-400">{cmp.summary.only_a} only in A</span></>}
              {cmp.summary.only_b > 0 && <><span>·</span><span className="text-purple-400">{cmp.summary.only_b} only in B</span></>}
            </div>
          )}
        </div>
        <button onClick={onClose} className="text-xs px-2 py-1 rounded text-muted-foreground hover:bg-accent transition-colors">✕ Close</button>
      </div>
      <div className="overflow-x-auto">
        {loading ? (
          <div className="p-8 text-center"><div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin mx-auto"/></div>
        ) : error ? (
          <div className="p-6 text-center text-sm text-red-500"><AlertCircle size={20} className="mx-auto mb-2"/>{error}</div>
        ) : !cmp || cmp.diff.length === 0 ? (
          <p className="p-6 text-center text-sm text-muted-foreground">No spans found in either session</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/50">
                <th className="px-3 py-2.5 text-left text-xs font-medium text-muted-foreground">Tool</th>
                <th className="px-3 py-2.5 text-center text-xs font-medium text-blue-400">A status</th>
                <th className="px-3 py-2.5 text-right text-xs font-medium text-blue-400">A latency</th>
                <th className="px-3 py-2.5 text-center text-xs font-medium text-purple-400">B status</th>
                <th className="px-3 py-2.5 text-right text-xs font-medium text-purple-400">B latency</th>
                <th className="px-3 py-2.5 text-right text-xs font-medium text-muted-foreground">Δ latency</th>
              </tr>
            </thead>
            <tbody>
              {cmp.diff.map((entry, i) => <DiffRow key={i} entry={entry}/>)}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

/* ── Status filter badge ─────────────────────────────────────── */

function FilterBadge({ label, active, count, onClick }: {
  label: string; active: boolean; count: number; onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors",
        active
          ? "bg-primary/10 border-primary/30 text-primary"
          : "bg-card border-border text-muted-foreground hover:bg-accent"
      )}>
      {label}
      <span className={cn(
        "text-[10px] px-1.5 py-0.5 rounded-full min-w-[18px] text-center",
        active ? "bg-primary/20 text-primary" : "bg-muted text-muted-foreground"
      )}>
        {count}
      </span>
    </button>
  );
}

/* ── Main page ───────────────────────────────────────────────── */

export default function SessionsPage() {
  const [hours, setHours] = useState(24);
  const [selected, setSelected] = useState<string | null>(null);
  const [compareWith, setCompareWith] = useState<string | null>(null);
  const [comparing, setComparing] = useState(false);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "clean" | "failed">("all");
  const [agentFilter, setAgentFilter] = useState<string>("all");
  const [page, setPage] = useState(0);

  const { data: sessions, isLoading, error } =
    useSWR<AgentSession[]>(`/api/agents/sessions?hours=${hours}&limit=500`, fetcher, { refreshInterval: 30_000 });

  // Reset page when filters change
  useEffect(() => { setPage(0); }, [search, statusFilter, agentFilter, hours]);

  // Unique agent names for filter dropdown
  const agentNames = useMemo(() => {
    if (!sessions) return [];
    const names = new Set(sessions.map(s => s.agent_name ?? "unknown"));
    return Array.from(names).sort();
  }, [sessions]);

  // Apply filters
  const filtered = useMemo(() => {
    if (!sessions) return [];
    return sessions.filter(s => {
      if (statusFilter === "clean" && s.failed_calls > 0) return false;
      if (statusFilter === "failed" && s.failed_calls === 0) return false;
      if (agentFilter !== "all" && (s.agent_name ?? "unknown") !== agentFilter) return false;
      if (search) {
        const q = search.toLowerCase();
        const matchId = s.session_id.toLowerCase().includes(q);
        const matchAgent = (s.agent_name ?? "").toLowerCase().includes(q);
        const matchServer = s.servers_used?.some(srv => srv.toLowerCase().includes(q));
        if (!matchId && !matchAgent && !matchServer) return false;
      }
      return true;
    });
  }, [sessions, statusFilter, agentFilter, search]);

  // Counts for filter badges
  const countAll = sessions?.length ?? 0;
  const countClean = sessions?.filter(s => s.failed_calls === 0).length ?? 0;
  const countFailed = sessions?.filter(s => s.failed_calls > 0).length ?? 0;

  // Pagination
  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const paginated = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  const totalCalls = filtered.reduce((n, s) => n + s.tool_calls, 0);
  const totalFailed = filtered.reduce((n, s) => n + s.failed_calls, 0);

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-foreground">Workflows</h1>
          <p className="text-sm text-muted-foreground">
            {filtered.length} sessions · {totalCalls} tool calls · {totalFailed} failures
            {selected && !comparing && <span className="ml-2 text-primary">· 1 selected — click another to compare</span>}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {selected && compareWith && !comparing && (
            <button
              onClick={() => setComparing(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border border-primary/30 bg-primary/10 text-primary hover:bg-primary/20 transition-colors">
              <GitCompare size={12}/>Compare
            </button>
          )}
          {(selected || comparing) && (
            <button
              onClick={() => { setSelected(null); setCompareWith(null); setComparing(false); }}
              className="px-3 py-1.5 rounded-lg text-xs font-medium border border-border text-muted-foreground hover:bg-accent transition-colors">
              Clear
            </button>
          )}
          <select value={hours} onChange={e => setHours(Number(e.target.value))}
            className="text-sm rounded-lg px-3 py-2 border border-border outline-none bg-card text-foreground">
            {[[1,"1h"],[6,"6h"],[24,"24h"],[168,"7d"]].map(([v, l]) => (
              <option key={v} value={v}>{l}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Filters bar */}
      <div className="flex flex-wrap items-center gap-3">
        {/* Search */}
        <div className="relative flex-1 min-w-[200px] max-w-sm">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search session ID, agent, server…"
            className="w-full pl-9 pr-3 py-2 rounded-lg border border-border bg-card text-sm text-foreground placeholder:text-muted-foreground outline-none focus:ring-1 focus:ring-primary/30"
          />
        </div>

        {/* Status badges */}
        <div className="flex items-center gap-1.5">
          <FilterBadge label="All" active={statusFilter === "all"} count={countAll} onClick={() => setStatusFilter("all")} />
          <FilterBadge label="Clean" active={statusFilter === "clean"} count={countClean} onClick={() => setStatusFilter("clean")} />
          <FilterBadge label="Failed" active={statusFilter === "failed"} count={countFailed} onClick={() => setStatusFilter("failed")} />
        </div>

        {/* Agent filter */}
        {agentNames.length > 1 && (
          <div className="flex items-center gap-1.5">
            <Filter size={14} className="text-muted-foreground" />
            <select
              value={agentFilter}
              onChange={e => setAgentFilter(e.target.value)}
              className="text-xs rounded-lg px-2 py-1.5 border border-border bg-card text-foreground outline-none">
              <option value="all">All agents</option>
              {agentNames.map(name => (
                <option key={name} value={name}>{name}</option>
              ))}
            </select>
          </div>
        )}
      </div>

      {/* Table */}
      <div className="rounded-xl border border-border overflow-hidden bg-card">
        {isLoading ? (
          <div className="divide-y divide-border">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="px-5 py-4 flex items-center justify-between">
                <div className="space-y-1.5"><span className="skeleton h-4 w-32 block rounded"/><span className="skeleton h-3 w-48 block rounded"/></div>
                <div className="flex gap-3"><span className="skeleton h-4 w-16 rounded"/><span className="skeleton h-5 w-20 rounded-full"/></div>
              </div>
            ))}
          </div>
        ) : error ? (
          <div className="p-12 text-center">
            <AlertCircle size={32} className="mx-auto mb-3 opacity-30"/>
            <p className="text-sm text-muted-foreground">Could not load workflows — check ClickHouse storage</p>
          </div>
        ) : filtered.length === 0 ? (
          <div className="p-12 text-center">
            <GitBranch size={40} className="mx-auto mb-4 opacity-20"/>
            <p className="font-medium mb-1 text-foreground">
              {sessions && sessions.length > 0 ? "No sessions match your filters" : "No workflows yet"}
            </p>
            <p className="text-sm text-muted-foreground">
              {sessions && sessions.length > 0
                ? "Try adjusting the search or filter criteria"
                : "Instrument your agents with the LangSight SDK to capture traces"}
            </p>
          </div>
        ) : (
          <>
            <table className="w-full">
              <thead>
                <tr className="border-b border-border bg-muted/50">
                  {["Session ID","Agent","Calls","Failed","Duration","Servers","Started"].map(h => (
                    <th key={h} className={cn(
                      "px-4 py-2.5 text-xs font-medium text-muted-foreground text-left",
                      (h === "Calls" || h === "Failed" || h === "Duration") && "text-right"
                    )}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {paginated.map(s => {
                  const isA = selected === s.session_id;
                  const isB = compareWith === s.session_id;
                  const active = isA || isB;
                  function handleRowClick() {
                    if (comparing) { setComparing(false); setCompareWith(null); return; }
                    if (isA) { setSelected(null); setCompareWith(null); return; }
                    if (isB) { setCompareWith(null); return; }
                    if (selected && !compareWith) { setCompareWith(s.session_id); return; }
                    setSelected(s.session_id); setCompareWith(null);
                  }
                  return (
                    <tr key={s.session_id}
                      onClick={handleRowClick}
                      className={cn(
                        "cursor-pointer transition-colors text-sm",
                        isA ? "bg-blue-500/5 border-l-2 border-l-blue-400"
                        : isB ? "bg-purple-500/5 border-l-2 border-l-purple-400"
                        : "hover:bg-accent/50"
                      )}>
                      <td className="px-4 py-3 font-mono text-xs text-foreground">
                        <div className="flex items-center gap-2">
                          {isA ? <span className="text-[10px] font-bold text-blue-400">A</span>
                           : isB ? <span className="text-[10px] font-bold text-purple-400">B</span>
                           : <ChevronRight size={12}/>}
                          {s.session_id.slice(0, 14)}…
                        </div>
                      </td>
                      <td className="px-4 py-3 text-xs text-muted-foreground">{s.agent_name || "—"}</td>
                      <td className="px-4 py-3 text-xs text-right">
                        <span className="inline-flex items-center gap-1"><Zap size={10}/>{s.tool_calls}</span>
                      </td>
                      <td className="px-4 py-3 text-xs text-right">
                        {s.failed_calls > 0
                          ? <span className="text-red-500 font-medium">{s.failed_calls}</span>
                          : <span className="text-muted-foreground">0</span>}
                      </td>
                      <td className="px-4 py-3 text-xs text-right font-mono text-muted-foreground">{formatDuration(s.duration_ms)}</td>
                      <td className="px-4 py-3 text-xs">
                        <div className="flex flex-wrap gap-1">
                          {(s.servers_used || []).slice(0, 2).map(srv => (
                            <span key={srv} className="px-1.5 py-0.5 rounded text-[10px] border border-border bg-muted text-muted-foreground">{srv}</span>
                          ))}
                          {(s.servers_used?.length ?? 0) > 2 && <span className="text-[10px] text-muted-foreground">+{s.servers_used.length - 2}</span>}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-xs text-muted-foreground">
                        <div className="flex items-center gap-1"><Clock size={11}/>{timeAgo(s.first_call_at)}</div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between px-4 py-3 border-t border-border bg-muted/30">
                <span className="text-xs text-muted-foreground">
                  Showing {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, filtered.length)} of {filtered.length}
                </span>
                <div className="flex items-center gap-1">
                  <button onClick={() => setPage(0)} disabled={page === 0}
                    className="p-1.5 rounded hover:bg-accent disabled:opacity-30 disabled:cursor-not-allowed text-muted-foreground"><ChevronsLeft size={14}/></button>
                  <button onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0}
                    className="p-1.5 rounded hover:bg-accent disabled:opacity-30 disabled:cursor-not-allowed text-muted-foreground"><ChevronLeft size={14}/></button>
                  <span className="text-xs text-muted-foreground px-2">
                    {page + 1} / {totalPages}
                  </span>
                  <button onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))} disabled={page >= totalPages - 1}
                    className="p-1.5 rounded hover:bg-accent disabled:opacity-30 disabled:cursor-not-allowed text-muted-foreground"><ChevronRight size={14}/></button>
                  <button onClick={() => setPage(totalPages - 1)} disabled={page >= totalPages - 1}
                    className="p-1.5 rounded hover:bg-accent disabled:opacity-30 disabled:cursor-not-allowed text-muted-foreground"><ChevronsRight size={14}/></button>
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {comparing && selected && compareWith && (
        <CompareDrawer
          idA={selected}
          idB={compareWith}
          onClose={() => { setComparing(false); setCompareWith(null); }}
        />
      )}
      {!comparing && selected && (
        <TraceDrawer
          sessionId={selected}
          onClose={() => { setSelected(null); setCompareWith(null); }}
          onReplay={(replayId) => {
            setCompareWith(replayId);
            setComparing(true);
          }}
        />
      )}
    </div>
  );
}
