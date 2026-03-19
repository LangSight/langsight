"use client";

import type { ReactNode } from "react";
import { useState } from "react";
import useSWR from "swr";
import { Database, DollarSign, Layers3, Wallet, Cpu, Wrench } from "lucide-react";
import { getCostsBreakdown } from "@/lib/api";
import { useProject } from "@/lib/project-context";
import type { CostsBreakdownResponse } from "@/lib/types";
import { cn } from "@/lib/utils";

const WINDOWS = [
  { label: "24h", hours: 24 },
  { label: "7d",  hours: 24 * 7 },
  { label: "30d", hours: 24 * 30 },
];

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

/* ── Section table ──────────────────────────────────────────── */
function SectionTable({ title, headers, rows }: {
  title: string; headers: string[]; rows: ReactNode;
}) {
  return (
    <div
      className="rounded-xl border overflow-hidden"
      style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
    >
      <div className="section-header">
        <h2>{title}</h2>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr style={{ borderBottom: "1px solid hsl(var(--border))", background: "hsl(var(--card-raised))" }}>
              {headers.map((header) => (
                <th
                  key={header}
                  className="px-5 py-2.5 text-left text-[11px] font-semibold text-muted-foreground uppercase tracking-wide"
                >
                  {header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y" style={{ borderColor: "hsl(var(--border))" }}>
            {rows}
          </tbody>
        </table>
      </div>
    </div>
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
  const { activeProject } = useProject();

  const { data, error, isLoading } = useSWR<CostsBreakdownResponse>(
    `/api/costs/breakdown?hours=${hours}${activeProject ? `&project_id=${activeProject.id}` : ""}`,
    () => getCostsBreakdown(hours, activeProject?.id),
    { refreshInterval: 30_000 }
  );

  return (
    <div className="space-y-5 page-in">
      {/* ── Header ────────────────────────────────────────────── */}
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-foreground">Cost Attribution</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Per-tool, per-agent, and per-session cost breakdown from traced tool calls
          </p>
        </div>
        <div
          className="flex rounded-lg border p-0.5"
          style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
        >
          {WINDOWS.map((w) => (
            <button
              key={w.hours}
              onClick={() => setHours(w.hours)}
              className={cn(
                "px-3 py-1.5 rounded-md text-xs font-medium transition-all",
                w.hours === hours
                  ? "bg-primary text-white shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              {w.label}
            </button>
          ))}
        </div>
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
          body={<p>Check that the LangSight API is running and reachable from the dashboard container.</p>}
        />
      ) : !data?.supports_costs ? (
        <EmptyState
          title="Cost attribution requires ClickHouse"
          description="This LangSight instance is not using a backend that exposes traced tool-call counts."
          body={
            <>
              <div className="flex items-start gap-2 mb-3">
                <Database size={14} className="mt-0.5 flex-shrink-0" style={{ color: "hsl(var(--primary))" }} />
                <div>
                  <p className="font-semibold mb-0.5" style={{ color: "hsl(var(--foreground))" }}>What&apos;s needed</p>
                  <p>1. Run LangSight with <code className="mono-pill-primary">storage.mode: clickhouse</code></p>
                  <p className="mt-1">2. Send traced spans through the SDK or OTLP endpoint</p>
                </div>
              </div>
              <p className="text-xs">Current backend: <code className="mono-pill">{data?.storage_mode ?? "unknown"}</code></p>
            </>
          }
        />
      ) : data.by_tool.length === 0 ? (
        <EmptyState
          title="No traced tool calls yet"
          description="ClickHouse is available, but there are no tool-call spans in the selected time window."
          body={
            <>
              <p className="font-semibold mb-1" style={{ color: "hsl(var(--foreground))" }}>To start seeing costs</p>
              <p>Instrument an agent with the LangSight SDK or send OTLP spans.</p>
              <p className="font-mono mt-2">uv run langsight costs</p>
            </>
          }
        />
      ) : (
        <>
          {/* Summary cards */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <SummaryCard
              title="Total Cost"
              value={formatUsd(data.total_cost_usd)}
              icon={<Wallet size={17} />}
              sub={`${data.total_calls.toLocaleString()} total calls`}
            />
            <SummaryCard
              title="LLM Cost"
              value={formatUsd(data.llm_cost_usd ?? 0)}
              icon={<Cpu size={17} />}
              sub="token-based pricing"
            />
            <SummaryCard
              title="Tool Call Cost"
              value={formatUsd(data.tool_cost_usd ?? 0)}
              icon={<Wrench size={17} />}
              sub="call-based pricing"
            />
            <SummaryCard
              title="Total Calls"
              value={data.total_calls.toLocaleString("en-US")}
              icon={<Layers3 size={17} />}
              sub={`${data.hours}h window`}
            />
          </div>

          {/* Token summary */}
          {(data.total_input_tokens ?? 0) > 0 && (
            <div
              className="rounded-xl border p-4 flex flex-wrap items-center gap-6"
              style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
            >
              {[
                { label: "Input Tokens",  value: (data.total_input_tokens ?? 0).toLocaleString() },
                { label: "Output Tokens", value: (data.total_output_tokens ?? 0).toLocaleString() },
                { label: "Total Tokens",  value: ((data.total_input_tokens ?? 0) + (data.total_output_tokens ?? 0)).toLocaleString() },
              ].map((t, i) => (
                <div key={t.label} className="flex items-center gap-4">
                  {i > 0 && <div className="w-px h-8" style={{ background: "hsl(var(--border))" }} />}
                  <div>
                    <p className="text-[11px] font-medium text-muted-foreground mb-0.5">{t.label}</p>
                    <p
                      className="text-lg font-bold text-foreground"
                      style={{ fontFamily: "var(--font-geist-mono)" }}
                    >
                      {t.value}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* By Model */}
          {data.by_tool.some((e) => e.cost_type === "token_based") && (
            <SectionTable
              title="By Model"
              headers={["Model", "Calls", "Input Tokens", "Output Tokens", "LLM Cost"]}
              rows={
                <>
                  {Object.values(
                    data.by_tool
                      .filter((e) => e.cost_type === "token_based" && e.model_id)
                      .reduce(
                        (acc: Record<string, { model_id: string; calls: number; inp: number; out: number; cost: number }>, e) => {
                          const k = e.model_id!;
                          if (!acc[k]) acc[k] = { model_id: k, calls: 0, inp: 0, out: 0, cost: 0 };
                          acc[k].calls += e.total_calls;
                          acc[k].inp   += e.total_input_tokens;
                          acc[k].out   += e.total_output_tokens;
                          acc[k].cost  += e.total_cost_usd;
                          return acc;
                        },
                        {}
                      )
                  )
                    .sort((a, b) => b.cost - a.cost)
                    .map((m) => (
                      <tr key={m.model_id}>
                        <td className="px-5 py-3">
                          <code className="mono-pill">{m.model_id}</code>
                        </td>
                        <td className="px-5 py-3 text-[13px] text-muted-foreground">
                          {m.calls.toLocaleString()}
                        </td>
                        <td className="px-5 py-3 text-[13px] text-muted-foreground font-mono" style={{ fontFamily: "var(--font-geist-mono)" }}>
                          {m.inp.toLocaleString()}
                        </td>
                        <td className="px-5 py-3 text-[13px] text-muted-foreground font-mono" style={{ fontFamily: "var(--font-geist-mono)" }}>
                          {m.out.toLocaleString()}
                        </td>
                        <td className="px-5 py-3 text-[13px] font-semibold text-foreground font-mono" style={{ fontFamily: "var(--font-geist-mono)" }}>
                          {formatUsd(m.cost)}
                        </td>
                      </tr>
                    ))}
                </>
              }
            />
          )}

          {/* By Tool */}
          <SectionTable
            title="By Tool"
            headers={["Server", "Tool", "Type", "Calls", "$/Call", "Total"]}
            rows={data.by_tool.map((entry) => (
              <tr key={`${entry.server_name}-${entry.tool_name}`} className="hover:bg-accent/30 transition-colors">
                <td className="px-5 py-3">
                  <code className="mono-pill">{entry.server_name}</code>
                </td>
                <td className="px-5 py-3 text-[13px] text-foreground">{entry.tool_name}</td>
                <td className="px-5 py-3">
                  <span
                    className={cn(
                      "text-[10px] px-1.5 py-0.5 rounded-full font-semibold",
                      entry.cost_type === "token_based" ? "badge-primary" : "badge-muted"
                    )}
                  >
                    {entry.cost_type === "token_based" ? "LLM" : "tool"}
                  </span>
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
          />

          {/* By Agent + By Session side by side */}
          <div className="grid lg:grid-cols-2 gap-4">
            <SectionTable
              title="By Agent"
              headers={["Agent", "Calls", "Total Cost"]}
              rows={data.by_agent.map((entry) => (
                <tr key={entry.agent_name} className="hover:bg-accent/30 transition-colors">
                  <td className="px-5 py-3 text-[13px] text-foreground">{entry.agent_name}</td>
                  <td className="px-5 py-3 text-[13px] text-muted-foreground tabular-nums">
                    {entry.total_calls.toLocaleString("en-US")}
                  </td>
                  <td className="px-5 py-3 text-[13px] font-semibold text-foreground font-mono" style={{ fontFamily: "var(--font-geist-mono)" }}>
                    {formatUsd(entry.total_cost_usd)}
                  </td>
                </tr>
              ))}
            />

            <SectionTable
              title="Top Sessions"
              headers={["Session", "Agent", "Calls", "Total"]}
              rows={data.by_session.map((entry) => (
                <tr key={entry.session_id} className="hover:bg-accent/30 transition-colors">
                  <td className="px-5 py-3">
                    <code
                      className="text-[11px] text-foreground"
                      style={{ fontFamily: "var(--font-geist-mono)" }}
                    >
                      {entry.session_id.slice(0, 16)}…
                    </code>
                  </td>
                  <td className="px-5 py-3 text-[13px] text-muted-foreground">
                    {entry.agent_name ?? "—"}
                  </td>
                  <td className="px-5 py-3 text-[13px] text-muted-foreground tabular-nums">
                    {entry.total_calls.toLocaleString("en-US")}
                  </td>
                  <td className="px-5 py-3 text-[13px] font-semibold text-foreground font-mono" style={{ fontFamily: "var(--font-geist-mono)" }}>
                    {formatUsd(entry.total_cost_usd)}
                  </td>
                </tr>
              ))}
            />
          </div>
        </>
      )}
    </div>
  );
}
