"use client";
import useSWR from "swr";
import { api } from "@/lib/api";

/** 토스 기반 종목 마이크로 정보: 호가창·체결·상하한가·장운영·마스터 */
export default function OrderbookPanel({ code, market }: { code: string; market: string }) {
  const isKR = market === "KR";
  const sym = code;

  const { data: ob } = useSWR(sym ? `ob-${sym}` : null, () => api.portfolio.orderbook(sym), { refreshInterval: 5000 });
  const { data: trades } = useSWR(sym ? `tr-${sym}` : null, () => api.portfolio.trades(sym, 20), { refreshInterval: 10000 });
  const { data: limits } = useSWR(sym ? `pl-${sym}` : null, () => api.portfolio.priceLimits(sym), { refreshInterval: 60000 });
  const { data: cal } = useSWR(`cal-${market}`, () => api.portfolio.marketCalendar(market), { refreshInterval: 1800000 });
  const { data: master } = useSWR(sym ? `ms-${sym}` : null, () => api.portfolio.stockMaster([sym]), { refreshInterval: 3600000 });

  const cur = ob?.currency ?? (isKR ? "KRW" : "USD");
  const fmt = (n: number) => isKR
    ? `₩${Math.round(n).toLocaleString()}`
    : `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  const fmtVol = (n: number) => n >= 10000 ? `${(n / 10000).toFixed(1)}만` : Math.round(n).toLocaleString();

  const meta = master?.[sym];
  const asks = (ob?.asks ?? []).slice(0, 5).reverse(); // 높은가 위로
  const bids = (ob?.bids ?? []).slice(0, 5);
  const maxVol = Math.max(1, ...asks.map(a => a.volume), ...bids.map(b => b.volume));

  const box: React.CSSProperties = { background: "var(--color-surface)", border: "1px solid var(--color-border)", borderRadius: "8px", padding: "12px" };
  const label: React.CSSProperties = { fontSize: "0.72rem", color: "var(--color-muted)", marginBottom: "6px", fontWeight: 700 };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
      {/* 헤더: 마스터 + 장운영 */}
      <div style={{ ...box, display: "flex", flexWrap: "wrap", gap: "12px", alignItems: "center", fontSize: "0.74rem" }}>
        {meta?.name && <span style={{ fontWeight: 800, fontSize: "0.85rem" }}>{meta.name}</span>}
        {meta?.market && <span style={{ color: "var(--color-muted)" }}>{meta.market}</span>}
        {meta?.list_date && <span style={{ color: "var(--color-muted)" }}>상장 {meta.list_date}</span>}
        {meta?.status && meta.status !== "ACTIVE" && <span style={{ color: "var(--color-danger)", fontWeight: 700 }}>{meta.status}</span>}
        <span style={{ marginLeft: "auto", color: cal?.is_open ? "var(--color-success)" : "var(--color-muted)", fontWeight: 700 }}>
          {cal?.is_open ? "● 오늘 개장" : "○ 오늘 휴장"}
        </span>
        {cal?.next_business_day && <span style={{ color: "var(--color-muted)" }}>다음 {cal.next_business_day.slice(5)}</span>}
      </div>

      {/* 상하한가 (KR) */}
      {(limits?.upper || limits?.lower) && (
        <div style={{ ...box, display: "flex", gap: "16px", fontSize: "0.76rem" }}>
          <span><span style={{ color: "var(--color-muted)" }}>상한가 </span><b style={{ color: "var(--color-danger)" }}>{fmt(limits!.upper!)}</b></span>
          <span><span style={{ color: "var(--color-muted)" }}>하한가 </span><b style={{ color: "var(--color-primary)" }}>{fmt(limits!.lower!)}</b></span>
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px" }}>
        {/* 호가창 */}
        <div style={box}>
          <div style={label}>호가창</div>
          {(asks.length === 0 && bids.length === 0) ? (
            <div style={{ fontSize: "0.72rem", color: "var(--color-muted)" }}>장 시간에 표시됩니다</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
              {asks.map((a, i) => (
                <Row key={`a${i}`} price={fmt(a.price)} vol={fmtVol(a.volume)} pct={a.volume / maxVol} side="ask" />
              ))}
              {bids.map((b, i) => (
                <Row key={`b${i}`} price={fmt(b.price)} vol={fmtVol(b.volume)} pct={b.volume / maxVol} side="bid" />
              ))}
            </div>
          )}
        </div>

        {/* 체결 */}
        <div style={box}>
          <div style={label}>최근 체결</div>
          {(!trades || trades.length === 0) ? (
            <div style={{ fontSize: "0.72rem", color: "var(--color-muted)" }}>장 시간에 표시됩니다</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "2px", maxHeight: "180px", overflowY: "auto" }}>
              {trades.slice(0, 15).map((t, i) => (
                <div key={i} style={{ display: "flex", justifyContent: "space-between", fontSize: "0.72rem" }}>
                  <span style={{ color: "var(--color-muted)" }}>{String(t.timestamp).slice(11, 19)}</span>
                  <span style={{ fontWeight: 700 }}>{fmt(t.price)}</span>
                  <span style={{ color: "var(--color-muted)" }}>{fmtVol(t.volume)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Row({ price, vol, pct, side }: { price: string; vol: string; pct: number; side: "ask" | "bid" }) {
  const color = side === "ask" ? "var(--color-primary)" : "var(--color-danger)";
  return (
    <div style={{ position: "relative", display: "flex", justifyContent: "space-between", fontSize: "0.72rem", padding: "2px 4px" }}>
      <div style={{ position: "absolute", top: 0, bottom: 0, [side === "ask" ? "left" : "right"]: 0, width: `${Math.max(3, pct * 100)}%`, background: side === "ask" ? "rgba(50,150,255,0.10)" : "rgba(239,68,68,0.10)", borderRadius: "3px" } as React.CSSProperties} />
      <span style={{ zIndex: 1, fontWeight: 700, color }}>{price}</span>
      <span style={{ zIndex: 1, color: "var(--color-muted)" }}>{vol}</span>
    </div>
  );
}
