/**
 * Tests for dashboard/components/ui/chart-primitives.tsx
 *
 * Covers:
 *   StatCard  — label, value, optional trend
 *   ChartCard — title + role="img" + aria-label
 *   ChartTooltip — label and value rendering
 *   TrendBadge — up/down arrow + correct colour
 *
 * Also covers the D9 regression: chart containers must carry role="img" with a
 * non-empty aria-label so screen readers can navigate past chart noise.
 */

import { render, screen } from "@testing-library/react";
import { Activity } from "lucide-react";
import {
  StatCard,
  ChartCard,
  ChartTooltip,
  TrendBadge,
} from "@/components/ui/chart-primitives";

/* ── StatCard ─────────────────────────────────────────────────────────────── */

describe("StatCard", () => {
  const baseProps = {
    label: "Sessions",
    value: 42,
    icon: Activity,
    color: "#14b8a6",
  };

  it("renders the label", () => {
    render(<StatCard {...baseProps} />);
    expect(screen.getByText("Sessions")).toBeInTheDocument();
  });

  it("renders the numeric value", () => {
    render(<StatCard {...baseProps} />);
    expect(screen.getByText("42")).toBeInTheDocument();
  });

  it("renders a string value", () => {
    render(<StatCard {...baseProps} value="1.2k" />);
    expect(screen.getByText("1.2k")).toBeInTheDocument();
  });

  it("renders optional sub-text when provided", () => {
    render(<StatCard {...baseProps} sub="last 24h" />);
    expect(screen.getByText("last 24h")).toBeInTheDocument();
  });

  it("does not render sub section when sub is omitted", () => {
    const { container } = render(<StatCard {...baseProps} />);
    // The sub paragraph is conditionally rendered — its text must not appear
    expect(container.querySelector("p.text-muted-foreground") ?? null).toBeNull();
  });

  it("renders the trend child when provided", () => {
    render(<StatCard {...baseProps} trend={<span data-testid="trend">↑5%</span>} />);
    expect(screen.getByTestId("trend")).toBeInTheDocument();
  });

  it("does not render a trend node when omitted", () => {
    render(<StatCard {...baseProps} />);
    expect(screen.queryByTestId("trend")).not.toBeInTheDocument();
  });
});

/* ── ChartCard ────────────────────────────────────────────────────────────── */

describe("ChartCard", () => {
  it("renders the title text", () => {
    render(<ChartCard title="Agent Runs"><div /></ChartCard>);
    expect(screen.getByText("Agent Runs")).toBeInTheDocument();
  });

  it("renders children inside the card", () => {
    render(
      <ChartCard title="Latency">
        <span data-testid="chart-child">chart</span>
      </ChartCard>
    );
    expect(screen.getByTestId("chart-child")).toBeInTheDocument();
  });

  // D9 regression: chart containers must have role="img" + non-empty aria-label
  it("has role='img' on the chart container (D9 ARIA regression)", () => {
    render(<ChartCard title="Error Rate"><div /></ChartCard>);
    const chartContainer = screen.getByRole("img");
    expect(chartContainer).toBeInTheDocument();
  });

  it("uses title as aria-label when ariaLabel prop is not given (D9)", () => {
    render(<ChartCard title="Token Usage"><div /></ChartCard>);
    const img = screen.getByRole("img");
    expect(img).toHaveAttribute("aria-label", "Token Usage");
  });

  it("uses the explicit ariaLabel prop when given (D9)", () => {
    render(
      <ChartCard title="Latency (p99)" ariaLabel="Line chart showing p99 latency">
        <div />
      </ChartCard>
    );
    const img = screen.getByRole("img");
    expect(img).toHaveAttribute("aria-label", "Line chart showing p99 latency");
  });

  it("aria-label is not empty (D9 non-empty requirement)", () => {
    render(<ChartCard title="Sessions"><div /></ChartCard>);
    const img = screen.getByRole("img");
    const label = img.getAttribute("aria-label") ?? "";
    expect(label.length).toBeGreaterThan(0);
  });
});

/* ── ChartTooltip ─────────────────────────────────────────────────────────── */

describe("ChartTooltip", () => {
  const singlePayload = [{ value: 123, name: "Sessions", color: "#14b8a6" }];

  it("renders nothing when active is false", () => {
    const { container } = render(
      <ChartTooltip active={false} payload={singlePayload} label="Mon" />
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing when payload is empty", () => {
    const { container } = render(
      <ChartTooltip active payload={[]} label="Mon" />
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders the label when active with payload", () => {
    render(<ChartTooltip active payload={singlePayload} label="Monday" />);
    expect(screen.getByText("Monday")).toBeInTheDocument();
  });

  it("renders the series name", () => {
    render(<ChartTooltip active payload={singlePayload} label="Mon" />);
    expect(screen.getByText("Sessions:")).toBeInTheDocument();
  });

  it("renders the numeric value with toLocaleString", () => {
    render(<ChartTooltip active payload={singlePayload} label="Mon" />);
    // 123 → "123" (locale-dependent but always a string)
    expect(screen.getByText("123")).toBeInTheDocument();
  });

  it("uses formatter when provided", () => {
    render(
      <ChartTooltip
        active
        payload={[{ value: 0.042, name: "Error Rate", color: "#ef4444" }]}
        label="Tue"
        formatter={(v) => `${(v * 100).toFixed(1)}%`}
      />
    );
    expect(screen.getByText("4.2%")).toBeInTheDocument();
  });

  it("renders multiple payload entries", () => {
    const multiPayload = [
      { value: 10, name: "Input", color: "#0ea5e9" },
      { value: 5, name: "Output", color: "#14b8a6" },
    ];
    render(<ChartTooltip active payload={multiPayload} label="Wed" />);
    expect(screen.getByText("Input:")).toBeInTheDocument();
    expect(screen.getByText("Output:")).toBeInTheDocument();
  });
});

/* ── TrendBadge ───────────────────────────────────────────────────────────── */

describe("TrendBadge", () => {
  it("renders nothing when pct is null", () => {
    const { container } = render(<TrendBadge pct={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing when pct is 0", () => {
    const { container } = render(<TrendBadge pct={0} />);
    expect(container.firstChild).toBeNull();
  });

  it("shows an up arrow for positive pct", () => {
    render(<TrendBadge pct={12.5} />);
    expect(screen.getByText(/↑.*12\.5%/)).toBeInTheDocument();
  });

  it("shows a down arrow for negative pct", () => {
    render(<TrendBadge pct={-7.3} />);
    expect(screen.getByText(/↓.*7\.3%/)).toBeInTheDocument();
  });

  it("is red (bad) for positive pct without invert", () => {
    render(<TrendBadge pct={5} />);
    const badge = screen.getByText(/↑.*5\.0%/);
    expect(badge).toHaveStyle({ color: "#ef4444" });
  });

  it("is green (good) for negative pct without invert", () => {
    render(<TrendBadge pct={-5} />);
    const badge = screen.getByText(/↓.*5\.0%/);
    expect(badge).toHaveStyle({ color: "#22c55e" });
  });

  it("inverts colour logic when invert=true — positive pct is green", () => {
    render(<TrendBadge pct={5} invert />);
    const badge = screen.getByText(/↑.*5\.0%/);
    expect(badge).toHaveStyle({ color: "#22c55e" });
  });

  it("inverts colour logic when invert=true — negative pct is red", () => {
    render(<TrendBadge pct={-5} invert />);
    const badge = screen.getByText(/↓.*5\.0%/);
    expect(badge).toHaveStyle({ color: "#ef4444" });
  });

  it("shows 'vs last 7d' suffix", () => {
    render(<TrendBadge pct={3} />);
    expect(screen.getByText(/vs last 7d/)).toBeInTheDocument();
  });
});
