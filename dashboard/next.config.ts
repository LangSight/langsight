import type { NextConfig } from "next";

// SECURITY: In production, the direct rewrite (below) MUST be backed by
// LANGSIGHT_API_KEYS on the FastAPI side. If NODE_ENV=production and
// LANGSIGHT_API_KEY is not set, log a prominent warning at build/startup.
if (process.env.NODE_ENV === "production" && !process.env.LANGSIGHT_API_KEY) {
  console.error("=".repeat(72));
  console.error(
    "SECURITY WARNING: LANGSIGHT_API_KEY is not set in production. " +
    "The /api/* rewrite will forward unauthenticated requests to FastAPI. " +
    "Set LANGSIGHT_API_KEY (and LANGSIGHT_API_KEYS on the API) before deploying."
  );
  console.error("=".repeat(72));
}

const nextConfig: NextConfig = {
  output: "standalone",   // required for Docker multi-stage build
  async rewrites() {
    const apiUrl = process.env.LANGSIGHT_API_URL || "http://127.0.0.1:8000";

    // In production without LANGSIGHT_API_KEY, disable the direct rewrite
    // to prevent unauthenticated pass-through. All dashboard traffic must
    // go through /api/proxy/* which enforces NextAuth session checks.
    if (process.env.NODE_ENV === "production" && !process.env.LANGSIGHT_API_KEY) {
      return [];
    }

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
          // CSP: 'unsafe-eval' removed — Next.js 15 production builds do not
          // require eval(). 'unsafe-inline' is still needed for Next.js inline
          // script chunks until nonce-based CSP is fully adopted.
          {
            key: "Content-Security-Policy",
            value: [
              "default-src 'self'",
              "script-src 'self' 'unsafe-inline'",
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
