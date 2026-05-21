"use client";
import { ReactNode } from "react";
import { LoadingSpinner } from "./LoadingSpinner";
import { StatusBox } from "./StatusBox";
import type { SseStatus } from "@/lib/types";

interface SSEPanelProps<T> {
  status:     SseStatus;
  message?:   string;
  result:     T | null;
  fromCache?: boolean;
  onStart:    () => void;
  startLabel?: string;
  startIcon?:  ReactNode;
  children:   (result: T) => ReactNode;   // 결과 렌더러
  idleHint?:  string;
  disabled?:  boolean;
}

/**
 * SSE 스트리밍 UI 래퍼 컴포넌트.
 * idle → 버튼 표시
 * running → 스피너 + 진행 메시지
 * done → children(result) 렌더링
 * error → 에러 박스
 */
export function SSEPanel<T>({
  status, message, result, fromCache,
  onStart, startLabel = "AI 분석 시작", startIcon,
  children, idleHint, disabled = false,
}: SSEPanelProps<T>) {
  return (
    <div>
      {/* 버튼 영역 */}
      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "1rem" }}>
        <button
          className="stockcy-btn stockcy-btn-primary"
          onClick={onStart}
          disabled={disabled || status === "running"}
        >
          {startIcon}
          {status === "running" ? "분석 중..." : startLabel}
        </button>
        {fromCache && (
          <span style={{ fontSize: "0.75rem", color: "var(--color-muted)" }}>
            ⚡ 캐시 결과
          </span>
        )}
      </div>

      {/* 상태별 렌더링 */}
      {status === "idle" && idleHint && (
        <StatusBox type="info">{idleHint}</StatusBox>
      )}

      {status === "running" && (
        <div style={{ padding: "1.5rem 0" }}>
          <LoadingSpinner text={message ?? "AI 분석 중..."} />
        </div>
      )}

      {status === "error" && (
        <StatusBox type="danger">{message ?? "오류가 발생했습니다."}</StatusBox>
      )}

      {status === "done" && result !== null && children(result)}
    </div>
  );
}
