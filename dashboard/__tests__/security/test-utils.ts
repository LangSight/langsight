/**
 * Shared helpers for security tests.
 *
 * These utilities produce adversarial inputs — hostile strings, malformed dates,
 * and oversized graph payloads — that are used across all security test files.
 * No external network or DB calls; all fixtures are in-memory.
 */

import type { SessionTrace, SpanNode } from "@/lib/types";

// ─── XSS payloads ────────────────────────────────────────────────────────────

/**
 * A representative list of XSS vectors.  Tests check that none of these appear
 * verbatim in the rendered DOM as executable markup.
 */
export const XSS_PAYLOADS = [
  '<script>window.__xss=1</script>',
  '<img src=x onerror="window.__xss=1">',
  '"><script>window.__xss=1</script>',
  "javascript:window.__xss=1",
  '<svg onload="window.__xss=1">',
  '&lt;script&gt;window.__xss=1&lt;/script&gt;',
  // Null-byte injection
  "\0<script>window.__xss=1</script>",
  // Unicode escape tricks
  "\u003cscript\u003ewindow.__xss=1\u003c/script\u003e",
] as const;

// ─── Session ID attack patterns ───────────────────────────────────────────────

/**
 * Hostile session IDs that should either be URL-encoded before reaching the
 * API layer, or rejected by client-side validation before a fetch is issued.
 */
export const HOSTILE_SESSION_IDS = [
  // SQL injection
  "' OR '1'='1",
  "1; DROP TABLE sessions;--",
  "1' UNION SELECT null,null,null--",
  // Path traversal
  "../../../etc/passwd",
  "..%2F..%2F..%2Fetc%2Fpasswd",
  "..\\..\\..\\windows\\system32",
  // Null byte injection
  "valid-id\0../admin",
  // Oversized ID (> 1 KB)
  "A".repeat(1025),
  // Empty string
  "",
  // Whitespace-only
  "   ",
] as const;

// ─── Malformed date inputs ────────────────────────────────────────────────────

/** Values that should not produce a valid ISO string or should be clamped. */
export const MALFORMED_DATES = [
  // Non-date strings
  "",
  "not-a-date",
  "0000-00-00",
  // Far future (year 9999)
  "9999-12-31",
  // Before Unix epoch
  "1600-01-01",
  // NaN-producing strings
  "NaN",
  "Infinity",
  "-Infinity",
  // SQL injection in date field
  "2024-01-01'; DROP TABLE sessions;--",
  // HTML injection in date field
  "<script>alert(1)</script>",
  // Negative timestamp representation
  "-1",
  // Extremely large numeric string
  "99999999999999",
] as const;

// ─── Oversized graph payloads (DoS fixtures) ──────────────────────────────────

/** Build a trace with `spanCount` tool-call spans — used to probe DoS resistance. */
export function makeOversizedTrace(spanCount: number): SessionTrace {
  const spans: SpanNode[] = Array.from({ length: spanCount }, (_, i) => ({
    span_id: `span-${i}`,
    parent_span_id: null,
    span_type: "tool_call" as const,
    server_name: `server-${i % 10}`,
    tool_name: `tool-${i % 5}`,
    agent_name: `agent-${i % 3}`,
    started_at: "2026-03-22T10:00:00Z",
    ended_at: "2026-03-22T10:00:00.100Z",
    latency_ms: 100,
    status: "success" as const,
    error: null,
    trace_id: "trace-1",
    input_json: null,
    output_json: null,
    llm_input: null,
    llm_output: null,
    input_tokens: null,
    output_tokens: null,
    model_id: null,
    target_agent_name: null,
    lineage_provenance: "explicit" as const,
    lineage_status: "complete" as const,
    finish_reason: null,
    schema_version: "1.0",
    children: [],
  }));

  return {
    session_id: "stress-test",
    spans_flat: spans,
    root_spans: [],
    total_spans: spanCount,
    tool_calls: spanCount,
    failed_calls: 0,
    duration_ms: 1000,
  };
}

/** Build a trace where every field that surfaces in UI contains an XSS payload. */
export function makeXssTrace(payload: string): SessionTrace {
  return {
    session_id: payload,
    spans_flat: [
      {
        span_id: payload,
        parent_span_id: null,
        span_type: "tool_call" as const,
        server_name: payload,
        tool_name: payload,
        agent_name: payload,
        started_at: "2026-03-22T10:00:00Z",
        ended_at: "2026-03-22T10:00:01Z",
        latency_ms: 100,
        status: "success" as const,
        error: payload,
        trace_id: null,
        input_json: JSON.stringify({ cmd: payload }),
        output_json: JSON.stringify({ result: payload }),
        llm_input: null,
        llm_output: null,
        input_tokens: null,
        output_tokens: null,
        model_id: payload,
        target_agent_name: null,
        lineage_provenance: "explicit" as const,
        lineage_status: "complete" as const,
        finish_reason: null,
        cache_read_tokens: null,
        cache_creation_tokens: null,
        schema_version: "1.0",
        children: [],
      },
    ],
    root_spans: [],
    total_spans: 1,
    tool_calls: 1,
    failed_calls: 0,
    duration_ms: 1000,
  };
}

/** Build a trace with a single span whose fields contain NaN / Infinity / negative numbers. */
export function makeNumericEdgeCaseTrace(): SessionTrace {
  return {
    session_id: "numeric-edge",
    spans_flat: [
      {
        span_id: "span-1",
        parent_span_id: null,
        span_type: "tool_call" as const,
        server_name: "test-server",
        tool_name: "test-tool",
        agent_name: "test-agent",
        started_at: "2026-03-22T10:00:00Z",
        ended_at: "2026-03-22T10:00:01Z",
        latency_ms: Number.NaN,
        status: "success" as const,
        error: null,
        trace_id: null,
        input_json: null,
        output_json: null,
        llm_input: null,
        llm_output: null,
        input_tokens: Number.MAX_SAFE_INTEGER,
        output_tokens: -1,
        model_id: null,
        target_agent_name: null,
        lineage_provenance: "explicit" as const,
        lineage_status: "complete" as const,
        finish_reason: null,
        cache_read_tokens: null,
        cache_creation_tokens: null,
        schema_version: "1.0",
        children: [],
      },
    ],
    root_spans: [],
    total_spans: 1,
    tool_calls: 1,
    failed_calls: 0,
    duration_ms: null,
  };
}
