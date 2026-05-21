import { ReactNode } from "react";
import { Info, CheckCircle, AlertTriangle, XCircle } from "lucide-react";

type BoxType = "info" | "success" | "warning" | "danger";

const ICONS = {
  info:    <Info     size={15} />,
  success: <CheckCircle  size={15} />,
  warning: <AlertTriangle size={15} />,
  danger:  <XCircle  size={15} />,
};

interface StatusBoxProps {
  type?:      BoxType;
  children:   ReactNode;
  className?: string;
}

/** Streamlit st.info / st.success / st.warning / st.error 재현 */
export function StatusBox({ type = "info", children, className = "" }: StatusBoxProps) {
  return (
    <div className={`stockcy-box stockcy-box-${type} ${className}`}
         style={{ display: "flex", alignItems: "flex-start", gap: "0.5rem" }}>
      <span style={{ marginTop: "1px", flexShrink: 0 }}>{ICONS[type]}</span>
      <span>{children}</span>
    </div>
  );
}
