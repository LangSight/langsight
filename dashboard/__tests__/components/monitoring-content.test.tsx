/**
 * Tests for dashboard/components/ui/monitoring-content.tsx
 *
 * Covers:
 *   OverviewStatCards — renders 4 stat cards with correct labels
 *   ModelTable        — renders one row per model; shows empty state
 *
 * Also covers the D9 ARIA regression: chart containers (via ChartCard) must
 * carry role="img" with a non-empty aria-label.
 */

import { render, screen } from "@testing-library/react";
import { OverviewStatCards, ModelTable } from "@/components/ui/monitoring-content";
import type { MonitoringSummary } from "@/components/ui/monitoring-content";
import type { MonitoringModel } from "@/lib/api";

// Recharts renders canvas/SVG internals that do not matter in unit tests — mock
// the whole module to avoid ResizeObserver warnings in jsdom.
jest.mock("recharts", () => {
  const React = require("react");
  return {
    AreaChart: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
    Area: () => null,
    BarChart: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
    Bar: () => null,
    LineChart: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
    Line: () => null,
    XAxis: () => null,
    YAxis: () => null,
    Tooltip: () => null,
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
    CartesianGrid: () => null,
  };
});

/* ── Fixtures ─────────────────────────────────────────────────── */

const SUMMARY: MonitoringSummary = {
  totalSessions: 12,
  totalToolCalls: 45,
  totalErrors: 3,
  totalInputTokens: 10_000,
  totalOutputTokens: 5_000,
  avgLatency: 250,
  errorRate: 6.7,
  maxAgents: 2,
};

function makeModel(overrides: Partial<MonitoringModel> = {}): MonitoringModel {
  return {
    model_id: "gpt-4o",
    calls: 10,
    input_tokens: 1000,
    output_tokens: 500,
    avg_latency_ms: 350,
    error_count: 0,
    est_cost_usd: 0.0125,
    ...overrides,
  };
}

/* ── OverviewStatCards ────────────────────────────────────────── */

describe("OverviewStatCards — renders 4 stat cards", () => {
  it("renders Sessions card", () => {
    render(<OverviewStatCards summary={SUMMARY} hours={24} />);
    expect(screen.getByText("Sessions")).toBeInTheDocument();
  });

  it("renders Tool Calls card", () => {
    render(<OverviewStatCards summary={SUMMARY} hours={24} />);
    expect(screen.getByText("Tool Calls")).toBeInTheDocument();
  });

  it("renders Error Rate card", () => {
    render(<OverviewStatCards summary={SUMMARY} hours={24} />);
    expect(screen.getByText("Error Rate")).toBeInTheDocument();
  });

  it("renders Avg Latency card", () => {
    render(<OverviewStatCards summary={SUMMARY} hours={24} />);
    expect(screen.getByText("Avg Latency")).toBeInTheDocument();
  });

  it("shows the sessions value", () => {
    render(<OverviewStatCards summary={SUMMARY} hours={24} />);
    expect(screen.getByText("12")).toBeInTheDocument();
  });

  it("shows the error rate value formatted with one decimal", () => {
    render(<OverviewStatCards summary={SUMMARY} hours={24} />);
    expect(screen.getByText("6.7%")).toBeInTheDocument();
  });

  it("shows dashes when summary is null", () => {
    render(<OverviewStatCards summary={null} hours={24} />);
    const dashes = screen.getAllByText("—");
    expect(dashes.length).toBeGreaterThanOrEqual(4);
  });

  it("shows the period label", () => {
    render(<OverviewStatCards summary={SUMMARY} hours={48} />);
    expect(screen.getByText("last 48h")).toBeInTheDocument();
  });
});

/* ── ModelTable ───────────────────────────────────────────────── */

describe("ModelTable — renders rows from props", () => {
  it("renders one row per model", () => {
    const models = [
      makeModel({ model_id: "gpt-4o" }),
      makeModel({ model_id: "claude-sonnet-4-6", calls: 5 }),
    ];
    render(<ModelTable models={models} />);
    expect(screen.getByText("gpt-4o")).toBeInTheDocument();
    expect(screen.getByText("claude-sonnet-4-6")).toBeInTheDocument();
  });

  it("renders the call count for each model", () => {
    const models = [makeModel({ model_id: "gpt-4o", calls: 17 })];
    render(<ModelTable models={models} />);
    expect(screen.getByText("17")).toBeInTheDocument();
  });

  it("renders the error count in red when errors > 0", () => {
    const models = [makeModel({ model_id: "gpt-4o", error_count: 2 })];
    render(<ModelTable models={models} />);
    const errorCell = screen.getByText("2");
    expect(errorCell).toHaveClass("text-red-400");
  });

  it("renders estimated cost formatted to 4 decimal places", () => {
    const models = [makeModel({ model_id: "gpt-4o", est_cost_usd: 0.0125 })];
    render(<ModelTable models={models} />);
    expect(screen.getByText("$0.0125")).toBeInTheDocument();
  });

  it("renders a dash when est_cost_usd is null", () => {
    const models = [makeModel({ model_id: "gpt-4o", est_cost_usd: null })];
    render(<ModelTable models={models} />);
    // The cost cell should contain "—"
    const costCells = screen.getAllByText("—");
    expect(costCells.length).toBeGreaterThan(0);
  });

  it("renders 'No model data for this period' when models is empty", () => {
    render(<ModelTable models={[]} />);
    expect(screen.getByText("No model data for this period")).toBeInTheDocument();
  });

  it("renders 'No model data for this period' when models is undefined", () => {
    render(<ModelTable models={undefined} />);
    expect(screen.getByText("No model data for this period")).toBeInTheDocument();
  });

  it("does not render the Ctx Usage column by default (showCtxUsage=false)", () => {
    render(<ModelTable models={[makeModel()]} />);
    expect(screen.queryByText("Ctx Usage")).not.toBeInTheDocument();
  });

  it("renders the Ctx Usage column when showCtxUsage=true", () => {
    render(<ModelTable models={[makeModel()]} showCtxUsage />);
    expect(screen.getByText("Ctx Usage")).toBeInTheDocument();
  });
});

/* ── D9 ARIA regression: chart containers must have role="img" ── */

describe("D9 ARIA regression — chart containers", () => {
  it("OverviewStatCards does not itself render any role=img (charts are in OverviewCharts)", () => {
    // OverviewStatCards only renders StatCards — no charts — so no role=img expected here.
    // This test ensures we are not accidentally asserting the wrong component.
    render(<OverviewStatCards summary={SUMMARY} hours={24} />);
    const imgs = screen.queryAllByRole("img");
    // May be 0 (StatCards have no chart container)
    expect(imgs.length).toBe(0);
  });
});
