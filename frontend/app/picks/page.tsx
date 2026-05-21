"use client";
import { useState, useEffect } from "react";
import { Target, Filter, TrendingUp, AlertCircle, Clock, Activity, Loader2 } from "lucide-react";
import { connectSSE, api } from "@/lib/api";

export default function PicksPage() {
  const [filter, setFilter] = useState("전체");

  const [loading, setLoading] = useState(true);
  const [statusMsg, setStatusMsg] = useState("시장 데이터를 수집 중입니다...");
  const [data, setData] = useState<{ market_comment?: string, picks: any[] }>({ picks: [] });

  useEffect(() => {
    let unmounted = false;
    setLoading(true);
    setStatusMsg("AI 분석 엔진 가동 중...");

    connectSSE(
      "/api/ai/realtime-picks-kr",
      (evt) => {
        if (unmounted) return;
        if (evt.status === "running") {
          setStatusMsg(evt.message || "분석 중...");
        } else if (evt.status === "done") {
          setData(evt.result as any);
          setLoading(false);
        } else if (evt.status === "error") {
          setStatusMsg(`오류 발생: ${evt.message}`);
          setLoading(false);
        }
      },
      { method: "POST", body: {} }
    ).catch(err => {
      if (!unmounted) {
        setStatusMsg("서버 연결 실패");
        setLoading(false);
      }
    });

    return () => { unmounted = true; };
  }, []);

  const picks = data.picks || [];
  
  // 필터링 적용
  const filteredPicks = picks.filter((p: any) => {
    if (filter === "전체") return true;
    if (filter === "극단타") return p.horizon?.includes("스캘핑") || p.urgency?.includes("즉시");
    if (filter === "단기스윙") return p.horizon?.includes("스윙");
    return true;
  });

  return (
    <div style={{ width: "100%", margin: "0 auto", display: "flex", flexDirection: "column", gap: "1.2rem" }}>
      
      {/* 상단 헤더 & 현황판 (Dense Mode) */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", borderBottom: "1px solid rgba(255,255,255,0.05)", paddingBottom: "1rem" }}>
        <div>
          <h1 style={{ fontSize: "1.6rem", fontWeight: 800, margin: "0 0 0.5rem 0", display: "flex", alignItems: "center", gap: "8px" }}>
            <Target color="var(--color-danger)" /> 실시간 타점 포착
          </h1>
          <div style={{ fontSize: "0.85rem", color: "var(--color-muted)", display: "flex", alignItems: "center", gap: "6px" }}>
            <Activity size={14} /> AI가 당일 주도 테마와 수급을 융합하여 5~10% 단타 구간을 찾아냅니다. 
            {data.market_comment && <span style={{ color: "var(--color-accent)", marginLeft: "8px" }}>[{data.market_comment}]</span>}
          </div>
        </div>
        
        {/* 미니 필터 버튼들 (오밀조밀하게) */}
        <div style={{ display: "flex", gap: "6px" }}>
          {["전체", "극단타", "단기스윙"].map(f => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              style={{
                padding: "6px 12px",
                fontSize: "0.85rem",
                fontWeight: 700,
                borderRadius: "4px",
                border: "1px solid",
                borderColor: filter === f ? "var(--color-accent)" : "var(--color-border)",
                background: filter === f ? "rgba(255,255,255,0.1)" : "transparent",
                color: filter === f ? "var(--color-text)" : "var(--color-muted)",
                cursor: "pointer",
                transition: "0.2s"
              }}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      {/* 요약 통계 패널 */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: "10px", marginBottom: "0.5rem" }}>
        {[
          { label: "신규 포착", val: `${picks.length}건`, icon: <AlertCircle size={16} color="var(--color-danger)"/> },
          { label: "과열 주의", val: "8건", icon: <TrendingUp size={16} color="var(--color-warning)"/> },
          { label: "단기 돌파", val: "22건", icon: <Target size={16} color="var(--color-success)"/> },
          { label: "마지막 업데이트", val: "1분 전", icon: <Clock size={16} color="var(--color-muted)"/> }
        ].map((stat, i) => (
          <div key={i} style={{ background: "rgba(255,255,255,0.02)", border: "1px solid var(--color-border)", padding: "10px", borderRadius: "6px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "0.8rem", color: "var(--color-muted)" }}>
              {stat.icon} {stat.label}
            </div>
            <div style={{ fontWeight: 800, fontSize: "1rem" }}>{stat.val}</div>
          </div>
        ))}
      </div>

      {/* 와이드 그리드 타점 카드 (가로로 빽빽하게) */}
      {loading ? (
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "4rem 0", gap: "1rem" }}>
          <Loader2 className="animate-spin" size={40} color="var(--color-danger)" />
          <div style={{ color: "var(--color-muted)", fontWeight: 600 }}>{statusMsg}</div>
        </div>
      ) : filteredPicks.length === 0 ? (
        <div style={{ padding: "4rem 0", textAlign: "center", color: "var(--color-muted)" }}>조건에 맞는 타점이 없습니다.</div>
      ) : (
        <div style={{ 
          display: "grid", 
          gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", 
          gap: "1rem" 
        }}>
          {filteredPicks.map((pick: any) => {
            const isUp = (pick.change_pct || 0) > 0;
            const urgencyColor = pick.urgency?.includes("즉시") ? "var(--color-danger)" : 
                                 pick.urgency?.includes("대기") ? "var(--color-warning)" : "var(--color-success)";
            
            return (
              <div key={pick.code} className="stockcy-card hover-highlight" style={{ padding: "14px", borderTop: `3px solid ${urgencyColor}`, background: "rgba(255,255,255,0.02)", cursor: "pointer", display: "flex", flexDirection: "column", gap: "10px" }}>
                {/* 카드 상단: 종목명 및 상태 */}
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                  <div>
                    <h3 style={{ margin: 0, fontSize: "1rem", fontWeight: 800 }}>{pick.name}</h3>
                    <span style={{ fontSize: "0.75rem", color: "var(--color-muted)" }}>{pick.code}</span>
                  </div>
                  <div style={{ display: "flex", gap: "4px" }}>
                    <span style={{ fontSize: "0.7rem", fontWeight: 700, padding: "2px 6px", background: "rgba(255,255,255,0.1)", borderRadius: "4px" }}>{pick.horizon || "단타"}</span>
                    <span style={{ fontSize: "0.7rem", fontWeight: 700, padding: "2px 6px", background: urgencyColor, color: "var(--bg-color)", borderRadius: "4px" }}>{pick.urgency || "보통"}</span>
                  </div>
                </div>

                {/* 현재가 및 등락률 */}
                <div style={{ display: "flex", alignItems: "baseline", gap: "6px" }}>
                  <span style={{ fontSize: "1.2rem", fontWeight: 800 }}>₩{pick.current_price?.toLocaleString()}</span>
                  <span style={{ fontSize: "0.85rem", fontWeight: 700, color: isUp ? "var(--color-danger)" : "var(--color-primary)" }}>
                    {isUp ? "▲" : "▼"} {Math.abs(pick.change_pct || 0)}%
                  </span>
                </div>

                <div style={{ fontSize: "0.8rem", color: "var(--color-subtle)", lineHeight: 1.4, background: "rgba(0,0,0,0.2)", padding: "8px", borderRadius: "4px" }}>
                  <span style={{ color: "var(--color-accent)", fontWeight: 700 }}>[{pick.pattern}]</span> {pick.reason}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
