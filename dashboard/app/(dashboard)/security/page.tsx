"use client";

import { useEffect, useRef, useState } from "react";
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from "recharts";
import { Shield, Scan, AlertTriangle, CheckCircle } from "lucide-react";
import { triggerSecurityScan } from "@/lib/api";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import type { SecurityScanResult } from "@/lib/types";

const SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"];
const PIE_COLORS: Record<string, string> = {
  critical: "#ef4444",
  high:     "#f97316",
  medium:   "#eab308",
  low:      "#6b7280",
  info:     "#3b82f6",
};
const SEV_CLASS: Record<string, string> = {
  critical: "sev-critical",
  high:     "sev-high",
  medium:   "sev-medium",
  low:      "sev-low",
  info:     "sev-info",
};

/* ── Stat card ──────────────────────────────────────────────── */
function StatCard({
  label, value, sub, color, icon: Icon,
}: {
  label: string; value: number; sub: string;
  color?: string; icon: React.ElementType;
}) {
  return (
    <div
      className="rounded-xl border p-5 flex flex-col gap-3"
      style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
    >
      <div
        className="w-9 h-9 rounded-lg flex items-center justify-center"
        style={{ background: color ? `${color}18` : "hsl(var(--muted))" }}
      >
        <Icon size={16} style={{ color: color ?? "hsl(var(--muted-foreground))" }} />
      </div>
      <div>
        <p
          className="text-2xl font-bold leading-none mb-1"
          style={{ color: color ?? "hsl(var(--foreground))" }}
        >
          {value}
        </p>
        <p className="text-[13px] font-medium text-foreground/80">{label}</p>
        <p className="text-[11px] text-muted-foreground mt-0.5">{sub}</p>
      </div>
    </div>
  );
}

/* ── Page ───────────────────────────────────────────────────── */
export default function SecurityPage() {
  const [results, setResults] = useState<SecurityScanResult[] | null>(null);
  const [scanning, setScanning] = useState(false);
  const didAutoScan = useRef(false);

  // Auto-trigger first scan on page load
  useEffect(() => {
    if (!didAutoScan.current && !results && !scanning) {
      didAutoScan.current = true;
      runScan();
    }
  });

  async function runScan() {
    setScanning(true);
    try {
      const data = await triggerSecurityScan();
      setResults(data);
      const total    = data.reduce((n, r) => n + r.findings_count, 0);
      const critical = data.reduce((n, r) => n + r.critical_count, 0);
      if (critical > 0)   toast.error(`${critical} critical findings detected`);
      else if (total > 0) toast.warning(`${total} findings — no critical issues`);
      else                toast.success("All servers are clean");
    } catch {
      toast.error("Scan failed — is langsight serve running?");
    } finally {
      setScanning(false);
    }
  }

  const allFindings = results?.flatMap((r) =>
    r.findings.map((f) => ({ ...f, server: r.server_name }))
  ) ?? [];

  const bySeverity = SEVERITY_ORDER.map((sev) => ({
    name: sev,
    value: allFindings.filter((f) => f.severity === sev).length,
  })).filter((d) => d.value > 0);

  const critical = allFindings.filter((f) => f.severity === "critical").length;
  const high     = allFindings.filter((f) => f.severity === "high").length;
  const clean    = results?.filter((r) => r.findings_count === 0).length ?? 0;

  return (
    <div className="space-y-5 page-in">
      {/* ── Header ────────────────────────────────────────────── */}
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-foreground">MCP Security</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            CVE detection · OWASP MCP Top 10 · Tool poisoning
          </p>
        </div>
        <button
          onClick={runScan}
          disabled={scanning}
          className="btn btn-primary"
        >
          <Scan size={13} className={scanning ? "animate-spin" : ""} />
          {scanning ? "Scanning…" : "Run Security Scan"}
        </button>
      </div>

      {/* ── Empty / scanning states ───────────────────────────── */}
      {!results && !scanning && (
        <div
          className="rounded-xl border p-14 text-center"
          style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
        >
          <div
            className="w-16 h-16 rounded-2xl flex items-center justify-center mx-auto mb-5"
            style={{ background: "hsl(var(--muted))" }}
          >
            <Shield size={28} className="text-muted-foreground" />
          </div>
          <p className="text-base font-semibold text-foreground mb-2">No scan results yet</p>
          <p className="text-sm text-muted-foreground mb-6 max-w-md mx-auto">
            Run a security scan to check all configured MCP servers for CVEs, OWASP issues,
            and tool poisoning attacks.
          </p>
          <button onClick={runScan} className="btn btn-primary">
            <Scan size={13} /> Start First Scan
          </button>
        </div>
      )}

      {scanning && (
        <div
          className="rounded-xl border p-10 text-center"
          style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
        >
          <div className="w-10 h-10 rounded-full border-2 border-primary border-t-transparent spin mx-auto mb-4" />
          <p className="text-sm text-muted-foreground">
            Scanning all servers for CVEs, OWASP issues, and tool poisoning…
          </p>
        </div>
      )}

      {/* ── Results ───────────────────────────────────────────── */}
      {results && results.length > 0 && (
        <>
          {/* Stat cards */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <StatCard
              icon={Shield}
              label="Servers scanned"
              value={results.length}
              sub={`${clean}/${results.length} clean`}
            />
            <StatCard
              icon={CheckCircle}
              label="Clean servers"
              value={clean}
              sub={clean === results.length ? "all clear ✓" : "no findings"}
              color={clean === results.length ? "#22c55e" : undefined}
            />
            <StatCard
              icon={AlertTriangle}
              label="Critical"
              value={critical}
              sub={critical > 0 ? "action required" : "none found"}
              color={critical > 0 ? "#ef4444" : undefined}
            />
            <StatCard
              icon={AlertTriangle}
              label="High"
              value={high}
              sub={high > 0 ? "review recommended" : "none found"}
              color={high > 0 ? "#f97316" : undefined}
            />
          </div>

          {/* Chart + findings */}
          <div className="grid lg:grid-cols-3 gap-5">
            {bySeverity.length > 0 && (
              <div
                className="rounded-xl border p-5"
                style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
              >
                <h3 className="text-[13px] font-semibold text-foreground mb-4">By Severity</h3>
                <div className="h-44">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={bySeverity}
                        dataKey="value"
                        nameKey="name"
                        cx="50%"
                        cy="50%"
                        outerRadius={64}
                        strokeWidth={2}
                        stroke="hsl(var(--card))"
                      >
                        {bySeverity.map((entry) => (
                          <Cell key={entry.name} fill={PIE_COLORS[entry.name]} />
                        ))}
                      </Pie>
                      <Tooltip
                        contentStyle={{
                          background: "hsl(var(--card))",
                          border: "1px solid hsl(var(--border))",
                          borderRadius: 8,
                          fontSize: 12,
                          color: "hsl(var(--foreground))",
                        }}
                      />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
                <div className="space-y-2 mt-3">
                  {bySeverity.map((d) => (
                    <div key={d.name} className="flex items-center justify-between text-xs">
                      <div className="flex items-center gap-2">
                        <div
                          className="w-2 h-2 rounded-full flex-shrink-0"
                          style={{ background: PIE_COLORS[d.name] }}
                        />
                        <span className="text-muted-foreground capitalize">{d.name}</span>
                      </div>
                      <span className="font-semibold text-foreground tabular-nums">{d.value}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Findings list */}
            <div
              className={cn(
                "rounded-xl border overflow-hidden",
                bySeverity.length > 0 ? "lg:col-span-2" : "lg:col-span-3"
              )}
              style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
            >
              <div className="section-header">
                <h2>
                  {allFindings.length === 0
                    ? "✓ All servers clean"
                    : `${allFindings.length} findings`}
                </h2>
              </div>

              {allFindings.length === 0 ? (
                <div className="p-10 text-center">
                  <CheckCircle size={32} className="mx-auto mb-3" style={{ color: "hsl(var(--success))" }} />
                  <p className="text-sm font-semibold" style={{ color: "hsl(var(--success))" }}>
                    All {results.length} servers are clean
                  </p>
                </div>
              ) : (
                <div
                  className="divide-y overflow-y-auto max-h-[420px]"
                  style={{ borderColor: "hsl(var(--border))" }}
                >
                  {[...allFindings]
                    .sort(
                      (a, b) =>
                        SEVERITY_ORDER.indexOf(a.severity) -
                        SEVERITY_ORDER.indexOf(b.severity)
                    )
                    .map((f, i) => (
                      <div
                        key={i}
                        className="px-5 py-4 hover:bg-accent/30 transition-colors"
                      >
                        <div className="flex items-center gap-2 mb-2">
                          <span
                            className={cn(
                              "text-[10px] px-2 py-0.5 rounded-full border font-semibold capitalize",
                              SEV_CLASS[f.severity] ?? "badge-muted"
                            )}
                          >
                            {f.severity}
                          </span>
                          <code
                            className="text-[11px] text-muted-foreground"
                            style={{ fontFamily: "var(--font-geist-mono)" }}
                          >
                            {f.server}
                          </code>
                          {f.cve_id && (
                            <code
                              className="text-[11px]"
                              style={{
                                fontFamily: "var(--font-geist-mono)",
                                color: "hsl(var(--info))",
                              }}
                            >
                              {f.cve_id}
                            </code>
                          )}
                          <span className="text-[11px] text-muted-foreground">{f.category}</span>
                        </div>
                        <p className="text-[13px] font-semibold text-foreground mb-1">{f.title}</p>
                        <p className="text-[11px] text-muted-foreground leading-relaxed">
                          {f.remediation.slice(0, 120)}
                          {f.remediation.length > 120 && "…"}
                        </p>
                      </div>
                    ))}
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
