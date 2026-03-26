"use client";

export const dynamic = "force-dynamic";

import useSWR from "swr";
import { useMemo, useState } from "react";
import { useProject } from "@/lib/project-context";
import { cn } from "@/lib/utils";
import {
  getMonitoringTimeseries, getMonitoringModels, getMonitoringTools, listAgentMetadata,
} from "@/lib/api";
import {
  OverviewStatCards,
  OverviewCharts,
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

  // Agent names for tool filtering — exclude spans where server_name is an agent name
  const { data: agentMetadata } = useSWR(
    pid ? `/agents/metadata/${pid}` : "/agents/metadata/all",
    () => listAgentMetadata(pid),
    { refreshInterval: 300_000, revalidateOnFocus: false },
  );

  // Aggregate summary from timeseries
  const summary = useMemo(() => {
    if (!timeseries?.length) return null;
    return deriveSummary(timeseries);
  }, [timeseries]);

  // Chart data with formatted labels
  const chartData = useMemo<ChartBucket[]>(() =>
    (timeseries ?? []).map(b => ({ ...b, label: fmtBucket(b.bucket) })),
    [timeseries],
  );

  // Filter tools: exclude LLM intent spans (server_name matches an actual agent name)
  const realTools = useMemo(() => {
    if (!tools) return [];
    const agentNames = new Set(agentMetadata?.map(a => a.agent_name) ?? []);
    return tools.filter(t => !agentNames.has(t.server_name));
  }, [tools, agentMetadata]);

  return (
    <div className="space-y-4 page-in">
      {/* ── Header bar ─────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div
          className="flex items-center gap-1 rounded-lg border overflow-hidden"
          role="tablist"
          aria-label="Monitoring view"
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
          <OverviewStatCards summary={summary} hours={hours} />
          <OverviewCharts chartData={chartData} />
        </>
      )}

      {/* ── MODELS TAB ────────────────────────────────────────── */}
      {tab === "models" && (
        <>
          <ModelStatCards models={models} />
          <ModelTable models={models} showCtxUsage={false} />
        </>
      )}

      {/* ── TOOLS TAB ─────────────────────────────────────────── */}
      {tab === "tools" && (
        <>
          <ToolStatCards realTools={realTools} />
          <ToolTable realTools={realTools} showExtended={false} />
        </>
      )}
    </div>
  );
}
