"use client";

export const dynamic = "force-dynamic";

import { useState, useEffect, useMemo, useCallback, useRef, useDeferredValue } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import useSWR from "swr";
import { AlertCircle, ArrowDown, ArrowUp, ArrowUpDown, GitBranch, RefreshCw } from "lucide-react";
import { fetcher } from "@/lib/api";
import { useProject } from "@/lib/project-context";
import { cn } from "@/lib/utils";
import { DateRangeFilter } from "@/components/date-range-filter";
import { SessionFilters } from "@/components/sessions/session-filters";
import { SessionRow, effectiveHealthTag } from "@/components/sessions/session-row";
import { SessionPagination } from "@/components/sessions/session-pagination";
import type { AgentSession } from "@/lib/types";

const PAGE_SIZE = 20;

const REFRESH_OPTIONS = [
  { label: "Off",    ms: 0 },
  { label: "30s",    ms: 30_000 },
  { label: "1 min",  ms: 60_000 },
  { label: "5 min",  ms: 300_000 },
  { label: "15 min", ms: 900_000 },
] as const;

type SortDir = "asc" | "desc" | null;
type SortKey =
  | "session_id" | "agent_name" | "health_tag" | "tool_calls"
  | "failed_calls" | "duration_ms" | "tokens" | "est_cost_usd"
  | "servers_used" | "first_call_at" | "timestamp";

function SortHeader({ label, sortKey, currentKey, currentDir, align, onSort }: {
  label: string; sortKey: SortKey; currentKey: SortKey | null;
  currentDir: SortDir; align: string; onSort: (k: SortKey) => void;
}) {
  const isActive = currentKey === sortKey;
  return (
    <th
      className={cn("px-4 py-2.5 text-[11px] font-semibold text-muted-foreground uppercase tracking-wide whitespace-nowrap cursor-pointer select-none hover:text-foreground transition-colors", align)}
      onClick={() => onSort(sortKey)}
    >
      <span className="inline-flex items-center gap-1">
        {label}
        {isActive && currentDir === "asc" ? <ArrowUp size={10} className="text-primary" />
          : isActive && currentDir === "desc" ? <ArrowDown size={10} className="text-primary" />
          : <ArrowUpDown size={10} className="opacity-30" />}
      </span>
    </th>
  );
}

const COLUMNS: { label: string; key: SortKey; align: string }[] = [
  { label: "Session ID", key: "session_id",   align: "text-left" },
  { label: "Agent",      key: "agent_name",   align: "text-left" },
  { label: "Health",     key: "health_tag",   align: "text-left" },
  { label: "Calls",      key: "tool_calls",   align: "text-right" },
  { label: "Failed",     key: "failed_calls", align: "text-right" },
  { label: "Duration",   key: "duration_ms",  align: "text-right" },
  { label: "Tokens",     key: "tokens",       align: "text-right" },
  { label: "Cost",       key: "est_cost_usd", align: "text-right" },
  { label: "Servers",    key: "servers_used", align: "text-left" },
  { label: "Started",    key: "first_call_at",align: "text-left" },
  { label: "Timestamp",  key: "timestamp",    align: "text-left" },
];

export default function SessionsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const pageRef = useRef<HTMLDivElement>(null);

  // Prevent parent <main> from scrolling
  useEffect(() => {
    const main = pageRef.current?.closest("main");
    if (main) { main.style.overflow = "hidden"; return () => { main.style.overflow = ""; }; }
  }, []);

  // Initialise filter state from URL
  const [hours, setHours] = useState(() => {
    const v = searchParams.get("hours"); const n = v ? Number(v) : 24;
    return Number.isFinite(n) && n > 0 ? Math.min(Math.floor(n), 8760) : 24;
  });
  const [search, setSearch]               = useState(() => searchParams.get("q") ?? "");
  const [statusFilter, setStatusFilter]   = useState<"all" | "clean" | "failed">(() => {
    const v = searchParams.get("status"); return (v === "clean" || v === "failed") ? v : "all";
  });
  const [agentFilter, setAgentFilter]     = useState(() => searchParams.get("agent") ?? "all");
  const [healthTagFilter, setHealthTag]   = useState(() => searchParams.get("tag") ?? "all");
  const [page, setPage]                   = useState(() => {
    const v = searchParams.get("page"); const n = v ? Number(v) : 0;
    return Number.isFinite(n) && n >= 0 ? Math.floor(n) : 0;
  });
  const [sortKey, setSortKey]             = useState<SortKey | null>(() => (searchParams.get("sort") as SortKey | null) ?? "first_call_at");
  const [sortDir, setSortDir]             = useState<SortDir>(() => {
    const v = searchParams.get("dir"); return (v === "asc" || v === "desc") ? v : "desc";
  });
  const [refreshMs, setRefreshMs]         = useState(30_000);

  // DASH-03: defer search to avoid filter/sort on every keystroke.
  // React renders the input immediately with the live value,
  // but the expensive filtered list only re-renders when the browser is idle.
  const deferredSearch = useDeferredValue(search);

  // Sync filters → URL
  useEffect(() => {
    const p = new URLSearchParams();
    if (hours !== 24) p.set("hours", String(hours));
    if (search) p.set("q", search);
    if (statusFilter !== "all") p.set("status", statusFilter);
    if (agentFilter !== "all") p.set("agent", agentFilter);
    if (healthTagFilter !== "all") p.set("tag", healthTagFilter);
    if (page !== 0) p.set("page", String(page));
    if (sortKey && sortKey !== "first_call_at") p.set("sort", sortKey);
    if (sortDir && sortDir !== "desc") p.set("dir", sortDir);
    const qs = p.toString();
    router.replace(qs ? `/sessions?${qs}` : "/sessions", { scroll: false });
  }, [hours, search, statusFilter, agentFilter, healthTagFilter, page, sortKey, sortDir, router]);

  const { activeProject } = useProject();
  const projectParam = activeProject ? `&project_id=${activeProject.id}` : "";

  const { data: sessions, isLoading, error, mutate } = useSWR<AgentSession[]>(
    `/api/agents/sessions?hours=${hours}&limit=500${projectParam}`,
    fetcher,
    { refreshInterval: refreshMs || undefined }
  );

  // Reset to page 0 when filters change
  const isFirstRender = useRef(true);
  useEffect(() => {
    if (isFirstRender.current) { isFirstRender.current = false; return; }
    setPage(0);
  }, [deferredSearch, statusFilter, agentFilter, healthTagFilter, hours]);

  const agentNames = useMemo(() => {
    if (!sessions) return [];
    return Array.from(new Set(sessions.map((s) => s.agent_name ?? "unknown"))).sort();
  }, [sessions]);

  const handleSort = useCallback((key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : d === "desc" ? null : "asc"));
      if (sortDir === null) setSortKey(null);
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
    setPage(0);
  }, [sortKey, sortDir]);

  // filtered uses deferredSearch — doesn't run on every keystroke
  const filtered = useMemo(() => {
    if (!sessions) return [];
    let list = sessions.filter((s) => {
      if (statusFilter === "clean"  && s.failed_calls > 0)  return false;
      if (statusFilter === "failed" && s.failed_calls === 0) return false;
      if (agentFilter !== "all" && (s.agent_name ?? "unknown") !== agentFilter) return false;
      if (healthTagFilter !== "all" && (effectiveHealthTag(s) ?? "") !== healthTagFilter) return false;
      if (deferredSearch) {
        const q = deferredSearch.toLowerCase();
        if (
          !s.session_id.toLowerCase().includes(q) &&
          !(s.agent_name ?? "").toLowerCase().includes(q) &&
          !s.servers_used?.some((srv) => srv.toLowerCase().includes(q))
        ) return false;
      }
      return true;
    });

    if (sortKey && sortDir) {
      list = [...list].sort((a, b) => {
        let va: number | string = 0, vb: number | string = 0;
        switch (sortKey) {
          case "session_id":    va = a.session_id;  vb = b.session_id;  break;
          case "agent_name":    va = a.agent_name ?? ""; vb = b.agent_name ?? ""; break;
          case "health_tag":    va = effectiveHealthTag(a) ?? ""; vb = effectiveHealthTag(b) ?? ""; break;
          case "tool_calls":    va = a.tool_calls;  vb = b.tool_calls;  break;
          case "failed_calls":  va = a.failed_calls; vb = b.failed_calls; break;
          case "duration_ms":   va = a.duration_ms; vb = b.duration_ms; break;
          case "tokens":        va = (a.total_input_tokens ?? 0) + (a.total_output_tokens ?? 0); vb = (b.total_input_tokens ?? 0) + (b.total_output_tokens ?? 0); break;
          case "est_cost_usd":  va = a.est_cost_usd ?? 0; vb = b.est_cost_usd ?? 0; break;
          case "servers_used":  va = (a.servers_used || []).length; vb = (b.servers_used || []).length; break;
          case "first_call_at":
          case "timestamp":     va = a.first_call_at; vb = b.first_call_at; break;
        }
        if (typeof va === "string") return sortDir === "asc" ? va.localeCompare(vb as string) : (vb as string).localeCompare(va);
        return sortDir === "asc" ? (va as number) - (vb as number) : (vb as number) - (va as number);
      });
    }
    return list;
  }, [sessions, statusFilter, agentFilter, healthTagFilter, deferredSearch, sortKey, sortDir]);

  const countAll    = sessions?.length ?? 0;
  const countClean  = useMemo(() => sessions?.filter((s) => s.failed_calls === 0).length ?? 0, [sessions]);
  const countFailed = useMemo(() => sessions?.filter((s) => s.failed_calls > 0).length  ?? 0, [sessions]);
  const totalPages  = Math.ceil(filtered.length / PAGE_SIZE);
  const paginated   = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const totalCalls  = useMemo(() => filtered.reduce((n, s) => n + s.tool_calls, 0),   [filtered]);
  const totalFailed = useMemo(() => filtered.reduce((n, s) => n + s.failed_calls, 0), [filtered]);

  return (
    <div ref={pageRef} className="page-in flex flex-col" style={{ maxHeight: "calc(100dvh - 92px)" }}>
      {/* Header */}
      <div className="flex-shrink-0 px-0 pb-3">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold text-foreground">Sessions</h1>
            <p className="text-sm text-muted-foreground mt-0.5">
              {filtered.length} sessions · {totalCalls} tool calls
              {totalFailed > 0 && <span style={{ color: "hsl(var(--danger))" }}> · {totalFailed} failures</span>}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => mutate()}
              title="Refresh now"
              className="p-1.5 rounded-lg border border-border bg-card text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
            >
              <RefreshCw size={13} className={isLoading ? "animate-spin" : ""} />
            </button>
            <div className="flex items-center gap-1 rounded-lg border border-border bg-card px-1 h-[34px]">
              {REFRESH_OPTIONS.map((opt) => (
                <button
                  key={opt.ms}
                  onClick={() => setRefreshMs(opt.ms)}
                  className={cn(
                    "px-2 py-1 rounded text-[11px] font-medium transition-colors",
                    refreshMs === opt.ms ? "bg-primary/10 text-primary" : "text-muted-foreground hover:text-foreground"
                  )}
                >
                  {opt.label}
                </button>
              ))}
            </div>
            <DateRangeFilter activeHours={hours} onPreset={setHours} />
          </div>
        </div>

        <SessionFilters
          search={search}           onSearch={setSearch}
          statusFilter={statusFilter} onStatus={setStatusFilter}
          agentFilter={agentFilter}   onAgent={setAgentFilter}
          healthTagFilter={healthTagFilter} onHealthTag={setHealthTag}
          agentNames={agentNames}
          countAll={countAll} countClean={countClean} countFailed={countFailed}
        />
      </div>

      {/* Session table */}
      <div
        className="rounded-xl border overflow-auto min-h-0"
        style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))", flex: "0 1 auto" }}
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
            <div className="w-14 h-14 rounded-2xl flex items-center justify-center mx-auto mb-4" style={{ background: "hsl(var(--muted))" }}>
              <GitBranch size={22} className="text-muted-foreground" />
            </div>
            <p className="text-sm font-semibold text-foreground mb-1">
              {sessions && sessions.length > 0 ? "No sessions match your filters" : "No sessions yet"}
            </p>
            <p className="text-xs text-muted-foreground">
              {sessions && sessions.length > 0
                ? "Try adjusting the search or filter criteria"
                : "Sessions require ClickHouse + SDK instrumentation. Run docker compose up, then instrument your agents."}
            </p>
          </div>
        ) : (
          <>
            <table className="w-full" style={{ minWidth: 1200 }}>
              <thead>
                <tr className="sticky top-0 z-10" style={{ borderBottom: "1px solid hsl(var(--border))", background: "hsl(var(--card-raised))" }}>
                  {COLUMNS.map((col) => (
                    <SortHeader
                      key={col.key} label={col.label} sortKey={col.key}
                      currentKey={sortKey} currentDir={sortDir} align={col.align}
                      onSort={handleSort}
                    />
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y" style={{ borderColor: "hsl(var(--border))" }}>
                {paginated.map((s) => (
                  <SessionRow key={`${s.session_id}-${s.agent_name}`} session={s} />
                ))}
              </tbody>
            </table>

            <SessionPagination
              page={page} totalPages={totalPages}
              totalItems={filtered.length} pageSize={PAGE_SIZE}
              onPage={setPage}
            />
          </>
        )}
      </div>
    </div>
  );
}
