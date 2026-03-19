import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",   // required for Docker multi-stage build
  async rewrites() {
    const apiUrl = process.env.LANGSIGHT_API_URL || "http://127.0.0.1:8000";
    return [
      {
        // Exclude /api/auth/* (NextAuth) and /api/proxy/* (our auth proxy route)
        // All other /api/* calls go directly to FastAPI (unauthenticated, for SDK/CLI compat)
        source: "/api/:path((?!auth|proxy).*)",
        destination: `${apiUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
