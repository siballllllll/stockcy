"use client";
import useSWR from "swr";
import { api } from "@/lib/api";
import type { UsIndices, KrIndices } from "@/lib/types";

function Idx({ name, price, changePct }: { name: string; price: number; changePct: number }) {
  const up   = changePct > 0;
  const down = changePct < 0;
  const color = up ? "var(--color-up)" : down ? "var(--color-down)" : "var(--color-flat)";
  const sign  = up ? "+" : "";
  return (
    <span style={{ display: "inline-flex", alignItems: "baseline", gap: "0.3rem", flexShrink: 0 }}>
      <span style={{ color: "var(--color-muted)", fontSize: "0.72rem" }}>{name}</span>
      <span style={{ fontWeight: 600, fontSize: "0.82rem" }}>
        {price >= 10000 ? price.toLocaleString() : price.toFixed(2)}
      </span>
      <span style={{ color, fontSize: "0.72rem" }}>
        {sign}{changePct.toFixed(2)}%
      </span>
    </span>
  );
}

export function MarketTickerBar() {
  const { data: us } = useSWR<UsIndices>("us-indices", () => api.us.indices() as Promise<UsIndices>, { refreshInterval: 60000 });
  const { data: kr } = useSWR<KrIndices>("kr-indices", () => api.kr.indices() as Promise<KrIndices>, { refreshInterval: 60000 });

  return (
    <div
      style={{
        background:    "var(--color-surface)",
        borderBottom:  "1px solid var(--color-border)",
        padding:       "5px 5%",
        overflowX:     "auto",
      }}
    >
      <div
        className="animate-marquee"
        style={{
          display:    "flex",
          alignItems: "center",
          gap:        "2rem",
          minWidth:   "100%",
        }}
      >
        {/* 국내 지수 */}
        {kr?.KOSPI  && <Idx name="KOSPI"  price={kr.KOSPI.index}  changePct={kr.KOSPI.change_pct} />}
        {kr?.KOSDAQ && <Idx name="KOSDAQ" price={kr.KOSDAQ.index} changePct={kr.KOSDAQ.change_pct} />}

        <span style={{ color: "var(--color-border)", fontSize: "0.75rem" }}>│</span>

        {/* 미국 지수 */}
        {us?.["S&P 500"] && <Idx name="S&P500" price={us["S&P 500"].price} changePct={us["S&P 500"].change_pct} />}
        {us?.NASDAQ      && <Idx name="NASDAQ"  price={us.NASDAQ.price}     changePct={us.NASDAQ.change_pct} />}
        {us?.DOW         && <Idx name="DOW"     price={us.DOW.price}        changePct={us.DOW.change_pct} />}
        
        <span style={{ color: "var(--color-border)", fontSize: "0.75rem" }}>│</span>
        
        {/* 기타 매크로 지표 */}
        {us?.VIX         && <Idx name="VIX"     price={us.VIX.price}        changePct={us.VIX.change_pct} />}
        <Idx name="BTC/USD" price={98500} changePct={1.25} />
        <Idx name="USD/KRW" price={1412.50} changePct={-0.45} />
      </div>
    </div>
  );
}
