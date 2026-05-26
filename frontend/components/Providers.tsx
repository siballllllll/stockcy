"use client";
import { MarketProvider } from "@/lib/market-context";
import { AnalysisReadyProvider } from "@/lib/analysis-ready-context";
import type { ReactNode } from "react";

// ngrok 외부 원격 터널을 통한 접속 시, 모든 비동기 fetch API 요청의 ngrok 차단 우회 자동화 (몽키 패치)
if (typeof window !== "undefined") {
  const originalFetch = window.fetch;
  window.fetch = async function (input, init) {
    const headers = new Headers(init?.headers);
    headers.set("ngrok-skip-browser-warning", "69420");
    return originalFetch(input, { ...init, headers });
  };
}

export function Providers({ children }: { children: ReactNode }) {
  return (
    <AnalysisReadyProvider>
      <MarketProvider>{children}</MarketProvider>
    </AnalysisReadyProvider>
  );
}
