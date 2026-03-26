"use client";

/**
 * SessionMetrics — right-panel default state when no node/edge is selected.
 * Shows session-level summary: duration, spans, tokens, cost, agents, servers.
 */

import type { ReactNode } from "react";
import { HealthTagBadge } from "@/components/health-tag-badge";
import { formatDuration } from "@/lib/utils";
import type { AgentSession, SessionTrace, SpanNode } from "@/lib/types";
import { cn } from "@/lib/utils";

interface MetricTileProps {
  label: string;
  value: string;
  danger?: boolean;
}

export function MetricTile({ label, value, danger }: MetricTileProps) {
  return (
    <div className="flex items-center justify-between py-1.5">
      <span className="text-[11px] text-muted-foreground">{label}</span>
      <span
        className={cn("text-[12px] font-semibold", danger ? "text-red-500" : "text-foreground")}
        style={{ fontFamily: "var(--font-geist-mono)" }}
      >
        {value}
      </span>
    </div>
  );
}

export function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <p className="text-[9px] font-semibold text-muted-foreground uppercase tracking-widest mb-2.5">
      {children}
    </p>
  );
}

interface SessionMetricsProps {
  trace: SessionTrace | null;
  session: AgentSession | undefined;
}

export function SessionMetrics({ trace, session }: SessionMetricsProps) {
  const errorCount = trace
    ? trace.spans_flat.filter((s: SpanNode) => s.status === "error").length
    : 0;

  return (
    <div className="p-5 space-y-5">
      {/* Session summary header */}
      <div className="flex items-center justify-between">
        <p className="text-[12px] font-semibold text-foreground">Session Summary</p>
        {(session?.health_tag || (trace && trace.failed_calls === 0)) && (
          <HealthTagBadge
            tag={session?.health_tag ?? (trace && trace.failed_calls > 0 ? "tool_failure" : "success")}
          />
        )}
      </div>

      {/* Overview stats */}
      {trace && (
        <div>
          <SectionLabel>Overview</SectionLabel>
          <div className="divide-y" style={{ borderColor: "hsl(var(--border) / 0.5)" }}>
            <MetricTile label="Duration" value={trace.duration_ms ? formatDuration(trace.duration_ms) : "—"} />
            <MetricTile label="Total Spans" value={String(trace.spans_flat.length)} />
            <MetricTile
              label="Tool Calls"
              value={String(trace.spans_flat.filter((s: SpanNode) => s.span_type === "tool_call").length)}
            />
            <MetricTile
              label="Errors"
              value={String(errorCount)}
              danger={errorCount > 0}
            />
          </div>
        </div>
      )}

      {/* Agents & Servers */}
      {trace && (
        <div className="space-y-3">
          <div>
            <SectionLabel>Agents</SectionLabel>
            <div className="flex flex-wrap gap-1">
              {Array.from(
                new Set(trace.spans_flat.map((s: SpanNode) => s.agent_name).filter(Boolean))
              ).map((a) => (
                <span
                  key={a as string}
                  className="px-2 py-0.5 rounded text-[10px] font-medium"
                  style={{
                    background: "hsl(var(--primary) / 0.08)",
                    color: "hsl(var(--primary))",
                    border: "1px solid hsl(var(--primary) / 0.15)",
                  }}
                >
                  {a as string}
                </span>
              ))}
            </div>
          </div>
          <div>
            <SectionLabel>Servers</SectionLabel>
            <div className="flex flex-wrap gap-1">
              {Array.from(
                new Set(
                  trace.spans_flat
                    .filter((s: SpanNode) => s.span_type === "tool_call")
                    .map((s: SpanNode) => s.server_name)
                )
              ).map((srv) => (
                <span
                  key={srv as string}
                  className="px-2 py-0.5 rounded text-[10px]"
                  style={{
                    background: "hsl(var(--muted))",
                    color: "hsl(var(--muted-foreground))",
                    border: "1px solid hsl(var(--border))",
                    fontFamily: "var(--font-geist-mono)",
                  }}
                >
                  {srv as string}
                </span>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Tokens & Cost */}
      {session && (session.total_input_tokens || session.est_cost_usd) && (
        <div>
          <SectionLabel>Tokens & Cost</SectionLabel>
          <div className="divide-y" style={{ borderColor: "hsl(var(--border) / 0.5)" }}>
            <MetricTile label="Input Tokens" value={(session.total_input_tokens ?? 0).toLocaleString()} />
            <MetricTile label="Output Tokens" value={(session.total_output_tokens ?? 0).toLocaleString()} />
            {session.model_id && (
              <div className="flex items-center justify-between py-1.5">
                <span className="text-[11px] text-muted-foreground">Model</span>
                <code
                  className="text-[10px] px-1.5 py-0.5 rounded"
                  style={{
                    background: "hsl(var(--primary) / 0.08)",
                    color: "hsl(var(--primary))",
                    fontFamily: "var(--font-geist-mono)",
                  }}
                >
                  {session.model_id}
                </code>
              </div>
            )}
            {session.est_cost_usd != null && (
              <MetricTile
                label="Cost"
                value={`$${session.est_cost_usd < 0.01 ? session.est_cost_usd.toFixed(4) : session.est_cost_usd.toFixed(2)}`}
              />
            )}
          </div>
        </div>
      )}

      <p className="text-[10px] text-muted-foreground text-center pt-2">
        Click any node or edge for details
      </p>
    </div>
  );
}
