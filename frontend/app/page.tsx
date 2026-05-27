"use client";

import { useState, useCallback, useEffect } from "react";
import { Activity, TrendingUp, ChevronRight, Zap, Target, Clock, Star, CheckCircle, Pin, AlertCircle, BarChart2, Brain } from "lucide-react";
import { api, connectSSE } from "@/lib/api";
import { useRouter } from "next/navigation";
import useSWR from "swr";
import { PicksBoard } from "@/components/picks/PicksBoard";
import { useSSE } from "@/hooks/useSSE";
import { SSEPanel } from "@/components/ui/SSEPanel";

// 스트림 응답 타입 정의
interface AIPick {
  rank: number;
  code: string;
  name: string;
  theme: string;
  pattern: string;
  reason: string;
  entry: number;
  target: number;
  stop: number;
  urgency: string;
  horizon: string;
  position: string;
  theme_stage: string;
  supply_signal: string;
  current_price?: number;
  change_pct?: number;
}

// 토스트 알림 컴포넌트
function Toast({ message, type }: { message: string; type: "success" | "info" }) {
  return (
    <div className={`fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-2 px-5 py-3 rounded-xl shadow-2xl text-sm font-semibold animate-in slide-in-from-bottom-4 duration-300 ${
      type === "success" ? "bg-emerald-500/90 text-white border border-emerald-400/50" : "bg-indigo-500/90 text-white border border-indigo-400/50"
    }`}>
      <CheckCircle size={16} />
      {message}
    </div>
  );
}

export default function RealtimePicksBoard() {
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<"picks" | "realtime" | "rotation" | "mypattern">("picks");
  const [picks, setPicks] = useState<AIPick[]>([]);
  const [selectedPick, setSelectedPick] = useState<AIPick | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [msg, setMsg] = useState("대기 중...");
  const [marketCond, setMarketCond] = useState("");
  const [marketComment, setMarketComment] = useState("");
  const [toast, setToast] = useState<{ message: string; type: "success" | "info" } | null>(null);
  const [favLoading, setFavLoading] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);

  const rotation = useSSE<string>("/api/ai/sector-rotation", { globalId: "sector-rotation", globalTitle: "섹터 순환 분석" });
  const myPick   = useSSE<{ profile_summary: any; top_picks: any[]; ai_narrative: string }>("/api/ai/pattern-screener", { method: "POST", globalId: "pattern-screener", globalTitle: "내 패턴 스크리너" });

  const HOT_KEY    = "stockcy_hot_picks";
  const HOT_TS_KEY = "stockcy_hot_picks_ts";

  // 마운트 시 localStorage에서 이전 결과 복원
  useEffect(() => {
    try {
      const saved = localStorage.getItem(HOT_KEY);
      const ts    = localStorage.getItem(HOT_TS_KEY);
      if (saved) {
        const d = JSON.parse(saved);
        setMarketCond(d.market_condition || "");
        setMarketComment(d.market_comment || "");
        setPicks(d.picks || []);
        if (d.picks?.length > 0) setSelectedPick(d.picks[0]);
        setStatus("done");
      }
      if (ts) setLastUpdated(ts);
    } catch {}
  }, []);

  // 현재 즐겨찾기 목록 (SWR)
  const { data: favorites, mutate: mutateFavs } = useSWR(
    "/api/favorites",
    () => api.portfolio.loadFavorites(),
    { revalidateOnFocus: false }
  );

  const favSet = new Set((favorites ?? []).map((f: any) => f["티커"] ?? f.ticker));

  const showToast = (message: string, type: "success" | "info" = "success") => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 2800);
  };

  const toggleFavorite = useCallback(async (pick: AIPick) => {
    if (favLoading) return;
    setFavLoading(pick.code);
    try {
      if (favSet.has(pick.code)) {
        await api.portfolio.removeFavorite(pick.code);
        showToast(`${pick.name} 관심종목에서 제거했습니다.`, "info");
      } else {
        await api.portfolio.addFavorite("국내", pick.code, pick.name);
        showToast(`⭐ ${pick.name} 관심종목에 추가했습니다!`, "success");
      }
      await mutateFavs();
    } catch {
      showToast("저장 중 오류가 발생했습니다.", "info");
    } finally {
      setFavLoading(null);
    }
  }, [favSet, favLoading, mutateFavs]);

  const addToBacktest = useCallback((pick: AIPick) => {
    const BACKTEST_KEY = "stockcy_backtest_picks";
    try {
      const saved = localStorage.getItem(BACKTEST_KEY);
      const existing: any[] = saved ? JSON.parse(saved) : [];
      const alreadyIn = existing.some(p => p.code === pick.code);
      if (alreadyIn) {
        showToast(`${pick.name}은 이미 추적 목록에 있습니다.`, "info");
        return;
      }
      const newPick = {
        id: `${pick.code}_${Date.now()}`,
        code: pick.code,
        name: pick.name,
        theme: pick.theme,
        entry: pick.entry,
        target: pick.target,
        stop: pick.stop,
        addedAt: new Date().toISOString(),
        result: "pending",
      };
      localStorage.setItem(BACKTEST_KEY, JSON.stringify([newPick, ...existing]));
      showToast(`📌 ${pick.name} 타점 추적에 등록했습니다!`, "success");
    } catch {
      showToast("저장 실패습니다.", "info");
    }
  }, []);

  const runAnalysis = async () => {
    setStatus("loading");
    setPicks([]);
    setSelectedPick(null);
    setMsg("실시간 시장 데이터 수집 중...");

    // 최대 3.5분 후 자동 타임아웃 (서버 무응답 시 로딩 무한 대기 방지)
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 210_000);

    try {
      await connectSSE("/api/ai/realtime-picks-kr", (parsed) => {
        if (parsed.status === "running") {
          setMsg(parsed.message || "분석 중...");
        } else if (parsed.status === "done") {
          const res = parsed.result as any;
          setMarketCond(res.market_condition || "");
          setMarketComment(res.market_comment || "");
          setPicks(res.picks || []);
          if (res.picks && res.picks.length > 0) {
            setSelectedPick(res.picks[0]);
          }
          setStatus("done");
          const ts = new Date().toLocaleString("ko-KR");
          setLastUpdated(ts);
          try {
            localStorage.setItem(HOT_KEY, JSON.stringify({
              market_condition: res.market_condition || "",
              market_comment:   res.market_comment   || "",
              picks:            res.picks            || [],
            }));
            localStorage.setItem(HOT_TS_KEY, ts);
          } catch {}
        } else if (parsed.status === "error") {
          setMsg(`❌ 오류: ${parsed.message}`);
          setStatus("error");
        }
      }, { method: "POST", body: {}, signal: controller.signal });
    } catch (err: any) {
      if (err?.name === "AbortError") {
        setMsg("⏱️ AI 분析 시간이 초과됐습니다 (3.5분). 잠시 후 다시 시도해주세요.");
      } else {
        setMsg(`❌ 연결 오류: ${err.message}`);
      }
      setStatus("error");
    } finally {
      clearTimeout(timeoutId);
    }
  };

  // 계산 유틸리티
  const calcReturn = (entry: number, target: number) => {
    if (!entry || !target) return 0;
    return (((target - entry) / entry) * 100).toFixed(1);
  };
  const calcRisk = (entry: number, stop: number) => {
    if (!entry || !stop) return 0;
    return (((stop - entry) / entry) * 100).toFixed(1);
  };

  return (
    <div className="flex flex-col gap-6 animate-in fade-in duration-300">
      <header className="flex justify-between items-end border-b border-white/5 pb-4">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <h1 className="text-2xl font-bold tracking-tight text-white m-0 flex items-center gap-2">
              <Activity color="var(--color-accent)" /> 
              통합 대시보드
            </h1>
          </div>
          <p className="text-sm text-gray-400 m-0">실시간 핫 종목 및 AI 타점 추천 현황</p>
        </div>
        <div className="flex gap-1 flex-wrap">
          {([
            { id: "picks",     label: "🎯 AI 타점 추천" },
            { id: "realtime",  label: "🔥 실시간 핫 종목" },
            { id: "rotation",  label: "📊 섹터 순환매" },
            { id: "mypattern", label: "🧠 내 패턴 스크리너" },
          ] as const).map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-2 text-sm font-bold rounded-lg transition-colors ${activeTab === tab.id ? "bg-white/10 text-white border border-white/20" : "text-gray-400 hover:text-white"}`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </header>

      {activeTab === "picks" && <PicksBoard />}

      {activeTab === "rotation" && (
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
      )}

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

      {activeTab === "realtime" && (
        <>
          <div className="flex justify-between items-center mb-[-1rem]">
            {status === "done" && picks.length > 0 && (
              <span className="px-2 py-1 rounded bg-red-500/20 text-red-400 text-xs font-bold border border-red-500/30 flex items-center gap-1 animate-pulse">
                🔥 {picks.length}개 신호 포착
              </span>
            )}
          </div>
          <div className="flex justify-between items-end">
            <div>
              <p className="text-zinc-400 text-sm m-0">거래량 급증, 돌파 패턴, 수급 유입 종목을 실시간으로 추적하여 타점을 계산합니다.</p>
              {lastUpdated && (
                <p className="text-zinc-600 text-xs m-0 mt-1">마지막 업데이트: {lastUpdated}</p>
              )}
            </div>
            <button
              onClick={runAnalysis}
              disabled={status === "loading"}
              className="stockcy-btn-primary flex items-center gap-2 px-5 py-2 text-sm font-semibold rounded-md shadow-lg shadow-indigo-500/20"
            >
              {status === "loading" ? <><Activity size={16} className="animate-spin" /> {msg}</> : <><Zap size={16} /> 타점 포착 실행</>}
            </button>
          </div>

      {/* 시장 코멘트 */}
      {status === "done" && (
        <div className="bg-indigo-500/10 border border-indigo-500/30 p-4 rounded-lg flex items-start gap-3">
          <Activity className="text-indigo-400 mt-0.5" size={18} />
          <div>
            <div className="font-bold text-indigo-300 mb-1">{marketCond || "현재 시장 상태"}</div>
            <div className="text-sm text-indigo-200/80 leading-relaxed">{marketComment}</div>
          </div>
        </div>
      )}
      
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* 좌측 패널: 신호 리스트 */}
        <section className="lg:col-span-4 flex flex-col gap-3">
          <div className="flex items-center justify-between px-1">
            <h2 className="font-bold text-sm text-zinc-300 flex items-center gap-2">
              <TrendingUp size={16} className="text-emerald-400" /> 포착 리스트
            </h2>
          </div>

          {status === "idle" && (
            <div className="stockcy-card p-10 flex flex-col items-center justify-center text-zinc-500 gap-3">
              <Target size={32} className="text-zinc-600" />
              <p className="text-sm">우측 상단의 '타점 포착 실행' 버튼을 눌러주세요.</p>
            </div>
          )}

          {status === "loading" && (
            <div className="stockcy-card p-10 flex flex-col items-center justify-center text-indigo-400 gap-4">
              <Activity size={32} className="animate-spin opacity-50" />
              <p className="text-sm font-medium animate-pulse">{msg}</p>
            </div>
          )}

          {status === "error" && (
            <div className="stockcy-card p-8 flex flex-col items-center justify-center text-red-400 gap-3 text-center">
              <AlertCircle size={32} className="text-red-500 opacity-70" />
              <p className="text-sm font-medium">{msg}</p>
              <p className="text-xs text-zinc-500">버튼을 다시 눌러 재시도하세요.</p>
            </div>
          )}

          {status === "done" && picks.length === 0 && (
            <div className="stockcy-card p-10 text-center text-zinc-400 text-sm">
              현재 포착된 조건 만족 종목이 없습니다.
            </div>
          )}

          <div className="flex flex-col gap-2">
            {picks.map((p) => (
              <div 
                key={p.code}
                onClick={() => setSelectedPick(p)}
                className={`p-4 rounded-lg cursor-pointer transition-all border ${
                  selectedPick?.code === p.code 
                    ? "bg-white/10 border-indigo-500 shadow-md shadow-indigo-500/10" 
                    : "bg-white/5 border-white/5 hover:bg-white/10"
                }`}
              >
                <div className="flex justify-between items-start mb-2">
                  <div>
                    <div className="font-bold text-base text-white">{p.name}</div>
                    <div className="text-xs text-zinc-400">{p.code}</div>
                  </div>
                  <div className={`text-[0.65rem] font-bold px-2 py-0.5 rounded ${
                    p.urgency.includes("즉시") ? "bg-red-500/20 text-red-400 border border-red-500/30" : "bg-orange-500/20 text-orange-400 border border-orange-500/30"
                  }`}>
                    {p.urgency}
                  </div>
                </div>
                
                <div className="flex items-center justify-between text-xs mt-3">
                  <div className="text-emerald-400 font-semibold bg-emerald-400/10 px-2 py-1 rounded border border-emerald-400/20">
                    기대 +{calcReturn(p.entry, p.target)}%
                  </div>
                  <div className="text-zinc-400">
                    {p.theme}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* 우측 패널: 상세 분석 */}
        <section className="lg:col-span-8">
          {!selectedPick ? (
            <div className="stockcy-card h-[400px] flex items-center justify-center text-zinc-500 text-sm">
              종목을 선택하면 상세 타점 정보가 표시됩니다.
            </div>
          ) : (
            <div className="flex flex-col gap-4">
              {/* 메인 상세 카드 */}
              <div className="stockcy-card p-6 border-t-4 border-t-indigo-500">
                <div className="flex justify-between items-start mb-6 border-b border-white/5 pb-4">
                  <div>
                    <div className="flex items-center gap-3 mb-1 flex-wrap">
                      <h2 className="text-2xl font-bold text-white">{selectedPick.name}</h2>
                      <span className="text-zinc-400 font-medium">{selectedPick.code}</span>
                      {selectedPick.current_price != null && (
                        <span className="text-lg font-bold" style={{ color: (selectedPick.change_pct ?? 0) > 0 ? "var(--color-up)" : (selectedPick.change_pct ?? 0) < 0 ? "var(--color-down)" : "var(--color-flat)" }}>
                          ₩{selectedPick.current_price.toLocaleString()}
                          <span className="text-sm ml-1">
                            {(selectedPick.change_pct ?? 0) > 0 ? "▲" : (selectedPick.change_pct ?? 0) < 0 ? "▼" : "─"}
                            {Math.abs(selectedPick.change_pct ?? 0).toFixed(2)}%
                          </span>
                        </span>
                      )}
                    </div>
                    <div className="flex gap-2 text-xs mt-3 flex-wrap">
                      <span className="px-2 py-1 bg-white/5 text-zinc-300 rounded border border-white/10">{selectedPick.position}</span>
                      <span className="px-2 py-1 bg-white/5 text-zinc-300 rounded border border-white/10">{selectedPick.theme_stage}</span>
                      <span className="px-2 py-1 bg-orange-500/15 text-orange-300 rounded border border-orange-500/25 font-medium">{selectedPick.pattern}</span>
                      <span className="px-2 py-1 bg-white/5 text-zinc-400 rounded border border-white/10">{selectedPick.horizon}</span>
                      <span className="px-2 py-1 bg-indigo-500/20 text-indigo-300 rounded border border-indigo-500/30 font-medium">수급: {selectedPick.supply_signal}</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {/* 관심종목 담기 버튼 */}
                    <button
                      onClick={() => toggleFavorite(selectedPick)}
                      disabled={favLoading === selectedPick.code}
                      title={favSet.has(selectedPick.code) ? "관심종목 제거" : "관심종목 담기"}
                      className={`flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded transition-all border ${
                        favSet.has(selectedPick.code)
                          ? "bg-yellow-500/20 text-yellow-400 border-yellow-500/40 hover:bg-yellow-500/30"
                          : "bg-white/5 text-zinc-400 border-white/10 hover:bg-yellow-500/10 hover:text-yellow-400 hover:border-yellow-500/30"
                      } disabled:opacity-50`}
                    >
                      <Star size={13} className={favSet.has(selectedPick.code) ? "fill-yellow-400 text-yellow-400" : ""} />
                      {favLoading === selectedPick.code ? "저장 중..." : favSet.has(selectedPick.code) ? "관심종목 해제" : "관심종목 담기"}
                    </button>
                    {/* 백테스트 추가 버튼 */}
                    <button
                      onClick={() => addToBacktest(selectedPick)}
                      title="타점 추적 등록"
                      className="flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded transition-all border bg-indigo-500/10 text-indigo-400 border-indigo-500/20 hover:bg-indigo-500/20"
                    >
                      <Pin size={12} /> 타점 추적
                    </button>
                    <button 
                      onClick={() => router.push(`/search?market=KR&q=${selectedPick.code}`)}
                      className="flex items-center gap-1 text-xs font-semibold bg-white/5 hover:bg-white/10 text-white px-3 py-1.5 rounded transition border border-white/10"
                    >
                      차트 및 상세 분석 <ChevronRight size={14} />
                    </button>
                  </div>
                </div>

                <div className="text-sm text-zinc-300 leading-relaxed bg-white/5 p-4 rounded-lg mb-6 border border-white/5">
                  <span className="font-bold text-white block mb-1 flex items-center gap-2"><Target size={14} className="text-indigo-400" /> 포착 이유</span>
                  {selectedPick.reason}
                </div>

                {/* 2x2 타점 그리드 */}
                <h3 className="text-sm font-bold text-zinc-400 mb-3 ml-1 flex items-center gap-2">
                  <Activity size={14} /> 매매 가이드라인
                </h3>
                <div className="grid grid-cols-2 gap-3">
                  <div className="bg-emerald-500/10 border border-emerald-500/20 p-4 rounded-lg flex flex-col justify-center items-center text-center">
                    <span className="text-xs font-bold text-emerald-400/80 mb-1">매수 진입가</span>
                    <span className="text-xl font-black text-emerald-400">₩{selectedPick.entry.toLocaleString()}</span>
                    <span className="text-[0.65rem] text-emerald-400/60 mt-1">이탈 시 관망</span>
                  </div>
                  
                  <div className="bg-red-500/10 border border-red-500/20 p-4 rounded-lg flex flex-col justify-center items-center text-center">
                    <span className="text-xs font-bold text-red-400/80 mb-1">목표가</span>
                    <span className="text-xl font-black text-red-400">₩{selectedPick.target.toLocaleString()}</span>
                    <span className="text-[0.7rem] font-bold text-red-400 mt-1">+{calcReturn(selectedPick.entry, selectedPick.target)}% 기대</span>
                  </div>

                  <div className="bg-blue-500/10 border border-blue-500/20 p-4 rounded-lg flex flex-col justify-center items-center text-center">
                    <span className="text-xs font-bold text-blue-400/80 mb-1">손절가</span>
                    <span className="text-xl font-black text-blue-400">₩{selectedPick.stop.toLocaleString()}</span>
                    <span className="text-[0.7rem] font-bold text-blue-400 mt-1">{calcRisk(selectedPick.entry, selectedPick.stop)}% 위험</span>
                  </div>

                  <div className="bg-orange-500/10 border border-orange-500/20 p-4 rounded-lg flex flex-col justify-center items-center text-center">
                    <span className="text-xs font-bold text-orange-400/80 mb-1">현재가</span>
                    {selectedPick.current_price != null ? (
                      <>
                        <span className="text-xl font-black text-orange-400">₩{selectedPick.current_price.toLocaleString()}</span>
                        <span className="text-[0.7rem] font-bold text-orange-400 mt-1"
                          style={{ color: (selectedPick.change_pct ?? 0) > 0 ? "var(--color-up)" : (selectedPick.change_pct ?? 0) < 0 ? "var(--color-down)" : "var(--color-flat)" }}>
                          {(selectedPick.change_pct ?? 0) > 0 ? "▲" : (selectedPick.change_pct ?? 0) < 0 ? "▼" : "─"}{Math.abs(selectedPick.change_pct ?? 0).toFixed(2)}%
                        </span>
                      </>
                    ) : (
                      <>
                        <Clock size={20} className="text-orange-400 my-1" />
                        <span className="text-sm font-bold text-orange-400 mt-1">{selectedPick.horizon}</span>
                      </>
                    )}
                  </div>
                </div>

              </div>
            </div>
          )}
        </section>
      </div>
      </>
      )}

      {/* 토스트 알림 */}
      {toast && <Toast message={toast.message} type={toast.type} />}
    </div>
  );
}
