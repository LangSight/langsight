"use client";

export const dynamic = "force-dynamic";

import { useState, useEffect } from "react";
import useSWR from "swr";
import { fetcher, getSessionTrace } from "@/lib/api";
import {
  Card, PageHeader, Table, Th, Td, Loading, ErrorState, Empty, Badge,
} from "@/components/ui";
import { timeAgo, formatDuration, CALL_STATUS_COLOR, SPAN_TYPE_ICON } from "@/lib/utils";
import type { AgentSession, SessionTrace, SpanNode } from "@/lib/types";

/* ── Span tree ──────────────────────────────────────────────────── */
function SpanRow({ span, depth = 0 }: { span: SpanNode; depth?: number }) {
  const [open, setOpen] = useState(true);
  const icon = SPAN_TYPE_ICON[span.span_type] ?? "●";
  const statusColor = CALL_STATUS_COLOR[span.status];
  const hasChildren = span.children && span.children.length > 0;

  return (
    <>
      <tr className="hover:bg-white/5 transition-colors">
        <Td>
          <div className="flex items-center gap-1" style={{ paddingLeft: `${depth * 20}px` }}>
            {hasChildren && (
              <button onClick={() => setOpen(o => !o)} className="text-xs w-4 shrink-0" style={{ color: "var(--muted)" }}>
                {open ? "▾" : "▸"}
              </button>
            )}
            {!hasChildren && <span className="w-4 shrink-0" />}
            <span className="text-xs mr-1">{icon}</span>
            <span className={`text-xs font-mono ${span.span_type === "handoff" ? "text-yellow-400" : span.span_type === "agent" ? "text-indigo-400" : "text-white"}`}>
              {span.server_name}/{span.tool_name}
            </span>
          </div>
        </Td>
        <Td><span className="text-xs" style={{ color: "var(--muted)" }}>{span.agent_name || "—"}</span></Td>
        <Td right>
          <span className={`text-xs font-mono ${statusColor}`}>
            {span.status === "success" ? "✓" : span.status === "error" ? "✗" : "⏱"}
          </span>
        </Td>
        <Td right>
          <span className="text-xs font-mono" style={{ color: "var(--muted)" }}>
            {span.latency_ms ? `${span.latency_ms.toFixed(0)}ms` : "—"}
          </span>
        </Td>
        <Td>
          <span className="text-xs text-red-400">{span.error ? span.error.slice(0, 40) : ""}</span>
        </Td>
      </tr>
      {open && span.children?.map(child => (
        <SpanRow key={child.span_id} span={child} depth={depth + 1} />
      ))}
    </>
  );
}

/* ── Trace view ─────────────────────────────────────────────────── */
function TraceView({ sessionId, onClose }: { sessionId: string; onClose: () => void }) {
  const [trace, setTrace] = useState<SessionTrace | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getSessionTrace(sessionId)
      .then(t => { setTrace(t); setLoading(false); })
      .catch(e => { setError(e.message); setLoading(false); });
  }, [sessionId]);

  return (
    <Card className="mt-4">
      <div className="flex items-start justify-between mb-4">
        <div>
          <h3 className="font-semibold text-white font-mono text-sm">{sessionId}</h3>
          {trace && (
            <p className="text-xs mt-1" style={{ color: "var(--muted)" }}>
              {trace.total_spans} spans · {trace.tool_calls} tool calls · {trace.failed_calls} failed
              {trace.duration_ms ? ` · ${formatDuration(trace.duration_ms)}` : ""}
            </p>
          )}
        </div>
        <button onClick={onClose} className="text-xs" style={{ color: "var(--muted)" }}>Close ✕</button>
      </div>
      {loading && <Loading />}
      {error && <ErrorState message={error} />}
      {trace && trace.root_spans.length === 0 && <Empty message="No spans found" />}
      {trace && trace.root_spans.length > 0 && (
        <Table>
          <thead>
            <tr><Th>Span</Th><Th>Agent</Th><Th right>Status</Th><Th right>Latency</Th><Th>Error</Th></tr>
          </thead>
          <tbody>
            {trace.root_spans.map(span => (
              <SpanRow key={span.span_id} span={span} depth={0} />
            ))}
          </tbody>
        </Table>
      )}
    </Card>
  );
}

/* ── Sessions list ──────────────────────────────────────────────── */
export default function SessionsPage() {
  const [hours, setHours] = useState(24);
  const [selected, setSelected] = useState<string | null>(null);

  const { data: sessions, error, isLoading } =
    useSWR<AgentSession[]>(`/api/agents/sessions?hours=${hours}&limit=100`, fetcher, { refreshInterval: 30_000 });

  return (
    <div className="max-w-5xl mx-auto">
      <PageHeader
        title="Agent Sessions"
        sub="Full traces of everything your agents called"
        action={
          <select
            value={hours}
            onChange={e => setHours(Number(e.target.value))}
            className="text-sm rounded-lg px-3 py-2 border"
            style={{ background: "var(--surface)", borderColor: "var(--border)", color: "var(--muted)" }}
          >
            <option value={1}>Last 1h</option>
            <option value={6}>Last 6h</option>
            <option value={24}>Last 24h</option>
            <option value={168}>Last 7d</option>
          </select>
        }
      />

      <Card>
        {isLoading && <Loading />}
        {error && <ErrorState message="Could not load sessions. Is ClickHouse running?" />}
        {!isLoading && !error && sessions?.length === 0 && (
          <Empty
            message="No sessions yet"
            hint="Instrument your agents with the LangSight SDK to see session traces here."
          />
        )}
        {sessions && sessions.length > 0 && (
          <Table>
            <thead>
              <tr>
                <Th>Session ID</Th><Th>Agent</Th><Th right>Calls</Th>
                <Th right>Failed</Th><Th right>Duration</Th><Th>Servers</Th><Th>Started</Th>
              </tr>
            </thead>
            <tbody>
              {sessions.map(s => (
                <tr
                  key={s.session_id}
                  className={`cursor-pointer transition-colors ${selected === s.session_id ? "bg-indigo-500/10" : "hover:bg-white/5"}`}
                  onClick={() => setSelected(selected === s.session_id ? null : s.session_id)}
                >
                  <Td mono>{s.session_id.slice(0, 14)}…</Td>
                  <Td><span style={{ color: "var(--muted)" }}>{s.agent_name || "—"}</span></Td>
                  <Td right>{s.tool_calls}</Td>
                  <Td right>
                    {s.failed_calls > 0
                      ? <span className="text-red-400">{s.failed_calls}</span>
                      : <span style={{ color: "var(--muted)" }}>0</span>}
                  </Td>
                  <Td right><span style={{ color: "var(--muted)" }}>{formatDuration(s.duration_ms)}</span></Td>
                  <Td>
                    <div className="flex flex-wrap gap-1">
                      {(s.servers_used || []).slice(0, 3).map(srv => (
                        <Badge key={srv} className="text-xs bg-zinc-500/10 text-zinc-400 border-zinc-500/20">{srv}</Badge>
                      ))}
                      {(s.servers_used?.length ?? 0) > 3 && (
                        <span className="text-xs" style={{ color: "var(--muted)" }}>+{s.servers_used.length - 3}</span>
                      )}
                    </div>
                  </Td>
                  <Td><span style={{ color: "var(--muted)" }}>{timeAgo(s.first_call_at)}</span></Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>

      {selected && <TraceView sessionId={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}
