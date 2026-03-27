"use client";

export const dynamic = "force-dynamic";

import { useEffect, useMemo, useState } from "react";
import useSWR from "swr";
import {
  Server, ChevronRight, Search, RefreshCw, ChevronDown,
  ChevronUp, ChevronLast, AlertTriangle, X, Bot,
} from "lucide-react";
import { AreaChart, Area, ResponsiveContainer } from "recharts";
import { fetcher, triggerHealthCheck, getServerHistory, listServerMetadata, upsertServerMetadata, discoverServers } from "@/lib/api";
import { useProject } from "@/lib/project-context";
import { cn, timeAgo, formatLatency, STATUS_BG, formatExact } from "@/lib/utils";
import { Timestamp } from "@/components/timestamp";
import { toast } from "sonner";
import { EditableTextarea, EditableText, EditableTags, EditableUrl } from "@/components/editable-field";
import type { HealthResult, ServerMetadata, LineageGraph, ToolReliability } from "@/lib/types";

/* ── Helpers ────────────────────────────────────────────────── */
const STATUS_COLOR: Record<string, string> = { up: "#22c55e", degraded: "#eab308", down: "#ef4444", stale: "#6b7280" };

function StatusDot({ status, pulse }: { status: string; pulse?: boolean }) {
  return (
    <span className="relative flex w-2 h-2 flex-shrink-0">
      {pulse && status === "up" && <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-40" style={{ background: STATUS_COLOR[status] }} />}
      <span className="relative inline-flex rounded-full w-2 h-2" style={{ background: STATUS_COLOR[status] ?? "#6b7280" }} />
    </span>
  );
}

function UptimeDots({ history }: { history: HealthResult[] }) {
  const dots = history.slice(0, 20).reverse();
  return (
    <div className="flex items-center gap-[2px]">
      {dots.map((h, i) => (
        <div key={i} className="w-[5px] h-[12px] rounded-[1px] transition-all hover:scale-y-125" style={{ background: STATUS_COLOR[h.status] ?? "#27272a" }} />
      ))}
      {dots.length === 0 && Array.from({ length: 10 }).map((_, i) => (
        <div key={i} className="w-[5px] h-[12px] rounded-[1px]" style={{ background: "#27272a" }} />
      ))}
    </div>
  );
}

function SparkLine({ history }: { history: HealthResult[] }) {
  const data = history.slice(0, 20).reverse().map((h) => ({ v: h.latency_ms ?? 0 }));
  if (data.length < 2) return null;
  return (
    <div style={{ width: 56, height: 18 }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data}>
          <Area type="monotone" dataKey="v" stroke="hsl(var(--primary))" fill="hsl(var(--primary))" fillOpacity={0.1} strokeWidth={1.2} dot={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

/* ── Sort table ─────────────────────────────────────────────── */
type SortCol = "name" | "status" | "latency" | "uptime" | "tools" | "checked" | "lastUsed";

interface InvocationStat {
  server_name: string;
  last_called_at: string | null;
  last_call_ok: boolean;
  last_call_status: string;
  total_calls: number;
  success_rate_pct: number;
}

function ThCell({ col, label, sortCol, sortDir, onSort, className }: { col: SortCol; label: string; sortCol: SortCol; sortDir: "asc" | "desc"; onSort: (c: SortCol) => void; className?: string }) {
  const active = sortCol === col;
  return (
    <th className={cn("px-3 py-2.5 text-left cursor-pointer select-none hover:bg-accent/30 transition-colors", className)} onClick={() => onSort(col)}>
      <div className="flex items-center gap-1">
        <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">{label}</span>
        {active ? (sortDir === "asc" ? <ChevronUp size={10} className="text-primary" /> : <ChevronDown size={10} className="text-primary" />) : <ChevronDown size={10} className="opacity-20" />}
      </div>
    </th>
  );
}

/* ── Server table (State 1) ─────────────────────────────────── */
function ServerTable({ servers, metaByName, historyCache, invByName, onSelect, onRunCheck, checking }: {
  servers: HealthResult[]; metaByName: Map<string, ServerMetadata>; historyCache: Map<string, HealthResult[]>;
  invByName: Map<string, InvocationStat>; onSelect: (name: string) => void; onRunCheck: () => void; checking: boolean;
}) {
  const [sortCol, setSortCol] = useState<SortCol>("status");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "up" | "degraded" | "down">("all");

  const counts = useMemo(() => ({
    all: servers.length,
    up: servers.filter((s) => s.status === "up").length,
    degraded: servers.filter((s) => s.status === "degraded").length,
    down: servers.filter((s) => s.status === "down").length,
  }), [servers]);

  const attention = useMemo(() => servers.filter((s) => s.status === "down" || s.status === "degraded"), [servers]);

  function handleSort(col: SortCol) {
    if (sortCol === col) setSortDir((d) => d === "asc" ? "desc" : "asc");
    else { setSortCol(col); setSortDir(sortCol === "status" ? "asc" : "desc"); }
  }

  const sorted = useMemo(() => {
    const statusOrder: Record<string, number> = { down: 0, degraded: 1, stale: 2, up: 3 };
    const base = servers.filter((s) => (statusFilter === "all" || s.status === statusFilter) && (!search || s.server_name.toLowerCase().includes(search.toLowerCase())));
    return [...base].sort((a, b) => {
      let diff = 0;
      if (sortCol === "name") diff = a.server_name.localeCompare(b.server_name);
      else if (sortCol === "status") diff = (statusOrder[a.status] ?? 4) - (statusOrder[b.status] ?? 4);
      else if (sortCol === "latency") diff = (a.latency_ms ?? 9999) - (b.latency_ms ?? 9999);
      else if (sortCol === "tools") diff = (b.tools_count ?? 0) - (a.tools_count ?? 0);
      else if (sortCol === "checked") diff = new Date(b.checked_at).getTime() - new Date(a.checked_at).getTime();
      else if (sortCol === "lastUsed") {
        const tA = invByName.get(a.server_name)?.last_called_at ?? "";
        const tB = invByName.get(b.server_name)?.last_called_at ?? "";
        diff = tB.localeCompare(tA);
      }
      else if (sortCol === "uptime") {
        const upA = historyCache.get(a.server_name) ?? []; const upB = historyCache.get(b.server_name) ?? [];
        const rateA = upA.length ? upA.filter((h) => h.status === "up").length / upA.length : 0;
        const rateB = upB.length ? upB.filter((h) => h.status === "up").length / upB.length : 0;
        diff = rateB - rateA;
      }
      return sortDir === "asc" ? diff : -diff;
    });
  }, [servers, sortCol, sortDir, search, statusFilter, historyCache]);

  return (
    <div className="flex flex-col h-full gap-3">
      {/* Filter row */}
      <div className="flex items-center gap-3 flex-shrink-0">
        <div className="relative">
          <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input type="text" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search servers..." className="input-base pl-8 pr-3 h-[30px] text-[12px] w-[200px]" />
        </div>
        <div className="flex items-center gap-1">
          {(["all", "down", "degraded", "up"] as const).map((f) => (
            <button key={f} onClick={() => setStatusFilter(f)}
              className={cn("px-2.5 py-1 rounded-lg text-[10px] font-medium transition-all", statusFilter === f ? "text-foreground" : "text-muted-foreground hover:text-foreground hover:bg-accent/40")}
              style={{ background: statusFilter === f ? "hsl(var(--card))" : undefined, border: statusFilter === f ? "1px solid hsl(var(--border))" : "1px solid transparent" }}>
              {f !== "all" && <span className="inline-block w-1.5 h-1.5 rounded-full mr-1" style={{ background: STATUS_COLOR[f] }} />}
              {f.charAt(0).toUpperCase() + f.slice(1)} <span className="text-muted-foreground">{counts[f as keyof typeof counts]}</span>
            </button>
          ))}
        </div>
        <button onClick={onRunCheck} disabled={checking} className="ml-auto btn btn-secondary h-[30px] text-[11px]">
          <RefreshCw size={11} className={checking ? "animate-spin" : ""} />
          {checking ? "Checking…" : "Run Check"}
        </button>
      </div>

      {/* Needs attention */}
      {attention.length > 0 && statusFilter === "all" && !search && (
        <div className="flex-shrink-0 rounded-xl border px-4 py-2.5" style={{ background: "rgba(239,68,68,0.04)", borderColor: "rgba(239,68,68,0.15)" }}>
          <div className="flex items-center gap-2 mb-2">
            <AlertTriangle size={12} style={{ color: "#ef4444" }} />
            <span className="text-[11px] font-semibold" style={{ color: "#ef4444" }}>Needs Attention · {attention.length} server{attention.length > 1 ? "s" : ""}</span>
          </div>
          <div className="flex flex-wrap gap-2">
            {attention.map((s) => (
              <button key={s.server_name} onClick={() => onSelect(s.server_name)}
                className="flex items-center gap-1.5 rounded-lg px-2.5 py-1 hover:opacity-80 transition-opacity"
                style={{ background: `${STATUS_COLOR[s.status]}10`, border: `1px solid ${STATUS_COLOR[s.status]}30` }}>
                <StatusDot status={s.status} />
                <span className="text-[11px] font-medium text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>{s.server_name}</span>
                {s.error && <span className="text-[9px] text-muted-foreground truncate max-w-[120px]">{s.error}</span>}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Table */}
      <div className="flex-1 rounded-xl border overflow-auto" style={{ borderColor: "hsl(var(--border))" }}>
        <table className="w-full border-collapse">
          <thead className="sticky top-0 z-10" style={{ background: "hsl(var(--card-raised))", borderBottom: "1px solid hsl(var(--border))" }}>
            <tr>
              <th className="w-7 px-3 py-2.5" />
              <ThCell col="name" label="Server" sortCol={sortCol} sortDir={sortDir} onSort={handleSort} className="min-w-[160px]" />
              <th className="px-3 py-2.5 text-left text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">Owner</th>
              <th className="px-3 py-2.5 text-left text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">Tags</th>
              <ThCell col="status" label="Status" sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />
              <ThCell col="latency" label="Latency" sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />
              <th className="px-3 py-2.5 text-left text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">Trend</th>
              <ThCell col="uptime" label="Uptime" sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />
              <ThCell col="tools" label="Tools" sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />
              <ThCell col="checked" label="Last Checked" sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />
              <ThCell col="lastUsed" label="Last Used" sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />
              <th className="px-3 py-2.5 text-left text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">Last OK?</th>
              <th className="px-3 py-2.5 text-left text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">Timestamp</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((server) => {
              const meta = metaByName.get(server.server_name);
              const hist = historyCache.get(server.server_name) ?? [];
              const upPct = hist.length > 0 ? (hist.filter((h) => h.status === "up").length / hist.length * 100) : null;
              return (
                <tr key={server.server_name} onClick={() => onSelect(server.server_name)}
                  className="cursor-pointer hover:bg-accent/20 transition-colors border-b" style={{ borderColor: "hsl(var(--border))" }}>
                  <td className="px-3 py-2.5"><StatusDot status={server.status} pulse /></td>
                  <td className="px-3 py-2.5">
                    <span className="text-[12px] font-semibold text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>{server.server_name}</span>
                    {meta?.description && <p className="text-[10px] text-muted-foreground truncate max-w-[220px]">{meta.description}</p>}
                  </td>
                  <td className="px-3 py-2.5 text-[11px] text-muted-foreground">{meta?.owner ?? <span className="opacity-30">—</span>}</td>
                  <td className="px-3 py-2.5">
                    <div className="flex flex-wrap gap-1">
                      {(meta?.tags ?? []).slice(0, 2).map((t) => <span key={t} className="text-[8px] px-1.5 py-0.5 rounded" style={{ background: "hsl(var(--primary) / 0.06)", color: "hsl(var(--primary))" }}>{t}</span>)}
                      {(meta?.tags ?? []).length > 2 && <span className="text-[8px] text-muted-foreground">+{(meta?.tags ?? []).length - 2}</span>}
                    </div>
                  </td>
                  <td className="px-3 py-2.5">
                    <span className={cn("text-[9px] px-1.5 py-0.5 rounded-full border font-semibold", STATUS_BG[server.status as keyof typeof STATUS_BG])}>{server.status}</span>
                  </td>
                  <td className="px-3 py-2.5 text-[11px] font-semibold text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>{formatLatency(server.latency_ms)}</td>
                  <td className="px-3 py-2.5"><SparkLine history={hist} /></td>
                  <td className="px-3 py-2.5">
                    {upPct !== null ? <span className="text-[11px] font-semibold" style={{ fontFamily: "var(--font-geist-mono)", color: upPct > 95 ? "#22c55e" : upPct > 80 ? "#eab308" : "#ef4444" }}>{upPct.toFixed(0)}%</span> : <span className="text-[11px] text-muted-foreground">—</span>}
                  </td>
                  <td className="px-3 py-2.5 text-[11px] text-muted-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>{server.tools_count ?? "—"}</td>
                  <td className="px-3 py-2.5 text-[11px] text-muted-foreground">
                    {invByName.get(server.server_name)?.last_called_at
                      ? <Timestamp iso={invByName.get(server.server_name)!.last_called_at!} compact />
                      : <span className="opacity-30">never</span>}
                  </td>
                  <td className="px-3 py-2.5">
                    {(() => {
                      const inv = invByName.get(server.server_name);
                      if (!inv?.last_called_at) return <span className="text-[10px] text-muted-foreground opacity-30">—</span>;
                      return inv.last_call_ok
                        ? <span className="inline-flex items-center gap-1 text-[10px] font-semibold" style={{ color: "#22c55e" }}>✓ success</span>
                        : <span className="inline-flex items-center gap-1 text-[10px] font-semibold" style={{ color: "#ef4444" }}>✗ {inv.last_call_status}</span>;
                    })()}
                  </td>
                  <td className="px-3 py-2.5 text-[11px] text-muted-foreground"><Timestamp iso={server.checked_at} compact /></td>
                  <td className="px-3 py-2.5 text-[10px] text-muted-foreground tabular-nums" style={{ fontFamily: "var(--font-geist-mono)", opacity: 0.7 }}>{formatExact(server.checked_at)}</td>
                </tr>
              );
            })}
            {sorted.length === 0 && <tr><td colSpan={11} className="text-center py-12 text-sm text-muted-foreground">No servers match</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ── Grouped sidebar (State 2) ──────────────────────────────── */
function GroupedSidebar({ servers, metaByName, selectedServer, onSelect, search, onSearchChange }: {
  servers: HealthResult[]; metaByName: Map<string, ServerMetadata>; selectedServer: string | null;
  onSelect: (n: string) => void; search: string; onSearchChange: (v: string) => void;
}) {
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set(["up"]));
  const toggleGroup = (g: string) => setCollapsedGroups((p) => { const n = new Set(p); n.has(g) ? n.delete(g) : n.add(g); return n; });

  const groups = useMemo(() => {
    const f = search ? servers.filter((s) => s.server_name.toLowerCase().includes(search.toLowerCase())) : servers;
    return { down: f.filter((s) => s.status === "down"), degraded: f.filter((s) => s.status === "degraded"), up: f.filter((s) => s.status === "up" || s.status === "stale") };
  }, [servers, search]);

  function Group({ name, items, label }: { name: string; items: HealthResult[]; label: string }) {
    if (items.length === 0) return null;
    const isCollapsed = collapsedGroups.has(name);
    const color = STATUS_COLOR[name] ?? "#6b7280";
    return (
      <div>
        <button onClick={() => toggleGroup(name)} className="w-full flex items-center justify-between px-3 py-1.5 hover:bg-accent/20 transition-colors">
          <div className="flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full" style={{ background: color }} />
            <span className="text-[9px] font-semibold text-muted-foreground uppercase tracking-wide">{label}</span>
            <span className="text-[9px] text-muted-foreground ml-1">{items.length}</span>
          </div>
          {isCollapsed ? <ChevronRight size={10} className="text-muted-foreground" /> : <ChevronDown size={10} className="text-muted-foreground" />}
        </button>
        {!isCollapsed && items.map((s) => {
          const isSel = selectedServer === s.server_name;
          return (
            <button key={s.server_name} onClick={() => onSelect(s.server_name)}
              className="w-full flex items-center gap-2.5 px-3 py-1.5 text-left hover:bg-accent/20 transition-colors"
              style={{ background: isSel ? "hsl(var(--primary) / 0.06)" : undefined, borderLeft: isSel ? "2px solid hsl(var(--primary))" : "2px solid transparent" }}>
              <StatusDot status={s.status} />
              <span className="flex-1 text-[11px] font-medium text-foreground truncate" style={{ fontFamily: "var(--font-geist-mono)" }}>{s.server_name}</span>
              <span className="text-[9px] text-muted-foreground flex-shrink-0">{s.tools_count ?? 0}t</span>
            </button>
          );
        })}
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full border-r" style={{ borderColor: "hsl(var(--border))", background: "hsl(var(--background))" }}>
      <div className="flex-shrink-0 px-3 py-2.5 border-b" style={{ borderColor: "hsl(var(--border))" }}>
        <div className="relative">
          <Search size={11} className="absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input type="text" value={search} onChange={(e) => onSearchChange(e.target.value)} placeholder="Search..." className="w-full pl-6 pr-2 py-1.5 text-[11px] rounded-md bg-transparent border outline-none" style={{ borderColor: "hsl(var(--border))", color: "hsl(var(--foreground))" }} />
        </div>
      </div>
      <div className="flex-1 overflow-y-auto py-1">
        <Group name="down" items={groups.down} label="Down" />
        <Group name="degraded" items={groups.degraded} label="Degraded" />
        <Group name="up" items={groups.up} label="Healthy" />
        {groups.down.length + groups.degraded.length + groups.up.length === 0 && <p className="text-center text-[11px] text-muted-foreground py-8">No servers match</p>}
      </div>
    </div>
  );
}

/* ── History detail inside right panel ─────────────────────── */
function HealthHistoryPanel({ serverName }: { serverName: string }) {
  const [history, setHistory] = useState<HealthResult[] | null>(null);
  useEffect(() => { getServerHistory(serverName, 50).then(setHistory).catch(() => setHistory([])); }, [serverName]);

  if (!history) return <div className="space-y-2">{[1, 2, 3].map((i) => <div key={i} className="skeleton h-6 rounded-lg" />)}</div>;
  if (history.length === 0) return <p className="text-[11px] text-muted-foreground">No history available</p>;

  const upPct = (history.filter((h) => h.status === "up").length / history.length * 100).toFixed(1);
  const avgMs = Math.round(history.reduce((s, h) => s + (h.latency_ms ?? 0), 0) / history.length);
  const sparkData = history.map((h) => ({ v: h.latency_ms ?? 0 })).reverse();

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-2">
        {[{ label: "Uptime", value: `${upPct}%`, danger: Number(upPct) < 80 }, { label: "Avg Latency", value: `${avgMs}ms` }, { label: "Checks", value: history.length.toString() }].map((t) => (
          <div key={t.label} className="rounded-lg p-3" style={{ background: "hsl(var(--muted))", border: "0.5px solid hsl(var(--border))" }}>
            <p className="text-[9px] text-muted-foreground uppercase tracking-wide mb-1">{t.label}</p>
            <p className="text-[13px] font-bold" style={{ fontFamily: "var(--font-geist-mono)", color: t.danger ? "#ef4444" : "hsl(var(--foreground))" }}>{t.value}</p>
          </div>
        ))}
      </div>
      {sparkData.length > 2 && (
        <div className="h-16 rounded-lg overflow-hidden" style={{ border: "1px solid hsl(var(--border))", background: "hsl(var(--card))" }}>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={sparkData}><Area type="monotone" dataKey="v" stroke="hsl(var(--primary))" fill="hsl(var(--primary))" fillOpacity={0.06} strokeWidth={1.5} dot={false} /></AreaChart>
          </ResponsiveContainer>
        </div>
      )}
      <div className="space-y-1">
        {history.slice(0, 15).map((h, i) => (
          <div key={i} className="flex items-center gap-3 rounded-lg px-3 py-1.5 text-[10px]" style={{ background: "hsl(var(--muted) / 0.5)" }}>
            <StatusDot status={h.status} />
            <span className="text-muted-foreground flex-shrink-0"><Timestamp iso={h.checked_at} /></span>
            <span className="font-semibold text-foreground w-12" style={{ fontFamily: "var(--font-geist-mono)" }}>{formatLatency(h.latency_ms)}</span>
            {h.error && <span className="text-red-400 truncate">{h.error}</span>}
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── Page ───────────────────────────────────────────────────── */
type DetailTab = "about" | "tools" | "health" | "consumers";

export default function ServersPage() {
  const { activeProject } = useProject();
  const pid = activeProject?.id ?? null;
  const pq = pid ? `?project_id=${encodeURIComponent(pid)}` : "";
  const [selectedServer, setSelectedServer] = useState<string | null>(null);
  const [sidebarSearch, setSidebarSearch] = useState("");
  const [activeTab, setActiveTab] = useState<DetailTab>("about");
  const [checking, setChecking] = useState(false);
  const [discovering, setDiscovering] = useState(false);

  async function runDiscover() {
    setDiscovering(true);
    try {
      const res = await discoverServers(pid);
      if (res.discovered > 0) {
        toast.success(`Discovered ${res.discovered} server${res.discovered > 1 ? "s" : ""}: ${res.servers.join(", ")}`);
        await Promise.all([mutate(), mutateMetadata()]);
      } else {
        toast.info("No new servers found in traces. Run your agent first, then discover.");
      }
    } catch {
      toast.error("Discover failed");
    } finally {
      setDiscovering(false);
    }
  }

  const { data: servers, isLoading, mutate } = useSWR<HealthResult[]>(`/api/health/servers${pq ? `?${pq.slice(1)}` : ""}`, fetcher, { refreshInterval: 30_000 });
  const { data: metadata, mutate: mutateMetadata } = useSWR<ServerMetadata[]>(`/api/servers/metadata${pq}`, () => listServerMetadata(pid), { refreshInterval: 60_000 });
  const { data: lineage } = useSWR<LineageGraph>(`/api/agents/lineage?hours=24${pid ? `&project_id=${encodeURIComponent(pid)}` : ""}`, fetcher, { refreshInterval: 60_000 });
  const { data: toolReliability } = useSWR<ToolReliability[]>(`/api/reliability/tools?hours=24${pid ? `&project_id=${encodeURIComponent(pid)}` : ""}`, fetcher, { refreshInterval: 60_000 });
  const { data: invocations } = useSWR<InvocationStat[]>(`/api/health/servers/invocations?hours=168${pid ? `&project_id=${encodeURIComponent(pid)}` : ""}`, fetcher, { refreshInterval: 60_000 });
  const invByName = useMemo(() => new Map((invocations ?? []).map(i => [i.server_name, i])), [invocations]);
  const { data: declaredTools } = useSWR<{ tool_name: string; description: string; input_schema: Record<string, unknown> }[]>(
    selectedServer ? `/api/servers/${encodeURIComponent(selectedServer)}/tools${pq}` : null,
    fetcher,
    { refreshInterval: 60_000 },
  );
  const metaByName = useMemo(() => { const m = new Map<string, ServerMetadata>(); for (const meta of metadata ?? []) m.set(meta.server_name, meta); return m; }, [metadata]);
  const selected = useMemo(() => servers?.find((s) => s.server_name === selectedServer) ?? null, [servers, selectedServer]);

  // Consumers from lineage
  const consumers = useMemo(() => {
    if (!selected || !lineage) return [] as { agent: string; calls: number; errors: number }[];
    const id = `server:${selected.server_name}`;
    return lineage.edges.filter((e) => e.target === id && e.type === "calls").map((e) => ({ agent: e.source.replace("agent:", ""), calls: e.metrics.call_count ?? 0, errors: e.metrics.error_count ?? 0 }));
  }, [selected, lineage]);

  async function runCheck() {
    setChecking(true);
    try { await triggerHealthCheck(); await mutate(); toast.success("Health checks complete"); }
    catch { toast.error("Check failed — is langsight serve running?"); }
    finally { setChecking(false); }
  }

  function selectServer(name: string) { setSelectedServer(selectedServer === name ? null : name); setActiveTab("about"); }

  return (
    <div className="flex flex-col page-in" style={{ height: "calc(100vh - 8rem)" }}>
      {/* Header */}
      <div className="flex-shrink-0 flex items-center justify-between mb-4">
        <div>
          <h1 className="text-xl font-bold text-foreground">MCP Servers</h1>
          <p className="text-[12px] text-muted-foreground mt-0.5">
            {isLoading ? "Loading…" : `${servers?.length ?? 0} server${(servers?.length ?? 0) !== 1 ? "s" : ""} · catalog + health`}
          </p>
        </div>
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="flex-1 space-y-2">{[1, 2, 3].map((i) => <div key={i} className="skeleton h-12 w-full rounded-xl" />)}</div>
      ) : !servers?.length ? (
        <div className="flex-1 flex flex-col items-center justify-center rounded-xl border" style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}>
          <Server size={28} className="mb-3 text-muted-foreground opacity-40" />
          <p className="text-sm font-semibold text-foreground mb-1">No servers found</p>
          <p className="text-xs text-muted-foreground mb-4">Auto-register servers seen in your agent traces</p>
          <button
            onClick={runDiscover}
            disabled={discovering}
            className="btn btn-primary flex items-center gap-2 text-xs px-4 py-2"
          >
            {discovering ? <span className="animate-spin">⟳</span> : <Search size={13} />}
            {discovering ? "Discovering…" : "Discover from traces"}
          </button>
        </div>
      ) : (
        <>
          {/* State 1: Full-width table */}
          {!selectedServer && (
            <div className="flex-1 min-h-0">
              <ServerTable servers={servers} metaByName={metaByName} historyCache={new Map()} invByName={invByName} onSelect={selectServer} onRunCheck={runCheck} checking={checking} />
            </div>
          )}

          {/* State 2: Sidebar + detail */}
          {selectedServer && selected && (
            <div className="flex-1 min-h-0 flex rounded-xl border overflow-hidden" style={{ borderColor: "hsl(var(--border))" }}>
              {/* Sidebar */}
              <div className="flex-shrink-0" style={{ width: 280 }}>
                <GroupedSidebar servers={servers} metaByName={metaByName} selectedServer={selectedServer} onSelect={selectServer} search={sidebarSearch} onSearchChange={setSidebarSearch} />
              </div>

              {/* Detail */}
              <div className="flex-1 min-w-0 flex flex-col" style={{ background: "hsl(var(--background))" }}>
                {/* Header */}
                <div className="flex-shrink-0 px-5 pt-4 pb-0 border-b" style={{ borderColor: "hsl(var(--border))", background: "hsl(var(--card))" }}>
                  <div className="flex items-center gap-3 mb-3">
                    <div className="w-9 h-9 rounded-xl flex items-center justify-center" style={{ background: "hsl(var(--primary) / 0.08)" }}>
                      <Server size={16} style={{ color: "hsl(var(--primary))" }} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-[14px] font-bold text-foreground truncate" style={{ fontFamily: "var(--font-geist-mono)" }}>{selected.server_name}</p>
                      <div className="flex items-center gap-2 mt-0.5">
                        <StatusDot status={selected.status} pulse />
                        <span className="text-[11px]" style={{ color: STATUS_COLOR[selected.status] }}>{selected.status}</span>
                        <span className="text-[10px] text-muted-foreground">· {selected.tools_count ?? 0} tools · last checked <Timestamp iso={selected.checked_at} compact /></span>
                        {selected.latency_ms && <span className="text-[10px] font-semibold text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>{Math.round(selected.latency_ms)}ms</span>}
                      </div>
                    </div>
                    <button onClick={() => setSelectedServer(null)} className="p-1.5 rounded hover:bg-accent/60 text-muted-foreground hover:text-foreground transition-colors"><X size={14} /></button>
                  </div>
                  <div className="flex">
                    {(["about", "tools", "health", "consumers"] as DetailTab[]).map((tab) => {
                      const serverTools = (toolReliability ?? []).filter((t) => t.server_name === selected.server_name);
                      const badge = tab === "consumers" ? consumers.length : tab === "tools" ? serverTools.length : 0;
                      return (
                      <button key={tab} onClick={() => setActiveTab(tab)}
                        className={cn("px-3 py-2 text-[12px] font-medium border-b-2 -mb-px transition-colors capitalize", activeTab === tab ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground")}>
                        {tab}{badge > 0 && <span className="ml-1 text-[9px] text-muted-foreground">{badge}</span>}
                      </button>
                      );
                    })}
                  </div>
                </div>

                {/* Tab content */}
                <div className="flex-1 overflow-y-auto p-5">
                  {/* ABOUT */}
                  {activeTab === "about" && (() => {
                    const meta = metaByName.get(selected.server_name);
                    async function save(field: string, value: string | string[]) {
                      const cur = meta ?? { description: "", owner: "", tags: [] as string[], transport: "", runbook_url: "" };
                      await upsertServerMetadata(selected!.server_name, { ...cur, [field]: value }, pid);
                      mutateMetadata();
                    }
                    return (
                      <div className="space-y-5">
                        <div><p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-1.5">Description</p><EditableTextarea value={meta?.description ?? ""} onSave={(v) => save("description", v)} placeholder="What does this server do? Click to add..." /></div>
                        <div><p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-1.5">Owner</p><EditableText value={meta?.owner ?? ""} onSave={(v) => save("owner", v)} placeholder="Team or person name" /></div>
                        <div><p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-1.5">Tags</p><EditableTags tags={meta?.tags ?? []} onSave={(v) => save("tags", v)} /></div>
                        <div><p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-1.5">Transport</p><EditableText value={meta?.transport ?? ""} onSave={(v) => save("transport", v)} placeholder="stdio / sse / streamable_http" /></div>
                        <div><p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-1.5">Runbook / Docs</p><EditableUrl value={meta?.runbook_url ?? ""} onSave={(v) => save("runbook_url", v)} placeholder="https://..." /></div>
                        {/* Error */}
                        {selected.error && (
                          <div className="rounded-lg px-3 py-2.5" style={{ background: "rgba(239,68,68,0.05)", border: "1px solid rgba(239,68,68,0.15)" }}>
                            <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-1">Last Error</p>
                            <p className="text-[11px]" style={{ color: "#ef4444", fontFamily: "var(--font-geist-mono)" }}>{selected.error}</p>
                          </div>
                        )}
                      </div>
                    );
                  })()}

                  {/* TOOLS */}
                  {activeTab === "tools" && (() => {
                    const reliability = (toolReliability ?? []).filter((t) => t.server_name === selected.server_name);
                    const reliabilityByName = new Map(reliability.map((t) => [t.tool_name, t]));
                    const declared = declaredTools ?? [];

                    // Merge: declared tools as base, observed tools as additions
                    const allToolNames = new Set([...declared.map((t) => t.tool_name), ...reliability.map((t) => t.tool_name)]);
                    const tools = Array.from(allToolNames).sort().map((name) => ({
                      name,
                      description: declared.find((d) => d.tool_name === name)?.description ?? "",
                      inputSchema: declared.find((d) => d.tool_name === name)?.input_schema ?? null,
                      reliability: reliabilityByName.get(name) ?? null,
                      declared: declared.some((d) => d.tool_name === name),
                    }));

                    if (tools.length === 0) return (
                      <div className="space-y-2">
                        <p className="text-[11px] text-muted-foreground">No tools captured yet.</p>
                        <p className="text-[10px] text-muted-foreground">Tools are automatically captured when your agent calls <code className="mono-pill-primary">list_tools()</code> via the LangSight SDK. Once your agent runs, all available tools will appear here with health metrics.</p>
                      </div>
                    );

                    return (
                      <div className="space-y-1.5">
                        {tools.map((tool) => {
                          const rel = tool.reliability;
                          const hasError = rel && rel.error_rate_pct > 0;
                          const dotColor = !rel ? "#6b7280" : rel.error_rate_pct > 20 ? "#ef4444" : rel.is_degraded ? "#eab308" : "#22c55e";
                          return (
                            <div key={tool.name} className="rounded-lg px-3 py-2.5" style={{ background: "hsl(var(--muted))", border: hasError ? "1px solid rgba(239,68,68,0.2)" : "0.5px solid hsl(var(--border))" }}>
                              <div className="flex items-center justify-between mb-1">
                                <div className="flex items-center gap-2">
                                  <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ background: dotColor }} />
                                  <span className="text-[12px] font-semibold text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>{tool.name}</span>
                                  {!tool.declared && <span className="text-[8px] px-1.5 py-0.5 rounded text-muted-foreground" style={{ background: "hsl(var(--border))" }}>observed</span>}
                                </div>
                                {rel && (
                                  <span className="text-[10px] font-semibold" style={{ fontFamily: "var(--font-geist-mono)", color: rel.error_rate_pct > 10 ? "#ef4444" : "#22c55e" }}>
                                    {rel.success_rate_pct.toFixed(0)}%
                                  </span>
                                )}
                              </div>
                              {tool.description && <p className="text-[10px] text-muted-foreground mb-1.5 ml-3.5">{tool.description}</p>}
                              {rel ? (
                                <div className="flex items-center gap-3 text-[10px] text-muted-foreground ml-3.5">
                                  <span style={{ fontFamily: "var(--font-geist-mono)" }}>{rel.total_calls} calls</span>
                                  {rel.error_calls > 0 && <span style={{ color: "#ef4444", fontFamily: "var(--font-geist-mono)" }}>{rel.error_calls} err</span>}
                                  <span style={{ fontFamily: "var(--font-geist-mono)" }}>{Math.round(rel.avg_latency_ms)}ms avg</span>
                                  <div className="flex-1 h-[3px] rounded-full overflow-hidden" style={{ background: "hsl(var(--border))", minWidth: 40, maxWidth: 60 }}>
                                    <div className="h-full rounded-full" style={{ width: `${Math.min(100, rel.success_rate_pct)}%`, background: dotColor }} />
                                  </div>
                                </div>
                              ) : (
                                <p className="text-[10px] text-muted-foreground ml-3.5">No calls in last 24h</p>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    );
                  })()}

                  {/* HEALTH */}
                  {activeTab === "health" && <HealthHistoryPanel serverName={selected.server_name} />}

                  {/* CONSUMERS */}
                  {activeTab === "consumers" && (
                    <div>
                      <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-3">Agents Using This Server</p>
                      {consumers.length === 0 ? (
                        <p className="text-[11px] text-muted-foreground">No agents observed calling this server in the last 24h</p>
                      ) : (
                        <div className="space-y-1">
                          {consumers.map((c) => (
                            <div key={c.agent} className="flex items-center justify-between rounded-lg px-3 py-2.5" style={{ background: "hsl(var(--muted))" }}>
                              <div className="flex items-center gap-2"><Bot size={11} style={{ color: "hsl(var(--primary))" }} /><span className="text-[12px] font-medium text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>{c.agent}</span></div>
                              <div className="flex items-center gap-3 text-[10px]">
                                <span className="text-muted-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>{c.calls} calls</span>
                                {c.errors > 0 && <span style={{ color: "#ef4444", fontFamily: "var(--font-geist-mono)" }}>{c.errors} err</span>}
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
