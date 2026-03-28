"use client";

/**
 * Shared chart primitives used across dashboard pages.
 *
 * StatCard    — single metric with icon + optional sub-text and trend badge
 * ChartCard   — titled wrapper with maximize button + fullscreen modal
 * ChartTooltip — consistent Recharts tooltip
 * TrendBadge  — week-over-week percentage badge
 *
 * ChartCard accepts children as either ReactNode or a render prop:
 *   (isExpanded: boolean) => ReactNode
 * Use the render prop to conditionally add <Brush> / <Legend> in expanded view.
 */

import { useState, useEffect, useCallback, type ElementType, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Maximize2, X } from "lucide-react";
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

/* ── Time ranges for chart modal ─────────────────────────────── */
const CHART_RANGES = [
  { label: "1h",  hours: 1 },
  { label: "6h",  hours: 6 },
  { label: "24h", hours: 24 },
  { label: "7d",  hours: 168 },
] as const;

/* ── Chart wrapper with maximize ─────────────────────────────── */
type ChildrenFn = (isExpanded: boolean) => ReactNode;

export function ChartCard({
  title,
  children,
  className,
  ariaLabel,
  hours,
  onHoursChange,
}: {
  title: string;
  children: ReactNode | ChildrenFn;
  className?: string;
  ariaLabel?: string;
  hours?: number;
  onHoursChange?: (h: number) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => { setMounted(true); }, []);

  const close = useCallback(() => setExpanded(false), []);

  useEffect(() => {
    if (!expanded) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") close(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [expanded, close]);

  const render = (isExp: boolean): ReactNode =>
    typeof children === "function" ? (children as ChildrenFn)(isExp) : children;

  return (
    <>
      {/* ── Compact card ─────────────────────────────────────── */}
      <div
        className={cn("rounded-xl border p-4", className)}
        style={{
          background: "hsl(var(--card))",
          borderColor: "hsl(var(--border))",
        }}
      >
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-[12px] font-semibold text-muted-foreground uppercase tracking-wider">
            {title}
          </h3>
          <button
            onClick={() => setExpanded(true)}
            className="p-1 rounded-md transition-colors text-muted-foreground hover:text-foreground hover:bg-accent"
            title="Expand chart"
            aria-label={`Expand ${title} chart`}
          >
            <Maximize2 size={11} />
          </button>
        </div>
        <div className="h-52" role="img" aria-label={ariaLabel ?? title}>
          {render(false)}
        </div>
      </div>

      {/* ── Fullscreen modal ─────────────────────────────────── */}
      {mounted && expanded && createPortal(
        <div
          role="dialog"
          aria-modal="true"
          aria-label={`${title} — expanded`}
          className="fixed inset-0 z-50 flex items-center justify-center p-4 md:p-8"
          style={{ background: "rgba(0,0,0,0.80)", backdropFilter: "blur(4px)" }}
          onClick={close}
        >
          <div
            className="w-full max-w-6xl rounded-2xl border shadow-2xl"
            style={{
              background: "hsl(var(--card))",
              borderColor: "hsl(var(--border))",
            }}
            onClick={e => e.stopPropagation()}
          >
            {/* Modal header */}
            <div
              className="flex items-center justify-between px-6 py-4 border-b"
              style={{ borderColor: "hsl(var(--border))" }}
            >
              <h2
                className="text-[13px] font-semibold text-foreground uppercase tracking-wider"
                style={{ fontFamily: "var(--font-geist-mono)" }}
              >
                {title}
              </h2>

              <div className="flex items-center gap-3">
                {/* Time range selector */}
                {onHoursChange && (
                  <div
                    className="flex items-center gap-0.5 rounded-lg border overflow-hidden"
                    style={{ borderColor: "hsl(var(--border))", background: "hsl(var(--muted))" }}
                  >
                    {CHART_RANGES.map(r => (
                      <button
                        key={r.hours}
                        onClick={() => onHoursChange(r.hours)}
                        className={cn(
                          "px-2.5 py-1 text-[11px] font-medium transition-colors",
                          hours === r.hours
                            ? "bg-background text-foreground shadow-sm rounded-md"
                            : "text-muted-foreground hover:text-foreground",
                        )}
                      >
                        {r.label}
                      </button>
                    ))}
                  </div>
                )}

                <span className="text-[10px] text-muted-foreground hidden md:block">
                  Drag range bar to zoom · Esc to close
                </span>

                <button
                  onClick={close}
                  className="p-1.5 rounded-lg transition-colors text-muted-foreground hover:text-foreground hover:bg-accent"
                  aria-label="Close"
                >
                  <X size={14} />
                </button>
              </div>
            </div>

            {/* Chart area — explicit px height so ResponsiveContainer can measure */}
            <div className="px-6 pb-6 pt-4" style={{ height: "500px" }}>
              {render(true)}
            </div>
          </div>
        </div>,
        document.body,
      )}
    </>
  );
}
