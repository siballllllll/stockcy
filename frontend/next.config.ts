import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // FastAPI 백엔드 프록시 (개발 환경)
  async rewrites() {
    // 윈도우 localhost IPv6 문제로 인한 socket hang up(ECONNRESET) 방지를 위해 127.0.0.1을 명시합니다.
    const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
    return [
      {
        source:      "/backend/:path*",
        destination: `${apiUrl}/:path*`,
      },
    ];
  },
  // ngrok 외부 원격 터널을 통한 HMR 및 Webpack 개발 리소스 로딩 차단 해제
  allowedDevOrigins: [
    "drop-down-prankish-breath.ngrok-free.dev",
    "*.ngrok-free.dev"
  ],
};

export default nextConfig;
