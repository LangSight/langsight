/**
 * Tests for dashboard/components/sessions/span-tree.tsx
 *
 * Covers:
 *   SpanRow    — renders tool name and status badge; collapse hides children
 *   SpanTree   — renders root spans; shows loading/error/empty states
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SpanRow, SpanTree } from "@/components/sessions/span-tree";
import type { SpanNode, SessionTrace } from "@/lib/types";

// Timestamp mock to avoid Date flakiness
jest.mock("@/components/timestamp", () => ({
  Timestamp: ({ iso }: { iso: string }) => <time dateTime={iso}>{iso}</time>,
}));

/* ── Fixtures ─────────────────────────────────────────────────── */

function makeSpan(overrides: Partial<SpanNode> = {}): SpanNode {
  return {
    span_id: "span-root",
    parent_span_id: null,
    span_type: "tool_call",
    server_name: "pg",
    tool_name: "query",
    agent_name: "agent-1",
    started_at: "2026-01-01T00:00:00Z",
    ended_at: "2026-01-01T00:00:01Z",
    latency_ms: 50,
    status: "success",
    error: null,
    trace_id: null,
    input_json: null,
    output_json: null,
    llm_input: null,
    llm_output: null,
    input_tokens: null,
    output_tokens: null,
    model_id: null,
    target_agent_name: null,
    lineage_provenance: "explicit" as const,
    lineage_status: "complete" as const,
    schema_version: "1.0",
    children: [],
    ...overrides,
  };
}

function makeTrace(overrides: Partial<SessionTrace> = {}): SessionTrace {
  const root = makeSpan();
  return {
    session_id: "sess-1",
    spans_flat: [root],
    root_spans: [root],
    total_spans: 1,
    tool_calls: 1,
    failed_calls: 0,
    duration_ms: 50,
    ...overrides,
  };
}

/* ── SpanRow ──────────────────────────────────────────────────── */

describe("SpanRow — tool name", () => {
  it("renders server_name/tool_name in the row", () => {
    render(
      <table>
        <tbody>
          <SpanRow span={makeSpan({ server_name: "postgres", tool_name: "list_tables" })} />
        </tbody>
      </table>
    );
    expect(screen.getByText("postgres/list_tables")).toBeInTheDocument();
  });
});

describe("SpanRow — status badge", () => {
  it("shows 'success' badge for success status", () => {
    render(
      <table>
        <tbody>
          <SpanRow span={makeSpan({ status: "success" })} />
        </tbody>
      </table>
    );
    expect(screen.getByText("success")).toBeInTheDocument();
  });

  it("shows 'error' badge for error status", () => {
    render(
      <table>
        <tbody>
          <SpanRow span={makeSpan({ status: "error" })} />
        </tbody>
      </table>
    );
    expect(screen.getByText("error")).toBeInTheDocument();
  });

  it("shows 'prevented' badge for prevented status", () => {
    render(
      <table>
        <tbody>
          <SpanRow span={makeSpan({ status: "prevented" })} />
        </tbody>
      </table>
    );
    expect(screen.getByText("prevented")).toBeInTheDocument();
  });

  it("shows 'timeout' badge for timeout status", () => {
    render(
      <table>
        <tbody>
          <SpanRow span={makeSpan({ status: "timeout" })} />
        </tbody>
      </table>
    );
    expect(screen.getByText("timeout")).toBeInTheDocument();
  });
});

describe("SpanRow — collapsed children", () => {
  it("renders children by default when a span has children", () => {
    const child = makeSpan({ span_id: "child-1", tool_name: "insert", parent_span_id: "span-root" });
    const parent = makeSpan({ children: [child] });

    render(
      <table>
        <tbody>
          <SpanRow span={parent} />
        </tbody>
      </table>
    );
    // child's server/tool should be visible (expanded by default)
    expect(screen.getByText("pg/insert")).toBeInTheDocument();
  });

  it("hides children after clicking the collapse toggle", async () => {
    const child = makeSpan({ span_id: "child-1", tool_name: "insert", parent_span_id: "span-root" });
    const parent = makeSpan({ span_id: "span-root", children: [child] });

    render(
      <table>
        <tbody>
          <SpanRow span={parent} />
        </tbody>
      </table>
    );

    // Child is visible before collapse
    expect(screen.getByText("pg/insert")).toBeInTheDocument();

    // The expand button has aria-expanded=true when open; click it to collapse
    const toggle = screen.getByRole("button", { expanded: true });
    await userEvent.click(toggle);

    // Child should no longer be visible after collapsing
    expect(screen.queryByText("pg/insert")).not.toBeInTheDocument();
  });

  it("does not render children when span has no children", () => {
    const parent = makeSpan({ children: [] });
    render(
      <table>
        <tbody>
          <SpanRow span={parent} />
        </tbody>
      </table>
    );
    // There's only one row rendered; no extra tool names
    const cells = screen.getAllByText("pg/query");
    expect(cells).toHaveLength(1);
  });
});

/* ── SpanTree ─────────────────────────────────────────────────── */

describe("SpanTree — loading state", () => {
  it("renders a spinner when loading=true and no trace", () => {
    const { container } = render(
      <SpanTree trace={null} loading error={null} onViewPayload={jest.fn()} />
    );
    // The spinning div is present
    expect(container.querySelector(".spin")).toBeInTheDocument();
  });
});

describe("SpanTree — error state", () => {
  it("renders the error message", () => {
    render(
      <SpanTree
        trace={null}
        loading={false}
        error="Failed to load trace"
        onViewPayload={jest.fn()}
      />
    );
    expect(screen.getByText("Failed to load trace")).toBeInTheDocument();
  });
});

describe("SpanTree — empty state", () => {
  it("shows 'No spans found' when trace has no root spans", () => {
    const emptyTrace = makeTrace({ root_spans: [], spans_flat: [] });
    render(
      <SpanTree
        trace={emptyTrace}
        loading={false}
        error={null}
        onViewPayload={jest.fn()}
      />
    );
    expect(screen.getByText("No spans found")).toBeInTheDocument();
  });
});

describe("SpanTree — renders root spans", () => {
  it("renders a row for each root span", () => {
    const trace = makeTrace({
      root_spans: [
        makeSpan({ span_id: "r1", tool_name: "query" }),
        makeSpan({ span_id: "r2", server_name: "s3", tool_name: "list_objects" }),
      ],
    });
    render(
      <SpanTree trace={trace} loading={false} error={null} onViewPayload={jest.fn()} />
    );
    expect(screen.getByText("pg/query")).toBeInTheDocument();
    expect(screen.getByText("s3/list_objects")).toBeInTheDocument();
  });

  it("renders the column headers", () => {
    const trace = makeTrace();
    render(
      <SpanTree trace={trace} loading={false} error={null} onViewPayload={jest.fn()} />
    );
    expect(screen.getByText("Span")).toBeInTheDocument();
    expect(screen.getByText("Status")).toBeInTheDocument();
    expect(screen.getByText("Latency")).toBeInTheDocument();
  });
});
