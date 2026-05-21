"use client";
import { useState, useEffect } from "react";
import { Activity, Flame, Layers, ArrowUpRight, ArrowDownRight, Wind, Loader2 } from "lucide-react";
import { connectSSE } from "@/lib/api";
import ReactMarkdown from "react-markdown";

export default function TrackingPage() {
  const [viewMode, setViewMode] = useState("AI 분석");
  const [loading, setLoading] = useState(true);
  const [statusMsg, setStatusMsg] = useState("AI 분석 준비 중...");
  const [report, setReport] = useState<string>("");

  useEffect(() => {
    if (viewMode !== "AI 분석") return;
    
    let unmounted = false;
    setLoading(true);
    setStatusMsg("시장 데이터를 수집 중...");

    connectSSE(
      "/api/ai/sector-rotation",
      (evt) => {
        if (unmounted) return;
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
    ).catch(err => {
      if (!unmounted) {
        setStatusMsg("서버 연결 실패");
        setLoading(false);
      }
    });

    return () => { unmounted = true; };
  }, [viewMode]);

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

      {/* 테마 흐름 요약 미니 패널 (가로로 길게) */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: "10px", marginBottom: "0.5rem" }}>
        <div className="stockcy-card" style={{ padding: "10px", display: "flex", flexDirection: "column", gap: "4px" }}>
          <span style={{ fontSize: "0.75rem", color: "var(--color-muted)" }}><Flame size={12}/> 주도 (과열)</span>
          <span style={{ fontSize: "0.9rem", fontWeight: 800, color: "var(--color-danger)" }}>반도체 장비</span>
        </div>
        <div className="stockcy-card" style={{ padding: "10px", display: "flex", flexDirection: "column", gap: "4px" }}>
          <span style={{ fontSize: "0.75rem", color: "var(--color-muted)" }}><Layers size={12}/> 확산 진행</span>
          <span style={{ fontSize: "0.9rem", fontWeight: 800, color: "var(--color-warning)" }}>AI 전력설비 / 전선</span>
        </div>
        <div className="stockcy-card" style={{ padding: "10px", display: "flex", flexDirection: "column", gap: "4px" }}>
          <span style={{ fontSize: "0.75rem", color: "var(--color-muted)" }}><ArrowUpRight size={12}/> 신규 진입</span>
          <span style={{ fontSize: "0.9rem", fontWeight: 800, color: "var(--color-success)" }}>자율주행 / 로봇</span>
        </div>
        <div className="stockcy-card" style={{ padding: "10px", display: "flex", flexDirection: "column", gap: "4px" }}>
          <span style={{ fontSize: "0.75rem", color: "var(--color-muted)" }}><Wind size={12}/> 소멸 (차익실현)</span>
          <span style={{ fontSize: "0.9rem", fontWeight: 800, color: "var(--color-primary)" }}>초전도체</span>
        </div>
        <div className="stockcy-card" style={{ padding: "10px", display: "flex", flexDirection: "column", gap: "4px" }}>
          <span style={{ fontSize: "0.75rem", color: "var(--color-muted)" }}><ArrowDownRight size={12}/> 역배열 지속</span>
          <span style={{ fontSize: "0.9rem", fontWeight: 800, color: "var(--color-subtle)" }}>건설 / 철강</span>
        </div>
      </div>

      {/* 2단 캔버스: 트리맵 & 리스트 영역 */}
      <div style={{ display: "grid", gridTemplateColumns: viewMode === "트리맵" ? "7fr 3fr" : "1fr", gap: "1rem", minHeight: "600px" }}>
        
        {/* 좌측: 거대한 트리맵 뷰 (가상 렌더링) */}
        {viewMode === "트리맵" && (
          <div className="stockcy-card" style={{ padding: "10px", display: "flex", flexDirection: "column", gap: "8px" }}>
            <div style={{ fontSize: "0.85rem", fontWeight: 700, color: "var(--color-muted)", paddingLeft: "4px" }}>
              시장 자금 지도 (시가총액 및 등락률 비례)
            </div>
            {/* 트리맵 가상 박스들 */}
            <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1.5fr", gridTemplateRows: "2fr 1.5fr", gap: "4px", flex: 1 }}>
              {/* 반도체 */}
              <div style={{ background: "rgba(255, 60, 60, 0.15)", border: "1px solid rgba(255, 60, 60, 0.3)", borderRadius: "4px", padding: "1rem", display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "center", gridRow: "span 2" }}>
                <div style={{ fontSize: "1.4rem", fontWeight: 800, color: "var(--color-danger)" }}>반도체 장비</div>
                <div style={{ fontSize: "1rem", fontWeight: 700, color: "var(--color-danger)" }}>+4.2%</div>
                <div style={{ fontSize: "0.75rem", color: "var(--color-subtle)", marginTop: "8px" }}>한미반도체, HPSP, 이수페타시스</div>
              </div>
              {/* 전력설비 */}
              <div style={{ background: "rgba(255, 180, 50, 0.15)", border: "1px solid rgba(255, 180, 50, 0.3)", borderRadius: "4px", padding: "1rem", display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "center" }}>
                <div style={{ fontSize: "1.1rem", fontWeight: 800, color: "var(--color-warning)" }}>AI 전력설비</div>
                <div style={{ fontSize: "0.9rem", fontWeight: 700, color: "var(--color-warning)" }}>+2.8%</div>
                <div style={{ fontSize: "0.75rem", color: "var(--color-subtle)", marginTop: "4px" }}>HD현대일렉, 제룡전기</div>
              </div>
              {/* 자동차 */}
              <div style={{ background: "rgba(100, 100, 100, 0.1)", border: "1px solid rgba(100, 100, 100, 0.2)", borderRadius: "4px", padding: "1rem", display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "center" }}>
                <div style={{ fontSize: "1rem", fontWeight: 800, color: "var(--color-text)" }}>자동차 부품</div>
                <div style={{ fontSize: "0.85rem", fontWeight: 700 }}>+0.5%</div>
              </div>
              {/* 바이오 */}
              <div style={{ background: "rgba(50, 200, 100, 0.15)", border: "1px solid rgba(50, 200, 100, 0.3)", borderRadius: "4px", padding: "1rem", display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "center" }}>
                <div style={{ fontSize: "1rem", fontWeight: 800, color: "var(--color-success)" }}>ADC / 비만약</div>
                <div style={{ fontSize: "0.85rem", fontWeight: 700, color: "var(--color-success)" }}>+1.5%</div>
              </div>
              {/* 2차전지 */}
              <div style={{ background: "rgba(50, 150, 255, 0.15)", border: "1px solid rgba(50, 150, 255, 0.3)", borderRadius: "4px", padding: "1rem", display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "center" }}>
                <div style={{ fontSize: "1rem", fontWeight: 800, color: "var(--color-primary)" }}>2차전지 소재</div>
                <div style={{ fontSize: "0.85rem", fontWeight: 700, color: "var(--color-primary)" }}>-2.1%</div>
                <div style={{ fontSize: "0.75rem", color: "var(--color-subtle)", marginTop: "4px" }}>에코프로, 엔켐</div>
              </div>
            </div>
          </div>
        )}

        {/* 우측(또는 전체): 빽빽한 테마 리스트 (테이블) */}
        {viewMode === "상세 리스트" && (
          <div className="stockcy-card" style={{ padding: "12px", overflowY: "auto", display: "flex", flexDirection: "column", gap: "8px" }}>
            <div style={{ fontSize: "0.85rem", fontWeight: 700, color: "var(--color-muted)", paddingLeft: "4px", borderBottom: "1px solid rgba(255,255,255,0.05)", paddingBottom: "8px" }}>
              실시간 테마 랭킹
            </div>
            <table style={{ width: "100%", fontSize: "0.8rem", textAlign: "left", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ color: "var(--color-subtle)", borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
                  <th style={{ padding: "6px" }}>순위</th>
                  <th style={{ padding: "6px" }}>테마명</th>
                  <th style={{ padding: "6px" }}>등락률</th>
                  <th style={{ padding: "6px" }}>주도주</th>
                </tr>
              </thead>
              <tbody>
                {[
                  { rank: 1, name: "반도체 장비", change: 4.2, lead: "한미반도체, HPSP" },
                  { rank: 2, name: "AI 전력설비", change: 2.8, lead: "HD현대일렉" },
                  { rank: 3, name: "자율주행", change: 1.5, lead: "스마트레이더" },
                  { rank: 4, name: "화장품", change: 1.2, lead: "실리콘투, 브이티" },
                  { rank: 5, name: "우주항공", change: 0.8, lead: "AP위성" },
                  { rank: 6, name: "로봇", change: 0.5, lead: "레인보우로보틱스" },
                  { rank: 7, name: "엔터", change: -0.5, lead: "하이브, JYP" },
                  { rank: 8, name: "2차전지 소재", change: -2.1, lead: "에코프로비엠" },
                  { rank: 9, name: "초전도체", change: -4.5, lead: "신성델타테크" },
                ].map(t => (
                  <tr key={t.rank} style={{ borderBottom: "1px solid rgba(255,255,255,0.02)", background: t.change > 0 ? "rgba(255, 60, 60, 0.05)" : t.change < 0 ? "rgba(50, 150, 255, 0.05)" : "transparent" }}>
                    <td style={{ padding: "8px 6px", fontWeight: 800 }}>{t.rank}</td>
                    <td style={{ padding: "8px 6px", fontWeight: 700 }}>{t.name}</td>
                    <td style={{ padding: "8px 6px", fontWeight: 800, color: t.change > 0 ? "var(--color-danger)" : t.change < 0 ? "var(--color-primary)" : "var(--color-text)" }}>
                      {t.change > 0 ? "+" : ""}{t.change}%
                    </td>
                    <td style={{ padding: "8px 6px", color: "var(--color-muted)" }}>{t.lead}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* AI 분석 리포트 모드 */}
        {viewMode === "AI 분석" && (
          <div className="stockcy-card" style={{ padding: "2rem", display: "flex", flexDirection: "column", gap: "1rem", minHeight: "500px", gridColumn: "1 / -1" }}>
            {loading ? (
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", gap: "1rem", minHeight: "300px" }}>
                <Loader2 className="animate-spin" size={40} color="var(--color-accent)" />
                <div style={{ color: "var(--color-muted)", fontSize: "0.9rem", fontWeight: 600 }}>{statusMsg}</div>
              </div>
            ) : (
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
            )}
          </div>
        )}

      </div>

    </div>
  );
}
