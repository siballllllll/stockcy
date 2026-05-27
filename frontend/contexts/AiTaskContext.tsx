"use client";

import React, { createContext, useContext, useState, useCallback, useRef, useEffect, ReactNode } from "react";
import { connectSSE } from "@/lib/api";
import type { SseStatus } from "@/lib/types";

export interface AiTask {
  id:          string;
  title:       string;
  status:      SseStatus;
  message:     string;
  result:      any | null;
  fromCache:   boolean;
  timestamp:   number;   // 시작 시각
  completedAt?: number;  // 완료 시각 (localStorage 복원 포함)
}

interface AiTaskContextType {
  tasks:     Record<string, AiTask>;
  startTask: (id: string, title: string, path: string, options?: { method?: "GET" | "POST"; body?: any }) => void;
  clearTask: (id: string) => void;
  getTask:   (id: string) => AiTask | undefined;
}

export const AiTaskContext = createContext<AiTaskContextType | null>(null);

// ── localStorage 헬퍼 ──────────────────────────────────────────────────────────
const STORAGE_KEY = "stockcy_ai_results";

function loadFromStorage(): Record<string, AiTask> {
  if (typeof window === "undefined") return {};
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as Record<string, AiTask>;
    const out: Record<string, AiTask> = {};
    for (const [id, task] of Object.entries(parsed)) {
      if (task.status === "done") out[id] = task;
    }
    return out;
  } catch {
    return {};
  }
}

function saveToStorage(tasks: Record<string, AiTask>) {
  if (typeof window === "undefined") return;
  try {
    const toSave: Record<string, AiTask> = {};
    for (const [id, task] of Object.entries(tasks)) {
      if (task.status === "done") toSave[id] = task;
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(toSave));
  } catch {}
}

// ── Provider ───────────────────────────────────────────────────────────────────
export function AiTaskProvider({ children }: { children: ReactNode }) {
  const [tasks, setTasks] = useState<Record<string, AiTask>>(() => loadFromStorage());
  const abortControllers = useRef<Record<string, AbortController>>({});

  // tasks 변경 시 done 항목만 localStorage에 저장
  useEffect(() => {
    saveToStorage(tasks);
  }, [tasks]);

  const startTask = useCallback((
    id: string, title: string, path: string,
    options?: { method?: "GET" | "POST"; body?: any }
  ) => {
    if (abortControllers.current[id]) {
      abortControllers.current[id].abort();
    }
    const abortController = new AbortController();
    abortControllers.current[id] = abortController;

    setTasks(prev => ({
      ...prev,
      [id]: { id, title, status: "running", message: "분석 시작 중...", result: null, fromCache: false, timestamp: Date.now() },
    }));

    connectSSE<any>(
      path,
      (evt) => {
        setTasks(prev => {
          const current = prev[id];
          if (!current) return prev;
          if (evt.status === "running") {
            return { ...prev, [id]: { ...current, status: "running", message: evt.message ?? "처리 중..." } };
          } else if (evt.status === "done") {
            return { ...prev, [id]: { ...current, status: "done", message: "", result: evt.result, fromCache: evt.from_cache ?? false, completedAt: Date.now() } };
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
      const { [id]: _, ...rest } = prev;
      return rest;
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
