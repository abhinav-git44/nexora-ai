import type { NextConfig } from "next";

const backend = process.env.BACKEND_URL || "http://localhost:8000";

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
  {
    key: "Content-Security-Policy",
    value: [
      "default-src 'self'",
      "script-src 'self' 'unsafe-inline'" + (process.env.NODE_ENV === "development" ? " 'unsafe-eval'" : ""),
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data: blob:",
      "font-src 'self' data:",
      "connect-src 'self'",
      "frame-ancestors 'none'",
      "base-uri 'self'",
      "form-action 'self'",
    ].join("; "),
  },
];

const config: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  output: "standalone",
  async rewrites() {
    // The browser only ever talks to this origin; the API (and its secrets) stay server-side.
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default config;
