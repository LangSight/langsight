"use client";

import type { ReactNode } from "react";
import { useState } from "react";
import useSWR from "swr";
import { Database, DollarSign, Layers3, Wallet, Cpu, Wrench } from "lucide-react";

import { getCostsBreakdown } from "@/lib/api";
import type { CostsBreakdownResponse } from "@/lib/types";

const WINDOWS = [
  { label: "24h", hours: 24 },
  { label: "7d", hours: 24 * 7 },
  { label: "30d", hours: 24 * 30 },
];

function formatUsd(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  }).format(value);
}

function SummaryCard({
  title,
  value,
  icon,
}: {
  title: string;
  value: string;
  icon: ReactNode;
}) {
  return (
    <div
      className="rounded-xl border p-4"
      style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
    >
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-medium" style={{ color: "hsl(var(--muted-foreground))" }}>
          {title}
        </span>
        <span style={{ color: "hsl(var(--primary))" }}>{icon}</span>
      </div>
      <p className="text-2xl font-bold" style={{ color: "hsl(var(--foreground))" }}>
        {value}
      </p>
    </div>
  );
}

function SectionTable({
  title,
  headers,
  rows,
}: {
  title: string;
  headers: string[];
  rows: ReactNode;
}) {
  return (
    <div
      className="rounded-xl border p-5"
      style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
    >
      <h2 className="text-sm font-semibold mb-4" style={{ color: "hsl(var(--foreground))" }}>
        {title}
      </h2>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr style={{ borderBottom: "1px solid hsl(var(--border))" }}>
              {headers.map((header) => (
                <th
                  key={header}
                  className="text-left pb-2 pr-4 font-medium"
                  style={{ color: "hsl(var(--muted-foreground))" }}
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

function EmptyState({
  title,
  description,
  body,
}: {
  title: string;
  description: string;
  body: ReactNode;
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
        <DollarSign size={24} style={{ color: "hsl(var(--primary))" }} />
      </div>
      <p className="text-lg font-bold mb-2" style={{ color: "hsl(var(--foreground))" }}>
        {title}
      </p>
      <p className="text-sm mb-6 max-w-md mx-auto" style={{ color: "hsl(var(--muted-foreground))" }}>
        {description}
      </p>
      <div
        className="rounded-lg p-4 text-left inline-block text-sm"
        style={{ background: "hsl(var(--muted))", color: "hsl(var(--muted-foreground))" }}
      >
        {body}
      </div>
    </div>
  );
}

export default function CostsPage() {
  const [hours, setHours] = useState<number>(24);
  const { data, error, isLoading } = useSWR<CostsBreakdownResponse>(
    `/api/costs/breakdown?hours=${hours}`,
    () => getCostsBreakdown(hours),
    { refreshInterval: 30_000 },
  );

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold" style={{ color: "hsl(var(--foreground))" }}>
            Cost Attribution
          </h1>
          <p className="text-sm" style={{ color: "hsl(var(--muted-foreground))" }}>
            Per-tool, per-agent, and per-session cost breakdown from traced tool calls
          </p>
        </div>
        <div
          className="inline-flex rounded-lg border p-1"
          style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
        >
          {WINDOWS.map((window) => (
            <button
              key={window.hours}
              onClick={() => setHours(window.hours)}
              className="px-3 py-1.5 rounded-md text-sm font-medium transition-colors"
              style={{
                background: window.hours === hours ? "hsl(var(--primary))" : "transparent",
                color: window.hours === hours ? "white" : "hsl(var(--foreground))",
              }}
            >
              {window.label}
            </button>
          ))}
        </div>
      </div>

      {isLoading ? (
        <div className="grid md:grid-cols-3 gap-4">
          {Array.from({ length: 3 }).map((_, index) => (
            <div
              key={index}
              className="rounded-xl border p-4 space-y-3"
              style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
            >
              <div className="skeleton h-4 w-24 rounded" />
              <div className="skeleton h-8 w-32 rounded" />
            </div>
          ))}
        </div>
      ) : error ? (
        <EmptyState
          title="Could not load costs"
          description="The dashboard could not fetch the cost attribution API."
          body={<p>Check that the LangSight API is running and reachable from the dashboard container.</p>}
        />
      ) : !data?.supports_costs ? (
        <EmptyState
          title="Costs require ClickHouse-backed traces"
          description="This LangSight instance is not using a backend that exposes traced tool-call counts for cost attribution."
          body={
            <>
              <div className="flex items-start gap-2 mb-3">
                <Database size={16} className="mt-0.5" style={{ color: "hsl(var(--primary))" }} />
                <div>
                  <p className="font-medium" style={{ color: "hsl(var(--foreground))" }}>
                    What is needed
                  </p>
                  <p>1. Run LangSight with <code className="text-primary">storage.mode: clickhouse</code>.</p>
                  <p>2. Send traced tool-call spans through the SDK or OTLP endpoint.</p>
                </div>
              </div>
              <p>Current storage mode: <code>{data?.storage_mode ?? "unknown"}</code></p>
            </>
          }
        />
      ) : data.by_tool.length === 0 ? (
        <EmptyState
          title="No traced tool calls yet"
          description="ClickHouse is available, but there are no tool-call spans in the selected time window."
          body={
            <>
              <p className="font-medium mb-1" style={{ color: "hsl(var(--foreground))" }}>
                Available today
              </p>
              <p>Instrument an agent with the LangSight SDK or send OTLP spans to start seeing cost data.</p>
              <p className="font-mono mt-2">uv run langsight costs</p>
            </>
          }
        />
      ) : (
        <>
          {/* Summary cards */}
          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-4">
            <SummaryCard title="Total Cost" value={formatUsd(data.total_cost_usd)} icon={<Wallet size={18} />} />
            <SummaryCard title="LLM Cost" value={formatUsd(data.llm_cost_usd ?? 0)} icon={<Cpu size={18} />} />
            <SummaryCard title="Tool Call Cost" value={formatUsd(data.tool_cost_usd ?? 0)} icon={<Wrench size={18} />} />
            <SummaryCard title="Total Calls" value={data.total_calls.toLocaleString("en-US")} icon={<Layers3 size={18} />} />
          </div>

          {/* Token summary if any LLM spans */}
          {(data.total_input_tokens ?? 0) > 0 && (
            <div className="rounded-xl border p-4 flex items-center gap-6" style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}>
              <div>
                <p className="text-xs font-medium" style={{ color: "hsl(var(--muted-foreground))" }}>Input Tokens</p>
                <p className="text-lg font-bold font-mono" style={{ color: "hsl(var(--foreground))" }}>{(data.total_input_tokens ?? 0).toLocaleString()}</p>
              </div>
              <div className="w-px h-8" style={{ background: "hsl(var(--border))" }} />
              <div>
                <p className="text-xs font-medium" style={{ color: "hsl(var(--muted-foreground))" }}>Output Tokens</p>
                <p className="text-lg font-bold font-mono" style={{ color: "hsl(var(--foreground))" }}>{(data.total_output_tokens ?? 0).toLocaleString()}</p>
              </div>
              <div className="w-px h-8" style={{ background: "hsl(var(--border))" }} />
              <div>
                <p className="text-xs font-medium" style={{ color: "hsl(var(--muted-foreground))" }}>Total Tokens</p>
                <p className="text-lg font-bold font-mono" style={{ color: "hsl(var(--foreground))" }}>{((data.total_input_tokens ?? 0) + (data.total_output_tokens ?? 0)).toLocaleString()}</p>
              </div>
            </div>
          )}

          {/* By Model (only shown when token-based entries exist) */}
          {data.by_tool.some(e => e.cost_type === "token_based") && (
            <SectionTable
              title="By Model"
              headers={["Model", "Calls", "Input Tokens", "Output Tokens", "LLM Cost"]}
              rows={
                <>
                  {Object.values(
                    data.by_tool
                      .filter(e => e.cost_type === "token_based" && e.model_id)
                      .reduce((acc: Record<string, { model_id: string; calls: number; inp: number; out: number; cost: number }>, e) => {
                        const k = e.model_id!;
                        if (!acc[k]) acc[k] = { model_id: k, calls: 0, inp: 0, out: 0, cost: 0 };
                        acc[k].calls += e.total_calls;
                        acc[k].inp += e.total_input_tokens;
                        acc[k].out += e.total_output_tokens;
                        acc[k].cost += e.total_cost_usd;
                        return acc;
                      }, {})
                  ).sort((a, b) => b.cost - a.cost).map(m => (
                    <tr key={m.model_id}>
                      <td className="py-2 pr-4 font-mono text-xs" style={{ color: "hsl(var(--foreground))" }}>{m.model_id}</td>
                      <td className="py-2 pr-4" style={{ color: "hsl(var(--muted-foreground))" }}>{m.calls.toLocaleString()}</td>
                      <td className="py-2 pr-4 font-mono" style={{ color: "hsl(var(--muted-foreground))" }}>{m.inp.toLocaleString()}</td>
                      <td className="py-2 pr-4 font-mono" style={{ color: "hsl(var(--muted-foreground))" }}>{m.out.toLocaleString()}</td>
                      <td className="py-2 font-mono" style={{ color: "hsl(var(--foreground))" }}>{formatUsd(m.cost)}</td>
                    </tr>
                  ))}
                </>
              }
            />
          )}

          <SectionTable
            title="By Tool"
            headers={["Server", "Tool", "Type", "Calls", "$/Call", "Total"]}
            rows={data.by_tool.map((entry) => (
              <tr key={`${entry.server_name}-${entry.tool_name}`}>
                <td className="py-2 pr-4 font-mono text-xs" style={{ color: "hsl(var(--foreground))" }}>
                  {entry.server_name}
                </td>
                <td className="py-2 pr-4" style={{ color: "hsl(var(--foreground))" }}>
                  {entry.tool_name}
                </td>
                <td className="py-2 pr-4">
                  <span className={`text-[10px] px-1.5 py-0.5 rounded-full border font-medium ${entry.cost_type === "token_based" ? "border-primary/30 bg-primary/10 text-primary" : "border-border text-muted-foreground"}`}>
                    {entry.cost_type === "token_based" ? "LLM" : "tool"}
                  </span>
                </td>
                <td className="py-2 pr-4" style={{ color: "hsl(var(--muted-foreground))" }}>
                  {entry.total_calls.toLocaleString("en-US")}
                </td>
                <td className="py-2 pr-4 font-mono" style={{ color: "hsl(var(--muted-foreground))" }}>
                  {formatUsd(entry.cost_per_call_usd)}
                </td>
                <td className="py-2 font-mono" style={{ color: "hsl(var(--foreground))" }}>
                  {formatUsd(entry.total_cost_usd)}
                </td>
              </tr>
            ))}
          />

          <div className="grid lg:grid-cols-2 gap-5">
            <SectionTable
              title="By Agent"
              headers={["Agent", "Calls", "Total Cost"]}
              rows={data.by_agent.map((entry) => (
                <tr key={entry.agent_name}>
                  <td className="py-2 pr-4" style={{ color: "hsl(var(--foreground))" }}>
                    {entry.agent_name}
                  </td>
                  <td className="py-2 pr-4" style={{ color: "hsl(var(--muted-foreground))" }}>
                    {entry.total_calls.toLocaleString("en-US")}
                  </td>
                  <td className="py-2 font-mono" style={{ color: "hsl(var(--foreground))" }}>
                    {formatUsd(entry.total_cost_usd)}
                  </td>
                </tr>
              ))}
            />

            <SectionTable
              title="Top Sessions"
              headers={["Session", "Agent", "Calls", "Total"]}
              rows={data.by_session.map((entry) => (
                <tr key={entry.session_id}>
                  <td className="py-2 pr-4 font-mono" style={{ color: "hsl(var(--foreground))" }}>
                    {entry.session_id}
                  </td>
                  <td className="py-2 pr-4" style={{ color: "hsl(var(--muted-foreground))" }}>
                    {entry.agent_name ?? "—"}
                  </td>
                  <td className="py-2 pr-4" style={{ color: "hsl(var(--muted-foreground))" }}>
                    {entry.total_calls.toLocaleString("en-US")}
                  </td>
                  <td className="py-2 font-mono" style={{ color: "hsl(var(--foreground))" }}>
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
