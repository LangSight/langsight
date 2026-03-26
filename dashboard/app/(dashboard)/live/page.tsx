"use client";

export const dynamic = "force-dynamic";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Radio, AlertTriangle, CheckCircle, ChevronRight, WifiOff } from "lucide-react";
import { useProject } from "@/lib/project-context";
import { cn } from "@/lib/utils";
import { mergeSpan, toUTCMs, RUNNING_MS, EXPIRE_MS, type LiveRow, type SpanEvent } from "@/lib/live-utils";
import type { AgentSession } from "@/lib/types";

/* ── Constants ───────────────────────────────────────────────── */
const STUCK_MS          = 2 * 60_000;  // > 2min since last span → stuck
const RECONNECT_BASE_MS = 2_000;       // initial reconnect delay
const RECONNECT_MAX_MS  = 30_000;      // max reconnect delay

type SessionStatus = "running" | "idle" | "stuck" | "done";
type ConnectionState = "connecting" | "connected" | "reconnecting" | "error";

/* ── Helpers ─────────────────────────────────────────────────── */
function getStatus(row: LiveRow, now: number): SessionStatus {
  if (now < row.running_until) return "running";
  const age = now - row.last_seen_ms;
  if (age < RUNNING_MS) return "running";
  if (!row.ever_grew) return "done";
  const stableFor = now - row.stable_since;
  if (stableFor < STUCK_MS) return "idle";
  return "stuck";
}

function elapsed(ms: number): string {
  const s = Math.floor(ms / 1000);
  if (s < 60)  return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60)  return `${m}m ${s % 60}s ago`;
  return `${Math.floor(m / 60)}h ${m % 60}m ago`;
}

function fmtDuration(from: number, to: number): string {
  const s = Math.floor((to - from) / 1000);
  if (s < 1)   return "<1s";
  if (s < 60)  return `${s}s`;
  const m = Math.floor(s / 60);
  return `${m}m ${s % 60}s`;
}

/* ── Status badge ────────────────────────────────────────────── */
function StatusDot({ status }: { status: SessionStatus }) {
  if (status === "running") return (
    <span className="flex items-center gap-1.5">
      <span className="relative flex w-2 h-2">
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75" style={{ background: "#22c55e" }} />
        <span className="relative inline-flex rounded-full w-2 h-2" style={{ background: "#22c55e" }} />
      </span>
      <span className="text-[11px] font-semibold" style={{ color: "#22c55e" }}>running</span>
    </span>
  );
  if (status === "idle") return (
    <span className="flex items-center gap-1.5">
      <span className="w-2 h-2 rounded-full" style={{ background: "#f59e0b" }} />
      <span className="text-[11px] font-semibold" style={{ color: "#f59e0b" }}>idle</span>
    </span>
  );
  if (status === "stuck") return (
    <span className="flex items-center gap-1.5">
      <span className="w-2 h-2 rounded-full animate-pulse" style={{ background: "#f59e0b" }} />
      <span className="text-[11px] font-medium" style={{ color: "#f59e0b" }}>verifying…</span>
    </span>
  );
  return (
    <span className="flex items-center gap-1.5">
      <CheckCircle size={12} className="text-muted-foreground" />
      <span className="text-[11px] text-muted-foreground">done</span>
    </span>
  );
}

/* ── Page ────────────────────────────────────────────────────── */
export default function LivePage() {
  const router = useRouter();
  const { activeProject } = useProject();
  const pid = activeProject?.id ?? null;

  const [rows, setRows]           = useState<Map<string, LiveRow>>(new Map());
  const [now, setNow]             = useState(Date.now());
  const [connState, setConnState] = useState<ConnectionState>("connecting");
  const esRef                     = useRef<EventSource | null>(null);
  const reconnectTimer            = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectDelay            = useRef(RECONNECT_BASE_MS);
  const unmounted                 = useRef(false);

  // Clock — tick every second
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1_000);
    return () => clearInterval(id);
  }, []);

  // Seed rows from DB on mount so existing sessions appear immediately,
  // even before any new SSE span arrives.
  useEffect(() => {
    const url = `/api/proxy/agents/sessions?hours=1${pid ? `&project_id=${encodeURIComponent(pid)}` : ""}`;
    fetch(url)
      .then(r => r.ok ? r.json() : [])
      .then((sessions: AgentSession[]) => {
        const now = Date.now();
        const cutoff = now - EXPIRE_MS;
        setRows(prev => {
          const next = new Map(prev);
          for (const s of sessions) {
            const firstMs = toUTCMs(s.first_call_at);
            const lastMs  = firstMs + (s.duration_ms ?? 0);
            if (lastMs < cutoff) continue;
            if (next.has(s.session_id)) continue;  // SSE already has a fresher version
            next.set(s.session_id, {
              session_id:    s.session_id,
              agent_name:    s.agent_name ?? null,
              span_count:    s.tool_calls ?? 0,
              error_count:   s.failed_calls ?? 0,
              first_seen_ms: firstMs,
              last_seen_ms:  lastMs,
              running_until: 0,         // not currently running — set by new SSE spans
              ever_grew:     false,
              stable_since:  lastMs,
            });
          }
          return next;
        });
      })
      .catch(() => {/* fail silently — SSE will still populate in real time */});
  }, [pid]);

  // SSE connection with exponential-backoff reconnect
  useEffect(() => {
    unmounted.current = false;

    function connect() {
      if (unmounted.current) return;

      const url = `/api/live/stream${pid ? `?project_id=${encodeURIComponent(pid)}` : ""}`;
      const es = new EventSource(url);
      esRef.current = es;
      setConnState("connecting");

      es.onopen = () => {
        if (unmounted.current) { es.close(); return; }
        setConnState("connected");
        reconnectDelay.current = RECONNECT_BASE_MS; // reset on successful connection
      };

      es.addEventListener("span:new", (event) => {
        if (unmounted.current) { es.close(); return; }
        try {
          const span = JSON.parse((event as MessageEvent).data) as SpanEvent;
          if (!span.session_id) return;
          setRows(prev => mergeSpan(prev, span));
        } catch {
          // Malformed event — ignore
        }
      });

      es.onerror = () => {
        if (unmounted.current) { es.close(); return; }
        es.close();
        esRef.current = null;
        setConnState("reconnecting");

        // Exponential backoff
        const delay = reconnectDelay.current;
        reconnectDelay.current = Math.min(delay * 2, RECONNECT_MAX_MS);
        reconnectTimer.current = setTimeout(connect, delay);
      };
    }

    connect();

    return () => {
      unmounted.current = true;
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      esRef.current?.close();
      esRef.current = null;
    };
  }, [pid]);

  // Sort: running → idle → stuck → done, then by last_seen desc
  const sorted = [...rows.values()].sort((a, b) => {
    const order: Record<SessionStatus, number> = { running: 0, idle: 1, stuck: 2, done: 3 };
    const sa = getStatus(a, now), sb = getStatus(b, now);
    if (order[sa] !== order[sb]) return order[sa] - order[sb];
    return b.last_seen_ms - a.last_seen_ms;
  });

  const runningCount = sorted.filter(r => getStatus(r, now) === "running").length;
  const stuckCount   = sorted.filter(r => getStatus(r, now) === "stuck").length;
  const isConnecting = connState === "connecting" || connState === "reconnecting";

  return (
    <div className="space-y-4 page-in">
      {/* ── Header ─────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center"
            style={{ background: "rgba(34,197,94,0.12)", border: "1px solid rgba(34,197,94,0.2)" }}>
            <Radio size={15} style={{ color: "#22c55e" }} />
          </div>
          <div>
            <h1 className="text-xl font-bold text-foreground">Live</h1>
            <p className="text-[11px] text-muted-foreground mt-0.5">
              {isConnecting
                ? connState === "reconnecting" ? "Reconnecting…" : "Connecting…"
                : runningCount > 0
                ? `${runningCount} agent${runningCount !== 1 ? "s" : ""} running now`
                : sorted.length > 0
                ? "No agents running right now"
                : "Waiting for agent activity…"}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {stuckCount > 0 && (
            <span className="flex items-center gap-1.5 text-[11px] font-medium px-2 py-1 rounded-full"
              style={{ background: "rgba(245,158,11,0.1)", color: "#f59e0b", border: "1px solid rgba(245,158,11,0.2)" }}>
              <AlertTriangle size={11} />
              {stuckCount} verifying
            </span>
          )}
          {/* Connection status indicator */}
          {connState === "connected" ? (
            <span className="flex items-center gap-1.5 text-[11px] font-semibold px-2 py-1 rounded-full"
              style={{ background: "rgba(34,197,94,0.12)", color: "#22c55e", border: "1px solid rgba(34,197,94,0.25)" }}>
              <span className="relative flex w-1.5 h-1.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75" style={{ background: "#22c55e" }} />
                <span className="relative inline-flex rounded-full w-1.5 h-1.5" style={{ background: "#22c55e" }} />
              </span>
              LIVE
            </span>
          ) : connState === "reconnecting" ? (
            <span className="flex items-center gap-1.5 text-[11px] font-semibold px-2 py-1 rounded-full"
              style={{ background: "rgba(245,158,11,0.1)", color: "#f59e0b", border: "1px solid rgba(245,158,11,0.2)" }}>
              <WifiOff size={11} />
              RECONNECTING
            </span>
          ) : (
            <span className="flex items-center gap-1.5 text-[11px] font-semibold px-2 py-1 rounded-full"
              style={{ background: "hsl(var(--muted))", color: "hsl(var(--muted-foreground))", border: "1px solid hsl(var(--border))" }}>
              <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: "hsl(var(--muted-foreground))" }} />
              CONNECTING
            </span>
          )}
        </div>
      </div>

      {/* ── Table ───────────────────────────────────────────────── */}
      <div className="rounded-xl border overflow-hidden"
        style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}>
        {sorted.length === 0 ? (
          <div className="py-20 flex flex-col items-center justify-center gap-3">
            <div className="w-12 h-12 rounded-2xl flex items-center justify-center"
              style={{ background: "hsl(var(--muted))" }}>
              {isConnecting
                ? <span className="w-5 h-5 rounded-full border-2 border-current border-t-transparent animate-spin" style={{ color: "hsl(var(--muted-foreground))" }} />
                : <Radio size={20} className="text-muted-foreground" />}
            </div>
            <p className="text-sm font-semibold text-foreground">
              {isConnecting ? "Connecting to live stream…" : "No active sessions"}
            </p>
            <p className="text-xs text-muted-foreground text-center max-w-xs">
              {isConnecting
                ? "Establishing SSE connection to the LangSight backend…"
                : "Run an agent instrumented with the LangSight SDK to see it here."}
            </p>
          </div>
        ) : (
          <table className="w-full text-[12px]">
            <thead>
              <tr className="sticky top-0 z-10 border-b"
                style={{ background: "hsl(var(--card-raised))", borderColor: "hsl(var(--border))" }}>
                <th className="text-left px-4 py-2.5 font-semibold text-muted-foreground uppercase tracking-wide text-[11px]">Session</th>
                <th className="text-left px-4 py-2.5 font-semibold text-muted-foreground uppercase tracking-wide text-[11px]">Agent</th>
                <th className="text-left px-4 py-2.5 font-semibold text-muted-foreground uppercase tracking-wide text-[11px]">Status</th>
                <th className="text-right px-4 py-2.5 font-semibold text-muted-foreground uppercase tracking-wide text-[11px]">Spans</th>
                <th className="text-right px-4 py-2.5 font-semibold text-muted-foreground uppercase tracking-wide text-[11px]">Errors</th>
                <th className="text-left px-4 py-2.5 font-semibold text-muted-foreground uppercase tracking-wide text-[11px]">Duration</th>
                <th className="text-left px-4 py-2.5 font-semibold text-muted-foreground uppercase tracking-wide text-[11px]">Last seen</th>
                <th className="px-4 py-2.5" />
              </tr>
            </thead>
            <tbody className="divide-y" style={{ borderColor: "hsl(var(--border))" }}>
              {sorted.map(r => {
                const status = getStatus(r, now);
                const age    = now - r.last_seen_ms;
                return (
                  <tr key={r.session_id}
                    onClick={() => router.push(`/sessions/${r.session_id}`)}
                    className={cn(
                      "cursor-pointer transition-colors hover:bg-accent/40 group",
                      status === "stuck" && "bg-amber-500/[0.03]",
                    )}>
                    <td className="px-4 py-3 whitespace-nowrap">
                      <span className="font-mono text-[11px] text-foreground"
                        style={{ fontFamily: "var(--font-geist-mono)" }}>
                        {r.session_id.slice(0, 8)}…
                      </span>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">
                      {r.agent_name ?? <span className="opacity-40">—</span>}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      <StatusDot status={status} />
                    </td>
                    <td className="px-4 py-3 text-right whitespace-nowrap">
                      <span className={cn(
                        "font-mono font-semibold tabular-nums",
                        status === "running" ? "text-foreground" : "text-muted-foreground"
                      )} style={{ fontFamily: "var(--font-geist-mono)" }}>
                        {r.span_count}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right whitespace-nowrap">
                      {r.error_count > 0
                        ? <span className="font-mono font-semibold tabular-nums text-red-400"
                            style={{ fontFamily: "var(--font-geist-mono)" }}>{r.error_count}</span>
                        : <span className="text-muted-foreground opacity-40">0</span>}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground whitespace-nowrap"
                      style={{ fontFamily: "var(--font-geist-mono)" }}>
                      {fmtDuration(r.first_seen_ms, r.last_seen_ms)}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      <span className={cn("text-[11px]", status === "stuck" && "text-amber-400 font-medium")}>
                        {elapsed(age)}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <ChevronRight size={13} className="text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {sorted.length > 0 && (
        <p className="text-[10px] text-muted-foreground text-center">
          Streaming via SSE · Sessions expire after 10min of inactivity · Click to view full trace
        </p>
      )}
    </div>
  );
}
