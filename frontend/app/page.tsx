"use client";
import { useState } from "react";
import { PicksBoard } from "@/components/picks/PicksBoard";
import { useSSE } from "@/hooks/useSSE";
import { SSEPanel } from "@/components/ui/SSEPanel";

type Tab = "picks" | "rotation" | "mypattern";

const TABS: { id: Tab; label: string }[] = [
  { id: "picks",     label: "🎯 AI 타점 포착" },
  { id: "rotation",  label: "📊 섹터 순환매" },
  { id: "mypattern", label: "🧠 내 패턴 스크리너" },
];

export default function Dashboard() {
  const [activeTab, setActiveTab] = useState<Tab>("picks");

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
            <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.83rem", lineHeight: 1.8, color: "var(--color-text)", fontFamily: "inherit" }}>
              {data}
            </pre>
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
            <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
              {data.profile_summary && (
                <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", padding: "0.75rem", background: "rgba(124,58,237,0.08)", borderRadius: "8px", border: "1px solid rgba(124,58,237,0.2)" }}>
                  <span style={{ fontSize: "0.75rem", color: "#a78bfa", fontWeight: 600, width: "100%", marginBottom: "2px" }}>학습된 패턴 기준</span>
                  {[
                    { label: "기반 거래", value: `${data.profile_summary.total_trades}건` },
                    { label: "승률",     value: `${data.profile_summary.win_rate_pct}%` },
                    { label: "평균수익", value: `${data.profile_summary.avg_profit_pct}%` },
                    { label: "업데이트", value: String(data.profile_summary.updated_time ?? "").slice(0, 10) },
                  ].map(s => (
                    <div key={s.label} style={{ textAlign: "center", padding: "4px 12px", background: "rgba(0,0,0,0.2)", borderRadius: "6px" }}>
                      <div style={{ fontSize: "0.65rem", color: "var(--color-muted)" }}>{s.label}</div>
                      <div style={{ fontWeight: 700, fontSize: "0.85rem", color: "#e2e8f0" }}>{s.value}</div>
                    </div>
                  ))}
                </div>
              )}
              {data.top_picks?.length > 0 && (
                <div>
                  <div style={{ fontSize: "0.78rem", fontWeight: 600, color: "var(--color-muted)", marginBottom: "0.5rem" }}>패턴 매칭 상위 종목</div>
                  <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
                    {data.top_picks.map((p: any, i: number) => (
                      <div key={p.code} style={{ display: "flex", alignItems: "center", gap: "0.75rem", padding: "0.6rem 0.9rem", background: "var(--color-elevated)", borderRadius: "7px", flexWrap: "wrap" }}>
                        <span style={{ width: "22px", height: "22px", borderRadius: "50%", background: i === 0 ? "#7c3aed" : i === 1 ? "#4f46e5" : "var(--color-surface)", color: "white", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "0.72rem", fontWeight: 700, flexShrink: 0 }}>{i + 1}</span>
                        <div style={{ flex: 1, minWidth: "120px" }}>
                          <span style={{ fontWeight: 700 }}>{p.name}</span>
                          <span style={{ fontSize: "0.75rem", color: "var(--color-muted)", marginLeft: "6px" }}>{p.code}</span>
                        </div>
                        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                          <span style={{ fontSize: "0.72rem", padding: "1px 7px", borderRadius: "10px", background: "rgba(124,58,237,0.2)", color: "#c4b5fd", fontWeight: 600 }}>매칭 {p.match_score}점</span>
                          {p.rsi != null && <span style={{ fontSize: "0.72rem", color: "var(--color-muted)" }}>RSI {p.rsi}</span>}
                          {p.vol_ratio != null && <span style={{ fontSize: "0.72rem", color: "var(--color-muted)" }}>거래량 {p.vol_ratio}배</span>}
                          {p.ma_aligned && <span style={{ fontSize: "0.7rem", padding: "1px 6px", borderRadius: "8px", background: "rgba(5,150,105,0.15)", color: "#34d399" }}>MA정배열</span>}
                          {p.signal === "both" && <span style={{ fontSize: "0.7rem", padding: "1px 6px", borderRadius: "8px", background: "rgba(245,158,11,0.15)", color: "#fbbf24" }}>이중신호</span>}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {data.ai_narrative && (
                <div style={{ background: "rgba(0,0,0,0.2)", borderRadius: "8px", padding: "1rem 1.2rem" }}>
                  <div style={{ fontSize: "0.75rem", fontWeight: 600, color: "#a78bfa", marginBottom: "0.5rem" }}>AI 진입 전략</div>
                  <div style={{ fontSize: "0.84rem", color: "var(--color-text)", lineHeight: 1.75, whiteSpace: "pre-wrap" }}>
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
