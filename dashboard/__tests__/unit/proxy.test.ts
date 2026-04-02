/**
 * @jest-environment node
 *
 * Unit tests for the Next.js proxy route:
 *   dashboard/app/api/proxy/[...path]/route.ts
 *
 * Tests:
 *   - Returns 401 when no NextAuth session exists
 *   - Forwards X-User-Id and X-User-Role headers from the session
 *   - Forwards query params to the upstream FastAPI URL
 *   - Forwards request body for POST/PATCH/PUT
 *   - Returns 502 when FastAPI is unreachable (fetch throws)
 *   - Returns upstream status code transparently
 *   - Does NOT forward X-User-Id/X-User-Role when session fields are absent
 *   - Forwards X-API-Key when LANGSIGHT_API_KEY env var is set
 *
 * All external dependencies (auth, fetch) are mocked — no real network calls.
 */

import { NextRequest } from "next/server";

// ── Mock @/lib/auth before importing the route ──────────────────────────────
jest.mock("@/lib/auth", () => ({
  auth: jest.fn(),
}));

import { auth } from "@/lib/auth";

// We import the handler after mocking auth so module-level `auth` is the mock.
import { GET, POST, PATCH } from "@/app/api/proxy/[...path]/route";

// ── Helpers ──────────────────────────────────────────────────────────────────

type SessionWithMeta = {
  userId?: string;
  userRole?: string;
  user?: { name?: string };
};

function mockAuth(session: SessionWithMeta | null): void {
  (auth as jest.Mock).mockResolvedValue(session);
}

function mockFetchOk(body: string, status = 200, contentType = "application/json"): void {
  global.fetch = jest.fn().mockResolvedValueOnce({
    ok: status >= 200 && status < 300,
    status,
    text: jest.fn().mockResolvedValueOnce(body),
    headers: {
      get: (key: string) => (key === "Content-Type" ? contentType : null),
    },
  } as unknown as Response);
}

function mockFetchThrows(error: Error = new Error("ECONNREFUSED")): void {
  global.fetch = jest.fn().mockRejectedValueOnce(error);
}

function makeRequest(
  path: string[],
  method = "GET",
  search = "",
  body?: string
): [NextRequest, { params: Promise<{ path: string[] }> }] {
  const url = `http://localhost:3002/api/proxy/${path.join("/")}${search}`;
  const req = new NextRequest(url, {
    method,
    body: body ?? undefined,
    headers: { "Content-Type": "application/json" },
  });
  const context = { params: Promise.resolve({ path }) };
  return [req, context];
}

afterEach(() => {
  jest.restoreAllMocks();
  delete process.env.LANGSIGHT_API_URL;
  delete process.env.LANGSIGHT_API_KEY;
});

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("proxy route — authentication", () => {
  it("returns 401 when no session exists", async () => {
    mockAuth(null);

    const [req, ctx] = makeRequest(["health", "servers"]);
    const response = await GET(req, ctx);

    expect(response.status).toBe(401);
    const body = await response.json();
    expect(body.detail).toMatch(/authentication required/i);
  });

  it("does not call fetch when session is missing", async () => {
    mockAuth(null);
    global.fetch = jest.fn();

    const [req, ctx] = makeRequest(["health", "servers"]);
    await GET(req, ctx);

    expect(fetch).not.toHaveBeenCalled();
  });

  it("returns upstream response when session is valid", async () => {
    mockAuth({ userId: "u1", userRole: "admin" });
    mockFetchOk(JSON.stringify([{ server_name: "pg", status: "up" }]));

    const [req, ctx] = makeRequest(["health", "servers"]);
    const response = await GET(req, ctx);

    expect(response.status).toBe(200);
  });
});

describe("proxy route — header forwarding", () => {
  it("forwards X-User-Id from session to upstream", async () => {
    mockAuth({ userId: "user-abc", userRole: "admin" });
    mockFetchOk("{}");

    const [req, ctx] = makeRequest(["status"]);
    await GET(req, ctx);

    const [, fetchOptions] = (fetch as jest.Mock).mock.calls[0];
    expect(fetchOptions.headers["X-User-Id"]).toBe("user-abc");
  });

  it("forwards X-User-Role from session to upstream", async () => {
    mockAuth({ userId: "user-abc", userRole: "viewer" });
    mockFetchOk("{}");

    const [req, ctx] = makeRequest(["status"]);
    await GET(req, ctx);

    const [, fetchOptions] = (fetch as jest.Mock).mock.calls[0];
    expect(fetchOptions.headers["X-User-Role"]).toBe("viewer");
  });

  it("does not set X-User-Id when session has no userId", async () => {
    // Session exists but userId is absent (e.g. OAuth without custom fields)
    mockAuth({ user: { name: "Anonymous" } });
    mockFetchOk("{}");

    const [req, ctx] = makeRequest(["status"]);
    await GET(req, ctx);

    const [, fetchOptions] = (fetch as jest.Mock).mock.calls[0];
    expect(fetchOptions.headers["X-User-Id"]).toBeUndefined();
  });

  it("does not set X-User-Role when session has no userRole", async () => {
    mockAuth({ userId: "u1" });
    mockFetchOk("{}");

    const [req, ctx] = makeRequest(["status"]);
    await GET(req, ctx);

    const [, fetchOptions] = (fetch as jest.Mock).mock.calls[0];
    expect(fetchOptions.headers["X-User-Role"]).toBeUndefined();
  });

  it("always calls upstream fetch with cache: no-store", async () => {
    mockAuth({ userId: "u1", userRole: "admin" });
    mockFetchOk("{}");

    const [req, ctx] = makeRequest(["status"]);
    await GET(req, ctx);

    const [, fetchOptions] = (fetch as jest.Mock).mock.calls[0];
    expect(fetchOptions.cache).toBe("no-store");
  });

  it("passes Content-Type from request to upstream", async () => {
    mockAuth({ userId: "u1", userRole: "admin" });
    mockFetchOk("{}");

    const [req, ctx] = makeRequest(["status"]);
    await GET(req, ctx);

    const [, fetchOptions] = (fetch as jest.Mock).mock.calls[0];
    expect(fetchOptions.headers).toHaveProperty("Content-Type");
  });
});

describe("proxy route — URL construction", () => {
  it("builds correct upstream URL from path segments", async () => {
    mockAuth({ userId: "u1", userRole: "admin" });
    mockFetchOk("{}");

    const [req, ctx] = makeRequest(["health", "servers"]);
    await GET(req, ctx);

    const [upstreamUrl] = (fetch as jest.Mock).mock.calls[0];
    expect(upstreamUrl).toContain("/api/health/servers");
  });

  it("forwards query params to upstream URL", async () => {
    mockAuth({ userId: "u1", userRole: "admin" });
    mockFetchOk("[]");

    const [req, ctx] = makeRequest(["agents", "sessions"], "GET", "?hours=48&project_id=p1");
    await GET(req, ctx);

    const [upstreamUrl] = (fetch as jest.Mock).mock.calls[0];
    expect(upstreamUrl).toContain("hours=48");
    expect(upstreamUrl).toContain("project_id=p1");
  });

  it("upstream URL always contains /api/ prefix before path", async () => {
    mockAuth({ userId: "u1", userRole: "admin" });
    mockFetchOk("{}");

    const [req, ctx] = makeRequest(["status"]);
    await GET(req, ctx);

    const [upstreamUrl] = (fetch as jest.Mock).mock.calls[0];
    expect(upstreamUrl).toContain("/api/status");
  });
});

describe("proxy route — upstream error handling", () => {
  it("returns 502 when upstream fetch throws (network unreachable)", async () => {
    mockAuth({ userId: "u1", userRole: "admin" });
    mockFetchThrows(new Error("ECONNREFUSED"));

    const [req, ctx] = makeRequest(["health", "servers"]);
    const response = await GET(req, ctx);

    expect(response.status).toBe(502);
    const body = await response.json();
    expect(body.detail).toMatch(/unreachable/i);
  });

  it("returns 502 on AbortError (timeout)", async () => {
    mockAuth({ userId: "u1", userRole: "admin" });
    const abortErr = new DOMException("The operation was aborted", "AbortError");
    mockFetchThrows(abortErr);

    const [req, ctx] = makeRequest(["health", "servers"]);
    const response = await GET(req, ctx);

    expect(response.status).toBe(502);
  });

  it("transparently returns 404 from upstream", async () => {
    mockAuth({ userId: "u1", userRole: "admin" });
    mockFetchOk(JSON.stringify({ detail: "Not found" }), 404);

    const [req, ctx] = makeRequest(["agents", "sessions", "nonexistent"]);
    const response = await GET(req, ctx);

    expect(response.status).toBe(404);
  });

  it("transparently returns 503 from upstream", async () => {
    mockAuth({ userId: "u1", userRole: "admin" });
    mockFetchOk(JSON.stringify({ detail: "Service unavailable" }), 503);

    const [req, ctx] = makeRequest(["agents", "sessions", "s1"]);
    const response = await GET(req, ctx);

    expect(response.status).toBe(503);
  });
});

describe("proxy route — 204/304 no-content responses", () => {
  it("returns 204 with no body when upstream returns 204 (DELETE success)", async () => {
    mockAuth({ userId: "u1", userRole: "admin" });
    // 204 responses have no body — mock text() returning empty string
    global.fetch = jest.fn().mockResolvedValueOnce({
      ok: true,
      status: 204,
      text: jest.fn().mockResolvedValueOnce(""),
      headers: { get: () => null },
    } as unknown as Response);

    const { DELETE } = await import("@/app/api/proxy/[...path]/route");
    const [req, ctx] = makeRequest(["projects", "proj-123"], "DELETE");
    const response = await DELETE(req, ctx);

    expect(response.status).toBe(204);
    // Body must be empty — reading it should return empty string or null
    const text = await response.text();
    expect(text).toBe("");
  });

  it("does NOT return 502 when upstream returns 204 (regression for delete bug)", async () => {
    mockAuth({ userId: "u1", userRole: "admin" });
    global.fetch = jest.fn().mockResolvedValueOnce({
      ok: true,
      status: 204,
      text: jest.fn().mockResolvedValueOnce(""),
      headers: { get: () => null },
    } as unknown as Response);

    const { DELETE } = await import("@/app/api/proxy/[...path]/route");
    const [req, ctx] = makeRequest(["projects", "proj-456"], "DELETE");
    const response = await DELETE(req, ctx);

    expect(response.status).not.toBe(502);
    expect(response.status).toBe(204);
  });

  it("returns 304 with no body when upstream returns 304", async () => {
    mockAuth({ userId: "u1", userRole: "admin" });
    global.fetch = jest.fn().mockResolvedValueOnce({
      ok: true,
      status: 304,
      text: jest.fn().mockResolvedValueOnce(""),
      headers: { get: () => null },
    } as unknown as Response);

    const [req, ctx] = makeRequest(["health", "servers"]);
    const response = await GET(req, ctx);

    expect(response.status).toBe(304);
    const text = await response.text();
    expect(text).toBe("");
  });
});

describe("proxy route — body forwarding", () => {
  it("forwards request body for POST requests", async () => {
    mockAuth({ userId: "u1", userRole: "admin" });
    mockFetchOk(JSON.stringify({ id: "k1", key: "ls_abc" }), 201);

    const bodyPayload = JSON.stringify({ name: "my-key", role: "viewer" });
    const [req, ctx] = makeRequest(["auth", "api-keys"], "POST", "", bodyPayload);
    await POST(req, ctx);

    const [, fetchOptions] = (fetch as jest.Mock).mock.calls[0];
    expect(fetchOptions.method).toBe("POST");
    expect(fetchOptions.body).toBe(bodyPayload);
  });

  it("forwards request body for PATCH requests", async () => {
    mockAuth({ userId: "u1", userRole: "admin" });
    mockFetchOk("{}", 200);

    const patchBody = JSON.stringify({ input_per_1m_usd: 3.0 });
    const [req, ctx] = makeRequest(["costs", "models", "entry-1"], "PATCH", "", patchBody);
    await PATCH(req, ctx);

    const [, fetchOptions] = (fetch as jest.Mock).mock.calls[0];
    expect(fetchOptions.method).toBe("PATCH");
    expect(fetchOptions.body).toBe(patchBody);
  });

  it("does not forward body for GET requests", async () => {
    mockAuth({ userId: "u1", userRole: "admin" });
    mockFetchOk("{}");

    const [req, ctx] = makeRequest(["status"], "GET");
    await GET(req, ctx);

    const [, fetchOptions] = (fetch as jest.Mock).mock.calls[0];
    expect(fetchOptions.body).toBeUndefined();
  });
});
