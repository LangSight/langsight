"use client";

import { useState, useEffect } from "react";
import useSWR from "swr";
import { AreaChart, Area, ResponsiveContainer } from "recharts";
import { RefreshCw, AlertTriangle, Search, ChevronRight, Server as ServerIcon } from "lucide-react";
import { fetcher, triggerHealthCheck, getServerHistory } from "@/lib/api";
import { cn, STATUS_BG, formatLatency, formatExact } from "@/lib/utils";
import { Timestamp } from "@/components/timestamp";
import { DateRangeFilter } from "@/components/date-range-filter";
import { toast } from "sonner";
import type { HealthResult } from "@/lib/types";

/* ── Uptime dots — last N checks as colored squares ─────────── */
function UptimeDots({ history }: { history: HealthResult[] }) {
  const dots = history.slice(0, 30).reverse();
  return (
    <div className="flex items-center gap-[2px]">
      {dots.map((h, i) => {
        const color = h.status === "up" ? "#22c55e" : h.status === "degraded" ? "#eab308" : h.status === "down" ? "#ef4444" : "#3f3f46";
        return (
          <div key={i} className="group relative">
            <div className="w-[6px] h-[14px] rounded-[1px] transition-all hover:scale-y-125" style={{ background: color }} />
            <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 hidden group-hover:block z-50">
              <div className="rounded-md px-2 py-1 text-[9px] whitespace-nowrap shadow-lg" style={{ background: "hsl(var(--card-raised))", border: "1px solid hsl(var(--border))" }}>
                <span className="font-semibold" style={{ color }}>{h.status}</span>
                <span className="text-muted-foreground ml-1.5"><Timestamp iso={h.checked_at} compact /></span>
                {h.latency_ms != null && <span className="text-muted-foreground ml-1.5" style={{ fontFamily: "var(--font-geist-mono)" }}>{Math.round(h.latency_ms)}ms</span>}
              </div>
            </div>
          </div>
        );
      })}
      {dots.length === 0 && Array.from({ length: 10 }).map((_, i) => (
        <div key={i} className="w-[6px] h-[14px] rounded-[1px]" style={{ background: "#27272a" }} />
      ))}
    </div>
  );
}

/* ── Inline latency sparkline ──────────────────────────────── */
function LatencySparkline({ history }: { history: HealthResult[] }) {
  const data = history.slice(0, 20).reverse().map((h) => ({ v: h.latency_ms ?? 0 }));
  if (data.length < 2) return <span className="text-[11px] text-muted-foreground">—</span>;
  return (
    <div style={{ width: 64, height: 20 }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data}>
          <Area type="monotone" dataKey="v" stroke="hsl(var(--primary))" fill="hsl(var(--primary))" fillOpacity={0.1} strokeWidth={1.2} dot={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

/* ── Expanded row: full history ────────────────────────────── */
function ExpandedHistory({ serverName }: { serverName: string }) {
  const [history, setHistory] = useState<HealthResult[] | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getServerHistory(serverName, 50)
      .then((h) => { setHistory(h); setLoading(false); })
      .catch(() => setLoading(false));
  }, [serverName]);

  if (loading) return <div className="p-4"><div className="skeleton h-24 rounded-lg" /></div>;
  if (!history || history.length === 0) return <div className="p-4 text-[11px] text-muted-foreground">No history available</div>;

  const avgLatency = history.reduce((s, h) => s + (h.latency_ms ?? 0), 0) / history.length;
  const upRate = (history.filter((h) => h.status === "up").length / history.length * 100).toFixed(1);
  const sparkData = history.map((h) => ({ v: h.latency_ms ?? 0 })).reverse();

  return (
    <div className="border-t" style={{ borderColor: "hsl(var(--border))", background: "hsl(var(--muted) / 0.3)" }}>
      {/* Summary + chart */}
      <div className="px-5 py-4 flex items-start gap-6">
        <div className="flex-1">
          <div className="flex items-center gap-4 mb-3">
            <div className="flex items-center gap-1.5">
              <span className="text-[10px] text-muted-foreground uppercase tracking-wide">Uptime</span>
              <span className="text-[13px] font-bold" style={{ color: Number(upRate) > 95 ? "#22c55e" : Number(upRate) > 80 ? "#eab308" : "#ef4444", fontFamily: "var(--font-geist-mono)" }}>{upRate}%</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="text-[10px] text-muted-foreground uppercase tracking-wide">Avg latency</span>
              <span className="text-[13px] font-bold text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>{Math.round(avgLatency)}ms</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="text-[10px] text-muted-foreground uppercase tracking-wide">Checks</span>
              <span className="text-[13px] font-bold text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>{history.length}</span>
            </div>
          </div>
          {sparkData.length > 2 && (
            <div className="h-16 rounded-lg overflow-hidden" style={{ border: "1px solid hsl(var(--border))", background: "hsl(var(--card))" }}>
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={sparkData}>
                  <Area type="monotone" dataKey="v" stroke="hsl(var(--primary))" fill="hsl(var(--primary))" fillOpacity={0.06} strokeWidth={1.5} dot={false} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      </div>

      {/* History table */}
      <div className="overflow-x-auto">
        <table className="w-full text-[11px]">
          <thead>
            <tr style={{ borderTop: "1px solid hsl(var(--border))", borderBottom: "1px solid hsl(var(--border))", background: "hsl(var(--card-raised))" }}>
              {["Time", "Timestamp", "Status", "Latency", "Tools", "Error"].map((h) => (
                <th key={h} className="px-5 py-2 text-left font-semibold text-muted-foreground uppercase tracking-wide" style={{ fontSize: 9 }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {history.slice(0, 15).map((h, i) => (
              <tr key={i} className="hover:bg-accent/20 transition-colors" style={{ borderBottom: "1px solid hsl(var(--border) / 0.5)" }}>
                <td className="px-5 py-1.5 text-muted-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}><Timestamp iso={h.checked_at} compact /></td>
                <td className="px-5 py-1.5 text-[10px] text-muted-foreground tabular-nums" style={{ fontFamily: "var(--font-geist-mono)", opacity: 0.7 }}>{formatExact(h.checked_at)}</td>
                <td className="px-5 py-1.5">
                  <span className={cn("text-[9px] px-1.5 py-0.5 rounded-full border font-semibold", STATUS_BG[h.status as keyof typeof STATUS_BG])}>{h.status}</span>
                </td>
                <td className="px-5 py-1.5 font-semibold text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>{formatLatency(h.latency_ms)}</td>
                <td className="px-5 py-1.5 text-muted-foreground">{h.tools_count || "—"}</td>
                <td className="px-5 py-1.5 max-w-xs" style={{ color: "hsl(var(--danger))" }}>
                  {h.error ? <span className="block truncate" title={h.error}>{h.error}</span> : ""}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ── Server row ────────────────────────────────────────────── */
function ServerRow({ server, expanded, onToggle }: {
  server: HealthResult;
  expanded: boolean;
  onToggle: () => void;
}) {
  const statusColor = server.status === "up" ? "#22c55e" : server.status === "degraded" ? "#eab308" : "#ef4444";
  return (
    <div className="rounded-xl border overflow-hidden transition-all" style={{ background: "hsl(var(--card))", borderColor: expanded ? "hsl(var(--primary) / 0.4)" : "hsl(var(--border))" }}>
      <div className="flex items-center gap-4 px-5 py-3.5 cursor-pointer hover:bg-accent/20 transition-colors" onClick={onToggle}>
        {/* Status dot */}
        <span className="relative flex w-2.5 h-2.5 flex-shrink-0">
          {server.status === "up" && <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-50" style={{ background: statusColor }} />}
          <span className="relative inline-flex rounded-full w-2.5 h-2.5" style={{ background: statusColor }} />
        </span>

        {/* Name */}
        <span className="text-[13px] font-semibold text-foreground min-w-[140px] truncate" style={{ fontFamily: "var(--font-geist-mono)" }}>{server.server_name}</span>

        {/* Status badge */}
        <span className={cn("text-[9px] px-2 py-0.5 rounded-full border font-semibold flex-shrink-0", STATUS_BG[server.status as keyof typeof STATUS_BG])}>{server.status}</span>

        {/* Latency */}
        <span className="text-[12px] font-semibold text-foreground flex-1 text-right flex-shrink-0" style={{ fontFamily: "var(--font-geist-mono)" }}>{formatLatency(server.latency_ms)}</span>

        {/* Tools count */}
        <span className="text-[11px] text-muted-foreground w-8 text-center flex-shrink-0">{server.tools_count ?? "—"}</span>

        {/* Checked */}
        <span className="text-[10px] text-muted-foreground w-16 text-right flex-shrink-0"><Timestamp iso={server.checked_at} compact /></span>
        <span className="text-[10px] text-muted-foreground w-40 text-right flex-shrink-0 tabular-nums" style={{ fontFamily: "var(--font-geist-mono)", opacity: 0.6 }}>{formatExact(server.checked_at)}</span>

        {/* Chevron */}
        <ChevronRight size={14} className={cn("text-muted-foreground flex-shrink-0 transition-transform", expanded && "rotate-90")} />
      </div>

      {/* Error banner */}
      {server.error && !expanded && (
        <div className="px-5 pb-3 -mt-1">
          <div className="flex items-start gap-1.5 text-[10px] rounded-lg px-2.5 py-1.5" style={{ background: "rgba(239,68,68,0.05)", color: "#ef4444" }}>
            <AlertTriangle size={10} className="flex-shrink-0 mt-0.5" />
            <span className="line-clamp-2">{server.error}</span>
          </div>
        </div>
      )}

      {/* Expanded history */}
      {expanded && <ExpandedHistory serverName={server.server_name} />}
    </div>
  );
}

/* ── Page ───────────────────────────────────────────────────── */
type StatusFilter = "all" | "up" | "degraded" | "down";

export default function HealthPage() {
  const [hours, setHours] = useState<number>(24);
  const { data: servers, isLoading, mutate } = useSWR<HealthResult[]>("/api/health/servers", fetcher, { refreshInterval: 30_000 });
  const [expanded, setExpanded] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<StatusFilter>("all");
  const up = servers?.filter((s) => s.status === "up").length ?? 0;
  const degraded = servers?.filter((s) => s.status === "degraded").length ?? 0;
  const down = servers?.filter((s) => s.status === "down").length ?? 0;
  const total = servers?.length ?? 0;

  const filtered = servers
    ?.filter((s) => filter === "all" || s.status === filter)
    ?.filter((s) => !search || s.server_name.toLowerCase().includes(search.toLowerCase()))
    ?.sort((a, b) => {
      const order: Record<string, number> = { down: 0, degraded: 1, stale: 2, up: 3 };
      return (order[a.status] ?? 4) - (order[b.status] ?? 4);
    }) ?? [];

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

  const filterPills: { label: string; value: StatusFilter; count: number; color?: string }[] = [
    { label: "All", value: "all", count: total },
    { label: "Up", value: "up", count: up, color: "#22c55e" },
    { label: "Degraded", value: "degraded", count: degraded, color: "#eab308" },
    { label: "Down", value: "down", count: down, color: "#ef4444" },
  ];

  return (
    <div className="space-y-4 page-in">
      {/* ── Alert banner (only when DOWN > 0) ───────────────── */}
      {!isLoading && down > 0 && (
        <div className="flex items-center gap-3 px-4 py-3 rounded-xl" style={{ background: "rgba(239,68,68,0.06)", border: "1px solid rgba(239,68,68,0.15)" }}>
          <AlertTriangle size={16} style={{ color: "#ef4444" }} />
          <span className="text-[13px] font-semibold" style={{ color: "#ef4444" }}>
            {down === total ? `All ${total} servers are down` : `${down} of ${total} server${down > 1 ? "s" : ""} down`}
          </span>
          <span className="text-[11px] text-muted-foreground ml-1">— immediate attention required</span>
        </div>
      )}

      {/* ── Header + toolbar ────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-foreground">Tool Health</h1>
          <p className="text-[12px] text-muted-foreground mt-0.5">
            {isLoading ? "Loading…" : total === 0 ? "No servers configured" : `${total} servers · refreshes every 30s`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <DateRangeFilter
            activeHours={hours}
            onPreset={(h) => setHours(h)}
          />
          {/* Search */}
          <div className="relative">
            <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              type="text" value={search} onChange={(e) => setSearch(e.target.value)}
              placeholder="Filter servers..."
              className="input-base pl-8 pr-3 h-[32px] text-[12px] w-[180px]"
            />
          </div>
          <button onClick={runCheck} disabled={checking} className="btn btn-secondary h-[32px] text-[12px]">
            <RefreshCw size={12} className={checking ? "animate-spin" : ""} />
            {checking ? "Checking…" : "Run Check"}
          </button>
        </div>
      </div>

      {/* ── Filter pills ────────────────────────────────────── */}
      {!isLoading && total > 0 && (
        <div className="flex items-center gap-1.5">
          {filterPills.map((pill) => (
            <button
              key={pill.value}
              onClick={() => setFilter(pill.value)}
              className={cn(
                "px-3 py-1.5 rounded-lg text-[11px] font-medium transition-all",
                filter === pill.value ? "text-foreground" : "text-muted-foreground hover:text-foreground hover:bg-accent/40",
              )}
              style={{
                background: filter === pill.value ? "hsl(var(--card))" : undefined,
                border: filter === pill.value ? "1px solid hsl(var(--border))" : "1px solid transparent",
                boxShadow: filter === pill.value ? "0 1px 3px rgba(0,0,0,0.08)" : undefined,
              }}
            >
              {pill.color && <span className="inline-block w-1.5 h-1.5 rounded-full mr-1.5" style={{ background: pill.color }} />}
              {pill.label}
              {pill.count > 0 && <span className="ml-1.5 text-[9px] text-muted-foreground">{pill.count}</span>}
            </button>
          ))}
        </div>
      )}

      {/* ── Table header ────────────────────────────────────── */}
      {!isLoading && total > 0 && (
        <div className="hidden sm:flex items-center gap-4 px-5 text-[9px] font-semibold text-muted-foreground uppercase tracking-wide">
          <span className="w-2.5" /> {/* dot */}
          <span className="min-w-[140px]">Server</span>
          <span className="w-14">Status</span>
          <span className="flex-1 text-right">Latency</span>
          <span className="w-8 text-center">Tools</span>
          <span className="w-16 text-right">Last Checked</span>
          <span className="w-40 text-right">Timestamp</span>
          <span className="w-3.5" /> {/* chevron */}
        </div>
      )}

      {/* ── Server rows ─────────────────────────────────────── */}
      {isLoading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="rounded-xl border p-5" style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}>
              <div className="flex items-center gap-4">
                <div className="skeleton w-2.5 h-2.5 rounded-full" />
                <div className="skeleton h-4 w-32 rounded" />
                <div className="skeleton h-5 w-14 rounded-full" />
                <div className="flex-1" />
                <div className="skeleton h-4 w-12 rounded" />
              </div>
            </div>
          ))}
        </div>
      ) : total === 0 ? (
        <div className="rounded-xl border p-12 text-center" style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}>
          <div className="w-14 h-14 rounded-2xl flex items-center justify-center mx-auto mb-4" style={{ background: "hsl(var(--muted))" }}>
            <ServerIcon size={22} className="text-muted-foreground" />
          </div>
          <p className="text-sm font-semibold text-foreground mb-1">No servers configured</p>
          <p className="text-xs text-muted-foreground">
            Run <code className="mono-pill-primary">langsight init</code> to discover MCP servers
          </p>
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-xl border p-8 text-center" style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}>
          <p className="text-sm text-muted-foreground">No servers match your filter</p>
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map((s) => (
            <ServerRow
              key={s.server_name}
              server={s}
              expanded={expanded === s.server_name}
              onToggle={() => setExpanded(expanded === s.server_name ? null : s.server_name)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
