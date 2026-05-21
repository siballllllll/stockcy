"use client";
import { createContext, useContext, useState, type ReactNode } from "react";

export type Market = "KR" | "US";

const MarketContext = createContext<{
  market: Market;
  setMarket: (m: Market) => void;
}>({ market: "KR", setMarket: () => {} });

export function MarketProvider({ children }: { children: ReactNode }) {
  const [market, setMarket] = useState<Market>("KR");
  return (
    <MarketContext.Provider value={{ market, setMarket }}>
      {children}
    </MarketContext.Provider>
  );
}

export function useMarket() {
  return useContext(MarketContext);
}
