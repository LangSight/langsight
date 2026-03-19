"use client";

export const dynamic = "force-dynamic";

import { useState, useEffect, useMemo } from "react";
import useSWR from "swr";
import {
  ChevronRight, ChevronDown, GitBranch, Clock, Zap, AlertCircle,
  Search, Filter, ChevronLeft, ChevronsLeft, ChevronsRight, GitCompare,
  Play, X,
} from "lucide-react";
import { fetcher, getSessionTrace, compareSessions, replaySession } from "@/lib/api";
import { useProject } from "@/lib/project-context";
import { cn, timeAgo, formatDuration, CALL_STATUS_COLOR, SPAN_TYPE_ICON } from "@/lib/utils";
import type { AgentSession, SessionTrace, SpanNode, SessionComparison, DiffEntry, ReplayResponse } from "@/lib/types";

const PAGE_SIZE = 20;

/* ── Payload panel ──────────────────────────────────────────── */
function PayloadPanel({ label, json }: { label: string; json: string | null }) {
  if (!json) return null;
  let formatted = json;
  try { formatted = JSON.stringify(JSON.parse(json), null, 2); } catch { /* keep raw */ }
  return (
    <div className="mt-2">
      <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-widest mb-1">{label}</p>
      <pre
        className="text-[11px] rounded-lg p-3 overflow-x-auto whitespace-pre-wrap break-all leading-relaxed max-h-44 overflow-y-auto"
        style={{
          fontFamily: "var(--font-geist-mono)",
          background: "hsl(var(--muted))",
          color: "hsl(var(--foreground))",
          border: "1px solid hsl(var(--border))",
        }}
      >
        {formatted}
      </pre>
    </div>
  );
}

/* ── Span row ───────────────────────────────────────────────── */
function SpanRow({ span, depth = 0 }: { span: SpanNode; depth?: number }) {
  const [open, setOpen] = useState(true);
  const [detailOpen, setDetailOpen] = useState(false);
  const icon = SPAN_TYPE_ICON[span.span_type] ?? "●";
  const statusColor = CALL_STATUS_COLOR[span.status] ?? "text-zinc-400";
  const hasChildren = span.children && span.children.length > 0;
  const isLlmSpan = span.span_type === "agent" && (span.llm_input || span.llm_output);
  const hasPayload = span.input_json || span.output_json || span.llm_input || span.llm_output || span.error;

  const spanColor =
    span.span_type === "handoff" ? "text-yellow-500"
    : span.span_type === "agent" ? "text-primary"
    : "text-foreground";

  return (
    <>
      <tr
        className={cn(
          "group transition-colors border-b border-border/40",
          hasPayload ? "cursor-pointer hover:bg-accent/40" : "hover:bg-accent/20",
          detailOpen && "bg-accent/20"
        )}
        onClick={() => hasPayload && setDetailOpen((o) => !o)}
      >
        <td className="py-2 pr-3">
          <div className="flex items-center" style={{ paddingLeft: `${depth * 18}px` }}>
            <button
              onClick={(e) => { e.stopPropagation(); hasChildren && setOpen((o) => !o); }}
              className={cn("flex items-center gap-1.5 min-w-0", hasChildren ? "cursor-pointer" : "cursor-default")}
            >
              {hasChildren
                ? open
                  ? <ChevronDown size={11} className="text-muted-foreground flex-shrink-0" />
                  : <ChevronRight size={11} className="text-muted-foreground flex-shrink-0" />
                : <span className="w-3 flex-shrink-0" />}
              <span className="text-xs mr-1">{icon}</span>
              <span className={cn("text-[12px] font-mono truncate", spanColor)} style={{ fontFamily: "var(--font-geist-mono)" }}>
                {span.server_name}/{span.tool_name}
              </span>
            </button>
            {hasPayload && (
              <span className="ml-2 text-[10px] text-muted-foreground opacity-0 group-hover:opacity-60 transition-opacity">
                {detailOpen ? "▲" : "▼"}
              </span>
            )}
          </div>
        </td>
        <td className="py-2 pr-3 text-[12px] text-muted-foreground">{span.agent_name || "—"}</td>
        <td className="py-2 pr-3 text-[12px]">
          <span className={cn("font-mono font-semibold", statusColor)}>
            {span.status === "success" ? "✓" : span.status === "error" ? "✗" : "⏱"}
          </span>
        </td>
        <td className="py-2 pr-3 text-[12px] font-mono text-right text-muted-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>
          {span.latency_ms ? `${span.latency_ms.toFixed(0)}ms` : "—"}
        </td>
        <td className="py-2 text-[11px] text-red-500 truncate max-w-xs">{span.error?.slice(0, 60) ?? ""}</td>
      </tr>

      {detailOpen && hasPayload && (
        <tr style={{ background: "hsl(var(--muted) / 0.5)" }}>
          <td colSpan={5} className="px-4 pb-3 pt-1" style={{ paddingLeft: `${depth * 18 + 28}px` }}>
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
              <div className="mt-2">
                <p className="text-[10px] font-semibold uppercase tracking-widest mb-1" style={{ color: "hsl(var(--danger))" }}>Error</p>
                <pre
                  className="text-[11px] rounded-lg p-3 whitespace-pre-wrap break-all"
                  style={{
                    fontFamily: "var(--font-geist-mono)",
                    background: "hsl(var(--danger-bg))",
                    color: "hsl(var(--danger))",
                    border: "1px solid hsl(var(--danger) / 0.2)",
                  }}
                >
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

/* ── Trace drawer ───────────────────────────────────────────── */
function TraceDrawer({
  sessionId, onClose, onReplay, projectId,
}: {
  sessionId: string;
  onClose: () => void;
  onReplay: (replaySessionId: string) => void;
  projectId?: string;
}) {
  const [trace, setTrace] = useState<SessionTrace | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [replaying, setReplaying] = useState(false);
  const [replayError, setReplayError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setTrace(null);
    setError(null);
    getSessionTrace(sessionId, projectId)
      .then((t) => { setTrace(t); setLoading(false); })
      .catch((e) => { setError(e.message); setLoading(false); });
  }, [sessionId, projectId]);

  async function handleReplay() {
    setReplaying(true);
    setReplayError(null);
    try {
      const result: ReplayResponse = await replaySession(sessionId, 10, 60, projectId);
      onReplay(result.replay_session_id);
    } catch (e: unknown) {
      setReplayError(e instanceof Error ? e.message : "Replay failed");
    } finally {
      setReplaying(false);
    }
  }

  return (
    <div
      className="rounded-xl border overflow-hidden mt-2"
      style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
    >
      {/* Drawer header */}
      <div
        className="flex items-center justify-between px-4 py-3 border-b"
        style={{ background: "hsl(var(--card-raised))", borderColor: "hsl(var(--border))" }}
      >
        <div className="flex items-center gap-3 min-w-0">
          <GitBranch size={13} className="text-primary flex-shrink-0" />
          <code
            className="text-[12px] text-foreground"
            style={{ fontFamily: "var(--font-geist-mono)" }}
          >
            {sessionId.slice(0, 24)}…
          </code>
          {trace && (
            <div className="hidden sm:flex items-center gap-2 text-[11px] text-muted-foreground">
              <span>{trace.total_spans} spans</span>
              <span>·</span>
              <span>{trace.tool_calls} tools</span>
              {trace.failed_calls > 0 && (
                <><span>·</span>
                <span style={{ color: "hsl(var(--danger))" }} className="font-semibold">
                  {trace.failed_calls} failed
                </span></>
              )}
              {trace.duration_ms && (
                <><span>·</span><span>{formatDuration(trace.duration_ms)}</span></>
              )}
            </div>
          )}
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <button
            onClick={handleReplay}
            disabled={replaying || loading}
            className="btn btn-secondary text-[12px] py-1.5 px-3"
          >
            {replaying
              ? <><span className="w-3 h-3 border border-current border-t-transparent rounded-full spin" />Replaying…</>
              : <><Play size={11} />Replay</>
            }
          </button>
          <button
            onClick={onClose}
            className="btn btn-ghost p-1.5"
            aria-label="Close trace"
          >
            <X size={14} />
          </button>
        </div>
      </div>

      {replayError && (
        <div
          className="px-4 py-2 text-xs border-b"
          style={{ background: "hsl(var(--danger-bg))", color: "hsl(var(--danger))", borderColor: "hsl(var(--danger) / 0.2)" }}
        >
          Replay failed: {replayError}
        </div>
      )}

      {/* Trace table */}
      <div className="overflow-x-auto">
        {loading ? (
          <div className="p-10 flex items-center justify-center">
            <div className="w-6 h-6 rounded-full border-2 border-primary border-t-transparent spin" />
          </div>
        ) : error ? (
          <div className="p-8 text-center text-sm" style={{ color: "hsl(var(--danger))" }}>
            <AlertCircle size={20} className="mx-auto mb-2" />
            {error}
          </div>
        ) : !trace || trace.root_spans.length === 0 ? (
          <p className="p-8 text-center text-sm text-muted-foreground">No spans found</p>
        ) : (
          <table className="w-full">
            <thead>
              <tr style={{ borderBottom: "1px solid hsl(var(--border))", background: "hsl(var(--card-raised))" }}>
                {["Span", "Agent", "Status", "Latency", "Error"].map((h) => (
                  <th
                    key={h}
                    className="px-4 py-2.5 text-left text-[11px] font-semibold text-muted-foreground uppercase tracking-wide"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {trace.root_spans.map((span) => (
                <SpanRow key={span.span_id} span={span} depth={0} />
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

/* ── Compare drawer ─────────────────────────────────────────── */
function DiffRow({ entry }: { entry: DiffEntry }) {
  const latStr = (span: Record<string, unknown> | null) =>
    span?.latency_ms != null ? `${Number(span.latency_ms).toFixed(0)}ms` : "—";
  const statusStr = (span: Record<string, unknown> | null) =>
    span ? (span.status === "success" ? "✓" : span.status === "error" ? "✗" : "⏱") : "—";
  const deltaColor =
    entry.latency_delta_pct === null ? ""
    : entry.latency_delta_pct > 0 ? "text-red-500" : "text-emerald-500";

  const rowBg =
    entry.status === "matched" ? ""
    : entry.status === "diverged" ? "bg-yellow-500/5"
    : entry.status === "only_a"  ? "bg-blue-500/5"
    : "bg-purple-500/5";

  const statusIcon =
    entry.status === "matched" ? "=" : entry.status === "diverged" ? "≠"
    : entry.status === "only_a" ? "A" : "B";

  const statusColor =
    entry.status === "matched" ? "text-emerald-500"
    : entry.status === "diverged" ? "text-yellow-500"
    : entry.status === "only_a" ? "text-blue-400"
    : "text-purple-400";

  return (
    <tr className={cn("border-b border-border/50 text-[12px]", rowBg)}>
      <td className="px-4 py-2 font-mono truncate max-w-[200px]" style={{ fontFamily: "var(--font-geist-mono)" }}>
        <span className={cn("mr-2 font-bold", statusColor)}>{statusIcon}</span>
        <span className="text-muted-foreground">{entry.tool_key}</span>
      </td>
      <td className="px-4 py-2 text-center font-mono" style={{ fontFamily: "var(--font-geist-mono)" }}>
        <span className={entry.span_a ? (CALL_STATUS_COLOR[entry.span_a.status as keyof typeof CALL_STATUS_COLOR] ?? "") : "text-muted-foreground"}>
          {statusStr(entry.span_a)}
        </span>
      </td>
      <td className="px-4 py-2 text-right font-mono text-muted-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>
        {latStr(entry.span_a)}
      </td>
      <td className="px-4 py-2 text-center font-mono" style={{ fontFamily: "var(--font-geist-mono)" }}>
        <span className={entry.span_b ? (CALL_STATUS_COLOR[entry.span_b.status as keyof typeof CALL_STATUS_COLOR] ?? "") : "text-muted-foreground"}>
          {statusStr(entry.span_b)}
        </span>
      </td>
      <td className="px-4 py-2 text-right font-mono text-muted-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>
        {latStr(entry.span_b)}
      </td>
      <td className={cn("px-4 py-2 text-right font-mono font-semibold", deltaColor)} style={{ fontFamily: "var(--font-geist-mono)" }}>
        {entry.latency_delta_pct !== null
          ? `${entry.latency_delta_pct > 0 ? "+" : ""}${entry.latency_delta_pct}%`
          : "—"}
      </td>
    </tr>
  );
}

function CompareDrawer({ idA, idB, onClose, projectId }: { idA: string; idB: string; onClose: () => void; projectId?: string }) {
  const [cmp, setCmp] = useState<SessionComparison | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    compareSessions(idA, idB, projectId)
      .then((c) => { setCmp(c); setLoading(false); })
      .catch((e) => { setError(e.message); setLoading(false); });
  }, [idA, idB, projectId]);

  return (
    <div
      className="rounded-xl border overflow-hidden mt-2"
      style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
    >
      <div
        className="flex items-center justify-between px-4 py-3 border-b"
        style={{ background: "hsl(var(--card-raised))", borderColor: "hsl(var(--border))" }}
      >
        <div className="flex items-center gap-3 min-w-0">
          <GitCompare size={13} className="text-primary flex-shrink-0" />
          <div className="flex items-center gap-2 text-[12px]" style={{ fontFamily: "var(--font-geist-mono)" }}>
            <span className="text-blue-400 font-semibold">{idA.slice(0, 12)}…</span>
            <span className="text-muted-foreground">vs</span>
            <span className="text-purple-400 font-semibold">{idB.slice(0, 12)}…</span>
          </div>
          {cmp && (
            <div className="hidden sm:flex items-center gap-2 text-[11px]">
              <span className="text-emerald-500">{cmp.summary.matched} matched</span>
              {cmp.summary.diverged > 0 && <><span className="text-muted-foreground">·</span><span className="text-yellow-500">{cmp.summary.diverged} diverged</span></>}
              {cmp.summary.only_a > 0 && <><span className="text-muted-foreground">·</span><span className="text-blue-400">{cmp.summary.only_a} only in A</span></>}
              {cmp.summary.only_b > 0 && <><span className="text-muted-foreground">·</span><span className="text-purple-400">{cmp.summary.only_b} only in B</span></>}
            </div>
          )}
        </div>
        <button onClick={onClose} className="btn btn-ghost p-1.5" aria-label="Close compare">
          <X size={14} />
        </button>
      </div>

      <div className="overflow-x-auto">
        {loading ? (
          <div className="p-10 flex items-center justify-center">
            <div className="w-6 h-6 rounded-full border-2 border-primary border-t-transparent spin" />
          </div>
        ) : error ? (
          <div className="p-8 text-center text-sm" style={{ color: "hsl(var(--danger))" }}>
            <AlertCircle size={20} className="mx-auto mb-2" /> {error}
          </div>
        ) : !cmp || cmp.diff.length === 0 ? (
          <p className="p-8 text-center text-sm text-muted-foreground">No spans found</p>
        ) : (
          <table className="w-full">
            <thead>
              <tr style={{ borderBottom: "1px solid hsl(var(--border))", background: "hsl(var(--card-raised))" }}>
                <th className="px-4 py-2.5 text-left text-[11px] font-semibold text-muted-foreground uppercase tracking-wide">Tool</th>
                <th className="px-4 py-2.5 text-center text-[11px] font-semibold text-blue-400 uppercase tracking-wide">A status</th>
                <th className="px-4 py-2.5 text-right text-[11px] font-semibold text-blue-400 uppercase tracking-wide">A latency</th>
                <th className="px-4 py-2.5 text-center text-[11px] font-semibold text-purple-400 uppercase tracking-wide">B status</th>
                <th className="px-4 py-2.5 text-right text-[11px] font-semibold text-purple-400 uppercase tracking-wide">B latency</th>
                <th className="px-4 py-2.5 text-right text-[11px] font-semibold text-muted-foreground uppercase tracking-wide">Δ latency</th>
              </tr>
            </thead>
            <tbody>
              {cmp.diff.map((entry, i) => <DiffRow key={i} entry={entry} />)}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

/* ── Page ───────────────────────────────────────────────────── */
export default function SessionsPage() {
  const [hours, setHours] = useState(24);
  const [selected, setSelected] = useState<string | null>(null);
  const [compareWith, setCompareWith] = useState<string | null>(null);
  const [comparing, setComparing] = useState(false);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "clean" | "failed">("all");
  const [agentFilter, setAgentFilter] = useState<string>("all");
  const [page, setPage] = useState(0);

  const { activeProject } = useProject();
  const p = activeProject ? `&project_id=${activeProject.id}` : "";

  const { data: sessions, isLoading, error } = useSWR<AgentSession[]>(
    `/api/agents/sessions?hours=${hours}&limit=500${p}`,
    fetcher,
    { refreshInterval: 30_000 }
  );

  useEffect(() => { setPage(0); }, [search, statusFilter, agentFilter, hours]);

  const agentNames = useMemo(() => {
    if (!sessions) return [];
    return Array.from(new Set(sessions.map((s) => s.agent_name ?? "unknown"))).sort();
  }, [sessions]);

  const filtered = useMemo(() => {
    if (!sessions) return [];
    return sessions.filter((s) => {
      if (statusFilter === "clean" && s.failed_calls > 0) return false;
      if (statusFilter === "failed" && s.failed_calls === 0) return false;
      if (agentFilter !== "all" && (s.agent_name ?? "unknown") !== agentFilter) return false;
      if (search) {
        const q = search.toLowerCase();
        if (
          !s.session_id.toLowerCase().includes(q) &&
          !(s.agent_name ?? "").toLowerCase().includes(q) &&
          !s.servers_used?.some((srv) => srv.toLowerCase().includes(q))
        ) return false;
      }
      return true;
    });
  }, [sessions, statusFilter, agentFilter, search]);

  const countAll    = sessions?.length ?? 0;
  const countClean  = sessions?.filter((s) => s.failed_calls === 0).length ?? 0;
  const countFailed = sessions?.filter((s) => s.failed_calls > 0).length ?? 0;
  const totalPages  = Math.ceil(filtered.length / PAGE_SIZE);
  const paginated   = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const totalCalls  = filtered.reduce((n, s) => n + s.tool_calls, 0);
  const totalFailed = filtered.reduce((n, s) => n + s.failed_calls, 0);

  const TIME_OPTIONS = [[1,"1h"],[6,"6h"],[24,"24h"],[168,"7d"]] as const;

  return (
    <div className="space-y-4 page-in">
      {/* ── Header ────────────────────────────────────────────── */}
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-foreground">Sessions</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            {filtered.length} sessions · {totalCalls} tool calls
            {totalFailed > 0 && <span style={{ color: "hsl(var(--danger))" }}> · {totalFailed} failures</span>}
            {selected && !comparing && (
              <span className="text-primary"> · 1 selected — click another to compare</span>
            )}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {selected && compareWith && !comparing && (
            <button
              onClick={() => setComparing(true)}
              className="btn badge-primary"
            >
              <GitCompare size={12} /> Compare
            </button>
          )}
          {(selected || comparing) && (
            <button
              onClick={() => { setSelected(null); setCompareWith(null); setComparing(false); }}
              className="btn btn-ghost"
            >
              <X size={12} /> Clear
            </button>
          )}
          <div
            className="flex rounded-lg border p-0.5"
            style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
          >
            {TIME_OPTIONS.map(([v, l]) => (
              <button
                key={v}
                onClick={() => setHours(v)}
                className={cn(
                  "px-2.5 py-1.5 rounded-md text-xs font-medium transition-all",
                  hours === v
                    ? "bg-primary text-white shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                {l}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ── Filters ───────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-2.5">
        <div className="relative flex-1 min-w-[180px] max-w-sm">
          <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search session ID, agent, server…"
            className="input-base pl-8 h-[34px] text-[13px]"
          />
        </div>

        <div className="flex items-center gap-1.5">
          {(
            [
              ["all", "All", countAll],
              ["clean", "Clean", countClean],
              ["failed", "Failed", countFailed],
            ] as const
          ).map(([key, label, count]) => (
            <button
              key={key}
              onClick={() => setStatusFilter(key)}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-all",
                statusFilter === key
                  ? "bg-primary/10 border-primary/30 text-primary"
                  : "bg-card border-border text-muted-foreground hover:bg-accent hover:text-foreground"
              )}
            >
              {label}
              <span
                className={cn(
                  "text-[10px] px-1.5 py-0.5 rounded-full min-w-[18px] text-center tabular-nums",
                  statusFilter === key ? "bg-primary/15 text-primary" : "bg-muted text-muted-foreground"
                )}
              >
                {count}
              </span>
            </button>
          ))}
        </div>

        {agentNames.length > 1 && (
          <div className="flex items-center gap-1.5">
            <Filter size={13} className="text-muted-foreground" />
            <select
              value={agentFilter}
              onChange={(e) => setAgentFilter(e.target.value)}
              className="text-xs rounded-lg px-2 py-1.5 border border-border bg-card text-foreground outline-none h-[34px]"
            >
              <option value="all">All agents</option>
              {agentNames.map((name) => (
                <option key={name} value={name}>{name}</option>
              ))}
            </select>
          </div>
        )}
      </div>

      {/* ── Table ─────────────────────────────────────────────── */}
      <div
        className="rounded-xl border overflow-hidden"
        style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
      >
        {isLoading ? (
          <div className="divide-y" style={{ borderColor: "hsl(var(--border))" }}>
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="px-5 py-3.5 flex items-center justify-between">
                <div className="space-y-1.5">
                  <div className="skeleton h-3.5 w-36 rounded" />
                  <div className="skeleton h-2.5 w-48 rounded" />
                </div>
                <div className="flex gap-3">
                  <div className="skeleton h-3 w-16 rounded" />
                  <div className="skeleton h-5 w-16 rounded-full" />
                </div>
              </div>
            ))}
          </div>
        ) : error ? (
          <div className="p-12 text-center">
            <AlertCircle size={32} className="mx-auto mb-3 text-muted-foreground opacity-30" />
            <p className="text-sm text-muted-foreground">Could not load sessions — check ClickHouse storage</p>
          </div>
        ) : filtered.length === 0 ? (
          <div className="p-12 text-center">
            <div
              className="w-14 h-14 rounded-2xl flex items-center justify-center mx-auto mb-4"
              style={{ background: "hsl(var(--muted))" }}
            >
              <GitBranch size={22} className="text-muted-foreground" />
            </div>
            <p className="text-sm font-semibold text-foreground mb-1">
              {sessions && sessions.length > 0 ? "No sessions match your filters" : "No sessions yet"}
            </p>
            <p className="text-xs text-muted-foreground">
              {sessions && sessions.length > 0
                ? "Try adjusting the search or filter criteria"
                : "Instrument your agents with the LangSight SDK to capture traces"}
            </p>
          </div>
        ) : (
          <>
            <table className="w-full">
              <thead>
                <tr
                  style={{
                    borderBottom: "1px solid hsl(var(--border))",
                    background: "hsl(var(--card-raised))",
                  }}
                >
                  {[
                    ["Session ID", "text-left"],
                    ["Agent", "text-left"],
                    ["Calls", "text-right"],
                    ["Failed", "text-right"],
                    ["Duration", "text-right"],
                    ["Servers", "text-left"],
                    ["Started", "text-left"],
                  ].map(([h, align]) => (
                    <th
                      key={h}
                      className={cn(
                        "px-4 py-2.5 text-[11px] font-semibold text-muted-foreground uppercase tracking-wide",
                        align
                      )}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y" style={{ borderColor: "hsl(var(--border))" }}>
                {paginated.map((s) => {
                  const isA = selected === s.session_id;
                  const isB = compareWith === s.session_id;

                  function handleRowClick() {
                    if (comparing) { setComparing(false); setCompareWith(null); return; }
                    if (isA) { setSelected(null); setCompareWith(null); return; }
                    if (isB) { setCompareWith(null); return; }
                    if (selected && !compareWith) { setCompareWith(s.session_id); return; }
                    setSelected(s.session_id);
                    setCompareWith(null);
                  }

                  return (
                    <tr
                      key={s.session_id}
                      onClick={handleRowClick}
                      className={cn(
                        "cursor-pointer transition-colors text-sm group",
                        isA ? "bg-blue-500/5 border-l-[3px] border-l-blue-400"
                        : isB ? "bg-purple-500/5 border-l-[3px] border-l-purple-400"
                        : "hover:bg-accent/40 border-l-[3px] border-l-transparent"
                      )}
                    >
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          {isA ? (
                            <span className="text-[10px] font-bold text-blue-400 w-4">A</span>
                          ) : isB ? (
                            <span className="text-[10px] font-bold text-purple-400 w-4">B</span>
                          ) : (
                            <ChevronRight size={12} className="text-muted-foreground group-hover:text-primary transition-colors w-4" />
                          )}
                          <span
                            className="text-[12px] font-mono text-foreground"
                            style={{ fontFamily: "var(--font-geist-mono)" }}
                          >
                            {s.session_id.slice(0, 16)}…
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-[12px] text-muted-foreground">
                        {s.agent_name || "—"}
                      </td>
                      <td className="px-4 py-3 text-[12px] text-right">
                        <span className="flex items-center justify-end gap-1 text-muted-foreground">
                          <Zap size={10} />
                          {s.tool_calls}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-[12px] text-right">
                        {s.failed_calls > 0 ? (
                          <span className="font-semibold" style={{ color: "hsl(var(--danger))" }}>
                            {s.failed_calls}
                          </span>
                        ) : (
                          <span className="text-muted-foreground">0</span>
                        )}
                      </td>
                      <td
                        className="px-4 py-3 text-[12px] text-right text-muted-foreground"
                        style={{ fontFamily: "var(--font-geist-mono)" }}
                      >
                        {formatDuration(s.duration_ms)}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex flex-wrap gap-1">
                          {(s.servers_used || []).slice(0, 2).map((srv) => (
                            <span
                              key={srv}
                              className="px-1.5 py-0.5 rounded text-[10px]"
                              style={{
                                background: "hsl(var(--muted))",
                                border: "1px solid hsl(var(--border))",
                                color: "hsl(var(--muted-foreground))",
                                fontFamily: "var(--font-geist-mono)",
                              }}
                            >
                              {srv}
                            </span>
                          ))}
                          {(s.servers_used?.length ?? 0) > 2 && (
                            <span className="text-[10px] text-muted-foreground">
                              +{s.servers_used.length - 2}
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-[12px] text-muted-foreground">
                        <div className="flex items-center gap-1">
                          <Clock size={11} />
                          {timeAgo(s.first_call_at)}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>

            {/* Pagination */}
            {totalPages > 1 && (
              <div
                className="flex items-center justify-between px-4 py-3 border-t text-xs text-muted-foreground"
                style={{ borderColor: "hsl(var(--border))", background: "hsl(var(--card-raised))" }}
              >
                <span>
                  {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, filtered.length)} of {filtered.length}
                </span>
                <div className="flex items-center gap-0.5">
                  <button
                    onClick={() => setPage(0)}
                    disabled={page === 0}
                    className="p-1.5 rounded hover:bg-accent disabled:opacity-30 transition-colors"
                  >
                    <ChevronsLeft size={13} />
                  </button>
                  <button
                    onClick={() => setPage((p) => Math.max(0, p - 1))}
                    disabled={page === 0}
                    className="p-1.5 rounded hover:bg-accent disabled:opacity-30 transition-colors"
                  >
                    <ChevronLeft size={13} />
                  </button>
                  <span className="px-2 tabular-nums">{page + 1} / {totalPages}</span>
                  <button
                    onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                    disabled={page >= totalPages - 1}
                    className="p-1.5 rounded hover:bg-accent disabled:opacity-30 transition-colors"
                  >
                    <ChevronRight size={13} />
                  </button>
                  <button
                    onClick={() => setPage(totalPages - 1)}
                    disabled={page >= totalPages - 1}
                    className="p-1.5 rounded hover:bg-accent disabled:opacity-30 transition-colors"
                  >
                    <ChevronsRight size={13} />
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {/* ── Trace / Compare drawers ────────────────────────────── */}
      {comparing && selected && compareWith && (
        <CompareDrawer
          idA={selected}
          idB={compareWith}
          onClose={() => { setComparing(false); setCompareWith(null); }}
          projectId={activeProject?.id}
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
          projectId={activeProject?.id}
        />
      )}
    </div>
  );
}
