type BadgeVariant = "up" | "down" | "flat" | "accent" | "success" | "info" | "warning" | "danger" | "muted";

const STYLES: Record<BadgeVariant, string> = {
  up:      "background:#1a3324;color:#00c853;",
  down:    "background:#3a1a1a;color:#ff5555;",
  flat:    "background:#2a2a30;color:#a3a8b0;",
  accent:  "background:#3a1515;color:#ff4b4b;",
  success: "background:#1a3324;color:#21c354;",
  info:    "background:#1c2d3f;color:#7ec8f7;",
  warning: "background:#2e2415;color:#ffc55a;",
  danger:  "background:#2e1a1a;color:#ff9090;",
  muted:   "background:#262730;color:#a3a8b0;",
};

interface BadgeProps {
  children:   React.ReactNode;
  variant?:   BadgeVariant;
  className?: string;
}

export function Badge({ children, variant = "muted", className = "" }: BadgeProps) {
  return (
    <span
      className={className}
      style={{
        display:      "inline-block",
        padding:      "1px 8px",
        borderRadius: "4px",
        fontSize:     "0.72rem",
        fontWeight:   700,
        ...Object.fromEntries(
          STYLES[variant].split(";").filter(Boolean).map((s) => {
            const [k, v] = s.split(":");
            return [k.trim(), v.trim()];
          })
        ),
      }}
    >
      {children}
    </span>
  );
}

/** 주식 등급에 따른 배지 자동 변환 */
export function SignalBadge({ signal }: { signal: string }) {
  const variantMap: Record<string, BadgeVariant> = {
    "매우 강력 추천": "up",
    "추천":           "success",
    "중간추천":       "info",
    "비추천":         "warning",
    "매우 비추천":    "down",
  };
  return <Badge variant={variantMap[signal] ?? "muted"}>{signal}</Badge>;
}

/** 시장 방향 배지 */
export function DirectionBadge({ direction }: { direction: string }) {
  const map: Record<string, BadgeVariant> = {
    "강세": "up", "약세": "down", "혼조": "warning",
  };
  return <Badge variant={map[direction] ?? "muted"}>{direction}</Badge>;
}

/** 긴급도 배지 */
export function UrgencyBadge({ urgency }: { urgency: string }) {
  const map: Record<string, BadgeVariant> = {
    "긴급": "danger", "보통": "warning", "장기": "info",
  };
  return <Badge variant={map[urgency] ?? "muted"}>{urgency}</Badge>;
}
