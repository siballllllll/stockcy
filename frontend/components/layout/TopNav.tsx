"use client";
import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { BarChart2, TrendingUp, GitBranch, Star } from "lucide-react";
import { BriefingModal } from "@/components/ui/BriefingModal";

const TABS = [
  { href: "/picks",     label: "🎯 AI 타점 보드",    icon: <TrendingUp size={15} /> },
  { href: "/search",    label: "📊 종목 종합 검색",  icon: <BarChart2 size={15} /> },
  { href: "/sectors",   label: "🔥 이슈 섹터 탐색",  icon: <GitBranch size={15} /> },
  { href: "/favorites", label: "⭐ 즐겨찾기",        icon: <Star size={15} /> },
];

export function TopNav() {
  const pathname = usePathname();
  const [briefingOpen, setBriefingOpen] = useState(false);

  return (
    <>
    <header
      style={{
        position:        "sticky",
        top:             0,
        zIndex:          50,
        background:      "var(--color-card)",
        borderBottom:    "1px solid var(--color-border)",
      }}
    >
      {/* 브랜드 + 탭 행 */}
      <div
        style={{
          width:      "100%",
          margin:     "0 auto",
          padding:    "0 5%",
          display:    "flex",
          alignItems: "stretch",
          height:     "52px",
          gap:        "0",
        }}
      >
        {/* 로고 */}
        <div
          style={{
            display:    "flex",
            alignItems: "center",
            paddingRight: "1.75rem",
            borderRight: "1px solid var(--color-border)",
            marginRight: "0.5rem",
            flexShrink:  0,
          }}
        >
          <span style={{ fontSize: "1.1rem", fontWeight: 800, color: "var(--color-accent)", letterSpacing: "-0.02em" }}>
            STOCKCY
          </span>
        </div>

        {/* 탭 목록 */}
        <nav style={{ display: "flex", flex: 1 }}>
          {TABS.map((tab) => {
            const active = pathname.startsWith(tab.href);
            return (
              <Link
                key={tab.href}
                href={tab.href}
                style={{
                  display:        "flex",
                  alignItems:     "center",
                  gap:            "0.375rem",
                  padding:        "0 1rem",
                  fontSize:       "0.9rem",
                  fontWeight:     active ? 700 : 500,
                  color:          active ? "var(--color-text)" : "var(--color-muted)",
                  borderBottom:   active ? "3px solid var(--color-danger)" : "3px solid transparent",
                  textDecoration: "none",
                  transition:     "color 0.15s, border-color 0.15s",
                  whiteSpace:     "nowrap",
                }}
              >
                {tab.icon}
                {tab.label}
              </Link>
            );
          })}
        </nav>
        {/* 우측 유틸리티 영역 */}
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginLeft: "auto", paddingLeft: "1rem" }}>
          {/* 브리핑 버튼 (팝업 오픈용) */}
          <button 
            className="stockcy-btn stockcy-btn-primary" 
            style={{ padding: "4px 12px", fontSize: "0.8rem", fontWeight: 600 }}
            onClick={() => setBriefingOpen(true)}
          >
            📰 브리핑
          </button>
          
          {/* 시장 토글 버튼 */}
          <div style={{ display: "flex", background: "var(--color-bg)", borderRadius: "6px", padding: "2px", border: "1px solid var(--color-border)" }}>
            <button 
              style={{ 
                padding: "2px 10px", fontSize: "0.8rem", borderRadius: "4px", border: "none", cursor: "pointer",
                background: "var(--color-accent)", color: "white", fontWeight: 600
              }}
            >
              🇰🇷 국내
            </button>
            <button 
              style={{ 
                padding: "2px 10px", fontSize: "0.8rem", borderRadius: "4px", border: "none", cursor: "pointer",
                background: "transparent", color: "var(--color-muted)", fontWeight: 500
              }}
            >
              🇺🇸 미국
            </button>
          </div>
        </div>
      </div>
    </header>

    {briefingOpen && <BriefingModal onClose={() => setBriefingOpen(false)} />}
    </>
  );
}
