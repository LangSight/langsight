"use client";

export const dynamic = "force-dynamic";

import { useState, useEffect, useMemo, useCallback, useRef } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import useSWR from "swr";
import {
  ChevronRight, ChevronDown, GitBranch, Clock, Zap, AlertCircle,
  Search, GitCompare, Play, ArrowLeft, Columns2, Bot, Server,
  Maximize2, Minimize2, ExternalLink, X,
} from "lucide-react";
import { LineageGraph, type GraphNode, type GraphEdge, type GraphSelection } from "@/components/lineage-graph";
import { PayloadSlideout } from "@/components/payload-slideout";
import { SessionTimeline } from "@/components/session-timeline";
import { fetcher, getSessionTrace, compareSessions, replaySession } from "@/lib/api";
import { useProject } from "@/lib/project-context";
import { buildSessionGraph, type SessionGraphResult } from "@/lib/session-graph";
import { cn, timeAgo, formatDuration, formatExact, CALL_STATUS_COLOR, SPAN_TYPE_ICON } from "@/lib/utils";
import { Timestamp } from "@/components/timestamp";
import type { AgentSession, SessionTrace, SpanNode, SessionComparison, DiffEntry, PathMetrics, ServerCallerInfo } from "@/lib/types";
import { HealthTagBadge } from "@/components/health-tag-badge";

/* ── Build session graph from trace spans (with per-path attribution) ── */

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

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-[9px] font-semibold text-muted-foreground uppercase tracking-widest mb-2.5">{children}</p>
  );
}

function MetricTile({ label, value, danger }: { label: string; value: string; danger?: boolean; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between py-1.5">
      <span className="text-[11px] text-muted-foreground">{label}</span>
      <span className={cn("text-[12px] font-semibold", danger ? "text-red-500" : "text-foreground")} style={{ fontFamily: "var(--font-geist-mono)" }}>{value}</span>
    </div>
  );
}

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
        const callers = serverCallers.get(name) ?? [];
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
          {spans[0].error && (
            <div className="mb-3">
              <SectionLabel>Error</SectionLabel>
              <div className="rounded-lg px-3 py-2.5 text-[11px]" style={{ background: "rgba(239,68,68,0.06)", color: "#ef4444", fontFamily: "var(--font-geist-mono)" }}>{spans[0].error}</div>
            </div>
          )}
          {(spans[0].input_tokens || spans[0].output_tokens) && (
            <div>
              <SectionLabel>Tokens</SectionLabel>
              <div className="flex items-center gap-4 text-[11px] text-muted-foreground">
                {spans[0].model_id && <span>Model: <code className="text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>{spans[0].model_id}</code></span>}
                {spans[0].input_tokens != null && <span>In: <strong className="text-foreground">{spans[0].input_tokens}</strong></span>}
                {spans[0].output_tokens != null && <span>Out: <strong className="text-foreground">{spans[0].output_tokens}</strong></span>}
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
                  {(s.input_tokens || s.output_tokens) && (
                    <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
                      {s.model_id && <span>Model: <code className="text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>{s.model_id}</code></span>}
                      {s.input_tokens != null && <span>In: <strong className="text-foreground">{s.input_tokens.toLocaleString()}</strong></span>}
                      {s.output_tokens != null && <span>Out: <strong className="text-foreground">{s.output_tokens.toLocaleString()}</strong></span>}
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

/* ── Payload panel ──────────────────────────────────────────── */
function PayloadPanel({ label, json, onViewFull }: { label: string; json: string | null; onViewFull?: () => void }) {
  if (!json) return null;
  let formatted = json;
  try { formatted = JSON.stringify(JSON.parse(json), null, 2); } catch { /* keep raw */ }
  return (
    <div className="mt-2">
      <div className="flex items-center justify-between mb-1.5">
        <p className="text-[11px] font-semibold text-muted-foreground uppercase tracking-widest">{label}</p>
        {onViewFull && (
          <button onClick={(e) => { e.stopPropagation(); onViewFull(); }} className="text-[10px] text-primary hover:underline flex items-center gap-1 font-medium">
            <ExternalLink size={10} />View full
          </button>
        )}
      </div>
      <pre
        className="text-[11px] rounded-xl p-3 overflow-x-auto whitespace-pre-wrap break-all leading-relaxed max-h-48 overflow-y-auto"
        style={{
          fontFamily: "var(--font-geist-mono)",
          background: "hsl(var(--muted))",
          color: "hsl(var(--foreground))",
          border: "1px solid hsl(var(--border))",
        }}
      >
        {formatted}
      </pre>
    </div>
  );
}

/* ── Span row ───────────────────────────────────────────────── */
function SpanRow({ span, depth = 0, onViewPayload }: { span: SpanNode; depth?: number; onViewPayload?: (title: string, tabs: { label: string; json: string | null }[]) => void }) {
  const [open, setOpen] = useState(true);
  const [detailOpen, setDetailOpen] = useState(false);
  const icon = SPAN_TYPE_ICON[span.span_type] ?? "●";
  const hasChildren = span.children && span.children.length > 0;
  const isLlmSpan = span.span_type === "agent" && (span.llm_input || span.llm_output);
  const hasPayload = span.input_json || span.output_json || span.llm_input || span.llm_output || span.error;
  const isError = span.status === "error";
  const isPrevented = span.status === "prevented";

  const spanColor =
    span.span_type === "handoff" ? "text-yellow-500"
    : span.span_type === "agent" ? "text-primary"
    : "text-foreground";

  const statusBadge = isError
    ? { text: "error", bg: "rgba(239,68,68,0.08)", color: "#ef4444" }
    : isPrevented
      ? { text: "prevented", bg: "rgba(234,179,8,0.08)", color: "#eab308" }
      : span.status === "success"
        ? { text: "success", bg: "rgba(16,185,129,0.08)", color: "#10b981" }
        : { text: span.status, bg: "hsl(var(--muted))", color: "hsl(var(--muted-foreground))" };

  return (
    <>
      <tr
        className={cn(
          "group transition-colors",
          hasPayload ? "cursor-pointer hover:bg-accent/40" : "hover:bg-accent/20",
          detailOpen && "bg-accent/20"
        )}
        style={{ borderBottom: "1px solid hsl(var(--border) / 0.4)", borderLeft: isError ? "3px solid #ef4444" : isPrevented ? "3px solid #eab308" : "3px solid transparent" }}
        onClick={() => hasPayload && setDetailOpen((o) => !o)}
      >
        <td className="py-2.5 pr-3">
          <div className="flex items-center" style={{ paddingLeft: `${depth * 28 + 8}px` }}>
            {/* Tree connector lines for nested spans */}
            {depth > 0 && (
              <span className="text-[12px] mr-1.5 flex-shrink-0" style={{ color: "hsl(var(--border))", fontFamily: "var(--font-geist-mono)" }}>└─</span>
            )}
            <button
              onClick={(e) => { e.stopPropagation(); hasChildren && setOpen((o) => !o); }}
              className={cn("flex items-center gap-1.5 min-w-0", hasChildren ? "cursor-pointer" : "cursor-default")}
            >
              {hasChildren
                ? open
                  ? <ChevronDown size={12} className="text-muted-foreground flex-shrink-0" />
                  : <ChevronRight size={12} className="text-muted-foreground flex-shrink-0" />
                : depth === 0 ? <span className="w-3.5 flex-shrink-0" /> : null}
              <span className="text-[12px] mr-1">{icon}</span>
              <span className={cn("text-[12px] font-semibold truncate", spanColor)} style={{ fontFamily: "var(--font-geist-mono)" }}>
                {span.server_name}/{span.tool_name}
              </span>
            </button>
            {hasPayload && (
              <span className="ml-2 text-[10px] text-muted-foreground opacity-0 group-hover:opacity-60 transition-opacity">
                {detailOpen ? "▲" : "▼"}
              </span>
            )}
          </div>
        </td>
        <td className="py-2.5 pr-3 text-[12px] text-muted-foreground">{span.agent_name || "—"}</td>
        <td className="py-2.5 pr-3">
          <span className="text-[10px] px-1.5 py-0.5 rounded-full font-medium" style={{ background: statusBadge.bg, color: statusBadge.color }}>
            {statusBadge.text}
          </span>
        </td>
        <td className="py-2.5 pr-3 text-[12px] text-right text-muted-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>
          {span.latency_ms ? `${span.latency_ms.toFixed(0)}ms` : "—"}
        </td>
        <td className="py-2.5 pr-3 text-[11px] text-muted-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>
          {span.input_tokens != null || span.output_tokens != null ? (
            <span className="flex items-center gap-1.5">
              {span.input_tokens != null && <span title="Input tokens">↑{span.input_tokens.toLocaleString()}</span>}
              {span.output_tokens != null && <span title="Output tokens">↓{span.output_tokens.toLocaleString()}</span>}
            </span>
          ) : "—"}
        </td>
        <td className="py-2.5 pr-3 text-[11px] text-muted-foreground">
          {span.started_at ? <Timestamp iso={span.started_at} compact /> : "—"}
        </td>
        <td className="py-2.5 text-[11px] text-red-500 truncate max-w-xs">{span.error?.slice(0, 80) ?? ""}</td>
      </tr>

      {detailOpen && hasPayload && (
        <tr style={{ background: "hsl(var(--muted) / 0.4)" }}>
          <td colSpan={7} className="px-4 pb-4 pt-2" style={{ paddingLeft: `${depth * 20 + 32}px` }}>
            {isLlmSpan ? (
              <>
                <PayloadPanel label="Prompt" json={span.llm_input ?? null} onViewFull={span.llm_input ? () => onViewPayload?.(`Prompt — ${span.tool_name}`, [{ label: "JSON", json: span.llm_input ?? null }]) : undefined} />
                <PayloadPanel label="Completion" json={span.llm_output ?? null} onViewFull={span.llm_output ? () => onViewPayload?.(`Completion — ${span.tool_name}`, [{ label: "JSON", json: span.llm_output ?? null }]) : undefined} />
              </>
            ) : (
              <>
                <PayloadPanel label="Input" json={span.input_json ?? null} onViewFull={span.input_json ? () => onViewPayload?.(`Input — ${span.tool_name}`, [{ label: "JSON", json: span.input_json ?? null }]) : undefined} />
                <PayloadPanel label="Output" json={span.output_json ?? null} onViewFull={span.output_json ? () => onViewPayload?.(`Output — ${span.tool_name}`, [{ label: "JSON", json: span.output_json ?? null }]) : undefined} />
              </>
            )}
            {span.error && !span.output_json && !span.llm_output && (
              <div className="mt-2">
                <p className="text-[11px] font-semibold uppercase tracking-widest mb-1.5" style={{ color: "hsl(var(--danger))" }}>Error</p>
                <pre
                  className="text-[11px] rounded-xl p-3 whitespace-pre-wrap break-all"
                  style={{
                    fontFamily: "var(--font-geist-mono)",
                    background: "hsl(var(--danger-bg))",
                    color: "hsl(var(--danger))",
                    border: "1px solid hsl(var(--danger) / 0.2)",
                  }}
                >
                  {span.error}
                </pre>
              </div>
            )}
          </td>
        </tr>
      )}
      {open && span.children?.map((child) => (
        <SpanRow key={child.span_id} span={child} depth={depth + 1} onViewPayload={onViewPayload} />
      ))}
    </>
  );
}

/* ── Diff row (compare view) ──────────────────────────────────── */
function DiffRow({ entry }: { entry: DiffEntry }) {
  const latStr = (span: Record<string, unknown> | null) =>
    span?.latency_ms != null ? `${Number(span.latency_ms).toFixed(0)}ms` : "—";
  const statusStr = (span: Record<string, unknown> | null) =>
    span ? (span.status === "success" ? "✓" : span.status === "error" ? "✗" : span.status === "prevented" ? "⊘" : "⏱") : "—";
  const deltaColor =
    entry.latency_delta_pct === null ? ""
    : entry.latency_delta_pct > 0 ? "text-red-500" : "text-emerald-500";

  const rowBg =
    entry.status === "matched" ? ""
    : entry.status === "diverged" ? "bg-yellow-500/5"
    : entry.status === "only_a"  ? "bg-blue-500/5"
    : "bg-purple-500/5";

  const statusIcon =
    entry.status === "matched" ? "=" : entry.status === "diverged" ? "≠"
    : entry.status === "only_a" ? "A" : "B";

  const statusColor =
    entry.status === "matched" ? "text-emerald-500"
    : entry.status === "diverged" ? "text-yellow-500"
    : entry.status === "only_a" ? "text-blue-400"
    : "text-purple-400";

  return (
    <tr className={cn("border-b border-border/50 text-[12px]", rowBg)}>
      <td className="px-4 py-2 font-mono truncate max-w-[200px]" style={{ fontFamily: "var(--font-geist-mono)" }}>
        <span className={cn("mr-2 font-bold", statusColor)}>{statusIcon}</span>
        <span className="text-muted-foreground">{entry.tool_key}</span>
      </td>
      <td className="px-4 py-2 text-center font-mono" style={{ fontFamily: "var(--font-geist-mono)" }}>
        <span className={entry.span_a ? (CALL_STATUS_COLOR[entry.span_a.status as keyof typeof CALL_STATUS_COLOR] ?? "") : "text-muted-foreground"}>
          {statusStr(entry.span_a)}
        </span>
      </td>
      <td className="px-4 py-2 text-right font-mono text-muted-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>
        {latStr(entry.span_a)}
      </td>
      <td className="px-4 py-2 text-center font-mono" style={{ fontFamily: "var(--font-geist-mono)" }}>
        <span className={entry.span_b ? (CALL_STATUS_COLOR[entry.span_b.status as keyof typeof CALL_STATUS_COLOR] ?? "") : "text-muted-foreground"}>
          {statusStr(entry.span_b)}
        </span>
      </td>
      <td className="px-4 py-2 text-right font-mono text-muted-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>
        {latStr(entry.span_b)}
      </td>
      <td className={cn("px-4 py-2 text-right font-mono font-semibold", deltaColor)} style={{ fontFamily: "var(--font-geist-mono)" }}>
        {entry.latency_delta_pct !== null
          ? `${entry.latency_delta_pct > 0 ? "+" : ""}${entry.latency_delta_pct}%`
          : "—"}
      </td>
    </tr>
  );
}

/* ── Compare picker ───────────────────────────────────────────── */
function ComparePicker({
  sessions,
  selectedId,
  onPick,
  onCancel,
}: {
  sessions: AgentSession[];
  selectedId: string;
  onPick: (id: string) => void;
  onCancel: () => void;
}) {
  const [pickerSearch, setPickerSearch] = useState("");

  const candidates = useMemo(() => {
    return sessions
      .filter((s) => s.session_id !== selectedId)
      .filter((s) => {
        if (!pickerSearch) return true;
        const q = pickerSearch.toLowerCase();
        return (
          s.session_id.toLowerCase().includes(q) ||
          (s.agent_name ?? "").toLowerCase().includes(q)
        );
      })
      .slice(0, 10);
  }, [sessions, selectedId, pickerSearch]);

  return (
    <div
      className="mt-6 rounded-xl border overflow-hidden"
      style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
    >
      <div
        className="border-b px-4 py-3"
        style={{ background: "hsl(var(--card-raised))", borderColor: "hsl(var(--border))" }}
      >
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <GitCompare size={13} className="text-primary" />
            <span className="text-sm font-semibold text-foreground">Select a session to compare with</span>
          </div>
          <button onClick={onCancel} className="btn btn-ghost text-xs">Cancel</button>
        </div>
        <div className="mt-3">
          <div className="relative max-w-sm">
            <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              type="text"
              value={pickerSearch}
              onChange={(e) => setPickerSearch(e.target.value)}
              placeholder="Search session ID or agent..."
              className="input-base pl-8 h-[34px] text-[13px] w-full"
              autoFocus
            />
          </div>
        </div>
      </div>

      <div className="max-h-[400px] overflow-y-auto">
        {candidates.length === 0 ? (
          <p className="p-8 text-center text-sm text-muted-foreground">No matching sessions</p>
        ) : (
          <div className="divide-y" style={{ borderColor: "hsl(var(--border))" }}>
            {candidates.map((s) => (
              <button
                key={s.session_id}
                onClick={() => onPick(s.session_id)}
                className="w-full text-left px-4 py-3 hover:bg-accent/40 transition-colors flex items-center justify-between gap-4"
              >
                <div className="min-w-0">
                  <code
                    className="text-[12px] text-foreground block truncate"
                    style={{ fontFamily: "var(--font-geist-mono)" }}
                  >
                    {s.session_id.slice(0, 24)}...
                  </code>
                  <div className="flex items-center gap-2 text-[11px] text-muted-foreground mt-0.5">
                    {s.agent_name && <span>{s.agent_name}</span>}
                    <span>{s.tool_calls} calls</span>
                    {s.failed_calls > 0 && (
                      <span style={{ color: "hsl(var(--danger))" }}>{s.failed_calls} failed</span>
                    )}
                    <span>{formatDuration(s.duration_ms)}</span>
                  </div>
                </div>
                <div className="flex items-center gap-1 text-[11px] text-muted-foreground flex-shrink-0">
                  <Clock size={11} />
                  <Timestamp iso={s.first_call_at} compact />
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Compare detail ───────────────────────────────────────────── */
function CompareDetail({
  idA, idB, sessionA, sessionB, onBack, projectId,
}: {
  idA: string;
  idB: string;
  sessionA: AgentSession | undefined;
  sessionB: AgentSession | undefined;
  onBack: () => void;
  projectId?: string;
}) {
  const [cmp, setCmp] = useState<SessionComparison | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setCmp(null);
    setError(null);
    compareSessions(idA, idB, projectId)
      .then((c) => { setCmp(c); setLoading(false); })
      .catch((e) => { setError(e.message); setLoading(false); });
  }, [idA, idB, projectId]);

  return (
    <div
      className="mt-6 rounded-xl border overflow-hidden"
      style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
    >
      <div
        className="border-b px-4 py-3"
        style={{ background: "hsl(var(--card-raised))", borderColor: "hsl(var(--border))" }}
      >
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <Columns2 size={13} className="text-primary flex-shrink-0" />
            <div className="flex items-center gap-2 text-[12px] min-w-0" style={{ fontFamily: "var(--font-geist-mono)" }}>
              <div className="flex items-center gap-1.5 min-w-0">
                <span className="text-[10px] font-bold text-blue-400 bg-blue-500/10 px-1.5 py-0.5 rounded">Base</span>
                <span className="text-foreground truncate">{idA.slice(0, 12)}...</span>
                {sessionA?.agent_name && <span className="text-muted-foreground text-[11px]">({sessionA.agent_name})</span>}
              </div>
              <span className="text-muted-foreground">vs</span>
              <div className="flex items-center gap-1.5 min-w-0">
                <span className="text-[10px] font-bold text-purple-400 bg-purple-500/10 px-1.5 py-0.5 rounded">Compare</span>
                <span className="text-foreground truncate">{idB.slice(0, 12)}...</span>
                {sessionB?.agent_name && <span className="text-muted-foreground text-[11px]">({sessionB.agent_name})</span>}
              </div>
            </div>
          </div>
          <button onClick={onBack} className="btn btn-ghost text-xs">Close</button>
        </div>
        {cmp && (
          <div className="flex items-center gap-2 text-[11px] mt-2 ml-[28px]">
            <span className="text-emerald-500">{cmp.summary.matched} matched</span>
            {cmp.summary.diverged > 0 && <><span className="text-muted-foreground">·</span><span className="text-yellow-500">{cmp.summary.diverged} diverged</span></>}
            {cmp.summary.only_a > 0 && <><span className="text-muted-foreground">·</span><span className="text-blue-400">{cmp.summary.only_a} only in base</span></>}
            {cmp.summary.only_b > 0 && <><span className="text-muted-foreground">·</span><span className="text-purple-400">{cmp.summary.only_b} only in compare</span></>}
          </div>
        )}
      </div>

      <div className="overflow-x-auto">
        {loading ? (
          <div className="p-10 flex items-center justify-center">
            <div className="w-6 h-6 rounded-full border-2 border-primary border-t-transparent spin" />
          </div>
        ) : error ? (
          <div className="p-8 text-center text-sm" style={{ color: "hsl(var(--danger))" }}>
            <AlertCircle size={20} className="mx-auto mb-2" /> {error}
          </div>
        ) : !cmp || cmp.diff.length === 0 ? (
          <p className="p-8 text-center text-sm text-muted-foreground">No spans found</p>
        ) : (
          <table className="w-full">
            <thead>
              <tr style={{ borderBottom: "1px solid hsl(var(--border))", background: "hsl(var(--card-raised))" }}>
                <th className="px-4 py-2.5 text-left text-[11px] font-semibold text-muted-foreground uppercase tracking-wide">Tool</th>
                <th className="px-4 py-2.5 text-center text-[11px] font-semibold text-blue-400 uppercase tracking-wide">Base status</th>
                <th className="px-4 py-2.5 text-right text-[11px] font-semibold text-blue-400 uppercase tracking-wide">Base latency</th>
                <th className="px-4 py-2.5 text-center text-[11px] font-semibold text-purple-400 uppercase tracking-wide">Compare status</th>
                <th className="px-4 py-2.5 text-right text-[11px] font-semibold text-purple-400 uppercase tracking-wide">Compare latency</th>
                <th className="px-4 py-2.5 text-right text-[11px] font-semibold text-muted-foreground uppercase tracking-wide">Delta</th>
              </tr>
            </thead>
            <tbody>
              {cmp.diff.map((entry, i) => <DiffRow key={i} entry={entry} />)}
            </tbody>
          </table>
        )}
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

  /* Replay */
  const [replaying, setReplaying] = useState(false);
  const [replayError, setReplayError] = useState<string | null>(null);

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

  /* Compare */
  const [comparePicking, setComparePicking] = useState(false);
  const [compareWith, setCompareWith] = useState<string | null>(null);

  /* Sessions list (for compare picker) */
  const { data: sessions } = useSWR<AgentSession[]>(
    `/api/agents/sessions?hours=168&limit=500${p}`,
    fetcher
  );

  /* Current session metadata from the sessions list */
  const session = useMemo(
    () => sessions?.find((s) => s.session_id === sessionId),
    [sessions, sessionId]
  );
  const compareSession = useMemo(
    () => sessions?.find((s) => s.session_id === compareWith),
    [sessions, compareWith]
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

  async function handleReplay() {
    setReplaying(true);
    setReplayError(null);
    try {
      await replaySession(sessionId, 10, 60, projectId);
    } catch (e: unknown) {
      setReplayError(e instanceof Error ? e.message : "Replay failed");
    } finally {
      setReplaying(false);
    }
  }

  return (
    <div className="page-in flex flex-col" style={{ height: "calc(100vh - 4rem)", paddingBottom: "1rem" }}>
      {/* ── Back + Header ──────────────────────────────────────── */}
      <div className="flex-shrink-0 pb-3">
        <button
          onClick={() => router.push("/sessions")}
          className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors mb-3"
        >
          <ArrowLeft size={14} />
          Back to Sessions
        </button>

        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 min-w-0">
            <GitBranch size={15} className="text-primary flex-shrink-0" />
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <code
                  className="text-[13px] text-foreground truncate"
                  style={{ fontFamily: "var(--font-geist-mono)" }}
                >
                  {sessionId}
                </code>
                {trace && (() => {
                  const agents = Array.from(new Set(trace.spans_flat.map((s: SpanNode) => s.agent_name).filter(Boolean)));
                  return agents.length > 0 ? (
                    <span className="text-[11px] text-primary font-medium flex-shrink-0">{agents.join(" → ")}</span>
                  ) : session?.agent_name ? (
                    <span className="text-[11px] text-primary font-medium flex-shrink-0">{session.agent_name}</span>
                  ) : null;
                })()}
              </div>
              <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground mt-0.5" style={{ fontFamily: "var(--font-geist-mono)" }}>
                {trace && (
                  <>
                    <span>{trace.total_spans} spans</span>
                    <span className="opacity-40">·</span>
                    <span>{trace.tool_calls} {trace.tool_calls === 1 ? "call" : "calls"}</span>
                    {trace.failed_calls > 0 && (
                      <><span className="opacity-40">·</span>
                      <span style={{ color: "hsl(var(--danger))" }} className="font-semibold">
                        {trace.failed_calls} failed
                      </span></>
                    )}
                    {trace.duration_ms && (
                      <><span className="opacity-40">·</span><span>{formatDuration(trace.duration_ms)}</span></>
                    )}
                  </>
                )}
                {session && (
                  <>
                    <span className="opacity-40">·</span>
                    <span className="flex items-center gap-1"><Clock size={9} /><Timestamp iso={session.first_call_at} compact /></span>
                    <span className="opacity-40">·</span>
                    <span>{formatExact(session.first_call_at)}</span>
                  </>
                )}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2.5 flex-shrink-0">
            <button
              onClick={handleReplay}
              disabled={replaying || loading}
              className="flex items-center gap-2 text-[13px] font-medium py-2 px-4 rounded-xl transition-all"
              style={{
                background: "linear-gradient(135deg, hsl(var(--primary) / 0.08), hsl(var(--primary) / 0.02))",
                border: "1px solid hsl(var(--primary) / 0.2)",
                color: "hsl(var(--primary))",
                opacity: replaying || loading ? 0.5 : 1,
                cursor: replaying || loading ? "not-allowed" : "pointer",
              }}
            >
              {replaying
                ? <><span className="w-3.5 h-3.5 border-2 border-current border-t-transparent rounded-full" style={{ animation: "spin 0.6s linear infinite" }} />Replaying...</>
                : <><div className="w-6 h-6 rounded-lg flex items-center justify-center" style={{ background: "hsl(var(--primary) / 0.12)" }}><Play size={12} /></div>Replay</>
              }
            </button>
            <button
              onClick={() => { setComparePicking((v) => !v); setCompareWith(null); }}
              className="flex items-center gap-2 text-[13px] font-medium py-2 px-4 rounded-xl transition-all"
              style={{
                background: comparePicking
                  ? "hsl(var(--primary))"
                  : "linear-gradient(135deg, hsl(var(--muted)), hsl(var(--card)))",
                border: comparePicking
                  ? "1px solid hsl(var(--primary))"
                  : "1px solid hsl(var(--border))",
                color: comparePicking ? "white" : "hsl(var(--foreground))",
              }}
            >
              <div className="w-6 h-6 rounded-lg flex items-center justify-center" style={{ background: comparePicking ? "rgba(255,255,255,0.15)" : "hsl(var(--muted))" }}><GitCompare size={12} /></div>Compare
            </button>
          </div>
        </div>
      </div>

      {replayError && (
        <div
          className="flex-shrink-0 rounded-lg px-4 py-2 text-xs mb-3"
          style={{ background: "hsl(var(--danger-bg))", color: "hsl(var(--danger))", border: "1px solid hsl(var(--danger) / 0.2)" }}
        >
          Replay failed: {replayError}
        </div>
      )}

      {/* ── Tab bar ────────────────────────────────────────────── */}
      <div className="flex-shrink-0 flex items-center gap-1 mb-3 border-b" style={{ borderColor: "hsl(var(--border))" }}>
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
              <div className="p-5 space-y-5">
                {/* Session summary header */}
                <div className="flex items-center justify-between">
                  <p className="text-[12px] font-semibold text-foreground">Session Summary</p>
                  {(session?.health_tag || (trace && trace.failed_calls === 0)) && (
                    <HealthTagBadge tag={session?.health_tag ?? (trace && trace.failed_calls > 0 ? "tool_failure" : "success")} />
                  )}
                </div>

                {/* Stats — clean rows */}
                {trace && (
                  <div>
                    <SectionLabel>Overview</SectionLabel>
                    <div className="divide-y" style={{ borderColor: "hsl(var(--border) / 0.5)" }}>
                      <MetricTile label="Duration" value={trace.duration_ms ? formatDuration(trace.duration_ms) : "—"} />
                      <MetricTile label="Total Spans" value={String(trace.spans_flat.length)} />
                      <MetricTile label="Tool Calls" value={String(trace.spans_flat.filter((s: SpanNode) => s.span_type === "tool_call").length)} />
                      <MetricTile label="Errors" value={String(trace.spans_flat.filter((s: SpanNode) => s.status === "error").length)} danger={(trace.spans_flat.filter((s: SpanNode) => s.status === "error").length) > 0} />
                    </div>
                  </div>
                )}

                {/* Agents & Servers */}
                {trace && (
                  <div className="space-y-3">
                    <div>
                      <SectionLabel>Agents</SectionLabel>
                      <div className="flex flex-wrap gap-1">
                        {Array.from(new Set(trace.spans_flat.map((s: SpanNode) => s.agent_name).filter(Boolean))).map((a) => (
                          <span key={a as string} className="px-2 py-0.5 rounded text-[10px] font-medium" style={{ background: "hsl(var(--primary) / 0.08)", color: "hsl(var(--primary))", border: "1px solid hsl(var(--primary) / 0.15)" }}>{a as string}</span>
                        ))}
                      </div>
                    </div>
                    <div>
                      <SectionLabel>Servers</SectionLabel>
                      <div className="flex flex-wrap gap-1">
                        {Array.from(new Set(trace.spans_flat.filter((s: SpanNode) => s.span_type === "tool_call").map((s: SpanNode) => s.server_name))).map((srv) => (
                          <span key={srv as string} className="px-2 py-0.5 rounded text-[10px]" style={{ background: "hsl(var(--muted))", color: "hsl(var(--muted-foreground))", border: "1px solid hsl(var(--border))", fontFamily: "var(--font-geist-mono)" }}>{srv as string}</span>
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
                          <code className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: "hsl(var(--primary) / 0.08)", color: "hsl(var(--primary))", fontFamily: "var(--font-geist-mono)" }}>{session.model_id}</code>
                        </div>
                      )}
                      {session.est_cost_usd != null && <MetricTile label="Cost" value={`$${session.est_cost_usd < 0.01 ? session.est_cost_usd.toFixed(4) : session.est_cost_usd.toFixed(2)}`} />}
                    </div>
                  </div>
                )}

                <p className="text-[10px] text-muted-foreground text-center pt-2">Click any node or edge for details</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Trace tab — span tree ──────────────────────────────── */}
      {activeTab === "trace" && (
        <>
          {/* Token + cost summary bar */}
          {trace && (() => {
            const allSpans = trace.spans_flat;
            const totalIn = allSpans.reduce((s, sp) => s + (sp.input_tokens ?? 0), 0);
            const totalOut = allSpans.reduce((s, sp) => s + (sp.output_tokens ?? 0), 0);
            const models = [...new Set(allSpans.map((sp) => sp.model_id).filter(Boolean))];
            const hasTokens = totalIn > 0 || totalOut > 0;
            if (!hasTokens) return null;
            return (
              <div className="flex items-center gap-4 px-4 py-2 rounded-xl border mb-2" style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}>
                <div className="flex items-center gap-1.5 text-[11px]" style={{ fontFamily: "var(--font-geist-mono)" }}>
                  <span className="text-muted-foreground">Tokens:</span>
                  <span className="font-semibold" style={{ color: "hsl(var(--foreground))" }}>↑{totalIn.toLocaleString()}</span>
                  <span className="text-muted-foreground">/</span>
                  <span className="font-semibold" style={{ color: "hsl(var(--foreground))" }}>↓{totalOut.toLocaleString()}</span>
                </div>
                <div className="w-px h-3" style={{ background: "hsl(var(--border))" }} />
                <div className="flex items-center gap-1.5 text-[11px]">
                  <span className="text-muted-foreground">Total:</span>
                  <span className="font-semibold" style={{ color: "hsl(var(--foreground))", fontFamily: "var(--font-geist-mono)" }}>{(totalIn + totalOut).toLocaleString()}</span>
                </div>
                {models.length > 0 && (
                  <>
                    <div className="w-px h-3" style={{ background: "hsl(var(--border))" }} />
                    <div className="flex items-center gap-1.5 text-[11px]">
                      <span className="text-muted-foreground">Model:</span>
                      <span className="font-medium" style={{ color: "hsl(var(--foreground))" }}>{models.join(", ")}</span>
                    </div>
                  </>
                )}
                <div className="w-px h-3" style={{ background: "hsl(var(--border))" }} />
                <div className="flex items-center gap-1.5 text-[11px]">
                  <span className="text-muted-foreground">LLM calls:</span>
                  <span className="font-semibold" style={{ color: "hsl(var(--foreground))", fontFamily: "var(--font-geist-mono)" }}>{allSpans.filter((sp) => sp.input_tokens != null).length}</span>
                </div>
              </div>
            );
          })()}
          <div
            className="flex-1 rounded-xl border overflow-hidden flex flex-col min-h-0"
            style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
          >
            <div className="flex-1 overflow-y-auto overflow-x-auto">
              {loading ? (
                <div className="p-10 flex items-center justify-center">
                  <div className="w-6 h-6 rounded-full border-2 border-primary border-t-transparent spin" />
                </div>
              ) : error ? (
                <div className="p-8 text-center text-sm" style={{ color: "hsl(var(--danger))" }}>
                  <AlertCircle size={20} className="mx-auto mb-2" />
                  {error}
                </div>
              ) : !trace || trace.root_spans.length === 0 ? (
                <p className="p-8 text-center text-sm text-muted-foreground">No spans found</p>
              ) : (
                <table className="w-full">
                  <thead>
                    <tr
                      className="sticky top-0 z-10"
                      style={{ borderBottom: "1px solid hsl(var(--border))", background: "hsl(var(--card-raised))" }}
                    >
                      {["Span", "Agent", "Status", "Latency", "Tokens", "Time", "Error"].map((h) => (
                        <th
                          key={h}
                          className="px-4 py-2.5 text-left text-[11px] font-semibold text-muted-foreground uppercase tracking-wide"
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {trace.root_spans.map((span) => (
                      <SpanRow key={span.span_id} span={span} depth={0} onViewPayload={(title, tabs) => setPayloadSlideout({ title, tabs })} />
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>

          {/* Compare picker */}
          {comparePicking && !compareWith && sessions && (
            <ComparePicker
              sessions={sessions}
              selectedId={sessionId}
              onPick={(id) => { setCompareWith(id); setComparePicking(false); }}
              onCancel={() => setComparePicking(false)}
            />
          )}
          {compareWith && (
            <CompareDetail
              idA={sessionId}
              idB={compareWith}
              sessionA={session}
              sessionB={compareSession}
              onBack={() => { setCompareWith(null); setComparePicking(false); }}
              projectId={projectId}
            />
          )}
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
