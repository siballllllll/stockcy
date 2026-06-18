"use client";
import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { BarChart2, TrendingUp, GitBranch, Star, Layers, FlaskConical, Brain, Bell } from "lucide-react";
import { BriefingModal } from "@/components/ui/BriefingModal";
import { TelegramSettingsModal } from "@/components/auth/TelegramSettingsModal";
import { useMarket } from "@/lib/market-context";
import { useAnalysisReady } from "@/lib/analysis-ready-context";
import { useAiTask } from "@/contexts/AiTaskContext";
import { useAuth } from "@/lib/auth-context";
import { Loader2, CheckCircle2, LogOut, Menu, X } from "lucide-react";
import useSWR from "swr";
import { useIsMobile } from "@/lib/use-is-mobile";

// 완료 시각 → "방금 전 / N분 전 / N시간 전 / N일 전" 상대시간 문자열
function _relTime(ts?: number): string {
  if (!ts) return "";
  const diff = Date.now() - ts;
  const m = Math.floor(diff / 60000);
  if (m < 1) return "방금 전";
  if (m < 60) return `${m}분 전`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}시간 전`;
  const d = Math.floor(h / 24);
  return `${d}일 전`;
}

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
  const { tasks, clearTask, markRead } = useAiTask();
  const router = useRouter();
  const [mounted, setMounted] = useState(false);
  const [open, setOpen] = useState(false);
  const [, setTick] = useState(0);  // 상대시간 주기적 갱신용
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => { setMounted(true); }, []);
  useEffect(() => {
    const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);
  // 1분마다 리렌더하여 "N분 전" 표시 갱신
  useEffect(() => {
    const iv = setInterval(() => setTick(x => x + 1), 60000);
    return () => clearInterval(iv);
  }, []);
  if (!mounted) return null;
  const taskList = Object.values(tasks).sort((a, b) => (b.completedAt ?? b.timestamp) - (a.completedAt ?? a.timestamp));
  if (taskList.length === 0) return null;

  const runningCount = taskList.filter(t => t.status === "running").length;
  const doneCount = taskList.filter(t => t.status === "done").length;
  const unreadCount = taskList.filter(t => t.status === "done" && !t.read).length;
  const errorCount = taskList.filter(t => t.status === "error").length;

  const goTo = (t: any) => {
    markRead(t.id);
    router.push(t.route || _taskRoute(t.id));
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
        ) : unreadCount > 0 ? (
          <>
            <Bell size={12} color="var(--color-success)" />
            <span style={{ color: "var(--color-success)" }}>알림 ({unreadCount})</span>
          </>
        ) : doneCount > 0 ? (
          <>
            <Bell size={12} color="var(--color-muted)" />
            <span style={{ color: "var(--color-muted)" }}>알림</span>
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
            const c = t.status === "done" ? "var(--color-success)" : t.status === "error" ? "var(--color-danger)" : "var(--color-info)";
            const label = t.status === "done" ? "완료" : t.status === "error" ? "오류" : "진행 중";
            const isRead = t.status === "done" && t.read;
            const rel = _relTime(t.completedAt ?? t.timestamp);
            return (
              <div key={t.id} style={{ display: "flex", alignItems: "center", gap: "8px", padding: "8px", borderRadius: "6px", cursor: t.status === "done" ? "pointer" : "default", opacity: isRead ? 0.45 : 1, transition: "opacity 0.2s" }}
                onClick={() => t.status === "done" && goTo(t)}
                onMouseEnter={e => { if (t.status === "done") e.currentTarget.style.background = "var(--color-surface)"; }}
                onMouseLeave={e => e.currentTarget.style.background = "transparent"}
              >
                {t.status === "running" ? <Loader2 className="stockcy-spin" size={13} color={c} /> : <div style={{ width: 8, height: 8, borderRadius: "50%", background: isRead ? "var(--color-muted)" : c, flexShrink: 0 }} />}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: "6px", alignItems: "baseline" }}>
                    <span style={{ fontSize: "0.76rem", fontWeight: isRead ? 500 : 700, color: "var(--color-text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{t.title}</span>
                    {rel && <span style={{ fontSize: "0.62rem", color: "var(--color-muted)", flexShrink: 0 }}>{rel}</span>}
                  </div>
                  <div style={{ fontSize: "0.66rem", color: c }}>{label}{t.fromCache ? " (캐시)" : ""} {t.status === "done" ? (isRead ? "· 확인함" : "· 클릭하여 보기 →") : ""}</div>
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

function AiCreditChip() {
  const { data } = useSWR(
    "/backend/api/auth/ai-status",
    (u: string) => fetch(u, { cache: "no-store" }).then(r => r.json()),
    { refreshInterval: 30000, revalidateOnFocus: true }
  );
  if (!data || data.is_admin) return null;
  const credits = data.ai_credits ?? 0;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "5px" }}>
      <span title="AI 분석 잔여 횟수" style={{ fontSize: "0.72rem", fontWeight: 700, color: credits > 0 ? "#34d399" : "var(--color-muted)", background: "var(--color-surface)", border: "1px solid var(--color-border)", borderRadius: "20px", padding: "3px 9px", whiteSpace: "nowrap" }}>
        🎟 AI {credits}회{data.pending ? " · 승인대기" : ""}
      </span>
      {credits <= 0 && !data.pending && (
        <button
          onClick={() => window.dispatchEvent(new CustomEvent("stockcy:need-ai-credit"))}
          style={{ fontSize: "0.72rem", fontWeight: 700, color: "#fff", background: "var(--color-accent)", border: "none", borderRadius: "20px", padding: "3px 9px", cursor: "pointer" }}
        >
          신청
        </button>
      )}
    </div>
  );
}

const TABS = [
  { href: "/",          label: "🔥 대시보드",        exact: true,  icon: <TrendingUp size={15} />, readyKey: "picks"     as const },
  { href: "/search",    label: "📊 종합 검색",       exact: false, icon: <BarChart2 size={15} />,  readyKey: null },
  { href: "/sectors",   label: "🌐 이슈 섹터",       exact: false, icon: <GitBranch size={15} />,  readyKey: null },
  { href: "/favorites", label: "💼 포트폴리오 관리", exact: false, icon: <Star size={15} />,       readyKey: null },
  { href: "/agent",     label: "🤖 AI 에이전트",      exact: false, icon: <Brain size={15} />,      readyKey: null },
  { href: "/scenarios", label: "📈 시나리오",        exact: false, icon: <Layers size={15} />,     readyKey: "scenarios" as const },
  { href: "/performance", label: "📊 성과·기록",     exact: false, icon: <BarChart2 size={15} />,  readyKey: null },
];

export function TopNav() {
  const pathname = usePathname();
  const [briefingOpen, setBriefingOpen] = useState(false);
  const [telegramOpen, setTelegramOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const { market, setMarket } = useMarket();
  const { ready } = useAnalysisReady();
  const { user, logout } = useAuth();
  const isMobile = useIsMobile();
  const { data: versionData } = useSWR(
    "/backend/api/admin/version",
    (url: string) => fetch(url).then(r => r.json()),
    { revalidateOnFocus: false, refreshInterval: 0 }
  );
  const appVersion = versionData?.version ?? "...";

  // 라우트 이동 시 모바일 메뉴 자동 닫기
  useEffect(() => { setMenuOpen(false); }, [pathname]);

  // 탭 렌더 (가로=데스크톱, 세로=모바일 드롭다운)
  const renderTabs = (vertical: boolean) => TABS.map((tab) => {
    const active = tab.exact ? pathname === tab.href : pathname.startsWith(tab.href);
    const isReady = tab.readyKey ? ready[tab.readyKey] : false;
    return (
      <Link
        key={tab.href}
        href={tab.href}
        onClick={() => setMenuOpen(false)}
        style={{
          display:        "flex",
          alignItems:     "center",
          gap:            "0.5rem",
          padding:        vertical ? "0.7rem 0.5rem" : "0 1rem",
          fontSize:       "0.9rem",
          fontWeight:     active ? 700 : 500,
          color:          active ? "var(--color-text)" : "var(--color-muted)",
          borderBottom:   vertical ? "none" : (active ? "3px solid var(--color-danger)" : "3px solid transparent"),
          borderLeft:     vertical ? (active ? "3px solid var(--color-danger)" : "3px solid transparent") : undefined,
          background:     vertical && active ? "var(--color-surface)" : undefined,
          borderRadius:   vertical ? "4px" : undefined,
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
  });

  // 시장 토글 (데스크톱·모바일 공용)
  const marketToggle = (
    <div style={{ display: "flex", background: "var(--color-bg)", borderRadius: "6px", padding: "2px", border: "1px solid var(--color-border)" }}>
      <button onClick={() => setMarket("KR")} style={{ padding: "2px 10px", fontSize: "0.8rem", borderRadius: "4px", border: "none", cursor: "pointer", background: market === "KR" ? "var(--color-accent)" : "transparent", color: market === "KR" ? "white" : "var(--color-muted)", fontWeight: 600, transition: "0.15s" }}>🇰🇷 국내</button>
      <button onClick={() => setMarket("US")} style={{ padding: "2px 10px", fontSize: "0.8rem", borderRadius: "4px", border: "none", cursor: "pointer", background: market === "US" ? "var(--color-accent)" : "transparent", color: market === "US" ? "white" : "var(--color-muted)", fontWeight: 600, transition: "0.15s" }}>🇺🇸 미국</button>
    </div>
  );

  // 사용자 + 로그아웃 블록 (vertical=모바일에서 약간 다른 정렬)
  const userBlock = user && (
    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", paddingLeft: isMobile ? 0 : "0.25rem", borderLeft: isMobile ? "none" : "1px solid var(--color-border)" }}>
      <button onClick={() => { setTelegramOpen(true); setMenuOpen(false); }} title="텔레그램 알림 설정" style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", borderRadius: "6px", padding: "3px 7px", fontSize: "0.85rem", cursor: "pointer" }}>🔔</button>
      {user.role === "admin" && (
        <Link href="/admin" onClick={() => setMenuOpen(false)} style={{ fontSize: "0.75rem", fontWeight: 700, color: "var(--color-accent)", textDecoration: "none", border: "1px solid var(--color-accent)", borderRadius: "6px", padding: "3px 8px", whiteSpace: "nowrap" }}>⚙ 관리자</Link>
      )}
      <span style={{ fontSize: "0.78rem", fontWeight: 600, color: "var(--color-text)", whiteSpace: "nowrap" }}>
        {user.username}
        {user.role === "admin" && (
          <span style={{ marginLeft: "5px", fontSize: "0.62rem", fontWeight: 700, color: "var(--color-accent)", border: "1px solid var(--color-accent)", borderRadius: "4px", padding: "1px 4px" }}>관리자</span>
        )}
      </span>
      <button onClick={logout} title="로그아웃" style={{ display: "flex", alignItems: "center", gap: "4px", background: "var(--color-surface)", border: "1px solid var(--color-border)", borderRadius: "6px", padding: "4px 8px", fontSize: "0.75rem", color: "var(--color-muted)", cursor: "pointer" }}>
        <LogOut size={13} /> 로그아웃
      </button>
    </div>
  );

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
          padding:    isMobile ? "0 0.75rem" : "0 5%",
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
            paddingRight: isMobile ? "0.75rem" : "1.75rem",
            borderRight: isMobile ? "none" : "1px solid var(--color-border)",
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

        {/* 데스크톱: 가로 탭 / 모바일: 공간만 */}
        {!isMobile
          ? <nav style={{ display: "flex", flex: 1 }}>{renderTabs(false)}</nav>
          : <div style={{ flex: 1 }} />}

        {/* 우측 유틸리티 영역 */}
        <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", marginLeft: "auto", paddingLeft: "0.5rem" }}>
          <AiTaskIndicator />
          {!isMobile ? (
            <>
              <button className="stockcy-btn stockcy-btn-primary" style={{ padding: "4px 12px", fontSize: "0.8rem", fontWeight: 600 }} onClick={() => setBriefingOpen(true)}>📰 브리핑</button>
              {marketToggle}
              {user && user.role !== "admin" && <AiCreditChip />}
              {userBlock}
            </>
          ) : (
            <>
              {user && user.role !== "admin" && <AiCreditChip />}
              <button
                onClick={() => setMenuOpen(o => !o)}
                aria-label="메뉴 열기"
                style={{ display: "flex", alignItems: "center", background: "var(--color-surface)", border: "1px solid var(--color-border)", borderRadius: "6px", padding: "6px 8px", cursor: "pointer", color: "var(--color-text)" }}
              >
                {menuOpen ? <X size={18} /> : <Menu size={18} />}
              </button>
            </>
          )}
        </div>
      </div>

      {/* 모바일 드롭다운 메뉴 */}
      {isMobile && menuOpen && (
        <div style={{ borderTop: "1px solid var(--color-border)", background: "var(--color-card)", padding: "0.6rem 0.75rem", display: "flex", flexDirection: "column", gap: "0.6rem", boxShadow: "0 8px 24px rgba(0,0,0,0.4)" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>{renderTabs(true)}</div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", flexWrap: "wrap", paddingTop: "0.6rem", borderTop: "1px solid var(--color-border)" }}>
            {marketToggle}
            <button className="stockcy-btn stockcy-btn-primary" style={{ padding: "4px 12px", fontSize: "0.8rem", fontWeight: 600 }} onClick={() => { setBriefingOpen(true); setMenuOpen(false); }}>📰 브리핑</button>
          </div>
          {userBlock && (
            <div style={{ paddingTop: "0.6rem", borderTop: "1px solid var(--color-border)" }}>{userBlock}</div>
          )}
        </div>
      )}
    </header>

    {briefingOpen && <BriefingModal onClose={() => setBriefingOpen(false)} />}
    <TelegramSettingsModal open={telegramOpen} onClose={() => setTelegramOpen(false)} />
    </>
  );
}
