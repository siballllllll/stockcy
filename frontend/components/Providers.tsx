"use client";
import { MarketProvider } from "@/lib/market-context";
import type { ReactNode } from "react";

export function Providers({ children }: { children: ReactNode }) {
  return <MarketProvider>{children}</MarketProvider>;
}
