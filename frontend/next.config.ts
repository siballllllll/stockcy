import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // FastAPI 백엔드 프록시 (개발 환경)
  async rewrites() {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    return [
      {
        source:      "/backend/:path*",
        destination: `${apiUrl}/:path*`,
      },
    ];
  },
};

export default nextConfig;
