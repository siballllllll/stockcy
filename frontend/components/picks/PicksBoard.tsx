"use client";
import { useState, useEffect, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  Target, TrendingUp, AlertCircle, Clock, Activity, Loader2, RefreshCw,
  LayoutGrid, List, Star, Pin, ChevronRight, CheckCircle,
} from "lucide-react";
import { connectSSE, api } from "@/lib/api";
import { useMarket } from "@/lib/market-context";
import { useAnalysisReady } from "@/lib/analysis-ready-context";
import useSWR from "swr";

interface Pick {
  code?:         string;
  ticker?:       string;
  name:          string;
  theme?:        string;
  pattern?:      string;
  reason?:       string;
  entry?:        number;
  target?:       number;
  stop?:         number;
  urgency?:      string;
  horizon?:      string;
  position?:     string;
  theme_stage?:  string;
  supply_signal?: string;
  current_price?: number;
  change_pct?:   number;
  leader_name?:  string;
  theme_linkage?: string;
}

function Toast({ message, type }: { message: string; type: "success" | "info" }) {
  return (
    <div className={`fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-2 px-5 py-3 rounded-xl shadow-2xl text-sm font-semibold animate-in slide-in-from-bottom-4 duration-300 ${
      type === "success"
        ? "bg-emerald-500/90 text-white border border-emerald-400/50"
        : "bg-indigo-500/90 text-white border border-indigo-400/50"
    }`}>
      <CheckCircle size={16} />
      {message}
    </div>
  );
}

const picksKey   = (mkt: string) => `stockcy_picks_${mkt.toLowerCase()}`;
const picksTsKey = (mkt: string) => `stockcy_picks_${mkt.toLowerCase()}_ts`;

export function PicksBoard() {
  const router   = useRouter();
  const { market } = useMarket();
  const isKR     = market === "KR";

  const [viewMode,      setViewMode]      = useState<"card" | "detail">("card");
  const [filter,        setFilter]        = useState("전체");
  const [loading,       setLoading]       = useState(false);
  const [statusMsg,     setStatusMsg]     = useState("");
  const [errorMsg,      setErrorMsg]      = useState("");
  const [data,          setData]          = useState<{ market_comment?: string; market_condition?: string; picks: Pick[] }>({ picks: [] });
  const [lastUpdated,   setLastUpdated]   = useState<Date | null>(null);
  const [selectedPick,  setSelectedPick]  = useState<Pick | null>(null);
  const [toast,         setToast]         = useState<{ message: string; type: "success" | "info" } | null>(null);
  const [favLoading,    setFavLoading]    = useState<string | null>(null);

  const { setReady }  = useAnalysisReady();
  const prevMarket    = useRef(market);
  const unmountedRef  = useRef(false);

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

  const loadFromStorage = (mkt: string) => {
    try {
      const saved = localStorage.getItem(picksKey(mkt));
      const ts    = localStorage.getItem(picksTsKey(mkt));
      if (saved) {
        const parsed = JSON.parse(saved);
        setData(parsed);
        setSelectedPick(parsed.picks?.[0] ?? null);
        setLastUpdated(ts ? new Date(ts) : null);
        return true;
      }
    } catch {}
    setData({ picks: [] });
    setSelectedPick(null);
    setLastUpdated(null);
    return false;
  };

  // 마운트 시 캐시 로드
  useEffect(() => { loadFromStorage(market); }, []);

  // 시장 전환 시 해당 시장 캐시 로드
  useEffect(() => {
    if (prevMarket.current !== market) {
      prevMarket.current = market;
      unmountedRef.current = true;
      setLoading(false);
      setReady("picks", false);
      loadFromStorage(market);
    }
    return () => { unmountedRef.current = true; };
  }, [market]);

  const startAnalysis = (mkt: string) => {
    if (loading) return;
    unmountedRef.current = false;
    const kr = mkt === "KR";
    setLoading(true);
    setErrorMsg("");
    setStatusMsg(kr ? "AI 분석 엔진 가동 중..." : "🇺🇸 US AI 분석 엔진 가동 중...");

    const endpoint   = kr ? "/api/ai/realtime-picks-kr" : "/api/ai/realtime-picks-us";
    const controller = new AbortController();
    const timeoutId  = setTimeout(() => controller.abort(), 210_000);

    connectSSE(endpoint, (evt) => {
      if (unmountedRef.current) return;
      if (evt.status === "running") {
        setStatusMsg(evt.message || "분석 중...");
      } else if (evt.status === "done") {
        const result = evt.result as any;
        if (result?.error && !result?.picks?.length) {
          setErrorMsg(`AI 분석 실패: ${result.error}`);
          setLoading(false);
          return;
        }
        setData(result);
        setSelectedPick(result.picks?.[0] ?? null);
        const now = new Date();
        setLastUpdated(now);
        setLoading(false);
        setReady("picks", true);
        try {
          localStorage.setItem(picksKey(mkt), JSON.stringify(result));
          localStorage.setItem(picksTsKey(mkt), now.toISOString());
        } catch {}
      } else if (evt.status === "error") {
        setErrorMsg(`오류: ${evt.message}`);
        setLoading(false);
      }
    }, { method: "POST", body: {}, signal: controller.signal })
      .then(() => { clearTimeout(timeoutId); if (!unmountedRef.current) setLoading(false); })
      .catch((err: any) => {
        clearTimeout(timeoutId);
        if (!unmountedRef.current) {
          setErrorMsg(err?.name === "AbortError"
            ? "⏱️ AI 분析 시간이 초과됐습니다 (3.5분). 잠시 후 다시 시도해주세요."
            : "서버 연결 실패");
          setLoading(false);
        }
      });
  };

  const toggleFavorite = useCallback(async (pick: Pick) => {
    const id = isKR ? pick.code! : pick.ticker!;
    if (favLoading) return;
    setFavLoading(id);
    try {
      if (favSet.has(id)) {
        await api.portfolio.removeFavorite(id);
        showToast(`${pick.name} 관심종목에서 제거했습니다.`, "info");
      } else {
        await api.portfolio.addFavorite(isKR ? "국내" : "미국", id, pick.name);
        showToast(`⭐ ${pick.name} 관심종목에 추가했습니다!`, "success");
      }
      await mutateFavs();
    } catch {
      showToast("저장 중 오류가 발생했습니다.", "info");
    } finally {
      setFavLoading(null);
    }
  }, [favSet, favLoading, mutateFavs, isKR]);

  const addToBacktest = useCallback((pick: Pick) => {
    const id = isKR ? pick.code! : pick.ticker!;
    const KEY = "stockcy_backtest_picks";
    try {
      const existing: any[] = JSON.parse(localStorage.getItem(KEY) || "[]");
      if (existing.some(p => p.code === id)) {
        showToast(`${pick.name}은 이미 추적 목록에 있습니다.`, "info");
        return;
      }
      localStorage.setItem(KEY, JSON.stringify([{
        id: `${id}_${Date.now()}`, code: id, name: pick.name, theme: pick.theme,
        entry: pick.entry, target: pick.target, stop: pick.stop,
        addedAt: new Date().toISOString(), result: "pending",
      }, ...existing]));
      showToast(`📌 ${pick.name} 타점 추적에 등록했습니다!`, "success");
    } catch {
      showToast("저장 실패했습니다.", "info");
    }
  }, [isKR]);

  // ── 계산 헬퍼 ──────────────────────────────────────────────────────────────
  const fmt = (v?: number) => isKR
    ? `₩${v?.toLocaleString() ?? "—"}`
    : `$${v?.toFixed(2) ?? "—"}`;

  const calcReturn = (entry?: number, target?: number) =>
    entry && target ? (((target - entry) / entry) * 100).toFixed(1) : "0";

  const calcRisk = (entry?: number, stop?: number) =>
    entry && stop ? (((stop - entry) / entry) * 100).toFixed(1) : "0";

  const picks       = data.picks || [];
  const urgentCount = picks.filter(p => p.urgency?.includes("즉시")).length;
  const swingCount  = picks.filter(p => p.horizon?.includes("스윙")).length;
  const timeLabel   = lastUpdated
    ? (lastUpdated.toDateString() === new Date().toDateString()
        ? lastUpdated.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" })
        : lastUpdated.toLocaleString("ko-KR", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }))
    : "—";

  const filteredPicks = picks.filter(p => {
    if (filter === "전체")    return true;
    if (filter === "극단타")  return p.horizon?.includes("스캘핑") || p.urgency?.includes("즉시");
    if (filter === "단기스윙") return p.horizon?.includes("스윙");
    return true;
  });

  const identifier = (p: Pick) => isKR ? p.code : p.ticker;

  // ── 렌더 ──────────────────────────────────────────────────────────────────
  return (
    <div style={{ width: "100%", display: "flex", flexDirection: "column", gap: "1.2rem" }}>

      {/* 헤더 */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", borderBottom: "1px solid rgba(255,255,255,0.05)", paddingBottom: "1rem", flexWrap: "wrap", gap: "0.75rem" }}>
        <div>
          <h1 style={{ fontSize: "1.6rem", fontWeight: 800, margin: "0 0 0.5rem 0", display: "flex", alignItems: "center", gap: "8px" }}>
            <Target color="var(--color-danger)" />
            {isKR ? "🇰🇷 국내 실시간 타점 포착" : "🇺🇸 미국 실시간 타점 포착"}
          </h1>
          <div style={{ fontSize: "0.85rem", color: "var(--color-muted)", display: "flex", alignItems: "center", gap: "6px", flexWrap: "wrap" }}>
            <Activity size={14} />
            {isKR
              ? "AI가 당일 주도 테마와 수급을 융합하여 5~10% 단타 구간을 찾아냅니다."
              : "AI가 US 시장 거래량·급등 패턴을 분석하여 스캘핑 타점을 찾아냅니다."}
            {data.market_condition && (
              <span style={{ color: "var(--color-accent)", marginLeft: "8px" }}>[{data.market_condition}]</span>
            )}
          </div>
        </div>

        <div style={{ display: "flex", gap: "6px", alignItems: "center", flexWrap: "wrap" }}>
          {/* 카드 / 상세 뷰 토글 */}
          <div style={{ display: "flex", background: "rgba(255,255,255,0.05)", borderRadius: "6px", padding: "2px", border: "1px solid var(--color-border)" }}>
            {([
              { id: "card"   as const, icon: <LayoutGrid size={14} />, title: "카드뷰" },
              { id: "detail" as const, icon: <List       size={14} />, title: "상세뷰" },
            ]).map(v => (
              <button key={v.id} onClick={() => setViewMode(v.id)} title={v.title} style={{
                padding: "4px 10px", borderRadius: "4px", border: "none", cursor: "pointer", transition: "0.15s",
                background: viewMode === v.id ? "rgba(255,255,255,0.15)" : "transparent",
                color: viewMode === v.id ? "var(--color-text)" : "var(--color-muted)",
                display: "flex", alignItems: "center",
              }}>{v.icon}</button>
            ))}
          </div>

          <button
            onClick={() => startAnalysis(market)}
            disabled={loading}
            className="stockcy-btn stockcy-btn-primary"
            style={{ display: "flex", alignItems: "center", gap: "5px", padding: "6px 14px", fontSize: "0.85rem" }}
          >
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
            {loading ? "분析 중..." : picks.length > 0 ? "재분석" : "AI 분析 시작"}
          </button>

          {/* 필터 (카드뷰에서만) */}
          {viewMode === "card" && ["전체", "극단타", "단기스윙"].map(f => (
            <button key={f} onClick={() => setFilter(f)} style={{
              padding: "6px 12px", fontSize: "0.85rem", fontWeight: 700, borderRadius: "4px", border: "1px solid",
              borderColor: filter === f ? "var(--color-accent)" : "var(--color-border)",
              background: filter === f ? "rgba(255,255,255,0.1)" : "transparent",
              color: filter === f ? "var(--color-text)" : "var(--color-muted)",
              cursor: "pointer", transition: "0.2s",
            }}>{f}</button>
          ))}
        </div>
      </div>

      {/* 요약 통계 */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: "10px", marginBottom: "0.5rem" }}>
        {[
          { label: "신규 포착",     val: picks.length > 0 ? `${picks.length}건` : "—", icon: <AlertCircle size={16} color="var(--color-danger)" /> },
          { label: "즉시진입 긴급", val: urgentCount > 0 ? `${urgentCount}건` : "—",   icon: <TrendingUp  size={16} color="var(--color-warning)" /> },
          { label: "단기 스윙",     val: swingCount > 0  ? `${swingCount}건`  : "—",   icon: <Target      size={16} color="var(--color-success)" /> },
          { label: "업데이트",      val: timeLabel,                                      icon: <Clock       size={16} color="var(--color-muted)" /> },
        ].map((s, i) => (
          <div key={i} style={{ background: "rgba(255,255,255,0.02)", border: "1px solid var(--color-border)", padding: "10px", borderRadius: "6px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "0.8rem", color: "var(--color-muted)" }}>{s.icon} {s.label}</div>
            <div style={{ fontWeight: 800, fontSize: "1rem" }}>{s.val}</div>
          </div>
        ))}
      </div>

      {/* 로딩 */}
      {loading && (
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "4rem 0", gap: "1rem" }}>
          <Loader2 className="animate-spin" size={40} color="var(--color-danger)" />
          <div style={{ color: "var(--color-muted)", fontWeight: 600 }}>{statusMsg}</div>
          <div style={{ fontSize: "0.8rem", color: "var(--color-subtle)" }}>KR: 약 1~2분 소요 (핫 섹터 AI 분석 + 타점 AI 선정)</div>
        </div>
      )}

      {/* 빈 상태 */}
      {!loading && picks.length === 0 && (
        <div style={{ padding: "4rem 0", textAlign: "center", color: "var(--color-muted)", display: "flex", flexDirection: "column", alignItems: "center", gap: "1rem" }}>
          {errorMsg ? (
            <>
              <AlertCircle size={48} color="var(--color-danger)" style={{ opacity: 0.7 }} />
              <div style={{ color: "var(--color-danger)", fontWeight: 600 }}>{errorMsg}</div>
              <div style={{ fontSize: "0.8rem", color: "var(--color-subtle)" }}>다시 분析 버튼을 눌러 재시도하세요.</div>
            </>
          ) : (
            <>
              <Target size={48} style={{ opacity: 0.3 }} />
              <div>위 &apos;AI 分析 시작&apos; 버튼을 눌러 오늘의 타점을 분析하세요.</div>
              <div style={{ fontSize: "0.8rem", color: "var(--color-subtle)" }}>
                {isKR ? "거래량·수급·핫 섹터 종합 AI 분析 → 3종목 타점 선정" : "US 거래량·모멘텀 분析 → 타점 선정"}
              </div>
            </>
          )}
        </div>
      )}

      {/* ── 카드뷰 ─────────────────────────────────────────────────────────── */}
      {!loading && picks.length > 0 && viewMode === "card" && (
        filteredPicks.length === 0 ? (
          <div style={{ padding: "4rem 0", textAlign: "center", color: "var(--color-muted)" }}>조건에 맞는 타점이 없습니다.</div>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: "1rem" }}>
            {filteredPicks.map((pick, idx) => {
              const isUp        = (pick.change_pct || 0) > 0;
              const id          = identifier(pick);
              const marketParam = isKR ? "" : "&market=US";
              const urgencyColor =
                pick.urgency?.includes("즉시") ? "var(--color-danger)" :
                pick.urgency?.includes("대기") ? "var(--color-warning)" : "var(--color-success)";

              return (
                <div key={id || idx} className="stockcy-card hover-highlight"
                  onClick={() => id && router.push(`/search?q=${id}${marketParam}`)}
                  style={{ padding: "14px", borderTop: `3px solid ${urgencyColor}`, background: "rgba(255,255,255,0.02)", cursor: "pointer", display: "flex", flexDirection: "column", gap: "10px" }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                    <div>
                      <h3 style={{ margin: 0, fontSize: "1rem", fontWeight: 800 }}>{pick.name}</h3>
                      <span style={{ fontSize: "0.75rem", color: "var(--color-muted)" }}>{id}</span>
                    </div>
                    <div style={{ display: "flex", gap: "4px" }}>
                      <span style={{ fontSize: "0.7rem", fontWeight: 700, padding: "2px 6px", background: "rgba(255,255,255,0.1)", borderRadius: "4px" }}>{pick.horizon || "단타"}</span>
                      <span style={{ fontSize: "0.7rem", fontWeight: 700, padding: "2px 6px", background: urgencyColor, color: "var(--bg-color)", borderRadius: "4px" }}>{pick.urgency || "보통"}</span>
                    </div>
                  </div>

                  <div style={{ display: "flex", alignItems: "baseline", gap: "6px" }}>
                    <span style={{ fontSize: "1.2rem", fontWeight: 800 }}>{fmt(pick.current_price)}</span>
                    <span style={{ fontSize: "0.85rem", fontWeight: 700, color: isUp ? "var(--color-danger)" : "var(--color-primary)" }}>
                      {isUp ? "▲" : "▼"} {Math.abs(pick.change_pct || 0).toFixed(2)}%
                    </span>
                  </div>

                  {(pick.entry || pick.target || pick.stop) && (
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "6px", fontSize: "0.78rem" }}>
                      {[
                        { label: "매수 타점", val: fmt(pick.entry),  bg: "rgba(0,255,0,0.05)",   color: "var(--color-success)" },
                        { label: "목표가",   val: fmt(pick.target), bg: "rgba(255,200,0,0.05)", color: "var(--color-warning)" },
                        { label: "손절가",   val: fmt(pick.stop),   bg: "rgba(255,0,0,0.05)",   color: "var(--color-danger)"  },
                      ].map(item => (
                        <div key={item.label} style={{ textAlign: "center", background: item.bg, padding: "4px", borderRadius: "4px" }}>
                          <div style={{ color: "var(--color-muted)" }}>{item.label}</div>
                          <div style={{ fontWeight: 700, color: item.color }}>{item.val}</div>
                        </div>
                      ))}
                    </div>
                  )}

                  {isKR && (pick.position || pick.theme_stage || pick.leader_name || pick.supply_signal) && (
                    <div style={{ display: "flex", gap: "6px", flexWrap: "wrap", fontSize: "0.73rem" }}>
                      {pick.position    && <span style={{ padding: "2px 7px", borderRadius: "4px", background: "rgba(255,200,0,0.1)",  border: "1px solid rgba(255,200,0,0.3)",  color: "#ffd740" }}>{pick.position}</span>}
                      {pick.theme_stage && <span style={{ padding: "2px 7px", borderRadius: "4px", background: "rgba(100,200,100,0.1)", border: "1px solid rgba(100,200,100,0.3)", color: "#69f0ae" }}>{pick.theme_stage}</span>}
                      {pick.leader_name && <span style={{ padding: "2px 7px", borderRadius: "4px", background: "rgba(200,100,255,0.1)", border: "1px solid rgba(200,100,255,0.3)", color: "#ce93d8" }}>대장: {pick.leader_name}</span>}
                      {pick.supply_signal && <span style={{ padding: "2px 7px", borderRadius: "4px", background: "rgba(100,180,255,0.1)", border: "1px solid rgba(100,180,255,0.3)", color: "#60a5fa" }}>{pick.supply_signal}</span>}
                    </div>
                  )}

                  {isKR && pick.theme_linkage && (
                    <div style={{ fontSize: "0.76rem", color: "#8ecdf7", background: "rgba(100,180,255,0.05)", border: "1px solid rgba(100,180,255,0.15)", borderRadius: "4px", padding: "5px 8px", lineHeight: 1.5 }}>
                      🔗 {pick.theme_linkage}
                    </div>
                  )}

                  <div style={{ fontSize: "0.8rem", color: "var(--color-subtle)", lineHeight: 1.4, background: "rgba(0,0,0,0.2)", padding: "8px", borderRadius: "4px" }}>
                    <span style={{ color: "var(--color-accent)", fontWeight: 700 }}>[{pick.pattern || pick.theme}]</span>{" "}{pick.reason}
                  </div>
                </div>
              );
            })}
          </div>
        )
      )}

      {/* ── 상세뷰 ─────────────────────────────────────────────────────────── */}
      {!loading && picks.length > 0 && viewMode === "detail" && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">

          {/* 좌측: 리스트 */}
          <section className="lg:col-span-4 flex flex-col gap-3">
            <h2 className="font-bold text-sm text-zinc-300 flex items-center gap-2 px-1">
              <TrendingUp size={16} className="text-emerald-400" /> 포착 리스트
            </h2>
            {picks.map(p => {
              const id      = identifier(p);
              const active  = selectedPick ? identifier(selectedPick) === id : false;
              return (
                <div key={id} onClick={() => setSelectedPick(p)}
                  className={`p-4 rounded-lg cursor-pointer transition-all border ${active ? "bg-white/10 border-indigo-500 shadow-md shadow-indigo-500/10" : "bg-white/5 border-white/5 hover:bg-white/10"}`}
                >
                  <div className="flex justify-between items-start mb-2">
                    <div>
                      <div className="font-bold text-base text-white">{p.name}</div>
                      <div className="text-xs text-zinc-400">{id}</div>
                    </div>
                    <div className={`text-[0.65rem] font-bold px-2 py-0.5 rounded ${p.urgency?.includes("즉시") ? "bg-red-500/20 text-red-400 border border-red-500/30" : "bg-orange-500/20 text-orange-400 border border-orange-500/30"}`}>
                      {p.urgency}
                    </div>
                  </div>
                  <div className="flex items-center justify-between text-xs mt-3">
                    <div className="text-emerald-400 font-semibold bg-emerald-400/10 px-2 py-1 rounded border border-emerald-400/20">
                      기대 +{calcReturn(p.entry, p.target)}%
                    </div>
                    <div className="text-zinc-400">{p.theme}</div>
                  </div>
                </div>
              );
            })}
          </section>

          {/* 우측: 상세 */}
          <section className="lg:col-span-8">
            {!selectedPick ? (
              <div className="stockcy-card h-[400px] flex items-center justify-center text-zinc-500 text-sm">
                종목을 선택하면 상세 타점 정보가 표시됩니다.
              </div>
            ) : (() => {
              const sp    = selectedPick;
              const id    = identifier(sp)!;
              const isFav = favSet.has(id);
              const changePct = sp.change_pct ?? 0;
              const priceColor = changePct > 0 ? "var(--color-up)" : changePct < 0 ? "var(--color-down)" : "var(--color-flat)";

              return (
                <div className="flex flex-col gap-4">
                  <div className="stockcy-card p-6 border-t-4 border-t-indigo-500">

                    {/* 종목 헤더 */}
                    <div className="flex justify-between items-start mb-6 border-b border-white/5 pb-4 flex-wrap gap-3">
                      <div>
                        <div className="flex items-center gap-3 mb-1 flex-wrap">
                          <h2 className="text-2xl font-bold text-white">{sp.name}</h2>
                          <span className="text-zinc-400 font-medium">{id}</span>
                          {sp.current_price != null && (
                            <span className="text-lg font-bold" style={{ color: priceColor }}>
                              {fmt(sp.current_price)}
                              <span className="text-sm ml-1">
                                {changePct > 0 ? "▲" : changePct < 0 ? "▼" : "─"}{Math.abs(changePct).toFixed(2)}%
                              </span>
                            </span>
                          )}
                        </div>
                        <div className="flex gap-2 text-xs mt-3 flex-wrap">
                          {sp.position     && <span className="px-2 py-1 bg-white/5 text-zinc-300 rounded border border-white/10">{sp.position}</span>}
                          {sp.theme_stage  && <span className="px-2 py-1 bg-white/5 text-zinc-300 rounded border border-white/10">{sp.theme_stage}</span>}
                          {sp.pattern      && <span className="px-2 py-1 bg-orange-500/15 text-orange-300 rounded border border-orange-500/25 font-medium">{sp.pattern}</span>}
                          {sp.horizon      && <span className="px-2 py-1 bg-white/5 text-zinc-400 rounded border border-white/10">{sp.horizon}</span>}
                          {sp.supply_signal && <span className="px-2 py-1 bg-indigo-500/20 text-indigo-300 rounded border border-indigo-500/30 font-medium">수급: {sp.supply_signal}</span>}
                        </div>
                      </div>

                      {/* 액션 버튼 */}
                      <div className="flex items-center gap-2 flex-wrap">
                        <button
                          onClick={() => toggleFavorite(sp)}
                          disabled={favLoading === id}
                          className={`flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded transition-all border disabled:opacity-50 ${isFav ? "bg-yellow-500/20 text-yellow-400 border-yellow-500/40" : "bg-white/5 text-zinc-400 border-white/10 hover:bg-yellow-500/10 hover:text-yellow-400"}`}
                        >
                          <Star size={13} className={isFav ? "fill-yellow-400 text-yellow-400" : ""} />
                          {favLoading === id ? "저장 중..." : isFav ? "관심종목 해제" : "관심종목 담기"}
                        </button>
                        <button onClick={() => addToBacktest(sp)} className="flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded transition-all border bg-indigo-500/10 text-indigo-400 border-indigo-500/20 hover:bg-indigo-500/20">
                          <Pin size={12} /> 타점 추적
                        </button>
                        <button onClick={() => router.push(`/search?market=${isKR ? "KR" : "US"}&q=${id}`)} className="flex items-center gap-1 text-xs font-semibold bg-white/5 hover:bg-white/10 text-white px-3 py-1.5 rounded border border-white/10">
                          차트 및 상세 분析 <ChevronRight size={14} />
                        </button>
                      </div>
                    </div>

                    {/* 포착 이유 */}
                    <div className="text-sm text-zinc-300 leading-relaxed bg-white/5 p-4 rounded-lg mb-6 border border-white/5">
                      <span className="font-bold text-white block mb-1 flex items-center gap-2">
                        <Target size={14} className="text-indigo-400" /> 포착 이유
                      </span>
                      {sp.reason}
                    </div>

                    {/* 2×2 타점 그리드 */}
                    <h3 className="text-sm font-bold text-zinc-400 mb-3 ml-1 flex items-center gap-2">
                      <Activity size={14} /> 매매 가이드라인
                    </h3>
                    <div className="grid grid-cols-2 gap-3">
                      <div className="bg-emerald-500/10 border border-emerald-500/20 p-4 rounded-lg flex flex-col justify-center items-center text-center">
                        <span className="text-xs font-bold text-emerald-400/80 mb-1">매수 진입가</span>
                        <span className="text-xl font-black text-emerald-400">{fmt(sp.entry)}</span>
                        <span className="text-[0.65rem] text-emerald-400/60 mt-1">이탈 시 관망</span>
                      </div>
                      <div className="bg-red-500/10 border border-red-500/20 p-4 rounded-lg flex flex-col justify-center items-center text-center">
                        <span className="text-xs font-bold text-red-400/80 mb-1">목표가</span>
                        <span className="text-xl font-black text-red-400">{fmt(sp.target)}</span>
                        <span className="text-[0.7rem] font-bold text-red-400 mt-1">+{calcReturn(sp.entry, sp.target)}% 기대</span>
                      </div>
                      <div className="bg-blue-500/10 border border-blue-500/20 p-4 rounded-lg flex flex-col justify-center items-center text-center">
                        <span className="text-xs font-bold text-blue-400/80 mb-1">손절가</span>
                        <span className="text-xl font-black text-blue-400">{fmt(sp.stop)}</span>
                        <span className="text-[0.7rem] font-bold text-blue-400 mt-1">{calcRisk(sp.entry, sp.stop)}% 위험</span>
                      </div>
                      <div className="bg-orange-500/10 border border-orange-500/20 p-4 rounded-lg flex flex-col justify-center items-center text-center">
                        <span className="text-xs font-bold text-orange-400/80 mb-1">현재가</span>
                        {sp.current_price != null ? (
                          <>
                            <span className="text-xl font-black text-orange-400">{fmt(sp.current_price)}</span>
                            <span className="text-[0.7rem] font-bold mt-1" style={{ color: priceColor }}>
                              {changePct > 0 ? "▲" : changePct < 0 ? "▼" : "─"}{Math.abs(changePct).toFixed(2)}%
                            </span>
                          </>
                        ) : (
                          <span className="text-sm font-bold text-orange-400 mt-1">{sp.horizon}</span>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })()}
          </section>
        </div>
      )}

      {toast && <Toast message={toast.message} type={toast.type} />}
    </div>
  );
}
