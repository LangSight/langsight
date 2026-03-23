"use client";

import { useState, useRef, useEffect } from "react";
import { Calendar, X } from "lucide-react";

const PRESETS = [
  { label: "1h", hours: 1 },
  { label: "6h", hours: 6 },
  { label: "24h", hours: 24 },
  { label: "7d", hours: 168 },
  { label: "30d", hours: 720 },
] as const;

interface DateRangeFilterProps {
  /** Currently active preset hours (e.g. 24). null if custom range is active. */
  activeHours: number | null;
  /** Called when a preset is clicked */
  onPreset: (hours: number) => void;
  /** Called when a custom date range is applied. Dates are ISO strings. */
  onCustomRange: (from: string, to: string) => void;
  /** Called when custom range is cleared (reverts to preset) */
  onClearCustom: () => void;
  /** Whether a custom range is currently active */
  customFrom?: string | null;
  customTo?: string | null;
}

export function DateRangeFilter({
  activeHours,
  onPreset,
  onCustomRange,
  onClearCustom,
  customFrom,
  customTo,
}: DateRangeFilterProps) {
  const [showPicker, setShowPicker] = useState(false);
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!showPicker) return;
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setShowPicker(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [showPicker]);
  const isCustomActive = !!(customFrom && customTo);

  function applyCustom() {
    if (!fromDate || !toDate) return;
    const from = new Date(fromDate + "T00:00:00").toISOString();
    const to = new Date(toDate + "T23:59:59").toISOString();
    onCustomRange(from, to);
    setShowPicker(false);
  }

  function clearCustom() {
    onClearCustom();
    setFromDate("");
    setToDate("");
    setShowPicker(false);
  }

  return (
    <div className="flex items-center gap-1.5">
      {/* Preset buttons */}
      {PRESETS.map((p) => (
        <button
          key={p.label}
          onClick={() => { clearCustom(); onPreset(p.hours); }}
          className="px-2.5 py-1 rounded-lg text-[11px] font-medium transition-colors"
          style={{
            background: !isCustomActive && activeHours === p.hours ? "hsl(var(--primary))" : "hsl(var(--muted))",
            color: !isCustomActive && activeHours === p.hours ? "white" : "hsl(var(--muted-foreground))",
            border: !isCustomActive && activeHours === p.hours ? "1px solid hsl(var(--primary))" : "1px solid hsl(var(--border))",
          }}
        >
          {p.label}
        </button>
      ))}

      {/* Custom range toggle */}
      <div className="relative" ref={containerRef}>
        <button
          onClick={() => setShowPicker((v) => !v)}
          className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] font-medium transition-colors"
          style={{
            background: isCustomActive ? "hsl(var(--primary) / 0.1)" : "hsl(var(--muted))",
            color: isCustomActive ? "hsl(var(--primary))" : "hsl(var(--muted-foreground))",
            border: isCustomActive ? "1px solid hsl(var(--primary) / 0.3)" : "1px solid hsl(var(--border))",
          }}
        >
          <Calendar size={11} />
          {isCustomActive ? "Custom" : "Range"}
        </button>

        {/* Custom range picker dropdown */}
        {showPicker && (
          <div
            className="absolute top-full right-0 mt-1.5 z-50 rounded-xl p-3 space-y-2.5 shadow-xl"
            style={{
              background: "hsl(var(--card))",
              border: "1px solid hsl(var(--border))",
              backdropFilter: "blur(12px)",
              minWidth: 240,
            }}
          >
            <p className="text-[11px] font-semibold text-muted-foreground uppercase tracking-widest">Custom range</p>
            <div className="space-y-2">
              <div>
                <label className="text-[10px] text-muted-foreground block mb-0.5">From</label>
                <input
                  type="date"
                  value={fromDate}
                  onChange={(e) => setFromDate(e.target.value)}
                  className="input-base h-8 text-[12px] w-full"
                />
              </div>
              <div>
                <label className="text-[10px] text-muted-foreground block mb-0.5">To</label>
                <input
                  type="date"
                  value={toDate}
                  onChange={(e) => setToDate(e.target.value)}
                  className="input-base h-8 text-[12px] w-full"
                />
              </div>
            </div>
            <div className="flex items-center gap-2 pt-1">
              <button
                onClick={applyCustom}
                disabled={!fromDate || !toDate}
                className="flex-1 py-1.5 rounded-lg text-[11px] font-medium transition-colors"
                style={{
                  background: fromDate && toDate ? "hsl(var(--primary))" : "hsl(var(--muted))",
                  color: fromDate && toDate ? "white" : "hsl(var(--muted-foreground))",
                  opacity: fromDate && toDate ? 1 : 0.5,
                  cursor: fromDate && toDate ? "pointer" : "not-allowed",
                }}
              >
                Apply
              </button>
              {isCustomActive && (
                <button onClick={clearCustom} className="p-1.5 rounded-lg hover:bg-accent/40 transition-colors" title="Clear custom range">
                  <X size={12} className="text-muted-foreground" />
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
