"use client";
import { useState } from "react";
import { Activity, Flame, Layers, ArrowUpRight, ArrowDownRight, Wind, Loader2 } from "lucide-react";
import { connectSSE } from "@/lib/api";
import { api } from "@/lib/api";
import useSWR from "swr";
import ReactMarkdown from "react-markdown";

export default function TrackingPage() {
  const [viewMode, setViewMode] = useState("AI 분석");
  const [loading, setLoading] = useState(false);
  const [statusMsg, setStatusMsg] = useState("");
  const [report, setReport] = useState<string>("");

  // ── 핫 섹터 데이터 (트리맵 / 상세 리스트 모드용) ──────────────────────────
  const { data: hotSectors } = useSWR(
    "/api/kr/hot-sectors",
    () => api.kr.hotSectors(),
    { revalidateOnFocus: false }
  ) as { data: any };

  const sectors: any[] = (hotSectors as any)?.sectors ?? [];

  // 핫 스코어 기준으로 분류
  const topSectors    = [...sectors].sort((a, b) => (b.hot_score ?? 0) - (a.hot_score ?? 0));
  const leadSector    = topSectors[0];
  const spreadSectors = topSectors.filter(s => (s.hot_score ?? 0) >= 7 && (s.hot_score ?? 0) < 9);
  const newSectors    = topSectors.filter(s => (s.hot_score ?? 0) >= 5 && (s.hot_score ?? 0) < 7);
  const coolSectors   = topSectors.filter(s => (s.hot_score ?? 0) < 5);

  const startAnalysis = () => {
    setLoading(true);
    setStatusMsg("시장 데이터를 수집 중...");
    setReport("");

    connectSSE(
      "/api/ai/sector-rotation",
      (evt) => {
        if (evt.status === "running") {
          setStatusMsg(evt.message || "분석 중...");
        } else if (evt.status === "done") {
          setReport((evt.result as any) || "데이터가 없습니다.");
          setLoading(false);
        } else if (evt.status === "error") {
          setStatusMsg(`오류 발생: ${evt.message}`);
          setLoading(false);
        }
      }
    ).catch(() => {
      setStatusMsg("서버 연결 실패");
      setLoading(false);
    });
  };

  return (
    <div style={{ width: "100%", margin: "0 auto", display: "flex", flexDirection: "column", gap: "1rem" }}>

      {/* 상단 헤더 영역 */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", borderBottom: "1px solid rgba(255,255,255,0.05)", paddingBottom: "1rem" }}>
        <div>
          <h1 style={{ fontSize: "1.6rem", fontWeight: 800, margin: "0 0 0.5rem 0", display: "flex", alignItems: "center", gap: "8px" }}>
            <Activity color="var(--color-primary)" /> 주도 테마 실시간 추적기
          </h1>
          <div style={{ fontSize: "0.85rem", color: "var(--color-muted)" }}>
            당일 시장 자금의 쏠림 현상과 테마의 순환매 흐름을 추적합니다.
          </div>
        </div>

        {/* 뷰 모드 토글 */}
        <div style={{ display: "flex", gap: "6px" }}>
          {["AI 분석", "트리맵", "상세 리스트"].map(mode => (
            <button
              key={mode}
              onClick={() => setViewMode(mode)}
              style={{
                padding: "6px 12px",
                fontSize: "0.85rem",
                fontWeight: 700,
                borderRadius: "4px",
                border: "1px solid",
                borderColor: viewMode === mode ? "var(--color-accent)" : "var(--color-border)",
                background: viewMode === mode ? "rgba(255,255,255,0.1)" : "transparent",
                color: viewMode === mode ? "var(--color-text)" : "var(--color-muted)",
                cursor: "pointer",
                transition: "0.2s"
              }}
            >
              {mode}
            </button>
          ))}
        </div>
      </div>

      {/* 테마 흐름 요약 미니 패널 */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: "10px", marginBottom: "0.5rem" }}>
        <MiniPanel icon={<Flame size={12}/>} label="주도 (과열)" color="var(--color-danger)">
          {leadSector?.keyword ?? "—"}
        </MiniPanel>
        <MiniPanel icon={<Layers size={12}/>} label="확산 진행" color="var(--color-warning)">
          {spreadSectors.slice(0, 2).map(s => s.keyword).join(" / ") || "—"}
        </MiniPanel>
        <MiniPanel icon={<ArrowUpRight size={12}/>} label="신규 진입" color="var(--color-success)">
          {newSectors.slice(0, 2).map(s => s.keyword).join(" / ") || "—"}
        </MiniPanel>
        <MiniPanel icon={<Wind size={12}/>} label="관망" color="var(--color-primary)">
          {coolSectors.slice(0, 1).map(s => s.keyword).join("") || "—"}
        </MiniPanel>
        <MiniPanel icon={<ArrowDownRight size={12}/>} label="총 섹터" color="var(--color-subtle)">
          {sectors.length > 0 ? `${sectors.length}개` : "—"}
        </MiniPanel>
      </div>

      {/* 뷰 모드별 콘텐츠 */}
      <div style={{ display: "grid", gridTemplateColumns: viewMode === "트리맵" ? "7fr 3fr" : "1fr", gap: "1rem", minHeight: "500px" }}>

        {/* 트리맵 뷰 */}
        {viewMode === "트리맵" && (
          <div className="stockcy-card" style={{ padding: "10px", display: "flex", flexDirection: "column", gap: "8px" }}>
            <div style={{ fontSize: "0.85rem", fontWeight: 700, color: "var(--color-muted)", paddingLeft: "4px" }}>
              시장 자금 지도 (핫스코어 비례)
            </div>
            {sectors.length === 0 ? (
              <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--color-muted)", fontSize: "0.9rem" }}>
                섹터 데이터 로딩 중...
              </div>
            ) : (
              <TreemapGrid sectors={topSectors} />
            )}
          </div>
        )}

        {/* 상세 리스트 */}
        {viewMode === "상세 리스트" && (
          <div className="stockcy-card" style={{ padding: "12px", overflowY: "auto", display: "flex", flexDirection: "column", gap: "8px" }}>
            <div style={{ fontSize: "0.85rem", fontWeight: 700, color: "var(--color-muted)", paddingLeft: "4px", borderBottom: "1px solid rgba(255,255,255,0.05)", paddingBottom: "8px" }}>
              AI 핫 섹터 랭킹 {sectors.length > 0 ? `(${sectors.length}개)` : ""}
            </div>
            {sectors.length === 0 ? (
              <div style={{ textAlign: "center", padding: "2rem", color: "var(--color-muted)" }}>섹터 데이터 로딩 중...</div>
            ) : (
              <table style={{ width: "100%", fontSize: "0.8rem", textAlign: "left", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ color: "var(--color-subtle)", borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
                    <th style={{ padding: "6px" }}>순위</th>
                    <th style={{ padding: "6px" }}>섹터명</th>
                    <th style={{ padding: "6px" }}>핫스코어</th>
                    <th style={{ padding: "6px" }}>이유</th>
                  </tr>
                </thead>
                <tbody>
                  {topSectors.map((s: any, i: number) => {
                    const score = s.hot_score ?? 0;
                    const color = score >= 8 ? "var(--color-danger)" : score >= 6 ? "var(--color-warning)" : score >= 4 ? "var(--color-success)" : "var(--color-muted)";
                    return (
                      <tr key={i} style={{ borderBottom: "1px solid rgba(255,255,255,0.02)", background: score >= 8 ? "rgba(255,60,60,0.05)" : "transparent" }}>
                        <td style={{ padding: "8px 6px", fontWeight: 800, color: "var(--color-muted)" }}>{i + 1}</td>
                        <td style={{ padding: "8px 6px", fontWeight: 700 }}>
                          {s.keyword}
                          {i === 0 && <span style={{ marginLeft: "6px", fontSize: "0.7rem", background: "rgba(255,60,60,0.2)", border: "1px solid rgba(255,60,60,0.4)", color: "#ff4b4b", borderRadius: "3px", padding: "1px 4px" }}>주도</span>}
                        </td>
                        <td style={{ padding: "8px 6px", fontWeight: 800, color }}>
                          {"🔥".repeat(Math.max(1, Math.min(Math.floor(score / 2.5), 4)))} {score}/10
                        </td>
                        <td style={{ padding: "8px 6px", color: "var(--color-muted)", fontSize: "0.75rem", maxWidth: "240px" }}>
                          {String(s.reason ?? "").slice(0, 60)}{String(s.reason ?? "").length > 60 ? "..." : ""}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        )}

        {/* AI 분석 리포트 모드 */}
        {viewMode === "AI 분석" && (
          <div className="stockcy-card" style={{ padding: "2rem", display: "flex", flexDirection: "column", gap: "1rem", minHeight: "500px", gridColumn: "1 / -1" }}>
            {!report && !loading && (
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", gap: "1rem", minHeight: "300px" }}>
                <Activity size={48} style={{ opacity: 0.3 }} />
                <div style={{ color: "var(--color-muted)", fontSize: "0.9rem" }}>
                  AI가 실시간 시장 데이터를 수집·분석하여 현재 자금 흐름과 섹터 순환매 경로를 파악합니다.
                </div>
                <button className="stockcy-btn stockcy-btn-primary" onClick={startAnalysis}>
                  🔄 섹터 순환매 분석 시작
                </button>
              </div>
            )}
            {loading && (
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", gap: "1rem", minHeight: "300px" }}>
                <Loader2 className="animate-spin" size={40} color="var(--color-accent)" />
                <div style={{ color: "var(--color-muted)", fontSize: "0.9rem", fontWeight: 600 }}>{statusMsg}</div>
              </div>
            )}
            {report && !loading && (
              <>
                <div style={{ display: "flex", justifyContent: "flex-end" }}>
                  <button className="stockcy-btn stockcy-btn-secondary" onClick={startAnalysis} style={{ fontSize: "0.82rem" }}>
                    🔄 다시 분석
                  </button>
                </div>
                <div style={{ fontSize: "0.95rem", lineHeight: 1.7, color: "var(--color-text)" }}>
                  <ReactMarkdown
                    components={{
                      h1: ({node, ...props}) => <h1 style={{ fontSize: "1.4rem", fontWeight: 800, borderBottom: "1px solid rgba(255,255,255,0.1)", paddingBottom: "8px", marginBottom: "16px", color: "var(--color-accent)" }} {...props} />,
                      h2: ({node, ...props}) => <h2 style={{ fontSize: "1.2rem", fontWeight: 800, marginTop: "24px", marginBottom: "12px", color: "var(--color-text)" }} {...props} />,
                      h3: ({node, ...props}) => <h3 style={{ fontSize: "1.05rem", fontWeight: 700, marginTop: "20px", marginBottom: "10px" }} {...props} />,
                      ul: ({node, ...props}) => <ul style={{ paddingLeft: "20px", marginBottom: "16px", display: "flex", flexDirection: "column", gap: "6px" }} {...props} />,
                      li: ({node, ...props}) => <li style={{ color: "var(--color-subtle)" }} {...props} />,
                      p: ({node, ...props}) => <p style={{ marginBottom: "16px", color: "var(--color-subtle)" }} {...props} />,
                      strong: ({node, ...props}) => <strong style={{ color: "var(--color-text)", fontWeight: 800 }} {...props} />
                    }}
                  >
                    {report}
                  </ReactMarkdown>
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ── 미니 상태 패널 ────────────────────────────────────────────────────────────
function MiniPanel({ icon, label, color, children }: { icon: React.ReactNode; label: string; color: string; children: React.ReactNode }) {
  return (
    <div className="stockcy-card" style={{ padding: "10px", display: "flex", flexDirection: "column", gap: "4px" }}>
      <span style={{ fontSize: "0.75rem", color: "var(--color-muted)", display: "flex", alignItems: "center", gap: "4px" }}>{icon} {label}</span>
      <span style={{ fontSize: "0.88rem", fontWeight: 800, color, wordBreak: "keep-all" }}>{children}</span>
    </div>
  );
}

// ── 트리맵 그리드 ──────────────────────────────────────────────────────────────
function TreemapGrid({ sectors }: { sectors: any[] }) {
  const top = sectors.slice(0, 6);

  const scoreColor = (score: number) => {
    if (score >= 8) return { bg: "rgba(255,60,60,0.15)", border: "rgba(255,60,60,0.35)", text: "var(--color-danger)" };
    if (score >= 6) return { bg: "rgba(255,180,50,0.15)", border: "rgba(255,180,50,0.35)", text: "var(--color-warning)" };
    if (score >= 4) return { bg: "rgba(50,200,100,0.12)", border: "rgba(50,200,100,0.3)", text: "var(--color-success)" };
    return { bg: "rgba(100,100,100,0.08)", border: "rgba(100,100,100,0.2)", text: "var(--color-muted)" };
  };

  // 첫 번째 섹터는 크게, 나머지는 작게
  return (
    <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1.5fr", gridTemplateRows: "2fr 1.5fr", gap: "6px", flex: 1, minHeight: "400px" }}>
      {top.map((s: any, i: number) => {
        const { bg, border, text } = scoreColor(s.hot_score ?? 0);
        const fires = "🔥".repeat(Math.max(1, Math.min(Math.floor((s.hot_score ?? 0) / 2.5), 4)));
        return (
          <div
            key={i}
            style={{
              background: bg, border: `1px solid ${border}`, borderRadius: "6px",
              padding: "1rem", display: "flex", flexDirection: "column",
              justifyContent: "center", alignItems: "center",
              gridRow: i === 0 ? "span 2" : undefined,
              textAlign: "center",
            }}
          >
            <div style={{ fontSize: i === 0 ? "1.3rem" : "1rem", fontWeight: 800, color: text }}>{s.keyword}</div>
            <div style={{ fontSize: i === 0 ? "0.95rem" : "0.8rem", fontWeight: 700, color: text, margin: "4px 0" }}>{fires} {s.hot_score}/10</div>
            {i === 0 && s.reason && (
              <div style={{ fontSize: "0.78rem", color: "var(--color-muted)", marginTop: "8px", lineHeight: 1.4 }}>
                {String(s.reason).slice(0, 80)}...
              </div>
            )}
            {s.hot_codes?.length > 0 && (
              <div style={{ fontSize: "0.72rem", color: "var(--color-subtle)", marginTop: "6px" }}>
                {s.hot_codes.slice(0, 3).join(", ")}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
