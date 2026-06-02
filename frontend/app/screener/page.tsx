"use client";
import { useState, useMemo, useEffect } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import { Filter, Search, BarChart2, Activity, Play, RefreshCw, X, Loader2, TrendingUp, Layers } from "lucide-react";
import { useRouter } from "next/navigation";

// ── 밸류체인 원클릭 팝업 모달 컴포넌트 ───────────────────────────────────────────
function ValueChainModal({
  isOpen,
  onClose,
  sector,
  subSector,
  market,
  sectorMapData
}: {
  isOpen: boolean;
  onClose: () => void;
  sector: string;
  subSector: string;
  market: string;
  sectorMapData: any;
}) {
  const isKr = market === "KR";

  // 해당 세부 섹터에 소속된 종목 리스트 추출
  const memberStocks = useMemo(() => {
    if (!sectorMapData || !sector || !subSector) return [];
    return sectorMapData[sector]?.[subSector] ?? [];
  }, [sectorMapData, sector, subSector]);

  // 종목 코드(티커) 리스트 추출
  const tickers = useMemo(() => {
    return memberStocks.map((s: any) => (isKr ? String(s.code).padStart(6, "0") : String(s.ticker).toUpperCase()));
  }, [memberStocks, isKr]);

  // 실시간 시세 조회 SWR
  const { data: prices, isLoading } = useSWR(
    isOpen && tickers.length > 0 ? `screener-valchain-${market}-${tickers.join(",")}` : null,
    async () => {
      if (isKr) {
        // 한국장 벌크 시세
        const res = await api.kr.stocksBulk(tickers) as any[];
        const map: Record<string, any> = {};
        for (const s of (res ?? [])) {
          const code = String(s.code || s.티커 || "").padStart(6, "0");
          if (code) {
            map[code] = {
              price: s.price || s.현재가 || 0,
              change_pct: s.change_pct || s.등락률 || 0,
              volume: s.volume || s.거래량 || 0,
            };
          }
        }
        return map;
      } else {
        // 미국장 벌크 시세
        const res = await api.us.stocks(tickers) as any[];
        const map: Record<string, any> = {};
        for (const s of (res ?? [])) {
          const ticker = String(s.ticker || s.심볼 || "").toUpperCase();
          if (ticker) {
            map[ticker] = {
              price: s.price || s.현재가 || s["현재가($)"] || 0,
              change_pct: s.change_pct || s.등락률 || s["등락률(%)"] || 0,
              volume: s.volume || s.거래량 || 0,
            };
          }
        }
        return map;
      }
    },
    { refreshInterval: 15000 }
  );

  // 시세 정보가 결합된 최종 관련주 리스트
  const enrichedStocks = useMemo(() => {
    const list = memberStocks.map((s: any) => {
      const code = isKr ? String(s.code).padStart(6, "0") : String(s.ticker).toUpperCase();
      const name = isKr ? s.name : s.name || s.ticker;
      const priceInfo = prices?.[code] ?? null;

      return {
        ticker: code,
        name,
        price: priceInfo?.price ?? 0,
        change_pct: priceInfo?.change_pct ?? 0,
        volume: priceInfo?.volume ?? 0,
        hasPrice: !!priceInfo,
      };
    });

    // 등락률 높은 순으로 정렬 (대장주 판단용)
    return list.sort((a: any, b: any) => b.change_pct - a.change_pct);
  }, [memberStocks, prices, isKr]);

  if (!isOpen) return null;

  return (
    <div style={{
      position: "fixed", top: 0, left: 0, right: 0, bottom: 0, zIndex: 99999,
      background: "rgba(15, 23, 42, 0.75)", backdropFilter: "blur(12px)",
      display: "flex", alignItems: "center", justifyContent: "center", padding: "1.5rem"
    }}>
      <div style={{
        background: "rgba(30, 41, 59, 0.85)", border: "1px solid rgba(255, 255, 255, 0.1)",
        boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.5)",
        borderRadius: "16px", padding: "1.75rem", width: "100%", maxWidth: "560px",
        display: "flex", flexDirection: "column", gap: "1.2rem",
        position: "relative"
      }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <Layers size={18} color="#a5b4fc" />
            <span style={{ fontSize: "1.1rem", fontWeight: 800, color: "var(--color-text)" }}>
              {subSector} 밸류체인 관련주 분석
            </span>
          </div>
          <button
            onClick={onClose}
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

        {/* 대분류 - 소분류 경로 배너 */}
        <div style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "0.8rem", background: "rgba(99, 102, 241, 0.1)", border: "1px solid rgba(99, 102, 241, 0.2)", padding: "8px 12px", borderRadius: "8px" }}>
          <span style={{ color: "#818cf8", fontWeight: 700 }}>{sector}</span>
          <span style={{ color: "var(--color-muted)" }}>›</span>
          <span style={{ color: "#a5b4fc", fontWeight: 700 }}>{subSector}</span>
        </div>

        {/* 밸류체인 관계 설명 */}
        <div style={{ fontSize: "0.82rem", color: "var(--color-subtle)", lineHeight: 1.5, background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.05)", padding: "12px", borderRadius: "8px" }}>
          💡 <strong>밸류체인 리포트:</strong> {subSector} 세부 업종에 편입된 실시간 관련주 라인업입니다. 등락률 순위에 따라 업종 내 자금이 쏠리는 <strong>대장주</strong>와 후발로 따라붙는 <strong>수혜주</strong> 구도를 실시간으로 추적할 수 있습니다.
        </div>

        {/* 관련주 테이블 */}
        <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
          <div style={{ fontSize: "0.8rem", color: "var(--color-muted)", fontWeight: 700 }}>
            소속 관련주 실시간 시세 ({enrichedStocks.length}종목)
          </div>
          
          {isLoading ? (
            <div style={{ display: "flex", alignItems: "center", justifyContent: "center", padding: "2rem 0", gap: "8px", color: "var(--color-muted)" }}>
              <Loader2 className="animate-spin" size={18} />
              <span>실시간 밸류체인 가격 동기화 중...</span>
            </div>
          ) : enrichedStocks.length === 0 ? (
            <div style={{ color: "var(--color-muted)", fontSize: "0.8rem", padding: "1rem 0", textAlign: "center" }}>
              소속된 종목이 없습니다.
            </div>
          ) : (
            <div style={{ maxHeight: "250px", overflowY: "auto", border: "1px solid var(--color-border)", borderRadius: "8px" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.8rem" }}>
                <thead>
                  <tr style={{ background: "var(--color-elevated)", borderBottom: "1px solid var(--color-border)", textAlign: "left" }}>
                    <th style={{ padding: "8px 12px", color: "var(--color-muted)", fontWeight: 600 }}>종목</th>
                    <th style={{ padding: "8px 12px", color: "var(--color-muted)", fontWeight: 600, textAlign: "right" }}>현재가</th>
                    <th style={{ padding: "8px 12px", color: "var(--color-muted)", fontWeight: 600, textAlign: "right" }}>등락률</th>
                    <th style={{ padding: "8px 12px", color: "var(--color-muted)", fontWeight: 600, textAlign: "center" }}>포지션</th>
                  </tr>
                </thead>
                <tbody>
                  {enrichedStocks.map((s: any, idx: number) => {
                    const isUp = s.change_pct > 0;
                    const isDown = s.change_pct < 0;
                    const c = isUp ? "var(--color-danger)" : isDown ? "var(--color-primary)" : "var(--color-text)";
                    const isLeader = idx === 0 && s.change_pct > 0;

                    return (
                      <tr key={s.ticker} style={{ borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
                        <td style={{ padding: "8px 12px" }}>
                          <div style={{ fontWeight: 700 }}>{s.name}</div>
                          <div style={{ fontSize: "0.7rem", color: "var(--color-muted)" }}>{s.ticker}</div>
                        </td>
                        <td style={{ padding: "8px 12px", textAlign: "right", fontWeight: 600 }}>
                          {s.hasPrice ? `${isKr ? "₩" : "$"}${s.price.toLocaleString()}` : "-"}
                        </td>
                        <td style={{ padding: "8px 12px", textAlign: "right", fontWeight: 700, color: c }}>
                          {s.hasPrice ? `${isUp ? "+" : ""}${s.change_pct.toFixed(2)}%` : "-"}
                        </td>
                        <td style={{ padding: "8px 12px", textAlign: "center" }}>
                          {isLeader ? (
                            <span style={{ fontSize: "0.68rem", padding: "1px 6px", borderRadius: "4px", background: "rgba(245, 158, 11, 0.15)", border: "1px solid rgba(245, 158, 11, 0.4)", color: "#fbbf24", fontWeight: 800 }}>
                              👑 대장주
                            </span>
                          ) : (
                            <span style={{ fontSize: "0.68rem", padding: "1px 6px", borderRadius: "4px", background: "rgba(99, 102, 241, 0.08)", border: "1px solid rgba(99, 102, 241, 0.2)", color: "#a5b4fc", fontWeight: 600 }}>
                              수혜주
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const MARKET_OPTIONS = ["KR", "US"];

const KR_CONDITIONS = [
  { id: "52w_high", label: "🔥 52주 신고가 근접 (-5% 이내)" },
  { id: "volume_spike", label: "🌊 거래량 폭발 (최근 5일 평균 대비 300% 이상)" },
  { id: "macd_golden_cross", label: "📈 MACD 골든크로스 (0선 부근 돌파)" },
];

export function ScreenerPanel() {
  const router = useRouter();
  const [market, setMarket] = useState("KR");
  const [selectedSector, setSelectedSector] = useState("전체");
  const [conditions, setConditions] = useState<string[]>([]);
  const [results, setResults] = useState<any[] | null>(null);
  const [isScreening, setIsScreening] = useState(false);
  const [reliableOnly, setReliableOnly] = useState(false);   // 학습된 정량필터(저승률 제외)

  // 밸류체인 팝업 모달 상태
  const [valChainTarget, setValChainTarget] = useState<{ sector: string; subSector: string } | null>(null);

  // URL 쿼리(?market=&sector=)로 진입 시 해당 시장/섹터 자동 선택 (섹터 칩 클릭 연동)
  useEffect(() => {
    const sp = new URLSearchParams(window.location.search);
    const m = sp.get("market");
    const s = sp.get("sector");
    if (m === "KR" || m === "US") setMarket(m);
    if (s) setSelectedSector(s);
  }, []);

  // KR / US 섹터 목록 가져오기
  const { data: sectorMapData } = useSWR(
    market === "KR" ? "/api/kr/sector-map" : "/api/us/sector-map",
    () => market === "KR" ? api.kr.sectorMap() : api.us.sectorMap(),
    { revalidateOnFocus: false }
  );

  const sectorList = useMemo(() => {
    if (!sectorMapData) return ["전체"];
    return ["전체", ...Object.keys(sectorMapData)];
  }, [sectorMapData]);

  // 현재 종목의 섹터/세부섹터 찾기 헬퍼
  const findSectorInfo = (ticker: string) => {
    if (!sectorMapData) return null;
    const isKr = market === "KR";
    const target = isKr ? String(ticker).padStart(6, "0") : String(ticker).toUpperCase();
    
    for (const [sector, subMap] of Object.entries(sectorMapData as Record<string, Record<string, any[]>>)) {
      if (!subMap || typeof subMap !== "object") continue;
      for (const [subSector, stocks] of Object.entries(subMap)) {
        if (!Array.isArray(stocks)) continue;
        const found = stocks.some((s: any) => {
          const code = isKr ? String(s.code).padStart(6, "0") : String(s.ticker).toUpperCase();
          return code === target;
        });
        if (found) return { sector, subSector };
      }
    }
    return null;
  };

  const toggleCondition = (id: string) => {
    if (conditions.includes(id)) {
      setConditions(conditions.filter(c => c !== id));
    } else {
      setConditions([...conditions, id]);
    }
  };

  const handleRunScreener = async () => {
    if (conditions.length === 0) {
      alert("최소 1개 이상의 조건식을 선택해주세요!");
      return;
    }
    
    setIsScreening(true);
    setResults(null);
    try {
      const BASE_URL = "/backend";
      const res = await fetch(`${BASE_URL}/api/screener/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          market,
          sector: selectedSector,
          conditions,
          reliable_only: reliableOnly,
        })
      });
      const data = await res.json();
      setResults(data.results || []);
    } catch (err) {
      console.error(err);
      alert("스크리닝 중 오류가 발생했습니다.");
    } finally {
      setIsScreening(false);
    }
  };

  return (
    <div style={{ padding: "24px", maxWidth: "1200px", margin: "0 auto", color: "var(--color-text)" }}>
      <div style={{ marginBottom: "24px", borderBottom: "1px solid var(--color-border)", paddingBottom: "16px" }}>
        <h1 style={{ fontSize: "1.8rem", display: "flex", alignItems: "center", gap: "10px", margin: 0 }}>
          <Filter size={28} color="var(--color-primary)" />
          나만의 복합 스크리너
        </h1>
        <p style={{ color: "var(--color-muted)", marginTop: "8px", fontSize: "0.95rem" }}>
          원하는 섹터의 모든 종목(소형주 포함)을 실시간으로 스캔하여 강력한 기술적 조건에 부합하는 숨겨진 진주를 발굴합니다.
        </p>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 3fr", gap: "24px", alignItems: "start" }}>
        
        {/* 좌측: 조건 설정 패널 */}
        <div style={{ background: "var(--color-card)", borderRadius: "12px", padding: "20px", border: "1px solid var(--color-border)", display: "flex", flexDirection: "column", gap: "24px" }}>
          
          {/* 1. 시장 및 섹터 선택 */}
          <div>
            <h3 style={{ fontSize: "1.1rem", margin: "0 0 12px 0", display: "flex", alignItems: "center", gap: "6px" }}>
              <Search size={16} /> 1. 대상 풀(Pool) 선택
            </h3>
            
            <div style={{ display: "flex", gap: "10px", marginBottom: "12px" }}>
              {MARKET_OPTIONS.map(m => (
                <button
                  key={m}
                  onClick={() => { setMarket(m); setSelectedSector("전체"); }}
                  className={`stockcy-btn ${market === m ? "stockcy-btn-primary" : ""}`}
                  style={{ flex: 1, padding: "8px", fontWeight: 700 }}
                >
                  {m === "KR" ? "🇰🇷 한국장" : "🇺🇸 미국장"}
                </button>
              ))}
            </div>

            <select 
              value={selectedSector}
              onChange={e => setSelectedSector(e.target.value)}
              className="stockcy-input"
              style={{ width: "100%", padding: "10px" }}
            >
              {sectorList.map(sec => (
                <option key={sec} value={sec}>{sec} 섹터 내 모든 종목 탐색</option>
              ))}
            </select>
          </div>

          {/* 2. 조건식 다중 선택 */}
          <div>
            <h3 style={{ fontSize: "1.1rem", margin: "0 0 12px 0", display: "flex", alignItems: "center", gap: "6px" }}>
              <Activity size={16} /> 2. 정밀 조건식 선택
            </h3>
            <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
              {KR_CONDITIONS.map(cond => {
                const checked = conditions.includes(cond.id);
                return (
                  <label key={cond.id} style={{ display: "flex", alignItems: "center", gap: "10px", cursor: "pointer", padding: "10px", background: checked ? "rgba(128,90,250,0.15)" : "var(--color-elevated)", border: `1px solid ${checked ? "var(--color-primary)" : "var(--color-border)"}`, borderRadius: "8px", transition: "all 0.2s" }}>
                    <input 
                      type="checkbox" 
                      checked={checked} 
                      onChange={() => toggleCondition(cond.id)} 
                      style={{ transform: "scale(1.2)", accentColor: "var(--color-primary)" }}
                    />
                    <span style={{ fontSize: "0.95rem", fontWeight: checked ? 600 : 400, color: checked ? "var(--color-primary)" : "var(--color-text)" }}>
                      {cond.label}
                    </span>
                  </label>
                );
              })}
            </div>
          </div>

          <label style={{ display: "flex", alignItems: "center", gap: "8px", marginTop: "12px", cursor: "pointer", fontSize: "0.8rem", color: "var(--color-text)" }}>
            <input type="checkbox" checked={reliableOnly} onChange={(e) => setReliableOnly(e.target.checked)} style={{ width: "16px", height: "16px", cursor: "pointer" }} />
            <span>✅ 검증된 조건만 보기 <span style={{ color: "var(--color-muted)", fontSize: "0.72rem" }}>(과거 저승률 조건 종목 제외)</span></span>
          </label>

          <button
            className="stockcy-btn stockcy-btn-primary"
            onClick={handleRunScreener}
            disabled={isScreening || conditions.length === 0}
            style={{ width: "100%", padding: "14px", fontSize: "1.05rem", fontWeight: 800, display: "flex", alignItems: "center", justifyContent: "center", gap: "8px", marginTop: "10px" }}
          >
            {isScreening ? <><RefreshCw className="animate-spin" size={18} /> 스캔 중...</> : <><Play size={18} fill="currentColor" /> 정밀 스크리닝 실행</>}
          </button>
        </div>

        {/* 우측: 스크리닝 결과 패널 */}
        <div style={{ background: "var(--color-card)", borderRadius: "12px", padding: "20px", border: "1px solid var(--color-border)", minHeight: "600px" }}>
          <h2 style={{ fontSize: "1.3rem", margin: "0 0 20px 0", display: "flex", alignItems: "center", gap: "8px" }}>
            <BarChart2 size={20} color="var(--color-success)" />
            스크리닝 결과 {results ? `(${results.length}종목 포착)` : ""}
          </h2>

          {isScreening ? (
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "400px", gap: "20px" }}>
              <RefreshCw className="animate-spin" size={48} color="var(--color-primary)" />
              <div style={{ fontSize: "1.2rem", fontWeight: 600, color: "var(--color-primary)" }}>선택하신 섹터의 모든 종목 차트를 스캔하고 있습니다...</div>
              <p style={{ color: "var(--color-muted)" }}>해당 섹터의 종목 수에 따라 5초 ~ 30초 정도 소요될 수 있습니다.</p>
            </div>
          ) : results === null ? (
            <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "400px", color: "var(--color-muted)", fontSize: "1.1rem" }}>
              좌측에서 조건을 설정한 후 스크리닝을 실행해주세요.
            </div>
          ) : results.length === 0 ? (
            <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "400px", color: "var(--color-warning)", fontSize: "1.1rem", flexDirection: "column", gap: "10px" }}>
              <div style={{ fontSize: "3rem" }}>📭</div>
              모든 조건을 만족하는 종목이 현재 없습니다.
            </div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ background: "var(--color-elevated)", borderBottom: "2px solid var(--color-border)", textAlign: "left" }}>
                    <th style={{ padding: "12px", color: "var(--color-muted)", fontWeight: 600 }}>종목</th>
                    <th style={{ padding: "12px", color: "var(--color-muted)", fontWeight: 600 }}>현재가</th>
                    <th style={{ padding: "12px", color: "var(--color-muted)", fontWeight: 600 }}>등락률</th>
                    <th style={{ padding: "12px", color: "var(--color-muted)", fontWeight: 600 }}>거래량</th>
                    <th style={{ padding: "12px", color: "var(--color-muted)", fontWeight: 600 }}>일치한 조건</th>
                  </tr>
                </thead>
                <tbody>
                  {results.map((res: any, idx: number) => {
                    const isUp = res.change_pct > 0;
                    const isDown = res.change_pct < 0;
                    const color = isUp ? "var(--color-danger)" : isDown ? "var(--color-primary)" : "var(--color-text)";
                    return (
                      <tr 
                        key={res.ticker} 
                        onClick={() => router.push(`/search?q=${res.ticker}&market=${market}`)}
                        style={{ borderBottom: "1px solid var(--color-border)", cursor: "pointer", transition: "background 0.2s" }} 
                        onMouseEnter={e => e.currentTarget.style.background="var(--color-elevated)"} 
                        onMouseLeave={e => e.currentTarget.style.background="transparent"}
                      >
                        <td style={{ padding: "16px 12px" }}>
                          <div style={{ display: "flex", alignItems: "baseline", gap: "6px", flexWrap: "wrap" }}>
                            <div style={{ fontWeight: 700, fontSize: "1.05rem" }}>{res.name}</div>
                            <div style={{ fontSize: "0.8rem", color: "var(--color-muted)" }}>{res.ticker}</div>
                          </div>
                          {/* 동적 섹터 배지 */}
                          {(() => {
                            const info = findSectorInfo(res.ticker);
                            if (!info) return null;
                            return (
                              <div style={{ display: "flex", gap: "4px", marginTop: "4px" }}>
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation(); // 테이블 행 클릭 이벤트(차트 이동) 차단
                                    setValChainTarget({ sector: info.sector, subSector: info.subSector });
                                  }}
                                  style={{
                                    fontSize: "0.72rem",
                                    fontWeight: 700,
                                    padding: "2px 6px",
                                    background: "rgba(139, 92, 246, 0.12)",
                                    border: "1px solid rgba(139, 92, 246, 0.35)",
                                    borderRadius: "4px",
                                    color: "#a78bfa",
                                    cursor: "pointer",
                                    transition: "all 0.2s"
                                  }}
                                  onMouseOver={(e) => {
                                    e.currentTarget.style.background = "rgba(139, 92, 246, 0.25)";
                                    e.currentTarget.style.borderColor = "rgba(139, 92, 246, 0.6)";
                                  }}
                                  onMouseOut={(e) => {
                                    e.currentTarget.style.background = "rgba(139, 92, 246, 0.12)";
                                    e.currentTarget.style.borderColor = "rgba(139, 92, 246, 0.35)";
                                  }}
                                  title={`${info.subSector} 밸류체인 관련주 보기`}
                                >
                                  🍇 {info.sector} › {info.subSector}
                                </button>
                              </div>
                            );
                          })()}
                        </td>
                        <td style={{ padding: "16px 12px", fontWeight: 600 }}>
                          {market === "KR" ? "₩" : "$"}{res.price.toLocaleString()}
                        </td>
                        <td style={{ padding: "16px 12px", fontWeight: 700, color }}>
                          {isUp ? "▲" : isDown ? "▼" : ""}{Math.abs(res.change_pct)}%
                        </td>
                        <td style={{ padding: "16px 12px", color: "var(--color-muted)" }}>
                          {res.volume.toLocaleString()}주
                        </td>
                        <td style={{ padding: "16px 12px" }}>
                          <div style={{ display: "flex", gap: "6px", flexWrap: "wrap", alignItems: "center" }}>
                            {res.matched.map((m: string) => (
                              <span key={m} style={{ background: "rgba(128,90,250,0.1)", color: "var(--color-primary)", padding: "4px 8px", borderRadius: "4px", fontSize: "0.8rem", fontWeight: 600 }}>
                                {m}
                              </span>
                            ))}
                            {res.reliability && res.reliability.win_rate != null && (
                              <span
                                title={(res.reliability.matched || []).map((x: any) => `${x.label} ${x.win_rate}%(${x.count})`).join(" · ") || "학습 승률"}
                                style={{
                                  padding: "4px 8px", borderRadius: "4px", fontSize: "0.78rem", fontWeight: 700,
                                  color: res.reliability.verdict === "good" ? "#34d399" : res.reliability.verdict === "avoid" ? "#f87171" : "#9ca3af",
                                  background: res.reliability.verdict === "good" ? "rgba(52,211,153,0.12)" : res.reliability.verdict === "avoid" ? "rgba(248,113,113,0.12)" : "rgba(156,163,175,0.12)",
                                  border: `1px solid ${res.reliability.verdict === "good" ? "rgba(52,211,153,0.4)" : res.reliability.verdict === "avoid" ? "rgba(248,113,113,0.4)" : "rgba(156,163,175,0.3)"}`,
                                }}
                              >
                                {res.reliability.verdict === "good" ? "✅" : res.reliability.verdict === "avoid" ? "⚠️" : "•"} 학습승률 {res.reliability.win_rate}%
                              </span>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* 밸류체인 원클릭 팝업 모달 */}
      <ValueChainModal
        isOpen={!!valChainTarget}
        onClose={() => setValChainTarget(null)}
        sector={valChainTarget?.sector ?? ""}
        subSector={valChainTarget?.subSector ?? ""}
        market={market}
        sectorMapData={sectorMapData}
      />
    </div>
  );
}

// /screener 라우트는 패널을 그대로 렌더 (대시보드 허브 탭에서도 동일 컴포넌트 재사용)
export default function ScreenerPage() {
  return <ScreenerPanel />;
}
