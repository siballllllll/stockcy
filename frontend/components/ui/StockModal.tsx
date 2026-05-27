"use client";
import { X, Zap } from "lucide-react";
import { StatusBox } from "./StatusBox";
import { Badge } from "./Badge";
import { Accordion } from "./Accordion";
import { MiniLineChart } from "./MiniLineChart";
import { useSSE } from "@/hooks/useSSE";
import useSWR from "swr";
import { api } from "@/lib/api";
import type { KrStock, StockReport, KrStockReport, ChartCandle } from "@/lib/types";

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

  const { data: krPrice } = useSWR<KrStock>(
    isKr ? `kr-modal-price-${stock.code}` : null,
    () => api.kr.stockPrice(stock.code) as Promise<KrStock>
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
        width:          "min(96vw, 600px)",
        maxHeight:      "90vh",
        overflowY:      "auto",
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
            <MiniLineChart data={chartPrices} width={530} height={56} />
          </div>
        )}

        {/* ── AI 분석 버튼 ── */}
        <button
          className="stockcy-btn stockcy-btn-primary"
          onClick={handleAnalyze}
          disabled={analysis.status === "running" || !priceReady}
          style={{ display: "flex", alignItems: "center", gap: "0.5rem", justifyContent: "center" }}
        >
          <Zap size={14} />
          {analysis.status === "running" ? "분석 중..." : "AI 분석 시작"}
        </button>

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
      </div>
    </>
  );
}
