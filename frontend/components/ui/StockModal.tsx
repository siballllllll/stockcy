"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { X, Zap, Search } from "lucide-react";
import { StatusBox } from "./StatusBox";
import { Badge } from "./Badge";
import { Accordion } from "./Accordion";
import { MiniLineChart } from "./MiniLineChart";
import { useSSE } from "@/hooks/useSSE";
import useSWR from "swr";
import { api } from "@/lib/api";
import { useIsMobile } from "@/lib/use-is-mobile";
import type { KrStock, StockReport, KrStockReport, ChartCandle } from "@/lib/types";

// 모달 우측 — 이 종목 관련 이슈 패널 (관련 종목 무료 + 시나리오/이슈섹터)
function IssuePanel({ code, market }: { code: string; market: string }) {
  const router = useRouter();
  const [activeIdx, setActiveIdx] = useState(0);
  const { data: issuesMap } = useSWR(`stk-issues-${code}`, () => {
    const fn = (api.ai as any).stockIssues;
    return typeof fn === "function" ? fn([code]) : Promise.resolve({});
  });
  const issues: any[] = (issuesMap as any)?.[code] || [];
  const active = issues.length ? issues[Math.min(activeIdx, issues.length - 1)] : null;
  const { data: relData } = useSWR(active ? `iss-stk-${active.keyword || active.title}` : null, () => {
    const fn = (api.ai as any).issueStocks;
    return typeof fn === "function" ? fn(active.keyword || active.title || "", code) : Promise.resolve({ stocks: [] });
  });
  const related: any[] = (relData as any)?.stocks || [];
  const isUs = (tk: string) => /[A-Za-z]/.test(tk || "");
  const roleLabel = (r: string) => r === "수혜" ? "수혜주(상승)" : r === "피해" ? "피해주(하락)" : r === "테마" ? "테마주" : r;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
      <div style={{ fontSize: "0.82rem", fontWeight: 800 }}>📣 이 종목 관련 이슈</div>
      {issues.length === 0 ? (
        <div style={{ fontSize: "0.74rem", color: "var(--color-muted)", lineHeight: 1.5 }}>
          시나리오에 등장한 이슈가 없습니다. (이슈가 누적되면 여기에 표시됩니다)
        </div>
      ) : (
        <>
          {issues.length > 1 && (
            <div style={{ display: "flex", gap: "4px", flexWrap: "wrap" }}>
              {issues.map((iss, i) => (
                <span key={i} onClick={() => setActiveIdx(i)} title={iss.title || iss.keyword}
                  style={{ fontSize: "0.64rem", padding: "1px 8px", borderRadius: "99px", cursor: "pointer", fontWeight: 700,
                    background: i === activeIdx ? "rgba(168,85,247,0.22)" : "var(--color-elevated)",
                    border: `1px solid ${i === activeIdx ? "rgba(168,85,247,0.6)" : "var(--color-border)"}`,
                    color: i === activeIdx ? "#c084fc" : "var(--color-muted)" }}>이슈 {i + 1}</span>
              ))}
            </div>
          )}
          <div style={{ fontSize: "0.8rem", fontWeight: 700, lineHeight: 1.45, color: "#c084fc" }}>📋 {active?.title || active?.keyword}</div>
          {(active?.role || active?.horizon || active?.captured_at) && (
            <div style={{ fontSize: "0.68rem", color: "var(--color-muted)", lineHeight: 1.45, display: "flex", flexWrap: "wrap", gap: "6px" }}>
              {active?.role && <span>이 종목 역할: <b style={{ color: "var(--color-text)" }}>{roleLabel(active.role)}</b></span>}
              {active?.horizon && <span style={{ padding: "0 6px", borderRadius: "4px", background: "rgba(168,85,247,0.1)", color: "#c084fc", fontWeight: 700 }}>{active.horizon}</span>}
              {active?.captured_at && <span>· {active.captured_at} 포착</span>}
            </div>
          )}

          <div style={{ fontSize: "0.66rem", color: "var(--color-muted)", marginTop: "2px" }}>이 이슈 관련 종목 <span style={{ color: "#34d399" }}>(무료)</span></div>
          {related.length > 0 ? (
            <div style={{ display: "flex", flexWrap: "wrap", gap: "5px" }}>
              {related.map((s) => {
                const rc = s.role === "수혜" ? "#34d399" : s.role === "피해" ? "#f87171" : "#c084fc";
                return (
                  <span key={s.ticker} onClick={() => router.push(`/search?q=${s.ticker}&market=${isUs(s.ticker) ? "US" : "KR"}`)}
                    title={s.role ? roleLabel(s.role) : undefined}
                    style={{ fontSize: "0.72rem", padding: "3px 8px", borderRadius: "6px", background: "var(--color-elevated)", border: `1px solid ${s.role ? rc + "55" : "var(--color-border)"}`, cursor: "pointer", color: "var(--color-text)", display: "inline-flex", alignItems: "center", gap: "4px" }}>
                    {s.name || s.ticker}
                    {s.role && <span style={{ fontSize: "0.58rem", color: rc, fontWeight: 700 }}>{s.role}</span>}
                  </span>
                );
              })}
            </div>
          ) : (
            <div style={{ fontSize: "0.7rem", color: "var(--color-muted)" }}>저장된 관련 종목 없음 — 아래 버튼으로 탐색</div>
          )}

          <div style={{ display: "flex", gap: "5px", marginTop: "2px" }}>
            <button onClick={() => router.push(`/scenarios?focus=${encodeURIComponent(active.keyword || active.title || "")}`)}
              style={{ flex: 1, padding: "8px 4px", fontSize: "0.72rem", fontWeight: 700, borderRadius: "7px", cursor: "pointer", background: "rgba(168,85,247,0.13)", border: "1px solid rgba(168,85,247,0.4)", color: "#c084fc" }}>🔍 시나리오</button>
            <button onClick={() => router.push(`/sectors?shadow=${encodeURIComponent(active.keyword || active.title || "")}`)}
              style={{ flex: 1, padding: "8px 4px", fontSize: "0.72rem", fontWeight: 700, borderRadius: "7px", cursor: "pointer", background: "rgba(96,165,250,0.13)", border: "1px solid rgba(96,165,250,0.4)", color: "#60a5fa" }}>🗺️ 이슈 섹터</button>
          </div>
        </>
      )}
    </div>
  );
}

// ── 인터페이스 ────────────────────────────────────────────────────────────────
export interface StockInfo {
  code:            string;   // KR: 6자리 코드, US: 티커
  name:            string;
  market:          "국내" | "미국";
  patternContext?: string;   // 패턴 스크리너에서 열 때 매칭 컨텍스트
}

// ── 마크다운 간이 렌더러 ───────────────────────────────────────────────────────
function Md({ text }: { text?: string }) {
  if (!text) return null;
  return (
    <div style={{ fontSize: "0.83rem", lineHeight: 1.8, color: "var(--color-text)" }}>
      {text.split("\n").map((line, i) => {
        const t = line.trim();
        if (!t) return <div key={i} style={{ height: "0.3rem" }} />;
        if (/^#{1,3} /.test(t))
          return (
            <p key={i} style={{ fontWeight: 700, color: "var(--color-text)", margin: "0.5rem 0 0.1rem" }}>
              {t.replace(/^#{1,3} /, "")}
            </p>
          );
        if (/^[-•*] /.test(t))
          return <p key={i} style={{ paddingLeft: "1em", margin: "0.1rem 0" }}>• {t.slice(2)}</p>;
        const parts = t.split(/(\*\*[^*]+\*\*)/g);
        return (
          <p key={i} style={{ margin: "0.1rem 0" }}>
            {parts.map((p, j) =>
              p.startsWith("**") && p.endsWith("**")
                ? <strong key={j}>{p.slice(2, -2)}</strong>
                : <span key={j}>{p}</span>
            )}
          </p>
        );
      })}
    </div>
  );
}

// ── 기대감 사이클 + 보유 판단 (뉴스·텔레그램 심리 × 펀더 교차) ──────────────────
function HoldVerdict({ r }: { r: any }) {
  const cyc: string | undefined = r?.expectation_cycle;
  const verdict: string | undefined = r?.hold_verdict;
  if (!cyc && !verdict) return null;
  const c = !cyc ? "var(--color-muted)"
    : cyc.includes("과열") ? "#f87171"
    : (cyc.includes("소멸") || cyc.includes("무관심")) ? "var(--color-muted)"
    : cyc.includes("확산") ? "#34d399"
    : cyc.includes("초기") ? "#60a5fa" : "var(--color-text)";
  return (
    <div style={{ background: "rgba(96,165,250,0.07)", border: "1px solid rgba(96,165,250,0.25)", borderRadius: "0.5rem", padding: "0.6rem 0.7rem", display: "flex", flexDirection: "column", gap: "0.35rem" }}>
      <div style={{ fontSize: "0.78rem", fontWeight: 800 }}>📣 기대감 사이클 + 보유 판단</div>
      {cyc && <div style={{ fontSize: "0.78rem" }}><span style={{ color: "var(--color-muted)" }}>기대감: </span><span style={{ fontWeight: 700, color: c }}>{cyc}</span></div>}
      {verdict && <div style={{ fontSize: "0.8rem", lineHeight: 1.5, color: "var(--color-text)" }}>{verdict}</div>}
    </div>
  );
}

// ── KR 리포트 결과 카드 ───────────────────────────────────────────────────────
function KrReport({ r }: { r: KrStockReport }) {
  const variantMap: Record<string, "success"|"info"|"warning"|"muted"|"danger"> = {
    "매우 강력": "success",
    "추천":      "info",
    "중간":      "warning",
    "비추천":    "danger",
    "매우 비":   "danger",
  };
  const v = Object.entries(variantMap).find(([k]) => (r.rating ?? "").includes(k))?.[1] ?? "muted";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      {r.error && <StatusBox type="danger">{r.error}</StatusBox>}

      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
        <span style={{ fontSize: "0.75rem", color: "var(--color-muted)" }}>단기 등급</span>
        <Badge variant={v}>{r.rating}</Badge>
        <Badge variant="muted">{r.short_term_view_pct}</Badge>
        {r.ticker_mismatch && <Badge variant="warning">종목명 불일치 확인</Badge>}
      </div>

      <HoldVerdict r={r} />

      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "0.5rem" }}>
        {[
          { label: "매수 타점", value: r.buy_target,  color: "var(--color-info)" },
          { label: "목표가",   value: r.sell_target, color: "var(--color-up)" },
          { label: "손절가",   value: r.stop_loss,   color: "var(--color-down)" },
        ].map(item => (
          <div key={item.label} style={{ background: "var(--color-elevated)", borderRadius: "0.375rem", padding: "0.5rem" }}>
            <div style={{ fontSize: "0.68rem", color: "var(--color-muted)" }}>{item.label}</div>
            <div style={{ fontSize: "0.78rem", fontWeight: 600, color: item.color, lineHeight: 1.4 }}>{item.value}</div>
          </div>
        ))}
      </div>

      {r.short_term_view_reason && (
        <div style={{ background: "var(--color-elevated)", borderRadius: "0.375rem", padding: "0.625rem" }}>
          <div style={{ fontSize: "0.7rem", color: "var(--color-muted)", marginBottom: "4px" }}>단기 전망 근거</div>
          <Md text={r.short_term_view_reason} />
        </div>
      )}

      {r.key_issues && (
        <Accordion title="핵심 이슈">
          <Md text={r.key_issues} />
        </Accordion>
      )}

      {r.analysis && (
        <Accordion title="종합 분석" defaultOpen>
          <Md text={r.analysis} />
        </Accordion>
      )}

      {r["세력분석"] && (
        <Accordion title="세력·수급 분석">
          <Md text={r["세력분석"]} />
        </Accordion>
      )}

      {r.long_term_analysis && (
        <Accordion title={`중장기 — ${r.long_term_rating ?? ""}`}>
          <div style={{ display: "flex", gap: "0.4rem", marginBottom: "0.5rem", flexWrap: "wrap" }}>
            {r.long_term_period && <Badge variant="muted">{r.long_term_period}</Badge>}
            {r.long_term_target && (
              <span style={{ color: "var(--color-up)", fontWeight: 600, fontSize: "0.82rem" }}>
                목표 {r.long_term_target}
              </span>
            )}
          </div>
          <Md text={r.long_term_analysis} />
        </Accordion>
      )}
    </div>
  );
}

// ── US 리포트 결과 카드 ───────────────────────────────────────────────────────
function UsReport({ r }: { r: StockReport }) {
  const variantMap: Record<string, "success"|"info"|"warning"|"muted"|"danger"> = {
    "매우 강력": "success",
    "추천":      "info",
    "중간":      "warning",
    "비추천":    "danger",
    "매우 비":   "danger",
  };
  const v = Object.entries(variantMap).find(([k]) => (r.rating ?? "").includes(k))?.[1] ?? "muted";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      {r.error && <StatusBox type="danger">{r.error}</StatusBox>}

      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
        <Badge variant={v}>{r.rating}</Badge>
        <Badge variant="muted">{r.short_term_view_pct}</Badge>
      </div>

      <HoldVerdict r={r} />

      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "0.5rem" }}>
        {[
          { label: "매수 타점", value: r.buy_target,  color: "var(--color-info)" },
          { label: "목표가",   value: r.sell_target, color: "var(--color-up)" },
          { label: "손절가",   value: r.stop_loss,   color: "var(--color-down)" },
        ].map(item => (
          <div key={item.label} style={{ background: "var(--color-elevated)", borderRadius: "0.375rem", padding: "0.5rem" }}>
            <div style={{ fontSize: "0.68rem", color: "var(--color-muted)" }}>{item.label}</div>
            <div style={{ fontSize: "0.78rem", fontWeight: 600, color: item.color, lineHeight: 1.4 }}>{item.value}</div>
          </div>
        ))}
      </div>

      {r.short_term_view_reason && (
        <div style={{ background: "var(--color-elevated)", borderRadius: "0.375rem", padding: "0.625rem" }}>
          <Md text={r.short_term_view_reason} />
        </div>
      )}

      {r.analysis && (
        <Accordion title="종합 분석" defaultOpen>
          <Md text={r.analysis} />
        </Accordion>
      )}

      {r.long_term_analysis && (
        <Accordion title={`중장기 — ${r.long_term_rating ?? ""}`}>
          <Md text={r.long_term_analysis} />
        </Accordion>
      )}
    </div>
  );
}

// ── 메인 모달 컴포넌트 ────────────────────────────────────────────────────────
export function StockModal({ stock, onClose }: { stock: StockInfo; onClose: () => void }) {
  const isKr = stock.market === "국내";
  const isMobile = useIsMobile();

  const { data: krPrice } = useSWR<KrStock>(
    isKr ? `kr-modal-price-${stock.code}` : null,
    () => api.kr.stockPrice(stock.code, true) as Promise<KrStock>   // 모달 — 펀더멘털 포함
  );

  const { data: usPrice } = useSWR<{ "심볼": string; "현재가($)": number; "등락률(%)": number } | null>(
    !isKr ? `us-modal-price-${stock.code}` : null,
    async () => {
      const arr = await api.us.stocks([stock.code]) as { "심볼": string; "현재가($)": number; "등락률(%)": number }[];
      return arr?.[0] ?? null;
    }
  );

  const { data: chartData } = useSWR<ChartCandle[]>(
    isKr ? `kr-chart-${stock.code}` : null,
    () => api.kr.dailyChart(stock.code, 40) as Promise<ChartCandle[]>
  );

  // [결정론 밸류에이션 점수] 실데이터로만 산출(추정 없음). 원시값을 투명하게 노출.
  const { data: valScore } = useSWR<any>(
    `valuation-${stock.code}`,
    () => api.ai.valuationScore(stock.code, isKr ? "KR" : "US")
  );

  const krAnalysis = useSSE<KrStockReport>("/api/ai/kr-stock-report", { method: "POST", globalId: `kr-report-${stock.code}`, globalTitle: `${stock.name} 종합 분석` });
  const usAnalysis = useSSE<StockReport>("/api/ai/stock-report",    { method: "POST", globalId: `us-report-${stock.code}`, globalTitle: `${stock.name} 종합 분석` });
  const analysis   = isKr ? krAnalysis : usAnalysis;

  const price     = isKr ? krPrice?.price            : usPrice?.["현재가($)"];
  const changePct = isKr ? krPrice?.change_pct        : usPrice?.["등락률(%)"];
  const up        = (changePct ?? 0) > 0;
  const down      = (changePct ?? 0) < 0;
  const color     = up ? "var(--color-up)" : down ? "var(--color-down)" : "var(--color-flat)";

  const chartPrices = (chartData ?? []).map(d => d.종가).filter(Boolean);
  const priceReady  = isKr ? !!krPrice : !!usPrice;

  const handleAnalyze = () => {
    if (isKr && krPrice) {
      krAnalysis.start({ code: stock.code, name: stock.name, price_data: krPrice, investor_data: [], pattern_context: stock.patternContext ?? null });
    } else if (!isKr && usPrice) {
      usAnalysis.start({ ticker: stock.code, current_price: usPrice["현재가($)"], change_pct: usPrice["등락률(%)"] });
    }
  };

  return (
    <>
      <div
        style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.65)", zIndex: 200 }}
        onClick={onClose}
      />
      <div style={{
        position:       "fixed",
        top:            "4vh",
        left:           "50%",
        transform:      "translateX(-50%)",
        width:          isMobile ? "96vw" : "min(98vw, 1200px)",
        maxHeight:      "92vh",
        overflowY:      isMobile ? "auto" : "hidden",
        background:     "var(--color-card)",
        borderRadius:   "0.75rem",
        border:         "1px solid var(--color-border)",
        zIndex:         201,
        padding:        "1.25rem",
        display:        "flex",
        flexDirection:  "column",
        gap:            "1rem",
      }}>
        {/* ── 헤더 ── */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
            <span style={{ fontWeight: 700, fontSize: "1rem" }}>{stock.name}</span>
            <span style={{ color: "var(--color-muted)", fontSize: "0.8rem" }}>({stock.code})</span>
            <Badge variant={isKr ? "info" : "success"}>{stock.market}</Badge>
          </div>
          <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--color-muted)", padding: "4px", lineHeight: 0 }}>
            <X size={18} />
          </button>
        </div>

        {/* ── 본문: 좌(분석) │ 우(이슈) 2단 ── */}
        <div style={{ display: "flex", flexDirection: isMobile ? "column" : "row", gap: "1rem", flex: 1, minHeight: 0, overflow: isMobile ? "visible" : "hidden" }}>
          <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: "1rem", overflowY: isMobile ? "visible" : "auto", paddingRight: isMobile ? 0 : "0.4rem" }}>

        {/* ── 현재가 ── */}
        {price !== undefined ? (
          <div style={{ display: "flex", alignItems: "baseline", gap: "0.5rem" }}>
            <span style={{ fontSize: "1.5rem", fontWeight: 700 }}>
              {isKr ? `₩${price.toLocaleString()}` : `$${price.toFixed(2)}`}
            </span>
            <span style={{ color, fontSize: "0.9rem", fontWeight: 600 }}>
              {up ? "▲" : down ? "▼" : "─"} {Math.abs(changePct ?? 0).toFixed(2)}%
            </span>
          </div>
        ) : (
          <div className="skeleton" style={{ height: "2rem", width: "160px", borderRadius: "4px" }} />
        )}

        {/* ── KR 지표 그리드 ── */}
        {isKr && krPrice && (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "0.4rem" }}>
            {[
              { label: "거래량",    value: krPrice.volume?.toLocaleString() ?? "-" },
              { label: "52주 최고", value: `₩${krPrice.w52_high?.toLocaleString()}` },
              { label: "52주 최저", value: `₩${krPrice.w52_low?.toLocaleString()}` },
              { label: "PER",       value: String(krPrice.per ?? "-") },
              { label: "PBR",       value: String(krPrice.pbr ?? "-") },
              { label: "시가총액",  value: krPrice.market_cap ?? "-" },
            ].map(item => (
              <div key={item.label} style={{ background: "var(--color-elevated)", borderRadius: "0.375rem", padding: "0.375rem 0.5rem" }}>
                <div style={{ fontSize: "0.66rem", color: "var(--color-muted)" }}>{item.label}</div>
                <div style={{ fontSize: "0.8rem", fontWeight: 600 }}>{item.value}</div>
              </div>
            ))}
          </div>
        )}

        {/* ── 미니 차트 ── */}
        {isKr && chartPrices.length > 4 && (
          <div style={{ background: "var(--color-elevated)", borderRadius: "0.375rem", padding: "0.5rem 0.75rem" }}>
            <p style={{ fontSize: "0.68rem", color: "var(--color-muted)", marginBottom: "0.25rem" }}>
              최근 {chartPrices.length}일 종가
            </p>
            <MiniLineChart data={chartPrices} width={710} height={64} />
          </div>
        )}

        {/* ── 밸류에이션 결정론 점수 (실데이터·투명 패널) ── */}
        {valScore && !valScore.error && (() => {
          const labels: Record<string, string> = { peg: "PEG", fcf_yield: "FCF Yield", ev_ebitda_band: "EV/EBITDA" };
          const s30 = valScore.score_30;
          const availMax = Number(valScore.available_max ?? 0);
          const conf = Number(valScore.confidence_pct ?? 0);
          const scoreColor = s30 == null ? "var(--color-muted)" : s30 >= 20 ? "var(--color-up)" : s30 >= 10 ? "var(--color-info)" : "var(--color-down)";
          // 헤드라인: 2항목+ → 30점 환산 / 1항목만 → 원점수(항목 부족) / 0항목 → 산정 불가
          const headline = s30 != null ? `${s30} / 30`
            : availMax > 0 ? `${valScore.score_raw}/${availMax} · 항목 부족`
            : "산정 불가";
          return (
            <div style={{ background: "var(--color-elevated)", borderRadius: "0.5rem", padding: "0.75rem", display: "flex", flexDirection: "column", gap: "0.5rem", border: "1px solid var(--color-border)" }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.5rem", flexWrap: "wrap" }}>
                <span style={{ fontSize: "0.78rem", fontWeight: 700 }}>🏛️ 밸류에이션 <span style={{ color: "var(--color-muted)", fontWeight: 400 }}>(결정론·실데이터)</span></span>
                <span style={{ display: "flex", alignItems: "baseline", gap: "0.4rem" }}>
                  <span style={{ fontSize: "1.05rem", fontWeight: 800, color: scoreColor }}>{headline}</span>
                  <span style={{ fontSize: "0.66rem", color: "var(--color-muted)" }}>{valScore.coverage} · 신뢰도 {conf}%</span>
                </span>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
                {(["peg", "fcf_yield", "ev_ebitda_band"] as const).map((k) => {
                  const it = valScore.items?.[k];
                  if (!it) return null;
                  const ok = it.available;
                  return (
                    <div key={k} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.5rem", fontSize: "0.72rem" }}>
                      <span style={{ color: "var(--color-muted)", minWidth: "72px" }}>{labels[k]}</span>
                      <span style={{ flex: 1, color: "var(--color-text)", lineHeight: 1.35 }}>{it.note}</span>
                      <span style={{ flexShrink: 0, fontWeight: 700, color: ok ? "var(--color-text)" : "var(--color-muted)", background: ok ? "rgba(255,255,255,0.06)" : "transparent", borderRadius: "4px", padding: "1px 6px" }}>
                        {ok ? `${it.score}/${it.max}` : "N/A"}
                      </span>
                    </div>
                  );
                })}
              </div>
              {valScore.phase?.phase && (() => {
                const ph = valScore.phase.phase as string;
                const c = ph.includes("취약") ? "#f87171" : ph.includes("쇠퇴") ? "#fb923c"
                  : ph.includes("바닥") ? "#fbbf24" : ph.includes("정상") ? "#34d399" : "var(--color-muted)";
                return (
                  <div style={{ fontSize: "0.72rem", display: "flex", alignItems: "center", gap: "0.4rem", flexWrap: "wrap", borderTop: "1px solid var(--color-border)", paddingTop: "0.4rem" }}>
                    <span style={{ color: "var(--color-muted)" }}>재무 국면</span>
                    <span style={{ fontWeight: 800, color: c }}>{ph}</span>
                    <span style={{ color: "var(--color-subtle)", fontSize: "0.66rem" }}>· {valScore.phase.reason}</span>
                  </div>
                );
              })()}
              {valScore.kr_note && (
                <div style={{ fontSize: "0.66rem", color: "var(--color-muted)", lineHeight: 1.4 }}>ℹ️ {valScore.kr_note}</div>
              )}
              {valScore.transient_note && (
                <div style={{ fontSize: "0.66rem", color: "var(--color-warning)", lineHeight: 1.4 }}>⚠️ {valScore.transient_note}</div>
              )}
              <div style={{ fontSize: "0.62rem", color: "var(--color-muted)" }}>※ AI 추정 아님. 실데이터 없는 항목은 N/A로 두고 신뢰도에 반영.</div>
            </div>
          );
        })()}

        {/* ── 액션 버튼 (AI 분석 + 종합검색 새 탭) ── */}
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <button
            className="stockcy-btn stockcy-btn-primary"
            onClick={handleAnalyze}
            disabled={analysis.status === "running" || !priceReady}
            style={{ flex: 1, display: "flex", alignItems: "center", gap: "0.5rem", justifyContent: "center" }}
          >
            <Zap size={14} />
            {analysis.status === "running" ? "분석 중..." : "AI 분석 시작"}
          </button>
          {/* 더 디테일한 정보는 종합검색 화면에서 — 새 탭으로 열어 모달 분석을 잃지 않게 함 */}
          <button
            className="stockcy-btn stockcy-btn-secondary"
            onClick={() => window.open(`/search?q=${encodeURIComponent(stock.code)}&market=${isKr ? "KR" : "US"}`, "_blank", "noopener,noreferrer")}
            title="종합검색 화면을 새 탭에서 엽니다"
            style={{ display: "flex", alignItems: "center", gap: "0.4rem", justifyContent: "center", whiteSpace: "nowrap" }}
          >
            <Search size={14} />
            종합검색
          </button>
        </div>

        {/* ── 분석 진행 상태 ── */}
        {analysis.status === "running" && (
          <StatusBox type="info">🔍 {analysis.message}</StatusBox>
        )}
        {analysis.status === "error" && (
          <StatusBox type="danger">{analysis.message}</StatusBox>
        )}

        {/* ── 분석 결과 ── */}
        {analysis.status === "done" && analysis.result && (
          isKr
            ? <KrReport r={analysis.result as KrStockReport} />
            : <UsReport r={analysis.result as StockReport} />
        )}
          </div>{/* /좌측 컬럼 */}

          {/* 우측 컬럼 — 이슈 패널 (가운데 구분선) */}
          <div style={{ width: isMobile ? "100%" : "420px", flexShrink: 0, borderLeft: isMobile ? "none" : "1px solid var(--color-border)", borderTop: isMobile ? "1px solid var(--color-border)" : "none", paddingLeft: isMobile ? 0 : "1.1rem", paddingTop: isMobile ? "0.85rem" : 0, overflowY: isMobile ? "visible" : "auto" }}>
            <IssuePanel code={stock.code} market={isKr ? "KR" : "US"} />
          </div>
        </div>{/* /2단 */}
      </div>
    </>
  );
}
