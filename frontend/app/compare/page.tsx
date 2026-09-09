"use client";
import { useState, useEffect, useMemo, useCallback } from "react";
import useSWR from "swr";
import { api, connectSSE } from "@/lib/api";
import { X, Search, Plus } from "lucide-react";

// ── 종목 비교 (v3.164.0) ─────────────────────────────────────────────────────
// 종목검색·차트와 독립된 화면. 사용자가 직접 고른 종목만 나란히 놓는다.
// 섹터가 달라도, 국내·미국이 섞여도 상관없다 — 차트는 절대가격이 아니라
// **기준일 대비 수익률(%)**로 정규화해서 겹치므로 원화·달러가 한 축에서 비교된다.
// (1,846,000원짜리와 7,610원짜리를 같은 축에 그리면 후자가 바닥 직선이 된다.)

const MAX = 5;
const COLORS = ["#6366f1", "#ef4444", "#10b981", "#f59e0b", "#a855f7"];
const PERIODS = [
  { key: "1mo", label: "1개월", days: 22 },
  { key: "3mo", label: "3개월", days: 66 },
  { key: "6mo", label: "6개월", days: 130 },
  { key: "1y", label: "1년", days: 250 },
];

interface Zone { key: string; label: string; win_rate: number | null; note: string }
interface Supply { date?: string; frgn?: number; orgn?: number; combined?: number; sum5?: number }
interface Issues { count?: number; recent?: Array<{ title: string; role: string; at: string }> }
interface Row {
  ticker: string; name: string; market: string;
  price: number | null; change_pct: number | null; rsi: number | null;
  mom_5: number | null; bb_pctb: number | null; ma20_dist: number | null;
  pos_52w: number | null; vol_ratio: number | null;
  zone: Zone | null; supply?: Supply; issues?: Issues;
  per?: any; pbr?: any; market_cap?: any;
  error?: string | null;
}
interface CompareResult { rows: Row[]; baseline_win_rate: number }
interface Verdict {
  issue_leader?: string; issue_reason?: string;
  pick?: string; pick_reason?: string; caution?: string;
  ranking?: Array<{ name: string; score: number; zone?: string; one_line: string }>;
  verdict?: string; error?: string;
}

const isKR = (t: string) => /^\d{6}$/.test(t.trim());
const fmtPrice = (r: Row) =>
  r.price === null ? "–" : r.market === "국내" ? r.price.toLocaleString() + "원" : "$" + r.price.toFixed(2);
const num = (v: number | null | undefined, suffix = "", digits = 1) =>
  v === null || v === undefined ? "–" : v.toFixed(digits) + suffix;
const fmtShares = (v?: number | null) => {
  if (v === null || v === undefined) return "–";
  const s = v >= 0 ? "+" : "";
  if (Math.abs(v) >= 10000) return s + (v / 10000).toFixed(1) + "만주";
  return s + v.toLocaleString() + "주";
};

export default function ComparePage() {
  const [tickers, setTickers] = useState<string[]>([]);
  const [input, setInput] = useState("");
  const [period, setPeriod] = useState(PERIODS[1]);
  const [showVal, setShowVal] = useState(false);
  const [charts, setCharts] = useState<Record<string, number[]>>({});
  const [chartLoading, setChartLoading] = useState(false);
  const [verdict, setVerdict] = useState<Verdict | null>(null);
  const [verdictLoading, setVerdictLoading] = useState(false);
  // 종목별 AI 종목분석 — 누른 종목만 실행(과금되므로 자동 실행하지 않는다)
  const [analysis, setAnalysis] = useState<Record<string, { status: string; msg?: string; result?: any }>>({});

  // 종목명 자동완성 — 전체 목록은 {코드: 이름} 맵이라 한 번 받아 클라이언트에서 거른다
  const { data: krAll } = useSWR<Record<string, string>>("kr-all", () => (api.kr as any).allStocks(),
    { revalidateOnFocus: false, dedupingInterval: 600000 });
  const { data: usAll } = useSWR<Record<string, string>>("us-all", () => (api.us as any).allStocks(),
    { revalidateOnFocus: false, dedupingInterval: 600000 });

  // 새로고침해도 담아둔 종목이 남도록 (이 화면은 여러 번 왔다 갔다 하며 쓴다)
  useEffect(() => {
    try {
      const saved = localStorage.getItem("stockcy_compare_tickers");
      if (saved) setTickers(JSON.parse(saved).slice(0, MAX));
    } catch {}
  }, []);
  useEffect(() => {
    try { localStorage.setItem("stockcy_compare_tickers", JSON.stringify(tickers)); } catch {}
  }, [tickers]);

  const suggestions = useMemo(() => {
    const q = input.trim().toLowerCase();
    if (!q) return [];
    const out: Array<{ code: string; name: string; market: string }> = [];
    const scan = (map: Record<string, string> | undefined, market: string) => {
      if (!map) return;
      for (const [code, name] of Object.entries(map)) {
        if (out.length >= 24) break;
        if (tickers.includes(code)) continue;
        const n = String(name || "").toLowerCase();
        if (code.toLowerCase().startsWith(q) || n.includes(q)) out.push({ code, name, market });
      }
    };
    scan(krAll, "KR");
    scan(usAll, "US");
    // 이름이 검색어로 시작하는 것을 앞으로 (부분일치보다 정확도 높음)
    return out.sort((a, b) => {
      const as = a.name.toLowerCase().startsWith(q) || a.code.toLowerCase().startsWith(q) ? 0 : 1;
      const bs = b.name.toLowerCase().startsWith(q) || b.code.toLowerCase().startsWith(q) ? 0 : 1;
      return as - bs;
    }).slice(0, 12);
  }, [input, krAll, usAll, tickers]);

  useEffect(() => { setVerdict(null); }, [tickers]);

  const askVerdict = async () => {
    if (tickers.length < 2 || verdictLoading) return;
    setVerdictLoading(true);
    setVerdict(null);
    try {
      const r = await (api.ai as any).compareVerdict(tickers);
      setVerdict(r as Verdict);
    } catch (e: any) {
      setVerdict({ error: String(e?.message || e) || "판단을 가져오지 못했습니다" });
    } finally {
      setVerdictLoading(false);
    }
  };

  // 종목분석 실행 — 검색 페이지와 같은 SSE 경로를 쓰고, 끝나면 이력에도 남긴다.
  // 이력(analysis_history)이 5종목뿐인 이유가 "종목검색에서 새로 분석할 때만 쌓여서"였으므로,
  // 여기서 돌린 것도 같은 방식으로 기록해 재료가 늘어나게 한다. 추가 과금은 분석 1회분뿐.
  const runAnalysis = async (r: Row) => {
    const tk = r.ticker;
    if (analysis[tk]?.status === "loading") return;
    if (!r.price || r.price <= 0) {
      setAnalysis((p) => ({ ...p, [tk]: { status: "error", msg: "시세를 불러오지 못했습니다" } }));
      return;
    }
    setAnalysis((p) => ({ ...p, [tk]: { status: "loading", msg: "분석 준비 중…" } }));
    const kr = r.market === "국내";
    try {
      await connectSSE<any>(
        kr ? "/api/ai/kr-stock-report" : "/api/ai/stock-report",
        (evt) => {
          if (evt.status === "running") {
            setAnalysis((p) => ({ ...p, [tk]: { status: "loading", msg: evt.message || "분석 중…" } }));
          } else if (evt.status === "done") {
            setAnalysis((p) => ({ ...p, [tk]: { status: "done", result: evt.result } }));
            // 이력 적재 — 실패해도 화면에 영향 없도록 완전 무시 (추가 AI 호출 없음)
            try {
              fetch("/backend/api/ai/analysis-history", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                  market: kr ? "KR" : "US", ticker: tk, name: r.name || tk,
                  current_price: r.price, analysis: evt.result,
                }),
              }).catch(() => {});
            } catch {}
          } else if (evt.status === "error") {
            setAnalysis((p) => ({ ...p, [tk]: { status: "error", msg: evt.message || "분석 실패" } }));
          }
        },
        {
          method: "POST",
          body: kr
            ? { code: tk, name: r.name || tk,
                price_data: { price: r.price, change_pct: r.change_pct ?? 0 }, investor_data: [] }
            : { ticker: tk, current_price: r.price, change_pct: r.change_pct ?? 0 },
        }
      );
    } catch (e: any) {
      setAnalysis((p) => ({ ...p, [tk]: { status: "error", msg: String(e?.message || e) } }));
    }
  };

  const key = tickers.length ? `cmp-${tickers.join(",")}-${showVal}` : null;
  const { data, isLoading } = useSWR<CompareResult>(
    key,
    () => (api.ai as any).compare(tickers, showVal),
    { revalidateOnFocus: false }
  );
  const rows = data?.rows ?? [];

  // ── 차트: 종목별 일봉을 받아 기준일 대비 %로 정규화 ────────────────────────
  const loadCharts = useCallback(async () => {
    if (!tickers.length) { setCharts({}); return; }
    setChartLoading(true);
    const out: Record<string, number[]> = {};
    await Promise.all(tickers.map(async (t) => {
      try {
        const raw: any = isKR(t)
          ? await (api.kr as any).dailyChart(t, period.days)
          : await (api.us as any).chart(t, period.key, "1d");
        const arr: any[] = Array.isArray(raw) ? raw : (raw?.candles ?? raw?.data ?? []);
        const closes = arr.map((c) => Number(c.close ?? c.Close ?? c.c)).filter((n) => !isNaN(n) && n > 0);
        if (closes.length >= 2) {
          const base = closes[0];
          out[t] = closes.map((c) => (c / base - 1) * 100);   // 기준일=0%
        }
      } catch {}
    }));
    setCharts(out);
    setChartLoading(false);
  }, [tickers, period]);

  useEffect(() => { loadCharts(); }, [loadCharts]);

  const add = (raw?: string) => {
    const t = (raw ?? input).trim().toUpperCase();
    if (!t || tickers.length >= MAX || tickers.includes(t)) return;
    setTickers([...tickers, t]);
    setInput("");
  };
  const remove = (t: string) => setTickers(tickers.filter((x) => x !== t));

  // 정규화 차트 SVG — 라이브러리 없이 직접 그린다(의존성 0, 이 용도엔 충분)
  const chart = useMemo(() => {
    const series = tickers.map((t, i) => ({ t, color: COLORS[i % COLORS.length], pts: charts[t] || [] }))
      .filter((s) => s.pts.length >= 2);
    if (!series.length) return null;
    const maxLen = Math.max(...series.map((s) => s.pts.length));
    const all = series.flatMap((s) => s.pts);
    let lo = Math.min(...all), hi = Math.max(...all);
    if (hi - lo < 1) { lo -= 1; hi += 1; }
    const pad = (hi - lo) * 0.08;
    lo -= pad; hi += pad;
    const W = 1000, H = 300;
    const x = (i: number, n: number) => (n <= 1 ? 0 : (i / (n - 1)) * W);
    const y = (v: number) => H - ((v - lo) / (hi - lo)) * H;
    return { series, maxLen, lo, hi, W, H, x, y };
  }, [tickers, charts]);

  return (
    <div style={{ padding: "1rem", maxWidth: "1300px", margin: "0 auto" }}>
      <h1 style={{ fontSize: "1.3rem", fontWeight: 800, marginBottom: "4px" }}>⚖ 종목 비교</h1>
      <div style={{ fontSize: "0.8rem", color: "var(--color-muted)", marginBottom: "1rem", lineHeight: 1.6 }}>
        고른 종목을 나란히 놓고 봅니다. 섹터가 달라도, 국내·미국이 섞여도 됩니다 —
        차트는 <b style={{ color: "var(--color-text)" }}>기준일 대비 수익률(%)</b>로 정규화해 겹치므로
        원화·달러를 한 축에서 비교할 수 있습니다.
      </div>

      {/* 종목 담기 */}
      <div style={{ background: "var(--color-card)", border: "1px solid var(--color-border)",
                    borderRadius: "10px", padding: "12px 14px", marginBottom: "12px" }}>
        <div style={{ display: "flex", gap: "8px", alignItems: "center", flexWrap: "wrap" }}>
          <div style={{ position: "relative", flex: "0 0 260px" }}>
            <Search size={14} style={{ position: "absolute", left: 9, top: 9, color: "var(--color-muted)" }} />
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") add(suggestions.length ? suggestions[0].code : undefined);
                if (e.key === "Escape") setInput("");
              }}
              placeholder="종목명·코드·티커 (삼성전자, 005930, NVDA)"
              disabled={tickers.length >= MAX}
              style={{ width: "100%", padding: "7px 8px 7px 28px", fontSize: "0.82rem",
                       background: "var(--color-elevated)", border: "1px solid var(--color-border)",
                       borderRadius: "6px", color: "var(--color-text)" }}
            />
            {suggestions.length > 0 && tickers.length < MAX && (
              <div style={{ position: "absolute", top: "100%", left: 0, right: 0, zIndex: 40,
                            marginTop: 4, maxHeight: 280, overflowY: "auto",
                            background: "var(--color-card)", border: "1px solid var(--color-border)",
                            borderRadius: 8, boxShadow: "0 12px 32px rgba(0,0,0,0.5)" }}>
                {suggestions.map((sg) => (
                  <div key={sg.market + sg.code} onClick={() => add(sg.code)}
                    style={{ padding: "7px 10px", fontSize: "0.8rem", cursor: "pointer",
                             display: "flex", justifyContent: "space-between", gap: 8,
                             borderBottom: "1px solid var(--color-border)" }}
                    onMouseDown={(e) => e.preventDefault()}>
                    <span><strong>{sg.name}</strong></span>
                    <span style={{ color: "var(--color-muted)", fontSize: "0.72rem", whiteSpace: "nowrap" }}>
                      {sg.code} · {sg.market}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
          <button onClick={() => add()} disabled={!input.trim() || tickers.length >= MAX}
            style={{ display: "flex", alignItems: "center", gap: "4px", padding: "7px 12px",
                     fontSize: "0.8rem", fontWeight: 700, borderRadius: "6px", cursor: "pointer",
                     background: "rgba(99,102,241,0.15)", border: "1px solid rgba(99,102,241,0.45)",
                     color: "#a5b4fc", opacity: (!input.trim() || tickers.length >= MAX) ? 0.45 : 1 }}>
            <Plus size={13} /> 추가
          </button>
          <span style={{ fontSize: "0.72rem", color: "var(--color-muted)" }}>
            {tickers.length}/{MAX}
          </span>
        </div>
        {tickers.length > 0 && (
          <div style={{ display: "flex", gap: "6px", flexWrap: "wrap", marginTop: "10px" }}>
            {tickers.map((t, i) => {
              const r = rows.find((x) => x.ticker === t);
              return (
                <span key={t} style={{
                  display: "inline-flex", alignItems: "center", gap: "6px",
                  fontSize: "0.78rem", fontWeight: 700, padding: "4px 8px", borderRadius: "6px",
                  background: "var(--color-elevated)",
                  border: `1px solid ${COLORS[i % COLORS.length]}`, color: "var(--color-text)",
                }}>
                  <span style={{ width: 8, height: 8, borderRadius: 99, background: COLORS[i % COLORS.length] }} />
                  {r?.name && r.name !== t ? `${r.name} (${t})` : t}
                  <X size={13} style={{ cursor: "pointer", color: "var(--color-muted)" }} onClick={() => remove(t)} />
                </span>
              );
            })}
          </div>
        )}
      </div>

      {tickers.length === 0 ? (
        <div style={{ textAlign: "center", padding: "4rem 1rem", color: "var(--color-muted)" }}>
          <div style={{ fontSize: "2.5rem", marginBottom: "0.75rem" }}>⚖</div>
          <div style={{ fontSize: "0.95rem", fontWeight: 600, color: "var(--color-text)" }}>
            비교할 종목을 담아보세요
          </div>
          <div style={{ fontSize: "0.82rem", marginTop: "6px" }}>
            예: 005930(삼성전자) · 000660(SK하이닉스) · NVDA · AMD
          </div>
        </div>
      ) : (
        <>
          {/* AI 비교 추천 (v3.165.0) — 버튼을 눌렀을 때만 LLM 1회 호출 */}
          <div style={{ background: "var(--color-card)", border: "1px solid var(--color-border)",
                        borderRadius: "10px", padding: "12px 14px", marginBottom: "12px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center",
                          gap: "8px", flexWrap: "wrap" }}>
              <div>
                <div style={{ fontSize: "0.85rem", fontWeight: 800 }}>AI 비교 추천</div>
                <div style={{ fontSize: "0.72rem", color: "var(--color-muted)", marginTop: "2px" }}>
                  지표·수급·이슈·실측 구간을 근거로 어느 쪽이 이슈를 타고 있고 매수 관점에서 나은지 판단합니다.
                </div>
              </div>
              <button onClick={askVerdict} disabled={tickers.length < 2 || verdictLoading}
                style={{ fontSize: "0.8rem", fontWeight: 700, padding: "7px 14px", borderRadius: "6px",
                         whiteSpace: "nowrap",
                         cursor: (tickers.length < 2 || verdictLoading) ? "not-allowed" : "pointer",
                         background: "rgba(168,85,247,0.15)", border: "1px solid rgba(168,85,247,0.5)",
                         color: "#c084fc", opacity: (tickers.length < 2 || verdictLoading) ? 0.5 : 1 }}>
                {verdictLoading ? "판단 중…" : tickers.length < 2 ? "종목 2개 이상 필요" : "🤖 비교 추천 받기"}
              </button>
            </div>

            {verdict && (
              <div style={{ marginTop: "12px", paddingTop: "12px", borderTop: "1px solid var(--color-border)" }}>
                {verdict.error ? (
                  <div style={{ fontSize: "0.82rem", color: "var(--color-danger)" }}>{verdict.error}</div>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                    {/* 결론 */}
                    <div style={{ background: verdict.pick ? "rgba(52,211,153,0.08)" : "rgba(255,255,255,0.04)",
                                  border: `1px solid ${verdict.pick ? "rgba(52,211,153,0.3)" : "var(--color-border)"}`,
                                  borderRadius: "8px", padding: "10px 12px" }}>
                      <div style={{ fontSize: "0.72rem", fontWeight: 800, color: "var(--color-muted)", marginBottom: "4px" }}>
                        매수 관점 추천
                      </div>
                      <div style={{ fontSize: "0.95rem", fontWeight: 800,
                                    color: verdict.pick ? "#6ee7b7" : "var(--color-muted)" }}>
                        {verdict.pick || "지금은 둘 다 진입 자리가 아닙니다"}
                      </div>
                      {verdict.pick_reason && (
                        <div style={{ fontSize: "0.83rem", color: "var(--color-text)", marginTop: "6px", lineHeight: 1.6 }}>
                          {verdict.pick_reason}
                        </div>
                      )}
                      {verdict.caution && (
                        <div style={{ fontSize: "0.78rem", color: "var(--color-warning)", marginTop: "6px", lineHeight: 1.55 }}>
                          ⚠️ {verdict.caution}
                        </div>
                      )}
                    </div>

                    {/* 이슈 리더 */}
                    {verdict.issue_leader && (
                      <div style={{ fontSize: "0.83rem", lineHeight: 1.6 }}>
                        <span style={{ fontSize: "0.72rem", fontWeight: 800, color: "var(--color-muted)", marginRight: "6px" }}>
                          이슈를 타는 쪽
                        </span>
                        <strong style={{ color: "#fbbf24" }}>{verdict.issue_leader}</strong>
                        {verdict.issue_reason && (
                          <div style={{ color: "var(--color-muted)", marginTop: "2px" }}>{verdict.issue_reason}</div>
                        )}
                      </div>
                    )}

                    {/* 랭킹 */}
                    {(verdict.ranking?.length ?? 0) > 0 && (
                      <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                        {verdict.ranking!.map((rk, i) => (
                          <div key={i} style={{ display: "flex", alignItems: "center", gap: "8px",
                                                fontSize: "0.8rem", padding: "4px 0",
                                                borderTop: i ? "1px solid var(--color-border)" : "none" }}>
                            <span style={{ fontWeight: 800, color: "var(--color-muted)", width: 18 }}>{i + 1}</span>
                            <strong style={{ minWidth: 90 }}>{rk.name}</strong>
                            <span style={{ fontWeight: 800, color: rk.score >= 70 ? "#6ee7b7" : rk.score >= 50 ? "var(--color-text)" : "#fca5a5" }}>
                              {rk.score}
                            </span>
                            {rk.zone && rk.zone !== "해당 없음" && (
                              <span style={{ fontSize: "0.68rem", padding: "1px 6px", borderRadius: 4,
                                             background: "rgba(255,255,255,0.05)", border: "1px solid var(--color-border)",
                                             color: "var(--color-muted)" }}>{rk.zone}</span>
                            )}
                            <span style={{ color: "var(--color-muted)", flex: 1 }}>{rk.one_line}</span>
                          </div>
                        ))}
                      </div>
                    )}

                    {verdict.verdict && (
                      <div style={{ fontSize: "0.8rem", color: "var(--color-muted)", lineHeight: 1.6,
                                    borderTop: "1px solid var(--color-border)", paddingTop: "8px" }}>
                        {verdict.verdict}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* 정규화 차트 */}
          <div style={{ background: "var(--color-card)", border: "1px solid var(--color-border)",
                        borderRadius: "10px", padding: "12px 14px", marginBottom: "12px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center",
                          marginBottom: "10px", flexWrap: "wrap", gap: "8px" }}>
              <div style={{ fontSize: "0.85rem", fontWeight: 800 }}>
                기준일 대비 수익률
                <span style={{ fontSize: "0.72rem", fontWeight: 500, color: "var(--color-muted)", marginLeft: "6px" }}>
                  ({period.label} 전 = 0%)
                </span>
              </div>
              <div style={{ display: "flex", gap: "4px" }}>
                {PERIODS.map((p) => (
                  <button key={p.key} onClick={() => setPeriod(p)}
                    style={{ fontSize: "0.72rem", fontWeight: 700, padding: "3px 10px", borderRadius: "5px",
                             cursor: "pointer",
                             background: period.key === p.key ? "rgba(99,102,241,0.2)" : "transparent",
                             border: `1px solid ${period.key === p.key ? "rgba(99,102,241,0.5)" : "var(--color-border)"}`,
                             color: period.key === p.key ? "#a5b4fc" : "var(--color-muted)" }}>
                    {p.label}
                  </button>
                ))}
              </div>
            </div>
            {chartLoading && !chart ? (
              <div style={{ height: 300, display: "flex", alignItems: "center", justifyContent: "center",
                            color: "var(--color-muted)", fontSize: "0.82rem" }}>차트 불러오는 중…</div>
            ) : !chart ? (
              <div style={{ height: 300, display: "flex", alignItems: "center", justifyContent: "center",
                            color: "var(--color-muted)", fontSize: "0.82rem" }}>차트 데이터를 받지 못했습니다</div>
            ) : (
              <div style={{ overflowX: "auto" }}>
                <svg viewBox={`0 0 ${chart.W} ${chart.H}`} preserveAspectRatio="none"
                     style={{ width: "100%", height: "300px", display: "block" }}>
                  {/* 0% 기준선 */}
                  {chart.lo < 0 && chart.hi > 0 && (
                    <line x1={0} x2={chart.W} y1={chart.y(0)} y2={chart.y(0)}
                          stroke="var(--color-border)" strokeWidth={1} strokeDasharray="4 4" />
                  )}
                  {chart.series.map((s) => (
                    <polyline key={s.t} fill="none" stroke={s.color} strokeWidth={2}
                      points={s.pts.map((v, i) => `${chart.x(i, s.pts.length)},${chart.y(v)}`).join(" ")} />
                  ))}
                </svg>
                <div style={{ display: "flex", justifyContent: "space-between",
                              fontSize: "0.7rem", color: "var(--color-muted)", marginTop: "2px" }}>
                  <span>{chart.lo.toFixed(1)}% ~ {chart.hi.toFixed(1)}%</span>
                  <span style={{ display: "flex", gap: "10px", flexWrap: "wrap" }}>
                    {chart.series.map((s) => {
                      const last = s.pts[s.pts.length - 1];
                      const r = rows.find((x) => x.ticker === s.t);
                      return (
                        <span key={s.t} style={{ color: s.color, fontWeight: 700 }}>
                          {r?.name && r.name !== s.t ? r.name : s.t} {last >= 0 ? "+" : ""}{last.toFixed(1)}%
                        </span>
                      );
                    })}
                  </span>
                </div>
              </div>
            )}
          </div>

          {/* 지표 표 */}
          <div style={{ background: "var(--color-card)", border: "1px solid var(--color-border)",
                        borderRadius: "10px", padding: "12px 14px", marginBottom: "12px", overflowX: "auto" }}>
            <div style={{ fontSize: "0.85rem", fontWeight: 800, marginBottom: "8px" }}>지표</div>
            {isLoading && !rows.length ? (
              <div style={{ color: "var(--color-muted)", fontSize: "0.82rem", padding: "1rem 0" }}>불러오는 중…</div>
            ) : (
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.8rem", minWidth: "760px" }}>
                <thead>
                  <tr style={{ color: "var(--color-muted)", textAlign: "right" }}>
                    <th style={{ textAlign: "left", padding: "5px 6px", fontWeight: 700 }}>종목</th>
                    <th style={{ padding: "5px 6px", fontWeight: 700 }}>현재가</th>
                    <th style={{ padding: "5px 6px", fontWeight: 700 }}>5일</th>
                    <th style={{ padding: "5px 6px", fontWeight: 700 }}>RSI</th>
                    <th style={{ padding: "5px 6px", fontWeight: 700 }}>%b</th>
                    <th style={{ padding: "5px 6px", fontWeight: 700 }}>MA20</th>
                    <th style={{ padding: "5px 6px", fontWeight: 700 }}>52주</th>
                    <th style={{ textAlign: "left", padding: "5px 6px", fontWeight: 700 }}>실측 구간</th>
                    <th style={{ textAlign: "left", padding: "5px 6px", fontWeight: 700 }}>AI 분석</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => {
                    const i = tickers.indexOf(r.ticker);
                    const z = r.zone;
                    const wr = z && z.win_rate !== null && z.win_rate !== undefined ? z.win_rate : null;
                    const base = data?.baseline_win_rate ?? 32.5;
                    const good = wr !== null && wr >= base + 10;
                    const bad = wr !== null && wr <= base + 3;
                    return (
                      <tr key={r.ticker} style={{ borderTop: "1px solid var(--color-border)", textAlign: "right" }}>
                        <td style={{ textAlign: "left", padding: "7px 6px", whiteSpace: "nowrap" }}>
                          <span style={{ display: "inline-block", width: 8, height: 8, borderRadius: 99,
                                         background: COLORS[i % COLORS.length], marginRight: 6 }} />
                          <strong>{r.name}</strong>
                          <span style={{ color: "var(--color-subtle)", marginLeft: 4, fontSize: "0.72rem" }}>
                            {r.market === "국내" ? "KR" : "US"}
                          </span>
                        </td>
                        <td style={{ padding: "7px 6px", whiteSpace: "nowrap" }}>
                          {fmtPrice(r)}
                          {r.change_pct !== null && (
                            <span style={{ marginLeft: 5, fontWeight: 700,
                                           color: r.change_pct >= 0 ? "var(--color-danger)" : "var(--color-primary)" }}>
                              {r.change_pct >= 0 ? "+" : ""}{r.change_pct.toFixed(2)}%
                            </span>
                          )}
                        </td>
                        <td style={{ padding: "7px 6px", fontWeight: 700,
                                     color: (r.mom_5 || 0) >= 10 ? "var(--color-warning)" : "var(--color-text)" }}>
                          {num(r.mom_5, "%")}
                        </td>
                        <td style={{ padding: "7px 6px" }}>{num(r.rsi, "", 0)}</td>
                        <td style={{ padding: "7px 6px" }}>{num(r.bb_pctb, "", 2)}</td>
                        <td style={{ padding: "7px 6px" }}>{num(r.ma20_dist, "%")}</td>
                        <td style={{ padding: "7px 6px" }}>{num(r.pos_52w, "%", 0)}</td>
                        <td style={{ textAlign: "left", padding: "7px 6px", whiteSpace: "nowrap" }}>
                          {r.error ? <span style={{ color: "var(--color-subtle)" }}>조회 실패</span>
                            : !z ? "–" : (
                            <span title={z.note} style={{
                              fontSize: "0.7rem", fontWeight: 700, padding: "2px 6px", borderRadius: "4px",
                              color: good ? "#6ee7b7" : bad ? "#fca5a5" : "var(--color-muted)",
                              background: good ? "rgba(52,211,153,0.12)" : bad ? "rgba(255,75,75,0.10)" : "rgba(255,255,255,0.04)",
                              border: `1px solid ${good ? "rgba(52,211,153,0.35)" : bad ? "rgba(255,75,75,0.3)" : "var(--color-border)"}`,
                            }}>
                              {z.label}{wr !== null ? ` ${wr}%` : z.key !== "neutral" ? " · 미검증" : ""}
                            </span>
                          )}
                        </td>
                        <td style={{ textAlign: "left", padding: "7px 6px", whiteSpace: "nowrap" }}>
                          {(() => {
                            const a = analysis[r.ticker];
                            if (a?.status === "loading")
                              return <span style={{ fontSize: "0.72rem", color: "var(--color-muted)" }}>{a.msg}</span>;
                            if (a?.status === "error")
                              return <span style={{ fontSize: "0.72rem", color: "var(--color-danger)" }} title={a.msg}>실패 · 재시도</span>;
                            if (a?.status === "done") {
                              const res = a.result || {};
                              return (
                                <span style={{ fontSize: "0.72rem" }}>
                                  <strong style={{ color: "#6ee7b7" }}>{res.rating || "완료"}</strong>
                                  {res.short_term_view_pct && (
                                    <span style={{ color: "var(--color-muted)" }}> · {res.short_term_view_pct}</span>
                                  )}
                                </span>
                              );
                            }
                            return (
                              <button onClick={() => runAnalysis(r)}
                                title="이 종목만 AI 종목분석을 실행합니다 (분석 1회분 과금 · 결과는 이력에도 쌓입니다)"
                                style={{ fontSize: "0.7rem", fontWeight: 700, padding: "2px 8px", borderRadius: "4px",
                                         cursor: "pointer", background: "rgba(168,85,247,0.12)",
                                         border: "1px solid rgba(168,85,247,0.4)", color: "#c084fc" }}>
                                🤖 분석
                              </button>
                            );
                          })()}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
            <div style={{ fontSize: "0.72rem", color: "var(--color-muted)", marginTop: "8px", lineHeight: 1.5 }}>
              실측 구간은 섀도우 리그 실현 거래에서 측정된 승률입니다 (랜덤 대조군 {data?.baseline_win_rate ?? 32.5}%).
              “미검증”은 그 시장에서 통계적 우위가 확인되지 않은 구간입니다.
              <br />
              🤖 분석 버튼은 그 종목만 AI 종목분석을 실행합니다 — 누를 때만 과금되고, 결과는 분석 이력에도 쌓여
              다음 비교의 근거가 됩니다.
            </div>
          </div>

          {/* 수급 · 이슈 */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: "12px" }}>
            <div style={{ background: "var(--color-card)", border: "1px solid var(--color-border)",
                          borderRadius: "10px", padding: "12px 14px" }}>
              <div style={{ fontSize: "0.85rem", fontWeight: 800, marginBottom: "8px" }}>
                수급 <span style={{ fontSize: "0.72rem", fontWeight: 500, color: "var(--color-muted)" }}>(외국인·기관 순매수, 국내만)</span>
              </div>
              {rows.filter((r) => r.market === "국내").length === 0 ? (
                <div style={{ fontSize: "0.8rem", color: "var(--color-muted)" }}>국내 종목이 없습니다.</div>
              ) : rows.filter((r) => r.market === "국내").map((r) => {
                const s = r.supply || {};
                const has = s.combined !== undefined && s.combined !== null;
                return (
                  <div key={r.ticker} style={{ fontSize: "0.8rem", padding: "5px 0",
                                               borderTop: "1px solid var(--color-border)", lineHeight: 1.6 }}>
                    <strong>{r.name}</strong>
                    {!has ? <span style={{ color: "var(--color-muted)" }}> — 스냅샷 없음</span> : (
                      <span style={{ marginLeft: 6, color: "var(--color-muted)" }}>
                        외인 <b style={{ color: (s.frgn || 0) >= 0 ? "var(--color-danger)" : "var(--color-primary)" }}>{fmtShares(s.frgn)}</b>
                        {" · "}기관 <b style={{ color: (s.orgn || 0) >= 0 ? "var(--color-danger)" : "var(--color-primary)" }}>{fmtShares(s.orgn)}</b>
                        {" · "}5일합 <b style={{ color: (s.sum5 || 0) >= 0 ? "var(--color-danger)" : "var(--color-primary)" }}>{fmtShares(s.sum5)}</b>
                        <span style={{ fontSize: "0.7rem" }}> ({s.date})</span>
                      </span>
                    )}
                  </div>
                );
              })}
            </div>

            <div style={{ background: "var(--color-card)", border: "1px solid var(--color-border)",
                          borderRadius: "10px", padding: "12px 14px" }}>
              <div style={{ fontSize: "0.85rem", fontWeight: 800, marginBottom: "8px" }}>
                이슈 연관 <span style={{ fontSize: "0.72rem", fontWeight: 500, color: "var(--color-muted)" }}>(시나리오 등장)</span>
              </div>
              {rows.map((r) => {
                const iss = r.issues || {};
                return (
                  <div key={r.ticker} style={{ fontSize: "0.8rem", padding: "5px 0",
                                               borderTop: "1px solid var(--color-border)", lineHeight: 1.6 }}>
                    <strong>{r.name}</strong>
                    <span style={{ marginLeft: 6, color: "var(--color-muted)" }}>{iss.count ?? 0}회 등장</span>
                    {(iss.recent || []).slice(0, 2).map((x, i) => (
                      <div key={i} style={{ fontSize: "0.74rem", color: "var(--color-subtle)", paddingLeft: 8 }}>
                        · {x.title} <span style={{ color: "var(--color-muted)" }}>({x.role} · {x.at})</span>
                      </div>
                    ))}
                  </div>
                );
              })}
            </div>
          </div>

          {/* 밸류에이션 — 네이버 스크래핑이라 느려서 눌렀을 때만 */}
          <div style={{ background: "var(--color-card)", border: "1px solid var(--color-border)",
                        borderRadius: "10px", padding: "12px 14px", marginTop: "12px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div style={{ fontSize: "0.85rem", fontWeight: 800 }}>밸류에이션</div>
              {!showVal && (
                <button onClick={() => setShowVal(true)}
                  style={{ fontSize: "0.75rem", fontWeight: 700, padding: "4px 10px", borderRadius: "5px",
                           cursor: "pointer", background: "rgba(255,255,255,0.05)",
                           border: "1px solid var(--color-border)", color: "var(--color-muted)" }}>
                  불러오기 (몇 초 걸립니다)
                </button>
              )}
            </div>
            {showVal && (
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.8rem", marginTop: "8px" }}>
                <thead>
                  <tr style={{ color: "var(--color-muted)", textAlign: "right" }}>
                    <th style={{ textAlign: "left", padding: "5px 6px", fontWeight: 700 }}>종목</th>
                    <th style={{ padding: "5px 6px", fontWeight: 700 }}>PER</th>
                    <th style={{ padding: "5px 6px", fontWeight: 700 }}>PBR</th>
                    <th style={{ padding: "5px 6px", fontWeight: 700 }}>시총</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.ticker} style={{ borderTop: "1px solid var(--color-border)", textAlign: "right" }}>
                      <td style={{ textAlign: "left", padding: "6px" }}><strong>{r.name}</strong></td>
                      <td style={{ padding: "6px" }}>{r.per ?? "–"}</td>
                      <td style={{ padding: "6px" }}>{r.pbr ?? "–"}</td>
                      <td style={{ padding: "6px" }}>{r.market_cap ?? "–"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
    </div>
  );
}
