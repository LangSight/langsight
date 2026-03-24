"use client";

export const dynamic = "force-dynamic";

import useSWR from "swr";
import { useState } from "react";
import {
  Bell, BellOff, AlertTriangle, CheckCircle, Send, Clock,
  Zap, Shield, Bot, Server, Activity, XCircle,
} from "lucide-react";
import { useProject } from "@/lib/project-context";
import { cn, timeAgo } from "@/lib/utils";
import { fetcher } from "@/lib/api";
import { toast } from "sonner";
import Link from "next/link";
import type { AnomalyResult } from "@/lib/types";

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

/* ── Alert type metadata ───────────────────────────────────────── */
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

/* ── Toggle switch ─────────────────────────────────────────────── */
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

/* ── Main page ─────────────────────────────────────────────────── */
export default function AlertsPage() {
  const { activeProject } = useProject();
  const pid = activeProject?.id ?? null;
  const p = pid ? `?project_id=${encodeURIComponent(pid)}` : "";

  const { data: config, mutate: mutateConfig } = useSWR<AlertConfig>(
    "/api/alerts/config",
    fetcher,
    { refreshInterval: 60_000 },
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

  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [tagging, setTagging] = useState(false);

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

  return (
    <div className="space-y-5 page-in">

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

      {/* ── Alert Types ─────────────────────────────────────────── */}
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
