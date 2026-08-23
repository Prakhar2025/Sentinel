import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The console is a local analyst tool; no image optimization needed.
  images: { unoptimized: true },
  // Standalone output for the container runtime; dev is unaffected.
  output: "standalone",
};

export default nextConfig;
