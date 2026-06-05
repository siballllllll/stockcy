"use client";
import { useState, useEffect, useMemo } from "react";
import { useRouter } from "next/navigation";
import ReactMarkdown from "react-markdown";
import { BarChart2, Zap } from "lucide-react";
import { PicksBoard } from "@/components/picks/PicksBoard";
import { ScreenerPanel } from "@/app/screener/page";
import { useSSE } from "@/hooks/useSSE";
import { SSEPanel } from "@/components/ui/SSEPanel";
import { StockModal } from "@/components/ui/StockModal";
import type { StockInfo } from "@/components/ui/StockModal";
import { MarkdownLite } from "@/components/ui/MarkdownLite";
import { SupplyPowerFlow } from "@/components/SupplyPowerFlow";
import { AiCostBadge } from "@/components/ui/AiCostBadge";
import { useAuth } from "@/lib/auth-context";
import { api } from "@/lib/api";
import useSWR from "swr";

function EntryTimingStats() {
  const [source, setSource] = useState<"leading" | "personal">("leading");
  const [market, setMarket] = useState<"kr" | "us">("kr");
  const { data } = useSWR(
    `/backend/api/ai/entry-timing?source=${source}&market=${market}`,
    (url: string) => fetch(url).then(r => r.json()),
    { revalidateOnFocus: false }
  );

  if (!data || data.error || !data.buckets) {
    return (
      <div style={{ background: "rgba(251,146,60,0.05)", border: "1px solid rgba(251,146,60,0.2)", borderRadius: "10px", padding: "1rem 1.2rem" }}>
        <div style={{ fontSize: "0.78rem", fontWeight: 700, color: "#fb923c", marginBottom: "0.5rem" }}>⏰ 시간대별 진입 타이밍</div>
        <div style={{ fontSize: "0.75rem", color: "var(--color-muted)" }}>{data?.error ?? "데이터 로딩 중..."}</div>
      </div>
    );
  }

  const buckets = data.buckets ?? [];
  const best = data.best_timing;
  const maxCount = Math.max(...buckets.map((b: any) => b.count), 1);

  return (
    <div style={{ background: "rgba(251,146,60,0.05)", border: "1px solid rgba(251,146,60,0.2)", borderRadius: "10px", padding: "1rem 1.2rem", display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ fontSize: "0.78rem", fontWeight: 700, color: "#fb923c", display: "flex", alignItems: "center", gap: "0.4rem" }}>
          ⏰ 시간대별 진입 타이밍 분석 ({data.total_trades}건)
        </div>
        <div style={{ display: "flex", gap: "8px" }}>
          <div style={{ display: "flex", gap: "3px" }}>
            {(["kr", "us"] as const).map((m) => (
              <button
                key={m}
                onClick={() => setMarket(m)}
                style={{ fontSize: "0.65rem", padding: "3px 8px", borderRadius: "4px", border: "1px solid", borderColor: market === m ? "rgba(251,146,60,0.5)" : "rgba(255,255,255,0.08)", background: market === m ? "rgba(251,146,60,0.15)" : "transparent", color: market === m ? "#fb923c" : "var(--color-muted)", fontWeight: 700, cursor: "pointer" }}
              >
                {m === "kr" ? "🇰🇷 국내" : "🇺🇸 미국"}
              </button>
            ))}
          </div>
          <div style={{ display: "flex", gap: "3px" }}>
            {(["leading", "personal"] as const).map((s) => (
              <button
                key={s}
                onClick={() => setSource(s)}
                style={{ fontSize: "0.65rem", padding: "3px 8px", borderRadius: "4px", border: "1px solid", borderColor: source === s ? "rgba(251,146,60,0.5)" : "rgba(255,255,255,0.08)", background: source === s ? "rgba(251,146,60,0.15)" : "transparent", color: source === s ? "#fb923c" : "var(--color-muted)", fontWeight: 700, cursor: "pointer" }}
              >
                {s === "leading" ? "리딩방" : "개인"}
              </button>
            ))}
          </div>
        </div>
      </div>

      {best && best.label && (
        <div style={{ background: "rgba(251,146,60,0.1)", border: "1px solid rgba(251,146,60,0.3)", borderRadius: "6px", padding: "0.5rem 0.75rem", fontSize: "0.78rem", color: "#fbbf24" }}>
          🏆 <b>최고 승률 시간대:</b> {best.label} — 승률 {best.win_rate}% / 평균 {best.avg_pct >= 0 ? "+" : ""}{best.avg_pct}% ({best.count}건)
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
        {buckets.map((b: any) => {
          const widthPct = (b.count / maxCount) * 100;
          const c = b.avg_pct > 0 ? "#34d399" : b.avg_pct < 0 ? "#f87171" : "var(--color-muted)";
          return (
            <div key={b.label} style={{ display: "flex", alignItems: "center", gap: "8px", fontSize: "0.72rem" }}>
              <div style={{ minWidth: "150px", color: "var(--color-muted)" }}>{b.label}</div>
              <div style={{ flex: 1, height: "18px", background: "rgba(255,255,255,0.03)", borderRadius: "4px", position: "relative", overflow: "hidden" }}>
                <div style={{ width: `${widthPct}%`, height: "100%", background: "rgba(251,146,60,0.25)" }} />
                <span style={{ position: "absolute", left: "6px", top: "1px", fontSize: "0.65rem", color: "var(--color-text)", lineHeight: "16px" }}>{b.count}건</span>
              </div>
              <div style={{ minWidth: "60px", textAlign: "right", color: c, fontWeight: 700 }}>
                {b.win_rate > 0 ? `${b.win_rate}%` : "-"}
              </div>
              <div style={{ minWidth: "60px", textAlign: "right", color: c, fontWeight: 700 }}>
                {b.avg_pct !== 0 ? `${b.avg_pct >= 0 ? "+" : ""}${b.avg_pct}%` : "-"}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function PerformanceVerification() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [tab, setTab] = useState<"backtest" | "feedback" | "timing">("backtest");
  const allTabs: { id: typeof tab; label: string; color: string }[] = [
    { id: "backtest", label: "📊 자동 백테스트", color: "#a5b4fc" },
    { id: "feedback", label: "🎯 리딩방 검증",  color: "#34d399" },
    { id: "timing",   label: "⏰ 시간대 분석",  color: "#fb923c" },
  ];
  // 리딩방 집계 분석(검증·시간대)은 관리자 전용 — 일반 유저는 백테스트만
  const tabs = isAdmin ? allTabs : allTabs.filter((t) => t.id === "backtest");
  return (
    <div style={{ background: "rgba(255,255,255,0.02)", border: "1px solid var(--color-border)", borderRadius: "10px", padding: "1rem 1.2rem", display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "8px", flexWrap: "wrap" }}>
        <div style={{ fontSize: "0.85rem", fontWeight: 800, color: "var(--color-text)" }}>🧪 추천 성과 검증</div>
        <div style={{ display: "flex", gap: "4px" }}>
          {tabs.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              style={{
                fontSize: "0.72rem", padding: "4px 10px", borderRadius: "5px",
                border: "1px solid",
                borderColor: tab === t.id ? `${t.color}80` : "rgba(255,255,255,0.08)",
                background: tab === t.id ? `${t.color}1f` : "transparent",
                color: tab === t.id ? t.color : "var(--color-muted)",
                fontWeight: 700, cursor: "pointer", whiteSpace: "nowrap",
              }}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>
      <div>
        {tab === "backtest" && <BacktestStats />}
        {tab === "feedback" && <ScreenerFeedbackStats />}
        {tab === "timing"   && <EntryTimingStats />}
      </div>
    </div>
  );
}

function DailyAlertCard() {
  const [sending, setSending] = useState(false);
  const [msg, setMsg] = useState("");
  const [preview, setPreview] = useState<string>("");

  const loadPreview = async () => {
    try {
      const res = await fetch("/backend/api/ai/alert/preview-daily");
      const json = await res.json();
      setPreview(json.preview ?? "");
    } catch {}
  };

  useEffect(() => { loadPreview(); }, []);

  const sendNow = async () => {
    setSending(true);
    setMsg("발송 중...");
    try {
      const res = await fetch("/backend/api/ai/alert/send-daily", { method: "POST" });
      const json = await res.json();
      if (json.sent) {
        setMsg(`✅ 텔레그램 발송 완료`);
      } else {
        setMsg(`⚠️ ${json.reason || json.error || "발송 실패"}`);
      }
    } catch (e: any) {
      setMsg(`❌ ${e?.message ?? String(e)}`);
    } finally {
      setSending(false);
    }
  };

  return (
    <div style={{ background: "rgba(168,85,247,0.05)", border: "1px solid rgba(168,85,247,0.2)", borderRadius: "10px", padding: "1rem 1.2rem", display: "flex", flexDirection: "column", gap: "0.6rem" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ fontSize: "0.78rem", fontWeight: 700, color: "#c084fc", display: "flex", alignItems: "center", gap: "0.4rem" }}>
          📨 일일 텔레그램 알림 (평일 08:30 자동)
        </div>
        <button
          onClick={sendNow}
          disabled={sending}
          style={{ fontSize: "0.7rem", padding: "4px 10px", background: "rgba(168,85,247,0.15)", border: "1px solid rgba(168,85,247,0.35)", color: "#c084fc", borderRadius: "5px", fontWeight: 700, cursor: sending ? "wait" : "pointer" }}
        >
          {sending ? "발송 중..." : "지금 발송"}
        </button>
      </div>
      {msg && <div style={{ fontSize: "0.7rem", color: "var(--color-muted)" }}>{msg}</div>}
      {preview && (
        <details style={{ fontSize: "0.72rem" }}>
          <summary style={{ cursor: "pointer", color: "var(--color-muted)", fontWeight: 700 }}>메시지 미리보기</summary>
          <pre style={{ marginTop: "6px", padding: "8px", background: "rgba(255,255,255,0.03)", borderRadius: "5px", whiteSpace: "pre-wrap", color: "var(--color-text)", fontSize: "0.7rem", fontFamily: "inherit" }}>{preview}</pre>
        </details>
      )}
    </div>
  );
}

function BacktestStats() {
  const [running, setRunning] = useState(false);
  const [msg, setMsg] = useState("");
  const { data, mutate } = useSWR(
    "/backend/api/ai/screener-backtest/stats",
    (url: string) => fetch(url).then(r => r.json()),
    { revalidateOnFocus: false }
  );

  const runBacktest = async () => {
    setRunning(true);
    setMsg("백테스트 실행 중...");
    try {
      const res = await fetch("/backend/api/ai/screener-backtest/run", { method: "POST" });
      const json = await res.json();
      if (json.error) {
        setMsg(`⚠️ ${json.error}`);
      } else {
        setMsg(`✅ 신규 ${json.processed_now ?? 0}건 계산 / 너무 최근 ${json.skipped_too_recent ?? 0}건 스킵`);
        mutate();
      }
    } catch (e: any) {
      setMsg(`❌ 오류: ${e?.message ?? String(e)}`);
    } finally {
      setRunning(false);
    }
  };

  const n = data?.total_picks_backtested ?? 0;
  const ov = data?.overall ?? {};
  const buckets = data?.score_buckets ?? [];
  const recent = data?.recent ?? [];

  return (
    <div style={{ background: "rgba(99,102,241,0.05)", border: "1px solid rgba(99,102,241,0.2)", borderRadius: "10px", padding: "1rem 1.2rem", display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ fontSize: "0.78rem", fontWeight: 700, color: "#a5b4fc", display: "flex", alignItems: "center", gap: "0.4rem" }}>
          🧪 백테스트 — 추천 종목 실전 성과
        </div>
        <button
          onClick={runBacktest}
          disabled={running}
          style={{ fontSize: "0.7rem", padding: "4px 10px", background: running ? "var(--color-elevated)" : "rgba(99,102,241,0.15)", border: "1px solid rgba(99,102,241,0.35)", color: "#a5b4fc", borderRadius: "5px", fontWeight: 700, cursor: running ? "wait" : "pointer" }}
        >
          {running ? "실행 중..." : "백테스트 실행"}
        </button>
      </div>
      {msg && <div style={{ fontSize: "0.72rem", color: "var(--color-muted)" }}>{msg}</div>}

      {n === 0 ? (
        <div style={{ fontSize: "0.78rem", color: "var(--color-muted)", textAlign: "center", padding: "0.5rem 0" }}>
          백테스트 결과 없음. 패턴 스크리너 추천 후 1일 이상 경과 시 "백테스트 실행" 버튼 클릭.
        </div>
      ) : (
        <>
          {/* 누적 성과 — 1일/3일/7일 */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "0.5rem" }}>
            {[
              { label: "+1일", ret: ov.avg_d1_return, wr: ov.win_rate_d1 },
              { label: "+3일", ret: ov.avg_d3_return, wr: ov.win_rate_d3 },
              { label: "+7일", ret: ov.avg_d7_return, wr: ov.win_rate_d7 },
            ].map((s: any) => {
              const c = s.ret > 0 ? "#34d399" : s.ret < 0 ? "#f87171" : "var(--color-muted)";
              return (
                <div key={s.label} style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.07)", borderRadius: "8px", padding: "0.55rem", textAlign: "center" }}>
                  <div style={{ fontSize: "0.68rem", color: "var(--color-muted)", marginBottom: "3px" }}>{s.label}</div>
                  <div style={{ fontSize: "1rem", fontWeight: 800, color: c }}>{s.ret >= 0 ? "+" : ""}{s.ret}%</div>
                  <div style={{ fontSize: "0.66rem", color: "var(--color-muted)" }}>승률 {s.wr}%</div>
                </div>
              );
            })}
          </div>

          {/* 매칭 점수 구간별 */}
          <div>
            <div style={{ fontSize: "0.7rem", color: "var(--color-muted)", marginBottom: "0.4rem", fontWeight: 700 }}>매칭 점수 구간별 (+3일 기준)</div>
            <div style={{ display: "flex", gap: "0.4rem" }}>
              {buckets.map((b: any) => {
                const c = b.avg_return > 0 ? "#34d399" : b.avg_return < 0 ? "#f87171" : "var(--color-muted)";
                return (
                  <div key={b.label} style={{ flex: 1, background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.06)", borderRadius: "6px", padding: "0.5rem", textAlign: "center" }}>
                    <div style={{ fontSize: "0.66rem", color: "var(--color-muted)" }}>{b.label}</div>
                    <div style={{ fontSize: "0.85rem", fontWeight: 700, color: c }}>{b.avg_return >= 0 ? "+" : ""}{b.avg_return}%</div>
                    <div style={{ fontSize: "0.62rem", color: "var(--color-muted)" }}>{b.count}건 · 승률 {b.win_rate}%</div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* 최근 결과 */}
          {recent.length > 0 && (
            <div>
              <div style={{ fontSize: "0.7rem", color: "var(--color-muted)", marginBottom: "0.4rem", fontWeight: 700 }}>최근 백테스트 결과 (총 {n}건)</div>
              <div style={{ display: "flex", flexDirection: "column", gap: "3px", maxHeight: "200px", overflowY: "auto" }}>
                {recent.map((r: any, i: number) => {
                  const ret = r.d3_return;
                  const c = ret > 0 ? "#34d399" : ret < 0 ? "#f87171" : "var(--color-muted)";
                  return (
                    <div key={i} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: "0.72rem", background: "rgba(255,255,255,0.02)", padding: "4px 8px", borderRadius: "4px" }}>
                      <span style={{ color: "var(--color-muted)", fontSize: "0.65rem" }}>{r.picked_date}</span>
                      <span style={{ color: "var(--color-text)", fontWeight: 600, flex: 1, marginLeft: "8px" }}>{r.name}</span>
                      <span style={{ color: "var(--color-muted)", fontSize: "0.65rem", marginRight: "8px" }}>매칭 {r.match_score}점</span>
                      <span style={{ color: c, fontWeight: 700 }}>{ret >= 0 ? "+" : ""}{ret}%</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function ScreenerFeedbackStats() {
  const { data } = useSWR(
    "/backend/api/ai/screener-feedback-stats",
    (url: string) => fetch(url).then(r => r.json()),
    { revalidateOnFocus: false, refreshInterval: 0 }
  );
  const s = data?.stats;
  if (!s) return null;

  const noData = s.total_picks === 0 && s.matched?.cnt === 0 && s.unmatched?.cnt === 0;
  const hasTradeData = (s.matched?.cnt ?? 0) + (s.unmatched?.cnt ?? 0) > 0;

  return (
    <div style={{ background: "rgba(16,185,129,0.05)", border: "1px solid rgba(16,185,129,0.2)", borderRadius: "10px", padding: "1rem 1.2rem", display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <div style={{ fontSize: "0.78rem", fontWeight: 700, color: "#34d399", display: "flex", alignItems: "center", gap: "0.4rem" }}>
        📊 피드백 학습 현황
      </div>

      {/* 추천 이력 */}
      <div style={{ display: "flex", gap: "0.6rem" }}>
        {[
          { label: "추천 기록일", value: noData ? "-" : `${s.pick_days}일` },
          { label: "누적 추천 종목", value: noData ? "-" : `${s.total_picks}건` },
        ].map(item => (
          <div key={item.label} style={{ flex: 1, background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.07)", borderRadius: "8px", padding: "0.6rem", textAlign: "center" }}>
            <div style={{ fontSize: "0.68rem", color: "var(--color-muted)", marginBottom: "3px" }}>{item.label}</div>
            <div style={{ fontSize: "1rem", fontWeight: 800, color: "var(--color-text)" }}>{item.value}</div>
          </div>
        ))}
      </div>

      {/* 매칭/비매칭 성과 비교 */}
      {hasTradeData ? (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.6rem" }}>
          {[
            { label: "스크리너 매칭 거래", data: s.matched, color: "#34d399", border: "rgba(16,185,129,0.3)", bg: "rgba(16,185,129,0.07)" },
            { label: "비매칭 거래", data: s.unmatched, color: "var(--color-muted)", border: "rgba(255,255,255,0.1)", bg: "rgba(255,255,255,0.02)" },
          ].map(item => (
            <div key={item.label} style={{ background: item.bg, border: `1px solid ${item.border}`, borderRadius: "8px", padding: "0.7rem" }}>
              <div style={{ fontSize: "0.68rem", fontWeight: 700, color: item.color, marginBottom: "0.4rem" }}>{item.label}</div>
              {item.data.cnt === 0 ? (
                <div style={{ fontSize: "0.75rem", color: "var(--color-muted)" }}>데이터 없음</div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: "3px" }}>
                  <div style={{ fontSize: "0.75rem", color: "var(--color-muted)" }}>{item.data.cnt}건 ({item.data.wins}승)</div>
                  <div style={{ fontSize: "1rem", fontWeight: 800, color: item.color }}>승률 {item.data.win_rate}%</div>
                  <div style={{ fontSize: "0.75rem", color: item.data.avg_pct >= 0 ? "#34d399" : "#f87171" }}>
                    평균 {item.data.avg_pct >= 0 ? "+" : ""}{item.data.avg_pct}%
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div style={{ fontSize: "0.78rem", color: "var(--color-muted)", textAlign: "center", padding: "0.5rem 0" }}>
          리딩방 거래가 쌓이면 매칭 성과 통계가 표시됩니다.
        </div>
      )}
    </div>
  );
}

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

type Tab = "picks" | "confluence" | "rotation" | "mypattern" | "supply" | "screener";

const TABS: { id: Tab; label: string }[] = [
  { id: "picks",      label: "🎯 AI 타점 포착" },
  { id: "confluence", label: "🎯 교차검증" },
  { id: "rotation",   label: "📊 섹터 순환매" },
  { id: "mypattern",  label: "🧠 내 패턴 스크리너" },
  { id: "supply",     label: "🔄 수급 이동 감지" },
  { id: "screener",   label: "🔍 복합 스크리너" },
];

// ── 시장 레짐(장세 신호등) 배너 ────────────────────────────────────────────────
function RegimeBanner() {
  const { data } = useSWR<any>("market-regime", async () => {
    const res = await fetch("/backend/api/ai/market-regime");
    return res.json();
  }, { refreshInterval: 600000 });
  if (!data) return null;
  const POSTURE: Record<string, { c: string; bg: string; tip: string }> = {
    "공격적": { c: "#34d399", bg: "rgba(52,211,153,0.12)", tip: "추세 우호적 — 모멘텀 전략 유리" },
    "중립":   { c: "#fbbf24", bg: "rgba(251,191,36,0.12)", tip: "방향성 약함 — 선별적 접근" },
    "방어적": { c: "#f87171", bg: "rgba(248,113,113,0.12)", tip: "하락/고변동 — 비중축소·손절 엄격" },
  };
  const cell = (label: string, r: any) => {
    if (!r) return null;
    const p = POSTURE[r.posture] || POSTURE["중립"];
    return (
      <div style={{ flex: 1, minWidth: "180px", background: p.bg, border: `1px solid ${p.c}55`, borderRadius: "8px", padding: "8px 12px" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "8px" }}>
          <span style={{ fontSize: "0.8rem", fontWeight: 800 }}>{label}</span>
          <span style={{ fontSize: "0.72rem", fontWeight: 800, color: p.c }}>{r.posture}</span>
        </div>
        <div style={{ fontSize: "0.66rem", color: "var(--color-muted)", marginTop: "2px" }}>
          {r.trend} · 변동성 {r.vol} · 20일 {r.ret20 >= 0 ? "+" : ""}{r.ret20}%
        </div>
        <div style={{ fontSize: "0.62rem", color: p.c, marginTop: "2px" }}>{p.tip}</div>
      </div>
    );
  };
  return (
    <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
      {cell("🇰🇷 국내 장세", data.kr)}
      {cell("🇺🇸 미국 장세", data.us)}
    </div>
  );
}

// ── 청산 가이드 (백테스트 기반 최적 보유기간/목표/손절) ──────────────────────────
function ExitGuidance() {
  const { data } = useSWR<any>("exit-guidance", async () => {
    const res = await fetch("/backend/api/ai/exit-guidance");
    return res.json();
  }, { refreshInterval: 600000 });
  if (!data || !data.samples) return null;
  return (
    <div style={{ background: "rgba(168,85,247,0.07)", border: "1px solid rgba(168,85,247,0.25)", borderRadius: "8px", padding: "8px 12px", fontSize: "0.72rem" }}>
      <span style={{ fontWeight: 800, color: "#c084fc" }}>🏁 청산 가이드</span>
      <span style={{ color: "var(--color-muted)", marginLeft: "6px" }}>(백테스트 {data.samples}건)</span>
      <span style={{ marginLeft: "8px", color: "var(--color-text)" }}>
        최적 보유 <b style={{ color: "#c084fc" }}>{data.best}</b>
        {data.suggest_target != null && <> · 목표 <b style={{ color: "#34d399" }}>+{data.suggest_target}%</b></>}
        {data.suggest_stop != null && <> · 손절 <b style={{ color: "#f87171" }}>{data.suggest_stop}%</b></>}
      </span>
    </div>
  );
}

// ── 교차검증(컨플루언스) 탭 ────────────────────────────────────────────────────
function ConfluenceTab({ onSelect }: { onSelect: (s: StockInfo) => void }) {
  const { data } = useSWR<{ picks: any[] }>(
    "confluence",
    async () => {
      const res = await fetch("/backend/api/ai/confluence?days=7&min_engines=2");
      return res.json();
    },
    { refreshInterval: 120000 }
  );
  const picks = data?.picks ?? [];
  const ENGINE_COLOR: Record<string, string> = {
    "시나리오": "#a78bfa", "패턴스크리너": "#34d399", "에이전트": "#60a5fa", "AI추천": "#fbbf24",
  };

  // ── 실시간 현재가 조회 (교차검증: 추천 당시가 대비 현재가) ──────────────────────
  const krTickers = useMemo(() => [...new Set(picks.filter((p: any) => p.market === "kr").map((p: any) => p.ticker))] as string[], [picks]);
  const usTickers = useMemo(() => [...new Set(picks.filter((p: any) => p.market !== "kr").map((p: any) => p.ticker))] as string[], [picks]);

  const { data: krPrices } = useSWR(
    krTickers.length > 0 ? `cf-kr-prices-${krTickers.join(",")}` : null,
    async () => {
      const map: Record<string, number> = {};
      await Promise.all(krTickers.map(async (code) => {
        try { const d = await api.kr.stockPrice(code) as any; if (d?.price) map[code] = d.price; } catch {}
      }));
      return map;
    },
    { revalidateOnFocus: false }
  );
  const { data: usPrices } = useSWR(
    usTickers.length > 0 ? `cf-us-prices-${usTickers.join(",")}` : null,
    async () => {
      const arr = await api.us.stocks(usTickers) as any[];
      const map: Record<string, number> = {};
      for (const s of (arr ?? [])) { const t = s["심볼"] ?? s.ticker ?? ""; if (t) map[t] = s["현재가($)"] ?? 0; }
      return map;
    },
    { revalidateOnFocus: false }
  );
  const priceOf = (p: any): number => (p.market === "kr" ? krPrices?.[p.ticker] : usPrices?.[p.ticker]) ?? 0;
  const fmtPrice = (isKr: boolean, v: number) => isKr ? `₩${Math.round(v).toLocaleString()}` : `$${v.toFixed(2)}`;

  return (
    <div className="flex flex-col gap-4">
      <RegimeBanner />
      <ExitGuidance />
      <div style={{ fontSize: "0.8rem", color: "var(--color-muted)", lineHeight: 1.6 }}>
        🎯 여러 AI 엔진(시나리오·패턴스크리너·에이전트·AI추천)이 <b style={{ color: "var(--color-text)" }}>최근 7일 내 동시에</b> 잡은 종목입니다.
        독립 신호가 겹칠수록 승률이 높은 경향이 있어, 겹친 엔진 수(점수)가 높을수록 상단에 노출됩니다.
      </div>
      {picks.length === 0 ? (
        <div className="stockcy-card p-8 text-center text-zinc-500 text-sm">
          아직 2개 이상 엔진이 동시에 잡은 종목이 없습니다. 각 엔진을 실행해 픽이 쌓이면 표시됩니다.
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: "12px" }}>
          {picks.map((p: any) => {
            const isKr = p.market === "kr";
            return (
              <div key={p.ticker}
                onClick={() => onSelect({ code: p.ticker, name: p.name, market: isKr ? "국내" : "미국" })}
                className="stockcy-card cursor-pointer hover:border-indigo-500/40 transition-colors"
                style={{ padding: "12px 14px", display: "flex", flexDirection: "column", gap: "8px", border: "1px solid var(--color-border)" }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                  <span style={{ fontSize: "1.1rem", fontWeight: 900, color: "var(--color-accent)", minWidth: "26px" }}>×{p.score}</span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 800, fontSize: "0.92rem", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{p.name}</div>
                    <div style={{ fontSize: "0.68rem", color: "var(--color-muted)" }}>{p.ticker} · {isKr ? "🇰🇷 국내" : "🇺🇸 미국"}</div>
                  </div>
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: "4px" }}>
                  {p.engines.map((e: string) => (
                    <span key={e} style={{
                      fontSize: "0.62rem", fontWeight: 700, padding: "2px 7px", borderRadius: "99px",
                      color: ENGINE_COLOR[e] || "#9ca3af",
                      background: `${ENGINE_COLOR[e] || "#9ca3af"}22`,
                      border: `1px solid ${ENGINE_COLOR[e] || "#9ca3af"}55`,
                    }}>{e}</span>
                  ))}
                </div>
                {/* 교차검증: 추천 당시가 → 현재가 변동률 (재진입 판단용) */}
                {(() => {
                  const cur = priceOf(p);
                  const rec = Number(p.rec_price) || 0;
                  if (!p.first_date && rec <= 0 && cur <= 0) return null;
                  const chg = rec > 0 && cur > 0 ? (cur - rec) / rec * 100 : null;
                  return (
                    <div style={{ display: "flex", flexWrap: "wrap", gap: "3px 10px", alignItems: "center", fontSize: "0.66rem", color: "var(--color-muted)", borderTop: "1px solid var(--color-border)", paddingTop: "6px" }}>
                      {p.first_date && <span>📅 최초 포착 <b style={{ color: "var(--color-text)" }}>{p.first_date}</b></span>}
                      {rec > 0 && <span>당시가 <b style={{ color: "var(--color-text)" }}>{fmtPrice(isKr, rec)}</b></span>}
                      {cur > 0 && <span>현재가 <b style={{ color: "var(--color-text)" }}>{fmtPrice(isKr, cur)}</b></span>}
                      {chg != null && <span style={{ fontWeight: 700, color: chg >= 0 ? "#ff4b4b" : "#3b82f6" }}>{chg >= 0 ? "▲" : "▼"} {Math.abs(chg).toFixed(2)}%</span>}
                    </div>
                  );
                })()}
                {p.detail && Object.keys(p.detail).length > 0 && (
                  <div style={{ fontSize: "0.64rem", color: "var(--color-muted)", lineHeight: 1.5, borderTop: "1px solid var(--color-border)", paddingTop: "6px" }}>
                    {Object.entries(p.detail).map(([k, v]: [string, any]) => v ? (
                      <div key={k}><b style={{ color: ENGINE_COLOR[k] || "#9ca3af" }}>{k}</b> {String(v)}</div>
                    ) : null)}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default function Dashboard() {
  const router = useRouter();
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [activeTab,     setActiveTab]     = useState<Tab>("picks");
  const [selectedStock, setSelectedStock] = useState<StockInfo | null>(null);

  const rotation = useSSE<string>(
    "/api/ai/sector-rotation",
    { globalId: "sector-rotation", globalTitle: "섹터 순환 분석" }
  );
  const myPick = useSSE<{ profile_summary: any; top_picks: any[]; ai_narrative: string }>(
    "/api/ai/pattern-screener",
    { method: "POST", globalId: "pattern-screener", globalTitle: "내 패턴 스크리너" }
  );
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

      {/* AI 타점 포착 — display:none으로 마운트 유지 (SSE 분석 중 탭 이동 가능) */}
      <div style={{ display: activeTab === "picks" ? "block" : "none" }}>
        <PicksBoard />
      </div>

      {activeTab === "confluence" && <ConfluenceTab onSelect={setSelectedStock} />}

      {/* 섹터 순환매 */}
      {activeTab === "rotation" && (
        <SSEPanel<string>
          status={rotation.status} message={rotation.message}
          result={rotation.result} fromCache={rotation.fromCache} completedAt={rotation.completedAt}
          onStart={rotation.start} startLabel="섹터 로테이션 분석"
          idleHint="실시간 시장 데이터를 기반으로 현재 주도 섹터와 다음 자금 이동 경로, 투자 성향별 추천 종목을 분석합니다. (1~2분 소요)"
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
                            <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: "2px", flexShrink: 0 }}>
                              <div style={{ background: scoreBg, color: scoreColor, fontWeight: 800, fontSize: "0.85rem", padding: "2px 8px", borderRadius: "6px" }}>{score}점</div>
                              {isAdmin && p.personal_score != null && p.leading_score != null && (
                                <div style={{ display: "flex", gap: "3px" }}>
                                  <span style={{ fontSize: "0.62rem", padding: "1px 5px", borderRadius: "4px", background: "rgba(99,102,241,0.12)", border: "1px solid rgba(99,102,241,0.25)", color: "#a5b4fc" }}>개인 {p.personal_score}</span>
                                  <span style={{ fontSize: "0.62rem", padding: "1px 5px", borderRadius: "4px", background: "rgba(16,185,129,0.12)", border: "1px solid rgba(16,185,129,0.25)", color: "#34d399" }}>리딩 {p.leading_score}</span>
                                </div>
                              )}
                            </div>
                          </div>

                          {/* 상태 배지 + 돌파직전/추격주의 */}
                          <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap", alignItems: "center" }}>
                            <span style={{ fontSize: "0.72rem", padding: "3px 10px", borderRadius: "99px", background: status.bg, color: status.color, border: `1px solid ${status.border}`, fontWeight: 700 }}>
                              {status.label}
                            </span>
                            {p.momentum_stage === "prebreak" && (
                              <span title={p.prebreakout_label || "돌파 직전 시그널"} style={{ fontSize: "0.72rem", padding: "3px 10px", borderRadius: "99px", background: "rgba(34,197,94,0.18)", color: "#4ade80", border: "1px solid rgba(34,197,94,0.5)", fontWeight: 800 }}>
                                🚀 돌파직전 {p.prebreakout_score}/5
                              </span>
                            )}
                            {p.momentum_stage === "runner" && (
                              <span title="오늘 올랐지만 추세가 살아있어 추가 상승 여력이 큰 대시세 후보" style={{ fontSize: "0.72rem", padding: "3px 10px", borderRadius: "99px", background: "rgba(245,158,11,0.18)", color: "#fbbf24", border: "1px solid rgba(245,158,11,0.5)", fontWeight: 800 }}>
                                🔥 강한추세
                              </span>
                            )}
                            {p.momentum_stage === "exhausted" && (
                              <span title="파라볼릭/과매수 — 추격 위험" style={{ fontSize: "0.72rem", padding: "3px 10px", borderRadius: "99px", background: "rgba(239,68,68,0.15)", color: "#f87171", border: "1px solid rgba(239,68,68,0.4)", fontWeight: 800 }}>
                                ⚠️ 추격주의
                              </span>
                            )}
                          </div>

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
                            {p.scenario_count > 0 && (
                              <span style={{ fontSize: "0.72rem", padding: "2px 7px", borderRadius: "6px", background: "rgba(168,85,247,0.15)", border: "1px solid rgba(168,85,247,0.3)", color: "#c084fc", fontWeight: 700 }} title="시나리오에 등장한 종목 (보너스 점수 적용)">
                                📋 시나리오 {p.scenario_count}건
                              </span>
                            )}
                            {p.supply_signal && (
                              <span style={{ fontSize: "0.72rem", padding: "2px 7px", borderRadius: "6px", background: "rgba(59,130,246,0.15)", border: "1px solid rgba(59,130,246,0.35)", color: "#60a5fa", fontWeight: 700 }} title="외국인·기관 순매수 상위 (객관적 수급 신호 — 가점)">
                                🏦 {p.supply_signal}
                              </span>
                            )}
                            {p.hot_sector && (
                              <span style={{ fontSize: "0.72rem", padding: "2px 7px", borderRadius: "6px", background: "rgba(244,63,94,0.13)", border: "1px solid rgba(244,63,94,0.35)", color: "#fb7185", fontWeight: 700 }} title="오늘의 핫섹터 소속 (객관적 모멘텀 — 가점)">
                                🔥 {p.hot_sector}
                              </span>
                            )}
                            {p.agent_adjust != null && p.agent_adjust !== 0 && (
                              <span style={{ fontSize: "0.72rem", padding: "2px 7px", borderRadius: "6px", background: p.agent_adjust > 0 ? "rgba(16,185,129,0.15)" : "rgba(239,68,68,0.15)", border: `1px solid ${p.agent_adjust > 0 ? "rgba(16,185,129,0.3)" : "rgba(239,68,68,0.3)"}`, color: p.agent_adjust > 0 ? "#34d399" : "#f87171", fontWeight: 700 }} title={`AI 자기학습 보정: ${p.agent_label}`}>
                                🧠 {p.agent_adjust > 0 ? "+" : ""}{p.agent_adjust}
                              </span>
                            )}
                          </div>

                          {/* 현재가 + 추천 매수 구간 + 과열 경고 */}
                          {p.current_price != null && (
                            <div style={{ background: p.overheated ? "rgba(239,68,68,0.06)" : "rgba(16,185,129,0.05)", border: `1px solid ${p.overheated ? "rgba(239,68,68,0.25)" : "rgba(16,185,129,0.2)"}`, borderRadius: "6px", padding: "6px 8px", display: "flex", flexDirection: "column", gap: "3px" }}>
                              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                                <span style={{ fontSize: "0.68rem", color: "var(--color-muted)" }}>현재가</span>
                                <span style={{ fontWeight: 800, fontSize: "0.9rem" }}>
                                  ₩{Number(p.current_price).toLocaleString()}
                                  {p.today_change_pct != null && (
                                    <span style={{ marginLeft: "5px", fontSize: "0.72rem", fontWeight: 700, color: p.today_change_pct >= 0 ? "var(--color-danger)" : "var(--color-primary)" }}>
                                      {p.today_change_pct >= 0 ? "▲" : "▼"}{Math.abs(p.today_change_pct).toFixed(2)}%
                                    </span>
                                  )}
                                </span>
                              </div>
                              {p.buy_low != null && p.buy_high != null && (
                                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                                  <span style={{ fontSize: "0.68rem", color: "var(--color-muted)" }}>추천 매수가</span>
                                  <span style={{ fontWeight: 700, fontSize: "0.82rem", color: "#34d399" }}>
                                    ₩{Number(p.buy_low).toLocaleString()} ~ ₩{Number(p.buy_high).toLocaleString()}
                                  </span>
                                </div>
                              )}
                              {p.entry_comment && (
                                <div style={{ fontSize: "0.66rem", color: p.overheated ? "#f87171" : "var(--color-muted)", lineHeight: 1.4 }}>
                                  {p.overheated ? "⚠️ " : ""}{p.entry_comment}
                                </div>
                              )}
                            </div>
                          )}

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
                    🧠 AI 진입 전략 <AiCostBadge small />
                  </div>
                  <MarkdownLite text={data.ai_narrative} style={{ fontSize: "0.87rem", color: "var(--color-text)", lineHeight: 1.85 }} />
                </div>
              )}

              <PerformanceVerification />
              <DailyAlertCard />
            </div>
          )}
        </SSEPanel>
      )}

      {/* 수급 이동 감지 — KR/US 토글 */}
      {activeTab === "supply" && (
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
      )}

      {activeTab === "supply" && supplyMarket === "kr" && (
        <SSEPanel
          status={supplyRotation.status} message={supplyRotation.message}
          result={supplyRotation.result} fromCache={supplyRotation.fromCache} completedAt={supplyRotation.completedAt}
          onStart={supplyRotation.start} startLabel="수급 이동 분석 시작 (국내)"
          idleHint="오늘의 거래량·등락률·외국인/기관 데이터와 뉴스를 종합해 어느 종목/섹터에서 수급이 이탈/유입 중인지 실시간 분석합니다. (1~2분 소요)"
        >
          {(data) => (
            <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>

              {/* 외국인·기관 수급 현황 (KOSPI / KOSDAQ × 매수/매도) */}
              {data.frgn_inst && (
                <div style={{ background: "rgba(34,197,94,0.05)", border: "1px solid rgba(34,197,94,0.2)", borderRadius: "10px", padding: "1rem 1.2rem" }}>
                  <div style={{ fontSize: "0.78rem", fontWeight: 700, color: "#34d399", marginBottom: "0.75rem", display: "flex", alignItems: "center", gap: "0.4rem" }}>
                    💎 외국인·기관 수급 현황 (주포 자금 흐름)
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
                    {[
                      { label: "🇰🇷 KOSPI 매수 TOP", items: data.frgn_inst.kospi_buy,   color: "#f87171", bg: "rgba(239,68,68,0.06)", border: "rgba(239,68,68,0.2)" },
                      { label: "🇰🇷 KOSPI 매도 TOP", items: data.frgn_inst.kospi_sell,  color: "#60a5fa", bg: "rgba(96,165,250,0.06)", border: "rgba(96,165,250,0.2)" },
                      { label: "📈 KOSDAQ 매수 TOP", items: data.frgn_inst.kosdaq_buy,  color: "#f87171", bg: "rgba(239,68,68,0.06)", border: "rgba(239,68,68,0.2)" },
                      { label: "📈 KOSDAQ 매도 TOP", items: data.frgn_inst.kosdaq_sell, color: "#60a5fa", bg: "rgba(96,165,250,0.06)", border: "rgba(96,165,250,0.2)" },
                    ].map((card: any) => (
                      <div key={card.label} style={{ background: card.bg, border: `1px solid ${card.border}`, borderRadius: "8px", padding: "0.6rem 0.75rem" }}>
                        <div style={{ fontSize: "0.7rem", fontWeight: 700, color: card.color, marginBottom: "0.4rem" }}>{card.label}</div>
                        {!card.items || card.items.length === 0 ? (
                          <div style={{ fontSize: "0.7rem", color: "var(--color-muted)" }}>데이터 없음</div>
                        ) : (
                          <div style={{ display: "flex", flexDirection: "column", gap: "3px" }}>
                            {card.items.slice(0, 5).map((s: any, i: number) => {
                              const total = (s["외국인순매수"] || 0) + (s["기관순매수"] || 0);
                              const sign = total >= 0 ? "+" : "";
                              return (
                                <div key={i} style={{ display: "flex", justifyContent: "space-between", fontSize: "0.72rem" }}>
                                  <span style={{ color: "var(--color-text)", fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: "60%" }}>{s["종목명"]}</span>
                                  <span style={{ color: card.color, fontWeight: 700 }}>{sign}{(total/1000).toFixed(0)}K주</span>
                                </div>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* 세력 자금 흐름 (외국인·기관 실데이터 — 옛 리딩방 거래이력 패턴 대체) */}
              <SupplyPowerFlow />

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
      {activeTab === "supply" && supplyMarket === "us" && (
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

      {/* 복합 스크리너 — 규칙 기반 기술적 필터 (별도 /screener 페이지와 동일 컴포넌트) */}
      {activeTab === "screener" && <ScreenerPanel />}
    </div>
  );
}
