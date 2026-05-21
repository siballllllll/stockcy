"use client";
import { useState, ReactNode } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";

interface AccordionProps {
  title:        ReactNode;
  children:     ReactNode;
  defaultOpen?: boolean;
  badge?:       ReactNode;
  className?:   string;
}

/** Streamlit st.expander 를 재현한 아코디언 컴포넌트 */
export function Accordion({ title, children, defaultOpen = false, badge, className = "" }: AccordionProps) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div
      className={className}
      style={{
        border:       "1px solid var(--color-border)",
        borderRadius: "0.5rem",
        overflow:     "hidden",
        marginBottom: "0.5rem",
      }}
    >
      <button
        onClick={() => setOpen((v) => !v)}
        style={{
          width:           "100%",
          display:         "flex",
          alignItems:      "center",
          justifyContent:  "space-between",
          padding:         "0.65rem 0.875rem",
          background:      open ? "var(--color-elevated)" : "var(--color-card)",
          color:           "var(--color-text)",
          border:          "none",
          cursor:          "pointer",
          fontSize:        "0.875rem",
          fontWeight:      500,
          textAlign:       "left",
          transition:      "background 0.15s",
        }}
      >
        <span style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          {title}
          {badge}
        </span>
        {open ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
      </button>

      {open && (
        <div
          style={{
            padding:    "0.875rem",
            background: "var(--color-card)",
            borderTop:  "1px solid var(--color-border)",
          }}
        >
          {children}
        </div>
      )}
    </div>
  );
}
