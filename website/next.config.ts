import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  experimental: {
    // Target modern browsers — eliminates ~11 KiB of legacy JS polyfills
    browsersListForSwc: true,
  },
};

export default nextConfig;
