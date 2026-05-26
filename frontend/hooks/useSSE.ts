"use client";
import { useState, useCallback, useRef, useContext, useEffect } from "react";
import { connectSSE } from "@/lib/api";
import type { SseStatus } from "@/lib/types";
import { AiTaskContext } from "@/contexts/AiTaskContext";

interface SseState<T> {
  status:     SseStatus;
  message:    string;
  result:     T | null;
  fromCache:  boolean;
}

export function useSSE<T>(
  path: string,
  options?: { method?: "GET" | "POST"; body?: object; globalId?: string; globalTitle?: string }
) {
  // 1. Local State
  const [localState, setLocalState] = useState<SseState<T>>({
    status:    "idle",
    message:   "",
    result:    null,
    fromCache: false,
  });

  const abortRef = useRef<AbortController | null>(null);

  // 2. Global Context
  const aiCtx = useContext(AiTaskContext);

  const startLocal = useCallback(async (runtimeBody?: object) => {
    abortRef.current?.abort();
    abortRef.current = new AbortController();

    setLocalState({ status: "running", message: "분석 시작 중...", result: null, fromCache: false });

    try {
      await connectSSE<T>(
        path,
        (evt) => {
          if (evt.status === "running") {
            setLocalState((s) => ({ ...s, status: "running", message: evt.message ?? "처리 중..." }));
          } else if (evt.status === "done") {
            setLocalState({
              status:    "done",
              message:   "",
              result:    (evt.result as T) ?? null,
              fromCache: evt.from_cache ?? false,
            });
          } else if (evt.status === "error") {
            setLocalState({ status: "error", message: evt.message ?? "오류 발생", result: null, fromCache: false });
          }
        },
        { method: options?.method, body: runtimeBody ?? options?.body, signal: abortRef.current.signal }
      );
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        setLocalState({ status: "error", message: String(err), result: null, fromCache: false });
      }
    }
  }, [path, options]);

  const resetLocal = useCallback(() => {
    abortRef.current?.abort();
    setLocalState({ status: "idle", message: "", result: null, fromCache: false });
  }, []);

  // 3. Delegate to Global or Local
  if (options?.globalId && aiCtx) {
    const task = aiCtx.getTask(options.globalId);
    return {
      status: task?.status || "idle",
      message: task?.message || "",
      result: (task?.result as T) || null,
      fromCache: task?.fromCache || false,
      start: (runtimeBody?: object) => {
        aiCtx.startTask(options.globalId!, options.globalTitle || "AI 분석", path, {
          method: options.method,
          body: runtimeBody ?? options.body
        });
      },
      reset: () => aiCtx.clearTask(options.globalId!),
    };
  }

  return { ...localState, start: startLocal, reset: resetLocal };
}
