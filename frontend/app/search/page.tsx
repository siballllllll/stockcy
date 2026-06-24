"use client";
import { useState, useEffect, useRef, useMemo, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import useSWR from "swr";
import { api, connectSSE } from "@/lib/api";
import { useMarket } from "@/lib/market-context";
import { useAiTask } from "@/contexts/AiTaskContext";
import { Search, Star, Briefcase, Bell, BarChart2, DollarSign, Activity, Loader2, PlusCircle, X } from "lucide-react";
import Chart from "@/components/Chart";
import OrderbookPanel from "@/components/ui/OrderbookPanel";
import { MarkdownLite } from "@/components/ui/MarkdownLite";
import { AiCostBadge } from "@/components/ui/AiCostBadge";
import ReactMarkdown from "react-markdown";

// ── 종목 AI 분석 결과 localStorage 캐시 (페이지 이동/재방문 후 복원용, 14일 유효) ──
// 분석 시점(ts)·당시 주가(price)를 함께 저장해 "언제·당시 얼마에 분석/추천했는지"를 표시 → 교차검증.
const _AI_CACHE_PREFIX = "stockcy_ai_stock_";
const _AI_CACHE_TTL = 14 * 24 * 60 * 60 * 1000;  // 14일
function _aiKey(code: string) { return _AI_CACHE_PREFIX + String(code).trim().toUpperCase(); }
// 분석 결과가 정상적인 객체 형태인지 검증 (구버전 배열 캐시 등 비정상 형태 차단)
function _isValidAiResult(r: any): boolean {
  return !!r && typeof r === "object" && !Array.isArray(r) && typeof r.rating !== "undefined";
}
function _saveAiCache(code: string, result: any, price?: number) {
  if (typeof window === "undefined" || !code || !_isValidAiResult(result)) return;
  try {
    localStorage.setItem(_aiKey(code), JSON.stringify({ result, ts: Date.now(), price: Number(price) || 0 }));
  } catch {}
}
// 반환: { result, ts, price } (없으면 null)
function _loadAiCache(code: string): { result: any; ts: number; price: number } | null {
  if (typeof window === "undefined" || !code) return null;
  try {
    const raw = localStorage.getItem(_aiKey(code));
    if (!raw) return null;
    const { result, ts, price } = JSON.parse(raw);
    if (Date.now() - ts > _AI_CACHE_TTL) { localStorage.removeItem(_aiKey(code)); return null; }
    // 구버전 배열 캐시 등 비정상 형태면 제거하고 재분석 유도 (가짜 '분석 중' 표시 방지)
    if (!_isValidAiResult(result)) { localStorage.removeItem(_aiKey(code)); return null; }
    return { result, ts: Number(ts) || 0, price: Number(price) || 0 };
  } catch { return null; }
}

// 즐겨찾기 버튼 (검색 페이지에서 즉시 추가/제거)
function FavButton({ ticker, name, market }: { ticker: string; name: string; market: string }) {
  const { data: checkData, mutate } = useSWR(
    ticker ? `/api/favorites/${ticker}/check` : null,
    () => api.portfolio.checkFavorite(ticker) as Promise<{ is_favorite: boolean }>
  );
  const [loading, setLoading] = useState(false);
  const isFav = checkData?.is_favorite ?? false;

  const toggle = async () => {
    setLoading(true);
    if (isFav) {
      await api.portfolio.removeFavorite(ticker).catch(() => {});
    } else {
      await api.portfolio.addFavorite(market, ticker, name || ticker).catch(() => {});
    }
    mutate();
    setLoading(false);
  };

  return (
    <button
      onClick={toggle}
      disabled={loading || !ticker}
      className="stockcy-btn"
      style={{ flex: 1, padding: "8px", fontSize: "0.95rem", display: "flex", justifyContent: "center", gap: "6px", background: isFav ? "rgba(255,180,0,0.1)" : "var(--color-elevated)", border: `1px solid ${isFav ? "var(--color-warning)" : "var(--color-border)"}` }}
    >
      <Star size={14} color={isFav ? "var(--color-warning)" : "var(--color-muted)"} fill={isFav ? "var(--color-warning)" : "none"} />
      {isFav ? "즐겨찾기 해제" : "즐겨찾기 추가"}
    </button>
  );
}

const BASE_URL_SEARCH = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// 보유종목 추가 버튼 (검색 페이지에서 직접 추가)
function PortfolioAddButton({
  ticker, name, market, currentPrice,
}: { ticker: string; name: string; market: string; currentPrice: number }) {
  const [open, setOpen]       = useState(false);
  const [buyPrice, setBuyPrice] = useState("");
  const [qty, setQty]         = useState("");
  const [loading, setLoading] = useState(false);
  const [msg, setMsg]         = useState<{ type: "success" | "error"; text: string } | null>(null);

  // ticker가 바뀌면 초기화
  const prevTicker = useRef(ticker);
  if (prevTicker.current !== ticker) {
    prevTicker.current = ticker;
    if (open) { setOpen(false); setMsg(null); }
  }

  const handleAdd = async () => {
    const bp = Number(buyPrice) || currentPrice;
    const q  = Number(qty);
    if (!q || q <= 0) return;
    setLoading(true);
    setMsg(null);
    try {
      const current = await api.portfolio.loadPortfolio() as any[];
      const padded  = market === "국내" ? String(ticker).padStart(6, "0") : ticker;
      const updated = [...(current ?? []), { ticker: padded, name: name || padded, buy_price: bp, quantity: q }];
      await fetch(`${BASE_URL_SEARCH}/api/portfolio`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ portfolio_list: updated }),
      });
      setMsg({ type: "success", text: `${name} 보유종목 추가 완료 (${q}주 @ ${market === "국내" ? "₩" : "$"}${bp.toLocaleString()})` });
      setQty(""); setOpen(false);
    } catch {
      setMsg({ type: "error", text: "추가 실패. 다시 시도해 주세요." });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ flex: 1, position: "relative" }}>
      <button
        onClick={() => { setOpen(v => !v); setMsg(null); }}
        className="stockcy-btn"
        style={{ width: "100%", padding: "8px", fontSize: "0.95rem", display: "flex", justifyContent: "center", alignItems: "center", gap: "6px", background: open ? "rgba(80,200,80,0.1)" : "var(--color-elevated)", border: `1px solid ${open ? "var(--color-success)" : "var(--color-border)"}` }}
      >
        <PlusCircle size={14} color={open ? "var(--color-success)" : "var(--color-muted)"} />
        보유종목 추가
      </button>

      {open && (
        <div style={{
          position: "absolute", top: "calc(100% + 6px)", left: 0, right: 0, zIndex: 30,
          background: "var(--color-card)", border: "1px solid var(--color-success)",
          borderRadius: "8px", padding: "12px", boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
          display: "flex", flexDirection: "column", gap: "8px",
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: "0.82rem", fontWeight: 700, color: "var(--color-text)" }}>
              {name} ({ticker}) 보유종목 추가
            </span>
            <button onClick={() => setOpen(false)} style={{ background: "transparent", border: "none", cursor: "pointer", color: "var(--color-muted)", padding: "2px" }}>
              <X size={14} />
            </button>
          </div>
          <div style={{ display: "flex", gap: "6px" }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: "0.72rem", color: "var(--color-muted)", marginBottom: "3px" }}>평단가</div>
              <input
                className="stockcy-input"
                type="number"
                placeholder={String(currentPrice || "")}
                value={buyPrice}
                onChange={e => setBuyPrice(e.target.value)}
                style={{ width: "100%", fontSize: "0.85rem", boxSizing: "border-box" }}
              />
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: "0.72rem", color: "var(--color-muted)", marginBottom: "3px" }}>수량 (주)</div>
              <input
                className="stockcy-input"
                type="number"
                placeholder="0"
                value={qty}
                onChange={e => setQty(e.target.value)}
                onKeyDown={e => e.key === "Enter" && handleAdd()}
                style={{ width: "100%", fontSize: "0.85rem", boxSizing: "border-box" }}
              />
            </div>
          </div>
          <button
            className="stockcy-btn stockcy-btn-primary"
            onClick={handleAdd}
            disabled={loading || !qty || Number(qty) <= 0}
            style={{ width: "100%", padding: "7px", fontWeight: 700, fontSize: "0.85rem", display: "flex", alignItems: "center", justifyContent: "center", gap: "6px" }}
          >
            {loading ? <><Loader2 className="animate-spin" size={13} /> 추가 중...</> : "추가하기"}
          </button>
          {msg && (
            <div style={{ fontSize: "0.75rem", color: msg.type === "success" ? "var(--color-success)" : "var(--color-danger)", textAlign: "center" }}>
              {msg.text}
            </div>
          )}
        </div>
      )}

      {/* 추가 완료 메시지 (팝업 닫힌 후) */}
      {!open && msg?.type === "success" && (
        <div style={{ fontSize: "0.72rem", color: "var(--color-success)", marginTop: "3px", textAlign: "center" }}>
          ✓ {msg.text}
        </div>
      )}
    </div>
  );
}

// 한글 초성 추출 유틸리티
const CHOSUNG = ["ㄱ", "ㄲ", "ㄴ", "ㄷ", "ㄸ", "ㄹ", "ㅁ", "ㅂ", "ㅃ", "ㅅ", "ㅆ", "ㅇ", "ㅈ", "ㅉ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ"];
function getChosung(str: string) {
  let res = "";
  for (let i = 0; i < str.length; i++) {
    const code = str.charCodeAt(i) - 44032;
    if (code > -1 && code < 11172) {
      res += CHOSUNG[Math.floor(code / 588)];
    } else {
      res += str.charAt(i);
    }
  }
  return res;
}

function SearchPageInner() {
  const { market, setMarket } = useMarket();
  const isKR = market === "KR";
  const currSymbol = isKR ? "₩" : "$";

  const searchParams = useSearchParams();
  const router = useRouter();
  const { notifyDone } = useAiTask();
  const [searchQuery, setSearchQuery] = useState("");
  const [activeTab, setActiveTab] = useState("시세");
  const [currentCode, setCurrentCode] = useState<string>(isKR ? "005930" : "AAPL");

  // 최근 검색 기록 (KR/US 통합, 최대 10개)
  const RECENT_KEY = "stockcy_recent_searches_v2";
  const [recentSearches, setRecentSearches] = useState<{ code: string; name: string; market: string }[]>([]);

  useEffect(() => {
    try {
      const stored = localStorage.getItem(RECENT_KEY);
      if (stored) {
        setRecentSearches(JSON.parse(stored));
      }
    } catch {
      // ignore
    }
  }, []);

  const removeRecentSearch = (code: string, market: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setRecentSearches(prev => {
      const next = prev.filter(r => !(r.code === code && r.market === market));
      try { localStorage.setItem(RECENT_KEY, JSON.stringify(next)); } catch {}
      return next;
    });
  };
  const [chartType, setChartType]     = useState<string>("daily");
  const [chartPeriod, setChartPeriod] = useState<string>("6M");   // 기본 6개월=토스 소스
  const [minuteInterval, setMinuteInterval] = useState<number>(5);

  // 기간 옵션: 차트 타입별 (분봉은 기간 없음)
  // 일봉의 3M/6M은 토스 소스로 그려짐(현재가·평가액과 일치), 1Y/MAX는 KIS/yfinance.
  const PERIOD_OPTIONS: Record<string, string[]> = {
    daily:   ["3M", "6M", "1Y", "MAX"],
    weekly:  ["MAX"],
    monthly: ["MAX"],
    minute:  [],
  };
  // KR: 기간 → 일봉 개수 (3M=66·6M=130 → get_kr_daily_chart에서 토스 1차)
  const KR_PERIOD_DAYS: Record<string, Record<string, number>> = {
    daily:   { "3M": 66, "6M": 130, "1Y": 250, "MAX": 5000 },
    weekly:  { "MAX": 1000 },
    monthly: { "MAX": 600 },
  };
  // US: 기간 → yfinance period (3mo/6mo → us_chart에서 토스 1차)
  const US_PERIOD: Record<string, Record<string, string>> = {
    daily:   { "3M": "3mo", "6M": "6mo", "1Y": "1y", "MAX": "max" },
    weekly:  { "MAX": "max" },
    monthly: { "MAX": "max" },
  };
  const [showDropdown, setShowDropdown] = useState(false);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [aiResult, setAiResult] = useState<any>(null);
  const [aiMeta, setAiMeta] = useState<{ ts: number; price: number } | null>(null);  // 분석 시점·당시가 (교차검증용)
  const [aiStatus, setAiStatus] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [aiAnalysisTab, setAiAnalysisTab] = useState<"short" | "entry" | "mid" | "long">("short");
  const [aiMsg, setAiMsg] = useState("");

  // RAG 상태 변수 정의 (아코디언 UI 제거 이전의 원래 기획 사양)
  const [shadowStatus, setShadowStatus] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [shadowResult, setShadowResult] = useState<any>(null);
  const [shadowMsg, setShadowMsg]       = useState<string>("RAG 분석 대기 중...");

  const [gapStatus, setGapStatus] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [gapResult, setGapResult] = useState<any>(null);
  const [gapMsg, setGapMsg]       = useState<string>("갭 예측 대기 중...");

  const [boxStatus, setBoxStatus] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [boxResult, setBoxResult] = useState<any>(null);
  const [boxMsg, setBoxMsg]       = useState<string>("박스권 분석 대기 중...");

  // 가격 알림 설정 모달 상태
  const [alertModalOpen, setAlertModalOpen] = useState(false);
  const [alertType, setAlertType] = useState("상승 돌파");
  const [targetPrice, setTargetPrice] = useState("");
  const [alertLoading, setAlertLoading] = useState(false);
  const [alertMsg, setAlertMsg] = useState<{ type: "success" | "error"; text: string } | null>(null);

  // 차트 타입 변경 시 유효한 기간으로 리셋
  useEffect(() => {
    if (chartType !== "minute") {
      setChartPeriod(chartType === "daily" ? "6M" : "MAX");
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chartType]);

  // 시장 전환 시 기본값 리셋
  const prevMarketRef = useRef<string | null>(null);
  useEffect(() => {
    if (prevMarketRef.current !== null && prevMarketRef.current !== market) {
      setCurrentCode(market === "KR" ? "005930" : "AAPL");
      setActiveTab("시세");
      setChartType("daily");
      setChartPeriod("6M");
      setAiStatus("idle");
      setAiResult(null);
    }
    prevMarketRef.current = market;
  }, [market]);

  // ── KR SWR ───────────────────────────────────────────────────────────────
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const { data: krStockData, isLoading: krLoading } = useSWR<any>(
    isKR ? `/api/kr/stocks/${currentCode}?fundamental=true` : null,
    () => api.kr.stockPrice(currentCode, true),   // 검색 상세 — PER/PBR 등 펀더멘털(KIS) 포함
    { refreshInterval: 30000 }
  );
  // 가격·등락률은 네이버 실시간으로 통일(슬라이드·즐겨찾기와 동일 소스). KIS는 펀더멘털용으로만 유지.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const { data: krRealtime } = useSWR<any>(
    isKR && currentCode ? `kr-rt-${currentCode}` : null,
    async () => {
      const m = await api.kr.realtimeBulk([currentCode]);
      return (m as any)[currentCode] ?? (m as any)[String(currentCode).padStart(6, "0")] ?? null;
    },
    { refreshInterval: 15000 }
  );
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const { data: nameData } = useSWR<any>(
    isKR ? `/api/kr/stocks/${currentCode}/name` : null,
    () => api.kr.stockName(currentCode)
  );
  const { data: allStocks } = useSWR(
    isKR ? "/api/kr/stocks/all" : null,
    () => api.kr.allStocks(),
    { revalidateOnFocus: false }
  );

  // US 전체 종목 맵 (ticker → 한국어 이름)
  const { data: usAllStocks } = useSWR(
    !isKR ? "/api/us/stocks/all" : null,
    () => api.us.allStocks(),
    { revalidateOnFocus: false }
  );

  // 섹터맵 (KR/US 공통)
  const { data: sectorMapData } = useSWR(
    isKR ? "/api/kr/sector-map" : "/api/us/sector-map",
    () => isKR ? api.kr.sectorMap() : api.us.sectorMap(),
    { revalidateOnFocus: false }
  );

  // 현재 종목의 섹터/세부섹터 찾기
  const sectorInfo = useMemo(() => {
    if (!sectorMapData || !currentCode) return null;
    const map = sectorMapData as Record<string, Record<string, any[]>>;
    for (const [sector, subMap] of Object.entries(map)) {
      if (!subMap || typeof subMap !== "object") continue;
      for (const [subSector, stocks] of Object.entries(subMap)) {
        if (!Array.isArray(stocks)) continue;
        const found = stocks.some((s: any) =>
          isKR ? String(s.code) === String(currentCode)
               : String(s.ticker).toUpperCase() === String(currentCode).toUpperCase()
        );
        if (found) return { sector, subSector };
      }
    }
    return null;
  }, [sectorMapData, currentCode, isKR]);

  // 투자경고/위험 배지 계산
  const warningBadges = useMemo(() => {
    if (!isKR || !krStockData) return [];
    const badges: { label: string; color: string; bg: string }[] = [];
    const warn    = krStockData.mrkt_warn   ?? "";
    const status  = krStockData.status_code ?? "";
    const halt    = krStockData.halt        ?? "N";
    const managed = krStockData.managed     ?? "N";
    const shortOv = krStockData.short_over  ?? "N";
    const vi      = krStockData.vi_type     ?? "N";

    if (halt === "Y")          badges.push({ label: "거래정지",  color: "#fff",     bg: "#555" });
    if (managed !== "N" && managed !== "00") badges.push({ label: "관리종목", color: "#fff", bg: "#7c3aed" });
    if (warn === "03" || status === "54")    badges.push({ label: "투자위험",  color: "#fff", bg: "#dc2626" });
    else if (warn === "02" || status === "53") badges.push({ label: "투자경고", color: "#fff", bg: "#ea580c" });
    else if (warn === "01" || status === "52") badges.push({ label: "투자주의", color: "#fff", bg: "#d97706" });
    if (shortOv === "Y")       badges.push({ label: "단기과열",  color: "#fff",     bg: "#0284c7" });
    if (vi !== "N" && vi !== "") badges.push({ label: "VI발동",  color: "#fff",     bg: "#059669" });
    return badges;
  }, [isKR, krStockData]);
  const { data: krChartRaw } = useSWR(
    isKR ? `/api/kr/chart/${currentCode}/${chartType}/${minuteInterval}/${chartPeriod}` : null,
    () => {
      if (chartType === "minute") return api.kr.minuteChart(currentCode, minuteInterval);
      const days = KR_PERIOD_DAYS[chartType]?.[chartPeriod] ?? 600;
      const unit = chartType === "weekly" ? "W" : chartType === "monthly" ? "M" : "D";
      return api.kr.dailyChart(currentCode, days, unit);
    }
  );
  const { data: invData, isLoading: invLoading } = useSWR(
    isKR && activeTab === "수급" ? `/api/kr/stocks/${currentCode}/investor-trend` : null,
    () => api.kr.stockInvestorTrendByCode(currentCode)
  );

  // ── US SWR ───────────────────────────────────────────────────────────────
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const { data: usStockData, isLoading: usLoading } = useSWR<any>(
    !isKR ? `/api/us/stocks/${currentCode}` : null,
    () => api.us.stockDetail(currentCode),
    { refreshInterval: 30000 }
  );
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const { data: usChartRaw } = useSWR<any>(
    !isKR ? `/api/us/chart/${currentCode}/${chartType}/${minuteInterval}/${chartPeriod}` : null,
    () => {
      if (chartType === "minute") return api.us.minuteChart(currentCode, minuteInterval);
      const period   = US_PERIOD[chartType]?.[chartPeriod] ?? "1y";
      const interval = chartType === "weekly" ? "1wk" : chartType === "monthly" ? "1mo" : "1d";
      return api.us.chart(currentCode, period, interval);
    }
  );

  // ── 통합 값 ──────────────────────────────────────────────────────────────
  const stockData  = isKR ? krStockData  : usStockData;
  const isLoading  = isKR ? krLoading    : usLoading;
  const chartDataRaw = isKR ? krChartRaw : usChartRaw;

  // KR이면 네이버 실시간으로 가격·등락률 통일(슬라이드와 일치). 없으면 KIS 값 폴백.
  const rtOk      = isKR && (krRealtime?.price ?? 0) > 0;
  const price     = rtOk ? krRealtime.price : (stockData?.price || 0);
  const change    = rtOk ? krRealtime.change_pct : (stockData?.change_pct || 0);
  const changeVal = Math.abs(rtOk ? krRealtime.change : (stockData?.change || 0));
  const isUp      = change > 0;
  const isDown    = change < 0;
  const color     = isUp ? "var(--color-danger)" : isDown ? "var(--color-primary)" : "var(--color-text)";
  const changeStr = isUp ? "▲" : isDown ? "▼" : "━";
  const stockName = isKR
    ? (nameData?.name || stockData?.name || currentCode)
    : (stockData?.name || currentCode);

  // KR 필드명 통합 (구 API: 52주최고가/PER, 신 API: w52_high/per 모두 지원)
  const w52High = stockData?.w52_high || stockData?.["52주최고가"] || price || 1;
  const w52Low  = stockData?.w52_low  || stockData?.["52주최저가"] || 1;
  const per = parseFloat(String(stockData?.per || stockData?.PER || "0").replace(/[^0-9.-]/g, "")) || 0;
  const pbr = parseFloat(String(stockData?.pbr || stockData?.PBR || 0).replace(",", "")) || 0;

  // 차트 데이터 파싱
  const chartData = useMemo(() => {
    if (!chartDataRaw || !Array.isArray(chartDataRaw)) return [];
    return chartDataRaw.map((d: any) => {
      const rawTime = d.일자 || d.date || d.날짜 || d.time || d.datetime || "";
      let finalTime: any = rawTime;
      if (chartType === "minute") {
        // KST 시간을 UTC 변환 없이 그대로 사용 → 차트에 KST 시간(09:00~15:30)이 표시됨
        const kstStr = rawTime.replace("T", " ").slice(0, 19); // "2024-05-26 09:05:00"
        const [datePart, timePart] = kstStr.split(" ");
        const [y, mo, d2] = datePart.split("-").map(Number);
        const [h, min, s] = (timePart || "00:00:00").split(":").map(Number);
        const ms = Date.UTC(y, mo - 1, d2, h, min, s || 0);
        finalTime = Math.floor(ms / 1000);
      } else {
        finalTime = rawTime.split(" ")[0];
      }
      return {
        time:   finalTime,
        open:   Number(d.open || d.시가 || 0),
        high:   Number(d.high || d.고가 || 0),
        low:    Number(d.low  || d.저가 || 0),
        close:  Number(d.close || d.종가 || 0),
        volume: Number(d.volume || d.거래량 || 0),
      };
    }).sort((a: any, b: any) => {
      const tA = typeof a.time === "number" ? a.time : new Date(a.time).getTime();
      const tB = typeof b.time === "number" ? b.time : new Date(b.time).getTime();
      return tA - tB;
    });
  }, [chartDataRaw, chartType]);

  // 분봉 차트 오른쪽 빈 공간: 장 마감까지 남은 봉 수
  const rightPadBars = useMemo(() => {
    if (chartType !== "minute") return 0;
    const now = new Date();
    if (isKR) {
      const kstH = (now.getUTCHours() + 9) % 24;
      const kstM = now.getUTCMinutes();
      const currentMin = kstH * 60 + kstM;
      const closeMin   = 15 * 60 + 30; // 15:30
      const remaining  = closeMin - currentMin;
      return remaining > 0 ? Math.ceil(remaining / minuteInterval) : 0;
    } else {
      // EDT(UTC-4) 기준, 동부 표준시(UTC-5)는 11월~3월
      const isDST = now.getMonth() >= 2 && now.getMonth() <= 10;
      const offset = isDST ? -4 : -5;
      const estH = ((now.getUTCHours() + offset) % 24 + 24) % 24;
      const estM = now.getUTCMinutes();
      const currentMin = estH * 60 + estM;
      const closeMin   = 16 * 60; // 16:00
      const remaining  = closeMin - currentMin;
      return remaining > 0 ? Math.ceil(remaining / minuteInterval) : 0;
    }
  }, [chartType, isKR, minuteInterval]);

  // 자동완성 (KR: 코드+이름+초성 / US: 티커+한국어이름+초성)
  const filteredStocks = useMemo(() => {
    if (!searchQuery.trim()) return [];
    const query = searchQuery.replace(/\s+/g, "").toLowerCase();
    const queryChosung = getChosung(query);
    const isChosungOnly = /^[ㄱ-ㅎ]+$/.test(query);

    if (isKR) {
      if (!allStocks) return [];
      const results: { code: string; name: string; score: number }[] = [];
      for (const [code, name] of Object.entries(allStocks as Record<string, string>)) {
        const nameSafe = name.replace(/\s+/g, "").toLowerCase();
        const nameChosung = getChosung(nameSafe);
        
        let score = 0;
        const matchChosung = isChosungOnly && nameChosung.includes(queryChosung);

        if (code === query) {
          score = 200;
        } else if (code.startsWith(query)) {
          score = 150;
        } else if (nameSafe === query) {
          score = 180;
        } else if (nameSafe.startsWith(query)) {
          score = 120;
        } else if (code.includes(query)) {
          score = 100;
        } else if (nameSafe.includes(query)) {
          score = 90;
        } else if (matchChosung) {
          if (nameChosung === queryChosung) score = 80;
          else if (nameChosung.startsWith(queryChosung)) score = 60;
          else score = 40;
        }

        if (score > 0) {
          results.push({ code, name, score });
        }
      }
      return results.sort((a, b) => b.score - a.score).slice(0, 10);
    } else {
      // US: ticker 또는 한국어 이름으로 검색
      if (!usAllStocks) return [];
      const results: { code: string; name: string; score: number }[] = [];
      for (const [ticker, name] of Object.entries(usAllStocks as Record<string, string>)) {
        const tickerLower = ticker.toLowerCase();
        const nameSafe = name.replace(/\s+/g, "").toLowerCase();
        const nameChosung = getChosung(nameSafe);
        
        let score = 0;
        const matchChosung = isChosungOnly && nameChosung.includes(queryChosung);

        if (tickerLower === query) {
          score = 200;
        } else if (tickerLower.startsWith(query)) {
          score = 150;
        } else if (nameSafe === query) {
          score = 180;
        } else if (nameSafe.startsWith(query)) {
          score = 120;
        } else if (tickerLower.includes(query)) {
          score = 100;
        } else if (nameSafe.includes(query)) {
          score = 90;
        } else if (matchChosung) {
          if (nameChosung === queryChosung) score = 80;
          else if (nameChosung.startsWith(queryChosung)) score = 60;
          else score = 40;
        }

        if (score > 0) {
          results.push({ code: ticker, name, score });
        }
      }
      return results.sort((a, b) => b.score - a.score).slice(0, 10);
    }
  }, [isKR, searchQuery, allStocks, usAllStocks]);

  const performSearch = (code: string, nameHint?: string) => {
    if (!code.trim()) return;
    const upper = code.toUpperCase();
    setSearchQuery("");
    setShowDropdown(false);
    setCurrentCode(upper);
    // 종목 AI 분석 결과 캐시 복원 (이전에 분석했던 종목이면 결과 즉시 표시)
    const _cachedAi = _loadAiCache(upper);
    if (_cachedAi) { setAiResult(_cachedAi.result); setAiMeta({ ts: _cachedAi.ts, price: _cachedAi.price }); setAiStatus("done"); }
    else { setAiStatus("idle"); setAiResult(null); setAiMeta(null); }
    // 최근 검색 저장
    let displayName = nameHint || upper;
    if (!nameHint) {
      if (isKR && allStocks) {
        const stocksMap = allStocks as Record<string, string>;
        if (stocksMap[upper]) {
          displayName = stocksMap[upper];
        } else {
          // 이름으로 검색했을 경우
          const entry = Object.entries(stocksMap).find(([c, n]) => n === upper);
          if (entry) displayName = entry[1];
        }
      } else if (!isKR && usAllStocks) {
        const foundName = (usAllStocks as Record<string, string>)[upper];
        if (foundName) displayName = foundName;
      }
    }
    const entry = { code: upper, name: displayName, market };
    setRecentSearches(prev => {
      const next = [entry, ...prev.filter(r => !(r.code === upper && r.market === market))].slice(0, 10);
      try { localStorage.setItem(RECENT_KEY, JSON.stringify(next)); } catch {}
      return next;
    });
  };

  const clearRecentSearches = () => {
    setRecentSearches([]);
    try { localStorage.removeItem(RECENT_KEY); } catch {}
  };

  useEffect(() => {
    const q = searchParams.get("q");
    const m = searchParams.get("market");
    if (m === "US" && market !== "US") setMarket("US");
    if (m === "KR" && market !== "KR") setMarket("KR");
    if (q) performSearch(q);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (filteredStocks.length > 0) {
      // 자동완성 최상단 항목 선택 (KR+US 공통)
      performSearch(filteredStocks[0].code);
    } else if (isKR && searchQuery.match(/^\d+$/)) {
      performSearch(searchQuery);
    } else if (!isKR && searchQuery.trim()) {
      performSearch(searchQuery.trim().toUpperCase());
    }
  };

  // ── 타점 보드 판정 ────────────────────────────────────────────────────────
  const bandPos = (() => {
    const hi = w52High || price || 1;
    const lo = w52Low || 1;
    if (hi <= lo) return 50;
    return Math.round(((price - lo) / (hi - lo)) * 100);
  })();

  const etBoard = (() => {
    const c = change;
    if (Math.abs(c) < 0.5) return { label: "⚪ 극단타 불가",      color: "#888",    desc: "변동 없음 — 거래비용 감안 시 손익 기대 불가" };
    if (c >= 5)             return { label: "🟢 극단타 적극 대응", color: "#00c853", desc: `강 모멘텀 ${c > 0 ? "+" : ""}${c.toFixed(2)}% — 눌림목 분봉 지지 확인 후 진입` };
    if (c >= 3)             return { label: "🟢 극단타 관심",      color: "#00c853", desc: `상승 ${c > 0 ? "+" : ""}${c.toFixed(2)}% — 직전 분봉 고점 돌파 시 추격` };
    if (c >= 1)             return { label: "🟡 극단타 관망",      color: "#ffd600", desc: `소폭 ${c > 0 ? "+" : ""}${c.toFixed(2)}% — 변동성 부족, 돌파 신호 대기` };
    if (c <= -5)            return { label: "🔵 반등 노림",        color: "#2b7cff", desc: `급락 ${c.toFixed(2)}% — 분봉 반등 캔들+거래량 폭발 확인 후` };
    if (c <= -1)            return { label: "🔴 극단타 자제",      color: "#ff4b4b", desc: `하락 ${c.toFixed(2)}% — 추세 꺾임, 섣부른 반매수 위험` };
    return                         { label: "🟡 극단타 관망",      color: "#ffd600", desc: `등락 ${c.toFixed(2)}% — 방향 미확정, 분봉 패턴 확인 필요` };
  })();

  const stBoard = (() => {
    const c = change;
    if (Math.abs(c) < 0.1) return { label: "⚪ 관망",           color: "#888",    desc: `등락 미미(${c.toFixed(2)}%) — 장 마감·거래 없음 상태 가능` };
    if (c >= 5)             return { label: "🟢 강력 단기 추천", color: "#00c853", desc: `강한 모멘텀 ${c > 0 ? "+" : ""}${c.toFixed(2)}% — 눌림목 진입 권장` };
    if (c >= 3)             return { label: "🟢 단기 추천",      color: "#00c853", desc: `상승세 ${c > 0 ? "+" : ""}${c.toFixed(2)}% — 손절: 당일 저점` };
    if (c >= 1)             return { label: "🟡 단기 관망",      color: "#ffd600", desc: `소폭 상승 ${c > 0 ? "+" : ""}${c.toFixed(2)}% — 3% 돌파 확인 후 진입` };
    if (c <= -5)            return { label: "🔵 반등 관찰",      color: "#2b7cff", desc: `급락 ${c.toFixed(2)}% — 지지선·거래량 확인 필수` };
    if (c <= -2)            return { label: "🔴 단기 비추천",    color: "#ff4b4b", desc: `하락세 ${c.toFixed(2)}% — 추가 하락 가능` };
    return                         { label: "🔴 단기 비추천",    color: "#ff4b4b", desc: `등락 ${c.toFixed(2)}% — 수수료 감안 시 실익 없음` };
  })();

  const mtBoard = (() => {
    if (bandPos <= 30) return { label: "🟢 중기 매수 관심", color: "#00c853", desc: `52주 저점 근처(${bandPos}%) — 중기 분할 매수 고려` };
    if (bandPos >= 80) return { label: "🔴 중기 고평가",   color: "#ff4b4b", desc: `52주 고점 근처(${bandPos}%) — 신규 진입 부담` };
    if (pbr < 1)       return { label: "🟢 중기 저평가",   color: "#00c853", desc: `PBR ${pbr.toFixed(2)} (자산가치 이하) — 중기 가치투자 유리` };
    return                    { label: "🟡 중기 중립",     color: "#ffd600", desc: `52주 중간대(${bandPos}%) — 방향성 확인 후 대응` };
  })();

  const ltBoard = (() => {
    if (per <= 0)  return { label: "🟡 장기 중립",   color: "#ffd600", desc: `PER 음수(적자) — 수익성 개선 추이 확인 필요` };
    if (per < 10)  return { label: "🟢 장기 저평가", color: "#00c853", desc: `PER ${per.toFixed(1)} — 업종 대비 저평가, 장기 보유 유리` };
    if (per < 20)  return { label: "🟢 장기 적정",   color: "#00c853", desc: `PER ${per.toFixed(1)} — 적정 밸류에이션` };
    if (per < 40)  return { label: "🟡 장기 중립",   color: "#ffd600", desc: `PER ${per.toFixed(1)} — 성장 프리미엄 반영, 모니터링 필요` };
    return                { label: "🔴 장기 고평가", color: "#ff4b4b", desc: `PER ${per.toFixed(1)} — 고평가 구간, 장기 진입 신중` };
  })();

  // 1. AI 실시간 쉐도우 섹터 & 팩트 진단 연동
  const runShadowSectorAnalysis = async (ticker: string, name: string, mkt: string) => {
    setShadowStatus("loading");
    setShadowResult(null);
    setShadowMsg("🔬 실시간 공시 및 밸류체인 추적 중...");
    try {
      await connectSSE<any>(
        "/api/ai/shadow-sector",
        (evt) => {
          if (evt.status === "running") {
            setShadowMsg(evt.message ?? "분석 중...");
          } else if (evt.status === "done" && evt.result) {
            setShadowResult(evt.result);
            setShadowStatus("done");
          } else if (evt.status === "error") {
            setShadowMsg(evt.message ?? "오류 발생");
            setShadowStatus("error");
          }
        },
        {
          method: "POST",
          body: {
            ticker: mkt === "KR" ? ticker.padStart(6, "0") : ticker,
            name: name || ticker,
            market: mkt === "KR" ? "국내" : "미국",
            force_update: false,
          },
        }
      );
    } catch (err: any) {
      setShadowMsg(`❌ 오류: ${err.message}`);
      setShadowStatus("error");
    }
  };

  // 2. AI 시간외 긴급 진단 & 익일 갭 예측 RAG 분석 연동
  const runOvernightGapAnalysis = async (ticker: string, name: string, mkt: string) => {
    setGapStatus("loading");
    setGapResult(null);
    setGapMsg("🌙 시간외 돌발 공시 및 최신 뉴스망 탐색 중...");
    try {
      await connectSSE<any>(
        "/api/ai/overnight-gap",
        (evt) => {
          if (evt.status === "running") {
            setGapMsg(evt.message ?? "분석 중...");
          } else if (evt.status === "done" && evt.result) {
            setGapResult(evt.result);
            setGapStatus("done");
          } else if (evt.status === "error") {
            setGapMsg(evt.message ?? "오류 발생");
            setGapStatus("error");
          }
        },
        {
          method: "POST",
          body: {
            ticker: mkt === "KR" ? ticker.padStart(6, "0") : ticker,
            name: name || ticker,
            market: mkt === "KR" ? "국내" : "미국",
          },
        }
      );
    } catch (err: any) {
      setGapMsg(`❌ 오류: ${err.message}`);
      setGapStatus("error");
    }
  };

  // 3. AI 차트 박스권 & 세력 수급 패턴 분석 RAG 분석 연동
  const runBoxAnalysis = async () => {
    setBoxStatus("loading");
    setBoxResult(null);
    setBoxMsg("📦 차트 데이터 분석 및 세력 수급 추적 중...");
    try {
      await connectSSE<any>(
        "/api/ai/box-pattern",
        (evt) => {
          if (evt.status === "running") {
            setBoxMsg(evt.message ?? "분석 중...");
          } else if (evt.status === "done" && evt.result) {
            setBoxResult(evt.result);
            setBoxStatus("done");
          } else if (evt.status === "error") {
            setBoxMsg(evt.message ?? "오류 발생");
            setBoxStatus("error");
          }
        },
        {
          method: "POST",
          body: {
            ticker: isKR ? currentCode.padStart(6, "0") : currentCode,
            name: stockName || currentCode,
            price_data: stockData || {},
            market: isKR ? "국내" : "미국",
          },
        }
      );
    } catch (err: any) {
      setBoxMsg(`❌ 오류: ${err.message}`);
      setBoxStatus("error");
    }
  };

  // 종목 변경 시 RAG 상태 초기화 (자동 실행 X — 버튼 클릭 시에만 실행)
  useEffect(() => {
    setShadowStatus("idle");
    setShadowResult(null);
    setGapStatus("idle");
    setGapResult(null);
    setBoxStatus("idle");
    setBoxResult(null);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentCode]);

  // AI 분석 (KR 전용)
  const runAiAnalysis = async () => {
    setAiStatus("loading");
    setAiResult(null);
    setAiMeta(null);
    setAiMsg("분석을 준비중입니다...");
    try {
      const payload = {
        code: currentCode,
        name: stockName,
        price_data: stockData || {},
        investor_data: [],
      };
      const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
      const res = await fetch(`${BASE}/api/ai/kr-stock-report`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.body) throw new Error("No body");
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let gotTerminal = false;
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() ?? "";
        for (const part of parts) {
          const line = part.trim();
          if (!line.startsWith("data:")) continue;
          try {
            const parsed = JSON.parse(line.slice(5).trim());
            if (parsed.status === "running") setAiMsg(parsed.message ?? aiMsg);
            else if (parsed.status === "done") { gotTerminal = true; setAiResult(parsed.result); setAiMeta({ ts: Date.now(), price }); setAiStatus("done"); _saveAiCache(currentCode, parsed.result, price); notifyDone(`stock-${currentCode}`, `${stockName || currentCode} AI 분석`, `/search?q=${currentCode}&market=KR`); }
            else if (parsed.status === "error") { gotTerminal = true; setAiMsg(`❌ ${parsed.message}`); setAiStatus("error"); }
          } catch {}
        }
      }
      // 스트림이 done/error 없이 종료된 경우 로딩 상태가 영구히 고착되는 것 방지
      if (!gotTerminal) { setAiMsg("❌ 분석이 완료되지 못했습니다. 다시 시도해주세요."); setAiStatus("error"); }
    } catch (err: any) {
      setAiMsg(`❌ 오류: ${err.message}`);
      setAiStatus("error");
    }
  };

  // 탭 목록 (수급은 KR 전용)
  const ANALYSIS_TABS = isKR ? ["시세", "수급", "박스권", "AI 분석"] : ["시세", "박스권", "AI 분석"];

  // AI 분석 (US)
  const runUsAiAnalysis = async () => {
    setAiStatus("loading");
    setAiResult(null);
    setAiMeta(null);
    setAiMsg("US 종목 분석 중...");
    try {
      const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
      const res = await fetch(`${BASE}/api/ai/stock-report`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticker: currentCode, current_price: price, change_pct: change }),
      });
      if (!res.body) throw new Error("No body");
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let gotTerminal = false;
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() ?? "";
        for (const part of parts) {
          const line = part.trim();
          if (!line.startsWith("data:")) continue;
          try {
            const parsed = JSON.parse(line.slice(5).trim());
            if (parsed.status === "running") setAiMsg(parsed.message ?? aiMsg);
            else if (parsed.status === "done") { gotTerminal = true; setAiResult(parsed.result); setAiMeta({ ts: Date.now(), price }); setAiStatus("done"); _saveAiCache(currentCode, parsed.result, price); notifyDone(`stock-${currentCode}`, `${stockName || currentCode} AI 분석`, `/search?q=${currentCode}&market=US`); }
            else if (parsed.status === "error") { gotTerminal = true; setAiMsg(`❌ ${parsed.message}`); setAiStatus("error"); }
          } catch {}
        }
      }
      // 스트림이 done/error 없이 종료된 경우 로딩 상태가 영구히 고착되는 것 방지
      if (!gotTerminal) { setAiMsg("❌ 분석이 완료되지 못했습니다. 다시 시도해주세요."); setAiStatus("error"); }
    } catch (err: any) {
      setAiMsg(`❌ 오류: ${err.message}`);
      setAiStatus("error");
    }
  };

  return (
    <div style={{ width: "100%", margin: "0 auto" }}>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "2rem" }}>

        {/* ── 좌측: 차트 영역 ─────────────────────────────────────────── */}
        <div className="stockcy-card" style={{ display: "flex", flexDirection: "column", padding: 0, minHeight: "700px" }}>
          <div style={{ padding: "1.5rem 1.5rem 1rem", borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
            <div style={{ display: "flex", alignItems: "baseline", gap: "8px", marginBottom: "0.25rem", flexWrap: "wrap" }}>
              <h2 style={{ fontSize: "1.4rem", fontWeight: 800, margin: 0 }}>
                {stockName || (isLoading ? "로딩중..." : "종목명")}
              </h2>
              {/* 투자경고 배지 */}
              {warningBadges.map((b, i) => (
                <span key={i} style={{
                  fontSize: "0.68rem", fontWeight: 800, padding: "2px 6px",
                  borderRadius: "4px", background: b.bg, color: b.color,
                  alignSelf: "center", flexShrink: 0,
                }}>
                  {b.label}
                </span>
              ))}
              <span style={{ color: "var(--color-muted)", fontSize: "0.95rem" }}>({currentCode})</span>
              <div style={{ marginLeft: "0.5rem", fontSize: "1.4rem", fontWeight: 800 }}>
                {currSymbol}{price.toLocaleString()}
              </div>
              <div style={{ fontSize: "0.95rem", fontWeight: 700, color }}>
                {changeStr} {isKR ? `${changeVal.toLocaleString()}원 ` : ""}({change > 0 ? "+" : ""}{change.toFixed(2)}%)
              </div>
            </div>

            {/* 섹터 정보 */}
            {sectorInfo && (
              <div style={{ display: "flex", alignItems: "center", gap: "6px", marginTop: "4px", marginBottom: "4px" }}>
                <span
                  onClick={() => router.push(`/sectors?tab=all&market=${isKR ? "KR" : "US"}&sector=${encodeURIComponent(sectorInfo.sector)}`)}
                  title={`'${sectorInfo.sector}' 섹터 지도 보기`}
                  style={{
                    fontSize: "0.75rem", fontWeight: 700, padding: "2px 8px",
                    background: "rgba(99,102,241,0.15)", border: "1px solid rgba(99,102,241,0.4)",
                    borderRadius: "4px", color: "#818cf8", cursor: "pointer",
                  }}
                >
                  {sectorInfo.sector} ↗
                </span>
                <span style={{ fontSize: "0.72rem", color: "var(--color-muted)" }}>›</span>
                <span style={{
                  fontSize: "0.75rem", fontWeight: 600, padding: "2px 8px",
                  background: "rgba(99,102,241,0.08)", border: "1px solid rgba(99,102,241,0.2)",
                  borderRadius: "4px", color: "#a5b4fc",
                }}>
                  {sectorInfo.subSector}
                </span>
              </div>
            )}

            {/* US: 프리/애프터마켓 표시 */}
            {!isKR && usStockData && (usStockData.pre_price > 0 || usStockData.post_price > 0) && (
              <div style={{ fontSize: "0.8rem", color: "var(--color-muted)", marginTop: "4px" }}>
                {usStockData.pre_price > 0 && (
                  <span style={{ marginRight: "12px" }}>
                    Pre: ${usStockData.pre_price}
                    <span style={{ color: usStockData.pre_pct >= 0 ? "var(--color-danger)" : "var(--color-primary)", marginLeft: "4px" }}>
                      {usStockData.pre_pct >= 0 ? "+" : ""}{usStockData.pre_pct}%
                    </span>
                  </span>
                )}
                {usStockData.post_price > 0 && (
                  <span>
                    After: ${usStockData.post_price}
                    <span style={{ color: usStockData.post_pct >= 0 ? "var(--color-danger)" : "var(--color-primary)", marginLeft: "4px" }}>
                      {usStockData.post_pct >= 0 ? "+" : ""}{usStockData.post_pct}%
                    </span>
                  </span>
                )}
              </div>
            )}

            <div style={{ marginTop: "1rem", display: "flex", gap: "10px", flexWrap: "wrap", alignItems: "center" }}>
              <select
                className="stockcy-input bg-zinc-800 text-white border border-white/10 rounded px-2 py-1 focus:outline-none focus:border-indigo-500 transition-colors"
                value={chartType}
                onChange={(e) => setChartType(e.target.value)}
                style={{ width: "100px" }}
              >
                <option value="minute" className="bg-zinc-800 text-white">분봉</option>
                <option value="daily" className="bg-zinc-800 text-white">일봉</option>
                <option value="weekly" className="bg-zinc-800 text-white">주봉</option>
                <option value="monthly" className="bg-zinc-800 text-white">월봉</option>
              </select>

              {chartType === "minute" && (
                <select
                  className="stockcy-input bg-zinc-800 text-white border border-white/10 rounded px-2 py-1 focus:outline-none focus:border-indigo-500 transition-colors"
                  value={minuteInterval}
                  onChange={(e) => setMinuteInterval(Number(e.target.value))}
                  style={{ width: "80px" }}
                >
                  <option value={1} className="bg-zinc-800 text-white">1분</option>
                  <option value={5} className="bg-zinc-800 text-white">5분</option>
                  <option value={15} className="bg-zinc-800 text-white">15분</option>
                  <option value={30} className="bg-zinc-800 text-white">30분</option>
                  <option value={60} className="bg-zinc-800 text-white">60분</option>
                </select>
              )}

              {/* 기간 버튼 (일봉만): 3M·6M은 토스 소스, 1Y·MAX는 KIS/yfinance */}
              {chartType !== "minute" && (PERIOD_OPTIONS[chartType]?.length ?? 0) > 1 &&
                PERIOD_OPTIONS[chartType].map((opt) => (
                  <button
                    key={opt}
                    onClick={() => setChartPeriod(opt)}
                    className="rounded px-3 py-1 text-sm transition-colors"
                    style={{
                      fontWeight: 700,
                      border: `1px solid ${chartPeriod === opt ? "var(--color-accent)" : "rgba(255,255,255,0.12)"}`,
                      background: chartPeriod === opt ? "rgba(99,102,241,0.18)" : "transparent",
                      color: chartPeriod === opt ? "#fff" : "rgba(255,255,255,0.6)",
                      cursor: "pointer",
                    }}
                  >
                    {opt}
                  </button>
                ))}
            </div>

            <div style={{ marginTop: "1.5rem" }}>
              <div style={{ display: "flex", gap: "1.5rem", borderBottom: "1px solid rgba(255,255,255,0.05)", paddingBottom: "0.5rem" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "6px", color: "var(--color-danger)", fontWeight: 700, cursor: "pointer", position: "relative" }}>
                  <span>📊 차트</span>
                  <div style={{ position: "absolute", bottom: "-0.5rem", left: 0, right: 0, height: "2px", background: "var(--color-danger)" }} />
                </div>
              </div>
              <div style={{ marginTop: "1rem", padding: "8px 12px", background: "rgba(255,255,255,0.02)", borderRadius: "4px", fontSize: "0.85rem", color: "rgba(255,255,255,0.6)", display: "flex", alignItems: "center", gap: "8px" }}>
                <span>ℹ️ 이동평균선 안내:</span>
                <span style={{ color: "#FACC15" }}>🟡5일(단기)</span> |
                <span style={{ color: "#EC4899" }}>💖20일(생명)</span> |
                <span style={{ color: "#22C55E" }}>🟢60일(수급)</span> |
                <span style={{ color: "#3B82F6" }}>🔵120일(경기)</span>
              </div>
            </div>
          </div>

          <div style={{ flex: 1, display: "flex", alignItems: "stretch", justifyContent: "stretch", minHeight: "500px", padding: "0" }}>
            {chartData.length > 0 ? (
              <Chart data={chartData} rightPadBars={rightPadBars} showSessions={!isKR && chartType === "minute"}
                initialVisibleBars={chartType === "minute" ? Math.ceil((390 / minuteInterval) * 1.5) : 0} />
            ) : (
              <div style={{ width: "100%", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--color-muted)" }}>
                <Loader2 className="animate-spin" size={32} />
              </div>
            )}
          </div>

          {/* 토스 호가창·체결·상하한가·장운영 (현재 종목) */}
          {currentCode && <OrderbookPanel code={currentCode} market={market} />}
        </div>

        {/* ── 우측: 검색 + 분석 영역 ───────────────────────────────────── */}
        <div style={{ display: "flex", flexDirection: "column", gap: "1.2rem" }}>

          {/* 검색창 */}
          <div style={{ position: "relative" }}>
            <form onSubmit={handleSearch} style={{ position: "relative" }}>
              <div style={{ position: "absolute", left: "12px", top: "50%", transform: "translateY(-50%)", color: "var(--color-muted)" }}>
                <Search size={18} />
              </div>
              <input
                type="text"
                placeholder={isKR ? "종목 검색 (예: 삼성전자, ㅅㅅㅈㅈ, 005930)" : "Ticker 검색 (예: AAPL, NVDA, TSLA)"}
                value={searchQuery}
                onFocus={() => setShowDropdown(true)}
                onBlur={() => setTimeout(() => setShowDropdown(false), 200)}
                onChange={(e) => { setSearchQuery(e.target.value); setShowDropdown(true); }}
                className="stockcy-input"
                style={{ paddingLeft: "36px", fontSize: "1rem", width: "100%", background: "var(--color-surface)", border: "1px solid var(--color-border)", padding: "12px 36px" }}
              />
            </form>

            {/* 최근 검색 종목 */}
            {recentSearches.filter(r => r.market === market).length > 0 && !searchQuery && (
              <div style={{ display: "flex", alignItems: "center", gap: "6px", marginTop: "8px", flexWrap: "wrap" }}>
                <span style={{ fontSize: "0.72rem", color: "var(--color-muted)", fontWeight: 700, flexShrink: 0 }}>최근 검색:</span>
                {recentSearches.filter(r => r.market === market).map((r, i) => {
                  let display = r.name && r.name !== r.code ? r.name : r.code;
                  if (display === r.code) {
                    if (market === "KR" && allStocks) {
                      const m = allStocks as Record<string, string>;
                      if (m[r.code]) display = m[r.code];
                    } else if (market === "US" && usAllStocks) {
                      const m = usAllStocks as Record<string, string>;
                      if (m[r.code]) display = m[r.code];
                    }
                  }
                  return (
                    <div
                      key={i}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "4px",
                        background: "rgba(255,255,255,0.08)",
                        border: "1px solid rgba(255,255,255,0.15)",
                        padding: "4px 8px 4px 10px",
                        borderRadius: "12px",
                        fontSize: "0.75rem",
                        color: "var(--color-text)",
                        fontWeight: 600,
                        transition: "all 0.2s",
                      }}
                    >
                      <span
                        onClick={() => performSearch(r.code, display)}
                        style={{ cursor: "pointer" }}
                        onMouseOver={(e) => e.currentTarget.style.color = "var(--color-accent)"}
                        onMouseOut={(e) => e.currentTarget.style.color = "var(--color-text)"}
                      >
                        {display}
                      </span>
                      <button
                        onClick={(e) => removeRecentSearch(r.code, r.market, e)}
                        style={{
                          background: "transparent",
                          border: "none",
                          cursor: "pointer",
                          color: "var(--color-muted)",
                          padding: "2px",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          borderRadius: "50%",
                        }}
                        onMouseOver={(e) => e.currentTarget.style.color = "var(--color-danger)"}
                        onMouseOut={(e) => e.currentTarget.style.color = "var(--color-muted)"}
                      >
                        <X size={10} />
                      </button>
                    </div>
                  );
                })}
                <button
                  onClick={clearRecentSearches}
                  style={{
                    background: "transparent", border: "none", padding: "0",
                    fontSize: "0.7rem", color: "var(--color-muted)",
                    cursor: "pointer", marginLeft: "6px",
                  }}
                  title="최근 검색 전체 삭제"
                >
                  전체삭제
                </button>
              </div>
            )}

            {/* 자동완성 드롭다운 (KR + US 공통) */}
            {showDropdown && searchQuery && filteredStocks.length > 0 && (
              <div style={{ position: "absolute", top: "100%", left: 0, right: 0, zIndex: 9999, backgroundColor: "#0F172A", border: "1px solid #334155", borderRadius: "8px", marginTop: "4px", overflow: "hidden", boxShadow: "0 12px 32px rgba(0,0,0,0.8)" }}>
                {filteredStocks.map((item, idx) => (
                  <div
                    key={item.code}
                    onClick={() => performSearch(item.code, item.name)}
                    style={{ padding: "10px 16px", cursor: "pointer", borderBottom: idx < filteredStocks.length - 1 ? "1px solid rgba(255,255,255,0.05)" : "none", display: "flex", justifyContent: "space-between" }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(255,255,255,0.05)")}
                    onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
                  >
                    <span style={{ fontWeight: 600 }}>{item.name}</span>
                    <span style={{ color: "var(--color-muted)", fontSize: "0.85rem" }}>{item.code}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* 탭 */}
          <div style={{ display: "flex", gap: "10px" }}>
            {ANALYSIS_TABS.map(tab => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                style={{ flex: 1, padding: "8px", borderRadius: "6px", fontWeight: 700, fontSize: "0.85rem", border: "1px solid", borderColor: activeTab === tab ? "var(--color-accent)" : "var(--color-border)", background: activeTab === tab ? "rgba(255,255,255,0.05)" : "var(--color-surface)", color: "var(--color-text)", cursor: "pointer", transition: "0.2s" }}
              >
                {tab === "시세" ? "📊 시세" : tab === "수급" ? "🔥 수급" : tab === "박스권" ? "📈 박스권" : "🤖 AI 분석"}
              </button>
            ))}
          </div>

          {/* ── 시세 탭 ─────────────────────────────────────────────────── */}
          {activeTab === "시세" && (
            <div className="stockcy-card" style={{ flex: 1, display: "flex", flexDirection: "column", gap: "1.2rem", padding: "1.5rem" }}>
              <div style={{ display: "flex", gap: "8px" }}>
                <FavButton ticker={currentCode} name={stockName} market={isKR ? "국내" : "미국"} />
                <PortfolioAddButton
                  ticker={currentCode}
                  name={stockName}
                  market={isKR ? "국내" : "미국"}
                  currentPrice={price}
                />
              </div>

              <div>
                <div style={{ display: "flex", alignItems: "center", gap: "6px", marginBottom: "0.25rem" }}>
                  <h3 style={{ fontSize: "0.95rem", fontWeight: 700, margin: 0 }}>{stockName || "..."}</h3>
                  {!isKR && stockData?.sector && (
                    <span style={{ fontSize: "0.75rem", background: "rgba(255,255,255,0.1)", padding: "2px 4px", borderRadius: "2px" }}>{stockData.sector}</span>
                  )}
                </div>
                <div style={{ fontSize: "1.4rem", fontWeight: 800 }}>
                  {currSymbol}{price.toLocaleString()}
                  <span style={{ fontSize: "0.9rem", color, marginLeft: "6px", fontWeight: 700 }}>
                    {changeStr} {isKR ? `${changeVal.toLocaleString()}원 ` : ""}({change > 0 ? "+" : ""}{change.toFixed(2)}%)
                  </span>
                </div>
              </div>

              {/* 스탯 테이블 */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "0.5rem", rowGap: "0.75rem", fontSize: "0.85rem" }}>
                {isKR ? (
                  <>
                    <div><div style={{ color: "var(--color-muted)", fontSize: "0.75rem" }}>거래량</div><div style={{ fontWeight: 700 }}>{(stockData?.volume || stockData?.거래량 || 0).toLocaleString()}주</div></div>
                    <div><div style={{ color: "var(--color-muted)", fontSize: "0.75rem" }}>거래대금</div><div style={{ fontWeight: 700 }}>₩{(((stockData?.amount || stockData?.거래대금 || 0)) / 100000000).toLocaleString(undefined, { maximumFractionDigits: 0 })}억</div></div>
                    <div><div style={{ color: "var(--color-muted)", fontSize: "0.75rem" }}>PER</div><div style={{ fontWeight: 700 }}>{stockData?.per || stockData?.PER || "N/A"}</div></div>
                    <div><div style={{ color: "var(--color-muted)", fontSize: "0.75rem" }}>시가</div><div style={{ fontWeight: 700 }}>₩{(stockData?.open || stockData?.시가 || 0).toLocaleString()}</div></div>
                    <div><div style={{ color: "var(--color-muted)", fontSize: "0.75rem" }}>고가</div><div style={{ fontWeight: 700 }}>₩{(stockData?.high || stockData?.고가 || 0).toLocaleString()}</div></div>
                    <div><div style={{ color: "var(--color-muted)", fontSize: "0.75rem" }}>저가</div><div style={{ fontWeight: 700 }}>₩{(stockData?.low  || stockData?.저가 || 0).toLocaleString()}</div></div>
                    <div><div style={{ color: "var(--color-muted)", fontSize: "0.75rem" }}>PBR</div><div style={{ fontWeight: 700 }}>{stockData?.pbr || stockData?.PBR || "N/A"}</div></div>
                    <div><div style={{ color: "var(--color-muted)", fontSize: "0.75rem" }}>52주 최고</div><div style={{ fontWeight: 700, color: "var(--color-danger)" }}>₩{(stockData?.w52_high || stockData?.["52주최고가"] || 0).toLocaleString()}</div></div>
                    <div><div style={{ color: "var(--color-muted)", fontSize: "0.75rem" }}>52주 최저</div><div style={{ fontWeight: 700, color: "var(--color-primary)" }}>₩{(stockData?.w52_low  || stockData?.["52주최저가"] || 0).toLocaleString()}</div></div>
                    <div><div style={{ color: "var(--color-muted)", fontSize: "0.75rem" }}>EPS</div><div style={{ fontWeight: 700 }}>{stockData?.eps ? `₩${Number(stockData.eps).toLocaleString()}` : "N/A"}</div></div>
                    <div><div style={{ color: "var(--color-muted)", fontSize: "0.75rem" }}>배당수익률</div><div style={{ fontWeight: 700 }}>{stockData?.dividend_yield != null && stockData.dividend_yield > 0 ? `${stockData.dividend_yield}%` : "N/A"}</div></div>
                    <div><div style={{ color: "var(--color-muted)", fontSize: "0.75rem" }}>시가총액</div><div style={{ fontWeight: 700 }}>{stockData?.market_cap || "N/A"}</div></div>
                  </>
                ) : (
                  <>
                    <div><div style={{ color: "var(--color-muted)", fontSize: "0.75rem" }}>거래량</div><div style={{ fontWeight: 700 }}>{(stockData?.volume || 0).toLocaleString()}</div></div>
                    <div><div style={{ color: "var(--color-muted)", fontSize: "0.75rem" }}>시가총액</div><div style={{ fontWeight: 700 }}>{stockData?.market_cap || "-"}</div></div>
                    <div><div style={{ color: "var(--color-muted)", fontSize: "0.75rem" }}>PER</div><div style={{ fontWeight: 700 }}>{stockData?.per || "N/A"}</div></div>
                    <div><div style={{ color: "var(--color-muted)", fontSize: "0.75rem" }}>시가(Open)</div><div style={{ fontWeight: 700 }}>${(stockData?.open || 0).toFixed(2)}</div></div>
                    <div><div style={{ color: "var(--color-muted)", fontSize: "0.75rem" }}>고가(High)</div><div style={{ fontWeight: 700 }}>${(stockData?.high || 0).toFixed(2)}</div></div>
                    <div><div style={{ color: "var(--color-muted)", fontSize: "0.75rem" }}>저가(Low)</div><div style={{ fontWeight: 700 }}>${(stockData?.low || 0).toFixed(2)}</div></div>
                    <div><div style={{ color: "var(--color-muted)", fontSize: "0.75rem" }}>PBR</div><div style={{ fontWeight: 700 }}>{stockData?.pbr || "N/A"}</div></div>
                    <div><div style={{ color: "var(--color-muted)", fontSize: "0.75rem" }}>52주 최고</div><div style={{ fontWeight: 700, color: "var(--color-danger)" }}>${(stockData?.w52_high || 0).toFixed(2)}</div></div>
                    <div><div style={{ color: "var(--color-muted)", fontSize: "0.75rem" }}>베타</div><div style={{ fontWeight: 700 }}>{stockData?.beta || "N/A"}</div></div>
                  </>
                )}
              </div>

              {/* 52주 가격 바 */}
              <div style={{ marginTop: "0.5rem" }}>
                <div style={{ fontSize: "0.75rem", color: "var(--color-muted)", marginBottom: "4px" }}>52주 가격 위치</div>
                <div style={{ position: "relative", height: "4px", background: "rgba(255,255,255,0.1)", borderRadius: "2px", margin: "0.75rem 0" }}>
                  <div style={{ position: "absolute", left: "0", top: 0, height: "100%", width: `${bandPos}%`, background: "var(--color-danger)", borderRadius: "2px" }}></div>
                  <div style={{ position: "absolute", left: `${bandPos}%`, top: "-8px", fontSize: "0.75rem", color: "var(--color-danger)", fontWeight: 700 }}>{bandPos}%</div>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.75rem", color: "var(--color-muted)" }}>
                  <span>최저 {currSymbol}{isKR ? (stockData?.["52주최저가"]?.toLocaleString() || 0) : (stockData?.w52_low?.toFixed(2) || 0)}</span>
                  <span>최고 {currSymbol}{isKR ? (stockData?.["52주최고가"]?.toLocaleString() || price) : (stockData?.w52_high?.toFixed(2) || 0)}</span>
                </div>
              </div>

              <button
                onClick={() => { setAlertModalOpen(true); setAlertMsg(null); setTargetPrice(String(price)); }}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: "8px",
                  color: "#ffd600",
                  fontSize: "0.85rem",
                  fontWeight: 700,
                  cursor: "pointer",
                  background: "rgba(253, 224, 71, 0.08)",
                  border: "1px solid rgba(253, 224, 71, 0.2)",
                  padding: "8px 16px",
                  borderRadius: "8px",
                  width: "100%",
                  transition: "all 0.2s ease-in-out",
                  marginTop: "0.5rem",
                  marginBottom: "0.5rem",
                }}
                onMouseOver={(e) => {
                  e.currentTarget.style.background = "rgba(253, 224, 71, 0.15)";
                  e.currentTarget.style.borderColor = "rgba(253, 224, 71, 0.4)";
                }}
                onMouseOut={(e) => {
                  e.currentTarget.style.background = "rgba(253, 224, 71, 0.08)";
                  e.currentTarget.style.borderColor = "rgba(253, 224, 71, 0.2)";
                }}
              >
                <Bell size={14} /> 실시간 가격 알림 설정
              </button>

              {/* 타점 보드 */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: "6px", marginTop: "auto" }}>
                {[
                  { title: "극단타", board: etBoard },
                  { title: "단기",   board: stBoard },
                  { title: "중기",   board: mtBoard },
                  { title: "장기",   board: ltBoard },
                ].map(({ title, board }) => (
                  <div key={title} style={{ background: "rgba(255,255,255,0.03)", border: `1px solid ${board.color}`, borderRadius: "6px", padding: "8px" }}>
                    <div style={{ fontSize: "0.75rem", color: "var(--color-muted)", marginBottom: "2px" }}>{title}</div>
                    <div style={{ fontWeight: 700, fontSize: "0.78rem", color: board.color, marginBottom: "4px" }}>{board.label}</div>
                    <div style={{ fontSize: "0.68rem", color: "var(--color-subtle)", lineHeight: 1.3 }}>{board.desc}</div>
                  </div>
                ))}
              </div>

              {/* ── AI RAG 분석 섹션 (온디맨드) ───────────────────────────── */}
              <div style={{ borderTop: "1px solid var(--color-border)", paddingTop: "1rem", display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                <div style={{ fontSize: "0.78rem", color: "var(--color-muted)", fontWeight: 600, letterSpacing: "0.05em", textTransform: "uppercase" }}>
                  🤖 AI RAG 실시간 분석 <span style={{ fontSize: "0.7rem", opacity: 0.6 }}>(클릭 시 유료 API 호출)</span>
                </div>

                {/* ─ 쉐도우 섹터 패널 ─ */}
                <div style={{ border: "1px solid var(--color-border)", borderRadius: "10px", overflow: "hidden" }}>
                  {/* idle: 버튼 */}
                  {shadowStatus === "idle" && (
                    <button
                      onClick={() => runShadowSectorAnalysis(currentCode, stockName || currentCode, isKR ? "KR" : "US")}
                      disabled={!currentCode}
                      style={{
                        width: "100%", padding: "12px 16px", display: "flex", alignItems: "center", gap: "10px",
                        background: "rgba(245, 158, 11, 0.04)", border: "none", cursor: currentCode ? "pointer" : "not-allowed",
                        color: "var(--color-text)", textAlign: "left",
                        transition: "background 0.2s",
                      }}
                      onMouseEnter={e => (e.currentTarget.style.background = "rgba(245, 158, 11, 0.1)")}
                      onMouseLeave={e => (e.currentTarget.style.background = "rgba(245, 158, 11, 0.04)")}
                    >
                      <span style={{ fontSize: "1.1rem" }}>🔬</span>
                      <div style={{ flex: 1 }}>
                        <div style={{ fontSize: "0.88rem", fontWeight: 700, color: "#fbbf24" }}>AI 실시간 쉐도우 섹터 &amp; 팩트 진단</div>
                        <div style={{ fontSize: "0.75rem", color: "var(--color-muted)", marginTop: "2px" }}>공시·밸류체인·섹터 연동 종목 영향 분석</div>
                      </div>
                      <span style={{ fontSize: "0.75rem", padding: "3px 8px", borderRadius: "6px", background: "rgba(245,158,11,0.15)", color: "#fbbf24", fontWeight: 700 }}>분석 시작 →</span>
                    </button>
                  )}
                  {/* loading */}
                  {shadowStatus === "loading" && (
                    <div style={{ padding: "14px 16px", display: "flex", alignItems: "center", gap: "10px" }}>
                      <Loader2 className="animate-spin" size={14} color="#fbbf24" />
                      <span style={{ fontSize: "0.85rem", color: "var(--color-muted)" }}>{shadowMsg}</span>
                    </div>
                  )}
                  {/* error */}
                  {shadowStatus === "error" && (
                    <div style={{ padding: "12px 16px", display: "flex", alignItems: "center", justifyContent: "space-between", gap: "8px" }}>
                      <span style={{ fontSize: "0.82rem", color: "#f87171" }}>{shadowMsg}</span>
                      <button onClick={() => runShadowSectorAnalysis(currentCode, stockName || currentCode, isKR ? "KR" : "US")} style={{ fontSize: "0.75rem", padding: "3px 8px", borderRadius: "6px", background: "rgba(239,68,68,0.15)", color: "#f87171", border: "1px solid rgba(239,68,68,0.3)", cursor: "pointer" }}>재시도</button>
                    </div>
                  )}
                  {/* done */}
                  {shadowStatus === "done" && shadowResult && (
                    <div style={{ padding: "14px 16px", display: "flex", flexDirection: "column", gap: "10px" }}>
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "8px" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                          <span style={{ fontSize: "1rem" }}>🔬</span>
                          <div>
                            <div style={{ fontSize: "0.88rem", fontWeight: 800, color: shadowResult.credibility === "상" ? "#fbbf24" : "#f87171" }}>AI 쉐도우 섹터 &amp; 팩트 진단</div>
                            {shadowResult.shadow_sector && (
                              <div style={{ fontSize: "0.75rem", color: "var(--color-muted)", marginTop: "2px" }}>{shadowResult.shadow_sector}</div>
                            )}
                          </div>
                        </div>
                        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                          <span style={{ fontSize: "0.72rem", fontWeight: 800, padding: "2px 8px", borderRadius: "12px", background: shadowResult.credibility === "상" ? "rgba(245,158,11,0.15)" : "rgba(239,68,68,0.15)", color: shadowResult.credibility === "상" ? "#fbbf24" : "#f87171", border: `1px solid ${shadowResult.credibility === "상" ? "rgba(245,158,11,0.3)" : "rgba(239,68,68,0.3)"}` }}>신뢰도: {shadowResult.credibility || "중립"}</span>
                          <button onClick={() => { setShadowStatus("idle"); setShadowResult(null); }} style={{ fontSize: "0.72rem", padding: "2px 6px", borderRadius: "6px", background: "rgba(255,255,255,0.06)", color: "var(--color-muted)", border: "1px solid var(--color-border)", cursor: "pointer" }}>닫기</button>
                        </div>
                      </div>
                      {/* 핵심 요약 */}
                      <div style={{ fontSize: "0.85rem", fontWeight: 700, color: "var(--color-text)", lineHeight: 1.5 }}>{shadowResult.catalyst_summary}</div>
                      {/* 연계 기업 */}
                      {shadowResult.partner_company && shadowResult.partner_company !== "-" && (
                        <div style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "0.8rem", background: "rgba(245,158,11,0.06)", padding: "6px 10px", borderRadius: "6px" }}>
                          <span style={{ color: "var(--color-muted)" }}>연계 기업:</span>
                          <span style={{ fontWeight: 700, color: "#fbbf24" }}>{shadowResult.partner_company}</span>
                        </div>
                      )}
                      {/* 리스크 가이드 */}
                      {shadowResult.rumor_warning_guide && (
                        <div style={{ fontSize: "0.8rem", color: "var(--color-muted)", lineHeight: 1.6, background: "rgba(255,255,255,0.02)", padding: "8px 12px", borderRadius: "6px", borderLeft: "3px solid rgba(245,158,11,0.4)" }}>
                          ⚠️ {shadowResult.rumor_warning_guide}
                        </div>
                      )}
                    </div>
                  )}
                </div>

                {/* ─ 시간외 갭 패널 ─ */}
                <div style={{ border: "1px solid var(--color-border)", borderRadius: "10px", overflow: "hidden" }}>
                  {/* idle: 버튼 */}
                  {gapStatus === "idle" && (
                    <button
                      onClick={() => runOvernightGapAnalysis(currentCode, stockName || currentCode, isKR ? "KR" : "US")}
                      disabled={!currentCode}
                      style={{
                        width: "100%", padding: "12px 16px", display: "flex", alignItems: "center", gap: "10px",
                        background: "rgba(59, 130, 246, 0.04)", border: "none", cursor: currentCode ? "pointer" : "not-allowed",
                        color: "var(--color-text)", textAlign: "left",
                        transition: "background 0.2s",
                      }}
                      onMouseEnter={e => (e.currentTarget.style.background = "rgba(59, 130, 246, 0.1)")}
                      onMouseLeave={e => (e.currentTarget.style.background = "rgba(59, 130, 246, 0.04)")}
                    >
                      <span style={{ fontSize: "1.1rem" }}>🌙</span>
                      <div style={{ flex: 1 }}>
                        <div style={{ fontSize: "0.88rem", fontWeight: 700, color: "#60a5fa" }}>AI 시간외 긴급 진단 &amp; 익일 갭 예측</div>
                        <div style={{ fontSize: "0.75rem", color: "var(--color-muted)", marginTop: "2px" }}>시간외 공시·뉴스 기반 익일 시가 갭 예측</div>
                      </div>
                      <span style={{ fontSize: "0.75rem", padding: "3px 8px", borderRadius: "6px", background: "rgba(59,130,246,0.15)", color: "#60a5fa", fontWeight: 700 }}>분석 시작 →</span>
                    </button>
                  )}
                  {/* loading */}
                  {gapStatus === "loading" && (
                    <div style={{ padding: "14px 16px", display: "flex", alignItems: "center", gap: "10px" }}>
                      <Loader2 className="animate-spin" size={14} color="#60a5fa" />
                      <span style={{ fontSize: "0.85rem", color: "var(--color-muted)" }}>{gapMsg}</span>
                    </div>
                  )}
                  {/* error */}
                  {gapStatus === "error" && (
                    <div style={{ padding: "12px 16px", display: "flex", alignItems: "center", justifyContent: "space-between", gap: "8px" }}>
                      <span style={{ fontSize: "0.82rem", color: "#f87171" }}>{gapMsg}</span>
                      <button onClick={() => runOvernightGapAnalysis(currentCode, stockName || currentCode, isKR ? "KR" : "US")} style={{ fontSize: "0.75rem", padding: "3px 8px", borderRadius: "6px", background: "rgba(239,68,68,0.15)", color: "#f87171", border: "1px solid rgba(239,68,68,0.3)", cursor: "pointer" }}>재시도</button>
                    </div>
                  )}
                  {/* done */}
                  {gapStatus === "done" && gapResult && (
                    <div style={{ padding: "14px 16px", display: "flex", flexDirection: "column", gap: "10px" }}>
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "8px" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                          <span style={{ fontSize: "1rem" }}>🌙</span>
                          <div>
                            <div style={{ fontSize: "0.88rem", fontWeight: 800, color: (gapResult.gap_direction || "").includes("갭상승") ? "#f87171" : (gapResult.gap_direction || "").includes("갭하락") ? "#60a5fa" : "var(--color-muted)" }}>AI 시간외 긴급 진단 &amp; 익일 갭 예측</div>
                            {gapResult.gap_direction && (
                              <div style={{ fontSize: "0.75rem", color: "var(--color-muted)", marginTop: "2px" }}>{gapResult.gap_direction}</div>
                            )}
                          </div>
                        </div>
                        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                          {gapResult.gap_strength && (
                            <span style={{ fontSize: "0.72rem", fontWeight: 800, padding: "2px 8px", borderRadius: "12px", background: (gapResult.gap_direction || "").includes("갭상승") ? "rgba(239,68,68,0.15)" : "rgba(59,130,246,0.15)", color: (gapResult.gap_direction || "").includes("갭상승") ? "#f87171" : "#60a5fa", border: `1px solid ${(gapResult.gap_direction || "").includes("갭상승") ? "rgba(239,68,68,0.3)" : "rgba(59,130,246,0.3)"}` }}>예상 폭: {gapResult.gap_strength}</span>
                          )}
                          <button onClick={() => { setGapStatus("idle"); setGapResult(null); }} style={{ fontSize: "0.72rem", padding: "2px 6px", borderRadius: "6px", background: "rgba(255,255,255,0.06)", color: "var(--color-muted)", border: "1px solid var(--color-border)", cursor: "pointer" }}>닫기</button>
                        </div>
                      </div>
                      {/* 시간외 이슈 요약 */}
                      {gapResult.overnight_issue_summary && (
                        <div style={{ fontSize: "0.85rem", fontWeight: 700, color: "var(--color-text)", lineHeight: 1.5 }}>{gapResult.overnight_issue_summary}</div>
                      )}
                      {/* 대응 행동 수칙 */}
                      {gapResult.trading_action_guide && (
                        <div style={{ display: "flex", flexDirection: "column", gap: "6px", fontSize: "0.8rem", background: "rgba(255,255,255,0.02)", padding: "10px 12px", borderRadius: "8px", borderLeft: "3px solid rgba(59,130,246,0.4)" }}>
                          <div style={{ fontWeight: 700, color: "var(--color-text)", marginBottom: "2px" }}>💡 시초가 대응 행동 수칙</div>
                          <div style={{ color: "var(--color-subtle)", lineHeight: 1.6 }}>{gapResult.trading_action_guide}</div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>

            </div>
          )}

          {/* ── 수급 탭 (KR 전용) ───────────────────────────────────────── */}
          {activeTab === "수급" && isKR && (
            <div className="stockcy-card" style={{ flex: 1, display: "flex", flexDirection: "column", padding: "1.5rem" }}>
              <h3 style={{ fontSize: "1.1rem", fontWeight: 700, marginBottom: "1rem" }}>💰 외국인/기관 최근 10일 수급 동향</h3>
              {invLoading ? (
                <div style={{ padding: "2rem", textAlign: "center", color: "var(--color-muted)" }}>
                  <Loader2 className="animate-spin inline" /> 수급 데이터 불러오는 중...
                </div>
              ) : !invData || !Array.isArray(invData) || invData.length === 0 ? (
                <div style={{ color: "var(--color-muted)" }}>수급 데이터가 없습니다.</div>
              ) : (
                <div style={{ overflowX: "auto" }}>
                  <table style={{ width: "100%", textAlign: "right", fontSize: "0.85rem", borderCollapse: "collapse" }}>
                    <thead>
                      <tr style={{ borderBottom: "1px solid rgba(255,255,255,0.1)", color: "var(--color-muted)" }}>
                        <th style={{ padding: "8px", textAlign: "left" }}>일자</th>
                        <th style={{ padding: "8px" }}>종가</th>
                        <th style={{ padding: "8px" }}>전일대비</th>
                        <th style={{ padding: "8px" }}>외국인 순매수</th>
                        <th style={{ padding: "8px" }}>기관 순매수</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(() => {
                        // 10일간의 데이터 중 외국인/기관 순매수 절대값의 최대값을 찾아 비례 스케일 기준으로 설정
                        const maxVal = Math.max(
                          ...invData.map((row: any) => Math.max(Math.abs(row.foreign || 0), Math.abs(row.inst || 0))),
                          1 // 0으로 나누기 방지
                        );

                        return invData.map((row: any, i: number) => {
                          const frgn = row.foreign || 0;
                          const inst = row.inst || 0;
                          
                          const frgnColor = frgn > 0 ? "var(--color-danger)" : frgn < 0 ? "var(--color-primary)" : "var(--color-text)";
                          const instColor = inst > 0 ? "var(--color-danger)" : inst < 0 ? "var(--color-primary)" : "var(--color-text)";
                          const chgColor  = row.change_pct > 0 ? "var(--color-danger)" : row.change_pct < 0 ? "var(--color-primary)" : "var(--color-text)";

                          // 만 주 단위 변환 함수 (소수점 1자리 반올림)
                          const toManJu = (val: number) => {
                            const man = val / 10000;
                            return `${man >= 0 ? "+" : ""}${man.toFixed(1)}만 주`;
                          };

                          // Progress Bar 가로폭 비율 계산 (최대값 대비 절대값 비율)
                          const frgnWidth = `${Math.min(100, (Math.abs(frgn) / maxVal) * 100)}%`;
                          const instWidth = `${Math.min(100, (Math.abs(inst) / maxVal) * 100)}%`;

                          return (
                            <tr key={i} style={{ borderBottom: "1px solid rgba(255,255,255,0.05)", height: "42px" }}>
                              <td style={{ padding: "8px", textAlign: "left" }}>{row.date}</td>
                              <td style={{ padding: "8px" }}>₩{(row.close || 0).toLocaleString()}</td>
                              <td style={{ padding: "8px", color: chgColor, fontWeight: 700 }}>
                                {row.change_pct > 0 ? "▲" : row.change_pct < 0 ? "▼" : ""} {(row.change_pct || 0).toFixed(2)}%
                              </td>
                              
                              {/* 외국인 순매수 Progress Bar */}
                              <td style={{ padding: "6px 8px", position: "relative", width: "25%", minWidth: "120px" }}>
                                <div style={{ position: "relative", width: "100%", height: "22px", background: "rgba(255,255,255,0.02)", borderRadius: "4px", overflow: "hidden" }}>
                                  {frgn !== 0 && (
                                    <div style={{
                                      position: "absolute",
                                      right: 0, // 우측 정렬로 채워지게 설계
                                      top: 0,
                                      height: "100%",
                                      width: frgnWidth,
                                      background: frgn > 0 
                                        ? "linear-gradient(90deg, rgba(239, 68, 68, 0.05) 0%, rgba(239, 68, 68, 0.6) 100%)"
                                        : "linear-gradient(90deg, rgba(59, 130, 246, 0.05) 0%, rgba(59, 130, 246, 0.6) 100%)",
                                      borderRight: `2px solid ${frgn > 0 ? "#ef4444" : "#3b82f6"}`,
                                      borderRadius: "2px",
                                      transition: "width 0.4s ease-out"
                                    }} />
                                  )}
                                  <div style={{
                                    position: "absolute",
                                    inset: 0,
                                    display: "flex",
                                    alignItems: "center",
                                    justifyContent: "flex-end",
                                    paddingRight: "8px",
                                    fontSize: "0.78rem",
                                    fontWeight: 700,
                                    color: frgnColor,
                                    zIndex: 2
                                  }}>
                                    {toManJu(frgn)}
                                  </div>
                                </div>
                              </td>

                              {/* 기관 순매수 Progress Bar */}
                              <td style={{ padding: "6px 8px", position: "relative", width: "25%", minWidth: "120px" }}>
                                <div style={{ position: "relative", width: "100%", height: "22px", background: "rgba(255,255,255,0.02)", borderRadius: "4px", overflow: "hidden" }}>
                                  {inst !== 0 && (
                                    <div style={{
                                      position: "absolute",
                                      left: 0, // 좌측 정렬로 채워지게 설계
                                      top: 0,
                                      height: "100%",
                                      width: instWidth,
                                      background: inst > 0 
                                        ? "linear-gradient(90deg, rgba(239, 68, 68, 0.05) 0%, rgba(239, 68, 68, 0.6) 100%)"
                                        : "linear-gradient(90deg, rgba(59, 130, 246, 0.05) 0%, rgba(59, 130, 246, 0.6) 100%)",
                                      borderLeft: `2px solid ${inst > 0 ? "#ef4444" : "#3b82f6"}`,
                                      borderRadius: "2px",
                                      transition: "width 0.4s ease-out"
                                    }} />
                                  )}
                                  <div style={{
                                    position: "absolute",
                                    inset: 0,
                                    display: "flex",
                                    alignItems: "center",
                                    justifyContent: "flex-start",
                                    paddingLeft: "8px",
                                    fontSize: "0.78rem",
                                    fontWeight: 700,
                                    color: instColor,
                                    zIndex: 2
                                  }}>
                                    {toManJu(inst)}
                                  </div>
                                </div>
                              </td>
                            </tr>
                          );
                        });
                      })()}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {/* ── AI 분석 탭 ──────────────────────────────────────────────── */}
          {activeTab === "AI 분석" && (
            <div className="stockcy-card" style={{ flex: 1, display: "flex", flexDirection: "column", padding: "1.5rem", gap: "1rem" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <h3 style={{ fontSize: "1.1rem", fontWeight: 700, margin: 0 }}>🧠 AI 심층 리포트 및 타점 분석 <AiCostBadge small /></h3>
                <button
                  onClick={isKR ? runAiAnalysis : runUsAiAnalysis}
                  disabled={aiStatus === "loading"}
                  className="stockcy-btn-primary"
                  style={{ padding: "8px 16px", borderRadius: "6px", fontSize: "0.9rem", fontWeight: 600, display: "flex", gap: "6px", alignItems: "center" }}
                >
                  {aiStatus === "loading" ? <><Loader2 size={15} className="animate-spin" /> 분석 중...</> : <><Activity size={15} /> 분석 실행</>}
                </button>
              </div>

              {aiStatus === "idle" && (
                <div style={{ color: "var(--color-muted)", textAlign: "center", padding: "3rem 0", fontSize: "0.9rem" }}>
                  '분석 실행' 버튼을 눌러주세요. (약 30~50초 소요)
                </div>
              )}

              {aiStatus === "loading" && (
                <div style={{ textAlign: "center", padding: "3rem 0" }}>
                  <Loader2 size={36} className="animate-spin" color="var(--color-accent)" style={{ margin: "0 auto 1rem" }} />
                  <div style={{ color: "var(--color-warning)", fontWeight: 600 }}>{aiMsg}</div>
                </div>
              )}

              {aiStatus === "error" && (
                <div style={{ color: "var(--color-danger)", padding: "1rem", textAlign: "center" }}>{aiMsg}</div>
              )}

              {aiStatus === "done" && aiResult && (
                <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                  <div style={{ display: "flex", gap: "10px", alignItems: "center", flexWrap: "wrap" }}>
                    <span style={{ fontWeight: 800, fontSize: "1rem", padding: "4px 12px", borderRadius: "6px", background: aiResult.rating?.includes("추천") ? "rgba(0,200,83,0.15)" : "rgba(255,75,75,0.1)", color: aiResult.rating?.includes("추천") ? "#00c853" : "#ff4b4b", border: `1px solid ${aiResult.rating?.includes("추천") ? "#00c853" : "#ff4b4b"}` }}>
                      {aiResult.rating || "분석 완료"}
                    </span>
                    {aiResult.verified_name && aiResult.ticker_mismatch && (
                      <span style={{ fontSize: "0.8rem", color: "var(--color-warning)" }}>⚠️ 실제 종목: {aiResult.verified_name}</span>
                    )}
                  </div>

                  {/* 교차검증: 언제·당시가 대비 현재가 (재분석 여부 판단용) */}
                  {aiMeta && (
                    <div style={{ display: "flex", flexWrap: "wrap", gap: "6px 14px", alignItems: "center", fontSize: "0.78rem", padding: "8px 12px", background: "rgba(255,255,255,0.03)", border: "1px solid var(--color-border)", borderRadius: "6px" }}>
                      <span style={{ color: "var(--color-muted)" }}>🕒 분석 시점 <b style={{ color: "var(--color-text)" }}>{new Date(aiMeta.ts).toLocaleString("ko-KR", { year: "2-digit", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false })}</b></span>
                      {aiMeta.price > 0 && (
                        <span style={{ color: "var(--color-muted)" }}>당시가 <b style={{ color: "var(--color-text)" }}>{isKR ? `₩${Math.round(aiMeta.price).toLocaleString()}` : `$${aiMeta.price.toFixed(2)}`}</b></span>
                      )}
                      {price > 0 && (
                        <span style={{ color: "var(--color-muted)" }}>현재가 <b style={{ color: "var(--color-text)" }}>{isKR ? `₩${Math.round(price).toLocaleString()}` : `$${price.toFixed(2)}`}</b></span>
                      )}
                      {aiMeta.price > 0 && price > 0 && (() => {
                        const d = (price - aiMeta.price) / aiMeta.price * 100;
                        return <span style={{ fontWeight: 700, color: d >= 0 ? "var(--color-danger)" : "var(--color-primary)" }}>{d >= 0 ? "▲" : "▼"} {Math.abs(d).toFixed(2)}% (분석 이후)</span>;
                      })()}
                      {((Date.now() - aiMeta.ts) / 3600000 >= 24) && (
                        <span style={{ fontSize: "0.72rem", color: "var(--color-warning)", fontWeight: 600 }}>· 24시간 경과 — 재분석 권장</span>
                      )}
                    </div>
                  )}

                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "8px" }}>
                    {[
                      { label: "매수 타점", val: aiResult.buy_target,  color: "var(--color-success)" },
                      { label: "목표가",   val: aiResult.sell_target, color: "var(--color-danger)" },
                      { label: "손절가",   val: aiResult.stop_loss,   color: "var(--color-primary)" },
                    ].map(({ label, val, color: c }) => (
                      <div key={label} style={{ background: "rgba(255,255,255,0.03)", border: `1px solid ${c}`, borderRadius: "6px", padding: "10px", textAlign: "center" }}>
                        <div style={{ fontSize: "0.75rem", color: "var(--color-muted)", marginBottom: "4px" }}>{label}</div>
                        <div style={{ fontWeight: 700, fontSize: "0.85rem", color: c }}>{val || "-"}</div>
                      </div>
                    ))}
                  </div>

                  <div style={{ display: "flex", gap: "6px", borderBottom: "1px solid var(--color-border)", paddingBottom: "4px" }}>
                    {([
                      { id: "short", label: "📊 단기 전망" },
                      { id: "entry", label: "📅 매수 전략" },
                      { id: "mid",   label: "📆 중기 전망" },
                      { id: "long",  label: "🗓 장기 분석" },
                    ] as const).map(({ id, label }) => (
                      <button
                        key={id}
                        onClick={() => setAiAnalysisTab(id)}
                        style={{ padding: "4px 10px", borderRadius: "4px", border: "none", cursor: "pointer", fontSize: "0.8rem", fontWeight: 600, background: aiAnalysisTab === id ? "rgba(255,255,255,0.1)" : "transparent", color: aiAnalysisTab === id ? "var(--color-text)" : "var(--color-muted)", borderBottom: aiAnalysisTab === id ? "2px solid var(--color-accent)" : "2px solid transparent" }}
                      >
                        {label}
                      </button>
                    ))}
                  </div>

                  <div style={{ padding: "0.75rem", background: "rgba(0,0,0,0.2)", borderRadius: "6px", fontSize: "0.88rem", lineHeight: 1.7, maxHeight: "320px", overflowY: "auto" }}>
                    {aiAnalysisTab === "short" && (
                      <div>
                        <div style={{ color: "var(--color-muted)", marginBottom: "0.5rem", fontSize: "0.8rem" }}>단기 예상 변동: <strong style={{ color: "var(--color-text)" }}>{aiResult.short_term_view_pct}</strong> → <strong style={{ color: "var(--color-text)" }}>{aiResult.short_term_view_price}</strong></div>
                        <ReactMarkdown>{aiResult.short_term_view_reason || aiResult.key_issues || ""}</ReactMarkdown>
                      </div>
                    )}
                    {aiAnalysisTab === "entry" && <ReactMarkdown>{aiResult.analysis || aiResult.세력분석 || ""}</ReactMarkdown>}
                    {aiAnalysisTab === "mid" && (
                      <div>
                        <div style={{ color: "var(--color-muted)", marginBottom: "0.5rem", fontSize: "0.8rem" }}>중기 예상: <strong style={{ color: "var(--color-text)" }}>{aiResult.mid_term_view_price}</strong></div>
                        <ReactMarkdown>{aiResult.mid_term_view_condition || ""}</ReactMarkdown>
                      </div>
                    )}
                    {aiAnalysisTab === "long" && (
                      <div>
                        <div style={{ color: "var(--color-muted)", marginBottom: "0.5rem", fontSize: "0.8rem" }}>장기 등급: <strong style={{ color: "var(--color-text)" }}>{aiResult.long_term_rating}</strong> | 목표: <strong style={{ color: "var(--color-text)" }}>{aiResult.long_term_target}</strong> | 기간: <strong style={{ color: "var(--color-text)" }}>{aiResult.long_term_period}</strong></div>
                        <ReactMarkdown>{aiResult.long_term_analysis || ""}</ReactMarkdown>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* box-pattern RAG panel */}
          {activeTab === "박스권" && (
            <div className="stockcy-card" style={{ flex: 1, display: "flex", flexDirection: "column", padding: "1.5rem", gap: "1rem" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <h3 style={{ fontSize: "1.1rem", fontWeight: 700, margin: 0 }}>📈 AI 차트 박스권 & 세력 수급 패턴 분석</h3>
                <button
                  onClick={runBoxAnalysis}
                  disabled={boxStatus === "loading"}
                  className="stockcy-btn-primary"
                  style={{ padding: "8px 16px", borderRadius: "6px", fontSize: "0.9rem", fontWeight: 600, display: "flex", gap: "6px", alignItems: "center" }}
                >
                  {boxStatus === "loading" ? <><Loader2 size={15} className="animate-spin" /> 분석 중...</> : <><Activity size={15} /> 정밀 진단</>}
                </button>
              </div>

              {boxStatus === "idle" && (
                <div style={{ color: "var(--color-muted)", textAlign: "center", padding: "3rem 0", fontSize: "0.9rem" }}>
                  '정밀 진단' 버튼을 누르시면 RAG 엔진이 세력 수급과 지지/저항선을 정밀 스캔합니다.
                </div>
              )}

              {boxStatus === "loading" && (
                <div style={{ textAlign: "center", padding: "3rem 0" }}>
                  <Loader2 size={36} className="animate-spin" color="var(--color-accent)" style={{ margin: "0 auto 1rem" }} />
                  <div style={{ color: "var(--color-warning)", fontWeight: 600 }}>{boxMsg}</div>
                </div>
              )}

              {boxStatus === "error" && (
                <div style={{ color: "var(--color-danger)", padding: "1rem", textAlign: "center" }}>{boxMsg}</div>
              )}

              {boxStatus === "done" && boxResult && (
                <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                  <div style={{ display: "flex", gap: "10px", alignItems: "center", flexWrap: "wrap" }}>
                    <span style={{ fontWeight: 800, fontSize: "1rem", padding: "4px 12px", borderRadius: "6px", background: "rgba(99,102,241,0.15)", color: "#818cf8", border: "1px solid #818cf8" }}>
                      패턴 등급: {boxResult.pattern_rating || "중립"}
                    </span>
                    <span style={{ fontWeight: 800, fontSize: "1rem", padding: "4px 12px", borderRadius: "6px", background: "rgba(0,200,83,0.15)", color: "#00c853", border: "1px solid #00c853" }}>
                      상승 확률: {boxResult.bullish_probability || "-"}
                    </span>
                  </div>

                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
                    <div style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(239, 68, 68, 0.3)", borderRadius: "8px", padding: "12px" }}>
                      <div style={{ fontSize: "0.75rem", color: "var(--color-muted)", marginBottom: "4px" }}>단기 저항선 (세력 매도 벽)</div>
                      <div style={{ fontWeight: 800, fontSize: "1.1rem", color: "#ff4b4b" }}>
                        {currSymbol}{(boxResult.resistance_line || 0).toLocaleString()}
                      </div>
                    </div>
                    <div style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(16, 185, 129, 0.3)", borderRadius: "8px", padding: "12px" }}>
                      <div style={{ fontSize: "0.75rem", color: "var(--color-muted)", marginBottom: "4px" }}>중요 지지선 (세력 매수 벽)</div>
                      <div style={{ fontWeight: 800, fontSize: "1.1rem", color: "#10b981" }}>
                        {currSymbol}{(boxResult.support_line || 0).toLocaleString()}
                      </div>
                    </div>
                  </div>

                  <div style={{ display: "flex", flexDirection: "column", gap: "8px", fontSize: "0.85rem", background: "rgba(0,0,0,0.15)", padding: "14px", borderRadius: "8px", border: "1px solid var(--color-border)" }}>
                    <div style={{ fontWeight: 700, borderBottom: "1px solid rgba(255,255,255,0.1)", paddingBottom: "6px", marginBottom: "4px" }}>📌 AI 차트 & 수급 진단 소견 <AiCostBadge small /></div>
                    <MarkdownLite text={boxResult.pattern_view} style={{ lineHeight: 1.6 }} />
                  </div>

                  <div style={{ display: "flex", flexDirection: "column", gap: "8px", fontSize: "0.85rem", background: "rgba(245, 158, 11, 0.05)", padding: "14px", borderRadius: "8px", border: "1px dashed rgba(245, 158, 11, 0.3)" }}>
                    <div style={{ fontWeight: 700, color: "#fbbf24", display: "flex", alignItems: "center", gap: "6px" }}>🎯 실시간 돌파 매매 가이드라인</div>
                    <MarkdownLite text={boxResult.trading_strategy} style={{ lineHeight: 1.6, color: "#fef08a" }} />
                  </div>
                </div>
              )}
            </div>
          )}

        </div>
      </div>
      {/* 글라스모피즘 실시간 가격 알림 모달 */}
      {alertModalOpen && (
        <div style={{
          position: "fixed", top: 0, left: 0, right: 0, bottom: 0, zIndex: 99999,
          background: "rgba(15, 23, 42, 0.75)", backdropFilter: "blur(12px)",
          display: "flex", alignItems: "center", justifyContent: "center", padding: "1.5rem"
        }}>
          <div style={{
            background: "rgba(30, 41, 59, 0.5)", border: "1px solid rgba(255, 255, 255, 0.1)",
            boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.5)",
            borderRadius: "16px", padding: "1.75rem", width: "100%", maxWidth: "420px",
            display: "flex", flexDirection: "column", gap: "1.2rem",
            position: "relative"
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <Bell size={18} color="var(--color-warning)" />
                <span style={{ fontSize: "1.1rem", fontWeight: 800, color: "var(--color-text)" }}>실시간 가격 알림 설정</span>
              </div>
              <button
                onClick={() => setAlertModalOpen(false)}
                style={{
                  background: "transparent", border: "none", cursor: "pointer",
                  color: "var(--color-muted)", padding: "4px", borderRadius: "50%",
                  display: "flex", alignItems: "center", justifyContent: "center"
                }}
                onMouseOver={(e) => e.currentTarget.style.color = "var(--color-danger)"}
                onMouseOut={(e) => e.currentTarget.style.color = "var(--color-muted)"}
              >
                <X size={20} />
              </button>
            </div>

            {/* 종목 요약 카드 */}
            <div style={{
              background: "rgba(255, 255, 255, 0.03)",
              border: "1px solid rgba(255, 255, 255, 0.05)",
              borderRadius: "8px", padding: "12px",
              display: "flex", flexDirection: "column", gap: "4px"
            }}>
              <div style={{ fontSize: "0.78rem", color: "var(--color-muted)" }}>알림 대상 종목</div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                <span style={{ fontWeight: 700, fontSize: "0.95rem" }}>{stockName} <span style={{ fontSize: "0.8rem", color: "var(--color-muted)" }}>({currentCode})</span></span>
                <span style={{ fontWeight: 800, color: "var(--color-accent)" }}>
                  현재가: {currSymbol}{price.toLocaleString()}
                </span>
              </div>
            </div>

            {/* 입력 폼 */}
            <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
              <div>
                <label style={{ fontSize: "0.78rem", color: "var(--color-muted)", display: "block", marginBottom: "6px" }}>감시 조건</label>
                <select
                  className="stockcy-input bg-zinc-900 border border-white/10 rounded px-3 py-2 w-full text-white text-sm focus:outline-none focus:border-indigo-500 transition-colors"
                  value={alertType}
                  onChange={e => setAlertType(e.target.value)}
                >
                  <option value="상승 돌파">현재가 대비 상승 돌파 (≥)</option>
                  <option value="하락 돌파">현재가 대비 하락 돌파 (≤)</option>
                  <option value="목표가 도달">지정가 목표가 도달</option>
                  <option value="손절가 도달">지정가 손절가 도달</option>
                </select>
              </div>

              <div>
                <label style={{ fontSize: "0.78rem", color: "var(--color-muted)", display: "block", marginBottom: "6px" }}>감시 가격 ({currSymbol})</label>
                <input
                  className="stockcy-input w-full bg-zinc-900/60 border border-white/10 rounded px-3 py-2 text-white"
                  type="number"
                  step="any"
                  placeholder={String(price)}
                  value={targetPrice}
                  onChange={e => setTargetPrice(e.target.value)}
                  style={{ boxSizing: "border-box" }}
                />
              </div>
            </div>

            {/* 텔레그램 가이드 팁 배너 */}
            <div style={{
              background: "rgba(99, 102, 241, 0.08)",
              border: "1px solid rgba(99, 102, 241, 0.2)",
              borderRadius: "10px", padding: "10px 12px",
              fontSize: "0.75rem", color: "#a5b4fc", lineHeight: 1.4
            }}>
              <span style={{ fontWeight: 800, color: "#818cf8" }}>💡 텔레그램 연동 안내:</span> 백엔드 봇이 활성화되어 있다면, 실시간 시장가 도달 즉시 텔레그램 메시지가 발송됩니다.
            </div>

            {/* 실행 버튼 */}
            <button
              className="stockcy-btn stockcy-btn-primary"
              onClick={async () => {
                const tp = Number(targetPrice);
                if (!tp || tp <= 0) {
                  setAlertMsg({ type: "error", text: "올바른 감시 가격을 입력해 주세요." });
                  return;
                }
                setAlertLoading(true);
                setAlertMsg(null);
                try {
                  const marketType = isKR ? "국내" : "미국";
                  await api.portfolio.saveAlert(marketType, currentCode, stockName, alertType, tp);
                  setAlertMsg({ type: "success", text: `성공: ${stockName} 알림 추가 완료 (${alertType} @ ${currSymbol}${tp.toLocaleString()})` });
                  setTimeout(() => {
                    setAlertModalOpen(false);
                  }, 1200);
                } catch (err: any) {
                  setAlertMsg({ type: "error", text: `추가 실패: ${err.message}` });
                } finally {
                  setAlertLoading(false);
                }
              }}
              disabled={alertLoading || !targetPrice}
              style={{
                width: "100%", padding: "12px", fontWeight: 700, fontSize: "0.9rem",
                display: "flex", alignItems: "center", justifyContent: "center", gap: "8px",
                background: "linear-gradient(135deg, #6366f1 0%, #4f46e5 100%)",
                border: "none", color: "white", borderRadius: "8px", cursor: "pointer"
              }}
            >
              {alertLoading ? <><Loader2 className="animate-spin" size={16} /> 설정 중...</> : "알림 설정 완료"}
            </button>

            {alertMsg && (
              <div style={{
                fontSize: "0.8rem",
                color: alertMsg.type === "success" ? "var(--color-success)" : "var(--color-danger)",
                textAlign: "center", marginTop: "4px",
                fontWeight: 600
              }}>
                {alertMsg.text}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default function SearchPage() {
  return (
    <Suspense fallback={<div style={{ padding: "2rem", textAlign: "center", color: "var(--color-muted)" }}>로딩 중...</div>}>
      <SearchPageInner />
    </Suspense>
  );
}
