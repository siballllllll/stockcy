import type { Metadata } from "next";
import "./globals.css";
import { TopNav } from "@/components/layout/TopNav";
import { MarketTickerBar } from "@/components/layout/MarketTickerBar";

export const metadata: Metadata = {
  title: "Stockcy — AI 트레이딩 대시보드",
  description: "실시간 주가 분석 · 매크로 시나리오 · AI 단타 전략",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko" style={{ height: "100%" }}>
      <body style={{ minHeight: "100%", display: "flex", flexDirection: "column" }}>
        <TopNav />
        <MarketTickerBar />
        <main
          style={{
            flex:       1,
            width:      "100%",
            margin:     "0 auto",
            padding:    "1.5rem 5%", // 양옆에 5% 여백을 주어 꽉 막힌 느낌 해소
          }}
        >
          {children}
        </main>
      </body>
    </html>
  );
}
