import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The console is a local analyst tool; no image optimization needed.
  images: { unoptimized: true },
  // Standalone for containers; static export for the zero-backend
  // demo snapshot (NEXT_PUBLIC_DEMO=1); dev is unaffected by either.
  output: process.env.NEXT_PUBLIC_DEMO === "1" ? "export" : "standalone",
};

export default nextConfig;
