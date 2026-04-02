"use client";

import { Sidebar } from "@/components/sidebar";
import { ProjectProvider } from "@/lib/project-context";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, useTransition } from "react";
import { SWRConfig } from "swr";

const PAGE_META: Record<string, { title: string; description: string }> = {
  "/":            { title: "Dashboard",      description: "Agent runtime health at a glance" },
  "/sessions":    { title: "Sessions",       description: "Full traces of every agent workflow" },
  "/agents":    { title: "Agents",         description: "Per-agent performance, costs, and error rates" },
  "/costs":     { title: "Cost Attribution", description: "Per-tool, per-agent, and per-session cost breakdown" },
  "/health":    { title: "Tool Health",    description: "Proactive health checks across all MCP servers" },
  "/security":  { title: "MCP Security",  description: "CVE detection · OWASP MCP Top 10 · Tool poisoning" },
  "/alerts":    { title: "Alerts",        description: "Alert rules, incomplete sessions, and active anomalies" },
  "/settings":  { title: "Settings",      description: "Manage users, model pricing, API keys, and instance config" },
};

/* ── Nav progress bar ───────────────────────────────────────── */
function NavProgress() {
  const pathname = usePathname();
  const [visible, setVisible] = useState(false);
  const [width, setWidth] = useState(0);
  const [prevPath, setPrevPath] = useState(pathname);

  useEffect(() => {
    if (pathname !== prevPath) {
      // Navigation completed — finish bar
      setWidth(100);
      const t = setTimeout(() => {
        setVisible(false);
        setWidth(0);
        setPrevPath(pathname);
      }, 300);
      return () => clearTimeout(t);
    }
  }, [pathname, prevPath]);

  // Start bar on click of any link
  useEffect(() => {
    function onLinkClick(e: MouseEvent) {
      const anchor = (e.target as HTMLElement).closest("a");
      if (!anchor) return;
      const href = anchor.getAttribute("href");
      if (!href || href.startsWith("http") || href.startsWith("#")) return;
      if (href !== pathname) {
        setVisible(true);
        setWidth(30);
        // Ramp up
        const t1 = setTimeout(() => setWidth(60), 150);
        const t2 = setTimeout(() => setWidth(80), 500);
        return () => { clearTimeout(t1); clearTimeout(t2); };
      }
    }
    document.addEventListener("click", onLinkClick);
    return () => document.removeEventListener("click", onLinkClick);
  }, [pathname]);

  if (!visible) return null;
  return (
    <div
      className="fixed top-0 left-0 z-50 h-[2px] transition-all"
      style={{
        width: `${width}%`,
        background: "hsl(var(--primary))",
        transitionDuration: width === 100 ? "200ms" : "400ms",
        transitionTimingFunction: "ease-out",
        boxShadow: "0 0 8px hsl(var(--primary) / 0.6)",
      }}
    />
  );
}

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
    // revalidateOnFocus: false — prevents API storm when user alt-tabs back.
    // Dashboard data is already refreshed on a per-page interval via refreshInterval.
    <SWRConfig value={{ revalidateOnFocus: false, revalidateOnReconnect: true }}>
    <ProjectProvider>
      <NavProgress />
      <div className="flex h-screen overflow-hidden">
        <Sidebar />
        <div className="flex-1 flex flex-col overflow-hidden">
          <Topbar />
          <main
            className="flex-1 overflow-y-auto"
            style={{ background: "hsl(var(--background))" }}
          >
            <div className="p-5 w-full">
              {children}
            </div>
          </main>
        </div>
      </div>
    </ProjectProvider>
    </SWRConfig>
  );
}
