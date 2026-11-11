import type { NextConfig } from "next";

// All /api/* requests are proxied to the Python simulation engine, so the browser only
// ever talks to its own origin (no CORS, no third-party calls). BACKEND_URL is set per
// deployment (e.g. the Render/Fly/Docker URL of the FastAPI service).
const backend = process.env.BACKEND_URL || "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // Allow the dev server to be opened via 127.0.0.1 as well as localhost (dev only).
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  devIndicators: false,
  async rewrites() {
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
