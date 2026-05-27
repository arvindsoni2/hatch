/** @type {import('next').NextConfig} */
const BACKEND_URL = process.env.API_URL || "http://127.0.0.1:8000";

const nextConfig = {
  reactStrictMode: true,
  ...(process.env.NODE_ENV === "production" && { output: "standalone" }),
  // Prevent Next.js from stripping trailing slashes on rewrite targets —
  // the FastAPI backend requires them and would 307-loop otherwise.
  skipTrailingSlashRedirect: true,
  // Proxy /api/** through Next.js so the browser uses same-origin requests.
  // This avoids IPv6 localhost resolution failures and CORS preflight overhead.
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${BACKEND_URL}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
