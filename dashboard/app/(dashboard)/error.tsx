"use client";

import { useEffect } from "react";
import { AlertTriangle, RotateCcw } from "lucide-react";

/**
 * Dashboard error boundary — catches runtime JS errors in any dashboard page.
 *
 * Without this, a single unhandled error (e.g., bad API response shape,
 * null dereference in a chart component) causes a white screen crash.
 * This component shows a recoverable error UI instead.
 */
export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("[dashboard] runtime error:", error);
  }, [error]);

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] px-6">
      <div
        className="w-14 h-14 rounded-2xl flex items-center justify-center mb-5"
        style={{ background: "rgba(239,68,68,0.08)" }}
      >
        <AlertTriangle size={24} style={{ color: "#ef4444" }} />
      </div>

      <h2 className="text-lg font-semibold text-foreground mb-2">
        Something went wrong
      </h2>

      <p className="text-sm text-muted-foreground text-center max-w-md mb-1">
        An unexpected error occurred while rendering this page.
      </p>

      <p
        className="text-xs text-muted-foreground font-mono mb-6 max-w-lg text-center truncate"
        title={error.message}
      >
        {error.message}
      </p>

      <button
        onClick={reset}
        className="btn btn-primary px-5 py-2 text-sm flex items-center gap-2"
      >
        <RotateCcw size={14} />
        Try again
      </button>

      {error.digest && (
        <p className="text-[10px] text-muted-foreground mt-4 font-mono">
          Error ID: {error.digest}
        </p>
      )}
    </div>
  );
}
