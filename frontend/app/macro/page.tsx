"use client";
import { useState } from "react";
import { BarChart2, TrendingUp, Map, Zap, Search } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { SSEPanel } from "@/components/ui/SSEPanel";
import { Accordion } from "@/components/ui/Accordion";
import { StatusBox } from "@/components/ui/StatusBox";
import { Badge } from "@/components/ui/Badge";
import { StockModal } from "@/components/ui/StockModal";
import type { StockInfo } from "@/components/ui/StockModal";
import { useSSE } from "@/hooks/useSSE";
import useSWR from "swr";
import { api } from "@/lib/api";
import type { DailyBriefing, UsIndices, AiSector, HotStockUs, StockReport } from "@/lib/types";

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
function SectorCard({ sector, rank, onStockClick }: {
  sector:       AiSector;
  rank:         number;
  onStockClick: (info: StockInfo) => void;
}) {
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
      <p style={{ color: "var(--color-text)", fontSize: "0.875rem", lineHeight: 1.7, marginBottom: "0.75rem" }}>
        {sector.reason}
      </p>

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

      {sector.related_stocks?.length > 0 && (
        <div style={{ marginTop: "0.75rem" }}>
          <p style={{ color: "var(--color-muted)", fontSize: "0.75rem", marginBottom: "0.4rem" }}>관련 종목 (클릭하면 AI 분석)</p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.375rem" }}>
            {sector.related_stocks.map((s) => (
              <button
                key={s.ticker}
                className="stockcy-btn stockcy-btn-secondary"
                style={{ padding: "2px 10px", fontSize: "0.78rem" }}
                onClick={() => onStockClick({ code: s.ticker, name: s.name_kr || s.ticker, market: "미국" })}
              >
                {s.name_kr} ({s.ticker})
              </button>
            ))}
          </div>
        </div>
      )}
    </Accordion>
  );
}

// ── 미국 단타 핫 종목 결과 ────────────────────────────────────────────────────
function HotStockCard({ data, onAnalyze }: { data: HotStockUs; onAnalyze: () => void }) {
  const analysis = useSSE<StockReport>("/api/ai/stock-report", { method: "POST", globalId: `report-${data.ticker}`, globalTitle: `${data.verified_name || data.ticker} 시나리오 분석` });
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      {data.error && <StatusBox type="danger">{data.error}</StatusBox>}

      {!data.error && (
        <>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
            <span style={{ fontWeight: 700, fontSize: "1.1rem" }}>{data.ticker}</span>
            <span style={{ color: "var(--color-muted)", fontSize: "0.85rem" }}>{data.verified_name}</span>
            {data.name_kr && <Badge variant="muted">{data.name_kr}</Badge>}
            {data.ticker_verified && <Badge variant="success">거래 확인됨</Badge>}
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "0.5rem" }}>
            {[
              { label: "매수 타점", value: data.buy_target,  color: "var(--color-info)" },
              { label: "목표가",   value: data.sell_target, color: "var(--color-up)" },
              { label: "손절가",   value: data.stop_loss,   color: "var(--color-down)" },
            ].map(item => (
              <div key={item.label} style={{ background: "var(--color-elevated)", borderRadius: "0.375rem", padding: "0.5rem" }}>
                <div style={{ fontSize: "0.68rem", color: "var(--color-muted)" }}>{item.label}</div>
                <div style={{ fontSize: "0.8rem", fontWeight: 600, color: item.color }}>{item.value}</div>
              </div>
            ))}
          </div>

          <Accordion title="선정 이유">
            <p style={{ fontSize: "0.83rem", lineHeight: 1.75, whiteSpace: "pre-wrap" }}>{data.reasoning}</p>
          </Accordion>
        </>
      )}
    </div>
  );
}

// ── 마인드맵 패널 ─────────────────────────────────────────────────────────────
function MindmapPanel() {
  const { status, message, result, start } = useSSE<{ mermaid: string }>("/api/ai/mindmap", { globalId: "macro-mindmap", globalTitle: "거시경제 마인드맵" });
  return (
    <SSEPanel<{ mermaid: string }>
      status={status} message={message} result={result}
      onStart={start} startLabel="마인드맵 생성"
      idleHint="오늘의 급등/급락 인과관계 마인드맵을 생성합니다."
    >
      {(data) => (
        <div style={{ background: "var(--color-elevated)", borderRadius: "0.375rem", padding: "1rem", overflowX: "auto" }}>
          <pre style={{ fontSize: "0.75rem", color: "var(--color-text)", whiteSpace: "pre-wrap", lineHeight: 1.6 }}>
            {data.mermaid}
          </pre>
        </div>
      )}
    </SSEPanel>
  );
}

// ── 메인 페이지 ───────────────────────────────────────────────────────────────
export default function MacroPage() {
  const [selectedStock, setSelectedStock] = useState<StockInfo | null>(null);
  const { data: indices } = useSWR<UsIndices>("us-indices", () => api.us.indices() as Promise<UsIndices>, { refreshInterval: 60000 });
  const briefing = useSSE<DailyBriefing>("/api/ai/daily-briefing", { globalId: "daily-brief", globalTitle: "데일리 매크로 브리핑" });
  const hotStock = useSSE<HotStockUs>("/api/ai/hot-stock-us", { method: "POST", globalId: "hot-stock", globalTitle: "오늘의 핫스톡" });

  // 단타 핫 종목 — 주도 섹터 컨텍스트 함께 전달
  const handleHotStock = () => {
    const ctx = briefing.result?.sectors?.slice(0, 3).map(s => s.keyword).join(", ") ?? "";
    hotStock.start({ context: ctx });
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>

      {selectedStock && (
        <StockModal stock={selectedStock} onClose={() => setSelectedStock(null)} />
      )}

      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
        <BarChart2 size={18} style={{ color: "var(--color-accent)" }} />
        <h1 style={{ fontSize: "1.05rem", fontWeight: 700 }}>매크로 분석</h1>
      </div>

      {/* ── 미국 지수 4개 타일 ─────────────────────────────────────────── */}
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
        <Card title={<span style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}><TrendingUp size={15} style={{ color: "var(--color-accent)" }} />오늘의 주도 섹터</span>}>
          <SSEPanel<DailyBriefing>
            status={briefing.status} message={briefing.message}
            result={briefing.result} fromCache={briefing.fromCache}
            onStart={briefing.start} startLabel="주도 섹터 분석"
            idleHint="Google Search 기반 오늘의 주도 섹터를 분석합니다."
          >
            {(data) =>
              data.error
                ? <StatusBox type="danger">{data.error}</StatusBox>
                : <div>{data.sectors?.map((s, i) => (
                    <SectorCard key={i} sector={s} rank={i} onStockClick={setSelectedStock} />
                  ))}</div>
            }
          </SSEPanel>
        </Card>

        <Card title={<span style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}><Map size={15} style={{ color: "var(--color-info)" }} />급등/급락 마인드맵</span>}>
          <MindmapPanel />
        </Card>
      </div>

      {/* ── 미국 단타 핫 종목 ─────────────────────────────────────────── */}
      <Card title={<span style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}><Zap size={15} style={{ color: "var(--color-warning)" }} />오늘의 미국 단타 핫 종목</span>}>
        <SSEPanel<HotStockUs>
          status={hotStock.status} message={hotStock.message}
          result={hotStock.result} fromCache={hotStock.fromCache}
          onStart={handleHotStock} startLabel="핫 종목 발굴"
          idleHint="Google Search로 오늘 거래량·모멘텀이 가장 강한 미국 단타 유망주 1개를 발굴합니다. (1~2분 소요)"
        >
          {(data) => <HotStockCard data={data} onAnalyze={() => setSelectedStock({ code: data.ticker, name: data.verified_name || data.ticker, market: "미국" })} />}
        </SSEPanel>
      </Card>

      {/* ── 미국 종목 개별 분석 ───────────────────────────────────────── */}
      <Card title={<span style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}><Search size={15} style={{ color: "var(--color-accent)" }} />미국 종목 개별 분석</span>}>
        <UsStockSearch onSelect={setSelectedStock} />
      </Card>
    </div>
  );
}

// ── 미국 종목 직접 검색 & 분석 ──────────────────────────────────────────────
function UsStockSearch({ onSelect }: { onSelect: (s: StockInfo) => void }) {
  const [ticker, setTicker] = useState("");
  const [name,   setName]   = useState("");

  const handleOpen = () => {
    const t = ticker.trim().toUpperCase();
    if (!t) return;
    onSelect({ code: t, name: name.trim() || t, market: "미국" });
    setTicker(""); setName("");
  };

  return (
    <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", flexWrap: "wrap" }}>
      <input
        className="stockcy-input"
        placeholder="티커 (예: NVDA, AAPL)"
        value={ticker}
        onChange={e => setTicker(e.target.value)}
        onKeyDown={e => e.key === "Enter" && handleOpen()}
        style={{ width: "140px", flexShrink: 0 }}
      />
      <input
        className="stockcy-input"
        placeholder="종목명 (선택)"
        value={name}
        onChange={e => setName(e.target.value)}
        onKeyDown={e => e.key === "Enter" && handleOpen()}
        style={{ flex: 1, minWidth: "120px" }}
      />
      <button
        className="stockcy-btn stockcy-btn-primary"
        onClick={handleOpen}
        disabled={!ticker.trim()}
        style={{ whiteSpace: "nowrap" }}
      >
        AI 분석
      </button>
      <span style={{ fontSize: "0.75rem", color: "var(--color-muted)" }}>
        주도 섹터 관련 종목은 위 섹터 카드에서 바로 클릭할 수 있습니다.
      </span>
    </div>
  );
}
