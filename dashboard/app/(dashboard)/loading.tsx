/**
 * Loading skeleton shown by Next.js App Router while a dashboard page loads.
 * Displayed instantly on navigation — no blank white flash.
 */
export default function DashboardLoading() {
  return (
    <div className="space-y-5 page-in">
      {/* Metric cards row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <div
            key={i}
            className="rounded-xl border p-5 space-y-3"
            style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
          >
            <div className="skeleton w-9 h-9 rounded-xl" />
            <div className="skeleton h-7 w-20 rounded" />
            <div className="skeleton h-3 w-28 rounded" />
          </div>
        ))}
      </div>

      {/* Main content area */}
      <div className="grid lg:grid-cols-5 gap-4">
        <div
          className="lg:col-span-3 rounded-xl border overflow-hidden"
          style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
        >
          <div
            className="px-5 py-3.5 border-b flex items-center justify-between"
            style={{ borderColor: "hsl(var(--border))" }}
          >
            <div className="skeleton h-4 w-32 rounded" />
            <div className="skeleton h-3 w-16 rounded" />
          </div>
          <div className="divide-y" style={{ borderColor: "hsl(var(--border))" }}>
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="flex items-center justify-between px-5 py-3.5 gap-4">
                <div className="flex items-center gap-3">
                  <div className="skeleton w-2 h-2 rounded-full flex-shrink-0" />
                  <div className="space-y-1.5">
                    <div className="skeleton h-3 w-36 rounded" />
                    <div className="skeleton h-2.5 w-20 rounded" />
                  </div>
                </div>
                <div className="skeleton h-5 w-14 rounded-full" />
              </div>
            ))}
          </div>
        </div>

        <div
          className="lg:col-span-2 rounded-xl border overflow-hidden"
          style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
        >
          <div
            className="px-5 py-3.5 border-b"
            style={{ borderColor: "hsl(var(--border))" }}
          >
            <div className="skeleton h-4 w-24 rounded" />
          </div>
          <div className="divide-y" style={{ borderColor: "hsl(var(--border))" }}>
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="px-5 py-3.5 space-y-1.5">
                <div className="skeleton h-3 w-28 rounded" />
                <div className="skeleton h-2.5 w-40 rounded" />
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
