"use client";

import { useState, useEffect } from "react";
import useSWR from "swr";
import { AreaChart, Area, ResponsiveContainer } from "recharts";
import { RefreshCw, AlertTriangle, Clock, Server, CheckCircle } from "lucide-react";
import { fetcher, triggerHealthCheck, getServerHistoty } from "@/lib/api";
import { cn, STATUS_BG, STATUS_ICON, timeAgo, formatLatency } from "@/lib/utils";
import { toast } from "sonner";
import type { HealthResult } from "@/lib/types";

/* ── Status pulse ───────────────────────────────────────────── */
function StatusPulse({ status }: { status: string }) {
  const colors: Record<string, string> = {
    up: "#22c55e", degraded: "#eab308", down: "#ef4444",
    stale: "#6b7280", unknown: "#6b7280",
  };
  const color = colors[status] ?? "#6b7280";
  return (
    <span className="relative flex w-2.5 h-2.5 flex-shrink-0">
      {status === "up" && (
        <span
          className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-60"
          style={{ background: color }}
        />
      )}
      <span className="relative inline-flex rounded-full w-2.5 h-2.5" style={{ background: color }} />
    </span>
  );
}

/* ── Server card ────────────────────────────────────────────── */
function ServerCard({
  server, selected, onSelect,
}: {
  server: HealthResult; selected: boolean; onSelect: () => void;
}) {
  return (
    <div
      onClick={onSelect}
      className={cn(
        "rounded-xl border p-5 cursor-pointer transition-all card-hover",
        selected && "border-primary/50 bg-primary/5"
      )}
      style={{
        background: selected ? undefined : "hsl(var(--card))",
        borderColor: selected ? "hsl(var(--primary) / 0.5)" : "hsl(var(--border))",
      }}
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-2.5 min-w-0">
          <StatusPulse status={server.status} />
          <span
            className="text-[13px] font-mono font-semibold text-foreground truncate"
            style={{ fontFamily: "var(--font-geist-mono)" }}
          >
            {server.server_name}
          </span>
        </div>
        <span
          className={cn(
            "text-[10px] px-2 py-0.5 rounded-full border font-semibold flex-shrink-0 ml-2",
            STATUS_BG[server.status as keyof typeof STATUS_BG]
          )}
        >
          {STATUS_ICON[server.status as keyof typeof STATUS_ICON]} {server.status}
        </span>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-3">
        {[
          { label: "Latency", value: formatLatency(server.latency_ms) },
          { label: "Tools",   value: server.tools_count?.toString() || "—" },
          { label: "Checked", value: timeAgo(server.checked_at) },
        ].map((stat) => (
          <div key={stat.label}>
            <p className="text-[10px] font-medium text-muted-foreground mb-0.5 uppercase tracking-wide">
              {stat.label}
            </p>
            <p
              className="text-[13px] font-semibold text-foreground"
              style={{ fontFamily: stat.label === "Latency" ? "var(--font-geist-mono)" : undefined }}
            >
              {stat.value}
            </p>
          </div>
        ))}
      </div>

      {/* Error */}
      {server.error && (
        <div
          className="mt-3 flex items-start gap-1.5 text-xs rounded-lg px-2.5 py-2"
          style={{ background: "hsl(var(--danger-bg))", color: "hsl(var(--danger))" }}
        >
          <AlertTriangle size={11} className="flex-shrink-0 mt-0.5" />
          <span className="truncate">{server.error}</span>
        </div>
      )}

      {/* Schema hash */}
      {server.schema_hash && (
        <div className="mt-2 flex items-center gap-1.5 text-[10px] text-muted-foreground">
          <span>Schema:</span>
          <code style={{ fontFamily: "var(--font-geist-mono)" }}>
            {server.schema_hash.slice(0, 8)}…
          </code>
          {server.status === "degraded" && (
            <span className="font-semibold" style={{ color: "hsl(var(--warning))" }}>
              ↑ changed
            </span>
          )}
        </div>
      )}
    </div>
  );
}

/* ── History panel ──────────────────────────────────────────── */
function HistoryPanel({ serverName }: { serverName: string }) {
  const [history, setHistory] = useState<HealthResult[] | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getServerHistoty(serverName, 30)
      .then((h) => { setHistory(h); setLoading(false); })
      .catch(() => setLoading(false));
  }, [serverName]);

  const sparkData = history?.map((h) => ({ v: h.latency_ms ?? 0 })) ?? [];
  const avgLatency = history && history.length > 0
    ? history.reduce((s, h) => s + (h.latency_ms ?? 0), 0) / history.length
    : null;
  const upRate = history && history.length > 0
    ? (history.filter((h) => h.status === "up").length / history.length * 100).toFixed(1)
    : null;

  return (
    <div
      className="rounded-xl border overflow-hidden"
      style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
    >
      <div className="section-header">
        <h2>
          <code style={{ fontFamily: "var(--font-geist-mono)" }}>{serverName}</code>
          <span className="text-muted-foreground font-normal ml-2">— history</span>
        </h2>
        <div className="flex items-center gap-4 text-xs text-muted-foreground">
          {upRate && (
            <span>
              <span className="font-semibold" style={{ color: "hsl(var(--success))" }}>{upRate}%</span> uptime
            </span>
          )}
          {avgLatency && (
            <span>
              avg <span className="font-mono font-semibold text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>
                {avgLatency.toFixed(0)}ms
              </span>
            </span>
          )}
        </div>
      </div>

      {loading ? (
        <div className="p-5">
          <div className="skeleton h-20 rounded-lg" />
        </div>
      ) : sparkData.length > 0 ? (
        <div className="px-5 pt-4 pb-2">
          <div className="h-20">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={sparkData}>
                <Area
                  type="monotone"
                  dataKey="v"
                  stroke="hsl(var(--primary))"
                  fill="hsl(var(--primary))"
                  fillOpacity={0.08}
                  strokeWidth={1.5}
                  dot={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      ) : null}

      {history && history.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr
                style={{
                  borderBottom: "1px solid hsl(var(--border))",
                  background: "hsl(var(--card-raised))",
                }}
              >
                {["Time", "Status", "Latency", "Tools", "Error"].map((h) => (
                  <th
                    key={h}
                    className="px-5 py-2.5 text-left text-[11px] font-semibold text-muted-foreground uppercase tracking-wide"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y" style={{ borderColor: "hsl(var(--border))" }}>
              {history.slice(0, 10).map((h, i) => (
                <tr key={i} className="hover:bg-accent/30 transition-colors">
                  <td
                    className="px-5 py-2.5 text-[12px] text-muted-foreground"
                    style={{ fontFamily: "var(--font-geist-mono)" }}
                  >
                    {timeAgo(h.checked_at)}
                  </td>
                  <td className="px-5 py-2.5">
                    <span
                      className={cn(
                        "text-[10px] px-1.5 py-0.5 rounded-full border font-semibold",
                        STATUS_BG[h.status as keyof typeof STATUS_BG]
                      )}
                    >
                      {h.status}
                    </span>
                  </td>
                  <td
                    className="px-5 py-2.5 text-[12px] font-semibold text-foreground"
                    style={{ fontFamily: "var(--font-geist-mono)" }}
                  >
                    {formatLatency(h.latency_ms)}
                  </td>
                  <td className="px-5 py-2.5 text-[12px] text-muted-foreground">
                    {h.tools_count || "—"}
                  </td>
                  <td
                    className="px-5 py-2.5 text-[11px] truncate max-w-xs"
                    style={{ color: "hsl(var(--danger))" }}
                  >
                    {h.error || ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/* ── Page ───────────────────────────────────────────────────── */
export default function HealthPage() {
  const { data: servers, isLoading, mutate } =
    useSWR<HealthResult[]>("/api/health/servers", fetcher, { refreshInterval: 30_000 });
  const [selected, setSelected] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);

  const up    = servers?.filter((s) => s.status === "up").length ?? 0;
  const total = servers?.length ?? 0;
  const down  = servers?.filter((s) => s.status === "down").length ?? 0;

  async function runCheck() {
    setChecking(true);
    try {
      await triggerHealthCheck();
      await mutate();
      toast.success("Health checks complete");
    } catch {
      toast.error("Check failed — is langsight serve running?");
    } finally {
      setChecking(false);
    }
  }

  return (
    <div className="space-y-5 page-in">
      {/* ── Header ────────────────────────────────────────────── */}
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-foreground">Tool Health</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            {isLoading
              ? "Loading…"
              : total === 0
              ? "No tools configured"
              : `${up}/${total} healthy · refreshes every 30s`
            }
          </p>
        </div>
        <button onClick={runCheck} disabled={checking} className="btn btn-secondary">
          <RefreshCw size={13} className={checking ? "animate-spin" : ""} />
          {checking ? "Checking…" : "Run Check"}
        </button>
      </div>

      {/* ── Status summary bar ────────────────────────────────── */}
      {!isLoading && total > 0 && (
        <div
          className="flex items-center gap-4 px-4 py-3 rounded-xl border text-sm"
          style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
        >
          <div className="flex items-center gap-1.5">
            <CheckCircle size={14} className="text-emerald-500" />
            <span className="font-semibold text-emerald-500">{up}</span>
            <span className="text-muted-foreground">up</span>
          </div>
          {servers?.filter((s) => s.status === "degraded").length ? (
            <div className="flex items-center gap-1.5">
              <AlertTriangle size={14} className="text-yellow-500" />
              <span className="font-semibold text-yellow-500">
                {servers?.filter((s) => s.status === "degraded").length}
              </span>
              <span className="text-muted-foreground">degraded</span>
            </div>
          ) : null}
          {down > 0 && (
            <div className="flex items-center gap-1.5">
              <Server size={14} style={{ color: "hsl(var(--danger))" }} />
              <span className="font-semibold" style={{ color: "hsl(var(--danger))" }}>{down}</span>
              <span className="text-muted-foreground">down</span>
            </div>
          )}
          <div className="flex-1" />
          <span className="text-xs text-muted-foreground">
            Click a server to view history
          </span>
        </div>
      )}

      {/* ── Server grid ───────────────────────────────────────── */}
      {isLoading ? (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 3 }).map((_, i) => (
            <div
              key={i}
              className="rounded-xl border p-5 space-y-4"
              style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
            >
              <div className="flex justify-between items-center">
                <div className="skeleton h-4 w-32 rounded" />
                <div className="skeleton h-5 w-16 rounded-full" />
              </div>
              <div className="grid grid-cols-3 gap-3">
                {[1,2,3].map((j) => (
                  <div key={j} className="space-y-1.5">
                    <div className="skeleton h-2.5 w-12 rounded" />
                    <div className="skeleton h-4 w-16 rounded" />
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : total === 0 ? (
        <div
          className="rounded-xl border p-12 text-center"
          style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
        >
          <div
            className="w-14 h-14 rounded-2xl flex items-center justify-center mx-auto mb-4"
            style={{ background: "hsl(var(--muted))" }}
          >
            <Clock size={22} className="text-muted-foreground" />
          </div>
          <p className="text-sm font-semibold text-foreground mb-1">No tools configured</p>
          <p className="text-xs text-muted-foreground">
            Run <code className="mono-pill-primary">langsight init</code> to discover MCP servers and tool backends
          </p>
        </div>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {servers?.map((s) => (
            <ServerCard
              key={s.server_name}
              server={s}
              selected={selected === s.server_name}
              onSelect={() => setSelected(selected === s.server_name ? null : s.server_name)}
            />
          ))}
        </div>
      )}

      {/* ── History panel ─────────────────────────────────────── */}
      {selected && <HistoryPanel serverName={selected} />}
    </div>
  );
}
