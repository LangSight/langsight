import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",   // required for Docker multi-stage build
  async rewrites() {
    const apiUrl = process.env.LANGSIGHT_API_URL || "http://localhost:8000";
    return [
      {
        // Exclude /api/auth/* — those are handled locally by NextAuth
        source: "/api/:path((?!auth).*)",
        destination: `${apiUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
