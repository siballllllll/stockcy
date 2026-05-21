import { ReactNode } from "react";

interface CardProps {
  title?:     ReactNode;
  children:   ReactNode;
  className?: string;
  action?:    ReactNode;   // 우측 상단 버튼 영역
  noPad?:     boolean;
}

export function Card({ title, children, className = "", action, noPad }: CardProps) {
  return (
    <div className={`stockcy-card ${className}`}>
      {(title || action) && (
        <div className="flex items-center justify-between mb-3">
          {title && (
            <h3 style={{ color: "var(--color-text)", fontWeight: 600, fontSize: "0.95rem" }}>
              {title}
            </h3>
          )}
          {action && <div>{action}</div>}
        </div>
      )}
      <div className={noPad ? "" : undefined}>{children}</div>
    </div>
  );
}
