"use client";

import React, { createContext, useContext, useState, useCallback, useRef, ReactNode } from "react";
import { connectSSE } from "@/lib/api";
import type { SseStatus } from "@/lib/types";

export interface AiTask {
  id: string;
  title: string;       // UI에 표시될 이름 (예: "NVDA 매수타점 추천")
  status: SseStatus;
  message: string;
  result: any | null;
  fromCache: boolean;
  timestamp: number;
}

interface AiTaskContextType {
  tasks: Record<string, AiTask>;
  startTask: (id: string, title: string, path: string, options?: { method?: "GET" | "POST"; body?: any }) => void;
  clearTask: (id: string) => void;
  getTask: (id: string) => AiTask | undefined;
}

export const AiTaskContext = createContext<AiTaskContextType | null>(null);

export function AiTaskProvider({ children }: { children: ReactNode }) {
  const [tasks, setTasks] = useState<Record<string, AiTask>>({});
  const abortControllers = useRef<Record<string, AbortController>>({});

  const startTask = useCallback((id: string, title: string, path: string, options?: { method?: "GET" | "POST"; body?: any }) => {
    // 이미 실행 중이면 취소
    if (abortControllers.current[id]) {
      abortControllers.current[id].abort();
    }
    
    const abortController = new AbortController();
    abortControllers.current[id] = abortController;

    setTasks(prev => ({
      ...prev,
      [id]: {
        id, title, status: "running", message: "분석 시작 중...", result: null, fromCache: false, timestamp: Date.now()
      }
    }));

    connectSSE<any>(
      path,
      (evt) => {
        setTasks(prev => {
          const current = prev[id];
          if (!current) return prev; // 삭제된 경우

          if (evt.status === "running") {
            return { ...prev, [id]: { ...current, status: "running", message: evt.message ?? "처리 중..." } };
          } else if (evt.status === "done") {
            // 완료 시
            return { ...prev, [id]: { ...current, status: "done", message: "", result: evt.result, fromCache: evt.from_cache ?? false } };
          } else if (evt.status === "error") {
            return { ...prev, [id]: { ...current, status: "error", message: evt.message ?? "오류 발생" } };
          }
          return prev;
        });
      },
      { method: options?.method, body: options?.body, signal: abortController.signal }
    ).catch(err => {
      if (err.name !== "AbortError") {
        setTasks(prev => {
          const current = prev[id];
          if (!current) return prev;
          return { ...prev, [id]: { ...current, status: "error", message: String(err) } };
        });
      }
    });
  }, []);

  const clearTask = useCallback((id: string) => {
    if (abortControllers.current[id]) {
      abortControllers.current[id].abort();
      delete abortControllers.current[id];
    }
    setTasks(prev => {
      const newTasks = { ...prev };
      delete newTasks[id];
      return newTasks;
    });
  }, []);

  const getTask = useCallback((id: string) => tasks[id], [tasks]);

  return (
    <AiTaskContext.Provider value={{ tasks, startTask, clearTask, getTask }}>
      {children}
    </AiTaskContext.Provider>
  );
}

export function useAiTask() {
  const ctx = useContext(AiTaskContext);
  if (!ctx) throw new Error("useAiTask must be used within AiTaskProvider");
  return ctx;
}
