"use client";
import { useState } from "react";
import { GitBranch, RefreshCw, BarChart2 } from "lucide-react";

export default function ScenariosPage() {
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [scenarioData, setScenarioData] = useState<any>(null);
  const [analyzeMsg, setAnalyzeMsg] = useState("");

  const fetchScenarios = async () => {
    setIsAnalyzing(true);
    setScenarioData(null);
    setAnalyzeMsg("🔍 Google Search로 오늘의 매크로 이슈 분석 중...");

    try {
      const response = await fetch("http://localhost:8000/api/ai/scenarios?use_cache=false");
      if (!response.body) throw new Error("No readable stream");
      
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() || "";
        
        for (const part of parts) {
          if (part.startsWith("data: ")) {
            try {
              const data = JSON.parse(part.slice(6));
              if (data.status === "running") {
                setAnalyzeMsg(data.message);
              } else if (data.status === "done") {
                setScenarioData(data.result);
                setIsAnalyzing(false);
              } else if (data.status === "error") {
                setAnalyzeMsg(`❌ 오류: ${data.message}`);
                setIsAnalyzing(false);
              }
            } catch (e) {}
          }
        }
      }
    } catch (err) {
      setAnalyzeMsg("❌ 분석 중 오류 발생");
      setIsAnalyzing(false);
    }
  };

  return (
    <div style={{ maxWidth: "1400px", margin: "0 auto", padding: "1.5rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
          <div style={{ fontSize: "1.8rem" }}>📈</div>
          <h1 style={{ fontSize: "1.5rem", fontWeight: 800, margin: 0 }}>거시경제 시나리오 분석</h1>
        </div>
        <button className="stockcy-btn stockcy-btn-primary" onClick={fetchScenarios} disabled={isAnalyzing}>
          <RefreshCw size={16} className={isAnalyzing ? "animate-spin" : ""} />
          <span style={{ marginLeft: "8px" }}>{isAnalyzing ? "분석 중..." : "AI 시나리오 생성"}</span>
        </button>
      </div>

      {!scenarioData && !isAnalyzing && (
        <div className="stockcy-card" style={{ height: "400px", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", color: "var(--color-muted)" }}>
          <GitBranch size={48} style={{ marginBottom: "1rem", opacity: 0.5 }} />
          <div style={{ fontSize: "1.1rem" }}>상단의 &apos;AI 시나리오 생성&apos; 버튼을 눌러주세요.</div>
          <div style={{ fontSize: "0.9rem", marginTop: "10px" }}>6대 매크로 핵심 이슈를 실시간으로 스크랩하여 상승/하락 시나리오를 예측합니다.</div>
        </div>
      )}

      {isAnalyzing && (
        <div className="stockcy-card" style={{ padding: "3rem", display: "flex", flexDirection: "column", alignItems: "center" }}>
          <div className="animate-spin" style={{ fontSize: "3rem", marginBottom: "1.5rem" }}>⚙️</div>
          <div style={{ fontSize: "1.2rem", fontWeight: 700, marginBottom: "1rem" }}>{analyzeMsg}</div>
          
          <div style={{ width: "100%", maxWidth: "500px", height: "8px", background: "var(--color-elevated)", borderRadius: "4px", overflow: "hidden" }}>
             <div className="skeleton" style={{ width: "100%", height: "100%" }}></div>
          </div>
          <div style={{ marginTop: "1rem", color: "var(--color-muted)", fontSize: "0.9rem" }}>이 작업은 약 1~2분 정도 소요될 수 있습니다.</div>
        </div>
      )}

      {scenarioData && !isAnalyzing && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: "1.5rem" }}>
          {scenarioData.summary && (
            <div className="stockcy-card" style={{ background: "rgba(28, 131, 225, 0.1)", borderLeft: "4px solid var(--color-info)" }}>
              <h3 style={{ margin: "0 0 10px 0", color: "var(--color-info)", display: "flex", alignItems: "center", gap: "8px" }}>
                <BarChart2 size={18} /> Market Overview
              </h3>
              <p style={{ margin: 0, lineHeight: 1.6 }}>{scenarioData.summary}</p>
            </div>
          )}

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(400px, 1fr))", gap: "1.5rem" }}>
            {scenarioData.issues?.map((issue: Record<string, unknown>, idx: number) => {
              const bull = issue.bull_scenario as string[] | undefined;
              const bear = issue.bear_scenario as string[] | undefined;
              const indicators = issue.key_indicators as string[] | undefined;
              return (
              <div key={idx} className="stockcy-card" style={{ display: "flex", flexDirection: "column" }}>
                <h3 style={{ fontSize: "1.3rem", fontWeight: 800, margin: "0 0 15px 0", color: "var(--color-text)" }}>
                  {String(issue.title ?? "")}
                </h3>

                <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: "10px" }}>
                  <div style={{ background: "rgba(33, 195, 84, 0.05)", border: "1px solid rgba(33, 195, 84, 0.2)", borderRadius: "8px", padding: "12px" }}>
                    <div style={{ color: "var(--color-success)", fontWeight: 700, marginBottom: "8px" }}>📈 긍정적 전개 (Bull)</div>
                    <ul style={{ margin: 0, paddingLeft: "20px", color: "var(--color-text)", fontSize: "0.95rem", lineHeight: 1.5 }}>
                      {bull?.map((s, i) => <li key={i}>{s}</li>)}
                    </ul>
                  </div>

                  <div style={{ background: "rgba(255, 75, 75, 0.05)", border: "1px solid rgba(255, 75, 75, 0.2)", borderRadius: "8px", padding: "12px" }}>
                    <div style={{ color: "var(--color-danger)", fontWeight: 700, marginBottom: "8px" }}>📉 부정적 전개 (Bear)</div>
                    <ul style={{ margin: 0, paddingLeft: "20px", color: "var(--color-text)", fontSize: "0.95rem", lineHeight: 1.5 }}>
                      {bear?.map((s, i) => <li key={i}>{s}</li>)}
                    </ul>
                  </div>
                </div>

                <div style={{ marginTop: "15px", paddingTop: "15px", borderTop: "1px dashed var(--color-border)", fontSize: "0.9rem", color: "var(--color-subtle)" }}>
                  핵심 경제 지표: {indicators?.join(", ")}
                </div>
              </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
