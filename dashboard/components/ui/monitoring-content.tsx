"use client";

/**
 * Shared monitoring content sections rendered by the home overview page.
 *
 * Consumers pass already-fetched data and styling constants so this component
 * stays purely presentational (no SWR / no data fetching).
 */

import {
  AreaChart, Area, BarChart, Bar, LineChart, Line,
  XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
  Brush, Legend,
} from "recharts";
import {
  Activity, Zap, AlertTriangle, Clock, Coins, Cpu, Server,
} from "lucide-react";
import { cn, formatLatency } from "@/lib/utils";
import { StatCard, ChartCard, ChartTooltip, TrendBadge } from "@/components/ui/chart-primitives";
import type { MonitoringBucket, MonitoringModel, MonitoringTool, ErrorCategory, MonitoringTrends } from "@/lib/api";

/* ── Shared axis / grid styles ─────────────────────────────────── */
export const AXIS_STYLE = {
  fontSize: 10,
  fill: "hsl(var(--muted-foreground))",
  fontFamily: "var(--font-geist-mono)",
} as const;

export const GRID_STYLE = {
  stroke: "hsl(var(--border))",
  strokeDasharray: "3 3",
} as const;

/* ── Chart data format ─────────────────────────────────────────── */
export type ChartBucket = MonitoringBucket & { label: string };

/* ── Summary derived from timeseries ──────────────────────────── */
export interface MonitoringSummary {
  totalSessions: number;
  totalToolCalls: number;
  totalErrors: number;
  totalInputTokens: number;
  totalOutputTokens: number;
  avgLatency: number;
  errorRate: number;
  maxAgents: number;
}

export function deriveSummary(timeseries: MonitoringBucket[]): MonitoringSummary {
  const totalSessions    = timeseries.reduce((s, b) => s + b.sessions, 0);
  const totalToolCalls   = timeseries.reduce((s, b) => s + b.tool_calls, 0);
  const totalErrors      = timeseries.reduce((s, b) => s + b.errors, 0);
  const totalInputTokens  = timeseries.reduce((s, b) => s + b.input_tokens, 0);
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
}

/* ── Overview stat cards ────────────────────────────────────────── */
export function OverviewStatCards({
  summary,
  hours,
  trends,
}: {
  summary: MonitoringSummary | null;
  hours: number;
  trends?: MonitoringTrends | null;
}) {
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      <StatCard
        label="Sessions"
        value={summary?.totalSessions ?? "—"}
        icon={Activity}
        color="#14b8a6"
        sub={`last ${hours}h`}
        trend={hours === 168 && trends ? <TrendBadge pct={trends.sessions_delta_pct} invert /> : undefined}
      />
      <StatCard
        label="Tool Calls"
        value={summary?.totalToolCalls?.toLocaleString() ?? "—"}
        icon={Zap}
        color="#0ea5e9"
        sub={`${summary?.totalErrors ?? 0} errors`}
      />
      <StatCard
        label="Error Rate"
        value={summary ? `${summary.errorRate.toFixed(1)}%` : "—"}
        icon={AlertTriangle}
        color={summary && summary.errorRate > 5 ? "#ef4444" : "#22c55e"}
        trend={hours === 168 && trends ? <TrendBadge pct={trends.error_rate_delta_pct} /> : undefined}
      />
      <StatCard
        label="Avg Latency"
        value={summary ? formatLatency(summary.avgLatency) : "—"}
        icon={Clock}
        color="#8b5cf6"
        trend={hours === 168 && trends ? <TrendBadge pct={trends.avg_latency_delta_pct} /> : undefined}
      />
    </div>
  );
}

/* ── Shared brush style ────────────────────────────────────────── */
const BRUSH_PROPS = {
  height: 20,
  stroke: "hsl(var(--border))",
  fill: "hsl(var(--muted))",
  travellerWidth: 8,
  style: { fontSize: 9, fontFamily: "var(--font-geist-mono)" },
} as const;

/* ── Agent charts ──────────────────────────────────────────────── */
export function AgentCharts({ chartData, hours, onHoursChange }: {
  chartData: ChartBucket[];
  hours?: number;
  onHoursChange?: (h: number) => void;
}) {
  return (
    <>
      <div className="grid lg:grid-cols-2 gap-3">
        <ChartCard title="Agent Sessions" ariaLabel="Bar chart showing agent session counts over time" hours={hours} onHoursChange={onHoursChange}>
          {(isExpanded) => (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData}>
                <CartesianGrid {...GRID_STYLE} />
                <XAxis dataKey="label" tick={AXIS_STYLE} />
                <YAxis tick={AXIS_STYLE} width={35} />
                <Tooltip content={<ChartTooltip />} />
                {isExpanded && <Legend wrapperStyle={{ fontSize: 11 }} />}
                <Bar dataKey="sessions" name="Sessions" fill="#14b8a6" radius={[3, 3, 0, 0]} />
                {isExpanded && <Brush dataKey="label" {...BRUSH_PROPS} />}
              </BarChart>
            </ResponsiveContainer>
          )}
        </ChartCard>

        <ChartCard title="Agent Error Rate" ariaLabel="Line chart showing percentage of agent sessions with at least one failed tool call" hours={hours} onHoursChange={onHoursChange}>
          {(isExpanded) => (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
                <CartesianGrid {...GRID_STYLE} />
                <XAxis dataKey="label" tick={AXIS_STYLE} />
                <YAxis tick={AXIS_STYLE} width={35} tickFormatter={v => `${(v * 100).toFixed(0)}%`} />
                <Tooltip content={<ChartTooltip formatter={v => `${(v * 100).toFixed(1)}%`} />} />
                {isExpanded && <Legend wrapperStyle={{ fontSize: 11 }} />}
                <Line type="monotone" dataKey="session_error_rate" name="Session Error Rate" stroke="#ef4444" strokeWidth={2} dot={false} />
                {isExpanded && <Brush dataKey="label" {...BRUSH_PROPS} />}
              </LineChart>
            </ResponsiveContainer>
          )}
        </ChartCard>
      </div>

      <div className="grid lg:grid-cols-2 gap-3">
        <ChartCard title="Agent p99 Latency" ariaLabel="Line chart showing p99 agent execution duration over time" hours={hours} onHoursChange={onHoursChange}>
          {(isExpanded) => (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
                <CartesianGrid {...GRID_STYLE} />
                <XAxis dataKey="label" tick={AXIS_STYLE} />
                <YAxis tick={AXIS_STYLE} width={45} tickFormatter={v => formatLatency(v)} />
                <Tooltip content={<ChartTooltip formatter={v => formatLatency(v)} />} />
                {isExpanded && <Legend wrapperStyle={{ fontSize: 11 }} />}
                <Line type="monotone" dataKey="session_p99_ms" name="p99 (agent)" stroke="#f59e0b" strokeWidth={2} dot={false} />
                {isExpanded && <Brush dataKey="label" {...BRUSH_PROPS} />}
              </LineChart>
            </ResponsiveContainer>
          )}
        </ChartCard>

        <ChartCard title="Agent Token Usage" ariaLabel="Stacked area chart showing LLM input and output token usage over time" hours={hours} onHoursChange={onHoursChange}>
          {(isExpanded) => (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData}>
                <CartesianGrid {...GRID_STYLE} />
                <XAxis dataKey="label" tick={AXIS_STYLE} />
                <YAxis tick={AXIS_STYLE} width={45} tickFormatter={v => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : String(v)} />
                <Tooltip content={<ChartTooltip />} />
                {isExpanded && <Legend wrapperStyle={{ fontSize: 11 }} />}
                <Area type="monotone" dataKey="input_tokens" name="Input" stackId="1" stroke="#0ea5e9" fill="#0ea5e920" />
                <Area type="monotone" dataKey="output_tokens" name="Output" stackId="1" stroke="#14b8a6" fill="#14b8a620" />
                {isExpanded && <Brush dataKey="label" {...BRUSH_PROPS} />}
              </AreaChart>
            </ResponsiveContainer>
          )}
        </ChartCard>
      </div>
    </>
  );
}

/* ── MCP charts ────────────────────────────────────────────────── */
export function McpCharts({ chartData, hours, onHoursChange }: {
  chartData: ChartBucket[];
  hours?: number;
  onHoursChange?: (h: number) => void;
}) {
  return (
    <div className="grid lg:grid-cols-3 gap-3">
      <ChartCard title="MCP Tool Calls" ariaLabel="Bar chart showing MCP tool call volume over time" hours={hours} onHoursChange={onHoursChange}>
        {(isExpanded) => (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData}>
              <CartesianGrid {...GRID_STYLE} />
              <XAxis dataKey="label" tick={AXIS_STYLE} />
              <YAxis tick={AXIS_STYLE} width={35} />
              <Tooltip content={<ChartTooltip />} />
              {isExpanded && <Legend wrapperStyle={{ fontSize: 11 }} />}
              <Bar dataKey="tool_calls" name="Tool Calls" fill="#0ea5e9" radius={[3, 3, 0, 0]} />
              {isExpanded && <Brush dataKey="label" {...BRUSH_PROPS} />}
            </BarChart>
          </ResponsiveContainer>
        )}
      </ChartCard>

      <ChartCard title="MCP Error Rate" ariaLabel="Line chart showing MCP tool call error rate over time" hours={hours} onHoursChange={onHoursChange}>
        {(isExpanded) => (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData}>
              <CartesianGrid {...GRID_STYLE} />
              <XAxis dataKey="label" tick={AXIS_STYLE} />
              <YAxis tick={AXIS_STYLE} width={35} tickFormatter={v => `${(v * 100).toFixed(0)}%`} />
              <Tooltip content={<ChartTooltip formatter={v => `${(v * 100).toFixed(1)}%`} />} />
              {isExpanded && <Legend wrapperStyle={{ fontSize: 11 }} />}
              <Line type="monotone" dataKey="error_rate" name="Error Rate" stroke="#ef4444" strokeWidth={2} dot={false} />
              {isExpanded && <Brush dataKey="label" {...BRUSH_PROPS} />}
            </LineChart>
          </ResponsiveContainer>
        )}
      </ChartCard>

      <ChartCard title="MCP p99 Latency" ariaLabel="Line chart showing MCP tool call p99 and average latency over time" hours={hours} onHoursChange={onHoursChange}>
        {(isExpanded) => (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData}>
              <CartesianGrid {...GRID_STYLE} />
              <XAxis dataKey="label" tick={AXIS_STYLE} />
              <YAxis tick={AXIS_STYLE} width={45} tickFormatter={v => formatLatency(v)} />
              <Tooltip content={<ChartTooltip formatter={v => formatLatency(v)} />} />
              {isExpanded && <Legend wrapperStyle={{ fontSize: 11 }} />}
              <Line type="monotone" dataKey="p99_latency_ms" name="p99" stroke="#8b5cf6" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="avg_latency_ms" name="avg" stroke="#8b5cf680" strokeWidth={1} dot={false} strokeDasharray="4 2" />
              {isExpanded && <Brush dataKey="label" {...BRUSH_PROPS} />}
            </LineChart>
          </ResponsiveContainer>
        )}
      </ChartCard>
    </div>
  );
}

/** @deprecated Use AgentCharts + McpCharts instead */
export function OverviewCharts({ chartData }: { chartData: ChartBucket[] }) {
  return (
    <>
      <AgentCharts chartData={chartData} />
      <McpCharts chartData={chartData} />
    </>
  );
}

/* ── Error breakdown bar list ────────────────────────────────────── */
export function ErrorBreakdown({ errorBreakdown }: { errorBreakdown: ErrorCategory[] }) {
  if (!errorBreakdown.length) return null;
  return (
    <div className="rounded-xl border p-4" style={{
      background: "hsl(var(--card))", borderColor: "hsl(var(--border))",
    }}>
      <h3 className="text-[12px] font-semibold text-muted-foreground mb-3 uppercase tracking-wider">Error Breakdown</h3>
      <div className="space-y-2">
        {errorBreakdown.map(e => {
          const color = e.category === "safety_filter" ? "#f59e0b"
            : e.category === "max_tokens" ? "#8b5cf6"
            : e.category === "api_unavailable" ? "#ef4444"
            : e.category === "timeout" ? "#f97316"
            : e.category === "rate_limit" ? "#eab308"
            : e.category === "auth_error" ? "#ec4899"
            : e.category === "agent_crash" ? "#ef4444"
            : "#6b7280";
          const label = e.category === "safety_filter" ? "Safety Filter"
            : e.category === "max_tokens" ? "Max Tokens Hit"
            : e.category === "api_unavailable" ? "API Unavailable (5xx)"
            : e.category === "timeout" ? "Timeout"
            : e.category === "rate_limit" ? "Rate Limited (429)"
            : e.category === "auth_error" ? "Auth Error (401/403)"
            : e.category === "agent_crash" ? "Agent Crash"
            : "Other";
          return (
            <div key={e.category} className="flex items-center gap-3">
              <span className="text-[11px] text-muted-foreground w-36 flex-shrink-0">{label}</span>
              <div className="flex-1 h-[6px] rounded-full overflow-hidden" style={{ background: "hsl(var(--muted))" }}>
                <div className="h-full rounded-full" style={{ width: `${e.pct}%`, background: color }} />
              </div>
              <span className="text-[11px] font-mono font-semibold w-10 text-right flex-shrink-0"
                style={{ color, fontFamily: "var(--font-geist-mono)" }}>
                {e.pct}%
              </span>
              <span className="text-[10px] text-muted-foreground w-10 text-right flex-shrink-0"
                style={{ fontFamily: "var(--font-geist-mono)" }}>
                {e.count}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ── Model stat cards ──────────────────────────────────────────── */
export function ModelStatCards({ models }: { models: MonitoringModel[] | undefined }) {
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      <StatCard label="Total Models" value={models?.length ?? "—"} icon={Cpu} color="#8b5cf6" />
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
        value={models?.length
          ? formatLatency(models.reduce((s, m) => s + m.avg_latency_ms * m.calls, 0) / models.reduce((s, m) => s + m.calls, 0))
          : "—"}
        icon={Clock}
        color="#f59e0b"
      />
    </div>
  );
}

/* ── Model table ────────────────────────────────────────────────── */
const MODEL_CONTEXT_LIMITS: Record<string, number> = {
  "gemini-2.5-flash": 1_048_576, "gemini-2.5-pro": 1_048_576,
  "gemini-2.0-flash": 1_048_576, "gemini-1.5-pro": 1_048_576,
  "gemini-1.5-flash": 1_048_576,
  "gpt-4o": 128_000, "gpt-4o-mini": 128_000, "o3": 200_000, "o3-mini": 200_000,
  "claude-opus-4-6": 200_000, "claude-sonnet-4-6": 200_000, "claude-haiku-4-5-20251001": 200_000,
};

export function ModelTable({
  models,
  showCtxUsage = false,
}: {
  models: MonitoringModel[] | undefined;
  /** Show context window usage column (home page only) */
  showCtxUsage?: boolean;
}) {
  const colCount = showCtxUsage ? 8 : 7;
  return (
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
            {showCtxUsage && (
              <th className="text-right px-4 py-2.5 font-semibold text-muted-foreground">Ctx Usage</th>
            )}
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
              <td className={cn("px-4 py-2.5 text-right font-mono", m.error_count > 0 ? "text-red-400" : "text-muted-foreground")}>
                {m.error_count}
              </td>
              {showCtxUsage && (
                <td className="px-4 py-2.5 text-right font-mono whitespace-nowrap">
                  {(() => {
                    const limit = MODEL_CONTEXT_LIMITS[m.model_id];
                    if (!limit || m.input_tokens === 0) return <span className="opacity-30">—</span>;
                    const avgPerCall = m.input_tokens / Math.max(m.calls, 1);
                    const pct = Math.round(avgPerCall / limit * 100);
                    return (
                      <span className={pct > 80 ? "text-red-400 font-semibold" : pct > 50 ? "text-amber-400" : "text-muted-foreground"}>
                        {pct}%
                      </span>
                    );
                  })()}
                </td>
              )}
              <td className="px-4 py-2.5 text-right font-mono text-emerald-400">
                {m.est_cost_usd != null ? `$${m.est_cost_usd.toFixed(4)}` : "—"}
              </td>
            </tr>
          ))}
          {(!models || models.length === 0) && (
            <tr>
              <td colSpan={colCount} className="px-4 py-8 text-center text-muted-foreground">
                No model data for this period
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

/* ── Tool stat cards ────────────────────────────────────────────── */
export function ToolStatCards({ realTools }: { realTools: MonitoringTool[] }) {
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      <StatCard label="Unique Tools" value={realTools.length} icon={Server} color="#0ea5e9" />
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
        value={realTools.length
          ? formatLatency(
              realTools.reduce((s, t) => s + t.avg_latency_ms * t.calls, 0) /
              Math.max(realTools.reduce((s, t) => s + t.calls, 0), 1)
            )
          : "—"}
        icon={Clock}
        color="#8b5cf6"
      />
    </div>
  );
}

/* ── Tool table ─────────────────────────────────────────────────── */
export function ToolTable({
  realTools,
  showExtended = false,
}: {
  realTools: MonitoringTool[];
  /** Show Silent Failures, Calls/Session columns (home page only) */
  showExtended?: boolean;
}) {
  const colCount = showExtended ? 9 : 7;
  return (
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
            {showExtended && (
              <th className="text-right px-4 py-2.5 font-semibold text-muted-foreground" title="isError=False responses that contained error text">
                Silent Failures
              </th>
            )}
            <th className="text-right px-4 py-2.5 font-semibold text-muted-foreground">Avg Latency</th>
            <th className="text-right px-4 py-2.5 font-semibold text-muted-foreground">p99 Latency</th>
            {showExtended && (
              <th className="text-right px-4 py-2.5 font-semibold text-muted-foreground">Calls/Session</th>
            )}
            <th className="text-right px-4 py-2.5 font-semibold text-muted-foreground">Success Rate</th>
          </tr>
        </thead>
        <tbody>
          {realTools.map(t => (
            <tr key={`${t.server_name}:${t.tool_name}`} className="border-b last:border-0 hover:bg-accent/30" style={{ borderColor: "hsl(var(--border))" }}>
              <td className="px-4 py-2.5 font-mono text-muted-foreground">{t.server_name}</td>
              <td className="px-4 py-2.5 font-mono font-medium text-foreground">{t.tool_name}</td>
              <td className="px-4 py-2.5 text-right font-mono text-muted-foreground">{t.calls.toLocaleString()}</td>
              <td className={cn("px-4 py-2.5 text-right font-mono", t.errors > 0 ? "text-red-400" : "text-muted-foreground")}>
                {t.errors}
              </td>
              {showExtended && (
                <td className={cn("px-4 py-2.5 text-right font-mono", t.content_errors > 0 ? "text-amber-400 font-semibold" : "text-muted-foreground opacity-40")}>
                  {t.content_errors > 0 ? t.content_errors : "0"}
                </td>
              )}
              <td className="px-4 py-2.5 text-right font-mono text-muted-foreground">{formatLatency(t.avg_latency_ms)}</td>
              <td className="px-4 py-2.5 text-right font-mono text-muted-foreground">{formatLatency(t.p99_latency_ms)}</td>
              {showExtended && (
                <td className={cn("px-4 py-2.5 text-right font-mono font-semibold", t.calls_per_session > 5 ? "text-amber-400" : "text-muted-foreground")}>
                  {t.calls_per_session > 0 ? `${t.calls_per_session.toFixed(1)}×` : "—"}
                </td>
              )}
              <td className={cn("px-4 py-2.5 text-right font-mono font-semibold", t.success_rate < 95 ? "text-red-400" : "text-emerald-400")}>
                {t.success_rate.toFixed(1)}%
              </td>
            </tr>
          ))}
          {realTools.length === 0 && (
            <tr>
              <td colSpan={colCount} className="px-4 py-8 text-center text-muted-foreground">
                No tool data for this period
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
