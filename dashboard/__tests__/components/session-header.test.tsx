/**
 * Tests for dashboard/components/sessions/session-header.tsx
 *
 * Covers:
 *   - Renders session ID in a <code> element
 *   - Renders agent name from trace spans
 *   - Renders span count and tool call stats from trace
 *   - Back button calls the onBack callback
 *   - Back button has correct label text
 *   - Failed call count renders in red when non-zero
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SessionHeader } from "@/components/sessions/session-header";
import type { AgentSession, SessionTrace, SpanNode } from "@/lib/types";

// Health tag badge just renders a span with the tag — mock it simply
jest.mock("@/components/health-tag-badge", () => ({
  HealthTagBadge: ({ tag }: { tag: string }) => (
    <span data-testid="health-tag">{tag}</span>
  ),
}));

// Timestamp renders relative time — mock to avoid Date flakiness
jest.mock("@/components/timestamp", () => ({
  Timestamp: ({ iso }: { iso: string }) => <time dateTime={iso}>{iso}</time>,
}));

/* ── Fixtures ─────────────────────────────────────────────────── */

function makeSpan(overrides: Partial<SpanNode> = {}): SpanNode {
  return {
    span_id: "span-1",
    parent_span_id: null,
    span_type: "tool_call",
    server_name: "pg",
    tool_name: "query",
    agent_name: "my-agent",
    started_at: "2026-01-01T00:00:00Z",
    ended_at: "2026-01-01T00:00:01Z",
    latency_ms: 100,
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
    finish_reason: null,
    cache_read_tokens: null,
    cache_creation_tokens: null,
    target_agent_name: null,
    lineage_provenance: "explicit" as const,
    lineage_status: "complete" as const,
    schema_version: "1.0",
    children: [],
    ...overrides,
  };
}

function makeTrace(overrides: Partial<SessionTrace> = {}): SessionTrace {
  const span = makeSpan();
  return {
    session_id: "sess-abc",
    spans_flat: [span],
    root_spans: [span],
    total_spans: 1,
    tool_calls: 1,
    failed_calls: 0,
    duration_ms: 1500,
    ...overrides,
  };
}

function makeSession(overrides: Partial<AgentSession> = {}): AgentSession {
  return {
    session_id: "sess-abc",
    agent_name: "my-agent",
    first_call_at: "2026-01-01T00:00:00Z",
    last_call_at: "2026-01-01T00:00:01Z",
    tool_calls: 1,
    failed_calls: 0,
    duration_ms: 1500,
    servers_used: ["pg"],
    health_tag: null,
    total_input_tokens: null,
    total_output_tokens: null,
    model_id: null,
    est_cost_usd: null,
    has_prompt: false,
    ...overrides,
  };
}

/* ── Tests ────────────────────────────────────────────────────── */

describe("SessionHeader — session ID", () => {
  it("renders the session ID in a code element", () => {
    render(
      <SessionHeader
        sessionId="sess-xyz-123"
        trace={null}
        session={undefined}
        onBack={jest.fn()}
      />
    );
    const code = screen.getByText("sess-xyz-123");
    expect(code.tagName.toLowerCase()).toBe("code");
  });
});

describe("SessionHeader — agent name", () => {
  it("renders agent name from trace spans when trace is provided", () => {
    const trace = makeTrace({ spans_flat: [makeSpan({ agent_name: "planner-agent" })] });
    render(
      <SessionHeader
        sessionId="s1"
        trace={trace}
        session={undefined}
        onBack={jest.fn()}
      />
    );
    expect(screen.getByText("planner-agent")).toBeInTheDocument();
  });

  it("falls back to session.agent_name when trace has no agent spans", () => {
    const trace = makeTrace({ spans_flat: [makeSpan({ agent_name: null })] });
    const session = makeSession({ agent_name: "fallback-agent" });
    render(
      <SessionHeader
        sessionId="s1"
        trace={trace}
        session={session}
        onBack={jest.fn()}
      />
    );
    expect(screen.getByText("fallback-agent")).toBeInTheDocument();
  });

  it("renders multiple agent names joined with arrow", () => {
    const trace = makeTrace({
      spans_flat: [
        makeSpan({ agent_name: "agent-a" }),
        makeSpan({ span_id: "span-2", agent_name: "agent-b" }),
      ],
    });
    render(
      <SessionHeader
        sessionId="s1"
        trace={trace}
        session={undefined}
        onBack={jest.fn()}
      />
    );
    expect(screen.getByText("agent-a → agent-b")).toBeInTheDocument();
  });
});

describe("SessionHeader — timing stats", () => {
  it("renders span count from trace", () => {
    const trace = makeTrace({ total_spans: 7 });
    render(
      <SessionHeader
        sessionId="s1"
        trace={trace}
        session={undefined}
        onBack={jest.fn()}
      />
    );
    expect(screen.getByText("7 spans")).toBeInTheDocument();
  });

  it("renders tool call count from trace", () => {
    const trace = makeTrace({ tool_calls: 3 });
    render(
      <SessionHeader
        sessionId="s1"
        trace={trace}
        session={undefined}
        onBack={jest.fn()}
      />
    );
    expect(screen.getByText("3 calls")).toBeInTheDocument();
  });

  it("renders singular 'call' label when tool_calls is 1", () => {
    const trace = makeTrace({ tool_calls: 1 });
    render(
      <SessionHeader
        sessionId="s1"
        trace={trace}
        session={undefined}
        onBack={jest.fn()}
      />
    );
    expect(screen.getByText("1 call")).toBeInTheDocument();
  });

  it("renders failed call count when greater than zero", () => {
    const trace = makeTrace({ failed_calls: 2 });
    render(
      <SessionHeader
        sessionId="s1"
        trace={trace}
        session={undefined}
        onBack={jest.fn()}
      />
    );
    expect(screen.getByText("2 failed")).toBeInTheDocument();
  });

  it("does not render failed count when failed_calls is 0", () => {
    const trace = makeTrace({ failed_calls: 0 });
    render(
      <SessionHeader
        sessionId="s1"
        trace={trace}
        session={undefined}
        onBack={jest.fn()}
      />
    );
    expect(screen.queryByText(/failed/)).not.toBeInTheDocument();
  });
});

describe("SessionHeader — back button", () => {
  it("renders 'Back to Sessions' text", () => {
    render(
      <SessionHeader
        sessionId="s1"
        trace={null}
        session={undefined}
        onBack={jest.fn()}
      />
    );
    expect(screen.getByText("Back to Sessions")).toBeInTheDocument();
  });

  it("calls onBack when the back button is clicked", async () => {
    const onBack = jest.fn();
    render(
      <SessionHeader
        sessionId="s1"
        trace={null}
        session={undefined}
        onBack={onBack}
      />
    );
    await userEvent.click(screen.getByText("Back to Sessions"));
    expect(onBack).toHaveBeenCalledTimes(1);
  });
});
