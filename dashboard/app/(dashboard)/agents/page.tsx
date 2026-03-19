"use client";

export const dynamic = "force-dynamic";

import { useMemo, useState } from "react";
import useSWR from "swr";
import {
  Bot, ChevronRight, GitBranch, Layers3, Wallet, Wrench,
  Search, AlertTriangle, CheckCircle, Clock, TrendingUp,
} from "lucide-react";
import { fetcher, getCostsBreakdown } from "@/lib/api";
import { cn, formatDuration, timeAgo } from "@/lib/utils";
import type { AgentSession, CostsBreakdownResponse } from "@/lib/types";

/* ── Types ──────────────────────────────────────────────────── */
type AgentSummary = {
  agent_name: string;
  sessions: number;
  tool_calls: number;
  failed_calls: number;
  total_duration_ms: number;
  avg_duration_ms: number;
  total_cost_usd: number;
  servers_used: string[];
  latest_started_at: string;
  session_ids: string[];
  error_rate: number;
};

/* ── Helpers ────────────────────────────────────────────────── */
function formatUsd(v: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency", currency: "USD",
    minimumFractionDigits: 2, maximumFractionDigits: 4,
  }).format(v);
}

function Skeleton({ className }: { className?: string }) {
  return <div className={cn("skeleton", className)} />;
}

function aggregateAgents(
  sessions: AgentSession[],
  costs: CostsBreakdownResponse | undefined
): AgentSummary[] {
  const costByAgent = new Map(
    (costs?.by_agent ?? []).map((e) => [e.agent_name, e.total_cost_usd])
  );
  const summaries = new Map<string, AgentSummary>();

  for (const session of sessions) {
    const name = session.agent_name ?? "unknown agent";
    const existing = summaries.get(name);
    const servers = new Set(existing?.servers_used ?? []);
    for (const s of session.servers_used ?? []) servers.add(s);

    const next: AgentSummary = existing ?? {
      agent_name: name, sessions: 0, tool_calls: 0, failed_calls: 0,
      total_duration_ms: 0, avg_duration_ms: 0,
      total_cost_usd: costByAgent.get(name) ?? 0,
      servers_used: [], latest_started_at: session.first_call_at,
      session_ids: [], error_rate: 0,
    };
    next.sessions += 1;
    next.tool_calls += session.tool_calls;
    next.failed_calls += session.failed_calls;
    next.total_duration_ms += session.duration_ms;
    next.avg_duration_ms = next.total_duration_ms / next.sessions;
    next.error_rate = next.tool_calls > 0 ? next.failed_calls / next.tool_calls : 0;
    next.latest_started_at =
      new Date(session.first_call_at) > new Date(next.latest_started_at)
        ? session.first_call_at : next.latest_started_at;
    next.session_ids = [...next.session_ids, session.session_id];
    next.servers_used = Array.from(servers).sort();
    next.total_cost_usd = costByAgent.get(name) ?? next.total_cost_usd;
    summaries.set(name, next);
  }

  return Array.from(summaries.values()).sort((a, b) => {
    if (b.failed_calls !== a.failed_calls) return b.failed_calls - a.failed_calls;
    return b.tool_calls - a.tool_calls;
  });
}

/* ── Stat tile ──────────────────────────────────────────────── */
function StatTile({
  icon: Icon, label, value, sub, danger,
}: {
  icon: React.ComponentType<{ size?: number; className?: string }>;
  label: string; value: string; sub?: string; danger?: boolean;
}) {
  return (
    <div
      className="rounded-lg p-3.5"
      style={{ background: "hsl(var(--card-raised))", border: "1px solid hsl(var(--border))" }}
    >
      <div className="flex items-center justify-between mb-2">
        <Icon
          size={14}
          className={danger ? "text-red-500" : "text-primary"}
        />
        <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">
          {label}
        </span>
      </div>
      <p className={cn("text-[15px] font-bold leading-none", danger ? "text-red-500" : "text-foreground")}>
        {value}
      </p>
      {sub && <p className="text-[10px] text-muted-foreground mt-1">{sub}</p>}
    </div>
  );
}

/* ── Agent row ──────────────────────────────────────────────── */
function AgentRow({
  agent, active, onClick,
}: {
  agent: AgentSummary; active: boolean; onClick: () => void;
}) {
  const failing = agent.failed_calls > 0;
  return (
    <button
      onClick={onClick}
      className={cn(
        "w-full text-left px-5 py-4 transition-all border-b border-border/50 last:border-0",
        active
          ? "bg-primary/5 border-l-2 border-l-primary"
          : "hover:bg-accent/40 border-l-2 border-l-transparent"
      )}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1.5">
            <div
              className="w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0"
              style={{
                background: failing
                  ? "hsl(var(--danger-bg))"
                  : "hsl(var(--success-bg))",
              }}
            >
              <Bot
                size={12}
                style={{ color: failing ? "hsl(var(--danger))" : "hsl(var(--success))" }}
              />
            </div>
            <span className="text-[13px] font-semibold text-foreground truncate">
              {agent.agent_name}
            </span>
            {failing ? (
              <span className="flex items-center gap-1 text-[10px] font-semibold px-1.5 py-0.5 rounded-full badge-danger flex-shrink-0">
                <AlertTriangle size={9} />
                {agent.failed_calls} failed
              </span>
            ) : (
              <span className="flex items-center gap-1 text-[10px] font-semibold px-1.5 py-0.5 rounded-full badge-success flex-shrink-0">
                <CheckCircle size={9} />
                clean
              </span>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] text-muted-foreground">
            <span>{agent.sessions} sessions</span>
            <span>·</span>
            <span>{agent.tool_calls} calls</span>
            <span>·</span>
            <span>{formatDuration(agent.avg_duration_ms)} avg</span>
            <span>·</span>
            <span>{timeAgo(agent.latest_started_at)}</span>
          </div>
        </div>
        <div className="text-right flex-shrink-0">
          <p
            className="text-[12px] font-mono text-muted-foreground"
            style={{ fontFamily: "var(--font-geist-mono)" }}
          >
            {formatUsd(agent.total_cost_usd)}
          </p>
          <p className="text-[10px] text-muted-foreground mt-0.5">
            {(agent.error_rate * 100).toFixed(1)}% errors
          </p>
        </div>
      </div>
    </button>
  );
}

/* ── Page ───────────────────────────────────────────────────── */
export default function AgentsPage() {
  const [hours, setHours] = useState(24);
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "healthy" | "failing">("all");

  const { data: sessions, isLoading, error } = useSWR<AgentSession[]>(
    `/api/agents/sessions?hours=${hours}&limit=500`,
    fetcher,
    { refreshInterval: 30_000 }
  );
  const { data: costs } = useSWR<CostsBreakdownResponse>(
    `/api/costs/breakdown?hours=${hours}`,
    () => getCostsBreakdown(hours),
    { refreshInterval: 30_000 }
  );

  const agents = useMemo(
    () => aggregateAgents(sessions ?? [], costs),
    [sessions, costs]
  );

  const filtered = useMemo(() => {
    return agents.filter((a) => {
      if (search && !a.agent_name.toLowerCase().includes(search.toLowerCase())) return false;
      if (statusFilter === "healthy" && a.failed_calls > 0) return false;
      if (statusFilter === "failing" && a.failed_calls === 0) return false;
      return true;
    });
  }, [agents, search, statusFilter]);

  const selected =
    filtered.find((a) => a.agent_name === selectedAgent) ?? filtered[0] ?? null;
  const selectedSessions = (sessions ?? []).filter(
    (s) => s.agent_name === selected?.agent_name
  );

  const TIME_OPTIONS = [[1,"1h"],[6,"6h"],[24,"24h"],[168,"7d"]] as const;

  return (
    <div className="space-y-5 page-in">
      {/* ── Header ────────────────────────────────────────────── */}
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-foreground">Agents</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            {agents.length} agents · {agents.reduce((n, a) => n + a.sessions, 0)} sessions
            in the last {hours >= 168 ? "7d" : `${hours}h`}
          </p>
        </div>
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

      {/* ── Filters ───────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-2.5">
        <div className="relative flex-1 min-w-[180px] max-w-xs">
          <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search agents…"
            className="input-base pl-8 h-[34px] text-[13px]"
          />
        </div>
        <div className="flex items-center gap-1.5">
          {(
            [
              ["all", "All", agents.length],
              ["healthy", "Healthy", agents.filter((a) => a.failed_calls === 0).length],
              ["failing", "Failing", agents.filter((a) => a.failed_calls > 0).length],
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
                  statusFilter === key
                    ? "bg-primary/15 text-primary"
                    : "bg-muted text-muted-foreground"
                )}
              >
                {count}
              </span>
            </button>
          ))}
        </div>
      </div>

      {/* ── Content ───────────────────────────────────────────── */}
      {isLoading ? (
        <div className="grid lg:grid-cols-5 gap-4">
          <div
            className="lg:col-span-3 rounded-xl border p-5 space-y-3"
            style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
          >
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-16 rounded-xl" />
            ))}
          </div>
          <div
            className="lg:col-span-2 rounded-xl border p-5 space-y-3"
            style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
          >
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-4 rounded" />
            ))}
          </div>
        </div>
      ) : error ? (
        <div
          className="rounded-xl border p-12 text-center"
          style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
        >
          <div
            className="w-14 h-14 rounded-2xl flex items-center justify-center mx-auto mb-4"
            style={{ background: "hsl(var(--muted))" }}
          >
            <Bot size={22} className="text-muted-foreground" />
          </div>
          <p className="text-sm font-semibold text-foreground mb-1">
            Could not load agent activity
          </p>
          <p className="text-xs text-muted-foreground">
            Agent views require ClickHouse-backed session traces.
          </p>
        </div>
      ) : filtered.length === 0 ? (
        <div
          className="rounded-xl border p-12 text-center"
          style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
        >
          <div
            className="w-14 h-14 rounded-2xl flex items-center justify-center mx-auto mb-4"
            style={{ background: "hsl(var(--muted))" }}
          >
            <Bot size={22} className="text-muted-foreground" />
          </div>
          <p className="text-sm font-semibold text-foreground mb-1">
            {agents.length > 0 ? "No agents match your filters" : "No agents observed yet"}
          </p>
          <p className="text-xs text-muted-foreground">
            {agents.length > 0
              ? "Try adjusting search or status filter"
              : "Instrument your agent with the LangSight SDK to start seeing activity"}
          </p>
        </div>
      ) : (
        <div className="grid lg:grid-cols-5 gap-4">

          {/* Agent list */}
          <div
            className="lg:col-span-3 rounded-xl border overflow-hidden"
            style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
          >
            <div className="section-header">
              <div>
                <h2>Agent Fleet</h2>
                <p className="text-[11px] text-muted-foreground mt-0.5">
                  {filtered.length} agents · ranked by failures, then call volume
                </p>
              </div>
            </div>
            <div className="max-h-[560px] overflow-y-auto">
              {filtered.map((agent) => (
                <AgentRow
                  key={agent.agent_name}
                  agent={agent}
                  active={selected?.agent_name === agent.agent_name}
                  onClick={() => setSelectedAgent(agent.agent_name)}
                />
              ))}
            </div>
          </div>

          {/* Detail panel */}
          <div
            className="lg:col-span-2 rounded-xl border overflow-hidden"
            style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
          >
            {selected ? (
              <div>
                {/* Detail header */}
                <div className="section-header">
                  <div className="flex items-center gap-2 min-w-0">
                    <div
                      className="w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0"
                      style={{ background: "hsl(var(--primary) / 0.12)" }}
                    >
                      <Bot size={13} className="text-primary" />
                    </div>
                    <h2 className="truncate">{selected.agent_name}</h2>
                  </div>
                </div>

                <div className="p-4 space-y-4">
                  {/* Stats grid */}
                  <div className="grid grid-cols-2 gap-2">
                    <StatTile icon={GitBranch} label="Sessions" value={selected.sessions.toString()} />
                    <StatTile icon={Layers3} label="Tool Calls" value={selected.tool_calls.toString()} />
                    <StatTile icon={Wallet} label="Total Cost" value={formatUsd(selected.total_cost_usd)} />
                    <StatTile icon={Clock} label="Avg Runtime" value={formatDuration(selected.avg_duration_ms)} />
                    <StatTile
                      icon={AlertTriangle}
                      label="Failures"
                      value={selected.failed_calls.toString()}
                      sub={`${(selected.error_rate * 100).toFixed(1)}% error rate`}
                      danger={selected.failed_calls > 0}
                    />
                    <StatTile
                      icon={TrendingUp}
                      label="Error Rate"
                      value={`${(selected.error_rate * 100).toFixed(1)}%`}
                      danger={selected.error_rate > 0.05}
                    />
                  </div>

                  {/* Servers used */}
                  {selected.servers_used.length > 0 && (
                    <div>
                      <p className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wide mb-2">
                        Tools &amp; MCPs Used
                      </p>
                      <div className="flex flex-wrap gap-1.5">
                        {selected.servers_used.map((server) => (
                          <span
                            key={server}
                            className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-[11px] font-mono"
                            style={{
                              background: "hsl(var(--card-raised))",
                              border: "1px solid hsl(var(--border))",
                              color: "hsl(var(--muted-foreground))",
                              fontFamily: "var(--font-geist-mono)",
                            }}
                          >
                            <Wrench size={10} />
                            {server}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Recent sessions */}
                  <div>
                    <p className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wide mb-2">
                      Recent Sessions
                    </p>
                    <div className="space-y-1.5 max-h-[220px] overflow-y-auto">
                      {selectedSessions.slice(0, 10).map((session) => (
                        <div
                          key={session.session_id}
                          className="flex items-center justify-between rounded-lg px-3 py-2.5 gap-2 transition-colors"
                          style={{
                            background: "hsl(var(--card-raised))",
                            border: "1px solid hsl(var(--border))",
                          }}
                        >
                          <div className="min-w-0">
                            <span
                              className="text-[11px] font-mono text-foreground block truncate"
                              style={{ fontFamily: "var(--font-geist-mono)" }}
                            >
                              {session.session_id.slice(0, 20)}…
                            </span>
                            <span className="text-[10px] text-muted-foreground">
                              {session.tool_calls} calls · {formatDuration(session.duration_ms)} · {timeAgo(session.first_call_at)}
                            </span>
                          </div>
                          <div className="flex items-center gap-1.5 flex-shrink-0">
                            {session.failed_calls > 0 && (
                              <span className="text-[10px] font-semibold text-red-500">
                                {session.failed_calls}✗
                              </span>
                            )}
                            <ChevronRight size={12} className="text-muted-foreground" />
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center h-48 gap-2 text-muted-foreground">
                <Bot size={24} className="opacity-30" />
                <p className="text-sm">Select an agent to view details</p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
