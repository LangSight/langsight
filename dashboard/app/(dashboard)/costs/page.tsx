"use client";

import { DollarSign, Database } from "lucide-react";

export default function CostsPage() {
  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-bold" style={{ color: "hsl(var(--foreground))" }}>Cost Attribution</h1>
        <p className="text-sm" style={{ color: "hsl(var(--muted-foreground))" }}>Per-tool and per-session cost breakdown</p>
      </div>
      <div className="rounded-xl border p-12 text-center" style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}>
        <div className="w-14 h-14 rounded-2xl flex items-center justify-center mx-auto mb-4" style={{ background: "hsl(var(--muted))" }}>
          <DollarSign size={24} style={{ color: "hsl(var(--primary))" }}/>
        </div>
        <p className="text-lg font-bold mb-2" style={{ color: "hsl(var(--foreground))" }}>Costs require ClickHouse</p>
        <p className="text-sm mb-6 max-w-md mx-auto" style={{ color: "hsl(var(--muted-foreground))" }}>
          Cost attribution is calculated from tool call spans stored in ClickHouse.
          Switch to <code className="text-primary">storage.mode: clickhouse</code> and start the stack.
        </p>
        <div className="rounded-lg p-4 text-left inline-block text-sm font-mono" style={{ background: "hsl(var(--muted))", color: "hsl(var(--muted-foreground))" }}>
          <p><span className="text-primary"># .langsight.yaml</span></p>
          <p>storage:</p>
          <p>  <span className="text-emerald-500">mode: clickhouse</span></p>
          <p>  clickhouse_url: http://localhost:8123</p>
          <br/>
          <p><span className="text-primary"># Then start ClickHouse</span></p>
          <p>docker compose up -d clickhouse</p>
        </div>
      </div>
    </div>
  );
}
