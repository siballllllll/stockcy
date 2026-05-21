"use client";
import { BarChart2 } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { SSEPanel } from "@/components/ui/SSEPanel";
import { useSSE } from "@/hooks/useSSE";

export default function SectorsPage() {
  const rotation = useSSE<string>("/api/ai/sector-rotation");

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
        <BarChart2 size={18} style={{ color: "var(--color-accent)" }} />
        <h1 style={{ fontSize: "1.05rem", fontWeight: 700 }}>섹터 순환매 로드맵</h1>
      </div>

      <Card title="AI 섹터 로테이션 분석">
        <SSEPanel<string>
          status={rotation.status}
          message={rotation.message}
          result={rotation.result}
          fromCache={rotation.fromCache}
          onStart={rotation.start}
          startLabel="섹터 로테이션 분석 시작"
          idleHint="실시간 시장 데이터(거래량·등락률·수급)를 기반으로 현재 주도 섹터와 다음 자금 이동 경로, 투자 성향별 추천 종목을 분석합니다. (1~2분 소요)"
        >
          {(data) => (
            <pre style={{
              whiteSpace: "pre-wrap",
              fontSize:   "0.83rem",
              lineHeight: 1.8,
              color:      "var(--color-text)",
              fontFamily: "inherit",
            }}>
              {data}
            </pre>
          )}
        </SSEPanel>
      </Card>
    </div>
  );
}
