"use client";

const PRESETS = [
  { label: "1h", hours: 1 },
  { label: "6h", hours: 6 },
  { label: "24h", hours: 24 },
  { label: "7d", hours: 168 },
  { label: "30d", hours: 720 },
] as const;

interface DateRangeFilterProps {
  /** Currently active preset hours (e.g. 24). */
  activeHours: number;
  /** Called when a preset is clicked */
  onPreset: (hours: number) => void;
}

export function DateRangeFilter({ activeHours, onPreset }: DateRangeFilterProps) {
  return (
    <div className="flex items-center gap-1.5">
      {PRESETS.map((p) => (
        <button
          key={p.label}
          onClick={() => onPreset(p.hours)}
          className="px-2.5 py-1 rounded-lg text-[11px] font-medium transition-colors"
          style={{
            background: activeHours === p.hours ? "hsl(var(--primary))" : "hsl(var(--muted))",
            color: activeHours === p.hours ? "white" : "hsl(var(--muted-foreground))",
            border: activeHours === p.hours ? "1px solid hsl(var(--primary))" : "1px solid hsl(var(--border))",
          }}
        >
          {p.label}
        </button>
      ))}
    </div>
  );
}
