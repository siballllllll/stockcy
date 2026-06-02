"use client";
import { useEffect, useState, useCallback } from "react";

const BASE = "/backend";

type FlowItem = {
  종목코드: string; 종목명: string;
  외국인순매수: number; 기관순매수: number; 합산: number;
  주도: string; 구분: string;
};

function fmt(n: number) {
  const v = Math.abs(n);
  if (v >= 1e8) return `${(n / 1e8).toFixed(1)}억`;
  if (v >= 1e4) return `${(n / 1e4).toFixed(0)}만`;
  return `${n.toLocaleString()}`;
}

function FlowRow({ x, inflow }: { x: FlowItem; inflow: boolean }) {
  const strong = x.구분 === "동반매수" || x.구분 === "동반매도";
  const color = inflow ? "#f87171" : "#60a5fa";
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "8px", padding: "5px 7px", borderRadius: "5px", background: strong ? (inflow ? "rgba(239,68,68,0.07)" : "rgba(96,165,250,0.07)") : "rgba(255,255,255,0.02)", fontSize: "0.74rem" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "5px", overflow: "hidden" }}>
        <span style={{ fontWeight: 700, color: "var(--color-text)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{x.종목명}</span>
        {strong && <span style={{ fontSize: "0.58rem", padding: "0 4px", borderRadius: "3px", background: color, color: "#0e1117", fontWeight: 800, whiteSpace: "nowrap" }}>{inflow ? "동반매수" : "동반매도"}</span>}
        <span style={{ fontSize: "0.6rem", color: "var(--color-muted)", whiteSpace: "nowrap" }}>{x.주도}주도</span>
      </div>
      <div style={{ textAlign: "right", whiteSpace: "nowrap" }}>
        <div style={{ color, fontWeight: 800 }}>{x.합산 >= 0 ? "+" : ""}{fmt(x.합산)}주</div>
        <div style={{ fontSize: "0.6rem", color: "var(--color-muted)" }}>외{fmt(x.외국인순매수)} · 기{fmt(x.기관순매수)}</div>
      </div>
    </div>
  );
}

export function SupplyPowerFlow() {
  const [flow, setFlow] = useState<any>(null);
  const [rotation, setRotation] = useState<any>(null);
  const [mkt, setMkt] = useState<"J" | "Q">("J");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [f, r] = await Promise.all([
        fetch(`${BASE}/api/kr/supply-power-flow`).then(res => res.json()).catch(() => null),
        fetch(`${BASE}/api/kr/supply-rotation`).then(res => res.json()).catch(() => null),
      ]);
      setFlow(f); setRotation(r);
    } catch { /* 무시 */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const m = flow?.markets?.[mkt];

  return (
    <div style={{ background: "var(--color-card)", border: "1px solid rgba(99,102,241,0.25)", borderRadius: "12px", padding: "1rem 1.25rem" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.5rem", marginBottom: "0.5rem", flexWrap: "wrap" }}>
        <div style={{ fontWeight: 800, fontSize: "0.98rem", color: "var(--color-text)" }}>
          🐋 세력 자금 흐름 <span style={{ fontSize: "0.74rem", color: "var(--color-muted)", fontWeight: 600 }}>외국인·기관 실시간 수급</span>
        </div>
        <div style={{ display: "flex", gap: "4px" }}>
          {(["J", "Q"] as const).map(k => (
            <button key={k} onClick={() => setMkt(k)} style={{ fontSize: "0.72rem", padding: "3px 10px", borderRadius: "6px", fontWeight: 700, cursor: "pointer", border: "1px solid var(--color-border)", background: mkt === k ? "var(--color-primary)" : "transparent", color: mkt === k ? "#0e1117" : "var(--color-muted)" }}>
              {k === "J" ? "코스피" : "코스닥"}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div style={{ color: "var(--color-muted)", fontSize: "0.82rem", padding: "1rem 0" }}>수급 불러오는 중...</div>
      ) : !m || (!m.inflow?.length && !m.outflow?.length) ? (
        <div style={{ color: "var(--color-muted)", fontSize: "0.82rem", padding: "1rem 0" }}>
          수급 데이터가 없습니다. (장중 09:00~15:30에 갱신됩니다)
        </div>
      ) : (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px" }}>
            <div>
              <div style={{ fontSize: "0.72rem", fontWeight: 800, color: "#f87171", marginBottom: "4px" }}>🟢 세력 유입 TOP (순매수)</div>
              <div style={{ display: "flex", flexDirection: "column", gap: "3px" }}>
                {(m.inflow || []).slice(0, 8).map((x: FlowItem, i: number) => <FlowRow key={i} x={x} inflow />)}
              </div>
            </div>
            <div>
              <div style={{ fontSize: "0.72rem", fontWeight: 800, color: "#60a5fa", marginBottom: "4px" }}>🔴 세력 이탈 TOP (순매도)</div>
              <div style={{ display: "flex", flexDirection: "column", gap: "3px" }}>
                {(m.outflow || []).slice(0, 8).map((x: FlowItem, i: number) => <FlowRow key={i} x={x} inflow={false} />)}
              </div>
            </div>
          </div>

          {/* 자금 이동 추적 (히스토리) */}
          <div style={{ marginTop: "0.9rem", borderTop: "1px solid var(--color-border)", paddingTop: "0.6rem" }}>
            <div style={{ fontSize: "0.74rem", fontWeight: 800, color: "var(--color-text)", marginBottom: "4px" }}>🔄 세력 자금 이동 (전일 대비)</div>
            {!rotation?.available ? (
              <div style={{ fontSize: "0.72rem", color: "var(--color-muted)" }}>{rotation?.reason || "준비 중"} {rotation?.have_dates?.length ? `(현재 ${rotation.have_dates.length}일치)` : ""}</div>
            ) : (
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px", fontSize: "0.72rem" }}>
                <div>
                  <div style={{ color: "#f87171", fontWeight: 700, marginBottom: "2px" }}>↗ 자금 유입 증가</div>
                  {(rotation.moved_in || []).slice(0, 5).map((r: any, i: number) => (
                    <div key={i} style={{ display: "flex", justifyContent: "space-between", color: "var(--color-subtle)" }}>
                      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: "60%" }}>{r.name}</span>
                      <span style={{ color: "#f87171" }}>+{fmt(r.delta)}주</span>
                    </div>
                  ))}
                </div>
                <div>
                  <div style={{ color: "#60a5fa", fontWeight: 700, marginBottom: "2px" }}>↘ 자금 이탈 증가</div>
                  {(rotation.moved_out || []).slice(0, 5).map((r: any, i: number) => (
                    <div key={i} style={{ display: "flex", justifyContent: "space-between", color: "var(--color-subtle)" }}>
                      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: "60%" }}>{r.name}</span>
                      <span style={{ color: "#60a5fa" }}>{fmt(r.delta)}주</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          <div style={{ marginTop: "0.6rem", fontSize: "0.66rem", color: "var(--color-muted)", lineHeight: 1.5 }}>
            💡 외국인·기관이 <b>함께 순매수</b>(동반매수)하는 종목 = 강한 세력 유입 신호. {flow?.generated_at} 기준.
          </div>
        </>
      )}
    </div>
  );
}
