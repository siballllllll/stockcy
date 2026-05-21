"use client";
import { useState, useEffect, useMemo } from "react";
import { useSearchParams } from "next/navigation";
import useSWR from "swr";
import { api } from "@/lib/api";
import { Search, Star, Briefcase, Bell, BarChart2, DollarSign, Activity, Loader2 } from "lucide-react";
import Chart from "@/components/Chart";

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
  const searchParams = useSearchParams();
  const [searchQuery, setSearchQuery] = useState("");
  const [activeTab, setActiveTab] = useState("시세");
  const [isSearching, setIsSearching] = useState(false);
  const [currentCode, setCurrentCode] = useState<string>("005930"); // 기본값 삼성전자
  const [chartType, setChartType] = useState<string>("daily"); // "minute" | "daily" | "weekly" | "monthly"
  const [minuteInterval, setMinuteInterval] = useState<number>(5); // 1, 5, 15, 30
  const [showDropdown, setShowDropdown] = useState(false);

  // 데이터 Fetching (API 연동)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const { data: stockData, error, isLoading } = useSWR<any>(`/api/kr/stocks/${currentCode}`, () => api.kr.stockPrice(currentCode));
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const { data: nameData } = useSWR<any>(`/api/kr/stocks/${currentCode}/name`, () => api.kr.stockName(currentCode));
  const { data: allStocks } = useSWR("/api/kr/stocks/all", () => api.kr.allStocks(), { revalidateOnFocus: false });
  
  // 차트 데이터 (일봉, 주봉, 월봉, 분봉)
  const { data: chartDataRaw } = useSWR(
    `/api/kr/chart/${currentCode}/${chartType}/${minuteInterval}`,
    () => {
      if (chartType === "minute") return api.kr.minuteChart(currentCode, minuteInterval);
      if (chartType === "weekly") return api.kr.dailyChart(currentCode, 600, "W");
      if (chartType === "monthly") return api.kr.dailyChart(currentCode, 600, "M");
      return api.kr.dailyChart(currentCode, 600, "D"); // 기본 일봉
    }
  );

  // 수급 데이터 (수급 탭이 활성화되었을 때만 fetch)
  const { data: invData, isLoading: invLoading } = useSWR(
    activeTab === "수급" ? `/api/kr/stocks/${currentCode}/investor-trend` : null,
    () => api.kr.stockInvestorTrendByCode(currentCode)
  );

  // 차트 데이터 파싱
  const chartData = useMemo(() => {
    if (!chartDataRaw || !Array.isArray(chartDataRaw)) return [];
    return chartDataRaw.map((d: any) => {
      const rawTime = d.일자 || d.date || d.날짜 || d.time || d.datetime || "";
      
      let finalTime: any = rawTime;
      if (chartType === "minute") {
        // 분봉은 Unix Timestamp (seconds)
        const dateObj = new Date(rawTime);
        finalTime = Math.floor(dateObj.getTime() / 1000) + (9 * 3600); // KST 조정
      } else {
        // 일봉, 주봉, 월봉은 YYYY-MM-DD
        finalTime = rawTime.split(" ")[0];
      }
      
      return {
        time: finalTime, 
        open: Number(d.open || d.시가 || 0),
        high: Number(d.high || d.고가 || 0),
        low: Number(d.low || d.저가 || 0),
        close: Number(d.close || d.종가 || 0),
        volume: Number(d.volume || d.거래량 || 0),
      };
    }).sort((a: any, b: any) => {
      const tA = typeof a.time === "number" ? a.time : new Date(a.time).getTime();
      const tB = typeof b.time === "number" ? b.time : new Date(b.time).getTime();
      return tA - tB;
    });
  }, [chartDataRaw, chartType]);

  // 자동완성 (초성 검색)
  const filteredStocks = useMemo(() => {
    if (!searchQuery.trim() || !allStocks) return [];
    
    const query = searchQuery.replace(/\s+/g, "").toLowerCase();
    const queryChosung = getChosung(query);
    
    const results = [];
    for (const [code, name] of Object.entries(allStocks as Record<string, string>)) {
      const nameSafe = name.replace(/\s+/g, "").toLowerCase();
      const nameChosung = getChosung(nameSafe);
      
      // 코드가 일치하거나, 이름이 일치하거나, 이름의 초성이 일치하면 매칭
      if (code.includes(query) || nameSafe.includes(query) || nameChosung.includes(queryChosung)) {
        results.push({ code, name });
      }
      if (results.length >= 10) break; // 최대 10개만 표시
    }
    return results;
  }, [searchQuery, allStocks]);

  const performSearch = (code: string) => {
    if (!code.trim()) return;
    setSearchQuery(""); // 검색창 비우기
    setShowDropdown(false);
    setIsSearching(true);
    setCurrentCode(code);
    setTimeout(() => setIsSearching(false), 500);
  };

  useEffect(() => {
    const q = searchParams.get("q");
    if (q) performSearch(q);
  }, [searchParams]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (filteredStocks.length > 0) {
      performSearch(filteredStocks[0].code); // 엔터 치면 자동완성 최상단 항목 검색
    } else {
      // 숫자 코드일 경우 그대로 시도
      if (searchQuery.match(/^\d+$/)) {
        performSearch(searchQuery);
      }
    }
  };

  // 실시간 가격 파싱
  const price = stockData?.price || 0;
  const change = stockData?.change_pct || 0;
  const changeVal = Math.abs(stockData?.change || 0);
  const isUp = change > 0;
  const isDown = change < 0;
  const color = isUp ? "var(--color-danger)" : isDown ? "var(--color-primary)" : "var(--color-text)";
  const changeStr = isUp ? "▲" : isDown ? "▼" : "━";

  // 가상의 타점 상태 로직 (백엔드 AI 분석 결과 모방)
  const isGoodBuy = change > 0 && change < 5; // 적당한 상승
  const isOverHeated = change >= 5; // 단기 과열
  
  return (
    <div style={{ width: "100%", margin: "0 auto" }}>
      
      {/* 전체 2단 레이아웃 (Grid) - 기존 스톡시 5:5 비율 복원 */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "2rem" }}>
        
        {/* ==========================================
            좌측: 차트 영역
        ========================================== */}
        <div className="stockcy-card" style={{ display: "flex", flexDirection: "column", padding: 0, minHeight: "700px" }}>
          {/* 헤더 */}
          <div style={{ padding: "1.5rem 1.5rem 1rem", borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
            <div style={{ display: "flex", alignItems: "baseline", gap: "10px", marginBottom: "0.25rem" }}>
              <h2 style={{ fontSize: "1.4rem", fontWeight: 800, margin: 0 }}>
                {nameData?.name ? nameData.name : (stockData?.name ? stockData.name : (isLoading ? "로딩중..." : "종목명"))}
              </h2>
              <span style={{ color: "var(--color-muted)", fontSize: "0.95rem" }}>({currentCode})</span>
              
              <div style={{ marginLeft: "0.5rem", fontSize: "1.4rem", fontWeight: 800 }}>
                ₩{price.toLocaleString()}
              </div>
              <div style={{ fontSize: "0.95rem", fontWeight: 700, color }}>
                {changeStr} {changeVal.toLocaleString()}원 ({change > 0 ? "+" : ""}{change.toFixed(2)}%)
              </div>
            </div>
            
            <div style={{ marginTop: "1rem", display: "flex", gap: "10px" }}>
              {/* 기간(일봉/분봉 등) 메인 선택기 */}
              <select 
                className="stockcy-input" 
                value={chartType}
                onChange={(e) => setChartType(e.target.value)}
                style={{ 
                  width: "100px", 
                  padding: "6px 10px", 
                  fontSize: "0.9rem",
                  background: "var(--color-surface-hover)",
                  border: "1px solid rgba(255,255,255,0.1)",
                  borderRadius: "4px",
                  color: "#fff"
                }}
              >
                <option value="minute">분봉</option>
                <option value="daily">일봉</option>
                <option value="weekly">주봉</option>
                <option value="monthly">월봉</option>
              </select>

              {/* 분봉 상세 간격 선택기 (조건부 렌더링) */}
              {chartType === "minute" && (
                <select 
                  className="stockcy-input" 
                  value={minuteInterval}
                  onChange={(e) => setMinuteInterval(Number(e.target.value))}
                  style={{ 
                    width: "80px", 
                    padding: "6px 10px", 
                    fontSize: "0.9rem",
                    background: "var(--color-surface-hover)",
                    border: "1px solid rgba(255,255,255,0.1)",
                    borderRadius: "4px",
                    color: "#fff"
                  }}
                >
                  <option value={1}>1분</option>
                  <option value={5}>5분</option>
                  <option value={15}>15분</option>
                  <option value={30}>30분</option>
                  <option value={60}>60분</option>
                </select>
              )}
            </div>

            {/* 탭 및 범례 영역 */}
            <div style={{ marginTop: "1.5rem" }}>
              {/* 차트 / 박스권·수급 분석 탭 */}
              <div style={{ display: "flex", gap: "1.5rem", borderBottom: "1px solid rgba(255,255,255,0.05)", paddingBottom: "0.5rem" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "6px", color: "var(--color-danger)", fontWeight: 700, cursor: "pointer", position: "relative" }}>
                  <span>📊 차트</span>
                  {/* 빨간색 밑줄 표시 (활성화 상태) */}
                  <div style={{ position: "absolute", bottom: "-0.5rem", left: 0, right: 0, height: "2px", background: "var(--color-danger)" }} />
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: "6px", color: "var(--color-text)", fontWeight: 600, cursor: "pointer", opacity: 0.8 }}>
                  <span>📦 박스권·수급 분석</span>
                </div>
              </div>

              {/* 이동평균선 안내 */}
              <div style={{ 
                marginTop: "1rem", 
                padding: "8px 12px", 
                background: "rgba(255,255,255,0.02)", 
                borderRadius: "4px",
                fontSize: "0.85rem",
                color: "rgba(255,255,255,0.6)",
                display: "flex",
                alignItems: "center",
                gap: "8px"
              }}>
                <span>ℹ️ 이동평균선 안내:</span>
                <span style={{ color: "#FACC15" }}>🟡5일(단기)</span> |
                <span style={{ color: "#EC4899" }}>💖20일(생명)</span> |
                <span style={{ color: "#22C55E" }}>🟢60일(수급)</span> |
                <span style={{ color: "#3B82F6" }}>🔵120일(경기)</span>
              </div>
            </div>
          </div>
          
          {/* 차트 영역 (실제 TradingView 차트 렌더링) */}
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


        {/* ==========================================
            우측: 상세 분석 및 타점 보드 영역
        ========================================== */}
        <div style={{ display: "flex", flexDirection: "column", gap: "1.2rem" }}>
          
          {/* 종목 검색창 (자동완성 드롭다운 포함) */}
          <div style={{ position: "relative" }}>
            <form onSubmit={handleSearch} style={{ position: "relative" }}>
              <div style={{ position: "absolute", left: "12px", top: "50%", transform: "translateY(-50%)", color: "var(--color-muted)" }}>
                <Search size={18} />
              </div>
              <input
                type="text"
                placeholder="종목 검색 (예: 삼성전자, ㅅㅅㅈㅈ, 005930)"
                value={searchQuery}
                onFocus={() => setShowDropdown(true)}
                onBlur={() => setTimeout(() => setShowDropdown(false), 200)}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  setShowDropdown(true);
                }}
                className="stockcy-input"
                style={{ paddingLeft: "36px", fontSize: "1rem", width: "100%", background: "var(--color-surface)", border: "1px solid var(--color-border)", padding: "12px 36px" }}
              />
            </form>
            
            {showDropdown && searchQuery && filteredStocks.length > 0 && (
              <div style={{ 
                position: "absolute", top: "100%", left: 0, right: 0, zIndex: 9999, 
                backgroundColor: "#0F172A", border: "1px solid #334155",
                borderRadius: "8px", marginTop: "4px", overflow: "hidden",
                boxShadow: "0 12px 32px rgba(0,0,0,0.8)"
              }}>
                {filteredStocks.map((item, idx) => (
                  <div 
                    key={item.code} 
                    onClick={() => performSearch(item.code)}
                    style={{ 
                      padding: "10px 16px", cursor: "pointer", 
                      borderBottom: idx < filteredStocks.length - 1 ? "1px solid rgba(255,255,255,0.05)" : "none",
                      display: "flex", justifyContent: "space-between"
                    }}
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

          {/* 3단 탭 */}
          <div style={{ display: "flex", gap: "10px" }}>
            {["시세", "수급", "AI 분석"].map(tab => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                style={{
                  flex: 1, padding: "8px", borderRadius: "6px", fontWeight: 700, fontSize: "0.85rem",
                  border: "1px solid", borderColor: activeTab === tab ? "var(--color-accent)" : "var(--color-border)",
                  background: activeTab === tab ? "rgba(255,255,255,0.05)" : "var(--color-surface)",
                  color: "var(--color-text)", cursor: "pointer", transition: "0.2s"
                }}
              >
                {tab === "시세" ? "📊 시세" : tab === "수급" ? "🔥 수급" : "🤖 AI 분석"}
              </button>
            ))}
          </div>

          {activeTab === "시세" && (
            <div className="stockcy-card" style={{ flex: 1, display: "flex", flexDirection: "column", gap: "1.2rem", padding: "1.5rem" }}>
              
              {/* 즐겨찾기 / 포트폴리오 액션 버튼 */}
              <div style={{ display: "flex", gap: "10px" }}>
                <button className="stockcy-btn" style={{ flex: 1, padding: "8px", fontSize: "0.95rem", display: "flex", justifyContent: "center", gap: "6px", background: "var(--color-elevated)", border: "1px solid var(--color-border)" }}>
                  <Star size={14} color="var(--color-warning)" /> 즐겨찾기
                </button>
                <button className="stockcy-btn" style={{ flex: 1, padding: "6px", fontSize: "0.85rem", display: "flex", justifyContent: "center", gap: "6px", background: "var(--color-elevated)", border: "1px solid var(--color-border)" }}>
                  <Briefcase size={14} color="var(--color-danger)" /> 포트폴리오
                </button>
              </div>

              {/* 시세 요약 헤더 (우측 상단) */}
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: "6px", marginBottom: "0.25rem" }}>
                  <h3 style={{ fontSize: "0.95rem", fontWeight: 700, margin: 0 }}>{nameData?.name ? nameData.name : (stockData?.name || "...")}</h3>
                  <span style={{ fontSize: "0.75rem", background: "rgba(255,255,255,0.1)", padding: "2px 4px", borderRadius: "2px" }}>반도체</span>
                </div>
                <div style={{ fontSize: "1.4rem", fontWeight: 800 }}>
                  ₩{price.toLocaleString()}
                  <span style={{ fontSize: "0.9rem", color, marginLeft: "6px", fontWeight: 700 }}>
                    {changeStr} {changeVal.toLocaleString()}원 ({change > 0 ? "+" : ""}{change.toFixed(2)}%)
                  </span>
                </div>
              </div>

              {/* 스탯 테이블 (Grid) */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "0.5rem", rowGap: "0.75rem", fontSize: "0.85rem" }}>
                <div>
                  <div style={{ color: "var(--color-muted)", fontSize: "0.75rem" }}>거래량</div>
                  <div style={{ fontWeight: 700 }}>{stockData?.거래량?.toLocaleString() || 0}주</div>
                </div>
                <div>
                  <div style={{ color: "var(--color-muted)", fontSize: "0.75rem" }}>거래대금</div>
                  <div style={{ fontWeight: 700 }}>₩{((stockData?.거래량 || 0) * price / 100000000).toLocaleString(undefined, {maximumFractionDigits:0})}억</div>
                </div>
                <div>
                  <div style={{ color: "var(--color-muted)", fontSize: "0.75rem" }}>시가총액</div>
                  <div style={{ fontWeight: 700 }}>₩3,900조</div>
                </div>
                <div>
                  <div style={{ color: "var(--color-muted)", fontSize: "0.75rem" }}>시가</div>
                  <div style={{ fontWeight: 700 }}>₩{stockData?.시가?.toLocaleString() || 0}</div>
                </div>
                <div>
                  <div style={{ color: "var(--color-muted)", fontSize: "0.75rem" }}>고가</div>
                  <div style={{ fontWeight: 700 }}>₩{stockData?.고가?.toLocaleString() || 0}</div>
                </div>
                <div>
                  <div style={{ color: "var(--color-muted)", fontSize: "0.75rem" }}>저가</div>
                  <div style={{ fontWeight: 700 }}>₩{stockData?.저가?.toLocaleString() || 0}</div>
                </div>
                <div>
                  <div style={{ color: "var(--color-muted)", fontSize: "0.75rem" }}>PER</div>
                  <div style={{ fontWeight: 700 }}>{stockData?.PER || "N/A"}</div>
                </div>
                <div>
                  <div style={{ color: "var(--color-muted)", fontSize: "0.75rem" }}>PBR</div>
                  <div style={{ fontWeight: 700 }}>{stockData?.PBR || "N/A"}</div>
                </div>
                <div>
                  <div style={{ color: "var(--color-muted)", fontSize: "0.75rem" }}>52주 최고</div>
                  <div style={{ fontWeight: 700, color: "var(--color-danger)" }}>₩{stockData?.['52주최고가']?.toLocaleString() || price}</div>
                </div>
              </div>

              {/* 52주 가격 바 */}
              <div style={{ marginTop: "0.5rem" }}>
                <div style={{ fontSize: "0.75rem", color: "var(--color-muted)", marginBottom: "4px" }}>52주 가격 위치</div>
                <div style={{ position: "relative", height: "4px", background: "rgba(255,255,255,0.1)", borderRadius: "2px", margin: "0.75rem 0" }}>
                  <div style={{ position: "absolute", left: "0", top: 0, height: "100%", width: "80%", background: "var(--color-danger)", borderRadius: "2px" }}></div>
                  <div style={{ position: "absolute", left: "80%", top: "-8px", fontSize: "0.75rem", color: "var(--color-danger)", fontWeight: 700 }}>80%</div>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.75rem", color: "var(--color-muted)" }}>
                  <span>최저 ₩{stockData?.['52주최저가']?.toLocaleString() || 0}</span>
                  <span>최고 ₩{stockData?.['52주최고가']?.toLocaleString() || price}</span>
                </div>
              </div>
              
              <div style={{ display: "flex", alignItems: "center", gap: "6px", color: "var(--color-warning)", fontSize: "0.8rem", cursor: "pointer", fontWeight: 600 }}>
                <Bell size={14} /> 가격 알림 설정
              </div>

              {/* =====================================
                  미니 타점 보드 (4구획)
              ===================================== */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: "6px", marginTop: "auto" }}>
                {/* 극단타 */}
                <div style={{ background: "rgba(255,255,255,0.03)", border: `1px solid ${isOverHeated ? "var(--color-warning)" : "var(--color-success)"}`, borderRadius: "6px", padding: "8px" }}>
                  <div style={{ fontSize: "0.75rem", color: "var(--color-muted)", marginBottom: "2px" }}>극단타</div>
                  <div style={{ fontWeight: 700, fontSize: "0.8rem", color: isOverHeated ? "var(--color-warning)" : "var(--color-success)", marginBottom: "4px" }}>
                    {isOverHeated ? "🟡 단기 과열 주의" : "🟢 극단타 적극 대응"}
                  </div>
                  <div style={{ fontSize: "0.7rem", color: "var(--color-subtle)", lineHeight: 1.3 }}>
                    {isOverHeated ? "차익 매물 출회 가능성." : "모멘텀 확보. 매수 유효."}
                  </div>
                </div>
                
                {/* 단기 */}
                <div style={{ background: "rgba(255,255,255,0.03)", border: `1px solid ${isGoodBuy ? "var(--color-success)" : "var(--color-danger)"}`, borderRadius: "6px", padding: "8px" }}>
                  <div style={{ fontSize: "0.75rem", color: "var(--color-muted)", marginBottom: "2px" }}>단기</div>
                  <div style={{ fontWeight: 700, fontSize: "0.8rem", color: isGoodBuy ? "var(--color-success)" : "var(--color-danger)", marginBottom: "4px" }}>
                    {isGoodBuy ? "🟢 강력 단기 추천" : "🔴 추격 매수 자제"}
                  </div>
                  <div style={{ fontSize: "0.7rem", color: "var(--color-subtle)", lineHeight: 1.3 }}>
                    {isGoodBuy ? "추세 상방 전환 확인." : "하방 압력. 지지선 확인."}
                  </div>
                </div>

                {/* 중기 */}
                <div style={{ background: "rgba(255,255,255,0.03)", border: "1px solid var(--color-danger)", borderRadius: "6px", padding: "8px" }}>
                  <div style={{ fontSize: "0.75rem", color: "var(--color-muted)", marginBottom: "2px" }}>중기</div>
                  <div style={{ fontWeight: 700, fontSize: "0.8rem", color: "var(--color-danger)", marginBottom: "4px" }}>
                    🔴 중기 고평가
                  </div>
                  <div style={{ fontSize: "0.7rem", color: "var(--color-subtle)", lineHeight: 1.3 }}>
                    고점 근접. 진입 부담.
                  </div>
                </div>

                {/* 장기 */}
                <div style={{ background: "rgba(255,255,255,0.03)", border: "1px solid var(--color-danger)", borderRadius: "6px", padding: "8px" }}>
                  <div style={{ fontSize: "0.75rem", color: "var(--color-muted)", marginBottom: "2px" }}>장기</div>
                  <div style={{ fontWeight: 700, fontSize: "0.8rem", color: "var(--color-danger)", marginBottom: "4px" }}>
                    🔴 장기 고평가
                  </div>
                  <div style={{ fontSize: "0.7rem", color: "var(--color-subtle)", lineHeight: 1.3 }}>
                    PER/PBR 밴드 최상단.
                  </div>
                </div>
              </div>
            </div>
          )}

          {activeTab === "수급" && (
            <div className="stockcy-card" style={{ flex: 1, display: "flex", flexDirection: "column", padding: "1.5rem" }}>
              <h3 style={{ fontSize: "1.1rem", fontWeight: 700, marginBottom: "1rem" }}>💰 외국인/기관 최근 10일 수급 동향</h3>
              {(() => {
                
                if (invLoading) return <div style={{ padding: "2rem", textAlign: "center", color: "var(--color-muted)" }}><Loader2 className="animate-spin inline" /> 수급 데이터 불러오는 중...</div>;
                if (!invData || !Array.isArray(invData) || invData.length === 0) return <div style={{ color: "var(--color-muted)" }}>수급 데이터가 없습니다.</div>;

                return (
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
                          const chgColor = row.change_pct > 0 ? "var(--color-danger)" : row.change_pct < 0 ? "var(--color-primary)" : "var(--color-text)";
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
                );
              })()}
            </div>
          )}

          {activeTab === "AI 분석" && (
            <div className="stockcy-card" style={{ flex: 1, display: "flex", flexDirection: "column", padding: "1.5rem" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
                <h3 style={{ fontSize: "1.1rem", fontWeight: 700, margin: 0 }}>🧠 AI 심층 리포트 및 타점 분석</h3>
                <button 
                  onClick={async () => {
                    const statusDiv = document.getElementById("ai-status");
                    const contentDiv = document.getElementById("ai-content");
                    if (statusDiv) statusDiv.innerText = "분석을 준비중입니다...";
                    if (contentDiv) contentDiv.innerHTML = "";
                    
                    try {
                      const payload = {
                        code: currentCode,
                        name: nameData?.name || stockData?.name || currentCode,
                        price_data: stockData || {},
                        investor_data: []
                      };
                      
                      const res = await fetch((process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000") + "/api/ai/kr-stock-report", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify(payload)
                      });
                      
                      if (!res.body) throw new Error("No body");
                      const reader = res.body.getReader();
                      const decoder = new TextDecoder();
                      let resultMd = "";
                      
                      while (true) {
                        const { value, done } = await reader.read();
                        if (done) break;
                        const chunk = decoder.decode(value);
                        const lines = chunk.split("\n");
                        
                        for (const line of lines) {
                          if (line.startsWith("data: ")) {
                            try {
                              const parsed = JSON.parse(line.slice(6));
                              if (parsed.status === "running") {
                                if (statusDiv) statusDiv.innerHTML = `<span class="animate-pulse">⏳ ${parsed.message}</span>`;
                              } else if (parsed.status === "done") {
                                if (statusDiv) statusDiv.innerHTML = "<span style='color:var(--color-success)'>✅ 분석 완료</span>";
                                resultMd = parsed.result?.report || JSON.stringify(parsed.result);
                                if (contentDiv) contentDiv.innerHTML = `<pre style="white-space: pre-wrap; font-family: inherit; line-height: 1.6; font-size: 0.95rem;">${resultMd}</pre>`;
                              } else if (parsed.status === "error") {
                                if (statusDiv) statusDiv.innerHTML = `<span style='color:var(--color-primary)'>❌ 에러: ${parsed.message}</span>`;
                              }
                            } catch(e) {}
                          }
                        }
                      }
                    } catch (err: any) {
                      if (statusDiv) statusDiv.innerText = `오류가 발생했습니다: ${err.message}`;
                    }
                  }}
                  className="stockcy-btn-primary"
                  style={{ padding: "8px 16px", borderRadius: "6px", fontSize: "0.9rem", fontWeight: 600, display: "flex", gap: "6px", alignItems: "center" }}
                >
                  <Activity size={16} /> 분석 실행
                </button>
              </div>
              
              <div id="ai-status" style={{ fontSize: "0.9rem", color: "var(--color-warning)", fontWeight: 600, marginBottom: "1rem" }}>
                상단의 '분석 실행' 버튼을 눌러주세요. (약 30~50초 소요)
              </div>
              
              <div id="ai-content" style={{ padding: "1.5rem", background: "rgba(0,0,0,0.2)", borderRadius: "8px", minHeight: "200px" }}>
                <div style={{ color: "var(--color-muted)", textAlign: "center", marginTop: "3rem" }}>AI 리포트가 이곳에 표시됩니다.</div>
              </div>
            </div>
          )}

        </div>
      </div>
    </div>
  );
}
