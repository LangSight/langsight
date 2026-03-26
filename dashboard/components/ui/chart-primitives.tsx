"use client";

/**
 * Shared chart primitives used across dashboard pages.
 *
 * StatCard   — single metric with icon + optional sub-text and trend badge
 * ChartCard  — titled wrapper around a Recharts chart
 * ChartTooltip — consistent Recharts tooltip
 * TrendBadge — week-over-week percentage badge
 */

import type { ElementType, ReactNode } from "react";
import { cn } from "@/lib/utils";

/* ── Chart tooltip ────────────────────────────────────────────── */
export function ChartTooltip({
  active,
  payload,
  label,
  formatter,
}: {
  active?: boolean;
  payload?: Array<{ value: number; name: string; color: string }>;
  label?: string;
  formatter?: (v: number) => string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div
      className="rounded-lg border px-3 py-2 shadow-lg"
      style={{
        background: "hsl(var(--card))",
        borderColor: "hsl(var(--border))",
        fontSize: "11px",
      }}
    >
      <p
        className="text-muted-foreground mb-1"
        style={{ fontFamily: "var(--font-geist-mono)" }}
      >
        {label}
      </p>
      {payload.map((p, i) => (
        <div key={i} className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full" style={{ background: p.color }} />
          <span className="text-muted-foreground">{p.name}:</span>
          <span
            className="font-semibold text-foreground"
            style={{ fontFamily: "var(--font-geist-mono)" }}
          >
            {formatter ? formatter(p.value) : p.value.toLocaleString()}
          </span>
        </div>
      ))}
    </div>
  );
}

/* ── WoW trend badge ──────────────────────────────────────────── */
export function TrendBadge({
  pct,
  invert,
}: {
  pct: number | null | undefined;
  invert?: boolean;
}) {
  if (pct == null || pct === 0) return null;
  const isBad = invert ? pct < 0 : pct > 0;
  const arrow = pct > 0 ? "↑" : "↓";
  const abs = Math.abs(pct).toFixed(1);
  return (
    <span
      className="text-[9px] font-semibold px-1 py-0.5 rounded"
      style={{
        background: isBad ? "rgba(239,68,68,0.1)" : "rgba(34,197,94,0.1)",
        color: isBad ? "#ef4444" : "#22c55e",
      }}
    >
      {arrow}{abs}% vs last 7d
    </span>
  );
}

/* ── Stat card ────────────────────────────────────────────────── */
export function StatCard({
  label,
  value,
  sub,
  icon: Icon,
  color,
  trend,
}: {
  label: string;
  value: string | number;
  sub?: string;
  icon: ElementType;
  color: string;
  trend?: ReactNode;
}) {
  return (
    <div
      className="rounded-xl border p-4"
      style={{
        background: "hsl(var(--card))",
        borderColor: "hsl(var(--border))",
      }}
    >
      <div className="flex items-center gap-2 mb-2">
        <div
          className="w-7 h-7 rounded-lg flex items-center justify-center"
          style={{
            background: `${color}18`,
            border: `1px solid ${color}30`,
          }}
        >
          <Icon size={13} style={{ color }} />
        </div>
        <span className="text-[11px] text-muted-foreground font-medium">
          {label}
        </span>
      </div>
      <p
        className="text-xl font-bold text-foreground"
        style={{ fontFamily: "var(--font-geist-mono)" }}
      >
        {value}
      </p>
      <div className="flex items-center gap-2 mt-0.5">
        {sub && <p className="text-[10px] text-muted-foreground">{sub}</p>}
        {trend}
      </div>
    </div>
  );
}

/* ── Chart wrapper ────────────────────────────────────────────── */
export function ChartCard({
  title,
  children,
  className,
  ariaLabel,
}: {
  title: string;
  children: ReactNode;
  className?: string;
  ariaLabel?: string;
}) {
  return (
    <div
      className={cn("rounded-xl border p-4", className)}
      style={{
        background: "hsl(var(--card))",
        borderColor: "hsl(var(--border))",
      }}
    >
      <h3 className="text-[12px] font-semibold text-muted-foreground mb-3 uppercase tracking-wider">
        {title}
      </h3>
      <div
        className="h-52"
        role="img"
        aria-label={ariaLabel ?? title}
      >
        {children}
      </div>
    </div>
  );
}
