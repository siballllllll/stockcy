import type { Metadata, Viewport } from "next";
import "./globals.css";
import { TopNav } from "@/components/layout/TopNav";
import { MarketTickerBar } from "@/components/layout/MarketTickerBar";
import { Providers } from "@/components/Providers";
import { AiTaskProvider } from "@/contexts/AiTaskContext";
import { NotificationPoller } from "@/components/NotificationPoller";

export const metadata: Metadata = {
  title: "Stockcy — AI 트레이딩 대시보드",
  description: "실시간 주가 분석 · 매크로 시나리오 · AI 단타 전략",
};

// 모바일 정상 렌더링: 기기 폭 기준 + 초기 배율 1 (없으면 데스크톱 폭으로 축소 렌더됨)
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko" style={{ height: "100%" }}>
      <body style={{ minHeight: "100%", display: "flex", flexDirection: "column" }}>
        <Providers>
          <AiTaskProvider>
            <NotificationPoller />
            <TopNav />
            <MarketTickerBar />
            <main
              style={{
                flex:    1,
                width:   "100%",
                margin:  "0 auto",
                padding: "1.5rem 5%",
              }}
            >
              {children}
            </main>
          </AiTaskProvider>
        </Providers>
      </body>
    </html>
  );
}
