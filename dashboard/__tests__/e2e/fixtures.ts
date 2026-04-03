/**
 * Shared fixtures and mock data for Playwright E2E tests.
 *
 * Provides:
 *   - mockApiRoutes()  — intercepts all /api/proxy/* and /api/auth/* routes
 *   - signInWithMocks() — performs sign-in with mocked auth and API data
 *   - MOCK_* constants  — realistic fixture data matching the TypeScript types
 *
 * Usage:
 *   test.beforeEach(async ({ page }) => {
 *     await mockApiRoutes(page);
 *     await signInWithMocks(page);
 *   });
 */
import { type Page, type Route } from "@playwright/test";

/* ── Mock data ────────────────────────────────────────────────── */

export const MOCK_USER = {
  id: "usr_test_001",
  name: "Admin User",
  email: "admin@langsight.dev",
  role: "admin",
};

export const MOCK_STATUS = {
  status: "ok",
  version: "0.2.0",
  servers_configured: 3,
  auth_enabled: true,
  storage_mode: "postgres",
};

export const MOCK_HEALTH_SERVERS = [
  {
    server_name: "postgres-mcp",
    status: "up",
    latency_ms: 42,
    tools_count: 5,
    schema_hash: "abc123",
    error: null,
    checked_at: new Date(Date.now() - 60_000).toISOString(),
  },
  {
    server_name: "s3-mcp",
    status: "degraded",
    latency_ms: 350,
    tools_count: 3,
    schema_hash: "def456",
    error: null,
    checked_at: new Date(Date.now() - 120_000).toISOString(),
  },
  {
    server_name: "redis-mcp",
    status: "down",
    latency_ms: null,
    tools_count: 0,
    schema_hash: null,
    error: "Connection refused: ECONNREFUSED 127.0.0.1:6379",
    checked_at: new Date(Date.now() - 300_000).toISOString(),
  },
];

export const MOCK_HEALTH_HISTORY = [
  {
    server_name: "postgres-mcp",
    status: "up",
    latency_ms: 38,
    tools_count: 5,
    schema_hash: "abc123",
    error: null,
    checked_at: new Date(Date.now() - 300_000).toISOString(),
  },
  {
    server_name: "postgres-mcp",
    status: "up",
    latency_ms: 45,
    tools_count: 5,
    schema_hash: "abc123",
    error: null,
    checked_at: new Date(Date.now() - 600_000).toISOString(),
  },
  {
    server_name: "postgres-mcp",
    status: "down",
    latency_ms: null,
    tools_count: 0,
    schema_hash: null,
    error: "Connection timeout",
    checked_at: new Date(Date.now() - 900_000).toISOString(),
  },
];

export const MOCK_SESSIONS = [
  {
    session_id: "sess_abc123def456789012345",
    agent_name: "data-pipeline-agent",
    first_call_at: new Date(Date.now() - 300_000).toISOString(),
    last_call_at: new Date(Date.now() - 60_000).toISOString(),
    tool_calls: 12,
    failed_calls: 0,
    duration_ms: 4500,
    servers_used: ["postgres-mcp", "s3-mcp"],
  },
  {
    session_id: "sess_xyz789abc123456789012",
    agent_name: "data-pipeline-agent",
    first_call_at: new Date(Date.now() - 600_000).toISOString(),
    last_call_at: new Date(Date.now() - 500_000).toISOString(),
    tool_calls: 8,
    failed_calls: 2,
    duration_ms: 2200,
    servers_used: ["postgres-mcp"],
  },
  {
    session_id: "sess_lmn456uvw789012345678",
    agent_name: "security-scanner-agent",
    first_call_at: new Date(Date.now() - 3600_000).toISOString(),
    last_call_at: new Date(Date.now() - 3300_000).toISOString(),
    tool_calls: 25,
    failed_calls: 1,
    duration_ms: 15000,
    servers_used: ["postgres-mcp", "s3-mcp", "redis-mcp"],
  },
];

export const MOCK_SESSION_TRACE = {
  session_id: "sess_abc123def456789012345",
  spans_flat: [
    {
      span_id: "span_001",
      parent_span_id: null,
      span_type: "agent",
      server_name: "",
      tool_name: "",
      agent_name: "data-pipeline-agent",
      started_at: new Date(Date.now() - 300_000).toISOString(),
      ended_at: new Date(Date.now() - 60_000).toISOString(),
      latency_ms: 240000,
      status: "success",
      error: null,
      trace_id: "trace_001",
      input_json: null,
      output_json: null,
      llm_input: "Process the data pipeline for today",
      llm_output: "I will query the database and upload results to S3.",
      input_tokens: 150,
      output_tokens: 45,
      model_id: "claude-3-5-sonnet",
      children: [],
    },
    {
      span_id: "span_002",
      parent_span_id: "span_001",
      span_type: "tool_call",
      server_name: "postgres-mcp",
      tool_name: "query",
      agent_name: "data-pipeline-agent",
      started_at: new Date(Date.now() - 280_000).toISOString(),
      ended_at: new Date(Date.now() - 275_000).toISOString(),
      latency_ms: 5000,
      status: "success",
      error: null,
      trace_id: "trace_001",
      input_json: '{"sql": "SELECT * FROM orders WHERE date = today()"}',
      output_json: '{"rows": 142}',
      llm_input: null,
      llm_output: null,
      input_tokens: null,
      output_tokens: null,
      model_id: null,
    finish_reason: null,
      target_agent_name: null,
      lineage_provenance: "explicit" as const,
      lineage_status: "complete" as const,
      schema_version: "1.0",
      children: [],
    },
    {
      span_id: "span_003",
      parent_span_id: "span_001",
      span_type: "tool_call",
      server_name: "s3-mcp",
      tool_name: "put_object",
      agent_name: "data-pipeline-agent",
      started_at: new Date(Date.now() - 200_000).toISOString(),
      ended_at: new Date(Date.now() - 195_000).toISOString(),
      latency_ms: 5000,
      status: "success",
      error: null,
      trace_id: "trace_001",
      input_json: '{"bucket": "data-lake", "key": "output/today.csv"}',
      output_json: '{"etag": "abc123"}',
      llm_input: null,
      llm_output: null,
      input_tokens: null,
      output_tokens: null,
      model_id: null,
    finish_reason: null,
      target_agent_name: null,
      lineage_provenance: "explicit" as const,
      lineage_status: "complete" as const,
      schema_version: "1.0",
      children: [],
    },
  ],
  root_spans: [],
  total_spans: 3,
  tool_calls: 2,
  failed_calls: 0,
  duration_ms: 240000,
};

export const MOCK_ANOMALIES = [
  {
    server_name: "redis-mcp",
    tool_name: "get",
    metric: "error_rate",
    current_value: 0.45,
    baseline_mean: 0.02,
    baseline_stddev: 0.01,
    z_score: 43.0,
    severity: "critical",
    sample_hours: 24,
  },
];

export const MOCK_SLO_STATUSES = [
  {
    slo_id: "slo_001",
    agent_name: "data-pipeline-agent",
    metric: "success_rate",
    target: 99.0,
    current_value: 99.5,
    window_hours: 24,
    status: "ok",
    evaluated_at: new Date(Date.now() - 60_000).toISOString(),
  },
  {
    slo_id: "slo_002",
    agent_name: "security-scanner-agent",
    metric: "latency_p99",
    target: 5000,
    current_value: 3200,
    window_hours: 24,
    status: "ok",
    evaluated_at: new Date(Date.now() - 60_000).toISOString(),
  },
];

export const MOCK_SECURITY_SCAN = [
  {
    server_name: "postgres-mcp",
    scanned_at: new Date().toISOString(),
    error: null,
    findings_count: 2,
    critical_count: 0,
    high_count: 1,
    highest_severity: "high",
    findings: [
      {
        severity: "high",
        category: "auth",
        title: "No authentication configured",
        description: "MCP server accepts connections without authentication",
        remediation: "Enable API key or TLS client cert authentication",
        tool_name: null,
        cve_id: null,
      },
      {
        severity: "medium",
        category: "config",
        title: "Default port exposed",
        description: "MCP server running on default port 5432",
        remediation: "Use a non-default port or restrict network access",
        tool_name: null,
        cve_id: null,
      },
    ],
  },
];

export const MOCK_COSTS_BREAKDOWN = {
  storage_mode: "postgres",
  supports_costs: false,
  hours: 24,
  total_calls: 45,
  total_cost_usd: 0.0,
  llm_cost_usd: 0.0,
  tool_cost_usd: 0.0,
  total_input_tokens: 0,
  total_output_tokens: 0,
  by_tool: [],
  by_agent: [],
  by_session: [],
};

export const MOCK_API_KEYS = [
  {
    id: "key_001",
    name: "Production SDK",
    key_prefix: "ls_prod_",
    created_at: new Date(Date.now() - 86400_000).toISOString(),
    last_used_at: new Date(Date.now() - 3600_000).toISOString(),
    revoked_at: null,
  },
  {
    id: "key_002",
    name: "Development",
    key_prefix: "ls_dev_",
    created_at: new Date(Date.now() - 172800_000).toISOString(),
    last_used_at: null,
    revoked_at: null,
  },
];

export const MOCK_USERS = [
  {
    id: "usr_test_001",
    email: "admin@langsight.dev",
    role: "admin",
    active: true,
    created_at: new Date(Date.now() - 604800_000).toISOString(),
    last_login_at: new Date().toISOString(),
  },
  {
    id: "usr_test_002",
    email: "viewer@langsight.dev",
    role: "viewer",
    active: true,
    created_at: new Date(Date.now() - 172800_000).toISOString(),
    last_login_at: new Date(Date.now() - 86400_000).toISOString(),
  },
];

export const MOCK_MODEL_PRICING = [
  {
    id: "mp_001",
    provider: "Anthropic",
    model_id: "claude-3-5-sonnet",
    display_name: "Claude 3.5 Sonnet",
    input_per_1m_usd: 3.0,
    output_per_1m_usd: 15.0,
    cache_read_per_1m_usd: 0.3,
    effective_from: new Date(Date.now() - 2592000_000).toISOString(),
    effective_to: null,
    notes: null,
    is_custom: false,
    is_active: true,
  },
];

export const MOCK_ALERTS_CONFIG = {
  slack_webhook: null,
  alert_types: {
    health_down: true,
    security_critical: true,
    anomaly_detected: true,
    slo_breach: true,
  },
  webhook_configured: false,
};

export const MOCK_AUDIT_LOGS = {
  total: 2,
  limit: 50,
  offset: 0,
  events: [
    {
      id: 1,
      timestamp: new Date(Date.now() - 3600_000).toISOString(),
      event: "user.login",
      user_id: "usr_test_001",
      ip: "127.0.0.1",
      details: { method: "credentials" },
    },
    {
      id: 2,
      timestamp: new Date(Date.now() - 7200_000).toISOString(),
      event: "api_key.created",
      user_id: "usr_test_001",
      ip: "127.0.0.1",
      details: { key_name: "Production SDK" },
    },
  ],
};

export const MOCK_PROJECTS = [
  {
    id: "proj_001",
    name: "Production",
    slug: "production",
    created_by: "usr_test_001",
    created_at: new Date(Date.now() - 604800_000).toISOString(),
    member_count: 2,
    your_role: "admin",
  },
];

export const MOCK_LINEAGE = {
  window_hours: 168,
  nodes: [
    { id: "agent:data-pipeline-agent", type: "agent", label: "data-pipeline-agent", metrics: { total_calls: 20, error_count: 2, avg_latency_ms: 120 } },
    { id: "agent:security-scanner-agent", type: "agent", label: "security-scanner-agent", metrics: { total_calls: 25, error_count: 1, avg_latency_ms: 300 } },
    { id: "server:postgres-mcp", type: "server", label: "postgres-mcp", metrics: { total_calls: 30, error_count: 1, avg_latency_ms: 42 } },
    { id: "server:s3-mcp", type: "server", label: "s3-mcp", metrics: { total_calls: 15, error_count: 2, avg_latency_ms: 350 } },
  ],
  edges: [
    { source: "agent:data-pipeline-agent", target: "server:postgres-mcp", type: "calls", metrics: { call_count: 12, error_count: 0, avg_latency_ms: 38 } },
    { source: "agent:data-pipeline-agent", target: "server:s3-mcp", type: "calls", metrics: { call_count: 8, error_count: 2, avg_latency_ms: 350 } },
    { source: "agent:security-scanner-agent", target: "server:postgres-mcp", type: "calls", metrics: { call_count: 18, error_count: 1, avg_latency_ms: 45 } },
  ],
};

export const MOCK_AGENT_METADATA = [
  {
    id: "meta_001",
    agent_name: "data-pipeline-agent",
    description: "Processes daily data pipeline ETL tasks",
    owner: "Data Engineering",
    tags: ["etl", "production"],
    status: "active",
    runbook_url: "https://wiki.example.com/data-pipeline",
    project_id: null,
    created_at: new Date(Date.now() - 604800_000).toISOString(),
    updated_at: new Date(Date.now() - 86400_000).toISOString(),
  },
  {
    id: "meta_002",
    agent_name: "security-scanner-agent",
    description: "Runs OWASP security scans on MCP servers",
    owner: "Security Team",
    tags: ["security", "compliance"],
    status: "active",
    runbook_url: "",
    project_id: null,
    created_at: new Date(Date.now() - 604800_000).toISOString(),
    updated_at: new Date(Date.now() - 172800_000).toISOString(),
  },
];

export const MOCK_SERVER_METADATA = [
  {
    id: "smeta_001",
    server_name: "postgres-mcp",
    description: "PostgreSQL data warehouse",
    owner: "DBA Team",
    tags: ["database", "production"],
    transport: "stdio",
    runbook_url: "https://wiki.example.com/postgres",
    project_id: null,
    created_at: new Date(Date.now() - 604800_000).toISOString(),
    updated_at: new Date(Date.now() - 86400_000).toISOString(),
  },
];

/* ── Route interception ───────────────────────────────────────── */

/**
 * Map of API path patterns to mock response data.
 * The keys are substring matches against the URL path.
 * Order matters: more specific paths should come first.
 */
function buildRouteMap() {
  return new Map<string, { body: unknown; status?: number }>([
    // Status
    ["/api/proxy/status", { body: MOCK_STATUS }],

    // Health
    ["/api/proxy/health/check", { body: MOCK_HEALTH_SERVERS }],
    ["/api/proxy/health/servers/", { body: MOCK_HEALTH_HISTORY }], // history endpoint (contains server name)
    ["/api/proxy/health/servers", { body: MOCK_HEALTH_SERVERS }],
    ["/api/health/servers/", { body: MOCK_HEALTH_HISTORY }],
    ["/api/health/servers", { body: MOCK_HEALTH_SERVERS }],

    // Sessions
    ["/api/proxy/agents/sessions/", { body: MOCK_SESSION_TRACE }],
    ["/api/proxy/agents/sessions", { body: MOCK_SESSIONS }],
    ["/api/agents/sessions/", { body: MOCK_SESSION_TRACE }],
    ["/api/agents/sessions", { body: MOCK_SESSIONS }],

    // Lineage
    ["/api/proxy/agents/lineage", { body: MOCK_LINEAGE }],
    ["/api/agents/lineage", { body: MOCK_LINEAGE }],

    // Agent metadata
    ["/api/proxy/agents/metadata", { body: MOCK_AGENT_METADATA }],
    ["/api/agents/metadata", { body: MOCK_AGENT_METADATA }],

    // Server metadata
    ["/api/proxy/servers/metadata", { body: MOCK_SERVER_METADATA }],
    ["/api/servers/metadata", { body: MOCK_SERVER_METADATA }],

    // Costs
    ["/api/proxy/costs/breakdown", { body: MOCK_COSTS_BREAKDOWN }],
    ["/api/proxy/costs/models", { body: MOCK_MODEL_PRICING }],
    ["/api/costs/breakdown", { body: MOCK_COSTS_BREAKDOWN }],
    ["/api/costs/models", { body: MOCK_MODEL_PRICING }],

    // Security
    ["/api/proxy/security/scan", { body: MOCK_SECURITY_SCAN }],
    ["/api/security/scan", { body: [] }], // GET returns empty before scan

    // Reliability / Anomalies
    ["/api/proxy/reliability/anomalies", { body: MOCK_ANOMALIES }],
    ["/api/reliability/anomalies", { body: MOCK_ANOMALIES }],

    // SLOs
    ["/api/proxy/slos/status", { body: MOCK_SLO_STATUSES }],
    ["/api/proxy/slos", { body: MOCK_SLO_STATUSES }],
    ["/api/slos/status", { body: MOCK_SLO_STATUSES }],
    ["/api/slos", { body: MOCK_SLO_STATUSES }],

    // API keys
    ["/api/proxy/auth/api-keys", { body: MOCK_API_KEYS }],
    ["/api/auth/api-keys", { body: MOCK_API_KEYS }],

    // Users
    ["/api/proxy/users", { body: MOCK_USERS }],

    // Alerts
    ["/api/proxy/alerts/config", { body: MOCK_ALERTS_CONFIG }],
    ["/api/alerts/config", { body: MOCK_ALERTS_CONFIG }],
    ["/api/proxy/alerts/test", { body: { ok: true, message: "Test notification sent" } }],

    // Audit logs
    ["/api/proxy/audit/logs", { body: MOCK_AUDIT_LOGS }],
    ["/api/audit/logs", { body: MOCK_AUDIT_LOGS }],

    // Projects
    ["/api/proxy/projects", { body: MOCK_PROJECTS }],
    ["/api/projects", { body: MOCK_PROJECTS }],
  ]);
}

/**
 * Intercept all API routes with mock data so tests run without a backend.
 *
 * Also mocks the NextAuth session endpoint to return a valid session,
 * which prevents the dashboard from redirecting to /login.
 */
export async function mockApiRoutes(page: Page): Promise<void> {
  const routeMap = buildRouteMap();

  // Mock NextAuth session — this is what useSession() reads
  await page.route("**/api/auth/session", async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        user: {
          id: MOCK_USER.id,
          name: MOCK_USER.name,
          email: MOCK_USER.email,
          role: MOCK_USER.role,
        },
        expires: new Date(Date.now() + 86400_000).toISOString(),
      }),
    });
  });

  // Mock the CSRF token endpoint (NextAuth needs this for sign-in)
  await page.route("**/api/auth/csrf", async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ csrfToken: "mock-csrf-token" }),
    });
  });

  // Mock the NextAuth providers endpoint
  await page.route("**/api/auth/providers", async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        credentials: {
          id: "credentials",
          name: "Credentials",
          type: "credentials",
          signinUrl: "/api/auth/signin/credentials",
          callbackUrl: "/api/auth/callback/credentials",
        },
      }),
    });
  });

  // Mock the sign-in callback — always succeed
  await page.route("**/api/auth/callback/credentials*", async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ url: "/", error: null }),
    });
  });

  // Mock the sign-in POST
  await page.route("**/api/auth/signin/credentials*", async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ url: "/" }),
    });
  });

  // Mock all data API routes
  await page.route("**/api/**", async (route: Route) => {
    const url = route.request().url();
    const pathname = new URL(url).pathname;

    // Skip auth routes — they are already handled above
    if (pathname.startsWith("/api/auth/")) {
      await route.fallback();
      return;
    }

    // Find matching mock
    for (const [pattern, response] of routeMap) {
      if (pathname.includes(pattern) || url.includes(pattern)) {
        await route.fulfill({
          status: response.status ?? 200,
          contentType: "application/json",
          body: JSON.stringify(response.body),
        });
        return;
      }
    }

    // Fallback: return empty JSON for unmatched API routes
    // This prevents 502 errors from the proxy when no backend is running
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    });
  });
}

/**
 * Navigate to the login page and perform a sign-in with mocked routes.
 *
 * After sign-in, waits for the redirect to / before returning.
 */
export async function signInWithMocks(page: Page): Promise<void> {
  await page.goto("/login");
  await page.fill('[id="email"]', "admin@langsight.dev");
  await page.fill('[id="password"]', "demo123");
  await page.getByRole("button", { name: /sign in/i }).click();
  // Wait for navigation to complete — either to / or the page stays on /login
  // with session now established
  await page.waitForURL(/^\/$|\/login/, { timeout: 10_000 });
}

/**
 * Variant: set up mocks and then directly navigate to a page
 * (bypassing login flow by using mocked session).
 */
export async function gotoWithMocks(page: Page, path: string): Promise<void> {
  await mockApiRoutes(page);
  await page.goto(path);
}
