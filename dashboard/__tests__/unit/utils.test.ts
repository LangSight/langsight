import {
  cn,
  formatLatency,
  formatDuration,
  timeAgo,
  STATUS_BG,
  STATUS_ICON,
  STATUS_COLOR,
  SEVERITY_BG,
  CALL_STATUS_COLOR,
  SPAN_TYPE_ICON,
} from "@/lib/utils";

/* ── cn ─────────────────────────────────────────────────────── */
describe("cn", () => {
  it("merges class names", () => {
    expect(cn("a", "b")).toBe("a b");
  });

  it("deduplicates tailwind classes (last wins)", () => {
    expect(cn("p-2", "p-4")).toBe("p-4");
  });

  it("ignores falsy values", () => {
    expect(cn("a", false, undefined, null, "b")).toBe("a b");
  });

  it("handles conditional object syntax", () => {
    expect(cn({ "text-red-500": true, "text-green-500": false })).toBe("text-red-500");
  });

  it("returns empty string when no classes", () => {
    expect(cn()).toBe("");
  });
});

/* ── formatLatency ──────────────────────────────────────────── */
describe("formatLatency", () => {
  it("returns — for null", () => {
    expect(formatLatency(null)).toBe("—");
  });

  it("returns — for undefined", () => {
    expect(formatLatency(undefined as unknown as null)).toBe("—");
  });

  it("formats sub-second latency in ms", () => {
    expect(formatLatency(42)).toBe("42ms");
    expect(formatLatency(999)).toBe("999ms");
  });

  it("formats >= 1000ms as seconds", () => {
    expect(formatLatency(1000)).toBe("1.0s");
    expect(formatLatency(1500)).toBe("1.5s");
    expect(formatLatency(2340)).toBe("2.3s");
  });

  it("rounds ms to nearest integer", () => {
    expect(formatLatency(42.7)).toBe("43ms");
  });

  it("formats zero as 0ms", () => {
    expect(formatLatency(0)).toBe("0ms");
  });
});

/* ── formatDuration ─────────────────────────────────────────── */
describe("formatDuration", () => {
  it("returns — for null", () => {
    expect(formatDuration(null)).toBe("—");
  });

  it("returns — for 0", () => {
    expect(formatDuration(0)).toBe("—");
  });

  it("formats sub-second duration in ms", () => {
    expect(formatDuration(500)).toBe("500ms");
  });

  it("formats 1s–59s in seconds", () => {
    expect(formatDuration(1_000)).toBe("1.0s");
    expect(formatDuration(59_999)).toBe("60.0s");
  });

  it("formats >= 60s in minutes", () => {
    expect(formatDuration(60_000)).toBe("1.0m");
    expect(formatDuration(90_000)).toBe("1.5m");
    expect(formatDuration(120_000)).toBe("2.0m");
  });
});

/* ── timeAgo ────────────────────────────────────────────────── */
describe("timeAgo", () => {
  beforeEach(() => {
    jest.useFakeTimers();
    jest.setSystemTime(new Date("2026-01-01T12:00:00Z"));
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it("shows seconds for < 60s ago", () => {
    const iso = new Date(Date.now() - 30_000).toISOString();
    expect(timeAgo(iso)).toBe("30s ago");
  });

  it("shows minutes for 60s–3599s ago", () => {
    const iso = new Date(Date.now() - 5 * 60_000).toISOString();
    expect(timeAgo(iso)).toBe("5m ago");
  });

  it("shows hours for 1h–23h ago", () => {
    const iso = new Date(Date.now() - 3 * 3600_000).toISOString();
    expect(timeAgo(iso)).toBe("3h ago");
  });

  it("shows days for >= 24h ago", () => {
    const iso = new Date(Date.now() - 2 * 86400_000).toISOString();
    expect(timeAgo(iso)).toBe("2d ago");
  });

  it("shows 0s ago for very recent", () => {
    const iso = new Date(Date.now() - 500).toISOString();
    expect(timeAgo(iso)).toBe("0s ago");
  });
});

/* ── Status maps ────────────────────────────────────────────── */
describe("STATUS_BG", () => {
  it("covers all server statuses", () => {
    const statuses = ["up", "degraded", "down", "stale", "unknown"] as const;
    statuses.forEach((s) => {
      expect(STATUS_BG[s]).toBeTruthy();
    });
  });

  it("up status contains emerald colour", () => {
    expect(STATUS_BG.up).toContain("emerald");
  });

  it("down status contains red colour", () => {
    expect(STATUS_BG.down).toContain("red");
  });

  it("degraded status contains yellow colour", () => {
    expect(STATUS_BG.degraded).toContain("yellow");
  });
});

describe("STATUS_ICON", () => {
  it("up shows ✓", () => expect(STATUS_ICON.up).toBe("✓"));
  it("down shows ✗", () => expect(STATUS_ICON.down).toBe("✗"));
  it("degraded shows ⚠", () => expect(STATUS_ICON.degraded).toBe("⚠"));
  it("stale shows ~", () => expect(STATUS_ICON.stale).toBe("~"));
  it("unknown shows ?", () => expect(STATUS_ICON.unknown).toBe("?"));
});

describe("STATUS_COLOR", () => {
  it("covers all server statuses", () => {
    ["up", "degraded", "down", "stale", "unknown"].forEach((s) => {
      expect(STATUS_COLOR[s as keyof typeof STATUS_COLOR]).toBeTruthy();
    });
  });
});

/* ── SEVERITY_BG ─────────────────────────────────────────────── */
describe("SEVERITY_BG", () => {
  it("covers all severity levels", () => {
    const severities = ["critical", "high", "medium", "low", "info"] as const;
    severities.forEach((s) => {
      expect(SEVERITY_BG[s]).toBeTruthy();
    });
  });

  it("critical severity contains red", () => {
    expect(SEVERITY_BG.critical).toContain("red");
  });

  it("info severity contains blue", () => {
    expect(SEVERITY_BG.info).toContain("blue");
  });
});

/* ── CALL_STATUS_COLOR ──────────────────────────────────────── */
describe("CALL_STATUS_COLOR", () => {
  it("success is green/emerald", () => {
    expect(CALL_STATUS_COLOR.success).toContain("emerald");
  });

  it("error is red", () => {
    expect(CALL_STATUS_COLOR.error).toContain("red");
  });

  it("timeout is yellow", () => {
    expect(CALL_STATUS_COLOR.timeout).toContain("yellow");
  });
});

/* ── SPAN_TYPE_ICON ─────────────────────────────────────────── */
describe("SPAN_TYPE_ICON", () => {
  it("tool_call shows wrench emoji", () => {
    expect(SPAN_TYPE_ICON.tool_call).toBe("🔧");
  });

  it("agent shows robot emoji", () => {
    expect(SPAN_TYPE_ICON.agent).toBe("🤖");
  });

  it("handoff shows arrow", () => {
    expect(SPAN_TYPE_ICON.handoff).toBe("→");
  });
});
