"use client";

import { Card, PageHeader, Empty } from "@/components/ui";

export default function CostsPage() {
  return (
    <div className="max-w-5xl mx-auto">
      <PageHeader
        title="Cost Attribution"
        sub="Per-tool and per-session cost breakdown"
      />
      <Card>
        <Empty
          message="Costs require ClickHouse"
          hint="Switch to storage.mode: clickhouse and instrument your agents with the LangSight SDK. Then run docker compose up -d to start ClickHouse."
        />
        <div className="mt-6 p-4 rounded-lg text-sm font-mono" style={{ background: "var(--bg)" }}>
          <p style={{ color: "var(--muted)" }}># .langsight.yaml</p>
          <p className="text-white">storage:</p>
          <p className="text-indigo-400 pl-4">mode: clickhouse</p>
          <p className="text-indigo-400 pl-4">clickhouse_url: http://localhost:8123</p>
        </div>
      </Card>
    </div>
  );
}
