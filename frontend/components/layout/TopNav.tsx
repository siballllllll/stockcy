"use client";
import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { BarChart2, TrendingUp, GitBranch, Star, Layers, FlaskConical, Brain, Filter, Bell } from "lucide-react";
import { BriefingModal } from "@/components/ui/BriefingModal";
import { useMarket } from "@/lib/market-context";
import { useAnalysisReady } from "@/lib/analysis-ready-context";
import { useAiTask } from "@/contexts/AiTaskContext";
import { Loader2, CheckCircle2 } from "lucide-react";
import useSWR from "swr";

// task id → 이동할 페이지 경로 매핑 (id에 키워드가 포함되면 매칭)
function _taskRoute(id: string): string {
  const s = id.toLowerCase();
  if (s.includes("pattern") || s.includes("picks") || s.includes("supply") || s.includes("rotation")) return "/";
  if (s.includes("scenario")) return "/scenarios";
  if (s.includes("sector") || s.includes("shadow")) return "/sectors";
  if (s.includes("screener")) return "/screener";
  if (s.includes("agent") || s.includes("capital")) return "/agent";
  if (s.includes("kr-stock") || s.includes("us-stock") || s.includes("report") || s.includes("search")) return "/search";
  return "/";
}

function AiTaskIndicator() {
  const { tasks, clearTask } = useAiTask();
  const router = useRouter();
  const [mounted, setMounted] = useState(false);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => { setMounted(true); }, []);
  useEffect(() => {
    const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);
  if (!mounted) return null;
  const taskList = Object.values(tasks).sort((a, b) => (b.completedAt ?? b.timestamp) - (a.completedAt ?? a.timestamp));
  if (taskList.length === 0) return null;

  const runningCount = taskList.filter(t => t.status === "running").length;
  const doneCount = taskList.filter(t => t.status === "done").length;
  const errorCount = taskList.filter(t => t.status === "error").length;
  const badgeCount = runningCount > 0 ? runningCount : doneCount;

  const goTo = (t: any) => {
    router.push(_taskRoute(t.id));
    setOpen(false);
  };

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{ display: "flex", alignItems: "center", gap: "6px", background: "var(--color-surface)", padding: "4px 10px", borderRadius: "20px", border: "1px solid var(--color-border)", fontSize: "0.75rem", fontWeight: 600, cursor: "pointer", color: "var(--color-text)" }}
      >
        {runningCount > 0 ? (
          <>
            <Loader2 className="stockcy-spin" size={12} color="var(--color-primary)" />
            <span>AI 분석 중 ({runningCount})</span>
          </>
        ) : doneCount > 0 ? (
          <>
            <Bell size={12} color="var(--color-up)" />
            <span style={{ color: "var(--color-up)" }}>알림 ({doneCount})</span>
          </>
        ) : (
          <span style={{ color: "var(--color-danger)" }}>에러 ({errorCount})</span>
        )}
      </button>

      {open && (
        <div style={{ position: "absolute", top: "calc(100% + 6px)", right: 0, width: "300px", maxHeight: "380px", overflowY: "auto", background: "var(--color-card)", border: "1px solid var(--color-border)", borderRadius: "10px", boxShadow: "0 8px 28px rgba(0,0,0,0.4)", zIndex: 300, padding: "6px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "6px 8px", borderBottom: "1px solid var(--color-border)", marginBottom: "4px" }}>
            <span style={{ fontSize: "0.78rem", fontWeight: 800, color: "var(--color-text)" }}>🔔 분석 알림</span>
            {doneCount > 0 && (
              <button onClick={() => taskList.filter(t => t.status === "done").forEach(t => clearTask(t.id))} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--color-muted)", fontSize: "0.68rem" }}>모두 지우기</button>
            )}
          </div>
          {taskList.map(t => {
            const c = t.status === "done" ? "var(--color-up)" : t.status === "error" ? "var(--color-danger)" : "var(--color-primary)";
            const label = t.status === "done" ? "완료" : t.status === "error" ? "오류" : "진행 중";
            return (
              <div key={t.id} style={{ display: "flex", alignItems: "center", gap: "8px", padding: "8px", borderRadius: "6px", cursor: t.status === "done" ? "pointer" : "default" }}
                onClick={() => t.status === "done" && goTo(t)}
                onMouseEnter={e => { if (t.status === "done") e.currentTarget.style.background = "var(--color-surface)"; }}
                onMouseLeave={e => e.currentTarget.style.background = "transparent"}
              >
                {t.status === "running" ? <Loader2 className="stockcy-spin" size={13} color={c} /> : <div style={{ width: 8, height: 8, borderRadius: "50%", background: c, flexShrink: 0 }} />}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: "0.76rem", fontWeight: 700, color: "var(--color-text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{t.title}</div>
                  <div style={{ fontSize: "0.66rem", color: c }}>{label}{t.fromCache ? " (캐시)" : ""} {t.status === "done" ? "· 클릭하여 보기 →" : ""}</div>
                </div>
                <button onClick={(e) => { e.stopPropagation(); clearTask(t.id); }} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--color-muted)", fontSize: "0.85rem", flexShrink: 0 }}>&times;</button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

const TABS = [
  { href: "/",          label: "🔥 대시보드",        exact: true,  icon: <TrendingUp size={15} />, readyKey: "picks"     as const },
  { href: "/search",    label: "📊 종합 검색",       exact: false, icon: <BarChart2 size={15} />,  readyKey: null },
  { href: "/screener",  label: "🔍 복합 스크리너",   exact: false, icon: <Filter size={15} />,     readyKey: null },
  { href: "/sectors",   label: "🌐 이슈 섹터",       exact: false, icon: <GitBranch size={15} />,  readyKey: null },
  { href: "/favorites", label: "💼 포트폴리오 관리", exact: false, icon: <Star size={15} />,       readyKey: null },
  { href: "/agent",     label: "🤖 AI 에이전트",      exact: false, icon: <Brain size={15} />,      readyKey: null },
  { href: "/scenarios", label: "📈 시나리오",        exact: false, icon: <Layers size={15} />,     readyKey: "scenarios" as const },
];

export function TopNav() {
  const pathname = usePathname();
  const [briefingOpen, setBriefingOpen] = useState(false);
  const { market, setMarket } = useMarket();
  const { ready } = useAnalysisReady();
  const { data: versionData } = useSWR(
    "/backend/api/admin/version",
    (url: string) => fetch(url).then(r => r.json()),
    { revalidateOnFocus: false, refreshInterval: 0 }
  );
  const appVersion = versionData?.version ?? "...";

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
          <span style={{ fontSize: "0.65rem", fontWeight: 500, color: "var(--color-muted)", marginLeft: "6px", opacity: 0.7 }}>
            v{appVersion}
          </span>
        </div>

        {/* 탭 목록 */}
        <nav style={{ display: "flex", flex: 1 }}>
          {TABS.map((tab) => {
            const active = tab.exact ? pathname === tab.href : pathname.startsWith(tab.href);
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
          
          {/* AI 태스크 인디케이터 */}
          <AiTaskIndicator />

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
