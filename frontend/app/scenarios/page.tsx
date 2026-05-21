"use client";
import { useState, useEffect } from "react";
import { Globe, TrendingUp, AlertTriangle, ChevronRight, Activity, DollarSign, Loader2 } from "lucide-react";
import { connectSSE, api } from "@/lib/api";
import useSWR from "swr";

export default function ScenariosPage() {
  const [activeRegion, setActiveRegion] = useState("글로벌 (미국)");
  const [loading, setLoading] = useState(true);
  const [statusMsg, setStatusMsg] = useState("AI 매크로 분석 준비 중...");
  const [scenarios, setScenarios] = useState<any>(null);

  const { data: us } = useSWR("us-indices", () => api.us.indices() as Promise<any>, { refreshInterval: 60000 });

  useEffect(() => {
    let unmounted = false;
    setLoading(true);
    setStatusMsg("AI 모델에 연결 중...");
    
    connectSSE(
      "/api/ai/scenarios",
      (evt) => {
        if (unmounted) return;
        if (evt.status === "running") {
          setStatusMsg(evt.message || "분석 중...");
        } else if (evt.status === "done") {
          setScenarios(evt.result);
          setLoading(false);
        } else if (evt.status === "error") {
          setStatusMsg(`오류 발생: ${evt.message}`);
          setLoading(false);
        }
      }
    ).catch((err) => {
      if (!unmounted) {
        setStatusMsg("연결 실패");
        setLoading(false);
      }
    });

    return () => { unmounted = true; };
  }, []);

  const issues: any[] = scenarios?.issues ?? [];
  const [issueIdx, setIssueIdx] = useState(0);
  const mainIssue = issues[issueIdx];

  return (
    <div style={{ width: "100%", margin: "0 auto", display: "flex", flexDirection: "column", gap: "1rem" }}>
      
      {/* 상단 헤더 영역 */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", borderBottom: "1px solid rgba(255,255,255,0.05)", paddingBottom: "1rem" }}>
        <div>
          <h1 style={{ fontSize: "1.6rem", fontWeight: 800, margin: "0 0 0.5rem 0", display: "flex", alignItems: "center", gap: "8px" }}>
            <Globe color="var(--color-info)" /> 매크로 시나리오 분석
          </h1>
          <div style={{ fontSize: "0.85rem", color: "var(--color-muted)" }}>
            글로벌 경제 지표와 연준의 동향을 분석하여 최적의 투자 비중과 전략을 제시합니다.
          </div>
        </div>
        
        {/* 지역 탭 버튼들 */}
        <div style={{ display: "flex", gap: "6px" }}>
          {["글로벌 (미국)", "국내 (한국)", "이머징 마켓"].map(r => (
            <button
              key={r}
              onClick={() => setActiveRegion(r)}
              style={{
                padding: "6px 12px",
                fontSize: "0.85rem",
                fontWeight: 700,
                borderRadius: "4px",
                border: "1px solid",
                borderColor: activeRegion === r ? "var(--color-accent)" : "var(--color-border)",
                background: activeRegion === r ? "rgba(255,255,255,0.1)" : "transparent",
                color: activeRegion === r ? "var(--color-text)" : "var(--color-muted)",
                cursor: "pointer",
                transition: "0.2s"
              }}
            >
              {r}
            </button>
          ))}
        </div>
      </div>

      {/* 2단 데스크보드 레이아웃 */}
      <div style={{ display: "grid", gridTemplateColumns: "3fr 7fr", gap: "1.5rem" }}>
        
        {/* =====================================
            좌측: 시장 지표 미니 위젯 모음 (Dense)
        ===================================== */}
        <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
          
          <div className="stockcy-card" style={{ padding: "12px", display: "flex", flexDirection: "column", gap: "10px" }}>
            <div style={{ fontSize: "0.85rem", fontWeight: 800, color: "var(--color-muted)", display: "flex", alignItems: "center", gap: "4px" }}>
              <TrendingUp size={14}/> 주요 지수 (미국 마감)
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", borderBottom: "1px solid rgba(255,255,255,0.05)", paddingBottom: "6px" }}>
              <span style={{ fontSize: "0.85rem", fontWeight: 700 }}>S&P 500</span>
              <span style={{ fontSize: "0.85rem", fontWeight: 800, color: (us?.["S&P 500"]?.change_pct ?? 0) >= 0 ? "var(--color-up)" : "var(--color-down)" }}>
                {us?.["S&P 500"] ? `${us["S&P 500"].price.toLocaleString()} (${us["S&P 500"].change_pct.toFixed(2)}%)` : "조회중"}
              </span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", borderBottom: "1px solid rgba(255,255,255,0.05)", paddingBottom: "6px" }}>
              <span style={{ fontSize: "0.85rem", fontWeight: 700 }}>NASDAQ</span>
              <span style={{ fontSize: "0.85rem", fontWeight: 800, color: (us?.NASDAQ?.change_pct ?? 0) >= 0 ? "var(--color-up)" : "var(--color-down)" }}>
                {us?.NASDAQ ? `${us.NASDAQ.price.toLocaleString()} (${us.NASDAQ.change_pct.toFixed(2)}%)` : "조회중"}
              </span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span style={{ fontSize: "0.85rem", fontWeight: 700 }}>VIX (공포지수)</span>
              <span style={{ fontSize: "0.85rem", fontWeight: 800, color: "var(--color-muted)" }}>
                {us?.VIX ? `${us.VIX.price} (${us.VIX.change_pct.toFixed(2)}%)` : "조회중"}
              </span>
            </div>
          </div>

          <div className="stockcy-card" style={{ padding: "12px", display: "flex", flexDirection: "column", gap: "10px" }}>
            <div style={{ fontSize: "0.85rem", fontWeight: 800, color: "var(--color-muted)", display: "flex", alignItems: "center", gap: "4px" }}>
              <DollarSign size={14}/> 환율 및 채권
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", borderBottom: "1px solid rgba(255,255,255,0.05)", paddingBottom: "6px" }}>
              <span style={{ fontSize: "0.85rem", fontWeight: 700 }}>원/달러 환율</span>
              <span style={{ fontSize: "0.85rem", fontWeight: 800, color: "var(--color-warning)" }}>1,365.20 (보합)</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span style={{ fontSize: "0.85rem", fontWeight: 700 }}>미 10년물 국채금리</span>
              <span style={{ fontSize: "0.85rem", fontWeight: 800, color: "var(--color-primary)" }}>4.425% (-1.2bp)</span>
            </div>
          </div>

          <div className="stockcy-card" style={{ padding: "12px", border: "1px solid var(--color-warning)", background: "rgba(255, 180, 50, 0.05)" }}>
            <div style={{ fontSize: "0.85rem", fontWeight: 800, color: "var(--color-warning)", display: "flex", alignItems: "center", gap: "4px", marginBottom: "8px" }}>
              <AlertTriangle size={14}/> 시장 경보 수준: 낮음
            </div>
            <div style={{ fontSize: "0.75rem", color: "var(--color-subtle)", lineHeight: 1.4 }}>
              금리 인하 기대감이 유지되며 시장의 변동성(VIX)은 역사적 최저 수준을 기록 중입니다. 시스템 리스크 징후는 발견되지 않았습니다.
            </div>
          </div>
          
          <button className="stockcy-btn" style={{ padding: "10px", fontSize: "0.85rem", display: "flex", justifyContent: "center", alignItems: "center", gap: "6px", width: "100%" }}>
            <Activity size={14} /> 최신 데이터 업데이트
          </button>
        </div>

        {/* =====================================
            우측: AI 매크로 리포트 영역
        ===================================== */}
        <div className="stockcy-card" style={{ padding: "2rem", display: "flex", flexDirection: "column", gap: "1rem", minHeight: "500px" }}>
          
          {loading ? (
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", gap: "1rem" }}>
              <Loader2 className="animate-spin" size={32} color="var(--color-accent)" />
              <div style={{ color: "var(--color-muted)", fontSize: "0.9rem", fontWeight: 600 }}>{statusMsg}</div>
            </div>
          ) : !mainIssue ? (
            <div style={{ color: "var(--color-muted)", textAlign: "center", marginTop: "2rem" }}>시나리오 데이터를 불러오지 못했습니다.</div>
          ) : (
            <>
              {/* 이슈 탭 선택 (최대 6개) */}
              {issues.length > 1 && (
                <div style={{ display: "flex", gap: "6px", flexWrap: "wrap", marginBottom: "0.5rem" }}>
                  {issues.map((issue: any, idx: number) => (
                    <button
                      key={idx}
                      onClick={() => setIssueIdx(idx)}
                      style={{
                        padding: "4px 10px", fontSize: "0.78rem", fontWeight: 600, borderRadius: "4px",
                        border: "1px solid", cursor: "pointer",
                        borderColor: issueIdx === idx ? "var(--color-accent)" : "var(--color-border)",
                        background: issueIdx === idx ? "rgba(255,255,255,0.08)" : "transparent",
                        color: issueIdx === idx ? "var(--color-text)" : "var(--color-muted)",
                      }}
                    >
                      Issue {idx + 1}: {String(issue.title ?? "").slice(0, 20)}{String(issue.title ?? "").length > 20 ? "…" : ""}
                    </button>
                  ))}
                </div>
              )}

              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "1rem" }}>
                <div>
                  <span style={{ fontSize: "0.8rem", color: "var(--color-accent)", fontWeight: 700, padding: "4px 8px", background: "rgba(255,255,255,0.05)", borderRadius: "4px", marginBottom: "8px", display: "inline-block" }}>
                    Daily Macro Issue #{issueIdx + 1}
                  </span>
                  <h2 style={{ fontSize: "1.4rem", fontWeight: 800, margin: 0 }}>
                    {mainIssue.title}
                  </h2>
                </div>
              </div>

              <div style={{ background: "rgba(255, 60, 60, 0.1)", borderLeft: "4px solid var(--color-danger)", padding: "12px 16px", borderRadius: "4px", color: "var(--color-text)", fontSize: "0.95rem", fontWeight: 600, lineHeight: 1.5 }}>
                {mainIssue.summary}
              </div>

              <div style={{ fontSize: "0.95rem", color: "var(--color-text)", lineHeight: 1.7, marginTop: "1rem" }}>
                <h3 style={{ fontSize: "1.1rem", fontWeight: 800, color: "var(--color-text)", borderBottom: "1px solid rgba(255,255,255,0.1)", paddingBottom: "8px", marginBottom: "12px" }}>
                  1. 시나리오 A (낙관) - {mainIssue.scenarios[0]?.probability_pct}%
                </h3>
                <div style={{ paddingLeft: "0.5rem", marginBottom: "1.5rem" }}>
                  <div style={{ fontWeight: 700, color: "var(--color-success)", marginBottom: "4px" }}>
                    {mainIssue.scenarios[0]?.title}
                  </div>
                  <p style={{ color: "var(--color-subtle)", fontSize: "0.9rem" }}>{mainIssue.scenarios[0]?.economic_analysis}</p>
                  
                  <div style={{ display: "flex", gap: "10px", marginTop: "10px", flexWrap: "wrap" }}>
                    {mainIssue.scenarios[0]?.theme_stocks?.map((st: any) => (
                      <span key={st.ticker} style={{ padding: "2px 8px", background: "rgba(255,255,255,0.05)", borderRadius: "4px", fontSize: "0.8rem" }}>
                        {st.name} <span style={{ color: "var(--color-muted)" }}>{st.ticker}</span>
                      </span>
                    ))}
                  </div>
                </div>

                {mainIssue.scenarios[1] && (
                  <>
                    <h3 style={{ fontSize: "1.1rem", fontWeight: 800, color: "var(--color-text)", borderBottom: "1px solid rgba(255,255,255,0.1)", paddingBottom: "8px", marginBottom: "12px" }}>
                      2. 시나리오 B (비관) - {mainIssue.scenarios[1]?.probability_pct}%
                    </h3>
                    <div style={{ paddingLeft: "0.5rem", marginBottom: "1.5rem" }}>
                      <div style={{ fontWeight: 700, color: "var(--color-warning)", marginBottom: "4px" }}>
                        {mainIssue.scenarios[1]?.title}
                      </div>
                      <p style={{ color: "var(--color-subtle)", fontSize: "0.9rem" }}>{mainIssue.scenarios[1]?.economic_analysis}</p>
                    </div>
                  </>
                )}
              </div>
            </>
          )}
        </div>
      </div>

    </div>
  );
}
