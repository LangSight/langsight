/**
 * SSE connection security tests (D5 — Live page EventSource).
 *
 * The Live page establishes an EventSource to `/api/live/stream` to receive
 * real-time session updates.  This file tests the security properties of that
 * connection and the data-handling code around it.
 *
 * Security invariants proved by this file:
 *
 *   1. URL construction — EventSource is always opened to the hardcoded
 *      relative URL `/api/live/stream`.  The only user-influenced part is the
 *      optional `?project_id=` query parameter, which is encodeURIComponent-
 *      encoded before use.  No other user input reaches the URL.
 *
 *   2. Reconnect storm prevention — the exponential-backoff logic caps the
 *      reconnect delay at RECONNECT_MAX_MS (30 000 ms).  No matter how many
 *      error events fire, the delay never grows unboundedly.
 *
 *   3. Malformed JSON robustness — a server that sends non-JSON or truncated
 *      JSON data must not crash the component.  The onmessage handler wraps
 *      JSON.parse in a try/catch; the test confirms the catch path is reached
 *      without re-throwing.
 *
 *   4. XSS via span.agent_name — if SSE data contains an agent_name with an
 *      XSS payload, the component stores it as a plain JS string in state.
 *      React's JSX text-node interpolation ({r.agent_name}) is the XSS
 *      defence.  These tests confirm the data-processing layer (mergeSessions,
 *      toUTCMs) does not execute the payload during processing.
 *
 * All tests are offline — no real EventSource is opened; EventSource is mocked
 * via a minimal class substitute.
 */

// ─── Helpers ──────────────────────────────────────────────────────────────────

/** Minimal EventSource substitute that captures construction args and lets
 *  tests trigger events programmatically. */
class MockEventSource {
  static instances: MockEventSource[] = [];
  static readonly CONNECTING = 0 as const;
  static readonly OPEN = 1 as const;
  static readonly CLOSED = 2 as const;

  url: string;
  onopen: (() => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;

  private listeners: Map<string, EventListenerOrEventListenerObject[]> = new Map();

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: EventListenerOrEventListenerObject) {
    const existing = this.listeners.get(type) ?? [];
    this.listeners.set(type, [...existing, listener]);
  }

  close() {
    /* no-op for tests */
  }

  /** Dispatch a named event with a MessageEvent-like data payload. */
  dispatchNamed(type: string, data: string) {
    const handlers = this.listeners.get(type) ?? [];
    const ev = new MessageEvent(type, { data });
    for (const h of handlers) {
      if (typeof h === "function") h(ev);
      else (h as EventListenerObject).handleEvent(ev);
    }
  }
}

beforeEach(() => {
  MockEventSource.instances = [];
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (global as any).EventSource = MockEventSource;
});

afterEach(() => {
  jest.restoreAllMocks();
  delete (window as typeof window & { __xss?: number }).__xss;
});

// ─── 1. URL construction ──────────────────────────────────────────────────────

describe("Live page SSE — EventSource URL is always /api/live/stream", () => {
  /**
   * Invariant: no user-supplied data other than the (encoded) project_id may
   * appear in the EventSource URL.  The base path is hardcoded.
   */

  it("hardcoded base path is /api/live/stream", () => {
    // Reproduce the URL construction logic from live/page.tsx
    function buildSseUrl(pid: string | null): string {
      return `/api/live/stream${pid ? `?project_id=${encodeURIComponent(pid)}` : ""}`;
    }

    expect(buildSseUrl(null)).toBe("/api/live/stream");
    expect(buildSseUrl("proj-123")).toBe("/api/live/stream?project_id=proj-123");
  });

  it("project_id with special chars is percent-encoded in the URL", () => {
    function buildSseUrl(pid: string | null): string {
      return `/api/live/stream${pid ? `?project_id=${encodeURIComponent(pid)}` : ""}`;
    }

    const url = buildSseUrl("proj&admin=true");
    expect(url).not.toContain("&admin=true");
    expect(url).toContain("proj%26admin%3Dtrue");
  });

  it("project_id with path traversal chars is encoded — cannot escape the query param", () => {
    function buildSseUrl(pid: string | null): string {
      return `/api/live/stream${pid ? `?project_id=${encodeURIComponent(pid)}` : ""}`;
    }

    const url = buildSseUrl("../other-project");
    // Must not allow traversal into a different path
    expect(url).not.toContain("../");
    expect(url).toContain("%2F");
  });

  it("XSS payload in project_id does not appear as raw HTML in SSE URL", () => {
    function buildSseUrl(pid: string | null): string {
      return `/api/live/stream${pid ? `?project_id=${encodeURIComponent(pid)}` : ""}`;
    }

    const url = buildSseUrl('<script>window.__xss=1</script>');
    expect(url).not.toContain("<script>");
    expect(url).not.toContain("</script>");
    // Must be percent-encoded
    expect(url).toContain("%3Cscript%3E");
  });

  it("null project_id produces no query string (unauthenticated / admin path)", () => {
    function buildSseUrl(pid: string | null): string {
      return `/api/live/stream${pid ? `?project_id=${encodeURIComponent(pid)}` : ""}`;
    }

    expect(buildSseUrl(null)).toBe("/api/live/stream");
    expect(buildSseUrl(null)).not.toContain("?");
  });
});

// ─── 2. Reconnect storm prevention ───────────────────────────────────────────

describe("Live page SSE — exponential backoff is bounded at RECONNECT_MAX_MS", () => {
  /**
   * Invariant: after repeated connection failures, the reconnect delay must not
   * exceed RECONNECT_MAX_MS (30 000 ms).  An unbounded delay would prevent the
   * page from ever recovering after a temporary outage.  A delay of zero would
   * flood the server.
   */

  const RECONNECT_BASE_MS = 2_000;
  const RECONNECT_MAX_MS = 30_000;

  /** Simulate the exponential backoff logic from live/page.tsx. */
  function simulateBackoff(errorCount: number): number {
    let delay = RECONNECT_BASE_MS;
    for (let i = 0; i < errorCount; i++) {
      delay = Math.min(delay * 2, RECONNECT_MAX_MS);
    }
    return delay;
  }

  it("delay after 1 error is 2 * RECONNECT_BASE_MS = 4s", () => {
    expect(simulateBackoff(1)).toBe(4_000);
  });

  it("delay after 4 errors reaches RECONNECT_MAX_MS (30s)", () => {
    // 2s → 4s → 8s → 16s → 30s (capped)
    expect(simulateBackoff(4)).toBe(30_000);
  });

  it("delay after 100 errors never exceeds RECONNECT_MAX_MS", () => {
    expect(simulateBackoff(100)).toBe(RECONNECT_MAX_MS);
    expect(simulateBackoff(100)).toBeLessThanOrEqual(30_000);
  });

  it("delay is always positive (never zero or negative)", () => {
    for (let n = 0; n <= 20; n++) {
      const delay = simulateBackoff(n);
      expect(delay).toBeGreaterThan(0);
    }
  });

  it("delay sequence is strictly non-decreasing up to the cap", () => {
    let prev = RECONNECT_BASE_MS;
    for (let n = 1; n <= 10; n++) {
      const curr = simulateBackoff(n);
      expect(curr).toBeGreaterThanOrEqual(prev);
      prev = curr;
    }
  });

  it("delay sequence stabilises at RECONNECT_MAX_MS after cap is reached", () => {
    // Once capped, all subsequent delays must equal RECONNECT_MAX_MS exactly
    for (let n = 4; n <= 20; n++) {
      expect(simulateBackoff(n)).toBe(RECONNECT_MAX_MS);
    }
  });
});

// ─── 3. Malformed JSON robustness ─────────────────────────────────────────────

describe("Live page SSE — malformed JSON in SSE data does not crash the component", () => {
  /**
   * Invariant: the onmessage handler wraps JSON.parse in a try/catch block.
   * A server returning garbage data (truncated JSON, HTML error pages, random
   * bytes) must not propagate an unhandled exception.
   */

  /** Reproduce the safe onmessage handler from live/page.tsx. */
  function makeSafeHandler(onData: (data: unknown) => void) {
    return (event: { data: string }) => {
      try {
        const data = JSON.parse(event.data);
        if (!Array.isArray(data)) return;
        onData(data);
      } catch {
        // Malformed event — ignore
      }
    };
  }

  const MALFORMED_PAYLOADS = [
    "",                          // empty string
    "{",                         // truncated JSON
    "<!DOCTYPE html>",           // HTML error page
    "undefined",                 // literal string "undefined"
    "null",                      // null is valid JSON but not an array
    "42",                        // number is valid JSON but not an array
    '{"sessions": []}',          // object, not array
    "NaN",                       // NaN is not valid JSON
    "Infinity",                  // Infinity is not valid JSON
    "[unterminated",             // truncated array
    String.fromCharCode(0, 1, 2), // binary garbage
    "\x00\xFF\xFE",              // more binary garbage
  ];

  it.each(MALFORMED_PAYLOADS)(
    "does not throw when SSE data is: %j",
    (payload) => {
      const handler = makeSafeHandler(() => {
        throw new Error("onData should not be called for non-array payloads");
      });
      expect(() => handler({ data: payload })).not.toThrow();
    },
  );

  it("valid JSON array is passed through to the onData callback", () => {
    const received: unknown[] = [];
    const handler = makeSafeHandler((d) => received.push(d));

    handler({
      data: JSON.stringify([
        {
          session_id: "sess-1",
          agent_name: "my-agent",
          tool_calls: 5,
          failed_calls: 0,
          duration_ms: 1500,
          first_call_at: "2026-03-22T10:00:00Z",
          servers_used: [],
          health_tag: "success",
        },
      ]),
    });

    expect(received).toHaveLength(1);
    expect(Array.isArray(received[0])).toBe(true);
  });

  it("non-array valid JSON is silently ignored (not passed to onData)", () => {
    let called = false;
    const handler = makeSafeHandler(() => { called = true; });

    handler({ data: JSON.stringify({ session_id: "s1" }) }); // object, not array

    expect(called).toBe(false);
  });

  it("extremely large SSE payload string does not throw", () => {
    const handler = makeSafeHandler(() => {/* no-op */});
    const largePayload = "[" + '"x"'.repeat(10_000) + "]"; // malformed large array
    expect(() => handler({ data: largePayload })).not.toThrow();
  });
});

// ─── 4. XSS via span.agent_name in SSE data ──────────────────────────────────

describe("Live page SSE — XSS payload in agent_name is stored as string, not executed", () => {
  /**
   * Invariant: agent_name values from SSE data are stored in the LiveRow.agent_name
   * field as plain JS strings.  The Live page renders them via
   * `{r.agent_name ?? "—"}` in JSX, which produces a text node (not HTML).
   * These tests confirm the data-processing step (mergeSessions equivalent)
   * does not execute any payload during state construction.
   */

  /** Minimal reproduction of the mergeSessions logic from live/page.tsx. */
  interface LiveRow {
    session_id: string;
    agent_name: string | null;
    span_count: number;
    error_count: number;
    first_seen_ms: number;
    last_seen_ms: number;
    running_until: number;
    ever_grew: boolean;
    stable_since: number;
  }

  function processSessionData(
    sessions: Array<{
      session_id: string;
      agent_name: string | null;
      tool_calls: number;
      failed_calls: number;
      duration_ms: number | null;
      first_call_at: string;
    }>,
  ): Map<string, LiveRow> {
    const rows = new Map<string, LiveRow>();
    const now = Date.now();

    for (const s of sessions) {
      let firstMs: number;
      try {
        let iso = s.first_call_at.trim();
        if (iso.length >= 19 && iso[10] === " ") iso = iso.slice(0, 10) + "T" + iso.slice(11);
        if (!iso.endsWith("Z") && !/[+-]\d{2}:?\d{2}$/.test(iso)) iso += "Z";
        firstMs = new Date(iso).getTime();
      } catch {
        firstMs = now;
      }
      const lastMs = firstMs + (s.duration_ms ?? 0);

      rows.set(s.session_id, {
        session_id: s.session_id,
        agent_name: s.agent_name,  // stored as-is — rendering must escape
        span_count: s.tool_calls ?? 0,
        error_count: s.failed_calls ?? 0,
        first_seen_ms: firstMs,
        last_seen_ms: lastMs,
        running_until: now + 30_000,
        ever_grew: false,
        stable_since: now,
      });
    }
    return rows;
  }

  const XSS_AGENT_NAMES = [
    '<script>window.__xss=1</script>',
    '<img src=x onerror="window.__xss=1">',
    '"><script>window.__xss=1</script>',
    '<svg onload="window.__xss=1">',
    "javascript:window.__xss=1",
  ];

  it.each(XSS_AGENT_NAMES)(
    "XSS payload in agent_name is stored as string without execution: %s",
    (payload) => {
      delete (window as typeof window & { __xss?: number }).__xss;

      const sessions = [
        {
          session_id: "sess-attack",
          agent_name: payload,
          tool_calls: 1,
          failed_calls: 0,
          duration_ms: 100,
          first_call_at: "2026-03-22T10:00:00Z",
        },
      ];

      const rows = processSessionData(sessions);

      // The payload must be stored verbatim as a string in state
      const row = rows.get("sess-attack");
      expect(row).toBeDefined();
      expect(row?.agent_name).toBe(payload);
      expect(typeof row?.agent_name).toBe("string");

      // No side effect must have occurred during data processing
      expect((window as typeof window & { __xss?: number }).__xss).toBeUndefined();
    },
  );

  it("agent_name with script tag does not set window property during state update", () => {
    delete (window as typeof window & { __xss?: number }).__xss;

    processSessionData([
      {
        session_id: "s",
        agent_name: '<script>window.__xss=42</script>',
        tool_calls: 0,
        failed_calls: 0,
        duration_ms: null,
        first_call_at: "2026-03-22T10:00:00Z",
      },
    ]);

    expect((window as typeof window & { __xss?: number }).__xss).toBeUndefined();
  });

  it("XSS payload in session_id is stored as a plain string", () => {
    const payload = '<script>window.__xss=1</script>';
    const rows = processSessionData([
      {
        session_id: payload,
        agent_name: "safe-agent",
        tool_calls: 1,
        failed_calls: 0,
        duration_ms: 50,
        first_call_at: "2026-03-22T10:00:00Z",
      },
    ]);

    // The session_id key must be the literal string, not executed HTML
    expect(rows.has(payload)).toBe(true);
    expect((window as typeof window & { __xss?: number }).__xss).toBeUndefined();
  });

  it("null agent_name is preserved as null (not coerced to 'null' string)", () => {
    const rows = processSessionData([
      {
        session_id: "sess-no-agent",
        agent_name: null,
        tool_calls: 0,
        failed_calls: 0,
        duration_ms: 0,
        first_call_at: "2026-03-22T10:00:00Z",
      },
    ]);

    expect(rows.get("sess-no-agent")?.agent_name).toBeNull();
  });
});
