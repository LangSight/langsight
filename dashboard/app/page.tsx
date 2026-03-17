"use client";

import useSWR from "swr";
import { fetcher, triggerHealthCheck } from "@/lib/api";
import { Card, StatCard, StatusBadge, Loading, ErrorState, PageHeader, Button } from "@/components/ui";
import { timeAgo, formatLatency, STATUS_COLOR } from "@/lib/utils";
import type { HealthResult, AgentSession } from "@/lib/types";
import { useState } from "react";
import Link from "next/link";

export default function OverviewPage() {
  const { data: servers, error: sErr, isLoading: sLoading, mutate: mutateHealth } =
    useSWR<HealthResult[]>("/api/health/servers", fetcher, { refreshInterval: 30_000 });
  const { data: sessions, isLoading: sessLoading } =
    useSWR<AgentSession[]>("/api/agents/sessions?hours=24&limit=5", fetcher, { refreshInterval: 30_000 });
  const { data: status } =
    useSWR("/api/status", fetcher, { refreshInterval: 60_000 });

  const [checking, setChecking] = useState(false);

  const up = servers?.filter(s => s.status === "up").length ?? 0;
  const total = servers?.length ?? 0;
  const critical = servers?.filter(s => s.status === "down").length ?? 0;
  const degraded = servers?.filter(s => s.status === "degraded").length ?? 0;
  const totalSessions = sessions?.length ?? 0;
  const failedSessions = sessions?.filter(s => s.failed_calls > 0).length ?? 0;

  async function runCheck() {
    setChecking(true);
    try { await triggerHealthCheck(); await mutateHealth(); }
    finally { setChecking(false); }
  }

  return (
    <div className="max-w-6xl mx-auto">
      <PageHeader
        title="Overview"
        sub={status ? `v${status.version} · ${status.servers_configured} servers configured` : "LangSight Dashboard"}
        action={<Button onClick={runCheck} loading={checking}>Run Health Check</Button>}
      />

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <StatCard label="Servers Healthy" value={`${up}/${total}`} sub="MCP servers" accent={up === total && total > 0} />
        <StatCard label="Servers Down" value={critical} sub={critical > 0 ? "action required" : "all clear"} />
        <StatCard label="Degraded" value={degraded} sub="schema drift / slow" />
        <StatCard label="Sessions (24h)" value={totalSessions} sub={`${failedSessions} with failures`} />
      </div>

      <div className="grid lg:grid-cols-2 gap-5">
        {/* Server health */}
        <Card>
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold text-white">MCP Servers</h2>
            <Link href="/health" className="text-xs text-indigo-400 hover:underline">View all →</Link>
          </div>
          {sLoading && <Loading />}
          {sErr && <ErrorState message="Could not load server health" />}
          {!sLoading && !sErr && servers?.length === 0 && (
            <p className="text-sm text-center py-8" style={{ color: "var(--muted)" }}>
              No servers configured. Run <code className="text-indigo-400">langsight init</code>.
            </p>
          )}
          {servers && servers.length > 0 && (
            <div className="space-y-2">
              {servers.map(s => (
                <div key={s.server_name}
                  className="flex items-center justify-between py-2 px-3 rounded-lg"
                  style={{ background: "var(--bg)" }}>
                  <div className="flex items-center gap-3">
                    <span className={`text-sm ${STATUS_COLOR[s.status]}`}>●</span>
                    <span className="text-sm text-white font-mono">{s.server_name}</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-xs" style={{ color: "var(--muted)" }}>{formatLatency(s.latency_ms)}</span>
                    <StatusBadge status={s.status} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* Recent sessions */}
        <Card>
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold text-white">Recent Sessions</h2>
            <Link href="/sessions" className="text-xs text-indigo-400 hover:underline">View all →</Link>
          </div>
          {sessLoading && <Loading />}
          {!sessLoading && (!sessions || sessions.length === 0) && (
            <p className="text-sm text-center py-8" style={{ color: "var(--muted)" }}>
              No sessions yet. Instrument your agents with the LangSight SDK.
            </p>
          )}
          {sessions && sessions.length > 0 && (
            <div className="space-y-2">
              {sessions.slice(0, 5).map(s => (
                <Link href={`/sessions?id=${s.session_id}`} key={s.session_id}>
                  <div className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-white/5 transition-colors cursor-pointer"
                    style={{ background: "var(--bg)" }}>
                    <div>
                      <span className="text-sm text-white font-mono">{s.session_id.slice(0, 12)}…</span>
                      <span className="text-xs ml-2" style={{ color: "var(--muted)" }}>{s.agent_name || "unknown"}</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-xs" style={{ color: "var(--muted)" }}>{s.tool_calls} calls</span>
                      {s.failed_calls > 0 && (
                        <span className="text-xs text-red-400">{s.failed_calls} failed</span>
                      )}
                      <span className="text-xs" style={{ color: "var(--muted)" }}>{timeAgo(s.first_call_at)}</span>
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
