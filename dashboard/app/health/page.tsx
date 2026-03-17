"use client";

import { useState, useEffect } from "react";
import useSWR from "swr";
import { fetcher, triggerHealthCheck, getServerHistoty } from "@/lib/api";
import {
  Card, PageHeader, Button, StatusBadge, Table, Th, Td,
  Loading, ErrorState, Empty,
} from "@/components/ui";
import { formatLatency, timeAgo } from "@/lib/utils";
import type { HealthResult } from "@/lib/types";

function HistoryDrawer({ name, onClose }: { name: string; onClose: () => void }) {
  const [history, setHistory] = useState<HealthResult[] | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getServerHistoty(name, 20).then(h => { setHistory(h); setLoading(false); }).catch(() => setLoading(false));
  }, [name]);


  return (
    <Card className="mt-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold text-white">History — {name}</h3>
        <button onClick={onClose} className="text-xs" style={{ color: "var(--muted)" }}>Close ✕</button>
      </div>
      {loading && <Loading />}
      {!loading && history && (
        <Table>
          <thead>
            <tr><Th>Time</Th><Th>Status</Th><Th right>Latency</Th><Th>Schema</Th><Th>Error</Th></tr>
          </thead>
          <tbody>
            {history.map((h, i) => (
              <tr key={i}>
                <Td><span style={{ color: "var(--muted)" }}>{timeAgo(h.checked_at)}</span></Td>
                <Td><StatusBadge status={h.status} /></Td>
                <Td right>{formatLatency(h.latency_ms)}</Td>
                <Td mono>{h.schema_hash ? h.schema_hash.slice(0, 8) + "…" : "—"}</Td>
                <Td><span className="text-red-400 text-xs">{h.error || ""}</span></Td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </Card>
  );
}

export default function HealthPage() {
  const { data: servers, error, isLoading, mutate } =
    useSWR<HealthResult[]>("/api/health/servers", fetcher, { refreshInterval: 30_000 });
  const [checking, setChecking] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);

  async function runCheck() {
    setChecking(true);
    try { await triggerHealthCheck(); await mutate(); }
    finally { setChecking(false); }
  }

  const up = servers?.filter(s => s.status === "up").length ?? 0;
  const total = servers?.length ?? 0;

  return (
    <div className="max-w-5xl mx-auto">
      <PageHeader
        title="MCP Health"
        sub={`${up}/${total} servers healthy · auto-refreshes every 30s`}
        action={<Button onClick={runCheck} loading={checking}>Run Check Now</Button>}
      />

      <Card>
        {isLoading && <Loading />}
        {error && <ErrorState message="Could not connect to LangSight API" />}
        {!isLoading && !error && servers?.length === 0 && (
          <Empty message="No servers configured" hint="Run langsight init to discover your MCP servers." />
        )}
        {servers && servers.length > 0 && (
          <Table>
            <thead>
              <tr>
                <Th>Server</Th><Th>Status</Th><Th right>Latency</Th>
                <Th right>Tools</Th><Th>Schema</Th><Th>Last check</Th><Th>Error</Th>
              </tr>
            </thead>
            <tbody>
              {servers.map(s => (
                <tr
                  key={s.server_name}
                  className="cursor-pointer hover:bg-white/5 transition-colors"
                  onClick={() => setSelected(selected === s.server_name ? null : s.server_name)}
                >
                  <Td>
                    <span className="font-mono text-white">{s.server_name}</span>
                  </Td>
                  <Td><StatusBadge status={s.status} /></Td>
                  <Td right>{formatLatency(s.latency_ms)}</Td>
                  <Td right><span style={{ color: "var(--muted)" }}>{s.tools_count || "—"}</span></Td>
                  <Td mono>{s.schema_hash ? s.schema_hash.slice(0, 8) + "…" : "—"}</Td>
                  <Td><span style={{ color: "var(--muted)" }}>{timeAgo(s.checked_at)}</span></Td>
                  <Td>
                    <span className="text-red-400 text-xs">{s.error ? s.error.slice(0, 40) : ""}</span>
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>

      {selected && <HistoryDrawer name={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}
