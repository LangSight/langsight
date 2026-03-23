/**
 * Tests for the new utility functions added in the date-range / timestamp commits:
 *   - formatExact
 *   - formatTime
 *
 * The existing timeAgo / formatLatency / formatDuration tests live in utils.test.ts.
 * This file adds coverage for the two functions that were previously untested.
 */
import { formatExact, formatTime } from "@/lib/utils";

/* ── formatExact ─────────────────────────────────────────────── */
describe("formatExact", () => {
  it("returns a non-empty string for a valid ISO date", () => {
    const result = formatExact("2026-03-22T14:30:05Z");
    expect(result).toBeTruthy();
    expect(typeof result).toBe("string");
  });

  it("includes the year in the output", () => {
    const result = formatExact("2026-03-22T14:30:05Z");
    expect(result).toContain("2026");
  });

  it("includes hours and minutes in the output", () => {
    // The exact locale string includes time portions like "14:30:05"
    const result = formatExact("2026-03-22T14:30:05Z");
    // Should contain both hours/minutes formatted (locale-dependent but always present)
    expect(result).toMatch(/\d{2}:\d{2}/);
  });

  it("includes a timezone abbreviation", () => {
    const result = formatExact("2026-03-22T14:30:05Z");
    // timeZoneName: "short" adds something like UTC, GMT, EST etc.
    expect(result).toMatch(/[A-Z]{2,5}|UTC[+-]/);
  });

  it("formats month as short name (Mar, Jan, etc.)", () => {
    const result = formatExact("2026-03-22T14:30:05Z");
    // en-US locale with month: "short" gives Jan, Feb, Mar ...
    expect(result).toMatch(/Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec/);
  });

  it("handles midnight correctly", () => {
    const result = formatExact("2026-01-01T00:00:00Z");
    expect(result).toContain("2026");
    expect(result).toMatch(/\d{2}:\d{2}/);
  });

  it("handles end-of-day timestamp", () => {
    // Use a date far from midnight UTC to avoid year rollover in any timezone
    const result = formatExact("2026-06-30T23:59:59Z");
    expect(result).toContain("2026");
  });

  it("produces different output for different dates", () => {
    const r1 = formatExact("2026-01-01T00:00:00Z");
    const r2 = formatExact("2026-06-15T12:00:00Z");
    expect(r1).not.toBe(r2);
  });
});

/* ── formatTime ──────────────────────────────────────────────── */
describe("formatTime", () => {
  it("returns a non-empty string for a valid ISO date", () => {
    const result = formatTime("2026-03-22T14:30:05Z");
    expect(result).toBeTruthy();
    expect(typeof result).toBe("string");
  });

  it("returns HH:MM:SS formatted time string", () => {
    const result = formatTime("2026-03-22T14:30:05Z");
    // Should contain colon-separated time parts
    expect(result).toMatch(/\d{1,2}:\d{2}:\d{2}/);
  });

  it("returns different strings for different times", () => {
    const r1 = formatTime("2026-03-22T08:00:00Z");
    const r2 = formatTime("2026-03-22T20:00:00Z");
    expect(r1).not.toBe(r2);
  });
});
