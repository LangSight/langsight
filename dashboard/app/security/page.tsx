"use client";

import { useState } from "react";
import { triggerSecurityScan } from "@/lib/api";
import {
  Card, PageHeader, Button, SeverityBadge, Table, Th, Td,
  Loading, Empty,
} from "@/components/ui";
import type { SecurityScanResult } from "@/lib/types";

export default function SecurityPage() {
  const [results, setResults] = useState<SecurityScanResult[] | null>(null);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function runScan() {
    setScanning(true);
    setError(null);
    try {
      const data = await triggerSecurityScan();
      setResults(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Scan failed");
    } finally {
      setScanning(false);
    }
  }

  const totalFindings = results?.reduce((n, r) => n + r.findings_count, 0) ?? 0;
  const critical = results?.reduce((n, r) => n + r.critical_count, 0) ?? 0;
  const high = results?.reduce((n, r) => n + r.high_count, 0) ?? 0;
  const clean = results?.filter(r => r.findings_count === 0).length ?? 0;

  return (
    <div className="max-w-5xl mx-auto">
      <PageHeader
        title="Security Scan"
        sub="CVE detection · OWASP MCP Top 10 · Tool poisoning"
        action={<Button onClick={runScan} loading={scanning}>
          {scanning ? "Scanning…" : "Run Security Scan"}
        </Button>}
      />

      {error && (
        <Card className="mb-4 border-red-500/20">
          <p className="text-red-400 text-sm">{error}</p>
        </Card>
      )}

      {!results && !scanning && (
        <Card>
          <Empty
            message="No scan results"
            hint="Click 'Run Security Scan' to check all configured MCP servers."
          />
        </Card>
      )}

      {scanning && <Card><Loading /></Card>}

      {results && results.length > 0 && (
        <>
          {/* Summary stats */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-5">
            <Card>
              <p className="text-xs mb-2" style={{ color: "var(--muted)" }}>Servers Scanned</p>
              <p className="text-3xl font-bold text-white">{results.length}</p>
            </Card>
            <Card>
              <p className="text-xs mb-2" style={{ color: "var(--muted)" }}>Clean</p>
              <p className={`text-3xl font-bold ${clean === results.length ? "text-emerald-400" : "text-white"}`}>{clean}</p>
            </Card>
            <Card>
              <p className="text-xs mb-2" style={{ color: "var(--muted)" }}>Critical</p>
              <p className={`text-3xl font-bold ${critical > 0 ? "text-red-400" : "text-white"}`}>{critical}</p>
            </Card>
            <Card>
              <p className="text-xs mb-2" style={{ color: "var(--muted)" }}>High</p>
              <p className={`text-3xl font-bold ${high > 0 ? "text-orange-400" : "text-white"}`}>{high}</p>
            </Card>
          </div>

          {/* Findings table */}
          {totalFindings === 0 ? (
            <Card>
              <p className="text-center text-emerald-400 py-8 font-semibold">
                ✓ All {results.length} servers are clean
              </p>
            </Card>
          ) : (
            <Card>
              <Table>
                <thead>
                  <tr><Th>Severity</Th><Th>Server</Th><Th>Category</Th><Th>Finding</Th><Th>Tool</Th></tr>
                </thead>
                <tbody>
                  {results.flatMap(r =>
                    r.findings.map((f, i) => (
                      <tr key={`${r.server_name}-${i}`} className="hover:bg-white/5 transition-colors">
                        <Td><SeverityBadge severity={f.severity} /></Td>
                        <Td mono>{r.server_name}</Td>
                        <Td><span className="text-xs" style={{ color: "var(--muted)" }}>{f.category}</span></Td>
                        <Td>
                          <div>
                            <p className="text-sm text-white">{f.title}</p>
                            <p className="text-xs mt-0.5" style={{ color: "var(--muted)" }}>{f.remediation.slice(0, 80)}…</p>
                          </div>
                        </Td>
                        <Td mono>{f.tool_name || "—"}</Td>
                      </tr>
                    ))
                  )}
                </tbody>
              </Table>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
