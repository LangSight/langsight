/**
 * Tests for lib/api.ts
 *
 * All tests mock global fetch — no real network calls.
 */

import {
  fetcher,
  getStatus,
  getServerHealth,
  triggerHealthCheck,
  getCostsBreakdown,
  getSessions,
  getSessionTrace,
  createProject,
  listProjects,
  createApiKey,
  revokeApiKey,
  inviteUser,
} from "@/lib/api";

/* ── Helpers ─────────────────────────────────────────────────── */
function mockFetch(body: unknown, status = 200) {
  global.fetch = jest.fn().mockResolvedValueOnce({
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? "OK" : "Error",
    json: jest.fn().mockResolvedValueOnce(body),
  } as unknown as Response);
}

function mockFetchError(status: number, statusText = "Error") {
  global.fetch = jest.fn().mockResolvedValueOnce({
    ok: false,
    status,
    statusText,
    json: jest.fn().mockResolvedValueOnce({ detail: statusText }),
  } as unknown as Response);
}

afterEach(() => {
  jest.restoreAllMocks();
});

/* ── fetcher ────────────────────────────────────────────────── */
describe("fetcher", () => {
  it("calls fetch with the given URL and returns JSON", async () => {
    mockFetch({ status: "ok" });
    const result = await fetcher("/api/proxy/status");
    expect(fetch).toHaveBeenCalledWith("/api/proxy/status", expect.objectContaining({ cache: "no-store" }));
    expect(result).toEqual({ status: "ok" });
  });

  it("throws on non-ok response", async () => {
    mockFetchError(500, "Internal Server Error");
    await expect(fetcher("/api/proxy/status")).rejects.toThrow("500");
  });

  it("throws 401 Unauthorized on 401 response", async () => {
    global.fetch = jest.fn().mockResolvedValueOnce({
      ok: false, status: 401, statusText: "Unauthorized",
      json: jest.fn().mockResolvedValueOnce({ detail: "Unauthorized" }),
    } as unknown as Response);
    await expect(fetcher("/api/proxy/status")).rejects.toThrow("401 Unauthorized");
  });
});

/* ── getStatus ──────────────────────────────────────────────── */
describe("getStatus", () => {
  it("calls /api/status and returns the response", async () => {
    const mockStatus = { status: "ok", version: "0.2.0", servers_configured: 2 };
    mockFetch(mockStatus);

    const result = await getStatus();

    expect(fetch).toHaveBeenCalledWith(
      "/api/proxy/status",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(result).toEqual(mockStatus);
  });

  it("throws when API is unreachable", async () => {
    mockFetchError(503, "Service Unavailable");
    await expect(getStatus()).rejects.toThrow("503");
  });
});

/* ── getServerHealth ────────────────────────────────────────── */
describe("getServerHealth", () => {
  it("returns array of health results", async () => {
    const mockServers = [
      { server_name: "postgres-mcp", status: "up", latency_ms: 42, tools_count: 5, schema_hash: "abc123", error: null, checked_at: new Date().toISOString() },
      { server_name: "jira-mcp",     status: "down", latency_ms: null, tools_count: 3, schema_hash: null, error: "timeout", checked_at: new Date().toISOString() },
    ];
    mockFetch(mockServers);

    const result = await getServerHealth();
    expect(result).toHaveLength(2);
    expect(result[0].server_name).toBe("postgres-mcp");
    expect(result[1].status).toBe("down");
  });

  it("returns empty array for no servers", async () => {
    mockFetch([]);
    const result = await getServerHealth();
    expect(result).toEqual([]);
  });
});

/* ── triggerHealthCheck ─────────────────────────────────────── */
describe("triggerHealthCheck", () => {
  it("POSTs to /api/health/check", async () => {
    mockFetch([]);
    await triggerHealthCheck();
    expect(fetch).toHaveBeenCalledWith(
      "/api/proxy/health/check",
      expect.objectContaining({ method: "POST" })
    );
  });
});

/* ── getCostsBreakdown ──────────────────────────────────────── */
describe("getCostsBreakdown", () => {
  it("uses default 24h window", async () => {
    mockFetch({ total_cost_usd: 0, total_calls: 0, supports_costs: false, hours: 24, by_tool: [], by_agent: [], by_session: [], storage_mode: "postgres" });
    await getCostsBreakdown();
    expect((fetch as jest.Mock).mock.calls[0][0]).toContain("hours=24");
  });

  it("passes custom hours parameter", async () => {
    mockFetch({ total_cost_usd: 0, total_calls: 0, supports_costs: false, hours: 168, by_tool: [], by_agent: [], by_session: [], storage_mode: "postgres" });
    await getCostsBreakdown(168);
    expect((fetch as jest.Mock).mock.calls[0][0]).toContain("hours=168");
  });

  it("appends project_id when provided", async () => {
    mockFetch({ total_cost_usd: 0, total_calls: 0, supports_costs: false, hours: 24, by_tool: [], by_agent: [], by_session: [], storage_mode: "postgres" });
    await getCostsBreakdown(24, "proj-abc");
    expect((fetch as jest.Mock).mock.calls[0][0]).toContain("project_id=proj-abc");
  });
});

/* ── getSessions ────────────────────────────────────────────── */
describe("getSessions", () => {
  it("calls correct endpoint with defaults", async () => {
    mockFetch([]);
    await getSessions();
    const url = (fetch as jest.Mock).mock.calls[0][0] as string;
    expect(url).toContain("/agents/sessions");
    expect(url).toContain("hours=24");
    expect(url).toContain("limit=50");
  });

  it("accepts custom hours and limit", async () => {
    mockFetch([]);
    await getSessions(168, 200);
    const url = (fetch as jest.Mock).mock.calls[0][0] as string;
    expect(url).toContain("hours=168");
    expect(url).toContain("limit=200");
  });
});

/* ── getSessionTrace ────────────────────────────────────────── */
describe("getSessionTrace", () => {
  it("encodes session ID in URL", async () => {
    mockFetch({ session_id: "sess-abc", spans_flat: [], root_spans: [], total_spans: 0, tool_calls: 0, failed_calls: 0, duration_ms: null });
    await getSessionTrace("sess/with spaces");
    const url = (fetch as jest.Mock).mock.calls[0][0] as string;
    expect(url).toContain("sess%2Fwith%20spaces");
  });

  it("returns trace with spans", async () => {
    const mockTrace = {
      session_id: "sess-abc",
      spans_flat: [],
      root_spans: [{ span_id: "s1", tool_name: "query", server_name: "pg", status: "success", latency_ms: 42, children: [] }],
      total_spans: 1,
      tool_calls: 1,
      failed_calls: 0,
      duration_ms: 42,
    };
    mockFetch(mockTrace);
    const result = await getSessionTrace("sess-abc");
    expect(result.total_spans).toBe(1);
    expect(result.root_spans).toHaveLength(1);
  });
});


/* ── createProject ──────────────────────────────────────────── */
describe("createProject", () => {
  it("POSTs project name to /api/projects", async () => {
    const mockProject = { id: "p1", name: "My Project", slug: "my-project", created_by: "u1", created_at: "", member_count: 1, your_role: "owner" };
    mockFetch(mockProject);

    const result = await createProject("My Project");

    expect(fetch).toHaveBeenCalledWith(
      "/api/proxy/projects",
      expect.objectContaining({
        method: "POST",
        body: expect.stringContaining('"name":"My Project"'),
      })
    );
    expect(result.name).toBe("My Project");
  });

  it("optionally sends slug", async () => {
    mockFetch({ id: "p2", name: "Test", slug: "custom-slug", created_by: "u1", created_at: "", member_count: 1, your_role: "owner" });
    await createProject("Test", "custom-slug");
    const body = JSON.parse((fetch as jest.Mock).mock.calls[0][1].body);
    expect(body.slug).toBe("custom-slug");
  });
});

/* ── listProjects ───────────────────────────────────────────── */
describe("listProjects", () => {
  it("returns array of projects", async () => {
    const mockProjects = [
      { id: "p1", name: "Default", slug: "default", created_by: "u1", created_at: "", member_count: 1, your_role: "owner" },
      { id: "p2", name: "Gotphoto", slug: "gotphoto", created_by: "u1", created_at: "", member_count: 2, your_role: "member" },
    ];
    mockFetch(mockProjects);
    const result = await listProjects();
    expect(result).toHaveLength(2);
    expect(result[0].slug).toBe("default");
  });
});

/* ── createApiKey ───────────────────────────────────────────── */
describe("createApiKey", () => {
  it("POSTs key name and returns created key response", async () => {
    const mockCreated = { id: "k1", name: "prod-key", key: "ls_abc123", key_prefix: "ls_abc", created_at: new Date().toISOString() };
    mockFetch(mockCreated);

    const result = await createApiKey("prod-key");

    expect(fetch).toHaveBeenCalledWith(
      "/api/proxy/auth/api-keys",
      expect.objectContaining({ method: "POST" })
    );
    expect(result.key).toBe("ls_abc123");
    expect(result.name).toBe("prod-key");
  });
});

/* ── revokeApiKey ───────────────────────────────────────────── */
describe("revokeApiKey", () => {
  it("DELETEs the key by ID", async () => {
    global.fetch = jest.fn().mockResolvedValueOnce({ ok: true, status: 204, json: jest.fn() } as unknown as Response);
    await revokeApiKey("key-123");
    expect(fetch).toHaveBeenCalledWith(
      "/api/proxy/auth/api-keys/key-123",
      expect.objectContaining({ method: "DELETE" })
    );
  });

  it("throws on 404 (key not found)", async () => {
    mockFetchError(404, "Not Found");
    await expect(revokeApiKey("nonexistent")).rejects.toThrow("404");
  });
});

/* ── inviteUser ─────────────────────────────────────────────── */
describe("inviteUser", () => {
  it("POSTs email and role to /api/users/invite", async () => {
    const mockInvite = { token: "tok_abc", invite_url: "http://localhost/accept?token=tok_abc", email: "user@example.com", role: "viewer", expires_at: "" };
    mockFetch(mockInvite);

    const result = await inviteUser("user@example.com", "viewer");

    const body = JSON.parse((fetch as jest.Mock).mock.calls[0][1].body);
    expect(body.email).toBe("user@example.com");
    expect(body.role).toBe("viewer");
    expect(result.token).toBe("tok_abc");
  });
});
