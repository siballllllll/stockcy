"use client";
import { TrendingUp, Zap, Users } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { SSEPanel } from "@/components/ui/SSEPanel";
import { Badge, SignalBadge } from "@/components/ui/Badge";
import { StatusBox } from "@/components/ui/StatusBox";
import { Skeleton } from "@/components/ui/LoadingSpinner";
import { useSSE } from "@/hooks/useSSE";
import useSWR from "swr";
import { api } from "@/lib/api";
import type { KrIndices, RankingStock, RealtimePick } from "@/lib/types";

// ── KOSPI/KOSDAQ 지수 타일 ────────────────────────────────────────────────────
function KrIndexTile({ name, data }: { name: string; data: { index: number; change_pct: number } | undefined }) {
  if (!data) return <div className="stockcy-card skeleton" style={{ height: "72px" }} />;
  const up   = data.change_pct > 0;
  const down = data.change_pct < 0;
  const color = up ? "var(--color-up)" : down ? "var(--color-down)" : "var(--color-flat)";
  return (
    <div className="stockcy-card" style={{ textAlign: "center", padding: "0.875rem" }}>
      <div style={{ color: "var(--color-muted)", fontSize: "0.75rem", marginBottom: "4px" }}>{name}</div>
      <div style={{ fontWeight: 700, fontSize: "1.15rem", marginBottom: "2px" }}>
        {data.index.toLocaleString()}
      </div>
      <div style={{ color, fontSize: "0.82rem" }}>
        {up ? "▲" : down ? "▼" : "─"} {Math.abs(data.change_pct).toFixed(2)}%
      </div>
    </div>
  );
}

// ── 랭킹 테이블 ────────────────────────────────────────────────────────────────
function RankingTable({ data, title }: { data: RankingStock[]; title: string }) {
  return (
    <div>
      <p style={{ color: "var(--color-muted)", fontSize: "0.78rem", marginBottom: "0.5rem" }}>{title}</p>
      <table className="stockcy-table">
        <thead>
          <tr>
            <th>#</th>
            <th>종목명</th>
            <th style={{ textAlign: "right" }}>현재가</th>
            <th style={{ textAlign: "right" }}>등락률</th>
            <th style={{ textAlign: "right" }}>거래량</th>
          </tr>
        </thead>
        <tbody>
          {data.slice(0, 10).map((s, i) => {
            const up   = s["등락률(%)"] > 0;
            const down = s["등락률(%)"] < 0;
            const color = up ? "var(--color-up)" : down ? "var(--color-down)" : "var(--color-flat)";
            return (
              <tr key={s["종목코드"]}>
                <td style={{ color: "var(--color-subtle)", fontSize: "0.75rem" }}>{i + 1}</td>
                <td>
                  <span style={{ fontWeight: 500 }}>{s["종목명"]}</span>
                  <span style={{ color: "var(--color-subtle)", fontSize: "0.72rem", marginLeft: "4px" }}>
                    {s["종목코드"]}
                  </span>
                </td>
                <td style={{ textAlign: "right" }}>{s["현재가"]?.toLocaleString()}</td>
                <td style={{ textAlign: "right", color }}>{up ? "+" : ""}{s["등락률(%)"]?.toFixed(2)}%</td>
                <td style={{ textAlign: "right", color: "var(--color-muted)", fontSize: "0.8rem" }}>
                  {(s["거래량"] as number)?.toLocaleString()}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── AI 픽 카드 ────────────────────────────────────────────────────────────────
function PickCard({ pick }: { pick: RealtimePick }) {
  const up   = pick.change_pct > 0;
  const down = pick.change_pct < 0;
  const color = up ? "var(--color-up)" : down ? "var(--color-down)" : "var(--color-flat)";

  return (
    <div className="stockcy-card" style={{ marginBottom: "0.75rem" }}>
      {/* 헤더 */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "0.5rem" }}>
        <div>
          <span style={{ fontWeight: 700, fontSize: "1rem" }}>
            {pick.name}
          </span>
          <span style={{ color: "var(--color-muted)", fontSize: "0.78rem", marginLeft: "6px" }}>{pick.code}</span>
          <Badge variant="info" className="ml-2">{pick.theme}</Badge>
        </div>
        <span style={{
          background: "var(--color-accent)", color: "white",
          borderRadius: "50%", width: "24px", height: "24px",
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: "0.78rem", fontWeight: 700, flexShrink: 0,
        }}>
          {pick.rank}
        </span>
      </div>

      {/* 시세 + 타점 */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "0.5rem", marginBottom: "0.625rem" }}>
        {[
          { label: "현재가",   value: `₩${pick.current_price?.toLocaleString()}`, color },
          { label: "매수 타점", value: `₩${pick.entry?.toLocaleString()}`,         color: "var(--color-info)" },
          { label: "목표가",   value: `₩${pick.target?.toLocaleString()}`,          color: "var(--color-up)" },
          { label: "손절가",   value: `₩${pick.stop?.toLocaleString()}`,            color: "var(--color-down)" },
        ].map((item) => (
          <div key={item.label} style={{ textAlign: "center", background: "var(--color-elevated)", borderRadius: "0.375rem", padding: "0.4rem" }}>
            <div style={{ fontSize: "0.68rem", color: "var(--color-muted)" }}>{item.label}</div>
            <div style={{ fontWeight: 600, fontSize: "0.85rem", color: item.color }}>{item.value}</div>
          </div>
        ))}
      </div>

      {/* 패턴 + 메타 */}
      <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap", marginBottom: "0.5rem" }}>
        <Badge variant="warning">{pick.pattern}</Badge>
        <Badge variant="muted">{pick.horizon}</Badge>
        <Badge variant="muted">{pick.theme_stage}</Badge>
        <Badge variant={pick.supply_signal.includes("유입") || pick.supply_signal.includes("매집") ? "success" : "muted"}>
          {pick.supply_signal}
        </Badge>
      </div>

      {/* 이유 */}
      <p style={{ fontSize: "0.82rem", color: "var(--color-muted)", lineHeight: 1.6 }}>
        {pick.reason}
      </p>
    </div>
  );
}

// ── 메인 페이지 ───────────────────────────────────────────────────────────────
export default function LeadingPage() {
  const { data: kr }   = useSWR<KrIndices>("kr-indices",   () => api.kr.indices() as Promise<KrIndices>,   { refreshInterval: 60000 });
  const { data: volR } = useSWR("kr-vol-rank",  () => api.kr.volumeRanking(), { refreshInterval: 60000 });
  const { data: chgR } = useSWR("kr-chg-rank",  () => api.kr.changeRanking(), { refreshInterval: 60000 });
  const { data: inv }  = useSWR("kr-investor",  () => api.kr.investorTrend(), { refreshInterval: 120000 });

  const picks = useSSE<{ picks: RealtimePick[]; market_condition: string; market_comment: string }>("/api/ai/realtime-picks-kr", { method: "POST" });

  const handlePickStart = () => {
    const marketData = {
      KOSPI:  kr?.KOSPI  ? { index: kr.KOSPI.index,  change_pct: kr.KOSPI.change_pct }  : {},
      KOSDAQ: kr?.KOSDAQ ? { index: kr.KOSDAQ.index, change_pct: kr.KOSDAQ.change_pct } : {},
    };
    picks.start({
      market_data:  marketData,
      volume_rank:  Array.isArray(volR) ? volR : [],
      change_rank:  Array.isArray(chgR) ? chgR : [],
    });
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>

      {/* 페이지 타이틀 */}
      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
        <TrendingUp size={18} style={{ color: "var(--color-accent)" }} />
        <h1 style={{ fontSize: "1.05rem", fontWeight: 700 }}>주도주 분석</h1>
      </div>

      {/* KOSPI / KOSDAQ */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "0.75rem" }}>
        <KrIndexTile name="KOSPI"  data={kr?.KOSPI} />
        <KrIndexTile name="KOSDAQ" data={kr?.KOSDAQ} />
      </div>

      {/* 투 컬럼: 랭킹 테이블 */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
        <Card title="거래량 상위">
          {Array.isArray(volR)
            ? <RankingTable data={volR as RankingStock[]} title="거래량 기준 상위 10종목" />
            : <Skeleton height="200px" />}
        </Card>
        <Card title="등락률 상위">
          {Array.isArray(chgR)
            ? <RankingTable data={chgR as RankingStock[]} title="등락률 기준 상위 10종목" />
            : <Skeleton height="200px" />}
        </Card>
      </div>

      {/* 외국인·기관 수급 */}
      <Card
        title={<span style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}><Users size={15} />외국인·기관 순매수</span>}
      >
        {Array.isArray(inv) ? (
          <table className="stockcy-table">
            <thead>
              <tr>
                <th>종목명</th>
                <th style={{ textAlign: "right" }}>외국인</th>
                <th style={{ textAlign: "right" }}>기관</th>
              </tr>
            </thead>
            <tbody>
              {(inv as Record<string, unknown>[]).slice(0, 10).map((row, i) => (
                <tr key={i}>
                  <td>{String(row["종목명"] ?? "")}</td>
                  <td style={{ textAlign: "right", color: (Number(row["외국인순매수"]) ?? 0) > 0 ? "var(--color-up)" : "var(--color-down)" }}>
                    {Number(row["외국인순매수"])?.toLocaleString()}
                  </td>
                  <td style={{ textAlign: "right", color: (Number(row["기관순매수"]) ?? 0) > 0 ? "var(--color-up)" : "var(--color-down)" }}>
                    {Number(row["기관순매수"])?.toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <Skeleton height="200px" />}
      </Card>

      {/* AI 실시간 픽 */}
      <Card title={<span style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}><Zap size={15} style={{ color: "var(--color-warning)" }} />AI 실시간 픽</span>}>
        <SSEPanel
          status={picks.status}
          message={picks.message}
          result={picks.result}
          fromCache={picks.fromCache}
          onStart={handlePickStart}
          startLabel="AI 픽 분석 시작"
          idleHint="거래량·등락률·수급 데이터를 종합하여 AI가 오늘의 유망 국내 단타 종목 3개를 선정합니다."
        >
          {(data) => (
            <div>
              {data.market_comment && (
                <StatusBox type="info" className="mb-3">
                  {data.market_condition} — {data.market_comment}
                </StatusBox>
              )}
              {data.picks?.map((p) => <PickCard key={p.rank} pick={p} />)}
            </div>
          )}
        </SSEPanel>
      </Card>
    </div>
  );
}
