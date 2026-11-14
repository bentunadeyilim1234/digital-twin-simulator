import type { NextConfig } from "next";

// The browser only calls same-origin /api/*. On Vercel the top-level rewrite in
// vercel.json routes /api/* to the backend service, so this proxy is only for running
// Next.js on its own (scripts/dev.sh, docker-compose), where BACKEND_URL points at FastAPI.
const backend = process.env.BACKEND_URL || "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // Allow the dev server to be opened via 127.0.0.1 as well as localhost (dev only).
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  devIndicators: false,
  async rewrites() {
    if (process.env.VERCEL) return [];
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "no-referrer" },
          { key: "X-Frame-Options", value: "SAMEORIGIN" },
        ],
      },
    ];
  },
};

export default nextConfig;
