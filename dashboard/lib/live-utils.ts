/**
 * Live page utilities — span:new SSE event processing.
 *
 * Extracted from live/page.tsx so they can be unit-tested without
 * importing the full React page (which uses hooks and browser APIs).
 */

/* ── Parse ClickHouse naive timestamps as UTC ─────────────────── */
export function toUTCMs(iso: string): number {
  let s = iso.trim();
  if (s.length >= 19 && s[10] === " ") s = s.slice(0, 10) + "T" + s.slice(11);
  if (!s.endsWith("Z") && !/[+-]\d{2}:?\d{2}$/.test(s)) s += "Z";
  return new Date(s).getTime();
}

/* ── Constants ────────────────────────────────────────────────── */
export const RUNNING_MS = 30_000;        // < 30s since last span → running
export const EXPIRE_MS  = 10 * 60_000;  // > 10min               → remove

/* ── Types ───────────────────────────────────────────────────── */
export interface SpanEvent {
  project_id:  string | null;
  session_id:  string;
  agent_name:  string | null;
  server_name: string | null;
  tool_name:   string | null;
  status:      string;
  latency_ms:  number | null;
  started_at:  string | null;
}

export interface LiveRow {
  session_id:    string;
  agent_name:    string | null;
  span_count:    number;
  error_count:   number;
  first_seen_ms: number;
  last_seen_ms:  number;
  running_until: number;
  ever_grew:     boolean;
  stable_since:  number;
}

/* ── Merge a single span:new event into the rows map ─────────── */
export function mergeSpan(
  prev: Map<string, LiveRow>,
  span: SpanEvent,
): Map<string, LiveRow> {
  if (!span.session_id) return prev;

  const now    = Date.now();
  const next   = new Map(prev);
  const spanMs = span.started_at ? toUTCMs(span.started_at) : now;
  const isErr  = span.status !== "success";

  // Evict sessions idle for > EXPIRE_MS
  for (const [sid, row] of next) {
    if (now - row.last_seen_ms > EXPIRE_MS) next.delete(sid);
  }

  const existing     = next.get(span.session_id);
  const spanCount    = (existing?.span_count  ?? 0) + 1;
  const errorCount   = (existing?.error_count ?? 0) + (isErr ? 1 : 0);
  const firstSeenMs  = existing?.first_seen_ms ?? spanMs;

  next.set(span.session_id, {
    session_id:    span.session_id,
    agent_name:    span.agent_name ?? existing?.agent_name ?? null,
    span_count:    spanCount,
    error_count:   errorCount,
    first_seen_ms: firstSeenMs,
    last_seen_ms:  spanMs,
    running_until: now + RUNNING_MS,
    ever_grew:     true,
    stable_since:  now,
  });

  return next;
}
