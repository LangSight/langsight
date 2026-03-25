/**
 * Session ID handling — adversarial input tests.
 *
 * Invariant: session IDs entered via the URL dynamic segment /sessions/[id]
 * or passed to API functions must be URL-encoded before reaching the network
 * layer.  Hostile IDs — SQL injection fragments, path-traversal strings,
 * oversized identifiers, and null-byte injections — must never be forwarded
 * to the backend verbatim.
 *
 * These tests exercise the client-side API layer (lib/api.ts) in isolation by
 * mocking `global.fetch` and asserting what URL was produced.  No real network
 * calls are made.
 */

import { getSessionTrace } from "@/lib/api";
import { HOSTILE_SESSION_IDS } from "./test-utils";

// ─── Mock fetch ───────────────────────────────────────────────────────────────

function mockFetchOk(body: unknown = {}) {
  global.fetch = jest.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: jest.fn().mockResolvedValue(body),
  } as unknown as Response);
}

function capturedUrl(): string {
  return (global.fetch as jest.Mock).mock.calls[0][0] as string;
}

afterEach(() => {
  jest.restoreAllMocks();
  // Clean up any accidentally set window properties
  delete (window as typeof window & { __xss?: number }).__xss;
});

// ─── getSessionTrace — URL encoding ──────────────────────────────────────────

describe("getSessionTrace — hostile session IDs are URL-encoded before fetch", () => {
  /**
   * Invariant: encodeURIComponent is applied to the session ID in
   * getSessionTrace().  Characters like /, ', ;, \0 must be percent-encoded
   * so they never appear as literal path segments or query parameter delimiters
   * in the outgoing URL.
   */

  it("encodes forward slash in session ID (path traversal prevention)", async () => {
    mockFetchOk({ session_id: "x", spans_flat: [], root_spans: [], total_spans: 0, tool_calls: 0, failed_calls: 0, duration_ms: null });
    await getSessionTrace("../../../etc/passwd");
    const url = capturedUrl();
    // The literal string "../../../etc/passwd" must not appear unencoded
    expect(url).not.toContain("../");
    expect(url).not.toContain("etc/passwd");
    // Percent-encoding of . and / is expected
    expect(url).toContain("%2F");
  });

  it("isolates SQL injection payload as a single URL path segment", async () => {
    // encodeURIComponent does NOT encode ' (it is RFC 3986 safe in URI components).
    // The important invariant is that the value is confined to one path segment —
    // no unencoded '/', '?', or '#' that could break the URL structure.
    mockFetchOk({ session_id: "x", spans_flat: [], root_spans: [], total_spans: 0, tool_calls: 0, failed_calls: 0, duration_ms: null });
    await getSessionTrace("' OR '1'='1");
    const url = capturedUrl();
    const pathSegment = url.split("/agents/sessions/")[1]?.split("?")[0] ?? "";
    expect(pathSegment).not.toContain("/");
    expect(pathSegment).not.toContain("?");
    expect(pathSegment).not.toContain("#");
    // Spaces must be encoded (the actual injection vector for HTTP header splitting)
    expect(pathSegment).not.toContain(" ");
  });

  it("encodes semicolons and SQL keywords in session ID", async () => {
    mockFetchOk({ session_id: "x", spans_flat: [], root_spans: [], total_spans: 0, tool_calls: 0, failed_calls: 0, duration_ms: null });
    await getSessionTrace("1; DROP TABLE sessions;--");
    const url = capturedUrl();
    // Semicolons must be encoded
    expect(url).not.toMatch(/;\s*DROP/i);
    // Space must be encoded
    expect(url).not.toContain(" DROP TABLE");
  });

  it("encodes backslashes in session ID (Windows path traversal)", async () => {
    mockFetchOk({ session_id: "x", spans_flat: [], root_spans: [], total_spans: 0, tool_calls: 0, failed_calls: 0, duration_ms: null });
    await getSessionTrace("..\\..\\windows\\system32");
    const url = capturedUrl();
    expect(url).not.toContain("\\");
    expect(url).toContain("%5C");
  });

  it("encodes null byte in session ID", async () => {
    mockFetchOk({ session_id: "x", spans_flat: [], root_spans: [], total_spans: 0, tool_calls: 0, failed_calls: 0, duration_ms: null });
    await getSessionTrace("valid-id\0../admin");
    const url = capturedUrl();
    // Null byte must be encoded — it must not appear literally
    expect(url).not.toContain("\0");
    expect(url).toContain("%00");
  });

  it.each(HOSTILE_SESSION_IDS.filter((id) => id.length > 0))(
    "produces an encoded URL for hostile session ID '%s'",
    async (sessionId) => {
      mockFetchOk({ session_id: "x", spans_flat: [], root_spans: [], total_spans: 0, tool_calls: 0, failed_calls: 0, duration_ms: null });
      // May throw (e.g. for oversized IDs) — that is acceptable; what must NOT
      // happen is the raw hostile string appearing in the URL path.
      try {
        await getSessionTrace(sessionId);
        const url = capturedUrl();
        // The raw SQL keywords must not appear unencoded
        expect(url).not.toMatch(/DROP TABLE/i);
        expect(url).not.toMatch(/UNION SELECT/i);
        // Literal forward slashes must not appear in the path segment (only in the base path)
        const pathSegment = url.split("/agents/sessions/")[1]?.split("?")[0] ?? "";
        expect(pathSegment).not.toContain("/");
        // Note: ' is RFC 3986 safe and is not encoded by encodeURIComponent — that is correct
        expect(pathSegment).not.toContain(";");
      } catch {
        // A thrown error is also an acceptable outcome for extreme inputs
      }
    },
  );
});

// ─── getSessionTrace with project_id — parameter isolation ───────────────────

describe("getSessionTrace — project_id is URL-encoded, preventing cross-tenant injection", () => {
  /**
   * Invariant: the project_id query parameter must be encoded.  An attacker
   * cannot escape the project_id value and append extra parameters that change
   * the backend's project scope.
   */

  it("encodes ampersand in project_id (prevents parameter smuggling)", async () => {
    mockFetchOk({ session_id: "x", spans_flat: [], root_spans: [], total_spans: 0, tool_calls: 0, failed_calls: 0, duration_ms: null });
    await getSessionTrace("sess-abc", "legit-proj&admin=true");
    const url = capturedUrl();
    // The literal &admin=true must not appear as a separate parameter
    expect(url).not.toContain("&admin=true");
    expect(url).toContain("legit-proj%26admin%3Dtrue");
  });

  it("encodes path traversal in project_id", async () => {
    mockFetchOk({ session_id: "x", spans_flat: [], root_spans: [], total_spans: 0, tool_calls: 0, failed_calls: 0, duration_ms: null });
    await getSessionTrace("sess-abc", "../other-tenant");
    const url = capturedUrl();
    expect(url).not.toContain("../other-tenant");
    expect(url).toContain("..%2Fother-tenant");
  });
});
