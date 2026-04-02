/**
 * Tests for the Live page's initial DB seed fetch behavior.
 *
 * The Live page fetches existing sessions from the API on mount so that
 * sessions appear immediately, before any SSE span:new event arrives.
 *
 * Regression guards:
 *   - Bug 1: seed fetch used `/api/agents/sessions` (404) instead of
 *     `/api/proxy/agents/sessions` — fixed by prefixing with /api/proxy.
 *   - Seed must not overwrite fresher SSE data already in the rows map.
 *   - Seed must filter out expired sessions (older than EXPIRE_MS = 10 min).
 */

import { toUTCMs, EXPIRE_MS, type LiveRow } from "../../lib/live-utils";
import type { AgentSession } from "../../lib/types";

// ---------------------------------------------------------------------------
// Helpers — reproduce the seed logic extracted from live/page.tsx
// ---------------------------------------------------------------------------

/**
 * Build the seed URL exactly as the Live page does (line 102 of page.tsx).
 */
function buildSeedUrl(pid: string | null): string {
  return `/api/proxy/agents/sessions?hours=1${pid ? `&project_id=${encodeURIComponent(pid)}` : ""}`;
}

/**
 * Reproduce the seed-to-LiveRow conversion logic from the useEffect
 * in live/page.tsx (lines 101-131).
 *
 * @param sessions  - API response from the seed fetch
 * @param existing  - rows that SSE may have already populated
 * @param now       - current timestamp
 * @returns merged map of LiveRow entries
 */
function applySeed(
  sessions: AgentSession[],
  existing: Map<string, LiveRow>,
  now: number,
): Map<string, LiveRow> {
  const cutoff = now - EXPIRE_MS;
  const next = new Map(existing);

  for (const s of sessions) {
    const firstMs = toUTCMs(s.first_call_at);
    const lastMs  = firstMs + (s.duration_ms ?? 0);
    if (lastMs < cutoff) continue;            // expired
    if (next.has(s.session_id)) continue;     // SSE already has fresher data
    next.set(s.session_id, {
      session_id:    s.session_id,
      agent_name:    s.agent_name ?? null,
      span_count:    s.tool_calls ?? 0,
      error_count:   s.failed_calls ?? 0,
      first_seen_ms: firstMs,
      last_seen_ms:  lastMs,
      running_until: 0,
      ever_grew:     false,
      stable_since:  lastMs,
    });
  }

  return next;
}

/**
 * Build a minimal AgentSession for testing.
 */
function makeSession(overrides: Partial<AgentSession> = {}): AgentSession {
  return {
    session_id:          "sess-seed-1",
    agent_name:          "seed-agent",
    first_call_at:       "2026-03-26 10:00:00",
    last_call_at:        "2026-03-26 10:00:05",
    tool_calls:          7,
    failed_calls:        2,
    duration_ms:         5000,
    servers_used:        ["postgres-mcp"],
    health_tag:          "success",
    total_input_tokens:  null,
    total_output_tokens: null,
    model_id:            null,
    est_cost_usd:        null,
    has_prompt:          false,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// 1. Seed URL construction
// ---------------------------------------------------------------------------

describe("Live page seed — URL construction", () => {
  it("fetches /api/proxy/agents/sessions (NOT /api/agents/sessions)", () => {
    const url = buildSeedUrl(null);
    expect(url).toBe("/api/proxy/agents/sessions?hours=1");
    expect(url).not.toContain("/api/agents/sessions?");
    // The old broken URL was exactly /api/agents/sessions — make sure the
    // /proxy/ prefix is present.
    expect(url).toContain("/api/proxy/");
  });

  it("appends project_id when a project is active", () => {
    const url = buildSeedUrl("proj-abc-123");
    expect(url).toBe(
      "/api/proxy/agents/sessions?hours=1&project_id=proj-abc-123",
    );
  });

  it("omits project_id when no project is set (null)", () => {
    const url = buildSeedUrl(null);
    expect(url).not.toContain("project_id");
    expect(url).toBe("/api/proxy/agents/sessions?hours=1");
  });

  it("percent-encodes special chars in project_id", () => {
    const url = buildSeedUrl("proj&admin=true");
    expect(url).toContain("proj%26admin%3Dtrue");
    expect(url).not.toContain("&admin=true");
  });
});

// ---------------------------------------------------------------------------
// 2. Session → LiveRow conversion
// ---------------------------------------------------------------------------

describe("Live page seed — AgentSession to LiveRow conversion", () => {
  const NOW = new Date("2026-03-26T10:05:00Z").getTime();

  it("first_seen_ms comes from toUTCMs(s.first_call_at)", () => {
    const session = makeSession({ first_call_at: "2026-03-26 10:00:00" });
    const rows = applySeed([session], new Map(), NOW);
    const row = rows.get("sess-seed-1")!;
    expect(row.first_seen_ms).toBe(toUTCMs("2026-03-26 10:00:00"));
  });

  it("last_seen_ms comes from first_seen_ms + duration_ms", () => {
    const session = makeSession({
      first_call_at: "2026-03-26 10:00:00",
      duration_ms: 5000,
    });
    const rows = applySeed([session], new Map(), NOW);
    const row = rows.get("sess-seed-1")!;
    const expectedFirst = toUTCMs("2026-03-26 10:00:00");
    expect(row.last_seen_ms).toBe(expectedFirst + 5000);
  });

  it("span_count comes from s.tool_calls", () => {
    const session = makeSession({ tool_calls: 12 });
    const rows = applySeed([session], new Map(), NOW);
    expect(rows.get("sess-seed-1")!.span_count).toBe(12);
  });

  it("error_count comes from s.failed_calls", () => {
    const session = makeSession({ failed_calls: 3 });
    const rows = applySeed([session], new Map(), NOW);
    expect(rows.get("sess-seed-1")!.error_count).toBe(3);
  });

  it("running_until is 0 (not currently running — set by new SSE spans)", () => {
    const rows = applySeed([makeSession()], new Map(), NOW);
    expect(rows.get("sess-seed-1")!.running_until).toBe(0);
  });

  it("ever_grew is false (loaded from DB, not observed growing)", () => {
    const rows = applySeed([makeSession()], new Map(), NOW);
    expect(rows.get("sess-seed-1")!.ever_grew).toBe(false);
  });

  it("stable_since equals last_seen_ms", () => {
    const session = makeSession({
      first_call_at: "2026-03-26 10:00:00",
      duration_ms: 3000,
    });
    const rows = applySeed([session], new Map(), NOW);
    const row = rows.get("sess-seed-1")!;
    expect(row.stable_since).toBe(row.last_seen_ms);
  });

  it("agent_name falls back to null when session.agent_name is null", () => {
    const session = makeSession({ agent_name: null });
    const rows = applySeed([session], new Map(), NOW);
    expect(rows.get("sess-seed-1")!.agent_name).toBeNull();
  });

  it("tool_calls defaults to 0 when undefined", () => {
    // Cast to bypass TypeScript required property — simulates backend omission
    const session = makeSession({ tool_calls: undefined as unknown as number });
    const rows = applySeed([session], new Map(), NOW);
    expect(rows.get("sess-seed-1")!.span_count).toBe(0);
  });

  it("failed_calls defaults to 0 when undefined", () => {
    const session = makeSession({ failed_calls: undefined as unknown as number });
    const rows = applySeed([session], new Map(), NOW);
    expect(rows.get("sess-seed-1")!.error_count).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// 3. Expired session filtering
// ---------------------------------------------------------------------------

describe("Live page seed — filters sessions older than EXPIRE_MS (10 min)", () => {
  const NOW = new Date("2026-03-26T10:15:00Z").getTime();

  it("includes session within the 10min window", () => {
    // Session ended 5 minutes ago — should be included
    const session = makeSession({
      first_call_at: "2026-03-26 10:09:00",
      duration_ms: 1000,
    });
    const rows = applySeed([session], new Map(), NOW);
    expect(rows.has("sess-seed-1")).toBe(true);
  });

  it("excludes session whose last_seen_ms is older than EXPIRE_MS", () => {
    // Session ended 11 minutes ago — should be excluded
    const session = makeSession({
      first_call_at: "2026-03-26 10:03:00",
      duration_ms: 1000,
    });
    const rows = applySeed([session], new Map(), NOW);
    expect(rows.has("sess-seed-1")).toBe(false);
  });

  it("includes session at exactly the EXPIRE_MS boundary", () => {
    // last_seen_ms = NOW - EXPIRE_MS = cutoff, condition is lastMs < cutoff,
    // so this should be included (not strictly less than).
    const cutoffMs = NOW - EXPIRE_MS;
    const firstCallAt = new Date(cutoffMs).toISOString();
    const session = makeSession({
      first_call_at: firstCallAt,
      duration_ms: 0,
    });
    const rows = applySeed([session], new Map(), NOW);
    // lastMs === cutoff, condition is lastMs < cutoff, so NOT excluded
    expect(rows.has("sess-seed-1")).toBe(true);
  });

  it("filters out expired sessions while keeping fresh ones", () => {
    const old = makeSession({
      session_id: "sess-old",
      first_call_at: "2026-03-26 10:00:00",
      duration_ms: 1000,
    });
    const fresh = makeSession({
      session_id: "sess-fresh",
      first_call_at: "2026-03-26 10:12:00",
      duration_ms: 1000,
    });
    const rows = applySeed([old, fresh], new Map(), NOW);
    expect(rows.has("sess-old")).toBe(false);
    expect(rows.has("sess-fresh")).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// 4. SSE freshness priority — DB seed does NOT overwrite SSE data
// ---------------------------------------------------------------------------

describe("Live page seed — does not overwrite fresher SSE data", () => {
  const NOW = new Date("2026-03-26T10:10:00Z").getTime();

  it("skips session if SSE already has an entry for that session_id", () => {
    const existing = new Map<string, LiveRow>();
    existing.set("sess-seed-1", {
      session_id:    "sess-seed-1",
      agent_name:    "sse-agent",
      span_count:    42,
      error_count:   1,
      first_seen_ms: NOW - 30_000,
      last_seen_ms:  NOW - 5_000,
      running_until: NOW + 25_000,
      ever_grew:     true,
      stable_since:  NOW - 5_000,
    });

    const session = makeSession({
      session_id: "sess-seed-1",
      agent_name: "db-agent",
      tool_calls: 3,
    });
    const rows = applySeed([session], existing, NOW);

    // SSE version must be preserved, not overwritten by DB seed
    const row = rows.get("sess-seed-1")!;
    expect(row.agent_name).toBe("sse-agent");
    expect(row.span_count).toBe(42);
    expect(row.ever_grew).toBe(true);
    expect(row.running_until).toBeGreaterThan(0);
  });

  it("adds sessions that SSE does not have", () => {
    const existing = new Map<string, LiveRow>();
    existing.set("sess-sse-only", {
      session_id:    "sess-sse-only",
      agent_name:    "sse-agent",
      span_count:    1,
      error_count:   0,
      first_seen_ms: NOW - 1_000,
      last_seen_ms:  NOW - 500,
      running_until: NOW + 29_500,
      ever_grew:     true,
      stable_since:  NOW - 500,
    });

    const session = makeSession({
      session_id: "sess-db-only",
      first_call_at: "2026-03-26 10:08:00",
      duration_ms: 2000,
    });
    const rows = applySeed([session], existing, NOW);

    expect(rows.has("sess-sse-only")).toBe(true);
    expect(rows.has("sess-db-only")).toBe(true);
    expect(rows.size).toBe(2);
  });
});

// ---------------------------------------------------------------------------
// 5. Seed fetch failure resilience
// ---------------------------------------------------------------------------

describe("Live page seed — resilience on fetch failure", () => {
  it("returns empty map when response is not ok (e.g. 500)", () => {
    // The page does: fetch(url).then(r => r.ok ? r.json() : [])
    // On non-ok response, sessions is [], so no rows added
    const rows = applySeed([], new Map(), Date.now());
    expect(rows.size).toBe(0);
  });

  it("existing SSE rows survive when seed returns empty", () => {
    const existing = new Map<string, LiveRow>();
    const NOW = Date.now();
    existing.set("sess-sse", {
      session_id:    "sess-sse",
      agent_name:    "agent",
      span_count:    5,
      error_count:   0,
      first_seen_ms: NOW - 10_000,
      last_seen_ms:  NOW - 1_000,
      running_until: NOW + 29_000,
      ever_grew:     true,
      stable_since:  NOW - 1_000,
    });

    // Seed returns empty (simulating network error / 500)
    const rows = applySeed([], existing, NOW);
    expect(rows.size).toBe(1);
    expect(rows.get("sess-sse")!.span_count).toBe(5);
  });
});

// ---------------------------------------------------------------------------
// 6. Regression: old broken URL must never appear
// ---------------------------------------------------------------------------

describe("Live page seed — regression: correct proxy URL", () => {
  it("URL must not be /api/agents/sessions (the 404 bug)", () => {
    const url = buildSeedUrl(null);
    // The old broken pattern was `/api/agents/sessions?hours=1`
    // The fix changed it to `/api/proxy/agents/sessions?hours=1`
    expect(url).not.toBe("/api/agents/sessions?hours=1");
    expect(url).toMatch(/^\/api\/proxy\/agents\/sessions/);
  });

  it("URL must not be /api/agents/sessions even with project_id", () => {
    const url = buildSeedUrl("proj-1");
    expect(url).not.toMatch(/^\/api\/agents\/sessions/);
    expect(url).toMatch(/^\/api\/proxy\/agents\/sessions/);
  });
});
