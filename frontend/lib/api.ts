/**
 * Stockcy API 클라이언트
 * 모든 백엔드(FastAPI) 호출은 이 파일을 통해 이루어집니다.
 */

import type { Favorite } from "@/lib/types";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function req<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) throw new Error(`API ${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

// ── 미국 시장 ─────────────────────────────────────────────────────────────────
export const api = {
  us: {
    indices:     ()                         => req("/api/us/indices"),
    session:     ()                         => req("/api/us/session"),
    stocks:      (tickers: string[])        => req(`/api/us/stocks?tickers=${tickers.join(",")}`),
    stockDetail: (ticker: string, exch = "NASDAQ") =>
                                               req(`/api/us/stocks/${ticker}?exchange=${exch}`),
    allStocks:   ()                         => req("/api/us/stocks/all"),
    sectorMap:   ()                         => req("/api/us/sector-map"),
    chart:       (ticker: string, period = "1y", interval = "1d") =>
                                               req(`/api/us/chart/${ticker}?period=${period}&interval=${interval}`),
    exchangeRate: ()                        => req<{ rate: number; symbol: string; fallback: boolean }>("/api/us/exchange-rate"),
    minuteChart: (ticker: string, iv = 5) => {
      const period = iv <= 5 ? "1d" : iv <= 30 ? "5d" : "1mo";
      return req(`/api/us/chart/${ticker}?period=${period}&interval=${iv}m`);
    },
  },

  // ── 국내 시장 ──────────────────────────────────────────────────────────────
  kr: {
    indices:        ()                       => req("/api/kr/indices"),
    stockPrice:     (code: string)           => req(`/api/kr/stocks/${code}`),
    stockName:      (code: string)           => req(`/api/kr/stocks/${code}/name`),
    allStocks:      ()                       => req("/api/kr/stocks/all"),
    volumeRanking:  (market = "ALL")         => req(`/api/kr/volume-ranking?market=${market}`),
    changeRanking:  (market = "ALL", dir = "up") =>
                                                req(`/api/kr/change-ranking?market=${market}&direction=${dir}`),
    investorTrend:  (market = "KOSPI")       => req(`/api/kr/investor-trend?market=${market}`),
    minuteChart:    (code: string, iv = 5)   => req(`/api/kr/chart/${code}/minute?interval=${iv}`),
    dailyChart:     (code: string, p = 600, unit = "D") => req(`/api/kr/chart/${code}/daily?period=${p}&unit=${unit}`),
    stocksBulk:     (codes: string[])        => req(`/api/kr/stocks-bulk?codes=${codes.join(",")}`),
    sectorMap:      ()                       => req("/api/kr/sector-map"),
    hotSectors:     ()                       => req("/api/kr/hot-sectors"),
    todayMarket:    ()                       => req("/api/kr/today-market"),
    stockInvestorTrendByCode: (code: string) => req(`/api/kr/stocks/${code}/investor-trend`),
  },

  ai: {
    krStockReport:  (code: string, name: string, priceData: any, investorData: any[]) => req("/api/ai/kr-stock-report", {
      method: "POST",
      body: JSON.stringify({ code: code, name: name, price_data: priceData, investor_data: investorData }),
    }),
    scenarios: ()                            => req("/api/ai/scenarios"),
    sectorRotation: ()                       => req("/api/ai/sector-rotation"),
    realtimePicksKr: (body: any = {})        => req("/api/ai/realtime-picks-kr", {
      method: "POST",
      body: JSON.stringify(body),
    }),
    realtimePicksUs: (body: any = {})        => req("/api/ai/realtime-picks-us", {
      method: "POST",
      body: JSON.stringify(body),
    }),
    usStockReport: (ticker: string, currentPrice: number, changePct: number) =>
      req("/api/ai/stock-report", {
        method: "POST",
        body: JSON.stringify({ ticker, current_price: currentPrice, change_pct: changePct }),
      }),
    sellTiming: (ticker: string, name: string, avgPrice: number, currentPrice: number, market: string) =>
      req("/api/ai/sell-timing", {
        method: "POST",
        body: JSON.stringify({ ticker, name, avg_price: avgPrice, current_price: currentPrice, market }),
      }),
  },

  // ── 포트폴리오·즐겨찾기 ───────────────────────────────────────────────────
  portfolio: {
    loadPortfolio: ()                        => req("/api/portfolio"),
    loadAi:        ()                        => req("/api/portfolio/ai"),
    loadFavorites: async () => {
      const r = await req<{ data: Favorite[]; message: string }>("/api/favorites");
      return r.data ?? [];
    },
    addFavorite: (marketType: string, ticker: string, name: string) =>
      req("/api/favorites", {
        method: "POST",
        body: JSON.stringify({ market_type: marketType, ticker, name }),
      }),
    removeFavorite: (ticker: string)         => req(`/api/favorites/${ticker}`, { method: "DELETE" }),
    checkFavorite:  (ticker: string)         => req(`/api/favorites/${ticker}/check`),
    loadTrades:    ()                        => req("/api/trades"),
    saveTrade:     (trade: Record<string, unknown>) => req("/api/trades", { method: "POST", body: JSON.stringify({ trade }) }),
    deleteTrade:   (ticker: string, sellDate: string) =>
                     req("/api/trades", { method: "DELETE", body: JSON.stringify({ ticker, sell_date: sellDate }) }),
    loadAlerts:    ()                        => req("/api/alerts"),
    saveAlert:     (market: string, ticker: string, name: string, alertType: string, targetPrice: number) =>
                     req("/api/alerts", { method: "POST", body: JSON.stringify({ market, ticker, name, alert_type: alertType, target_price: targetPrice }) }),
    deleteAlert:   (ticker: string, alertType: string) =>
                     req("/api/alerts", { method: "DELETE", body: JSON.stringify({ ticker, alert_type: alertType }) }),
  },

  // ── 시스템 ────────────────────────────────────────────────────────────────
  system: {
    health:       ()                         => req("/api/health"),
    configStatus: ()                         => req("/api/config-status"),
  },

};

// ── SSE 연결 유틸 ─────────────────────────────────────────────────────────────
/**
 * SSE 스트림에 연결하고 각 이벤트를 콜백으로 전달합니다.
 * POST body가 있으면 fetch + ReadableStream 방식으로 처리합니다.
 */
export async function connectSSE<T>(
  path: string,
  onEvent: (evt: { status: string; message?: string; result?: T; from_cache?: boolean }) => void,
  options?: { method?: "GET" | "POST"; body?: object }
): Promise<void> {
  const method = options?.method ?? "GET";
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: options?.body ? JSON.stringify(options.body) : undefined,
  });

  if (!res.body) throw new Error("SSE: no response body");

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE 메시지는 "data: {...}\n\n" 형태
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";   // 마지막 미완성 청크는 보관

    for (const part of parts) {
      const line = part.trim();
      if (!line.startsWith("data:")) continue;
      try {
        const payload = JSON.parse(line.slice(5).trim());
        onEvent(payload);
      } catch {
        // 파싱 실패 무시
      }
    }
  }
}
