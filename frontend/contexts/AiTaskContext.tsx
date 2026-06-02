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
  route?:      string;   // 알림 클릭 시 이동할 경로 (외부 등록 알림용)
  read?:       boolean;  // 사용자가 클릭하여 확인한 알림 여부
}

interface AiTaskContextType {
  tasks:     Record<string, AiTask>;
  startTask: (id: string, title: string, path: string, options?: { method?: "GET" | "POST"; body?: any }) => void;
  clearTask: (id: string) => void;
  getTask:   (id: string) => AiTask | undefined;
  notifyDone: (id: string, title: string, route: string) => void;  // 외부 분석 완료 알림 직접 등록
  markRead:  (id: string) => void;  // 알림 읽음 처리
}

export const AiTaskContext = createContext<AiTaskContextType | null>(null);

// ── localStorage 헬퍼 ──────────────────────────────────────────────────────────
const STORAGE_KEY = "stockcy_ai_results";
const MAX_AGE_MS = 3 * 24 * 60 * 60 * 1000;  // 알림 보관 기간: 3일 (이후 자동 삭제)

function loadFromStorage(): Record<string, AiTask> {
  if (typeof window === "undefined") return {};
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as Record<string, AiTask>;
    const out: Record<string, AiTask> = {};
    const cutoff = Date.now() - MAX_AGE_MS;
    for (const [id, task] of Object.entries(parsed)) {
      if (task.status === "done" && (task.completedAt ?? task.timestamp) >= cutoff) out[id] = task;
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
    const cutoff = Date.now() - MAX_AGE_MS;
    for (const [id, task] of Object.entries(tasks)) {
      if (task.status === "done" && (task.completedAt ?? task.timestamp) >= cutoff) toSave[id] = task;
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

  // 3일 지난 알림 주기적 정리 (1시간마다, 마운트 직후 1회)
  useEffect(() => {
    const prune = () => {
      const cutoff = Date.now() - MAX_AGE_MS;
      setTasks(prev => {
        const next: Record<string, AiTask> = {};
        let changed = false;
        for (const [id, t] of Object.entries(prev)) {
          if ((t.completedAt ?? t.timestamp) >= cutoff) next[id] = t;
          else changed = true;
        }
        return changed ? next : prev;
      });
    };
    prune();
    const iv = setInterval(prune, 60 * 60 * 1000);
    return () => clearInterval(iv);
  }, []);

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

  // 외부(페이지)에서 분석 완료 시 알림만 직접 등록 (분석은 페이지가 자체 실행)
  // 멱등: 같은 id가 이미 있으면 덮어쓰지 않는다 → 서버 이벤트 폴링 시 읽음 상태가
  // 매 폴링마다 다시 '안읽음'으로 초기화되는 것을 막는다. (수동 재생성은 고유 id 사용)
  const notifyDone = useCallback((id: string, title: string, route: string) => {
    setTasks(prev => {
      if (prev[id]) return prev;
      return {
        ...prev,
        [id]: { id, title, status: "done", message: "", result: null, fromCache: false, timestamp: Date.now(), completedAt: Date.now(), route, read: false },
      };
    });
  }, []);

  // 알림 클릭 시 읽음 처리 (배지에서 제외, UI에서 어둡게 표시)
  const markRead = useCallback((id: string) => {
    setTasks(prev => {
      const t = prev[id];
      if (!t || t.read) return prev;
      return { ...prev, [id]: { ...t, read: true } };
    });
  }, []);

  return (
    <AiTaskContext.Provider value={{ tasks, startTask, clearTask, getTask, notifyDone, markRead }}>
      {children}
    </AiTaskContext.Provider>
  );
}

export function useAiTask() {
  const ctx = useContext(AiTaskContext);
  if (!ctx) throw new Error("useAiTask must be used within AiTaskProvider");
  return ctx;
}
