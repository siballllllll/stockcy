"use client";
import { useState, useEffect } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";

export default function PicksPage() {
  const [activeTab, setActiveTab] = useState<"picks" | "tracking">("picks");
  const [subTab, setSubTab] = useState<"holdings" | "history">("holdings");

  // 타점 보드 상태
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analyzeMsg, setAnalyzeMsg] = useState("");
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [picksData, setPicksData] = useState<any>(null);
  const [selectedIdx, setSelectedIdx] = useState(0);

  // 성과 트래킹 SWR
  const { data: portfolio, mutate: refreshPortfolio } = useSWR("/api/portfolio", () => api.portfolio.loadPortfolio());
  const { data: tradeData, mutate: refreshTrades } = useSWR("/api/trades", () => api.portfolio.loadTrades());

  const startAnalysis = async () => {
    setIsAnalyzing(true);
    setPicksData(null);
    setAnalyzeMsg("🔥 국내 실시간 AI 픽 분석 중...");

    try {
      const response = await fetch("http://localhost:8000/api/ai/realtime-picks-kr", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ market_data: {}, volume_rank: [], change_rank: [], hot_sectors: [], investor_rank: [] }),
      });

      if (!response.body) throw new Error("No readable stream");
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
              if (data.status === "running") {
                setAnalyzeMsg(data.message);
              } else if (data.status === "done") {
                setPicksData(data.result);
                setIsAnalyzing(false);
              } else if (data.status === "error") {
                setAnalyzeMsg(`❌ 오류 발생: ${data.message}`);
                setIsAnalyzing(false);
              }
            } catch (e) {
              console.error(e);
            }
          }
        }
      }
    } catch (err) {
      setAnalyzeMsg("❌ 분석 중 치명적 오류 발생");
      setIsAnalyzing(false);
    }
  };

  return (
    <div style={{ maxWidth: "1400px", margin: "0 auto", padding: "1.5rem" }}>
      {/* ── 상단 탭 ── */}
      <div style={{ display: "flex", gap: "1rem", borderBottom: "1px solid var(--color-border)", marginBottom: "1.5rem" }}>
        <button
          onClick={() => setActiveTab("picks")}
          className={activeTab === "picks" ? "tab-active" : "tab-inactive"}
          style={{ padding: "0.75rem 1.5rem", fontSize: "1.1rem", fontWeight: 700, background: "transparent", border: "none", cursor: "pointer", borderBottom: activeTab === "picks" ? "2px solid var(--color-accent)" : "2px solid transparent" }}
        >
          🎯 AI 타점 보드
        </button>
        <button
          onClick={() => setActiveTab("tracking")}
          className={activeTab === "tracking" ? "tab-active" : "tab-inactive"}
          style={{ padding: "0.75rem 1.5rem", fontSize: "1.1rem", fontWeight: 700, background: "transparent", border: "none", cursor: "pointer", borderBottom: activeTab === "tracking" ? "2px solid var(--color-accent)" : "2px solid transparent" }}
        >
          📈 성과 트래킹
        </button>
      </div>

      {/* ── AI 타점 보드 영역 ── */}
      {activeTab === "picks" && (
        <div style={{ display: "flex", gap: "1.5rem" }}>
          {/* 좌측 리스트 */}
          <div style={{ flex: "0 0 40%", display: "flex", flexDirection: "column", gap: "1rem" }}>
            <button className="stockcy-btn stockcy-btn-primary" onClick={startAnalysis} disabled={isAnalyzing} style={{ justifyContent: "center", padding: "12px" }}>
              {isAnalyzing ? "분석 중..." : "🔄 AI 타점 분석 실행"}
            </button>
            
            {isAnalyzing && (
              <div className="stockcy-box stockcy-box-info animate-pulse" style={{ padding: "2rem", textAlign: "center" }}>
                <div style={{ fontSize: "2rem", marginBottom: "1rem" }}>🤖</div>
                <div style={{ fontWeight: 600 }}>{analyzeMsg}</div>
              </div>
            )}

            {picksData && !isAnalyzing && (
              <div className="stockcy-card" style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                <div style={{ color: "var(--color-accent)", fontWeight: 700, marginBottom: "0.5rem" }}>
                  {picksData.market_condition}
                </div>
                {picksData.picks?.map((pick: Record<string, unknown>, idx: number) => {
                  const entry = Number(pick.entry ?? 0);
                  const changePct = Number(pick.change_pct ?? 0);
                  return (
                  <div
                    key={idx}
                    onClick={() => setSelectedIdx(idx)}
                    style={{
                      padding: "12px", borderRadius: "8px", cursor: "pointer",
                      background: selectedIdx === idx ? "rgba(255,75,75,0.1)" : "var(--color-surface)",
                      border: selectedIdx === idx ? "1px solid var(--color-accent)" : "1px solid var(--color-border)"
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "4px" }}>
                      <span style={{ fontWeight: 700, fontSize: "1.05rem" }}>{String(pick.name ?? "")}</span>
                      <span style={{ color: "var(--color-muted)", fontSize: "0.85rem" }}>{String(pick.code ?? "")}</span>
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.9rem" }}>
                      <span>매수 ₩{entry.toLocaleString()}</span>
                      <span className={changePct >= 0 ? "price-up" : "price-down"}>
                        {changePct >= 0 ? "▲" : "▼"}{Math.abs(changePct).toFixed(2)}%
                      </span>
                    </div>
                  </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* 우측 상세 카드 */}
          <div style={{ flex: "1", display: "flex", flexDirection: "column", gap: "1rem" }}>
            {!picksData ? (
              <div className="stockcy-card" style={{ height: "400px", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", color: "var(--color-muted)" }}>
                <div style={{ fontSize: "4rem", marginBottom: "1rem" }}>📊</div>
                <div>좌측에서 AI 분석을 실행하면 종목 상세가 여기에 표시됩니다.</div>
              </div>
            ) : (
              picksData.picks?.[selectedIdx] && (
                <div className="stockcy-card" style={{ padding: "1.5rem" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "1rem" }}>
                    <div>
                      <h2 style={{ fontSize: "1.5rem", fontWeight: 800, margin: 0, color: "var(--color-text)" }}>
                        {picksData.picks[selectedIdx].name}
                      </h2>
                      <div style={{ color: "var(--color-subtle)" }}>{picksData.picks[selectedIdx].code}</div>
                    </div>
                    <div style={{ textAlign: "right" }}>
                      <div style={{ background: "rgba(255,152,0,0.15)", color: "#ff9800", padding: "4px 8px", borderRadius: "6px", fontWeight: 700, marginBottom: "4px" }}>
                        ⚡ {picksData.picks[selectedIdx].urgency || "즉시 진입"}
                      </div>
                      <div style={{ color: "var(--color-success)", fontWeight: 600 }}>
                        {picksData.picks[selectedIdx].horizon || "단기"}
                      </div>
                    </div>
                  </div>

                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px", marginBottom: "1.5rem" }}>
                    <div style={{ gridColumn: "span 2", background: "var(--color-surface)", border: "1px solid var(--color-border)", padding: "15px", borderRadius: "8px", textAlign: "center" }}>
                      <div style={{ color: "var(--color-muted)", fontSize: "0.9rem", marginBottom: "5px" }}>적정 매수 타점</div>
                      <div style={{ fontSize: "1.4rem", fontWeight: 800 }}>₩{parseInt(picksData.picks[selectedIdx].entry || 0).toLocaleString()}</div>
                    </div>
                    <div style={{ background: "rgba(33, 195, 84, 0.1)", border: "1px solid var(--color-success)", padding: "15px", borderRadius: "8px", textAlign: "center" }}>
                      <div style={{ color: "var(--color-success)", fontSize: "0.9rem", marginBottom: "5px" }}>목표가</div>
                      <div style={{ fontSize: "1.2rem", fontWeight: 800, color: "var(--color-success)" }}>₩{parseInt(picksData.picks[selectedIdx].target || 0).toLocaleString()}</div>
                    </div>
                    <div style={{ background: "rgba(255, 75, 75, 0.1)", border: "1px solid var(--color-danger)", padding: "15px", borderRadius: "8px", textAlign: "center" }}>
                      <div style={{ color: "var(--color-danger)", fontSize: "0.9rem", marginBottom: "5px" }}>손절가</div>
                      <div style={{ fontSize: "1.2rem", fontWeight: 800, color: "var(--color-danger)" }}>₩{parseInt(picksData.picks[selectedIdx].stop || 0).toLocaleString()}</div>
                    </div>
                  </div>

                  <div style={{ background: "var(--color-surface)", padding: "1rem", borderRadius: "8px", color: "var(--color-muted)", lineHeight: "1.6" }}>
                    {picksData.picks[selectedIdx].reason}
                  </div>
                  
                  <div style={{ marginTop: "1.5rem", display: "flex", gap: "10px" }}>
                     <button className="stockcy-btn stockcy-btn-primary" style={{ flex: 1, justifyContent: "center" }}>🎒 포트폴리오 편입</button>
                     <button className="stockcy-btn stockcy-btn-secondary" style={{ flex: 1, justifyContent: "center" }}>📊 차트 보기</button>
                  </div>
                </div>
              )
            )}
          </div>
        </div>
      )}

      {/* ── 성과 트래킹 영역 ── */}
      {activeTab === "tracking" && (
        <div className="stockcy-card">
          <div style={{ display: "flex", gap: "1rem", marginBottom: "1rem" }}>
            <button onClick={() => setSubTab("holdings")} className={subTab === "holdings" ? "stockcy-btn stockcy-btn-primary" : "stockcy-btn stockcy-btn-secondary"}>
              📈 보유 종목
            </button>
            <button onClick={() => setSubTab("history")} className={subTab === "history" ? "stockcy-btn stockcy-btn-primary" : "stockcy-btn stockcy-btn-secondary"}>
              📋 거래 내역
            </button>
          </div>

          <table className="stockcy-table">
            <thead>
              {subTab === "holdings" ? (
                <tr><th>종목명</th><th>티커</th><th>매수가</th><th>수량</th><th>상태</th></tr>
              ) : (
                <tr><th>종목명</th><th>매수/매도가</th><th>수익금</th><th>수익률</th><th>매도일</th></tr>
              )}
            </thead>
            <tbody>
              {subTab === "holdings" && (portfolio as Record<string, unknown>[] | undefined)?.map((p, i) => (
                <tr key={i}>
                  <td style={{ fontWeight: 600 }}>{String(p.name ?? "")}</td>
                  <td>{String(p.ticker ?? "")}</td>
                  <td>{String(p.buy_price ?? "")}</td>
                  <td>{String(p.quantity ?? "")}</td>
                  <td>{String(p.rating ?? "")}</td>
                </tr>
              ))}
              {subTab === "history" && ((tradeData as { data?: Record<string, unknown>[] } | undefined)?.data)?.map((t, i) => {
                const profit = Number(t.profit ?? 0);
                const profitPct = Number(t.profit_pct ?? 0);
                return (
                <tr key={i}>
                  <td style={{ fontWeight: 600 }}>{String(t.name ?? "")}</td>
                  <td>{String(t.buy_price ?? "")} → {String(t.sell_price ?? "")}</td>
                  <td className={profit >= 0 ? "price-up" : "price-down"}>{profit}</td>
                  <td className={profitPct >= 0 ? "price-up" : "price-down"}>{profitPct}%</td>
                  <td>{String(t.sell_date ?? "")}</td>
                </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
