"use client";
import { BarChart2, TrendingUp, Brain, Map } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { SSEPanel } from "@/components/ui/SSEPanel";
import { Accordion } from "@/components/ui/Accordion";
import { StatusBox } from "@/components/ui/StatusBox";
import { Badge, SignalBadge } from "@/components/ui/Badge";
import { useSSE } from "@/hooks/useSSE";
import useSWR from "swr";
import { api } from "@/lib/api";
import type { DailyBriefing, UsIndices, AiSector } from "@/lib/types";

// ── 미국 지수 타일 ─────────────────────────────────────────────────────────────
function IndexTile({ name, price, changePct }: { name: string; price: number; changePct: number }) {
  const up   = changePct > 0;
  const down = changePct < 0;
  const color = up ? "var(--color-up)" : down ? "var(--color-down)" : "var(--color-flat)";
  return (
    <div className="stockcy-card" style={{ textAlign: "center", padding: "0.875rem" }}>
      <div style={{ color: "var(--color-muted)", fontSize: "0.75rem", marginBottom: "4px" }}>{name}</div>
      <div style={{ fontWeight: 700, fontSize: "1.15rem", marginBottom: "2px" }}>
        {price >= 10000 ? price.toLocaleString() : price.toFixed(2)}
      </div>
      <div style={{ color, fontSize: "0.82rem" }}>
        {up ? "▲" : down ? "▼" : "─"} {Math.abs(changePct).toFixed(2)}%
      </div>
    </div>
  );
}

// ── 주도 섹터 카드 ────────────────────────────────────────────────────────────
function SectorCard({ sector, rank }: { sector: AiSector; rank: number }) {
  return (
    <Accordion
      title={
        <span style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <span style={{
            width: "22px", height: "22px", borderRadius: "50%",
            background: rank === 0 ? "var(--color-accent)" : "var(--color-elevated)",
            color: rank === 0 ? "white" : "var(--color-muted)",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: "0.72rem", fontWeight: 700, flexShrink: 0,
          }}>
            {rank + 1}
          </span>
          {sector.keyword}
          {sector.is_main && <Badge variant="accent">주도</Badge>}
        </span>
      }
      defaultOpen={rank === 0}
    >
      {/* 분석 이유 */}
      <p style={{ color: "var(--color-text)", fontSize: "0.875rem", lineHeight: 1.7, marginBottom: "0.75rem" }}>
        {sector.reason}
      </p>

      {/* 관련 뉴스 */}
      {sector.reference_news_title && (
        <StatusBox type="info">
          <span style={{ fontSize: "0.82rem" }}>
            📰 <a href={sector.reference_news_url} target="_blank" rel="noopener noreferrer"
                  style={{ color: "inherit", textDecoration: "underline" }}>
              {sector.reference_news_title}
            </a>
          </span>
        </StatusBox>
      )}

      {/* 관련 종목 */}
      {sector.related_stocks?.length > 0 && (
        <div style={{ marginTop: "0.75rem" }}>
          <p style={{ color: "var(--color-muted)", fontSize: "0.75rem", marginBottom: "0.4rem" }}>관련 종목</p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.375rem" }}>
            {sector.related_stocks.map((s) => (
              <Badge key={s.ticker} variant="muted">{s.name_kr} ({s.ticker})</Badge>
            ))}
          </div>
        </div>
      )}
    </Accordion>
  );
}

// ── 메인 페이지 ───────────────────────────────────────────────────────────────
export default function MacroPage() {
  const { data: indices } = useSWR<UsIndices>("us-indices", () => api.us.indices() as Promise<UsIndices>, { refreshInterval: 60000 });
  const { status, message, result, fromCache, start } = useSSE<DailyBriefing>("/api/ai/daily-briefing");

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>

      {/* ── 페이지 타이틀 ────────────────────────────────────────────── */}
      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
        <BarChart2 size={18} style={{ color: "var(--color-accent)" }} />
        <h1 style={{ fontSize: "1.05rem", fontWeight: 700 }}>매크로 분석</h1>
      </div>

      {/* ── 미국 지수 4개 타일 ───────────────────────────────────────── */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "0.75rem" }}>
        {["S&P 500", "NASDAQ", "DOW", "VIX"].map((name) => {
          const d = indices?.[name as keyof UsIndices];
          return d
            ? <IndexTile key={name} name={name} price={d.price} changePct={d.change_pct} />
            : <div key={name} className="stockcy-card skeleton" style={{ height: "80px" }} />;
        })}
      </div>

      {/* ── 투 컬럼: 주도 섹터 브리핑 + 마인드맵 ─────────────────────── */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem", alignItems: "start" }}>

        {/* 좌: 주도 섹터 브리핑 */}
        <Card
          title={<span style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}><TrendingUp size={15} style={{ color: "var(--color-accent)" }} />오늘의 주도 섹터</span>}
        >
          <SSEPanel<DailyBriefing>
            status={status}
            message={message}
            result={result}
            fromCache={fromCache}
            onStart={start}
            startLabel="주도 섹터 분석"
            idleHint="버튼을 눌러 Google Search 기반 오늘의 주도 섹터를 분석합니다."
          >
            {(data) =>
              data.error
                ? <StatusBox type="danger">{data.error}</StatusBox>
                : <div>{data.sectors?.map((s, i) => <SectorCard key={i} sector={s} rank={i} />)}</div>
            }
          </SSEPanel>
        </Card>

        {/* 우: 마인드맵 (Step 4에서 완성) */}
        <Card
          title={<span style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}><Map size={15} style={{ color: "var(--color-info)" }} />급등/급락 마인드맵</span>}
        >
          <MindmapPanel />
        </Card>
      </div>

      {/* ── 미국 섹터별 종목 분석 (Step 4에서 완성) ─────────────────── */}
      <Card
        title={<span style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}><Brain size={15} style={{ color: "var(--color-warning)" }} />미국 섹터 종목 개별 분석</span>}
      >
        <StatusBox type="info">
          미국 섹터 맵에서 종목을 선택하면 AI 개별 분석을 시작합니다. (Step 4 구현 예정)
        </StatusBox>
      </Card>
    </div>
  );
}

// ── 마인드맵 패널 (독립 클라이언트 컴포넌트) ─────────────────────────────────
function MindmapPanel() {
  const { status, message, result, start } = useSSE<{ mermaid: string }>("/api/ai/mindmap");

  return (
    <SSEPanel<{ mermaid: string }>
      status={status}
      message={message}
      result={result}
      onStart={start}
      startLabel="마인드맵 생성"
      idleHint="오늘의 급등/급락 인과관계 마인드맵을 생성합니다."
    >
      {(data) => (
        <div style={{ background: "var(--color-elevated)", borderRadius: "0.375rem", padding: "1rem", overflowX: "auto" }}>
          <pre style={{ fontSize: "0.75rem", color: "var(--color-text)", whiteSpace: "pre-wrap", lineHeight: 1.6 }}>
            {data.mermaid}
          </pre>
          <p style={{ fontSize: "0.72rem", color: "var(--color-muted)", marginTop: "0.5rem" }}>
            * Mermaid 다이어그램 — Step 4에서 시각화 렌더러 추가 예정
          </p>
        </div>
      )}
    </SSEPanel>
  );
}
