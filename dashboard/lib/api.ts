import type {
  AgentSession,
  AnomalyResult,
  ApiKeyCreatedResponse,
  ApiKeyResponse,
  ApiStatus,
  CostsBreakdownResponse,
  DashboardUser,
  HealthResult,
  InviteResponse,
  LineageGraph,
  ModelPricingEntry,
  ProjectMember,
  ProjectResponse,
  SecurityScanResult,
  SessionTrace,
  SLOStatus,
} from "./types";

/**
 * All API calls go through /api/proxy/* which server-side injects
 * the authenticated user's session headers before forwarding to FastAPI.
 *
 * This means:
 *   - No API keys exposed to the browser
 *   - Every request is authenticated via NextAuth session
 *   - Unauthenticated requests get 401 before reaching FastAPI
 */
const BASE = "/api/proxy";

/** Default timeout for API requests (ms). */
const DEFAULT_TIMEOUT_MS = 15_000;

/** Create an AbortSignal that fires after `ms` milliseconds. */
function timeoutSignal(ms: number = DEFAULT_TIMEOUT_MS): AbortSignal {
  return AbortSignal.timeout(ms);
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`, { cache: "no-store", signal: timeoutSignal() });
  if (r.status === 401) throw new Error("401 Unauthorized");
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json() as Promise<T>;
}

async function del(path: string): Promise<void> {
  const r = await fetch(`${BASE}${path}`, { method: "DELETE", cache: "no-store", signal: timeoutSignal() });
  if (r.status === 401) throw new Error("401 Unauthorized");
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
}

async function post<T>(path: string, body?: object): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
    cache: "no-store",
    signal: timeoutSignal(),
  });
  if (r.status === 401) throw new Error("401 Unauthorized");
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json() as Promise<T>;
}

async function put<T>(path: string, body?: object): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
    cache: "no-store",
    signal: timeoutSignal(),
  });
  if (r.status === 401) throw new Error("401 Unauthorized");
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json() as Promise<T>;
}

async function patch<T>(path: string, body?: object): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
    cache: "no-store",
    signal: timeoutSignal(),
  });
  if (r.status === 401) throw new Error("401 Unauthorized");
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json() as Promise<T>;
}

// SWR fetcher — uses authenticated proxy route
export const fetcher = (url: string) => {
  // Rewrite /api/* → /api/proxy/* for SWR keys that use the old BASE
  const proxyUrl = url.startsWith("/api/proxy") ? url : url.replace(/^\/api\//, "/api/proxy/");
  return fetch(proxyUrl, { cache: "no-store", signal: timeoutSignal() }).then((r) => {
    if (r.status === 401) throw new Error("401 Unauthorized");
    if (!r.ok) throw new Error(`${r.status}`);
    return r.json();
  });
};

// ─── Status ───────────────────────────────────────────────────────────────────
export const getStatus = () => get<ApiStatus>("/status");

// ─── Health ───────────────────────────────────────────────────────────────────
export const getServerHealth = () => get<HealthResult[]>("/health/servers");
export const getServerHistory = (name: string, limit = 20) =>
  get<HealthResult[]>(`/health/servers/${encodeURIComponent(name)}/history?limit=${limit}`);
export const triggerHealthCheck = () => post<HealthResult[]>("/health/check");

// ─── Costs ────────────────────────────────────────────────────────────────────
export const getCostsBreakdown = (hours = 24, projectId?: string) =>
  get<CostsBreakdownResponse>(`/costs/breakdown?hours=${hours}${projectId ? `&project_id=${encodeURIComponent(projectId)}` : ""}`);

// ─── Model pricing ────────────────────────────────────────────────────────────
export const listModelPricing = () => get<ModelPricingEntry[]>("/costs/models");
export const createModelPricing = (body: Omit<ModelPricingEntry, "id" | "effective_from" | "effective_to" | "is_active" | "is_custom">) =>
  post<ModelPricingEntry>("/costs/models", body);
export const updateModelPricing = (id: string, body: Omit<ModelPricingEntry, "id" | "effective_from" | "effective_to" | "is_active" | "is_custom">) =>
  patch<ModelPricingEntry>(`/costs/models/${encodeURIComponent(id)}`, body);
export const deactivateModelPricing = (id: string) =>
  del(`/costs/models/${encodeURIComponent(id)}`);

// ─── Security ─────────────────────────────────────────────────────────────────
export const triggerSecurityScan = (projectId?: string | null) =>
  post<SecurityScanResult[]>(projectId ? `/security/scan?project_id=${encodeURIComponent(projectId)}` : "/security/scan");

// ─── API Keys ─────────────────────────────────────────────────────────────────
export const getApiKeys = () => get<ApiKeyResponse[]>("/auth/api-keys");
export const createApiKey = (name: string) =>
  post<ApiKeyCreatedResponse>("/auth/api-keys", { name });
export const revokeApiKey = (id: string) =>
  del(`/auth/api-keys/${encodeURIComponent(id)}`);

// ─── Sessions ─────────────────────────────────────────────────────────────────
export const getSessions = (hours = 24, limit = 50) =>
  get<AgentSession[]>(`/agents/sessions?hours=${hours}&limit=${limit}`);
export const getSessionTrace = (sessionId: string, projectId?: string) =>
  get<SessionTrace>(`/agents/sessions/${encodeURIComponent(sessionId)}${projectId ? `?project_id=${encodeURIComponent(projectId)}` : ""}`);

// ─── Lineage (agent action DAG) ──────────────────────────────────────────────
export const getLineageGraph = (hours = 168, projectId?: string) =>
  get<LineageGraph>(`/agents/lineage?hours=${hours}${projectId ? `&project_id=${encodeURIComponent(projectId)}` : ""}`);

// ─── Reliability / Anomalies (P5.4) ───────────────────────────────────────────
export const getAnomalies = (currentHours = 1, zThreshold = 2.0) =>
  get<AnomalyResult[]>(`/reliability/anomalies?current_hours=${currentHours}&z_threshold=${zThreshold}`);

// ─── Projects ─────────────────────────────────────────────────────────────────
export const listProjects = () => get<ProjectResponse[]>("/projects");
export const createProject = (name: string, slug?: string) =>
  post<ProjectResponse>("/projects", { name, slug });
export const getProject = (id: string) => get<ProjectResponse>(`/projects/${encodeURIComponent(id)}`);
export const updateProject = (id: string, name: string, slug?: string) =>
  patch<ProjectResponse>(`/projects/${encodeURIComponent(id)}`, { name, slug });
export const deleteProject = (id: string) => del(`/projects/${encodeURIComponent(id)}`);
export const listProjectMembers = (id: string) => get<ProjectMember[]>(`/projects/${encodeURIComponent(id)}/members`);
export const addProjectMember = (projectId: string, userId: string, role: string) =>
  post<ProjectMember>(`/projects/${encodeURIComponent(projectId)}/members`, { user_id: userId, role });
export const removeProjectMember = (projectId: string, userId: string) =>
  del(`/projects/${encodeURIComponent(projectId)}/members/${encodeURIComponent(userId)}`);

// ─── User management ──────────────────────────────────────────────────────────
export const listUsers = () => get<DashboardUser[]>("/users");
export const inviteUser = (email: string, role: "admin" | "viewer") =>
  post<InviteResponse>("/users/invite", { email, role });
export const updateUserRole = (userId: string, role: "admin" | "viewer") =>
  patch<DashboardUser>(`/users/${encodeURIComponent(userId)}/role`, { role });
export const deactivateUser = (userId: string) =>
  del(`/users/${encodeURIComponent(userId)}`);

// ─── Alerts config & Slack ────────────────────────────────────────────────────
export const getAlertsConfig = () => get<{
  slack_webhook: string | null;
  alert_types: Record<string, boolean>;
  webhook_configured: boolean;
}>("/alerts/config");

export const saveAlertsConfig = (body: {
  slack_webhook?: string | null;
  alert_types?: Record<string, boolean>;
}) => post<{
  slack_webhook: string | null;
  alert_types: Record<string, boolean>;
  webhook_configured: boolean;
}>("/alerts/config", body);

export const testSlackWebhook = () =>
  post<{ ok: boolean; message: string }>("/alerts/test");

// ─── Audit logs ───────────────────────────────────────────────────────────────
export const getAuditLogs = (limit = 50, offset = 0) =>
  get<{
    total: number;
    limit: number;
    offset: number;
    events: Array<{
      id: number;
      timestamp: string;
      event: string;
      user_id: string;
      ip: string;
      details: Record<string, unknown>;
    }>;
  }>(`/audit/logs?limit=${limit}&offset=${offset}`);

// ─── SLOs (P5.5) ──────────────────────────────────────────────────────────────
export const getSLOStatus = () => get<SLOStatus[]>("/slos/status");
export const listSLOs = () => get<SLOStatus[]>("/slos");
export const deleteSLO = (id: string) => del(`/slos/${encodeURIComponent(id)}`);

// ── Agent Metadata (Catalog) ─────────────────────────────────────────────────
import type { AgentMetadata, ServerMetadata } from "./types";

function withProject(path: string, projectId?: string | null): string {
  return projectId ? `${path}?project_id=${encodeURIComponent(projectId)}` : path;
}

export const listAgentMetadata = (projectId?: string | null) =>
  get<AgentMetadata[]>(withProject("/agents/metadata", projectId));
export const getAgentMetadata = (name: string, projectId?: string | null) =>
  get<AgentMetadata>(withProject(`/agents/metadata/${encodeURIComponent(name)}`, projectId));
export const upsertAgentMetadata = (name: string, body: { description?: string; owner?: string; tags?: string[]; status?: string; runbook_url?: string }, projectId?: string | null) =>
  put<AgentMetadata>(withProject(`/agents/metadata/${encodeURIComponent(name)}`, projectId), body);
export const deleteAgentMetadata = (name: string, projectId?: string | null) =>
  del(withProject(`/agents/metadata/${encodeURIComponent(name)}`, projectId));

// ── v0.3 Prevention Config ────────────────────────────────────────────────────
export const listPreventionConfigs = (projectId?: string | null) =>
  get<import("@/lib/types").PreventionConfig[]>(withProject("/agents/prevention-configs", projectId));
export const getPreventionConfig = (agentName: string, projectId?: string | null) =>
  get<import("@/lib/types").PreventionConfig>(withProject(`/agents/${encodeURIComponent(agentName)}/prevention-config`, projectId));
export const savePreventionConfig = (agentName: string, body: import("@/lib/types").PreventionConfigUpdate, projectId?: string | null) =>
  put<import("@/lib/types").PreventionConfig>(withProject(`/agents/${encodeURIComponent(agentName)}/prevention-config`, projectId), body);
export const deletePreventionConfig = (agentName: string, projectId?: string | null) =>
  del(withProject(`/agents/${encodeURIComponent(agentName)}/prevention-config`, projectId));
export const getProjectPreventionConfig = (projectId?: string | null) =>
  get<import("@/lib/types").PreventionConfig>(withProject("/projects/prevention-config", projectId));
export const saveProjectPreventionConfig = (body: import("@/lib/types").PreventionConfigUpdate, projectId?: string | null) =>
  put<import("@/lib/types").PreventionConfig>(withProject("/projects/prevention-config", projectId), body);

// ── Monitoring ────────────────────────────────────────────────────────────────
export interface MonitoringBucket {
  bucket: string; sessions: number; tool_calls: number; errors: number;
  error_rate: number; avg_latency_ms: number; p99_latency_ms: number;
  input_tokens: number; output_tokens: number; agents: number;
}
export interface MonitoringModel {
  model_id: string; calls: number; input_tokens: number; output_tokens: number;
  avg_latency_ms: number; error_count: number; est_cost_usd: number | null;
}
export interface MonitoringTool {
  server_name: string; tool_name: string; calls: number; errors: number;
  avg_latency_ms: number; p99_latency_ms: number; success_rate: number;
  calls_per_session: number; content_errors: number;
}
export const getMonitoringTimeseries = (hours: number, projectId?: string | null) =>
  get<MonitoringBucket[]>(`/monitoring/timeseries?hours=${hours}${projectId ? `&project_id=${encodeURIComponent(projectId)}` : ""}`);
export const getMonitoringModels = (hours: number, projectId?: string | null) =>
  get<MonitoringModel[]>(`/monitoring/models?hours=${hours}${projectId ? `&project_id=${encodeURIComponent(projectId)}` : ""}`);
export const getMonitoringTools = (hours: number, projectId?: string | null) =>
  get<MonitoringTool[]>(`/monitoring/tools?hours=${hours}${projectId ? `&project_id=${encodeURIComponent(projectId)}` : ""}`);
export interface ErrorCategory {
  category: string; count: number; llm_errors: number; tool_errors: number; pct: number;
}
export const getMonitoringErrors = (hours: number, projectId?: string | null) =>
  get<ErrorCategory[]>(`/monitoring/errors?hours=${hours}${projectId ? `&project_id=${encodeURIComponent(projectId)}` : ""}`);
export const getAgentLoopCounts = (hours: number, projectId?: string | null) =>
  get<{ agent_name: string; loop_count: number }[]>(`/agents/loop-counts?hours=${hours}${projectId ? `&project_id=${encodeURIComponent(projectId)}` : ""}`);

// ── Server Metadata (Catalog) ─────────────────────────────────────────────────
export const listServerMetadata = (projectId?: string | null) =>
  get<ServerMetadata[]>(withProject("/servers/metadata", projectId));
export const upsertServerMetadata = (name: string, body: { description?: string; owner?: string; tags?: string[]; transport?: string; runbook_url?: string }, projectId?: string | null) =>
  put<ServerMetadata>(withProject(`/servers/metadata/${encodeURIComponent(name)}`, projectId), body);
export const discoverServers = (projectId?: string | null) =>
  post<{ discovered: number; servers: string[] }>(withProject("/servers/discover", projectId));
