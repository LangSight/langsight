"use client";

export const dynamic = "force-dynamic";

import { useMemo, useRef, useState } from "react";
import useSWR from "swr";
import Link from "next/link";
import * as Dialog from "@radix-ui/react-dialog";
import {
  Bot, ChevronRight, Search, Network, X, Server, GitBranch,
  ChevronUp, ChevronDown, ChevronLast, AlertTriangle, Wrench,
} from "lucide-react";
import { fetcher, getCostsBreakdown, listAgentMetadata, upsertAgentMetadata, getAgentLoopCounts, getSLOStatus, createSLO, deleteSLO } from "@/lib/api";
import type { SLOStatus } from "@/lib/types";
import { useProject } from "@/lib/project-context";
import { cn, formatDuration, timeAgo, formatExact } from "@/lib/utils";
import { Timestamp } from "@/components/timestamp";
import { LineageGraph as LineageGraphComponent, type GraphNode, type GraphEdge } from "@/components/lineage-graph";
import { AgentTopology } from "@/components/agent-topology";
import { EditableTextarea, EditableText, EditableTags, EditableUrl } from "@/components/editable-field";
import type { AgentSession, AgentMetadata, CostsBreakdownResponse, LineageGraph, HealthResult, ToolReliability } from "@/lib/types";

/* ── Types ──────────────────────────────────────────────────── */
type AgentSummary = {
  agent_name: string; sessions: number; tool_calls: number; failed_calls: number;
  total_duration_ms: number; avg_duration_ms: number; total_cost_usd: number;
  servers_used: string[]; latest_started_at: string; session_ids: string[];
  error_rate: number; status: "healthy" | "degraded" | "failing";
  health_score: number;
  healthy_sessions: number;
  total_input_tokens: number;
  total_output_tokens: number;
  avg_tokens_per_session: number;
};
type DetailTab = "about" | "overview" | "servers" | "topology" | "sessions" | "slos";
type SortCol = "name" | "healthScore" | "errorRate" | "cost" | "lastActive" | "sessions";

/* ── Helpers ────────────────────────────────────────────────── */
function formatUsd(v: number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 4 }).format(v);
}

function aggregateAgents(sessions: AgentSession[], costs: CostsBreakdownResponse | undefined): AgentSummary[] {
  const costByAgent = new Map((costs?.by_agent ?? []).map((e) => [e.agent_name, e.total_cost_usd]));
  const summaries = new Map<string, AgentSummary>();
  for (const session of sessions) {
    // Use agents_used (all agents in the session) if available, fall back to agent_name
    const agentNames = session.agents_used?.length
      ? session.agents_used
      : [session.agent_name ?? "unknown agent"];

    for (const name of agentNames) {
      const existing = summaries.get(name);
      const servers = new Set(existing?.servers_used ?? []);
      for (const s of session.servers_used ?? []) servers.add(s);
      const isHealthy = session.health_tag === "success" || session.health_tag === "success_with_fallback";
      const next: AgentSummary = existing ?? {
        agent_name: name, sessions: 0, tool_calls: 0, failed_calls: 0,
        total_duration_ms: 0, avg_duration_ms: 0, total_cost_usd: costByAgent.get(name) ?? 0,
        servers_used: [], latest_started_at: session.first_call_at, session_ids: [],
        error_rate: 0, status: "healthy", health_score: 100, healthy_sessions: 0,
        total_input_tokens: 0, total_output_tokens: 0, avg_tokens_per_session: 0,
      };
      next.sessions += 1; next.tool_calls += session.tool_calls; next.failed_calls += session.failed_calls;
      next.total_duration_ms += session.duration_ms; next.avg_duration_ms = next.total_duration_ms / next.sessions;
      next.error_rate = next.tool_calls > 0 ? next.failed_calls / next.tool_calls : 0;
      next.healthy_sessions += isHealthy ? 1 : 0;
      next.health_score = Math.round(next.healthy_sessions / next.sessions * 100);
      next.status = next.health_score < 70 ? "failing" : next.health_score < 90 ? "degraded" : "healthy";
      next.total_input_tokens += session.total_input_tokens ?? 0;
      next.total_output_tokens += session.total_output_tokens ?? 0;
      next.avg_tokens_per_session = next.sessions > 0
        ? Math.round((next.total_input_tokens + next.total_output_tokens) / next.sessions)
        : 0;
      next.latest_started_at = new Date(session.first_call_at) > new Date(next.latest_started_at) ? session.first_call_at : next.latest_started_at;
      if (!next.session_ids.includes(session.session_id)) next.session_ids.push(session.session_id);
      next.servers_used = Array.from(servers).sort();
      next.total_cost_usd = costByAgent.get(name) ?? next.total_cost_usd;
      summaries.set(name, next);
    }
  }
  return Array.from(summaries.values()).sort((a, b) => b.failed_calls - a.failed_calls || b.tool_calls - a.tool_calls);
}

const STATUS_COLOR: Record<string, string> = { healthy: "#22c55e", degraded: "#eab308", failing: "#ef4444" };
const STATUS_BG: Record<string, string> = { healthy: "rgba(34,197,94,0.08)", degraded: "rgba(234,179,8,0.08)", failing: "rgba(239,68,68,0.08)" };

function StatusDot({ status, pulse }: { status: string; pulse?: boolean }) {
  return (
    <span className="relative flex w-2 h-2 flex-shrink-0">
      {pulse && status === "healthy" && <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-40" style={{ background: STATUS_COLOR[status] }} />}
      <span className="relative inline-flex rounded-full w-2 h-2" style={{ background: STATUS_COLOR[status] }} />
    </span>
  );
}

function StatTile({ label, value, danger }: { label: string; value: string; danger?: boolean }) {
  return (
    <div className="flex items-center justify-between py-1.5">
      <span className="text-[11px] text-muted-foreground">{label}</span>
      <span className={cn("text-[12px] font-semibold", danger ? "text-red-500" : "text-foreground")} style={{ fontFamily: "var(--font-geist-mono)" }}>{value}</span>
    </div>
  );
}

/* ── Sortable table header cell ─────────────────────────────── */
function ThCell({ col, label, sortCol, sortDir, onSort, className }: { col: SortCol; label: string; sortCol: SortCol; sortDir: "asc" | "desc"; onSort: (c: SortCol) => void; className?: string }) {
  const active = sortCol === col;
  return (
    <th className={cn("px-3 py-2.5 text-left cursor-pointer select-none hover:bg-accent/30 transition-colors", className)}
      onClick={() => onSort(col)}>
      <div className="flex items-center gap-1">
        <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">{label}</span>
        {active ? (sortDir === "asc" ? <ChevronUp size={10} className="text-primary" /> : <ChevronDown size={10} className="text-primary" />) : <ChevronDown size={10} className="opacity-20" />}
      </div>
    </th>
  );
}

/* ── State 1: Full-width sortable table ─────────────────────── */
function AgentTable({ agents, metaByName, onSelect, hours, loopByAgent, sloByAgent }: { agents: AgentSummary[]; metaByName: Map<string, AgentMetadata>; onSelect: (name: string) => void; hours: number; loopByAgent: Map<string, number>; sloByAgent: Map<string, "ok" | "breached" | "no_data"> }) {
  const [sortCol, setSortCol] = useState<SortCol>("errorRate");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "healthy" | "degraded" | "failing">("all");

  const counts = useMemo(() => ({
    all: agents.length,
    healthy: agents.filter((a) => a.status === "healthy").length,
    degraded: agents.filter((a) => a.status === "degraded").length,
    failing: agents.filter((a) => a.status === "failing").length,
  }), [agents]);

  const attention = useMemo(() => agents.filter((a) => a.status !== "healthy"), [agents]);

  function handleSort(col: SortCol) {
    if (sortCol === col) setSortDir((d) => d === "asc" ? "desc" : "asc");
    else { setSortCol(col); setSortDir("desc"); }
  }

  const sorted = useMemo(() => {
    const base = agents.filter((a) => (statusFilter === "all" || a.status === statusFilter) && (!search || a.agent_name.toLowerCase().includes(search.toLowerCase())));
    return [...base].sort((a, b) => {
      let diff = 0;
      if (sortCol === "name") diff = a.agent_name.localeCompare(b.agent_name);
      else if (sortCol === "healthScore") diff = b.health_score - a.health_score;
      else if (sortCol === "errorRate") diff = b.error_rate - a.error_rate;
      else if (sortCol === "cost") diff = b.total_cost_usd - a.total_cost_usd;
      else if (sortCol === "sessions") diff = b.sessions - a.sessions;
      else if (sortCol === "lastActive") diff = new Date(b.latest_started_at).getTime() - new Date(a.latest_started_at).getTime();
      return sortDir === "asc" ? -diff : diff;
    });
  }, [agents, sortCol, sortDir, search, statusFilter]);

  return (
    <div className="flex flex-col h-full gap-3">
      {/* Filter row */}
      <div className="flex items-center gap-3 flex-shrink-0">
        <div className="relative">
          <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input type="text" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search agents..." className="input-base pl-8 pr-3 h-[30px] text-[12px] w-[200px]" />
        </div>
        <div className="flex items-center gap-1">
          {(["all", "failing", "degraded", "healthy"] as const).map((f) => (
            <button key={f} onClick={() => setStatusFilter(f)}
              className={cn("px-2.5 py-1 rounded-lg text-[10px] font-medium transition-all", statusFilter === f ? "text-foreground" : "text-muted-foreground hover:text-foreground hover:bg-accent/40")}
              style={{ background: statusFilter === f ? "hsl(var(--card))" : undefined, border: statusFilter === f ? "1px solid hsl(var(--border))" : "1px solid transparent" }}>
              {f !== "all" && <span className="inline-block w-1.5 h-1.5 rounded-full mr-1" style={{ background: STATUS_COLOR[f] }} />}
              {f.charAt(0).toUpperCase() + f.slice(1)} <span className="text-muted-foreground">{counts[f]}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Needs attention banner */}
      {attention.length > 0 && statusFilter === "all" && !search && (
        <div className="flex-shrink-0 rounded-xl border px-4 py-2.5" style={{ background: "rgba(239,68,68,0.04)", borderColor: "rgba(239,68,68,0.15)" }}>
          <div className="flex items-center gap-2 mb-2">
            <AlertTriangle size={12} style={{ color: "#ef4444" }} />
            <span className="text-[11px] font-semibold" style={{ color: "#ef4444" }}>Needs Attention · {attention.length} agent{attention.length > 1 ? "s" : ""}</span>
          </div>
          <div className="flex flex-wrap gap-2">
            {attention.map((a) => (
              <button key={a.agent_name} onClick={() => onSelect(a.agent_name)}
                className="flex items-center gap-1.5 rounded-lg px-2.5 py-1 hover:opacity-80 transition-opacity"
                style={{ background: STATUS_BG[a.status], border: `1px solid ${STATUS_COLOR[a.status]}30` }}>
                <StatusDot status={a.status} />
                <span className="text-[11px] font-medium text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>{a.agent_name}</span>
                <span className="text-[10px]" style={{ color: "#ef4444", fontFamily: "var(--font-geist-mono)" }}>{a.failed_calls} err</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Table */}
      <div className="flex-1 rounded-xl border overflow-auto" style={{ borderColor: "hsl(var(--border))" }}>
        <table className="w-full border-collapse">
          <thead className="sticky top-0 z-10" style={{ background: "hsl(var(--card-raised))", borderBottom: "1px solid hsl(var(--border))" }}>
            <tr>
              <th className="w-8 px-3 py-2.5" />
              <ThCell col="name" label="Name" sortCol={sortCol} sortDir={sortDir} onSort={handleSort} className="min-w-[180px]" />
              <th className="px-3 py-2.5 text-left text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">Owner</th>
              <th className="px-3 py-2.5 text-left text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">Tags</th>
              <ThCell col="sessions" label="Sessions" sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />
              <ThCell col="healthScore" label="Health" sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />
              <ThCell col="errorRate" label="Error %" sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />
              <th className="px-3 py-2.5 text-left text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">Tokens/Session</th>
              <th className="px-3 py-2.5 text-left text-[10px] font-semibold text-muted-foreground uppercase tracking-wide" title="Loop detections in time window">Loops</th>
              <ThCell col="cost" label={`Cost ${hours}h`} sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />
              <ThCell col="lastActive" label="Last Seen" sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />
            </tr>
          </thead>
          <tbody>
            {sorted.map((agent) => {
              const meta = metaByName.get(agent.agent_name);
              return (
                <tr key={agent.agent_name}
                  onClick={() => onSelect(agent.agent_name)}
                  className="cursor-pointer hover:bg-accent/20 transition-colors border-b"
                  style={{ borderColor: "hsl(var(--border))" }}>
                  <td className="px-3 py-2.5 text-center">
                    <StatusDot status={agent.status} pulse />
                  </td>
                  <td className="px-3 py-2.5">
                    <div className="flex items-center gap-2">
                      <span className="text-[12px] font-semibold text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>{agent.agent_name}</span>
                      {sloByAgent.has(agent.agent_name) && (() => {
                        const slo = sloByAgent.get(agent.agent_name)!;
                        return slo === "breached" ? (
                          <span className="text-[9px] font-bold px-1.5 py-0.5 rounded" style={{ background: "rgba(239,68,68,0.1)", color: "#ef4444", border: "1px solid rgba(239,68,68,0.2)" }}>SLO ✗</span>
                        ) : slo === "ok" ? (
                          <span className="text-[9px] font-bold px-1.5 py-0.5 rounded" style={{ background: "rgba(34,197,94,0.1)", color: "#22c55e", border: "1px solid rgba(34,197,94,0.2)" }}>SLO ✓</span>
                        ) : null;
                      })()}
                    </div>
                    {meta?.description && <p className="text-[10px] text-muted-foreground truncate max-w-[240px]">{meta.description}</p>}
                  </td>
                  <td className="px-3 py-2.5 text-[11px] text-muted-foreground">{meta?.owner ?? <span className="opacity-30">—</span>}</td>
                  <td className="px-3 py-2.5">
                    <div className="flex items-center gap-1 flex-wrap max-w-[180px]">
                      {(meta?.tags ?? []).slice(0, 2).map((t) => (
                        <span key={t} className="text-[8px] font-medium px-1.5 py-0.5 rounded" style={{ background: "hsl(var(--primary) / 0.06)", color: "hsl(var(--primary))" }}>{t}</span>
                      ))}
                      {(meta?.tags ?? []).length > 2 && <span className="text-[8px] text-muted-foreground">+{(meta?.tags ?? []).length - 2}</span>}
                    </div>
                  </td>
                  <td className="px-3 py-2.5 text-[11px] text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>{agent.sessions}</td>
                  <td className="px-3 py-2.5">
                    <div className="flex items-center gap-2">
                      <span className="text-[12px] font-bold" style={{
                        fontFamily: "var(--font-geist-mono)",
                        color: agent.health_score >= 90 ? "#22c55e" : agent.health_score >= 70 ? "#eab308" : "#ef4444",
                      }}>
                        {agent.health_score}%
                      </span>
                      <div className="w-14 h-[4px] rounded-full overflow-hidden" style={{ background: "hsl(var(--muted))" }}>
                        <div className="h-full rounded-full transition-all" style={{
                          width: `${agent.health_score}%`,
                          background: agent.health_score >= 90 ? "#22c55e" : agent.health_score >= 70 ? "#eab308" : "#ef4444",
                        }} />
                      </div>
                    </div>
                    <div className="text-[9px] text-muted-foreground mt-0.5">{agent.healthy_sessions}/{agent.sessions} sessions</div>
                  </td>
                  <td className="px-3 py-2.5">
                    <div className="flex items-center gap-2">
                      <span className="text-[11px] font-semibold" style={{ fontFamily: "var(--font-geist-mono)", color: agent.error_rate > 0.2 ? "#ef4444" : agent.error_rate > 0.05 ? "#eab308" : "#22c55e" }}>
                        {(agent.error_rate * 100).toFixed(1)}%
                      </span>
                      {agent.failed_calls > 0 && (
                        <div className="w-12 h-[3px] rounded-full overflow-hidden" style={{ background: "hsl(var(--muted))" }}>
                          <div className="h-full rounded-full" style={{ width: `${Math.min(100, agent.error_rate * 100)}%`, background: agent.error_rate > 0.2 ? "#ef4444" : "#eab308" }} />
                        </div>
                      )}
                    </div>
                  </td>
                  <td className="px-3 py-2.5">
                    {agent.avg_tokens_per_session > 0 ? (
                      <div>
                        <span className="text-[11px] font-mono text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>
                          {agent.avg_tokens_per_session >= 1000
                            ? `${(agent.avg_tokens_per_session / 1000).toFixed(1)}k`
                            : agent.avg_tokens_per_session}
                        </span>
                        <div className="text-[9px] text-muted-foreground mt-0.5">
                          avg/session
                        </div>
                      </div>
                    ) : <span className="opacity-30 text-[11px]">—</span>}
                  </td>
                  <td className="px-3 py-2.5">
                    {(loopByAgent.get(agent.agent_name) ?? 0) > 0 ? (
                      <span className="flex items-center gap-1 text-[10px] font-semibold px-1.5 py-0.5 rounded-full w-fit"
                        style={{ background: "rgba(239,68,68,0.1)", color: "#ef4444", border: "1px solid rgba(239,68,68,0.2)" }}>
                        <AlertTriangle size={9} />
                        {loopByAgent.get(agent.agent_name)}
                      </span>
                    ) : <span className="opacity-30 text-[11px]">—</span>}
                  </td>
                  <td className="px-3 py-2.5 text-[11px] text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>{agent.total_cost_usd > 0 ? formatUsd(agent.total_cost_usd) : <span className="opacity-30">—</span>}</td>
                  <td className="px-3 py-2.5">
                    <div className="text-[11px] text-muted-foreground"><Timestamp iso={agent.latest_started_at} compact /></div>
                    <div className="text-[9px] text-muted-foreground opacity-60 mt-0.5" style={{ fontFamily: "var(--font-geist-mono)" }}>{formatExact(agent.latest_started_at)}</div>
                  </td>
                </tr>
              );
            })}
            {sorted.length === 0 && (
              <tr><td colSpan={10} className="text-center py-12 text-sm text-muted-foreground">No agents match</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ── State 2 sidebar: Grouped compact list ──────────────────── */
function GroupedSidebar({ agents, metaByName, selectedAgent, onSelect, search, onSearchChange }: {
  agents: AgentSummary[]; metaByName: Map<string, AgentMetadata>; selectedAgent: string | null;
  onSelect: (n: string) => void; search: string; onSearchChange: (v: string) => void;
}) {
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set(["healthy"]));
  const toggleGroup = (g: string) => setCollapsedGroups((p) => { const n = new Set(p); n.has(g) ? n.delete(g) : n.add(g); return n; });

  const groups = useMemo(() => {
    const filtered = search ? agents.filter((a) => a.agent_name.toLowerCase().includes(search.toLowerCase())) : agents;
    return {
      failing: filtered.filter((a) => a.status === "failing"),
      degraded: filtered.filter((a) => a.status === "degraded"),
      healthy: filtered.filter((a) => a.status === "healthy"),
    };
  }, [agents, search]);

  function Group({ name, items, label }: { name: string; items: AgentSummary[]; label: string }) {
    if (items.length === 0) return null;
    const isCollapsed = collapsedGroups.has(name);
    const color = STATUS_COLOR[name] ?? "#6b7280";
    return (
      <div>
        <button onClick={() => toggleGroup(name)} className="w-full flex items-center justify-between px-3 py-1.5 hover:bg-accent/20 transition-colors">
          <div className="flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full" style={{ background: color }} />
            <span className="text-[9px] font-semibold text-muted-foreground uppercase tracking-wide">{label}</span>
            <span className="text-[9px] text-muted-foreground ml-1">{items.length}</span>
          </div>
          {isCollapsed ? <ChevronRight size={10} className="text-muted-foreground" /> : <ChevronDown size={10} className="text-muted-foreground" />}
        </button>
        {!isCollapsed && items.map((a) => {
          const isSel = selectedAgent === a.agent_name;
          return (
            <button key={a.agent_name} onClick={() => onSelect(a.agent_name)} className={cn("w-full flex items-center gap-2.5 px-3 py-1.5 text-left hover:bg-accent/20 transition-colors", isSel && "bg-primary/8")}
              style={{ background: isSel ? "hsl(var(--primary) / 0.06)" : undefined, borderLeft: isSel ? `2px solid hsl(var(--primary))` : "2px solid transparent" }}>
              <StatusDot status={a.status} />
              <span className="flex-1 text-[11px] font-medium text-foreground truncate" style={{ fontFamily: "var(--font-geist-mono)" }}>{a.agent_name}</span>
              {a.failed_calls > 0 && <span className="text-[9px] flex-shrink-0" style={{ color: "#ef4444", fontFamily: "var(--font-geist-mono)" }}>{a.failed_calls}✗</span>}
            </button>
          );
        })}
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full border-r" style={{ borderColor: "hsl(var(--border))", background: "hsl(var(--background))" }}>
      {/* Search */}
      <div className="flex-shrink-0 px-3 py-2.5 border-b" style={{ borderColor: "hsl(var(--border))" }}>
        <div className="relative">
          <Search size={11} className="absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input type="text" value={search} onChange={(e) => onSearchChange(e.target.value)} placeholder="Search..." className="w-full pl-6 pr-2 py-1.5 text-[11px] rounded-md bg-transparent border outline-none" style={{ borderColor: "hsl(var(--border))", color: "hsl(var(--foreground))" }} />
        </div>
      </div>
      {/* Groups */}
      <div className="flex-1 overflow-y-auto py-1">
        <Group name="failing" items={groups.failing} label="Failing" />
        <Group name="degraded" items={groups.degraded} label="Degraded" />
        <Group name="healthy" items={groups.healthy} label="Healthy" />
        {groups.failing.length + groups.degraded.length + groups.healthy.length === 0 && (
          <p className="text-center text-[11px] text-muted-foreground py-8">No agents match</p>
        )}
      </div>
    </div>
  );
}

/* ── State 3 sidebar: Icon rail ─────────────────────────────── */
function AgentRail({ agents, selectedAgent, onSelect, onExpand }: {
  agents: AgentSummary[]; selectedAgent: string | null;
  onSelect: (n: string) => void; onExpand: () => void;
}) {
  const [hovered, setHovered] = useState<string | null>(null);
  const hoveredAgent = agents.find((a) => a.agent_name === hovered);

  return (
    <div className="flex flex-col h-full border-r relative" style={{ borderColor: "hsl(var(--border))", background: "hsl(var(--background))" }}>
      {/* Expand button */}
      <button onClick={onExpand} className="flex-shrink-0 flex items-center justify-center h-10 hover:bg-accent/40 transition-colors border-b" style={{ borderColor: "hsl(var(--border))" }} title="Expand agent list">
        <ChevronLast size={14} className="text-muted-foreground" />
      </button>
      {/* Agent initials */}
      <div className="flex-1 overflow-y-auto py-1">
        {agents.map((a) => {
          const isSel = selectedAgent === a.agent_name;
          const initial = a.agent_name.charAt(0).toUpperCase();
          return (
            <div key={a.agent_name} className="relative flex items-center justify-center h-11" onMouseEnter={() => setHovered(a.agent_name)} onMouseLeave={() => setHovered(null)}>
              {/* Active left bar */}
              {isSel && <span className="absolute left-0 top-2 bottom-2 w-0.5 rounded-r" style={{ background: "hsl(var(--primary))" }} />}
              <button onClick={() => onSelect(a.agent_name)} className="w-7 h-7 rounded-full flex items-center justify-center text-[10px] font-bold transition-all"
                style={{ background: isSel ? "hsl(var(--primary))" : STATUS_BG[a.status] ?? "hsl(var(--muted))", color: isSel ? "white" : STATUS_COLOR[a.status], border: `1px solid ${isSel ? "hsl(var(--primary))" : STATUS_COLOR[a.status] + "40"}` }}>
                {initial}
              </button>
            </div>
          );
        })}
      </div>
      {/* Hover tooltip */}
      {hovered && hoveredAgent && (
        <div className="fixed z-50 left-16 rounded-lg px-3 py-2 shadow-xl pointer-events-none" style={{ top: "50%", transform: "translateY(-50%)", background: "hsl(var(--card-raised))", border: "1px solid hsl(var(--border))", animation: "fadeIn 0.1s ease", minWidth: 180 }}>
          <p className="text-[12px] font-bold text-foreground mb-0.5" style={{ fontFamily: "var(--font-geist-mono)" }}>{hoveredAgent.agent_name}</p>
          <div className="flex items-center gap-2 text-[10px]">
            <span style={{ color: STATUS_COLOR[hoveredAgent.status] }}>{hoveredAgent.status}</span>
            {hoveredAgent.failed_calls > 0 && <span style={{ color: "#ef4444" }}>{hoveredAgent.failed_calls} errors</span>}
          </div>
        </div>
      )}
    </div>
  );
}

/* ── SLO tab ────────────────────────────────────────────────── */
function SLOTab({ agentName, slos, projectId, onRefresh }: {
  agentName: string;
  slos: SLOStatus[];
  projectId: string | null;
  onRefresh: () => void;
}) {
  const [adding, setAdding] = useState(false);
  const [saving, setSaving] = useState(false);
  const [metric, setMetric] = useState<"success_rate" | "latency_p99">("success_rate");
  const [target, setTarget] = useState("");
  const [windowHours, setWindowHours] = useState(24);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  async function handleCreate() {
    const t = parseFloat(target);
    if (!t || t <= 0) return;
    setSaving(true);
    try {
      await createSLO({ agent_name: agentName, metric, target: t, window_hours: windowHours }, projectId);
      setAdding(false);
      setTarget("");
      onRefresh();
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: string) {
    setDeletingId(id);
    try {
      await deleteSLO(id);
      onRefresh();
    } finally {
      setDeletingId(null);
    }
  }

  const statusColor = (s: string) =>
    s === "ok" ? "#22c55e" : s === "breached" ? "#ef4444" : "#6b7280";
  const statusLabel = (s: string) =>
    s === "ok" ? "Passing" : s === "breached" ? "Breached" : "No data";

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">
          SLO Targets — {agentName}
        </p>
        {!adding && (
          <button
            onClick={() => setAdding(true)}
            className="text-[11px] font-medium px-2.5 py-1 rounded-lg transition-colors"
            style={{ background: "hsl(var(--primary) / 0.08)", color: "hsl(var(--primary))", border: "1px solid hsl(var(--primary) / 0.2)" }}
          >
            + Add SLO
          </button>
        )}
      </div>

      {/* Existing SLOs */}
      {slos.length === 0 && !adding && (
        <div className="rounded-xl border border-dashed py-8 text-center" style={{ borderColor: "hsl(var(--border))" }}>
          <p className="text-[12px] font-semibold text-foreground mb-1">No SLOs defined</p>
          <p className="text-[11px] text-muted-foreground">Set a reliability target to track pass/fail against it.</p>
        </div>
      )}

      <div className="space-y-2">
        {slos.map(slo => (
          <div key={slo.slo_id} className="rounded-xl border p-3 flex items-center justify-between gap-3"
            style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-[12px] font-semibold text-foreground capitalize">
                  {slo.metric === "success_rate" ? "Success Rate" : "Latency p99"}
                </span>
                <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full"
                  style={{ background: `${statusColor(slo.status)}18`, color: statusColor(slo.status) }}>
                  {statusLabel(slo.status)}
                </span>
              </div>
              <div className="flex items-center gap-3 text-[11px]">
                <span className="text-muted-foreground">
                  Target: <span className="text-foreground font-mono font-semibold">
                    {slo.metric === "success_rate" ? `${slo.target}%` : `${slo.target}ms`}
                  </span>
                </span>
                {slo.current_value != null && (
                  <span className="text-muted-foreground">
                    Current: <span className="font-mono font-semibold" style={{ color: statusColor(slo.status) }}>
                      {slo.metric === "success_rate"
                        ? `${slo.current_value.toFixed(1)}%`
                        : `${Math.round(slo.current_value)}ms`}
                    </span>
                  </span>
                )}
                <span className="text-muted-foreground">{slo.window_hours}h window</span>
              </div>
            </div>
            <button
              onClick={() => handleDelete(slo.slo_id)}
              disabled={deletingId === slo.slo_id}
              className="text-[10px] text-muted-foreground hover:text-red-400 transition-colors px-2 py-1 rounded disabled:opacity-40"
            >
              {deletingId === slo.slo_id ? "…" : "Delete"}
            </button>
          </div>
        ))}
      </div>

      {/* Add SLO form */}
      {adding && (
        <div className="rounded-xl border p-4 space-y-3" style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--primary) / 0.3)" }}>
          <p className="text-[11px] font-semibold text-foreground">New SLO for {agentName}</p>

          <div className="flex gap-2">
            {(["success_rate", "latency_p99"] as const).map(m => (
              <button key={m} onClick={() => setMetric(m)}
                className="flex-1 py-1.5 rounded-lg text-[11px] font-medium transition-all capitalize"
                style={{
                  background: metric === m ? "hsl(var(--primary))" : "hsl(var(--muted))",
                  color: metric === m ? "white" : "hsl(var(--muted-foreground))",
                }}>
                {m === "success_rate" ? "Success Rate" : "Latency p99"}
              </button>
            ))}
          </div>

          <div className="flex gap-2 items-center">
            <div className="flex-1">
              <label className="text-[10px] text-muted-foreground mb-1 block">
                Target {metric === "success_rate" ? "(% — e.g. 95)" : "(ms — e.g. 2000)"}
              </label>
              <input
                type="number"
                value={target}
                onChange={e => setTarget(e.target.value)}
                placeholder={metric === "success_rate" ? "95" : "2000"}
                className="input-base h-[32px] text-[12px] w-full"
                style={{ fontFamily: "var(--font-geist-mono)" }}
              />
            </div>
            <div>
              <label className="text-[10px] text-muted-foreground mb-1 block">Window</label>
              <select value={windowHours} onChange={e => setWindowHours(Number(e.target.value))}
                className="h-[32px] text-[12px] rounded-lg border px-2 outline-none"
                style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))", color: "hsl(var(--foreground))" }}>
                <option value={1}>1h</option>
                <option value={6}>6h</option>
                <option value={24}>24h</option>
                <option value={168}>7d</option>
              </select>
            </div>
          </div>

          <div className="flex gap-2">
            <button onClick={handleCreate} disabled={saving || !target}
              className="flex-1 py-1.5 rounded-lg text-[12px] font-semibold transition-all disabled:opacity-40"
              style={{ background: "hsl(var(--primary))", color: "white" }}>
              {saving ? "Saving…" : "Create SLO"}
            </button>
            <button onClick={() => { setAdding(false); setTarget(""); }}
              className="px-4 py-1.5 rounded-lg text-[12px] text-muted-foreground hover:text-foreground transition-colors"
              style={{ background: "hsl(var(--muted))" }}>
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Per-server tool card (fetches declared tools, collapsible) ── */
const STATUS_COLOR_MAP: Record<string, string> = { up: "#22c55e", degraded: "#eab308", down: "#ef4444", stale: "#6b7280" };

function ServerToolsCard({ serverName, reliability, healthStatus, isMcpServer, projectId }: {
  serverName: string;
  reliability: ToolReliability[];
  healthStatus: string | undefined;
  isMcpServer: boolean;
  projectId: string | null;
}) {
  const [expanded, setExpanded] = useState(false);
  const pq = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
  const { data: declared } = useSWR<{ tool_name: string; description: string; input_schema: Record<string, unknown> }[]>(
    expanded ? `/api/servers/${encodeURIComponent(serverName)}/tools${pq}` : null,
    fetcher,
    { refreshInterval: 60_000 },
  );

  // Merge declared (schema) + observed (call stats)
  const allNames = new Set([...(declared ?? []).map(d => d.tool_name), ...reliability.map(r => r.tool_name)]);
  const tools = Array.from(allNames).sort().map((name) => ({
    name,
    description: declared?.find(d => d.tool_name === name)?.description ?? "",
    rel: reliability.find(r => r.tool_name === name) ?? null,
    isDeclared: !!(declared?.find(d => d.tool_name === name)),
  }));

  const statusColor = STATUS_COLOR_MAP[healthStatus ?? ""] ?? "#6b7280";
  const totalCalls = reliability.reduce((s, r) => s + r.total_calls, 0);

  return (
    <div className="rounded-xl border overflow-hidden transition-all" style={{ borderColor: expanded ? "hsl(var(--primary) / 0.3)" : "hsl(var(--border))" }}>
      {/* Server header — click to expand/collapse */}
      <button
        onClick={() => setExpanded(e => !e)}
        className="w-full flex items-center gap-2.5 px-4 py-2.5 hover:bg-accent/20 transition-colors text-left"
        style={{ background: "hsl(var(--card-raised))" }}
      >
        <ChevronRight size={12} className={cn("text-muted-foreground transition-transform flex-shrink-0", expanded && "rotate-90")} />
        <Server size={13} style={{ color: "hsl(var(--primary))" }} />
        <span className="text-[12px] font-bold text-foreground flex-1" style={{ fontFamily: "var(--font-geist-mono)" }}>{serverName}</span>
        {/* MCP Server vs Sub-agent badge */}
        <span className="text-[8px] px-1.5 py-0.5 rounded font-semibold flex-shrink-0" style={{
          background: isMcpServer ? "rgba(99,102,241,0.1)" : "hsl(var(--muted))",
          color: isMcpServer ? "hsl(var(--primary))" : "hsl(var(--muted-foreground))",
          border: `1px solid ${isMcpServer ? "rgba(99,102,241,0.2)" : "hsl(var(--border))"}`,
        }}>
          {isMcpServer ? "MCP Server" : "Sub-agent"}
        </span>
        {healthStatus && isMcpServer && (
          <span className="flex items-center gap-1 text-[10px] font-semibold flex-shrink-0" style={{ color: statusColor }}>
            <span className="w-1.5 h-1.5 rounded-full" style={{ background: statusColor }} />
            {healthStatus}
          </span>
        )}
        <span className="text-[10px] text-muted-foreground flex-shrink-0">
          {totalCalls > 0 ? `${totalCalls.toLocaleString()} calls` : `${reliability.length || "?"} tools`}
        </span>
      </button>

      {/* Tool list — only when expanded */}
      {expanded && (
        tools.length === 0 ? (
          <p className="px-4 py-3 text-[11px] text-muted-foreground italic">No tools observed yet</p>
        ) : (
          <div className="divide-y" style={{ borderColor: "hsl(var(--border) / 0.5)" }}>
            {tools.map((tool) => {
              const rel = tool.rel;
              const errColor = rel && rel.error_rate_pct > 10 ? "#ef4444" : rel && rel.error_rate_pct > 0 ? "#eab308" : "#22c55e";
              return (
                <div key={tool.name} className="px-4 py-2 hover:bg-accent/10 transition-colors">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="w-1.5 h-1.5 rounded-full flex-shrink-0 mt-1" style={{ background: rel ? errColor : "#6b7280" }} />
                      <div className="min-w-0">
                        <span className="text-[11px] font-semibold text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>{tool.name}</span>
                        {!tool.isDeclared && <span className="ml-1.5 text-[8px] px-1 py-0.5 rounded text-muted-foreground" style={{ background: "hsl(var(--border))" }}>observed</span>}
                        {tool.description && <p className="text-[10px] text-muted-foreground mt-0.5 truncate max-w-xs">{tool.description}</p>}
                      </div>
                    </div>
                    {rel ? (
                      <div className="flex items-center gap-3 flex-shrink-0 text-[10px]">
                        <span className="text-muted-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>{rel.total_calls} calls</span>
                        {rel.error_calls > 0 && <span style={{ color: "#ef4444", fontFamily: "var(--font-geist-mono)" }}>{rel.error_calls} err</span>}
                        <span className="text-muted-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>{Math.round(rel.avg_latency_ms)}ms</span>
                        <div className="w-10 h-1.5 rounded-full overflow-hidden" style={{ background: "hsl(var(--border))" }}>
                          <div className="h-full rounded-full" style={{ width: `${Math.min(100, rel.success_rate_pct)}%`, background: errColor }} />
                        </div>
                      </div>
                    ) : (
                      <span className="text-[10px] text-muted-foreground flex-shrink-0">schema only</span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )
      )}
    </div>
  );
}

/* ── Page ───────────────────────────────────────────────────── */
export default function AgentsPage() {
  const { activeProject } = useProject();
  const p = activeProject?.id ? `&project_id=${activeProject.id}` : "";
  const [hours, setHours] = useState(24);
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [sidebarSearch, setSidebarSearch] = useState("");
  const [activeTab, setActiveTab] = useState<DetailTab>("about");
  const [sessionFilter, setSessionFilter] = useState<"all" | "clean" | "failed">("all");
  const [showGlobalTopology, setShowGlobalTopology] = useState(false);
  const [globalTopoSelected, setGlobalTopoSelected] = useState<string | null>(null);
  const [railExpanded, setRailExpanded] = useState(false);

  // Layout state
  const isTopologyTab = selectedAgent !== null && activeTab === "topology";
  const sidebarMode: "none" | "list" | "rail" = !selectedAgent ? "none" : (isTopologyTab && !railExpanded) ? "rail" : "list";

  // Data — staggered refresh intervals to avoid thundering herd at page load
  const { data: sessions, isLoading } = useSWR<AgentSession[]>(`/api/agents/sessions?hours=${hours}&limit=100${p}`, fetcher, { refreshInterval: 30_000 });
  const { data: costs } = useSWR<CostsBreakdownResponse>(`/api/costs/breakdown?hours=${hours}${p}`, () => getCostsBreakdown(hours, activeProject?.id), { refreshInterval: 60_000 });
  const { data: lineage, isLoading: lineageLoading } = useSWR<LineageGraph>(`/api/agents/lineage?hours=${hours}${p}`, fetcher, { refreshInterval: 120_000 });
  const pid = activeProject?.id ?? null;
  const { data: metadata, mutate: mutateMetadata } = useSWR<AgentMetadata[]>(`/api/agents/metadata${p}`, () => listAgentMetadata(pid), { refreshInterval: 300_000 });
  const { data: healthServers } = useSWR<HealthResult[]>("/api/health/servers", fetcher, { refreshInterval: 30_000 });
  const { data: toolReliability } = useSWR<ToolReliability[]>(`/api/reliability/tools?hours=${hours}${p}`, fetcher, { refreshInterval: 60_000 });
  const { data: loopCounts } = useSWR<{ agent_name: string; loop_count: number }[]>(
    `/api/agents/loop-counts?hours=${hours}${p}`,
    () => getAgentLoopCounts(hours, pid),
    { refreshInterval: 120_000 },
  );
  const loopByAgent = useMemo(() => new Map((loopCounts ?? []).map(l => [l.agent_name, l.loop_count])), [loopCounts]);
  const { data: sloStatuses, mutate: mutateSlos } = useSWR<SLOStatus[]>(
    `/api/slos/status${p}`,
    () => getSLOStatus(pid),
    { refreshInterval: 120_000 },
  );
  // Worst SLO status per agent: breached > no_data > ok
  const sloByAgent = useMemo(() => {
    const m = new Map<string, "ok" | "breached" | "no_data">();
    for (const s of sloStatuses ?? []) {
      const cur = m.get(s.agent_name);
      if (!cur || (s.status === "breached") || (s.status === "no_data" && cur === "ok")) {
        m.set(s.agent_name, s.status);
      }
    }
    return m;
  }, [sloStatuses]);

  const metaByName = useMemo(() => { const m = new Map<string, AgentMetadata>(); for (const meta of metadata ?? []) m.set(meta.agent_name, meta); return m; }, [metadata]);
  const agents = useMemo(() => sessions ? aggregateAgents(sessions, costs) : [], [sessions, costs]);
  const selected = useMemo(() => agents.find((a) => a.agent_name === selectedAgent) ?? null, [agents, selectedAgent]);

  const selectedSessions = useMemo(() => {
    if (!selected || !sessions) return [];
    return sessions.filter((s) => s.agent_name === selected.agent_name)
      .filter((s) => sessionFilter === "all" || (sessionFilter === "clean" ? s.failed_calls === 0 : s.failed_calls > 0))
      .sort((a, b) => new Date(b.first_call_at).getTime() - new Date(a.first_call_at).getTime())
      .slice(0, 20);
  }, [selected, sessions, sessionFilter]);

  const toolBreakdown = useMemo(() => {
    if (!selected || !lineage) return [];
    const agentId = `agent:${selected.agent_name}`;
    return lineage.edges.filter((e) => e.source === agentId && e.type === "calls").map((e) => {
      const node = lineage.nodes.find((n) => n.id === e.target);
      return { server: node?.label ?? e.target.replace("server:", ""), calls: e.metrics.call_count ?? 0, errors: e.metrics.error_count ?? 0, avgLatency: e.metrics.avg_latency_ms ?? 0, errorRate: (e.metrics.call_count ?? 0) > 0 ? ((e.metrics.error_count ?? 0) / (e.metrics.call_count ?? 0)) * 100 : 0 };
    }).sort((a, b) => b.calls - a.calls);
  }, [selected, lineage]);

  const handoffTargets = useMemo(() => { if (!selected || !lineage) return []; const id = `agent:${selected.agent_name}`; return lineage.edges.filter((e) => e.source === id && e.type === "handoff").map((e) => e.target.replace("agent:", "")); }, [selected, lineage]);
  const handoffSources = useMemo(() => { if (!selected || !lineage) return []; const id = `agent:${selected.agent_name}`; return lineage.edges.filter((e) => e.target === id && e.type === "handoff").map((e) => e.source.replace("agent:", "")); }, [selected, lineage]);

  const globalTopoData = useMemo(() => {
    if (!lineage) return { nodes: [] as GraphNode[], edges: [] as GraphEdge[] };
    return {
      nodes: lineage.nodes.map((n) => ({ id: n.id, type: n.type, label: n.label, hasError: (n.metrics.error_count ?? 0) > 0, callCount: n.metrics.total_calls ?? 0, errorCount: n.metrics.error_count ?? 0, avgLatencyMs: n.metrics.avg_latency_ms ?? 0 })),
      edges: lineage.edges.map((e) => ({ source: e.source, target: e.target, type: e.type, label: e.type === "calls" ? (e.metrics.call_count > 1 ? `${e.metrics.call_count}×` : undefined) : (e.metrics.handoff_count > 1 ? `${e.metrics.handoff_count}×` : undefined), errorCount: e.metrics.error_count ?? 0, avgLatencyMs: e.metrics.avg_latency_ms ?? 0 })),
    };
  }, [lineage]);

  function selectAgent(name: string) { setSelectedAgent(selectedAgent === name ? null : name); setActiveTab("about"); setSessionFilter("all"); setRailExpanded(false); }

  const timeWindows = [{ label: "1h", value: 1 }, { label: "6h", value: 6 }, { label: "24h", value: 24 }, { label: "7d", value: 168 }];

  return (
    <div className="flex flex-col page-in" style={{ height: "calc(100vh - 8rem)" }}>
      {/* ── Header ── */}
      <div className="flex-shrink-0 flex items-center justify-between mb-4">
        <div>
          <h1 className="text-xl font-bold text-foreground">Agents</h1>
          <p className="text-[12px] text-muted-foreground mt-0.5">
            {isLoading ? "Loading…" : `${agents.length} agent${agents.length !== 1 ? "s" : ""} · last ${hours}h`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center rounded-lg overflow-hidden" style={{ border: "1px solid hsl(var(--border))" }}>
            {timeWindows.map((tw) => (
              <button key={tw.value} onClick={() => setHours(tw.value)} className={cn("px-2.5 py-1 text-[11px] font-medium transition-colors", hours === tw.value ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground hover:bg-accent/40")}>{tw.label}</button>
            ))}
          </div>
          <button onClick={() => setShowGlobalTopology(true)} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-medium text-muted-foreground hover:text-foreground hover:bg-accent/40 transition-colors" style={{ border: "1px solid hsl(var(--border))" }}>
            <Network size={12} /> Topology
          </button>
        </div>
      </div>

      {/* ── Content ── */}
      {isLoading ? (
        <div className="flex-1 space-y-2">
          {[1, 2, 3].map((i) => <div key={i} className="skeleton h-12 w-full rounded-xl" />)}
        </div>
      ) : agents.length === 0 ? (
        <div className="flex-1 flex flex-col items-center justify-center rounded-xl border" style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}>
          <Bot size={28} className="mb-3 text-muted-foreground opacity-40" />
          <p className="text-sm font-semibold text-foreground mb-1">No agents found</p>
          <p className="text-xs text-muted-foreground">Instrument your agents with the LangSight SDK</p>
        </div>
      ) : (
        <>
          {/* State 1: No agent selected — full-width table */}
          {!selectedAgent && (
            <div className="flex-1 min-h-0">
              <AgentTable agents={agents} metaByName={metaByName} onSelect={selectAgent} hours={hours} loopByAgent={loopByAgent} sloByAgent={sloByAgent} />
            </div>
          )}

          {/* States 2 & 3: Sidebar + detail */}
          {selectedAgent && selected && (
            <div className="flex-1 min-h-0 flex rounded-xl border overflow-hidden" style={{ borderColor: "hsl(var(--border))" }}>
              {/* Left sidebar */}
              <div className="flex-shrink-0 transition-all duration-200" style={{ width: sidebarMode === "rail" ? 56 : 280 }}>
                {sidebarMode === "rail" ? (
                  <AgentRail agents={agents} selectedAgent={selectedAgent} onSelect={selectAgent} onExpand={() => setRailExpanded(true)} />
                ) : (
                  <GroupedSidebar agents={agents} metaByName={metaByName} selectedAgent={selectedAgent} onSelect={selectAgent} search={sidebarSearch} onSearchChange={setSidebarSearch} />
                )}
              </div>

              {/* Right detail */}
              <div className="flex-1 min-w-0 flex flex-col" style={{ background: "hsl(var(--background))" }}>
                {/* Agent header */}
                <div className="flex-shrink-0 px-5 pt-4 pb-3 border-b" style={{ borderColor: "hsl(var(--border))", background: "hsl(var(--card))" }}>
                  <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-xl flex items-center justify-center" style={{ background: "hsl(var(--primary) / 0.08)" }}>
                      <Bot size={16} style={{ color: "hsl(var(--primary))" }} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-[14px] font-bold text-foreground truncate" style={{ fontFamily: "var(--font-geist-mono)" }}>{selected.agent_name}</p>
                      <div className="flex items-center gap-2 mt-0.5">
                        <span className="w-1.5 h-1.5 rounded-full" style={{ background: STATUS_COLOR[selected.status] }} />
                        <span className="text-[11px]" style={{ color: STATUS_COLOR[selected.status] }}>{selected.status}</span>
                        <span className="text-[10px] text-muted-foreground">· {selected.sessions} sessions · <Timestamp iso={selected.latest_started_at} /></span>
                      </div>
                    </div>
                    <button onClick={() => setSelectedAgent(null)} className="p-1.5 rounded hover:bg-accent/60 text-muted-foreground hover:text-foreground transition-colors">
                      <X size={14} />
                    </button>
                  </div>
                  {/* Tabs */}
                  <div className="flex mt-3 -mb-3">
                    {(["about", "overview", "servers", "topology", "sessions", "slos"] as DetailTab[]).map((tab) => {
                      const badge = tab === "servers" ? (selected.servers_used.length) : 0;
                      return (
                        <button key={tab} onClick={() => { setActiveTab(tab); if (tab !== "topology") setRailExpanded(false); }}
                          className={cn("px-3 py-2 text-[12px] font-medium border-b-2 -mb-px transition-colors capitalize", activeTab === tab ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground")}>
                          {tab}{badge > 0 && <span className="ml-1 text-[9px] text-muted-foreground">{badge}</span>}
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* Tab content */}
                {activeTab === "topology" ? (
                  <div className="flex-1 min-h-0">
                    <AgentTopology agentName={selected.agent_name} lineageGraph={lineage} isLoading={lineageLoading} className="h-full" />
                  </div>
                ) : (
                  <div className="flex-1 overflow-y-auto p-5">
                    {/* ABOUT */}
                    {activeTab === "about" && (() => {
                      const meta = metaByName.get(selected.agent_name);
                      async function saveMeta(field: string, value: string | string[]) {
                        const current = meta ?? { description: "", owner: "", tags: [] as string[], status: "active" as const, runbook_url: "" };
                        await upsertAgentMetadata(selected!.agent_name, { ...current, [field]: value }, pid);
                        mutateMetadata();
                      }
                      const serverHealthMap = new Map<string, string>();
                      for (const h of healthServers ?? []) serverHealthMap.set(h.server_name, h.status);
                      return (
                        <div className="space-y-5">
                          <div><p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-1.5">Description</p><EditableTextarea value={meta?.description ?? ""} onSave={(v) => saveMeta("description", v)} placeholder="What does this agent do? Click to add..." /></div>
                          <div><p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-1.5">Owner</p><EditableText value={meta?.owner ?? ""} onSave={(v) => saveMeta("owner", v)} placeholder="Team or person name" /></div>
                          <div><p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-1.5">Tags</p><EditableTags tags={meta?.tags ?? []} onSave={(v) => saveMeta("tags", v)} /></div>
                          <div>
                            <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-1.5">Status</p>
                            <div className="flex items-center gap-3">
                              {(["active", "deprecated", "experimental"] as const).map((s) => (
                                <label key={s} className="flex items-center gap-1.5 cursor-pointer text-[11px]">
                                  <input type="radio" name="agent-status" checked={(meta?.status ?? "active") === s} onChange={() => saveMeta("status", s)} className="w-3 h-3 accent-primary" />
                                  <span className={cn("capitalize", (meta?.status ?? "active") === s ? "text-foreground font-medium" : "text-muted-foreground")}>{s}</span>
                                </label>
                              ))}
                            </div>
                          </div>
                          <div><p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-1.5">Runbook / Docs</p><EditableUrl value={meta?.runbook_url ?? ""} onSave={(v) => saveMeta("runbook_url", v)} placeholder="https://wiki.example.com/..." /></div>
                          <div className="border-t pt-4" style={{ borderColor: "hsl(var(--border))" }}>
                            <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-3">Health Summary</p>
                            <div className="space-y-2">
                              <div className="flex items-center justify-between text-[11px]"><span className="text-muted-foreground">Error Rate</span><span className="font-semibold" style={{ fontFamily: "var(--font-geist-mono)", color: selected.error_rate > 0.05 ? "#ef4444" : "#22c55e" }}>{(selected.error_rate * 100).toFixed(1)}%</span></div>
                              <div className="flex items-center justify-between text-[11px]"><span className="text-muted-foreground">Last Active</span><span className="font-medium text-foreground"><Timestamp iso={selected.latest_started_at} /></span></div>
                              <div className="flex items-center justify-between text-[11px]"><span className="text-muted-foreground">Sessions ({hours}h)</span><span className="font-semibold text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>{selected.sessions}</span></div>
                              {selected.servers_used.length > 0 && (
                                <div><span className="text-[11px] text-muted-foreground">Servers</span>
                                  <div className="flex flex-wrap gap-1.5 mt-1">
                                    {selected.servers_used.map((srv) => { const health = serverHealthMap.get(srv); const color = health === "up" ? "#22c55e" : health === "degraded" ? "#eab308" : health === "down" ? "#ef4444" : "#6b7280"; return <span key={srv} className="inline-flex items-center gap-1.5 text-[10px] px-2 py-0.5 rounded-lg" style={{ background: "hsl(var(--muted))", fontFamily: "var(--font-geist-mono)" }}><span className="w-1.5 h-1.5 rounded-full" style={{ background: color }} />{srv}</span>; })}
                                  </div>
                                </div>
                              )}
                              {handoffTargets.length > 0 && <div className="flex items-center justify-between text-[11px]"><span className="text-muted-foreground">Delegates to</span><span className="font-medium text-foreground">{handoffTargets.join(", ")}</span></div>}
                              {handoffSources.length > 0 && <div className="flex items-center justify-between text-[11px]"><span className="text-muted-foreground">Called by</span><span className="font-medium text-foreground">{handoffSources.join(", ")}</span></div>}
                            </div>
                          </div>
                        </div>
                      );
                    })()}

                    {/* SERVERS */}
                    {activeTab === "servers" && (() => {
                      const serverHealthMap = new Map((healthServers ?? []).map(h => [h.server_name, h.status]));
                      const servers = selected.servers_used;
                      if (servers.length === 0) return (
                        <div className="text-center py-12">
                          <Server size={22} className="text-muted-foreground opacity-30 mx-auto mb-3" />
                          <p className="text-[12px] font-semibold text-foreground mb-1">No servers observed</p>
                          <p className="text-[11px] text-muted-foreground">Run your agent — server connections appear from trace data</p>
                        </div>
                      );
                      return (
                        <div className="space-y-3">
                          <p className="text-[10px] text-muted-foreground">
                            Showing {servers.length} MCP server{servers.length !== 1 ? "s" : ""} observed in the last {hours}h.
                            Call stats are across all agents on these servers.
                          </p>
                          {servers.map((srv) => (
                            <ServerToolsCard
                              key={srv}
                              serverName={srv}
                              reliability={(toolReliability ?? []).filter(r => r.server_name === srv)}
                              healthStatus={serverHealthMap.get(srv)}
                              isMcpServer={serverHealthMap.has(srv)}
                              projectId={pid}
                            />
                          ))}
                        </div>
                      );
                    })()}

                    {/* OVERVIEW */}
                    {activeTab === "overview" && (
                      <div className="space-y-5">
                        <div className="divide-y" style={{ borderColor: "hsl(var(--border) / 0.5)" }}>
                          <StatTile label="Sessions" value={selected.sessions.toLocaleString()} />
                          <StatTile label="Tool Calls" value={selected.tool_calls.toLocaleString()} />
                          <StatTile label="Failures" value={selected.failed_calls.toLocaleString()} danger={selected.failed_calls > 0} />
                          <StatTile label="Error Rate" value={`${(selected.error_rate * 100).toFixed(1)}%`} danger={selected.error_rate > 0.05} />
                          <StatTile label="Avg Duration" value={formatDuration(selected.avg_duration_ms)} />
                          <StatTile label="Total Cost" value={formatUsd(selected.total_cost_usd)} />
                        </div>
                        {toolBreakdown.length > 0 && (
                          <div>
                            <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-2">Servers & Tools</p>
                            <div className="space-y-1">
                              {toolBreakdown.map((t) => (
                                <div key={t.server} className="flex items-center justify-between rounded-lg px-3 py-2.5" style={{ background: "hsl(var(--muted))" }}>
                                  <div className="flex items-center gap-2"><Server size={11} className="text-muted-foreground" /><span className="text-[12px] font-medium text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>{t.server}</span></div>
                                  <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
                                    <span style={{ fontFamily: "var(--font-geist-mono)" }}>{t.calls} calls</span>
                                    {t.errors > 0 && <span style={{ color: "#ef4444", fontFamily: "var(--font-geist-mono)" }}>{t.errors} err</span>}
                                    <span style={{ fontFamily: "var(--font-geist-mono)" }}>{Math.round(t.avgLatency)}ms</span>
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                        {(handoffTargets.length > 0 || handoffSources.length > 0) && (
                          <div>
                            <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-2">Handoffs</p>
                            {handoffTargets.length > 0 && <div className="mb-2"><span className="text-[9px] text-muted-foreground">Delegates to: </span>{handoffTargets.map((t) => <span key={t} className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-lg mr-1" style={{ background: "hsl(var(--primary) / 0.06)", color: "hsl(var(--primary))", fontFamily: "var(--font-geist-mono)" }}><GitBranch size={9} />{t}</span>)}</div>}
                            {handoffSources.length > 0 && <div><span className="text-[9px] text-muted-foreground">Called by: </span>{handoffSources.map((s) => <span key={s} className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-lg mr-1" style={{ background: "hsl(var(--muted))", fontFamily: "var(--font-geist-mono)" }}><Bot size={9} />{s}</span>)}</div>}
                          </div>
                        )}
                      </div>
                    )}

                    {/* SESSIONS */}
                    {activeTab === "sessions" && (
                      <div>
                        <div className="flex items-center gap-1 mb-3">
                          {(["all", "clean", "failed"] as const).map((f) => {
                            const count = f === "all" ? selected.sessions : f === "clean" ? sessions?.filter((s) => s.agent_name === selected.agent_name && s.failed_calls === 0).length ?? 0 : sessions?.filter((s) => s.agent_name === selected.agent_name && s.failed_calls > 0).length ?? 0;
                            return <button key={f} onClick={() => setSessionFilter(f)} className={cn("px-2 py-1 rounded text-[10px] font-medium transition-all capitalize", sessionFilter === f ? "text-foreground bg-accent" : "text-muted-foreground hover:text-foreground")}>{f} <span className="text-muted-foreground">{count}</span></button>;
                          })}
                        </div>
                        <div className="divide-y" style={{ borderColor: "hsl(var(--border) / 0.5)" }}>
                          {selectedSessions.map((s) => (
                            <Link key={s.session_id} href={`/sessions/${s.session_id}`} className="flex items-center justify-between py-2 hover:bg-accent/20 transition-colors -mx-1 px-1 rounded">
                              <div className="flex items-center gap-2 min-w-0">
                                <span className={cn("w-1.5 h-1.5 rounded-full flex-shrink-0", s.failed_calls > 0 ? "bg-red-500" : "bg-emerald-500")} />
                                <span className="text-[10px] font-medium text-foreground truncate" style={{ fontFamily: "var(--font-geist-mono)" }}>{s.session_id.slice(0, 20)}</span>
                              </div>
                              <div className="flex items-center gap-2.5 text-[9px] text-muted-foreground flex-shrink-0">
                                <span>{s.tool_calls} {s.tool_calls === 1 ? "call" : "calls"}</span>
                                {s.failed_calls > 0 && <span style={{ color: "#ef4444" }}>{s.failed_calls} failed</span>}
                                <span style={{ fontFamily: "var(--font-geist-mono)" }}>{formatDuration(s.duration_ms)}</span>
                                <Timestamp iso={s.first_call_at} compact />
                                <ChevronRight size={10} />
                              </div>
                            </Link>
                          ))}
                          {selectedSessions.length === 0 && <p className="text-[11px] text-muted-foreground text-center py-6">No sessions match</p>}
                        </div>
                        {selected.sessions > 20 && <Link href={`/sessions?agent=${selected.agent_name}`} className="block text-center text-[11px] text-primary hover:underline mt-3">View all {selected.sessions} sessions →</Link>}
                      </div>
                    )}

                    {/* SLOS */}
                    {activeTab === "slos" && (() => {
                      const agentSlos = (sloStatuses ?? []).filter(s => s.agent_name === selected.agent_name);
                      return <SLOTab agentName={selected.agent_name} slos={agentSlos} projectId={pid} onRefresh={() => mutateSlos()} />;
                    })()}
                  </div>
                )}
              </div>
            </div>
          )}
        </>
      )}

      {/* Global Topology Modal */}
      <Dialog.Root open={showGlobalTopology} onOpenChange={setShowGlobalTopology}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm" style={{ animation: "fadeIn 0.15s ease" }} />
          <Dialog.Content className="fixed z-50 rounded-2xl overflow-hidden flex flex-col" style={{ top: "5vh", left: "2.5vw", width: "95vw", height: "90vh", background: "hsl(var(--background))", border: "1px solid hsl(var(--border))", boxShadow: "0 24px 64px rgba(0,0,0,0.3)" }}>
            <div className="flex items-center justify-between px-5 py-3 border-b flex-shrink-0" style={{ borderColor: "hsl(var(--border))", background: "hsl(var(--card))" }}>
              <div className="flex items-center gap-2">
                <Network size={14} style={{ color: "hsl(var(--primary))" }} />
                <span className="text-[13px] font-semibold text-foreground">Global Agent Topology</span>
                <span className="text-[10px] text-muted-foreground">· {globalTopoData.nodes.length} nodes · {globalTopoData.edges.length} edges · last {hours}h</span>
              </div>
              <Dialog.Close asChild><button className="p-1.5 rounded hover:bg-accent/60 text-muted-foreground hover:text-foreground transition-colors"><X size={16} /></button></Dialog.Close>
            </div>
            <div className="flex-1 relative">
              {globalTopoData.nodes.length > 0 ? (
                <LineageGraphComponent nodes={globalTopoData.nodes} edges={globalTopoData.edges} selectedId={globalTopoSelected} onSelect={setGlobalTopoSelected} className="h-full" />
              ) : (
                <div className="flex items-center justify-center h-full text-muted-foreground"><p className="text-sm">No topology data available</p></div>
              )}
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </div>
  );
}
