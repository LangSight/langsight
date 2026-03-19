"use client";

import { Sidebar } from "@/components/sidebar";
import { ProjectProvider } from "@/lib/project-context";
import { usePathname } from "next/navigation";

const PAGE_META: Record<string, { title: string; description: string }> = {
  "/":          { title: "Overview",       description: "Monitor your AI agents and the tools they use" },
  "/sessions":  { title: "Sessions",       description: "Full traces of every agent workflow" },
  "/agents":    { title: "Agents",         description: "Per-agent performance, costs, and error rates" },
  "/costs":     { title: "Cost Attribution", description: "Per-tool, per-agent, and per-session cost breakdown" },
  "/health":    { title: "Tool Health",    description: "Proactive health checks across all MCP servers" },
  "/security":  { title: "MCP Security",  description: "CVE detection · OWASP MCP Top 10 · Tool poisoning" },
  "/settings":  { title: "Settings",      description: "Manage users, model pricing, API keys, and instance config" },
};

function Topbar() {
  const path = usePathname();
  const meta = PAGE_META[path] ?? { title: "LangSight", description: "" };

  return (
    <div className="topbar flex-shrink-0">
      <div>
        <h1
          className="text-[15px] font-semibold leading-tight"
          style={{ color: "hsl(var(--foreground))", letterSpacing: "-0.015em" }}
        >
          {meta.title}
        </h1>
        {meta.description && (
          <p className="text-[11.5px] leading-tight mt-0.5" style={{ color: "hsl(var(--muted-foreground))" }}>
            {meta.description}
          </p>
        )}
      </div>
    </div>
  );
}

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <ProjectProvider>
      <div className="flex h-screen overflow-hidden">
        <Sidebar />
        <div className="flex-1 flex flex-col overflow-hidden">
          <Topbar />
          <main
            className="flex-1 overflow-y-auto"
            style={{ background: "hsl(var(--background))" }}
          >
            <div className="p-5 max-w-7xl mx-auto">
              {children}
            </div>
          </main>
        </div>
      </div>
    </ProjectProvider>
  );
}
