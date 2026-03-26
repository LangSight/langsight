/**
 * Tests for dashboard/components/sessions/session-metrics.tsx
 *
 * Covers:
 *   MetricTile  — renders label + value; danger styling when danger=true
 *   SectionLabel — renders children text
 */

import { render, screen } from "@testing-library/react";
import { MetricTile, SectionLabel } from "@/components/sessions/session-metrics";

/* ── MetricTile ───────────────────────────────────────────────── */

describe("MetricTile", () => {
  it("renders the label text", () => {
    render(<MetricTile label="Duration" value="1.5s" />);
    expect(screen.getByText("Duration")).toBeInTheDocument();
  });

  it("renders the value text", () => {
    render(<MetricTile label="Duration" value="1.5s" />);
    expect(screen.getByText("1.5s")).toBeInTheDocument();
  });

  it("applies default foreground colour when danger is not set", () => {
    render(<MetricTile label="Errors" value="0" />);
    const valueEl = screen.getByText("0");
    // Without danger the element must NOT have the red colour class
    expect(valueEl).not.toHaveClass("text-red-500");
  });

  it("applies red colour class when danger=true", () => {
    render(<MetricTile label="Errors" value="3" danger />);
    const valueEl = screen.getByText("3");
    expect(valueEl).toHaveClass("text-red-500");
  });

  it("does not apply red colour when danger=false explicitly", () => {
    render(<MetricTile label="Errors" value="0" danger={false} />);
    const valueEl = screen.getByText("0");
    expect(valueEl).not.toHaveClass("text-red-500");
  });
});

/* ── SectionLabel ─────────────────────────────────────────────── */

describe("SectionLabel", () => {
  it("renders the children text", () => {
    render(<SectionLabel>Overview</SectionLabel>);
    expect(screen.getByText("Overview")).toBeInTheDocument();
  });

  it("renders different children text", () => {
    render(<SectionLabel>Agents</SectionLabel>);
    expect(screen.getByText("Agents")).toBeInTheDocument();
  });
});
