"use client";

export const dynamic = "force-dynamic";

import useSWR from "swr";
import { useState } from "react";
import { AreaChart, Area, ResponsiveContainer } from "recharts";
import {
  RefreshCw, Server, GitBranch, Bot, AlertTriangle,
  CheckCircle, ArrowUpRight, Activity,
} from "lucide-react";
import { fetcher, triggerHealthCheck } from "@/lib/api";
import { useProject } from "@/lib/project-context";
import { cn, timeAgo, formatLatency } from "@/lib/utils";
import { toast } from "sonner";
import Link from "next/link";
import type { HealthResult, AgentSession, AnomalyResult, SLOStatus } from "@/lib/types";

/* ── Helpers ────────────────────────────────────────────────── */
function Skeleton({ className }: { className?: string }) {
  return <div className={cn("skeleton", className)} />;
}

function StatusDot({ status }: { status: string }) {
  const map: Record<string, string> = {
    up: "#22c55e", degraded: "#eab308", down: "#ef4444",
    stale: "#71717a", unknown: "#71717a",
  };
  const color = map[status] ?? "#71717a";
  return (
    <span className="relative inline-flex w-2 h-2 flex-shrink-0">
      {status === "up" && (
        <span
          className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-60"
          style={{ background: color }}
        />
      )}
      <span className="relative inline-flex rounded-full w-2 h-2" style={{ background: color }} />
    </span>
  );
}

/* ── Metric card ────────────────────────────────────────────── */
function MetricCard({
  label, value, sub, icon: Icon, trend, color, href,
}: {
  label: string;
  value: string | number;
  sub?: string;
  icon: React.ElementType;
  trend?: number[];
  color: string;
  href?: string;
}) {
  const inner = (
    <div
      className={cn(
        "metric-card flex flex-col gap-4",
        href && "cursor-pointer"
      )}
      style={{ "--card-accent": color } as React.CSSProperties}
    >
      {/* Top row: icon + sparkline */}
      <div className="flex items-start justify-between">
        <div
          className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 shadow-sm"
          style={{
            background: `linear-gradient(135deg, ${color}22, ${color}12)`,
            border: `1px solid ${color}25`,
          }}
        >
          <Icon size={18} style={{ color }} />
        </div>
        {trend && trend.length > 0 && (
          <div className="h-10 w-24 opacity-70">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={trend.map((v, i) => ({ v, i }))}>
                <Area
                  type="monotone"
                  dataKey="v"
                  stroke={color}
                  fill={color}
                  fillOpacity={0.15}
                  strokeWidth={1.5}
                  dot={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* Bottom: number + label */}
      <div>
        <p
          className="font-bold leading-none mb-1.5"
          style={{
            fontSize: "1.75rem",
            color: "hsl(var(--foreground))",
            letterSpacing: "-0.03em",
          }}
        >
          {value}
        </p>
        <p
          className="text-[12.5px] font-medium"
          style={{ color: "hsl(var(--muted-foreground))" }}
        >
          {label}
        </p>
        {sub && (
          <p className="text-[11px] mt-0.5" style={{ color: "hsl(var(--muted-foreground))", opacity: 0.7 }}>
            {sub}
          </p>
        )}
      </div>

      {/* Bottom accent line */}
      <div
        className="absolute bottom-0 left-0 right-0 h-[2px] rounded-b-xl opacity-40"
        style={{ background: `linear-gradient(90deg, ${color}, transparent)` }}
      />
    </div>
  );
  return href ? <Link href={href}>{inner}</Link> : inner;
}

/* ── Session row ────────────────────────────────────────────── */
function SessionRow({ session }: { session: AgentSession }) {
  const failed = session.failed_calls > 0;
  return (
    <Link
      href={`/sessions/${session.session_id}`}
      className="flex items-center justify-between px-5 py-3 hover:bg-accent/50 transition-colors group"
    >
      <div className="flex items-center gap-3 min-w-0">
        <StatusDot status={failed ? "down" : "up"} />
        <div className="min-w-0">
          <span
            className="text-[13px] font-mono block truncate text-foreground"
            style={{ fontFamily: "var(--font-geist-mono)" }}
          >
            {session.session_id.slice(0, 18)}…
          </span>
          <span className="text-[11px] text-muted-foreground">
            {session.agent_name || "unknown"} · {timeAgo(session.first_call_at)}
          </span>
        </div>
      </div>
      <div className="flex items-center gap-3 flex-shrink-0">
        <span className="text-[11px] font-mono text-muted-foreground hidden sm:block">
          {session.tool_calls} calls
        </span>
        <span
          className={cn(
            "text-[10px] px-2 py-0.5 rounded-full font-semibold",
            failed ? "badge-danger" : "badge-success"
          )}
        >
          {failed ? `${session.failed_calls} failed` : "clean"}
        </span>
        <ArrowUpRight size={13} className="text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
      </div>
    </Link>
  );
}

/* ── Page ───────────────────────────────────────────────────── */
export default function OverviewPage() {
  const { activeProject } = useProject();
  const p = activeProject ? `&project_id=${activeProject.id}` : "";

  const { data: servers, isLoading: serversLoading, mutate } =
    useSWR<HealthResult[]>("/api/health/servers", fetcher, { refreshInterval: 30_000 });
  const { data: sessions, isLoading: sessionsLoading } =
    useSWR<AgentSession[]>(`/api/agents/sessions?hours=24&limit=8${p}`, fetcher, { refreshInterval: 30_000 });
  const { data: anomalies } =
    useSWR<AnomalyResult[]>(`/api/reliability/anomalies?current_hours=1&z_threshold=2${p}`, fetcher, { refreshInterval: 60_000 });
  const { data: sloStatuses } =
    useSWR<SLOStatus[]>(`/api/slos/status${p ? `?${p.slice(1)}` : ""}`, fetcher, { refreshInterval: 60_000 });
  const [checking, setChecking] = useState(false);

  const up       = servers?.filter((s) => s.status === "up").length ?? 0;
  const total    = servers?.length ?? 0;
  const down     = servers?.filter((s) => s.status === "down").length ?? 0;
  const degraded = servers?.filter((s) => s.status === "degraded").length ?? 0;
  const sessTotal  = sessions?.length ?? 0;
  const sessFailed = sessions?.filter((s) => s.failed_calls > 0).length ?? 0;

  const spark = [3,5,4,6,5,8,7,9,8,10].map((v) => v);

  const systemStatus =
    down > 0 ? "down" : degraded > 0 ? "degraded" : "all_up";
  const systemLabel =
    systemStatus === "all_up" ? "All Systems Operational"
    : systemStatus === "degraded" ? "Systems Degraded"
    : "Outage Detected";
  const systemColor =
    systemStatus === "all_up" ? "#22c55e"
    : systemStatus === "degraded" ? "#eab308"
    : "#ef4444";

  async function runCheck() {
    setChecking(true);
    try {
      await triggerHealthCheck();
      await mutate();
      toast.success("Health check complete");
    } catch {
      toast.error("Health check failed");
    } finally {
      setChecking(false);
    }
  }

  return (
    <div className="space-y-5 page-in">
      {/* ── Actions bar ───────────────────────────────────────── */}
      <div className="flex items-center justify-end gap-2.5">
          {!serversLoading && (
            <div
              className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold border"
              style={{
                background: systemColor + "12",
                borderColor: systemColor + "40",
                color: systemColor,
              }}
            >
              <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ background: systemColor }} />
              {systemLabel}
            </div>
          )}
          <button
            onClick={runCheck}
            disabled={checking}
            className="btn btn-secondary"
          >
            <RefreshCw size={13} className={checking ? "animate-spin" : ""} />
            {checking ? "Checking…" : "Run Check"}
          </button>
        </div>

      {/* ── Metric cards ──────────────────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {serversLoading ? (
          Array.from({ length: 4 }).map((_, i) => (
            <div
              key={i}
              className="rounded-xl border p-5 space-y-3"
              style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
            >
              <Skeleton className="w-9 h-9 rounded-lg" />
              <Skeleton className="h-7 w-16" />
              <Skeleton className="h-3 w-24" />
            </div>
          ))
        ) : (
          <>
            <MetricCard
              label="Active Sessions"
              value={sessTotal}
              sub={sessFailed > 0 ? `${sessFailed} with failures` : "all clean"}
              icon={GitBranch}
              trend={spark}
              color="#14B8A6"
              href="/sessions"
            />
            <MetricCard
              label="Agents Running"
              value={Math.max(sessTotal - sessFailed, 0)}
              sub={sessFailed > 0 ? `${sessFailed} with errors` : "no issues detected"}
              icon={Bot}
              color={sessFailed > 0 ? "#eab308" : "#22c55e"}
              href="/agents"
            />
            <MetricCard
              label="Tools Online"
              value={total > 0 ? `${up}/${total}` : "—"}
              sub={
                total === 0 ? "run langsight init"
                : degraded > 0 || down > 0 ? `${degraded} degraded · ${down} down`
                : "all healthy"
              }
              icon={Server}
              trend={spark}
              color={down > 0 ? "#ef4444" : degraded > 0 ? "#eab308" : "#6366f1"}
              href="/health"
            />
            <MetricCard
              label="Anomalies"
              value={anomalies === undefined ? "—" : anomalies.length}
              sub={
                anomalies === undefined ? "loading…"
                : anomalies.length === 0 ? "all tools normal"
                : `${anomalies.filter((a) => a.severity === "critical").length} critical`
              }
              icon={AlertTriangle}
              color={
                !anomalies || anomalies.length === 0 ? "#22c55e"
                : anomalies.some((a) => a.severity === "critical") ? "#ef4444"
                : "#eab308"
              }
            />
          </>
        )}
      </div>

      {/* ── Main content grid ─────────────────────────────────── */}
      <div className="grid lg:grid-cols-5 gap-4">

        {/* Recent sessions — 3 cols */}
        <div
          className="lg:col-span-3 rounded-xl border overflow-hidden"
          style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
        >
          <div className="section-header">
            <h2>Recent Sessions</h2>
            <Link
              href="/sessions"
              className="text-xs font-medium text-primary hover:underline underline-offset-2"
            >
              View all →
            </Link>
          </div>

          {sessionsLoading ? (
            <div className="divide-y" style={{ borderColor: "hsl(var(--border))" }}>
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="flex items-center justify-between px-5 py-3 gap-4">
                  <div className="flex items-center gap-3">
                    <Skeleton className="w-2 h-2 rounded-full flex-shrink-0" />
                    <div className="space-y-1.5">
                      <Skeleton className="h-3.5 w-36" />
                      <Skeleton className="h-2.5 w-24" />
                    </div>
                  </div>
                  <Skeleton className="h-5 w-14 rounded-full" />
                </div>
              ))}
            </div>
          ) : !sessions || sessions.length === 0 ? (
            <div className="p-12 text-center">
              <div
                className="w-14 h-14 rounded-2xl flex items-center justify-center mx-auto mb-4"
                style={{ background: "hsl(var(--muted))" }}
              >
                <GitBranch size={22} className="text-muted-foreground" />
              </div>
              <p className="text-sm font-semibold text-foreground mb-1">No sessions yet</p>
              <p className="text-xs text-muted-foreground">
                Instrument an agent with the LangSight SDK to start seeing sessions
              </p>
            </div>
          ) : (
            <div className="divide-y" style={{ borderColor: "hsl(var(--border))" }}>
              {sessions.map((s) => (
                <SessionRow key={s.session_id} session={s} />
              ))}
            </div>
          )}
        </div>

        {/* Tool health — 2 cols */}
        <div
          className="lg:col-span-2 rounded-xl border overflow-hidden"
          style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
        >
          <div className="section-header">
            <h2>Tools &amp; MCPs</h2>
            <Link
              href="/health"
              className="text-xs font-medium text-primary hover:underline underline-offset-2"
            >
              View all →
            </Link>
          </div>

          {serversLoading ? (
            <div className="divide-y" style={{ borderColor: "hsl(var(--border))" }}>
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="px-5 py-3 space-y-1.5">
                  <Skeleton className="h-3.5 w-28" />
                  <Skeleton className="h-2.5 w-40" />
                </div>
              ))}
            </div>
          ) : !servers || servers.length === 0 ? (
            <div className="p-10 text-center">
              <div
                className="w-14 h-14 rounded-2xl flex items-center justify-center mx-auto mb-4"
                style={{ background: "hsl(var(--muted))" }}
              >
                <Server size={22} className="text-muted-foreground" />
              </div>
              <p className="text-sm font-semibold text-foreground mb-1">No tools configured</p>
              <p className="text-xs text-muted-foreground font-mono">langsight init</p>
            </div>
          ) : (
            <div className="divide-y" style={{ borderColor: "hsl(var(--border))" }}>
              {servers.map((s) => (
                <Link
                  href="/health"
                  key={s.server_name}
                  className="flex items-center justify-between px-5 py-3 hover:bg-accent/50 transition-colors group"
                >
                  <div className="flex items-center gap-2.5 min-w-0">
                    <StatusDot status={s.status} />
                    <div className="min-w-0">
                      <span
                        className="text-[13px] font-mono font-medium text-foreground block truncate"
                        style={{ fontFamily: "var(--font-geist-mono)" }}
                      >
                        {s.server_name}
                      </span>
                      <span className="text-[11px] text-muted-foreground">
                        {s.tools_count} tools · {formatLatency(s.latency_ms)} · {timeAgo(s.checked_at)}
                      </span>
                    </div>
                  </div>
                  {s.status === "up" ? (
                    <CheckCircle size={13} className="text-emerald-500 flex-shrink-0" />
                  ) : (
                    <span
                      className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full flex-shrink-0"
                      style={{
                        background: s.status === "down" ? "hsl(var(--danger-bg))" : "hsl(var(--warning-bg))",
                        color: s.status === "down" ? "hsl(var(--danger))" : "hsl(var(--warning))",
                      }}
                    >
                      {s.status}
                    </span>
                  )}
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ── SLO Status ────────────────────────────────────────── */}
      {sloStatuses && sloStatuses.length > 0 && (
        <div
          className="rounded-xl border overflow-hidden"
          style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
        >
          <div className="section-header">
            <div className="flex items-center gap-2">
              <Activity size={14} className="text-primary" />
              <h2>Agent SLOs</h2>
            </div>
            <span className="text-xs text-muted-foreground">
              {sloStatuses.filter((s) => s.status === "ok").length}/{sloStatuses.length} meeting target
            </span>
          </div>
          <div className="divide-y" style={{ borderColor: "hsl(var(--border))" }}>
            {sloStatuses.map((slo) => {
              const ok = slo.status === "ok";
              const noData = slo.status === "no_data";
              const statusColor = ok ? "#22c55e" : noData ? "#71717a" : "#ef4444";
              const metricLabel = slo.metric === "success_rate" ? "Success Rate" : "p99 Latency";
              const targetLabel = slo.metric === "success_rate"
                ? `≥ ${slo.target}%` : `≤ ${slo.target}ms`;
              const currentLabel =
                slo.current_value === null ? "no data"
                : slo.metric === "success_rate" ? `${slo.current_value.toFixed(1)}%`
                : `${slo.current_value.toFixed(0)}ms`;

              return (
                <div
                  key={slo.slo_id}
                  className="flex items-center justify-between px-5 py-3 gap-4"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <span
                      className="w-2 h-2 rounded-full flex-shrink-0"
                      style={{ background: statusColor }}
                    />
                    <div className="min-w-0">
                      <span
                        className="text-[13px] font-mono text-foreground"
                        style={{ fontFamily: "var(--font-geist-mono)" }}
                      >
                        {slo.agent_name}
                      </span>
                      <span className="text-[11px] text-muted-foreground ml-2">
                        {metricLabel} · {slo.window_hours}h window
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 flex-shrink-0 text-xs">
                    <span className="text-muted-foreground hidden sm:block">
                      target: {targetLabel}
                    </span>
                    <span
                      className="font-mono font-semibold"
                      style={{ color: statusColor }}
                    >
                      {currentLabel}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
