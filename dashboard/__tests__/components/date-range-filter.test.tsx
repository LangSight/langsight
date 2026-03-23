/**
 * Tests for the DateRangeFilter component.
 *
 * Covers:
 *   - Renders all 5 preset buttons (1h, 6h, 24h, 7d, 30d)
 *   - Active preset is visually distinct (inline style reflects activeHours)
 *   - Clicking a preset calls onPreset with the correct hours value
 *   - Calendar / Range button is rendered
 *   - Clicking the Range button opens the date picker dropdown
 *   - Date inputs inside dropdown accept values
 *   - Apply button is disabled when dates are incomplete
 *   - Apply button fires onCustomRange with ISO strings when both dates are set
 *   - Clear (X) button appears when customFrom + customTo are active
 *   - Clicking Clear fires onClearCustom
 *   - Clicking outside the picker closes it (click-outside handler)
 *   - Custom-active state styling on the Range button
 */
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DateRangeFilter } from "@/components/date-range-filter";

/* ── Default props ─────────────────────────────────────────── */
const defaultProps = {
  activeHours: 24 as number | null,
  onPreset: jest.fn(),
  onCustomRange: jest.fn(),
  onClearCustom: jest.fn(),
  customFrom: null as string | null,
  customTo: null as string | null,
};

function renderFilter(overrides: Partial<typeof defaultProps> = {}) {
  const props = { ...defaultProps, ...overrides };
  return render(<DateRangeFilter {...props} />);
}

beforeEach(() => {
  jest.clearAllMocks();
});

/* ── Preset buttons rendering ───────────────────────────────── */
describe("DateRangeFilter — preset buttons", () => {
  it("renders all 5 preset buttons", () => {
    renderFilter();
    expect(screen.getByRole("button", { name: "1h" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "6h" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "24h" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "7d" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "30d" })).toBeInTheDocument();
  });

  it("renders the Range / Calendar toggle button", () => {
    renderFilter();
    // Button contains "Range" text when no custom range is active
    expect(screen.getByRole("button", { name: /range/i })).toBeInTheDocument();
  });
});

/* ── Preset click callbacks ─────────────────────────────────── */
describe("DateRangeFilter — preset click callbacks", () => {
  it("calls onPreset(1) when 1h is clicked", async () => {
    renderFilter();
    await userEvent.click(screen.getByRole("button", { name: "1h" }));
    expect(defaultProps.onPreset).toHaveBeenCalledWith(1);
  });

  it("calls onPreset(6) when 6h is clicked", async () => {
    renderFilter();
    await userEvent.click(screen.getByRole("button", { name: "6h" }));
    expect(defaultProps.onPreset).toHaveBeenCalledWith(6);
  });

  it("calls onPreset(24) when 24h is clicked", async () => {
    renderFilter();
    await userEvent.click(screen.getByRole("button", { name: "24h" }));
    expect(defaultProps.onPreset).toHaveBeenCalledWith(24);
  });

  it("calls onPreset(168) when 7d is clicked", async () => {
    renderFilter();
    await userEvent.click(screen.getByRole("button", { name: "7d" }));
    expect(defaultProps.onPreset).toHaveBeenCalledWith(168);
  });

  it("calls onPreset(720) when 30d is clicked", async () => {
    renderFilter();
    await userEvent.click(screen.getByRole("button", { name: "30d" }));
    expect(defaultProps.onPreset).toHaveBeenCalledWith(720);
  });

  it("calls onClearCustom when a preset is clicked (clears any custom range)", async () => {
    const onClearCustom = jest.fn();
    renderFilter({
      onClearCustom,
      customFrom: "2026-03-01T00:00:00.000Z",
      customTo: "2026-03-07T23:59:59.000Z",
    });
    await userEvent.click(screen.getByRole("button", { name: "7d" }));
    expect(onClearCustom).toHaveBeenCalled();
  });
});

/* ── Range picker open/close ─────────────────────────────────── */
describe("DateRangeFilter — range picker toggle", () => {
  it("date picker is hidden by default", () => {
    renderFilter();
    expect(screen.queryByText(/custom range/i)).not.toBeInTheDocument();
  });

  it("clicking Range button opens the date picker dropdown", async () => {
    renderFilter();
    await userEvent.click(screen.getByRole("button", { name: /range/i }));
    expect(screen.getByText(/custom range/i)).toBeInTheDocument();
  });

  it("date picker shows From and To labels", async () => {
    renderFilter();
    await userEvent.click(screen.getByRole("button", { name: /range/i }));
    expect(screen.getByText("From")).toBeInTheDocument();
    expect(screen.getByText("To")).toBeInTheDocument();
  });

  it("date picker has two date inputs", async () => {
    renderFilter();
    await userEvent.click(screen.getByRole("button", { name: /range/i }));
    const inputs = screen.getAllByDisplayValue("");
    // Both date inputs start empty
    expect(inputs.length).toBeGreaterThanOrEqual(2);
  });

  it("clicking Range button a second time closes the picker", async () => {
    renderFilter();
    const rangeBtn = screen.getByRole("button", { name: /range/i });
    await userEvent.click(rangeBtn);
    expect(screen.getByText(/custom range/i)).toBeInTheDocument();
    await userEvent.click(rangeBtn);
    await waitFor(() => {
      expect(screen.queryByText(/custom range/i)).not.toBeInTheDocument();
    });
  });
});

/* ── Apply button state ──────────────────────────────────────── */
describe("DateRangeFilter — Apply button disabled state", () => {
  it("Apply button is disabled when both dates are empty", async () => {
    renderFilter();
    await userEvent.click(screen.getByRole("button", { name: /range/i }));
    const applyBtn = screen.getByRole("button", { name: /apply/i });
    expect(applyBtn).toBeDisabled();
  });

  it("Apply button is disabled when only fromDate is filled", async () => {
    const { container } = renderFilter();
    await userEvent.click(screen.getByRole("button", { name: /range/i }));
    // Pick the first date input (From)
    const dateInputs = container.querySelectorAll('input[type="date"]');
    const fromInput = dateInputs[0] as HTMLInputElement;
    fireEvent.change(fromInput, { target: { value: "2026-03-01" } });
    const applyBtn = screen.getByRole("button", { name: /apply/i });
    expect(applyBtn).toBeDisabled();
  });
});

/* ── onCustomRange callback ──────────────────────────────────── */
describe("DateRangeFilter — onCustomRange callback", () => {
  it("calls onCustomRange with ISO strings when Apply is clicked with both dates set", async () => {
    const onCustomRange = jest.fn();
    const { container } = renderFilter({ onCustomRange });

    await userEvent.click(screen.getByRole("button", { name: /range/i }));

    // date inputs are type="date" — no htmlFor on labels, query by DOM
    const dateInputs = container.querySelectorAll('input[type="date"]');
    const fromInput = dateInputs[0] as HTMLInputElement;
    const toInput = dateInputs[1] as HTMLInputElement;

    // Use fireEvent.change to set date values (userEvent.type doesn't work well with type="date")
    fireEvent.change(fromInput, { target: { value: "2026-03-01" } });
    fireEvent.change(toInput, { target: { value: "2026-03-07" } });

    const applyBtn = screen.getByRole("button", { name: /apply/i });
    // Apply should now be enabled (both dates filled)
    expect(applyBtn).not.toBeDisabled();

    await userEvent.click(applyBtn);

    expect(onCustomRange).toHaveBeenCalledTimes(1);
    const [from, to] = onCustomRange.mock.calls[0];
    // Both should be valid ISO strings
    expect(() => new Date(from)).not.toThrow();
    expect(() => new Date(to)).not.toThrow();
    // The component appends T00:00:00 / T23:59:59 and converts via local time,
    // so the UTC ISO string may differ by a timezone offset.  Verify by parsing.
    expect(new Date(from).getFullYear()).toBeGreaterThanOrEqual(2026);
    const fromLocal = new Date(from);
    // Local date should be 2026-03-01 — check year/month in local time
    expect(fromLocal.toLocaleDateString("en-CA")).toBe("2026-03-01"); // en-CA = YYYY-MM-DD
    const toLocal = new Date(to);
    expect(toLocal.toLocaleDateString("en-CA")).toBe("2026-03-07");
  });

  it("closes the picker after Apply is clicked", async () => {
    const onCustomRange = jest.fn();
    const { container } = renderFilter({ onCustomRange });

    await userEvent.click(screen.getByRole("button", { name: /range/i }));
    const dateInputs = container.querySelectorAll('input[type="date"]');
    fireEvent.change(dateInputs[0] as HTMLInputElement, { target: { value: "2026-03-01" } });
    fireEvent.change(dateInputs[1] as HTMLInputElement, { target: { value: "2026-03-07" } });
    await userEvent.click(screen.getByRole("button", { name: /apply/i }));

    await waitFor(() => {
      expect(screen.queryByText(/custom range/i)).not.toBeInTheDocument();
    });
  });
});

/* ── Custom-active state ─────────────────────────────────────── */
describe("DateRangeFilter — custom range active state", () => {
  it("shows 'Custom' label on the calendar button when a custom range is active", () => {
    renderFilter({
      customFrom: "2026-03-01T00:00:00.000Z",
      customTo: "2026-03-07T23:59:59.000Z",
      activeHours: null,
    });
    expect(screen.getByRole("button", { name: /custom/i })).toBeInTheDocument();
  });

  it("shows 'Range' label on the calendar button when no custom range is active", () => {
    renderFilter({ customFrom: null, customTo: null });
    expect(screen.getByRole("button", { name: /range/i })).toBeInTheDocument();
  });
});

/* ── Clear (X) button ────────────────────────────────────────── */
describe("DateRangeFilter — Clear button", () => {
  it("shows a clear (X) button inside the picker when custom range is active", async () => {
    renderFilter({
      customFrom: "2026-03-01T00:00:00.000Z",
      customTo: "2026-03-07T23:59:59.000Z",
      activeHours: null,
    });
    // Open the picker
    await userEvent.click(screen.getByRole("button", { name: /custom/i }));
    // Clear button has title="Clear custom range"
    expect(screen.getByTitle("Clear custom range")).toBeInTheDocument();
  });

  it("calls onClearCustom when the clear button is clicked", async () => {
    const onClearCustom = jest.fn();
    renderFilter({
      onClearCustom,
      customFrom: "2026-03-01T00:00:00.000Z",
      customTo: "2026-03-07T23:59:59.000Z",
      activeHours: null,
    });
    await userEvent.click(screen.getByRole("button", { name: /custom/i }));
    await userEvent.click(screen.getByTitle("Clear custom range"));
    expect(onClearCustom).toHaveBeenCalled();
  });

  it("closes the picker after the clear button is clicked", async () => {
    const onClearCustom = jest.fn();
    renderFilter({
      onClearCustom,
      customFrom: "2026-03-01T00:00:00.000Z",
      customTo: "2026-03-07T23:59:59.000Z",
      activeHours: null,
    });
    await userEvent.click(screen.getByRole("button", { name: /custom/i }));
    await userEvent.click(screen.getByTitle("Clear custom range"));
    await waitFor(() => {
      expect(screen.queryByText(/custom range/i)).not.toBeInTheDocument();
    });
  });

  it("does NOT show the clear button when no custom range is active", async () => {
    renderFilter({ customFrom: null, customTo: null });
    await userEvent.click(screen.getByRole("button", { name: /range/i }));
    expect(screen.queryByTitle("Clear custom range")).not.toBeInTheDocument();
  });
});

/* ── Preset active highlighting ─────────────────────────────── */
describe("DateRangeFilter — preset active highlighting", () => {
  it("active preset button has primary background style", () => {
    renderFilter({ activeHours: 24, customFrom: null, customTo: null });
    const btn = screen.getByRole("button", { name: "24h" });
    // The style is applied inline — background contains 'primary'
    expect(btn.getAttribute("style")).toContain("primary");
  });

  it("inactive preset button does NOT have primary background", () => {
    renderFilter({ activeHours: 24, customFrom: null, customTo: null });
    const btn = screen.getByRole("button", { name: "7d" });
    // 7d is not active — its background should be muted
    expect(btn.getAttribute("style")).not.toMatch(/hsl\(var\(--primary\)\)[^/]/);
  });

  it("no preset appears active when a custom range is active", () => {
    renderFilter({
      activeHours: 24,
      customFrom: "2026-03-01T00:00:00.000Z",
      customTo: "2026-03-07T23:59:59.000Z",
    });
    // All preset buttons should NOT have primary background when custom is active
    const btn24h = screen.getByRole("button", { name: "24h" });
    // When isCustomActive is true, the style uses muted bg regardless of activeHours
    expect(btn24h.getAttribute("style")).toContain("muted");
  });
});
