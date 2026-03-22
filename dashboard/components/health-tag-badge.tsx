"use client";

import type { HealthTag } from "@/lib/types";

const TAG_CONFIG: Record<
  HealthTag,
  { label: string; bg: string; text: string; dot: string }
> = {
  success: {
    label: "Success",
    bg: "bg-emerald-500/10",
    text: "text-emerald-400",
    dot: "bg-emerald-400",
  },
  success_with_fallback: {
    label: "Fallback",
    bg: "bg-yellow-500/10",
    text: "text-yellow-400",
    dot: "bg-yellow-400",
  },
  loop_detected: {
    label: "Loop",
    bg: "bg-red-500/10",
    text: "text-red-400",
    dot: "bg-red-400",
  },
  budget_exceeded: {
    label: "Budget",
    bg: "bg-red-500/10",
    text: "text-red-400",
    dot: "bg-red-400",
  },
  tool_failure: {
    label: "Failure",
    bg: "bg-red-500/10",
    text: "text-red-400",
    dot: "bg-red-400",
  },
  circuit_breaker_open: {
    label: "Circuit Open",
    bg: "bg-red-500/10",
    text: "text-red-400",
    dot: "bg-red-400",
  },
  timeout: {
    label: "Timeout",
    bg: "bg-yellow-500/10",
    text: "text-yellow-400",
    dot: "bg-yellow-400",
  },
  schema_drift: {
    label: "Schema Drift",
    bg: "bg-blue-500/10",
    text: "text-blue-400",
    dot: "bg-blue-400",
  },
};

interface HealthTagBadgeProps {
  tag: HealthTag | null;
}

export function HealthTagBadge({ tag }: HealthTagBadgeProps) {
  if (!tag) return null;

  const config = TAG_CONFIG[tag];
  if (!config) return null;

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${config.bg} ${config.text}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${config.dot}`} />
      {config.label}
    </span>
  );
}
