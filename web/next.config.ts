import type { NextConfig } from "next";

const config: NextConfig = {
  reactStrictMode: true,
  // Lint runs as its own CI step (`pnpm lint`), not inside the build.
  eslint: { ignoreDuringBuilds: true },
  async rewrites() {
    const base = process.env.WHALETALE_API_URL ?? "http://127.0.0.1:8000";
    return [{ source: "/api/whaletale/:path*", destination: `${base}/:path*` }];
  },
};

export default config;
