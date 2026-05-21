"use client";
import { useState } from "react";
import { GitBranch, Search, TrendingUp, TrendingDown, BookOpen } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { SSEPanel } from "@/components/ui/SSEPanel";
import { Accordion } from "@/components/ui/Accordion";
import { Badge, SignalBadge, DirectionBadge, UrgencyBadge } from "@/components/ui/Badge";
import { StatusBox } from "@/components/ui/StatusBox";
import { useSSE } from "@/hooks/useSSE";
import type { MarketScenarios, MacroIssue, Scenario, ScenarioStock } from "@/lib/types";

// ── 종목 행 ────────────────────────────────────────────────────────────────────
function StockRow({ stock }: { stock: ScenarioStock }) {
  const isKr = /^\d{6}$/.test(stock.ticker);
  return (
    <tr>
      <td>
        <span style={{ fontWeight: 500 }}>{stock.name}</span>
        <span style={{ color: "var(--color-subtle)", fontSize: "0.72rem", marginLeft: "4px" }}>({stock.ticker})</span>
        {isKr && <span style={{ fontSize: "0.68rem", color: "var(--color-muted)", marginLeft: "4px" }}>KR</span>}
      </td>
      <td style={{ fontSize: "0.82rem", color: "var(--color-muted)" }}>{stock.reason}</td>
      <td><SignalBadge signal={stock.signal} /></td>
      {stock.buy_target && <td style={{ fontSize: "0.78rem", color: "var(--color-info)" }}>{stock.buy_target}</td>}
    </tr>
  );
}

// ── 시나리오 섹션 ─────────────────────────────────────────────────────────────
function ScenarioSection({ sc }: { sc: Scenario }) {
  const isA = sc.label === "A";
  return (
    <div
      style={{
        border:       `1px solid ${isA ? "var(--color-up)" : "var(--color-down)"}30`,
        borderRadius: "0.5rem",
        overflow:     "hidden",
        marginBottom: "0.625rem",
      }}
    >
      {/* 헤더 */}
      <div style={{
        background: isA ? "#1a2e1a" : "#2e1a1a",
        padding:    "0.625rem 0.875rem",
        display:    "flex",
        alignItems: "center",
        gap:        "0.625rem",
        flexWrap:   "wrap",
      }}>
        <span style={{
          background: isA ? "var(--color-up)" : "var(--color-down)",
          color: "white", borderRadius: "4px", padding: "1px 8px",
          fontSize: "0.72rem", fontWeight: 700,
        }}>
          시나리오 {sc.label}
        </span>
        <span style={{ fontWeight: 600, fontSize: "0.9rem" }}>{sc.title}</span>
        <DirectionBadge direction={sc.market_direction} />
        <span style={{ color: "var(--color-muted)", fontSize: "0.78rem", marginLeft: "auto" }}>
          확률 {sc.probability_pct}%
        </span>
      </div>

      <div style={{ padding: "0.875rem", background: "var(--color-card)" }}>
        {/* 트리거 + 분석 */}
        <p style={{ fontSize: "0.82rem", color: "var(--color-muted)", marginBottom: "0.375rem" }}>
          🎯 <strong style={{ color: "var(--color-text)" }}>촉발 조건:</strong> {sc.trigger}
        </p>
        <p style={{ fontSize: "0.85rem", color: "var(--color-text)", lineHeight: 1.7, marginBottom: "0.75rem" }}>
          {sc.economic_analysis}
        </p>

        {/* 단타/장타 전략 */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem", marginBottom: "0.75rem" }}>
          <StatusBox type="info">⚡ 단타: {sc.short_strategy}</StatusBox>
          <StatusBox type="warning">📈 장타: {sc.long_strategy}</StatusBox>
        </div>

        {/* 상승 종목 */}
        {sc.rising_stocks?.length > 0 && (
          <Accordion title={<span style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}><TrendingUp size={13} style={{ color: "var(--color-up)" }} />상승 후보 ({sc.rising_stocks.length})</span>}>
            <table className="stockcy-table">
              <thead><tr><th>종목</th><th>이유</th><th>시그널</th><th>매수 타점</th></tr></thead>
              <tbody>{sc.rising_stocks.map((s) => <StockRow key={s.ticker} stock={s} />)}</tbody>
            </table>
          </Accordion>
        )}

        {/* 하락 종목 */}
        {sc.falling_stocks?.length > 0 && (
          <Accordion title={<span style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}><TrendingDown size={13} style={{ color: "var(--color-down)" }} />하락 후보 ({sc.falling_stocks.length})</span>}>
            <table className="stockcy-table">
              <thead><tr><th>종목</th><th>이유</th><th>시그널</th></tr></thead>
              <tbody>{sc.falling_stocks.map((s) => <StockRow key={s.ticker} stock={s} />)}</tbody>
            </table>
          </Accordion>
        )}

        {/* 테마 연동주 */}
        {sc.theme_stocks?.length > 0 && (
          <Accordion title={`🔥 테마 연동주 (${sc.theme_stocks.length})`}>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>
              {sc.theme_stocks.map((s) => (
                <div key={s.ticker} style={{ background: "var(--color-elevated)", borderRadius: "0.375rem", padding: "0.375rem 0.625rem", fontSize: "0.8rem" }}>
                  <span style={{ fontWeight: 600 }}>{s.name}</span>
                  <span style={{ color: "var(--color-muted)", marginLeft: "4px" }}>({s.ticker})</span>
                  <div style={{ marginTop: "2px" }}><SignalBadge signal={s.signal} /></div>
                </div>
              ))}
            </div>
          </Accordion>
        )}
      </div>
    </div>
  );
}

// ── 이슈 아코디언 ──────────────────────────────────────────────────────────────
function IssueAccordion({ issue }: { issue: MacroIssue }) {
  return (
    <Accordion
      title={
        <span style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <span style={{ background: "var(--color-accent)", color: "white", borderRadius: "4px", padding: "1px 7px", fontSize: "0.72rem", fontWeight: 700 }}>
            #{issue.issue_no}
          </span>
          {issue.title}
          <UrgencyBadge urgency={issue.urgency} />
          <Badge variant="muted">{issue.category}</Badge>
        </span>
      }
      defaultOpen={issue.issue_no === 1}
    >
      <p style={{ color: "var(--color-muted)", fontSize: "0.85rem", marginBottom: "0.75rem", lineHeight: 1.6 }}>
        {issue.summary}
      </p>
      {issue.scenarios?.map((sc) => <ScenarioSection key={sc.label} sc={sc} />)}
    </Accordion>
  );
}

// ── 메인 페이지 ───────────────────────────────────────────────────────────────
export default function ScenariosPage() {
  const macro    = useSSE<MarketScenarios>("/api/ai/scenarios");
  const custom   = useSSE<{ title: string; summary: string; scenarios: Scenario[] }>("/api/ai/scenarios/custom", { method: "POST" });
  const [kw, setKw] = useState("");

  const handleCustom = () => {
    if (!kw.trim()) return;
    custom.start({ keyword: kw.trim() });
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>

      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
        <GitBranch size={18} style={{ color: "var(--color-accent)" }} />
        <h1 style={{ fontSize: "1.05rem", fontWeight: 700 }}>시나리오 분석</h1>
      </div>

      {/* ── 오늘의 매크로 시나리오 ─────────────────────────────────── */}
      <Card title={<span style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}><BookOpen size={15} />오늘의 6대 이슈 시나리오</span>}>
        <SSEPanel<MarketScenarios>
          status={macro.status}
          message={macro.message}
          result={macro.result}
          fromCache={macro.fromCache}
          onStart={macro.start}
          startLabel="시나리오 분석 시작"
          idleHint="Google Search 기반으로 오늘의 주요 매크로 이슈 6개에 대한 A/B 시나리오를 자동 분석합니다. (1~2분 소요)"
        >
          {(data) =>
            data.error
              ? <StatusBox type="danger">{data.error}</StatusBox>
              : <div>{data.issues?.map((issue) => <IssueAccordion key={issue.issue_no} issue={issue} />)}</div>
          }
        </SSEPanel>
      </Card>

      {/* ── 커스텀 이슈 분석 ───────────────────────────────────────── */}
      <Card title={<span style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}><Search size={15} />커스텀 이슈 분석</span>}>
        <div style={{ display: "flex", gap: "0.625rem", marginBottom: "1rem" }}>
          <input
            className="stockcy-input"
            style={{ flex: 1 }}
            placeholder="분석할 이슈 키워드 입력 (예: 미중 관세, 반도체 수출 제한, 비트코인 ETF)"
            value={kw}
            onChange={(e) => setKw(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleCustom()}
          />
          <button
            className="stockcy-btn stockcy-btn-primary"
            onClick={handleCustom}
            disabled={!kw.trim() || custom.status === "running"}
            style={{ whiteSpace: "nowrap" }}
          >
            분석
          </button>
        </div>

        {custom.status === "running" && (
          <StatusBox type="info">🔍 [{kw}] 분석 중... {custom.message}</StatusBox>
        )}
        {custom.status === "error" && (
          <StatusBox type="danger">{custom.message}</StatusBox>
        )}
        {custom.status === "done" && custom.result && (
          <IssueAccordion issue={{
            issue_no:  0,
            title:     custom.result.title ?? kw,
            summary:   custom.result.summary ?? "",
            urgency:   "보통",
            category:  "커스텀",
            scenarios: custom.result.scenarios ?? [],
          }} />
        )}
      </Card>
    </div>
  );
}
