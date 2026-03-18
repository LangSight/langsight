import type {
  AgentSession,
  ApiStatus,
  CostsBreakdownResponse,
  HealthResult,
  SecurityScanResult,
  SessionTrace,
} from "./types";

const BASE = "/api";

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json() as Promise<T>;
}

async function post<T>(path: string, body?: object): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
    cache: "no-store",
  });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json() as Promise<T>;
}

// SWR fetcher
export const fetcher = (url: string) =>
  fetch(url, { cache: "no-store" }).then((r) => {
    if (!r.ok) throw new Error(`${r.status}`);
    return r.json();
  });

// ─── Status ───────────────────────────────────────────────────────────────────
export const getStatus = () => get<ApiStatus>("/status");

// ─── Health ───────────────────────────────────────────────────────────────────
export const getServerHealth = () => get<HealthResult[]>("/health/servers");
export const getServerHistoty = (name: string, limit = 20) =>
  get<HealthResult[]>(`/health/servers/${encodeURIComponent(name)}/history?limit=${limit}`);
export const triggerHealthCheck = () => post<HealthResult[]>("/health/check");

// ─── Costs ────────────────────────────────────────────────────────────────────
export const getCostsBreakdown = (hours = 24) =>
  get<CostsBreakdownResponse>(`/costs/breakdown?hours=${hours}`);

// ─── Security ─────────────────────────────────────────────────────────────────
export const triggerSecurityScan = () =>
  post<SecurityScanResult[]>("/security/scan");

// ─── Sessions ─────────────────────────────────────────────────────────────────
export const getSessions = (hours = 24, limit = 50) =>
  get<AgentSession[]>(`/agents/sessions?hours=${hours}&limit=${limit}`);
export const getSessionTrace = (sessionId: string) =>
  get<SessionTrace>(`/agents/sessions/${encodeURIComponent(sessionId)}`);
