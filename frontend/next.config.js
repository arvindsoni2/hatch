/** @type {import('next').NextConfig} */
const withPWA = require("@ducanh2912/next-pwa").default({
  dest: "public",
  disable: process.env.NODE_ENV === "development",
  register: true,
  skipWaiting: true,
  runtimeCaching: [
    {
      urlPattern: /^https?:\/\/.*\/api\/.*/,
      handler: "StaleWhileRevalidate",
      options: {
        cacheName: "api-cache",
        expiration: { maxEntries: 200, maxAgeSeconds: 60 * 60 },
      },
    },
    {
      urlPattern: /\/_next\/static\/.*/,
      handler: "CacheFirst",
      options: {
        cacheName: "static-cache",
        expiration: { maxEntries: 100, maxAgeSeconds: 60 * 60 * 24 * 30 },
      },
    },
  ],
});

// In container builds API_URL is injected as a Docker build arg; fall back to
// the Compose service name so the rewrite works even if the arg is missing.
const BACKEND_URL = process.env.API_URL || "http://backend:8000";

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
  async headers() {
    const csp = [
      "default-src 'self'",
      "connect-src 'self' https://cdn.jsdelivr.net",
      "img-src 'self' data: blob:",
      "style-src 'self' 'unsafe-inline'",
      "script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'",
      "media-src 'self' blob:",
      "frame-ancestors 'none'",
    ].join("; ");
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-XSS-Protection", value: "1; mode=block" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Content-Security-Policy-Report-Only", value: csp },
        ],
      },
    ];
  },
};

module.exports = withPWA(nextConfig);
