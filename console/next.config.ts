import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The console is a local analyst tool; no image optimization needed.
  images: { unoptimized: true },
  // Standalone for containers; static export for the zero-backend demo
  // snapshot (NEXT_PUBLIC_DEMO=1) and for the hosted live demo on S3 +
  // CloudFront (SENTINEL_STATIC=1, which still talks to the live API via
  // NEXT_PUBLIC_API_URL). Dev is unaffected by either.
  output:
    process.env.NEXT_PUBLIC_DEMO === "1" || process.env.SENTINEL_STATIC === "1"
      ? "export"
      : "standalone",
};

export default nextConfig;
