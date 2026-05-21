"use client";
import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { Target, Filter, TrendingUp, AlertCircle, Clock, Activity, Loader2, RefreshCw } from "lucide-react";
import { connectSSE } from "@/lib/api";
import { useMarket } from "@/lib/market-context";
import { useAnalysisReady } from "@/lib/analysis-ready-context";

export default function PicksPage() {
  const router = useRouter();
  const { market } = useMarket();
  const isKR = market === "KR";

  const [filter, setFilter] = useState("전체");
  const [loading, setLoading] = useState(false);
  const [statusMsg, setStatusMsg] = useState("");
  const [data, setData] = useState<{ market_comment?: string; market_condition?: string; picks: any[] }>({ picks: [] });
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const { setReady } = useAnalysisReady();
  const prevMarket = useRef(market);
  const unmountedRef = useRef(false);

  const startAnalysis = (mkt: string) => {
    if (loading) return;
    unmountedRef.current = false;
    const kr = mkt === "KR";
    setLoading(true);
    setStatusMsg(kr ? "AI 분석 엔진 가동 중..." : "🇺🇸 US AI 분석 엔진 가동 중...");

    const endpoint = kr ? "/api/ai/realtime-picks-kr" : "/api/ai/realtime-picks-us";

    connectSSE(
      endpoint,
      (evt) => {
        if (unmountedRef.current) return;
        if (evt.status === "running") {
          setStatusMsg(evt.message || "분석 중...");
        } else if (evt.status === "done") {
          setData(evt.result as any);
          setLoading(false);
          setLastUpdated(new Date());
          setReady("picks", true);
        } else if (evt.status === "error") {
          setStatusMsg(`오류 발생: ${evt.message}`);
          setLoading(false);
        }
      },
      { method: "POST", body: {} }
    ).then(() => {
      if (!unmountedRef.current) setLoading(false);
    }).catch(() => {
      if (!unmountedRef.current) {
        setStatusMsg("서버 연결 실패");
        setLoading(false);
      }
    });
  };

  // 시장 전환 시에만 자동 리셋 (재분석은 수동)
  useEffect(() => {
    if (prevMarket.current !== market) {
      prevMarket.current = market;
      unmountedRef.current = true;
      setData({ picks: [] });
      setLastUpdated(null);
      setReady("picks", false);
    }
    return () => { unmountedRef.current = true; };
  }, [market]);

  const picks = data.picks || [];

  // 통계 계산
  const urgentCount = picks.filter((p: any) => p.urgency?.includes("즉시")).length;
  const swingCount  = picks.filter((p: any) => p.horizon?.includes("스윙")).length;
  const timeLabel   = lastUpdated
    ? lastUpdated.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" })
    : "—";

  const filteredPicks = picks.filter((p: any) => {
    if (filter === "전체") return true;
    if (filter === "극단타") return p.horizon?.includes("스캘핑") || p.urgency?.includes("즉시");
    if (filter === "단기스윙") return p.horizon?.includes("스윙");
    return true;
  });

  return (
    <div style={{ width: "100%", margin: "0 auto", display: "flex", flexDirection: "column", gap: "1.2rem" }}>

      {/* 상단 헤더 & 현황판 */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", borderBottom: "1px solid rgba(255,255,255,0.05)", paddingBottom: "1rem" }}>
        <div>
          <h1 style={{ fontSize: "1.6rem", fontWeight: 800, margin: "0 0 0.5rem 0", display: "flex", alignItems: "center", gap: "8px" }}>
            <Target color="var(--color-danger)" />
            {isKR ? "🇰🇷 국내 실시간 타점 포착" : "🇺🇸 미국 실시간 타점 포착"}
          </h1>
          <div style={{ fontSize: "0.85rem", color: "var(--color-muted)", display: "flex", alignItems: "center", gap: "6px" }}>
            <Activity size={14} />
            {isKR
              ? "AI가 당일 주도 테마와 수급을 융합하여 5~10% 단타 구간을 찾아냅니다."
              : "AI가 US 시장 거래량·급등 패턴을 분석하여 스캘핑 타점을 찾아냅니다."}
            {data.market_condition && (
              <span style={{ color: "var(--color-accent)", marginLeft: "8px" }}>[{data.market_condition}]</span>
            )}
            {data.market_comment && (
              <span style={{ color: "var(--color-muted)", marginLeft: "4px" }}>{data.market_comment}</span>
            )}
          </div>
        </div>

        {/* 우측 컨트롤 */}
        <div style={{ display: "flex", gap: "6px", alignItems: "center" }}>
          {/* 새로고침 버튼 */}
          <button
            onClick={() => startAnalysis(market)}
            disabled={loading}
            className="stockcy-btn stockcy-btn-primary"
            style={{ display: "flex", alignItems: "center", gap: "5px", padding: "6px 14px", fontSize: "0.85rem" }}
          >
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
            {loading ? "분석 중..." : picks.length > 0 ? "재분석" : "AI 분석 시작"}
          </button>
          {/* 필터 버튼 */}
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
          { label: "신규 포착",       val: picks.length > 0 ? `${picks.length}건` : "—", icon: <AlertCircle size={16} color="var(--color-danger)" /> },
          { label: "즉시진입 긴급",   val: urgentCount > 0 ? `${urgentCount}건` : "—",   icon: <TrendingUp  size={16} color="var(--color-warning)" /> },
          { label: "단기 스윙",       val: swingCount > 0  ? `${swingCount}건`  : "—",   icon: <Target      size={16} color="var(--color-success)" /> },
          { label: "업데이트",        val: timeLabel,                                      icon: <Clock       size={16} color="var(--color-muted)" /> },
        ].map((stat, i) => (
          <div key={i} style={{ background: "rgba(255,255,255,0.02)", border: "1px solid var(--color-border)", padding: "10px", borderRadius: "6px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "0.8rem", color: "var(--color-muted)" }}>
              {stat.icon} {stat.label}
            </div>
            <div style={{ fontWeight: 800, fontSize: "1rem" }}>{stat.val}</div>
          </div>
        ))}
      </div>

      {/* 타점 카드 그리드 */}
      {loading ? (
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "4rem 0", gap: "1rem" }}>
          <Loader2 className="animate-spin" size={40} color="var(--color-danger)" />
          <div style={{ color: "var(--color-muted)", fontWeight: 600 }}>{statusMsg}</div>
          <div style={{ fontSize: "0.8rem", color: "var(--color-subtle)" }}>KR: 약 1~2분 소요 (핫 섹터 AI 분석 + 타점 AI 선정)</div>
        </div>
      ) : picks.length === 0 ? (
        <div style={{ padding: "4rem 0", textAlign: "center", color: "var(--color-muted)", display: "flex", flexDirection: "column", alignItems: "center", gap: "1rem" }}>
          <Target size={48} style={{ opacity: 0.3 }} />
          <div>위 &apos;AI 분석 시작&apos; 버튼을 눌러 오늘의 타점을 분석하세요.</div>
          <div style={{ fontSize: "0.8rem", color: "var(--color-subtle)" }}>
            {isKR ? "거래량·수급·핫 섹터 종합 AI 분석 → 3종목 타점 선정" : "US 거래량·모멘텀 분석 → 타점 선정"}
          </div>
        </div>
      ) : filteredPicks.length === 0 ? (
        <div style={{ padding: "4rem 0", textAlign: "center", color: "var(--color-muted)" }}>
          조건에 맞는 타점이 없습니다.
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: "1rem" }}>
          {filteredPicks.map((pick: any, idx: number) => {
            const isUp = (pick.change_pct || 0) > 0;
            const urgencyColor =
              pick.urgency?.includes("즉시") ? "var(--color-danger)" :
              pick.urgency?.includes("대기") ? "var(--color-warning)" :
              "var(--color-success)";

            // KR: pick.code, US: pick.ticker
            const identifier = isKR ? pick.code : pick.ticker;
            const marketParam = isKR ? "" : "&market=US";
            const priceLabel = isKR
              ? `₩${pick.current_price?.toLocaleString()}`
              : `$${(pick.current_price || 0).toFixed(2)}`;

            return (
              <div
                key={identifier || idx}
                className="stockcy-card hover-highlight"
                onClick={() => identifier && router.push(`/search?q=${identifier}${marketParam}`)}
                style={{ padding: "14px", borderTop: `3px solid ${urgencyColor}`, background: "rgba(255,255,255,0.02)", cursor: "pointer", display: "flex", flexDirection: "column", gap: "10px" }}
              >
                {/* 카드 상단 */}
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                  <div>
                    <h3 style={{ margin: 0, fontSize: "1rem", fontWeight: 800 }}>{pick.name}</h3>
                    <span style={{ fontSize: "0.75rem", color: "var(--color-muted)" }}>
                      {isKR ? pick.code : pick.ticker}
                    </span>
                  </div>
                  <div style={{ display: "flex", gap: "4px" }}>
                    <span style={{ fontSize: "0.7rem", fontWeight: 700, padding: "2px 6px", background: "rgba(255,255,255,0.1)", borderRadius: "4px" }}>
                      {pick.horizon || "단타"}
                    </span>
                    <span style={{ fontSize: "0.7rem", fontWeight: 700, padding: "2px 6px", background: urgencyColor, color: "var(--bg-color)", borderRadius: "4px" }}>
                      {pick.urgency || "보통"}
                    </span>
                  </div>
                </div>

                {/* 현재가 및 등락률 */}
                <div style={{ display: "flex", alignItems: "baseline", gap: "6px" }}>
                  <span style={{ fontSize: "1.2rem", fontWeight: 800 }}>{priceLabel}</span>
                  <span style={{ fontSize: "0.85rem", fontWeight: 700, color: isUp ? "var(--color-danger)" : "var(--color-primary)" }}>
                    {isUp ? "▲" : "▼"} {Math.abs(pick.change_pct || 0).toFixed(2)}%
                  </span>
                </div>

                {/* 타점 정보 */}
                {(pick.entry || pick.target || pick.stop) && (
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "6px", fontSize: "0.78rem" }}>
                    <div style={{ textAlign: "center", background: "rgba(0,255,0,0.05)", padding: "4px", borderRadius: "4px" }}>
                      <div style={{ color: "var(--color-muted)" }}>매수 타점</div>
                      <div style={{ fontWeight: 700, color: "var(--color-success)" }}>
                        {isKR ? (pick.entry ? `₩${Number(pick.entry).toLocaleString()}` : "—") : (pick.entry ? `$${Number(pick.entry).toFixed(2)}` : "—")}
                      </div>
                    </div>
                    <div style={{ textAlign: "center", background: "rgba(255,200,0,0.05)", padding: "4px", borderRadius: "4px" }}>
                      <div style={{ color: "var(--color-muted)" }}>목표가</div>
                      <div style={{ fontWeight: 700, color: "var(--color-warning)" }}>
                        {isKR ? (pick.target ? `₩${Number(pick.target).toLocaleString()}` : "—") : (pick.target ? `$${Number(pick.target).toFixed(2)}` : "—")}
                      </div>
                    </div>
                    <div style={{ textAlign: "center", background: "rgba(255,0,0,0.05)", padding: "4px", borderRadius: "4px" }}>
                      <div style={{ color: "var(--color-muted)" }}>손절가</div>
                      <div style={{ fontWeight: 700, color: "var(--color-danger)" }}>
                        {isKR ? (pick.stop ? `₩${Number(pick.stop).toLocaleString()}` : "—") : (pick.stop ? `$${Number(pick.stop).toFixed(2)}` : "—")}
                      </div>
                    </div>
                  </div>
                )}

                {/* KR 전용 추가 정보 */}
                {isKR && (pick.position || pick.theme_stage || pick.leader_name) && (
                  <div style={{ display: "flex", gap: "6px", flexWrap: "wrap", fontSize: "0.73rem" }}>
                    {pick.position && (
                      <span style={{ padding: "2px 7px", borderRadius: "4px", background: "rgba(255,200,0,0.1)", border: "1px solid rgba(255,200,0,0.3)", color: "#ffd740" }}>
                        {pick.position}
                      </span>
                    )}
                    {pick.theme_stage && (
                      <span style={{ padding: "2px 7px", borderRadius: "4px", background: "rgba(100,200,100,0.1)", border: "1px solid rgba(100,200,100,0.3)", color: "#69f0ae" }}>
                        {pick.theme_stage}
                      </span>
                    )}
                    {pick.leader_name && (
                      <span style={{ padding: "2px 7px", borderRadius: "4px", background: "rgba(200,100,255,0.1)", border: "1px solid rgba(200,100,255,0.3)", color: "#ce93d8" }}>
                        대장: {pick.leader_name}
                      </span>
                    )}
                    {pick.supply_signal && (
                      <span style={{ padding: "2px 7px", borderRadius: "4px", background: "rgba(100,180,255,0.1)", border: "1px solid rgba(100,180,255,0.3)", color: "#60a5fa" }}>
                        {pick.supply_signal}
                      </span>
                    )}
                  </div>
                )}

                {/* KR 테마 연동 */}
                {isKR && pick.theme_linkage && (
                  <div style={{ fontSize: "0.76rem", color: "#8ecdf7", background: "rgba(100,180,255,0.05)", border: "1px solid rgba(100,180,255,0.15)", borderRadius: "4px", padding: "5px 8px", lineHeight: 1.5 }}>
                    🔗 {pick.theme_linkage}
                  </div>
                )}

                {/* 분석 이유 */}
                <div style={{ fontSize: "0.8rem", color: "var(--color-subtle)", lineHeight: 1.4, background: "rgba(0,0,0,0.2)", padding: "8px", borderRadius: "4px" }}>
                  <span style={{ color: "var(--color-accent)", fontWeight: 700 }}>[{pick.pattern || pick.theme}]</span>{" "}
                  {pick.reason}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
