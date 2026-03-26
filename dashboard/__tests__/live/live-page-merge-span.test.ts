/**
 * Tests for the Live page's mergeSpan function and SSE span:new contract.
 *
 * These tests lock the contract between the backend's span:new SSE event
 * and the frontend's incremental session row update logic.
 *
 * Regression guard for:
 *   - Bug 1: onmessage / sessions listener silently dropped all events
 *     because backend sends span:new (single object), not AgentSession[] arrays
 *   - Bug 3: started_at was absent from span:new, so timestamps showed wrong values
 */

import { mergeSpan, type SpanEvent } from "../../lib/live-utils";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeSpan(overrides: Partial<SpanEvent> = {}): SpanEvent {
  return {
    project_id:  "proj-1",
    session_id:  "sess-abc",
    agent_name:  "test-agent",
    server_name: "postgres-mcp",
    tool_name:   "query",
    status:      "success",
    latency_ms:  42,
    started_at:  "2026-03-26T10:00:00Z",
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Basic row creation
// ---------------------------------------------------------------------------

describe("mergeSpan — creates a new row on first span for a session", () => {
  it("adds a new session row when session_id is unseen", () => {
    const prev = new Map();
    const next = mergeSpan(prev, makeSpan());
    expect(next.has("sess-abc")).toBe(true);
  });

  it("span_count starts at 1 for first span", () => {
    const next = mergeSpan(new Map(), makeSpan());
    expect(next.get("sess-abc")?.span_count).toBe(1);
  });

  it("error_count is 0 for a success span", () => {
    const next = mergeSpan(new Map(), makeSpan({ status: "success" }));
    expect(next.get("sess-abc")?.error_count).toBe(0);
  });

  it("error_count is 1 for an error span", () => {
    const next = mergeSpan(new Map(), makeSpan({ status: "error" }));
    expect(next.get("sess-abc")?.error_count).toBe(1);
  });

  it("first_seen_ms is set from started_at on first span", () => {
    const next = mergeSpan(new Map(), makeSpan({ started_at: "2026-03-26T10:00:00Z" }));
    const row = next.get("sess-abc");
    expect(row?.first_seen_ms).toBeGreaterThan(0);
    expect(row?.first_seen_ms).toBe(new Date("2026-03-26T10:00:00Z").getTime());
  });

  it("last_seen_ms is set from started_at", () => {
    const next = mergeSpan(new Map(), makeSpan({ started_at: "2026-03-26T10:00:05Z" }));
    expect(next.get("sess-abc")?.last_seen_ms).toBe(
      new Date("2026-03-26T10:00:05Z").getTime()
    );
  });

  it("agent_name is stored from span payload", () => {
    const next = mergeSpan(new Map(), makeSpan({ agent_name: "my-agent" }));
    expect(next.get("sess-abc")?.agent_name).toBe("my-agent");
  });

  it("null agent_name is stored as null", () => {
    const next = mergeSpan(new Map(), makeSpan({ agent_name: null }));
    expect(next.get("sess-abc")?.agent_name).toBeNull();
  });

  it("running_until is set to the future", () => {
    const before = Date.now();
    const next = mergeSpan(new Map(), makeSpan());
    const row = next.get("sess-abc")!;
    expect(row.running_until).toBeGreaterThan(before);
  });

  it("ever_grew is true on first span", () => {
    const next = mergeSpan(new Map(), makeSpan());
    expect(next.get("sess-abc")?.ever_grew).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Incremental update on subsequent spans
// ---------------------------------------------------------------------------

describe("mergeSpan — increments counters on each new span", () => {
  it("span_count increments by 1 per span", () => {
    let rows = new Map();
    rows = mergeSpan(rows, makeSpan());
    rows = mergeSpan(rows, makeSpan());
    rows = mergeSpan(rows, makeSpan());
    expect(rows.get("sess-abc")?.span_count).toBe(3);
  });

  it("error_count accumulates across spans", () => {
    let rows = new Map();
    rows = mergeSpan(rows, makeSpan({ status: "success" }));
    rows = mergeSpan(rows, makeSpan({ status: "error" }));
    rows = mergeSpan(rows, makeSpan({ status: "timeout" }));
    rows = mergeSpan(rows, makeSpan({ status: "success" }));
    expect(rows.get("sess-abc")?.error_count).toBe(2);
  });

  it("first_seen_ms does not change on subsequent spans", () => {
    let rows = new Map();
    rows = mergeSpan(rows, makeSpan({ started_at: "2026-03-26T10:00:00Z" }));
    const firstSeen = rows.get("sess-abc")!.first_seen_ms;
    rows = mergeSpan(rows, makeSpan({ started_at: "2026-03-26T10:00:05Z" }));
    expect(rows.get("sess-abc")?.first_seen_ms).toBe(firstSeen);
  });

  it("last_seen_ms updates to the latest span timestamp", () => {
    let rows = new Map();
    rows = mergeSpan(rows, makeSpan({ started_at: "2026-03-26T10:00:00Z" }));
    rows = mergeSpan(rows, makeSpan({ started_at: "2026-03-26T10:00:05Z" }));
    expect(rows.get("sess-abc")?.last_seen_ms).toBe(
      new Date("2026-03-26T10:00:05Z").getTime()
    );
  });

  it("agent_name from later span fills in if earlier was null", () => {
    let rows = new Map();
    rows = mergeSpan(rows, makeSpan({ agent_name: null }));
    rows = mergeSpan(rows, makeSpan({ agent_name: "late-agent" }));
    expect(rows.get("sess-abc")?.agent_name).toBe("late-agent");
  });
});

// ---------------------------------------------------------------------------
// Multiple independent sessions
// ---------------------------------------------------------------------------

describe("mergeSpan — handles multiple sessions independently", () => {
  it("spans for different sessions create separate rows", () => {
    let rows = new Map();
    rows = mergeSpan(rows, makeSpan({ session_id: "sess-1" }));
    rows = mergeSpan(rows, makeSpan({ session_id: "sess-2" }));
    expect(rows.size).toBe(2);
    expect(rows.has("sess-1")).toBe(true);
    expect(rows.has("sess-2")).toBe(true);
  });

  it("span counts are independent per session", () => {
    let rows = new Map();
    rows = mergeSpan(rows, makeSpan({ session_id: "sess-1" }));
    rows = mergeSpan(rows, makeSpan({ session_id: "sess-1" }));
    rows = mergeSpan(rows, makeSpan({ session_id: "sess-2" }));
    expect(rows.get("sess-1")?.span_count).toBe(2);
    expect(rows.get("sess-2")?.span_count).toBe(1);
  });
});

// ---------------------------------------------------------------------------
// Safety: invalid or missing session_id
// ---------------------------------------------------------------------------

describe("mergeSpan — handles invalid input gracefully", () => {
  it("returns unchanged map when session_id is empty string", () => {
    const prev = new Map();
    const next = mergeSpan(prev, makeSpan({ session_id: "" }));
    expect(next.size).toBe(0);
  });

  it("does not throw on null started_at — falls back to now", () => {
    expect(() =>
      mergeSpan(new Map(), makeSpan({ started_at: null }))
    ).not.toThrow();
  });

  it("does not throw on malformed started_at", () => {
    expect(() =>
      mergeSpan(new Map(), makeSpan({ started_at: "not-a-date" }))
    ).not.toThrow();
  });
});

// ---------------------------------------------------------------------------
// SSE contract: span:new is a single object, not an array
// ---------------------------------------------------------------------------

describe("span:new SSE contract — backend sends a single object, not AgentSession[]", () => {
  it("mergeSpan accepts a plain object, not an array", () => {
    // This test documents and guards the fundamental contract fix:
    // Before the fix, the frontend did: if (!Array.isArray(data)) return;
    // which silently dropped every span:new event.
    const span = makeSpan();
    expect(Array.isArray(span)).toBe(false);  // span:new is NOT an array
    expect(() => mergeSpan(new Map(), span)).not.toThrow();
    const result = mergeSpan(new Map(), span);
    expect(result.size).toBeGreaterThan(0);   // row was actually created
  });

  it("started_at is present in SpanEvent type (Bug 3 guard)", () => {
    // If started_at is removed from SpanEvent, this type-check fails at compile time.
    const span: SpanEvent = makeSpan();
    expect("started_at" in span).toBe(true);
  });
});
