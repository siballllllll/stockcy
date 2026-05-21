interface SpinnerProps {
  text?:  string;
  size?:  "sm" | "md" | "lg";
}

const SIZE = { sm: 16, md: 24, lg: 36 };

export function LoadingSpinner({ text, size = "md" }: SpinnerProps) {
  const px = SIZE[size];
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "0.625rem", color: "var(--color-muted)", fontSize: "0.875rem" }}>
      <span
        className="animate-spin"
        style={{
          display:     "inline-block",
          width:       px,
          height:      px,
          border:      `2px solid var(--color-border)`,
          borderTop:   `2px solid var(--color-accent)`,
          borderRadius: "50%",
          flexShrink:  0,
        }}
      />
      {text && <span>{text}</span>}
    </div>
  );
}

/** 풀 페이지 또는 섹션 중앙 로딩 */
export function CenterSpinner({ text = "로딩 중..." }: { text?: string }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: "0.75rem", padding: "3rem 0" }}>
      <LoadingSpinner size="lg" />
      <p style={{ color: "var(--color-muted)", fontSize: "0.875rem" }}>{text}</p>
    </div>
  );
}

/** 스켈레톤 로더 */
export function Skeleton({ width = "100%", height = "1rem", className = "" }: {
  width?: string; height?: string; className?: string;
}) {
  return (
    <div
      className={`skeleton ${className}`}
      style={{ width, height }}
    />
  );
}
