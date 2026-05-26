"use client";
import { useRef, useEffect } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import type { UsIndices, KrIndices, Favorite } from "@/lib/types";
import { useRouter } from "next/navigation";
import { useMarket } from "@/lib/market-context";

const PX_PER_SEC = 80;

// 국내 대표 종목 (코드 순)
const KR_REPS = ["005930","000660","005380","035420","051910","005490","000270","035720","096770","028260","012330","068270","247540","373220"];
// 미국 대표 종목
const US_REPS = ["AAPL","MSFT","NVDA","AMZN","GOOGL","META","TSLA","AVGO","JPM","V","UNH","LLY","XOM","WMT","COST"];

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
  const up    = changePct > 0;
  const down  = changePct < 0;
  const color = up ? "var(--color-up)" : down ? "var(--color-down)" : "var(--color-flat)";
  const sign  = up ? "+" : "";
  return (
    <button
      onClick={() => router.push(`/search?market=KR&q=${code}`)}
      style={{ display: "inline-flex", alignItems: "baseline", gap: "0.3rem", flexShrink: 0, background: "none", border: "none", cursor: "pointer", padding: 0 }}
    >
      <span style={{ color: "var(--color-muted)", fontSize: "0.72rem" }}>{name}</span>
      <span style={{ fontWeight: 600, fontSize: "0.82rem", color: "var(--color-text)" }}>₩{price.toLocaleString()}</span>
      <span style={{ color, fontSize: "0.72rem" }}>{sign}{changePct.toFixed(2)}%</span>
    </button>
  );
}

const DOT = <span style={{ color: "rgba(255,255,255,0.25)", fontSize: "0.75rem", flexShrink: 0 }}>│</span>;
const SEP = <span style={{ color: "var(--color-border)", fontSize: "0.75rem", flexShrink: 0 }}>│</span>;

function TickerRow({ children }: { children: React.ReactNode }) {
  const trackRef  = useRef<HTMLDivElement>(null);
  const firstRef  = useRef<HTMLSpanElement>(null);
  const pausedRef = useRef(false);
  const posRef    = useRef(0);

  useEffect(() => {
    let rafId: number;
    const STEP = PX_PER_SEC / 60; // px per frame at 60fps

    const tick = () => {
      rafId = requestAnimationFrame(tick);
      if (pausedRef.current) return;
      const track = trackRef.current;
      const first = firstRef.current;
      if (!track || !first) return;
      const w = first.scrollWidth;
      if (w < 10) return; // 콘텐츠 아직 없음
      posRef.current -= STEP;
      if (posRef.current <= -w) posRef.current += w; // seamless wrap
      track.style.transform = `translateX(${posRef.current}px)`;
    };

    rafId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafId);
  }, []);

  return (
    <div style={{ overflow: "hidden", padding: "4px 0" }}>
      <div
        ref={trackRef}
        style={{ display: "inline-flex", alignItems: "center", whiteSpace: "nowrap" }}
        onMouseEnter={() => { pausedRef.current = true; }}
        onMouseLeave={() => { pausedRef.current = false; }}
      >
        <span ref={firstRef} style={{ display: "inline-flex", alignItems: "center", gap: "1.5rem", paddingRight: "5rem" }}>
          {children}
        </span>
        <span aria-hidden style={{ display: "inline-flex", alignItems: "center", gap: "1.5rem", paddingRight: "5rem" }}>
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
  const { data: krReps }  = useSWR("kr-rep-stocks",            () => api.kr.stocksBulk(KR_REPS)          as Promise<Record<string, any>>, { refreshInterval: 60000,  revalidateOnFocus: false });
  const { data: usReps }  = useSWR("us-rep-stocks",            () => api.us.stocks(US_REPS)               as Promise<any[]>, { refreshInterval: 60000,  revalidateOnFocus: false });
  const { data: favList } = useSWR("favorites",                () => api.portfolio.loadFavorites(),        { refreshInterval: 300000, revalidateOnFocus: false });

  const krFavCodes = (favList ?? []).filter((f: Favorite) => f["시장"] === "국내").map((f: Favorite) => f["티커"]);
  const usFavTickers = (favList ?? []).filter((f: Favorite) => f["시장"] === "미국").map((f: Favorite) => f["티커"]);

  const { data: krFavPrices } = useSWR(
    krFavCodes.length > 0 ? ["kr-fav-prices", krFavCodes.join(",")] : null,
    () => api.kr.stocksBulk(krFavCodes) as Promise<Record<string, any>>,
    { refreshInterval: 60000, revalidateOnFocus: false }
  );
  const { data: usFavPrices } = useSWR(
    usFavTickers.length > 0 ? ["us-fav-prices", usFavTickers.join(",")] : null,
    () => api.us.stocks(usFavTickers) as Promise<any[]>,
    { refreshInterval: 60000, revalidateOnFocus: false }
  );

  const topGainers = Array.isArray(gainers)
    ? gainers.slice(0, 8).map((g: any) => ({
        name: g.name ?? g.종목명, code: g.code ?? g.종목코드,
        change_pct: g.change_pct ?? g["등락률(%)"] ?? 0, price: g.price ?? g.현재가 ?? 0,
      }))
    : [];

  // 즐겨찾기 KR — bulk 응답은 { [code]: { name, price, change_pct, ... } } 형태
  const krFavItems = krFavCodes
    .map(code => {
      const d = (krFavPrices as any)?.[code];
      if (!d) return null;
      const fav = (favList ?? []).find((f: Favorite) => f["티커"] === code);
      return {
        code,
        name: d.name ?? d["종목명"] ?? fav?.["종목명"] ?? code,
        price: d.price ?? d["현재가"] ?? 0,
        change_pct: d.change_pct ?? d["등락률(%)"] ?? 0,
      };
    })
    .filter(Boolean) as { code: string; name: string; price: number; change_pct: number }[];

  // 즐겨찾기 US — /api/us/stocks 응답은 [{ 심볼, 현재가($), 등락률(%) }] 형태
  const usFavItems = usFavTickers
    .map(ticker => {
      const d = Array.isArray(usFavPrices)
        ? usFavPrices.find((r: any) => (r["심볼"] ?? r.ticker ?? "").toUpperCase() === ticker.toUpperCase())
        : null;
      const fav = (favList ?? []).find((f: Favorite) => f["티커"] === ticker);
      return {
        ticker,
        name: fav?.["종목명"] ?? ticker,
        price: d?.["현재가($)"] ?? d?.price ?? 0,
        change_pct: d?.["등락률(%)"] ?? d?.change_pct ?? 0,
      };
    });

  return (
    <div style={{ background: "var(--color-surface)", borderBottom: "1px solid var(--color-border)" }}>
      {/* 윗줄: 시장 탭에 따라 국내/미국 지수 + 대표 종목 */}
      <div style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
        <TickerRow>
          {market === "KR" ? (
            <>
              {kr?.KOSPI  && <IdxItem name="KOSPI"  price={kr.KOSPI.index}  changePct={kr.KOSPI.change_pct} />}
              {DOT}
              {kr?.KOSDAQ && <IdxItem name="KOSDAQ" price={kr.KOSDAQ.index} changePct={kr.KOSDAQ.change_pct} />}
              {krReps && Object.keys(krReps).length > 0 && (
                <>
                  {SEP}
                  {KR_REPS.map((code, i) => {
                    const d = (krReps as any)[code];
                    if (!d) return null;
                    const price = d.price ?? d["현재가"] ?? 0;
                    const chg   = d.change_pct ?? d["등락률(%)"] ?? 0;
                    const name  = d.name ?? d["종목명"] ?? code;
                    return (
                      <span key={code} style={{ display: "inline-flex", alignItems: "center", gap: "1.5rem" }}>
                        <StockItem name={name} code={code} changePct={chg} price={price} />
                        {i < KR_REPS.length - 1 && DOT}
                      </span>
                    );
                  })}
                </>
              )}
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
              {Array.isArray(usReps) && usReps.length > 0 && (
                <>
                  {SEP}
                  {usReps.map((d: any, i: number) => {
                    const ticker = d["심볼"] ?? d.ticker ?? "";
                    const price  = d["현재가($)"] ?? d.price ?? 0;
                    const chg    = d["등락률(%)"] ?? d.change_pct ?? 0;
                    return (
                      <span key={ticker} style={{ display: "inline-flex", alignItems: "center", gap: "1.5rem" }}>
                        <IdxItem name={ticker} price={price} changePct={chg} />
                        {i < usReps.length - 1 && DOT}
                      </span>
                    );
                  })}
                </>
              )}
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

        {(krFavItems.length > 0 || usFavItems.length > 0) && (
          <>
            {SEP}
            <span style={{ color: "var(--color-accent)", fontSize: "0.7rem", fontWeight: 700, flexShrink: 0 }}>⭐ 즐겨찾기</span>
            {krFavItems.map((f, i) => (
              <span key={f.code} style={{ display: "inline-flex", alignItems: "center", gap: "1.5rem" }}>
                <StockItem name={f.name} code={f.code} changePct={f.change_pct} price={f.price} />
                {(i < krFavItems.length - 1 || usFavItems.length > 0) && DOT}
              </span>
            ))}
            {usFavItems.map((f, i) => (
              <span key={f.ticker} style={{ display: "inline-flex", alignItems: "center", gap: "1.5rem" }}>
                <IdxItem name={f.name} price={f.price} changePct={f.change_pct} />
                {i < usFavItems.length - 1 && DOT}
              </span>
            ))}
          </>
        )}
      </TickerRow>
    </div>
  );
}
