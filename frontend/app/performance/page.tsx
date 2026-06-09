"use client";
import { useEffect, useState } from "react";
import useSWR from "swr";
import { MarkdownLite } from "@/components/ui/MarkdownLite";

const B = "/backend";
const fetcher = (url: string) => fetch(url).then((r) => (r.ok ? r.json() : null));

const wrColor = (v: number | null | undefined) =>
  v == null ? "var(--color-muted)" : v >= 60 ? "#34d399" : v >= 45 ? "#fbbf24" : "#f87171";
const pct = (v: number | null | undefined) => (v == null ? "—" : `${v}%`);
const ret = (v: number | null | undefined) => (v == null ? "—" : `${v >= 0 ? "+" : ""}${v}%`);

// ── 엔진별 성과 + AI추천 적중률 ─────────────────────────────────────────────────
function EngineScoreboard() {
  const { data: rec } = useSWR(`${B}/api/ai/recommendation-stats`, fetcher);
  const { data: scn } = useSWR(`${B}/api/ai/scenario-tracking/stats`, fetcher);
  const { data: scr } = useSWR(`${B}/api/ai/screener-backtest/stats`, fetcher);

  // 엔진별 d7 헤드라인 산출
  const recH = (rec?.horizons ?? []).find((h: any) => h.horizon === "7일");
  // 시나리오: by_scenario 가중 평균
  const bs: any[] = scn?.by_scenario ?? [];
  const scnN = bs.reduce((a, b) => a + (b.count || 0), 0);
  const scnWin = scnN > 0 ? Math.round(bs.reduce((a, b) => a + (b.win_rate_d7 || 0) * (b.count || 0), 0) / scnN * 10) / 10 : null;
  const scnAvg = scnN > 0 ? Math.round(bs.reduce((a, b) => a + (b.avg_d7_return || 0) * (b.count || 0), 0) / scnN * 100) / 100 : null;
  const scrO = scr?.overall ?? {};

  const engines = [
    { name: "🤖 AI추천", n: rec?.measured ?? 0, win: recH?.win_rate ?? null, avg: recH?.avg_return ?? null, note: "단타발굴·종목분석 추천의 7일 후 성과" },
    { name: "📈 시나리오", n: scnN, win: scnWin, avg: scnAvg, note: "시나리오 등장 종목 7일 후 (방향 적중)" },
    { name: "🔍 복합스크리너", n: scr?.total_picks_backtested ?? 0, win: scrO.win_rate_d7 ?? null, avg: scrO.avg_d7_return ?? null, note: "패턴 스크리너 픽 7일 후 백테스트" },
  ];

  return (
    <div className="stockcy-card" style={{ padding: "1rem 1.2rem" }}>
      <div style={{ fontWeight: 800, fontSize: "1rem", marginBottom: "4px" }}>📊 엔진별 성과 (7일 기준)</div>
      <div style={{ fontSize: "0.74rem", color: "var(--color-muted)", marginBottom: "12px" }}>각 AI 엔진이 추천한 종목이 실제로 며칠 뒤 맞았나 — 표본이 쌓일수록 정확해집니다.</div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "10px" }}>
        {engines.map((e, i) => (
          <div key={i} style={{ background: "rgba(255,255,255,0.03)", border: "1px solid var(--color-border)", borderRadius: "10px", padding: "12px 14px" }}>
            <div style={{ fontWeight: 800, fontSize: "0.9rem", marginBottom: "6px" }}>{e.name}</div>
            <div style={{ display: "flex", alignItems: "baseline", gap: "8px" }}>
              <span style={{ fontSize: "1.5rem", fontWeight: 900, color: wrColor(e.win) }}>{pct(e.win)}</span>
              <span style={{ fontSize: "0.78rem", color: "var(--color-muted)" }}>승률</span>
            </div>
            <div style={{ fontSize: "0.8rem", color: "var(--color-subtle)" }}>평균 {ret(e.avg)} · 표본 {e.n}건</div>
            <div style={{ fontSize: "0.68rem", color: "var(--color-muted)", marginTop: "4px", lineHeight: 1.4 }}>{e.note}</div>
          </div>
        ))}
      </div>
      {/* AI추천 1/3/7일 분해 */}
      {(rec?.horizons ?? []).length > 0 && (
        <div style={{ marginTop: "12px", borderTop: "1px solid var(--color-border)", paddingTop: "10px" }}>
          <div style={{ fontSize: "0.78rem", fontWeight: 700, color: "var(--color-muted)", marginBottom: "6px" }}>🤖 AI추천 기간별 적중률</div>
          <div style={{ display: "flex", gap: "10px", flexWrap: "wrap" }}>
            {rec.horizons.map((h: any, i: number) => (
              <div key={i} style={{ background: "rgba(0,0,0,0.15)", borderRadius: "6px", padding: "6px 12px", fontSize: "0.8rem" }}>
                {h.horizon} <b style={{ color: wrColor(h.win_rate) }}>{pct(h.win_rate)}</b> <span style={{ color: "var(--color-muted)" }}>(평균 {ret(h.avg_return)}, {h.n}건)</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── 자산 추이 ────────────────────────────────────────────────────────────────────
function EquityCurve() {
  const { data } = useSWR(`${B}/api/ai/portfolio-series?days=90`, fetcher);
  const series: any[] = data?.series ?? [];
  if (series.length === 0) {
    return (
      <div className="stockcy-card" style={{ padding: "1rem 1.2rem" }}>
        <div style={{ fontWeight: 800, fontSize: "1rem", marginBottom: "4px" }}>💰 자산 추이</div>
        <div style={{ fontSize: "0.8rem", color: "var(--color-muted)" }}>매일 새벽 보유 스냅샷이 쌓이면 평가손익 추이가 표시됩니다. (오늘부터 누적)</div>
      </div>
    );
  }
  const pcts = series.map((s) => s.eval_pct).filter((v) => v != null) as number[];
  const lo = Math.min(0, ...pcts), hi = Math.max(0, ...pcts);
  const span = hi - lo || 1;
  return (
    <div className="stockcy-card" style={{ padding: "1rem 1.2rem" }}>
      <div style={{ fontWeight: 800, fontSize: "1rem", marginBottom: "10px" }}>💰 자산 추이 <span style={{ fontSize: "0.72rem", fontWeight: 600, color: "var(--color-muted)" }}>— 일별 평가손익률 (KR 보유 기준)</span></div>
      <div style={{ display: "flex", alignItems: "flex-end", gap: "3px", height: "90px", marginBottom: "8px" }}>
        {series.map((s, i) => {
          const v = s.eval_pct ?? 0;
          const h = Math.max(3, ((v - lo) / span) * 86);
          return <div key={i} title={`${s.date}: ${ret(s.eval_pct)}`} style={{ flex: 1, minWidth: "2px", height: `${h}px`, background: v >= 0 ? "#34d399" : "#f87171", borderRadius: "2px 2px 0 0", opacity: 0.85 }} />;
        })}
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.74rem", color: "var(--color-subtle)" }}>
        <span>{series[0].date} · {ret(series[0].eval_pct)}</span>
        <span style={{ fontWeight: 800, color: wrColor((series[series.length - 1].eval_pct ?? 0) >= 0 ? 60 : 0) }}>최신 {ret(series[series.length - 1].eval_pct)}</span>
      </div>
    </div>
  );
}

// ── 시장 기록 다시보기 ──────────────────────────────────────────────────────────
function MarketLogArchive() {
  const { data } = useSWR(`${B}/api/ai/market-log/dates?limit=60`, fetcher);
  const items: any[] = data?.items ?? [];
  const [sel, setSel] = useState<{ date: string; kind: string } | null>(null);
  const { data: detail } = useSWR(
    sel ? `${B}/api/ai/market-log?date=${sel.date}&kind=${sel.kind}` : null,
    fetcher
  );

  const kindLabel = (k: string) => (k === "commentary" ? "🧭 시장 인사이트" : "📈 시나리오");

  return (
    <div className="stockcy-card" style={{ padding: "1rem 1.2rem" }}>
      <div style={{ fontWeight: 800, fontSize: "1rem", marginBottom: "4px" }}>🗂️ 시장 기록 다시보기</div>
      <div style={{ fontSize: "0.74rem", color: "var(--color-muted)", marginBottom: "10px" }}>그날의 시장 인사이트·시나리오를 날짜별로 보관합니다. (오늘부터 누적)</div>
      {items.length === 0 ? (
        <div style={{ fontSize: "0.8rem", color: "var(--color-muted)" }}>아직 보관된 기록이 없습니다. 시장 인사이트/시나리오가 생성되면 쌓입니다.</div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "minmax(180px, 240px) 1fr", gap: "14px" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: "4px", maxHeight: "360px", overflowY: "auto" }}>
            {items.map((it, i) => {
              const active = sel?.date === it.log_date && sel?.kind === it.kind;
              return (
                <button key={i} onClick={() => setSel({ date: it.log_date, kind: it.kind })}
                  style={{ textAlign: "left", padding: "6px 10px", borderRadius: "6px", cursor: "pointer", fontSize: "0.78rem",
                    border: `1px solid ${active ? "var(--color-accent)" : "var(--color-border)"}`,
                    background: active ? "rgba(99,102,241,0.15)" : "transparent", color: "var(--color-text)" }}>
                  <div style={{ fontWeight: 700 }}>{it.log_date}</div>
                  <div style={{ fontSize: "0.7rem", color: "var(--color-muted)" }}>{kindLabel(it.kind)}</div>
                </button>
              );
            })}
          </div>
          <div style={{ minWidth: 0 }}>
            {!sel ? (
              <div style={{ fontSize: "0.8rem", color: "var(--color-muted)", padding: "1rem" }}>왼쪽에서 날짜를 선택하세요.</div>
            ) : !detail?.data ? (
              <div style={{ fontSize: "0.8rem", color: "var(--color-muted)", padding: "1rem" }}>불러오는 중...</div>
            ) : sel.kind === "commentary" ? (
              <div>
                <div style={{ fontWeight: 800, fontSize: "0.95rem", marginBottom: "6px" }}>{detail.data.title}</div>
                <MarkdownLite text={detail.data.commentary} style={{ fontSize: "0.84rem", color: "var(--color-subtle)", lineHeight: 1.7 }} />
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                {(detail.data.issues ?? []).map((iss: any, i: number) => (
                  <div key={i} style={{ background: "rgba(0,0,0,0.18)", borderRadius: "6px", padding: "8px 12px" }}>
                    <div style={{ fontWeight: 700, fontSize: "0.85rem" }}>{iss.title}</div>
                    <div style={{ fontSize: "0.76rem", color: "var(--color-subtle)", marginTop: "2px" }}>{iss.summary}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default function PerformancePage() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "16px", maxWidth: "1100px" }}>
      <h1 style={{ fontSize: "1.5rem", fontWeight: 800, margin: 0 }}>📊 성과 · 기록</h1>
      <div style={{ fontSize: "0.82rem", color: "var(--color-muted)", marginTop: "-8px" }}>이 시스템이 실제로 맞고 있는지, 그때 시장을 어떻게 봤는지, 내 자산이 어떻게 변했는지를 한 곳에서.</div>
      <EngineScoreboard />
      <EquityCurve />
      <MarketLogArchive />
    </div>
  );
}
