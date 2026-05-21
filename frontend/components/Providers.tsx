"use client";
import { MarketProvider } from "@/lib/market-context";
import { AnalysisReadyProvider } from "@/lib/analysis-ready-context";
import type { ReactNode } from "react";

export function Providers({ children }: { children: ReactNode }) {
  return (
    <AnalysisReadyProvider>
      <MarketProvider>{children}</MarketProvider>
    </AnalysisReadyProvider>
  );
}
