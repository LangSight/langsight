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
  input_json: string | null;   // P5.1 — tool call arguments (null when redacted)
  output_json: string | null;  // P5.1 — tool return value (null when redacted or error)
  llm_input: string | null;    // P5.3 — LLM prompt/messages (agent spans only)
  llm_output: string | null;   // P5.3 — LLM completion text (agent spans only)
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
  auth_enabled?: boolean;
  storage_mode?: string;
}

export interface ApiKeyResponse {
  id: string;
  name: string;
  key_prefix: string;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
}

export interface ApiKeyCreatedResponse {
  id: string;
  name: string;
  key: string;
  key_prefix: string;
  created_at: string;
}

export interface CostBreakdownEntry {
  server_name: string;
  tool_name: string;
  total_calls: number;
  cost_per_call_usd: number;
  total_cost_usd: number;
  cost_type: "call_based" | "token_based";
  model_id: string | null;
  total_input_tokens: number;
  total_output_tokens: number;
}

export interface AgentCostBreakdownEntry {
  agent_name: string;
  total_calls: number;
  total_cost_usd: number;
}

export interface SessionCostBreakdownEntry {
  session_id: string;
  agent_name: string | null;
  total_calls: number;
  total_cost_usd: number;
}

export interface AnomalyResult {
  server_name: string;
  tool_name: string;
  metric: "error_rate" | "avg_latency_ms";
  current_value: number;
  baseline_mean: number;
  baseline_stddev: number;
  z_score: number;
  severity: "warning" | "critical";
  sample_hours: number;
}

export interface ProjectResponse {
  id: string;
  name: string;
  slug: string;
  created_by: string;
  created_at: string;
  member_count: number;
  your_role: string | null;
}

export interface ProjectMember {
  user_id: string;
  role: string;
  added_by: string;
  added_at: string;
}

export interface DashboardUser {
  id: string;
  email: string;
  role: "admin" | "viewer";
  active: boolean;
  created_at: string;
  last_login_at: string | null;
}

export interface InviteResponse {
  token: string;
  email: string;
  role: string;
  expires_at: string;
  invite_url: string;
}

export interface ReplayResponse {
  original_session_id: string;
  replay_session_id: string;
  total_spans: number;
  replayed: number;
  skipped: number;
  failed: number;
  duration_ms: number;
}

export interface DiffEntry {
  tool_key: string;
  status: "matched" | "diverged" | "only_a" | "only_b";
  span_a: Record<string, unknown> | null;
  span_b: Record<string, unknown> | null;
  latency_delta_pct: number | null;
  status_changed: boolean;
}

export interface SessionComparison {
  session_a: string;
  session_b: string;
  spans_a: Record<string, unknown>[];
  spans_b: Record<string, unknown>[];
  diff: DiffEntry[];
  summary: { matched: number; diverged: number; only_a: number; only_b: number };
}

export interface SLOStatus {
  slo_id: string;
  agent_name: string;
  metric: "success_rate" | "latency_p99";
  target: number;
  current_value: number | null;
  window_hours: number;
  status: "ok" | "breached" | "no_data";
  evaluated_at: string;
}

export interface ModelPricingEntry {
  id: string;
  provider: string;
  model_id: string;
  display_name: string;
  input_per_1m_usd: number;
  output_per_1m_usd: number;
  cache_read_per_1m_usd: number;
  effective_from: string;
  effective_to: string | null;
  notes: string | null;
  is_custom: boolean;
  is_active: boolean;
}

// ─── Lineage (agent action DAG) ──────────────────────────────────────────────

export interface LineageNode {
  id: string;
  type: "agent" | "server";
  label: string;
  metrics: Record<string, number>;
}

export interface LineageEdge {
  source: string;
  target: string;
  type: "calls" | "handoff";
  metrics: Record<string, number>;
}

export interface LineageGraph {
  window_hours: number;
  nodes: LineageNode[];
  edges: LineageEdge[];
}

// ─── Costs ───────────────────────────────────────────────────────────────────

export interface CostsBreakdownResponse {
  storage_mode: string;
  supports_costs: boolean;
  hours: number;
  total_calls: number;
  total_cost_usd: number;
  llm_cost_usd: number;
  tool_cost_usd: number;
  total_input_tokens: number;
  total_output_tokens: number;
  by_tool: CostBreakdownEntry[];
  by_agent: AgentCostBreakdownEntry[];
  by_session: SessionCostBreakdownEntry[];
}
