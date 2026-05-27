"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import ReactMarkdown from "react-markdown";
import { BarChart2, Zap } from "lucide-react";
import { PicksBoard } from "@/components/picks/PicksBoard";
import { useSSE } from "@/hooks/useSSE";
import { SSEPanel } from "@/components/ui/SSEPanel";
import { StockModal } from "@/components/ui/StockModal";
import type { StockInfo } from "@/components/ui/StockModal";

function getPickStatus(rsi?: number, signal?: string) {
  if (rsi != null) {
    if (rsi <= 30) return { label: "🔵 과매도 (반등 확인)", color: "#2b7cff", bg: "rgba(43,124,255,0.12)", border: "rgba(43,124,255,0.4)" };
    if (rsi <= 45) return { label: "💎 매수 구간",          color: "#00c853", bg: "rgba(0,200,83,0.12)",   border: "rgba(0,200,83,0.4)"   };
    if (rsi <= 60) return { label: "🟢 모멘텀 유지",        color: "#4ade80", bg: "rgba(74,222,128,0.12)", border: "rgba(74,222,128,0.4)" };
    if (rsi <= 75) return { label: "⚠️ 과열 접근",          color: "#ff9800", bg: "rgba(255,152,0,0.12)",  border: "rgba(255,152,0,0.4)"  };
    return               { label: "🔥 과열 (추격 신중)",    color: "#ff4b4b", bg: "rgba(255,75,75,0.12)",  border: "rgba(255,75,75,0.4)"  };
  }
  if (signal === "both") return { label: "⚡ 이중 신호",   color: "#fbbf24", bg: "rgba(251,191,36,0.12)", border: "rgba(251,191,36,0.4)" };
  return                        { label: "⚪ 관망",         color: "#888",    bg: "rgba(150,150,150,0.10)", border: "rgba(150,150,150,0.3)" };
}

type Tab = "picks" | "rotation" | "mypattern";

const TABS: { id: Tab; label: string }[] = [
  { id: "picks",     label: "🎯 AI 타점 포착" },
  { id: "rotation",  label: "📊 섹터 순환매" },
  { id: "mypattern", label: "🧠 내 패턴 스크리너" },
];

export default function Dashboard() {
  const router = useRouter();
  const [activeTab,     setActiveTab]     = useState<Tab>("picks");
  const [selectedStock, setSelectedStock] = useState<StockInfo | null>(null);

  const rotation = useSSE<string>(
    "/api/ai/sector-rotation",
    { globalId: "sector-rotation", globalTitle: "섹터 순환 분析" }
  );
  const myPick = useSSE<{ profile_summary: any; top_picks: any[]; ai_narrative: string }>(
    "/api/ai/pattern-screener",
    { method: "POST", globalId: "pattern-screener", globalTitle: "내 패턴 스크리너" }
  );

  return (
    <div className="flex flex-col gap-6 animate-in fade-in duration-300">

      {selectedStock && <StockModal stock={selectedStock} onClose={() => setSelectedStock(null)} />}

      {/* 탭 네비게이션 */}
      <div style={{ display: "flex", gap: "6px", flexWrap: "wrap", borderBottom: "1px solid rgba(255,255,255,0.05)", paddingBottom: "1rem" }}>
        {TABS.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-2 text-sm font-bold rounded-lg transition-colors ${
              activeTab === tab.id
                ? "bg-white/10 text-white border border-white/20"
                : "text-gray-400 hover:text-white"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* AI 타점 포착 — display:none으로 마운트 유지 (SSE 분析 중 탭 이동 가능) */}
      <div style={{ display: activeTab === "picks" ? "block" : "none" }}>
        <PicksBoard />
      </div>

      {/* 섹터 순환매 */}
      {activeTab === "rotation" && (
        <SSEPanel<string>
          status={rotation.status} message={rotation.message}
          result={rotation.result} fromCache={rotation.fromCache} completedAt={rotation.completedAt}
          onStart={rotation.start} startLabel="섹터 로테이션 분析"
          idleHint="실시간 시장 데이터를 기반으로 현재 주도 섹터와 다음 자금 이동 경로, 투자 성향별 추천 종목을 분析합니다. (1~2분 소요)"
        >
          {(data) => (
            <div className="stockcy-markdown">
              <ReactMarkdown
                components={{
                  h1: ({ children }) => (
                    <h1 style={{ fontSize: "1.15rem", fontWeight: 800, color: "var(--color-text)", borderBottom: "2px solid var(--color-accent)", paddingBottom: "0.5rem", marginBottom: "1.2rem", marginTop: "1.5rem" }}>{children}</h1>
                  ),
                  h2: ({ children }) => (
                    <h2 style={{ fontSize: "1rem", fontWeight: 700, color: "var(--color-accent)", marginBottom: "0.75rem", marginTop: "1.5rem", display: "flex", alignItems: "center", gap: "0.4rem" }}>{children}</h2>
                  ),
                  h3: ({ children }) => (
                    <h3 style={{ fontSize: "0.9rem", fontWeight: 700, color: "#a78bfa", marginBottom: "0.5rem", marginTop: "1rem" }}>{children}</h3>
                  ),
                  p: ({ children }) => (
                    <p style={{ fontSize: "0.87rem", lineHeight: 1.85, color: "var(--color-muted)", marginBottom: "0.6rem" }}>{children}</p>
                  ),
                  ul: ({ children }) => (
                    <ul style={{ paddingLeft: "1.2rem", marginBottom: "0.75rem", display: "flex", flexDirection: "column", gap: "0.3rem" }}>{children}</ul>
                  ),
                  li: ({ children }) => (
                    <li style={{ fontSize: "0.87rem", lineHeight: 1.8, color: "var(--color-muted)", listStyleType: "disc" }}>{children}</li>
                  ),
                  strong: ({ children }) => (
                    <strong style={{ color: "var(--color-text)", fontWeight: 700 }}>{children}</strong>
                  ),
                  blockquote: ({ children }) => (
                    <blockquote style={{ borderLeft: "3px solid var(--color-accent)", paddingLeft: "1rem", margin: "0.75rem 0", background: "rgba(255,255,255,0.03)", borderRadius: "0 6px 6px 0", padding: "0.6rem 1rem" }}>{children}</blockquote>
                  ),
                  hr: () => (
                    <hr style={{ border: "none", borderTop: "1px solid var(--color-border)", margin: "1.5rem 0" }} />
                  ),
                  code: ({ children }) => (
                    <code style={{ background: "rgba(255,255,255,0.08)", borderRadius: "4px", padding: "1px 6px", fontSize: "0.82rem", color: "#fbbf24", fontFamily: "monospace" }}>{children}</code>
                  ),
                }}
              >
                {data}
              </ReactMarkdown>
            </div>
          )}
        </SSEPanel>
      )}

      {/* 내 패턴 스크리너 */}
      {activeTab === "mypattern" && (
        <SSEPanel
          status={myPick.status} message={myPick.message}
          result={myPick.result} fromCache={myPick.fromCache} completedAt={myPick.completedAt}
          onStart={myPick.start} startLabel="내 패턴으로 종목 찾기"
          idleHint="내 거래 기록에서 승률이 높았던 매매 조건을 학습하고, 오늘 시장에서 그 조건에 가장 근접한 단기 유망 종목을 찾습니다. (1~2분 소요)"
        >
          {(data) => (
            <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>

              {/* 프로필 요약 */}
              {data.profile_summary && (() => {
                const ps = data.profile_summary;
                const winRate = Number(ps.win_rate_pct ?? 0);
                const reliabilityColor = winRate >= 60 ? "#34d399" : winRate >= 50 ? "#fbbf24" : winRate >= 40 ? "#fb923c" : "#f87171";
                return (
                  <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "0.75rem" }}>
                      {[
                        { label: "기반 거래",  value: `${ps.total_trades}건`,  color: "var(--color-text)" },
                        { label: "승률",       value: `${winRate}%`,            color: reliabilityColor },
                        { label: "평균 수익",  value: `+${ps.avg_profit_pct}%`, color: "#34d399" },
                        { label: "프로필 갱신", value: String(ps.updated_time ?? "").slice(0, 10), color: "var(--color-muted)" },
                      ].map(s => (
                        <div key={s.label} style={{ background: "rgba(124,58,237,0.08)", border: "1px solid rgba(124,58,237,0.2)", borderRadius: "8px", padding: "0.75rem", textAlign: "center" }}>
                          <div style={{ fontSize: "0.7rem", color: "#a78bfa", marginBottom: "4px" }}>{s.label}</div>
                          <div style={{ fontSize: "1.1rem", fontWeight: 800, color: s.color }}>{s.value}</div>
                        </div>
                      ))}
                    </div>
                    {/* 신뢰도 경고 배너 */}
                    {ps.reliability_warning && (
                      <div style={{ background: "rgba(251,146,60,0.12)", border: "1px solid rgba(251,146,60,0.35)", borderRadius: "6px", padding: "0.5rem 0.75rem", fontSize: "0.78rem", color: "#fb923c", display: "flex", alignItems: "center", gap: "0.4rem" }}>
                        ⚠️ {ps.reliability_warning}
                      </div>
                    )}
                  </div>
                );
              })()}

              {/* 매칭 종목 카드 그리드 */}
              {data.top_picks?.length > 0 && (
                <div>
                  <div style={{ fontSize: "0.8rem", fontWeight: 700, color: "var(--color-muted)", marginBottom: "0.75rem", display: "flex", alignItems: "center", gap: "0.4rem" }}>
                    🎯 패턴 매칭 상위 종목
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: "0.75rem" }}>
                    {data.top_picks.map((p: any, i: number) => {
                      const score      = Number(p.match_score ?? 0);
                      const rankColors = ["#7c3aed", "#4f46e5", "#0369a1"];
                      const rankColor  = rankColors[i] ?? "var(--color-surface)";
                      const scoreBg    = score >= 80 ? "rgba(34,197,94,0.12)"  : score >= 60 ? "rgba(234,179,8,0.12)"  : "rgba(255,255,255,0.05)";
                      const scoreColor = score >= 80 ? "#4ade80"               : score >= 60 ? "#fbbf24"               : "var(--color-muted)";
                      const status     = getPickStatus(p.rsi, p.signal);
                      return (
                        <div key={p.code} style={{ background: "var(--color-elevated)", border: `1px solid ${i < 3 ? rankColor + "55" : "var(--color-border)"}`, borderTop: `3px solid ${rankColor}`, borderRadius: "8px", padding: "0.9rem", display: "flex", flexDirection: "column", gap: "0.6rem" }}>

                          {/* 상단: 순위 + 종목명 + 점수 */}
                          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                            <span style={{ width: "22px", height: "22px", borderRadius: "50%", background: rankColor, color: "white", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "0.72rem", fontWeight: 800, flexShrink: 0 }}>{i + 1}</span>
                            <div style={{ flex: 1, minWidth: 0 }}>
                              <div style={{ fontWeight: 700, fontSize: "0.95rem", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{p.name}</div>
                              <div style={{ fontSize: "0.72rem", color: "var(--color-muted)" }}>{p.code}</div>
                            </div>
                            <div style={{ background: scoreBg, color: scoreColor, fontWeight: 800, fontSize: "0.85rem", padding: "2px 8px", borderRadius: "6px", flexShrink: 0 }}>{score}점</div>
                          </div>

                          {/* 상태 배지 */}
                          <span style={{ fontSize: "0.72rem", padding: "3px 10px", borderRadius: "99px", background: status.bg, color: status.color, border: `1px solid ${status.border}`, fontWeight: 700, alignSelf: "flex-start" }}>
                            {status.label}
                          </span>

                          {/* 지표 뱃지 */}
                          <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap" }}>
                            {p.rsi != null && (
                              <span style={{ fontSize: "0.72rem", padding: "2px 7px", borderRadius: "6px", background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.1)", color: "var(--color-muted)" }}>RSI {p.rsi}</span>
                            )}
                            {p.vol_ratio != null && (
                              <span style={{ fontSize: "0.72rem", padding: "2px 7px", borderRadius: "6px", background: "rgba(99,102,241,0.15)", border: "1px solid rgba(99,102,241,0.25)", color: "#a5b4fc" }}>거래량 {p.vol_ratio}배</span>
                            )}
                            {p.ma_aligned && (
                              <span style={{ fontSize: "0.72rem", padding: "2px 7px", borderRadius: "6px", background: "rgba(5,150,105,0.15)", border: "1px solid rgba(5,150,105,0.25)", color: "#34d399" }}>MA정배열</span>
                            )}
                            {p.signal === "both" && (
                              <span style={{ fontSize: "0.72rem", padding: "2px 7px", borderRadius: "6px", background: "rgba(245,158,11,0.15)", border: "1px solid rgba(245,158,11,0.25)", color: "#fbbf24" }}>이중신호</span>
                            )}
                          </div>

                          {/* 액션 버튼 */}
                          <div style={{ display: "flex", gap: "5px" }}>
                            <button
                              className="stockcy-btn stockcy-btn-secondary"
                              style={{ flex: 1, padding: "5px 4px", fontSize: "0.71rem", display: "flex", alignItems: "center", justifyContent: "center", gap: "3px" }}
                              onClick={() => router.push(`/search?q=${p.code}&market=KR`)}
                            >
                              <BarChart2 size={11} /> 차트보기
                            </button>
                            <button
                              className="stockcy-btn stockcy-btn-secondary"
                              style={{ flex: 1, padding: "5px 4px", fontSize: "0.71rem", display: "flex", alignItems: "center", justifyContent: "center", gap: "3px" }}
                              onClick={() => {
                                const ctx = [
                                  `패턴 매칭 점수: ${p.match_score}점`,
                                  p.rsi != null   ? `RSI: ${p.rsi}` : null,
                                  p.vol_ratio != null ? `거래량 비율: ${p.vol_ratio}배` : null,
                                  p.ma_aligned    ? "MA 정배열 확인됨" : null,
                                  p.signal === "both" ? "거래량 급증+등락률 상위 이중 신호" : `신호 유형: ${p.signal}`,
                                ].filter(Boolean).join(" / ");
                                setSelectedStock({ code: p.code, name: p.name, market: "국내", patternContext: ctx });
                              }}
                            >
                              <Zap size={11} /> AI분석
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* AI 진입 전략 */}
              {data.ai_narrative && (
                <div style={{ background: "rgba(124,58,237,0.06)", border: "1px solid rgba(124,58,237,0.2)", borderRadius: "10px", padding: "1.1rem 1.3rem" }}>
                  <div style={{ fontSize: "0.78rem", fontWeight: 700, color: "#a78bfa", marginBottom: "0.75rem", display: "flex", alignItems: "center", gap: "0.4rem" }}>
                    🧠 AI 진입 전략
                  </div>
                  <div style={{ fontSize: "0.87rem", color: "var(--color-text)", lineHeight: 1.85, whiteSpace: "pre-wrap" }}>
                    {data.ai_narrative}
                  </div>
                </div>
              )}
            </div>
          )}
        </SSEPanel>
      )}
    </div>
  );
}
