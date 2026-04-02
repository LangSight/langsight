import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",   // required for Docker multi-stage build
  async rewrites() {
    const apiUrl = process.env.LANGSIGHT_API_URL || "http://127.0.0.1:8000";
    return [
      {
        // SDK/CLI compatibility rewrite — allows agents to POST spans directly
        // to the dashboard host without CORS preflight.  FastAPI enforces its
        // own API-key auth on every route, so this is NOT an auth bypass when
        // LANGSIGHT_API_KEYS is configured (the default for any real deployment).
        //
        // Excluded paths (handled by Next.js itself, never forwarded):
        //   /api/auth/*  — NextAuth session endpoints
        //   /api/proxy/* — authenticated server-side proxy (session → API key)
        //
        // In fail-open mode (no LANGSIGHT_API_KEYS set) all FastAPI routes are
        // publicly accessible — this is intentional for local dev only.
        // Always set LANGSIGHT_API_KEYS before exposing on a network.
        source: "/api/:path((?!auth(?:/|$)|proxy(?:/|$)).*)",
        destination: `${apiUrl}/api/:path*`,
      },
    ];
  },
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-XSS-Protection", value: "1; mode=block" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
          // CSP: restrict sources to self + inline scripts (Next.js uses inline)
          // Adjust script-src if using external analytics/CDNs.
          {
            key: "Content-Security-Policy",
            value: [
              "default-src 'self'",
              "script-src 'self' 'unsafe-inline' 'unsafe-eval'",  // Next.js requires these
              "style-src 'self' 'unsafe-inline'",
              "img-src 'self' data: blob:",
              "font-src 'self' data:",
              "connect-src 'self'",
              "frame-ancestors 'none'",
            ].join("; "),
          },
        ],
      },
    ];
  },
};

export default nextConfig;
