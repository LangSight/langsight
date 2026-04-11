"use client";

/**
 * SpanTree — the collapsible span table shown in the Trace tab of session detail.
 * Includes SpanRow (recursive) and PayloadPanel.
 */

import { useState } from "react";
import { ChevronRight, ChevronDown, ExternalLink, AlertCircle } from "lucide-react";
import { Timestamp } from "@/components/timestamp";
import { cn, SPAN_TYPE_ICON } from "@/lib/utils";
import { MarkdownContent } from "@/components/markdown-content";
import type { SessionTrace, SpanNode } from "@/lib/types";

/* ── PayloadPanel ────────────────────────────────────────────── */
interface PayloadPanelProps {
  label: string;
  json: string | null;
  onViewFull?: () => void;
  /** When true, render content as markdown instead of raw/JSON */
  markdown?: boolean;
}

export function PayloadPanel({ label, json, onViewFull, markdown }: PayloadPanelProps) {
  if (!json) return null;
  let formatted = json;
  try {
    formatted = JSON.stringify(JSON.parse(json), null, 2);
  } catch {
    /* keep raw */
  }
  return (
    <div className="mt-2">
      <div className="flex items-center justify-between mb-1.5">
        <p className="text-[11px] font-semibold text-muted-foreground uppercase tracking-widest">
          {label}
        </p>
        {onViewFull && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onViewFull();
            }}
            className="text-[10px] text-primary hover:underline flex items-center gap-1 font-medium"
          >
            <ExternalLink size={10} />
            View full
          </button>
        )}
      </div>
      {markdown ? (
        <MarkdownContent content={json} className="max-h-48" fontSize="text-[11px]" />
      ) : (
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
      )}
    </div>
  );
}

/* ── SpanRow ─────────────────────────────────────────────────── */
interface SpanRowProps {
  span: SpanNode;
  depth?: number;
  onViewPayload?: (title: string, tabs: { label: string; json: string | null }[]) => void;
}

export function SpanRow({ span, depth = 0, onViewPayload }: SpanRowProps) {
  const [open, setOpen] = useState(true);
  const [detailOpen, setDetailOpen] = useState(false);
  const icon = SPAN_TYPE_ICON[span.span_type] ?? "●";
  const hasChildren = span.children && span.children.length > 0;
  const isLlmSpan = span.span_type === "agent" && (span.llm_input || span.llm_output);
  const hasPayload = span.input_json || span.output_json || span.llm_input || span.llm_output || span.error;
  const isError = span.status === "error";
  const isPrevented = span.status === "prevented";

  const spanColor =
    span.span_type === "handoff"
      ? "text-yellow-500"
      : span.span_type === "agent"
      ? "text-primary"
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
        style={{
          borderBottom: "1px solid hsl(var(--border) / 0.4)",
          borderLeft: isError
            ? "3px solid #ef4444"
            : isPrevented
            ? "3px solid #eab308"
            : "3px solid transparent",
        }}
        onClick={() => hasPayload && setDetailOpen((o) => !o)}
      >
        <td className="py-2.5 pr-3">
          <div className="flex items-center" style={{ paddingLeft: `${depth * 28 + 8}px` }}>
            {depth > 0 && (
              <span
                className="text-[12px] mr-1.5 flex-shrink-0"
                style={{ color: "hsl(var(--border))", fontFamily: "var(--font-geist-mono)" }}
              >
                └─
              </span>
            )}
            <button
              onClick={(e) => {
                e.stopPropagation();
                hasChildren && setOpen((o) => !o);
              }}
              aria-expanded={hasChildren ? open : undefined}
              className={cn(
                "flex items-center gap-1.5 min-w-0",
                hasChildren ? "cursor-pointer" : "cursor-default"
              )}
            >
              {hasChildren ? (
                open ? (
                  <ChevronDown size={12} className="text-muted-foreground flex-shrink-0" />
                ) : (
                  <ChevronRight size={12} className="text-muted-foreground flex-shrink-0" />
                )
              ) : depth === 0 ? (
                <span className="w-3.5 flex-shrink-0" />
              ) : null}
              <span className="text-[12px] mr-1">{icon}</span>
              <span
                className={cn("text-[12px] font-semibold truncate", spanColor)}
                style={{ fontFamily: "var(--font-geist-mono)" }}
              >
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
        <td className="py-2.5 pr-3 text-[12px] text-muted-foreground">
          {span.agent_name || "—"}
        </td>
        <td className="py-2.5 pr-3">
          <span
            className="text-[10px] px-1.5 py-0.5 rounded-full font-medium"
            style={{ background: statusBadge.bg, color: statusBadge.color }}
          >
            {statusBadge.text}
          </span>
        </td>
        <td
          className="py-2.5 pr-3 text-[12px] text-right text-muted-foreground"
          style={{ fontFamily: "var(--font-geist-mono)" }}
        >
          {span.latency_ms ? `${span.latency_ms.toFixed(0)}ms` : "—"}
        </td>
        <td
          className="py-2.5 pr-3 text-[11px] text-muted-foreground"
          style={{ fontFamily: "var(--font-geist-mono)" }}
        >
          {span.input_tokens != null || span.output_tokens != null ? (
            <span className="flex items-center gap-1.5">
              {span.input_tokens != null && (
                <span title="Input tokens">↑{span.input_tokens.toLocaleString()}</span>
              )}
              {span.output_tokens != null && (
                <span title="Output tokens">↓{span.output_tokens.toLocaleString()}</span>
              )}
            </span>
          ) : "—"}
        </td>
        <td className="py-2.5 pr-3 text-[11px] text-muted-foreground">
          {span.started_at ? <Timestamp iso={span.started_at} compact /> : "—"}
        </td>
        <td className="py-2.5 text-[11px] text-red-500 truncate max-w-xs">
          {span.error?.slice(0, 80) ?? ""}
        </td>
      </tr>

      {detailOpen && hasPayload && (
        <tr style={{ background: "hsl(var(--muted) / 0.4)" }}>
          <td
            colSpan={7}
            className="px-4 pb-4 pt-2"
            style={{ paddingLeft: `${depth * 20 + 32}px` }}
          >
            {isLlmSpan ? (
              <>
                <PayloadPanel
                  label="Prompt"
                  json={span.llm_input ?? null}
                  markdown
                  onViewFull={
                    span.llm_input
                      ? () => onViewPayload?.(`Prompt — ${span.tool_name}`, [{ label: "Text", json: span.llm_input ?? null }])
                      : undefined
                  }
                />
                <PayloadPanel
                  label="Completion"
                  json={span.llm_output ?? null}
                  markdown
                  onViewFull={
                    span.llm_output
                      ? () => onViewPayload?.(`Completion — ${span.tool_name}`, [{ label: "Text", json: span.llm_output ?? null }])
                      : undefined
                  }
                />
              </>
            ) : (
              <>
                <PayloadPanel
                  label="Input"
                  json={span.input_json ?? null}
                  onViewFull={
                    span.input_json
                      ? () => onViewPayload?.(`Input — ${span.tool_name}`, [{ label: "JSON", json: span.input_json ?? null }])
                      : undefined
                  }
                />
                <PayloadPanel
                  label="Output"
                  json={span.output_json ?? null}
                  onViewFull={
                    span.output_json
                      ? () => onViewPayload?.(`Output — ${span.tool_name}`, [{ label: "JSON", json: span.output_json ?? null }])
                      : undefined
                  }
                />
              </>
            )}
            {span.error && !span.output_json && !span.llm_output && (
              <div className="mt-2">
                <p
                  className="text-[11px] font-semibold uppercase tracking-widest mb-1.5"
                  style={{ color: "hsl(var(--danger))" }}
                >
                  Error
                </p>
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

      {open &&
        span.children?.map((child) => (
          <SpanRow key={child.span_id} span={child} depth={depth + 1} onViewPayload={onViewPayload} />
        ))}
    </>
  );
}

/* ── SpanTree container ──────────────────────────────────────── */
interface SpanTreeProps {
  trace: SessionTrace | null;
  loading: boolean;
  error: string | null;
  onViewPayload: (title: string, tabs: { label: string; json: string | null }[]) => void;
}

export function SpanTree({ trace, loading, error, onViewPayload }: SpanTreeProps) {
  if (loading) {
    return (
      <div className="p-10 flex items-center justify-center">
        <div className="w-6 h-6 rounded-full border-2 border-primary border-t-transparent spin" />
      </div>
    );
  }

  if (error) {
    const isClickHouse = error.toLowerCase().includes("clickhouse");
    return (
      <div className="p-8 text-center text-sm" style={{ color: isClickHouse ? "hsl(var(--muted-foreground))" : "hsl(var(--danger))" }}>
        <AlertCircle size={20} className="mx-auto mb-2" style={{ color: isClickHouse ? "hsl(var(--muted-foreground))" : undefined }} />
        {isClickHouse ? (
          <>
            <p className="font-semibold mb-1">Session traces require ClickHouse</p>
            <p className="text-xs">Start the full stack with <code className="font-mono">docker compose up</code> to enable trace replay.</p>
          </>
        ) : error}
      </div>
    );
  }

  if (!trace) {
    return (
      <div className="p-10 flex items-center justify-center">
        <div className="w-6 h-6 rounded-full border-2 border-primary border-t-transparent spin" />
      </div>
    );
  }

  if (trace.root_spans.length === 0) {
    return (
      <p className="p-8 text-center text-sm text-muted-foreground">No spans found</p>
    );
  }

  return (
    <table className="w-full">
      <thead>
        <tr
          className="sticky top-0 z-10"
          style={{
            borderBottom: "1px solid hsl(var(--border))",
            background: "hsl(var(--card-raised))",
          }}
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
        {trace.root_spans
          .filter((span) => span.span_type !== "topology" && span.tool_name !== "session")
          .map((span) => (
            <SpanRow key={span.span_id} span={span} depth={0} onViewPayload={onViewPayload} />
          ))}
      </tbody>
    </table>
  );
}

/* ── Token summary bar ───────────────────────────────────────── */
export function TokenSummaryBar({ trace }: { trace: SessionTrace }) {
  const allSpans = trace.spans_flat;
  const totalIn = allSpans.reduce((s, sp) => s + (sp.input_tokens ?? 0), 0);
  const totalOut = allSpans.reduce((s, sp) => s + (sp.output_tokens ?? 0), 0);
  const models = [...new Set(allSpans.map((sp) => sp.model_id).filter(Boolean))];
  const hasTokens = totalIn > 0 || totalOut > 0;

  if (!hasTokens) return null;

  return (
    <div
      className="flex items-center gap-4 px-4 py-2 rounded-xl border mb-2"
      style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
    >
      <div
        className="flex items-center gap-1.5 text-[11px]"
        style={{ fontFamily: "var(--font-geist-mono)" }}
      >
        <span className="text-muted-foreground">Tokens:</span>
        <span className="font-semibold" style={{ color: "hsl(var(--foreground))" }}>
          ↑{totalIn.toLocaleString()}
        </span>
        <span className="text-muted-foreground">/</span>
        <span className="font-semibold" style={{ color: "hsl(var(--foreground))" }}>
          ↓{totalOut.toLocaleString()}
        </span>
      </div>
      <div className="w-px h-3" style={{ background: "hsl(var(--border))" }} />
      <div className="flex items-center gap-1.5 text-[11px]">
        <span className="text-muted-foreground">Total:</span>
        <span
          className="font-semibold"
          style={{ color: "hsl(var(--foreground))", fontFamily: "var(--font-geist-mono)" }}
        >
          {(totalIn + totalOut).toLocaleString()}
        </span>
      </div>
      {models.length > 0 && (
        <>
          <div className="w-px h-3" style={{ background: "hsl(var(--border))" }} />
          <div className="flex items-center gap-1.5 text-[11px]">
            <span className="text-muted-foreground">Model:</span>
            <span className="font-medium" style={{ color: "hsl(var(--foreground))" }}>
              {models.join(", ")}
            </span>
          </div>
        </>
      )}
      <div className="w-px h-3" style={{ background: "hsl(var(--border))" }} />
      <div className="flex items-center gap-1.5 text-[11px]">
        <span className="text-muted-foreground">LLM calls:</span>
        <span
          className="font-semibold"
          style={{ color: "hsl(var(--foreground))", fontFamily: "var(--font-geist-mono)" }}
        >
          {allSpans.filter((sp) => sp.input_tokens != null).length}
        </span>
      </div>
    </div>
  );
}
