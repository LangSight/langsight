"use client";

import { cn } from "@/lib/utils";
import type { Severity, ServerStatus } from "@/lib/types";
import { SEVERITY_BG, STATUS_BG, STATUS_ICON } from "@/lib/utils";

/* ── Card ──────────────────────────────────────────────────────── */
export function Card({ children, className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("rounded-xl border p-5", className)}
      style={{ background: "var(--surface)", borderColor: "var(--border)" }}
      {...props}
    >
      {children}
    </div>
  );
}

/* ── Stat card ─────────────────────────────────────────────────── */
export function StatCard({ label, value, sub, accent }: {
  label: string; value: string | number; sub?: string; accent?: boolean;
}) {
  return (
    <Card>
      <p className="text-xs mb-2" style={{ color: "var(--muted)" }}>{label}</p>
      <p className={cn("text-3xl font-bold", accent ? "text-indigo-400" : "text-white")}>{value}</p>
      {sub && <p className="text-xs mt-1" style={{ color: "var(--muted)" }}>{sub}</p>}
    </Card>
  );
}

/* ── Badge ─────────────────────────────────────────────────────── */
export function Badge({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <span className={cn("inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium", className)}>
      {children}
    </span>
  );
}

export function StatusBadge({ status }: { status: ServerStatus }) {
  return (
    <Badge className={STATUS_BG[status]}>
      {STATUS_ICON[status]} {status}
    </Badge>
  );
}

export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <Badge className={SEVERITY_BG[severity]}>
      {severity}
    </Badge>
  );
}

/* ── Table ─────────────────────────────────────────────────────── */
export function Table({ children }: { children: React.ReactNode }) {
  return (
    <div className="w-full overflow-x-auto">
      <table className="w-full text-sm">{children}</table>
    </div>
  );
}
export function Th({ children, right }: { children: React.ReactNode; right?: boolean }) {
  return (
    <th className={cn("px-4 py-3 text-xs font-medium text-left whitespace-nowrap", right && "text-right")}
      style={{ color: "var(--muted)", borderBottom: "1px solid var(--border)" }}>
      {children}
    </th>
  );
}
export function Td({ children, right, mono, className }: {
  children: React.ReactNode; right?: boolean; mono?: boolean; className?: string;
}) {
  return (
    <td className={cn("px-4 py-3", right && "text-right", mono && "font-mono text-xs", className)}
      style={{ borderBottom: "1px solid var(--border)" }}>
      {children}
    </td>
  );
}

/* ── Section header ────────────────────────────────────────────── */
export function PageHeader({ title, sub, action }: {
  title: string; sub?: string; action?: React.ReactNode;
}) {
  return (
    <div className="flex items-start justify-between mb-6">
      <div>
        <h1 className="text-xl font-bold text-white">{title}</h1>
        {sub && <p className="text-sm mt-1" style={{ color: "var(--muted)" }}>{sub}</p>}
      </div>
      {action}
    </div>
  );
}

/* ── Empty state ───────────────────────────────────────────────── */
export function Empty({ message, hint }: { message: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <p className="text-white mb-2">{message}</p>
      {hint && <p className="text-sm" style={{ color: "var(--muted)" }}>{hint}</p>}
    </div>
  );
}

/* ── Loading ───────────────────────────────────────────────────── */
export function Loading() {
  return (
    <div className="flex items-center justify-center py-16">
      <div className="w-6 h-6 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
    </div>
  );
}

/* ── Error ─────────────────────────────────────────────────────── */
export function ErrorState({ message }: { message: string }) {
  return (
    <Card className="border-red-500/20">
      <p className="text-red-400 text-sm">{message}</p>
      <p className="text-xs mt-1" style={{ color: "var(--muted)" }}>
        Make sure <code className="text-indigo-400">langsight serve</code> is running on port 8000.
      </p>
    </Card>
  );
}

/* ── Button ────────────────────────────────────────────────────── */
export function Button({ children, onClick, loading, variant = "primary" }: {
  children: React.ReactNode; onClick?: () => void;
  loading?: boolean; variant?: "primary" | "secondary";
}) {
  return (
    <button
      onClick={onClick}
      disabled={loading}
      className={cn(
        "flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all",
        "disabled:opacity-50",
        variant === "primary"
          ? "text-white hover:opacity-90"
          : "border hover:bg-white/5"
      )}
      style={variant === "primary"
        ? { background: "var(--accent)" }
        : { background: "transparent", borderColor: "var(--border)", color: "var(--muted)" }
      }
    >
      {loading ? <span className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" /> : null}
      {children}
    </button>
  );
}
