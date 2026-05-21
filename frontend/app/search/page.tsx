"use client";
import { useState, useEffect, useRef, useMemo } from "react";
import { useSearchParams } from "next/navigation";
import useSWR from "swr";
import { api } from "@/lib/api";
import { useMarket } from "@/lib/market-context";
import { Search, Star, Briefcase, Bell, BarChart2, DollarSign, Activity, Loader2 } from "lucide-react";
import Chart from "@/components/Chart";
import ReactMarkdown from "react-markdown";

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

export default function SearchPage() {
  const { market, setMarket } = useMarket();
  const isKR = market === "KR";
  const currSymbol = isKR ? "₩" : "$";

  const searchParams = useSearchParams();
  const [searchQuery, setSearchQuery] = useState("");
  const [activeTab, setActiveTab] = useState("시세");
  const [currentCode, setCurrentCode] = useState<string>(isKR ? "005930" : "AAPL");
  const [chartType, setChartType] = useState<string>("daily");
  const [minuteInterval, setMinuteInterval] = useState<number>(5);
  const [showDropdown, setShowDropdown] = useState(false);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [aiResult, setAiResult] = useState<any>(null);
  const [aiStatus, setAiStatus] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [aiAnalysisTab, setAiAnalysisTab] = useState<"short" | "entry" | "mid" | "long">("short");
  const [aiMsg, setAiMsg] = useState("");

  // 시장 전환 시 기본값 리셋
  const prevMarketRef = useRef<string | null>(null);
  useEffect(() => {
    if (prevMarketRef.current !== null && prevMarketRef.current !== market) {
      setCurrentCode(market === "KR" ? "005930" : "AAPL");
      setActiveTab("시세");
      setChartType("daily");
      setAiStatus("idle");
      setAiResult(null);
    }
    prevMarketRef.current = market;
  }, [market]);

  // ── KR SWR ───────────────────────────────────────────────────────────────
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const { data: krStockData, isLoading: krLoading } = useSWR<any>(
    isKR ? `/api/kr/stocks/${currentCode}` : null,
    () => api.kr.stockPrice(currentCode)
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
  const { data: krChartRaw } = useSWR(
    isKR ? `/api/kr/chart/${currentCode}/${chartType}/${minuteInterval}` : null,
    () => {
      if (chartType === "minute") return api.kr.minuteChart(currentCode, minuteInterval);
      if (chartType === "weekly")  return api.kr.dailyChart(currentCode, 600, "W");
      if (chartType === "monthly") return api.kr.dailyChart(currentCode, 600, "M");
      return api.kr.dailyChart(currentCode, 600, "D");
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
    () => api.us.stockDetail(currentCode)
  );
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const { data: usChartRaw } = useSWR<any>(
    !isKR ? `/api/us/chart/${currentCode}/${chartType}` : null,
    () => {
      if (chartType === "weekly")  return api.us.chart(currentCode, "2y",  "1wk");
      if (chartType === "monthly") return api.us.chart(currentCode, "5y",  "1mo");
      return api.us.chart(currentCode, "1y", "1d");
    }
  );

  // ── 통합 값 ──────────────────────────────────────────────────────────────
  const stockData  = isKR ? krStockData  : usStockData;
  const isLoading  = isKR ? krLoading    : usLoading;
  const chartDataRaw = isKR ? krChartRaw : usChartRaw;

  const price     = stockData?.price || 0;
  const change    = stockData?.change_pct || 0;
  const changeVal = Math.abs(stockData?.change || 0);
  const isUp      = change > 0;
  const isDown    = change < 0;
  const color     = isUp ? "var(--color-danger)" : isDown ? "var(--color-primary)" : "var(--color-text)";
  const changeStr = isUp ? "▲" : isDown ? "▼" : "━";
  const stockName = isKR
    ? (nameData?.name || stockData?.name || currentCode)
    : (stockData?.name || currentCode);

  const w52High = isKR ? (stockData?.["52주최고가"] || price || 1) : (stockData?.w52_high || price || 1);
  const w52Low  = isKR ? (stockData?.["52주최저가"] || 1)          : (stockData?.w52_low  || 1);
  const per = parseFloat(String(isKR ? (stockData?.PER || "20") : (stockData?.per || "20")).replace(",", "")) || 20;
  const pbr = parseFloat(String(isKR ? (stockData?.PBR || "1.5") : (stockData?.pbr || "1.5")).replace(",", "")) || 1.5;

  // 차트 데이터 파싱
  const chartData = useMemo(() => {
    if (!chartDataRaw || !Array.isArray(chartDataRaw)) return [];
    return chartDataRaw.map((d: any) => {
      const rawTime = d.일자 || d.date || d.날짜 || d.time || d.datetime || "";
      let finalTime: any = rawTime;
      if (chartType === "minute") {
        const dateObj = new Date(rawTime);
        finalTime = Math.floor(dateObj.getTime() / 1000) + (9 * 3600);
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

  // 자동완성 (KR: 코드+이름+초성 / US: 티커+한국어이름+초성)
  const filteredStocks = useMemo(() => {
    if (!searchQuery.trim()) return [];
    const query = searchQuery.replace(/\s+/g, "").toLowerCase();
    const queryChosung = getChosung(query);

    if (isKR) {
      if (!allStocks) return [];
      const results = [];
      for (const [code, name] of Object.entries(allStocks as Record<string, string>)) {
        const nameSafe = name.replace(/\s+/g, "").toLowerCase();
        const nameChosung = getChosung(nameSafe);
        if (code.includes(query) || nameSafe.includes(query) || nameChosung.includes(queryChosung)) {
          results.push({ code, name });
        }
        if (results.length >= 10) break;
      }
      return results;
    } else {
      // US: ticker 또는 한국어 이름으로 검색
      if (!usAllStocks) return [];
      const results = [];
      for (const [ticker, name] of Object.entries(usAllStocks as Record<string, string>)) {
        const tickerLower = ticker.toLowerCase();
        const nameSafe = name.replace(/\s+/g, "").toLowerCase();
        const nameChosung = getChosung(nameSafe);
        if (
          tickerLower.startsWith(query) ||
          tickerLower.includes(query) ||
          nameSafe.includes(query) ||
          nameChosung.includes(queryChosung)
        ) {
          results.push({ code: ticker, name });
        }
        if (results.length >= 10) break;
      }
      return results;
    }
  }, [isKR, searchQuery, allStocks, usAllStocks]);

  const performSearch = (code: string) => {
    if (!code.trim()) return;
    setSearchQuery("");
    setShowDropdown(false);
    setCurrentCode(code.toUpperCase());
    setAiStatus("idle");
    setAiResult(null);
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

  // AI 분석 (KR 전용)
  const runAiAnalysis = async () => {
    setAiStatus("loading");
    setAiResult(null);
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
            else if (parsed.status === "done") { setAiResult(parsed.result); setAiStatus("done"); }
            else if (parsed.status === "error") { setAiMsg(`❌ ${parsed.message}`); setAiStatus("error"); }
          } catch {}
        }
      }
    } catch (err: any) {
      setAiMsg(`❌ 오류: ${err.message}`);
      setAiStatus("error");
    }
  };

  // 탭 목록 (수급은 KR 전용)
  const ANALYSIS_TABS = isKR ? ["시세", "수급", "AI 분석"] : ["시세", "AI 분석"];

  return (
    <div style={{ width: "100%", margin: "0 auto" }}>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "2rem" }}>

        {/* ── 좌측: 차트 영역 ─────────────────────────────────────────── */}
        <div className="stockcy-card" style={{ display: "flex", flexDirection: "column", padding: 0, minHeight: "700px" }}>
          <div style={{ padding: "1.5rem 1.5rem 1rem", borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
            <div style={{ display: "flex", alignItems: "baseline", gap: "10px", marginBottom: "0.25rem" }}>
              <h2 style={{ fontSize: "1.4rem", fontWeight: 800, margin: 0 }}>
                {stockName || (isLoading ? "로딩중..." : "종목명")}
              </h2>
              <span style={{ color: "var(--color-muted)", fontSize: "0.95rem" }}>({currentCode})</span>
              <div style={{ marginLeft: "0.5rem", fontSize: "1.4rem", fontWeight: 800 }}>
                {currSymbol}{price.toLocaleString()}
              </div>
              <div style={{ fontSize: "0.95rem", fontWeight: 700, color }}>
                {changeStr} {isKR ? `${changeVal.toLocaleString()}원 ` : ""}({change > 0 ? "+" : ""}{change.toFixed(2)}%)
              </div>
            </div>

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

            <div style={{ marginTop: "1rem", display: "flex", gap: "10px" }}>
              <select
                className="stockcy-input"
                value={chartType}
                onChange={(e) => setChartType(e.target.value)}
                style={{ width: "100px", padding: "6px 10px", fontSize: "0.9rem", background: "var(--color-surface-hover)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: "4px", color: "#fff" }}
              >
                {isKR && <option value="minute">분봉</option>}
                <option value="daily">일봉</option>
                <option value="weekly">주봉</option>
                <option value="monthly">월봉</option>
              </select>

              {isKR && chartType === "minute" && (
                <select
                  className="stockcy-input"
                  value={minuteInterval}
                  onChange={(e) => setMinuteInterval(Number(e.target.value))}
                  style={{ width: "80px", padding: "6px 10px", fontSize: "0.9rem", background: "var(--color-surface-hover)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: "4px", color: "#fff" }}
                >
                  <option value={1}>1분</option>
                  <option value={5}>5분</option>
                  <option value={15}>15분</option>
                  <option value={30}>30분</option>
                  <option value={60}>60분</option>
                </select>
              )}
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
              <Chart data={chartData} />
            ) : (
              <div style={{ width: "100%", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--color-muted)" }}>
                <Loader2 className="animate-spin" size={32} />
              </div>
            )}
          </div>
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

            {/* 자동완성 드롭다운 (KR + US 공통) */}
            {showDropdown && searchQuery && filteredStocks.length > 0 && (
              <div style={{ position: "absolute", top: "100%", left: 0, right: 0, zIndex: 9999, backgroundColor: "#0F172A", border: "1px solid #334155", borderRadius: "8px", marginTop: "4px", overflow: "hidden", boxShadow: "0 12px 32px rgba(0,0,0,0.8)" }}>
                {filteredStocks.map((item, idx) => (
                  <div
                    key={item.code}
                    onClick={() => performSearch(item.code)}
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
                {tab === "시세" ? "📊 시세" : tab === "수급" ? "🔥 수급" : "🤖 AI 분석"}
              </button>
            ))}
          </div>

          {/* ── 시세 탭 ─────────────────────────────────────────────────── */}
          {activeTab === "시세" && (
            <div className="stockcy-card" style={{ flex: 1, display: "flex", flexDirection: "column", gap: "1.2rem", padding: "1.5rem" }}>
              <div style={{ display: "flex", gap: "10px" }}>
                <button className="stockcy-btn" style={{ flex: 1, padding: "8px", fontSize: "0.95rem", display: "flex", justifyContent: "center", gap: "6px", background: "var(--color-elevated)", border: "1px solid var(--color-border)" }}>
                  <Star size={14} color="var(--color-warning)" /> 즐겨찾기
                </button>
                <button className="stockcy-btn" style={{ flex: 1, padding: "6px", fontSize: "0.85rem", display: "flex", justifyContent: "center", gap: "6px", background: "var(--color-elevated)", border: "1px solid var(--color-border)" }}>
                  <Briefcase size={14} color="var(--color-danger)" /> 포트폴리오
                </button>
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
                    <div><div style={{ color: "var(--color-muted)", fontSize: "0.75rem" }}>거래량</div><div style={{ fontWeight: 700 }}>{stockData?.거래량?.toLocaleString() || 0}주</div></div>
                    <div><div style={{ color: "var(--color-muted)", fontSize: "0.75rem" }}>거래대금</div><div style={{ fontWeight: 700 }}>₩{((stockData?.거래량 || 0) * price / 100000000).toLocaleString(undefined, { maximumFractionDigits: 0 })}억</div></div>
                    <div><div style={{ color: "var(--color-muted)", fontSize: "0.75rem" }}>PER</div><div style={{ fontWeight: 700 }}>{stockData?.PER || "N/A"}</div></div>
                    <div><div style={{ color: "var(--color-muted)", fontSize: "0.75rem" }}>시가</div><div style={{ fontWeight: 700 }}>₩{stockData?.시가?.toLocaleString() || 0}</div></div>
                    <div><div style={{ color: "var(--color-muted)", fontSize: "0.75rem" }}>고가</div><div style={{ fontWeight: 700 }}>₩{stockData?.고가?.toLocaleString() || 0}</div></div>
                    <div><div style={{ color: "var(--color-muted)", fontSize: "0.75rem" }}>저가</div><div style={{ fontWeight: 700 }}>₩{stockData?.저가?.toLocaleString() || 0}</div></div>
                    <div><div style={{ color: "var(--color-muted)", fontSize: "0.75rem" }}>PBR</div><div style={{ fontWeight: 700 }}>{stockData?.PBR || "N/A"}</div></div>
                    <div><div style={{ color: "var(--color-muted)", fontSize: "0.75rem" }}>52주 최고</div><div style={{ fontWeight: 700, color: "var(--color-danger)" }}>₩{stockData?.["52주최고가"]?.toLocaleString() || price}</div></div>
                    <div><div style={{ color: "var(--color-muted)", fontSize: "0.75rem" }}>52주 최저</div><div style={{ fontWeight: 700, color: "var(--color-primary)" }}>₩{stockData?.["52주최저가"]?.toLocaleString() || 0}</div></div>
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

              <div style={{ display: "flex", alignItems: "center", gap: "6px", color: "var(--color-warning)", fontSize: "0.8rem", cursor: "pointer", fontWeight: 600 }}>
                <Bell size={14} /> 가격 알림 설정
              </div>

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
                      {invData.map((row: any, i: number) => {
                        const frgnColor = row.foreign > 0 ? "var(--color-danger)" : row.foreign < 0 ? "var(--color-primary)" : "var(--color-text)";
                        const instColor = row.inst > 0 ? "var(--color-danger)" : row.inst < 0 ? "var(--color-primary)" : "var(--color-text)";
                        const chgColor  = row.change_pct > 0 ? "var(--color-danger)" : row.change_pct < 0 ? "var(--color-primary)" : "var(--color-text)";
                        return (
                          <tr key={i} style={{ borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
                            <td style={{ padding: "8px", textAlign: "left" }}>{row.date}</td>
                            <td style={{ padding: "8px" }}>₩{(row.close || 0).toLocaleString()}</td>
                            <td style={{ padding: "8px", color: chgColor }}>{row.change_pct > 0 ? "▲" : row.change_pct < 0 ? "▼" : ""} {(row.change_pct || 0).toFixed(2)}%</td>
                            <td style={{ padding: "8px", color: frgnColor, fontWeight: 600 }}>{(row.foreign || 0).toLocaleString()}</td>
                            <td style={{ padding: "8px", color: instColor, fontWeight: 600 }}>{(row.inst || 0).toLocaleString()}</td>
                          </tr>
                        );
                      })}
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
                <h3 style={{ fontSize: "1.1rem", fontWeight: 700, margin: 0 }}>🧠 AI 심층 리포트 및 타점 분석</h3>
                {isKR && (
                  <button
                    onClick={runAiAnalysis}
                    disabled={aiStatus === "loading"}
                    className="stockcy-btn-primary"
                    style={{ padding: "8px 16px", borderRadius: "6px", fontSize: "0.9rem", fontWeight: 600, display: "flex", gap: "6px", alignItems: "center" }}
                  >
                    {aiStatus === "loading" ? <><Loader2 size={15} className="animate-spin" /> 분석 중...</> : <><Activity size={15} /> 분석 실행</>}
                  </button>
                )}
              </div>

              {!isKR && (
                <div style={{ color: "var(--color-muted)", textAlign: "center", padding: "3rem 0", fontSize: "0.9rem" }}>
                  🔧 미국 주식 AI 분석은 준비 중입니다.
                </div>
              )}

              {isKR && aiStatus === "idle" && (
                <div style={{ color: "var(--color-muted)", textAlign: "center", padding: "3rem 0", fontSize: "0.9rem" }}>
                  '분석 실행' 버튼을 눌러주세요. (약 30~50초 소요)
                </div>
              )}

              {isKR && aiStatus === "loading" && (
                <div style={{ textAlign: "center", padding: "3rem 0" }}>
                  <Loader2 size={36} className="animate-spin" color="var(--color-accent)" style={{ margin: "0 auto 1rem" }} />
                  <div style={{ color: "var(--color-warning)", fontWeight: 600 }}>{aiMsg}</div>
                </div>
              )}

              {isKR && aiStatus === "error" && (
                <div style={{ color: "var(--color-danger)", padding: "1rem", textAlign: "center" }}>{aiMsg}</div>
              )}

              {isKR && aiStatus === "done" && aiResult && (
                <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                  <div style={{ display: "flex", gap: "10px", alignItems: "center", flexWrap: "wrap" }}>
                    <span style={{ fontWeight: 800, fontSize: "1rem", padding: "4px 12px", borderRadius: "6px", background: aiResult.rating?.includes("추천") ? "rgba(0,200,83,0.15)" : "rgba(255,75,75,0.1)", color: aiResult.rating?.includes("추천") ? "#00c853" : "#ff4b4b", border: `1px solid ${aiResult.rating?.includes("추천") ? "#00c853" : "#ff4b4b"}` }}>
                      {aiResult.rating || "분석 중"}
                    </span>
                    {aiResult.verified_name && aiResult.ticker_mismatch && (
                      <span style={{ fontSize: "0.8rem", color: "var(--color-warning)" }}>⚠️ 실제 종목: {aiResult.verified_name}</span>
                    )}
                  </div>

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

        </div>
      </div>
    </div>
  );
}
