"use client";
import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";

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

function FlowRow({ x, inflow, onPick }: { x: FlowItem; inflow: boolean; onPick?: (code: string) => void }) {
  const strong = x.구분 === "동반매수" || x.구분 === "동반매도";
  const color = inflow ? "#f87171" : "#60a5fa";
  const baseBg = strong ? (inflow ? "rgba(239,68,68,0.07)" : "rgba(96,165,250,0.07)") : "rgba(255,255,255,0.02)";
  const clickable = !!(onPick && x.종목코드);
  return (
    <div
      onClick={clickable ? () => onPick!(String(x.종목코드)) : undefined}
      title={clickable ? `${x.종목명} 종목검색으로 이동` : undefined}
      style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "8px", padding: "5px 7px", borderRadius: "5px", background: baseBg, fontSize: "0.74rem", cursor: clickable ? "pointer" : "default", transition: "background 0.12s" }}
      onMouseEnter={clickable ? (e) => { e.currentTarget.style.background = inflow ? "rgba(239,68,68,0.15)" : "rgba(96,165,250,0.15)"; } : undefined}
      onMouseLeave={clickable ? (e) => { e.currentTarget.style.background = baseBg; } : undefined}
    >
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
  const [abnormal, setAbnormal] = useState<any>(null);
  const [sectorToday, setSectorToday] = useState<any[]>([]);
  const [sectorRot, setSectorRot] = useState<any>(null);
  const [mkt, setMkt] = useState<"J" | "Q">("J");
  const [loading, setLoading] = useState(true);
  const [cumDays, setCumDays] = useState(20);   // 누적 매집 기간
  const [cum, setCum] = useState<any>(null);
  const router = useRouter();
  // 순매수/순매도 종목 클릭 → 해당 종목 검색 페이지로 이동 (코스피·코스닥 모두 KR)
  const goSearch = useCallback((code: string) => {
    if (code) router.push(`/search?q=${encodeURIComponent(code)}&market=KR`);
  }, [router]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [f, r, ab, sf, sr] = await Promise.all([
        fetch(`${BASE}/api/kr/supply-power-flow`).then(res => res.json()).catch(() => null),
        fetch(`${BASE}/api/kr/supply-rotation`).then(res => res.json()).catch(() => null),
        fetch(`${BASE}/api/kr/supply-abnormal`).then(res => res.json()).catch(() => null),
        fetch(`${BASE}/api/kr/sector-flow?days=1`).then(res => res.json()).catch(() => null),
        fetch(`${BASE}/api/kr/sector-rotation`).then(res => res.json()).catch(() => null),
      ]);
      setFlow(f); setRotation(r); setAbnormal(ab);
      setSectorToday(sf?.series || []);
      setSectorRot(sr);
    } catch { /* 무시 */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  // 기간 누적 세력 매집 — 기간/시장 바뀔 때 조회
  useEffect(() => {
    let alive = true;
    fetch(`${BASE}/api/kr/supply-cumulative?days=${cumDays}&market=${mkt}`)
      .then(res => res.json()).then(d => { if (alive) setCum(d); }).catch(() => {});
    return () => { alive = false; };
  }, [cumDays, mkt]);

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
                {(m.inflow || []).slice(0, 8).map((x: FlowItem, i: number) => <FlowRow key={i} x={x} inflow onPick={goSearch} />)}
              </div>
            </div>
            <div>
              <div style={{ fontSize: "0.72rem", fontWeight: 800, color: "#60a5fa", marginBottom: "4px" }}>🔴 세력 이탈 TOP (순매도)</div>
              <div style={{ display: "flex", flexDirection: "column", gap: "3px" }}>
                {(m.outflow || []).slice(0, 8).map((x: FlowItem, i: number) => <FlowRow key={i} x={x} inflow={false} onPick={goSearch} />)}
              </div>
            </div>
          </div>

          {/* 세력 이상 급증 감지 — 순매수 절대금액이 아니라 '제 덩치 대비 갑자기 몰린' 종목 */}
          {abnormal?.available && (() => {
            const surge = (abnormal.surge || []).filter((x: any) => x.market === mkt);
            const fresh = (abnormal.new_entrant || []).filter((x: any) => x.market === mkt);
            if (!surge.length && !fresh.length) return null;
            return (
              <div style={{ marginTop: "0.9rem", borderTop: "1px solid var(--color-border)", paddingTop: "0.6rem" }}>
                <div style={{ fontSize: "0.74rem", fontWeight: 800, color: "#fbbf24", marginBottom: "5px" }}>
                  🚨 세력 이상 급증 <span style={{ fontSize: "0.66rem", color: "var(--color-muted)", fontWeight: 600 }}>제 덩치 대비 비정상적으로 몰린 종목</span>
                </div>
                {surge.length > 0 && (
                  <div style={{ display: "flex", flexDirection: "column", gap: "3px", marginBottom: fresh.length ? "6px" : 0 }}>
                    {surge.slice(0, 6).map((x: any, i: number) => (
                      <div key={i} onClick={() => goSearch(String(x.ticker))} title={`${x.name} 종목검색`}
                        style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "8px", padding: "4px 8px", borderRadius: "5px", background: "rgba(245,158,11,0.08)", border: "1px solid rgba(245,158,11,0.2)", fontSize: "0.74rem", cursor: "pointer" }}
                        onMouseEnter={e => { e.currentTarget.style.background = "rgba(245,158,11,0.18)"; }}
                        onMouseLeave={e => { e.currentTarget.style.background = "rgba(245,158,11,0.08)"; }}>
                        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          <b style={{ color: "var(--color-text)" }}>{x.name}</b>
                          {x.multiple != null && <span style={{ fontSize: "0.62rem", color: "#fbbf24", marginLeft: "5px", fontWeight: 700 }}>평소 {x.multiple}배</span>}
                        </span>
                        <span style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                          <span style={{ color: "#f87171", fontWeight: 800 }}>+{fmt(x.today)}주</span>
                          <span style={{ fontSize: "0.6rem", color: "var(--color-muted)", marginLeft: "5px" }}>z{x.zscore}</span>
                        </span>
                      </div>
                    ))}
                  </div>
                )}
                {fresh.length > 0 && (
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "5px" }}>
                    <span style={{ fontSize: "0.66rem", color: "var(--color-muted)", fontWeight: 700, alignSelf: "center" }}>🆕 신규 급습:</span>
                    {fresh.slice(0, 8).map((x: any, i: number) => (
                      <span key={i} onClick={() => goSearch(String(x.ticker))} title={`${x.name} 종목검색`}
                        style={{ fontSize: "0.68rem", padding: "2px 7px", borderRadius: "5px", background: "rgba(52,211,153,0.1)", border: "1px solid rgba(52,211,153,0.3)", color: "#34d399", fontWeight: 700, cursor: "pointer" }}>
                        {x.name} +{fmt(x.today)}주
                      </span>
                    ))}
                  </div>
                )}
                <div style={{ fontSize: "0.62rem", color: "var(--color-muted)", marginTop: "4px" }}>※ 최근 {abnormal.lookback_days}일 기준. z = 자기 과거 평균 대비 표준편차 배수(2↑ 이상급증). 신규 급습 = 평소 상위권에 없다가 오늘 강하게 등장.</div>
              </div>
            );
          })()}

          {/* 기간 누적 세력 매집 TOP — 오늘 하루가 아닌 '일정 기간 꾸준히 사 모은' 종목 */}
          <div style={{ marginTop: "0.9rem", borderTop: "1px solid var(--color-border)", paddingTop: "0.6rem" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "6px", marginBottom: "5px" }}>
              <div style={{ fontSize: "0.74rem", fontWeight: 800, color: "var(--color-text)" }}>📈 기간 누적 세력 매집 TOP <span style={{ fontSize: "0.66rem", color: "var(--color-muted)", fontWeight: 600 }}>꾸준히 사 모은 종목</span></div>
              <div style={{ display: "flex", gap: "3px" }}>
                {[5, 20, 60].map(d => (
                  <button key={d} onClick={() => setCumDays(d)} style={{ fontSize: "0.66rem", padding: "2px 8px", borderRadius: "5px", fontWeight: 700, cursor: "pointer", border: "1px solid var(--color-border)", background: cumDays === d ? "var(--color-primary)" : "transparent", color: cumDays === d ? "#0e1117" : "var(--color-muted)" }}>{d}일</button>
                ))}
              </div>
            </div>
            {!cum?.items?.length ? (
              <div style={{ fontSize: "0.7rem", color: "var(--color-muted)" }}>누적 수급 데이터가 아직 부족합니다. (일별 스냅샷이 쌓이면 표시)</div>
            ) : (
              <>
                <div style={{ display: "flex", flexDirection: "column", gap: "3px" }}>
                  {cum.items.slice(0, 8).map((x: any, i: number) => (
                    <div key={i} onClick={() => goSearch(String(x.ticker))} title={`${x.name} 종목검색`}
                      style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "8px", padding: "4px 8px", borderRadius: "5px", background: "rgba(239,68,68,0.05)", fontSize: "0.74rem", cursor: "pointer" }}
                      onMouseEnter={e => { e.currentTarget.style.background = "rgba(239,68,68,0.13)"; }}
                      onMouseLeave={e => { e.currentTarget.style.background = "rgba(239,68,68,0.05)"; }}>
                      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        <b style={{ color: "var(--color-text)" }}>{x.name}</b>
                        <span style={{ fontSize: "0.62rem", color: "#34d399", marginLeft: "5px" }}>매집 {x.buy_days}/{x.days_seen}일</span>
                      </span>
                      <span style={{ color: "#f87171", fontWeight: 800, whiteSpace: "nowrap" }}>+{fmt(x.combined_sum)}주</span>
                    </div>
                  ))}
                </div>
                <div style={{ fontSize: "0.62rem", color: "var(--color-muted)", marginTop: "4px" }}>※ {cum.period} 누적 (외국인+기관 합산). 매집 N/M일 = 순매수한 날 / 데이터 있는 날.</div>
              </>
            )}
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

          {/* 섹터 자금 흐름 / 로테이션 */}
          {sectorToday.length > 0 && (
            <div style={{ marginTop: "0.9rem", borderTop: "1px solid var(--color-border)", paddingTop: "0.6rem" }}>
              <div style={{ fontSize: "0.74rem", fontWeight: 800, color: "var(--color-text)", marginBottom: "5px" }}>
                🔀 섹터 자금 흐름 <span style={{ fontSize: "0.66rem", color: "var(--color-muted)", fontWeight: 600 }}>오늘 세력 집중 섹터</span>
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "5px", marginBottom: "6px" }}>
                {[...sectorToday].sort((a, b) => (b.combined_sum || 0) - (a.combined_sum || 0)).slice(0, 8).map((s: any, i: number) => {
                  const pos = (s.combined_sum || 0) >= 0;
                  return (
                    <span key={i} style={{ fontSize: "0.7rem", padding: "2px 7px", borderRadius: "5px", background: pos ? "rgba(239,68,68,0.1)" : "rgba(96,165,250,0.1)", border: `1px solid ${pos ? "rgba(239,68,68,0.3)" : "rgba(96,165,250,0.3)"}`, color: pos ? "#f87171" : "#60a5fa", fontWeight: 700 }}>
                      {s.sector} {pos ? "+" : ""}{fmt(s.combined_sum)}주
                    </span>
                  );
                })}
              </div>
              {sectorRot?.available ? (
                <div style={{ fontSize: "0.7rem", color: "var(--color-subtle)", lineHeight: 1.6 }}>
                  <span style={{ color: "#f87171", fontWeight: 700 }}>↗ 자금 유입 전환:</span> {(sectorRot.into || []).slice(0, 3).map((x: any) => x.sector).join(", ") || "-"}<br />
                  <span style={{ color: "#60a5fa", fontWeight: 700 }}>↘ 자금 이탈 전환:</span> {(sectorRot.outof || []).slice(0, 3).map((x: any) => x.sector).join(", ") || "-"}
                  <span style={{ color: "var(--color-muted)", fontSize: "0.64rem" }}> ({sectorRot.prev}→{sectorRot.today})</span>
                </div>
              ) : (
                <div style={{ fontSize: "0.68rem", color: "var(--color-muted)" }}>
                  {sectorRot?.reason || "섹터 로테이션은 2거래일 쌓이면 표시됩니다"}{sectorRot?.have_dates?.length ? ` (현재 ${sectorRot.have_dates.length}일치)` : ""}
                </div>
              )}
            </div>
          )}

          <div style={{ marginTop: "0.6rem", fontSize: "0.66rem", color: "var(--color-muted)", lineHeight: 1.5 }}>
            💡 외국인·기관이 <b>함께 순매수</b>(동반매수)하는 종목 = 강한 세력 유입 신호. {flow?.generated_at} 기준.
          </div>
        </>
      )}
    </div>
  );
}
