"use client";

export const dynamic = "force-dynamic";

import useSWR from "swr";
import { useMemo, useState } from "react";
import {
  AreaChart, Area, BarChart, Bar, LineChart, Line,
  XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from "recharts";
import {
  Activity, Zap, AlertTriangle, Clock, Coins, Cpu, Server,
} from "lucide-react";
import { useProject } from "@/lib/project-context";
import { cn, formatLatency } from "@/lib/utils";
import type { MonitoringBucket, MonitoringModel, MonitoringTool } from "@/lib/api";
import {
  getMonitoringTimeseries, getMonitoringModels, getMonitoringTools,
} from "@/lib/api";

/* ── Time range selector ──────────────────────────────────────── */
const RANGES = [
  { label: "1h", hours: 1 },
  { label: "6h", hours: 6 },
  { label: "24h", hours: 24 },
  { label: "7d", hours: 168 },
] as const;

/* ── Tab type ─────────────────────────────────────────────────── */
type Tab = "overview" | "models" | "tools";

/* ── Chart tooltip ────────────────────────────────────────────── */
function ChartTooltip({ active, payload, label, formatter }: {
  active?: boolean; payload?: Array<{ value: number; name: string; color: string }>;
  label?: string; formatter?: (v: number) => string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border px-3 py-2 shadow-lg" style={{
      background: "hsl(var(--card))", borderColor: "hsl(var(--border))",
      fontSize: "11px",
    }}>
      <p className="text-muted-foreground mb-1" style={{ fontFamily: "var(--font-geist-mono)" }}>
        {label}
      </p>
      {payload.map((p, i) => (
        <div key={i} className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full" style={{ background: p.color }} />
          <span className="text-muted-foreground">{p.name}:</span>
          <span className="font-semibold text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>
            {formatter ? formatter(p.value) : p.value.toLocaleString()}
          </span>
        </div>
      ))}
    </div>
  );
}

/* ── Stat card ────────────────────────────────────────────────── */
function StatCard({ label, value, sub, icon: Icon, color }: {
  label: string; value: string | number; sub?: string;
  icon: React.ElementType; color: string;
}) {
  return (
    <div className="rounded-xl border p-4" style={{
      background: "hsl(var(--card))", borderColor: "hsl(var(--border))",
    }}>
      <div className="flex items-center gap-2 mb-2">
        <div className="w-7 h-7 rounded-lg flex items-center justify-center" style={{
          background: `${color}18`, border: `1px solid ${color}30`,
        }}>
          <Icon size={13} style={{ color }} />
        </div>
        <span className="text-[11px] text-muted-foreground font-medium">{label}</span>
      </div>
      <p className="text-xl font-bold text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>
        {value}
      </p>
      {sub && <p className="text-[10px] text-muted-foreground mt-0.5">{sub}</p>}
    </div>
  );
}

/* ── Chart wrapper ────────────────────────────────────────────── */
function ChartCard({ title, children, className }: {
  title: string; children: React.ReactNode; className?: string;
}) {
  return (
    <div className={cn("rounded-xl border p-4", className)} style={{
      background: "hsl(var(--card))", borderColor: "hsl(var(--border))",
    }}>
      <h3 className="text-[12px] font-semibold text-muted-foreground mb-3 uppercase tracking-wider">{title}</h3>
      <div className="h-52">{children}</div>
    </div>
  );
}

/* ── Format bucket label ──────────────────────────────────────── */
function fmtBucket(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", hour12: false });
}

/* ── Main page ────────────────────────────────────────────────── */
export default function MonitoringPage() {
  const { activeProject } = useProject();
  const pid = activeProject?.id ?? null;
  const [hours, setHours] = useState(24);
  const [tab, setTab] = useState<Tab>("overview");

  const { data: timeseries } = useSWR(
    pid ? `/monitoring/ts/${hours}/${pid}` : null,
    () => getMonitoringTimeseries(hours, pid),
    { refreshInterval: 60_000 },
  );
  const { data: models } = useSWR(
    pid && tab === "models" ? `/monitoring/models/${hours}/${pid}` : null,
    () => getMonitoringModels(hours, pid),
    { refreshInterval: 120_000 },
  );
  const { data: tools } = useSWR(
    pid && tab === "tools" ? `/monitoring/tools/${hours}/${pid}` : null,
    () => getMonitoringTools(hours, pid),
    { refreshInterval: 120_000 },
  );

  // Aggregate summary from timeseries
  const summary = useMemo(() => {
    if (!timeseries?.length) return null;
    const totalSessions = timeseries.reduce((s, b) => s + b.sessions, 0);
    const totalToolCalls = timeseries.reduce((s, b) => s + b.tool_calls, 0);
    const totalErrors = timeseries.reduce((s, b) => s + b.errors, 0);
    const totalInputTokens = timeseries.reduce((s, b) => s + b.input_tokens, 0);
    const totalOutputTokens = timeseries.reduce((s, b) => s + b.output_tokens, 0);
    const avgLatency = totalToolCalls > 0
      ? timeseries.reduce((s, b) => s + b.avg_latency_ms * b.tool_calls, 0) / totalToolCalls
      : 0;
    const errorRate = totalToolCalls > 0 ? (totalErrors / totalToolCalls * 100) : 0;
    const maxAgents = Math.max(...timeseries.map(b => b.agents), 0);
    return {
      totalSessions, totalToolCalls, totalErrors, totalInputTokens,
      totalOutputTokens, avgLatency, errorRate, maxAgents,
    };
  }, [timeseries]);

  // Chart data with formatted labels
  const chartData = useMemo(() =>
    (timeseries ?? []).map(b => ({ ...b, label: fmtBucket(b.bucket) })),
    [timeseries],
  );

  // Filter tools: exclude LLM intent spans (server_name matches an agent pattern)
  const realTools = useMemo(() => {
    if (!tools) return [];
    const agentServers = new Set(["orchestrator", "analyst", "procurement"]);
    return tools.filter(t => !agentServers.has(t.server_name));
  }, [tools]);

  const AXIS_STYLE = { fontSize: 10, fill: "hsl(var(--muted-foreground))", fontFamily: "var(--font-geist-mono)" };
  const GRID_STYLE = { stroke: "hsl(var(--border))", strokeDasharray: "3 3" };

  return (
    <div className="space-y-4 page-in">
      {/* ── Header bar ─────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1 rounded-lg border overflow-hidden" style={{
          borderColor: "hsl(var(--border))", background: "hsl(var(--muted))",
        }}>
          {(["overview", "models", "tools"] as Tab[]).map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={cn(
                "px-3 py-1.5 text-[12px] font-medium transition-colors capitalize",
                tab === t
                  ? "bg-background text-foreground shadow-sm rounded-md"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {t}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-1 rounded-lg border overflow-hidden" style={{
          borderColor: "hsl(var(--border))", background: "hsl(var(--muted))",
        }}>
          {RANGES.map(r => (
            <button
              key={r.hours}
              onClick={() => setHours(r.hours)}
              className={cn(
                "px-2.5 py-1.5 text-[12px] font-medium transition-colors",
                hours === r.hours
                  ? "bg-background text-foreground shadow-sm rounded-md"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>

      {/* ── OVERVIEW TAB ──────────────────────────────────────── */}
      {tab === "overview" && (
        <>
          {/* Summary cards */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <StatCard label="Sessions" value={summary?.totalSessions ?? "—"} icon={Activity} color="#14b8a6" sub={`last ${hours}h`} />
            <StatCard label="Tool Calls" value={summary?.totalToolCalls?.toLocaleString() ?? "—"} icon={Zap} color="#0ea5e9" sub={`${summary?.totalErrors ?? 0} errors`} />
            <StatCard label="Error Rate" value={summary ? `${summary.errorRate.toFixed(1)}%` : "—"} icon={AlertTriangle} color={summary && summary.errorRate > 5 ? "#ef4444" : "#22c55e"} />
            <StatCard label="Avg Latency" value={summary ? formatLatency(summary.avgLatency) : "—"} icon={Clock} color="#8b5cf6" />
          </div>

          {/* Charts row 1: Sessions + Error Rate */}
          <div className="grid lg:grid-cols-2 gap-3">
            <ChartCard title="Agent Runs">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData}>
                  <CartesianGrid {...GRID_STYLE} />
                  <XAxis dataKey="label" tick={AXIS_STYLE} />
                  <YAxis tick={AXIS_STYLE} width={35} />
                  <Tooltip content={<ChartTooltip />} />
                  <Bar dataKey="sessions" name="Sessions" fill="#14b8a6" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>

            <ChartCard title="Error Rate">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData}>
                  <CartesianGrid {...GRID_STYLE} />
                  <XAxis dataKey="label" tick={AXIS_STYLE} />
                  <YAxis tick={AXIS_STYLE} width={35} tickFormatter={v => `${(v * 100).toFixed(0)}%`} />
                  <Tooltip content={<ChartTooltip formatter={v => `${(v * 100).toFixed(1)}%`} />} />
                  <Line type="monotone" dataKey="error_rate" name="Error Rate" stroke="#ef4444" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </ChartCard>
          </div>

          {/* Charts row 2: Latency + Tokens */}
          <div className="grid lg:grid-cols-2 gap-3">
            <ChartCard title="Latency (p99)">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData}>
                  <CartesianGrid {...GRID_STYLE} />
                  <XAxis dataKey="label" tick={AXIS_STYLE} />
                  <YAxis tick={AXIS_STYLE} width={45} tickFormatter={v => formatLatency(v)} />
                  <Tooltip content={<ChartTooltip formatter={v => formatLatency(v)} />} />
                  <Line type="monotone" dataKey="p99_latency_ms" name="p99" stroke="#8b5cf6" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="avg_latency_ms" name="avg" stroke="#8b5cf680" strokeWidth={1} dot={false} strokeDasharray="4 2" />
                </LineChart>
              </ResponsiveContainer>
            </ChartCard>

            <ChartCard title="Token Usage">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData}>
                  <CartesianGrid {...GRID_STYLE} />
                  <XAxis dataKey="label" tick={AXIS_STYLE} />
                  <YAxis tick={AXIS_STYLE} width={45} tickFormatter={v => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : v} />
                  <Tooltip content={<ChartTooltip />} />
                  <Area type="monotone" dataKey="input_tokens" name="Input" stackId="1" stroke="#0ea5e9" fill="#0ea5e920" />
                  <Area type="monotone" dataKey="output_tokens" name="Output" stackId="1" stroke="#14b8a6" fill="#14b8a620" />
                </AreaChart>
              </ResponsiveContainer>
            </ChartCard>
          </div>
        </>
      )}

      {/* ── MODELS TAB ────────────────────────────────────────── */}
      {tab === "models" && (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <StatCard
              label="Total Models"
              value={models?.length ?? "—"}
              icon={Cpu}
              color="#8b5cf6"
            />
            <StatCard
              label="Total Tokens"
              value={models ? `${((models.reduce((s, m) => s + m.input_tokens + m.output_tokens, 0)) / 1000).toFixed(0)}k` : "—"}
              icon={Coins}
              color="#0ea5e9"
            />
            <StatCard
              label="Total Cost"
              value={models ? `$${models.reduce((s, m) => s + (m.est_cost_usd ?? 0), 0).toFixed(3)}` : "—"}
              icon={Coins}
              color="#10b981"
            />
            <StatCard
              label="Avg Latency"
              value={models?.length ? formatLatency(models.reduce((s, m) => s + m.avg_latency_ms * m.calls, 0) / models.reduce((s, m) => s + m.calls, 0)) : "—"}
              icon={Clock}
              color="#f59e0b"
            />
          </div>

          {/* Model table */}
          <div className="rounded-xl border overflow-hidden" style={{
            background: "hsl(var(--card))", borderColor: "hsl(var(--border))",
          }}>
            <table className="w-full text-[12px]">
              <thead>
                <tr className="border-b" style={{ borderColor: "hsl(var(--border))" }}>
                  <th className="text-left px-4 py-2.5 font-semibold text-muted-foreground">Model</th>
                  <th className="text-right px-4 py-2.5 font-semibold text-muted-foreground">Calls</th>
                  <th className="text-right px-4 py-2.5 font-semibold text-muted-foreground">Input Tokens</th>
                  <th className="text-right px-4 py-2.5 font-semibold text-muted-foreground">Output Tokens</th>
                  <th className="text-right px-4 py-2.5 font-semibold text-muted-foreground">Avg Latency</th>
                  <th className="text-right px-4 py-2.5 font-semibold text-muted-foreground">Errors</th>
                  <th className="text-right px-4 py-2.5 font-semibold text-muted-foreground">Est. Cost</th>
                </tr>
              </thead>
              <tbody>
                {(models ?? []).map(m => (
                  <tr key={m.model_id} className="border-b last:border-0 hover:bg-accent/30" style={{ borderColor: "hsl(var(--border))" }}>
                    <td className="px-4 py-2.5 font-mono font-medium text-foreground">{m.model_id}</td>
                    <td className="px-4 py-2.5 text-right font-mono text-muted-foreground">{m.calls.toLocaleString()}</td>
                    <td className="px-4 py-2.5 text-right font-mono text-muted-foreground">{m.input_tokens.toLocaleString()}</td>
                    <td className="px-4 py-2.5 text-right font-mono text-muted-foreground">{m.output_tokens.toLocaleString()}</td>
                    <td className="px-4 py-2.5 text-right font-mono text-muted-foreground">{formatLatency(m.avg_latency_ms)}</td>
                    <td className={cn("px-4 py-2.5 text-right font-mono", m.error_count > 0 ? "text-red-400" : "text-muted-foreground")}>{m.error_count}</td>
                    <td className="px-4 py-2.5 text-right font-mono text-emerald-400">{m.est_cost_usd != null ? `$${m.est_cost_usd.toFixed(4)}` : "—"}</td>
                  </tr>
                ))}
                {(!models || models.length === 0) && (
                  <tr><td colSpan={7} className="px-4 py-8 text-center text-muted-foreground">No model data for this period</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* ── TOOLS TAB ─────────────────────────────────────────── */}
      {tab === "tools" && (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <StatCard
              label="Unique Tools"
              value={realTools.length}
              icon={Server}
              color="#0ea5e9"
            />
            <StatCard
              label="Total Calls"
              value={realTools.reduce((s, t) => s + t.calls, 0).toLocaleString()}
              icon={Zap}
              color="#14b8a6"
            />
            <StatCard
              label="Total Errors"
              value={realTools.reduce((s, t) => s + t.errors, 0)}
              icon={AlertTriangle}
              color={realTools.some(t => t.errors > 0) ? "#ef4444" : "#22c55e"}
            />
            <StatCard
              label="Avg Latency"
              value={realTools.length ? formatLatency(realTools.reduce((s, t) => s + t.avg_latency_ms * t.calls, 0) / Math.max(realTools.reduce((s, t) => s + t.calls, 0), 1)) : "—"}
              icon={Clock}
              color="#8b5cf6"
            />
          </div>

          {/* Tool table */}
          <div className="rounded-xl border overflow-hidden" style={{
            background: "hsl(var(--card))", borderColor: "hsl(var(--border))",
          }}>
            <table className="w-full text-[12px]">
              <thead>
                <tr className="border-b" style={{ borderColor: "hsl(var(--border))" }}>
                  <th className="text-left px-4 py-2.5 font-semibold text-muted-foreground">Server</th>
                  <th className="text-left px-4 py-2.5 font-semibold text-muted-foreground">Tool</th>
                  <th className="text-right px-4 py-2.5 font-semibold text-muted-foreground">Calls</th>
                  <th className="text-right px-4 py-2.5 font-semibold text-muted-foreground">Errors</th>
                  <th className="text-right px-4 py-2.5 font-semibold text-muted-foreground">Avg Latency</th>
                  <th className="text-right px-4 py-2.5 font-semibold text-muted-foreground">p99 Latency</th>
                  <th className="text-right px-4 py-2.5 font-semibold text-muted-foreground">Success Rate</th>
                </tr>
              </thead>
              <tbody>
                {realTools.map(t => (
                  <tr key={`${t.server_name}:${t.tool_name}`} className="border-b last:border-0 hover:bg-accent/30" style={{ borderColor: "hsl(var(--border))" }}>
                    <td className="px-4 py-2.5 font-mono text-muted-foreground">{t.server_name}</td>
                    <td className="px-4 py-2.5 font-mono font-medium text-foreground">{t.tool_name}</td>
                    <td className="px-4 py-2.5 text-right font-mono text-muted-foreground">{t.calls.toLocaleString()}</td>
                    <td className={cn("px-4 py-2.5 text-right font-mono", t.errors > 0 ? "text-red-400" : "text-muted-foreground")}>{t.errors}</td>
                    <td className="px-4 py-2.5 text-right font-mono text-muted-foreground">{formatLatency(t.avg_latency_ms)}</td>
                    <td className="px-4 py-2.5 text-right font-mono text-muted-foreground">{formatLatency(t.p99_latency_ms)}</td>
                    <td className={cn("px-4 py-2.5 text-right font-mono font-semibold", t.success_rate < 95 ? "text-red-400" : "text-emerald-400")}>{t.success_rate.toFixed(1)}%</td>
                  </tr>
                ))}
                {realTools.length === 0 && (
                  <tr><td colSpan={7} className="px-4 py-8 text-center text-muted-foreground">No tool data for this period</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
