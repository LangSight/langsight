"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/",         label: "Overview",  icon: "◼" },
  { href: "/health",   label: "MCP Health", icon: "♥" },
  { href: "/security", label: "Security",   icon: "🛡" },
  { href: "/sessions", label: "Sessions",   icon: "🔭" },
  { href: "/costs",    label: "Costs",      icon: "💰" },
];

export function Sidebar() {
  const path = usePathname();
  return (
    <aside className="w-56 shrink-0 flex flex-col border-r" style={{ background: "var(--surface)", borderColor: "var(--border)" }}>
      {/* Logo */}
      <div className="h-16 flex items-center gap-2.5 px-5 border-b" style={{ borderColor: "var(--border)" }}>
        <div className="w-7 h-7 rounded-lg flex items-center justify-center text-white text-sm font-bold" style={{ background: "var(--accent)" }}>
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path d="M2 7h10M7 2v10M4 4l6 6M10 4l-6 6" stroke="white" strokeWidth="1.5" strokeLinecap="round"/>
          </svg>
        </div>
        <span className="font-bold text-white">LangSight</span>
      </div>

      {/* Nav */}
      <nav className="flex-1 p-3 space-y-1">
        {NAV.map((item) => {
          const active = item.href === "/" ? path === "/" : path.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors",
                active
                  ? "text-white font-medium"
                  : "text-zinc-400 hover:text-white hover:bg-white/5"
              )}
              style={active ? { background: "var(--accent)", opacity: 0.9 } : {}}
            >
              <span className="text-base">{item.icon}</span>
              {item.label}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="p-4 border-t text-xs" style={{ borderColor: "var(--border)", color: "var(--muted)" }}>
        <a href="http://localhost:8000/docs" target="_blank" rel="noreferrer"
          className="flex items-center gap-1.5 hover:text-white transition-colors">
          <span>API Docs</span>
          <span>↗</span>
        </a>
      </div>
    </aside>
  );
}
