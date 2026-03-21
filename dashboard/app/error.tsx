"use client";

import { useEffect } from "react";

/**
 * Root error boundary — last resort for errors outside the dashboard layout.
 */
export default function RootError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("[root] runtime error:", error);
  }, [error]);

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        minHeight: "100vh",
        fontFamily: "system-ui, sans-serif",
        background: "#09090B",
        color: "#fafafa",
        padding: "2rem",
      }}
    >
      <h2 style={{ fontSize: "1.25rem", fontWeight: 600, marginBottom: "0.5rem" }}>
        Something went wrong
      </h2>
      <p style={{ fontSize: "0.875rem", color: "#a1a1aa", marginBottom: "1.5rem", textAlign: "center" }}>
        {error.message}
      </p>
      <button
        onClick={reset}
        style={{
          padding: "0.5rem 1.25rem",
          borderRadius: "0.5rem",
          background: "#6366F1",
          color: "#fff",
          border: "none",
          cursor: "pointer",
          fontSize: "0.875rem",
        }}
      >
        Try again
      </button>
    </div>
  );
}
