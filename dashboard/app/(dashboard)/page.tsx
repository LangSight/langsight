"use client";

export const dynamic = "force-dynamic";

import useSWR from "swr";
import { useMemo, useState, useEffect } from "react";
import { Activity } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useProject } from "@/lib/project-context";
import { cn } from "@/lib/utils";
import {
  getMonitoringTimeseries, getMonitoringModels, getMonitoringTools, getMonitoringErrors, getMonitoringTrends,
  listAgentMetadata,
} from "@/lib/api";
import {
  OverviewStatCards,
  OverviewCharts,
  ErrorBreakdown,
  ModelStatCards,
  ModelTable,
  ToolStatCards,
  ToolTable,
  deriveSummary,
  type ChartBucket,
} from "@/components/ui/monitoring-content";

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
          <OverviewCharts chartData={chartData} />
          {errorBreakdown && errorBreakdown.length > 0 && (
            <ErrorBreakdown errorBreakdown={errorBreakdown} />
          )}
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
