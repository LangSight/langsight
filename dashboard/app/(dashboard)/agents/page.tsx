"use client";

export const dynamic = "force-dynamic";

import { useMemo, useState } from "react";
import useSWR from "swr";
import {
  Bot, ChevronRight, GitBranch, Layers3, Wallet, Wrench, Search,
  AlertTriangle, CheckCircle,
} from "lucide-react";
import { fetcher, getCostsBreakdown } from "@/lib/api";
import { cn, formatDuration, timeAgo } from "@/lib/utils";
import type { AgentSession, CostsBreakdownResponse } from "@/lib/types";

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

function formatUsd(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 4,
  }).format(value);
}

function aggregateAgents(sessions: AgentSession[], costs: CostsBreakdownResponse | undefined): AgentSummary[] {
  const costByAgent = new Map((costs?.by_agent ?? []).map(e => [e.agent_name, e.total_cost_usd]));
  const summaries = new Map<string, AgentSummary>();

  for (const session of sessions) {
    const agentName = session.agent_name ?? "unknown agent";
    const existing = summaries.get(agentName);
    const servers = new Set(existing?.servers_used ?? []);
    for (const server of session.servers_used ?? []) servers.add(server);

    const next: AgentSummary = existing ?? {
      agent_name: agentName, sessions: 0, tool_calls: 0, failed_calls: 0,
      total_duration_ms: 0, avg_duration_ms: 0, total_cost_usd: costByAgent.get(agentName) ?? 0,
      servers_used: [], latest_started_at: session.first_call_at, session_ids: [], error_rate: 0,
    };

    next.sessions += 1;
    next.tool_calls += session.tool_calls;
    next.failed_calls += session.failed_calls;
    next.total_duration_ms += session.duration_ms;
    next.avg_duration_ms = next.total_duration_ms / next.sessions;
    next.error_rate = next.tool_calls > 0 ? next.failed_calls / next.tool_calls : 0;
    next.latest_started_at = new Date(session.first_call_at) > new Date(next.latest_started_at)
      ? session.first_call_at : next.latest_started_at;
    next.session_ids = [...next.session_ids, session.session_id];
    next.servers_used = Array.from(servers).sort();
    next.total_cost_usd = costByAgent.get(agentName) ?? next.total_cost_usd;

    summaries.set(agentName, next);
  }

  return Array.from(summaries.values()).sort((a, b) => {
    if (b.failed_calls !== a.failed_calls) return b.failed_calls - a.failed_calls;
    return b.tool_calls - a.tool_calls;
  });
}

function StatCard({ icon: Icon, label, value, sub, alert }: {
  icon: React.ComponentType<{ size?: number; className?: string }>;
  label: string; value: string; sub?: string; alert?: boolean;
}) {
  return (
    <div className="rounded-lg border border-border p-3 bg-muted/30">
      <div className="flex items-center justify-between mb-2">
        <Icon size={14} className={alert ? "text-red-500" : "text-primary"} />
        <span className="text-[11px] text-muted-foreground">{label}</span>
      </div>
      <p className={cn("text-sm font-semibold", alert ? "text-red-500" : "text-foreground")}>{value}</p>
      {sub && <p className="text-[10px] text-muted-foreground mt-0.5">{sub}</p>}
    </div>
  );
}

export default function AgentsPage() {
  const [hours, setHours] = useState(24);
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "healthy" | "failing">("all");

  const { data: sessions, isLoading, error: sessionsError } = useSWR<AgentSession[]>(
    `/api/agents/sessions?hours=${hours}&limit=500`, fetcher, { refreshInterval: 30_000 },
  );
  const { data: costs } = useSWR<CostsBreakdownResponse>(
    `/api/costs/breakdown?hours=${hours}`, () => getCostsBreakdown(hours), { refreshInterval: 30_000 },
  );

  const agents = useMemo(() => aggregateAgents(sessions ?? [], costs), [sessions, costs]);

  const filtered = useMemo(() => {
    return agents.filter(a => {
      if (search && !a.agent_name.toLowerCase().includes(search.toLowerCase())) return false;
      if (statusFilter === "healthy" && a.failed_calls > 0) return false;
      if (statusFilter === "failing" && a.failed_calls === 0) return false;
      return true;
    });
  }, [agents, search, statusFilter]);

  const selected = filtered.find(a => a.agent_name === selectedAgent) ?? filtered[0] ?? null;
  const selectedSessions = (sessions ?? []).filter(s => s.agent_name === selected?.agent_name);

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-foreground">Agents</h1>
          <p className="text-sm text-muted-foreground">
            {agents.length} agents · {agents.reduce((n, a) => n + a.sessions, 0)} sessions in the last {hours}h
          </p>
        </div>
        <select value={hours} onChange={e => setHours(Number(e.target.value))}
          className="text-sm rounded-lg px-3 py-2 border border-border outline-none bg-card text-foreground">
          {[[1,"1h"],[6,"6h"],[24,"24h"],[168,"7d"]].map(([v, l]) => (
            <option key={v} value={v}>{l}</option>
          ))}
        </select>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[200px] max-w-sm">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text" value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Search agents…"
            className="w-full pl-9 pr-3 py-2 rounded-lg border border-border bg-card text-sm text-foreground placeholder:text-muted-foreground outline-none focus:ring-1 focus:ring-primary/30"
          />
        </div>
        <div className="flex items-center gap-1.5">
          {([["all", "All", agents.length], ["healthy", "Healthy", agents.filter(a => a.failed_calls === 0).length], ["failing", "Failing", agents.filter(a => a.failed_calls > 0).length]] as const).map(([key, label, count]) => (
            <button key={key} onClick={() => setStatusFilter(key)}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors",
                statusFilter === key
                  ? "bg-primary/10 border-primary/30 text-primary"
                  : "bg-card border-border text-muted-foreground hover:bg-accent"
              )}>
              {label}
              <span className={cn("text-[10px] px-1.5 py-0.5 rounded-full min-w-[18px] text-center",
                statusFilter === key ? "bg-primary/20 text-primary" : "bg-muted text-muted-foreground")}>{count}</span>
            </button>
          ))}
        </div>
      </div>

      {isLoading ? (
        <div className="grid lg:grid-cols-5 gap-4">
          <div className="lg:col-span-3 rounded-xl border border-border p-6 bg-card space-y-3">
            {Array.from({ length: 5 }).map((_, i) => <div key={i} className="skeleton h-14 rounded-lg" />)}
          </div>
          <div className="lg:col-span-2 rounded-xl border border-border p-6 bg-card space-y-3">
            {Array.from({ length: 6 }).map((_, i) => <div key={i} className="skeleton h-4 rounded" />)}
          </div>
        </div>
      ) : sessionsError ? (
        <div className="rounded-xl border border-border p-12 text-center bg-card">
          <Bot size={40} className="mx-auto mb-4 opacity-20" />
          <p className="font-medium mb-1 text-foreground">Could not load agent activity</p>
          <p className="text-sm text-muted-foreground">Agent views depend on session traces stored in ClickHouse.</p>
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-xl border border-border p-12 text-center bg-card">
          <Bot size={40} className="mx-auto mb-4 opacity-20" />
          <p className="font-medium mb-1 text-foreground">
            {agents.length > 0 ? "No agents match your filters" : "No agents observed yet"}
          </p>
          <p className="text-sm text-muted-foreground">
            {agents.length > 0 ? "Try adjusting search or filters" : "Instrument with the LangSight SDK to capture agent sessions."}
          </p>
        </div>
      ) : (
        <div className="grid lg:grid-cols-5 gap-4">
          {/* Agent list — scrollable */}
          <div className="lg:col-span-3 rounded-xl border border-border overflow-hidden bg-card">
            <div className="px-5 py-3 border-b border-border bg-muted/30">
              <h2 className="text-sm font-semibold text-foreground">Agent Fleet</h2>
              <p className="text-xs text-muted-foreground mt-0.5">
                {filtered.length} agents · ranked by failures, then call volume
              </p>
            </div>
            <div className="max-h-[600px] overflow-y-auto divide-y divide-border">
              {filtered.map(agent => {
                const active = selected?.agent_name === agent.agent_name;
                return (
                  <button key={agent.agent_name}
                    onClick={() => setSelectedAgent(agent.agent_name)}
                    className={cn("w-full text-left px-5 py-3.5 transition-colors", active ? "bg-primary/5" : "hover:bg-accent/40")}>
                    <div className="flex items-start justify-between gap-4">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <Bot size={14} className="text-primary flex-shrink-0" />
                          <span className="text-sm font-medium truncate text-foreground">{agent.agent_name}</span>
                          {agent.failed_calls > 0 ? (
                            <span className="flex items-center gap-0.5 text-[10px] text-red-500 bg-red-500/10 px-1.5 py-0.5 rounded-full">
                              <AlertTriangle size={10} /> {agent.failed_calls} failures
                            </span>
                          ) : (
                            <span className="flex items-center gap-0.5 text-[10px] text-emerald-500 bg-emerald-500/10 px-1.5 py-0.5 rounded-full">
                              <CheckCircle size={10} /> clean
                            </span>
                          )}
                        </div>
                        <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-muted-foreground">
                          <span>{agent.sessions} sessions</span>
                          <span>·</span>
                          <span>{agent.tool_calls} calls</span>
                          <span>·</span>
                          <span>{formatDuration(agent.avg_duration_ms)} avg</span>
                          <span>·</span>
                          <span>{timeAgo(agent.latest_started_at)}</span>
                        </div>
                      </div>
                      <div className="text-right shrink-0">
                        <p className="text-xs font-mono text-muted-foreground">{formatUsd(agent.total_cost_usd)}</p>
                        <p className="text-[10px] text-muted-foreground mt-0.5">
                          {(agent.error_rate * 100).toFixed(1)}% error rate
                        </p>
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Detail panel */}
          <div className="lg:col-span-2 rounded-xl border border-border p-5 bg-card">
            {selected ? (
              <div className="space-y-5">
                <div>
                  <p className="text-[11px] font-medium text-muted-foreground mb-1">Selected Agent</p>
                  <h2 className="text-lg font-semibold text-foreground">{selected.agent_name}</h2>
                </div>

                <div className="grid grid-cols-2 gap-2">
                  <StatCard icon={GitBranch} label="Workflows" value={selected.sessions.toString()} />
                  <StatCard icon={Layers3} label="Tool Calls" value={selected.tool_calls.toString()} />
                  <StatCard icon={Wallet} label="Total Cost" value={formatUsd(selected.total_cost_usd)} />
                  <StatCard icon={Bot} label="Avg Runtime" value={formatDuration(selected.avg_duration_ms)} />
                  <StatCard icon={AlertTriangle} label="Failures" value={selected.failed_calls.toString()} alert={selected.failed_calls > 0}
                    sub={`${(selected.error_rate * 100).toFixed(1)}% error rate`} />
                </div>

                {selected.servers_used.length > 0 && (
                  <div>
                    <p className="text-xs font-medium text-muted-foreground mb-2">Tools & MCPs</p>
                    <div className="flex flex-wrap gap-1.5">
                      {selected.servers_used.map(server => (
                        <span key={server} className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs border border-border bg-muted text-muted-foreground">
                          <Wrench size={11} />{server}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                <div>
                  <p className="text-xs font-medium text-muted-foreground mb-2">Recent Workflows</p>
                  <div className="space-y-1.5 max-h-[200px] overflow-y-auto">
                    {selectedSessions.slice(0, 10).map(session => (
                      <div key={session.session_id} className="rounded-lg border border-border p-2.5 bg-muted/30 hover:bg-accent/30 transition-colors">
                        <div className="flex items-center justify-between gap-2 mb-0.5">
                          <span className="text-xs font-mono text-foreground truncate">{session.session_id.slice(0, 20)}…</span>
                          <ChevronRight size={12} className="text-muted-foreground flex-shrink-0" />
                        </div>
                        <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
                          <span>{session.tool_calls} calls</span>
                          <span>·</span>
                          <span>{formatDuration(session.duration_ms)}</span>
                          <span>·</span>
                          <span>{timeAgo(session.first_call_at)}</span>
                          {session.failed_calls > 0 && (
                            <span className="text-red-500 font-medium">{session.failed_calls} failed</span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              <div className="flex items-center justify-center h-40 text-sm text-muted-foreground">
                Select an agent to view details
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
