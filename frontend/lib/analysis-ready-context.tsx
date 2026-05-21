"use client";
import { createContext, useContext, useState, useCallback } from "react";
import type { ReactNode } from "react";

type PageKey = "picks" | "scenarios";

interface AnalysisReadyCtx {
  ready: Record<PageKey, boolean>;
  setReady: (page: PageKey, val: boolean) => void;
}

const AnalysisReadyContext = createContext<AnalysisReadyCtx>({
  ready: { picks: false, scenarios: false },
  setReady: () => {},
});

export function AnalysisReadyProvider({ children }: { children: ReactNode }) {
  const [ready, setReadyState] = useState<Record<PageKey, boolean>>({ picks: false, scenarios: false });
  const setReady = useCallback((page: PageKey, val: boolean) => {
    setReadyState(prev => ({ ...prev, [page]: val }));
  }, []);
  return (
    <AnalysisReadyContext.Provider value={{ ready, setReady }}>
      {children}
    </AnalysisReadyContext.Provider>
  );
}

export function useAnalysisReady() {
  return useContext(AnalysisReadyContext);
}
