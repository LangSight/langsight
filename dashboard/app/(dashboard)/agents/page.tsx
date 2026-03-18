"use client";

import { useMemo, useState } from "react";
import useSWR from "swr";
import { Bot, ChevronRight, GitBranch, Layers3, Wallet, Wrench } from "lucide-react";

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
};

function formatUsd(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  }).format(value);
}

function aggregateAgents(
  sessions: AgentSession[],
  costs: CostsBreakdownResponse | undefined,
): AgentSummary[] {
  const costByAgent = new Map(
    (costs?.by_agent ?? []).map((entry) => [entry.agent_name, entry.total_cost_usd]),
  );
  const summaries = new Map<string, AgentSummary>();

  for (const session of sessions) {
    const agentName = session.agent_name ?? "unknown agent";
    const existing = summaries.get(agentName);
    const servers = new Set(existing?.servers_used ?? []);
    for (const server of session.servers_used ?? []) {
      servers.add(server);
    }

    const next: AgentSummary = existing ?? {
      agent_name: agentName,
      sessions: 0,
      tool_calls: 0,
      failed_calls: 0,
      total_duration_ms: 0,
      avg_duration_ms: 0,
      total_cost_usd: costByAgent.get(agentName) ?? 0,
      servers_used: [],
      latest_started_at: session.first_call_at,
      session_ids: [],
    };

    next.sessions += 1;
    next.tool_calls += session.tool_calls;
    next.failed_calls += session.failed_calls;
    next.total_duration_ms += session.duration_ms;
    next.avg_duration_ms = next.total_duration_ms / next.sessions;
    next.latest_started_at =
      new Date(session.first_call_at) > new Date(next.latest_started_at)
        ? session.first_call_at
        : next.latest_started_at;
    next.session_ids = [...next.session_ids, session.session_id];
    next.servers_used = Array.from(servers).sort();
    next.total_cost_usd = costByAgent.get(agentName) ?? next.total_cost_usd;

    summaries.set(agentName, next);
  }

  return Array.from(summaries.values()).sort((a, b) => {
    if (b.failed_calls !== a.failed_calls) return b.failed_calls - a.failed_calls;
    if (b.tool_calls !== a.tool_calls) return b.tool_calls - a.tool_calls;
    return b.total_cost_usd - a.total_cost_usd;
  });
}

export default function AgentsPage() {
  const [hours, setHours] = useState(24);
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);

  const { data: sessions, isLoading: sessionsLoading, error: sessionsError } = useSWR<AgentSession[]>(
    `/api/agents/sessions?hours=${hours}&limit=100`,
    fetcher,
    { refreshInterval: 30_000 },
  );
  const { data: costs } = useSWR<CostsBreakdownResponse>(
    `/api/costs/breakdown?hours=${hours}`,
    () => getCostsBreakdown(hours),
    { refreshInterval: 30_000 },
  );

  const agents = useMemo(
    () => aggregateAgents(sessions ?? [], costs),
    [sessions, costs],
  );
  const selected = agents.find((agent) => agent.agent_name === selectedAgent) ?? agents[0] ?? null;
  const selectedSessions = (sessions ?? []).filter(
    (session) => session.agent_name === selected?.agent_name,
  );

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold" style={{ color: "hsl(var(--foreground))" }}>
            Agents
          </h1>
          <p className="text-sm" style={{ color: "hsl(var(--muted-foreground))" }}>
            Start with agents, then drill into their workflows, tools, and MCP dependencies
          </p>
        </div>
        <select
          value={hours}
          onChange={(event) => setHours(Number(event.target.value))}
          className="text-sm rounded-lg px-3 py-2 border outline-none"
          style={{
            background: "hsl(var(--card))",
            borderColor: "hsl(var(--border))",
            color: "hsl(var(--foreground))",
          }}
        >
          {[
            [1, "1h"],
            [6, "6h"],
            [24, "24h"],
            [168, "7d"],
          ].map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </div>

      {sessionsLoading ? (
        <div className="grid lg:grid-cols-3 gap-5">
          <div
            className="lg:col-span-2 rounded-xl border p-6 space-y-3"
            style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
          >
            {Array.from({ length: 4 }).map((_, index) => (
              <div key={index} className="skeleton h-14 rounded-lg" />
            ))}
          </div>
          <div
            className="rounded-xl border p-6 space-y-3"
            style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
          >
            {Array.from({ length: 6 }).map((_, index) => (
              <div key={index} className="skeleton h-4 rounded" />
            ))}
          </div>
        </div>
      ) : sessionsError ? (
        <div
          className="rounded-xl border p-12 text-center"
          style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
        >
          <Bot size={40} className="mx-auto mb-4 opacity-20" />
          <p className="font-medium mb-1" style={{ color: "hsl(var(--foreground))" }}>
            Could not load agent activity
          </p>
          <p className="text-sm" style={{ color: "hsl(var(--muted-foreground))" }}>
            Agent views depend on session traces stored in ClickHouse.
          </p>
        </div>
      ) : agents.length === 0 ? (
        <div
          className="rounded-xl border p-12 text-center"
          style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
        >
          <Bot size={40} className="mx-auto mb-4 opacity-20" />
          <p className="font-medium mb-1" style={{ color: "hsl(var(--foreground))" }}>
            No agents observed yet
          </p>
          <p className="text-sm" style={{ color: "hsl(var(--muted-foreground))" }}>
            Instrument your application with the LangSight SDK to capture agent sessions and handoffs.
          </p>
        </div>
      ) : (
        <div className="grid lg:grid-cols-3 gap-5">
          <div
            className="lg:col-span-2 rounded-xl border overflow-hidden"
            style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
          >
            <div
              className="px-5 py-4 border-b"
              style={{ borderColor: "hsl(var(--border))" }}
            >
              <h2 className="text-sm font-semibold" style={{ color: "hsl(var(--foreground))" }}>
                Agent Fleet
              </h2>
              <p className="text-xs mt-1" style={{ color: "hsl(var(--muted-foreground))" }}>
                Ranked by failures first, then call volume and cost
              </p>
            </div>
            <div className="divide-y" style={{ borderColor: "hsl(var(--border))" }}>
              {agents.map((agent) => {
                const active = selected?.agent_name === agent.agent_name;
                return (
                  <button
                    key={agent.agent_name}
                    onClick={() => setSelectedAgent(agent.agent_name)}
                    className={cn(
                      "w-full text-left px-5 py-4 transition-colors",
                      active ? "bg-primary/5" : "hover:bg-accent/50",
                    )}
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <Bot size={14} style={{ color: "hsl(var(--primary))" }} />
                          <span
                            className="text-sm font-medium truncate"
                            style={{ color: "hsl(var(--foreground))" }}
                          >
                            {agent.agent_name}
                          </span>
                        </div>
                        <div
                          className="flex flex-wrap items-center gap-2 text-xs"
                          style={{ color: "hsl(var(--muted-foreground))" }}
                        >
                          <span>{agent.sessions} sessions</span>
                          <span>·</span>
                          <span>{agent.tool_calls} tool calls</span>
                          <span>·</span>
                          <span>{timeAgo(agent.latest_started_at)}</span>
                        </div>
                      </div>
                      <div className="text-right shrink-0">
                        <p
                          className={cn(
                            "text-xs font-medium",
                            agent.failed_calls > 0 ? "text-red-500" : "text-emerald-500",
                          )}
                        >
                          {agent.failed_calls > 0 ? `${agent.failed_calls} failures` : "clean"}
                        </p>
                        <p className="text-xs font-mono" style={{ color: "hsl(var(--muted-foreground))" }}>
                          {formatUsd(agent.total_cost_usd)}
                        </p>
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          <div
            className="rounded-xl border p-5"
            style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
          >
            {selected ? (
              <div className="space-y-5">
                <div>
                  <p className="text-xs font-medium mb-1" style={{ color: "hsl(var(--muted-foreground))" }}>
                    Selected Agent
                  </p>
                  <h2 className="text-lg font-semibold" style={{ color: "hsl(var(--foreground))" }}>
                    {selected.agent_name}
                  </h2>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  {[
                    {
                      icon: GitBranch,
                      label: "Workflows",
                      value: selected.sessions.toString(),
                    },
                    {
                      icon: Layers3,
                      label: "Tool Calls",
                      value: selected.tool_calls.toString(),
                    },
                    {
                      icon: Wallet,
                      label: "Cost",
                      value: formatUsd(selected.total_cost_usd),
                    },
                    {
                      icon: Bot,
                      label: "Avg Runtime",
                      value: formatDuration(selected.avg_duration_ms),
                    },
                  ].map((metric) => (
                    <div
                      key={metric.label}
                      className="rounded-lg border p-3"
                      style={{ background: "hsl(var(--muted))", borderColor: "hsl(var(--border))" }}
                    >
                      <div className="flex items-center justify-between mb-2">
                        <metric.icon size={14} style={{ color: "hsl(var(--primary))" }} />
                        <span className="text-[11px]" style={{ color: "hsl(var(--muted-foreground))" }}>
                          {metric.label}
                        </span>
                      </div>
                      <p className="text-sm font-semibold" style={{ color: "hsl(var(--foreground))" }}>
                        {metric.value}
                      </p>
                    </div>
                  ))}
                </div>

                <div>
                  <p className="text-xs font-medium mb-2" style={{ color: "hsl(var(--muted-foreground))" }}>
                    Tools & MCPs touched
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {selected.servers_used.map((server) => (
                      <span
                        key={server}
                        className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs border"
                        style={{
                          background: "hsl(var(--muted))",
                          borderColor: "hsl(var(--border))",
                          color: "hsl(var(--muted-foreground))",
                        }}
                      >
                        <Wrench size={11} />
                        {server}
                      </span>
                    ))}
                  </div>
                </div>

                <div>
                  <p className="text-xs font-medium mb-2" style={{ color: "hsl(var(--muted-foreground))" }}>
                    Recent workflows
                  </p>
                  <div className="space-y-2">
                    {selectedSessions.slice(0, 5).map((session) => (
                      <div
                        key={session.session_id}
                        className="rounded-lg border p-3"
                        style={{ background: "hsl(var(--muted))", borderColor: "hsl(var(--border))" }}
                      >
                        <div className="flex items-center justify-between gap-2 mb-1">
                          <span className="text-xs font-mono" style={{ color: "hsl(var(--foreground))" }}>
                            {session.session_id}
                          </span>
                          <ChevronRight size={12} style={{ color: "hsl(var(--muted-foreground))" }} />
                        </div>
                        <div
                          className="flex flex-wrap items-center gap-2 text-[11px]"
                          style={{ color: "hsl(var(--muted-foreground))" }}
                        >
                          <span>{session.tool_calls} calls</span>
                          <span>·</span>
                          <span>{formatDuration(session.duration_ms)}</span>
                          <span>·</span>
                          <span>{timeAgo(session.first_call_at)}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}
