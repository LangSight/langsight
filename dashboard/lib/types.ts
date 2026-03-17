export type ServerStatus = "up" | "degraded" | "down" | "stale" | "unknown";
export type ToolCallStatus = "success" | "error" | "timeout";
export type Severity = "critical" | "high" | "medium" | "low" | "info";
export type SpanType = "tool_call" | "agent" | "handoff";

export interface HealthResult {
  server_name: string;
  status: ServerStatus;
  latency_ms: number | null;
  tools_count: number;
  schema_hash: string | null;
  error: string | null;
  checked_at: string;
}

export interface SecurityFinding {
  severity: Severity;
  category: string;
  title: string;
  description: string;
  remediation: string;
  tool_name: string | null;
  cve_id: string | null;
}

export interface SecurityScanResult {
  server_name: string;
  scanned_at: string;
  error: string | null;
  findings_count: number;
  critical_count: number;
  high_count: number;
  highest_severity: Severity | null;
  findings: SecurityFinding[];
}

export interface AgentSession {
  session_id: string;
  agent_name: string | null;
  first_call_at: string;
  last_call_at: string;
  tool_calls: number;
  failed_calls: number;
  duration_ms: number;
  servers_used: string[];
}

export interface SpanNode {
  span_id: string;
  parent_span_id: string | null;
  span_type: SpanType;
  server_name: string;
  tool_name: string;
  agent_name: string | null;
  started_at: string;
  ended_at: string;
  latency_ms: number;
  status: ToolCallStatus;
  error: string | null;
  trace_id: string | null;
  children: SpanNode[];
}

export interface SessionTrace {
  session_id: string;
  spans_flat: SpanNode[];
  root_spans: SpanNode[];
  total_spans: number;
  tool_calls: number;
  failed_calls: number;
  duration_ms: number | null;
}

export interface ApiStatus {
  status: string;
  version: string;
  servers_configured: number;
}
