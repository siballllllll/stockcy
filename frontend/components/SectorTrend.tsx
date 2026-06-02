"use client";
import { useEffect, useState, useCallback } from "react";

const BASE = "/backend";

function fmt(n: number) {
  const v = Math.abs(n);
  if (v >= 1e8) return `${(n / 1e8).toFixed(1)}억`;
  if (v >= 1e4) return `${(n / 1e4).toFixed(0)}만`;
  return `${n}`;
}

function Sparkline({ values }: { values: number[] }) {
  const w = 130, h = 30;
  if (!values?.length) return null;
  const max = Math.max(...values.map(Math.abs), 1);
  const n = values.length;
  const xs = (i: number) => (i * w) / Math.max(n - 1, 1);
  const ys = (v: number) => h / 2 - (v / max) * (h / 2 - 3);
  const pts = values.map((v, i) => `${xs(i).toFixed(1)},${ys(v).toFixed(1)}`).join(" ");
  return (
    <svg width={w} height={h} style={{ display: "block", flexShrink: 0 }}>
      <line x1={0} y1={h / 2} x2={w} y2={h / 2} stroke="rgba(255,255,255,0.12)" strokeWidth={1} />
      <polyline points={pts} fill="none" stroke="#a78bfa" strokeWidth={1.4} />
      {values.map((v, i) => (
        <circle key={i} cx={xs(i)} cy={ys(v)} r={1.6} fill={v >= 0 ? "#f87171" : "#60a5fa"} />
      ))}
    </svg>
  );
}

export function SectorTrend() {
  const [data, setData] = useState<any>(null);
  const [analysis, setAnalysis] = useState<any>(null);
  const [days, setDays] = useState(14);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (d: number) => {
    setLoading(true);
    try {
      const res = await fetch(`${BASE}/api/kr/sector-trend?days=${d}&top_n=10`);
      setData(await res.json());
    } catch { /* 무시 */ } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(days); }, [load, days]);
  useEffect(() => {
    fetch(`${BASE}/api/kr/sector-analysis`).then(r => r.json()).then(setAnalysis).catch(() => {});
  }, []);

  const sectors = data?.sectors || [];
  const nDays = (data?.dates || []).length;

  return (
    <div style={{ background: "var(--color-card)", border: "1px solid rgba(167,139,250,0.25)", borderRadius: "12px", padding: "1rem 1.25rem" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.5rem", marginBottom: "0.6rem", flexWrap: "wrap" }}>
        <div style={{ fontWeight: 800, fontSize: "0.98rem", color: "var(--color-text)" }}>
          📈 섹터 자금 추세 <span style={{ fontSize: "0.74rem", color: "var(--color-muted)", fontWeight: 600 }}>{nDays}일 세력 누적 흐름</span>
        </div>
        <div style={{ display: "flex", gap: "4px" }}>
          {[7, 14, 30].map(d => (
            <button key={d} onClick={() => setDays(d)} style={{ fontSize: "0.72rem", padding: "3px 9px", borderRadius: "6px", fontWeight: 700, cursor: "pointer", border: "1px solid var(--color-border)", background: days === d ? "#a78bfa" : "transparent", color: days === d ? "#0e1117" : "var(--color-muted)" }}>
              {d}일
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div style={{ color: "var(--color-muted)", fontSize: "0.82rem", padding: "1rem 0" }}>추세 불러오는 중...</div>
      ) : sectors.length === 0 ? (
        <div style={{ color: "var(--color-muted)", fontSize: "0.82rem", padding: "1rem 0" }}>
          아직 추세 데이터가 부족합니다. (매일 자동 적재되며, 며칠 쌓이면 표시됩니다)
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
          {sectors.map((s: any, i: number) => {
            const pos = (s.total || 0) >= 0;
            return (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: "10px", padding: "5px 7px", borderRadius: "6px", background: "rgba(255,255,255,0.02)" }}>
                <span style={{ fontSize: "0.7rem", color: "var(--color-muted)", width: "16px", textAlign: "right", flexShrink: 0 }}>{i + 1}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "5px", flexWrap: "wrap" }}>
                    <span style={{ fontWeight: 700, fontSize: "0.8rem", color: "var(--color-text)" }}>{s.sector}</span>
                    {s.inflow_streak >= 2 && (
                      <span style={{ fontSize: "0.6rem", padding: "0 5px", borderRadius: "3px", background: "rgba(239,68,68,0.15)", color: "#f87171", border: "1px solid rgba(239,68,68,0.3)", fontWeight: 800 }}>🔥 {s.inflow_streak}일 연속유입</span>
                    )}
                  </div>
                  <div style={{ fontSize: "0.66rem", color: "var(--color-muted)" }}>
                    누적 <span style={{ color: pos ? "#f87171" : "#60a5fa", fontWeight: 700 }}>{pos ? "+" : ""}{fmt(s.total)}주</span> · 유입 {s.days_positive}/{nDays}일
                  </div>
                </div>
                <Sparkline values={s.series} />
              </div>
            );
          })}
        </div>
      )}
      {/* 히스토리 분석 — 지속 매집 섹터 */}
      {analysis?.available && (
        <div style={{ marginTop: "0.9rem", borderTop: "1px solid var(--color-border)", paddingTop: "0.6rem" }}>
          <div style={{ fontSize: "0.74rem", fontWeight: 800, color: "var(--color-text)", marginBottom: "5px" }}>
            🧠 지속 매집 섹터 <span style={{ fontSize: "0.66rem", color: "var(--color-muted)", fontWeight: 600 }}>{analysis.period} ({analysis.days}일 분석)</span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "3px" }}>
            {(analysis.accumulation || []).slice(0, 6).map((x: any, i: number) => (
              <div key={i} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "8px", fontSize: "0.72rem", padding: "2px 4px" }}>
                <span style={{ fontWeight: 700, color: "var(--color-text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{x.sector}</span>
                <span style={{ color: "var(--color-muted)", whiteSpace: "nowrap", flexShrink: 0 }}>
                  유입비율 <b style={{ color: "#f87171" }}>{x.pos_ratio}%</b> · 최장 {x.best_streak}일{x.now_streak >= 2 ? ` · 🔥현재 ${x.now_streak}일` : ""}
                </span>
              </div>
            ))}
          </div>
          <div style={{ marginTop: "4px", fontSize: "0.64rem", color: "var(--color-muted)" }}>
            ↘ 지속 이탈: {(analysis.distribution || []).slice(0, 4).map((x: any) => x.sector).join(", ") || "-"}
          </div>
        </div>
      )}

      <div style={{ marginTop: "0.6rem", fontSize: "0.65rem", color: "var(--color-muted)", lineHeight: 1.5 }}>
        💡 막대선은 일별 세력 순매수(🔴양/🔵음). <b>연속유입</b>·<b>누적</b>이 클수록 세력이 지속 매집 중인 섹터.
      </div>
    </div>
  );
}
