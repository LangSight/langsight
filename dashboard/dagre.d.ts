declare module "dagre" {
  namespace graphlib {
    class Graph {
      constructor(opts?: Record<string, unknown>);
      setDefaultEdgeLabel(fn: () => Record<string, unknown>): void;
      setGraph(opts: Record<string, unknown>): void;
      setNode(id: string, label: Record<string, unknown>): void;
      setEdge(source: string, target: string, label?: Record<string, unknown>): void;
      node(id: string): { x: number; y: number; width: number; height: number };
    }
  }
  function layout(g: graphlib.Graph): void;
  export default dagre;
}
