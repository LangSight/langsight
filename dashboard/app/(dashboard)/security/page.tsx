"use client";

import { useState } from "react";
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from "recharts";
import { Shield, Scan, AlertTriangle, CheckCircle } from "lucide-react";
import { triggerSecurityScan } from "@/lib/api";
import { cn, SEVERITY_BG } from "@/lib/utils";
import { toast } from "sonner";
import type { SecurityScanResult } from "@/lib/types";

const SEVERITY_ORDER = ["critical","high","medium","low","info"];
const PIE_COLORS: Record<string, string> = { critical: "#ef4444", high: "#f97316", medium: "#eab308", low: "#6b7280", info: "#3b82f6" };

export default function SecurityPage() {
  const [results, setResults] = useState<SecurityScanResult[] | null>(null);
  const [scanning, setScanning] = useState(false);

  async function runScan() {
    setScanning(true);
    try {
      const data = await triggerSecurityScan();
      setResults(data);
      const total = data.reduce((n, r) => n + r.findings_count, 0);
      const critical = data.reduce((n, r) => n + r.critical_count, 0);
      if (critical > 0) toast.error(`${critical} critical findings detected`);
      else if (total > 0) toast.warning(`${total} findings — no critical issues`);
      else toast.success("All servers are clean");
    } catch { toast.error("Scan failed — is langsight serve running?"); }
    finally { setScanning(false); }
  }

  const allFindings = results?.flatMap(r => r.findings.map(f => ({ ...f, server: r.server_name }))) ?? [];
  const bySeverity = SEVERITY_ORDER.map(sev => ({
    name: sev, value: allFindings.filter(f => f.severity === sev).length,
  })).filter(d => d.value > 0);

  const critical = allFindings.filter(f => f.severity === "critical").length;
  const high = allFindings.filter(f => f.severity === "high").length;
  const clean = results?.filter(r => r.findings_count === 0).length ?? 0;

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold" style={{ color: "hsl(var(--foreground))" }}>Security</h1>
          <p className="text-sm" style={{ color: "hsl(var(--muted-foreground))" }}>CVE · OWASP MCP Top 10 · Tool poisoning</p>
        </div>
        <button onClick={runScan} disabled={scanning}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-60"
          style={{ background: scanning ? "hsl(var(--muted-foreground))" : "hsl(var(--primary))" }}>
          <Scan size={14} className={scanning ? "animate-spin" : ""}/>
          {scanning ? "Scanning…" : "Run Security Scan"}
        </button>
      </div>

      {!results && !scanning && (
        <div className="rounded-xl border p-12 text-center" style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}>
          <Shield size={48} className="mx-auto mb-4 opacity-20"/>
          <p className="font-medium mb-2" style={{ color: "hsl(var(--foreground))" }}>No scan results yet</p>
          <p className="text-sm mb-5" style={{ color: "hsl(var(--muted-foreground))" }}>Run a security scan to check all configured MCP servers for CVEs, OWASP issues, and tool poisoning.</p>
          <button onClick={runScan}
            className="px-5 py-2.5 rounded-lg text-sm font-medium text-white"
            style={{ background: "hsl(var(--primary))" }}>
            Start First Scan
          </button>
        </div>
      )}

      {scanning && (
        <div className="rounded-xl border p-8 text-center" style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}>
          <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin mx-auto mb-4"/>
          <p className="text-sm" style={{ color: "hsl(var(--muted-foreground))" }}>Scanning all servers for CVEs, OWASP issues, and tool poisoning…</p>
        </div>
      )}

      {results && results.length > 0 && (
        <>
          {/* Stats */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {[
              { label: "Servers", value: results.length, icon: Shield, sub: "scanned" },
              { label: "Clean", value: clean, icon: CheckCircle, sub: clean === results.length ? "all clear ✓" : "no findings", color: clean === results.length ? "#22c55e" : undefined },
              { label: "Critical", value: critical, icon: AlertTriangle, sub: critical > 0 ? "action required" : "none", color: critical > 0 ? "#ef4444" : undefined },
              { label: "High", value: high, icon: AlertTriangle, sub: "findings", color: high > 0 ? "#f97316" : undefined },
            ].map(item => (
              <div key={item.label} className="rounded-xl border p-4" style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}>
                <div className="flex items-center gap-2 mb-2">
                  <item.icon size={14} style={{ color: item.color ?? "hsl(var(--muted-foreground))" }}/>
                  <span className="text-xs" style={{ color: "hsl(var(--muted-foreground))" }}>{item.label}</span>
                </div>
                <p className="text-2xl font-bold" style={{ color: item.color ?? "hsl(var(--foreground))" }}>{item.value}</p>
                <p className="text-xs" style={{ color: "hsl(var(--muted-foreground))" }}>{item.sub}</p>
              </div>
            ))}
          </div>

          <div className="grid lg:grid-cols-3 gap-5">
            {/* Pie chart */}
            {bySeverity.length > 0 && (
              <div className="rounded-xl border p-5" style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}>
                <h3 className="text-sm font-semibold mb-3" style={{ color: "hsl(var(--foreground))" }}>By Severity</h3>
                <div className="h-40">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie data={bySeverity} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={60} strokeWidth={0}>
                        {bySeverity.map(entry => <Cell key={entry.name} fill={PIE_COLORS[entry.name]}/>)}
                      </Pie>
                      <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8, fontSize: 12 }}/>
                    </PieChart>
                  </ResponsiveContainer>
                </div>
                <div className="space-y-1.5 mt-2">
                  {bySeverity.map(d => (
                    <div key={d.name} className="flex items-center justify-between text-xs">
                      <div className="flex items-center gap-2">
                        <div className="w-2 h-2 rounded-full" style={{ background: PIE_COLORS[d.name] }}/>
                        <span style={{ color: "hsl(var(--muted-foreground))" }}>{d.name}</span>
                      </div>
                      <span className="font-medium" style={{ color: "hsl(var(--foreground))" }}>{d.value}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Findings table */}
            <div className={cn("rounded-xl border overflow-hidden", bySeverity.length > 0 ? "lg:col-span-2" : "lg:col-span-3")}
              style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}>
              <div className="px-5 py-4 border-b" style={{ borderColor: "hsl(var(--border))", background: "hsl(var(--muted))" }}>
                <h3 className="text-sm font-semibold" style={{ color: "hsl(var(--foreground))" }}>
                  {allFindings.length === 0 ? "✓ All servers clean" : `${allFindings.length} findings`}
                </h3>
              </div>
              {allFindings.length === 0 ? (
                <div className="p-8 text-center">
                  <CheckCircle size={32} className="mx-auto mb-3 text-emerald-500 opacity-80"/>
                  <p className="text-sm text-emerald-500 font-medium">All {results.length} servers are clean</p>
                </div>
              ) : (
                <div className="divide-y overflow-y-auto max-h-96" style={{ borderColor: "hsl(var(--border))" }}>
                  {[...allFindings]
                    .sort((a, b) => SEVERITY_ORDER.indexOf(a.severity) - SEVERITY_ORDER.indexOf(b.severity))
                    .map((f, i) => (
                      <div key={i} className="px-5 py-3.5 hover:bg-accent/50 transition-colors">
                        <div className="flex items-start justify-between gap-3 mb-1">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className={cn("text-[11px] px-2 py-0.5 rounded-full border font-medium", SEVERITY_BG[f.severity as keyof typeof SEVERITY_BG])}>{f.severity}</span>
                            <span className="text-xs font-mono" style={{ color: "hsl(var(--muted-foreground))" }}>{f.server}</span>
                            <span className="text-xs" style={{ color: "hsl(var(--muted-foreground))" }}>{f.category}</span>
                          </div>
                        </div>
                        <p className="text-sm font-medium mb-0.5" style={{ color: "hsl(var(--foreground))" }}>{f.title}</p>
                        <p className="text-xs" style={{ color: "hsl(var(--muted-foreground))" }}>{f.remediation.slice(0, 100)}</p>
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
