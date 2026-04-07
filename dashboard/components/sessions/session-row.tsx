"use client";

import { memo } from "react";
import { useRouter } from "next/navigation";
import { ChevronRight, Clock, Zap } from "lucide-react";
import { cn, formatDuration, formatExact } from "@/lib/utils";
import { Timestamp } from "@/components/timestamp";
import { HealthTagBadge } from "@/components/health-tag-badge";
import type { AgentSession, HealthTag } from "@/lib/types";

function effectiveHealthTag(s: AgentSession): HealthTag | "incomplete" | null {
  if (s.health_tag) return s.health_tag;
  if (s.failed_calls > 0) return "tool_failure";
  if (s.tool_calls > 0) return "success";
  if (!s.has_prompt) return "incomplete";
  return null;
}

export { effectiveHealthTag };

export const SessionRow = memo(function SessionRow({ session }: { session: AgentSession }) {
  const router = useRouter();
  const s = session;

  return (
    <tr
      onClick={() => router.push(`/sessions/${s.session_id}`)}
      className="cursor-pointer transition-colors text-sm group hover:bg-accent/40 border-l-[3px] border-l-transparent"
    >
      <td className="px-4 py-3 whitespace-nowrap">
        <div className="flex items-center gap-2">
          <ChevronRight size={12} className="text-muted-foreground group-hover:text-primary transition-colors w-4 flex-shrink-0" />
          <span className="text-[12px] font-mono text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>
            {s.session_id}
          </span>
        </div>
      </td>
      <td className="px-4 py-3 text-[12px] text-muted-foreground whitespace-nowrap">
        {s.agent_name || "—"}
      </td>
      <td className="px-4 py-3 whitespace-nowrap">
        <HealthTagBadge tag={effectiveHealthTag(s)} />
      </td>
      <td className="px-4 py-3 text-[12px] text-right whitespace-nowrap">
        <span className="flex items-center justify-end gap-1 text-muted-foreground">
          <Zap size={10} />
          {s.tool_calls}
        </span>
      </td>
      <td className="px-4 py-3 text-[12px] text-right whitespace-nowrap">
        {s.failed_calls > 0 ? (
          <span className="font-semibold" style={{ color: "hsl(var(--danger))" }}>{s.failed_calls}</span>
        ) : (
          <span className="text-muted-foreground">0</span>
        )}
      </td>
      <td className="px-4 py-3 text-[12px] text-right text-muted-foreground whitespace-nowrap" style={{ fontFamily: "var(--font-geist-mono)" }}>
        {formatDuration(s.duration_ms)}
      </td>
      <td className="px-4 py-3 text-[11px] text-right text-muted-foreground whitespace-nowrap" style={{ fontFamily: "var(--font-geist-mono)" }}>
        {(s.total_input_tokens || s.total_output_tokens) ? (
          <span>↑{(s.total_input_tokens ?? 0).toLocaleString()} ↓{(s.total_output_tokens ?? 0).toLocaleString()}</span>
        ) : "—"}
      </td>
      <td className="px-4 py-3 text-[11px] text-right whitespace-nowrap" style={{ fontFamily: "var(--font-geist-mono)" }}>
        {s.est_cost_usd != null ? (
          <span style={{ color: "hsl(var(--foreground))" }}>
            ${s.est_cost_usd < 0.01 ? s.est_cost_usd.toFixed(4) : s.est_cost_usd.toFixed(2)}
          </span>
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </td>
      <td className="px-4 py-3 whitespace-nowrap">
        <div className="flex flex-nowrap gap-1">
          {(s.servers_used || []).slice(0, 2).map((srv) => (
            <span key={srv} className="px-1.5 py-0.5 rounded text-[10px]" style={{
              background: "hsl(var(--muted))",
              border: "1px solid hsl(var(--border))",
              color: "hsl(var(--muted-foreground))",
              fontFamily: "var(--font-geist-mono)",
            }}>
              {srv}
            </span>
          ))}
          {(s.servers_used?.length ?? 0) > 2 && (
            <span className="text-[10px] text-muted-foreground">+{s.servers_used.length - 2}</span>
          )}
        </div>
      </td>
      <td className="px-4 py-3 text-[12px] text-muted-foreground whitespace-nowrap">
        <div className="flex items-center gap-1">
          <Clock size={11} />
          <Timestamp iso={s.first_call_at} compact />
        </div>
      </td>
      <td className="px-4 py-3 text-[11px] text-muted-foreground tabular-nums whitespace-nowrap" style={{ fontFamily: "var(--font-geist-mono)", opacity: 0.7 }}>
        {formatExact(s.first_call_at)}
      </td>
    </tr>
  );
});
