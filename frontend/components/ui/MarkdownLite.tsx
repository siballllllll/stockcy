import React from "react";

/** '**굵게**' 인라인 마크다운을 <strong>으로 변환 */
function renderSegments(text: string) {
  return text.split("**").map((seg, i) =>
    i % 2 === 1 ? <strong key={i}>{seg}</strong> : <React.Fragment key={i}>{seg}</React.Fragment>
  );
}

/**
 * AI 출력에 섞인 경량 마크다운(**굵게**, # 헤더)을 실제 스타일로 렌더링한다.
 * 줄바꿈은 pre-wrap으로 보존. 날것의 '**' 가 화면에 그대로 보이는 문제를 해결한다.
 */
export function MarkdownLite({
  text,
  style,
  className,
}: {
  text?: string | null;
  style?: React.CSSProperties;
  className?: string;
}) {
  const lines = String(text ?? "").split("\n");
  return (
    <div className={className} style={{ whiteSpace: "pre-wrap", ...style }}>
      {lines.map((line, i) => {
        const h = line.match(/^\s*#{1,6}\s+(.*)$/);   // 헤더 라인
        const content = h ? h[1] : line;
        const segs = renderSegments(content);
        return (
          <React.Fragment key={i}>
            {h ? <strong>{segs}</strong> : segs}
            {i < lines.length - 1 ? "\n" : null}
          </React.Fragment>
        );
      })}
    </div>
  );
}
