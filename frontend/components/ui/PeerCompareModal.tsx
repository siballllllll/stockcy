"use client";
import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { api } from "@/lib/api";

// ── 동종 비교 (v3.154.0) ─────────────────────────────────────────────────────
// 종목검색 안에서 인라인으로 펼치던 표를 모달로 옮겼다. 표가 12~13행이라 인라인이면
// 아래 내용이 통째로 밀려 가시성이 떨어진다는 사용자 지적.
//
// zone.win_rate는 섀도우 리그 실현 거래의 실측 승률이고, 검증되지 않은 시장에서는
// null로 내려온다(예: '이슈×지지구간'은 국내에서만 유의). null이면 "· 미검증"으로 표시한다.
interface PeerZone {
  key: string;
  label: string;
  win_rate: number | null;
  n: number | null;
  note: string;
}
export interface PeerRow {
  ticker: string;
  name: string;
  market: string;
  price: number | null;
  change_pct: number | null;
  rsi: number | null;
  mom_5: number | null;
  bb_pctb: number | null;
  ma20_dist: number | null;
  pos_52w: number | null;
  vol_ratio: number | null;
  zone: PeerZone | null;
  error?: string | null;
}
interface PeerCompare {
  base: PeerRow | null;
  cached?: boolean;
  sector: string | null;
  sub_sector: string | null;
  theme: string | null;
  same_market: PeerRow[];
  cross_market: PeerRow[];
  baseline_win_rate: number;
}

export function PeerCompareModal({
  ticker,
  market,
  onClose,
}: {
  ticker: string;
  market: string;
  onClose: () => void;
}) {
  const [data, setData] = useState<PeerCompare | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const r = await (api.ai as any).peerCompare(ticker, market);
        if (alive) setData(r as PeerCompare);
      } catch (e: any) {
        if (alive) setError(String(e?.message || e) || "불러오지 못했습니다");
      }
    })();
    return () => { alive = false; };
  }, [ticker, market]);

  // ESC로 닫기 — 기존 모달들과 동일한 조작감
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const num = (v: number | null | undefined, suffix = "", digits = 1) =>
    v === null || v === undefined ? "–" : v.toFixed(digits) + suffix;

  const rows: Array<{ row: PeerRow; group: string }> = data
    ? ([] as Array<{ row: PeerRow; group: string }>)
        .concat(data.base ? [{ row: data.base, group: "기준" }] : [])
        .concat(data.same_market.map((r) => ({ row: r, group: "동종" })))
        .concat(data.cross_market.map((r) => ({ row: r, group: "교차" })))
    : [];

  return (
    <div
      style={{
        position: "fixed", inset: 0, zIndex: 9999,
        background: "rgba(0,0,0,0.7)", backdropFilter: "blur(4px)",
        display: "flex", alignItems: "center", justifyContent: "center",
        padding: "1rem",
      }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        style={{
          background: "var(--color-card)", border: "1px solid var(--color-border)",
          borderRadius: "12px", width: "100%", maxWidth: "940px",
          maxHeight: "85vh", display: "flex", flexDirection: "column",
          boxShadow: "0 24px 64px rgba(0,0,0,0.6)",
        }}
      >
        {/* 헤더 */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "1rem 1.25rem", borderBottom: "1px solid var(--color-border)" }}>
          <div style={{ minWidth: 0 }}>
            <h2 style={{ margin: 0, fontSize: "1.05rem", fontWeight: 700 }}>⚖ 동종 비교</h2>
            <div style={{ fontSize: "0.72rem", color: "var(--color-muted)", marginTop: "3px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {data
                ? [data.sub_sector ? data.sector + " › " + data.sub_sector : null,
                   data.theme ? "교차 테마 " + data.theme : null].filter(Boolean).join(" · ") || "섹터 정보 없음"
                : "불러오는 중…"}
            </div>
          </div>
          <button
            onClick={onClose}
            title="닫기 (ESC)"
            style={{ background: "transparent", border: "none", cursor: "pointer", color: "var(--color-muted)", display: "flex", alignItems: "center", flexShrink: 0 }}
          >
            <X size={20} />
          </button>
        </div>

        {/* 바디 */}
        <div style={{ flex: 1, overflowY: "auto", padding: "1rem 1.25rem 1.25rem" }}>
          {error ? (
            <div style={{ fontSize: "0.85rem", color: "var(--color-danger)", padding: "1.5rem 0", textAlign: "center" }}>{error}</div>
          ) : !data ? (
            <div style={{ textAlign: "center", padding: "3rem 0", color: "var(--color-muted)" }}>
              <div style={{ fontSize: "2rem", marginBottom: "0.75rem" }}>⚖</div>
              <div style={{ fontSize: "0.9rem", fontWeight: 600, color: "var(--color-text)" }}>동종 종목 지표 수집 중…</div>
              <div style={{ fontSize: "0.8rem", marginTop: "4px" }}>첫 조회는 몇 초 걸립니다 (이후 3분간 즉시)</div>
            </div>
          ) : (
            <>
              <div style={{ fontSize: "0.74rem", color: "var(--color-muted)", marginBottom: "10px", lineHeight: 1.55 }}>
                오른쪽 <b style={{ color: "var(--color-text)" }}>실측 구간</b>은 섀도우 리그 실현 거래에서 측정된 승률입니다
                (랜덤 대조군 <b style={{ color: "var(--color-text)" }}>{data.baseline_win_rate}%</b>).
                승률 없이 “미검증”으로 표시되면 그 시장에서는 통계적 우위가 확인되지 않은 구간입니다.
              </div>
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.8rem", minWidth: "700px" }}>
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
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map(({ row, group }, i) => {
                      const isBase = group === "기준";
                      const z = row.zone;
                      const wr = z && z.win_rate !== null && z.win_rate !== undefined ? z.win_rate : null;
                      const good = wr !== null && wr >= data.baseline_win_rate + 10;
                      const bad = wr !== null && wr <= data.baseline_win_rate + 3;
                      return (
                        <tr key={row.ticker + "-" + i} style={{
                          borderTop: "1px solid var(--color-border)",
                          background: isBase ? "rgba(99,102,241,0.10)" : undefined,
                          textAlign: "right",
                        }}>
                          <td style={{ textAlign: "left", padding: "6px", whiteSpace: "nowrap" }}>
                            <span style={{
                              fontSize: "0.64rem", fontWeight: 800, marginRight: "5px",
                              color: group === "교차" ? "#fbbf24" : "var(--color-muted)",
                            }}>{group}</span>
                            <strong style={{ color: "var(--color-text)" }}>{row.name}</strong>
                            <span style={{ color: "var(--color-subtle)", marginLeft: "4px", fontSize: "0.7rem" }}>
                              {row.market === "국내" ? "KR" : "US"}
                            </span>
                          </td>
                          <td style={{ padding: "6px", whiteSpace: "nowrap" }}>
                            {row.price === null ? "–" : row.market === "국내"
                              ? row.price.toLocaleString() : "$" + row.price.toFixed(2)}
                            {row.change_pct !== null && (
                              <span style={{
                                marginLeft: "5px", fontWeight: 700,
                                color: row.change_pct >= 0 ? "var(--color-danger)" : "var(--color-primary)",
                              }}>{row.change_pct >= 0 ? "+" : ""}{row.change_pct.toFixed(2)}%</span>
                            )}
                          </td>
                          <td style={{ padding: "6px", fontWeight: 700,
                                       color: (row.mom_5 || 0) >= 10 ? "var(--color-warning)" : "var(--color-text)" }}>
                            {num(row.mom_5, "%")}
                          </td>
                          <td style={{ padding: "6px" }}>{num(row.rsi, "", 0)}</td>
                          <td style={{ padding: "6px" }}>{num(row.bb_pctb, "", 2)}</td>
                          <td style={{ padding: "6px" }}>{num(row.ma20_dist, "%")}</td>
                          <td style={{ padding: "6px" }}>{num(row.pos_52w, "%", 0)}</td>
                          <td style={{ textAlign: "left", padding: "6px", whiteSpace: "nowrap" }}>
                            {row.error ? (
                              <span style={{ color: "var(--color-subtle)" }}>조회 실패</span>
                            ) : !z ? "–" : (
                              <span title={z.note} style={{
                                fontSize: "0.7rem", fontWeight: 700, padding: "2px 6px", borderRadius: "4px",
                                color: good ? "#6ee7b7" : bad ? "#fca5a5" : "var(--color-muted)",
                                background: good ? "rgba(52,211,153,0.12)" : bad ? "rgba(255,75,75,0.10)" : "rgba(255,255,255,0.04)",
                                border: "1px solid " + (good ? "rgba(52,211,153,0.35)" : bad ? "rgba(255,75,75,0.30)" : "var(--color-border)"),
                              }}>
                                {z.label}{wr !== null ? " " + wr + "%" : " · 미검증"}
                              </span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              {rows.length <= 1 && (
                <div style={{ fontSize: "0.78rem", color: "var(--color-muted)", marginTop: "10px" }}>
                  같은 섹터에서 비교할 종목을 찾지 못했습니다.
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
