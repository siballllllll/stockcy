"use client";

import { useState } from "react";
import { useSSE } from "@/hooks/useSSE";
import { SSEPanel } from "@/components/ui/SSEPanel";
import { MarkdownLite } from "@/components/ui/MarkdownLite";
import { AiCostBadge } from "@/components/ui/AiCostBadge";

/**
 * 수급 이동 감지 패널 (KR/US).
 * 오늘 거래량·등락률 + 외국인/기관 순매수(KR) / yfinance 기관·공매도·거래량 급증(US)을
 * 종합해 "지금 돈이 어느 종목/섹터로 들어오나"를 실시간 포착한다.
 * (대시보드에서 시나리오 → 시장 인사이트 영역으로 흡수)
 */
export function SupplyRotationPanel() {
  const supplyRotation = useSSE<{ narrative: string; vol_ranking: any[]; chg_up: any[]; chg_dn: any[]; frgn_inst?: any }>(
    "/api/ai/supply-rotation-detect",
    { method: "POST", globalId: "supply-rotation", globalTitle: "수급 이동 감지 (KR)" }
  );
  const supplyRotationUs = useSSE<{ narrative: string; stocks: any[]; analyzed_count: number }>(
    "/api/ai/supply-rotation-detect/us",
    { method: "POST", globalId: "supply-rotation-us", globalTitle: "수급 이동 감지 (US)" }
  );
  const [supplyMarket, setSupplyMarket] = useState<"kr" | "us">("kr");

  return (
    <div>
      <div style={{ display: "flex", gap: "6px", marginBottom: "0.75rem" }}>
        {(["kr", "us"] as const).map((m) => (
          <button
            key={m}
            onClick={() => setSupplyMarket(m)}
            style={{ fontSize: "0.78rem", padding: "5px 12px", borderRadius: "6px", border: "1px solid", borderColor: supplyMarket === m ? "rgba(245,158,11,0.55)" : "rgba(255,255,255,0.08)", background: supplyMarket === m ? "rgba(245,158,11,0.15)" : "transparent", color: supplyMarket === m ? "#fbbf24" : "var(--color-muted)", fontWeight: 800, cursor: "pointer" }}
          >
            {m === "kr" ? "🇰🇷 국내 시장" : "🇺🇸 미국 시장"}
          </button>
        ))}
      </div>

      {supplyMarket === "kr" && (
        <SSEPanel
          status={supplyRotation.status} message={supplyRotation.message}
          result={supplyRotation.result} fromCache={supplyRotation.fromCache} completedAt={supplyRotation.completedAt}
          onStart={supplyRotation.start} startLabel="수급 이동 분석 시작 (국내)"
          idleHint="오늘의 거래량·등락률·외국인/기관 데이터와 뉴스를 종합해 어느 종목/섹터에서 수급이 이탈/유입 중인지 실시간 분석합니다. (1~2분 소요)"
        >
          {(data) => (
            <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>

              {/* AI 수급 이동 분석 */}
              {data.narrative && (
                <div style={{ background: "rgba(245,158,11,0.05)", border: "1px solid rgba(245,158,11,0.15)", borderRadius: "10px", padding: "1.1rem 1.3rem" }}>
                  <div style={{ fontSize: "0.78rem", fontWeight: 700, color: "#fbbf24", marginBottom: "0.75rem" }}>🔄 AI 수급 이동 분석 <AiCostBadge small /></div>
                  <MarkdownLite text={data.narrative} style={{ fontSize: "0.87rem", color: "var(--color-text)", lineHeight: 1.85 }} />
                </div>
              )}
            </div>
          )}
        </SSEPanel>
      )}

      {/* 미국 수급 이동 감지 */}
      {supplyMarket === "us" && (
        <SSEPanel
          status={supplyRotationUs.status} message={supplyRotationUs.message}
          result={supplyRotationUs.result} fromCache={supplyRotationUs.fromCache} completedAt={supplyRotationUs.completedAt}
          onStart={supplyRotationUs.start} startLabel="수급 이동 분석 시작 (미국)"
          idleHint="포트폴리오·즐겨찾기에 있는 미국 종목의 yfinance 기관/내부자 보유 비율 + 공매도 + 거래량 급증 데이터를 분석합니다. (1~2분 소요)"
        >
          {(data) => (
            <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
              {/* 종목 카드 그리드 */}
              {data.stocks?.length > 0 && (
                <div>
                  <div style={{ fontSize: "0.78rem", fontWeight: 700, color: "var(--color-muted)", marginBottom: "0.6rem" }}>
                    🇺🇸 분석 종목 ({data.analyzed_count}개 중 거래량 급증 TOP {data.stocks.length})
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: "0.6rem" }}>
                    {data.stocks.map((s: any) => {
                      const up = s.change_pct > 0;
                      const high_inst = s.institutional_pct >= 60;
                      const high_short = s.float_short_pct >= 10;
                      const vol_spike = s.vol_ratio >= 1.5;
                      return (
                        <div key={s.ticker} style={{ background: "var(--color-elevated)", border: "1px solid var(--color-border)", borderRadius: "8px", padding: "0.7rem 0.85rem" }}>
                          <div style={{ display: "flex", alignItems: "baseline", gap: "6px", marginBottom: "5px" }}>
                            <span style={{ fontWeight: 700, color: "var(--color-text)" }}>{s.ticker}</span>
                            <span style={{ fontSize: "0.7rem", color: "var(--color-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.name}</span>
                            <span style={{ fontSize: "0.72rem", color: up ? "#34d399" : "#f87171", fontWeight: 700, marginLeft: "auto" }}>{up ? "+" : ""}{s.change_pct}%</span>
                          </div>
                          <div style={{ display: "flex", flexWrap: "wrap", gap: "4px", fontSize: "0.65rem" }}>
                            {vol_spike && <span style={{ background: "rgba(245,158,11,0.15)", color: "#fbbf24", padding: "1px 6px", borderRadius: "4px", fontWeight: 700, border: "1px solid rgba(245,158,11,0.3)" }}>거래량 {s.vol_ratio}배</span>}
                            {high_inst && <span style={{ background: "rgba(99,102,241,0.15)", color: "#a5b4fc", padding: "1px 6px", borderRadius: "4px", fontWeight: 700, border: "1px solid rgba(99,102,241,0.3)" }}>기관 {s.institutional_pct}%</span>}
                            {high_short && <span style={{ background: "rgba(239,68,68,0.15)", color: "#f87171", padding: "1px 6px", borderRadius: "4px", fontWeight: 700, border: "1px solid rgba(239,68,68,0.3)" }}>공매도 {s.float_short_pct}%</span>}
                            {s.insider_pct >= 3 && <span style={{ background: "rgba(16,185,129,0.15)", color: "#34d399", padding: "1px 6px", borderRadius: "4px", fontWeight: 700, border: "1px solid rgba(16,185,129,0.3)" }}>내부자 {s.insider_pct}%</span>}
                            {s.sector && <span style={{ background: "rgba(255,255,255,0.04)", color: "var(--color-muted)", padding: "1px 6px", borderRadius: "4px" }}>{s.sector}</span>}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* AI 분석 */}
              {data.narrative && (
                <div style={{ background: "rgba(245,158,11,0.05)", border: "1px solid rgba(245,158,11,0.15)", borderRadius: "10px", padding: "1.1rem 1.3rem" }}>
                  <div style={{ fontSize: "0.78rem", fontWeight: 700, color: "#fbbf24", marginBottom: "0.75rem" }}>🇺🇸 AI 수급 이동 분석 <AiCostBadge small /></div>
                  <MarkdownLite text={data.narrative} style={{ fontSize: "0.87rem", color: "var(--color-text)", lineHeight: 1.85 }} />
                </div>
              )}
            </div>
          )}
        </SSEPanel>
      )}
    </div>
  );
}
