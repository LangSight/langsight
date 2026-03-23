/**
 * Tests for the Timestamp component.
 *
 * Covers:
 *   - Default (non-compact) mode: renders both relative and exact time
 *   - Compact mode: renders only relative time
 *   - title attribute holds the exact time (for tooltip-on-hover)
 *   - dateTime attribute carries the original ISO string
 *   - className prop is forwarded to the <time> element
 *   - Edge cases: far-future date, very old date
 */
import { render, screen } from "@testing-library/react";
import { Timestamp } from "@/components/timestamp";

/* ── Freeze time so timeAgo / formatExact output is deterministic ── */
beforeEach(() => {
  jest.useFakeTimers();
  jest.setSystemTime(new Date("2026-03-22T12:00:00Z"));
});

afterEach(() => {
  jest.useRealTimers();
});

/* ── Helper: a fixed ISO string 2 hours before frozen clock ───── */
const TWO_HOURS_AGO = "2026-03-22T10:00:00Z";
const THREE_DAYS_AGO = "2026-03-19T12:00:00Z";
const THIRTY_SECS_AGO = "2026-03-22T11:59:30Z";

/* ── Default (non-compact) mode ──────────────────────────────── */
describe("Timestamp — default (non-compact) mode", () => {
  it("renders a <time> element", () => {
    render(<Timestamp iso={TWO_HOURS_AGO} />);
    expect(screen.getByRole("time")).toBeInTheDocument();
  });

  it("sets dateTime attribute to a valid ISO string for a valid iso prop", () => {
    render(<Timestamp iso={TWO_HOURS_AGO} />);
    const dateTime = screen.getByRole("time").getAttribute("dateTime") ?? "";
    // Component normalizes via new Date().toISOString() — verify same point in time
    expect(new Date(dateTime).getTime()).toBe(new Date(TWO_HOURS_AGO).getTime());
    expect(dateTime).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/);
  });

  it("renders the relative time text (e.g. '2h ago')", () => {
    render(<Timestamp iso={TWO_HOURS_AGO} />);
    expect(screen.getByText("2h ago")).toBeInTheDocument();
  });

  it("renders the exact time separator ' · '", () => {
    render(<Timestamp iso={TWO_HOURS_AGO} />);
    // The exact span contains " · " prefix followed by the formatted time
    const timeEl = screen.getByRole("time");
    expect(timeEl.textContent).toContain("·");
  });

  it("sets the title attribute to the exact formatted time", () => {
    render(<Timestamp iso={TWO_HOURS_AGO} />);
    const timeEl = screen.getByRole("time");
    // title must be non-empty and contain 2026
    expect(timeEl.getAttribute("title")).toBeTruthy();
    expect(timeEl.getAttribute("title")).toContain("2026");
  });

  it("forwards className to the <time> element", () => {
    render(<Timestamp iso={TWO_HOURS_AGO} className="my-custom-class" />);
    expect(screen.getByRole("time")).toHaveClass("my-custom-class");
  });

  it("shows seconds for very recent timestamps", () => {
    render(<Timestamp iso={THIRTY_SECS_AGO} />);
    expect(screen.getByText("30s ago")).toBeInTheDocument();
  });

  it("shows days for old timestamps", () => {
    render(<Timestamp iso={THREE_DAYS_AGO} />);
    expect(screen.getByText("3d ago")).toBeInTheDocument();
  });
});

/* ── Compact mode ────────────────────────────────────────────── */
describe("Timestamp — compact mode", () => {
  it("renders a <time> element", () => {
    render(<Timestamp iso={TWO_HOURS_AGO} compact />);
    expect(screen.getByRole("time")).toBeInTheDocument();
  });

  it("sets dateTime attribute to a valid ISO string for a valid iso prop", () => {
    render(<Timestamp iso={TWO_HOURS_AGO} compact />);
    const dateTime = screen.getByRole("time").getAttribute("dateTime") ?? "";
    expect(new Date(dateTime).getTime()).toBe(new Date(TWO_HOURS_AGO).getTime());
    expect(dateTime).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/);
  });

  it("shows relative time as the visible text", () => {
    render(<Timestamp iso={TWO_HOURS_AGO} compact />);
    expect(screen.getByRole("time").textContent).toBe("2h ago");
  });

  it("does NOT render the ' · exact' separator in compact mode", () => {
    render(<Timestamp iso={TWO_HOURS_AGO} compact />);
    expect(screen.getByRole("time").textContent).not.toContain("·");
  });

  it("sets title to the exact formatted time for tooltip", () => {
    render(<Timestamp iso={TWO_HOURS_AGO} compact />);
    const timeEl = screen.getByRole("time");
    expect(timeEl.getAttribute("title")).toBeTruthy();
    expect(timeEl.getAttribute("title")).toContain("2026");
  });

  it("has cursor: default style (no pointer cursor in compact mode)", () => {
    render(<Timestamp iso={TWO_HOURS_AGO} compact />);
    const timeEl = screen.getByRole("time");
    expect(timeEl).toHaveStyle({ cursor: "default" });
  });

  it("forwards className in compact mode", () => {
    render(<Timestamp iso={TWO_HOURS_AGO} compact className="compact-cls" />);
    expect(screen.getByRole("time")).toHaveClass("compact-cls");
  });

  it("shows correct relative time for days in compact mode", () => {
    render(<Timestamp iso={THREE_DAYS_AGO} compact />);
    expect(screen.getByRole("time").textContent).toBe("3d ago");
  });
});

/* ── Title (exact time) consistency ─────────────────────────── */
describe("Timestamp — title attribute (tooltip content)", () => {
  it("compact and non-compact modes produce the same title value", () => {
    const { unmount } = render(<Timestamp iso={TWO_HOURS_AGO} />);
    const nonCompactTitle = screen.getByRole("time").getAttribute("title");
    unmount();

    render(<Timestamp iso={TWO_HOURS_AGO} compact />);
    const compactTitle = screen.getByRole("time").getAttribute("title");

    expect(compactTitle).toBe(nonCompactTitle);
  });

  it("title includes the month abbreviation", () => {
    render(<Timestamp iso={TWO_HOURS_AGO} />);
    const title = screen.getByRole("time").getAttribute("title") ?? "";
    expect(title).toMatch(/Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec/);
  });
});

/* ── Regression: component does not crash on epoch / extreme dates ── */
describe("Timestamp — edge cases", () => {
  it("renders without crashing for a far-future date", () => {
    // Should render without throwing
    expect(() => render(<Timestamp iso="2099-12-31T23:59:59Z" />)).not.toThrow();
  });

  it("renders without crashing for the Unix epoch", () => {
    expect(() => render(<Timestamp iso="1970-01-01T00:00:00Z" />)).not.toThrow();
  });

  it("renders without crashing for a date many years ago", () => {
    expect(() => render(<Timestamp iso="2000-01-01T00:00:00Z" />)).not.toThrow();
  });
});
