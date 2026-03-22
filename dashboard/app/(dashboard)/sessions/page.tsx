"use client";

export const dynamic = "force-dynamic";

import { useState, useEffect, useMemo } from "react";
import { useRouter } from "next/navigation";
import useSWR from "swr";
import {
  ChevronRight, GitBranch, Clock, Zap, AlertCircle,
  Search, Filter, ChevronLeft, ChevronsLeft, ChevronsRight,
} from "lucide-react";
import { fetcher } from "@/lib/api";
import { useProject } from "@/lib/project-context";
import { cn, timeAgo, formatDuration } from "@/lib/utils";
import type { AgentSession, HealthTag } from "@/lib/types";
import { HealthTagBadge } from "@/components/health-tag-badge";

const PAGE_SIZE = 20;

/* ── Page ───────────────────────────────────────────────────── */
export default function SessionsPage() {
  const router = useRouter();
  const [hours, setHours] = useState(24);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "clean" | "failed">("all");
  const [agentFilter, setAgentFilter] = useState<string>("all");
  const [healthTagFilter, setHealthTagFilter] = useState<string>("all");
  const [page, setPage] = useState(0);

  const { activeProject } = useProject();
  const p = activeProject ? `&project_id=${activeProject.id}` : "";

  const { data: sessions, isLoading, error } = useSWR<AgentSession[]>(
    `/api/agents/sessions?hours=${hours}&limit=500${p}`,
    fetcher,
    { refreshInterval: 30_000 }
  );

  useEffect(() => { setPage(0); }, [search, statusFilter, agentFilter, healthTagFilter, hours]);

  const agentNames = useMemo(() => {
    if (!sessions) return [];
    return Array.from(new Set(sessions.map((s) => s.agent_name ?? "unknown"))).sort();
  }, [sessions]);

  const filtered = useMemo(() => {
    if (!sessions) return [];
    return sessions.filter((s) => {
      if (statusFilter === "clean" && s.failed_calls > 0) return false;
      if (statusFilter === "failed" && s.failed_calls === 0) return false;
      if (agentFilter !== "all" && (s.agent_name ?? "unknown") !== agentFilter) return false;
      if (healthTagFilter !== "all" && (s.health_tag ?? "") !== healthTagFilter) return false;
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
  }, [sessions, statusFilter, agentFilter, healthTagFilter, search]);

  const countAll    = sessions?.length ?? 0;
  const countClean  = sessions?.filter((s) => s.failed_calls === 0).length ?? 0;
  const countFailed = sessions?.filter((s) => s.failed_calls > 0).length ?? 0;
  const totalPages  = Math.ceil(filtered.length / PAGE_SIZE);
  const paginated   = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const totalCalls  = filtered.reduce((n, s) => n + s.tool_calls, 0);
  const totalFailed = filtered.reduce((n, s) => n + s.failed_calls, 0);

  const TIME_OPTIONS = [[1,"1h"],[6,"6h"],[24,"24h"],[168,"7d"]] as const;

  return (
    <div className="page-in flex flex-col" style={{ height: "calc(100vh - 4rem)" }}>
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
          <div className="flex items-center gap-2">
            <div
              className="flex rounded-lg border p-0.5"
              style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
            >
              {TIME_OPTIONS.map(([v, l]) => (
                <button
                  key={v}
                  onClick={() => setHours(v)}
                  className={cn(
                    "px-2.5 py-1.5 rounded-md text-xs font-medium transition-all",
                    hours === v
                      ? "bg-primary text-white shadow-sm"
                      : "text-muted-foreground hover:text-foreground"
                  )}
                >
                  {l}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* ── Filters ───────────────────────────────────────────── */}
        <div className="flex flex-wrap items-center gap-2.5 mt-3">
          <div className="relative flex-1 min-w-[180px] max-w-sm">
            <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search session ID, agent, server..."
              className="input-base pl-8 h-[34px] text-[13px]"
            />
          </div>

          <div className="flex items-center gap-1.5">
            {(
              [
                ["all", "All", countAll],
                ["clean", "Clean", countClean],
                ["failed", "Failed", countFailed],
              ] as const
            ).map(([key, label, count]) => (
              <button
                key={key}
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
                >
                  {count}
                </span>
              </button>
            ))}
          </div>

          {agentNames.length > 1 && (
            <div className="flex items-center gap-1.5">
              <Filter size={13} className="text-muted-foreground" />
              <select
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
            <select
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

      {/* ── Session list (full width) ────────────────────────── */}
      <div
        className="flex-1 rounded-xl border overflow-hidden flex flex-col min-h-0"
        style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
      >
        <div className="flex-1 overflow-y-auto">
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
                  : "Instrument your agents with the LangSight SDK to capture traces"}
              </p>
            </div>
          ) : (
            <>
              <table className="w-full">
                <thead>
                  <tr
                    className="sticky top-0 z-10"
                    style={{
                      borderBottom: "1px solid hsl(var(--border))",
                      background: "hsl(var(--card-raised))",
                    }}
                  >
                    {[
                      ["Session ID", "text-left"],
                      ["Agent", "text-left"],
                      ["Health", "text-left"],
                      ["Calls", "text-right"],
                      ["Failed", "text-right"],
                      ["Duration", "text-right"],
                      ["Servers", "text-left"],
                      ["Started", "text-left"],
                    ].map(([h, align]) => (
                      <th
                        key={h}
                        className={cn(
                          "px-4 py-2.5 text-[11px] font-semibold text-muted-foreground uppercase tracking-wide",
                          align
                        )}
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y" style={{ borderColor: "hsl(var(--border))" }}>
                  {paginated.map((s) => (
                    <tr
                      key={s.session_id}
                      onClick={() => router.push(`/sessions/${s.session_id}`)}
                      className="cursor-pointer transition-colors text-sm group hover:bg-accent/40 border-l-[3px] border-l-transparent"
                    >
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <ChevronRight size={12} className="text-muted-foreground group-hover:text-primary transition-colors w-4" />
                          <span
                            className="text-[12px] font-mono text-foreground"
                            style={{ fontFamily: "var(--font-geist-mono)" }}
                          >
                            {s.session_id.slice(0, 16)}...
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-[12px] text-muted-foreground">
                        {s.agent_name || "—"}
                      </td>
                      <td className="px-4 py-3">
                        <HealthTagBadge tag={s.health_tag} />
                      </td>
                      <td className="px-4 py-3 text-[12px] text-right">
                        <span className="flex items-center justify-end gap-1 text-muted-foreground">
                          <Zap size={10} />
                          {s.tool_calls}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-[12px] text-right">
                        {s.failed_calls > 0 ? (
                          <span className="font-semibold" style={{ color: "hsl(var(--danger))" }}>
                            {s.failed_calls}
                          </span>
                        ) : (
                          <span className="text-muted-foreground">0</span>
                        )}
                      </td>
                      <td
                        className="px-4 py-3 text-[12px] text-right text-muted-foreground"
                        style={{ fontFamily: "var(--font-geist-mono)" }}
                      >
                        {formatDuration(s.duration_ms)}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex flex-wrap gap-1">
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
                      <td className="px-4 py-3 text-[12px] text-muted-foreground">
                        <div className="flex items-center gap-1">
                          <Clock size={11} />
                          {timeAgo(s.first_call_at)}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {/* Pagination */}
              {totalPages > 1 && (
                <div
                  className="sticky bottom-0 flex items-center justify-between px-4 py-3 border-t text-xs text-muted-foreground"
                  style={{ borderColor: "hsl(var(--border))", background: "hsl(var(--card-raised))" }}
                >
                  <span>
                    {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, filtered.length)} of {filtered.length}
                  </span>
                  <div className="flex items-center gap-0.5">
                    <button
                      onClick={() => setPage(0)}
                      disabled={page === 0}
                      className="p-1.5 rounded hover:bg-accent disabled:opacity-30 transition-colors"
                    >
                      <ChevronsLeft size={13} />
                    </button>
                    <button
                      onClick={() => setPage((p) => Math.max(0, p - 1))}
                      disabled={page === 0}
                      className="p-1.5 rounded hover:bg-accent disabled:opacity-30 transition-colors"
                    >
                      <ChevronLeft size={13} />
                    </button>
                    <span className="px-2 tabular-nums">{page + 1} / {totalPages}</span>
                    <button
                      onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                      disabled={page >= totalPages - 1}
                      className="p-1.5 rounded hover:bg-accent disabled:opacity-30 transition-colors"
                    >
                      <ChevronRight size={13} />
                    </button>
                    <button
                      onClick={() => setPage(totalPages - 1)}
                      disabled={page >= totalPages - 1}
                      className="p-1.5 rounded hover:bg-accent disabled:opacity-30 transition-colors"
                    >
                      <ChevronsRight size={13} />
                    </button>
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
