"use client";

import { timeAgo, formatExact } from "@/lib/utils";

interface TimestampProps {
  iso: string;
  className?: string;
  /** Show only relative time (compact mode for tight spaces) */
  compact?: boolean;
}

/**
 * Displays both relative ("16h ago") and exact ("Mar 22, 14:30:05") timestamps.
 * In compact mode, shows only relative with exact in tooltip.
 */
export function Timestamp({ iso, className, compact }: TimestampProps) {
  const exact = formatExact(iso);
  const relative = timeAgo(iso);

  if (compact) {
    return (
      <time dateTime={iso} title={exact} className={className} style={{ cursor: "default" }}>
        {relative}
      </time>
    );
  }

  return (
    <time dateTime={iso} title={exact} className={className}>
      <span>{relative}</span>
      <span className="text-muted-foreground" style={{ opacity: 0.6 }}> · {exact}</span>
    </time>
  );
}
