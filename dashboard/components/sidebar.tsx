"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { signOut, useSession } from "next-auth/react";
import { useTheme } from "next-themes";
import { useState } from "react";
import {
  LayoutDashboard, Activity, Shield, GitBranch, DollarSign, Bot,
  ChevronUp, LogOut, Sun, Moon, Settings, ExternalLink, Search,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

const PRIMARY_NAV = [
  { href: "/",         label: "Overview",  icon: LayoutDashboard },
  { href: "/sessions", label: "Sessions",  icon: GitBranch },
  { href: "/agents",   label: "Agents",    icon: Bot },
  { href: "/costs",    label: "Costs",     icon: DollarSign },
];

const INFRA_NAV = [
  { href: "/health",   label: "Tool Health",  icon: Activity },
  { href: "/security", label: "MCP Security", icon: Shield },
];

function NavItem({ href, label, icon: Icon, active, count }: {
  href: string; label: string; icon: React.ComponentType<{ size?: number; className?: string }>;
  active: boolean; count?: number;
}) {
  return (
    <Link href={href}
      className={cn(
        "group relative flex items-center gap-2.5 h-8 px-3 rounded-md text-[13px] transition-all duration-150",
        active
          ? "bg-accent font-medium text-foreground"
          : "text-muted-foreground hover:bg-accent/60 hover:text-foreground"
      )}>
      {active && (
        <span className="absolute left-0 top-1/2 -translate-y-1/2 w-[2px] h-4 rounded-r-full bg-primary" />
      )}
      <Icon size={16} className={cn(active ? "text-primary" : "text-muted-foreground group-hover:text-foreground")} />
      <span className="flex-1">{label}</span>
      {count !== undefined && count > 0 && (
        <span className="text-[10px] font-medium bg-red-500/10 text-red-500 px-1.5 py-0.5 rounded-full min-w-[18px] text-center">
          {count}
        </span>
      )}
    </Link>
  );
}

function UserMenu() {
  const { data: session } = useSession();
  const { theme, setTheme } = useTheme();
  const [open, setOpen] = useState(false);
  const user = session?.user;

  const initials = user?.name?.split(" ").map(n => n[0]).join("").slice(0, 2) ?? "??";

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-2.5 w-full px-2 py-1.5 rounded-md transition-colors hover:bg-accent/60">
        <div className="w-7 h-7 rounded-full flex items-center justify-center text-[11px] font-semibold text-white bg-primary flex-shrink-0">
          {initials}
        </div>
        <div className="flex-1 min-w-0 text-left">
          <p className="text-[13px] font-medium truncate leading-tight text-foreground">
            {user?.name ?? "User"}
          </p>
          <p className="text-[11px] truncate leading-tight text-muted-foreground">
            {user?.email ?? ""}
          </p>
        </div>
        <ChevronUp
          size={14}
          className={cn("transition-transform flex-shrink-0 text-muted-foreground", open ? "rotate-0" : "rotate-180")}
        />
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute bottom-full left-0 right-0 mb-1.5 rounded-lg border border-border bg-card shadow-lg z-20 py-1 overflow-hidden">
            <div className="px-3 py-2 border-b border-border">
              <p className="text-[13px] font-semibold truncate text-foreground">{user?.name}</p>
              <p className="text-[11px] truncate text-muted-foreground">{user?.email}</p>
            </div>

            <Link href="/settings" onClick={() => setOpen(false)}
              className="flex items-center gap-2.5 w-full px-3 py-2 text-[13px] transition-colors hover:bg-accent text-foreground">
              <Settings size={14} /> Settings
            </Link>

            <button
              onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
              className="flex items-center gap-2.5 w-full px-3 py-2 text-[13px] transition-colors hover:bg-accent text-foreground">
              {theme === "dark" ? <Sun size={14} /> : <Moon size={14} />}
              {theme === "dark" ? "Light mode" : "Dark mode"}
            </button>

            <div className="border-t border-border my-1" />

            <button
              onClick={() => signOut({ callbackUrl: "/login" })}
              className="flex items-center gap-2.5 w-full px-3 py-2 text-[13px] transition-colors hover:bg-accent text-red-500">
              <LogOut size={14} /> Sign out
            </button>
          </div>
        </>
      )}
    </div>
  );
}

export function Sidebar() {
  const path = usePathname();
  const isActive = (href: string) => href === "/" ? path === "/" : path.startsWith(href);

  return (
    <aside className="w-56 shrink-0 flex flex-col h-full border-r border-border bg-card/50">
      {/* Logo */}
      <div className="h-14 flex items-center gap-2.5 px-4 border-b border-border flex-shrink-0">
        <div className="w-7 h-7 rounded-lg flex items-center justify-center text-white bg-primary flex-shrink-0">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path d="M2 7h10M7 2v10M4 4l6 6M10 4l-6 6" stroke="white" strokeWidth="1.5" strokeLinecap="round"/>
          </svg>
        </div>
        <span className="font-bold text-sm text-foreground">LangSight</span>
        <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground ml-auto">
          v0.1
        </span>
      </div>

      {/* Search */}
      <div className="px-3 pt-3 pb-1">
        <button
          className="flex items-center gap-2 w-full h-8 px-2.5 rounded-md border border-border text-[13px] text-muted-foreground transition-colors hover:bg-accent/40"
          onClick={() => toast.info("Search — coming soon")}>
          <Search size={14} />
          <span className="flex-1 text-left">Search…</span>
          <kbd className="hidden sm:inline text-[10px] font-medium px-1.5 py-0.5 rounded border border-border bg-muted text-muted-foreground">
            ⌘K
          </kbd>
        </button>
      </div>

      {/* Primary nav */}
      <nav className="px-3 pt-2 space-y-0.5">
        {PRIMARY_NAV.map(item => (
          <NavItem key={item.href} {...item} active={isActive(item.href)} />
        ))}
      </nav>

      {/* Infrastructure section */}
      <div className="px-3 mt-5">
        <p className="text-[11px] font-medium uppercase tracking-wider px-3 mb-1.5 text-muted-foreground">
          Infrastructure
        </p>
        <div className="space-y-0.5">
          {INFRA_NAV.map(item => (
            <NavItem key={item.href} {...item} active={isActive(item.href)} />
          ))}
        </div>
      </div>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Footer */}
      <div className="px-3 pb-1">
        <a href="http://localhost:8000/docs" target="_blank" rel="noreferrer"
          className="flex items-center gap-2 h-8 px-3 rounded-md text-[12px] text-muted-foreground transition-colors hover:bg-accent/60 hover:text-foreground">
          <ExternalLink size={13} /> API Docs
        </a>
      </div>

      <div className="px-3 pt-1 pb-3 border-t border-border">
        <UserMenu />
      </div>
    </aside>
  );
}
