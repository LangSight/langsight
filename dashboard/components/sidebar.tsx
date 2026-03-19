"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { signOut, useSession } from "next-auth/react";
import { useTheme } from "next-themes";
import { useState } from "react";
import useSWR from "swr";
import {
  LayoutDashboard, Activity, Shield, GitBranch, DollarSign, Bot,
  ChevronUp, LogOut, Sun, Moon, Settings, ExternalLink, Search,
  Folder, ChevronDown, Plus, Check,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import { useProject } from "@/lib/project-context";
import { fetcher, createProject } from "@/lib/api";
import type { ProjectResponse } from "@/lib/types";

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

function ProjectSwitcher() {
  const { activeProject, setActiveProject } = useProject();
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const { data: projects } = useSWR<ProjectResponse[]>("/api/projects", fetcher, { refreshInterval: 60_000 });

  async function handleCreate() {
    if (!newName.trim()) return;
    setCreating(true);
    try {
      const p = await createProject(newName.trim());
      setActiveProject(p);
      setNewName("");
      setOpen(false);
      toast.success(`Project "${p.name}" created`);
    } catch {
      toast.error("Failed to create project");
    } finally {
      setCreating(false);
    }
  }

  const label = activeProject?.name ?? "All Projects";

  return (
    <div className="relative px-3 pt-2 pb-1">
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-2 w-full h-8 px-2.5 rounded-md border border-border text-[13px] transition-colors hover:bg-accent/40 text-foreground">
        <Folder size={13} className="text-primary flex-shrink-0" />
        <span className="flex-1 text-left truncate">{label}</span>
        <ChevronDown size={12} className={cn("text-muted-foreground transition-transform", open && "rotate-180")} />
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute top-full left-3 right-3 mt-1 rounded-lg border border-border bg-card shadow-lg z-20 py-1 overflow-hidden">
            {/* All projects option */}
            <button
              onClick={() => { setActiveProject(null); setOpen(false); }}
              className="flex items-center gap-2 w-full px-3 py-2 text-[13px] transition-colors hover:bg-accent text-foreground">
              {!activeProject && <Check size={12} className="text-primary" />}
              {activeProject && <span className="w-3" />}
              All Projects
            </button>

            {projects && projects.length > 0 && (
              <div className="border-t border-border my-1" />
            )}

            {projects?.map(p => (
              <button
                key={p.id}
                onClick={() => { setActiveProject(p); setOpen(false); }}
                className="flex items-center gap-2 w-full px-3 py-2 text-[13px] transition-colors hover:bg-accent text-foreground">
                {activeProject?.id === p.id ? <Check size={12} className="text-primary" /> : <span className="w-3" />}
                <span className="flex-1 truncate text-left">{p.name}</span>
                <span className="text-[10px] text-muted-foreground">{p.your_role}</span>
              </button>
            ))}

            <div className="border-t border-border my-1 px-3 pt-2 pb-1">
              <div className="flex items-center gap-1.5">
                <input
                  type="text"
                  value={newName}
                  onChange={e => setNewName(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && handleCreate()}
                  placeholder="New project name…"
                  className="flex-1 min-w-0 text-[12px] bg-transparent outline-none text-foreground placeholder:text-muted-foreground"
                />
                <button
                  onClick={handleCreate}
                  disabled={creating || !newName.trim()}
                  className="flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[11px] font-medium bg-primary/10 text-primary hover:bg-primary/20 transition-colors disabled:opacity-50">
                  <Plus size={10} />{creating ? "…" : "Add"}
                </button>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
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

      {/* Project switcher */}
      <ProjectSwitcher />

      {/* Search */}
      <div className="px-3 pt-1 pb-1">
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
