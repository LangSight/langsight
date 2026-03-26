/**
 * Tests for the Live page's getStatus function — session status classification.
 *
 * The getStatus function determines the visual state of each session row:
 *   - "running"  — actively receiving spans
 *   - "idle"     — stopped growing recently, might resume
 *   - "stuck"    — stopped growing for > 2 minutes
 *   - "done"     — never grew (loaded from DB seed, never received SSE spans)
 *
 * The function is defined in live/page.tsx lines 22-30:
 *
 *   function getStatus(row: LiveRow, now: number): SessionStatus {
 *     if (now < row.running_until) return "running";
 *     const age = now - row.last_seen_ms;
 *     if (age < RUNNING_MS) return "running";
 *     if (!row.ever_grew) return "done";
 *     const stableFor = now - row.stable_since;
 *     if (stableFor < STUCK_MS) return "idle";
 *     return "stuck";
 *   }
 */

import { RUNNING_MS, EXPIRE_MS, type LiveRow } from "../../lib/live-utils";

// ---------------------------------------------------------------------------
// Constants — must match live/page.tsx
// ---------------------------------------------------------------------------

const STUCK_MS = 2 * 60_000;  // 2 minutes (from page.tsx line 14)

// ---------------------------------------------------------------------------
// Reproduce getStatus exactly from live/page.tsx lines 22-30
// ---------------------------------------------------------------------------

type SessionStatus = "running" | "idle" | "stuck" | "done";

function getStatus(row: LiveRow, now: number): SessionStatus {
  if (now < row.running_until) return "running";
  const age = now - row.last_seen_ms;
  if (age < RUNNING_MS) return "running";
  if (!row.ever_grew) return "done";
  const stableFor = now - row.stable_since;
  if (stableFor < STUCK_MS) return "idle";
  return "stuck";
}

// ---------------------------------------------------------------------------
// Helper — build a LiveRow with sensible defaults
// ---------------------------------------------------------------------------

function makeRow(overrides: Partial<LiveRow> = {}): LiveRow {
  const NOW = Date.now();
  return {
    session_id:    "sess-status-1",
    agent_name:    "test-agent",
    span_count:    5,
    error_count:   0,
    first_seen_ms: NOW - 60_000,
    last_seen_ms:  NOW - 10_000,
    running_until: 0,
    ever_grew:     true,
    stable_since:  NOW - 10_000,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// 1. running — via running_until
// ---------------------------------------------------------------------------

describe("getStatus — running (running_until in the future)", () => {
  it("returns 'running' when running_until > now", () => {
    const NOW = Date.now();
    const row = makeRow({
      running_until: NOW + 10_000,
      last_seen_ms:  NOW - 60_000,  // old, but running_until overrides
      ever_grew:     true,
    });
    expect(getStatus(row, NOW)).toBe("running");
  });

  it("returns 'running' when running_until is exactly now + 1ms", () => {
    const NOW = Date.now();
    const row = makeRow({ running_until: NOW + 1 });
    expect(getStatus(row, NOW)).toBe("running");
  });
});

// ---------------------------------------------------------------------------
// 2. running — via last_seen_ms recency (< RUNNING_MS = 30s)
// ---------------------------------------------------------------------------

describe("getStatus — running (last seen < 30s ago)", () => {
  it("returns 'running' when last_seen_ms is 5s ago", () => {
    const NOW = Date.now();
    const row = makeRow({
      running_until: 0,
      last_seen_ms:  NOW - 5_000,
      ever_grew:     true,
    });
    expect(getStatus(row, NOW)).toBe("running");
  });

  it("returns 'running' when last_seen_ms is 29s ago (just under threshold)", () => {
    const NOW = Date.now();
    const row = makeRow({
      running_until: 0,
      last_seen_ms:  NOW - 29_000,
      ever_grew:     true,
    });
    expect(getStatus(row, NOW)).toBe("running");
  });

  it("does NOT return 'running' when last_seen_ms is exactly RUNNING_MS ago", () => {
    const NOW = Date.now();
    const row = makeRow({
      running_until: 0,
      last_seen_ms:  NOW - RUNNING_MS,
      ever_grew:     true,
      stable_since:  NOW - 10_000,  // < STUCK_MS → idle
    });
    // age = RUNNING_MS, condition is age < RUNNING_MS → false, so not "running"
    expect(getStatus(row, NOW)).not.toBe("running");
  });
});

// ---------------------------------------------------------------------------
// 3. done — never grew (ever_grew: false)
// ---------------------------------------------------------------------------

describe("getStatus — done (ever_grew is false)", () => {
  it("returns 'done' for a DB-seeded session that never received SSE spans", () => {
    const NOW = Date.now();
    const row = makeRow({
      running_until: 0,
      last_seen_ms:  NOW - 60_000,  // old
      ever_grew:     false,
    });
    expect(getStatus(row, NOW)).toBe("done");
  });

  it("returns 'done' even if stable_since is recent (ever_grew takes priority)", () => {
    const NOW = Date.now();
    const row = makeRow({
      running_until: 0,
      last_seen_ms:  NOW - 60_000,
      ever_grew:     false,
      stable_since:  NOW - 1_000,  // very recent, but ever_grew=false wins
    });
    expect(getStatus(row, NOW)).toBe("done");
  });

  it("a session with ever_grew=false but last_seen_ms < 30s ago is still 'running'", () => {
    // The age < RUNNING_MS check comes before the ever_grew check
    const NOW = Date.now();
    const row = makeRow({
      running_until: 0,
      last_seen_ms:  NOW - 5_000,  // very recent
      ever_grew:     false,
    });
    expect(getStatus(row, NOW)).toBe("running");
  });
});

// ---------------------------------------------------------------------------
// 4. idle — stopped growing but < 2min ago
// ---------------------------------------------------------------------------

describe("getStatus — idle (stopped growing < 2min ago)", () => {
  it("returns 'idle' when stable_since is 30s ago", () => {
    const NOW = Date.now();
    const row = makeRow({
      running_until: 0,
      last_seen_ms:  NOW - 45_000,  // > 30s → not running via recency
      ever_grew:     true,
      stable_since:  NOW - 30_000,  // 30s ago, < 2min
    });
    expect(getStatus(row, NOW)).toBe("idle");
  });

  it("returns 'idle' when stable_since is 1min 59s ago (just under STUCK_MS)", () => {
    const NOW = Date.now();
    const row = makeRow({
      running_until: 0,
      last_seen_ms:  NOW - 180_000,
      ever_grew:     true,
      stable_since:  NOW - 119_000,  // 119s, just under 120s STUCK_MS
    });
    expect(getStatus(row, NOW)).toBe("idle");
  });

  it("returns 'idle' at exactly stable_since = 1s ago", () => {
    const NOW = Date.now();
    const row = makeRow({
      running_until: 0,
      last_seen_ms:  NOW - 60_000,
      ever_grew:     true,
      stable_since:  NOW - 1_000,
    });
    expect(getStatus(row, NOW)).toBe("idle");
  });
});

// ---------------------------------------------------------------------------
// 5. stuck — stopped growing > 2min ago
// ---------------------------------------------------------------------------

describe("getStatus — stuck (stopped growing > 2min ago)", () => {
  it("returns 'stuck' when stable_since is 3min ago", () => {
    const NOW = Date.now();
    const row = makeRow({
      running_until: 0,
      last_seen_ms:  NOW - 240_000,
      ever_grew:     true,
      stable_since:  NOW - 180_000,  // 3 minutes
    });
    expect(getStatus(row, NOW)).toBe("stuck");
  });

  it("returns 'stuck' when stable_since is exactly STUCK_MS ago", () => {
    const NOW = Date.now();
    const row = makeRow({
      running_until: 0,
      last_seen_ms:  NOW - 180_000,
      ever_grew:     true,
      stable_since:  NOW - STUCK_MS,  // exactly 2 minutes
    });
    // stableFor = STUCK_MS, condition is stableFor < STUCK_MS → false → "stuck"
    expect(getStatus(row, NOW)).toBe("stuck");
  });

  it("returns 'stuck' for a session idle for 10min", () => {
    const NOW = Date.now();
    const row = makeRow({
      running_until: 0,
      last_seen_ms:  NOW - 600_000,
      ever_grew:     true,
      stable_since:  NOW - 600_000,
    });
    expect(getStatus(row, NOW)).toBe("stuck");
  });
});

// ---------------------------------------------------------------------------
// 6. Priority ordering of status checks
// ---------------------------------------------------------------------------

describe("getStatus — priority: running_until > age > ever_grew > stable_since", () => {
  it("running_until takes precedence over everything else", () => {
    const NOW = Date.now();
    const row = makeRow({
      running_until: NOW + 5_000,    // future → running
      last_seen_ms:  NOW - 300_000,  // 5min ago → would be stuck otherwise
      ever_grew:     false,          // would be done otherwise
      stable_since:  NOW - 300_000,  // would be stuck otherwise
    });
    expect(getStatus(row, NOW)).toBe("running");
  });

  it("age recency takes precedence over ever_grew and stable_since", () => {
    const NOW = Date.now();
    const row = makeRow({
      running_until: 0,
      last_seen_ms:  NOW - 10_000,   // 10s ago → running via recency
      ever_grew:     false,          // would be done otherwise
      stable_since:  NOW - 300_000,
    });
    expect(getStatus(row, NOW)).toBe("running");
  });

  it("ever_grew=false takes precedence over stable_since check", () => {
    const NOW = Date.now();
    const row = makeRow({
      running_until: 0,
      last_seen_ms:  NOW - 60_000,
      ever_grew:     false,          // → done (skip stable_since check)
      stable_since:  NOW - 30_000,   // would be idle if ever_grew were true
    });
    expect(getStatus(row, NOW)).toBe("done");
  });
});

// ---------------------------------------------------------------------------
// 7. EXPIRE_MS eviction boundary
// ---------------------------------------------------------------------------

describe("getStatus + EXPIRE_MS — session eviction", () => {
  it("EXPIRE_MS is 10 minutes (600,000ms)", () => {
    expect(EXPIRE_MS).toBe(10 * 60_000);
    expect(EXPIRE_MS).toBe(600_000);
  });

  it("RUNNING_MS is 30 seconds (30,000ms)", () => {
    expect(RUNNING_MS).toBe(30_000);
  });

  it("STUCK_MS is 2 minutes (120,000ms)", () => {
    expect(STUCK_MS).toBe(120_000);
  });

  it("a session with last_seen_ms older than EXPIRE_MS would be evicted by mergeSpan", () => {
    // This test documents that eviction happens in mergeSpan, not getStatus.
    // getStatus determines display status; mergeSpan handles eviction.
    // A session that exceeds EXPIRE_MS should be removed from the map by
    // the eviction loop in mergeSpan, so getStatus would never see it.
    const NOW = Date.now();
    const row = makeRow({
      running_until: 0,
      last_seen_ms:  NOW - EXPIRE_MS - 1,  // 1ms past expiry
      ever_grew:     true,
      stable_since:  NOW - EXPIRE_MS - 1,
    });
    // getStatus still returns a status (it doesn't know about eviction)
    const status = getStatus(row, NOW);
    expect(status).toBe("stuck");
    // But mergeSpan would have deleted this row before getStatus runs
  });
});

// ---------------------------------------------------------------------------
// 8. Edge cases
// ---------------------------------------------------------------------------

describe("getStatus — edge cases", () => {
  it("handles row where all timestamps are 0", () => {
    const NOW = Date.now();
    const row = makeRow({
      running_until: 0,
      last_seen_ms:  0,
      ever_grew:     false,
      stable_since:  0,
    });
    // age = NOW - 0 = NOW (very old), not running via recency
    // ever_grew = false → done
    expect(getStatus(row, NOW)).toBe("done");
  });

  it("handles row with running_until exactly equal to now", () => {
    const NOW = Date.now();
    const row = makeRow({
      running_until: NOW,  // now < now is false
      last_seen_ms:  NOW - 60_000,
      ever_grew:     true,
      stable_since:  NOW - 60_000,
    });
    // running_until = NOW → (NOW < NOW) is false → not running via running_until
    // Then falls through to age check, stable_since check etc.
    expect(getStatus(row, NOW)).not.toBe("running");
  });

  it("handles brand new session that just appeared", () => {
    const NOW = Date.now();
    const row = makeRow({
      running_until: NOW + RUNNING_MS,
      last_seen_ms:  NOW,
      ever_grew:     true,
      stable_since:  NOW,
    });
    expect(getStatus(row, NOW)).toBe("running");
  });
});
