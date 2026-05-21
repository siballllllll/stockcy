"use client";
import { useState, useMemo, useEffect } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import { Activity, Flame, ChevronRight, ChevronDown, Bot } from "lucide-react";

export default function SectorsPage() {
  const [activeTab, setActiveTab] = useState<"hot" | "explore">("explore");
  
  // ── 1. 오늘의 핫 섹터 (SSE 분석용) ──
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [sectorData, setSectorData] = useState<any>(null);

  // ── 2. 전체 섹터 백과사전 데이터 ──
  const { data: sectorMap } = useSWR("/api/kr/sector-map", () => api.kr.sectorMap());
  
  // 캐시된 핫섹터 (불꽃 효과용)
  const { data: cachedHotSectors } = useSWR("/api/kr/hot-sectors", () => api.kr.hotSectors(), {
    revalidateOnFocus: false,
  });
  const hotThemes = useMemo(() => {
    const targetData = sectorData || cachedHotSectors;
    if (!targetData || !targetData.sectors) return [];
    return targetData.sectors.map((s: any) => s.name);
  }, [sectorData, cachedHotSectors]);

  // UI 상태
  const [selectedMainSector, setSelectedMainSector] = useState<string>("반도체");
  
  // 아코디언 열림/닫힘 상태 관리
  const [expandedSubSectors, setExpandedSubSectors] = useState<Record<string, boolean>>({});
  const toggleSubSector = (sub: string) => {
    setExpandedSubSectors(prev => ({ ...prev, [sub]: !prev[sub] }));
  };

  // 실시간 핫 섹터 분석 SSE 통신
  const fetchSectorRotation = async () => {
    setIsAnalyzing(true);
    setSectorData(null);
    try {
      const response = await fetch("http://localhost:8000/api/ai/sector-rotation");
      if (!response.body) throw new Error("No stream");
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() || "";
        
        for (const part of parts) {
          if (part.startsWith("data: ")) {
            try {
              const data = JSON.parse(part.slice(6));
              if (data.status === "done") {
                setSectorData(data.result);
                setIsAnalyzing(false);
              } else if (data.status === "error") {
                setIsAnalyzing(false);
              }
            } catch (e) {}
          }
        }
      }
    } catch (err) {
      setIsAnalyzing(false);
    }
  };

  return (
    <div style={{ maxWidth: "1200px", margin: "0 auto", padding: "1.5rem" }}>
      
      {/* ── 타이틀 ── */}
      <h1 style={{ fontSize: "1.8rem", fontWeight: 800, marginBottom: "1.5rem", display: "flex", alignItems: "center", gap: "8px" }}>
        <Flame color="var(--color-danger)" /> 이슈 섹터
      </h1>

      {/* ── 상단 탭 (사진과 동일한 스타일) ── */}
      <div style={{ display: "flex", gap: "1rem", marginBottom: "2rem" }}>
        <button
          onClick={() => setActiveTab("hot")}
          style={{ flex: 1, padding: "1rem", borderRadius: "8px", border: "1px solid", borderColor: activeTab === "hot" ? "var(--color-accent)" : "var(--color-border)", background: activeTab === "hot" ? "rgba(255,255,255,0.05)" : "var(--color-surface)", color: "var(--color-text)", fontWeight: 700, fontSize: "1rem", cursor: "pointer", transition: "0.2s" }}
        >
          📊 AI 시장분석
        </button>
        <button
          onClick={() => setActiveTab("explore")}
          style={{ flex: 1, padding: "1rem", borderRadius: "8px", border: "1px solid", borderColor: activeTab === "explore" ? "var(--color-accent)" : "var(--color-border)", background: activeTab === "explore" ? "rgba(255,255,255,0.05)" : "var(--color-surface)", color: "var(--color-text)", fontWeight: 700, fontSize: "1rem", cursor: "pointer", transition: "0.2s" }}
        >
          🗺️ 전체 섹터 탐색
        </button>
      </div>

      {/* ==============================================================
          전체 섹터 백과사전 탐색 영역 (사진 UI 구현)
      ============================================================== */}
      {activeTab === "explore" && (
        <div>
          <div style={{ fontSize: "0.9rem", color: "var(--color-muted)", marginBottom: "1rem" }}>
            섹터를 클릭해 종목을 탐색하세요 · 🔥 = 오늘의 이슈 섹터
          </div>

          <div style={{ marginBottom: "0.5rem", fontWeight: 700 }}>섹터 선택 (직접 선택)</div>
          
          {/* 대분류 셀렉트 박스 */}
          <select 
            value={selectedMainSector}
            onChange={(e) => setSelectedMainSector(e.target.value)}
            style={{ width: "100%", padding: "1rem", borderRadius: "8px", border: "1px solid var(--color-border)", background: "var(--color-surface)", color: "var(--color-text)", fontSize: "1rem", marginBottom: "1.5rem", outline: "none", cursor: "pointer" }}
          >
            {sectorMap && Object.keys(sectorMap).map(mainSec => (
              <option key={mainSec} value={mainSec}>{mainSec}</option>
            ))}
          </select>

          {/* 테이블 헤더 */}
          <div style={{ display: "grid", gridTemplateColumns: "60px 2fr 1fr 1fr 100px", padding: "10px 1rem", borderBottom: "1px solid var(--color-border)", fontSize: "0.85rem", color: "var(--color-muted)", fontWeight: 600 }}>
            <div>단타</div>
            <div>종목명</div>
            <div style={{ textAlign: "right" }}>현재가</div>
            <div style={{ textAlign: "right" }}>등락률</div>
            <div></div>
          </div>

          {/* 세부 섹터 리스트 */}
          {sectorMap && sectorMap[selectedMainSector] && Object.entries(sectorMap[selectedMainSector]).map(([subSector, stocks]: [string, any]) => {
            const isHot = hotThemes.includes(subSector);
            const isOpen = expandedSubSectors[subSector];

            return (
              <div key={subSector} style={{ borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
                {/* 섹터 행 (아코디언 헤더) */}
                <div 
                  onClick={() => toggleSubSector(subSector)}
                  style={{ display: "grid", gridTemplateColumns: "60px 2fr 1fr 1fr 100px", padding: "1rem", alignItems: "center", background: "var(--color-surface)", cursor: "pointer", transition: "0.2s" }}
                  className="hover-highlight"
                >
                  <div style={{ display: "flex", justifyContent: "center" }}>
                    {isOpen ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
                  </div>
                  
                  <div style={{ display: "flex", alignItems: "center", gap: "8px", fontWeight: 700, fontSize: "1.05rem" }}>
                    📌 {subSector} 
                    <span style={{ fontSize: "0.85rem", color: "var(--color-muted)", fontWeight: 500 }}>{stocks.length}개</span>
                    {isHot && <Flame size={14} color="var(--color-danger)" style={{ marginLeft: "4px" }} />}
                  </div>

                  <div style={{ textAlign: "right", color: "var(--color-muted)" }}>-</div>
                  {/* 섹터 평균 등락률 표시는 가격 데이터를 모두 로드해야 하므로 임시 생략(또는 개별 SWR로 갱신 가능) */}
                  <div style={{ textAlign: "right", fontWeight: 700, color: "var(--color-danger)" }}>+0.00%</div>

                  <div style={{ display: "flex", justifyContent: "flex-end" }}>
                    <button 
                      onClick={(e) => { e.stopPropagation(); alert(`${subSector} AI 분석 시작`); }}
                      style={{ padding: "4px 12px", background: "transparent", border: "1px solid var(--color-border)", borderRadius: "4px", color: "var(--color-text)", fontWeight: 600, display: "flex", alignItems: "center", gap: "4px", cursor: "pointer" }}
                    >
                      <Bot size={14} /> AI
                    </button>
                  </div>
                </div>

                {/* 아코디언 내용 (종목 리스트) */}
                {isOpen && (
                  <div style={{ background: "rgba(0,0,0,0.2)", padding: "0" }}>
                    {stocks.map((stock: any, i: number) => (
                      <SubSectorStockRow key={i} stock={stock} />
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* ==============================================================
          오늘의 주도 테마 (AI 로테이션) 영역
      ============================================================== */}
      {activeTab === "hot" && (
        <div>
          <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: "1.5rem" }}>
            <button className="stockcy-btn stockcy-btn-primary" onClick={fetchSectorRotation} disabled={isAnalyzing}>
              {isAnalyzing ? "실시간 분석 중..." : "🔄 AI 자금 흐름 분석 시작"}
            </button>
          </div>

          {!sectorData ? (
            <div className="stockcy-card" style={{ height: "400px", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
              {isAnalyzing ? (
                <div style={{ textAlign: "center" }}>
                  <div className="animate-spin" style={{ fontSize: "3rem", marginBottom: "1rem" }}>⏳</div>
                  <div style={{ fontSize: "1.2rem", fontWeight: 600 }}>실시간 자금 흐름 분석 중...</div>
                </div>
              ) : (
                <div style={{ color: "var(--color-muted)", textAlign: "center" }}>
                  <Flame size={48} style={{ marginBottom: "1rem", opacity: 0.5, margin: "0 auto" }} />
                  <div>'AI 자금 흐름 분석 시작' 버튼을 눌러 오늘의 주도 테마를 스캔하세요.</div>
                </div>
              )}
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
              <h3 style={{ margin: "0 0 0.5rem 0", color: "var(--color-danger)", display: "flex", alignItems: "center", gap: "8px" }}>
                <Flame size={20} /> HOT 섹터
              </h3>

              {sectorData?.sectors?.map((sec: Record<string, unknown>, idx: number) => {
                const bdr = sec.strength === "과열" ? "var(--color-danger)" : sec.strength === "확산" ? "var(--color-warning)" : "var(--color-success)";
                
                return (
                  <div key={idx} className="stockcy-card" style={{ border: `1px solid ${bdr}`, padding: "1.2rem", background: "rgba(255,255,255,0.02)" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "0.5rem" }}>
                      <h4 style={{ margin: 0, fontSize: "1.1rem", fontWeight: 700, display: "flex", alignItems: "center", gap: "6px" }}>
                        <Flame size={16} color={bdr} /> {sec.name as string} <span style={{ color: "var(--color-warning)", fontSize: "0.95rem" }}>[{sec.score as number}점]</span>
                      </h4>
                    </div>
                    <div style={{ color: "var(--color-subtle)", fontSize: "0.95rem", lineHeight: 1.5 }}>
                      {sec.reason as string}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// 개별 종목 행 컴포넌트 (가격과 등락률을 SWR로 비동기 로드)
function SubSectorStockRow({ stock }: { stock: any }) {
  // 실제로는 useSWR(`/api/kr/stocks/${stock.code}`) 을 호출하여 실시간 가격을 가져와야 함.
  // 여기서는 UI 틀을 먼저 맞춤.
  const { data } = useSWR(`/api/kr/stocks/${stock.code}`, () => api.kr.stockPrice(stock.code));

  const price = data ? (data.현재가 ?? 0) : 0;
  const change = data ? (data.등락률 ?? 0) : 0;
  const isUp = change > 0;
  const isDown = change < 0;
  const color = isUp ? "var(--color-danger)" : isDown ? "var(--color-primary)" : "var(--color-text)";

  return (
    <div style={{ display: "grid", gridTemplateColumns: "60px 2fr 1fr 1fr 100px", padding: "12px 1rem", borderBottom: "1px solid rgba(255,255,255,0.03)", fontSize: "0.95rem", alignItems: "center" }}>
      <div style={{ textAlign: "center" }}>
        <input type="checkbox" />
      </div>
      <div style={{ fontWeight: 600 }}>{stock.name}</div>
      <div style={{ textAlign: "right" }}>
        {data ? price.toLocaleString() : "..."}
      </div>
      <div style={{ textAlign: "right", color: color, fontWeight: 700 }}>
        {data ? `${change > 0 ? "+" : ""}${change.toFixed(2)}%` : "..."}
      </div>
      <div></div>
    </div>
  );
}
