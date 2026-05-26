"use client";
import { useRef, useEffect, useState } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import type { UsIndices, KrIndices } from "@/lib/types";
import { useRouter } from "next/navigation";
import { useMarket } from "@/lib/market-context";

const PX_PER_SEC = 80; // 픽셀/초 — 이 값으로 속도 고정

function IdxItem({ name, price, changePct }: { name: string; price: number; changePct: number }) {
  if (!price) return null;
  const up    = changePct > 0;
  const down  = changePct < 0;
  const color = up ? "var(--color-up)" : down ? "var(--color-down)" : "var(--color-flat)";
  const sign  = up ? "+" : "";
  return (
    <span style={{ display: "inline-flex", alignItems: "baseline", gap: "0.3rem", flexShrink: 0 }}>
      <span style={{ color: "var(--color-muted)", fontSize: "0.72rem" }}>{name}</span>
      <span style={{ fontWeight: 600, fontSize: "0.82rem" }}>
        {price >= 10000 ? price.toLocaleString() : price.toFixed(2)}
      </span>
      <span style={{ color, fontSize: "0.72rem" }}>{sign}{changePct.toFixed(2)}%</span>
    </span>
  );
}

function StockItem({ name, code, changePct, price }: { name: string; code: string; changePct: number; price: number }) {
  const router = useRouter();
  const up   = changePct > 0;
  const down = changePct < 0;
  const color = up ? "var(--color-up)" : down ? "var(--color-down)" : "var(--color-flat)";
  const sign  = up ? "+" : "";
  return (
    <button
      onClick={() => router.push(`/search?market=KR&q=${code}`)}
      style={{
        display: "inline-flex", alignItems: "baseline", gap: "0.3rem", flexShrink: 0,
        background: "none", border: "none", cursor: "pointer", padding: 0,
      }}
    >
      <span style={{ color: "var(--color-muted)", fontSize: "0.72rem" }}>{name}</span>
      <span style={{ fontWeight: 600, fontSize: "0.82rem", color: "var(--color-text)" }}>
        ₩{price.toLocaleString()}
      </span>
      <span style={{ color, fontSize: "0.72rem" }}>{sign}{changePct.toFixed(2)}%</span>
    </button>
  );
}

const DOT = <span style={{ color: "rgba(255,255,255,0.15)", fontSize: "0.75rem", flexShrink: 0 }}>●</span>;
const SEP = <span style={{ color: "var(--color-border)", fontSize: "0.75rem", flexShrink: 0 }}>│</span>;

function TickerRow({ children }: { children: React.ReactNode }) {
  const firstRef = useRef<HTMLSpanElement>(null);
  const [duration, setDuration] = useState(30);

  useEffect(() => {
    const el = firstRef.current;
    if (!el) return;
    const measure = () => {
      const w = el.offsetWidth;
      if (w > 0) setDuration(Math.round(w / PX_PER_SEC));
    };
    measure();
    const obs = new ResizeObserver(measure);
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  return (
    <div style={{ overflow: "hidden", padding: "4px 0" }}>
      <div
        style={{
          display: "inline-flex",
          alignItems: "center",
          whiteSpace: "nowrap",
          animation: `marquee-seamless ${duration}s linear infinite`,
        }}
        onMouseEnter={e => (e.currentTarget.style.animationPlayState = "paused")}
        onMouseLeave={e => (e.currentTarget.style.animationPlayState = "running")}
      >
        <span ref={firstRef} style={{ display: "inline-flex", alignItems: "center", gap: "1.5rem", paddingRight: "3rem" }}>
          {children}
        </span>
        <span style={{ display: "inline-flex", alignItems: "center", gap: "1.5rem", paddingRight: "3rem" }}>
          {children}
        </span>
      </div>
    </div>
  );
}

export function MarketTickerBar() {
  const { market } = useMarket();

  const { data: us }      = useSWR<UsIndices>("us-indices",    () => api.us.indices()       as Promise<UsIndices>, { refreshInterval: 60000,  revalidateOnFocus: false });
  const { data: kr }      = useSWR<KrIndices>("kr-indices",    () => api.kr.indices()       as Promise<KrIndices>, { refreshInterval: 60000,  revalidateOnFocus: false });
  const { data: btc }     = useSWR("btc-price",                () => api.us.crypto("BTC"),                         { refreshInterval: 120000, revalidateOnFocus: false });
  const { data: fx }      = useSWR("usd-krw-rate",             () => api.us.exchangeRate(),                        { refreshInterval: 300000, revalidateOnFocus: false });
  const { data: gainers } = useSWR("kr-top-gainers",           () => api.kr.changeRanking("KOSPI", "up") as Promise<any[]>, { refreshInterval: 300000, revalidateOnFocus: false });
  const { data: volumes } = useSWR("kr-top-volumes",           () => api.kr.volumeRanking("ALL")         as Promise<any[]>, { refreshInterval: 300000, revalidateOnFocus: false });

  const topGainers: Array<{ name: string; code: string; change_pct: number; price: number }> =
    Array.isArray(gainers)
      ? gainers.slice(0, 8).map((g: any) => ({
          name: g.name ?? g.종목명,
          code: g.code ?? g.종목코드,
          change_pct: g.change_pct ?? g["등락률(%)"] ?? 0,
          price: g.price ?? g.현재가 ?? 0,
        }))
      : [];

  const topVolumes: Array<{ name: string; code: string; change_pct: number; price: number }> =
    Array.isArray(volumes)
      ? volumes.slice(0, 8).map((v: any) => ({
          name: v.name ?? v.종목명,
          code: v.code ?? v.종목코드,
          change_pct: v.change_pct ?? v["등락률(%)"] ?? 0,
          price: v.price ?? v.현재가 ?? 0,
        }))
      : [];

  return (
    <div style={{
      background: "var(--color-surface)",
      borderBottom: "1px solid var(--color-border)",
    }}>
      {/* 윗줄: 시장 탭에 따라 국내/미국 지수 */}
      <div style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
        <TickerRow>
          {market === "KR" ? (
            <>
              {kr?.KOSPI  && <IdxItem name="KOSPI"  price={kr.KOSPI.index}  changePct={kr.KOSPI.change_pct} />}
              {DOT}
              {kr?.KOSDAQ && <IdxItem name="KOSDAQ" price={kr.KOSDAQ.index} changePct={kr.KOSDAQ.change_pct} />}
            </>
          ) : (
            <>
              {us?.["S&P 500"] && <IdxItem name="S&P500" price={us["S&P 500"].price} changePct={us["S&P 500"].change_pct} />}
              {DOT}
              {us?.NASDAQ      && <IdxItem name="NASDAQ"  price={us.NASDAQ.price}     changePct={us.NASDAQ.change_pct} />}
              {DOT}
              {us?.DOW         && <IdxItem name="DOW"     price={us.DOW.price}        changePct={us.DOW.change_pct} />}
              {DOT}
              {us?.VIX         && <IdxItem name="VIX"     price={us.VIX.price}        changePct={us.VIX.change_pct} />}
            </>
          )}
        </TickerRow>
      </div>

      {/* 아랫줄: BTC/환율 + 급등 + 거래대금 */}
      <TickerRow>
        {btc && !btc.error && <IdxItem name="BTC/USD" price={btc.price} changePct={btc.change_pct} />}
        {fx && fx.rate > 0 && <>{DOT}<IdxItem name="USD/KRW" price={fx.rate} changePct={0} /></>}

        {topGainers.length > 0 && (
          <>
            {SEP}
            <span style={{ color: "var(--color-warning)", fontSize: "0.7rem", fontWeight: 700, flexShrink: 0 }}>🔥 급등</span>
            {topGainers.map((g, i) => (
              <span key={i} style={{ display: "inline-flex", alignItems: "center", gap: "1.5rem" }}>
                <StockItem name={g.name} code={g.code} changePct={g.change_pct} price={g.price} />
                {i < topGainers.length - 1 && DOT}
              </span>
            ))}
          </>
        )}

        {topVolumes.length > 0 && (
          <>
            {SEP}
            <span style={{ color: "var(--color-primary)", fontSize: "0.7rem", fontWeight: 700, flexShrink: 0 }}>💰 거래대금</span>
            {topVolumes.map((v, i) => (
              <span key={i} style={{ display: "inline-flex", alignItems: "center", gap: "1.5rem" }}>
                <StockItem name={v.name} code={v.code} changePct={v.change_pct} price={v.price} />
                {i < topVolumes.length - 1 && DOT}
              </span>
            ))}
          </>
        )}
      </TickerRow>
    </div>
  );
}
