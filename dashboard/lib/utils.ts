import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";
import type { ServerStatus, Severity, ToolCallStatus } from "./types";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatLatency(ms: number | null): string {
  if (ms === null || ms === undefined) return "—";
  if (ms < 1000) return `${ms.toFixed(0)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export function formatDuration(ms: number | null): string {
  if (!ms) return "—";
  if (ms < 1000) return `${ms.toFixed(0)}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60_000).toFixed(1)}m`;
}

/**
 * Ensure a timestamp string is parsed as UTC.
 * ClickHouse returns naive timestamps ("2026-03-24 10:48:07.704000") without
 * a timezone indicator.  Without the trailing "Z", browsers parse them as
 * local time, which shifts every display by the user's UTC offset.
 */
function asUTC(iso: string): Date {
  let s = iso.trim();
  // Add "T" separator if missing (ClickHouse uses space)
  if (s.length >= 19 && s[10] === " ") s = s.slice(0, 10) + "T" + s.slice(11);
  // Append Z if no timezone indicator present
  if (!s.endsWith("Z") && !s.includes("+") && !/[+-]\d{2}:\d{2}$/.test(s)) s += "Z";
  return new Date(s);
}

export function formatTime(iso: string): string {
  return asUTC(iso).toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function timeAgo(iso: string): string {
  const secs = Math.floor((Date.now() - asUTC(iso).getTime()) / 1000);
  if (secs < 0) return "just now";
  if (secs < 60) return `${secs}s ago`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`;
  return `${Math.floor(secs / 86400)}d ago`;
}

export function formatExact(iso: string): string {
  return asUTC(iso).toLocaleString("en-US", {
    month: "short", day: "numeric", year: "numeric",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
    hour12: false, timeZoneName: "short",
  });
}

export const STATUS_COLOR: Record<ServerStatus, string> = {
  up:       "text-emerald-400",
  degraded: "text-yellow-400",
  down:     "text-red-400",
  stale:    "text-zinc-500",
  unknown:  "text-zinc-500",
};

export const STATUS_BG: Record<ServerStatus, string> = {
  up:       "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  degraded: "bg-yellow-500/10 text-yellow-400 border-yellow-500/20",
  down:     "bg-red-500/10 text-red-400 border-red-500/20",
  stale:    "bg-zinc-500/10 text-zinc-400 border-zinc-500/20",
  unknown:  "bg-zinc-500/10 text-zinc-400 border-zinc-500/20",
};

export const STATUS_ICON: Record<ServerStatus, string> = {
  up: "✓", degraded: "⚠", down: "✗", stale: "~", unknown: "?",
};

export const SEVERITY_BG: Record<Severity, string> = {
  critical: "bg-red-500/10 text-red-400 border-red-500/20",
  high:     "bg-orange-500/10 text-orange-400 border-orange-500/20",
  medium:   "bg-yellow-500/10 text-yellow-400 border-yellow-500/20",
  low:      "bg-zinc-500/10 text-zinc-400 border-zinc-500/20",
  info:     "bg-blue-500/10 text-blue-400 border-blue-500/20",
};

export const CALL_STATUS_COLOR: Record<ToolCallStatus, string> = {
  success:   "text-emerald-400",
  error:     "text-red-400",
  timeout:   "text-yellow-400",
  prevented: "text-orange-400",  // v0.3 — blocked by loop/budget/circuit breaker
};

export const SPAN_TYPE_ICON: Record<string, string> = {
  tool_call: "🔧",
  agent:     "🤖",
  handoff:   "→",
};
