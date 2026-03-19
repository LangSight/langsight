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
  ModelPricingEntry,
  ProjectMember,
  ProjectResponse,
  ReplayResponse,
  SecurityScanResult,
  SessionComparison,
  SessionTrace,
  SLOStatus,
} from "./types";

const BASE = "/api";

/** Build headers including the optional API key for authentication. */
function apiHeaders(extra?: Record<string, string>): Record<string, string> {
  const headers: Record<string, string> = { ...extra };
  const key = process.env.NEXT_PUBLIC_LANGSIGHT_API_KEY;
  if (key) headers["X-API-Key"] = key;
  return headers;
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    cache: "no-store",
    headers: apiHeaders(),
  });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json() as Promise<T>;
}

async function del(path: string): Promise<void> {
  const r = await fetch(`${BASE}${path}`, {
    method: "DELETE",
    headers: apiHeaders(),
    cache: "no-store",
  });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
}

async function post<T>(path: string, body?: object): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: apiHeaders({ "Content-Type": "application/json" }),
    body: body ? JSON.stringify(body) : undefined,
    cache: "no-store",
  });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json() as Promise<T>;
}

// SWR fetcher — passes API key header
export const fetcher = (url: string) => {
  const key = process.env.NEXT_PUBLIC_LANGSIGHT_API_KEY;
  const headers: Record<string, string> = {};
  if (key) headers["X-API-Key"] = key;
  return fetch(url, { cache: "no-store", headers }).then((r) => {
    if (!r.ok) throw new Error(`${r.status}`);
    return r.json();
  });
};

// ─── Status ───────────────────────────────────────────────────────────────────
export const getStatus = () => get<ApiStatus>("/status");

// ─── Health ───────────────────────────────────────────────────────────────────
export const getServerHealth = () => get<HealthResult[]>("/health/servers");
export const getServerHistoty = (name: string, limit = 20) =>
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
  post<ModelPricingEntry>(`/costs/models/${encodeURIComponent(id)}`, body);
export const deactivateModelPricing = (id: string) =>
  del(`/costs/models/${encodeURIComponent(id)}`);

// ─── Security ─────────────────────────────────────────────────────────────────
export const triggerSecurityScan = () =>
  post<SecurityScanResult[]>("/security/scan");

// ─── API Keys ─────────────────────────────────────────────────────────────────
export const getApiKeys = () => get<ApiKeyResponse[]>("/auth/api-keys");
export const createApiKey = (name: string) =>
  post<ApiKeyCreatedResponse>("/auth/api-keys", { name });
export const revokeApiKey = (id: string) =>
  del(`/auth/api-keys/${encodeURIComponent(id)}`);

// ─── Sessions ─────────────────────────────────────────────────────────────────
export const getSessions = (hours = 24, limit = 50) =>
  get<AgentSession[]>(`/agents/sessions?hours=${hours}&limit=${limit}`);
export const getSessionTrace = (sessionId: string) =>
  get<SessionTrace>(`/agents/sessions/${encodeURIComponent(sessionId)}`);
export const compareSessions = (a: string, b: string) =>
  get<SessionComparison>(`/agents/sessions/compare?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`);
export const replaySession = (sessionId: string, timeoutPerCall = 10, totalTimeout = 60) =>
  post<ReplayResponse>(`/agents/sessions/${encodeURIComponent(sessionId)}/replay?timeout_per_call=${timeoutPerCall}&total_timeout=${totalTimeout}`);

// ─── Reliability / Anomalies (P5.4) ───────────────────────────────────────────
export const getAnomalies = (currentHours = 1, zThreshold = 2.0) =>
  get<AnomalyResult[]>(`/reliability/anomalies?current_hours=${currentHours}&z_threshold=${zThreshold}`);

// ─── Projects ─────────────────────────────────────────────────────────────────
export const listProjects = () => get<ProjectResponse[]>("/projects");
export const createProject = (name: string, slug?: string) =>
  post<ProjectResponse>("/projects", { name, slug });
export const getProject = (id: string) => get<ProjectResponse>(`/projects/${encodeURIComponent(id)}`);
export const updateProject = (id: string, name: string, slug?: string) =>
  post<ProjectResponse>(`/projects/${encodeURIComponent(id)}`, { name, slug });
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
  post<DashboardUser>(`/users/${encodeURIComponent(userId)}/role`, { role });
export const deactivateUser = (userId: string) =>
  del(`/users/${encodeURIComponent(userId)}`);

// ─── SLOs (P5.5) ──────────────────────────────────────────────────────────────
export const getSLOStatus = () => get<SLOStatus[]>("/slos/status");
export const listSLOs = () => get<SLOStatus[]>("/slos");
export const deleteSLO = (id: string) => del(`/slos/${encodeURIComponent(id)}`);
