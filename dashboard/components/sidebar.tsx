"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { signOut, useSession } from "next-auth/react";
import { useTheme } from "next-themes";
import { useState } from "react";
import {
  LayoutDashboard, Activity, Shield, GitBranch, DollarSign, Bot,
  ChevronDown, LogOut, Sun, Moon, Settings, User, ExternalLink,
  Bell
} from "lucide-react";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

const NAV = [
  { href: "/",         label: "Overview",   icon: LayoutDashboard },
  { href: "/agents",   label: "Agents",     icon: Bot },
  { href: "/sessions", label: "Workflows",  icon: GitBranch },
  { href: "/health",   label: "Tools & MCPs", icon: Activity },
  { href: "/security", label: "Security",   icon: Shield },
  { href: "/costs",    label: "Costs",      icon: DollarSign },
];

function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  return (
    <button onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
      className="p-1.5 rounded-lg transition-colors hover:bg-accent"
      style={{ color: "hsl(var(--muted-foreground))" }}>
      {theme === "dark" ? <Sun size={15}/> : <Moon size={15}/>}
    </button>
  );
}

function UserMenu() {
  const { data: session } = useSession();
  const [open, setOpen] = useState(false);
  const user = session?.user;

  const initials = user?.name?.split(" ").map(n => n[0]).join("").slice(0, 2) ?? "??";

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-2.5 w-full p-2 rounded-lg hover:bg-accent transition-colors">
        <div className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold text-white flex-shrink-0"
          style={{ background: "hsl(var(--primary))" }}>
          {initials}
        </div>
        <div className="flex-1 min-w-0 text-left">
          <p className="text-xs font-medium truncate" style={{ color: "hsl(var(--foreground))" }}>{user?.name ?? "User"}</p>
          <p className="text-[10px] truncate" style={{ color: "hsl(var(--muted-foreground))" }}>{user?.email ?? ""}</p>
        </div>
        <ChevronDown size={14} style={{ color: "hsl(var(--muted-foreground))" }}/>
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)}/>
          <div className="absolute bottom-full left-0 right-0 mb-1 rounded-lg border shadow-xl z-20 py-1"
            style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}>
            <div className="px-3 py-2 border-b" style={{ borderColor: "hsl(var(--border))" }}>
              <p className="text-xs font-semibold" style={{ color: "hsl(var(--foreground))" }}>{user?.name}</p>
              <p className="text-[10px]" style={{ color: "hsl(var(--muted-foreground))" }}>{user?.email}</p>
            </div>
            {[
              { icon: User, label: "Profile" },
              { icon: Settings, label: "Settings" },
            ].map(item => (
              <button key={item.label}
                onClick={() => { setOpen(false); toast.info(`${item.label} — coming soon`); }}
                className="flex items-center gap-2.5 w-full px-3 py-2 text-xs hover:bg-accent transition-colors"
                style={{ color: "hsl(var(--foreground))" }}>
                <item.icon size={13}/> {item.label}
              </button>
            ))}
            <div className="border-t my-1" style={{ borderColor: "hsl(var(--border))" }}/>
            <button
              onClick={() => signOut({ callbackUrl: "/login" })}
              className="flex items-center gap-2.5 w-full px-3 py-2 text-xs hover:bg-accent transition-colors text-red-500">
              <LogOut size={13}/> Sign out
            </button>
          </div>
        </>
      )}
    </div>
  );
}

export function Sidebar() {
  const path = usePathname();

  return (
    <aside className="w-56 shrink-0 flex flex-col h-full border-r"
      style={{ background: "hsl(var(--sidebar))", borderColor: "hsl(var(--sidebar-border))" }}>
      {/* Header */}
      <div className="h-14 flex items-center justify-between px-4 border-b flex-shrink-0"
        style={{ borderColor: "hsl(var(--sidebar-border))" }}>
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-lg flex items-center justify-center text-white"
            style={{ background: "hsl(var(--primary))" }}>
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M2 7h10M7 2v10M4 4l6 6M10 4l-6 6" stroke="white" strokeWidth="1.5" strokeLinecap="round"/>
            </svg>
          </div>
          <span className="font-bold text-sm" style={{ color: "hsl(var(--foreground))" }}>LangSight</span>
        </div>
        <div className="flex items-center gap-0.5">
          <button className="p-1.5 rounded-lg transition-colors hover:bg-accent relative"
            style={{ color: "hsl(var(--muted-foreground))" }}
            onClick={() => toast.info("Alerts — coming soon")}>
            <Bell size={14}/>
          </button>
          <ThemeToggle/>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 p-2 space-y-0.5 overflow-y-auto">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = href === "/" ? path === "/" : path.startsWith(href);
          return (
            <Link key={href} href={href}
              className={cn(
                "flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-all",
                active
                  ? "font-medium text-white shadow-sm"
                  : "hover:bg-accent"
              )}
              style={active
                ? { background: "hsl(var(--primary))" }
                : { color: "hsl(var(--muted-foreground))" }
              }>
              <Icon size={15}/>
              {label}
            </Link>
          );
        })}
      </nav>

      {/* Footer links */}
      <div className="p-2 border-t space-y-0.5" style={{ borderColor: "hsl(var(--sidebar-border))" }}>
        <a href="http://localhost:8000/docs" target="_blank" rel="noreferrer"
          className="flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs transition-colors hover:bg-accent"
          style={{ color: "hsl(var(--muted-foreground))" }}>
          <ExternalLink size={13}/> API Docs
        </a>
      </div>

      {/* User menu */}
      <div className="p-2 border-t" style={{ borderColor: "hsl(var(--sidebar-border))" }}>
        <UserMenu/>
      </div>
    </aside>
  );
}
