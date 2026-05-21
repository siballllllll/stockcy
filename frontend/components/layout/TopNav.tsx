"use client";
import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { BarChart2, TrendingUp, GitBranch, Star, Layers } from "lucide-react";
import { BriefingModal } from "@/components/ui/BriefingModal";
import { useMarket } from "@/lib/market-context";
import { useAnalysisReady } from "@/lib/analysis-ready-context";

const TABS = [
  { href: "/picks",     label: "🎯 AI 타점 보드",    icon: <TrendingUp size={15} />, readyKey: "picks"     as const },
  { href: "/search",    label: "📊 종목 종합 검색",  icon: <BarChart2 size={15} />,  readyKey: null },
  { href: "/sectors",   label: "🔥 이슈 섹터 탐색",  icon: <GitBranch size={15} />,  readyKey: null },
  { href: "/favorites", label: "⭐ 즐겨찾기",        icon: <Star size={15} />,       readyKey: null },
  { href: "/scenarios", label: "📈 시나리오",         icon: <Layers size={15} />,     readyKey: "scenarios" as const },
];

export function TopNav() {
  const pathname = usePathname();
  const [briefingOpen, setBriefingOpen] = useState(false);
  const { market, setMarket } = useMarket();
  const { ready } = useAnalysisReady();

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
            const isReady = tab.readyKey ? ready[tab.readyKey] : false;
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
                  position:       "relative",
                }}
              >
                {tab.icon}
                {tab.label}
                {isReady && !active && (
                  <span style={{
                    width: "7px", height: "7px", borderRadius: "50%",
                    background: "#22c55e",
                    animation: "blink-green 1.2s ease-in-out infinite",
                    flexShrink: 0,
                  }} />
                )}
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
              onClick={() => setMarket("KR")}
              style={{
                padding: "2px 10px", fontSize: "0.8rem", borderRadius: "4px", border: "none", cursor: "pointer",
                background: market === "KR" ? "var(--color-accent)" : "transparent",
                color: market === "KR" ? "white" : "var(--color-muted)", fontWeight: 600,
                transition: "0.15s",
              }}
            >
              🇰🇷 국내
            </button>
            <button
              onClick={() => setMarket("US")}
              style={{
                padding: "2px 10px", fontSize: "0.8rem", borderRadius: "4px", border: "none", cursor: "pointer",
                background: market === "US" ? "var(--color-accent)" : "transparent",
                color: market === "US" ? "white" : "var(--color-muted)", fontWeight: 600,
                transition: "0.15s",
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
