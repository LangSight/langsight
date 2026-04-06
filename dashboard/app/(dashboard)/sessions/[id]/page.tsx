"use client";

export const dynamic = "force-dynamic";

import { useState, useEffect, useMemo, useCallback, useRef } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import useSWR from "swr";
import {
  Bot, Server,
  Maximize2, Minimize2, ExternalLink,
} from "lucide-react";
import { LineageGraph, type GraphSelection } from "@/components/lineage-graph";
import { PayloadSlideout } from "@/components/payload-slideout";
import { SessionTimeline } from "@/components/session-timeline";
import { fetcher, getSessionTrace } from "@/lib/api";
import { useProject } from "@/lib/project-context";
import { buildSessionGraph, type SessionGraphResult } from "@/lib/session-graph";
import { cn } from "@/lib/utils";
import { Timestamp } from "@/components/timestamp";
import type { AgentSession, SessionTrace, SpanNode, PathMetrics, ServerCallerInfo } from "@/lib/types";
import { SessionHeader } from "@/components/sessions/session-header";
import { SessionMetrics, MetricTile, SectionLabel } from "@/components/sessions/session-metrics";
import { SpanTree, TokenSummaryBar } from "@/components/sessions/span-tree";

/* ── Build session graph from trace spans ──────────────────── */

function useSessionGraph(
  trace: SessionTrace | null,
  expandedGroups: Set<string>,
  expandedEdges: Set<string>,
): SessionGraphResult {
  return useMemo(
    () => buildSessionGraph(trace, expandedGroups, expandedEdges),
    [trace, expandedGroups, expandedEdges],
  );
}

/* ── Right panel: node detail for session ──────────────────── */

function SessionNodeDetail({ nodeId, trace, serverCallers, onViewPayload }: { nodeId: string; trace: SessionTrace; serverCallers: Map<string, ServerCallerInfo[]>; onViewPayload?: (title: string, tabs: { label: string; json: string | null }[]) => void }) {
  const isAgent = nodeId.startsWith("agent:");
  const isPerCall = nodeId.includes("::call:");
  const isViaSplit = nodeId.includes("::via:");

  // Extract the base server/agent name from compound node IDs:
  //   "server:inventory::via:procurement" → serverName="inventory", viaAgent="procurement"
  //   "server:catalog::call:abc123"       → name="catalog", callSpanId="abc123"
  //   "server:catalog"                    → name="catalog"
  //   "agent:orchestrator"                → name="orchestrator"
  const name = nodeId.replace(/^(agent|server):/, "").replace(/::call:.*$/, "").replace(/::via:.*$/, "");
  const viaAgent = isViaSplit ? nodeId.replace(/^.*::via:/, "") : null;

  // For per-call nodes, find the exact span by span_id
  const callSpanId = isPerCall ? nodeId.replace(/^.*::call:/, "") : null;

  const spans = isPerCall
    ? trace.spans_flat.filter((s: SpanNode) => s.span_id === callSpanId)
    : trace.spans_flat.filter((s: SpanNode) => {
        if (isAgent) return s.agent_name === name;
        // Server node: match by server_name + tool_call type
        if (s.server_name !== name || s.span_type !== "tool_call") return false;
        // For "via X" split nodes, also filter by agent_name
        if (viaAgent && s.agent_name !== viaAgent) return false;
        return true;
      });

  const totalCalls = spans.length;
  const errors = spans.filter((s: SpanNode) => s.status !== "success").length;
  const avgLatency = totalCalls > 0 ? spans.reduce((sum: number, s: SpanNode) => sum + (s.latency_ms ?? 0), 0) / totalCalls : 0;
  const maxLatency = spans.reduce((max: number, s: SpanNode) => Math.max(max, s.latency_ms ?? 0), 0);
  const tools = [...new Set(spans.map((s: SpanNode) => s.tool_name))];
  const errorRate = totalCalls > 0 ? (errors / totalCalls) * 100 : 0;
  const totalInputTokens = spans.reduce((s: number, sp: SpanNode) => s + (sp.input_tokens ?? 0), 0);
  const totalOutputTokens = spans.reduce((s: number, sp: SpanNode) => s + (sp.output_tokens ?? 0), 0);
  const models = [...new Set(spans.map((s: SpanNode) => s.model_id).filter(Boolean))];

  return (
    <div className="h-full overflow-y-auto">
      {/* Header */}
      <div className="px-5 pt-5 pb-4 border-b" style={{
        borderColor: "hsl(var(--border))",
        background: isAgent
          ? "linear-gradient(180deg, hsl(var(--primary) / 0.05) 0%, transparent 100%)"
          : "linear-gradient(180deg, hsl(var(--muted) / 0.3) 0%, transparent 100%)",
      }}>
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0" style={{
            background: isAgent
              ? "linear-gradient(135deg, hsl(var(--primary) / 0.15), hsl(var(--primary) / 0.06))"
              : "linear-gradient(135deg, rgba(100,116,139,0.14), rgba(100,116,139,0.05))",
            border: isAgent ? "1px solid hsl(var(--primary) / 0.2)" : "1px solid rgba(100,116,139,0.15)",
          }}>
            {isAgent ? <Bot size={16} style={{ color: "hsl(var(--primary))" }} /> : <Server size={16} className="text-muted-foreground" />}
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-[14px] font-bold text-foreground truncate" style={{ letterSpacing: "-0.01em" }}>{isPerCall && spans[0] ? spans[0].tool_name : name}</p>
            <div className="flex items-center gap-2 mt-0.5">
              <span className="text-[11px] text-muted-foreground">{isPerCall ? `${name} · Tool Call` : isAgent ? "Agent" : "MCP Server"}</span>
              <span className={cn("w-2 h-2 rounded-full", errors > 0 ? "bg-red-500" : "bg-emerald-500")} style={{ boxShadow: errors > 0 ? "0 0 6px rgba(239,68,68,0.4)" : "0 0 4px rgba(16,185,129,0.3)" }} />
              <span className="text-[12px] font-medium" style={{ color: errors > 0 ? "#ef4444" : "#10b981" }}>
                {errors > 0 ? `${errors} error${errors > 1 ? "s" : ""}` : "All OK"}
              </span>
            </div>
            {!isPerCall && (
              <Link
                href={isAgent ? `/agents` : `/servers`}
                className="mt-1.5 inline-flex items-center gap-1 text-[11px] text-primary hover:underline font-medium"
              >
                View in {isAgent ? "Agent" : "Server"} Catalog →
              </Link>
            )}
          </div>
        </div>
      </div>

      {/* Overview metrics */}
      <div className="px-5 py-4">
        <SectionLabel>Overview</SectionLabel>
        <div className="divide-y" style={{ borderColor: "hsl(var(--border) / 0.5)" }}>
          <MetricTile label="Calls" value={totalCalls.toLocaleString()} />
          <MetricTile label="Errors" value={errors.toLocaleString()} danger={errors > 0} />
          <MetricTile label="Avg Latency" value={`${Math.round(avgLatency)}ms`} />
          <MetricTile label="Max Latency" value={`${Math.round(maxLatency)}ms`} />
          {errorRate > 0 && <MetricTile label="Error Rate" value={`${errorRate.toFixed(1)}%`} danger />}
          {spans.length > 0 && spans[0].started_at && (
            <div className="flex items-center justify-between py-1.5">
              <span className="text-[11px] text-muted-foreground">Started</span>
              <span className="text-[10px] text-muted-foreground"><Timestamp iso={spans[0].started_at} /></span>
            </div>
          )}
        </div>
      </div>

      {/* Tools */}
      {tools.length > 0 && (
        <div className="px-5 py-4 border-t" style={{ borderColor: "hsl(var(--border))" }}>
          <SectionLabel>Tools ({tools.length})</SectionLabel>
          <div className="divide-y" style={{ borderColor: "hsl(var(--border) / 0.5)" }}>
            {tools.map((tool) => {
              const toolSpans = spans.filter((s: SpanNode) => s.tool_name === tool);
              const toolErrors = toolSpans.filter((s: SpanNode) => s.status !== "success").length;
              const toolAvgMs = toolSpans.reduce((s: number, sp: SpanNode) => s + (sp.latency_ms ?? 0), 0) / toolSpans.length;
              return (
                <div key={tool} className="flex items-center justify-between py-1.5">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className={cn("w-1.5 h-1.5 rounded-full flex-shrink-0", toolErrors > 0 ? "bg-red-500" : "bg-emerald-500")} />
                    <span className="text-[11px] font-medium text-foreground truncate">{tool}</span>
                    {toolErrors > 0 && <span className="text-[9px] px-1 py-0.5 rounded-full flex-shrink-0" style={{ background: "rgba(239,68,68,0.08)", color: "#ef4444" }}>{toolErrors} err</span>}
                  </div>
                  <div className="flex items-center gap-2.5 text-[10px] text-muted-foreground flex-shrink-0" style={{ fontFamily: "var(--font-geist-mono)" }}>
                    <span>{Math.round(toolAvgMs)}ms</span>
                    <span>{toolSpans.length}×</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Per-agent breakdown (server nodes called by 2+ agents) */}
      {!isAgent && (() => {
        // For "via X" split nodes, scope to that single agent
        const allCallers = serverCallers.get(name) ?? [];
        const callers = viaAgent
          ? allCallers.filter((c) => c.agentLabel === viaAgent)
          : allCallers;
        if (callers.length < 2) return null;
        return (
          <div className="px-5 py-4 border-t" style={{ borderColor: "hsl(var(--border))" }}>
            <SectionLabel>By Agent ({callers.length})</SectionLabel>
            <div className="space-y-1.5">
              {callers.map((caller) => (
                <div key={caller.agentId} className="rounded-lg px-3 py-2.5" style={{ background: "hsl(var(--muted))" }}>
                  <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center gap-2">
                      <Bot size={11} style={{ color: "hsl(var(--primary))" }} />
                      <span className="text-[12px] font-medium text-foreground">{caller.agentLabel}</span>
                    </div>
                    {caller.metrics.errorCount > 0 && (
                      <span className="text-[10px]" style={{ color: "#ef4444" }}>{caller.metrics.errorCount} errors</span>
                    )}
                  </div>
                  <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
                    <span style={{ fontFamily: "var(--font-geist-mono)" }}>{caller.metrics.callCount} calls</span>
                    <span style={{ fontFamily: "var(--font-geist-mono)" }}>{Math.round(caller.metrics.avgLatencyMs)}ms avg</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        );
      })()}

      {/* Per-server breakdown (agent nodes calling 2+ servers) */}
      {isAgent && (() => {
        const serverBreakdown: { server: string; metrics: PathMetrics }[] = [];
        for (const [server, callers] of serverCallers) {
          const match = callers.find((c) => c.agentLabel === name);
          if (match) serverBreakdown.push({ server, metrics: match.metrics });
        }
        if (serverBreakdown.length < 2) return null;
        return (
          <div className="px-5 py-4 border-t" style={{ borderColor: "hsl(var(--border))" }}>
            <SectionLabel>By Server ({serverBreakdown.length})</SectionLabel>
            <div className="space-y-1.5">
              {serverBreakdown.map(({ server, metrics }) => (
                <div key={server} className="rounded-lg px-3 py-2.5" style={{ background: "hsl(var(--muted))" }}>
                  <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center gap-2">
                      <Server size={11} className="text-muted-foreground" />
                      <span className="text-[12px] font-medium text-foreground">{server}</span>
                    </div>
                    {metrics.errorCount > 0 && (
                      <span className="text-[10px]" style={{ color: "#ef4444" }}>{metrics.errorCount} errors</span>
                    )}
                  </div>
                  <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
                    <span style={{ fontFamily: "var(--font-geist-mono)" }}>{metrics.callCount} calls</span>
                    <span style={{ fontFamily: "var(--font-geist-mono)" }}>{Math.round(metrics.avgLatencyMs)}ms avg</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        );
      })()}

      {/* Token usage */}
      {totalInputTokens > 0 && (
        <div className="px-5 py-4 border-t" style={{ borderColor: "hsl(var(--border))" }}>
          <SectionLabel>Token Usage</SectionLabel>
          <div className="divide-y" style={{ borderColor: "hsl(var(--border) / 0.5)" }}>
            <MetricTile label="Input" value={totalInputTokens.toLocaleString()} />
            <MetricTile label="Output" value={totalOutputTokens.toLocaleString()} />
            {models.length > 0 && (
              <div className="flex items-center justify-between py-1.5">
                <span className="text-[11px] text-muted-foreground">Model</span>
                <div className="flex gap-1">
                  {models.map((m) => (
                    <code key={m} className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: "hsl(var(--primary) / 0.08)", color: "hsl(var(--primary))", fontFamily: "var(--font-geist-mono)" }}>{m}</code>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Session Input / Output — shown when clicking an agent node that has a
          root session span (emitted by session(input=...) / sess.set_output()),
          OR a crew/agent span with llm_input/llm_output (e.g. CrewAI event bus). */}
      {isAgent && (() => {
        // 1. Traditional session spans (from langsight.session())
        const sessionSpans = trace.spans_flat.filter(
          (s: SpanNode) => s.span_type === "agent" && s.tool_name === "session" && s.agent_name === name
        );
        // 2. CrewAI crew/agent spans that carry llm_input/llm_output
        const crewSpans = trace.spans_flat.filter(
          (s: SpanNode) => s.span_type === "agent" && s.agent_name === name && (s.llm_input || s.llm_output) && s.tool_name !== "session"
        );
        const candidates = [...sessionSpans, ...crewSpans];
        const rootSpan = candidates.find((s: SpanNode) => s.llm_output) ?? candidates[0];
        if (!rootSpan?.llm_input && !rootSpan?.llm_output) return null;
        return (
          <div className="px-5 py-4 border-t" style={{ borderColor: "hsl(var(--border))" }}>
            <SectionLabel>Input / Output</SectionLabel>
            {rootSpan.llm_input && (
              <div className="mb-3">
                <p className="text-[11px] font-semibold uppercase tracking-widest mb-1.5 text-muted-foreground">Input</p>
                <p className="text-[12px] text-foreground rounded-lg px-3 py-2.5 leading-relaxed line-clamp-6" style={{ background: "hsl(var(--muted))" }}>{rootSpan.llm_input}</p>
                {rootSpan.llm_input.length > 300 && (
                  <button
                    onClick={() => onViewPayload?.(`Input — ${name}`, [{ label: "Text", json: rootSpan.llm_input ?? null }])}
                    className="mt-2 text-[11px] font-medium hover:underline" style={{ color: "hsl(var(--primary))" }}
                  >
                    View full input →
                  </button>
                )}
              </div>
            )}
            {!rootSpan.llm_output && rootSpan.llm_input && (
              <div className="mt-1 inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium bg-zinc-500/10 text-zinc-400">
                <span className="h-1.5 w-1.5 rounded-full bg-zinc-400" />
                No answer captured — agent may have crashed or set_output() was not called
              </div>
            )}
            {rootSpan.llm_output && (
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-widest mb-1.5 text-muted-foreground">Output</p>
                <p className="text-[12px] text-foreground rounded-lg px-3 py-2.5 leading-relaxed line-clamp-6" style={{ background: "hsl(var(--muted))" }}>{rootSpan.llm_output}</p>
                {rootSpan.llm_output.length > 300 && (
                  <button
                    onClick={() => onViewPayload?.(`Output — ${name}`, [{ label: "Text", json: rootSpan.llm_output ?? null }])}
                    className="mt-2 text-[11px] font-medium hover:underline" style={{ color: "hsl(var(--primary))" }}
                  >
                    View full output →
                  </button>
                )}
              </div>
            )}
          </div>
        );
      })()}

      {/* Per-call detail: show input/output prominently */}
      {isPerCall && spans[0] && (
        <div className="px-5 py-4 border-t" style={{ borderColor: "hsl(var(--border))" }}>
          {spans[0].input_json && (
            <div className="mb-3">
              <SectionLabel>Input</SectionLabel>
              <pre className="text-[11px] text-foreground rounded-lg p-3 whitespace-pre-wrap break-all max-h-48 overflow-y-auto" style={{ fontFamily: "var(--font-geist-mono)", background: "hsl(var(--muted))", border: "1px solid hsl(var(--border))" }}>
                {(() => { try { return JSON.stringify(JSON.parse(spans[0].input_json!), null, 2); } catch { return spans[0].input_json; } })()}
              </pre>
            </div>
          )}
          {spans[0].output_json && (
            <div className="mb-3">
              <SectionLabel>Output</SectionLabel>
              <pre className="text-[11px] text-foreground rounded-lg p-3 whitespace-pre-wrap break-all max-h-48 overflow-y-auto" style={{ fontFamily: "var(--font-geist-mono)", background: "hsl(var(--muted))", border: "1px solid hsl(var(--border))" }}>
                {(() => { try { return JSON.stringify(JSON.parse(spans[0].output_json!), null, 2); } catch { return spans[0].output_json; } })()}
              </pre>
            </div>
          )}
          {/* LLM prompt/completion — shown on agent-type spans (LLM calls) */}
          {spans[0].llm_input && (
            <div className="mb-3">
              <div className="flex items-center justify-between mb-1">
                <SectionLabel>Prompt</SectionLabel>
                {spans[0].llm_input.length > 300 && (
                  <button
                    onClick={() => onViewPayload?.(`Prompt — ${spans[0].tool_name}`, [{ label: "Text", json: spans[0].llm_input ?? null }])}
                    className="text-[9px] text-primary hover:underline flex items-center gap-1 font-medium"
                  ><ExternalLink size={9} />View full</button>
                )}
              </div>
              <pre className="text-[11px] text-foreground rounded-lg p-3 whitespace-pre-wrap break-all max-h-48 overflow-y-auto" style={{ fontFamily: "var(--font-geist-mono)", background: "hsl(var(--muted))", border: "1px solid hsl(var(--border))" }}>
                {spans[0].llm_input}
              </pre>
            </div>
          )}
          {spans[0].llm_output && (
            <div className="mb-3">
              <div className="flex items-center justify-between mb-1">
                <SectionLabel>Completion</SectionLabel>
                {spans[0].llm_output.length > 300 && (
                  <button
                    onClick={() => onViewPayload?.(`Completion — ${spans[0].tool_name}`, [{ label: "Text", json: spans[0].llm_output ?? null }])}
                    className="text-[9px] text-primary hover:underline flex items-center gap-1 font-medium"
                  ><ExternalLink size={9} />View full</button>
                )}
              </div>
              <pre className="text-[11px] text-foreground rounded-lg p-3 whitespace-pre-wrap break-all max-h-48 overflow-y-auto" style={{ fontFamily: "var(--font-geist-mono)", background: "hsl(var(--muted))", border: "1px solid hsl(var(--border))" }}>
                {spans[0].llm_output}
              </pre>
            </div>
          )}
          {spans[0].error && (
            <div className="mb-3">
              <SectionLabel>Error</SectionLabel>
              <div className="rounded-lg px-3 py-2.5 text-[11px]" style={{ background: "rgba(239,68,68,0.06)", color: "#ef4444", fontFamily: "var(--font-geist-mono)" }}>{spans[0].error}</div>
            </div>
          )}
          {(spans[0].input_tokens || spans[0].output_tokens || spans[0].finish_reason) && (
            <div>
              <SectionLabel>Tokens</SectionLabel>
              <div className="flex items-center gap-4 text-[11px] text-muted-foreground">
                {spans[0].model_id && <span>Model: <code className="text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>{spans[0].model_id}</code></span>}
                {spans[0].input_tokens != null && <span>In: <strong className="text-foreground">{spans[0].input_tokens}</strong></span>}
                {spans[0].output_tokens != null && <span>Out: <strong className="text-foreground">{spans[0].output_tokens}</strong></span>}
                {spans[0].cache_read_tokens != null && <span title="Anthropic cached read tokens (10× cheaper)">Cache↗: <strong className="text-foreground" style={{ color: "#34d399" }}>{spans[0].cache_read_tokens}</strong></span>}
                {spans[0].cache_creation_tokens != null && <span title="Anthropic cache creation tokens">Cache+: <strong className="text-foreground">{spans[0].cache_creation_tokens}</strong></span>}
                {spans[0].finish_reason && (() => {
                  const fr = spans[0].finish_reason!;
                  const isError = ["content_filter","safety","recitation","prohibited_content","content_filtered"].includes(fr);
                  const isWarn = ["max_tokens","length"].includes(fr);
                  return (
                    <span style={{ color: isError ? "hsl(var(--danger))" : isWarn ? "#f59e0b" : "inherit" }}>
                      Stop: <strong style={{ fontFamily: "var(--font-geist-mono)" }}>{fr}</strong>
                      {isWarn && " ⚠ truncated"}
                      {isError && " ✗ filtered"}
                    </span>
                  );
                })()}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Span timeline — hidden for per-call nodes (already showing the single span above) */}
      {!isPerCall && (
        <div className="px-5 py-4 border-t" style={{ borderColor: "hsl(var(--border))" }}>
          <SectionLabel>Calls ({spans.length})</SectionLabel>
          <div className="divide-y" style={{ borderColor: "hsl(var(--border) / 0.5)" }}>
            {spans.map((s: SpanNode, i: number) => {
              const isError = s.status !== "success";
              return (
              <details key={i} className="group">
                <summary className="flex items-center justify-between py-2 cursor-pointer hover:bg-accent/20 transition-colors list-none -mx-1 px-1 rounded">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className={cn("w-1.5 h-1.5 rounded-full flex-shrink-0", isError ? "bg-red-500" : "bg-emerald-500")} />
                    <span className="text-[11px] font-medium text-foreground truncate">{s.tool_name}</span>
                    <span className="text-[9px] px-1.5 py-0.5 rounded-full font-medium flex-shrink-0" style={{
                      background: isError ? "rgba(239,68,68,0.08)" : "rgba(16,185,129,0.08)",
                      color: isError ? "#ef4444" : "#10b981",
                    }}>{isError ? "error" : "ok"}</span>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0 text-[10px] text-muted-foreground">
                    <span style={{ fontFamily: "var(--font-geist-mono)" }}>{Math.round(s.latency_ms ?? 0)}ms</span>
                    {s.started_at && <Timestamp iso={s.started_at} compact />}
                  </div>
                </summary>
                <div className="pl-3.5 pb-2.5 space-y-2 mt-1">
                  {s.error && (
                    <div className="rounded-lg px-3 py-2 text-[10px]" style={{ background: "rgba(239,68,68,0.05)", color: "#ef4444", fontFamily: "var(--font-geist-mono)" }}>{s.error}</div>
                  )}
                  {s.input_json && (
                    <div>
                      <div className="flex items-center justify-between mb-1">
                        <p className="text-[9px] text-muted-foreground uppercase tracking-widest font-semibold">Input</p>
                        <button
                          className="text-[9px] text-primary hover:underline flex items-center gap-1 font-medium"
                          onClick={(e) => { e.stopPropagation(); onViewPayload?.(`Input — ${s.tool_name}`, [{ label: "JSON", json: s.input_json }]); }}
                        ><ExternalLink size={9} />View</button>
                      </div>
                      <pre className="text-[10px] text-foreground rounded-lg p-2.5 whitespace-pre-wrap break-all max-h-36 overflow-y-auto" style={{ fontFamily: "var(--font-geist-mono)", background: "hsl(var(--muted))", border: "1px solid hsl(var(--border))" }}>
                        {(() => { try { return JSON.stringify(JSON.parse(s.input_json), null, 2); } catch { return s.input_json; } })()}
                      </pre>
                    </div>
                  )}
                  {s.output_json && (
                    <div>
                      <div className="flex items-center justify-between mb-1">
                        <p className="text-[9px] text-muted-foreground uppercase tracking-widest font-semibold">Output</p>
                        <button
                          className="text-[9px] text-primary hover:underline flex items-center gap-1 font-medium"
                          onClick={(e) => { e.stopPropagation(); onViewPayload?.(`Output — ${s.tool_name}`, [{ label: "JSON", json: s.output_json }]); }}
                        ><ExternalLink size={9} />View</button>
                      </div>
                      <pre className="text-[10px] text-foreground rounded-lg p-2.5 whitespace-pre-wrap break-all max-h-36 overflow-y-auto" style={{ fontFamily: "var(--font-geist-mono)", background: "hsl(var(--muted))", border: "1px solid hsl(var(--border))" }}>
                        {(() => { try { return JSON.stringify(JSON.parse(s.output_json), null, 2); } catch { return s.output_json; } })()}
                      </pre>
                    </div>
                  )}
                  {/* LLM prompt/completion — shown on agent-type spans in the Calls list */}
                  {s.llm_input && (
                    <div>
                      <div className="flex items-center justify-between mb-1">
                        <p className="text-[9px] text-muted-foreground uppercase tracking-widest font-semibold">Prompt</p>
                        <button
                          className="text-[9px] text-primary hover:underline flex items-center gap-1 font-medium"
                          onClick={(e) => { e.stopPropagation(); onViewPayload?.(`Prompt — ${s.tool_name}`, [{ label: "Text", json: s.llm_input }]); }}
                        ><ExternalLink size={9} />View</button>
                      </div>
                      <pre className="text-[10px] text-foreground rounded-lg p-2.5 whitespace-pre-wrap break-all max-h-36 overflow-y-auto" style={{ fontFamily: "var(--font-geist-mono)", background: "hsl(var(--muted))", border: "1px solid hsl(var(--border))" }}>
                        {s.llm_input}
                      </pre>
                    </div>
                  )}
                  {s.llm_output && (
                    <div>
                      <div className="flex items-center justify-between mb-1">
                        <p className="text-[9px] text-muted-foreground uppercase tracking-widest font-semibold">Completion</p>
                        <button
                          className="text-[9px] text-primary hover:underline flex items-center gap-1 font-medium"
                          onClick={(e) => { e.stopPropagation(); onViewPayload?.(`Completion — ${s.tool_name}`, [{ label: "Text", json: s.llm_output }]); }}
                        ><ExternalLink size={9} />View</button>
                      </div>
                      <pre className="text-[10px] text-foreground rounded-lg p-2.5 whitespace-pre-wrap break-all max-h-36 overflow-y-auto" style={{ fontFamily: "var(--font-geist-mono)", background: "hsl(var(--muted))", border: "1px solid hsl(var(--border))" }}>
                        {s.llm_output}
                      </pre>
                    </div>
                  )}
                  {(s.input_tokens || s.output_tokens || s.finish_reason) && (
                    <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
                      {s.model_id && <span>Model: <code className="text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>{s.model_id}</code></span>}
                      {s.input_tokens != null && <span>In: <strong className="text-foreground">{s.input_tokens.toLocaleString()}</strong></span>}
                      {s.output_tokens != null && <span>Out: <strong className="text-foreground">{s.output_tokens.toLocaleString()}</strong></span>}
                      {s.finish_reason && (() => {
                        const fr = s.finish_reason!;
                        const isError = ["content_filter","safety","recitation","prohibited_content","content_filtered"].includes(fr);
                        const isWarn = ["max_tokens","length"].includes(fr);
                        return <span style={{ color: isError ? "hsl(var(--danger))" : isWarn ? "#f59e0b" : "inherit" }}>Stop: <strong style={{ fontFamily: "var(--font-geist-mono)" }}>{fr}</strong>{isWarn && " ⚠"}{isError && " ✗"}</span>;
                      })()}
                    </div>
                  )}
                </div>
              </details>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Edge detail panel ─────────────────────────────────────── */

function SessionEdgeDetail({
  source, target, metrics, spans, onViewPayload,
}: {
  source: string;
  target: string;
  metrics: PathMetrics | null;
  spans: SpanNode[];
  onViewPayload?: (title: string, tabs: { label: string; json: string | null }[]) => void;
}) {
  const sourceName = source.replace(/^(agent|server):/, "");
  const targetName = target.replace(/^(agent|server):/, "");

  if (!metrics) {
    return (
      <div className="h-full flex items-center justify-center text-sm text-muted-foreground">
        No data for this edge
      </div>
    );
  }

  const errorRate = metrics.callCount > 0 ? (metrics.errorCount / metrics.callCount) * 100 : 0;

  return (
    <div className="h-full overflow-y-auto">
      {/* Header */}
      <div className="px-5 pt-5 pb-4 border-b" style={{ borderColor: "hsl(var(--border))" }}>
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: "hsl(var(--primary) / 0.08)" }}>
            <Bot size={14} style={{ color: "hsl(var(--primary))" }} />
          </div>
          <span className="text-[12px] font-bold text-foreground">{sourceName}</span>
          <span className="text-[11px] text-muted-foreground">{"\u2192"}</span>
          <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: "rgba(100,116,139,0.08)" }}>
            <Server size={14} className="text-muted-foreground" />
          </div>
          <span className="text-[12px] font-bold text-foreground">{targetName}</span>
        </div>
        <p className="text-[10px] text-muted-foreground mt-1.5">
          Edge — {metrics.callCount} call{metrics.callCount !== 1 ? "s" : ""} on this path
        </p>
      </div>

      {/* Metrics */}
      <div className="px-5 py-4">
        <SectionLabel>Path Metrics</SectionLabel>
        <div className="grid grid-cols-2 gap-2">
          <MetricTile label="Calls" value={metrics.callCount.toLocaleString()} />
          <MetricTile label="Errors" value={metrics.errorCount.toLocaleString()} />
          <MetricTile label="Avg Latency" value={`${Math.round(metrics.avgLatencyMs)}ms`} />
          <MetricTile label="Max Latency" value={`${Math.round(metrics.maxLatencyMs)}ms`} />
        </div>
        {metrics.repeatCallCount != null && metrics.repeatCallCount >= 2 && metrics.repeatCallName && (
          <div className="mt-2 rounded-lg px-3 py-2 flex items-center justify-between" style={{ background: "rgba(245,158,11,0.08)", borderLeft: "3px solid #f59e0b" }}>
            <span className="text-[11px] text-muted-foreground">Repeated identical call</span>
            <span className="text-[12px] font-bold" style={{ color: "#b45309", fontFamily: "var(--font-geist-mono)" }}>
              {metrics.repeatCallName} {metrics.repeatCallCount}×
            </span>
          </div>
        )}
        {errorRate > 0 && (
          <div className="mt-2 rounded-lg px-3 py-2 flex items-center justify-between" style={{ background: "rgba(239,68,68,0.06)" }}>
            <span className="text-[11px] text-muted-foreground">Error Rate</span>
            <span className="text-[12px] font-bold" style={{ color: "#ef4444", fontFamily: "var(--font-geist-mono)" }}>{errorRate.toFixed(1)}%</span>
          </div>
        )}
      </div>

      {/* Tools on this path */}
      {metrics.tools.length > 0 && (
        <div className="px-5 py-4 border-t" style={{ borderColor: "hsl(var(--border))" }}>
          <SectionLabel>Tools ({metrics.tools.length})</SectionLabel>
          <div className="space-y-1">
            {metrics.tools.map((tool) => {
              const toolSpans = spans.filter((s) => s.tool_name === tool);
              const toolErrors = toolSpans.filter((s) => s.status !== "success").length;
              const toolAvgMs = toolSpans.length > 0
                ? toolSpans.reduce((s, sp) => s + (sp.latency_ms ?? 0), 0) / toolSpans.length : 0;
              return (
                <div key={tool} className="flex items-center justify-between rounded-lg px-3 py-2.5" style={{ background: "hsl(var(--muted))" }}>
                  <div className="flex items-center gap-2">
                    <span className={cn("w-1.5 h-1.5 rounded-full", toolErrors > 0 ? "bg-red-500" : "bg-emerald-500")} />
                    <span className="text-[12px] font-medium text-foreground">{tool}</span>
                  </div>
                  <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
                    <span style={{ fontFamily: "var(--font-geist-mono)" }}>{Math.round(toolAvgMs)}ms</span>
                    <span>{toolSpans.length}×</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Token usage */}
      {metrics.inputTokens > 0 && (
        <div className="px-5 py-4 border-t" style={{ borderColor: "hsl(var(--border))" }}>
          <SectionLabel>Token Usage</SectionLabel>
          <div className="grid grid-cols-2 gap-2">
            <MetricTile label="Input" value={metrics.inputTokens.toLocaleString()} />
            <MetricTile label="Output" value={metrics.outputTokens.toLocaleString()} />
          </div>
          {metrics.models.length > 0 && (
            <div className="mt-2 rounded-lg px-3 py-2 flex items-center gap-2" style={{ background: "hsl(var(--muted))" }}>
              <span className="text-[11px] text-muted-foreground">Model</span>
              {metrics.models.map((m) => (
                <code key={m} className="text-[11px] px-1.5 py-0.5 rounded" style={{ background: "hsl(var(--primary) / 0.08)", color: "hsl(var(--primary))", fontFamily: "var(--font-geist-mono)" }}>{m}</code>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Span timeline */}
      <div className="px-5 py-4 border-t" style={{ borderColor: "hsl(var(--border))" }}>
        <SectionLabel>Calls ({spans.length})</SectionLabel>
        <div className="space-y-2">
          {spans.map((s: SpanNode, i: number) => {
            const isErr = s.status !== "success";
            return (
            <details key={i} className="group rounded-xl overflow-hidden" style={{ border: "1px solid hsl(var(--border))", borderLeft: `3px solid ${isErr ? "#ef4444" : "#10b981"}` }}>
              <summary className="flex items-center justify-between px-3.5 py-2.5 cursor-pointer hover:bg-accent/30 transition-colors list-none">
                <div className="flex items-center gap-2">
                  <span className="text-[12px] font-semibold text-foreground">{s.tool_name}</span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded-full font-medium" style={{
                    background: isErr ? "rgba(239,68,68,0.08)" : "rgba(16,185,129,0.08)",
                    color: isErr ? "#ef4444" : "#10b981",
                  }}>{isErr ? "error" : "success"}</span>
                </div>
                <div className="flex flex-col items-end gap-0.5 flex-shrink-0">
                  <span className="text-[12px] text-muted-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>{Math.round(s.latency_ms ?? 0)}ms</span>
                  {s.started_at && <span className="text-[10px] text-muted-foreground" style={{ opacity: 0.6 }}><Timestamp iso={s.started_at} compact /></span>}
                </div>
              </summary>
              <div className="px-3.5 pb-3.5 space-y-2.5" style={{ borderTop: "1px solid hsl(var(--border))" }}>
                {s.error && (
                  <div className="mt-2 rounded-xl px-3.5 py-2.5 text-[11px]" style={{ background: "rgba(239,68,68,0.05)", color: "#ef4444", fontFamily: "var(--font-geist-mono)" }}>{s.error}</div>
                )}
                {s.input_json && (
                  <div className="mt-2">
                    <div className="flex items-center justify-between mb-1.5">
                      <p className="text-[11px] text-muted-foreground uppercase tracking-widest font-semibold">Input</p>
                      <button
                        className="text-[10px] text-primary hover:underline flex items-center gap-1 font-medium"
                        onClick={(e) => { e.stopPropagation(); onViewPayload?.(`Input — ${s.tool_name}`, [{ label: "JSON", json: s.input_json }]); }}
                      ><ExternalLink size={10} />View full</button>
                    </div>
                    <pre className="text-[11px] text-foreground rounded-xl p-3 whitespace-pre-wrap break-all max-h-48 overflow-y-auto" style={{ fontFamily: "var(--font-geist-mono)", background: "hsl(var(--muted))", border: "1px solid hsl(var(--border))" }}>
                      {(() => { try { return JSON.stringify(JSON.parse(s.input_json), null, 2); } catch { return s.input_json; } })()}
                    </pre>
                  </div>
                )}
                {s.output_json && (
                  <div>
                    <div className="flex items-center justify-between mb-1.5">
                      <p className="text-[11px] text-muted-foreground uppercase tracking-widest font-semibold">Output</p>
                      <button
                        className="text-[10px] text-primary hover:underline flex items-center gap-1 font-medium"
                        onClick={(e) => { e.stopPropagation(); onViewPayload?.(`Output — ${s.tool_name}`, [{ label: "JSON", json: s.output_json }]); }}
                      ><ExternalLink size={10} />View full</button>
                    </div>
                    <pre className="text-[11px] text-foreground rounded-xl p-3 whitespace-pre-wrap break-all max-h-48 overflow-y-auto" style={{ fontFamily: "var(--font-geist-mono)", background: "hsl(var(--muted))", border: "1px solid hsl(var(--border))" }}>
                      {(() => { try { return JSON.stringify(JSON.parse(s.output_json), null, 2); } catch { return s.output_json; } })()}
                    </pre>
                  </div>
                )}
              </div>
            </details>
            );
          })}
        </div>
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════ */
/* ── Session Detail Page ──────────────────────────────────────── */
/* ══════════════════════════════════════════════════════════════ */
export default function SessionDetailPage() {
  const params = useParams();
  const router = useRouter();
  const sessionId = params.id as string;

  const { activeProject } = useProject();
  const projectId = activeProject?.id;
  const p = projectId ? `&project_id=${projectId}` : "";

  /* Trace data */
  const [trace, setTrace] = useState<SessionTrace | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  /* Tabs */
  const [activeTab, setActiveTab] = useState<"details" | "trace">("details");

  /* Graph selection + expand/collapse */
  const [selection, setSelection] = useState<GraphSelection>(null);
  // Auto-expand all multi-caller servers on first load
  const autoExpandedRef = useRef(false);
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());
  const [expandedEdges, setExpandedEdges] = useState<Set<string>>(new Set());

  const handleToggleGroup = useCallback((groupId: string) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(groupId)) next.delete(groupId);
      else next.add(groupId);
      return next;
    });
    setSelection(null);
  }, []);

  const handleToggleEdge = useCallback((edgeId: string) => {
    setExpandedEdges((prev) => {
      const next = new Set(prev);
      if (next.has(edgeId)) next.delete(edgeId);
      else next.add(edgeId);
      console.log("[toggle-edge]", edgeId, "→ expanded:", [...next]);
      return next;
    });
    setSelection(null);
  }, []);
  // Auto-expand multi-caller servers when trace first loads
  useEffect(() => {
    if (!trace || autoExpandedRef.current) return;
    autoExpandedRef.current = true;
    const callerCount = new Map<string, Set<string>>();
    for (const span of trace.spans_flat) {
      if (span.span_type === "tool_call" && span.agent_name && span.server_name) {
        if (!callerCount.has(span.server_name)) callerCount.set(span.server_name, new Set());
        callerCount.get(span.server_name)!.add(span.agent_name);
      }
    }
    const toExpand = new Set<string>();
    for (const [server, agents] of callerCount) {
      if (agents.size >= 2) toExpand.add(`server:${server}`);
    }
    if (toExpand.size > 0) setExpandedGroups(toExpand);
  }, [trace]);

  const sessionGraph = useSessionGraph(trace, expandedGroups, expandedEdges);

  const handleExpandAll = useCallback(() => {
    const groups = new Set<string>();
    for (const n of sessionGraph.nodes) if (n.isCollapsible) groups.add(n.groupId ?? n.id);
    setExpandedGroups(groups);
    const edgeIds = new Set<string>();
    for (const [pk, pm] of sessionGraph.edgeMetrics) if (pm.callCount >= 2) edgeIds.add(pk);
    setExpandedEdges(edgeIds);
  }, [sessionGraph]);

  const handleCollapseAll = useCallback(() => {
    setExpandedGroups(new Set());
    setExpandedEdges(new Set());
    setSelection(null);
  }, []);

  /* Payload slideout */
  const [payloadSlideout, setPayloadSlideout] = useState<{ title: string; tabs: { label: string; json: string | null }[] } | null>(null);

  /* Graph fullscreen */
  const [graphFullscreen, setGraphFullscreen] = useState(false);

  /* Sessions list (for session metadata) */
  const { data: sessions } = useSWR<AgentSession[]>(
    `/api/agents/sessions?hours=168&limit=500${p}`,
    fetcher
  );

  /* Current session metadata from the sessions list */
  const session = useMemo(
    () => sessions?.find((s) => s.session_id === sessionId),
    [sessions, sessionId]
  );
  /* Fetch trace */
  useEffect(() => {
    setLoading(true);
    setTrace(null);
    setError(null);
    getSessionTrace(sessionId, projectId)
      .then((t) => { setTrace(t); setLoading(false); })
      .catch((e) => { setError(e.message); setLoading(false); });
  }, [sessionId, projectId]);

  return (
    <div className="page-in flex flex-col" style={{ height: "calc(100vh - 4rem)", paddingBottom: "1rem" }}>
      {/* ── Back + Header ──────────────────────────────────────── */}
      <SessionHeader
        sessionId={sessionId}
        trace={trace}
        session={session}
        onBack={() => router.push("/sessions")}
      />


      {/* ── Tab bar ────────────────────────────────────────────── */}
      <div className="flex-shrink-0 flex items-center gap-1 mb-3 border-b" role="tablist" aria-label="Session views" style={{ borderColor: "hsl(var(--border))" }}>
        {([
          { key: "details", label: "Details", count: trace ? (() => {
            const spanMap = new Map(trace.spans_flat.map((s: SpanNode) => [s.span_id, s]));
            const realServerSpans = trace.spans_flat.filter((s: SpanNode) => {
              if (s.span_type !== "tool_call") return false;
              // Skip LLM intent spans (parent is an agent span)
              if (s.parent_span_id) {
                const parent = spanMap.get(s.parent_span_id);
                if (parent?.span_type === "agent") return false;
              }
              return true;
            });
            const agentCount = new Set(trace.spans_flat.map((s: SpanNode) => s.agent_name).filter(Boolean)).size;
            const serverCount = new Set(realServerSpans.map((s: SpanNode) => s.server_name)).size;
            return `${agentCount} ${agentCount === 1 ? "agent" : "agents"} · ${serverCount} ${serverCount === 1 ? "server" : "servers"}`;
          })() : undefined },
          { key: "trace", label: "Trace", count: trace ? `${trace.total_spans} spans` : undefined },
        ] as const).map((tab) => (
          <button
            key={tab.key}
            role="tab"
            aria-selected={activeTab === tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={cn(
              "px-4 py-2.5 text-[12px] font-medium border-b-2 -mb-px transition-colors",
              activeTab === tab.key
                ? "border-primary text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            {tab.label}
            {tab.count && (
              <span className="ml-2 text-[10px] px-1.5 py-0.5 rounded-full" style={{ background: "hsl(var(--muted))" }}>
                {tab.count}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* ── Details tab — session lineage graph ─────────────────── */}
      {activeTab === "details" && (
        <div className="flex-1 flex gap-0 rounded-xl border overflow-hidden min-h-0" style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}>
          {/* Graph (~70%) */}
          <div className="flex-[7] flex flex-col">
            {/* Timeline bar */}
            {trace && trace.duration_ms && (
              <div className="flex-shrink-0 px-3 pt-2">
                <SessionTimeline
                  spans={trace.spans_flat}
                  sessionDurationMs={trace.duration_ms}
                  onSelectNode={(nodeId) => setSelection({ type: "node", id: nodeId })}
                />
              </div>
            )}
            {/* Graph */}
            <div className="flex-1 relative min-h-0">
              {loading ? (
                <div className="flex items-center justify-center h-full">
                  <div className="w-6 h-6 rounded-full border-2 border-primary border-t-transparent spin" />
                </div>
              ) : !trace ? (
                <div className="flex items-center justify-center h-full text-sm text-muted-foreground">No data</div>
              ) : (
                <>
                  <LineageGraph
                    nodes={sessionGraph.nodes}
                    edges={sessionGraph.edges}
                    selection={selection}
                    onSelectionChange={setSelection}
                    expandedGroups={expandedGroups}
                    onToggleGroup={handleToggleGroup}
                    expandedEdges={expandedEdges}
                    onToggleEdge={handleToggleEdge}
                    onExpandAll={handleExpandAll}
                    onCollapseAll={handleCollapseAll}
                    nodeHeight={76}
                    className="h-full"
                  />
                  {/* Fullscreen button — top-right corner overlay */}
                  <button
                    onClick={() => setGraphFullscreen(true)}
                    className="btn btn-secondary absolute top-2 right-2 h-[26px] px-2 text-[11px] flex items-center gap-1 z-10"
                    title="Fullscreen"
                  >
                    <Maximize2 size={12} />
                  </button>
                </>
              )}
            </div>

            {/* Fullscreen overlay */}
            {graphFullscreen && trace && (
              <div className="fixed inset-0 z-50 flex flex-col" style={{ background: "hsl(var(--background))" }}>
                <div className="flex items-center justify-between px-4 py-2 border-b flex-shrink-0" style={{ borderColor: "hsl(var(--border))" }}>
                  <span className="text-[13px] font-semibold" style={{ color: "hsl(var(--foreground))" }}>Session graph — {sessionId}</span>
                  <button
                    onClick={() => setGraphFullscreen(false)}
                    className="btn btn-secondary text-xs flex items-center gap-1.5"
                  >
                    <Minimize2 size={12} /> Exit fullscreen
                  </button>
                </div>
                <div className="flex-1 relative min-h-0">
                  <LineageGraph
                    nodes={sessionGraph.nodes}
                    edges={sessionGraph.edges}
                    selection={selection}
                    onSelectionChange={setSelection}
                    expandedGroups={expandedGroups}
                    onToggleGroup={handleToggleGroup}
                    expandedEdges={expandedEdges}
                    onToggleEdge={handleToggleEdge}
                    onExpandAll={handleExpandAll}
                    onCollapseAll={handleCollapseAll}
                    nodeHeight={76}
                    className="h-full"
                  />
                </div>
              </div>
            )}
          </div>
          {/* Right panel (~30%) */}
          <div className="flex-[3] border-l overflow-y-auto" style={{ borderColor: "hsl(var(--border))", background: "hsl(var(--background))" }}>
            {selection?.type === "node" && trace ? (
              <SessionNodeDetail
                nodeId={selection.id}
                trace={trace}
                serverCallers={sessionGraph.serverCallers}
                onViewPayload={(title, tabs) => setPayloadSlideout({ title, tabs })}
              />
            ) : selection?.type === "edge" && trace ? (
              <SessionEdgeDetail
                source={selection.source}
                target={selection.target}
                metrics={sessionGraph.edgeMetrics.get(`${selection.source}→${selection.target}`) ?? null}
                spans={sessionGraph.edgeSpans.get(`${selection.source}→${selection.target}`) ?? []}
                onViewPayload={(title, tabs) => setPayloadSlideout({ title, tabs })}
              />
            ) : (
              <SessionMetrics trace={trace} session={session} />
            )}
          </div>
        </div>
      )}

      {/* ── Trace tab — span tree ──────────────────────────────── */}
      {activeTab === "trace" && (
        <>
          {trace && <TokenSummaryBar trace={trace} />}
          <div
            className="flex-1 rounded-xl border overflow-hidden flex flex-col min-h-0"
            style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
          >
            <div className="flex-1 overflow-y-auto overflow-x-auto">
              <SpanTree
                trace={trace}
                loading={loading}
                error={error}
                onViewPayload={(title, tabs) => setPayloadSlideout({ title, tabs })}
              />
            </div>
          </div>
        </>
      )}

      {/* ── Payload slideout ── */}
      {payloadSlideout && (
        <PayloadSlideout
          open={true}
          onClose={() => setPayloadSlideout(null)}
          title={payloadSlideout.title}
          tabs={payloadSlideout.tabs}
        />
      )}
    </div>
  );
}
