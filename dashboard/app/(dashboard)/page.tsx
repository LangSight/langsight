"use client";

export const dynamic = "force-dynamic";

import useSWR from "swr";
import { useState } from "react";
import { Area, AreaChart, ResponsiveContainer } from "recharts";
import { Activity, CheckCircle, Server, GitBranch, RefreshCw, Bot, AlertTriangle } from "lucide-react";
import { fetcher, triggerHealthCheck } from "@/lib/api";
import { cn, STATUS_BG, timeAgo, formatLatency } from "@/lib/utils";
import { toast } from "sonner";
import Link from "next/link";
import type { HealthResult, AgentSession, AnomalyResult, SLOStatus } from "@/lib/types";

function MetricCard({ label, value, sub, icon: Icon, trend, color }: {
  label: string; value: string | number; sub?: string;
  icon: React.ElementType; trend?: number[]; color?: string;
}) {
  return (
    <div className="rounded-xl border p-5" style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}>
      <div className="flex items-start justify-between mb-3">
        <div className="p-2 rounded-lg" style={{ background: color ?? "hsl(var(--muted))" }}>
          <Icon size={16} className="text-white" style={{ opacity: 0.9 }}/>
        </div>
        {trend && trend.length > 0 && (
          <div className="h-8 w-20">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={trend.map((v, i) => ({ v, i }))}>
                <Area type="monotone" dataKey="v" stroke={color ?? "hsl(var(--primary))"} fill={color ?? "hsl(var(--primary))"} fillOpacity={0.15} strokeWidth={1.5} dot={false}/>
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
      <p className="text-2xl font-bold mb-0.5" style={{ color: "hsl(var(--foreground))" }}>{value}</p>
      <p className="text-xs font-medium mb-0.5" style={{ color: "hsl(var(--foreground))" }}>{label}</p>
      {sub && <p className="text-xs" style={{ color: "hsl(var(--muted-foreground))" }}>{sub}</p>}
    </div>
  );
}

function StatusDot({ status }: { status: string }) {
  const colors: Record<string, string> = {
    up: "#22c55e", degraded: "#eab308", down: "#ef4444", stale: "#71717a", unknown: "#71717a",
  };
  const c = colors[status] ?? "#71717a";
  return (
    <span className="relative inline-flex w-2 h-2">
      {(status === "up") && (
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75" style={{ background: c }}/>
      )}
      <span className="relative inline-flex rounded-full w-2 h-2" style={{ background: c }}/>
    </span>
  );
}

function Skeleton({ className }: { className?: string }) {
  return <div className={cn("skeleton", className)}/>;
}

export default function OverviewPage() {
  const { data: servers, isLoading: sl, mutate } =
    useSWR<HealthResult[]>("/api/health/servers", fetcher, { refreshInterval: 30_000 });
  const { data: sessions, isLoading: ssl } =
    useSWR<AgentSession[]>("/api/agents/sessions?hours=24&limit=6", fetcher, { refreshInterval: 30_000 });
  const { data: anomalies } =
    useSWR<AnomalyResult[]>("/api/reliability/anomalies?current_hours=1&z_threshold=2", fetcher, { refreshInterval: 60_000 });
  const { data: sloStatuses } =
    useSWR<SLOStatus[]>("/api/slos/status", fetcher, { refreshInterval: 60_000 });
  const [checking, setChecking] = useState(false);

  const up = servers?.filter(s => s.status === "up").length ?? 0;
  const total = servers?.length ?? 0;
  const down = servers?.filter(s => s.status === "down").length ?? 0;
  const degraded = servers?.filter(s => s.status === "degraded").length ?? 0;
  const sessTotal = sessions?.length ?? 0;
  const sessFailed = sessions?.filter(s => s.failed_calls > 0).length ?? 0;

  // Fake sparkline data — real data would come from /api/health/{name}/history
  const spark = [3, 5, 4, 7, 6, 8, 7, 9, 8, 10].map((v, i) => ({ v: v + i * 0.2 }));

  const systemStatus: "all_up" | "degraded" | "down" =
    down > 0 ? "down" : degraded > 0 ? "degraded" : "all_up";
  const systemStatusLabel = systemStatus === "all_up" ? "All Systems Operational" : systemStatus === "degraded" ? "Degraded" : "Outage Detected";
  const systemStatusColor = systemStatus === "all_up" ? "#22c55e" : systemStatus === "degraded" ? "#eab308" : "#ef4444";

  async function runCheck() {
    setChecking(true);
    try { await triggerHealthCheck(); await mutate(); toast.success("Health check complete"); }
    catch { toast.error("Health check failed"); }
    finally { setChecking(false); }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold" style={{ color: "hsl(var(--foreground))" }}>Overview</h1>
          <p className="text-sm" style={{ color: "hsl(var(--muted-foreground))" }}>Monitor your AI agents and the tools they use</p>
        </div>
        <div className="flex items-center gap-3">
          {!sl && (
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-full border text-xs font-medium"
              style={{ borderColor: systemStatusColor + "44", background: systemStatusColor + "11", color: systemStatusColor }}>
              <span className="relative flex w-1.5 h-1.5">
                {systemStatus === "all_up" && <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75" style={{ background: systemStatusColor }}/>}
                <span className="relative inline-flex rounded-full w-1.5 h-1.5" style={{ background: systemStatusColor }}/>
              </span>
              {systemStatusLabel}
            </div>
          )}
          <button onClick={runCheck} disabled={checking}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-60"
            style={{ background: "hsl(var(--primary))" }}>
            <RefreshCw size={14} className={checking ? "animate-spin" : ""}/>
            {checking ? "Checking…" : "Run Check"}
          </button>
        </div>
      </div>

      {/* Metric cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {sl ? (
          Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="rounded-xl border p-5 space-y-3" style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}>
              <Skeleton className="h-8 w-8 rounded-lg"/>
              <Skeleton className="h-7 w-16"/>
              <Skeleton className="h-3 w-24"/>
            </div>
          ))
        ) : (
          <>
            <MetricCard label="Active Workflows" value={sessTotal} sub={`${sessFailed} with failures`} icon={GitBranch} trend={spark.map(s => s.v)} color="#6366f1"/>
            <MetricCard label="Healthy Agents" value={Math.max(sessTotal - sessFailed, 0)} sub="agents without failed sessions in window" icon={Bot} color={sessFailed > 0 ? "#eab308" : "#22c55e"}/>
            <MetricCard label="Tools & MCPs Online" value={`${up}/${total}`} sub={`${degraded} degraded · ${down} down`} icon={Server} trend={spark.map(s => s.v)} color="#6366f1"/>
            <MetricCard
              label="Anomalies Detected"
              value={anomalies?.length ?? "—"}
              sub={
                anomalies === undefined ? "loading…"
                : anomalies.length === 0 ? "all tools within normal range"
                : `${anomalies.filter(a => a.severity === "critical").length} critical · ${anomalies.filter(a => a.severity === "warning").length} warning`
              }
              icon={AlertTriangle}
              color={
                !anomalies || anomalies.length === 0 ? "#22c55e"
                : anomalies.some(a => a.severity === "critical") ? "#ef4444"
                : "#eab308"
              }
            />
          </>
        )}
      </div>

      <div className="grid lg:grid-cols-5 gap-5">
        {/* Recent agent workflows (3/5) */}
        <div className="lg:col-span-3 rounded-xl border" style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}>
          <div className="flex items-center justify-between px-5 py-4 border-b" style={{ borderColor: "hsl(var(--border))" }}>
            <h2 className="text-sm font-semibold" style={{ color: "hsl(var(--foreground))" }}>Recent Agent Workflows</h2>
            <Link href="/sessions" className="text-xs font-medium" style={{ color: "hsl(var(--primary))" }}>View all →</Link>
          </div>
          <div className="divide-y" style={{ borderColor: "hsl(var(--border))" }}>
            {sl ? (
              Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="flex items-center justify-between px-5 py-3.5">
                  <div className="flex items-center gap-3"><Skeleton className="w-2 h-2 rounded-full"/><Skeleton className="h-4 w-32"/></div>
                  <div className="flex items-center gap-3"><Skeleton className="h-4 w-12"/><Skeleton className="h-5 w-16 rounded-full"/></div>
                </div>
              ))
            ) : !sessions || sessions.length === 0 ? (
              <div className="px-5 py-12 text-center flex flex-col items-center gap-3">
                <svg width="48" height="48" viewBox="0 0 48 48" fill="none" className="opacity-20">
                  <rect x="6" y="20" width="36" height="18" rx="4" stroke="currentColor" strokeWidth="1.5"/>
                  <circle cx="16" cy="14" r="5" stroke="currentColor" strokeWidth="1.5"/>
                  <circle cx="32" cy="14" r="5" stroke="currentColor" strokeWidth="1.5"/>
                  <path d="M16 19v1M32 19v1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                  <path d="M16 29h16" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                  <path d="M18 33h12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                </svg>
                <div>
                  <p className="text-sm font-medium" style={{ color: "hsl(var(--foreground))" }}>No agent workflows yet</p>
                  <p className="text-xs mt-1" style={{ color: "hsl(var(--muted-foreground))" }}>Instrument with the LangSight SDK or OTLP</p>
                </div>
              </div>
            ) : sessions?.slice(0, 6).map(s => (
              <div key={s.session_id} className="flex items-center justify-between px-5 py-3.5 hover:bg-accent/50 transition-colors">
                <div className="flex items-center gap-3">
                  <StatusDot status={s.failed_calls > 0 ? "down" : "up"}/>
                  <div>
                    <span className="text-sm font-mono block" style={{ color: "hsl(var(--foreground))" }}>{s.session_id.slice(0, 16)}…</span>
                    <span className="text-[11px]" style={{ color: "hsl(var(--muted-foreground))" }}>{s.agent_name || "unknown agent"}</span>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-xs font-mono" style={{ color: "hsl(var(--muted-foreground))" }}>{s.tool_calls} calls</span>
                  <span className={cn("text-xs px-2 py-0.5 rounded-full border font-medium", s.failed_calls > 0 ? STATUS_BG.down : STATUS_BG.up)}>
                    {s.failed_calls > 0 ? `${s.failed_calls} failed` : "clean"}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Tool infrastructure (2/5) */}
        <div className="lg:col-span-2 rounded-xl border" style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}>
          <div className="flex items-center justify-between px-5 py-4 border-b" style={{ borderColor: "hsl(var(--border))" }}>
            <h2 className="text-sm font-semibold" style={{ color: "hsl(var(--foreground))" }}>Tools & MCPs</h2>
            <Link href="/health" className="text-xs font-medium" style={{ color: "hsl(var(--primary))" }}>View all →</Link>
          </div>
          <div className="divide-y" style={{ borderColor: "hsl(var(--border))" }}>
            {ssl ? (
              Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="px-5 py-3.5 space-y-1.5">
                  <Skeleton className="h-3.5 w-28"/><Skeleton className="h-3 w-40"/>
                </div>
              ))
            ) : !servers || servers.length === 0 ? (
              <div className="px-5 py-12 text-center flex flex-col items-center gap-3">
                <svg width="48" height="48" viewBox="0 0 48 48" fill="none" className="opacity-20">
                  <rect x="6" y="8" width="36" height="10" rx="3" stroke="currentColor" strokeWidth="1.5"/>
                  <rect x="6" y="22" width="36" height="10" rx="3" stroke="currentColor" strokeWidth="1.5"/>
                  <rect x="6" y="36" width="36" height="6" rx="3" stroke="currentColor" strokeWidth="1.5"/>
                  <circle cx="38" cy="13" r="2" fill="currentColor"/>
                  <circle cx="38" cy="27" r="2" fill="currentColor"/>
                </svg>
                <div>
                  <p className="text-sm font-medium" style={{ color: "hsl(var(--foreground))" }}>No tools configured</p>
                  <p className="text-xs mt-1" style={{ color: "hsl(var(--muted-foreground))" }}>Run <code className="font-mono" style={{ color: "hsl(var(--primary))" }}>langsight init</code></p>
                </div>
              </div>
            ) : servers?.map(s => (
              <Link href="/health" key={s.server_name}>
                <div className="px-5 py-3.5 hover:bg-accent/50 transition-colors">
                  <div className="flex items-center justify-between mb-0.5">
                    <span className="text-xs font-mono" style={{ color: "hsl(var(--foreground))" }}>{s.server_name}</span>
                    {s.status !== "up"
                      ? <span className="text-xs text-red-500 font-medium">{s.status}</span>
                      : <span className="text-xs text-emerald-500 font-medium"><CheckCircle size={11} className="inline mr-0.5"/>up</span>
                    }
                  </div>
                  <div className="flex items-center gap-2 text-[11px]" style={{ color: "hsl(var(--muted-foreground))" }}>
                    <span>{s.tools_count} tools</span>
                    <span>·</span>
                    <span>{formatLatency(s.latency_ms)}</span>
                    <span>·</span>
                    <span>{timeAgo(s.checked_at)}</span>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        </div>
      </div>

      {/* SLO Status (P5.5) — only shown when SLOs are defined */}
      {sloStatuses && sloStatuses.length > 0 && (
        <div className="rounded-xl border" style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}>
          <div className="flex items-center justify-between px-5 py-4 border-b" style={{ borderColor: "hsl(var(--border))" }}>
            <h2 className="text-sm font-semibold" style={{ color: "hsl(var(--foreground))" }}>Agent SLOs</h2>
            <span className="text-xs" style={{ color: "hsl(var(--muted-foreground))" }}>
              {sloStatuses.filter(s => s.status === "ok").length}/{sloStatuses.length} meeting target
            </span>
          </div>
          <div className="divide-y" style={{ borderColor: "hsl(var(--border))" }}>
            {sloStatuses.map(slo => {
              const statusColor = slo.status === "ok" ? "#22c55e" : slo.status === "breached" ? "#ef4444" : "#71717a";
              const metricLabel = slo.metric === "success_rate" ? "Success Rate" : "p99 Latency";
              const targetLabel = slo.metric === "success_rate" ? `≥ ${slo.target}%` : `≤ ${slo.target}ms`;
              const currentLabel = slo.current_value === null ? "no data"
                : slo.metric === "success_rate" ? `${slo.current_value.toFixed(1)}%`
                : `${slo.current_value.toFixed(0)}ms`;
              return (
                <div key={slo.slo_id} className="flex items-center justify-between px-5 py-3">
                  <div className="flex items-center gap-3">
                    <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: statusColor }}/>
                    <div>
                      <span className="text-xs font-mono" style={{ color: "hsl(var(--foreground))" }}>{slo.agent_name}</span>
                      <span className="text-[11px] ml-2" style={{ color: "hsl(var(--muted-foreground))" }}>{metricLabel} · {slo.window_hours}h window</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 text-xs">
                    <span style={{ color: "hsl(var(--muted-foreground))" }}>target: {targetLabel}</span>
                    <span className="font-mono font-medium" style={{ color: statusColor }}>{currentLabel}</span>
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
