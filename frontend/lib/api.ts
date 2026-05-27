/**
 * Stockcy API 클라이언트
 * 모든 백엔드(FastAPI) 호출은 이 파일을 통해 이루어집니다.
 */

import type { Favorite } from "@/lib/types";

const BASE = typeof window === "undefined"
  ? (process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000")
  : "/backend";

async function req<T>(path: string, opts?: RequestInit): Promise<T> {
  const headers = new Headers(opts?.headers);
  headers.set("Content-Type", "application/json");
  headers.set("ngrok-skip-browser-warning", "69420");

  const res = await fetch(`${BASE}${path}`, {
    ...opts,
    headers: headers,
    cache: "no-store", // Next.js 서버 사이드 캐싱 강력 차단
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
    exchangeRatesHistorical: (dates: string[]) => req<Record<string, number>>(`/api/us/exchange-rates-historical?dates=${dates.join(",")}`),
    crypto:       (symbol = "BTC")         => req<{ symbol: string; price: number; change_pct: number; error?: boolean }>(`/api/us/crypto/${symbol}`),
    minuteChart: (ticker: string, iv = 5) => {
      // 1분봉은 7일치, 5분봉 이상은 60일치로 미국 주식 물리적 제공 한계 극대화!
      const period = iv <= 1 ? "7d" : "60d";
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
    boxPattern: (ticker: string, name: string, priceData: any, market: string = "KR") =>
      req("/api/ai/box-pattern", {
        method: "POST",
        body: JSON.stringify({ ticker, name, price_data: priceData, market }),
      }),
    shadowSector: (ticker: string, name: string, market: string = "KR") =>
      req("/api/ai/shadow-sector", {
        method: "POST",
        body: JSON.stringify({ ticker, name, market }),
      }),
    shadowDiscover: (keyword: string) =>
      req("/api/ai/shadow-discover", {
        method: "POST",
        body: JSON.stringify({ keyword }),
      }),
    overnightGap: (ticker: string, name: string, market: string = "KR") =>
      req("/api/ai/overnight-gap", {
        method: "POST",
        body: JSON.stringify({ ticker, name, market }),
      }),
    overnightGapBulk: (tickers: string[]) =>
      req<{ status: string; results: Record<string, any> }>("/api/ai/overnight-gap-bulk", {
        method: "POST",
        body: JSON.stringify({ tickers }),
      }),
  },

  // ── 포트폴리오·즐겨찾기 ───────────────────────────────────────────────────
  portfolio: {
    loadPortfolio: ()                        => req("/api/portfolio"),
    loadAgentPortfolio: ()                   => req("/api/portfolio/agent"),
    loadAgentScanLogs: ()                    => req<any[]>("/api/portfolio/agent/scan-logs"),
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
    loadAgentTrades: ()                      => req("/api/trades/agent"),
    
    saveTrade:     (trade: Record<string, unknown>) => req("/api/trades", { method: "POST", body: JSON.stringify({ trade }) }),
    deleteTrade:   (ticker: string, sellDate: string) =>
                     req("/api/trades", { method: "DELETE", body: JSON.stringify({ ticker, sell_date: sellDate }) }),
    updateTradeTag: (ticker: string, sellDate: string, tradeSource: string, tradeType: string) =>
                     req("/api/trades", { method: "PATCH", body: JSON.stringify({ ticker, sell_date: sellDate, trade_source: tradeSource, trade_type: tradeType }) }),
    loadAlerts:    ()                        => req("/api/alerts"),
    saveAlert:     (market: string, ticker: string, name: string, alertType: string, targetPrice: number) =>
                     req("/api/alerts", { method: "POST", body: JSON.stringify({ market, ticker, name, alert_type: alertType, target_price: targetPrice }) }),
    deleteAlert:   (ticker: string, alertType: string) =>
                     req("/api/alerts", { method: "DELETE", body: JSON.stringify({ ticker, alert_type: alertType }) }),
  },

  // ── 트레이딩 ──────────────────────────────────────────────────────────────
  trading: {
    getBalances: () => req("/api/trading/balances"),
    buy:         (owner: string, ticker: string, name: string, price: number, quantity: number, rating = "-") =>
                   req("/api/trading/buy", { method: "POST", body: JSON.stringify({ owner, ticker, name, buy_price: price, quantity, rating }) }),
    sell:        (owner: string, ticker: string, name: string, price: number, quantity: number) =>
                   req("/api/trading/sell", { method: "POST", body: JSON.stringify({ owner, ticker, name, sell_price: price, quantity }) }),
  },

  // ── 시스템 ────────────────────────────────────────────────────────────────
  system: {
    health:       ()                         => req("/api/health"),
    configStatus: ()                         => req("/api/config-status"),
  },

};

// ── SSE 전용 베이스 URL (Next.js 프록시 우회 — 프록시가 큰 done 응답을 버퍼링하는 문제 방지) ──
// 클라이언트에서도 백엔드를 직접 호출합니다. CORS는 main.py에서 허용 중.
const SSE_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

// ── SSE 연결 유틸 ─────────────────────────────────────────────────────────────
/**
 * SSE 스트림에 연결하고 각 이벤트를 콜백으로 전달합니다.
 * POST body가 있으면 fetch + ReadableStream 방식으로 처리합니다.
 */
export async function connectSSE<T>(
  path: string,
  onEvent: (evt: { status: string; message?: string; result?: T; from_cache?: boolean }) => void,
  options?: { method?: "GET" | "POST"; body?: object; signal?: AbortSignal }
): Promise<void> {
  const method = options?.method ?? "GET";
  const headers = new Headers();
  headers.set("Content-Type", "application/json");
  headers.set("ngrok-skip-browser-warning", "69420");

  const res = await fetch(`${SSE_BASE}${path}`, {
    method,
    headers: headers,
    body: options?.body ? JSON.stringify(options.body) : undefined,
    signal: options?.signal,
  });

  if (!res.body) throw new Error("SSE: no response body");

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let lastStatus = "idle";

  while (true) {
    const { done, value } = await reader.read();
    if (value) {
      buffer += decoder.decode(value, { stream: true });
    }

    // SSE 메시지는 "data: {...}\n\n" 형태
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";   // 마지막 미완성 청크는 보관

    for (const part of parts) {
      const line = part.trim();
      if (!line.startsWith("data:")) continue;
      try {
        const payload = JSON.parse(line.slice(5).trim());
        lastStatus = payload.status;
        onEvent(payload);
      } catch {
        // 파싱 실패 무시
      }
    }

    if (done) break;
  }

  // 스트림 리더가 종료되었으나 남아있는 버퍼가 있는 경우 최종 파싱 처리 (경계 조건 구제)
  const remaining = buffer.trim();
  if (remaining) {
    const lines = remaining.split("\n");
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed.startsWith("data:")) continue;
      try {
        const payload = JSON.parse(trimmed.slice(5).trim());
        lastStatus = payload.status;
        onEvent(payload);
      } catch {
        // 파싱 실패 무시
      }
    }
  }

  // 스트림이 종료되었는데 완료(done)나 에러(error) 상태가 아니라면 비정상 종료로 간주
  if (lastStatus !== "done" && lastStatus !== "error") {
    onEvent({ status: "error", message: "서버와의 연결이 비정상적으로 끊어졌거나 응답이 올바르지 않습니다. 다시 시도해주세요." });
  }
}
