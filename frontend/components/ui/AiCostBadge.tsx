import React from "react";

/**
 * AI(Google AI Studio / Gemini) API를 호출하는 기능 표시.
 * 길이를 차지하지 않도록 작은 동전(🪙) 아이콘만 두고, 마우스를 올리면(hover)
 * 비용 발생 안내가 tooltip으로 뜬다. 수급·섹터 등 비-AI 기능엔 붙이지 않는다.
 */
export function AiCostBadge({ small = false }: { small?: boolean; label?: string }) {
  return (
    <span
      title="🪙 AI 기능 (Google AI Studio · Gemini 호출) — 사용량에 따라 비용이 발생할 수 있습니다"
      role="img"
      aria-label="AI 비용 발생 가능"
      style={{
        fontSize: small ? "0.72rem" : "0.82rem",
        cursor: "help",
        marginLeft: "3px",
        opacity: 0.85,
        verticalAlign: "middle",
        userSelect: "none",
      }}
    >
      🪙
    </span>
  );
}
