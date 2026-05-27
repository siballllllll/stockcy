"use client";
import { useState } from "react";
import { TrendingUp, Zap, Users, BarChart2, Brain, ChevronDown, ChevronUp } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { SSEPanel } from "@/components/ui/SSEPanel";
import { Badge, SignalBadge } from "@/components/ui/Badge";
import { StatusBox } from "@/components/ui/StatusBox";
import { Skeleton } from "@/components/ui/LoadingSpinner";
import { StockModal } from "@/components/ui/StockModal";
import type { StockInfo } from "@/components/ui/StockModal";
import { useSSE } from "@/hooks/useSSE";
import useSWR from "swr";
import { api } from "@/lib/api";
import type { KrIndices, RankingStock, RealtimePick } from "@/lib/types";

// ── KOSPI/KOSDAQ 지수 타일 ────────────────────────────────────────────────────
function KrIndexTile({ name, data }: { name: string; data: { index: number; change_pct: number } | undefined }) {
  if (!data) return <div className="stockcy-card skeleton" style={{ height: "72px" }} />;
  const up   = data.change_pct > 0;
  const down = data.change_pct < 0;
  const color = up ? "var(--color-up)" : down ? "var(--color-down)" : "var(--color-flat)";
  return (
    <div className="stockcy-card" style={{ textAlign: "center", padding: "0.875rem" }}>
      <div style={{ color: "var(--color-muted)", fontSize: "0.75rem", marginBottom: "4px" }}>{name}</div>
      <div style={{ fontWeight: 700, fontSize: "1.15rem", marginBottom: "2px" }}>
        {data.index.toLocaleString()}
      </div>
      <div style={{ color, fontSize: "0.82rem" }}>
        {up ? "▲" : down ? "▼" : "─"} {Math.abs(data.change_pct).toFixed(2)}%
      </div>
    </div>
  );
}

// ── 랭킹 테이블 ────────────────────────────────────────────────────────────────
function RankingTable({ data, title, onRowClick }: {
  data:       RankingStock[];
  title:      string;
  onRowClick: (s: StockInfo) => void;
}) {
  return (
    <div>
      <p style={{ color: "var(--color-muted)", fontSize: "0.78rem", marginBottom: "0.5rem" }}>{title}</p>
      <table className="stockcy-table">
        <thead>
          <tr>
            <th>#</th>
            <th>종목명</th>
            <th style={{ textAlign: "right" }}>현재가</th>
            <th style={{ textAlign: "right" }}>등락률</th>
            <th style={{ textAlign: "right" }}>거래량</th>
          </tr>
        </thead>
        <tbody>
          {data.slice(0, 10).map((s, i) => {
            const up    = s["등락률(%)"] > 0;
            const down  = s["등락률(%)"] < 0;
            const color = up ? "var(--color-up)" : down ? "var(--color-down)" : "var(--color-flat)";
            return (
              <tr
                key={s["종목코드"]}
                style={{ cursor: "pointer" }}
                onClick={() => onRowClick({ code: s["종목코드"], name: s["종목명"], market: "국내" })}
              >
                <td style={{ color: "var(--color-subtle)", fontSize: "0.75rem" }}>{i + 1}</td>
                <td>
                  <span style={{ fontWeight: 500 }}>{s["종목명"]}</span>
                  <span style={{ color: "var(--color-subtle)", fontSize: "0.72rem", marginLeft: "4px" }}>
                    {s["종목코드"]}
                  </span>
                </td>
                <td style={{ textAlign: "right" }}>{s["현재가"]?.toLocaleString()}</td>
                <td style={{ textAlign: "right", color }}>{up ? "+" : ""}{s["등락률(%)"]?.toFixed(2)}%</td>
                <td style={{ textAlign: "right", color: "var(--color-muted)", fontSize: "0.8rem" }}>
                  {(s["거래량"] as number)?.toLocaleString()}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── AI 픽 카드 ────────────────────────────────────────────────────────────────
function PickCard({ pick, onAnalyze }: { pick: RealtimePick; onAnalyze: (s: StockInfo) => void }) {
  const up   = pick.change_pct > 0;
  const down = pick.change_pct < 0;
  const color = up ? "var(--color-up)" : down ? "var(--color-down)" : "var(--color-flat)";

  return (
    <div className="stockcy-card" style={{ marginBottom: "0.75rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "0.5rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", flexWrap: "wrap" }}>
          <span style={{ fontWeight: 700, fontSize: "1rem" }}>{pick.name}</span>
          <span style={{ color: "var(--color-muted)", fontSize: "0.78rem" }}>{pick.code}</span>
          <Badge variant="info">{pick.theme}</Badge>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
          <button
            className="stockcy-btn stockcy-btn-secondary"
            style={{ padding: "2px 8px", fontSize: "0.72rem" }}
            onClick={() => onAnalyze({ code: pick.code, name: pick.name, market: "국내" })}
          >
            AI 분석
          </button>
          <span style={{
            background: "var(--color-accent)", color: "white",
            borderRadius: "50%", width: "24px", height: "24px",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: "0.78rem", fontWeight: 700, flexShrink: 0,
          }}>
            {pick.rank}
          </span>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "0.5rem", marginBottom: "0.625rem" }}>
        {[
          { label: "현재가",    value: `₩${pick.current_price?.toLocaleString()}`, color },
          { label: "매수 타점", value: `₩${pick.entry?.toLocaleString()}`,         color: "var(--color-info)" },
          { label: "목표가",    value: `₩${pick.target?.toLocaleString()}`,          color: "var(--color-up)" },
          { label: "손절가",    value: `₩${pick.stop?.toLocaleString()}`,            color: "var(--color-down)" },
        ].map((item) => (
          <div key={item.label} style={{ textAlign: "center", background: "var(--color-elevated)", borderRadius: "0.375rem", padding: "0.4rem" }}>
            <div style={{ fontSize: "0.68rem", color: "var(--color-muted)" }}>{item.label}</div>
            <div style={{ fontWeight: 600, fontSize: "0.85rem", color: item.color }}>{item.value}</div>
          </div>
        ))}
      </div>

      <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap", marginBottom: "0.5rem" }}>
        <Badge variant="warning">{pick.pattern}</Badge>
        <Badge variant="muted">{pick.horizon}</Badge>
        <Badge variant="muted">{pick.theme_stage}</Badge>
        <Badge variant={pick.supply_signal.includes("유입") || pick.supply_signal.includes("매집") ? "success" : "muted"}>
          {pick.supply_signal}
        </Badge>
      </div>

      <p style={{ fontSize: "0.82rem", color: "var(--color-muted)", lineHeight: 1.6 }}>
        {pick.reason}
      </p>
    </div>
  );
}

type AiTab = "picks" | "rotation" | "mypattern";

// ── 메인 페이지 ───────────────────────────────────────────────────────────────
export default function LeadingPage() {
  const [selectedStock,  setSelectedStock]  = useState<StockInfo | null>(null);
  const [activeAiTab,    setActiveAiTab]    = useState<AiTab>("picks");
  const [invExpanded,    setInvExpanded]    = useState(false);
  const [allExpanded,    setAllExpanded]    = useState(false);

  const { data: kr }   = useSWR<KrIndices>("kr-indices",   () => api.kr.indices() as Promise<KrIndices>,   { refreshInterval: 60000 });
  const { data: volR } = useSWR("kr-vol-rank",  () => api.kr.volumeRanking(), { refreshInterval: 60000 });
  const { data: chgR } = useSWR("kr-chg-rank",  () => api.kr.changeRanking(), { refreshInterval: 60000 });
  const { data: inv }  = useSWR("kr-investor",  () => api.kr.investorTrend(), { refreshInterval: 120000 });

  const picks    = useSSE<{ picks: RealtimePick[]; market_condition: string; market_comment: string }>("/api/ai/realtime-picks-kr", { method: "POST", globalId: "realtime-picks", globalTitle: "실시간 단타 전략" });
  const rotation = useSSE<string>("/api/ai/sector-rotation", { globalId: "sector-rotation", globalTitle: "섹터 순환 분석" });
  const myPick   = useSSE<{ profile_summary: any; top_picks: any[]; ai_narrative: string }>("/api/ai/pattern-screener", { method: "POST", globalId: "pattern-screener", globalTitle: "내 패턴 스크리너" });

  const handlePickStart = () => {
    const marketData = {
      KOSPI:  kr?.KOSPI  ? { index: kr.KOSPI.index,  change_pct: kr.KOSPI.change_pct }  : {},
      KOSDAQ: kr?.KOSDAQ ? { index: kr.KOSDAQ.index, change_pct: kr.KOSDAQ.change_pct } : {},
    };
    picks.start({
      market_data:  marketData,
      volume_rank:  Array.isArray(volR) ? volR : [],
      change_rank:  Array.isArray(chgR) ? chgR : [],
    });
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>

      {selectedStock && (
        <StockModal stock={selectedStock} onClose={() => setSelectedStock(null)} />
      )}

      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
        <TrendingUp size={18} style={{ color: "var(--color-accent)" }} />
        <h1 style={{ fontSize: "1.05rem", fontWeight: 700 }}>주도주 분석</h1>
      </div>

      {/* KOSPI / KOSDAQ */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "0.75rem" }}>
        <KrIndexTile name="KOSPI"  data={kr?.KOSPI} />
        <KrIndexTile name="KOSDAQ" data={kr?.KOSDAQ} />
      </div>

      {/* 랭킹 테이블 */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
        <Card title="거래량 상위">
          {Array.isArray(volR)
            ? <RankingTable data={volR as RankingStock[]} title="클릭하면 AI 분석" onRowClick={setSelectedStock} />
            : <Skeleton height="200px" />}
        </Card>
        <Card title="등락률 상위">
          {Array.isArray(chgR)
            ? <RankingTable data={chgR as RankingStock[]} title="클릭하면 AI 분석" onRowClick={setSelectedStock} />
            : <Skeleton height="200px" />}
        </Card>
      </div>

      {/* 외국인·기관 수급 — 접을 수 있음 */}
      <div className="stockcy-card" style={{ padding: 0, overflow: "hidden" }}>
        <button
          onClick={() => setInvExpanded(v => !v)}
          style={{ width: "100%", display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0.75rem 1rem", background: "none", border: "none", cursor: "pointer", color: "var(--color-text)" }}
        >
          <span style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.85rem", fontWeight: 600 }}>
            <Users size={14} style={{ color: "var(--color-muted)" }} />외국인·기관 순매수
          </span>
          {invExpanded ? <ChevronUp size={14} style={{ color: "var(--color-muted)" }} /> : <ChevronDown size={14} style={{ color: "var(--color-muted)" }} />}
        </button>
        {invExpanded && (
          <div style={{ padding: "0 1rem 0.75rem" }}>
            {Array.isArray(inv) ? (
              <table className="stockcy-table">
                <thead>
                  <tr>
                    <th>종목명</th>
                    <th style={{ textAlign: "right" }}>외국인</th>
                    <th style={{ textAlign: "right" }}>기관</th>
                  </tr>
                </thead>
                <tbody>
                  {(inv as Record<string, unknown>[]).slice(0, 10).map((row, i) => (
                    <tr key={i}>
                      <td>{String(row["종목명"] ?? "")}</td>
                      <td style={{ textAlign: "right", color: (Number(row["외국인순매수"]) ?? 0) > 0 ? "var(--color-up)" : "var(--color-down)" }}>
                        {Number(row["외국인순매수"])?.toLocaleString()}
                      </td>
                      <td style={{ textAlign: "right", color: (Number(row["기관순매수"]) ?? 0) > 0 ? "var(--color-up)" : "var(--color-down)" }}>
                        {Number(row["기관순매수"])?.toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : <Skeleton height="160px" />}
          </div>
        )}
      </div>

      {/* AI 분석 탭 패널 */}
      <div className="stockcy-card" style={{ padding: 0, overflow: "hidden" }}>
        {/* 탭 헤더 */}
        <div style={{ display: "flex", alignItems: "stretch", borderBottom: "1px solid var(--color-border)", padding: "0 0.25rem" }}>
          {!allExpanded && ([
            { id: "picks"     as AiTab, icon: <Zap       size={13} />, label: "AI 실시간 픽",    color: "var(--color-warning)" },
            { id: "rotation"  as AiTab, icon: <BarChart2 size={13} />, label: "섹터 순환매",      color: "var(--color-info)" },
            { id: "mypattern" as AiTab, icon: <Brain     size={13} />, label: "내 패턴 스크리너", color: "#a78bfa" },
          ] as const).map(tab => {
            const active = activeAiTab === tab.id;
            return (
              <button key={tab.id} onClick={() => setActiveAiTab(tab.id)} style={{
                flex: 1, display: "flex", alignItems: "center", justifyContent: "center", gap: "0.3rem",
                padding: "0.65rem 0.5rem", background: "none", border: "none", cursor: "pointer",
                fontSize: "0.78rem", fontWeight: active ? 700 : 400,
                color: active ? tab.color : "var(--color-muted)",
                borderBottom: active ? `2px solid ${tab.color}` : "2px solid transparent",
                marginBottom: "-1px", transition: "color 0.15s",
              }}>
                <span style={{ color: active ? tab.color : "var(--color-subtle)" }}>{tab.icon}</span>
                {tab.label}
              </button>
            );
          })}
          {allExpanded && (
            <div style={{ flex: 1, display: "flex", alignItems: "center", gap: "0.5rem", padding: "0.5rem 0.75rem" }}>
              <Zap size={12} style={{ color: "var(--color-warning)" }} />
              <BarChart2 size={12} style={{ color: "var(--color-info)" }} />
              <Brain size={12} style={{ color: "#a78bfa" }} />
              <span style={{ fontSize: "0.78rem", color: "var(--color-muted)" }}>전체 보기</span>
            </div>
          )}
          {/* 전체/탭 토글 버튼 */}
          <button
            onClick={() => setAllExpanded(v => !v)}
            title={allExpanded ? "탭 보기로 전환" : "전체 펼치기"}
            style={{
              flexShrink: 0, display: "flex", alignItems: "center", gap: "0.3rem",
              padding: "0.5rem 0.75rem", background: "none", border: "none", cursor: "pointer",
              fontSize: "0.72rem", color: "var(--color-muted)",
              borderLeft: "1px solid var(--color-border)", marginBottom: "-1px",
              transition: "color 0.15s",
            }}
          >
            {allExpanded ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
            {allExpanded ? "탭 보기" : "전체 보기"}
          </button>
        </div>

        {/* 콘텐츠 */}
        <div style={{ padding: "1rem", display: "flex", flexDirection: "column", gap: allExpanded ? "1.5rem" : 0 }}>

          {/* ── AI 실시간 픽 ── */}
          {(allExpanded || activeAiTab === "picks") && (
            <div>
              {allExpanded && (
                <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", marginBottom: "0.75rem", paddingBottom: "0.5rem", borderBottom: "1px solid var(--color-border)" }}>
                  <Zap size={14} style={{ color: "var(--color-warning)" }} />
                  <span style={{ fontSize: "0.85rem", fontWeight: 700, color: "var(--color-warning)" }}>AI 실시간 픽</span>
                </div>
              )}
              <SSEPanel
                status={picks.status} message={picks.message}
                result={picks.result} fromCache={picks.fromCache} completedAt={picks.completedAt}
                onStart={handlePickStart} startLabel="AI 픽 분석 시작"
                idleHint="거래량·등락률·수급 데이터를 종합하여 AI가 오늘의 국내 단타 유망 종목 3개를 선정합니다."
              >
                {(data) => (
                  <div>
                    {data.market_comment && (
                      <StatusBox type="info" className="mb-3">
                        {data.market_condition} — {data.market_comment}
                      </StatusBox>
                    )}
                    {data.picks?.map((p) => <PickCard key={p.rank} pick={p} onAnalyze={setSelectedStock} />)}
                  </div>
                )}
              </SSEPanel>
            </div>
          )}

          {/* ── 섹터 순환매 ── */}
          {(allExpanded || activeAiTab === "rotation") && (
            <div>
              {allExpanded && (
                <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", marginBottom: "0.75rem", paddingBottom: "0.5rem", borderBottom: "1px solid var(--color-border)" }}>
                  <BarChart2 size={14} style={{ color: "var(--color-info)" }} />
                  <span style={{ fontSize: "0.85rem", fontWeight: 700, color: "var(--color-info)" }}>섹터 순환매 로드맵</span>
                </div>
              )}
              <SSEPanel<string>
                status={rotation.status} message={rotation.message}
                result={rotation.result} fromCache={rotation.fromCache} completedAt={rotation.completedAt}
                onStart={rotation.start} startLabel="섹터 로테이션 분석"
                idleHint="실시간 시장 데이터를 기반으로 현재 주도 섹터와 다음 자금 이동 경로, 투자 성향별 추천 종목을 분석합니다. (1~2분 소요)"
              >
                {(data) => (
                  <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.83rem", lineHeight: 1.8, color: "var(--color-text)", fontFamily: "inherit" }}>
                    {data}
                  </pre>
                )}
              </SSEPanel>
            </div>
          )}

          {/* ── 내 패턴 스크리너 ── */}
          {(allExpanded || activeAiTab === "mypattern") && (
            <div>
              {allExpanded && (
                <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", marginBottom: "0.75rem", paddingBottom: "0.5rem", borderBottom: "1px solid var(--color-border)" }}>
                  <Brain size={14} style={{ color: "#a78bfa" }} />
                  <span style={{ fontSize: "0.85rem", fontWeight: 700, color: "#a78bfa" }}>내 매매 패턴 기반 단기 추천</span>
                </div>
              )}
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
                    {data.top_picks && data.top_picks.length > 0 && (
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
            </div>
          )}

        </div>
      </div>
    </div>
  );
}
