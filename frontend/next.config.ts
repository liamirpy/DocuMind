import type { NextConfig } from "next";

// The existing public Nginx/backend is available on host port 80.
// Browser requests stay on the Next.js origin and are proxied server-side.
const apiProxyTarget = (
  process.env.API_PROXY_TARGET ?? "http://127.0.0.1"
).replace(/\/$/, "");

// Next.js protects development assets from requests coming through another
// hostname/IP. Add comma-separated LAN hostnames here when needed.
const allowedDevOrigins = (
  process.env.ALLOWED_DEV_ORIGINS ?? "192.168.0.102"
)
  .split(",")
  .map((origin) => origin.trim())
  .filter(Boolean);

const nextConfig: NextConfig = {
  reactStrictMode: true,
  allowedDevOrigins,
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${apiProxyTarget}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
