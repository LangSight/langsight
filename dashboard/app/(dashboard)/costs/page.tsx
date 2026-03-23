"use client";

import type { ReactNode } from "react";
import { useMemo, useState } from "react";
import useSWR from "swr";
import { Database, DollarSign, Layers3, Wallet, Cpu, Wrench, Filter, X } from "lucide-react";
import { getCostsBreakdown } from "@/lib/api";
import { useProject } from "@/lib/project-context";
import type { CostsBreakdownResponse } from "@/lib/types";
import { cn } from "@/lib/utils";
import { DateRangeFilter } from "@/components/date-range-filter";

function formatUsd(v: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency", currency: "USD",
    minimumFractionDigits: 2, maximumFractionDigits: 4,
  }).format(v);
}

/* ── Summary card ───────────────────────────────────────────── */
function SummaryCard({ title, value, icon, sub }: {
  title: string; value: string; icon: ReactNode; sub?: string;
}) {
  return (
    <div
      className="rounded-xl border p-5 flex flex-col gap-3"
      style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
    >
      <div className="flex items-start justify-between">
        <div
          className="w-9 h-9 rounded-lg flex items-center justify-center"
          style={{ background: "hsl(var(--primary) / 0.1)" }}
        >
          <span style={{ color: "hsl(var(--primary))" }}>{icon}</span>
        </div>
      </div>
      <div>
        <p className="text-2xl font-bold text-foreground leading-none mb-1">{value}</p>
        <p className="text-[13px] font-medium text-foreground/80">{title}</p>
        {sub && <p className="text-[11px] text-muted-foreground mt-0.5">{sub}</p>}
      </div>
    </div>
  );
}

/* ── Filter pill ───────────────────────────────────────────── */
function FilterPill({ label, value, onClear }: {
  label: string; value: string; onClear: () => void;
}) {
  return (
    <span
      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-semibold"
      style={{ background: "hsl(var(--primary) / 0.1)", color: "hsl(var(--primary))" }}
    >
      <span className="text-muted-foreground">{label}:</span>
      {value}
      <button onClick={onClear} className="hover:opacity-70 ml-0.5"><X size={10} /></button>
    </span>
  );
}

/* ── Empty state ────────────────────────────────────────────── */
function EmptyState({ title, description, body }: {
  title: string; description: string; body: ReactNode;
}) {
  return (
    <div
      className="rounded-xl border p-12 text-center"
      style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
    >
      <div
        className="w-14 h-14 rounded-2xl flex items-center justify-center mx-auto mb-4"
        style={{ background: "hsl(var(--muted))" }}
      >
        <DollarSign size={22} className="text-muted-foreground" />
      </div>
      <p className="text-base font-bold text-foreground mb-2">{title}</p>
      <p className="text-sm text-muted-foreground mb-6 max-w-md mx-auto">{description}</p>
      <div
        className="rounded-xl p-4 text-left inline-block text-sm max-w-md"
        style={{ background: "hsl(var(--muted))", color: "hsl(var(--muted-foreground))" }}
      >
        {body}
      </div>
    </div>
  );
}

/* ── Page ───────────────────────────────────────────────────── */
export default function CostsPage() {
  const [hours, setHours] = useState<number>(24);
  const [customFrom, setCustomFrom] = useState<string | null>(null);
  const [customTo, setCustomTo] = useState<string | null>(null);
  const { activeProject } = useProject();

  // Filters
  const [serverFilter, setServerFilter] = useState<string | null>(null);
  const [agentFilter, setAgentFilter] = useState<string | null>(null);
  const [modelFilter, setModelFilter] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState<"all" | "token_based" | "call_based">("all");

  const { data, error, isLoading } = useSWR<CostsBreakdownResponse>(
    `/api/costs/breakdown?hours=${hours}${activeProject ? `&project_id=${activeProject.id}` : ""}`,
    () => getCostsBreakdown(hours, activeProject?.id),
    { refreshInterval: 30_000 }
  );

  // Derive unique values for filter dropdowns
  const servers = useMemo(() => [...new Set(data?.by_tool.map((e) => e.server_name) ?? [])].sort(), [data]);
  const agents = useMemo(() => [...new Set(data?.by_agent.map((e) => e.agent_name) ?? [])].sort(), [data]);
  const models = useMemo(() => [...new Set(data?.by_tool.filter((e) => e.model_id).map((e) => e.model_id!) ?? [])].sort(), [data]);

  // Filtered data
  const filteredTools = useMemo(() => {
    if (!data) return [];
    return data.by_tool.filter((e) => {
      if (serverFilter && e.server_name !== serverFilter) return false;
      if (modelFilter && e.model_id !== modelFilter) return false;
      if (typeFilter !== "all" && e.cost_type !== typeFilter) return false;
      return true;
    });
  }, [data, serverFilter, modelFilter, typeFilter]);

  const filteredAgents = useMemo(() => {
    if (!data) return [];
    if (!agentFilter) return data.by_agent;
    return data.by_agent.filter((e) => e.agent_name === agentFilter);
  }, [data, agentFilter]);

  const filteredSessions = useMemo(() => {
    if (!data) return [];
    if (!agentFilter) return data.by_session;
    return data.by_session.filter((e) => e.agent_name === agentFilter);
  }, [data, agentFilter]);

  // Filtered totals
  const filteredTotal = filteredTools.reduce((sum, e) => sum + e.total_cost_usd, 0);
  const filteredCalls = filteredTools.reduce((sum, e) => sum + e.total_calls, 0);
  const hasFilters = serverFilter || agentFilter || modelFilter || typeFilter !== "all";

  function clearAll() {
    setServerFilter(null);
    setAgentFilter(null);
    setModelFilter(null);
    setTypeFilter("all");
  }

  return (
    <div className="space-y-5 page-in">
      {/* ── Header ────────────────────────────────────────────── */}
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-foreground">Cost Attribution</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Filter by server, agent, model, or cost type to explore spend
          </p>
        </div>
        <DateRangeFilter
          activeHours={hours}
          onPreset={(h) => { setHours(h); setCustomFrom(null); setCustomTo(null); }}
          onCustomRange={(from, to) => { setCustomFrom(from); setCustomTo(to); }}
          onClearCustom={() => { setCustomFrom(null); setCustomTo(null); }}
          customFrom={customFrom}
          customTo={customTo}
        />
      </div>

      {isLoading ? (
        <div className="grid md:grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div
              key={i}
              className="rounded-xl border p-5 space-y-3"
              style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
            >
              <div className="skeleton w-9 h-9 rounded-lg" />
              <div className="skeleton h-7 w-20 rounded" />
              <div className="skeleton h-3 w-28 rounded" />
            </div>
          ))}
        </div>
      ) : error ? (
        <EmptyState
          title="Could not load costs"
          description="The dashboard could not reach the cost attribution API."
          body={<p>Check that the LangSight API is running and reachable.</p>}
        />
      ) : !data?.supports_costs ? (
        <EmptyState
          title="Cost attribution requires ClickHouse"
          description="This instance is not using a backend that exposes traced tool-call counts."
          body={
            <>
              <div className="flex items-start gap-2 mb-3">
                <Database size={14} className="mt-0.5 flex-shrink-0" style={{ color: "hsl(var(--primary))" }} />
                <div>
                  <p className="font-semibold mb-0.5" style={{ color: "hsl(var(--foreground))" }}>What&apos;s needed</p>
                  <p>Run LangSight with <code className="mono-pill-primary">storage.mode: clickhouse</code> or <code className="mono-pill-primary">dual</code></p>
                </div>
              </div>
              <p className="text-xs">Current backend: <code className="mono-pill">{data?.storage_mode ?? "unknown"}</code></p>
            </>
          }
        />
      ) : data.by_tool.length === 0 ? (
        <EmptyState
          title="No traced tool calls yet"
          description="ClickHouse is ready but no spans are in the selected window."
          body={
            <>
              <p className="font-semibold mb-1" style={{ color: "hsl(var(--foreground))" }}>To start seeing costs</p>
              <p>Instrument an agent with the LangSight SDK or send OTLP spans.</p>
            </>
          }
        />
      ) : (
        <>
          {/* ── Filter bar ──────────────────────────────────────── */}
          <div
            className="rounded-xl border p-3 flex flex-wrap items-center gap-2"
            style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
          >
            <Filter size={13} className="text-muted-foreground mr-1" />

            <select
              value={serverFilter ?? ""}
              onChange={(e) => setServerFilter(e.target.value || null)}
              className="filter-select"
            >
              <option value="">All servers</option>
              {servers.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>

            <select
              value={agentFilter ?? ""}
              onChange={(e) => setAgentFilter(e.target.value || null)}
              className="filter-select"
            >
              <option value="">All agents</option>
              {agents.map((a) => <option key={a} value={a}>{a}</option>)}
            </select>

            {models.length > 0 && (
              <select
                value={modelFilter ?? ""}
                onChange={(e) => setModelFilter(e.target.value || null)}
                className="filter-select"
              >
                <option value="">All models</option>
                {models.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
            )}

            <select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value as typeof typeFilter)}
              className="filter-select"
            >
              <option value="all">All types</option>
              <option value="token_based">LLM (token)</option>
              <option value="call_based">Tool (per-call)</option>
            </select>

            {hasFilters && (
              <button
                onClick={clearAll}
                className="text-[11px] text-muted-foreground hover:text-foreground ml-auto flex items-center gap-1"
              >
                <X size={10} /> Clear all
              </button>
            )}
          </div>

          {/* Active filter pills */}
          {hasFilters && (
            <div className="flex flex-wrap gap-1.5">
              {serverFilter && <FilterPill label="Server" value={serverFilter} onClear={() => setServerFilter(null)} />}
              {agentFilter && <FilterPill label="Agent" value={agentFilter} onClear={() => setAgentFilter(null)} />}
              {modelFilter && <FilterPill label="Model" value={modelFilter} onClear={() => setModelFilter(null)} />}
              {typeFilter !== "all" && <FilterPill label="Type" value={typeFilter === "token_based" ? "LLM" : "Tool"} onClear={() => setTypeFilter("all")} />}
            </div>
          )}

          {/* Summary cards */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <SummaryCard
              title="Total Cost"
              value={formatUsd(hasFilters ? filteredTotal : data.total_cost_usd)}
              icon={<Wallet size={17} />}
              sub={`${(hasFilters ? filteredCalls : data.total_calls).toLocaleString()} calls${hasFilters ? " (filtered)" : ""}`}
            />
            <SummaryCard
              title="LLM Cost"
              value={formatUsd(filteredTools.filter((e) => e.cost_type === "token_based").reduce((s, e) => s + e.total_cost_usd, 0))}
              icon={<Cpu size={17} />}
              sub="token-based pricing"
            />
            <SummaryCard
              title="Tool Call Cost"
              value={formatUsd(filteredTools.filter((e) => e.cost_type === "call_based").reduce((s, e) => s + e.total_cost_usd, 0))}
              icon={<Wrench size={17} />}
              sub="call-based pricing"
            />
            <SummaryCard
              title="Total Calls"
              value={(hasFilters ? filteredCalls : data.total_calls).toLocaleString("en-US")}
              icon={<Layers3 size={17} />}
              sub={`${data.hours}h window`}
            />
          </div>

          {/* Token summary */}
          {filteredTools.some((e) => e.total_input_tokens > 0) && (
            <div
              className="rounded-xl border p-4 flex flex-wrap items-center gap-6"
              style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
            >
              {[
                { label: "Input Tokens",  value: filteredTools.reduce((s, e) => s + e.total_input_tokens, 0).toLocaleString() },
                { label: "Output Tokens", value: filteredTools.reduce((s, e) => s + e.total_output_tokens, 0).toLocaleString() },
              ].map((t, i) => (
                <div key={t.label} className="flex items-center gap-4">
                  {i > 0 && <div className="w-px h-8" style={{ background: "hsl(var(--border))" }} />}
                  <div>
                    <p className="text-[11px] font-medium text-muted-foreground mb-0.5">{t.label}</p>
                    <p className="text-lg font-bold text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>{t.value}</p>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* By Tool — the main table */}
          <div
            className="rounded-xl border overflow-hidden"
            style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
          >
            <div className="section-header flex items-center justify-between">
              <h2>Cost by Tool {hasFilters && <span className="text-muted-foreground font-normal">({filteredTools.length} results)</span>}</h2>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr style={{ borderBottom: "1px solid hsl(var(--border))", background: "hsl(var(--card-raised))" }}>
                    {["Server", "Tool", "Type", "Model", "Calls", "$/Call", "Total"].map((h) => (
                      <th key={h} className="px-5 py-2.5 text-left text-[11px] font-semibold text-muted-foreground uppercase tracking-wide">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y" style={{ borderColor: "hsl(var(--border))" }}>
                  {filteredTools
                    .sort((a, b) => b.total_cost_usd - a.total_cost_usd)
                    .map((entry) => (
                    <tr
                      key={`${entry.server_name}-${entry.tool_name}-${entry.model_id ?? ""}`}
                      className="hover:bg-accent/30 transition-colors cursor-pointer"
                      onClick={() => {
                        if (!serverFilter) setServerFilter(entry.server_name);
                        else if (!agentFilter && entry.model_id) setModelFilter(entry.model_id);
                      }}
                    >
                      <td className="px-5 py-3">
                        <code className="mono-pill">{entry.server_name}</code>
                      </td>
                      <td className="px-5 py-3 text-[13px] text-foreground">{entry.tool_name}</td>
                      <td className="px-5 py-3">
                        <span className={cn(
                          "text-[10px] px-1.5 py-0.5 rounded-full font-semibold",
                          entry.cost_type === "token_based" ? "badge-primary" : "badge-muted"
                        )}>
                          {entry.cost_type === "token_based" ? "LLM" : "tool"}
                        </span>
                      </td>
                      <td className="px-5 py-3 text-[13px] text-muted-foreground">
                        {entry.model_id ? <code className="mono-pill text-[10px]">{entry.model_id}</code> : "—"}
                      </td>
                      <td className="px-5 py-3 text-[13px] text-muted-foreground tabular-nums">
                        {entry.total_calls.toLocaleString("en-US")}
                      </td>
                      <td className="px-5 py-3 text-[13px] text-muted-foreground font-mono" style={{ fontFamily: "var(--font-geist-mono)" }}>
                        {formatUsd(entry.cost_per_call_usd)}
                      </td>
                      <td className="px-5 py-3 text-[13px] font-semibold text-foreground font-mono" style={{ fontFamily: "var(--font-geist-mono)" }}>
                        {formatUsd(entry.total_cost_usd)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* By Agent + By Session side by side */}
          <div className="grid lg:grid-cols-2 gap-4">
            <div
              className="rounded-xl border overflow-hidden"
              style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
            >
              <div className="section-header"><h2>By Agent</h2></div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr style={{ borderBottom: "1px solid hsl(var(--border))", background: "hsl(var(--card-raised))" }}>
                      {["Agent", "Calls", "Total Cost"].map((h) => (
                        <th key={h} className="px-5 py-2.5 text-left text-[11px] font-semibold text-muted-foreground uppercase tracking-wide">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y" style={{ borderColor: "hsl(var(--border))" }}>
                    {filteredAgents.map((entry) => (
                      <tr
                        key={entry.agent_name}
                        className="hover:bg-accent/30 transition-colors cursor-pointer"
                        onClick={() => setAgentFilter(agentFilter === entry.agent_name ? null : entry.agent_name)}
                      >
                        <td className="px-5 py-3 text-[13px] text-foreground flex items-center gap-2">
                          {agentFilter === entry.agent_name && <span className="w-1.5 h-1.5 rounded-full bg-primary" />}
                          {entry.agent_name}
                        </td>
                        <td className="px-5 py-3 text-[13px] text-muted-foreground tabular-nums">
                          {entry.total_calls.toLocaleString("en-US")}
                        </td>
                        <td className="px-5 py-3 text-[13px] font-semibold text-foreground font-mono" style={{ fontFamily: "var(--font-geist-mono)" }}>
                          {formatUsd(entry.total_cost_usd)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div
              className="rounded-xl border overflow-hidden"
              style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
            >
              <div className="section-header"><h2>Top Sessions</h2></div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr style={{ borderBottom: "1px solid hsl(var(--border))", background: "hsl(var(--card-raised))" }}>
                      {["Session", "Agent", "Calls", "Total"].map((h) => (
                        <th key={h} className="px-5 py-2.5 text-left text-[11px] font-semibold text-muted-foreground uppercase tracking-wide">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y" style={{ borderColor: "hsl(var(--border))" }}>
                    {filteredSessions.map((entry) => (
                      <tr key={entry.session_id} className="hover:bg-accent/30 transition-colors">
                        <td className="px-5 py-3">
                          <code className="text-[11px] text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>
                            {entry.session_id.slice(0, 16)}…
                          </code>
                        </td>
                        <td className="px-5 py-3 text-[13px] text-muted-foreground">{entry.agent_name ?? "—"}</td>
                        <td className="px-5 py-3 text-[13px] text-muted-foreground tabular-nums">
                          {entry.total_calls.toLocaleString("en-US")}
                        </td>
                        <td className="px-5 py-3 text-[13px] font-semibold text-foreground font-mono" style={{ fontFamily: "var(--font-geist-mono)" }}>
                          {formatUsd(entry.total_cost_usd)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
