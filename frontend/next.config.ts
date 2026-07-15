import type { NextConfig } from "next";

const isolatedDistDir = process.env.NEXT_DIST_DIR?.trim();

const nextConfig: NextConfig = {
  reactStrictMode: true,
  devIndicators: false,
  ...(isolatedDistDir ? { distDir: isolatedDistDir } : {}),
  async redirects() {
    return [
      {
        source: "/review",
        destination: "/profile?tab=plan",
        permanent: false,
      },
    ];
  },
};

export default nextConfig;
