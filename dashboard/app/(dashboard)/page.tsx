"use client";

export const dynamic = "force-dynamic";

import useSWR from "swr";
import { useMemo, useState, useEffect } from "react";
import { Activity, Server, ArrowRight, AlertTriangle, CheckCircle2, XCircle, Clock } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { useProject } from "@/lib/project-context";
import { cn } from "@/lib/utils";
import {
  getMonitoringTimeseries, getMonitoringModels, getMonitoringTools, getMonitoringErrors, getMonitoringTrends,
  listAgentMetadata, getServerHealth,
} from "@/lib/api";
import type { HealthResult } from "@/lib/types";
import {
  OverviewStatCards,
  AgentCharts,
  McpCharts,
  ErrorBreakdown,
  ModelStatCards,
  ModelTable,
  ToolStatCards,
  ToolTable,
  deriveSummary,
  type ChartBucket,
} from "@/components/ui/monitoring-content";

/* ── MCP health status helpers ────────────────────────────────── */
const STATUS_COLOR: Record<string, string> = {
  up: "#22c55e",
  degraded: "#f59e0b",
  down: "#ef4444",
  stale: "#6b7280",
  unknown: "#6b7280",
};

function McpHealthSummaryCard({ servers }: { servers: HealthResult[] }) {
  const up       = servers.filter(s => s.status === "up").length;
  const degraded = servers.filter(s => s.status === "degraded").length;
  const down     = servers.filter(s => s.status === "down").length;
  const stale    = servers.filter(s => s.status === "stale" || s.status === "unknown").length;
  const issues   = servers.filter(s => s.status === "down" || s.status === "degraded");
  const allOk    = issues.length === 0 && servers.length > 0;

  const latestCheck = servers.reduce<string | null>((best, s) => {
    if (!best) return s.checked_at;
    return s.checked_at > best ? s.checked_at : best;
  }, null);

  function fmtChecked(iso: string | null): string {
    if (!iso) return "never";
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60_000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins}m ago`;
    return `${Math.floor(mins / 60)}h ago`;
  }

  if (servers.length === 0) {
    return (
      <div className="rounded-xl border p-4 flex items-center gap-3" style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}>
        <div className="w-7 h-7 rounded-lg flex items-center justify-center" style={{ background: "#6366f118", border: "1px solid #6366f130" }}>
          <Server size={13} style={{ color: "#6366f1" }} />
        </div>
        <span className="text-[12px] text-muted-foreground">No MCP servers configured. <Link href="/servers" className="underline underline-offset-2 hover:text-foreground transition-colors">Add one →</Link></span>
      </div>
    );
  }

  return (
    <div
      className="rounded-xl border p-4"
      style={{
        background: "hsl(var(--card))",
        borderColor: allOk ? "hsl(var(--border))" : issues.some(s => s.status === "down") ? "#ef444430" : "#f59e0b30",
      }}
    >
      {/* Header row */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg flex items-center justify-center" style={{ background: allOk ? "#22c55e18" : "#ef444418", border: `1px solid ${allOk ? "#22c55e30" : "#ef444430"}` }}>
            <Server size={13} style={{ color: allOk ? "#22c55e" : "#ef4444" }} />
          </div>
          <span className="text-[11px] text-muted-foreground font-medium uppercase tracking-wider">MCP Servers</span>
        </div>
        <Link href="/servers" className="flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground transition-colors">
          View all <ArrowRight size={11} />
        </Link>
      </div>

      {/* Status dots row */}
      <div className="flex items-center gap-3 mb-3">
        <div className="flex items-center gap-1 flex-wrap">
          {servers.map(s => (
            <span
              key={s.server_name}
              title={`${s.server_name}: ${s.status}`}
              className="w-2.5 h-2.5 rounded-full inline-block"
              style={{ background: STATUS_COLOR[s.status] ?? "#6b7280" }}
            />
          ))}
        </div>
        <div className="flex items-center gap-2 text-[11px]" style={{ fontFamily: "var(--font-geist-mono)" }}>
          {up > 0 && <span style={{ color: "#22c55e" }}>{up} up</span>}
          {degraded > 0 && <span style={{ color: "#f59e0b" }}>{degraded} degraded</span>}
          {down > 0 && <span style={{ color: "#ef4444" }}>{down} down</span>}
          {stale > 0 && <span style={{ color: "#6b7280" }}>{stale} stale</span>}
        </div>
        {latestCheck && (
          <div className="flex items-center gap-1 text-[10px] text-muted-foreground ml-auto">
            <Clock size={10} />
            <span>{fmtChecked(latestCheck)}</span>
          </div>
        )}
      </div>

      {/* Issue alerts */}
      {issues.length > 0 && (
        <div className="space-y-1.5 border-t pt-3" style={{ borderColor: "hsl(var(--border))" }}>
          {issues.map(s => (
            <div key={s.server_name} className="flex items-center gap-2 text-[11px]">
              {s.status === "down"
                ? <XCircle size={12} style={{ color: "#ef4444", flexShrink: 0 }} />
                : <AlertTriangle size={12} style={{ color: "#f59e0b", flexShrink: 0 }} />}
              <span className="font-medium text-foreground">{s.server_name}</span>
              <span className="text-muted-foreground capitalize">{s.status}</span>
              {s.latency_ms != null && (
                <span className="text-muted-foreground ml-auto" style={{ fontFamily: "var(--font-geist-mono)" }}>
                  {s.latency_ms.toFixed(0)}ms
                </span>
              )}
              {s.error && (
                <span className="text-muted-foreground truncate max-w-[240px]" title={s.error}>
                  {s.error.length > 60 ? s.error.slice(0, 60) + "…" : s.error}
                </span>
              )}
            </div>
          ))}
        </div>
      )}

      {/* All OK banner */}
      {allOk && (
        <div className="flex items-center gap-2 text-[11px]" style={{ color: "#22c55e" }}>
          <CheckCircle2 size={12} />
          <span>All {servers.length} servers healthy</span>
        </div>
      )}
    </div>
  );
}

/* ── Time range selector ──────────────────────────────────────── */
const RANGES = [
  { label: "1h", hours: 1 },
  { label: "6h", hours: 6 },
  { label: "24h", hours: 24 },
  { label: "7d", hours: 168 },
] as const;

/* ── Tab type ─────────────────────────────────────────────────── */
type Tab = "overview" | "models" | "tools";

/* ── Format bucket label ──────────────────────────────────────── */
function fmtBucket(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", hour12: false });
}

/* ── Main page ────────────────────────────────────────────────── */
export default function DashboardPage() {
  const { activeProject, isLoading: projectLoading } = useProject();
  const pid = activeProject?.id ?? null;
  const router = useRouter();
  const searchParams = useSearchParams();

  const [hours, setHours] = useState<number>(() => {
    const v = searchParams.get("hours");
    const n = v ? Number(v) : 24;
    return Number.isFinite(n) && n > 0 ? Math.min(Math.floor(n), 8760) : 24;
  });
  const [tab, setTab] = useState<Tab>(() => {
    const v = searchParams.get("tab");
    return (v === "models" || v === "tools") ? v : "overview";
  });

  // Sync hours + tab to URL
  useEffect(() => {
    const params = new URLSearchParams();
    if (hours !== 24) params.set("hours", String(hours));
    if (tab !== "overview") params.set("tab", tab);
    const qs = params.toString();
    router.replace(qs ? `/?${qs}` : "/", { scroll: false });
  }, [hours, tab, router]);

  // Allow fetching without a project_id — API returns aggregated data for admins.
  // Use stable SWR keys that encode hours, tab, and pid (or "all" when pid is null).
  const pidKey = pid ?? "all";

  const { data: timeseries, isLoading: tsLoading } = useSWR(
    projectLoading ? null : `/monitoring/ts/${hours}/${pidKey}`,
    () => getMonitoringTimeseries(hours, pid),
    { refreshInterval: 60_000 },
  );
  const { data: models } = useSWR(
    !projectLoading && tab === "models" ? `/monitoring/models/${hours}/${pidKey}` : null,
    () => getMonitoringModels(hours, pid),
    { refreshInterval: 120_000 },
  );
  const { data: tools } = useSWR(
    !projectLoading && tab === "tools" ? `/monitoring/tools/${hours}/${pidKey}` : null,
    () => getMonitoringTools(hours, pid),
    { refreshInterval: 120_000 },
  );
  const { data: errorBreakdown } = useSWR(
    !projectLoading && tab === "overview" ? `/monitoring/errors/${hours}/${pidKey}` : null,
    () => getMonitoringErrors(hours, pid),
    { refreshInterval: 120_000 },
  );
  const { data: trends } = useSWR(
    !projectLoading && tab === "overview" ? `/monitoring/trends/${pidKey}` : null,
    () => getMonitoringTrends(pid),
    { refreshInterval: 300_000 },
  );

  // MCP server health — shown in overview tab summary card
  const { data: serverHealth } = useSWR(
    !projectLoading && tab === "overview" ? "/health/servers" : null,
    () => getServerHealth(),
    { refreshInterval: 60_000, revalidateOnFocus: false },
  );

  // Agent names for tool filtering — exclude spans where server_name is an agent name
  const { data: agentMetadata } = useSWR(
    projectLoading ? null : pid ? `/agents/metadata/${pid}` : "/agents/metadata/all",
    () => listAgentMetadata(pid),
    { refreshInterval: 300_000, revalidateOnFocus: false },
  );

  // Aggregate summary from timeseries
  const summary = useMemo(() => {
    if (!timeseries?.length) return null;
    return deriveSummary(timeseries);
  }, [timeseries]);

  // Chart data with formatted labels
  const chartData = useMemo(() =>
    (timeseries ?? []).map(b => ({ ...b, label: fmtBucket(b.bucket) })),
    [timeseries],
  );

  // Filter tools: exclude LLM intent spans (server_name matches an actual agent name)
  const realTools = useMemo(() => {
    if (!tools) return [];
    const agentNames = new Set(agentMetadata?.map(a => a.agent_name) ?? []);
    return tools.filter(t => !agentNames.has(t.server_name));
  }, [tools, agentMetadata]);

  // Project context still initialising — show skeleton to avoid blank flash
  if (projectLoading) {
    return (
      <div className="space-y-4 page-in">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="rounded-xl border p-4 space-y-3 animate-pulse" style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}>
              <div className="h-3 w-24 rounded" style={{ background: "hsl(var(--muted))" }} />
              <div className="h-7 w-32 rounded" style={{ background: "hsl(var(--muted))" }} />
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4 page-in">
      {/* ── "All Projects" info banner (admin only) ─────────────── */}
      {!pid && (
        <div className="rounded-lg border px-4 py-2.5 flex items-center gap-2 text-[12px]" style={{
          background: "hsl(var(--primary) / 0.05)",
          borderColor: "hsl(var(--primary) / 0.2)",
          color: "hsl(var(--primary))",
        }}>
          <Activity size={13} />
          <span>Showing aggregated data across all projects</span>
        </div>
      )}

      {/* ── Loading skeleton while initial timeseries fetch ─────── */}
      {tsLoading && !timeseries && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="rounded-xl border p-4 space-y-3 animate-pulse" style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}>
              <div className="h-3 w-24 rounded" style={{ background: "hsl(var(--muted))" }} />
              <div className="h-7 w-32 rounded" style={{ background: "hsl(var(--muted))" }} />
            </div>
          ))}
        </div>
      )}

      {/* ── Header bar ─────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div
          className="flex items-center gap-1 rounded-lg border overflow-hidden"
          role="tablist"
          aria-label="Overview sections"
          style={{ borderColor: "hsl(var(--border))", background: "hsl(var(--muted))" }}
        >
          {(["overview", "models", "tools"] as Tab[]).map(t => (
            <button
              key={t}
              role="tab"
              aria-selected={tab === t}
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

        <div
          className="flex items-center gap-1 rounded-lg border overflow-hidden"
          role="group"
          aria-label="Time range"
          style={{ borderColor: "hsl(var(--border))", background: "hsl(var(--muted))" }}
        >
          {RANGES.map(r => (
            <button
              key={r.hours}
              aria-pressed={hours === r.hours}
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
          <OverviewStatCards summary={summary} hours={hours} trends={trends} />

          {/* Agent Activity section */}
          <div className="flex items-center gap-3">
            <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-widest whitespace-nowrap">Agent Activity</span>
            <div className="flex-1 h-px" style={{ background: "hsl(var(--border))" }} />
          </div>
          <AgentCharts chartData={chartData} hours={hours} onHoursChange={setHours} />

          {/* MCP Infrastructure section */}
          <div className="flex items-center gap-3">
            <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-widest whitespace-nowrap">MCP Infrastructure</span>
            <div className="flex-1 h-px" style={{ background: "hsl(var(--border))" }} />
          </div>
          <McpCharts chartData={chartData} hours={hours} onHoursChange={setHours} />

          {/* Bottom split: Agent error breakdown (left) + MCP server status (right) */}
          <div className="grid lg:grid-cols-2 gap-3">
            {errorBreakdown && errorBreakdown.length > 0
              ? <ErrorBreakdown errorBreakdown={errorBreakdown} />
              : <div />}
            {serverHealth != null && (
              <McpHealthSummaryCard servers={serverHealth} />
            )}
          </div>
        </>
      )}

      {/* ── MODELS TAB ────────────────────────────────────────── */}
      {tab === "models" && (
        <>
          <ModelStatCards models={models} />
          <ModelTable models={models} showCtxUsage={true} />
        </>
      )}

      {/* ── TOOLS TAB ─────────────────────────────────────────── */}
      {tab === "tools" && (
        <>
          <ToolStatCards realTools={realTools} />
          <ToolTable realTools={realTools} showExtended={true} />
        </>
      )}
    </div>
  );
}
