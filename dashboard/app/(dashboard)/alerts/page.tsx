"use client";

export const dynamic = "force-dynamic";

import useSWR from "swr";
import { useState } from "react";
import {
  Bell, BellOff, AlertTriangle, CheckCircle, Send, Clock,
  Zap, Shield, Bot, Server, Activity, XCircle, Check,
  EyeOff, X, ChevronDown,
} from "lucide-react";
import { useProject } from "@/lib/project-context";
import { cn, timeAgo } from "@/lib/utils";
import { fetcher } from "@/lib/api";
import { toast } from "sonner";
import Link from "next/link";
import type { AnomalyResult, FiredAlert, AlertCounts } from "@/lib/types";

/* ── Types ─────────────────────────────────────────────────────── */
interface AlertConfig {
  slack_webhook: string | null;
  alert_types: Record<string, boolean>;
  webhook_configured: boolean;
}

interface IncompleteSession {
  session_id: string;
  agent_name: string;
  last_activity: string;
  span_count: number;
  llm_calls: number;
  tool_calls: number;
}

/* ── Constants ─────────────────────────────────────────────────── */
const SEV_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  critical: { bg: "#ef444415", text: "#ef4444", border: "#ef444430" },
  warning:  { bg: "#f59e0b15", text: "#f59e0b", border: "#f59e0b30" },
  info:     { bg: "#6366f115", text: "#6366f1", border: "#6366f130" },
};

const STATUS_TABS = [
  { key: "active",   label: "Active" },
  { key: "acked",    label: "Acked" },
  { key: "snoozed",  label: "Snoozed" },
  { key: "resolved", label: "Resolved" },
  { key: "all",      label: "All" },
] as const;

const SNOOZE_OPTIONS: { label: string; minutes: 15 | 60 | 240 | 1440 }[] = [
  { label: "15 min", minutes: 15 },
  { label: "1 hour", minutes: 60 },
  { label: "4 hours", minutes: 240 },
  { label: "1 day", minutes: 1440 },
];

const ALERT_TYPE_META: Record<string, { label: string; icon: React.ElementType; color: string; description: string }> = {
  agent_failure:     { label: "Agent Failure",     icon: Bot,           color: "#ef4444", description: "Session with failed tool calls" },
  slo_breached:      { label: "SLO Breached",      icon: Activity,      color: "#f59e0b", description: "Service level objective violated" },
  anomaly_critical:  { label: "Anomaly (Critical)", icon: AlertTriangle, color: "#ef4444", description: "Z-score >= 3.0 deviation from baseline" },
  anomaly_warning:   { label: "Anomaly (Warning)",  icon: AlertTriangle, color: "#f59e0b", description: "Z-score >= 2.0 deviation from baseline" },
  security_critical: { label: "Security Critical",  icon: Shield,        color: "#ef4444", description: "Critical CVE or OWASP finding" },
  security_high:     { label: "Security High",      icon: Shield,        color: "#f97316", description: "High severity security finding" },
  mcp_down:          { label: "MCP Server Down",    icon: Server,        color: "#ef4444", description: "Health check reports server down" },
  mcp_recovered:     { label: "MCP Recovered",      icon: CheckCircle,   color: "#22c55e", description: "Server recovered from down state" },
};

/* ── Toggle ────────────────────────────────────────────────────── */
function Toggle({ checked, onChange, disabled }: { checked: boolean; onChange: () => void; disabled?: boolean }) {
  return (
    <button
      onClick={onChange}
      disabled={disabled}
      className={cn(
        "relative w-9 h-5 rounded-full transition-colors",
        checked ? "bg-primary" : "bg-muted-foreground/30",
        disabled && "opacity-50 cursor-not-allowed",
      )}
    >
      <span className={cn(
        "absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform",
        checked ? "translate-x-[18px]" : "translate-x-0.5",
      )} />
    </button>
  );
}

/* ── Snooze dropdown ───────────────────────────────────────────── */
function SnoozeMenu({ onSnooze }: { onSnooze: (m: 15 | 60 | 240 | 1440) => void }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative">
      <button
        onClick={() => setOpen(v => !v)}
        className="flex items-center gap-1 px-2 py-1 rounded text-[10px] text-muted-foreground hover:text-foreground hover:bg-accent/40 transition-colors"
      >
        <EyeOff size={11} />
        Snooze
        <ChevronDown size={10} />
      </button>
      {open && (
        <div
          className="absolute right-0 top-full mt-1 z-50 rounded-lg border py-1 shadow-xl"
          style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))", minWidth: 100 }}
          onMouseLeave={() => setOpen(false)}
        >
          {SNOOZE_OPTIONS.map(o => (
            <button
              key={o.minutes}
              onClick={() => { onSnooze(o.minutes); setOpen(false); }}
              className="w-full text-left px-3 py-1.5 text-[11px] text-foreground hover:bg-accent/40 transition-colors"
            >
              {o.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/* ── Alert row ─────────────────────────────────────────────────── */
function AlertRow({
  alert,
  onAck,
  onResolve,
  onSnooze,
}: {
  alert: FiredAlert;
  onAck: () => void;
  onResolve: () => void;
  onSnooze: (m: 15 | 60 | 240 | 1440) => void;
}) {
  const sev = SEV_COLORS[alert.severity] ?? SEV_COLORS.info;
  const isActive = alert.status === "active";
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      className="border-b last:border-0 transition-colors"
      style={{ borderColor: "hsl(var(--border))" }}
    >
      <div
        className={cn("flex items-start gap-3 px-5 py-3 hover:bg-accent/20 cursor-pointer", !isActive && "opacity-60")}
        onClick={() => setExpanded(v => !v)}
      >
        {/* severity dot */}
        <div
          className="mt-0.5 w-2 h-2 rounded-full flex-shrink-0"
          style={{ background: sev.text, marginTop: 6 }}
        />

        {/* content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span
              className="text-[10px] font-bold px-1.5 py-0.5 rounded-full uppercase tracking-wide"
              style={{ background: sev.bg, color: sev.text, border: `1px solid ${sev.border}` }}
            >
              {alert.severity}
            </span>
            {alert.server_name && (
              <span className="text-[10px] font-mono text-muted-foreground">{alert.server_name}</span>
            )}
            <span className="text-[10px] text-muted-foreground ml-auto flex-shrink-0">{timeAgo(alert.fired_at)}</span>
          </div>
          <p className="text-[12px] font-medium text-foreground mt-0.5 leading-snug">{alert.title}</p>
          {expanded && (
            <p className="text-[11px] text-muted-foreground mt-1 leading-relaxed">{alert.message}</p>
          )}
          {alert.status === "acked" && alert.acked_by && (
            <p className="text-[10px] text-muted-foreground mt-0.5">Acked by {alert.acked_by} · {timeAgo(alert.acked_at!)}</p>
          )}
          {alert.status === "snoozed" && alert.snoozed_until && (
            <p className="text-[10px] text-muted-foreground mt-0.5">Snoozed until {new Date(alert.snoozed_until).toLocaleString()}</p>
          )}
          {alert.status === "resolved" && alert.resolved_at && (
            <p className="text-[10px] text-muted-foreground mt-0.5">Resolved {timeAgo(alert.resolved_at)}</p>
          )}
        </div>

        {/* actions */}
        {isActive && (
          <div className="flex items-center gap-1 flex-shrink-0 ml-2" onClick={e => e.stopPropagation()}>
            <button
              onClick={onAck}
              title="Acknowledge"
              className="flex items-center gap-1 px-2 py-1 rounded text-[10px] text-muted-foreground hover:text-foreground hover:bg-accent/40 transition-colors"
            >
              <Check size={11} />
              Ack
            </button>
            <SnoozeMenu onSnooze={onSnooze} />
            <button
              onClick={onResolve}
              title="Resolve"
              className="flex items-center gap-1 px-2 py-1 rounded text-[10px] text-muted-foreground hover:text-emerald-400 hover:bg-emerald-500/10 transition-colors"
            >
              <X size={11} />
              Resolve
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Main page ─────────────────────────────────────────────────── */
export default function AlertsPage() {
  const { activeProject } = useProject();
  const pid = activeProject?.id ?? null;
  const p = pid ? `?project_id=${encodeURIComponent(pid)}` : "";

  const [feedStatus, setFeedStatus] = useState<string>("active");
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [tagging, setTagging] = useState(false);

  const { data: config, mutate: mutateConfig } = useSWR<AlertConfig>(
    "/api/alerts/config",
    fetcher,
    { refreshInterval: 60_000 },
  );

  const feedKey = `/api/alerts/feed?limit=50&offset=0${pid ? `&project_id=${encodeURIComponent(pid)}` : ""}${feedStatus !== "all" ? `&status=${feedStatus}` : ""}`;
  const { data: feedData, mutate: mutateFeed } = useSWR<{
    total: number; limit: number; offset: number; alerts: FiredAlert[];
  }>(feedKey, fetcher, { refreshInterval: 15_000 });

  const { data: counts, mutate: mutateCounts } = useSWR<AlertCounts>(
    `/api/alerts/counts${pid ? `?project_id=${encodeURIComponent(pid)}` : ""}`,
    fetcher,
    { refreshInterval: 15_000 },
  );

  const { data: incomplete } = useSWR<IncompleteSession[]>(
    pid ? `/api/reliability/incomplete-sessions${p}` : null,
    fetcher,
    { refreshInterval: 30_000 },
  );
  const { data: anomalies } = useSWR<AnomalyResult[]>(
    pid ? `/api/reliability/anomalies${p}` : null,
    fetcher,
    { refreshInterval: 60_000 },
  );

  async function toggleType(type: string) {
    if (!config) return;
    const updated = { ...config.alert_types, [type]: !config.alert_types[type] };
    setSaving(true);
    try {
      await fetch("/api/proxy/alerts/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ alert_types: updated }),
      });
      await mutateConfig();
      toast.success(`${ALERT_TYPE_META[type]?.label ?? type} ${updated[type] ? "enabled" : "disabled"}`);
    } catch {
      toast.error("Failed to update");
    } finally {
      setSaving(false);
    }
  }

  async function testWebhook() {
    setTesting(true);
    try {
      const res = await fetch("/api/proxy/alerts/test", { method: "POST" });
      if (!res.ok) throw new Error(await res.text());
      toast.success("Test notification sent");
    } catch {
      toast.error("Test failed — check webhook URL");
    } finally {
      setTesting(false);
    }
  }

  async function tagIncomplete() {
    setTagging(true);
    try {
      const res = await fetch(`/api/proxy/reliability/tag-incomplete${p}`, { method: "POST" });
      const data = await res.json();
      toast.success(`Tagged ${data.tagged} incomplete sessions`);
    } catch {
      toast.error("Failed to tag sessions");
    } finally {
      setTagging(false);
    }
  }

  async function handleAck(alertId: string) {
    try {
      const res = await fetch(`/api/proxy/alerts/${encodeURIComponent(alertId)}/ack`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ acked_by: "user" }),
      });
      if (!res.ok) throw new Error();
      await Promise.all([mutateFeed(), mutateCounts()]);
      toast.success("Alert acknowledged");
    } catch {
      toast.error("Failed to acknowledge");
    }
  }

  async function handleResolve(alertId: string) {
    try {
      const res = await fetch(`/api/proxy/alerts/${encodeURIComponent(alertId)}/resolve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      if (!res.ok) throw new Error();
      await Promise.all([mutateFeed(), mutateCounts()]);
      toast.success("Alert resolved");
    } catch {
      toast.error("Failed to resolve");
    }
  }

  async function handleSnooze(alertId: string, minutes: 15 | 60 | 240 | 1440) {
    try {
      const res = await fetch(`/api/proxy/alerts/${encodeURIComponent(alertId)}/snooze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ minutes }),
      });
      if (!res.ok) throw new Error();
      await Promise.all([mutateFeed(), mutateCounts()]);
      const label = SNOOZE_OPTIONS.find(o => o.minutes === minutes)?.label ?? `${minutes}m`;
      toast.success(`Snoozed for ${label}`);
    } catch {
      toast.error("Failed to snooze");
    }
  }

  const alerts = feedData?.alerts ?? [];

  return (
    <div className="space-y-5 page-in">

      {/* ── Alert Inbox ──────────────────────────────────────────── */}
      <div className="rounded-xl border overflow-hidden" style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}>
        {/* header */}
        <div className="px-5 py-3 border-b flex items-center justify-between" style={{ borderColor: "hsl(var(--border))" }}>
          <div className="flex items-center gap-3">
            <h2 className="text-sm font-semibold text-foreground flex items-center gap-2">
              <Bell size={14} className="text-primary" />
              Alert Inbox
            </h2>
            {/* severity count pills */}
            {counts && counts.total > 0 && (
              <div className="flex items-center gap-1.5">
                {counts.critical > 0 && (
                  <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-red-500/10 text-red-400">
                    {counts.critical} crit
                  </span>
                )}
                {counts.warning > 0 && (
                  <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-yellow-500/10 text-yellow-400">
                    {counts.warning} warn
                  </span>
                )}
              </div>
            )}
          </div>
          {/* status tab filter */}
          <div className="flex items-center gap-0.5 rounded-lg p-0.5" style={{ background: "hsl(var(--muted))" }}>
            {STATUS_TABS.map(tab => (
              <button
                key={tab.key}
                onClick={() => setFeedStatus(tab.key)}
                className={cn(
                  "px-2.5 py-1 rounded-md text-[10px] font-medium transition-colors",
                  feedStatus === tab.key
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {tab.label}
                {tab.key === "active" && counts && counts.total > 0 && (
                  <span className="ml-1 opacity-70">{counts.total}</span>
                )}
              </button>
            ))}
          </div>
        </div>

        {/* feed */}
        {alerts.length === 0 ? (
          <div className="px-5 py-10 text-center">
            <CheckCircle size={20} className="mx-auto text-emerald-400 mb-2" />
            <p className="text-xs text-muted-foreground">
              {feedStatus === "active" ? "No active alerts" : `No ${feedStatus} alerts`}
            </p>
          </div>
        ) : (
          <div>
            {alerts.map(alert => (
              <AlertRow
                key={alert.id}
                alert={alert}
                onAck={() => handleAck(alert.id)}
                onResolve={() => handleResolve(alert.id)}
                onSnooze={(m) => handleSnooze(alert.id, m)}
              />
            ))}
            {feedData && feedData.total > alerts.length && (
              <div className="px-5 py-2 text-center">
                <p className="text-[10px] text-muted-foreground">
                  Showing {alerts.length} of {feedData.total} — scroll or paginate
                </p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── Webhook Status ──────────────────────────────────────── */}
      <div className="rounded-xl border p-5" style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}>
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            {config?.webhook_configured ? (
              <Bell size={15} className="text-primary" />
            ) : (
              <BellOff size={15} className="text-muted-foreground" />
            )}
            <h2 className="text-sm font-semibold text-foreground">Slack Notifications</h2>
          </div>
          {config?.webhook_configured && (
            <button onClick={testWebhook} disabled={testing} className="btn btn-secondary text-xs">
              <Send size={12} />
              {testing ? "Sending..." : "Test"}
            </button>
          )}
        </div>
        <p className="text-xs text-muted-foreground">
          {config?.webhook_configured
            ? "Webhook configured. Alerts will be delivered to your Slack channel."
            : "No webhook configured. Go to Settings → Notifications to add a Slack webhook URL."}
        </p>
      </div>

      {/* ── Alert Rules ─────────────────────────────────────────── */}
      <div className="rounded-xl border overflow-hidden" style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}>
        <div className="px-5 py-3 border-b" style={{ borderColor: "hsl(var(--border))" }}>
          <h2 className="text-sm font-semibold text-foreground">Alert Rules</h2>
          <p className="text-[11px] text-muted-foreground mt-0.5">Toggle which alert types fire notifications</p>
        </div>
        <div className="divide-y" style={{ borderColor: "hsl(var(--border))" }}>
          {Object.entries(ALERT_TYPE_META).map(([type, meta]) => (
            <div key={type} className="flex items-center justify-between px-5 py-3">
              <div className="flex items-center gap-3">
                <div className="w-7 h-7 rounded-lg flex items-center justify-center" style={{
                  background: `${meta.color}15`, border: `1px solid ${meta.color}30`,
                }}>
                  <meta.icon size={13} style={{ color: meta.color }} />
                </div>
                <div>
                  <p className="text-[12px] font-medium text-foreground">{meta.label}</p>
                  <p className="text-[10px] text-muted-foreground">{meta.description}</p>
                </div>
              </div>
              <Toggle
                checked={config?.alert_types[type] ?? false}
                onChange={() => toggleType(type)}
                disabled={saving}
              />
            </div>
          ))}
        </div>
      </div>

      {/* ── Incomplete Sessions ──────────────────────────────────── */}
      <div className="rounded-xl border overflow-hidden" style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}>
        <div className="px-5 py-3 border-b flex items-center justify-between" style={{ borderColor: "hsl(var(--border))" }}>
          <div>
            <h2 className="text-sm font-semibold text-foreground flex items-center gap-2">
              <XCircle size={14} className="text-orange-400" />
              Incomplete Sessions
              {incomplete && incomplete.length > 0 && (
                <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-orange-500/10 text-orange-400">
                  {incomplete.length}
                </span>
              )}
            </h2>
            <p className="text-[11px] text-muted-foreground mt-0.5">Sessions that crashed or stopped mid-execution</p>
          </div>
          {incomplete && incomplete.length > 0 && (
            <button onClick={tagIncomplete} disabled={tagging} className="btn btn-secondary text-xs">
              {tagging ? "Tagging..." : `Tag ${incomplete.length} as incomplete`}
            </button>
          )}
        </div>
        {!incomplete || incomplete.length === 0 ? (
          <div className="px-5 py-8 text-center">
            <CheckCircle size={20} className="mx-auto text-emerald-400 mb-2" />
            <p className="text-xs text-muted-foreground">No incomplete sessions detected</p>
          </div>
        ) : (
          <div className="divide-y" style={{ borderColor: "hsl(var(--border))" }}>
            {incomplete.map(s => (
              <Link
                key={s.session_id}
                href={`/sessions/${s.session_id}`}
                className="flex items-center justify-between px-5 py-2.5 hover:bg-accent/30 transition-colors"
              >
                <div className="min-w-0">
                  <span className="text-[11px] font-mono text-foreground block truncate" style={{ fontFamily: "var(--font-geist-mono)" }}>
                    {s.session_id}
                  </span>
                  <span className="text-[10px] text-muted-foreground">
                    {s.agent_name} · {s.span_count} spans · {s.llm_calls} LLM / {s.tool_calls} tool
                  </span>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  <Clock size={11} className="text-muted-foreground" />
                  <span className="text-[10px] text-muted-foreground">{timeAgo(s.last_activity)}</span>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>

      {/* ── Active Anomalies ──────────────────────────────────────── */}
      <div className="rounded-xl border overflow-hidden" style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}>
        <div className="px-5 py-3 border-b" style={{ borderColor: "hsl(var(--border))" }}>
          <h2 className="text-sm font-semibold text-foreground flex items-center gap-2">
            <Zap size={14} className="text-yellow-400" />
            Active Anomalies
            {anomalies && anomalies.length > 0 && (
              <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-yellow-500/10 text-yellow-400">
                {anomalies.length}
              </span>
            )}
          </h2>
        </div>
        {!anomalies || anomalies.length === 0 ? (
          <div className="px-5 py-8 text-center">
            <CheckCircle size={20} className="mx-auto text-emerald-400 mb-2" />
            <p className="text-xs text-muted-foreground">No anomalies detected — all tools within baseline</p>
          </div>
        ) : (
          <div className="divide-y" style={{ borderColor: "hsl(var(--border))" }}>
            {anomalies.map((a, i) => (
              <div key={i} className="flex items-center justify-between px-5 py-2.5">
                <div>
                  <span className="text-[12px] font-mono font-medium text-foreground">{a.server_name}/{a.tool_name}</span>
                  <span className="text-[10px] text-muted-foreground ml-2">{a.metric}: z={a.z_score.toFixed(1)}</span>
                </div>
                <span className={cn(
                  "text-[10px] font-bold px-1.5 py-0.5 rounded-full",
                  a.severity === "critical" ? "bg-red-500/10 text-red-400" : "bg-yellow-500/10 text-yellow-400",
                )}>
                  {a.severity}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
