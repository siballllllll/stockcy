import React from "react";

/**
 * AI(Google AI Studio / Gemini) API를 호출하는 기능 옆에 붙이는 '비용 발생 가능' 배지.
 * 수급·섹터처럼 AI를 안 쓰는 데이터 기능과 시각적으로 구분하기 위함.
 */
export function AiCostBadge({ label = "AI 비용", small = false }: { label?: string; small?: boolean }) {
  return (
    <span
      title="Google AI Studio(Gemini) API 호출 — 사용량에 따라 비용이 발생할 수 있습니다"
      style={{
        fontSize: small ? "0.55rem" : "0.6rem",
        padding: small ? "0 4px" : "1px 5px",
        borderRadius: "4px",
        background: "rgba(251,191,36,0.12)",
        border: "1px solid rgba(251,191,36,0.35)",
        color: "#fbbf24",
        fontWeight: 700,
        whiteSpace: "nowrap",
        cursor: "help",
        display: "inline-flex",
        alignItems: "center",
        gap: "2px",
        verticalAlign: "middle",
        flexShrink: 0,
      }}
    >
      ⚡ {label}
    </span>
  );
}
