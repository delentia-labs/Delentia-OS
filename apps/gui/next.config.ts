import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Static export for Tauri — no Node.js server needed
  output: "export",
  // Disable image optimization (Tauri handles assets directly)
  images: {
    unoptimized: true,
  },
  // Allow API calls to localhost gateway
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
        ],
      },
    ];
  },
};

export default nextConfig;
