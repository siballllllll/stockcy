/**
 * Stockcy API 클라이언트
 * 모든 백엔드(FastAPI) 호출은 이 파일을 통해 이루어집니다.
 */

import type { Favorite } from "@/lib/types";
import { getToken } from "@/lib/auth-context";

const BASE = typeof window === "undefined"
  ? (process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000")
  : "/backend";

async function req<T>(path: string, opts?: RequestInit): Promise<T> {
  const headers = new Headers(opts?.headers);
  headers.set("Content-Type", "application/json");
  headers.set("ngrok-skip-browser-warning", "69420");
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  // 30초 타임아웃 — 백엔드가 일시적으로 응답 불능(524 등)일 때 100초씩 매달리지 않도록.
  // (AI 생성은 SSE(connectSSE)를 쓰므로 이 경로는 빠른 JSON 조회만 해당.)
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 30000);
  try {
    const res = await fetch(`${BASE}${path}`, {
      ...opts,
      headers: headers,
      cache: "no-store", // Next.js 서버 사이드 캐싱 강력 차단
      signal: opts?.signal ?? ctrl.signal,
    });
    if (!res.ok) throw new Error(`API ${path} → ${res.status}`);
    return res.json() as Promise<T>;
  } finally {
    clearTimeout(timer);
  }
}

// ── 미국 시장 ─────────────────────────────────────────────────────────────────
export const api = {
  us: {
    indices:     ()                         => req("/api/us/indices"),
    session:     ()                         => req("/api/us/session"),
    stocks:      (tickers: string[])        => req(`/api/us/stocks?tickers=${tickers.join(",")}`),
    krNames:     (tickers: string[])        => req<Record<string, string>>(`/api/us/kr-names?tickers=${tickers.join(",")}`),
    pricesBulk:  (tickers: string[]) =>
      req<Record<string, { price: number; change_pct: number }>>("/api/us/prices-bulk", {
        method: "POST",
        body: JSON.stringify({ tickers }),
      }),
    stockDetail: (ticker: string, exch = "NASDAQ") =>
                                               req(`/api/us/stocks/${ticker}?exchange=${exch}`),
    allStocks:   ()                         => req("/api/us/stocks/all"),
    sectorMap:   ()                         => req("/api/us/sector-map"),
    chart:       (ticker: string, period = "1y", interval = "1d") =>
                                               req(`/api/us/chart/${ticker}?period=${period}&interval=${interval}`),
    exchangeRate: ()                        => req<{ rate: number; symbol: string; fallback: boolean }>("/api/us/exchange-rate"),
    treasury10y:  ()                        => req<{ yield: number; change: number; fallback: boolean }>("/api/us/treasury-10y"),
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
    stockPrice:     (code: string, fundamental = false) => req(`/api/kr/stocks/${code}${fundamental ? "?fundamental=true" : ""}`),
    stockName:      (code: string)           => req(`/api/kr/stocks/${code}/name`),
    allStocks:      ()                       => req("/api/kr/stocks/all"),
    volumeRanking:  (market = "ALL")         => req(`/api/kr/volume-ranking?market=${market}`),
    changeRanking:  (market = "ALL", dir = "up") =>
                                                req(`/api/kr/change-ranking?market=${market}&direction=${dir}`),
    investorTrend:  (market = "KOSPI")       => req(`/api/kr/investor-trend?market=${market}`),
    minuteChart:    (code: string, iv = 5)   => req(`/api/kr/chart/${code}/minute?interval=${iv}`),
    dailyChart:     (code: string, p = 600, unit = "D") => req(`/api/kr/chart/${code}/daily?period=${p}&unit=${unit}`),
    stocksBulk:     async (codes: string[]) => {
      const CHUNK = 50;
      const results: Record<string, any> = {};
      for (let i = 0; i < codes.length; i += CHUNK) {
        const chunk = codes.slice(i, i + CHUNK);
        const data = await req<Record<string, any>>(`/api/kr/stocks-bulk?codes=${chunk.join(",")}`);
        Object.assign(results, data);
      }
      return results;
    },
    overtimeBulk:   (codes: string[]) =>
      req<Record<string, { price: number; change: number; change_pct: number; sign: string; status: string; session: string }>>(
        `/api/kr/overtime-bulk?codes=${codes.join(",")}`),
    // 정규장 실시간 시세(네이버) — 화면용. FDR(지연)·KIS(보합) 대체.
    realtimeBulk:   (codes: string[]) =>
      req<Record<string, { price: number; change: number; change_pct: number; sign: string }>>(
        `/api/kr/realtime-bulk?codes=${codes.join(",")}`),
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
    valuationScore: (ticker: string, market: string) =>
      req(`/api/ai/valuation-score?ticker=${encodeURIComponent(ticker)}&market=${market}`),
    stockIssues: (tickers: string[]) =>
      req("/api/ai/stock-issues", { method: "POST", body: JSON.stringify({ tickers }) }),
    issueStocks: (keyword: string, exclude?: string) =>
      req(`/api/ai/issue-stocks?keyword=${encodeURIComponent(keyword)}${exclude ? `&exclude=${encodeURIComponent(exclude)}` : ""}`),
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
    loadTossHoldings: ()                      => req<{ connected: boolean; holdings: Array<{ symbol: string; name: string; quantity: number; avg_price: number; last_price: number; market_value: number; profit_loss: number }> }>("/api/portfolio/toss/holdings"),
    tossPricesBulk: (symbols: string[])       => req<Record<string, number>>(`/api/prices/toss-bulk?symbols=${symbols.join(",")}`),
    stockWarnings: (symbols: string[])        => req<Record<string, Array<{ type: string; type_kr: string; severe: boolean; start: string | null; end: string | null }>>>(`/api/stocks/warnings?symbols=${symbols.join(",")}`),
    loadAgentPortfolio: ()                   => req("/api/portfolio/agent"),
    loadAgentBalance: ()                     => req<{ cash: number; seed: number }>("/api/portfolio/agent/balance"),
    loadAgentScanLogs: ()                    => req<any[]>("/api/portfolio/agent/scan-logs"),
    loadAi:        ()                        => req("/api/portfolio/ai"),
    loadFavorites: async () => {
      const r = await req<{ data: Favorite[]; message: string }>("/api/favorites");
      return r.data ?? [];
    },
    addFavorite: (marketType: string, ticker: string, name: string, memo = "", sector = "") =>
      req("/api/favorites", {
        method: "POST",
        body: JSON.stringify({ market_type: marketType, ticker, name, memo, sector }),
      }),
    updateFavoriteMemo: (ticker: string, memo: string) =>
      req("/api/favorites/memo", {
        method: "POST",
        body: JSON.stringify({ ticker, memo }),
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
    updateTradeBuyDate: (ticker: string, sellDate: string, buyDate: string) =>
                     req("/api/trades/buy-date", { method: "PATCH", body: JSON.stringify({ ticker, sell_date: sellDate, buy_date: buyDate }) }),
    updatePortfolioBuyTime: (ticker: string, buyTime: string, owner: string = "USER") =>
                     req("/api/portfolio/buy-time", { method: "PATCH", body: JSON.stringify({ ticker, buy_time: buyTime, owner }) }),
    updateTradeBuyReason: (ticker: string, sellDate: string, buyReason: string) =>
                     req("/api/trades/buy-reason", { method: "PATCH", body: JSON.stringify({ ticker, sell_date: sellDate, buy_reason: buyReason }) }),
    loadAlerts:    ()                        => req("/api/alerts"),
    saveAlert:     (market: string, ticker: string, name: string, alertType: string, targetPrice: number) =>
                     req("/api/alerts", { method: "POST", body: JSON.stringify({ market, ticker, name, alert_type: alertType, target_price: targetPrice }) }),
    deleteAlert:   (ticker: string, alertType: string) =>
                     req("/api/alerts", { method: "DELETE", body: JSON.stringify({ ticker, alert_type: alertType }) }),
  },

  // ── 시나리오 유저 데이터(서버 영속): 커스텀 시나리오 · 최근 검색어 ──────────
  scenarios: {
    loadCustom: async () => {
      const r = await req<{ data: any[] }>("/api/custom-scenarios");
      return r.data ?? [];
    },
    saveCustom: (keyword: string, title: string, payload: any, searchedAt = "") =>
      req<{ success: boolean; id: number | null }>("/api/custom-scenarios", {
        method: "POST",
        body: JSON.stringify({ keyword, title, payload, searched_at: searchedAt }),
      }),
    deleteCustom: (id: number) => req(`/api/custom-scenarios/${id}`, { method: "DELETE" }),
    loadRecent: async () => {
      const r = await req<{ data: string[] }>("/api/recent-searches");
      return r.data ?? [];
    },
    saveRecent: (keyword: string) =>
      req("/api/recent-searches", { method: "POST", body: JSON.stringify({ keyword }) }),
    // [마인드맵 탐색] 노드 펼치기 — 가벼운 연관 키워드(검색X·무크레딧·캐시). refresh=true면 최신 갱신.
    mindmapExpand: (topic: string, context = "", refresh = false) =>
      req<{ topic: string; keywords: { label: string; desc: string }[]; from_cache?: boolean; error?: string }>(
        "/api/ai/scenarios/mindmap/expand",
        { method: "POST", body: JSON.stringify({ topic, context, refresh }) },
      ),
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
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

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
