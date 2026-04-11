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
import { MarkdownContent } from "@/components/markdown-content";

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
            <MetricTile label="Latency" value={trace.duration_ms ? formatDuration(trace.duration_ms) : "—"} />
            <MetricTile label="Total Spans" value={String(trace.spans_flat.length)} />
            <MetricTile
              label="Tool Calls"
              value={String(trace.spans_flat.filter((s: SpanNode) => s.span_type === "tool_call" || s.span_type === "node").length)}
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
              <>
                <MetricTile
                  label="Cost"
                  value={`$${session.est_cost_usd < 0.01 ? session.est_cost_usd.toFixed(4) : session.est_cost_usd.toFixed(2)}`}
                />
                {/* Cost breakdown */}
                {trace && (() => {
                  const llmSpans = trace.spans_flat.filter((s: SpanNode) => s.model_id && s.input_tokens);
                  const totalIn = llmSpans.reduce((sum, sp) => sum + (sp.input_tokens ?? 0), 0);
                  const totalOut = llmSpans.reduce((sum, sp) => sum + (sp.output_tokens ?? 0), 0);
                  const totalThinking = llmSpans.reduce((sum, sp) => sum + (sp.thinking_tokens ?? 0), 0);
                  const totalCacheRead = llmSpans.reduce((sum, sp) => sum + (sp.cache_read_tokens ?? 0), 0);
                  const totalCacheCreation = llmSpans.reduce((sum, sp) => sum + (sp.cache_creation_tokens ?? 0), 0);
                  if (totalIn === 0) return null;
                  return (
                    <div className="px-1 py-1.5 text-[9px] text-muted-foreground space-y-0.5" style={{ fontFamily: "var(--font-geist-mono)" }}>
                      <div>{totalIn.toLocaleString()} in · {totalOut.toLocaleString()} out{totalThinking > 0 && ` · ${totalThinking.toLocaleString()} thinking`}</div>
                      {(totalCacheRead > 0 || totalCacheCreation > 0) && (
                        <div className="text-primary">
                          {totalCacheRead > 0 && `${totalCacheRead.toLocaleString()} cached`}
                          {totalCacheRead > 0 && totalCacheCreation > 0 && " · "}
                          {totalCacheCreation > 0 && `${totalCacheCreation.toLocaleString()} cache write`}
                        </div>
                      )}
                    </div>
                  );
                })()}
              </>
            )}
          </div>
        </div>
      )}

      {/* Input / Output Preview */}
      {trace && (() => {
        const sessionSpans = trace.spans_flat.filter((s: SpanNode) => s.tool_name === "session");
        const inputText = sessionSpans.find(s => s.llm_input)?.llm_input;
        const outputText = sessionSpans.find(s => s.llm_output)?.llm_output;
        if (!inputText && !outputText) return null;
        return (
          <div>
            <SectionLabel>Input / Output</SectionLabel>
            <div className="space-y-3">
              {inputText && (
                <div>
                  <p className="text-[10px] text-muted-foreground mb-1">Input</p>
                  <MarkdownContent content={inputText} clamp={3} fontSize="text-[11px]" />
                </div>
              )}
              {outputText && (
                <div>
                  <p className="text-[10px] text-muted-foreground mb-1">Output</p>
                  <MarkdownContent content={outputText.length > 500 ? `${outputText.slice(0, 500)}...` : outputText} clamp={4} fontSize="text-[11px]" />
                </div>
              )}
            </div>
          </div>
        );
      })()}

      {/* Node Execution Summary */}
      {trace && (() => {
        const nodeSpans = trace.spans_flat
          .filter((s: SpanNode) => s.span_type === "node")
          .sort((a, b) => new Date(a.started_at).getTime() - new Date(b.started_at).getTime());
        if (nodeSpans.length === 0) return null;

        // For each node span, find its matching LLM span (same agent_name, span_type="agent", has model_id)
        const llmSpans = trace.spans_flat.filter((s: SpanNode) => s.span_type === "agent" && s.model_id);

        return (
          <div>
            <SectionLabel>Node Execution</SectionLabel>
            <div className="divide-y" style={{ borderColor: "hsl(var(--border) / 0.5)" }}>
              {nodeSpans.map((node, i) => {
                const llm = llmSpans.find(l => l.agent_name === node.agent_name &&
                  Math.abs(new Date(l.started_at).getTime() - new Date(node.started_at).getTime()) < 60000);
                const latency = node.latency_ms ? `${(node.latency_ms / 1000).toFixed(1)}s` : "—";
                const inTok = llm?.input_tokens ?? 0;
                const outTok = llm?.output_tokens ?? 0;
                const thinkTok = llm?.thinking_tokens ?? 0;
                const tokens = llm ? `${inTok}→${outTok}${thinkTok > 0 ? `+${thinkTok}t` : ""}` : "—";
                const hasError = node.status === "error";
                return (
                  <div key={node.span_id} className="flex items-center justify-between py-1.5 px-1">
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] text-muted-foreground w-4">{i + 1}</span>
                      <span
                        className={cn(
                          "text-[11px] font-semibold",
                          hasError ? "text-red-500" : "text-foreground"
                        )}
                        style={{ fontFamily: "var(--font-geist-mono)" }}
                      >
                        {node.agent_name}
                      </span>
                    </div>
                    <div className="flex items-center gap-3 text-[10px]" style={{ fontFamily: "var(--font-geist-mono)" }}>
                      <span className="text-muted-foreground">{latency}</span>
                      <span className="text-foreground">{tokens}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })()}

      <p className="text-[10px] text-muted-foreground text-center pt-2">
        Click any node or edge for details
      </p>
    </div>
  );
}
