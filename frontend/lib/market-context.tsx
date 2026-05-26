"use client";
import { createContext, useContext, useState, useMemo, type ReactNode } from "react";

export type Market = "KR" | "US";

const MarketContext = createContext<{
  market: Market;
  setMarket: (m: Market) => void;
}>({ market: "KR", setMarket: () => {} });

export function MarketProvider({ children }: { children: ReactNode }) {
  const [market, setMarket] = useState<Market>("KR");
  const value = useMemo(() => ({ market, setMarket }), [market]);
  return (
    <MarketContext.Provider value={value}>
      {children}
    </MarketContext.Provider>
  );
}

export function useMarket() {
  return useContext(MarketContext);
}
