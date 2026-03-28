export type ServerStatus = "up" | "degraded" | "down" | "stale" | "unknown";
export type ToolCallStatus = "success" | "error" | "timeout" | "prevented";
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

export type HealthTag =
  | "success"
  | "success_with_fallback"
  | "loop_detected"
  | "budget_exceeded"
  | "tool_failure"
  | "circuit_breaker_open"
  | "timeout"
  | "schema_drift";

export interface AgentSession {
  session_id: string;
  agent_name: string | null;
  first_call_at: string;
  last_call_at: string;
  tool_calls: number;
  failed_calls: number;
  duration_ms: number;
  servers_used: string[];
  agents_used?: string[];
  health_tag: HealthTag | null;  // v0.3
  total_input_tokens: number | null;
  total_output_tokens: number | null;
  model_id: string | null;
  est_cost_usd: number | null;
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
  input_tokens: number | null;  // P7 — LLM input token count
  output_tokens: number | null; // P7 — LLM output token count
  model_id: string | null;      // P7 — model used
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

// ─── Agent Metadata (Catalog) ────────────────────────────────────────────────

export interface AgentMetadata {
  id: string;
  agent_name: string;
  description: string;
  owner: string;
  tags: string[];
  status: "active" | "deprecated" | "experimental";
  runbook_url: string;
  project_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface ToolReliability {
  server_name: string;
  tool_name: string;
  window_hours: number;
  total_calls: number;
  success_calls: number;
  error_calls: number;
  timeout_calls: number;
  success_rate_pct: number;
  error_rate_pct: number;
  avg_latency_ms: number;
  max_latency_ms: number;
  p50_latency_ms: number;
  p95_latency_ms: number;
  p99_latency_ms: number;
  is_degraded: boolean;
  error_breakdown: { timeout: number; connection: number; params: number; server: number };
}

export interface ServerMetadata {
  id: string;
  server_name: string;
  description: string;
  owner: string;
  tags: string[];
  transport: string;
  runbook_url: string;
  project_id: string | null;
  created_at: string;
  updated_at: string;
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

// ─── Session lineage (per-path attribution) ──────────────────────────────────

/** Metrics scoped to a specific agent → server path in a session. */
export interface PathMetrics {
  callCount: number;
  errorCount: number;
  avgLatencyMs: number;
  maxLatencyMs: number;
  tools: string[];
  inputTokens: number;
  outputTokens: number;
  models: string[];
  repeatCallName?: string;
  repeatCallCount?: number;
}

/** Which agents call a given server, with per-path metrics. */
export interface ServerCallerInfo {
  agentId: string;
  agentLabel: string;
  metrics: PathMetrics;
}

// ─── v0.3 Prevention Config ───────────────────────────────────────────────────

export interface PreventionConfig {
  agent_name: string;        // "*" = project-level default
  loop_enabled: boolean;
  loop_threshold: number;
  loop_action: "terminate" | "warn";
  max_steps: number | null;
  max_cost_usd: number | null;
  max_wall_time_s: number | null;
  budget_soft_alert: number;
  cb_enabled: boolean;
  cb_failure_threshold: number;
  cb_cooldown_seconds: number;
  cb_half_open_max_calls: number;
  is_default: boolean;
  updated_at: string;
}

export interface PreventionConfigUpdate {
  loop_enabled: boolean;
  loop_threshold: number;
  loop_action: "terminate" | "warn";
  max_steps: number | null;
  max_cost_usd: number | null;
  max_wall_time_s: number | null;
  budget_soft_alert: number;
  cb_enabled: boolean;
  cb_failure_threshold: number;
  cb_cooldown_seconds: number;
  cb_half_open_max_calls: number;
}

// ─── Server Logs ──────────────────────────────────────────────────────────────

export interface ServerLogEntry {
  started_at: string;
  agent_name: string;
  tool_name: string;
  status: "success" | "error" | "timeout" | "prevented";
  latency_ms: number | null;
  error: string | null;
  session_id: string;
  span_id: string;
}

// ─── Blast Radius ─────────────────────────────────────────────────────────────

export interface BlastRadiusAgent {
  agent_name: string;
  call_count: number;
  session_count: number;
  error_count: number;
  error_rate_pct: number;
  avg_latency_ms: number | null;
  last_called_at: string | null;
}

export interface BlastRadius {
  server_name: string;
  server_status: string;
  hours: number;
  severity: "critical" | "high" | "medium" | "low";
  total_sessions_at_risk: number;
  total_agents_affected: number;
  total_calls: number;
  affected_agents: BlastRadiusAgent[];
}

// ─── Schema Drift ─────────────────────────────────────────────────────────────

export interface SchemaDriftEvent {
  server_name: string;
  tool_name: string;
  drift_type: "breaking" | "compatible" | "warning";
  change_kind: string;
  param_name: string | null;
  old_value: string | null;
  new_value: string | null;
  previous_hash: string;
  current_hash: string;
  has_breaking: boolean;
  detected_at: string;
}

export interface DriftImpact {
  agent_name: string;
  session_id: string;
  call_count: number;
  error_count: number;
  avg_latency_ms: number;
  last_called_at: string;
}
