"use client";
import { useState, useMemo, useEffect, useCallback, useRef } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import { Brain, TrendingUp, History, Clock, Loader2, Sparkles } from "lucide-react";
import { StatusBox } from "@/components/ui/StatusBox";
import { AiCostBadge } from "@/components/ui/AiCostBadge";

const BASE_URL = "/backend";

// ── AI 자기학습 현황 대시보드 ──────────────────────────────────────────────────
function AgentLearningDashboard() {
  const { data } = useSWR(
    "/backend/api/ai/agent-learning",
    (url: string) => fetch(url).then(r => r.json()),
    { refreshInterval: 60000 }
  );

  const sample = data?.sample ?? 0;
  const provisionalSample = data?.provisional_sample ?? 0;
  const realizedTrades = data?.realized_trades ?? 0;     // 실제 완료된 AI 거래내역 건수
  const realizedWinRate = data?.realized_win_rate;        // null이면 확정 거래 없음
  const rules = data?.rules ?? [];

  return (
    <div style={{ background: "var(--color-card)", border: "1px solid rgba(99,102,241,0.25)", borderRadius: "12px", padding: "1.25rem 1.5rem", marginBottom: "1rem" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.75rem" }}>
        <Brain size={18} color="#a5b4fc" />
        <span style={{ fontSize: "1rem", fontWeight: 800, color: "var(--color-text)" }}>AI 자기학습 현황</span>
        <span style={{ fontSize: "0.75rem", color: "var(--color-muted)", marginLeft: "auto" }}>
          {realizedTrades > 0 && (
            <span style={{ color: "#34d399", fontWeight: 700 }}>확정 거래 승률 {realizedWinRate ?? 0}% ({realizedTrades}건) · </span>
          )}
          학습 표본 {sample}건
          {sample > 0 && <span style={{ color: "var(--color-subtle)" }}> (보유중 {provisionalSample})</span>}
          {sample > 0 && ` · 잠정포함 ${data?.overall_win_rate ?? 0}%`}
        </span>
      </div>

      {sample < 5 ? (
        <div style={{ fontSize: "0.82rem", color: "var(--color-muted)", lineHeight: 1.6 }}>
          아직 학습 데이터가 부족합니다. AI 에이전트가 매수→매도를 완료할수록 "어떤 조건에서 승률이 높은지"를 스스로 학습하고,
          그 결과를 패턴 스크리너·시나리오 분석에도 공유합니다. (최소 5건 필요, 현재 {sample}건)
        </div>
      ) : (
        <div>
          <div style={{ fontSize: "0.78rem", color: "var(--color-muted)", marginBottom: "0.6rem" }}>
            📚 모의매매 결과로 학습한 조건별 승률 (승률 높은 순)
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: "0.6rem" }}>
            {rules.map((r: any, i: number) => {
              const good = r.win_rate >= 55;
              const bad = r.win_rate < 45;
              const c = good ? "#34d399" : bad ? "#f87171" : "#fbbf24";
              return (
                <div key={i} style={{ background: "var(--color-elevated)", border: `1px solid ${c}33`, borderLeft: `3px solid ${c}`, borderRadius: "8px", padding: "0.7rem 0.85rem" }}>
                  <div style={{ fontSize: "0.82rem", fontWeight: 700, color: "var(--color-text)", marginBottom: "4px" }}>{r.label}</div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                    <span style={{ fontSize: "1.1rem", fontWeight: 800, color: c }}>승률 {r.win_rate}%</span>
                    <span style={{ fontSize: "0.72rem", color: r.avg_return >= 0 ? "#34d399" : "#f87171" }}>{r.avg_return >= 0 ? "+" : ""}{r.avg_return}%</span>
                  </div>
                  <div style={{ fontSize: "0.68rem", color: "var(--color-muted)", marginTop: "2px" }}>{r.count}건 표본</div>
                </div>
              );
            })}
          </div>
          <div style={{ fontSize: "0.7rem", color: "var(--color-muted)", marginTop: "0.75rem", lineHeight: 1.5 }}>
            💡 이 학습 결과는 에이전트의 다음 매매 판단에 자동 반영되며, 패턴 스크리너 점수 보정에도 활용됩니다.
            {provisionalSample > 0 && (
              <> <br />⏳ <strong>보유중 {provisionalSample}건</strong>은 아직 매도 전이라 현재 평가손익을 반영한 <strong>잠정(미실현)</strong> 표본입니다. 매도 시 실현 수익률로 확정됩니다.</>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default function AgentDashboardPage() {
  const [activeTab, setActiveTab] = useState<"portfolio" | "trades" | "scanLogs">("portfolio");

  // ── 시간외 갭 스캔 상태 ────────────────────────────────────────────────────
  const [gapBulkMap, setGapBulkMap]     = useState<Record<string, any>>({});
  const [gapBulkStatus, setGapBulkStatus] = useState<"idle" | "loading" | "done">("idle");
  const [gapBulkMsg,   setGapBulkMsg]   = useState("");

  const { data: portfolio = [], isLoading: isLoadingPortfolio } = useSWR<any[]>("/api/portfolio/agent", () => api.portfolio.loadAgentPortfolio() as Promise<any[]>);
  const { data: tradesRes, isLoading: isLoadingTrades } = useSWR("/api/trades/agent", () => api.portfolio.loadAgentTrades() as Promise<{ data: any[]; message: string }>);

  // 에이전트 현금 잔액 + 현재 환율(평가용) + 보유종목 현재가(KR/US 분리)
  const { data: agentBalance } = useSWR("/api/portfolio/agent/balance", () => api.portfolio.loadAgentBalance(), { refreshInterval: 60000 });
  const { data: fxNow } = useSWR("agent-fx-now", () => api.us.exchangeRate(), { refreshInterval: 300000 });
  const usdkrw = Number((fxNow as any)?.rate ?? 1350);
  const { data: krPriceMap } = useSWR(
    portfolio.length ? ["agent-kr-prices", portfolio.map((p: any) => p.ticker).join(",")] : null,
    () => {
      const codes = portfolio.filter((p: any) => String(p.ticker).match(/^[0-9]+$/)).map((p: any) => String(p.ticker).padStart(6, "0"));
      return codes.length ? api.kr.stocksBulk(codes) as Promise<Record<string, any>> : Promise.resolve({});
    },
    { refreshInterval: 60000 }
  );
  const { data: usPriceMap } = useSWR(
    portfolio.length ? ["agent-us-prices", portfolio.map((p: any) => p.ticker).join(",")] : null,
    () => {
      const tk = portfolio.filter((p: any) => !String(p.ticker).match(/^[0-9]+$/)).map((p: any) => String(p.ticker).toUpperCase());
      return tk.length ? api.us.pricesBulk(tk) : Promise.resolve({});
    },
    { refreshInterval: 60000 }
  );
  const currentPriceOf = useCallback((p: any): number => {
    const t = String(p.ticker ?? "");
    if (t.match(/^[0-9]+$/)) return Number((krPriceMap as any)?.[t.padStart(6, "0")]?.price ?? (krPriceMap as any)?.[t]?.price ?? 0);
    return Number((usPriceMap as any)?.[t.toUpperCase()]?.price ?? 0);
  }, [krPriceMap, usPriceMap]);

  // 보유 평가금액(원화 환산) + 총자산
  const holdingsValueKRW = useMemo(() => portfolio.reduce((s: number, p: any) => {
    const isUs = !String(p.ticker).match(/^[0-9]+$/);
    const qty = Number(p.quantity || 0);
    const cur = currentPriceOf(p) || Number(p.buy_price || 0);   // 현재가 없으면 매수가로 대체
    return s + cur * qty * (isUs ? usdkrw : 1);
  }, 0), [portfolio, currentPriceOf, usdkrw]);
  const cashKRW = Number((agentBalance as any)?.cash ?? 0);
  const seedKRW = Number((agentBalance as any)?.seed ?? 10000000);
  const totalAssetKRW = cashKRW + holdingsValueKRW;
  
  // 실시간 에이전트 스캔 로그 로드 (10초 주기 갱신)
  const { data: scanLogs = [], isLoading: isLoadingScanLogs, mutate: mutateScanLogs } = useSWR(
    "/api/portfolio/agent/scan-logs",
    () => api.portfolio.loadAgentScanLogs(),
    { refreshInterval: 10000 }
  );

  // 수동 스캔 트리거 (30분 주기를 기다리지 않고 즉시 1회 점검)
  const [scanningNow, setScanningNow] = useState(false);
  const [scanNowMsg, setScanNowMsg] = useState("");

  // 고민 일지 필터: 날짜 선택 + 종목 검색
  const [scanLogDate, setScanLogDate] = useState<string>("");   // "" = 전체 날짜
  const [scanLogQuery, setScanLogQuery] = useState<string>(""); // 종목명/티커 검색어
  const runScanNow = async () => {
    setScanningNow(true);
    setScanNowMsg("AI 에이전트 스캔 실행 중... (최대 수십 초)");
    try {
      const res = await fetch("/backend/api/portfolio/agent/scan-now", { method: "POST" });
      const raw = await res.text();
      let j: any = null;
      try { j = JSON.parse(raw); } catch { /* 비-JSON 응답 */ }
      if (!res.ok || !j) {
        setScanNowMsg(`실패: 서버 응답 오류 (${res.status}). 백엔드 재시작이 필요할 수 있어요.`);
        return;
      }
      if (j.success) {
        const s = j.summary || {};
        setScanNowMsg(s.skipped ? `스캔 건너뜀: ${s.skipped}` : `완료 — 분석 ${s.scanned ?? 0}종목 (매수 ${s.buy ?? 0} / 매도 ${s.sell ?? 0} / 홀드 ${s.hold ?? 0})`);
      } else {
        setScanNowMsg(`실패: ${j.message ?? "오류"}`);
      }
      mutateScanLogs();
    } catch (e: any) {
      setScanNowMsg(`오류: ${e?.message ?? String(e)}`);
    } finally {
      setScanningNow(false);
    }
  };

  // 고민 일지에 존재하는 날짜 목록 (최신순)
  const scanLogDates = useMemo(() => {
    const set = new Set<string>();
    for (const log of scanLogs as any[]) {
      const d = String(log.scan_time ?? "").slice(0, 10);
      if (d.length === 10) set.add(d);
    }
    return Array.from(set).sort((a, b) => b.localeCompare(a));
  }, [scanLogs]);

  // 날짜 + 검색어로 필터링된 고민 일지
  const filteredScanLogs = useMemo(() => {
    const q = scanLogQuery.trim().toLowerCase();
    return (scanLogs as any[]).filter((log) => {
      if (scanLogDate && String(log.scan_time ?? "").slice(0, 10) !== scanLogDate) return false;
      if (q) {
        const hay = `${log.name ?? ""} ${log.ticker ?? ""}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [scanLogs, scanLogDate, scanLogQuery]);

  const trades = tradesRes?.data ?? [];

  const { data: usRates } = useSWR(
    "us-historical-rates-agent",
    () => {
      const dates = Array.from(new Set(trades.filter((t: any) => !String(t["티커"] ?? t.ticker ?? "").match(/^[0-9]+$/)).map((t: any) => String(t["매도시간"] ?? t.sell_date ?? "").slice(0, 10)).filter((d: string) => d.length === 10)));
      return dates.length > 0 ? api.us.exchangeRatesHistorical(dates as string[]) : {};
    }
  );

  // 미국 매도건이 있는데 아직 거래일 환율(usRates)이 로드 전이면, 1350 폴백으로 숫자가 '튀는' 것을
  // 방지하기 위해 집계를 보류한다(ratesReady=false). 거래일 환율은 종가 기준 파일캐시라 한번 잡히면 고정.
  const hasUsTrade = useMemo(() => trades.some((t: any) => !String(t["티커"] ?? t.ticker ?? "").match(/^[0-9]+$/)), [trades]);
  const ratesReady = !hasUsTrade || (usRates && Object.keys(usRates as any).length > 0);
  const totalProfit = useMemo(() => {
    return trades.reduce((sum: number, t: any) => {
      const ticker = String(t["티커"] ?? t.ticker ?? "");
      const isUs = !ticker.match(/^[0-9]+$/);
      const p = Number(t["수익금($)"] ?? t.profit ?? 0);
      if (isUs) {
        const d = String(t["매도시간"] ?? t.sell_date ?? "").slice(0, 10);
        // 거래일(매도일) 종가 환율로 고정. 해당 날짜가 캐시에 없을 때만 현재환율로 대체(하드코딩 1350 제거).
        const rate = (usRates as any)?.[d] || usdkrw;
        return sum + (p * rate);
      }
      return sum + p;
    }, 0);
  }, [trades, usRates, usdkrw]);

  // ── 갭 일괄 스캔: 서버 백그라운드 실행 + 폴링 (화면 나가도 계속 진행) ──────────
  const gapPollingRef = useRef(false);

  const gapTickers = useCallback(() => Array.from(
    new Set(portfolio.map((p: any) => String(p.ticker ?? "").toUpperCase().trim()))
  ).filter(Boolean), [portfolio]);

  // 진행 상황 폴링: 서버 작업이 끝날 때까지 상태 + 캐시 결과를 주기적으로 갱신
  const pollGapBulk = useCallback(async (tickers: string[]) => {
    if (gapPollingRef.current) return;   // 중복 폴링 방지
    gapPollingRef.current = true;
    setGapBulkStatus("loading");
    try {
      for (;;) {
        let job: any = null;
        try {
          const sres = await fetch(`${BASE_URL}/api/ai/overnight-gap-bulk/status`);
          job = await sres.json();
        } catch {}
        try {
          const res: any = await api.ai.overnightGapBulk(tickers);
          if (res?.results) setGapBulkMap(prev => ({ ...prev, ...res.results }));
        } catch {}
        if (job && job.running) {
          setGapBulkMsg(`📡 분석 중... (${job.done}/${job.total})${job.current ? " · 현재: " + job.current : ""}`);
          await new Promise(r => setTimeout(r, 4000));
        } else {
          setGapBulkStatus("done");
          setGapBulkMsg("🌙 시간외 갭 일괄 분석이 완료되었습니다!");
          break;
        }
      }
    } finally {
      gapPollingRef.current = false;
    }
  }, []);

  const handleGapBulkScan = useCallback(async () => {
    const allTickers = gapTickers();
    if (allTickers.length === 0) return;
    const names: Record<string, string> = {};
    portfolio.forEach((p: any) => {
      const t = String(p.ticker ?? "").toUpperCase().trim();
      if (t) names[t] = p.name || t;
    });
    setGapBulkStatus("loading");
    setGapBulkMsg("🌙 서버에서 시간외 갭 일괄 분석을 시작합니다... (화면을 나가도 계속 진행돼요)");
    try {
      await fetch(`${BASE_URL}/api/ai/overnight-gap-bulk/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "ngrok-skip-browser-warning": "69420" },
        body: JSON.stringify({ tickers: allTickers, names }),
      });
      pollGapBulk(allTickers);
    } catch (err: any) {
      setGapBulkStatus("done");
      setGapBulkMsg(`❌ 갭 스캔 시작 오류: ${err.message}`);
    }
  }, [portfolio, gapTickers, pollGapBulk]);

  // 마운트/포트폴리오 로드 시: 캐시 결과 로드 + 서버 작업 진행 중이면 폴링 재개
  useEffect(() => {
    if (portfolio.length === 0) return;
    const tickers = gapTickers();
    api.ai.overnightGapBulk(tickers).then((res: any) => {
      if (res?.results) setGapBulkMap(prev => ({ ...prev, ...res.results }));
    }).catch(() => {});
    fetch(`${BASE_URL}/api/ai/overnight-gap-bulk/status`).then(r => r.json()).then((job: any) => {
      if (job?.running) pollGapBulk(tickers);
    }).catch(() => {});
  }, [portfolio, gapTickers, pollGapBulk]);

  return (
    <main style={{ padding: "2rem", maxWidth: "1200px", margin: "0 auto", color: "var(--color-text)" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "1rem", marginBottom: "2rem", flexWrap: "wrap" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
          <Brain size={32} color="var(--color-primary)" />
          <h1 style={{ margin: 0, fontSize: "1.8rem" }}>AI 자율 매매 에이전트</h1>
        </div>
        {/* 🌙 시간외 갭 일괄 스캔 버튼 */}
        <button
          onClick={handleGapBulkScan}
          disabled={gapBulkStatus === "loading" || portfolio.length === 0}
          style={{
            display: "flex", alignItems: "center", gap: "6px",
            padding: "8px 16px", borderRadius: "8px", fontSize: "0.82rem",
            fontWeight: 700, cursor: portfolio.length === 0 ? "not-allowed" : "pointer",
            background: "rgba(245, 158, 11, 0.12)",
            border: "1px solid rgba(245, 158, 11, 0.35)",
            color: "#fbbf24", transition: "all 0.2s"
          }}
        >
          {gapBulkStatus === "loading"
            ? <><Loader2 size={14} className="animate-spin" /> 갭 분석 중...</>
            : <><Sparkles size={14} /> 🌙 시간외 갭 일괄 분석</>}
        </button>
        <AiCostBadge />
      </div>

      <div style={{ marginBottom: "2rem" }}>
        <StatusBox type="info">
          <strong>에이전트 스케줄러 동작 중</strong><br />
          백그라운드에서 주기적으로 즐겨찾기 종목을 스캔하고 매수/매도 시그널을 평가하여 가상 모의투자를 진행합니다. 시그널 발생 시 텔레그램으로 알림을 전송합니다.
        </StatusBox>
      </div>

      {/* 갭 스캔 진행 메시지 */}
      {gapBulkMsg && (
        <div style={{
          fontSize: "0.78rem", background: "rgba(0,0,0,0.3)", padding: "8px 14px",
          borderRadius: "7px", border: "1px solid var(--color-border)",
          color: "var(--color-subtle)", marginBottom: "1rem",
          display: "flex", alignItems: "center", justifyContent: "space-between"
        }}>
          <span>{gapBulkMsg}</span>
          <button style={{ background: "none", border: "none", color: "var(--color-muted)", cursor: "pointer", fontSize: "0.75rem" }}
            onClick={() => setGapBulkMsg("")}>
            ✕
          </button>
        </div>
      )}

      {/* 요약 카드 */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(250px, 1fr))", gap: "1rem", marginBottom: "2rem" }}>
        <div style={{ background: "var(--color-card)", border: "1px solid var(--color-border)", borderRadius: "12px", padding: "1.5rem" }}>
          <div style={{ color: "var(--color-muted)", fontSize: "0.9rem", marginBottom: "0.5rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <TrendingUp size={16} /> 총 모의투자 보유 종목
          </div>
          <div style={{ fontSize: "2rem", fontWeight: 700 }}>{portfolio.length}건</div>
        </div>
        <div style={{ background: "var(--color-card)", border: "1px solid var(--color-border)", borderRadius: "12px", padding: "1.5rem" }}>
          <div style={{ color: "var(--color-muted)", fontSize: "0.9rem", marginBottom: "0.5rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <History size={16} /> 총 모의투자 거래 횟수
          </div>
          <div style={{ fontSize: "2rem", fontWeight: 700 }}>{trades.length}건</div>
        </div>
        <div style={{ background: "var(--color-card)", border: "1px solid var(--color-border)", borderRadius: "12px", padding: "1.5rem" }}>
          <div style={{ color: "var(--color-muted)", fontSize: "0.9rem", marginBottom: "0.5rem" }}>누적 가상 손익 (거래일 환율 고정 환산)</div>
          {ratesReady ? (
            <div style={{ fontSize: "2rem", fontWeight: 700, color: totalProfit >= 0 ? "var(--color-danger)" : "var(--color-primary)" }}>
              {totalProfit >= 0 ? "+" : ""}₩{Math.round(totalProfit).toLocaleString()}
            </div>
          ) : (
            <div style={{ fontSize: "1.2rem", fontWeight: 700, color: "var(--color-muted)" }}>집계 중…</div>
          )}
        </div>
      </div>

      {/* 자기학습 현황 */}
      <AgentLearningDashboard />

      {/* 프리미엄 세그먼트형 버튼형 탭 네비게이터 */}
      <div style={{
        display: "flex",
        background: "rgba(26, 29, 36, 0.75)",
        border: "1px solid var(--color-border)",
        borderRadius: "14px",
        padding: "0.375rem",
        marginBottom: "1rem",
        backdropFilter: "blur(12px)",
        boxShadow: "0 8px 32px rgba(0, 0, 0, 0.4)",
        gap: "0.375rem"
      }}>
        <button
          onClick={() => setActiveTab("portfolio")}
          style={{
            flex: 1,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: "0.5rem",
            padding: "0.85rem 1rem",
            borderRadius: "10px",
            fontSize: "0.95rem",
            fontWeight: 700,
            cursor: "pointer",
            border: "none",
            outline: "none",
            transition: "all 0.25s cubic-bezier(0.4, 0, 0.2, 1)",
            background: activeTab === "portfolio" 
              ? "linear-gradient(135deg, #fbbf24 0%, #d97706 100%)" 
              : "transparent",
            color: activeTab === "portfolio" ? "#0e1117" : "var(--color-muted)",
            boxShadow: activeTab === "portfolio" ? "0 4px 14px rgba(245, 158, 11, 0.35)" : "none",
            transform: activeTab === "portfolio" ? "translateY(-1px)" : "none"
          }}
          className="agent-tab-btn"
        >
          <TrendingUp size={16} />
          <span>보유 종목</span>
          <span style={{
            fontSize: "0.75rem",
            padding: "2px 8px",
            borderRadius: "9999px",
            background: activeTab === "portfolio" ? "rgba(14, 17, 23, 0.15)" : "var(--color-elevated)",
            color: activeTab === "portfolio" ? "#0e1117" : "var(--color-muted)",
            fontWeight: 700,
            transition: "all 0.25s"
          }}>
            {portfolio.length}
          </span>
        </button>

        <button
          onClick={() => setActiveTab("trades")}
          style={{
            flex: 1,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: "0.5rem",
            padding: "0.85rem 1rem",
            borderRadius: "10px",
            fontSize: "0.95rem",
            fontWeight: 700,
            cursor: "pointer",
            border: "none",
            outline: "none",
            transition: "all 0.25s cubic-bezier(0.4, 0, 0.2, 1)",
            background: activeTab === "trades" 
              ? "linear-gradient(135deg, #fbbf24 0%, #d97706 100%)" 
              : "transparent",
            color: activeTab === "trades" ? "#0e1117" : "var(--color-muted)",
            boxShadow: activeTab === "trades" ? "0 4px 14px rgba(245, 158, 11, 0.35)" : "none",
            transform: activeTab === "trades" ? "translateY(-1px)" : "none"
          }}
          className="agent-tab-btn"
        >
          <History size={16} />
          <span>거래 내역 (복기)</span>
          <span style={{
            fontSize: "0.75rem",
            padding: "2px 8px",
            borderRadius: "9999px",
            background: activeTab === "trades" ? "rgba(14, 17, 23, 0.15)" : "var(--color-elevated)",
            color: activeTab === "trades" ? "#0e1117" : "var(--color-muted)",
            fontWeight: 700,
            transition: "all 0.25s"
          }}>
            {trades.length}
          </span>
        </button>

        <button
          onClick={() => setActiveTab("scanLogs")}
          style={{
            flex: 1,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: "0.5rem",
            padding: "0.85rem 1rem",
            borderRadius: "10px",
            fontSize: "0.95rem",
            fontWeight: 700,
            cursor: "pointer",
            border: "none",
            outline: "none",
            transition: "all 0.25s cubic-bezier(0.4, 0, 0.2, 1)",
            background: activeTab === "scanLogs" 
              ? "linear-gradient(135deg, #fbbf24 0%, #d97706 100%)" 
              : "transparent",
            color: activeTab === "scanLogs" ? "#0e1117" : "var(--color-muted)",
            boxShadow: activeTab === "scanLogs" ? "0 4px 14px rgba(245, 158, 11, 0.35)" : "none",
            transform: activeTab === "scanLogs" ? "translateY(-1px)" : "none"
          }}
          className="agent-tab-btn"
        >
          <Brain size={16} />
          <span>고민 일지 (실시간)</span>
          <span style={{
            fontSize: "0.75rem",
            padding: "2px 8px",
            borderRadius: "9999px",
            background: activeTab === "scanLogs" ? "rgba(14, 17, 23, 0.15)" : "var(--color-elevated)",
            color: activeTab === "scanLogs" ? "#0e1117" : "var(--color-muted)",
            fontWeight: 700,
            transition: "all 0.25s"
          }}>
            {scanLogs.length}
          </span>
        </button>
      </div>

      {/* 활성 탭 가이드 안내 메시지 */}
      <div style={{
        fontSize: "0.85rem",
        color: "var(--color-muted)",
        marginBottom: "1.5rem",
        padding: "0 0.5rem",
        display: "flex",
        alignItems: "center",
        gap: "0.5rem"
      }}>
        {activeTab === "portfolio" && (
          <>
            <TrendingUp size={14} color="#fbbf24" />
            <span>🤖 AI 에이전트가 매수 판단을 마치고 <strong>현재 가상 포트폴리오로 보유 중인 종목 목록</strong>입니다.</span>
          </>
        )}
        {activeTab === "trades" && (
          <>
            <History size={14} color="#fbbf24" />
            <span>💸 AI 에이전트가 보유 종목을 매도하여 <strong>실현 손익을 확정한 청산/복기 매매 역사기록</strong>입니다.</span>
          </>
        )}
        {activeTab === "scanLogs" && (
          <>
            <Clock size={14} color="#fbbf24" />
            <span>⏱️ AI 에이전트가 즐겨찾기 종목들을 <strong>실시간 모니터링하며 매수/매도 고민을 남긴 분석 로그</strong>입니다. (10초 자동 갱신)</span>
          </>
        )}
      </div>

      {activeTab === "portfolio" && (
        <div>
          {/* 잔액·평가·총자산 요약 */}
          <div style={{ display: "flex", flexWrap: "wrap", gap: "10px", marginBottom: "12px" }}>
            {[
              { label: "현금 잔액", value: cashKRW, sub: `시드 ${(seedKRW / 10000).toLocaleString()}만` },
              { label: "보유 평가금액", value: holdingsValueKRW, sub: `${portfolio.length}종목` },
              { label: "총 자산", value: totalAssetKRW, sub: (() => { const pl = totalAssetKRW - seedKRW; const r = seedKRW ? (pl / seedKRW * 100) : 0; return `${pl >= 0 ? "+" : ""}${Math.round(pl).toLocaleString()}원 (${r >= 0 ? "+" : ""}${r.toFixed(1)}%)`; })() },
            ].map((c, i) => (
              <div key={i} style={{ flex: "1 1 150px", background: "var(--color-card)", border: "1px solid var(--color-border)", borderRadius: "10px", padding: "10px 14px" }}>
                <div style={{ fontSize: "0.72rem", color: "var(--color-muted)", fontWeight: 700 }}>{c.label}</div>
                <div style={{ fontSize: "1.05rem", fontWeight: 800, color: "var(--color-text)", marginTop: "2px" }}>₩{Math.round(c.value).toLocaleString()}</div>
                <div style={{ fontSize: "0.68rem", color: i === 2 && totalAssetKRW >= seedKRW ? "#34d399" : i === 2 ? "#f87171" : "var(--color-subtle)", marginTop: "1px" }}>{c.sub}</div>
              </div>
            ))}
          </div>
          {isLoadingPortfolio ? <p>로딩 중...</p> : (
            portfolio.length === 0 ? <p style={{ color: "var(--color-muted)" }}>현재 에이전트가 보유 중인 종목이 없습니다.</p> : (
              <table className="stockcy-table">
                <thead>
                  <tr>
                    <th>종목</th>
                    <th style={{ textAlign: "right" }}>매수가</th>
                    <th style={{ textAlign: "right" }}>현재가</th>
                    <th style={{ textAlign: "right" }}>수익률</th>
                    <th style={{ textAlign: "right" }}>수량</th>
                    <th>매수 근거</th>
                  </tr>
                </thead>
                <tbody>
                  {portfolio.map((p: any, idx: number) => {
                    const isUs = !String(p.ticker).match(/^[0-9]+$/);
                    const sym = isUs ? "$" : "₩";
                    // 갭 배지 데이터
                    const gapKey = String(p.ticker ?? "").toUpperCase().trim();
                    const gapData = gapBulkMap?.[gapKey];
                    const gapUp   = gapData?.gap_direction?.includes("상승");
                    const gapDown = gapData?.gap_direction?.includes("하락");
                    const gapText = gapData?.gap_strength && gapData?.gap_strength !== "보합권" ? gapData.gap_strength : null;
                    return (
                      <tr key={idx}>
                        <td>
                          <div style={{ display: "flex", flexDirection: "column", gap: "3px" }}>
                            <div style={{ display: "flex", alignItems: "center", gap: "5px", flexWrap: "wrap" }}>
                              <strong>{p.name}</strong>
                              <span style={{ color: "var(--color-muted)", fontSize: "0.8rem" }}>{p.ticker}</span>
                              {/* 🌙 시간외 갭 배지 */}
                              {gapData && gapText && (
                                <span
                                  style={{
                                    fontSize: "0.65rem", padding: "1px 5px", borderRadius: "4px",
                                    background: gapUp ? "rgba(16,185,129,0.15)" : gapDown ? "rgba(239,68,68,0.15)" : "rgba(255,255,255,0.06)",
                                    color: gapUp ? "#34d399" : gapDown ? "#f87171" : "#a1a1aa",
                                    border: `1px solid ${gapUp ? "rgba(16,185,129,0.3)" : gapDown ? "rgba(239,68,68,0.3)" : "rgba(255,255,255,0.12)"}`,
                                    fontWeight: 800, cursor: "help",
                                    display: "inline-flex", alignItems: "center", gap: "2px"
                                  }}
                                  title={`🌙 시간외 주요 변수:\n${gapData.overnight_issue_summary}\n\n💡 대응 가이드:\n${gapData.trading_action_guide}\n\n📈 매수 적정가: ${gapData.buy_target ?? "-"}\n🛑 손절가: ${gapData.stop_loss ?? "-"}`}
                                >
                                  {gapUp ? "🟢 갭상" : gapDown ? "🔴 갭하" : "⚪ 보합"} {gapText}
                                </span>
                              )}
                            </div>
                          </div>
                        </td>
                        <td style={{ textAlign: "right" }}>{sym}{Number(p.buy_price ?? 0).toLocaleString()}</td>
                        <td style={{ textAlign: "right" }}>{(() => { const cur = currentPriceOf(p); return cur > 0 ? `${sym}${cur.toLocaleString()}` : <span style={{ color: "var(--color-subtle)" }}>—</span>; })()}</td>
                        <td style={{ textAlign: "right", fontWeight: 700 }}>{(() => {
                          const cur = currentPriceOf(p); const bp = Number(p.buy_price ?? 0);
                          if (!(cur > 0) || !(bp > 0)) return <span style={{ color: "var(--color-subtle)" }}>—</span>;
                          const r = (cur - bp) / bp * 100;
                          return <span style={{ color: r >= 0 ? "var(--color-danger)" : "var(--color-primary)" }}>{r >= 0 ? "+" : ""}{r.toFixed(2)}%</span>;
                        })()}</td>
                        <td style={{ textAlign: "right" }}>{p.quantity}</td>
                        <td style={{ maxWidth: "260px" }}>
                          <div style={{ fontSize: "0.82rem", color: "var(--color-text)", whiteSpace: "pre-wrap", lineHeight: 1.45 }}>
                            {String(p.buy_reason ?? "").trim() || <span style={{ color: "var(--color-subtle)" }}>{p.rating ?? "—"}</span>}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )
          )}
        </div>
      )}

      {activeTab === "trades" && (
        <div>
          {isLoadingTrades ? <p>로딩 중...</p> : (
            trades.length === 0 ? <p style={{ color: "var(--color-muted)" }}>아직 에이전트의 매매 내역이 없습니다.</p> : (
              <table className="stockcy-table">
                <thead>
                  <tr>
                    <th>종목</th>
                    <th style={{ textAlign: "right" }}>매수가</th>
                    <th style={{ textAlign: "right" }}>매도가</th>
                    <th style={{ textAlign: "right" }}>수익률</th>
                    <th>매도 사유 (학습점)</th>
                    <th>매도일</th>
                  </tr>
                </thead>
                <tbody>
                  {trades.map((t: any, idx: number) => {
                    const isUs = !String(t["티커"] ?? t.ticker).match(/^[0-9]+$/);
                    const sym = isUs ? "$" : "₩";
                    const pct = Number(t["수익률(%)"] ?? t.profit_pct ?? 0);
                    const color = pct >= 0 ? "var(--color-danger)" : "var(--color-primary)";
                    return (
                      <tr key={idx}>
                        <td><strong>{t["종목명"] ?? t.name}</strong></td>
                        <td style={{ textAlign: "right" }}>{sym}{Number(t["매수가($)"] ?? t.buy_price ?? 0).toLocaleString()}</td>
                        <td style={{ textAlign: "right" }}>{sym}{Number(t["매도가($)"] ?? t.sell_price ?? 0).toLocaleString()}</td>
                        <td style={{ textAlign: "right", color, fontWeight: "bold" }}>{pct >= 0 ? "+" : ""}{pct.toFixed(2)}%</td>
                        <td><span style={{ fontSize: "0.85rem" }}>{t["학습/복기"] ?? t.learning_point ?? ""}</span></td>
                        <td>{String(t["매도시간"] ?? t.sell_date).slice(0, 10)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )
          )}
        </div>
      )}

      {activeTab === "scanLogs" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
          {/* 수동 스캔 트리거 */}
          <div style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap", paddingBottom: "4px" }}>
            <button
              onClick={runScanNow}
              disabled={scanningNow}
              className="stockcy-btn stockcy-btn-primary"
              style={{ display: "flex", alignItems: "center", gap: "6px", padding: "6px 14px", fontSize: "0.85rem", fontWeight: 700 }}
            >
              {scanningNow ? <Loader2 className="animate-spin" size={14} /> : <Brain size={14} />}
              {scanningNow ? "스캔 중..." : "지금 스캔 실행"}
            </button>
            <AiCostBadge />
            <span style={{ fontSize: "0.78rem", color: "var(--color-muted)" }}>
              {scanNowMsg || "30분 주기를 기다리지 않고 즉시 1회 점검 (휴장에도 즐겨찾기·보유종목 분석)"}
            </span>
          </div>

          {/* 날짜 선택 + 종목 검색 필터 */}
          {scanLogs.length > 0 && (
            <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
              <select
                value={scanLogDate}
                onChange={(e) => setScanLogDate(e.target.value)}
                style={{
                  padding: "6px 10px", borderRadius: "8px", fontSize: "0.82rem",
                  background: "var(--color-surface)", color: "var(--color-text)",
                  border: "1px solid var(--color-border)", cursor: "pointer",
                }}
              >
                <option value="">전체 날짜 ({scanLogs.length})</option>
                {scanLogDates.map((d) => (
                  <option key={d} value={d}>{d}</option>
                ))}
              </select>
              <input
                type="text"
                value={scanLogQuery}
                onChange={(e) => setScanLogQuery(e.target.value)}
                placeholder="🔍 종목명 또는 티커 검색"
                style={{
                  flex: 1, minWidth: "180px", padding: "6px 12px", borderRadius: "8px",
                  fontSize: "0.82rem", background: "var(--color-surface)",
                  color: "var(--color-text)", border: "1px solid var(--color-border)",
                }}
              />
              {(scanLogDate || scanLogQuery) && (
                <button
                  onClick={() => { setScanLogDate(""); setScanLogQuery(""); }}
                  style={{
                    padding: "6px 12px", borderRadius: "8px", fontSize: "0.78rem",
                    background: "transparent", color: "var(--color-muted)",
                    border: "1px solid var(--color-border)", cursor: "pointer", fontWeight: 600,
                  }}
                >
                  필터 초기화
                </button>
              )}
              <span style={{ fontSize: "0.75rem", color: "var(--color-muted)" }}>
                {filteredScanLogs.length}건 표시
              </span>
            </div>
          )}

          {isLoadingScanLogs ? (
            <div style={{ display: "flex", alignItems: "center", gap: "8px", color: "var(--color-muted)", padding: "2rem 0" }}>
              <Loader2 className="animate-spin" size={18} />
              <span>스캔 고민 일지 로드 중...</span>
            </div>
          ) : scanLogs.length === 0 ? (
            <p style={{ color: "var(--color-muted)", padding: "1rem 0" }}>
              아직 에이전트가 기록한 스캔 이력이 없습니다.<br />
              감시를 시작하려면 <strong>'즐겨찾기' 탭에 종목을 추가</strong>해 주세요! 즐겨찾기 종목 목록을 에이전트가 실시간 우주(Universe)로 활용해 판단을 내립니다.
            </p>
          ) : filteredScanLogs.length === 0 ? (
            <p style={{ color: "var(--color-muted)", padding: "1rem 0" }}>
              조건에 맞는 고민 일지가 없습니다. 날짜나 검색어를 바꿔보세요.
            </p>
          ) : (
            <div style={{
              display: "flex", flexDirection: "column", gap: "10px",
              maxHeight: "560px", overflowY: "auto", paddingRight: "6px",
            }}>
              {filteredScanLogs.map((log: any, idx: number) => {
                const isBuy = log.action === "BUY";
                const isSell = log.action === "SELL";
                const badgeBg = isBuy ? "rgba(16, 185, 129, 0.15)" : isSell ? "rgba(239, 68, 68, 0.15)" : "rgba(255,255,255,0.06)";
                const badgeColor = isBuy ? "#34d399" : isSell ? "#f87171" : "var(--color-muted)";
                const badgeBorder = isBuy ? "1px solid rgba(16, 185, 129, 0.3)" : isSell ? "1px solid rgba(239, 68, 68, 0.3)" : "1px solid rgba(255,255,255,0.1)";
                
                return (
                  <div key={idx} style={{
                    background: "var(--color-surface)",
                    border: "1px solid var(--color-border)",
                    borderRadius: "10px",
                    padding: "14px",
                    display: "flex",
                    flexDirection: "column",
                    gap: "8px"
                  }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "8px" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                        <span style={{ fontWeight: 700, fontSize: "0.95rem" }}>{log.name}</span>
                        <span style={{ color: "var(--color-muted)", fontSize: "0.78rem" }}>({log.ticker})</span>
                        <span style={{ fontSize: "0.75rem", padding: "1px 6px", borderRadius: "4px", background: badgeBg, color: badgeColor, border: badgeBorder, fontWeight: 700 }}>
                          {log.action} ({log.confidence}%)
                        </span>
                      </div>
                      <div style={{ color: "var(--color-muted)", fontSize: "0.75rem", display: "flex", alignItems: "center", gap: "4px" }}>
                        <Clock size={12} /> {log.scan_time}
                      </div>
                    </div>
                    
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px", fontSize: "0.8rem", color: "var(--color-muted)" }}>
                      <div>현재가: <span style={{ color: "var(--color-text)", fontWeight: 600 }}>{String(log.ticker).match(/^[0-9]+$/) ? "₩" : "$"}{log.price.toLocaleString()}</span></div>
                      <div>에이전트 보유상태: <span style={{ color: log.position === "HOLDING" ? "#fbbf24" : "var(--color-text)", fontWeight: 600 }}>{log.position}</span></div>
                    </div>
                    
                    <div style={{ fontSize: "0.82rem", color: "var(--color-subtle)", borderTop: "1px dashed rgba(255,255,255,0.06)", paddingTop: "6px", lineHeight: 1.4 }}>
                      💡 <strong>에이전트 생각:</strong> {log.reason}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </main>
  );
}
