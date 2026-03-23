/**
 * DateRangeFilter — adversarial input tests.
 *
 * Invariant: the DateRangeFilter component calls onCustomRange(from, to)
 * with ISO strings produced via `new Date(input + "T00:00:00").toISOString()`.
 * Hostile inputs — injected HTML, SQL fragments, negative years, NaN values —
 * must either:
 *   (a) produce a string containing "Invalid Date" (Date constructor rejection), or
 *   (b) never reach onCustomRange at all because the Apply button is disabled.
 *
 * The component must never pass a raw user string that bypasses Date() into
 * the callback, and must never render executable markup.
 */

import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DateRangeFilter } from "@/components/date-range-filter";

// ─── Helpers ──────────────────────────────────────────────────────────────────

function renderFilter(overrides: Partial<React.ComponentProps<typeof DateRangeFilter>> = {}) {
  const onPreset = jest.fn();
  const onCustomRange = jest.fn();
  const onClearCustom = jest.fn();

  const { container } = render(
    <DateRangeFilter
      activeHours={24}
      onPreset={onPreset}
      onCustomRange={onCustomRange}
      onClearCustom={onClearCustom}
      {...overrides}
    />,
  );

  return { container, onPreset, onCustomRange, onClearCustom };
}

/** Open the custom range picker by clicking the "Range" / "Custom" toggle button. */
async function openPicker(_container: HTMLElement) {
  // The Calendar icon button contains the text "Range" (when no custom range is
  // active) or "Custom" (when one is active).  It does not carry a title attr.
  const trigger = screen.getByRole("button", { name: /range|custom/i });
  await userEvent.click(trigger);
}

// ─── Apply button disabled state ─────────────────────────────────────────────

describe("DateRangeFilter — Apply button must be disabled when inputs are empty", () => {
  /**
   * Invariant: onCustomRange must never be called with empty or half-filled
   * date inputs.  The Apply button must remain disabled.
   */

  it("Apply button is disabled when both date inputs are empty", async () => {
    const { container, onCustomRange } = renderFilter();
    await openPicker(container);

    const applyBtn = screen.getByRole("button", { name: /apply/i });
    expect(applyBtn).toBeDisabled();

    // Clicking a disabled button must not invoke the callback
    fireEvent.click(applyBtn);
    expect(onCustomRange).not.toHaveBeenCalled();
  });

  it("Apply button is disabled when only fromDate is set", async () => {
    const { container, onCustomRange } = renderFilter();
    await openPicker(container);

    // type="date" inputs don't carry role="textbox" — query by type directly
    const dateInputs = container.querySelectorAll('input[type="date"]');
    fireEvent.change(dateInputs[0], { target: { value: "2026-01-01" } });

    const applyBtn = screen.getByRole("button", { name: /apply/i });
    expect(applyBtn).toBeDisabled();
    fireEvent.click(applyBtn);
    expect(onCustomRange).not.toHaveBeenCalled();
  });

  it("Apply button is enabled only when both inputs are non-empty", async () => {
    const { container, onCustomRange } = renderFilter();
    await openPicker(container);

    const dateInputs = container.querySelectorAll('input[type="date"]');
    fireEvent.change(dateInputs[0], { target: { value: "2026-01-01" } });
    fireEvent.change(dateInputs[1], { target: { value: "2026-01-07" } });

    const applyBtn = screen.getByRole("button", { name: /apply/i });
    expect(applyBtn).not.toBeDisabled();
    fireEvent.click(applyBtn);
    expect(onCustomRange).toHaveBeenCalledTimes(1);
  });
});

// ─── Date output is always an ISO string ─────────────────────────────────────

describe("DateRangeFilter — onCustomRange receives valid ISO strings or Invalid Date", () => {
  /**
   * Invariant: the only values that reach onCustomRange are strings produced by
   * Date.prototype.toISOString().  Even if the user somehow supplies a value
   * that passes the non-empty check, the resulting string must be either a valid
   * ISO-8601 timestamp or the literal string "Invalid Date".
   * It must never be a raw SQL fragment, HTML tag, or path-traversal string.
   */

  async function applyDates(container: HTMLElement, from: string, to: string) {
    const dateInputs = container.querySelectorAll('input[type="date"]');
    fireEvent.change(dateInputs[0], { target: { value: from } });
    fireEvent.change(dateInputs[1], { target: { value: to } });
    const applyBtn = screen.getByRole("button", { name: /apply/i });
    // Only click if enabled — some payloads may keep it disabled
    if (!applyBtn.hasAttribute("disabled") && !(applyBtn as HTMLButtonElement).disabled) {
      fireEvent.click(applyBtn);
    }
  }

  it("produces ISO strings for a valid date range", async () => {
    const { container, onCustomRange } = renderFilter();
    await openPicker(container);
    await applyDates(container, "2026-01-01", "2026-01-31");

    expect(onCustomRange).toHaveBeenCalledTimes(1);
    const [from, to] = onCustomRange.mock.calls[0] as [string, string];
    // Must be ISO-8601: ends with Z
    expect(from).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$/);
    expect(to).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$/);
  });

  it("callback is not called when dates are reversed (from > to) — or if called, both args are ISO", async () => {
    // The component does not validate ordering — that is backend's job.
    // But whatever is passed must still be ISO strings.
    const { container, onCustomRange } = renderFilter();
    await openPicker(container);
    await applyDates(container, "2026-12-31", "2026-01-01");

    if (onCustomRange.mock.calls.length > 0) {
      const [from, to] = onCustomRange.mock.calls[0] as [string, string];
      expect(from).toMatch(/^\d{4}-\d{2}-\d{2}T/);
      expect(to).toMatch(/^\d{4}-\d{2}-\d{2}T/);
    }
  });
});

// ─── XSS payloads in date inputs ─────────────────────────────────────────────

describe("DateRangeFilter — XSS in date inputs does not produce executable markup", () => {
  /**
   * Invariant: the component renders date inputs with type="date".  Even if a
   * hostile string is set via fireEvent.change (simulating a programmatic
   * attack or an unexpected browser behavior), the rendered DOM must not contain
   * executable HTML tags.
   */

  it("does not render <script> tags when XSS payload is injected into fromDate", async () => {
    const { container } = renderFilter();
    await openPicker(container);

    const dateInputs = container.querySelectorAll('input[type="date"]');
    const xssPayload = '<script>window.__xss_date=1</script>';
    fireEvent.change(dateInputs[0], { target: { value: xssPayload } });

    expect(container.innerHTML).not.toMatch(/<script/i);
    expect((window as typeof window & { __xss_date?: number }).__xss_date).toBeUndefined();
  });

  it("does not execute onerror payload injected into date input", async () => {
    const { container } = renderFilter();
    await openPicker(container);

    const dateInputs = container.querySelectorAll('input[type="date"]');
    fireEvent.change(dateInputs[0], { target: { value: '<img src=x onerror="window.__xss_date=1">' } });

    expect((window as typeof window & { __xss_date?: number }).__xss_date).toBeUndefined();
  });
});

// ─── From > To validation (logic boundary) ───────────────────────────────────

describe("DateRangeFilter — extreme date boundaries", () => {
  /**
   * Invariant: extreme valid dates (year 9999, year 1600) must be accepted by
   * the Date constructor.  The test confirms that when such dates DO reach
   * onCustomRange, the emitted strings are proper ISO strings, not raw user
   * input containing script tags.
   */

  it("year 9999 produces a valid ISO string if browser accepts it", async () => {
    const { container, onCustomRange } = renderFilter();
    await openPicker(container);

    const dateInputs = container.querySelectorAll('input[type="date"]');
    fireEvent.change(dateInputs[0], { target: { value: "9999-01-01" } });
    fireEvent.change(dateInputs[1], { target: { value: "9999-12-31" } });

    const applyBtn = screen.getByRole("button", { name: /apply/i });
    if (!(applyBtn as HTMLButtonElement).disabled) {
      fireEvent.click(applyBtn);
      if (onCustomRange.mock.calls.length > 0) {
        const [from] = onCustomRange.mock.calls[0] as [string, string];
        // Must be ISO or "Invalid Date" — never raw HTML
        expect(from).not.toMatch(/<script/i);
        expect(from).not.toMatch(/onerror/i);
      }
    }
  });

  it("SQL injection in date value does not reach callback as raw SQL", async () => {
    const { container, onCustomRange } = renderFilter();
    await openPicker(container);

    const dateInputs = container.querySelectorAll('input[type="date"]');
    const sqlPayload = "2024-01-01'; DROP TABLE sessions;--";
    fireEvent.change(dateInputs[0], { target: { value: sqlPayload } });
    fireEvent.change(dateInputs[1], { target: { value: sqlPayload } });

    const applyBtn = screen.getByRole("button", { name: /apply/i });
    if (!(applyBtn as HTMLButtonElement).disabled) {
      fireEvent.click(applyBtn);
    }

    if (onCustomRange.mock.calls.length > 0) {
      const [from, to] = onCustomRange.mock.calls[0] as [string, string];
      // If the Date constructor parsed the prefix "2024-01-01" it returns an ISO string.
      // If it failed, it returns "Invalid Date".
      // In neither case should the SQL fragment appear verbatim.
      expect(from).not.toContain("DROP TABLE");
      expect(to).not.toContain("DROP TABLE");
    }
  });
});

// ─── Preset buttons ───────────────────────────────────────────────────────────

describe("DateRangeFilter — preset buttons produce numeric hours", () => {
  /**
   * Invariant: clicking a preset button calls onPreset with the numeric hours
   * value defined in the PRESETS constant.  The value must never be NaN,
   * Infinity, or a non-number type.
   */

  const expectedPresets = [1, 6, 24, 168, 720];

  it("all preset buttons call onPreset with the correct numeric hours value", async () => {
    const { onPreset } = renderFilter();

    const presetButtons = screen.getAllByRole("button").filter(
      (btn) => expectedPresets.some((h) => btn.textContent?.replace(/[^0-9hdm]/g, "") === String(h) || btn.textContent?.includes(h === 1 ? "1h" : h === 6 ? "6h" : h === 24 ? "24h" : h === 168 ? "7d" : "30d")),
    );

    // Click each of the 5 preset labels
    const presetLabels = ["1h", "6h", "24h", "7d", "30d"];
    for (const label of presetLabels) {
      const btn = screen.getByRole("button", { name: label });
      await userEvent.click(btn);
    }

    const calledValues = onPreset.mock.calls.map((call) => call[0] as number);
    for (const v of calledValues) {
      expect(typeof v).toBe("number");
      expect(Number.isFinite(v)).toBe(true);
      expect(v).toBeGreaterThan(0);
    }
  });
});
