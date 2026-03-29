"use client";

export const dynamic = "force-dynamic";

import { useState, useEffect, useMemo, useCallback, useRef } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import useSWR from "swr";
import {
  ChevronRight, GitBranch, Clock, Zap, AlertCircle,
  Search, Filter, ChevronLeft, ChevronsLeft, ChevronsRight,
  ArrowUp, ArrowDown, ArrowUpDown,
} from "lucide-react";
import { fetcher } from "@/lib/api";
import { useProject } from "@/lib/project-context";
import { cn, formatDuration, formatExact } from "@/lib/utils";
import { Timestamp } from "@/components/timestamp";
import { DateRangeFilter } from "@/components/date-range-filter";
import type { AgentSession, HealthTag } from "@/lib/types";
import { HealthTagBadge } from "@/components/health-tag-badge";

const PAGE_SIZE = 20;

/* ── Sortable column header ───────────────────────────────── */
type SortDir = "asc" | "desc" | null;
type SortKey =
  | "session_id"
  | "agent_name"
  | "health_tag"
  | "tool_calls"
  | "failed_calls"
  | "duration_ms"
  | "tokens"
  | "est_cost_usd"
  | "servers_used"
  | "first_call_at"
  | "timestamp";

function SortHeader({
  label,
  sortKey,
  currentKey,
  currentDir,
  align,
  onSort,
}: {
  label: string;
  sortKey: SortKey;
  currentKey: SortKey | null;
  currentDir: SortDir;
  align: string;
  onSort: (key: SortKey) => void;
}) {
  const isActive = currentKey === sortKey;
  return (
    <th
      className={cn(
        "px-4 py-2.5 text-[11px] font-semibold text-muted-foreground uppercase tracking-wide whitespace-nowrap cursor-pointer select-none hover:text-foreground transition-colors",
        align
      )}
      onClick={() => onSort(sortKey)}
    >
      <span className="inline-flex items-center gap-1">
        {label}
        {isActive && currentDir === "asc" ? (
          <ArrowUp size={10} className="text-primary" />
        ) : isActive && currentDir === "desc" ? (
          <ArrowDown size={10} className="text-primary" />
        ) : (
          <ArrowUpDown size={10} className="opacity-30" />
        )}
      </span>
    </th>
  );
}

/* ── Compute fallback health tag ─────────────────────────── */
function effectiveHealthTag(s: AgentSession): HealthTag | null {
  if (s.health_tag) return s.health_tag;
  if (s.failed_calls > 0) return "tool_failure";
  if (s.tool_calls > 0) return "success";
  return null;
}

/* ── Page ───────────────────────────────────────────────────── */
export default function SessionsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  // Prevent parent <main> from scrolling — this page manages its own scroll
  const pageRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const main = pageRef.current?.closest("main");
    if (main) {
      main.style.overflow = "hidden";
      return () => { main.style.overflow = ""; };
    }
  }, []);

  // Initialise filter state from URL search params so filters survive refresh
  const [hours, setHours] = useState<number>(() => {
    const v = searchParams.get("hours");
    const n = v ? Number(v) : 24;
    return Number.isFinite(n) && n > 0 ? Math.min(Math.floor(n), 8760) : 24;
  });
  const [search, setSearch] = useState(() => searchParams.get("q") ?? "");
  const [statusFilter, setStatusFilter] = useState<"all" | "clean" | "failed">(() => {
    const v = searchParams.get("status");
    return (v === "clean" || v === "failed") ? v : "all";
  });
  const [agentFilter, setAgentFilter] = useState<string>(() => searchParams.get("agent") ?? "all");
  const [healthTagFilter, setHealthTagFilter] = useState<string>(() => searchParams.get("tag") ?? "all");
  const [page, setPage] = useState<number>(() => {
    const v = searchParams.get("page");
    const n = v ? Number(v) : 0;
    return Number.isFinite(n) && n >= 0 ? Math.floor(n) : 0;
  });
  const [sortKey, setSortKey] = useState<SortKey | null>(() => {
    const v = searchParams.get("sort");
    return (v as SortKey | null) ?? "first_call_at";
  });
  const [sortDir, setSortDir] = useState<SortDir>(() => {
    const v = searchParams.get("dir");
    return (v === "asc" || v === "desc") ? v : "desc";
  });

  // Sync filter state → URL (replaces history entry so back-button works correctly)
  useEffect(() => {
    const params = new URLSearchParams();
    if (hours !== 24) params.set("hours", String(hours));
    if (search) params.set("q", search);
    if (statusFilter !== "all") params.set("status", statusFilter);
    if (agentFilter !== "all") params.set("agent", agentFilter);
    if (healthTagFilter !== "all") params.set("tag", healthTagFilter);
    if (page !== 0) params.set("page", String(page));
    if (sortKey && sortKey !== "first_call_at") params.set("sort", sortKey);
    if (sortDir && sortDir !== "desc") params.set("dir", sortDir);
    const qs = params.toString();
    router.replace(qs ? `/sessions?${qs}` : "/sessions", { scroll: false });
  }, [hours, search, statusFilter, agentFilter, healthTagFilter, page, sortKey, sortDir, router]);

  const { activeProject } = useProject();
  const p = activeProject ? `&project_id=${activeProject.id}` : "";

  const { data: sessions, isLoading, error } = useSWR<AgentSession[]>(
    `/api/agents/sessions?hours=${hours}&limit=500${p}`,
    fetcher,
    { refreshInterval: 30_000 }
  );

  // Reset to page 0 when filters change (but not on initial mount)
  const isFirstRender = useRef(true);
  useEffect(() => {
    if (isFirstRender.current) { isFirstRender.current = false; return; }
    setPage(0);
  }, [search, statusFilter, agentFilter, healthTagFilter, hours]);

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

  const filtered = useMemo(() => {
    if (!sessions) return [];
    let list = sessions.filter((s) => {
      if (statusFilter === "clean" && s.failed_calls > 0) return false;
      if (statusFilter === "failed" && s.failed_calls === 0) return false;
      if (agentFilter !== "all" && (s.agent_name ?? "unknown") !== agentFilter) return false;
      if (healthTagFilter !== "all" && (effectiveHealthTag(s) ?? "") !== healthTagFilter) return false;
      if (search) {
        const q = search.toLowerCase();
        if (
          !s.session_id.toLowerCase().includes(q) &&
          !(s.agent_name ?? "").toLowerCase().includes(q) &&
          !s.servers_used?.some((srv) => srv.toLowerCase().includes(q))
        ) return false;
      }
      return true;
    });

    // Sort
    if (sortKey && sortDir) {
      list = [...list].sort((a, b) => {
        let va: number | string = 0;
        let vb: number | string = 0;
        switch (sortKey) {
          case "session_id":    va = a.session_id; vb = b.session_id; break;
          case "agent_name":    va = a.agent_name ?? ""; vb = b.agent_name ?? ""; break;
          case "health_tag":    va = effectiveHealthTag(a) ?? ""; vb = effectiveHealthTag(b) ?? ""; break;
          case "tool_calls":    va = a.tool_calls; vb = b.tool_calls; break;
          case "failed_calls":  va = a.failed_calls; vb = b.failed_calls; break;
          case "duration_ms":   va = a.duration_ms; vb = b.duration_ms; break;
          case "tokens":        va = (a.total_input_tokens ?? 0) + (a.total_output_tokens ?? 0); vb = (b.total_input_tokens ?? 0) + (b.total_output_tokens ?? 0); break;
          case "est_cost_usd":  va = a.est_cost_usd ?? 0; vb = b.est_cost_usd ?? 0; break;
          case "servers_used":  va = (a.servers_used || []).length; vb = (b.servers_used || []).length; break;
          case "first_call_at": va = a.first_call_at; vb = b.first_call_at; break;
          case "timestamp":     va = a.first_call_at; vb = b.first_call_at; break;
        }
        if (typeof va === "string" && typeof vb === "string") {
          return sortDir === "asc" ? va.localeCompare(vb) : vb.localeCompare(va);
        }
        return sortDir === "asc" ? (va as number) - (vb as number) : (vb as number) - (va as number);
      });
    }
    return list;
  }, [sessions, statusFilter, agentFilter, healthTagFilter, search, sortKey, sortDir]);

  const countAll    = sessions?.length ?? 0;
  const countClean  = sessions?.filter((s) => s.failed_calls === 0).length ?? 0;
  const countFailed = sessions?.filter((s) => s.failed_calls > 0).length ?? 0;
  const totalPages  = Math.ceil(filtered.length / PAGE_SIZE);
  const paginated   = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const totalCalls  = filtered.reduce((n, s) => n + s.tool_calls, 0);
  const totalFailed = filtered.reduce((n, s) => n + s.failed_calls, 0);

  const columns: { label: string; key: SortKey; align: string }[] = [
    { label: "Session ID", key: "session_id", align: "text-left" },
    { label: "Agent", key: "agent_name", align: "text-left" },
    { label: "Health", key: "health_tag", align: "text-left" },
    { label: "Calls", key: "tool_calls", align: "text-right" },
    { label: "Failed", key: "failed_calls", align: "text-right" },
    { label: "Duration", key: "duration_ms", align: "text-right" },
    { label: "Tokens", key: "tokens", align: "text-right" },
    { label: "Cost", key: "est_cost_usd", align: "text-right" },
    { label: "Servers", key: "servers_used", align: "text-left" },
    { label: "Started", key: "first_call_at", align: "text-left" },
    { label: "Timestamp", key: "timestamp", align: "text-left" },
  ];

  return (
    <div ref={pageRef} className="page-in flex flex-col" style={{ maxHeight: "calc(100dvh - 92px)" }}>
      {/* ── Header ────────────────────────────────────────────── */}
      <div className="flex-shrink-0 px-0 pb-3">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold text-foreground">Sessions</h1>
            <p className="text-sm text-muted-foreground mt-0.5">
              {filtered.length} sessions · {totalCalls} tool calls
              {totalFailed > 0 && <span style={{ color: "hsl(var(--danger))" }}> · {totalFailed} failures</span>}
            </p>
          </div>
          <DateRangeFilter
            activeHours={hours}
            onPreset={(h) => setHours(h)}
          />
        </div>

        {/* ── Filters ───────────────────────────────────────────── */}
        <div className="flex flex-wrap items-center gap-2.5 mt-3">
          <div className="relative flex-1 min-w-[180px] max-w-sm">
            <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              type="search"
              aria-label="Search sessions"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search session ID, agent, server..."
              className="input-base pl-8 h-[34px] text-[13px]"
            />
          </div>

          <div className="flex items-center gap-1.5" role="group" aria-label="Session status filter">
            {(
              [
                ["all", "All", countAll],
                ["clean", "Clean", countClean],
                ["failed", "Failed", countFailed],
              ] as const
            ).map(([key, label, count]) => (
              <button
                key={key}
                aria-pressed={statusFilter === key}
                onClick={() => setStatusFilter(key)}
                className={cn(
                  "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-all",
                  statusFilter === key
                    ? "bg-primary/10 border-primary/30 text-primary"
                    : "bg-card border-border text-muted-foreground hover:bg-accent hover:text-foreground"
                )}
              >
                {label}
                <span
                  className={cn(
                    "text-[10px] px-1.5 py-0.5 rounded-full min-w-[18px] text-center tabular-nums",
                    statusFilter === key ? "bg-primary/15 text-primary" : "bg-muted text-muted-foreground"
                  )}
                  aria-label={`${count} sessions`}
                >
                  {count}
                </span>
              </button>
            ))}
          </div>

          {agentNames.length > 1 && (
            <div className="flex items-center gap-1.5">
              <Filter size={13} className="text-muted-foreground" aria-hidden="true" />
              <label htmlFor="agent-filter" className="sr-only">Filter by agent</label>
              <select
                id="agent-filter"
                value={agentFilter}
                onChange={(e) => setAgentFilter(e.target.value)}
                className="text-xs rounded-lg px-2 py-1.5 border border-border bg-card text-foreground outline-none h-[34px]"
              >
                <option value="all">All agents</option>
                {agentNames.map((name) => (
                  <option key={name} value={name}>{name}</option>
                ))}
              </select>
            </div>
          )}

          <div className="flex items-center gap-1.5">
            <label htmlFor="health-tag-filter" className="sr-only">Filter by health tag</label>
            <select
              id="health-tag-filter"
              value={healthTagFilter}
              onChange={(e) => setHealthTagFilter(e.target.value)}
              className="text-xs rounded-lg px-2 py-1.5 border border-border bg-card text-foreground outline-none h-[34px]"
            >
              <option value="all">All health tags</option>
              <option value="success">Success</option>
              <option value="success_with_fallback">Fallback</option>
              <option value="loop_detected">Loop</option>
              <option value="budget_exceeded">Budget</option>
              <option value="tool_failure">Failure</option>
              <option value="circuit_breaker_open">Circuit Open</option>
              <option value="timeout">Timeout</option>
              <option value="schema_drift">Schema Drift</option>
            </select>
          </div>
        </div>
      </div>

      {/* ── Session list (full width, horizontally scrollable) ── */}
      <div
        className="rounded-xl border overflow-auto min-h-0"
        style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))", flex: "0 1 auto" }}
      >
        <div>
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
              <div
                className="w-14 h-14 rounded-2xl flex items-center justify-center mx-auto mb-4"
                style={{ background: "hsl(var(--muted))" }}
              >
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
                  <tr
                    className="sticky top-0 z-10"
                    style={{
                      borderBottom: "1px solid hsl(var(--border))",
                      background: "hsl(var(--card-raised))",
                    }}
                  >
                    {columns.map((col) => (
                      <SortHeader
                        key={col.key}
                        label={col.label}
                        sortKey={col.key}
                        currentKey={sortKey}
                        currentDir={sortDir}
                        align={col.align}
                        onSort={handleSort}
                      />
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y" style={{ borderColor: "hsl(var(--border))" }}>
                  {paginated.map((s) => (
                    <tr
                      key={`${s.session_id}-${s.agent_name}`}
                      onClick={() => router.push(`/sessions/${s.session_id}`)}
                      className="cursor-pointer transition-colors text-sm group hover:bg-accent/40 border-l-[3px] border-l-transparent"
                    >
                      <td className="px-4 py-3 whitespace-nowrap">
                        <div className="flex items-center gap-2">
                          <ChevronRight size={12} className="text-muted-foreground group-hover:text-primary transition-colors w-4 flex-shrink-0" />
                          <span
                            className="text-[12px] font-mono text-foreground"
                            style={{ fontFamily: "var(--font-geist-mono)" }}
                          >
                            {s.session_id}
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-[12px] text-muted-foreground whitespace-nowrap">
                        {s.agent_name || "—"}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        <HealthTagBadge tag={effectiveHealthTag(s)} />
                      </td>
                      <td className="px-4 py-3 text-[12px] text-right whitespace-nowrap">
                        <span className="flex items-center justify-end gap-1 text-muted-foreground">
                          <Zap size={10} />
                          {s.tool_calls}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-[12px] text-right whitespace-nowrap">
                        {s.failed_calls > 0 ? (
                          <span className="font-semibold" style={{ color: "hsl(var(--danger))" }}>
                            {s.failed_calls}
                          </span>
                        ) : (
                          <span className="text-muted-foreground">0</span>
                        )}
                      </td>
                      <td
                        className="px-4 py-3 text-[12px] text-right text-muted-foreground whitespace-nowrap"
                        style={{ fontFamily: "var(--font-geist-mono)" }}
                      >
                        {formatDuration(s.duration_ms)}
                      </td>
                      <td className="px-4 py-3 text-[11px] text-right text-muted-foreground whitespace-nowrap" style={{ fontFamily: "var(--font-geist-mono)" }}>
                        {(s.total_input_tokens || s.total_output_tokens) ? (
                          <span>
                            ↑{(s.total_input_tokens ?? 0).toLocaleString()} ↓{(s.total_output_tokens ?? 0).toLocaleString()}
                          </span>
                        ) : "—"}
                      </td>
                      <td className="px-4 py-3 text-[11px] text-right whitespace-nowrap" style={{ fontFamily: "var(--font-geist-mono)" }}>
                        {s.est_cost_usd != null ? (
                          <span style={{ color: "hsl(var(--foreground))" }}>
                            ${s.est_cost_usd < 0.01 ? s.est_cost_usd.toFixed(4) : s.est_cost_usd.toFixed(2)}
                          </span>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        <div className="flex flex-nowrap gap-1">
                          {(s.servers_used || []).slice(0, 2).map((srv) => (
                            <span
                              key={srv}
                              className="px-1.5 py-0.5 rounded text-[10px]"
                              style={{
                                background: "hsl(var(--muted))",
                                border: "1px solid hsl(var(--border))",
                                color: "hsl(var(--muted-foreground))",
                                fontFamily: "var(--font-geist-mono)",
                              }}
                            >
                              {srv}
                            </span>
                          ))}
                          {(s.servers_used?.length ?? 0) > 2 && (
                            <span className="text-[10px] text-muted-foreground">
                              +{s.servers_used.length - 2}
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-[12px] text-muted-foreground whitespace-nowrap">
                        <div className="flex items-center gap-1">
                          <Clock size={11} />
                          <Timestamp iso={s.first_call_at} compact />
                        </div>
                      </td>
                      <td className="px-4 py-3 text-[11px] text-muted-foreground tabular-nums whitespace-nowrap" style={{ fontFamily: "var(--font-geist-mono)", opacity: 0.7 }}>
                        {formatExact(s.first_call_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {/* Pagination */}
              {filtered.length > 0 && (
                <div className="flex items-center justify-between px-4 py-2 border-t text-[10px] text-muted-foreground" style={{ borderColor: "hsl(var(--border))" }}>
                  <span>
                    {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, filtered.length)} of {filtered.length}
                  </span>
                  <div className="flex items-center gap-px">
                    <button onClick={() => setPage(0)} disabled={page === 0} className="p-1 rounded hover:bg-accent disabled:opacity-30 transition-colors"><ChevronsLeft size={10} /></button>
                    <button onClick={() => setPage((p) => Math.max(0, p - 1))} disabled={page === 0} className="p-1 rounded hover:bg-accent disabled:opacity-30 transition-colors"><ChevronLeft size={10} /></button>
                    {(() => {
                      const pages: (number | "...")[] = [];
                      if (totalPages <= 7) {
                        for (let i = 0; i < totalPages; i++) pages.push(i);
                      } else {
                        pages.push(0);
                        if (page > 2) pages.push("...");
                        for (let i = Math.max(1, page - 1); i <= Math.min(totalPages - 2, page + 1); i++) pages.push(i);
                        if (page < totalPages - 3) pages.push("...");
                        pages.push(totalPages - 1);
                      }
                      return pages.map((p, idx) =>
                        p === "..." ? (
                          <span key={`ellipsis-${idx}`} className="px-1 text-muted-foreground">…</span>
                        ) : (
                          <button key={p} onClick={() => setPage(p)} className={cn("min-w-[20px] h-[20px] rounded text-[9px] font-medium tabular-nums transition-colors", page === p ? "bg-primary text-primary-foreground" : "hover:bg-accent text-muted-foreground")}>{p + 1}</button>
                        )
                      );
                    })()}
                    <button onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))} disabled={page >= totalPages - 1} className="p-1 rounded hover:bg-accent disabled:opacity-30 transition-colors"><ChevronRight size={10} /></button>
                    <button onClick={() => setPage(totalPages - 1)} disabled={page >= totalPages - 1} className="p-1 rounded hover:bg-accent disabled:opacity-30 transition-colors"><ChevronsRight size={10} /></button>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
