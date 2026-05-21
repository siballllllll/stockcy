"use client";
import { useState, useCallback, useRef } from "react";
import { connectSSE } from "@/lib/api";
import type { SseStatus } from "@/lib/types";

interface SseState<T> {
  status:     SseStatus;
  message:    string;
  result:     T | null;
  fromCache:  boolean;
}

/**
 * SSE 스트림 훅
 * @example
 *   const { status, result, message, start } = useSSE<DailyBriefing>("/api/ai/daily-briefing");
 *   <button onClick={start}>분석 시작</button>
 *   {status === "running" && <Spinner text={message} />}
 *   {status === "done" && <Result data={result} />}
 */
export function useSSE<T>(
  path: string,
  options?: { method?: "GET" | "POST"; body?: object }
) {
  const [state, setState] = useState<SseState<T>>({
    status:    "idle",
    message:   "",
    result:    null,
    fromCache: false,
  });

  const abortRef = useRef<AbortController | null>(null);

  const start = useCallback(async (runtimeBody?: object) => {
    // 이전 요청 취소
    abortRef.current?.abort();
    abortRef.current = new AbortController();

    setState({ status: "running", message: "분석 시작 중...", result: null, fromCache: false });

    try {
      await connectSSE<T>(
        path,
        (evt) => {
          if (evt.status === "running") {
            setState((s) => ({ ...s, status: "running", message: evt.message ?? "처리 중..." }));
          } else if (evt.status === "done") {
            setState({
              status:    "done",
              message:   "",
              result:    (evt.result as T) ?? null,
              fromCache: evt.from_cache ?? false,
            });
          } else if (evt.status === "error") {
            setState({ status: "error", message: evt.message ?? "오류 발생", result: null, fromCache: false });
          }
        },
        { method: options?.method, body: runtimeBody ?? options?.body }
      );
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        setState({ status: "error", message: String(err), result: null, fromCache: false });
      }
    }
  }, [path, options]);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    setState({ status: "idle", message: "", result: null, fromCache: false });
  }, []);

  return { ...state, start, reset };
}
