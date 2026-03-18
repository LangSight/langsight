"use client";

import { useState } from "react";
import useSWR from "swr";
import { Area, AreaChart, ResponsiveContainer } from "recharts";
import { RefreshCw, TrendingUp, AlertTriangle, Clock } from "lucide-react";
import { fetcher, triggerHealthCheck, getServerHistoty } from "@/lib/api";
import { cn, STATUS_BG, STATUS_ICON, timeAgo, formatLatency } from "@/lib/utils";
import { toast } from "sonner";
import type { HealthResult } from "@/lib/types";

function StatusPulse({ status }: { status: string }) {
  const colors: Record<string, string> = { up: "#22c55e", degraded: "#eab308", down: "#ef4444", stale: "#6b7280", unknown: "#6b7280" };
  const c = colors[status] ?? "#6b7280";
  return (
    <span className="relative flex w-2.5 h-2.5">
      {status === "up" && <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-60" style={{ background: c }}/>}
      <span className="relative inline-flex rounded-full w-2.5 h-2.5" style={{ background: c }}/>
    </span>
  );
}

function ServerCard({ server, onSelect, selected }: { server: HealthResult; onSelect: () => void; selected: boolean }) {
  return (
    <div
      onClick={onSelect}
      className={cn("rounded-xl border p-4 cursor-pointer transition-all hover:-translate-y-0.5", selected && "ring-2")}
      style={{
        background: "hsl(var(--card))",
        borderColor: selected ? "hsl(var(--primary))" : "hsl(var(--border))",
        ...(selected ? { "--tw-ring-color": "hsl(var(--primary))" } as React.CSSProperties : {}),
      }}>
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <StatusPulse status={server.status}/>
          <span className="text-sm font-mono font-medium" style={{ color: "hsl(var(--foreground))" }}>{server.server_name}</span>
        </div>
        <span className={cn("text-xs px-2 py-0.5 rounded-full border font-medium", STATUS_BG[server.status as keyof typeof STATUS_BG])}>
          {STATUS_ICON[server.status as keyof typeof STATUS_ICON]} {server.status}
        </span>
      </div>
      <div className="grid grid-cols-3 gap-2 text-[11px]" style={{ color: "hsl(var(--muted-foreground))" }}>
        <div><p className="font-medium mb-0.5">Latency</p><p className="font-mono">{formatLatency(server.latency_ms)}</p></div>
        <div><p className="font-medium mb-0.5">Tools</p><p className="font-mono">{server.tools_count || "—"}</p></div>
        <div><p className="font-medium mb-0.5">Checked</p><p>{timeAgo(server.checked_at)}</p></div>
      </div>
      {server.error && (
        <div className="mt-3 flex items-center gap-1.5 text-xs text-red-500">
          <AlertTriangle size={11}/><span className="truncate">{server.error}</span>
        </div>
      )}
      {server.schema_hash && (
        <div className="mt-2 flex items-center gap-1.5 text-[10px]" style={{ color: "hsl(var(--muted-foreground))" }}>
          <span>Schema:</span><span className="font-mono">{server.schema_hash.slice(0, 8)}…</span>
          {server.status === "degraded" && <span className="text-yellow-500 font-medium">↑ changed</span>}
        </div>
      )}
    </div>
  );
}

function HistoryPanel({ serverName }: { serverName: string }) {
  const [history, setHistory] = useState<HealthResult[] | null>(null);
  const [loading, setLoading] = useState(true);

  useState(() => {
    getServerHistoty(serverName, 30)
      .then(h => { setHistory(h); setLoading(false); })
      .catch(() => setLoading(false));
  });

  const sparkData = history?.map(h => ({ v: h.latency_ms ?? 0, s: h.status })) ?? [];
  const avgLatency = history && history.length > 0
    ? history.reduce((s, h) => s + (h.latency_ms ?? 0), 0) / history.length
    : null;
  const upRate = history && history.length > 0
    ? (history.filter(h => h.status === "up").length / history.length * 100).toFixed(1)
    : null;

  return (
    <div className="rounded-xl border p-5 mt-4" style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold" style={{ color: "hsl(var(--foreground))" }}>
          {serverName} — history
        </h3>
        <div className="flex items-center gap-4 text-xs" style={{ color: "hsl(var(--muted-foreground))" }}>
          {upRate && <span><span className="text-emerald-500 font-medium">{upRate}%</span> uptime</span>}
          {avgLatency && <span>avg <span className="font-mono font-medium">{avgLatency.toFixed(0)}ms</span></span>}
        </div>
      </div>
      {loading ? (
        <div className="h-20 skeleton rounded-lg"/>
      ) : sparkData.length > 0 ? (
        <div className="h-20 mb-4">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={sparkData}>
              <Area type="monotone" dataKey="v" stroke="hsl(var(--primary))" fill="hsl(var(--primary))" fillOpacity={0.1} strokeWidth={1.5} dot={false}/>
            </AreaChart>
          </ResponsiveContainer>
        </div>
      ) : null}
      {history && history.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr style={{ borderBottom: "1px solid hsl(var(--border))" }}>
                {["Time","Status","Latency","Tools","Error"].map(h => (
                  <th key={h} className="text-left pb-2 pr-4 font-medium" style={{ color: "hsl(var(--muted-foreground))" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y" style={{ borderColor: "hsl(var(--border))" }}>
              {history.slice(0, 10).map((h, i) => (
                <tr key={i}>
                  <td className="py-2 pr-4 font-mono" style={{ color: "hsl(var(--muted-foreground))" }}>{timeAgo(h.checked_at)}</td>
                  <td className="py-2 pr-4">
                    <span className={cn("px-1.5 py-0.5 rounded-full border text-[10px]", STATUS_BG[h.status as keyof typeof STATUS_BG])}>
                      {h.status}
                    </span>
                  </td>
                  <td className="py-2 pr-4 font-mono" style={{ color: "hsl(var(--foreground))" }}>{formatLatency(h.latency_ms)}</td>
                  <td className="py-2 pr-4" style={{ color: "hsl(var(--muted-foreground))" }}>{h.tools_count || "—"}</td>
                  <td className="py-2 text-red-500 truncate max-w-xs">{h.error || ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default function HealthPage() {
  const { data: servers, isLoading, mutate } =
    useSWR<HealthResult[]>("/api/health/servers", fetcher, { refreshInterval: 30_000 });
  const [selected, setSelected] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);

  const up = servers?.filter(s => s.status === "up").length ?? 0;
  const total = servers?.length ?? 0;

  async function runCheck() {
    setChecking(true);
    try { await triggerHealthCheck(); await mutate(); toast.success("Health checks complete"); }
    catch { toast.error("Check failed — is langsight serve running?"); }
    finally { setChecking(false); }
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold" style={{ color: "hsl(var(--foreground))" }}>Tool Health</h1>
          <p className="text-sm" style={{ color: "hsl(var(--muted-foreground))" }}>
            {isLoading ? "Loading…" : `${up}/${total} tool backends healthy · refreshes every 30s`}
          </p>
        </div>
        <button onClick={runCheck} disabled={checking}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-60"
          style={{ background: "hsl(var(--primary))" }}>
          <RefreshCw size={14} className={checking ? "animate-spin" : ""}/>
          {checking ? "Checking…" : "Run Check"}
        </button>
      </div>

      {isLoading ? (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="rounded-xl border p-4 space-y-3" style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}>
              <div className="flex justify-between"><span className="skeleton h-4 w-32 rounded"/><span className="skeleton h-5 w-16 rounded-full"/></div>
              <div className="grid grid-cols-3 gap-2"><span className="skeleton h-8 rounded"/><span className="skeleton h-8 rounded"/><span className="skeleton h-8 rounded"/></div>
            </div>
          ))}
        </div>
      ) : servers?.length === 0 ? (
        <div className="rounded-xl border p-12 text-center" style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}>
          <Clock size={40} className="mx-auto mb-4 opacity-20"/>
          <p className="font-medium mb-1" style={{ color: "hsl(var(--foreground))" }}>No tools configured</p>
          <p className="text-sm" style={{ color: "hsl(var(--muted-foreground))" }}>Run <code>langsight init</code> to discover MCP servers and tool backends</p>
        </div>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {servers?.map(s => (
            <ServerCard key={s.server_name} server={s}
              selected={selected === s.server_name}
              onSelect={() => setSelected(selected === s.server_name ? null : s.server_name)}/>
          ))}
        </div>
      )}

      {selected && <HistoryPanel serverName={selected}/>}
    </div>
  );
}
