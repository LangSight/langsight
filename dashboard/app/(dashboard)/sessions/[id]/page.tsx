"use client";

export const dynamic = "force-dynamic";

import { useState, useEffect, useMemo } from "react";
import { useParams, useRouter } from "next/navigation";
import useSWR from "swr";
import {
  ChevronRight, ChevronDown, GitBranch, Clock, Zap, AlertCircle,
  Search, GitCompare, Play, ArrowLeft, Columns2,
} from "lucide-react";
import { fetcher, getSessionTrace, compareSessions, replaySession } from "@/lib/api";
import { useProject } from "@/lib/project-context";
import { cn, timeAgo, formatDuration, CALL_STATUS_COLOR, SPAN_TYPE_ICON } from "@/lib/utils";
import type { AgentSession, SessionTrace, SpanNode, SessionComparison, DiffEntry } from "@/lib/types";

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

/* ── Diff row (compare view) ──────────────────────────────────── */
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

/* ── Compare picker ───────────────────────────────────────────── */
function ComparePicker({
  sessions,
  selectedId,
  onPick,
  onCancel,
}: {
  sessions: AgentSession[];
  selectedId: string;
  onPick: (id: string) => void;
  onCancel: () => void;
}) {
  const [pickerSearch, setPickerSearch] = useState("");

  const candidates = useMemo(() => {
    return sessions
      .filter((s) => s.session_id !== selectedId)
      .filter((s) => {
        if (!pickerSearch) return true;
        const q = pickerSearch.toLowerCase();
        return (
          s.session_id.toLowerCase().includes(q) ||
          (s.agent_name ?? "").toLowerCase().includes(q)
        );
      })
      .slice(0, 10);
  }, [sessions, selectedId, pickerSearch]);

  return (
    <div
      className="mt-6 rounded-xl border overflow-hidden"
      style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
    >
      <div
        className="border-b px-4 py-3"
        style={{ background: "hsl(var(--card-raised))", borderColor: "hsl(var(--border))" }}
      >
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <GitCompare size={13} className="text-primary" />
            <span className="text-sm font-semibold text-foreground">Select a session to compare with</span>
          </div>
          <button onClick={onCancel} className="btn btn-ghost text-xs">Cancel</button>
        </div>
        <div className="mt-3">
          <div className="relative max-w-sm">
            <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              type="text"
              value={pickerSearch}
              onChange={(e) => setPickerSearch(e.target.value)}
              placeholder="Search session ID or agent..."
              className="input-base pl-8 h-[34px] text-[13px] w-full"
              autoFocus
            />
          </div>
        </div>
      </div>

      <div className="max-h-[400px] overflow-y-auto">
        {candidates.length === 0 ? (
          <p className="p-8 text-center text-sm text-muted-foreground">No matching sessions</p>
        ) : (
          <div className="divide-y" style={{ borderColor: "hsl(var(--border))" }}>
            {candidates.map((s) => (
              <button
                key={s.session_id}
                onClick={() => onPick(s.session_id)}
                className="w-full text-left px-4 py-3 hover:bg-accent/40 transition-colors flex items-center justify-between gap-4"
              >
                <div className="min-w-0">
                  <code
                    className="text-[12px] text-foreground block truncate"
                    style={{ fontFamily: "var(--font-geist-mono)" }}
                  >
                    {s.session_id.slice(0, 24)}...
                  </code>
                  <div className="flex items-center gap-2 text-[11px] text-muted-foreground mt-0.5">
                    {s.agent_name && <span>{s.agent_name}</span>}
                    <span>{s.tool_calls} calls</span>
                    {s.failed_calls > 0 && (
                      <span style={{ color: "hsl(var(--danger))" }}>{s.failed_calls} failed</span>
                    )}
                    <span>{formatDuration(s.duration_ms)}</span>
                  </div>
                </div>
                <div className="flex items-center gap-1 text-[11px] text-muted-foreground flex-shrink-0">
                  <Clock size={11} />
                  {timeAgo(s.first_call_at)}
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Compare detail ───────────────────────────────────────────── */
function CompareDetail({
  idA, idB, sessionA, sessionB, onBack, projectId,
}: {
  idA: string;
  idB: string;
  sessionA: AgentSession | undefined;
  sessionB: AgentSession | undefined;
  onBack: () => void;
  projectId?: string;
}) {
  const [cmp, setCmp] = useState<SessionComparison | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setCmp(null);
    setError(null);
    compareSessions(idA, idB, projectId)
      .then((c) => { setCmp(c); setLoading(false); })
      .catch((e) => { setError(e.message); setLoading(false); });
  }, [idA, idB, projectId]);

  return (
    <div
      className="mt-6 rounded-xl border overflow-hidden"
      style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
    >
      <div
        className="border-b px-4 py-3"
        style={{ background: "hsl(var(--card-raised))", borderColor: "hsl(var(--border))" }}
      >
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <Columns2 size={13} className="text-primary flex-shrink-0" />
            <div className="flex items-center gap-2 text-[12px] min-w-0" style={{ fontFamily: "var(--font-geist-mono)" }}>
              <div className="flex items-center gap-1.5 min-w-0">
                <span className="text-[10px] font-bold text-blue-400 bg-blue-500/10 px-1.5 py-0.5 rounded">Base</span>
                <span className="text-foreground truncate">{idA.slice(0, 12)}...</span>
                {sessionA?.agent_name && <span className="text-muted-foreground text-[11px]">({sessionA.agent_name})</span>}
              </div>
              <span className="text-muted-foreground">vs</span>
              <div className="flex items-center gap-1.5 min-w-0">
                <span className="text-[10px] font-bold text-purple-400 bg-purple-500/10 px-1.5 py-0.5 rounded">Compare</span>
                <span className="text-foreground truncate">{idB.slice(0, 12)}...</span>
                {sessionB?.agent_name && <span className="text-muted-foreground text-[11px]">({sessionB.agent_name})</span>}
              </div>
            </div>
          </div>
          <button onClick={onBack} className="btn btn-ghost text-xs">Close</button>
        </div>
        {cmp && (
          <div className="flex items-center gap-2 text-[11px] mt-2 ml-[28px]">
            <span className="text-emerald-500">{cmp.summary.matched} matched</span>
            {cmp.summary.diverged > 0 && <><span className="text-muted-foreground">·</span><span className="text-yellow-500">{cmp.summary.diverged} diverged</span></>}
            {cmp.summary.only_a > 0 && <><span className="text-muted-foreground">·</span><span className="text-blue-400">{cmp.summary.only_a} only in base</span></>}
            {cmp.summary.only_b > 0 && <><span className="text-muted-foreground">·</span><span className="text-purple-400">{cmp.summary.only_b} only in compare</span></>}
          </div>
        )}
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
                <th className="px-4 py-2.5 text-center text-[11px] font-semibold text-blue-400 uppercase tracking-wide">Base status</th>
                <th className="px-4 py-2.5 text-right text-[11px] font-semibold text-blue-400 uppercase tracking-wide">Base latency</th>
                <th className="px-4 py-2.5 text-center text-[11px] font-semibold text-purple-400 uppercase tracking-wide">Compare status</th>
                <th className="px-4 py-2.5 text-right text-[11px] font-semibold text-purple-400 uppercase tracking-wide">Compare latency</th>
                <th className="px-4 py-2.5 text-right text-[11px] font-semibold text-muted-foreground uppercase tracking-wide">Delta</th>
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

/* ══════════════════════════════════════════════════════════════ */
/* ── Session Detail Page ──────────────────────────────────────── */
/* ══════════════════════════════════════════════════════════════ */
export default function SessionDetailPage() {
  const params = useParams();
  const router = useRouter();
  const sessionId = params.id as string;

  const { activeProject } = useProject();
  const projectId = activeProject?.id;
  const p = projectId ? `&project_id=${projectId}` : "";

  /* Trace data */
  const [trace, setTrace] = useState<SessionTrace | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  /* Replay */
  const [replaying, setReplaying] = useState(false);
  const [replayError, setReplayError] = useState<string | null>(null);

  /* Compare */
  const [comparePicking, setComparePicking] = useState(false);
  const [compareWith, setCompareWith] = useState<string | null>(null);

  /* Sessions list (for compare picker) */
  const { data: sessions } = useSWR<AgentSession[]>(
    `/api/agents/sessions?hours=168&limit=500${p}`,
    fetcher
  );

  /* Current session metadata from the sessions list */
  const session = useMemo(
    () => sessions?.find((s) => s.session_id === sessionId),
    [sessions, sessionId]
  );
  const compareSession = useMemo(
    () => sessions?.find((s) => s.session_id === compareWith),
    [sessions, compareWith]
  );

  /* Fetch trace */
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
      await replaySession(sessionId, 10, 60, projectId);
    } catch (e: unknown) {
      setReplayError(e instanceof Error ? e.message : "Replay failed");
    } finally {
      setReplaying(false);
    }
  }

  return (
    <div className="page-in flex flex-col" style={{ height: "calc(100vh - 4rem)" }}>
      {/* ── Back + Header ──────────────────────────────────────── */}
      <div className="flex-shrink-0 pb-3">
        <button
          onClick={() => router.push("/sessions")}
          className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors mb-3"
        >
          <ArrowLeft size={14} />
          Back to Sessions
        </button>

        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 min-w-0">
            <GitBranch size={15} className="text-primary flex-shrink-0" />
            <div className="min-w-0">
              <code
                className="text-sm text-foreground block truncate"
                style={{ fontFamily: "var(--font-geist-mono)" }}
              >
                {sessionId}
              </code>
              <div className="flex items-center gap-2 text-[12px] text-muted-foreground mt-0.5">
                {session?.agent_name && (
                  <span className="text-primary font-medium">{session.agent_name}</span>
                )}
                {trace && (
                  <>
                    <span>{trace.total_spans} spans</span>
                    <span>·</span>
                    <span>{trace.tool_calls} tool calls</span>
                    {trace.failed_calls > 0 && (
                      <><span>·</span>
                      <span style={{ color: "hsl(var(--danger))" }} className="font-semibold">
                        {trace.failed_calls} failed
                      </span></>
                    )}
                    {trace.duration_ms && (
                      <><span>·</span><span>{formatDuration(trace.duration_ms)}</span></>
                    )}
                  </>
                )}
                {session && (
                  <>
                    <span>·</span>
                    <span className="flex items-center gap-1"><Clock size={11} />{timeAgo(session.first_call_at)}</span>
                  </>
                )}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2 flex-shrink-0">
            <button
              onClick={handleReplay}
              disabled={replaying || loading}
              className="btn btn-secondary text-[12px] py-1.5 px-3"
            >
              {replaying
                ? <><span className="w-3 h-3 border border-current border-t-transparent rounded-full spin" />Replaying...</>
                : <><Play size={11} />Replay</>
              }
            </button>
            <button
              onClick={() => { setComparePicking((v) => !v); setCompareWith(null); }}
              className={cn(
                "btn text-[12px] py-1.5 px-3",
                comparePicking ? "btn-primary" : "btn-secondary"
              )}
            >
              <GitCompare size={11} />Compare
            </button>
          </div>
        </div>
      </div>

      {replayError && (
        <div
          className="flex-shrink-0 rounded-lg px-4 py-2 text-xs mb-3"
          style={{ background: "hsl(var(--danger-bg))", color: "hsl(var(--danger))", border: "1px solid hsl(var(--danger) / 0.2)" }}
        >
          Replay failed: {replayError}
        </div>
      )}

      {/* ── Trace tree ─────────────────────────────────────────── */}
      <div
        className="flex-1 rounded-xl border overflow-hidden flex flex-col min-h-0"
        style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
      >
        <div className="flex-1 overflow-y-auto overflow-x-auto">
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
                <tr
                  className="sticky top-0 z-10"
                  style={{ borderBottom: "1px solid hsl(var(--border))", background: "hsl(var(--card-raised))" }}
                >
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

      {/* ── Compare picker (shown below trace when active) ───── */}
      {comparePicking && !compareWith && sessions && (
        <ComparePicker
          sessions={sessions}
          selectedId={sessionId}
          onPick={(id) => { setCompareWith(id); setComparePicking(false); }}
          onCancel={() => setComparePicking(false)}
        />
      )}

      {/* ── Compare diff (shown below trace) ─────────────────── */}
      {compareWith && (
        <CompareDetail
          idA={sessionId}
          idB={compareWith}
          sessionA={session}
          sessionB={compareSession}
          onBack={() => { setCompareWith(null); setComparePicking(false); }}
          projectId={projectId}
        />
      )}
    </div>
  );
}
