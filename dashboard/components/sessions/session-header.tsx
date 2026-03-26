"use client";

/**
 * SessionHeader — back button + session ID + agent chain + quick stats.
 * Extracted from session detail page to keep that file manageable.
 */

import { GitBranch, Clock, ArrowLeft } from "lucide-react";
import { Timestamp } from "@/components/timestamp";
import { HealthTagBadge } from "@/components/health-tag-badge";
import { formatDuration, formatExact } from "@/lib/utils";
import type { AgentSession, SessionTrace, SpanNode } from "@/lib/types";

interface SessionHeaderProps {
  sessionId: string;
  trace: SessionTrace | null;
  session: AgentSession | undefined;
  onBack: () => void;
}

export function SessionHeader({ sessionId, trace, session, onBack }: SessionHeaderProps) {
  return (
    <div className="flex-shrink-0 pb-3">
      <button
        onClick={onBack}
        className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors mb-3"
      >
        <ArrowLeft size={14} />
        Back to Sessions
      </button>

      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3 min-w-0">
          <GitBranch size={15} className="text-primary flex-shrink-0" />
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <code
                className="text-[13px] text-foreground truncate"
                style={{ fontFamily: "var(--font-geist-mono)" }}
              >
                {sessionId}
              </code>
              {trace && (() => {
                const agents = Array.from(
                  new Set(trace.spans_flat.map((s: SpanNode) => s.agent_name).filter(Boolean))
                );
                return agents.length > 0 ? (
                  <span className="text-[11px] text-primary font-medium flex-shrink-0">
                    {agents.join(" → ")}
                  </span>
                ) : session?.agent_name ? (
                  <span className="text-[11px] text-primary font-medium flex-shrink-0">
                    {session.agent_name}
                  </span>
                ) : null;
              })()}
              {(session?.health_tag || (trace && trace.failed_calls === 0)) && (
                <HealthTagBadge
                  tag={session?.health_tag ?? (trace && trace.failed_calls > 0 ? "tool_failure" : "success")}
                />
              )}
            </div>
            <div
              className="flex items-center flex-wrap gap-1.5 text-[10px] text-muted-foreground mt-0.5"
              style={{ fontFamily: "var(--font-geist-mono)" }}
            >
              {trace && (
                <>
                  <span>{trace.total_spans} spans</span>
                  <span className="opacity-40">·</span>
                  <span>{trace.tool_calls} {trace.tool_calls === 1 ? "call" : "calls"}</span>
                  {trace.failed_calls > 0 && (
                    <>
                      <span className="opacity-40">·</span>
                      <span style={{ color: "hsl(var(--danger))" }} className="font-semibold">
                        {trace.failed_calls} failed
                      </span>
                    </>
                  )}
                  {trace.duration_ms && (
                    <>
                      <span className="opacity-40">·</span>
                      <span>{formatDuration(trace.duration_ms)}</span>
                    </>
                  )}
                </>
              )}
              {session && (
                <>
                  <span className="opacity-40">·</span>
                  <span className="flex items-center gap-1">
                    <Clock size={9} />
                    <Timestamp iso={session.first_call_at} compact />
                  </span>
                  <span className="opacity-40">·</span>
                  <span>{formatExact(session.first_call_at)}</span>
                </>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
