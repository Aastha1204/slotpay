import type { NextConfig } from "next";

// Where the FastAPI server lives (resolved when the app is built/started). Browsers talk to "/api/*" on this same origin.
const API_INTERNAL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  // One website, one origin: /api/* is proxied to the API, so no CORS and a single URL to share.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_INTERNAL}/:path*` }];
  },
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
