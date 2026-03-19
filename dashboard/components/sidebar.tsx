"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { signOut, useSession } from "next-auth/react";
import { useTheme } from "next-themes";
import { useState } from "react";
import useSWR from "swr";
import {
  LayoutDashboard, Activity, Shield, GitBranch, DollarSign, Bot,
  LogOut, Sun, Moon, Settings, Folder, ChevronDown, Plus, Check,
  Zap, ChevronRight,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import { useProject } from "@/lib/project-context";
import { fetcher, createProject } from "@/lib/api";
import type { ProjectResponse } from "@/lib/types";

/* ── Nav config ─────────────────────────────────────────────── */
const PRIMARY_NAV = [
  { href: "/",         label: "Overview",     icon: LayoutDashboard, color: "#6366f1" },
  { href: "/sessions", label: "Sessions",     icon: GitBranch,       color: "#8b5cf6" },
  { href: "/agents",   label: "Agents",       icon: Bot,             color: "#06b6d4" },
  { href: "/costs",    label: "Costs",        icon: DollarSign,      color: "#10b981" },
];

const INFRA_NAV = [
  { href: "/health",   label: "Tool Health",  icon: Activity, color: "#f59e0b" },
  { href: "/security", label: "MCP Security", icon: Shield,   color: "#ef4444" },
];

/* ── Nav item ───────────────────────────────────────────────── */
function NavItem({
  href, label, icon: Icon, color, active, count,
}: {
  href: string;
  label: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  color: string;
  active: boolean;
  count?: number;
}) {
  return (
    <Link href={href} className={cn("sidebar-nav-item", active && "active")}>
      <span
        className="nav-icon flex-shrink-0"
        style={{
          ...(active ? { background: `${color}22` } : {}),
          color: active ? color : undefined,
        }}
      >
        <Icon size={15} />
      </span>
      <span className="flex-1 leading-none">{label}</span>
      {count !== undefined && count > 0 && (
        <span className="text-[10px] font-bold tabular-nums px-1.5 py-0.5 rounded-full min-w-[20px] text-center badge-danger">
          {count > 99 ? "99+" : count}
        </span>
      )}
    </Link>
  );
}

/* ── Section divider ────────────────────────────────────────── */
function NavSection({ label }: { label: string }) {
  return (
    <div className="px-3 pt-3 pb-1">
      <p
        className="text-[10px] font-semibold uppercase tracking-widest select-none"
        style={{ color: "hsl(var(--sidebar-muted))" }}
      >
        {label}
      </p>
    </div>
  );
}

/* ── Project switcher ───────────────────────────────────────── */
function ProjectSwitcher() {
  const { activeProject, setActiveProject } = useProject();
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const { data: projects } = useSWR<ProjectResponse[]>("/api/projects", fetcher, {
    refreshInterval: 60_000,
  });

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
    <div className="relative px-2 pb-1">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 w-full h-[32px] px-2.5 rounded-lg text-[12px] font-medium transition-colors"
        style={{
          background: "hsl(var(--sidebar-accent))",
          color: "hsl(var(--sidebar-fg))",
          border: "1px solid hsl(var(--sidebar-border))",
        }}
      >
        <Folder size={12} style={{ color: "hsl(var(--primary))", flexShrink: 0 }} />
        <span className="flex-1 text-left truncate">{label}</span>
        <ChevronDown
          size={11}
          className={cn("transition-transform flex-shrink-0", open && "rotate-180")}
          style={{ color: "hsl(var(--sidebar-muted))" }}
        />
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div
            className="absolute top-full left-0 right-0 mt-1 rounded-xl shadow-2xl z-20 py-1 overflow-hidden"
            style={{
              background: "hsl(224 20% 8%)",
              border: "1px solid hsl(var(--sidebar-border))",
            }}
          >
            <button
              onClick={() => { setActiveProject(null); setOpen(false); }}
              className="flex items-center gap-2 w-full px-3 py-2 text-[12px] transition-colors"
              style={{ color: "hsl(var(--sidebar-fg))" }}
              onMouseEnter={e => (e.currentTarget.style.background = "hsl(var(--sidebar-accent))")}
              onMouseLeave={e => (e.currentTarget.style.background = "")}
            >
              <span className="w-3 flex-shrink-0">
                {!activeProject && <Check size={11} style={{ color: "hsl(var(--primary))" }} />}
              </span>
              All Projects
            </button>

            {projects && projects.length > 0 && (
              <div className="my-1" style={{ borderTop: "1px solid hsl(var(--sidebar-border))" }} />
            )}

            {projects?.map((p) => (
              <button
                key={p.id}
                onClick={() => { setActiveProject(p); setOpen(false); }}
                className="flex items-center gap-2 w-full px-3 py-2 text-[12px] transition-colors"
                style={{ color: "hsl(var(--sidebar-fg))" }}
                onMouseEnter={e => (e.currentTarget.style.background = "hsl(var(--sidebar-accent))")}
                onMouseLeave={e => (e.currentTarget.style.background = "")}
              >
                <span className="w-3 flex-shrink-0">
                  {activeProject?.id === p.id && <Check size={11} style={{ color: "hsl(var(--primary))" }} />}
                </span>
                <span className="flex-1 truncate text-left">{p.name}</span>
                <span
                  className="text-[10px] capitalize"
                  style={{ color: "hsl(var(--sidebar-muted))" }}
                >
                  {p.your_role}
                </span>
              </button>
            ))}

            <div
              className="mt-1 px-3 py-2"
              style={{ borderTop: "1px solid hsl(var(--sidebar-border))" }}
            >
              <div className="flex items-center gap-1.5">
                <input
                  type="text"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleCreate()}
                  placeholder="New project…"
                  className="flex-1 min-w-0 text-[11px] bg-transparent outline-none"
                  style={{ color: "hsl(var(--sidebar-fg))" }}
                />
                <button
                  onClick={handleCreate}
                  disabled={creating || !newName.trim()}
                  className="flex items-center gap-0.5 px-2 py-0.5 rounded-md text-[11px] font-semibold badge-primary transition-colors disabled:opacity-40"
                >
                  <Plus size={9} />{creating ? "…" : "Add"}
                </button>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

/* ── User menu ──────────────────────────────────────────────── */
function UserMenu() {
  const { data: session } = useSession();
  const { theme, setTheme } = useTheme();
  const [open, setOpen] = useState(false);
  const user = session?.user;

  const initials =
    user?.name?.split(" ").map((n) => n[0]).join("").slice(0, 2).toUpperCase() ?? "?";

  // Generate a consistent gradient from the user's initials
  const gradients = [
    "linear-gradient(135deg, #6366f1, #8b5cf6)",
    "linear-gradient(135deg, #06b6d4, #3b82f6)",
    "linear-gradient(135deg, #10b981, #06b6d4)",
    "linear-gradient(135deg, #f59e0b, #ef4444)",
    "linear-gradient(135deg, #8b5cf6, #ec4899)",
  ];
  const avatarGradient = gradients[(initials.charCodeAt(0) ?? 0) % gradients.length];

  return (
    <div className="relative px-2 pb-2">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2.5 w-full px-2 py-2 rounded-xl transition-colors"
        style={{ color: "hsl(var(--sidebar-fg))" }}
        onMouseEnter={e => (e.currentTarget.style.background = "hsl(var(--sidebar-accent))")}
        onMouseLeave={e => (e.currentTarget.style.background = "")}
      >
        {/* Avatar */}
        <div
          className="w-7 h-7 rounded-lg flex items-center justify-center text-[11px] font-bold text-white flex-shrink-0 shadow-sm"
          style={{ background: avatarGradient }}
        >
          {initials}
        </div>
        {/* Name + email */}
        <div className="flex-1 min-w-0 text-left">
          <p
            className="text-[12.5px] font-semibold truncate leading-tight"
            style={{ color: "hsl(var(--sidebar-fg))" }}
          >
            {user?.name ?? "User"}
          </p>
          <p
            className="text-[10.5px] truncate leading-tight"
            style={{ color: "hsl(var(--sidebar-muted))" }}
          >
            {user?.email ?? ""}
          </p>
        </div>
        <ChevronRight
          size={12}
          style={{ color: "hsl(var(--sidebar-muted))", flexShrink: 0 }}
        />
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div
            className="absolute bottom-full left-0 right-0 mb-1.5 rounded-xl shadow-2xl z-20 py-1 overflow-hidden"
            style={{
              background: "hsl(224 20% 8%)",
              border: "1px solid hsl(var(--sidebar-border))",
            }}
          >
            {/* User header */}
            <div
              className="flex items-center gap-2.5 px-3 py-2.5"
              style={{ borderBottom: "1px solid hsl(var(--sidebar-border))" }}
            >
              <div
                className="w-8 h-8 rounded-lg flex items-center justify-center text-[12px] font-bold text-white flex-shrink-0"
                style={{ background: avatarGradient }}
              >
                {initials}
              </div>
              <div className="min-w-0">
                <p className="text-[13px] font-semibold truncate" style={{ color: "hsl(var(--sidebar-fg))" }}>
                  {user?.name}
                </p>
                <p className="text-[11px] truncate" style={{ color: "hsl(var(--sidebar-muted))" }}>
                  {user?.email}
                </p>
              </div>
            </div>

            {[
              {
                icon: Settings,
                label: "Settings",
                action: () => { setOpen(false); window.location.href = "/settings"; },
              },
              {
                icon: theme === "dark" ? Sun : Moon,
                label: theme === "dark" ? "Light mode" : "Dark mode",
                action: () => setTheme(theme === "dark" ? "light" : "dark"),
              },
            ].map((item) => (
              <button
                key={item.label}
                onClick={item.action}
                className="flex items-center gap-2.5 w-full px-3 py-2 text-[12.5px] transition-colors"
                style={{ color: "hsl(var(--sidebar-fg))" }}
                onMouseEnter={e => (e.currentTarget.style.background = "hsl(var(--sidebar-accent))")}
                onMouseLeave={e => (e.currentTarget.style.background = "")}
              >
                <item.icon size={13} style={{ color: "hsl(var(--sidebar-muted))" }} />
                {item.label}
              </button>
            ))}

            <div className="my-1" style={{ borderTop: "1px solid hsl(var(--sidebar-border))" }} />

            <button
              onClick={() => signOut({ callbackUrl: "/login" })}
              className="flex items-center gap-2.5 w-full px-3 py-2 text-[12.5px] transition-colors"
              style={{ color: "hsl(var(--danger))" }}
              onMouseEnter={e => (e.currentTarget.style.background = "hsl(var(--sidebar-accent))")}
              onMouseLeave={e => (e.currentTarget.style.background = "")}
            >
              <LogOut size={13} />
              Sign out
            </button>
          </div>
        </>
      )}
    </div>
  );
}

/* ── Sidebar ────────────────────────────────────────────────── */
export function Sidebar() {
  const path = usePathname();
  const isActive = (href: string) =>
    href === "/" ? path === "/" : path.startsWith(href);

  return (
    <aside
      className="w-[224px] shrink-0 flex flex-col h-full"
      style={{
        background: "hsl(var(--sidebar-bg))",
        borderRight: "1px solid hsl(var(--sidebar-border))",
      }}
    >
      {/* ── Logo ──────────────────────────────────────────────── */}
      <div
        className="h-[54px] flex items-center gap-3 px-4 flex-shrink-0"
        style={{ borderBottom: "1px solid hsl(var(--sidebar-border))" }}
      >
        {/* Logo mark */}
        <div
          className="w-7 h-7 rounded-lg flex items-center justify-center shadow-lg flex-shrink-0"
          style={{ background: "linear-gradient(135deg, #6366f1, #8b5cf6)" }}
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path
              d="M2 7h10M7 2v10M4 4l6 6M10 4l-6 6"
              stroke="white"
              strokeWidth="1.7"
              strokeLinecap="round"
            />
          </svg>
        </div>

        {/* Wordmark */}
        <div className="flex-1 min-w-0">
          <span
            className="font-bold text-[14px] tracking-tight"
            style={{ color: "hsl(var(--sidebar-fg))" }}
          >
            LangSight
          </span>
        </div>

        {/* Version badge */}
        <span
          className="text-[9px] font-bold px-1.5 py-0.5 rounded-full flex-shrink-0"
          style={{
            background: "hsl(var(--primary) / 0.2)",
            color: "hsl(var(--primary))",
            border: "1px solid hsl(var(--primary) / 0.3)",
            letterSpacing: "0.02em",
          }}
        >
          v0.2
        </span>
      </div>

      {/* ── Project switcher ──────────────────────────────────── */}
      <div
        className="px-2 py-2.5"
        style={{ borderBottom: "1px solid hsl(var(--sidebar-border))" }}
      >
        <ProjectSwitcher />
      </div>

      {/* ── Primary nav ───────────────────────────────────────── */}
      <nav className="px-2 pt-2 space-y-0.5 flex-shrink-0">
        {PRIMARY_NAV.map((item) => (
          <NavItem key={item.href} {...item} active={isActive(item.href)} />
        ))}
      </nav>

      {/* ── Infrastructure ────────────────────────────────────── */}
      <div className="px-2 flex-shrink-0">
        <NavSection label="Infrastructure" />
        <div className="space-y-0.5">
          {INFRA_NAV.map((item) => (
            <NavItem key={item.href} {...item} active={isActive(item.href)} />
          ))}
        </div>
      </div>

      {/* ── Spacer ────────────────────────────────────────────── */}
      <div className="flex-1" />

      {/* ── Status indicator ──────────────────────────────────── */}
      <div
        className="mx-2 mb-2 rounded-xl px-3 py-2.5"
        style={{
          background: "hsl(var(--primary) / 0.06)",
          border: "1px solid hsl(var(--primary) / 0.12)",
        }}
      >
        <div className="flex items-center gap-2 mb-1">
          <Zap size={11} style={{ color: "hsl(var(--primary))" }} />
          <span
            className="text-[11px] font-semibold"
            style={{ color: "hsl(var(--primary))" }}
          >
            LangSight API
          </span>
          <span className="ml-auto relative flex w-1.5 h-1.5">
            <span
              className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-60"
              style={{ background: "#22c55e" }}
            />
            <span
              className="relative inline-flex rounded-full w-1.5 h-1.5"
              style={{ background: "#22c55e" }}
            />
          </span>
        </div>
        <p className="text-[10px]" style={{ color: "hsl(var(--sidebar-muted))" }}>
          localhost:8000 · SQLite
        </p>
      </div>

      {/* ── Footer nav ────────────────────────────────────────── */}
      <div
        className="px-2 py-1.5 space-y-0.5"
        style={{ borderTop: "1px solid hsl(var(--sidebar-border))" }}
      >
        <Link
          href="/settings"
          className={cn("sidebar-nav-item", isActive("/settings") && "active")}
        >
          <span
            className="nav-icon"
            style={{
              ...(isActive("/settings") ? { background: "rgba(99,102,241,0.15)" } : {}),
              color: isActive("/settings") ? "#6366f1" : undefined,
            }}
          >
            <Settings size={15} />
          </span>
          <span className="flex-1 leading-none">Settings</span>
        </Link>
      </div>

      {/* ── User ──────────────────────────────────────────────── */}
      <div style={{ borderTop: "1px solid hsl(var(--sidebar-border))" }}>
        <UserMenu />
      </div>
    </aside>
  );
}
