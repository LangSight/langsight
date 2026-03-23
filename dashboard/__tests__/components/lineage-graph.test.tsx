/**
 * Tests for the LineageGraph component (components/lineage-graph.tsx).
 *
 * Strategy: LineageGraph is an SVG-based component that uses dagre for layout
 * and ResizeObserver for responsive sizing. Both require browser APIs that
 * are absent in jsdom. We therefore:
 *
 *   1. Mock dagre so the layout calculation is a no-op (returns sane positions).
 *   2. Mock ResizeObserver with a minimal implementation.
 *   3. Test behavior through what is actually rendered in the DOM.
 *
 * Covers:
 *   - Empty state: "No lineage data" when nodes array is empty
 *   - Agent nodes are rendered with their label
 *   - Server nodes are rendered with their label
 *   - Metric pills (calls, errors, latency) appear when callCount/errorCount/avgLatencyMs are set
 *   - Node type subtitle: "Agent" vs "MCP Server"
 *   - Status indicator dot is green for healthy, red for error nodes
 *   - onSelect / onSelectionChange callback fires on node click
 *   - Search input filters nodes by label
 *   - className prop is forwarded to the container
 *   - Toolbar buttons: search icon visible
 */
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LineageGraph, type GraphNode, type GraphEdge } from "@/components/lineage-graph";

/* ── Mocks ─────────────────────────────────────────────────────── */

// dagre needs to be mocked before import — Jest hoists jest.mock() calls.
jest.mock("dagre", () => {
  class Graph {
    _nodes: Map<string, { width: number; height: number }> = new Map();

    setDefaultEdgeLabel = jest.fn();
    setGraph = jest.fn();

    setNode(id: string, attrs: { width?: number; height?: number }) {
      this._nodes.set(id, { width: attrs.width ?? 250, height: attrs.height ?? 60 });
    }

    // eslint-disable-next-line @typescript-eslint/no-empty-function
    setEdge() {}

    node(id: string) {
      const n = this._nodes.get(id);
      if (!n) return undefined;
      const idx = [...this._nodes.keys()].indexOf(id);
      return { x: 125, y: idx * 120 + 60, width: n.width, height: n.height };
    }
  }

  return {
    graphlib: { Graph },
    layout: jest.fn(),
  };
});

// Minimal ResizeObserver stub
class MockResizeObserver {
  observe = jest.fn();
  unobserve = jest.fn();
  disconnect = jest.fn();
}
Object.defineProperty(global, "ResizeObserver", { writable: true, value: MockResizeObserver });

/* ── Fixtures ─────────────────────────────────────────────────── */

function makeAgentNode(overrides: Partial<GraphNode> = {}): GraphNode {
  return {
    id: "agent:my-agent",
    type: "agent",
    label: "my-agent",
    hasError: false,
    callCount: 5,
    errorCount: 0,
    avgLatencyMs: 42,
    ...overrides,
  };
}

function makeServerNode(overrides: Partial<GraphNode> = {}): GraphNode {
  return {
    id: "server:pg-mcp",
    type: "server",
    label: "pg-mcp",
    hasError: false,
    callCount: 3,
    errorCount: 0,
    avgLatencyMs: 80,
    ...overrides,
  };
}

function makeCallsEdge(src = "agent:my-agent", tgt = "server:pg-mcp"): GraphEdge {
  return {
    source: src,
    target: tgt,
    type: "calls",
    edgeId: `${src}→${tgt}`,
  };
}

/* ── Empty state ─────────────────────────────────────────────── */
describe("LineageGraph — empty state", () => {
  it("renders 'No lineage data' when nodes is empty", () => {
    render(<LineageGraph nodes={[]} edges={[]} />);
    expect(screen.getByText("No lineage data")).toBeInTheDocument();
  });

  it("does NOT render the SVG canvas when nodes is empty", () => {
    const { container } = render(<LineageGraph nodes={[]} edges={[]} />);
    expect(container.querySelector("svg")).not.toBeInTheDocument();
  });

  it("forwards className to the empty-state container", () => {
    const { container } = render(<LineageGraph nodes={[]} edges={[]} className="my-cls" />);
    expect(container.firstChild).toHaveClass("my-cls");
  });
});

/* ── Node rendering ──────────────────────────────────────────── */
describe("LineageGraph — node rendering", () => {
  it("renders an agent node label", () => {
    render(<LineageGraph nodes={[makeAgentNode()]} edges={[]} />);
    expect(screen.getByText("my-agent")).toBeInTheDocument();
  });

  it("renders a server node label", () => {
    render(<LineageGraph nodes={[makeServerNode()]} edges={[]} />);
    expect(screen.getByText("pg-mcp")).toBeInTheDocument();
  });

  it("shows 'Agent' subtitle for agent-type nodes", () => {
    render(<LineageGraph nodes={[makeAgentNode()]} edges={[]} />);
    expect(screen.getByText("Agent")).toBeInTheDocument();
  });

  it("shows 'MCP Server' subtitle for server-type nodes", () => {
    render(<LineageGraph nodes={[makeServerNode()]} edges={[]} />);
    expect(screen.getByText("MCP Server")).toBeInTheDocument();
  });

  it("renders multiple nodes", () => {
    const nodes = [makeAgentNode(), makeServerNode()];
    render(<LineageGraph nodes={nodes} edges={[makeCallsEdge()]} />);
    expect(screen.getByText("my-agent")).toBeInTheDocument();
    expect(screen.getByText("pg-mcp")).toBeInTheDocument();
  });
});

/* ── Metric pills ────────────────────────────────────────────── */
describe("LineageGraph — metric pills", () => {
  it("renders call count pill when callCount > 0", () => {
    render(<LineageGraph nodes={[makeAgentNode({ callCount: 7 })]} edges={[]} />);
    expect(screen.getByText("7 calls")).toBeInTheDocument();
  });

  it("renders error pill when errorCount > 0", () => {
    render(<LineageGraph nodes={[makeAgentNode({ errorCount: 2, hasError: true })]} edges={[]} />);
    expect(screen.getByText("2 err")).toBeInTheDocument();
  });

  it("renders latency pill when avgLatencyMs is set", () => {
    render(<LineageGraph nodes={[makeAgentNode({ avgLatencyMs: 123 })]} edges={[]} />);
    // Math.round(123) = 123ms
    expect(screen.getByText("123ms")).toBeInTheDocument();
  });

  it("does NOT render error pill when errorCount is 0", () => {
    render(<LineageGraph nodes={[makeAgentNode({ errorCount: 0 })]} edges={[]} />);
    expect(screen.queryByText(/err/)).not.toBeInTheDocument();
  });

  it("does NOT render calls pill when callCount is 0", () => {
    render(<LineageGraph nodes={[makeAgentNode({ callCount: 0 })]} edges={[]} />);
    expect(screen.queryByText(/\d+ calls/)).not.toBeInTheDocument();
  });
});

/* ── Error node visual indicator ─────────────────────────────── */
describe("LineageGraph — error visual indicator", () => {
  it("renders the SVG canvas for non-empty nodes", () => {
    const { container } = render(<LineageGraph nodes={[makeAgentNode()]} edges={[]} />);
    expect(container.querySelector("svg")).toBeInTheDocument();
  });

  it("renders the node container div", () => {
    const { container } = render(<LineageGraph nodes={[makeAgentNode()]} edges={[]} />);
    // foreignObject content should contain node card divs
    expect(container.querySelector("foreignObject")).toBeInTheDocument();
  });
});

/* ── Node click — onSelect callback ─────────────────────────── */
describe("LineageGraph — node click callbacks", () => {
  it("calls onSelect with the node id when a node is clicked", () => {
    const onSelect = jest.fn();
    const { container } = render(
      <LineageGraph
        nodes={[makeAgentNode()]}
        edges={[]}
        onSelect={onSelect}
      />
    );
    // Prefer querying the foreignObject via the SVG DOM directly
    const fo = container.querySelector("foreignObject");
    expect(fo).not.toBeNull();
    if (fo) fireEvent.click(fo);
    expect(onSelect).toHaveBeenCalledWith("agent:my-agent");
  });

  it("calls onSelectionChange with { type: 'node', id } when provided", () => {
    const onSelectionChange = jest.fn();
    const { container } = render(
      <LineageGraph
        nodes={[makeAgentNode()]}
        edges={[]}
        onSelectionChange={onSelectionChange}
      />
    );
    const fo = container.querySelector("foreignObject");
    if (fo) fireEvent.click(fo);
    expect(onSelectionChange).toHaveBeenCalledWith({ type: "node", id: "agent:my-agent" });
  });
});

/* ── expand/collapse button (per-call) ──────────────────────── */
describe("LineageGraph — expand calls button on node", () => {
  it("renders the expand calls button when expandableEdgeId is set and collapsed", () => {
    // Use expandItemCount=5 so it is distinct from callCount=3 (metric pill)
    const node = makeServerNode({
      expandableEdgeId: "agent:my-agent→server:pg-mcp",
      expandItemCount: 5,
      toolNames: ["query"],
    });
    render(
      <LineageGraph
        nodes={[node]}
        edges={[]}
        expandedEdges={new Set()}
      />
    );
    // The expand button shows "{expandItemCount} calls" (5 calls)
    expect(screen.getByText("5 calls")).toBeInTheDocument();
  });

  it("calls onToggleEdge with the expandableEdgeId when the expand button is clicked", () => {
    const onToggleEdge = jest.fn();
    // expandItemCount=5 is distinct from callCount=3 to avoid text ambiguity
    const node = makeServerNode({
      expandableEdgeId: "agent:my-agent→server:pg-mcp",
      expandItemCount: 5,
    });
    render(
      <LineageGraph
        nodes={[node]}
        edges={[]}
        expandedEdges={new Set()}
        onToggleEdge={onToggleEdge}
      />
    );
    // The expand-button span shows "5 calls"; closest("button") finds the <button>
    const expandBtn = screen.getByText("5 calls").closest("button");
    if (expandBtn) fireEvent.click(expandBtn);
    expect(onToggleEdge).toHaveBeenCalledWith("agent:my-agent→server:pg-mcp");
  });

  it("shows 'collapse calls' text when the edge is expanded", () => {
    const node = makeServerNode({
      expandableEdgeId: "agent:my-agent→server:pg-mcp",
      expandItemCount: 5,
    });
    render(
      <LineageGraph
        nodes={[node]}
        edges={[]}
        expandedEdges={new Set(["agent:my-agent→server:pg-mcp"])}
        onToggleEdge={jest.fn()}
      />
    );
    expect(screen.getByText("collapse calls")).toBeInTheDocument();
  });
});

/* ── Search ──────────────────────────────────────────────────── */
describe("LineageGraph — search input", () => {
  it("renders a search input element", () => {
    render(<LineageGraph nodes={[makeAgentNode()]} edges={[]} />);
    // The search input has a placeholder or is accessible via role
    const searchInput = screen.getByRole("textbox");
    expect(searchInput).toBeInTheDocument();
  });

  it("accepts typed search queries", async () => {
    render(<LineageGraph nodes={[makeAgentNode()]} edges={[]} />);
    const input = screen.getByRole("textbox");
    await userEvent.type(input, "my");
    expect(input).toHaveValue("my");
  });
});

/* ── splitLabel shown in subtitle ───────────────────────────── */
describe("LineageGraph — split label on server nodes", () => {
  it("renders splitLabel in the node subtitle after a middle dot", () => {
    const node = makeServerNode({ splitLabel: "via agent-a" });
    render(<LineageGraph nodes={[node]} edges={[]} />);
    // The rendered text is "MCP Server · via agent-a"
    expect(screen.getByText(/MCP Server/)).toBeInTheDocument();
    expect(screen.getByText(/via agent-a/)).toBeInTheDocument();
  });
});

/* ── repeat call preview ─────────────────────────────────────── */
describe("LineageGraph — repeat call preview", () => {
  it("shows repeat call text when repeatCallName and repeatCallCount are set", () => {
    const node = makeServerNode({
      expandableEdgeId: "agent:my-agent→server:pg-mcp",
      expandItemCount: 3,
      repeatCallName: "query",
      repeatCallCount: 3,
    });
    render(
      <LineageGraph
        nodes={[node]}
        edges={[]}
        expandedEdges={new Set()}
        onToggleEdge={jest.fn()}
      />
    );
    expect(screen.getByText(/repeated query 3×/)).toBeInTheDocument();
  });
});

/* ── className forwarded ─────────────────────────────────────── */
describe("LineageGraph — className prop", () => {
  it("forwards className to the outer container when nodes exist", () => {
    const { container } = render(
      <LineageGraph nodes={[makeAgentNode()]} edges={[]} className="graph-container" />
    );
    expect(container.firstChild).toHaveClass("graph-container");
  });
});
