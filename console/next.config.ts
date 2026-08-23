import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The console is a local analyst tool; no image optimization needed.
  images: { unoptimized: true },
};

export default nextConfig;
