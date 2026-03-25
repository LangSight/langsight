/**
 * Tests for the DateRangeFilter component.
 *
 * Covers:
 *   - Renders all 5 preset buttons (1h, 6h, 24h, 7d, 30d)
 *   - Clicking a preset calls onPreset with the correct hours value
 *   - Active preset is visually distinct (inline style reflects activeHours)
 *   - Inactive preset does not have primary background
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DateRangeFilter } from "@/components/date-range-filter";

const defaultProps = {
  activeHours: 24,
  onPreset: jest.fn(),
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
});

/* ── Preset active highlighting ─────────────────────────────── */
describe("DateRangeFilter — preset active highlighting", () => {
  it("active preset button has primary background style", () => {
    renderFilter({ activeHours: 24 });
    const btn = screen.getByRole("button", { name: "24h" });
    expect(btn.getAttribute("style")).toContain("primary");
  });

  it("inactive preset button does NOT have primary background", () => {
    renderFilter({ activeHours: 24 });
    const btn = screen.getByRole("button", { name: "7d" });
    expect(btn.getAttribute("style")).not.toMatch(/hsl\(var\(--primary\)\)[^/]/);
  });
});
