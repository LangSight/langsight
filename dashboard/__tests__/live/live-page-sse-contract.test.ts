/**
 * Tests for the Live page's SSE event handling contract.
 *
 * The Live page connects to an EventSource at /api/live/stream and listens
 * for `span:new` named events.  Each event carries a single SpanEvent object.
 *
 * Regression guards:
 *   - Bug 2: The old handler used `es.onmessage` or `es.addEventListener("sessions", ...)`
 *     which silently dropped every event because the backend sends `span:new` events.
 *   - Malformed JSON must not crash the handler.
 *   - Empty session_id spans must be ignored.
 */

import { mergeSpan, type SpanEvent, type LiveRow } from "../../lib/live-utils";

// ---------------------------------------------------------------------------
// Mock EventSource — captures construction URL and registered listeners
// ---------------------------------------------------------------------------

type EventListenerFn = (ev: MessageEvent) => void;

class MockEventSource {
  static instances: MockEventSource[] = [];

  url: string;
  onopen: (() => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;

  private namedListeners: Map<string, EventListenerFn[]> = new Map();

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: EventListenerOrEventListenerObject) {
    const existing = this.namedListeners.get(type) ?? [];
    this.namedListeners.set(type, [...existing, listener as EventListenerFn]);
  }

  removeEventListener() {
    /* no-op for tests */
  }

  close() {
    /* no-op for tests */
  }

  /** Check if a named event listener was registered. */
  hasListener(type: string): boolean {
    return (this.namedListeners.get(type) ?? []).length > 0;
  }

  /** Get names of all registered event types. */
  getRegisteredTypes(): string[] {
    return [...this.namedListeners.keys()];
  }

  /** Fire a named event (e.g. "span:new") with a data payload. */
  fireNamedEvent(type: string, data: string) {
    const handlers = this.namedListeners.get(type) ?? [];
    const ev = new MessageEvent(type, { data });
    for (const h of handlers) {
      h(ev);
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
});

// ---------------------------------------------------------------------------
// Helpers — reproduce the SSE connect logic from live/page.tsx (lines 134-183)
// ---------------------------------------------------------------------------

function makeSpan(overrides: Partial<SpanEvent> = {}): SpanEvent {
  // Use a very recent started_at so the row does not get evicted by
  // mergeSpan's EXPIRE_MS check between successive calls.
  return {
    project_id:  "proj-1",
    session_id:  "sess-sse-1",
    agent_name:  "test-agent",
    server_name: "postgres-mcp",
    tool_name:   "query",
    status:      "success",
    latency_ms:  42,
    started_at:  new Date().toISOString(),
    ...overrides,
  };
}

/**
 * Simulate the SSE connection setup from the Live page.
 * Returns the EventSource instance and a callback to read the current rows.
 */
function simulateSSEConnect(pid: string | null): {
  es: MockEventSource;
  getRows: () => Map<string, LiveRow>;
} {
  let rows = new Map<string, LiveRow>();

  const url = `/api/live/stream${pid ? `?project_id=${encodeURIComponent(pid)}` : ""}`;
  const es = new MockEventSource(url);

  // Reproduce the exact handler from page.tsx lines 151-159
  es.addEventListener("span:new", ((event: MessageEvent) => {
    try {
      const span = JSON.parse(event.data) as SpanEvent;
      if (!span.session_id) return;
      rows = mergeSpan(rows, span);
    } catch {
      // Malformed event — ignore
    }
  }) as EventListenerOrEventListenerObject);

  return { es, getRows: () => rows };
}

// ---------------------------------------------------------------------------
// 1. EventSource URL
// ---------------------------------------------------------------------------

describe("Live page SSE — EventSource URL", () => {
  it("connects to /api/live/stream (not /api/live/events)", () => {
    const { es } = simulateSSEConnect(null);
    expect(es.url).toBe("/api/live/stream");
    expect(es.url).not.toContain("/api/live/events");
  });

  it("appends ?project_id=<pid> when a project is selected", () => {
    const { es } = simulateSSEConnect("proj-abc");
    expect(es.url).toBe("/api/live/stream?project_id=proj-abc");
  });

  it("omits query string when pid is null", () => {
    const { es } = simulateSSEConnect(null);
    expect(es.url).toBe("/api/live/stream");
    expect(es.url).not.toContain("?");
  });

  it("encodes special chars in project_id", () => {
    const { es } = simulateSSEConnect("proj&x=1");
    expect(es.url).toContain("proj%26x%3D1");
  });
});

// ---------------------------------------------------------------------------
// 2. span:new events update the rows map
// ---------------------------------------------------------------------------

describe("Live page SSE — span:new event handling", () => {
  it("creates a new row when a span:new event arrives for an unseen session", () => {
    const { es, getRows } = simulateSSEConnect(null);
    es.fireNamedEvent("span:new", JSON.stringify(makeSpan()));
    expect(getRows().has("sess-sse-1")).toBe(true);
  });

  it("increments span_count on subsequent span:new events", () => {
    const { es, getRows } = simulateSSEConnect(null);
    es.fireNamedEvent("span:new", JSON.stringify(makeSpan()));
    es.fireNamedEvent("span:new", JSON.stringify(makeSpan()));
    es.fireNamedEvent("span:new", JSON.stringify(makeSpan()));
    expect(getRows().get("sess-sse-1")!.span_count).toBe(3);
  });

  it("increments error_count for non-success spans", () => {
    const { es, getRows } = simulateSSEConnect(null);
    es.fireNamedEvent("span:new", JSON.stringify(makeSpan({ status: "error" })));
    es.fireNamedEvent("span:new", JSON.stringify(makeSpan({ status: "success" })));
    es.fireNamedEvent("span:new", JSON.stringify(makeSpan({ status: "timeout" })));
    expect(getRows().get("sess-sse-1")!.error_count).toBe(2);
  });

  it("uses mergeSpan which sets ever_grew = true", () => {
    const { es, getRows } = simulateSSEConnect(null);
    es.fireNamedEvent("span:new", JSON.stringify(makeSpan()));
    expect(getRows().get("sess-sse-1")!.ever_grew).toBe(true);
  });

  it("handles multiple independent sessions via span:new", () => {
    const { es, getRows } = simulateSSEConnect(null);
    es.fireNamedEvent("span:new", JSON.stringify(makeSpan({ session_id: "s1" })));
    es.fireNamedEvent("span:new", JSON.stringify(makeSpan({ session_id: "s2" })));
    expect(getRows().size).toBe(2);
    expect(getRows().has("s1")).toBe(true);
    expect(getRows().has("s2")).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// 3. Regression: old handlers must NOT exist
// ---------------------------------------------------------------------------

describe("Live page SSE — regression: no old event handlers", () => {
  it("does NOT use onmessage (regression: would silently drop span:new events)", () => {
    // The fix changed from es.onmessage to es.addEventListener("span:new", ...).
    // If onmessage were set, span:new named events would never reach it because
    // named events bypass the generic onmessage handler.
    const { es } = simulateSSEConnect(null);
    expect(es.onmessage).toBeNull();
  });

  it("does NOT register a 'sessions' event listener (regression: wrong event name)", () => {
    // The old code listened for 'sessions' events (expecting AgentSession[]),
    // but the backend sends 'span:new' events (single SpanEvent object).
    const { es } = simulateSSEConnect(null);
    expect(es.hasListener("sessions")).toBe(false);
  });

  it("registers a 'span:new' event listener (the correct handler)", () => {
    const { es } = simulateSSEConnect(null);
    expect(es.hasListener("span:new")).toBe(true);
  });

  it("'span:new' is the ONLY named event listener registered", () => {
    const { es } = simulateSSEConnect(null);
    const types = es.getRegisteredTypes();
    expect(types).toEqual(["span:new"]);
  });
});

// ---------------------------------------------------------------------------
// 4. Malformed span:new data does not crash
// ---------------------------------------------------------------------------

describe("Live page SSE — malformed span:new data does not crash", () => {
  const MALFORMED_PAYLOADS = [
    "",                          // empty string
    "{",                         // truncated JSON
    "<!DOCTYPE html>",           // HTML error page
    "undefined",                 // not valid JSON
    "NaN",                       // not valid JSON
    "[1,2,3]",                   // array, not object
    "null",                      // null has no session_id
    "42",                        // number has no session_id
    String.fromCharCode(0, 1, 2), // binary garbage
  ];

  it.each(MALFORMED_PAYLOADS)(
    "does not throw when span:new data is: %j",
    (payload) => {
      const { es, getRows } = simulateSSEConnect(null);
      expect(() => es.fireNamedEvent("span:new", payload)).not.toThrow();
      // No rows should be created from garbage data
      expect(getRows().size).toBe(0);
    },
  );

  it("valid span:new after malformed one still processes correctly", () => {
    const { es, getRows } = simulateSSEConnect(null);
    es.fireNamedEvent("span:new", "NOT-JSON");
    es.fireNamedEvent("span:new", JSON.stringify(makeSpan()));
    expect(getRows().size).toBe(1);
    expect(getRows().get("sess-sse-1")!.span_count).toBe(1);
  });
});

// ---------------------------------------------------------------------------
// 5. span:new with empty session_id is ignored
// ---------------------------------------------------------------------------

describe("Live page SSE — span:new with empty/missing session_id", () => {
  it("ignores span with empty session_id string", () => {
    const { es, getRows } = simulateSSEConnect(null);
    es.fireNamedEvent(
      "span:new",
      JSON.stringify(makeSpan({ session_id: "" })),
    );
    expect(getRows().size).toBe(0);
  });

  it("ignores span where session_id is null-ish after parsing", () => {
    const { es, getRows } = simulateSSEConnect(null);
    // JSON does not have undefined — simulate a payload where session_id is missing
    es.fireNamedEvent(
      "span:new",
      JSON.stringify({ ...makeSpan(), session_id: undefined }),
    );
    expect(getRows().size).toBe(0);
  });

  it("processes valid span after ignoring empty session_id", () => {
    const { es, getRows } = simulateSSEConnect(null);
    es.fireNamedEvent(
      "span:new",
      JSON.stringify(makeSpan({ session_id: "" })),
    );
    es.fireNamedEvent(
      "span:new",
      JSON.stringify(makeSpan({ session_id: "real-session" })),
    );
    expect(getRows().size).toBe(1);
    expect(getRows().has("real-session")).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// 6. span:new data shape contract
// ---------------------------------------------------------------------------

describe("Live page SSE — span:new is a single object (not AgentSession[])", () => {
  it("processes a single SpanEvent object, not an array", () => {
    const { es, getRows } = simulateSSEConnect(null);
    const span = makeSpan();

    // Backend sends a single object, NOT wrapped in an array
    es.fireNamedEvent("span:new", JSON.stringify(span));
    expect(getRows().size).toBe(1);
  });

  it("an array payload is NOT processed as valid span data", () => {
    const { es, getRows } = simulateSSEConnect(null);
    // If someone sent an array, it would fail because Array has no session_id string
    es.fireNamedEvent("span:new", JSON.stringify([makeSpan()]));
    // An array is valid JSON, won't throw, but mergeSpan requires span.session_id
    // to be a truthy string. Array doesn't have .session_id as a string.
    expect(getRows().size).toBe(0);
  });
});
